#!/usr/bin/env python3
"""Person counting test app (DeepStream 6.0.1 + pyds 1.1.1, Python 3.6) — MQTT status heartbeat only.

Tapo RTSP (video only) → rtph264depay → h264parse → nvv4l2decoder → queue
  → nvstreammux 1280x720 → nvinfer [→ nvinfer #2] → nvtracker → nvvideoconvert(RGBA) → nvdsosd [probe on sink pad]
  → nvvideoconvert(I420) → queue → nvv4l2h264enc (Baseline, SPS/PPS on every IDR, IDR every 30) → rtph264pay
  → udpsink 127.0.0.1:<udp-port>
RTSP server (GstRtspServer, same as deepstream-test1-rtsp-out) serves udpsrc <udp-port> at
rtsp://<bind>:<rtsp-port>/<rtsp-path> (default 127.0.0.1:8555/cam01 = the MediaMTX source in dashboard/mediamtx)

Camera credentials come only from the environment (CAM_IP, CAM_USER, CAM_PASS), set by run_person_app.sh,
which sources ~/safety/.cam.env. They go into rtspsrc properties, never into a URL that is printed or logged.

Numbering is done by person_ids.PersonIds (unchanged); this app only feeds it tracker output and draws the result.
Models: two models ("way A", the default, temporary until the next ppe3 passes): --person-config = COCO person only,
320x192 (gie-unique-id 1, --interval applies), --ppe-config = ppe3 helmet / vest only (gie-unique-id 2, its own
interval from the config); or one model (--ppe-config "" and a ppe3 --person-config: 0 person, 1 helmet, 2 vest).
Objects are told apart
by obj_meta.unique_component_id + class_id (obj_route.Router), never class_id alone (both models start at 0).
Only persons go to PersonIds. nvtracker drops the helmet / vest objects, so they are read on the nvtracker sink pad
(ppe_pretrack.PreTrackerPpe, matched to the OSD frame by (frame_num, pts)), given to people by ppe_assign.assign_ppe
and drawn thin through display meta ("H 0.72" / "V 0.65"), so a person label reads "P1 0.87 H✓ V✗".
The number after the label is obj_meta.confidence of that box (person label: the person box, not its helmet / vest);
outside 0..1 (e.g. -0.1 when the tracker carries a box the detector did not give) it shows "--".
Every 5 s the log also has mean / min confidence per class over that window (invalid values counted apart).
H / V on a person label is the steady status from ppe_smooth.PpeSmoother (last 20 frames of that person, ✓ >= 30 %,
✗ < 10 %, keep in between, "?" before 8 frames); "No helmet / No vest" count people with ✗ (not "?").
A person PersonIds holds as hidden for at most --hold seconds keeps the last box (thin line, "P1 -- H✓ V✗").
MQTT: factory/safety/<camera-id>/status every 5 s, QoS 1, retained, LWT {"online":false} (status_mqtt.py,
docs/mqtt_spec.md v3); a clean stop publishes online:false too. --mqtt-host "" turns MQTT off.
Seen in part (violations.vest_judgeable / helmet_judgeable, edges of the real picture, also with --mux-padding):
box at the left / right edge or width / height < 0.25 -> vest "?"; box at the top edge -> helmet "?" (that frame
is not added to that item's PpeSmoother history; no violation from a "?").
Violations (violations.py, spec sections 1, 2, 6): no_helmet / no_vest (✗ held 2 s) and restricted_zone (foot point in
a zone from <cam>/config/zones held 0.5 s) → <cam>/ds/violation, re-sent every 5 s while it lasts. Before every
ds/violation (repeats too) a snapshot of that frame (OSD-drawn, copied at the nvdsosd src pad, 640 px JPEG q80,
snapshot_id = the picture's own time) goes to <cam>/snapshot/<snapshot_id>. While cira/status is missing or
older than 15 s the app also publishes <cam>/event itself (via "fallback", 30 s cooldown per (camera, track_id,
type), event_id = <snapshot_id>-<nh|nv|rz|uv>). JPEG encoding and every publish run in one worker thread (FIFO queue),
so the probe thread only copies the frame and the order snapshot → violation → event is kept.
--events off (default): only status is published — no ds/violation, no event, no snapshot taken; detection, labels,
KPI counts (compliant / violating) work the same. --events on: everything above.
Watchdog: no frame for 3 s (after the first frame of a start), or ERROR/EOS from the camera source
→ pipeline to NULL, wait 2 s, PLAYING again. The RTSP server keeps running.
After --rediscover-after (3) failed reconnects in a row, ~/safety/perception/cam_discover.sh runs in a thread (again every 3 more);
a new camera IP it finds (e.g. phone hotspot gave a new DHCP lease) is set on rtspsrc at the next reconnect.
--source-file <mp4>: filesrc → qtdemux (video only: an audio pad, e.g. AAC, is left unlinked) → h264parse
→ nvv4l2decoder instead of the camera (repeatable tests); --mux-padding keeps the clip's aspect ratio (black bars);
no watchdog / reconnect, the app stops by itself at EOS. Frames are processed as fast as the pipeline can (no
clock sync), so fps is throughput, not the camera rate. Test option --realtime: the clip is played at its own
frame times (identity sync=true before the decoder) and nvstreammux runs as live-source=1, like the camera.
"""
import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections import deque

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GLib, Gst, GstRtspServer  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pyds  # noqa: E402

from person_ids import PersonIds  # noqa: E402
from pts_guard import PtsGuard  # noqa: E402  (v4 A1: PTS retime + camera-reset rebase)
from ppe_pretrack import PreTrackerPpe  # noqa: E402
from ppe_smooth import PpeSmoother  # noqa: E402
from obj_route import HELMET, PERSON, ROLES, VEST, Router, gie_unique_id  # noqa: E402
import status_mqtt  # noqa: E402
import violations as vio  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DS_DIR = os.path.normpath(os.path.join(HERE, ".."))
DS_ROOT = "/opt/nvidia/deepstream/deepstream-6.0"
TRACKER_LIB = DS_ROOT + "/lib/libnvds_nvmultiobjecttracker.so"
TRACKER_CFG = {
    "iou": DS_ROOT + "/samples/configs/deepstream-app/config_tracker_IOU.yml",
    "nvdcf": os.path.join(DS_DIR, "test", "tracker_nvdcf_tuned.yml"),
}
MUX_W, MUX_H = 1280, 720
# thin PPE boxes: (label, RGBA) — helmet white, vest orange
PPE_STYLE = {HELMET: ("H", (1.0, 1.0, 1.0, 1.0)), VEST: ("V", (1.0, 0.55, 0.0, 1.0))}
FPS_SHOW_S = 2.0          # on-screen FPS = frames through the probe in the last 2 s
UNTRACKED = 0xFFFFFFFFFFFFFFFF
NO_FRAME_S = 3.0          # watchdog: no frame for this long → restart
FIRST_FRAME_S = 30.0      # after (re)start: engine load + RTSP setup must give a frame within this
RECONNECT_WAIT_MS = 2000
# camera got a new IP (e.g. phone hotspot DHCP) while running: after --rediscover-after failed reconnects in a row,
# run cam_discover.sh in a thread; a new IP is put into rtspsrc on the next reconnect (pipeline is NULL then)
CAM_DISCOVER = os.path.expanduser("~/safety/perception/cam_discover.sh")
REDISCOVER_LIMIT_S = 20     # CAM_DISCOVER_TIMEOUT for one cam_discover run (its own retry loop)
REDISCOVER_KILL_S = 40      # hard limit: the whole process group is killed after this
FPS_LOG_S = 5
SNAP_W, SNAP_Q = 640, 80          # snapshot JPEG width / quality
SNAP_MAX_BYTES = 2 * 1024 * 1024  # recorder rejects bigger snapshots
PUB_QUEUE = 8                     # pending snapshot / publish jobs; when full, a snapshot is skipped (messages still go)
TOPIC = "factory/safety/"
MAX_HELD = 13             # display meta has 16 labels; 3 are the overlay text lines

# 12 distinct colours (RGBA 0..1). PersonIds gives each person a color_index when they enter (first one nobody
# in the frame uses) and keeps it, so a person keeps the same colour while the on-screen number moves
PALETTE = [
    (0.90, 0.10, 0.10, 1.0),  # red
    (0.10, 0.75, 0.10, 1.0),  # green
    (0.15, 0.35, 1.00, 1.0),  # blue
    (1.00, 0.85, 0.00, 1.0),  # yellow
    (1.00, 0.20, 0.90, 1.0),  # magenta
    (0.00, 0.90, 0.90, 1.0),  # cyan
    (1.00, 0.50, 0.00, 1.0),  # orange
    (0.55, 0.25, 0.90, 1.0),  # purple
    (0.60, 1.00, 0.20, 1.0),  # lime
    (1.00, 0.60, 0.70, 1.0),  # pink
    (0.55, 0.35, 0.15, 1.0),  # brown
    (1.00, 1.00, 1.00, 1.0),  # white
]


def log(msg):
    print("%s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def ppe_marks():
    """("✓", "✗") if an installed font has both glyphs (Pango falls back to it), else ("+", "-")."""
    try:
        out = subprocess.check_output(["fc-list", ":charset=2713 2717", "family"], stderr=subprocess.DEVNULL)
        if out.strip():
            return u"✓", u"✗"
    except (OSError, subprocess.CalledProcessError):
        pass
    return "+", "-"


def valid_conf(c):
    """Detector confidence in 0..1; the tracker writes -0.1 for a box it carries without a detection (NaN fails too)."""
    return 0.0 <= c <= 1.0


def conf_text(c):
    return "%.2f" % c if valid_conf(c) else "--"


class ObjCounter(object):
    """DEBUG (temporary, D2): count obj_meta by (unique_component_id, class_id) at one pad, per log window."""

    def __init__(self, dump=None):
        self._lock = threading.Lock()
        self._dump = dump    # open file: one JSON line per frame {"f", "pts", "o": [[comp, class, conf, l, t, w, h], ...]}
        self._win = {}
        self._frames = 0
        self._par = {}       # key -> [frames with key at even frame_num, at odd frame_num]
        self._fpar = [0, 0]  # all frames by frame_num parity

    def add_frame(self, frame_meta):
        keys, objs = [], []
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            obj = pyds.NvDsObjectMeta.cast(l_obj.data)
            keys.append((obj.unique_component_id, obj.class_id))
            r = obj.rect_params   # box in nvstreammux pixels (1280x720)
            objs.append([obj.unique_component_id, obj.class_id, round(obj.confidence, 3),
                         round(r.left, 1), round(r.top, 1), round(r.width, 1), round(r.height, 1)])
            l_obj = l_obj.next
        par = frame_meta.frame_num % 2
        with self._lock:
            if self._dump is not None:
                self._dump.write(json.dumps({"f": frame_meta.frame_num, "pts": round(frame_meta.buf_pts / 1e9, 3),
                                             "o": objs}) + "\n")
            self._frames += 1
            self._fpar[par] += 1
            for k in keys:
                self._win[k] = self._win.get(k, 0) + 1
            for k in set(keys):
                self._par.setdefault(k, [0, 0])[par] += 1

    def take_window(self):
        with self._lock:
            w, f, par, fpar = self._win, self._frames, self._par, self._fpar
            self._win, self._frames, self._par, self._fpar = {}, 0, {}, [0, 0]
        # "(1,0)=52[e30/o22]" = 52 objects; frames having one: 30 with even frame_num, 22 with odd
        return "frames=%d[e%d/o%d] %s" % (f, fpar[0], fpar[1], " ".join(
            "(%d,%d)=%d[e%d/o%d]" % (k[0], k[1], w[k], par[k][0], par[k][1]) for k in sorted(w)) or "none")


class ConfStats(object):
    """Per-role (person / helmet / vest) confidence stats: n valid, sum, min, n invalid. Filled by the probe thread, read by the log timer."""

    def __init__(self):
        self._lock = threading.Lock()
        self._win = self._new()
        self.total = self._new()

    @staticmethod
    def _new():
        return dict((k, [0, 0.0, None, 0]) for k in ROLES)

    def add(self, role, c):
        with self._lock:
            for d in (self._win, self.total):
                a = d.get(role)
                if a is None:
                    continue
                if valid_conf(c):
                    a[0] += 1
                    a[1] += c
                    a[2] = c if a[2] is None else min(a[2], c)
                else:
                    a[3] += 1

    def take_window(self):
        with self._lock:
            w, self._win = self._win, self._new()
        return w

    @staticmethod
    def describe(d):
        parts = []
        for name in ROLES:
            n, s, mn, bad = d[name]
            if n:
                parts.append("%s n=%d mean=%.2f min=%.2f inv=%d" % (name, n, s / n, mn, bad))
            else:
                parts.append("%s n=0 mean=-- min=-- inv=%d" % (name, bad))
        return "  |  ".join(parts)

    @staticmethod
    def as_json(d):
        out = {}
        for name in ROLES:
            n, s, mn, bad = d[name]
            out[name] = {"n": n, "mean": round(s / n, 3) if n else None,
                         "min": round(mn, 3) if mn is not None else None, "invalid": bad}
        return out


def make(factory, name, **props):
    e = Gst.ElementFactory.make(factory, name)
    if e is None:
        raise RuntimeError("cannot create element %s (%s)" % (factory, name))
    for k, v in props.items():
        e.set_property(k.replace("_", "-"), v)
    return e


class App(object):
    def __init__(self, args):
        self.args = args
        self.cam_ip = os.environ.get("CAM_IP", "")
        self.cam_user = os.environ.get("CAM_USER", "")
        self.cam_pass = os.environ.get("CAM_PASS", "")
        if args.source_file:
            self.safe_url = "file:" + args.source_file
        else:
            if not (self.cam_ip and self.cam_user and self.cam_pass):
                raise SystemExit("CAM_IP/CAM_USER/CAM_PASS not set (start with run_person_app.sh)")
            self.safe_url = "rtsp://***@%s:554/stream%d" % (self.cam_ip, args.stream)

        self.mgr = PersonIds(MUX_W, MUX_H, edge_margin=args.edge_margin, hidden_ttl_s=args.hidden_ttl,
                             edge_ttl_s=args.edge_ttl, regrace_s=args.regrace, n_colors=len(PALETTE))
        os.makedirs(args.out_dir, exist_ok=True)
        self.events_path = os.path.join(args.out_dir, args.run_name + "_events.jsonl")
        self.summary_path = os.path.join(args.out_dir, args.run_name + "_summary.json")
        self.events_f = open(self.events_path, "w")
        self.event_counts = {"enter": 0, "exit": 0, "rejoin": 0, "renumber": 0}

        # frame / time bookkeeping (probe runs in a streaming thread; plain attributes are fine under the GIL)
        self.frames = 0
        self.last_frame_mono = None
        self.started_mono = None
        self.got_first_frame = False
        self.t_offset = 0.0        # keeps PersonIds time continuous across restarts (pts restarts from ~0)
        self.last_t = None
        self.need_rebase = False
        self.last_in_frame = 0
        self.last_detected = 0
        self.last_no_helmet = 0
        self.last_no_vest = 0
        self.last_ppe = None       # v7.1: status_mqtt.ppe_breakdown() of the people seen in the last frame
        self.mark_yes, self.mark_no = ppe_marks()
        self.conf = ConfStats()
        # DEBUG (temporary, D2): obj_meta per (component, class) before the tracker and at the OSD probe
        self.dbg_dump = open(os.path.join(args.out_dir, args.run_name + "_objs.jsonl"), "w") \
            if args.debug_objs else None
        self.dbg_pre = ObjCounter(self.dbg_dump) if args.debug_objs else None
        # DEBUG: per OSD frame, each labelled person [uid, helmet, vest (1 / 0 / null = ?), box height px]
        self.dbg_ppe = open(os.path.join(args.out_dir, args.run_name + "_ppe.jsonl"), "w") \
            if args.debug_objs else None
        self.dbg_osd = ObjCounter() if args.debug_objs else None
        self.person_gie = gie_unique_id(args.person_config)
        self.ppe_gie = gie_unique_id(args.ppe_config) if args.ppe_config else None
        self.router = Router(self.person_gie, self.ppe_gie)
        self.ppe_smooth = PpeSmoother()
        self.ppe_pre = PreTrackerPpe()
        self.last_held = 0
        self._show_times = deque()  # monotonic time of each frame in the last FPS_SHOW_S (on-screen FPS)
        # MQTT status: frames out of the decoder (= camera rate), camera size, people by PPE state
        self.frames_in = 0
        self.resolution = None
        self.last_compliant = 0
        self.last_violating = 0
        self._status_last = (time.monotonic(), 0, 0)   # (time, frames_in, frames) at the last status
        self._status_fps = (0.0, 0.0)                  # (fps_in, fps through the OSD probe) of the last window
        self.mqtt = None
        # violations / snapshots / fallback events
        self.viol = vio.ViolationTracker(hold_s={vio.NO_VEST: args.vest_hold},
                                         zone_mode=args.zone_mode, zone_overlap=args.zone_overlap)
        self._content = None       # picture rect inside the mux frame (mux px), known after the first decoded frame
        self._vest_partial = set()  # uids cut at the left / right edge or too narrow in the last frame: vest "?"
        self._helmet_partial = set()  # uids cut at the top edge in the last frame: helmet "?"
        self.fallback = vio.Fallback()
        self._mode_lock = threading.Lock()
        self.pub_q = queue.Queue(maxsize=PUB_QUEUE)
        self._snap_req = None      # (snapshot ids, messages): set by the OSD sink probe, taken by the OSD src probe
        self.worker = threading.Thread(target=self._worker, name="publish", daemon=True)
        self.stats = {"violations": {}, "events": 0, "snapshots": 0, "snap_skipped": 0, "snap_bytes": [],
                      "encode_ms": [], "event_ids_dup": 0, "mode_switches": []}
        self._event_ids = set()
        self._last_conf = {}       # uid -> last valid person-box confidence
        self._snaps_win = 0        # snapshots encoded in the current fps log window

        self.restarting = False
        self.restarts = []         # [(wall time, reason)]
        self.fail_streak = 0       # restarts since the last first frame (reset by the probe)
        self._discovering = False  # a cam_discover thread is running
        self._new_ip = None        # IP found by cam_discover, applied in _play
        self.ip_changes = []       # [(wall time, old ip, new ip)]
        self.fps_samples = []
        self._fps_last = (time.monotonic(), 0)
        self._fps_skip = True      # the first 5 s window after a (re)start is partial: not in the stats
        self._pts_guard = PtsGuard()   # v4 A1: non-decreasing PTS + rebase on camera stream reset

        self.loop = GLib.MainLoop()
        self.pipeline = self._build_pipeline()
        self.server = self._start_rtsp_server()

    # ---- pipeline ----------------------------------------------------------------------------------
    def _build_pipeline(self):
        a = self.args
        p = Gst.Pipeline.new("person-count")
        parse = make("h264parse", "parse")
        self.parse = parse
        if a.source_file:
            self.src = make("filesrc", "file", location=a.source_file)
            # --realtime (test): hold each frame until its time, so frames arrive like from the camera
            self.pace = make("identity", "pace", sync=True) if a.realtime else None
            self.depay = make("qtdemux", "demux")      # first element after the source; video pad → parse
            self.depay.connect("pad-added", self._on_demux_pad)
        else:
            self.src = make("rtspsrc", "cam", location="rtsp://%s:554/stream%d" % (self.cam_ip, a.stream),
                            user_id=self.cam_user, user_pw=self.cam_pass, latency=200, drop_on_latency=True)
            Gst.util_set_object_arg(self.src, "protocols", "tcp")   # flags property: set by nick, TCP only
            self.src.connect("select-stream", self._on_select_stream)
            self.src.connect("pad-added", self._on_pad_added)
            self.depay = make("rtph264depay", "depay")
        dec = make("nvv4l2decoder", "dec")
        q_dec = make("queue", "q_dec", leaky=0, max_size_buffers=4, max_size_bytes=0, max_size_time=0)
        mux = make("nvstreammux", "mux", width=MUX_W, height=MUX_H, batch_size=1,
                   live_source=0 if (a.source_file and not a.realtime) else 1,
                   batched_push_timeout=40000, enable_padding=1 if a.mux_padding else 0)
        infer = make("nvinfer", "infer", config_file_path=a.person_config, interval=a.interval)
        # second model: its interval comes from its own config (not overridden here)
        infer2 = make("nvinfer", "infer_ppe", config_file_path=a.ppe_config) if a.ppe_config else None
        infers = [infer] + ([infer2] if infer2 is not None else [])
        if a.ppe_first and infer2 is not None:
            infers.reverse()       # test only: ppe nvinfer before the person nvinfer (gie ids unchanged)
        trk = make("nvtracker", "tracker", ll_lib_file=TRACKER_LIB, ll_config_file=TRACKER_CFG[a.tracker],
                   tracker_width=640, tracker_height=384, enable_batch_process=1, enable_past_frame=1,
                   display_tracking_id=0)
        conv1 = make("nvvideoconvert", "conv_rgba")
        caps1 = make("capsfilter", "caps_rgba",
                     caps=Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA"))
        osd = make("nvdsosd", "osd")
        conv2 = make("nvvideoconvert", "conv_i420")
        caps2 = make("capsfilter", "caps_i420",
                     caps=Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))
        q_enc = make("queue", "q_enc", leaky=0, max_size_buffers=4, max_size_bytes=0, max_size_time=0)
        # Baseline (no B-frames) + SPS/PPS before every IDR + IDR every 30 frames: WebRTC players (MediaMTX WHEP)
        # can start decoding at most 1 s after joining. insert_vui=1 writes the VUI reorder info in the SPS so
        # MediaMTX v1.9.3 stops guessing the stream may reorder and refusing it as "H264 with B-frames".
        enc = make("nvv4l2h264enc", "enc", bitrate=2000000, iframeinterval=30, idrinterval=30, insert_sps_pps=1, insert_vui=1)
        Gst.util_set_object_arg(enc, "profile", "0")   # enum property: 0 = Baseline
        # h264parse re-stamps the AU (clean DTS). SPS/PPS are re-sent with every IDR by rtph264pay below
        # (config_interval=-1), so parse2 no longer duplicates that (v3 A4: cut the duplicate config-interval).
        parse2 = make("h264parse", "parse2")
        # config_interval=-1: re-send SPS/PPS in the RTP with every IDR (default 0 = only once at start, so a
        # WebRTC viewer joining later saw "non-existing PPS 0" and could not decode).
        # ssrc fixed (not the default random): on a camera reboot the pipeline restarts (NULL->PLAYING) and
        # rtph264pay would otherwise pick a NEW random ssrc. MediaMTX's RTSP source locks onto the first ssrc
        # and drops every packet with a different one ("received packet with wrong SSRC") -> the live view
        # freezes until mediamtx is restarted. A constant ssrc keeps MediaMTX on the same source across our
        # restart; PtsGuard.restart() keeps the RTP timestamp monotonic so the stream resumes cleanly.
        pay = make("rtph264pay", "pay", pt=96, config_interval=-1, ssrc=2779096485)
        udp = make("udpsink", "udp", host="127.0.0.1", port=a.udp_port, sync=False, **{"async": False})

        pace = [self.pace] if a.source_file and self.pace is not None else []
        for e in [self.src, self.depay, parse] + pace + [dec, q_dec, mux] + infers + [trk, conv1, caps1, osd, conv2, caps2,
                                                                       q_enc, enc, parse2, pay, udp]:
            p.add(e)
        if a.source_file:
            after_parse = pace + [dec]
            ok = self.src.link(self.depay) and parse.link(after_parse[0]) and dec.link(q_dec)  # demux → parse: pad-added
            if ok and pace:
                ok = self.pace.link(dec)
        else:
            ok = self.depay.link(parse) and parse.link(dec) and dec.link(q_dec)
        if not ok:
            raise RuntimeError("link source → parse → dec → queue failed")
        if q_dec.get_static_pad("src").link(mux.get_request_pad("sink_0")) != Gst.PadLinkReturn.OK:
            raise RuntimeError("link queue → nvstreammux failed")
        chain = [mux] + infers + [trk, conv1, caps1, osd, conv2, caps2, q_enc, enc, parse2, pay, udp]
        for x, y in zip(chain, chain[1:]):
            if not x.link(y):
                raise RuntimeError("link %s → %s failed" % (x.get_name(), y.get_name()))

        osd.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, self._osd_probe, None)
        osd.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self._osd_src_probe, None)
        dec.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self._dec_probe, None)
        pay.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, self._pay_pts_probe, None)  # v3 A1
        trk.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, self._pre_trk_probe, None)
        if a.debug_objs:   # DEBUG (temporary, D2)
            trk.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, self._dbg_pre_probe, None)
        bus = p.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus)
        return p

    def _on_select_stream(self, src, num, caps):
        s = caps.get_structure(0)
        media = s.get_string("media") if s is not None else None
        return media == "video"     # never SETUP the PCMA audio stream

    def _on_pad_added(self, src, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        s = caps.get_structure(0)
        if s.get_string("media") != "video":
            return
        sink = self.depay.get_static_pad("sink")
        if sink.is_linked():
            return
        if pad.link(sink) != Gst.PadLinkReturn.OK:
            log("ERROR: cannot link rtspsrc video pad to depay")

    def _on_demux_pad(self, demux, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        name = caps.get_structure(0).get_name()
        sink = self.parse.get_static_pad("sink")
        if not name.startswith("video/x-h264") or sink.is_linked():
            return                 # audio (e.g. AAC) and extra pads stay unlinked: video only
        if pad.link(sink) != Gst.PadLinkReturn.OK:
            log("ERROR: cannot link qtdemux video pad to h264parse")

    def _start_rtsp_server(self):
        a = self.args
        server = GstRtspServer.RTSPServer.new()
        server.set_address(a.rtsp_bind)
        server.props.service = str(a.rtsp_port)
        factory = GstRtspServer.RTSPMediaFactory.new()
        factory.set_launch(
            '( udpsrc name=pay0 port=%d buffer-size=524288 caps="application/x-rtp, media=video, '
            'clock-rate=90000, encoding-name=(string)H264, payload=96 " )' % a.udp_port)
        factory.set_shared(True)
        server.get_mount_points().add_factory("/" + a.rtsp_path, factory)
        if server.attach(None) == 0:
            raise RuntimeError("RTSP server could not bind %s:%d" % (a.rtsp_bind, a.rtsp_port))
        log("RTSP out: rtsp://%s:%d/%s (udp %d)" % (a.rtsp_bind, a.rtsp_port, a.rtsp_path, a.udp_port))
        return server

    # ---- probe -------------------------------------------------------------------------------------
    def _pay_pts_probe(self, pad, info, _):
        """v4 A1: retime PTS just before rtph264pay via PtsGuard. A small backward wobble is nudged
        +1 ms; a large backward step (>200 ms) or forward jump (>2 s) in the source PTS means the camera
        reset its stream, so the guard rebases a running offset to continue ~one frame after the last
        emitted PTS (never pinned at 1 ms/frame as v3 did). See pts_guard.py."""
        buf = info.get_buffer()
        if buf is None:
            return Gst.PadProbeReturn.OK
        pts = buf.pts
        if pts == Gst.CLOCK_TIME_NONE:
            return Gst.PadProbeReturn.OK
        adj = self._pts_guard.feed(int(pts))
        buf.pts = adj
        if buf.dts == Gst.CLOCK_TIME_NONE or buf.dts > adj:
            buf.dts = adj
        return Gst.PadProbeReturn.OK

    def _dec_probe(self, pad, info, _):
        """Count decoded frames (fps_in) and read the camera frame size from the first one."""
        self.frames_in += 1
        if self.resolution is None:
            caps = pad.get_current_caps()
            s = caps.get_structure(0) if caps is not None else None
            if s is not None:
                ok_w, w = s.get_int("width")
                ok_h, h = s.get_int("height")
                if ok_w and ok_h:
                    self.resolution = "%dx%d" % (w, h)
        return Gst.PadProbeReturn.OK

    def _pre_trk_probe(self, pad, info, _):
        """Before nvtracker: keep this frame's helmet / vest boxes (the tracker drops them) for the OSD probe."""
        buf = info.get_buffer()
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buf)) if buf is not None else None
        if not batch_meta:
            return Gst.PadProbeReturn.OK
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            fm = pyds.NvDsFrameMeta.cast(l_frame.data)
            helmets, vests = [], []
            l_obj = fm.obj_meta_list
            while l_obj is not None:
                obj = pyds.NvDsObjectMeta.cast(l_obj.data)
                role = self.router.role(obj.unique_component_id, obj.class_id)
                if role == HELMET or role == VEST:
                    r = obj.rect_params
                    (helmets if role == HELMET else vests).append((r.left, r.top, r.width, r.height, obj.confidence))
                    self.conf.add(role, obj.confidence)
                l_obj = l_obj.next
            self.ppe_pre.put((fm.frame_num, fm.buf_pts), helmets, vests)
            l_frame = l_frame.next
        return Gst.PadProbeReturn.OK

    def _dbg_pre_probe(self, pad, info, _):
        """DEBUG (temporary, D2): count objects leaving the nvinfer(s), before nvtracker."""
        buf = info.get_buffer()
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buf)) if buf is not None else None
        if batch_meta:
            l_frame = batch_meta.frame_meta_list
            while l_frame is not None:
                self.dbg_pre.add_frame(pyds.NvDsFrameMeta.cast(l_frame.data))
                l_frame = l_frame.next
        return Gst.PadProbeReturn.OK

    def _osd_probe(self, pad, info, _):
        buf = info.get_buffer()
        if buf is None:
            return Gst.PadProbeReturn.OK
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buf))
        if not batch_meta:
            return Gst.PadProbeReturn.OK
        now = time.monotonic()
        pts_s = buf.pts / 1e9 if buf.pts != Gst.CLOCK_TIME_NONE else now
        if self.need_rebase or self.last_t is None:
            # first frame of a (re)start: continue from the last time used, plus the real gap
            gap = (now - self.last_frame_mono) if self.last_frame_mono is not None else 0.0
            base = (self.last_t + gap) if self.last_t is not None else 0.0
            self.t_offset = base - pts_s
            self.need_rebase = False
        t = self.t_offset + pts_s
        if self.last_t is not None and t < self.last_t:
            t = self.last_t        # never let time go backwards
        self.last_t = t
        self.last_frame_mono = now
        if not self.got_first_frame:
            self.got_first_frame = True
            self.fail_streak = 0
            log("first frame (start %.1f s ago)" % (now - self.started_mono))

        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            self.frames += 1
            if self.dbg_osd is not None:   # DEBUG (temporary, D2): before the Router
                self.dbg_osd.add_frame(frame_meta)
            self._show_times.append(now)
            while self._show_times and now - self._show_times[0] > FPS_SHOW_S:
                self._show_times.popleft()
            objs, roles, dets, confs = [], [], [], {}
            l_obj = frame_meta.obj_meta_list
            while l_obj is not None:
                obj = pyds.NvDsObjectMeta.cast(l_obj.data)
                objs.append(obj)
                role = self.router.role(obj.unique_component_id, obj.class_id)
                roles.append(role)
                if role == PERSON:         # helmet / vest confidence is counted before the tracker
                    self.conf.add(role, obj.confidence)
                r = obj.rect_params
                if role == PERSON and obj.object_id != UNTRACKED:
                    dets.append((obj.object_id, (r.left, r.top, r.width, r.height)))
                    confs[obj.object_id] = obj.confidence
                l_obj = l_obj.next

            out = self.mgr.update(t, dets)
            # PPE only for people detected in this frame (they are the ones with a label)
            boxes = dict(dets)
            persons = [(oid, boxes[oid]) for oid in sorted(out.labels, key=lambda k: out.labels[k][0])
                       if oid in boxes]
            ppe, helmets, vests = self.ppe_pre.assign((frame_meta.frame_num, frame_meta.buf_pts), persons)
            rect = self._picture_rect()
            v_partial, h_partial = set(), set()
            for oid, box in persons:
                uid = out.labels[oid][1]
                has_h, has_v = ppe[oid]
                if not vio.vest_judgeable(box, rect, self.args.partial_edge, self.args.partial_aspect):
                    v_partial.add(uid)   # cut at the left / right edge or too narrow: vest "?"
                    has_v = None
                if not vio.helmet_judgeable(box, rect, self.args.partial_edge):
                    h_partial.add(uid)   # cut at the top edge (head may be out of view): helmet "?"
                    has_h = None
                self.ppe_smooth.update(uid, has_h, has_v)
            self._vest_partial, self._helmet_partial = v_partial, h_partial
            people = self.mgr.people
            self.ppe_smooth.forget(list(people) + [q.uid for q in self.mgr.recently_exited])
            states = [self._ppe_state(uid) for uid in people]
            self.last_no_helmet = sum(1 for h, _ in states if h is False)
            self.last_no_vest = sum(1 for _, v in states if v is False)
            # violations: people seen in this frame, with the same smoothed ✓ / ✗ / ? as their labels
            seen = []
            for oid, (bl, bt, bw, bh) in persons:
                uid = out.labels[oid][1]
                h, v = self._ppe_state(uid)
                c = confs.get(oid, -1.0)
                if valid_conf(c):          # a box the tracker carries has -0.1: keep the last detector value
                    self._last_conf[uid] = c
                seen.append(vio.Person(uid, (bl / MUX_W, bt / MUX_H, bw / MUX_W, bh / MUX_H),
                                       self._last_conf.get(uid, 0.0), h, v))
            for uid in [u for u in self._last_conf if u not in people]:
                del self._last_conf[uid]
            found = self.viol.update(t, seen, list(people))
            if self.dbg_ppe is not None:
                b = lambda x: None if x is None else int(x)  # noqa: E731
                self.dbg_ppe.write(json.dumps({"f": frame_meta.frame_num, "t": round(t, 3), "p": [
                    [p.uid, b(p.helmet), b(p.vest), round(p.bbox[3] * MUX_H, 1)] for p in seen]}) + "\n")
            self.last_compliant, self.last_violating = self.viol.compliant, self.viol.violating
            self.last_ppe = status_mqtt.ppe_breakdown([(p.helmet, p.vest) for p in seen])
            if found and self.args.events == "on":
                self._on_violations(t, found)
            held = [q for q in people.values()
                    if q.hidden_since is not None and t - q.hidden_since <= self.args.hold][:MAX_HELD]
            self.last_held = len(held)
            for obj, role in zip(objs, roles):
                tp = obj.text_params
                lab = out.labels.get(obj.object_id) if role == PERSON else None
                if lab is None:            # not a counted person: hide box and text
                    obj.rect_params.border_width = 0
                    tp.display_text = ""
                    continue
                number = lab[0]
                c = PALETTE[lab.color_index % len(PALETTE)]
                obj.rect_params.border_width = 3
                obj.rect_params.border_color.set(*c)
                tp.display_text = "P%d %s %s" % (number, conf_text(obj.confidence), self._ppe_text(lab[1]))
                tp.font_params.font_name = "Serif"
                tp.font_params.font_size = 14
                tp.font_params.font_color.set(0.0, 0.0, 0.0, 1.0)
                tp.set_bg_clr = 1
                tp.text_bg_clr.set(*c)

            for kind, uid, number in out.events:
                self.event_counts[kind] = self.event_counts.get(kind, 0) + 1
                self.events_f.write(json.dumps({
                    "t": round(t, 3), "wall": time.strftime("%H:%M:%S"), "event": kind, "uid": uid,
                    "number": number, "in_frame": out.in_frame, "detected": out.detected,
                    "box": [round(v, 1) for v in out.event_boxes.get(uid, ())]}) + "\n")
            for uid, old, new in out.renumbered:
                self.event_counts["renumber"] = self.event_counts.get("renumber", 0) + 1
                self.events_f.write(json.dumps({
                    "t": round(t, 3), "wall": time.strftime("%H:%M:%S"), "event": "renumber", "uid": uid,
                    "old_number": old, "new_number": new, "in_frame": out.in_frame, "detected": out.detected}) + "\n")
            if out.events or out.renumbered:
                self.events_f.flush()
            self.last_in_frame, self.last_detected = out.in_frame, out.detected
            self._draw_overlay(batch_meta, frame_meta, out, held)
            self._draw_ppe(batch_meta, frame_meta, [(HELMET, b) for b in helmets] + [(VEST, b) for b in vests])
            l_frame = l_frame.next
        return Gst.PadProbeReturn.OK

    # ---- violations / snapshots / fallback events ---------------------------------------------------
    def _check_mode(self, now):
        """cira / fallback for this moment; logs every switch (probe thread and main loop both call it)."""
        with self._mode_lock:
            sw = self.fallback.switched(now)
            mode = self.fallback.last_mode
        if sw is not None:
            old, new = sw
            self.stats["mode_switches"].append([time.strftime("%H:%M:%S"), old, new])
            log("MODE %s -> %s (cira/status %s)" % (old or "start", new, "fresh" if new == "cira" else
                                                       "missing or older than %.0f s" % vio.CIRA_STALE_S))
        return mode

    def _on_violations(self, t, found):
        """Probe thread: decide cira / fallback and the cooldown now; the OSD src probe of this same buffer then
        takes the picture, names it by its own time and builds the messages (snapshot → violation → event)."""
        mode = self._check_mode(time.time())
        items = []
        for v in found:
            event = mode == "fallback" and self.fallback.allow(self.args.camera_id, v.uid, v.type, time.time())
            items.append((t, v, mode, event))
        self._snap_req = items

    def _enqueue(self, job):
        try:
            self.pub_q.put_nowait(job)
        except queue.Full:
            if job[0] == "snap":   # never drop messages: send them without the picture
                self.stats["snap_skipped"] += 1
                log("WARNING: publish queue full, snapshot %s skipped" % ",".join(job[2]))
                self.pub_q.put(("msgs", None, None, job[3]))
            else:
                self.pub_q.put(job)

    def _osd_src_probe(self, pad, info, _):
        """After nvdsosd (boxes drawn): copy the RGBA frame for this frame's violations; encoding is in the worker.
        Every ds/violation (repeats too) and every fallback event gets a picture of this frame, named by its time;
        several violations in one frame share it (one picture per person)."""
        items, self._snap_req = self._snap_req, None
        if not items:
            return Gst.PadProbeReturn.OK
        frame = None
        buf = info.get_buffer()
        now = time.time()
        try:
            batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buf))
            fm = pyds.NvDsFrameMeta.cast(batch_meta.frame_meta_list.data)
            surf = pyds.get_nvds_buf_surface(hash(buf), fm.batch_id)
            frame = np.array(surf, copy=True, order="C")
            if hasattr(pyds, "unmap_nvds_buf_surface"):
                pyds.unmap_nvds_buf_surface(hash(buf), fm.batch_id)
        except Exception as e:     # noqa: BLE001 — a lost picture must not stop the messages
            log("WARNING: snapshot frame copy failed: %s" % e)
        cam = self.args.camera_id
        snap_ids, msgs = [], []
        for t, v, mode, event in items:
            sid = vio.make_id(cam, now, v.uid) if frame is not None else None
            if sid is not None and sid not in snap_ids:
                snap_ids.append(sid)
            self.stats["violations"][v.type] = self.stats["violations"].get(v.type, 0) + 1
            msgs.append((TOPIC + cam + "/ds/violation", json.dumps(vio.violation_msg(cam, v, now, sid))))
            ev = None
            if event:
                ev = vio.event_msg(cam, v, now, sid)
                if ev["event_id"] in self._event_ids:
                    self.stats["event_ids_dup"] += 1
                    log("WARNING: event_id %s already used (recorder keeps the first one)" % ev["event_id"])
                self._event_ids.add(ev["event_id"])
                self.stats["events"] += 1
                msgs.append((TOPIC + cam + "/event", json.dumps(ev)))
            log("VIOL t=%.1f %s uid=%d repeat=%d conf=%.2f zone=%s snap=%s mode=%s%s" % (
                t, v.type, v.uid, v.repeat, v.conf, v.zone_id or "-", sid, mode,
                " event=%s" % ev["event_id"] if ev else ""))
        if frame is None:
            self._enqueue(("msgs", None, None, msgs))
        else:
            self._enqueue(("snap", frame, snap_ids, msgs))
        return Gst.PadProbeReturn.OK

    def _encode(self, rgba):
        h, w = rgba.shape[:2]
        small = cv2.resize(rgba, (SNAP_W, int(round(h * SNAP_W / float(w)))), interpolation=cv2.INTER_AREA)
        bgr = cv2.cvtColor(small, cv2.COLOR_RGBA2BGR)
        q = SNAP_Q
        while True:
            ok, jpg = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
            if not ok:
                return None
            data = jpg.tobytes()
            if len(data) <= SNAP_MAX_BYTES or q <= 40:
                return data if len(data) <= SNAP_MAX_BYTES else None
            q -= 10

    def _publish(self, topic, payload):
        if self.mqtt is not None:
            self.mqtt.publish(topic, payload, qos=1, retain=False)

    def _worker(self):
        """One thread, FIFO: snapshot JPEG(s) first, then the violation / event messages of the same job."""
        while True:
            job = self.pub_q.get()
            if job is None:
                return
            kind, frame, snap_ids, msgs = job
            try:
                if kind == "snap":
                    t0 = time.monotonic()
                    data = self._encode(frame)
                    ms = (time.monotonic() - t0) * 1000.0
                    if data is None:
                        log("WARNING: snapshot encode failed / too big: %s" % ",".join(snap_ids))
                    else:
                        for sid in snap_ids:
                            self._publish(TOPIC + self.args.camera_id + "/snapshot/" + sid, data)
                            self.stats["snapshots"] += 1
                            self.stats["snap_bytes"].append(len(data))
                        self.stats["encode_ms"].append(round(ms, 1))
                        self._snaps_win += 1
                        log("SNAP %s %d bytes %dx%d encode %.0f ms" % (",".join(snap_ids), len(data), SNAP_W,
                                                                     int(round(frame.shape[0] * SNAP_W / float(frame.shape[1]))), ms))
                for topic, payload in msgs:
                    self._publish(topic, payload)
            except Exception as e:  # noqa: BLE001 — keep the worker alive
                log("ERROR in publish worker: %s" % e)

    def _picture_rect(self):
        """The real picture inside the mux frame (with --mux-padding the black bars are left out)."""
        if self._content is None:
            if self.resolution is None:
                return 0.0, 0.0, float(MUX_W), float(MUX_H)
            w, h = (int(x) for x in self.resolution.split("x"))
            self._content = vio.content_rect(w, h, MUX_W, MUX_H, self.args.mux_padding)
            log("picture rect in the mux frame: %s" % ", ".join("%.1f" % v for v in self._content))
        return self._content

    def _ppe_state(self, uid):
        """(helmet, vest) as used for labels, counts and violations: "?" for an item that may be out of view."""
        h, v = self.ppe_smooth.status(uid)
        return (None if uid in self._helmet_partial else h), (None if uid in self._vest_partial else v)

    def _ppe_text(self, uid):
        h, v = self._ppe_state(uid)
        mark = lambda x: "?" if x is None else (self.mark_yes if x else self.mark_no)  # noqa: E731
        return "H%s V%s" % (mark(h), mark(v))

    def _draw_ppe(self, batch_meta, frame_meta, items):
        """Helmet / vest boxes from before the tracker: thin box + "H 0.72" / "V 0.65", 16 per display meta."""
        for i in range(0, len(items), 16):
            chunk = items[i:i + 16]
            dm = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
            dm.num_rects = dm.num_labels = len(chunk)
            for j, (role, (l, t, w, h, conf)) in enumerate(chunk):
                text, c = PPE_STYLE[role]
                rp = dm.rect_params[j]
                rp.left, rp.top, rp.width, rp.height = l, t, w, h
                rp.border_width = 1
                rp.border_color.set(*c)
                rp.has_bg_color = 0
                tp = dm.text_params[j]
                tp.display_text = "%s %s" % (text, conf_text(conf))
                tp.x_offset, tp.y_offset = int(max(0, l)), int(max(0, t - 18))
                tp.font_params.font_name = "Serif"
                tp.font_params.font_size = 10
                tp.font_params.font_color.set(*c)
                tp.set_bg_clr = 1
                tp.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)
            pyds.nvds_add_display_meta_to_frame(frame_meta, dm)

    def _draw_overlay(self, batch_meta, frame_meta, out, held):
        dm = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        now = time.monotonic()
        span = min(FPS_SHOW_S, now - self.started_mono) if self.started_mono is not None else FPS_SHOW_S
        show_fps = len(self._show_times) / max(span, 1e-3)
        texts = [
            "In frame: %d   Detected: %d   Entered: %d" % (out.in_frame, out.detected, self.mgr.total_entered),
            "No helmet: %d  No vest: %d" % (self.last_no_helmet, self.last_no_vest),
            "FPS: %.1f" % show_fps,
        ]
        dm.num_labels = len(texts)
        for i, text in enumerate(texts):
            tp = dm.text_params[i]
            tp.display_text = text
            tp.x_offset, tp.y_offset = 10, 50 + 32 * i    # 40 px below the Tapo date / time at the top left
            tp.font_params.font_name = "Serif"
            tp.font_params.font_size = 16
            tp.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
            tp.set_bg_clr = 1
            tp.text_bg_clr.set(0.0, 0.0, 0.0, 0.6)
        # people hidden for at most --hold s: last box, thin, no confidence (no detection this frame)
        dm.num_rects = len(held)
        for i, q in enumerate(held):
            l, t, w, h = q.box
            c = PALETTE[q.color_index % len(PALETTE)]
            rp = dm.rect_params[i]
            rp.left, rp.top, rp.width, rp.height = l, t, w, h
            rp.border_width = 1
            rp.border_color.set(*c)
            rp.has_bg_color = 0
            tp = dm.text_params[len(texts) + i]
            tp.display_text = "P%d -- %s" % (q.number, self._ppe_text(q.uid))
            tp.x_offset, tp.y_offset = int(max(0, l)), int(max(0, t - 26))
            tp.font_params.font_name = "Serif"
            tp.font_params.font_size = 14
            tp.font_params.font_color.set(0.0, 0.0, 0.0, 1.0)
            tp.set_bg_clr = 1
            tp.text_bg_clr.set(*c)
        dm.num_labels = len(texts) + len(held)
        # thin lines showing the edge zone used by PersonIds (edge_margin of width / height)
        mx = int(round(self.mgr.mx))
        my = int(round(self.mgr.my))
        lines = [(mx, 0, mx, MUX_H - 1), (MUX_W - 1 - mx, 0, MUX_W - 1 - mx, MUX_H - 1),
                 (0, my, MUX_W - 1, my), (0, MUX_H - 1 - my, MUX_W - 1, MUX_H - 1 - my)]
        dm.num_lines = len(lines)
        for i, (x1, y1, x2, y2) in enumerate(lines):
            lp = dm.line_params[i]
            lp.x1, lp.y1, lp.x2, lp.y2 = x1, y1, x2, y2
            lp.line_width = 1
            lp.line_color.set(1.0, 1.0, 0.0, 0.6)
        pyds.nvds_add_display_meta_to_frame(frame_meta, dm)

    # ---- bus / watchdog / restart -------------------------------------------------------------------
    def _from_camera(self, obj):
        while obj is not None:
            if obj is self.src:
                return True
            obj = obj.get_parent()
        return False

    def _on_bus(self, bus, msg):
        t = msg.type
        if t == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            name = msg.src.get_name() if msg.src else "?"
            log("ERROR from %s: %s" % (name, err.message))
            if self.args.source_file:
                self._stop("error (file source)")
            elif self._from_camera(msg.src) or name in ("depay", "parse", "dec"):
                self.restart("camera error: %s" % err.message)
            else:
                log("non-camera error, stopping")
                self.loop.quit()
        elif t == Gst.MessageType.EOS:
            log("EOS")
            if self.args.source_file:
                self._stop("end of file")
            else:
                self.restart("EOS")
        elif t == Gst.MessageType.WARNING:
            w, _ = msg.parse_warning()
            log("WARNING from %s: %s" % (msg.src.get_name() if msg.src else "?", w.message))
        return True

    def _watchdog(self):
        if self.restarting or self.started_mono is None:
            return True
        now = time.monotonic()
        if self.got_first_frame:
            if now - self.last_frame_mono > NO_FRAME_S:
                self.restart("no frame for %.1f s" % (now - self.last_frame_mono))
        elif now - self.started_mono > FIRST_FRAME_S:
            self.restart("no first frame within %.0f s" % FIRST_FRAME_S)
        return True

    def restart(self, reason):
        if self.restarting:
            return
        self.restarting = True
        self.restarts.append((time.strftime("%H:%M:%S"), reason))
        log("RESTART #%d: %s → NULL, reconnect in %.0f s" % (len(self.restarts), reason, RECONNECT_WAIT_MS / 1000.0))
        self.pipeline.set_state(Gst.State.NULL)
        self.fail_streak += 1
        n = self.args.rediscover_after
        if (not self.args.source_file and n > 0 and self.fail_streak % n == 0 and not self._discovering):
            self._discovering = True
            log("%d failed reconnects in a row: cam_discover in background" % self.fail_streak)
            threading.Thread(target=self._rediscover, name="cam_discover", daemon=True).start()
        GLib.timeout_add(RECONNECT_WAIT_MS, self._play)

    def _rediscover(self):
        """Thread: run cam_discover.sh; a new IP goes to self._new_ip (applied by _play). Never logs secrets:
        cam_discover sources .cam.env itself, so CAM_USER / CAM_PASS are removed from the child environment."""
        env = dict(os.environ)
        env.pop("CAM_USER", None)
        env.pop("CAM_PASS", None)
        env["CAM_IP"] = self.cam_ip
        env["CAM_STREAM"] = str(self.args.stream)
        env["CAM_DISCOVER_TIMEOUT"] = str(REDISCOVER_LIMIT_S)
        try:
            p = subprocess.Popen(["bash", CAM_DISCOVER], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, env=env, start_new_session=True,
                                 universal_newlines=True)
            try:
                out, _ = p.communicate(timeout=REDISCOVER_KILL_S)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)   # its scan runs xargs / bash children
                except OSError:
                    pass
                p.communicate()
                log("cam_discover: no answer within %d s, killed" % REDISCOVER_KILL_S)
                return
            ip = (out or "").strip()
            parts = ip.split(".")
            if p.returncode != 0 or len(parts) != 4 or not all(x.isdigit() for x in parts):
                log("cam_discover: camera not found (rc=%s), keeping %s" % (p.returncode, self.cam_ip))
            elif ip == self.cam_ip:
                log("cam_discover: camera still at %s" % ip)
            else:
                log("cam_discover: camera found at new IP %s (was %s)" % (ip, self.cam_ip))
                self._new_ip = ip
        except Exception as e:  # noqa: BLE001  a failed discover must never stop the app
            log("cam_discover: failed: %s" % e)
        finally:
            self._discovering = False

    def _play(self):
        ip, self._new_ip = self._new_ip, None
        if ip and ip != self.cam_ip:     # pipeline is NULL here (restart), so rtspsrc takes the new location
            self.ip_changes.append((time.strftime("%H:%M:%S"), self.cam_ip, ip))
            log("camera IP %s → %s" % (self.cam_ip, ip))
            self.cam_ip = ip
            self.src.set_property("location", "rtsp://%s:554/stream%d" % (ip, self.args.stream))
            self.safe_url = "rtsp://***@%s:554/stream%d" % (ip, self.args.stream)
        self.got_first_frame = False
        self.need_rebase = True
        self._pts_guard.restart()   # v4 A1: keep the PTS/RTP timeline continuous across a restart
        self.started_mono = time.monotonic()
        self._fps_last = (self.started_mono, self.frames)
        self._fps_skip = True
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            log("ERROR: cannot set PLAYING")
        self.restarting = False
        return False

    def _fps_tick(self):
        now = time.monotonic()
        t0, f0 = self._fps_last
        fps = (self.frames - f0) / max(now - t0, 1e-6)
        self._fps_last = (now, self.frames)
        if self.got_first_frame and not self.restarting:
            if self._fps_skip:
                self._fps_skip = False
            else:
                self.fps_samples.append(fps)
        snaps, self._snaps_win = self._snaps_win, 0
        g = self._pts_guard
        dmin, dmax = g.window_ms()
        log("fps %.2f  frames=%d  in_frame=%d  detected=%d  held=%d  no_helmet=%d  no_vest=%d  entered=%d  restarts=%d"
            "  snaps=%d  pts_fixed=%d  pts_rebase=%d  pts_dmin_ms=%s  pts_dmax_ms=%s  app_restarts=%d" % (
                fps, self.frames, self.last_in_frame, self.last_detected, self.last_held, self.last_no_helmet,
                self.last_no_vest,
                self.mgr.total_entered, len(self.restarts), snaps,
                g.fixed, g.rebase, dmin, dmax, len(self.restarts)))
        g.stats_window_reset()
        log("conf %s" % ConfStats.describe(self.conf.take_window()))
        if self.dbg_pre is not None:   # DEBUG (temporary, D2)
            log("dbg objs pre-tracker %s  |  osd %s" % (self.dbg_pre.take_window(), self.dbg_osd.take_window()))
        return True

    # ---- MQTT status -------------------------------------------------------------------------------
    def _status(self, online=True):
        a = self.args
        now = time.monotonic()
        age = (now - self.last_frame_mono) if self.last_frame_mono is not None else None
        connected = online and self.got_first_frame and not self.restarting and age is not None and age <= NO_FRAME_S
        fps_in, fps_out = self._status_fps if connected else (0.0, 0.0)
        return status_mqtt.build_status(
            a.camera_id, a.camera_name, online, connected, fps_in,
            fps_out / (a.interval + 1),    # person-model inferences per second (it runs every interval+1 frames)
            age, self.resolution, a.model_name,
            self.last_in_frame if connected else 0, self.last_compliant if connected else 0,
            self.last_violating if connected else 0, a.rtsp_path,
            ppe=self.last_ppe if connected else None)

    def _publish_status(self, online=True):
        if self.mqtt is None:
            return None
        payload = json.dumps(self._status(online), ensure_ascii=False)
        return self.mqtt.publish(status_mqtt.status_topic(self.args.camera_id), payload, qos=1, retain=True)

    def _status_tick(self):
        now = time.monotonic()
        t0, fin0, f0 = self._status_last
        dt = max(now - t0, 1e-6)
        self._status_fps = ((self.frames_in - fin0) / dt, (self.frames - f0) / dt)
        self._status_last = (now, self.frames_in, self.frames)
        self._publish_status()
        self._check_mode(time.time())    # log cira <-> fallback switches even when nobody is violating
        return True

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log("MQTT connected %s:%d" % (self.args.mqtt_host, self.args.mqtt_port))
            client.subscribe([(TOPIC + "cira/status", 1), (TOPIC + self.args.camera_id + "/config/zones", 1)])
            self._publish_status()       # retained status right away, not 5 s later
        else:
            log("MQTT connect refused rc=%s" % rc)

    def _on_mqtt_message(self, client, userdata, msg):
        if msg.topic == TOPIC + "cira/status":
            self.fallback.on_cira_status(msg.payload)
        elif msg.topic == TOPIC + self.args.camera_id + "/config/zones":
            zones = vio.parse_zones(msg.payload, self.args.camera_id)
            if zones is None:
                log("WARNING: ignored unreadable config/zones")
            else:
                self.viol.set_zones(zones)
                log("zones: %s" % (", ".join("%s(%d pts)" % (z, len(p)) for z, p in zones) or "none"))

    def _on_mqtt_disconnect(self, client, userdata, rc):
        if rc != 0:
            log("MQTT disconnected rc=%s, reconnecting" % rc)

    def _start_mqtt(self):
        a = self.args
        if not a.mqtt_host:
            log("MQTT off (--mqtt-host empty)")
            return
        c = status_mqtt.make_client("ds-%s-%d" % (a.camera_id, os.getpid()), a.camera_id)
        c.on_connect = self._on_mqtt_connect
        c.on_disconnect = self._on_mqtt_disconnect
        c.on_message = self._on_mqtt_message
        c.connect_async(a.mqtt_host, a.mqtt_port, keepalive=15)
        c.loop_start()
        self.mqtt = c
        GLib.timeout_add_seconds(status_mqtt.STATUS_EVERY_S, self._status_tick)

    def _stop_mqtt(self):
        """Clean stop: no LWT is sent, so publish online:false ourselves."""
        if self.mqtt is None:
            return
        try:
            info = self._publish_status(online=False)
            if self.mqtt.is_connected():
                info.wait_for_publish(2.0)
        except (RuntimeError, ValueError) as e:
            log("MQTT offline status not sent: %s" % e)
        self.mqtt.disconnect()
        self.mqtt.loop_stop()

    # ---- run ---------------------------------------------------------------------------------------
    def _mem_debug_loop(self):
        """v3 §2: sample RSS vs Python heap every 60 s so a Python leak (tracemalloc / gc grow with RSS)
        can be told apart from a native one (RSS grows, Python flat). Writes <out-dir>/<run>_mem.csv."""
        import gc, tracemalloc, time as _t
        tracemalloc.start(15)
        a = self.args
        path = os.path.join(a.out_dir, "%s_mem.csv" % a.run_name)
        t0 = _t.time()
        try:
            with open(path, "w") as f:
                f.write("ts,elapsed_s,rss_mb,py_objects,tm_current_mb,tm_peak_mb,pts_fixed,top1,top2,top3\n")
        except Exception:
            return

        def rss_mb():
            try:
                for ln in open("/proc/self/status"):
                    if ln.startswith("VmRSS:"):
                        return round(int(ln.split()[1]) / 1024.0, 1)
            except Exception:
                pass
            return ""

        while True:
            _t.sleep(60)
            try:
                gc.collect()
                cur, peak = tracemalloc.get_traced_memory()
                tops = []
                for s in tracemalloc.take_snapshot().statistics("lineno")[:3]:
                    fr = s.traceback[0]
                    tops.append("%s:%d=%dKB" % (os.path.basename(fr.filename), fr.lineno, s.size // 1024))
                while len(tops) < 3:
                    tops.append("")
                row = [time.strftime("%Y-%m-%d %H:%M:%S"), "%.0f" % (_t.time() - t0),
                       str(rss_mb()), str(len(gc.get_objects())),
                       "%.2f" % (cur / 1e6), "%.2f" % (peak / 1e6), str(self._pts_guard.fixed)] + tops
                with open(path, "a") as f:
                    f.write(",".join(row) + "\n")
            except Exception:
                pass

    def run(self):
        a = self.args
        log("models: person=%s (gie %d, interval %d)  ppe=%s" % (
            a.person_config, self.person_gie, a.interval,
            "%s (gie %d, interval from config)" % (a.ppe_config, self.ppe_gie) if a.ppe_config else "none (one model)"))
        log("events=%s (ds/violation, snapshots, fallback events)  vest_hold=%.1f s  partial: edge %.3f aspect %.2f"
            "  zone_mode=%s overlap>=%.2f" % (
            a.events, a.vest_hold, a.partial_edge, a.partial_aspect, a.zone_mode, a.zone_overlap))
        log("run=%s camera=%s tracker=%s interval=%d edge_margin=%.3f edge_ttl=%.1f regrace=%.1f "
            "hidden_ttl=%.1f hold=%.2f seconds=%d ppe_marks=%s/%s" % (
                a.run_name, self.safe_url, a.tracker, a.interval, a.edge_margin, a.edge_ttl,
                a.regrace, a.hidden_ttl, a.hold, a.seconds, ascii(self.mark_yes), ascii(self.mark_no)))  # C locale safe
        if not a.source_file:      # file: no watchdog / reconnect, stops at EOS
            GLib.timeout_add(1000, self._watchdog)
        GLib.timeout_add_seconds(FPS_LOG_S, self._fps_tick)
        if a.seconds > 0:
            GLib.timeout_add_seconds(a.seconds, self._stop, "time limit")
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._stop, "SIGINT")
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._stop, "SIGTERM")
        self.worker.start()
        if a.mem_debug:
            threading.Thread(target=self._mem_debug_loop, name="mem-debug", daemon=True).start()
        self._start_mqtt()
        self._play()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass   # PyGObject's MainLoop.run re-raises SIGINT after _stop has already quit the loop
        finally:
            self.pipeline.set_state(Gst.State.NULL)
            self.pub_q.put(None)       # worker: finish the queued snapshots / messages, then stop
            self.worker.join(10.0)
            self._stop_mqtt()
            self.events_f.close()
            if self.dbg_dump is not None:
                self.dbg_dump.close()
            if self.dbg_ppe is not None:
                self.dbg_ppe.close()
            self._write_summary()

    def _stop(self, why):
        log("stop: %s" % why)
        self.loop.quit()
        return False

    def _write_summary(self):
        s = self.fps_samples
        summary = {
            "run": self.args.run_name, "tracker": self.args.tracker, "interval": self.args.interval,
            "person_config": self.args.person_config, "ppe_config": self.args.ppe_config,
            "person_gie": self.person_gie, "ppe_gie": self.ppe_gie, "edge_margin": self.args.edge_margin,
            "hidden_ttl": self.args.hidden_ttl, "hold": self.args.hold, "edge_ttl": self.args.edge_ttl, "regrace": self.args.regrace,
            "frames": self.frames,
            "fps_mean": round(sum(s) / len(s), 2) if s else None,
            "fps_min": round(min(s), 2) if s else None, "fps_max": round(max(s), 2) if s else None,
            "fps_samples": len(s), "conf": ConfStats.as_json(self.conf.total), "events": self.event_counts, "entered": self.mgr.total_entered,
            "restarts": [{"wall": w, "reason": r} for w, r in self.restarts],
            "cam_ip_changes": [{"wall": w, "old": o, "new": n} for w, o, n in self.ip_changes],
            "events_mode": self.args.events, "violations": self.stats["violations"], "fallback_events": self.stats["events"],
            "event_ids_dup": self.stats["event_ids_dup"], "snapshots": self.stats["snapshots"],
            "snap_skipped": self.stats["snap_skipped"], "mode_switches": self.stats["mode_switches"],
        }
        b, ms = self.stats["snap_bytes"], self.stats["encode_ms"]
        if b:
            summary["snap_bytes"] = {"min": min(b), "mean": int(sum(b) / len(b)), "max": max(b)}
            summary["encode_ms"] = {"min": min(ms), "mean": round(sum(ms) / len(ms), 1), "max": max(ms)}
        with open(self.summary_path, "w") as f:
            json.dump(summary, f, indent=1)
        log("summary: %s" % json.dumps(summary))


def parse_args():
    ap = argparse.ArgumentParser(description="DeepStream person counting + PPE app (MQTT status heartbeat)")
    ap.add_argument("--seconds", type=int, default=0, help="stop after N seconds (0 = run until Ctrl-C)")
    ap.add_argument("--run-name", default="person_app", help="name for <out-dir>/<run>_events.jsonl etc.")
    ap.add_argument("--edge-margin", type=float, default=0.04, help="PersonIds edge zone, fraction of frame size")
    ap.add_argument("--hidden-ttl", type=float, default=4.0, help="PersonIds: seconds a hidden person is kept")
    ap.add_argument("--edge-ttl", type=float, default=1.5, help="PersonIds: lost at the edge this long -> left")
    ap.add_argument("--regrace", type=float, default=2.0,
                    help="PersonIds: back near the exit point within this many seconds -> same uid (0 = off)")
    ap.add_argument("--hold", type=float, default=0.6,
                    help="keep drawing the last box of a person hidden for at most this many seconds")
    ap.add_argument("--tracker", choices=sorted(TRACKER_CFG), default="iou")
    # Default = two models ("way A"): COCO person 320x192 (not the COCO 416 config_infer_cam_person.txt)
    #   + ppe3 helmet / vest (yolov8n_ppe3_416, chosen 2026-10-15; yolo11n_ppe3_416 is the spare).
    # One model: --person-config ../models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_416.txt --ppe-config ""
    # (that config says interval=1, but --interval (default 0) overrides it on the person nvinfer)
    ap.add_argument("--person-config", "--infer-config", dest="person_config",
                    default=os.path.join(DS_DIR, "test", "config_infer_cam_person_320.txt"),
                    help="nvinfer #1: people (and helmet / vest too when there is no --ppe-config)")
    ap.add_argument("--ppe-config",
                    default=os.path.join(DS_DIR, "models", "yolov8n_ppe3_416", "config_infer_yolov8n_ppe3_hv.txt"),
                    help='nvinfer #2: helmet / vest model (own gie-unique-id and interval); "" = one model')
    ap.add_argument("--interval", type=int, default=0,
                    help="interval of the person nvinfer (frames skipped between inferences)")
    ap.add_argument("--source-file", default=None,
                    help="H.264 mp4 instead of the camera (test); no watchdog / reconnect, stops at EOS")
    ap.add_argument("--mux-padding", action="store_true",
                    help="test, with --source-file: nvstreammux enable-padding=1 (keep the aspect ratio, black "
                         "bars, e.g. a portrait clip) instead of stretching to 1280x720")
    ap.add_argument("--realtime", action="store_true",
                    help="test, with --source-file: play the clip at its frame times, nvstreammux live-source=1")
    ap.add_argument("--ppe-first", action="store_true",
                    help="test only: put the --ppe-config nvinfer before the person nvinfer")
    ap.add_argument("--debug-objs", action="store_true",
                    help="DEBUG (temporary): log obj_meta count per (component id, class id) before nvtracker "
                         "and at the OSD probe every 5 s; per-frame list before nvtracker in <run>_objs.jsonl")
    ap.add_argument("--mem-debug", action="store_true",
                    help="DEBUG (v3 §2): every 60 s log RSS, gc object count, tracemalloc current/peak + top 3 "
                         "allocation lines and the A1 PTS-fix count to <out-dir>/<run>_mem.csv (to tell a Python "
                         "leak from a native one). Small overhead; off by default.")
    ap.add_argument("--stream", type=int, choices=(1, 2), default=1)
    ap.add_argument("--rediscover-after", type=int, default=3,
                    help="after this many failed camera reconnects in a row run ~/safety/perception/cam_discover.sh (again every "
                         "N more) and switch to the IP it finds; 0 = off")
    ap.add_argument("--rtsp-bind", default="127.0.0.1",
                    help="RTSP server address (MediaMTX pulls on this machine; 0.0.0.0 = all interfaces)")
    ap.add_argument("--rtsp-port", type=int, default=8555)
    ap.add_argument("--rtsp-path", default="cam01", help="RTSP mount, = the source path in mediamtx.yml")
    ap.add_argument("--udp-port", type=int, default=5400)
    ap.add_argument("--out-dir", default=os.path.join(DS_DIR, "test", "results", "cam"))
    ap.add_argument("--camera-id", default="cam01", help="<cam> in factory/safety/<cam>/status")
    ap.add_argument("--camera-name", default="CAM 01 - Tapo C200C", help="name shown on the Dashboard")
    ap.add_argument("--model-name", default=None, help="status 'model' field (default: from the config file names)")
    ap.add_argument("--mqtt-host", default="127.0.0.1", help='broker for the status heartbeat ("" = MQTT off)')
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--vest-hold", type=float, default=vio.HOLD_S[vio.NO_VEST],
                    help="seconds a vest ✗ must last before no_vest is sent (no_helmet stays %.0f s)"
                         % vio.HOLD_S[vio.NO_HELMET])
    ap.add_argument("--partial-edge", type=float, default=vio.EDGE_FRAC,
                    help="person box this close to the picture edge (fraction of its size) = seen in part: "
                         "left / right edge -> vest ?, top edge -> helmet ?")
    ap.add_argument("--partial-aspect", type=float, default=vio.MIN_ASPECT,
                    help="person box width / height below this = seen in part: vest ?")
    ap.add_argument("--zone-mode", choices=("overlap", "foot", "bottom"), default="overlap",
                    help="restricted-zone test: overlap (box&zone area >= --zone-overlap, default), "
                         "foot (foot point in zone, old rule), bottom (bottom 25%% band overlaps). "
                         "A per-zone \"mode\" in config/zones wins over this.")
    ap.add_argument("--zone-overlap", type=float, default=0.10,
                    help="min box&zone area fraction for --zone-mode overlap / bottom (per-zone "
                         "\"min_overlap\" wins over this)")
    ap.add_argument("--events", choices=("on", "off"), default="off",
                    help="on = publish ds/violation + snapshots + fallback events; off = status only (default)")
    a = ap.parse_args()
    a.rtsp_path = a.rtsp_path.strip("/")
    if not a.rtsp_path:
        ap.error("--rtsp-path must not be empty")
    if a.realtime and not a.source_file:
        ap.error("--realtime needs --source-file")
    if a.mux_padding and not a.source_file:
        ap.error("--mux-padding needs --source-file")
    if a.source_file:
        a.source_file = os.path.abspath(a.source_file)
        if not os.path.isfile(a.source_file):
            ap.error("source file not found: %s" % a.source_file)
    for k in ("person_config", "ppe_config"):
        v = getattr(a, k)
        if not v:
            setattr(a, k, None)
            continue
        v = os.path.abspath(v)
        setattr(a, k, v)
        if not os.path.isfile(v):
            ap.error("%s not found: %s" % (k.replace("_", "-"), v))
    if a.ppe_config and gie_unique_id(a.ppe_config) == gie_unique_id(a.person_config):
        ap.error("--person-config and --ppe-config must have different gie-unique-id")
    if not os.path.isfile(TRACKER_CFG[a.tracker]):
        ap.error("tracker config not found: %s" % TRACKER_CFG[a.tracker])
    if a.model_name is None:   # config_infer_cam_person_320.txt + ..._yolov8n_ppe3_hv.txt -> cam_person_320+yolov8n_ppe3_hv
        a.model_name = "+".join(os.path.basename(c)[:-4].replace("config_infer_", "")
                                for c in (a.person_config, a.ppe_config) if c)
    return a


def main():
    args = parse_args()
    Gst.init(None)
    App(args).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
