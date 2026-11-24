# 2026-10-21 — CiRA decision layer, headless autostart, port hardening

Three phases, all on the Jetson over SSH. End state: DeepStream live (`--events off`) + CiRA running
`safety_decision_v1` + heartbeat every 10 s; broker/RTSP/WebRTC-signalling/ROS off the LAN; boot autostart
installed. All files are in the PC repo and md5-match the Jetson.

## Phase 1 — CiRA decision layer (deliverables)

- `decision/`: `safety_decision_v1.npj` (running flow), `src/cira_node_decide.js`,
  `src/cira_node_heartbeat.js`, `tests/test_decide_es5.js`, `CIRA_NOTES.md`, `TEST_RESULTS.md`,
  `QUESTIONS.md`, `SOM_HANDOVER.md` (Thai).
- **Unit tests** (`node tests/test_decide_es5.js`, vm + mocked getGlobal/setGlobal/hasGlobal/print): 15 checks
  pass — wrapped-topic payload, stale-event echo, 30 s cooldown, nh+nv same second, two tracks,
  restricted_zone + zone_id, unknown_visibility disabled, broken JSON, missing track_id, ts/event_id with no
  milliseconds. `npx acorn --ecma5` passes both JS files.
- **Live CiRA test** (14 cases, `TEST_RESULTS.md`): 13 PASS + case 10 (fallback) PASS. Heartbeat 9.8–10.1 s,
  `received = published + filtered`, mosquitto restart → CiRA reconnects by itself.

## Phase 2 — headless autostart of CiRA (`cira-up`)

CiRA has no CLI auto-load/run, so `cira-autoload` drives the GUI on Xvfb :99 with xdotool:
1. click **Open Project** (fixed toolbar pixel) → click the **File name** field (fixed dialog pixel) → type
   the path → Enter. The project loads and the engine starts.
2. click **fit-to-view** → normalises the canvas to a **deterministic layout** (so node pixels are stable
   regardless of the previous pan/zoom).
3. click the **decide** AutoRun Run (starts MqttSub/decide) and the **heartbeat** AutoRun Run (starts the
   10 s heartbeat). A global run does NOT fire AutoRun source nodes, and `node_enable` alone does not either —
   the node's own Run must be clicked.
4. verify: heartbeat on `factory/safety/cira/status` ≤ 30 s **and** a fake `track 990` → event `via:"cira"`.
   Up to 3 attempts; on failure exits non-zero with log + screenshots. Never presses Save Project, never
   touches the toolbar Run/STOP. First attempt waits 45 s for the "Starting…" splash.

- `~/cira-up` = `cira-start` (fresh Xvfb + CiRA at nice 19) → `cira-autoload`.
- **3 rounds** `cira-stop → cira-up`: all PASS on attempt 1, ~110 s each.
- **Fallback (case 10)**, clip `clean_ppe_01.mp4 --events on --realtime`: `via:cira` → `cira-stop` →
  `via:fallback` in **9 s** (`CIRA_STALE_S = 15 s`) → `cira-up` → back to `via:cira`. (Full table in
  `decision/TEST_RESULTS.md`.)

Files: `tools/cira-autoload.sh`, `tools/cira-up.sh` (+ `cira-start.sh` keeps nice 19). `npj_tool.py`
gained `set` support for an AutoRun node's `node_enable` flag.

## Phase 3 — close ports exposed on the LAN (config, not firewall)

The 4 containers run `network_mode: host`; the dashboard (dashboard) reaches everything through nginx
on **8080** with relative URLs (`/mqtt` → 9001, `/webrtc` → 8889, `/api` → 8000), so those back-ends only
need localhost. Changes:

| Port | Who uses it | Plan | Done |
|---|---|---|---|
| 1883 MQTT | DeepStream/CiRA/recorder (127.0.0.1); PC via `ssh -L` | → 127.0.0.1 | ✓ closed |
| 9001 ws | nginx `/mqtt` (local) | → 127.0.0.1 | ✓ |
| 8554 RTSP | nothing off-box (dashboard = WebRTC) | → 127.0.0.1 | ✓ closed |
| 8889 WHEP sig | nginx `/webrtc` (local) | → 127.0.0.1 | ✓ |
| 9997 API | already 127.0.0.1 | — | ✓ |
| 8000 recorder | already 127.0.0.1 | — | ✓ |
| 8189 WebRTC media | browser direct via Tailscale | keep open | ✓ open |
| 8080 dashboard | browser via Tailscale | keep open | ✓ 200 |
| 11311 + ROS ports | CiRA's own nodes | `ROS_IP=127.0.0.1` in cira-start | partial (see below) |

Config diffs: `dashboard/mosquitto/mosquitto.conf` (`listener 1883/9001 127.0.0.1`, kept `protocol
websockets` + `allow_anonymous`), `dashboard/mediamtx/mediamtx.yml` (`rtspAddress`/`webrtcAddress` →
127.0.0.1; rtmp/hls/srt already `no`), `tools/cira-start.sh` (ROS_IP / ROS_HOSTNAME / ROS_MASTER_URI =
localhost). 3 files backed up on the Jetson as `*.bak-20261021-225912`. Restarted mosquitto + mediamtx;
mediamtx came up clean (`RTSP 127.0.0.1:8554`, `WebRTC 127.0.0.1:8889 + :8189 ICE`, `API 127.0.0.1:9997`).

Verified from the PC over Tailscale: 8080 **200 OK**, 1883/8554 **refused**, 8189 **open**. Dashboard loads,
live video + 3 greens confirmed by the user. decide `track 991` → `via:cira`, heartbeat OK.

**ROS caveat:** `ROS_IP=127.0.0.1` makes nodes *advertise* localhost, but ROS1's rosmaster/nodes still
*listen* on `0.0.0.0` (11311 + dynamic ports) — there is no env to bind the socket. The graph is effectively
localhost-only (returned URIs are 127.0.0.1), but the sockets are still open. Truly closing them would need
iptables (out of scope here). **Decision pending** with the user.

## Boot autostart (phase 2, item 6)

`systemd` unit `safety-autostart.service` → `tools/safety-boot.sh`: wait for mosquitto (≤ 120 s) →
`ds-start --events off` → `cira-up`; logs each step to `~/safety/logs/boot_<ts>.log`; on failure logs and
exits (no endless retry). Unit: `Type=oneshot`, `RemainAfterExit=yes`, `TimeoutStartSec=600`,
`KillMode=process`, `User=jetson`, `Environment=HOME=/home/jetson`, `After=docker.service
network-online.target`, `Wants=network-online.target`. Installed + enabled.

**Test (no reboot):** `ds-stop` + `cira-stop` → `sudo systemctl start safety-autostart` → 132 s,
`Result=success`, `ExecMainStatus=0`. After: DeepStream `--events off`, CiRA up, heartbeat, decide
`track 994` → `via:cira`. Ready for a real reboot test when the user chooses.

## Pending / decisions
- ROS sockets still listen on 0.0.0.0 (see caveat) — keep as-is or seek another method.
- Real reboot test not yet run (no self-reboot by rule).
- All test events/snapshots deleted after each test (events 0, snapshots 0).
