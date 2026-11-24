# 2026-10-16 — Docker stack v2 → v3 on the Jetson

Goal: replace the v2 stack (`~/safety/legacy/docker_v2`) with the v3 stack (`~/safety/dashboard`, adds MediaMTX),
then run `person_count_app.py` with an MQTT status heartbeat so the Dashboard shows live video and fps.
Access was remote (Tailscale <JETSON_TAILSCALE_IP>).

## B) State before the move (2026-10-16 00:24 +07:00)

Disk (`df -h /`): 29G size, 21G used, **7.4G free** (needed ≥ 3 GB: OK)
RAM: 3964 MB total, 3365 MB available; swap 4030 MB (58 MB used)

`docker ps` (v2, all `network_mode: host`, up 22 h):

| Name | Image | Status |
|---|---|---|
| dashboard | nginx:1.27-alpine | Up 22 hours |
| recorder | 11docker_recorder (33e43bb5191b, 162MB) | Up 22 hours |
| mosquitto | eclipse-mosquitto:2.0.18 | Up 22 hours |

`docker volume ls`:

| Volume | Size |
|---|---|
| 11docker_safety-data | 13M |
| 11docker_mosquitto-data | 12K |
| 7fd934e2cfc50d355c6cf9d51c8a8915bb6f008dcb033d96cf176bae617311dc | (anonymous, untouched) |

Listening before the move: 8080 (nginx), 1883, 9001 (mosquitto). Nothing on 8000/8554/8555/8889/8189.
tmux sessions: `cira`, `ds`. paho-mqtt: not installed for python3.6.

## A) Dashboard web fixes (PC, before copying)

- `web/js/mqtt-client.js` `nowIso07()`: `.replace(/\.\d{3}Z$/, "+07:00")` — ack and config/zones `ts` have no milliseconds
- `web/js/pages/events.js`: camera cell has `data-cam-name`; `ctx.on("status", ...)` (same hook as dashboard.js / live.js)
  rewrites the name in place and refreshes the camera filter, so rows drawn before the first status no longer stay `cam01`
- No other file in `web/` changed; `web/whep-test.html` md5 = 45fcd636179d10a7cb8543646fabb5cb

## C) Copy to `~/safety/dashboard/`

Left out: `test_screenshots/`, `dev_mock/`, `media/*.mp4`, `__pycache__/`. 38 files, `md5sum -c` on the Jetson: all OK.
`recorder/app.py` = e9252460bb2466c2ade431abe319859e.

## D) Stop v2

`cd ~/safety/legacy/docker_v2 && docker-compose down` (no `-v`, no prune): dashboard / recorder / mosquitto removed, rc=0.
Volumes `11docker_safety-data` and `11docker_mosquitto-data` still listed.

## E) Start v3 (00:26)

`docker-compose up -d --build`: rc=0 (image `14dashboardv3_recorder` built, `bluenviron/mediamtx:1.9.3` pulled).
Containers: mosquitto, recorder, mediamtx, dashboard.
`/api/health`: `{"ok":true,"mqtt":"connected",...,"server_time":"2026-10-16T00:26:34+07:00",...,"events":1000,"snapshots":1000}`
(recorder log: `migrated 1000 events from v2 events.json`).
Listening: 1883, 9001, 8080, 8000 (127.0.0.1), 8554, 8889, 8189 tcp+udp, 9997 (127.0.0.1).

## F) `perception/app/person_count_app.py`

- Defaults: `--person-config test/config_infer_cam_person_320.txt` (COCO person 320x192),
  `--ppe-config models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_hv.txt` (`""` = one model),
  `--rtsp-path cam01`, `--rtsp-bind 127.0.0.1`
- `nvv4l2h264enc`: profile=0 (Baseline), insert-sps-pps=1, iframeinterval=30
- New `status_mqtt.py` (+ `test_status_mqtt.py`): `factory/safety/cam01/status` every 5 s, QoS 1, retain,
  LWT `{"online":false}`; clean stop publishes `online:false`. `fps_in` = decoder output, `fps_infer` =
  OSD-probe fps / (interval+1). New options `--camera-id`, `--camera-name`, `--model-name`, `--mqtt-host` (`""` = off), `--mqtt-port`
- paho-mqtt 1.6.1 installed with `pip install --user` on the Jetson (approved by the user)
- Tests (`test_obj_route`, `test_person_ids`, `test_ppe_assign`, `test_ppe_smooth`, `test_status_mqtt`):
  all OK on the PC (Python 3.14, paho 2.1.0) and on the Jetson (Python 3.6, paho 1.6.1)

## G) Run `v3_status_600` (600 s, started 00:29:24)

`bash run_person_app.sh v3_status_600 --seconds 600` in tmux `ds`. Log: `perception/test/results/cam/v3_status_600.log`.
Pipeline fps 29.4–30.2. Sample status:

```json
{"camera_id": "cam01", "name": "CAM 01 - Tapo C200C", "ts": "2026-10-16T00:30:04+07:00", "online": true,
 "camera_connected": true, "fps_in": 29.8, "fps_infer": 29.6, "last_frame_age_s": 0.0, "resolution": "1920x1080",
 "model": "cam_person_320+yolov8n_ppe3_hv", "persons": 1, "compliant": 0, "violating": 1, "stream_path": "cam01"}
```

MediaMTX check: `gst-launch-1.0 rtspsrc location=rtsp://127.0.0.1:8554/cam01` rc=0; MediaMTX log
`[path cam01] [RTSP source] ready: 1 track (H264)`.

## Clear old event history (00:36, approved by the user, no backup)

Test data from before the camera was installed. Only `recorder` was stopped (`docker-compose stop recorder`);
mosquitto / mediamtx / dashboard and the running `v3_status_600` app were not touched.
In volume `11docker_safety-data`, via `docker run --rm -i python:3.11-slim` (local image, no pull):
- `safety.db`: `DELETE FROM events` (1000 rows) + `VACUUM` → 0 rows, file 28 KB (WAL checkpointed at recorder stop)
- `snapshots/*.jpg`: 1000 files deleted → folder empty
- `events.json.migrated` deleted
After `docker-compose start recorder`: `/api/health` → `"events":0,"snapshots":0`, MQTT connected.

## G) Dashboard check by the user (run `v3_live`, `--seconds 0`, started 00:43:12)

Checked by the user in Chrome over Tailscale (http://<JETSON_TAILSCALE_IP>:8080) — **pass**:
- Live view: video shows (DeepStream → MediaMTX → WebRTC), OSD FPS 31.0
- Lights: Camera and Perception green; Decision "ไม่มีข้อมูล" (expected: CiRA is not running yet)
- KPI: persons 1, fully equipped 0 %. `violating=1` is a real person at home without helmet / vest,
  not a false detection (ppe3 saw no helmet / vest: helmet n=0, vest n=0 in the conf log)

The earlier 600 s run `v3_status_600` ended at 00:39:24 by its time limit (fps mean 27.61, min 16.0, max 31.0,
16178 frames, no restarts, secret check clean); its `online:false` status made the Dashboard show the camera as
disconnected until `v3_live` was started.

Short commands on the Jetson (symlinks in `~` to scripts in `perception/app/`):
- `ssh jetson ./ds-start [run-name] [app options]` → `start_person_app.sh`: starts the app in tmux `ds` with
  `--seconds 0` (default run name `live_<YYYYmmdd_HHMM>`), refuses if one is already running, waits for the first frame
- `ssh jetson ./ds-stop` → `stop_person_app.sh`: SIGINT to the python process only, waits up to 30 s
- Off-LAN add `-o HostName=<JETSON_TAILSCALE_IP>` after `ssh`. Not started again after a reboot.
