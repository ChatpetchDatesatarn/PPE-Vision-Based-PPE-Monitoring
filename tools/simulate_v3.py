"""
Simulator v3 — stands in for DeepStream + CiRA so the Dashboard can be built without the camera.
Publishes exactly what docs/mqtt_spec.md (v3) defines.

  pip install paho-mqtt pillow        (pillow optional: nicer snapshot images)
  python tools/simulate_v3.py --host localhost                 # normal: events via CiRA
  python tools/simulate_v3.py --host localhost --cams 2        # two cameras
  python tools/simulate_v3.py --host localhost --cira-down     # CiRA offline -> fallback events
  python tools/simulate_v3.py --host localhost --camera-down   # camera_connected=false
  python tools/simulate_v3.py --host localhost --emit ds       # send ds/violation only (to test a CiRA flow / decide.js)
  python tools/simulate_v3.py --host <JETSON_LAN_IP> --once      # one snapshot+event and exit
"""
import argparse
import base64
import io
import json
import random
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

BKK = timezone(timedelta(hours=7))
P = "factory/safety/"
TYPES = [("no_helmet", 0.45), ("no_vest", 0.35), ("restricted_zone", 0.15), ("unknown_visibility", 0.05)]
SEVERITY = {"restricted_zone": "critical", "no_helmet": "high", "no_vest": "warning", "unknown_visibility": "info"}
COLORS = {"critical": (220, 38, 38), "high": (234, 88, 12), "warning": (202, 138, 4), "info": (100, 116, 139)}
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgQEBMQExYWFhYWFhoYGhsbGxoaGhobGxsdHR0iIiIdHR0bGx0d"
    "ICAiIiUmJSMjIiMmJigoKDAwLi44ODpFRVP/xABMAAEBAAAAAAAAAAAAAAAAAAAABwEBAQAAAAAAAAAAAAAAAAAAAAQQAQAAAAAAAAAAAAAA"
    "AAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCABaAKADASIAAhEAAxEA/9oADAMBAAIRAxEAPwCfALUwAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD//2Q==")


def now():
    return datetime.now(BKK)


def iso(dt):
    return dt.isoformat(timespec="seconds")


def snapshot_jpeg(cam, etype, sev, track, bbox):
    """640x360 picture with a box and a label; falls back to a tiny gray JPEG without Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return TINY_JPEG
    img = Image.new("RGB", (640, 360), (40, 48, 60))
    d = ImageDraw.Draw(img)
    for x in range(0, 640, 40):
        d.line([(x, 0), (x, 360)], fill=(52, 62, 78))
    x, y, w, h = [int(v * s) for v, s in zip(bbox, (640, 360, 640, 360))]
    c = COLORS[sev]
    d.rectangle([x, y, x + w, y + h], outline=c, width=3)
    d.rectangle([x, y - 18, x + 150, y], fill=c)
    d.text((x + 4, y - 15), "#%d %s" % (track, etype.upper()), fill=(255, 255, 255))
    d.text((8, 340), "%s  %s  (simulated)" % (cam, now().strftime("%Y-%m-%d %H:%M:%S")), fill=(230, 230, 230))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=75)
    return buf.getvalue()


class Sim(object):
    def __init__(self, a):
        self.a = a
        self.cams = ["cam%02d" % (i + 1) for i in range(a.cams)]
        self.counts = {"received": 0, "published": 0, "filtered": 0}
        try:
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sim-v3-%d" % random.randint(0, 9999))
        except AttributeError:  # paho-mqtt 1.x
            self.c = mqtt.Client(client_id="sim-v3-%d" % random.randint(0, 9999))
        self.c.connect(a.host, a.port, 30)
        self.c.loop_start()

    def pub(self, topic, payload, retain=False):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False)
        self.c.publish(P + topic, data, qos=1, retain=retain).wait_for_publish(5)

    def status(self, cam, i):
        persons = random.randint(0, 5)
        violating = random.randint(0, persons) if persons else 0
        down = self.a.camera_down
        self.pub(cam + "/status", {
            "camera_id": cam, "name": "CAM %02d - Simulated %s" % (i + 1, ["Main Entrance", "Factory Floor"][i % 2]),
            "ts": iso(now()), "online": True, "camera_connected": not down,
            "fps_in": 0.0 if down else round(random.uniform(29.0, 30.0), 1),
            "fps_infer": 0.0 if down else round(random.uniform(14.0, 15.0), 1),
            "last_frame_age_s": 999.0 if down else round(random.uniform(0.03, 0.2), 2),
            "resolution": "1920x1080", "model": "ppe_sim",
            "persons": 0 if down else persons, "compliant": 0 if down else persons - violating,
            "violating": 0 if down else violating, "stream_path": cam}, retain=True)

    def cira_status(self):
        self.pub("cira/status", dict({"online": True, "ts": iso(now()), "flow": "simulated"}, **self.counts),
                 retain=True)

    def violation(self, cam):
        etype = random.choices([t for t, _ in TYPES], [w for _, w in TYPES])[0]
        sev, track, t = SEVERITY[etype], random.randint(1, 40), now()
        bbox = [round(random.uniform(0.05, 0.7), 3), round(random.uniform(0.1, 0.4), 3),
                round(random.uniform(0.1, 0.2), 3), round(random.uniform(0.35, 0.55), 3)]
        conf = round(random.uniform(0.3, 0.95), 2)
        sid = "%s-%s-%03d" % (cam, t.strftime("%Y%m%d-%H%M%S"), track)
        zone = "zone-a" if etype == "restricted_zone" else "line-1"
        self.pub("%s/snapshot/%s" % (cam, sid), snapshot_jpeg(cam, etype, sev, track, bbox))
        if self.a.emit == "ds":
            self.pub(cam + "/ds/violation", {"camera_id": cam, "ts": iso(t), "type": etype, "track_id": track,
                                             "conf": conf, "zone_id": zone, "bbox": bbox, "snapshot_id": sid,
                                             "repeat": 0})
            print("ds/violation", cam, etype, conf)
            return
        self.counts["received"] += 1
        if conf < 0.40 and not self.a.cira_down:  # what CiRA would filter out
            self.counts["filtered"] += 1
            print("filtered   ", cam, etype, conf)
            return
        self.counts["published"] += 1
        ev = {"event_id": "%s-%s-%03d" % (cam, (t + timedelta(seconds=1)).strftime("%Y%m%d-%H%M%S"), track),
              "ts": iso(t + timedelta(seconds=1)), "camera_id": cam, "zone_id": zone, "type": etype,
              "severity": sev, "track_id": track, "confidence": conf, "bbox": bbox, "snapshot_id": sid,
              "via": "fallback" if self.a.cira_down else "cira"}
        self.pub(cam + "/event", ev)
        print("event      ", cam, etype, sev, ev["via"])

    def run(self):
        if self.a.once:
            for i, cam in enumerate(self.cams):
                self.status(cam, i)
            if not self.a.cira_down:
                self.cira_status()
            self.violation(self.cams[0])
            return
        t_status = t_cira = 0.0
        t_next = time.time() + 2
        print("simulating %s on %s:%d (Ctrl+C to stop)" % (", ".join(self.cams), self.a.host, self.a.port))
        while True:
            tnow = time.time()
            if tnow >= t_status:
                for i, cam in enumerate(self.cams):
                    self.status(cam, i)
                t_status = tnow + 5
            if tnow >= t_cira and not self.a.cira_down:
                self.cira_status()
                t_cira = tnow + 10
            if tnow >= t_next and not self.a.camera_down:
                self.violation(random.choice(self.cams))
                t_next = tnow + random.uniform(self.a.min_gap, self.a.max_gap)
            time.sleep(0.2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--cams", type=int, default=1, choices=range(1, 5))
    ap.add_argument("--min-gap", type=float, default=5.0, help="min seconds between violations")
    ap.add_argument("--max-gap", type=float, default=20.0)
    ap.add_argument("--cira-down", action="store_true", help="no CiRA heartbeat, events marked via=fallback")
    ap.add_argument("--camera-down", action="store_true", help="camera_connected=false, no events")
    ap.add_argument("--emit", choices=["event", "ds"], default="event",
                    help="event = act as DeepStream+CiRA; ds = act as DeepStream only")
    ap.add_argument("--once", action="store_true")
    try:
        Sim(ap.parse_args()).run()
    except KeyboardInterrupt:
        pass
