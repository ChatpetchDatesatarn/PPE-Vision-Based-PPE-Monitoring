# Design v3 (concept, not built yet): 30 fps video + low-latency detection

Status: **on hold until a USB camera is available** (recorded 2026-10-15)
Combines the Frigate approach (separate live/detect streams) + DeepStream (detect some frames + tracker fills the rest) with our system

## Goals
- Dashboard shows smooth 30 fps video, latency ~150–350 ms (LAN)
- Detection boxes overlaid on the video, moving smoothly, and aligned with the image
- Detection is accurate + fast within the limits of the Jetson Nano (YOLOv8n ~10–15 inferences/s)

## Architecture
```
USB camera MJPEG 1280×720@30
   │ hardware JPEG decode (nvv4l2decoder mjpeg=1) — no CPU
   ▼
GStreamer tee (image stays in NVMM/GPU memory)
 ├─ LIVE stream 1280×720 30fps ─► nvv4l2h264enc (low-latency) ─► MediaMTX ─► WebRTC (fallback MSE) ─► Dashboard <video>
 └─ DETECT stream 640×360 (16:9 same as LIVE) ─► queue leaky max-size-buffers=1 ─► v4l2loopback /dev/video10
                                   │
             Jetson: CiRA CORE opens /dev/video10 like a webcam
             ├─ YOLOv8n detects every N frames (interval, e.g. N=2 ≈ 15/s)
             ├─ Kalman tracker (SORT-style) every frame → smooth boxes + stable track_id
             └─ PPE logic (ppe_logic.py) uses track_id from the tracker → events
                                   │
             MQTT: factory/safety/<cam>/detections (boxes + velocity + capture timestamp)
                   factory/safety/<cam>/event (+ snapshot, existing system)
                                   ▼
Dashboard: <canvas> over <video> draws boxes; between updates, moves boxes along their velocity at every display frame
```

## What we take from each approach
| Source | Usage |
|---|---|
| Frigate | separate live/detect streams; both streams **16:9** so normalized 0–1 coordinates line up; **keyframe interval = fps** so video starts fast; WebRTC primary, MSE when UDP is blocked |
| DeepStream | `interval` = detect every N frames, tracker fills the rest; increase N when the Nano is hot/slow while boxes stay smooth |
| Ours | raw frames to CiRA via v4l2loopback (no encode→decode); send only box coordinates via MQTT; Dashboard extrapolates boxes using velocity |

## Key settings
- Encoder: `nvv4l2h264enc maxperf-enable=1 preset-level=1 poc-type=2 iframeinterval=30 idrinterval=30 insert-sps-pps=1` (no B-frames)
- Detect queue: `queue leaky=downstream max-size-buffers=1` → always detect the newest frame, never a stale one
- Detect resolution 640×360 (letterbox to 640, matching training); if too slow, reduce input to 416
- MediaMTX: enable WebRTC (UDP 8189) + set `webrtcAdditionalHosts` = LAN IP + Tailscale IP (<JETSON_TAILSCALE_IP>)

## Planned MQTT `detections` topic (v3)
```json
{ "ts": "2026-10-15T10:15:12.345+07:00", "frame": 1234, "w": 640, "h": 360,
  "objects": [ { "track_id": 7, "cls": "person", "conf": 0.91,
                 "box": [0.41, 0.22, 0.18, 0.55], "vel": [0.02, 0.0],
                 "state": "NO_HELMET" } ] }
```
- `box` = [x, y, w, h] normalized 0–1, `vel` = velocity in units/s for the Dashboard to extrapolate
- Sent at detection/tracker rate (~15–30 Hz); JSON is small
- Dashboard hides boxes if no update arrives within 1 second

## Estimated latency (must measure on the real board)
| Path | Estimate |
|---|---|
| video glass-to-glass (LAN) | 150–350 ms (+30–100 ms via Tailscale) |
| detection boxes after capture | 100–200 ms |

## Must test first (when the camera is available)
1. Does the camera support MJPEG 1280×720 @30 — `v4l2-ctl -d /dev/video0 --list-formats-ext`
2. GStreamer plugins: `gst-inspect-1.0 nvv4l2decoder nvv4l2h264enc rtspclientsink`
3. Build v4l2loopback on kernel 4.9 (dkms already installed) — if not possible, use a small RTSP stream `cam01_det` instead
4. Can CiRA open `/dev/video10` (check after installing CiRA)

## What to build later
1. GStreamer pipeline + systemd service
2. MediaMTX in Docker (WebRTC + MSE)
3. `legacy/cira_v2_python/tracker.py` (Kalman/SORT) to replace the IoU matching in `ppe_logic.py`
4. Publisher sends `detections` (+ velocity, capture timestamp)
5. Dashboard: video WebRTC/MSE + canvas overlay + extrapolation
6. Simulator for testing without a camera
7. Update `mqtt_spec.md` to v3

## Fallback
If CiRA on the Nano is too slow: NVIDIA DeepStream 6.0.1 (supports JetPack 4.6) does nvinfer + nvtracker + OSD + RTSP + nvmsgbroker(MQTT) in one pipeline,
but it replaces CiRA (conflicts with the proposal) — use only when necessary

## Addition (2026-10-15): CiRA + TensorRT — one model, two runtimes
- Model: **YOLOv7-tiny (darknet) input 416×256**, trained once via the official CiRA Colab → `.cfg` + `.weights` (not encrypted)
- Runtime 1: CiRA DeepDetect (darknet CUDA) — for CiRA workflow / official demo
- Runtime 2: convert darknet → ONNX → **TensorRT FP16 engine** on the Jetson → fast detector (~25–35 fps, estimate, MAXN)
  - sends `detections` to the Dashboard (boxes over 30 fps video) and sends to CiRA via MqttSub for logic/workflow
- Dashboard frame rate = video (30 fps from H.264/WebRTC) + box update rate (TensorRT + tracker) — both are needed
- Benchmark darknet in CiRA (5W, 2 cores, inference-only): v7-tiny 416×256 = 16.2 fps, v4-tiny 416×256 = 22.1 fps (details in docs/test-results/benchmark_darknet_5W)
- Prerequisites: 5V 4A barrel jack + fan (MAXN); check TensorRT 8.2 / trtexec / darknet→onnx converter that supports yolov7-tiny

## Decision (2026-10-15, after TensorRT readiness check)
- On the Jetson: TensorRT 8.2.1.8, trtexec, python3-tensorrt, CUDA 10.2 and cuDNN 8.2.1 are present; pycuda and pip3 are missing; no CiRA node uses TensorRT
- Rejected: the CiRA PythonScript node spawns a new python3 on every run (3.5–4.8 s for CUDA init each time) → under 0.3 fps
- Chosen: a **persistent TensorRT process** (`13_trt/trt_detector.py`, systemd) = fast path
  - camera → TRT FP16 → `ppe_logic.py` → `safety_publisher.py` → Dashboard (mqtt_spec v2: frame/event/status)
  - also publishes `factory/safety/<cam>/detections` JSON → CiRA MqttSub subscribes to it for workflow, logging and display (CiRA stays in the system)
  - the TRT side draws its own boxes (no CiRA node draws boxes from a generic payload)
- Two modes, **one at a time** (Nano 4GB cannot run both detectors well, and only one process can open the camera before the v3 tee exists):
  - `CIRA mode` = CiRA DeepDetect darknet (official demo for the proposal)
  - `FAST mode` = TRT process (high fps on the Dashboard)
- Converter: jkjung-avt/tensorrt_demos (darknet→ONNX on PC/Colab, plugin + engine built on the Jetson); files named like `yolov4-416x256` pattern; v7-tiny on TRT 8.2 still untested → validate the toolchain first with stock COCO yolov7-tiny weights
- Native install only (~0.3–0.5 GB): python3-pip, python3-dev, libboost-python-dev, libboost-thread-dev, pycuda 2019.1.2 — Docker l4t images (1.7–1.8 GB) are not used
- Dashboard fps note: MJPEG over MQTT is limited by CPU JPEG encode (~10–15 fps at 640 px on the Nano); real 30 fps needs the v3 H.264 path

## Decision (2026-10-15, chosen architecture): DeepStream perception + CiRA decision
- Perception = **DeepStream 6.0.1 + YOLOv8n TensorRT FP16 (DeepStream-Yolo)**, 416×256, 3 classes (person, helmet, vest), `interval=1` + tracker, `ppe_logic.py` in a pyds probe (hold only)
- Heavy data goes direct: H.264 video with boxes → MediaMTX → Dashboard (WebRTC); snapshot JPEG → `snapshot/<id>` → recorder
- **CiRA CORE = decision + alert layer** (MqttSub `ds/violation` → flow → MqttPub `event`):
  - filter: cooldown per person/zone, merge duplicates, drop low confidence
  - policy: enable/disable rules per camera, zone and shift; severity (restricted_zone = critical, no_vest = warning)
  - official event: event_id, severity, timestamp → Dashboard + recorder
  - heartbeat `factory/safety/cira/status`
- Fallback: if the CiRA heartbeat is stale for over 15 s, DeepStream publishes the event directly with `via: "fallback"`
- Blocking checks in the CiRA GUI: MqttPub exists, JSON fields can be read/edited, a stateful node for cooldown exists, Xvfb/autostart works without a monitor

## Decision (2026-10-15, camera): TP-Link Tapo C200C over RTSP
Camera chosen: Tapo C200C (~400 THB). Spec page: RTSP yes, ONVIF yes, H.264, max 1080p, 15/20/25/30 fps (default 15), 2.4 GHz Wi-Fi only, no Ethernet port.
This replaces the USB-camera assumptions above (MJPEG, GStreamer tee, v4l2loopback are no longer needed).

### Pipeline
```
Tapo C200C rtsp://<cam>:554/stream1 (1920×1080 @30 fps H.264, Wi-Fi)
  → DeepStream: rtspsrc → nvv4l2decoder (NVDEC) → nvstreammux 1280×720 live-source=1 (scales 1080p down)
    → nvinfer YOLOv8n 416×256 FP16 (interval=1) → nvtracker → probe (ppe_logic, snapshot, MQTT)
    → nvdsosd → nvv4l2h264enc (720p30, iframeinterval=30, no B-frames, baseline-compatible for WebRTC)
    → DeepStream RTSP server on port 8555 (NOT 8554: MediaMTX owns 8554)
  → MediaMTX pulls rtsp://127.0.0.1:8555/... → WebRTC → Dashboard
```
- One RTSP session to the camera only (stream1, 1920×1080 @30 fps) — main image of the system; stream2 (1280×720) is not used
- Why stream1: probe 2026-10-15 over TCP with the camera set to 30 fps in the Tapo app — stream2 caps report 30/1 but measured only 17–20 fps (60 s: average 19.12; 150 s: average 17.18), stream1 measured 29.25 fps average, 0 dropped, NVDEC decodes 1080p at CPU mean 21.4%
- Boxes are burned in by nvdsosd, so the Dashboard needs no canvas overlay (raw passthrough + overlay = later option)

### Changes required
| Area | Change |
|---|---|
| Camera setup | 30 fps, Camera Account for RTSP, Motion Tracking/Patrol OFF, Privacy Mode OFF, no SD card, no Tapo Care, auto-update OFF, DHCP reservation, mount fixed at 2.5–3 m |
| Secrets | `~/safety/.cam.env` (chmod 600, git-ignored), typed by the user; never in logs or reports |
| DeepStream app | RTSP reconnect logic (DS 6.0.1 has no nvurisrcbin → rebuild the source), values from the probe below |
| Ports | DeepStream RTSP out 8555; MediaMTX 8554 / WebRTC 8889 / UDP 8189 |
| MQTT status | add `camera_connected`, `fps_in`, `fps_infer`, `last_frame_age_s` |
| Model (Mel) | camera view is elevated + wide-angle; IR night mode is grayscale → add elevated/night/grayscale images and grayscale augmentation |
| Dashboard (Guy) | WebRTC player via nginx proxy to MediaMTX; separate "camera disconnected" vs "DeepStream down" |
| Tests (Som) | Wi-Fi drop/weak signal, camera reboot recovery time, night IR accuracy, glass-to-glass latency over Wi-Fi |

### RTSP values from the probe (2026-10-15, details in `docs/test-results/2026-10-15_tapo_c200c_probe/README.md`)
- rtspsrc: `protocols=tcp`, `latency=200`, `drop-on-latency=true`, `tcp-timeout=5000000`; video only via `select-stream` (`media=video`), PCMA audio never set up
- Camera unplug test: no ERROR; EOS only 25 s after the last frame (default `tcp-timeout` 20 s); the pipeline does not recover by itself; while booting the camera came up, dropped again for 13 s, then stayed stable
- Camera lost = no frame for 3 s (watchdog) or EOS/ERROR on the bus → rebuild the source every 2 s for the first 60 s, then every 5 s (max 10 s), no attempt limit
- `camera_connected=true` and backoff reset only after 10 s of continuous frames

### Unchanged
CiRA decision layer, ds/violation → event flow, recorder, snapshot storage, fallback.
