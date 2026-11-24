# 2026-10-17 — CiRA CORE decision path (via:"cira") end-to-end on the clip

CiRA CORE now runs the decision: DeepStream publishes `cam01/ds/violation`, CiRA's JavaScript `decide` node applies
conf threshold + 30 s cooldown and publishes `cam01/event` (via "cira"); a second JS node sends `cira/status` every
10 s. DeepStream stays in CiRA mode (no fallback) as long as `cira/status` is fresher than 15 s.

## CiRA setup (headless, no monitor)
- CiRA GUI runs on a virtual display: `Xvfb :99` + `x11vnc -localhost -rfbport 5900 -rfbportv6 -1 -forever -shared
  -loop` (localhost only, reached over an SSH tunnel `ssh -L 5900:localhost:5900`), all in tmux `cira-gui`
- Flow file: `decision/test_flow_tooltest.npj` (test copy; `test_flow.npj` untouched). Nodes: MqttSub
  `factory/safety/+/ds/violation` → JavaScript `decide` → IfElse `payload.hasOwnProperty("event_id")` → MqttPub
  `factory/safety/cam01/event`; AutoRun → Delay 10000 ms → JavaScript `heartbeat` → MqttPub `factory/safety/cira/status`
- JS node code is kept in `decision/src/cira_node_decide.js` / `cira_node_heartbeat.js` and written into the
  `.npj` with `tools/npj_tool.py set-js <id>` (CiRA engine = QtScript / ES5)
- Key fixes to get CiRA's JS engine working: globals are `hasGlobal/getGlobal/setGlobal` (not `*Payload`);
  state stored as a JSON **string**; no `Date.prototype.toISOString` (build the +07:00 stamp by hand with getUTC*);
  `findViolation` looks under a `.../ds/violation` key first and rejects objects carrying `event_id` (the
  JS→AutoRun→MqttSub loop leaves the previous event on top of the payload, which otherwise caused every-other-message drops)

## Clip run `cira_clip_01` (clean_ppe_01.mp4, --source-file --realtime --events on, 09:43:55–09:46:08)
DeepStream app sends `ds/violation` + snapshot; CiRA decides and publishes the events.

| Check | Result |
|---|---|
| via | **all 7 events via:"cira"**, 0 fallback (app summary `fallback_events: 0`, mode switch `09:44:11 → cira` only) |
| event count | **no_helmet 4, no_vest 3** (recorder `/api/events` total 7). App-side raw violations: no_helmet 17, no_vest 11 (repeats); CiRA's 30 s cooldown per (camera, track, type) collapses them. Comparable to the earlier fallback round on this clip (~3 each); the small difference is cooldown-window alignment |
| event_id unique | yes (7 distinct) |
| snapshot_id + image | 7/7 events have `snapshot_id` and a `snapshot_url`; the recorder stored the JPEGs (DeepStream sent the snapshot before each `ds/violation`, CiRA passes `snapshot_id` through) |
| cira/status | streamed every 10 s through the whole run; `received`/`published` counters climbed (…→ published 17, received 36), `last_rx` tracked the last violation, 7 fields only |
| fps (DeepStream) | **mean 23.2** (21.0–26.0), vs ~31 on the earlier `viol_clip` runs **without** CiRA — running CiRA + roscore + Xvfb + x11vnc alongside DeepStream costs ~8 fps |
| tegrastats | RAM peak **2289 / 3964 MB**; CPU (2 online cores) **86–97 %** — CPU is the limit with both running |
| secret check | clean, rc=0 |

All 7 events (sorted): nh 09:44:20, nv 09:44:22, nh 09:44:53, nv 09:45:11, nh 09:45:24, nv 09:45:41, nh 09:44:57…
(ts 094557 nh was the last, after the live MQTT sub's -W window; the recorder caught it).

## Clean-up
Recorder stopped → `DELETE FROM events` (7) + VACUUM, 24 snapshots deleted → `/api/health` events 0, snapshots 0.
Then `./ds-start` → `live_20261017_0947`, `--events off` (status only, no events — pictures of people at home stay off),
first frame 09:48:00.

## Notes
- No fallback events means DeepStream correctly saw CiRA's heartbeat the whole time. If CiRA stops sending
  `cira/status` for >15 s, DeepStream will publish `cam01/event` itself with via:"fallback" — watch for duplicate
  events (one via:cira + one via:fallback) if both run during a CiRA restart
- fps drop to ~23 is acceptable for the clip test; on the real camera, consider whether CiRA and DeepStream must run
  on the same Jetson at once, or stagger them
- `test_flow.npj` (the real flow file) was never modified (md5 6449f398835212ae3a69fe3bd9e13374)

## Reducing CiRA CPU (2026-10-17)

Changes (on the test flow copy `safety_decision_v1.npj`; `test_flow_tooltest.npj` and `test_flow.npj` untouched):
- `src/cira_node_decide.js` `DEBUG = false` (no per-message `print`)
- Removed both Debug nodes and their connections with `tools/npj_tool.py del-node <id>` (new command; removes a
  node and every connection touching it). Debug renders JSON on screen for every message — costly under load
- VNC on/off scripts: `~/ds-vnc-on` (x11vnc `-loop`, localhost only, in tmux `cira-gui:vnc`) and `~/ds-vnc-off`
  (stops x11vnc only, leaves Xvfb :99 + CiRA). x11vnc polls the framebuffer continuously, so it is stopped when not viewing

### Measurements (live, events off, 60 s each)
| State | fps (live camera) | CPU (2 cores) | RAM |
|---|---|---|---|
| no CiRA (earlier runs) | ~27–31 | — | — |
| CiRA old flow + VNC (cira_clip baseline) | ~23 | ~88–94 % | — |
| **M1** CiRA new flow + x11vnc **on** | 16.8–28.6 (~24) | ~85–91 % | 2274 MB |
| **M2** CiRA new flow + x11vnc **off** | 12.4–29 (~20, erratic) | **~55–89 % (mostly 70–78 %)** | used 2.1 G |

Live-camera fps is dominated by Wi-Fi / RTSP jitter, not CPU, so it is not a clean headroom signal (M2 fps looks
worse despite lower CPU). x11vnc off clearly lowers CPU (steady ~88 % → ~70–78 % with dips to ~55 %).

### Clip run `cira_clip_02` (clean_ppe_01.mp4, --events on --realtime, x11vnc off, DEBUG=false, no Debug nodes)
Deterministic (clip, CPU-bound) — the clean comparison:

| Run | fps mean (min–max) | CPU | RAM peak | events (via) |
|---|---|---|---|---|
| `cira_clip_01` (x11vnc on, Debug nodes, DEBUG=true) | 23.2 (21.0–26.0) | 86–97 % | 2289 MB | 7, all cira |
| **`cira_clip_02`** (x11vnc off, no Debug, DEBUG=false) | **25.58 (23.8–28.2)** | 90–97 % (inference) | 2312 MB | **6, all cira** |

**+2.4 fps (~10 %)** from the CiRA-side trims, toward the ~27–31 no-CiRA baseline. clip2 events: all via:"cira"
(no_helmet 3, no_vest 3), unique event_id, all 6 with snapshot images, fallback 0, loop works (>1 event). CPU during
clip stays high because DeepStream inference itself is the dominant load; the CiRA idle cost (GUI render + x11vnc) is
what the trims reduce.

### Clean-up
Recorder stopped → `DELETE FROM events` (6) + VACUUM, 22 snapshots deleted → `/api/health` 0/0. `./ds-start` →
`live_20261017_1005`, `--events off`, first frame 10:06:06. **x11vnc left off** (use `./ds-vnc-on` to view again).

### Not done (awaiting approval)
- Option B: shrink Xvfb to 1280x720x16 — needs restarting Xvfb, which also closes CiRA (it runs on :99), so CiRA must
  be reopened + the project re-run afterwards

## Lowering CiRA priority with renice +19 (2026-10-17)

Gave the CiRA / ROS / X stack the lowest CPU priority so DeepStream (left at nice 0) wins the CPU. DeepStream, docker,
tmux `cira`, nvpmodel and jetson_clocks were not touched.

Command (own processes, no sudo needed):
```
renice -n 19 -p $(pgrep -f "cira_core_run|cira_core_launch|rosmaster|roscore|rosout|Xvfb :99|x11vnc -display")
```
Reniced to ni=19: Xvfb(:99), cira_core_launch, cira_core_run, roscore, rosmaster, rosout (x11vnc was off). Verified
`ps -eo pid,ni,comm` before (ni 0) and after (ni 19).

### Clip run `cira_clip_03` (clean_ppe_01.mp4, --events on --realtime, x11vnc off, CiRA at nice 19)
| Run | fps mean (min–max) | events |
|---|---|---|
| no CiRA (`viol_clip_02`) | 31.13 | — (fallback) |
| CiRA, no Debug, x11vnc off (`cira_clip_02`) | 25.58 | 6 cira |
| **CiRA at nice +19 (`cira_clip_03`)** | **30.1 (27.4–31.6)** | **6 cira** |

renice +19 recovered almost all the fps lost to CiRA: **25.58 → 30.1**, within ~1 fps of the no-CiRA 31.13.
RAM peak 2317 MB.

CiRA stayed healthy under low priority:
- `cira/status` every **10 s exactly** (13 msgs, max gap 10 s, well under the 13 s limit)
- `ds/violation` → `cam01/event` latency **0–1 s** (all ≤ 2 s)
- events: 6, **all via:"cira"**, fallback 0

### Clean-up
Recorder stopped → `DELETE FROM events` (6) + VACUUM, 20 snapshots deleted → `/api/health` 0/0. `./ds-start` →
`live_20261017_1011`, `--events off`, first frame 10:12:03. **nice +19 left in place**, x11vnc left off.

Note: renice is per-process and resets if CiRA/ROS is restarted (e.g. reopening the project) — re-run the renice
command after any CiRA restart. A startup hook could make it automatic later.
