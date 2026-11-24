# 2026-10-21 — full system health check

Run from the PC over SSH (`-o HostName=<JETSON_TAILSCALE_IP>`), 20:36–20:39 +07. Read-only except step 9 (one fake
`ds/violation`, then its event deleted). Nothing stopped or restarted; `tmux cira`, `nvpmodel`,
`jetson_clocks`, network and `.cam.env` untouched.

## Results

| Part | Result | Measured | Evidence |
|---|---|---|---|
| 1 DeepStream app | PASS | pid 20159, run `live_20261017_1011`, up 4 d 10 h, `--events off` | `pgrep -af person_count_app.py`; ps etime `4-10:24:12` |
| 1 docker (4 svc) | PASS | mosquitto/recorder/dashboard/mediamtx all **Up 4–5 days**, RestartCount **0** each | `docker ps`, `docker inspect -f {{.RestartCount}}` |
| 1 CiRA procs + nice | PASS | cira_core_launch 32569, cira_core_run 32716, roscore 32664, rosmaster 343, rosout 427, Xvfb 31433 — **all ni=19** | `ps -eo pid,ni,comm` |
| 1 x11vnc | **WARN** | **ON** (pid 12284, 127.0.0.1:5900) — expected off | started for GUI access (`ds-vnc-on`); run `ds-vnc-off` when done |
| 1 tmux | PASS | `cira`, `cira-gui` (3 win), `ds` | `tmux ls` |
| 2 RAM | PASS | Mem 2.2G used / 96M free / **1.5G available**; swap 72M/3.9G | `free -h` |
| 2 disk / | PASS | 7.3G avail, 74% used (> 3 GB free) | `df -h /` |
| 2 temp (15 s) | PASS | CPU max **59°C**, GPU 57°C, AO 65°C — all < 70°C. CPU 2 cores 90–98% @921 (2 cores off, 5 W), GPU 42–67% | `tegrastats` |
| 3 camera | PASS | `camera_connected=True`, fps_in 28.8, fps_infer 29.8, last_frame_age_s 0.0, persons 2, ts 20:37:05 (fresh) | `factory/safety/cam01/status` |
| 4 CiRA heartbeat | PASS | 2 msgs 10 s apart, 7 fields (`filtered,flow,last_rx,online,published,received,ts`). Topic `factory/safety/cira/status` (= spec's `cira/status` with the `factory/safety/` prefix) | `mosquitto_sub -t factory/safety/cira/status` |
| 5 MQTT retained zones | PASS | `cam01/config/zones` retained (ts 2026-10-16T01:00:08), 2 zones | `mosquitto_sub -C 1` |
| 5 broker clients | PASS | **6** connected | `$SYS/broker/clients/connected` |
| 6 MediaMTX cam01 | **WARN** | `ready=False`, readers 0, webrtcsessions 0 (rtspSource, on-demand — no viewer now) | `9997/v3/paths/list`, `/webrtcsessions/list` |
| 7 recorder | PASS | `/api/health` ok, mqtt connected, events 0, snapshots 0 (after step 9 cleanup) | `curl 8000/api/health` |
| 8 dashboard | PASS | `HTTP/1.1 200 OK` | `curl -I 8080` |
| 9 end-to-end decide | PASS | fake `ds/violation` → `cam01/event` **via:"cira"** in ~1 s (`cam01-20261021-203802-901-nh`), recorder stored it, then deleted | see below |
| 9 status +1 | PASS | heartbeat shows `received:1 published:1 last_rx:20:38:02` = the test event | `factory/safety/cira/status` |
| 10 port 5900 | PASS | **127.0.0.1 only** (not external) | `ss -ltnp :5900` |
| 10 port 8554 | **WARN** | `*:8554` (all interfaces) — spec wants 127.0.0.1 | `ss -ltnp` |
| 10 other external | WARN | also 0.0.0.0: 1883 (mqtt), 8080 (dash), 8889/8189 (webrtc), 9001 (ws), ros 11311/rand | `ss -ltnp` |
| 11 time / tz | PASS | Jetson 20:36:02 +0700 == PC 20:36:02 +0700 (diff 0 s), tz Asia/Bangkok | `date`, `/etc/timezone` |
| 12 app log errors | WARN | 26 error lines / 4 d 10 h, all camera "Could not open resource" reconnects (last RESTART #23 at 19:19) | run log grep |
| 12 docker logs 1h | PASS | 0 error-lines each container (--since 1h) | `docker logs --since 1h` |

## Step 9 detail

Published once:
`factory/safety/cam01/ds/violation` = `{"camera_id":"cam01","type":"no_helmet","track_id":901,"conf":0.9,...}`.
Received on `factory/safety/cam01/event` within ~1 s:
`{"event_id":"cam01-20261021-203802-901-nh","via":"cira","type":"no_helmet","track_id":901,"severity":"high",...}`.
Recorder stored it (events 1, mqtt_messages 1). Deleted the single row by `event_id` from the recorder sqlite
`/data/safety.db` (`delete … where event_id='cam01-20261021-203802-901-nh'`, rowcount 1) → events 0 again.

Note: the live recorder runs `app.py` + `store.py` on sqlite `/data/safety.db`; the PC `legacy/jetson_v2/recorder.py`
is the old v2 JSON recorder and is **not** what is deployed.

## Correction

Step 4 was first reported FAIL — that was a **wrong-topic subscription** on my side. The heartbeat publishes
to `factory/safety/cira/status`. The spec defines the prefix `factory/safety/`, so the spec's `cira/status`
is exactly that topic — there is **no mismatch**, nothing to change. On the correct topic the heartbeat
arrives every 10 s with all 7 fields, and its `received:1 / published:1 / last_rx:20:38:02` match the step-9
test, so step 9's "+1" is confirmed too. CiRA is fully healthy.

## Verdict — system healthy; minor items to review

1. **Port 8554 (RTSP) on all interfaces (WARN).** Spec wants `127.0.0.1`. Also 1883/8080/8889/8189/9001 and
   ROS ports (11311 etc.) listen on 0.0.0.0 — reachable by any device on the home Wi-Fi + Tailscale. Close or
   bind to localhost before taking this off-site or demoing on the university network.
2. **MediaMTX cam01 `ready=False` (WARN).** Confirm the dashboard shows live video (rtspSource is on-demand;
   may connect only when a viewer opens). Check again with a reader attached.
3. **Camera reconnects (WARN).** 23 RTSP drops over 4 d 10 h (last 19:19), app reconnects every time,
   currently connected — Wi-Fi/Tapo placement, low priority.

x11vnc was turned off after the check (`ds-vnc-off`, 5900 closed). Everything else PASS: DeepStream + camera
healthy (≈29 fps), CiRA decide + heartbeat both live, 4 containers up with 0 restarts, resources and
temperature fine, decision path proven end-to-end, time in sync.
