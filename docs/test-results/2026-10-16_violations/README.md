# 2026-10-16 — ds/violation + snapshot + fallback event (person_count_app.py)

Spec: `docs/mqtt_spec.md` v3 sections 1, 2, 3, 6 (event_id format changed in section 2, see below).
Clip: `perception/test/results/cam/clean_ppe_01.mp4` (Jetson only), 87.0 s, 2531 frames,
`--source-file --realtime`, default models (COCO 320 person → ppe3_hv helmet / vest, interval 0 / 1), tracker IOU.
No `cira/status` on the broker → fallback mode for the whole run. Retained zone `zone-a` (right edge, x 0.83–0.94).

## Code
- `perception/app/violations.py` (+ `test_violations.py`, 21 tests): hold no_helmet / no_vest 2.0 s, restricted_zone
  0.5 s (foot point = bottom-centre), repeat every 5 s, "?" does not count, run ends when the person leaves,
  ray-casting point-in-polygon, `config/zones` parsing, fallback mode (cira/status missing or ts > 15 s),
  cooldown 30 s per (camera, track_id, type), severity critical / high / warning / info
- `perception/app/ppe_pretrack.py` (+ `test_ppe_pretrack.py`, 6 tests): **nvtracker drops every helmet / vest
  object** (before this fix the OSD probe saw 0 helmet / vest in the whole clip, so everybody was H✗ V✗). Boxes are now
  read on the nvtracker sink pad, keyed by (frame_num, pts), handed to `assign_ppe` → `PpeSmoother` in the OSD probe of
  the same frame, and drawn thin through display meta
- `person_count_app.py`: every ds/violation (repeats too) and every fallback event gets a new picture of its own frame
  (copied at the nvdsosd src pad, encoded in a worker thread: 640 px, JPEG q80, ≤ 2 MB); one picture per person per
  frame; publish order snapshot → ds/violation → event (one FIFO worker). Status compliant / violating = same smoothed
  states as the violations ("?" not counted)
- `event_id` = `<cam>-YYYYMMDD-HHMMSS-<uid 3 digits>-<nh|nv|rz|uv>` (spec section 2 updated, with a note that CiRA's
  `decide.js` must use the same format). Before this, no_helmet + no_vest of one person in the same second had the
  same id and the recorder silently kept only the first (run `viol_clip_01`: 3 of 6 events lost)
- Recorder `store.py`: logs `duplicate event_id ... ignored, the first one is kept`; nothing else changed
  (`recorder/app.py` md5 unchanged e9252460bb2466c2ade431abe319859e); test `test_two_types_same_person_same_second_both_kept`
- Tests: all app tests (7 files) OK on the PC (3.14) and the Jetson (3.6); `test_store.py` (8) OK on the PC and in
  `python:3.11-slim` on the Jetson

## Run `viol_clip_02` (01:11:35–01:12:58)
Before the run: recorder stopped, `DELETE FROM events` (6) + VACUUM, 2 snapshots deleted, recorder rebuilt
(`docker-compose up -d --build recorder`), `/api/health` events 0 / snapshots 0.

| Item | Result |
|---|---|
| fps (5 s windows) | mean 31.13, min 28.8, max 33.4; every window from 5 s on had 1–2 snapshots, no drop |
| Snapshots | 24 sent, all JPEG, 640×360, 42 237–51 929 bytes (mean 44 567), encode 11–48 ms (mean 26), 0 skipped |
| ds/violation | 27 (no_helmet 16, no_vest 11); every one after its snapshot (0 out of order) |
| Fallback events | 6 (3 no_helmet, 3 no_vest), **event_id all different** (0 duplicates) |
| `/api/events` | total **6**, all with `snapshot_url`; recorder log: 0 duplicate / rejected |
| Picture vs event time | snapshot_id second = event ts second for all 6 (0 s); snapshot → event arrival 7–18 ms |
| Helmet / vest before tracker | helmet n=0 (none worn), vest n=375 (mean conf 0.70) |

### Violations against the clip segments (clip time t)
Segment edges come from `2026-10-15_clip_ab` and are approximate (the video was not watched).

| Segment | no_vest (repeat) | no_vest event | no_helmet |
|---|---|---|---|
| before the sequence 0–12 s | 4.9 (0), 9.9 (1) | 4.9 `011137-001-nv` | every 5 s from 4.9 (no helmet worn: correct) |
| standing, vest on 14–38 s | 14.9 (2) only, at the start edge; then none (status `no_vest=0` from ~16 s to ~41 s) | none | events at 4.9, 35.8, 66.1 (30 s cooldown) |
| standing, vest off 38–58 s | **42.2 (0), 47.2, 52.2, 57.2** | **42.2 `011215-001-nv`** | |
| sitting, vest on 58–68 s | **yes**: 63.6 (0) — vest seen in few frames while sitting (16.7 % in clip_ab) | none (cooldown from 42.2) | |
| bending / walking out 68–88 s | 68.2 (0), 73.2 (1), 78.2 (2) | 73.2 `011246-001-nv` | |

- Standing with the vest: no no_vest after the run that started before the sequence ended (last repeat 14.9 s); label
  `P1 0.85 H✗ V✓` with the thin `V 0.60` box (`snap_t20_vest_on.jpg`, t = 20.3 s)
- Vest off: no_vest from 42.2 s (✗ needs < 10 % vest in the last 20 frames, then 2 s hold), label `H✗ V✗`
  (`snap_t42_vest_off.jpg`)
- restricted_zone: none (correct: the person never stood in `zone-a`)

### Notes
- 18 of the 24 snapshots belong only to ds/violation messages (no fallback event): the recorder deletes such orphans
  after its 600 s grace. With CiRA running, CiRA's events will reference them
- The live app was not started again after this run (waiting for the user)

## Dashboard check by the user (live `live_20261016_0122`, events on)
All correct: event_id split nh / nv, picture time matches, same type in the latest alert and the history page,
cooldown about 30 s. The live app then sent events with pictures of people at home every 30 s → stopped by the user
(`ds-stop`, 01:24:43).

## `--events on|off` (2026-10-16)
- `person_count_app.py --events off` (app default): status only — no ds/violation, no fallback event, no snapshot
  taken (no frame copy, no encode). Detection, labels, KPI counts (compliant / violating) work the same.
  `--events on` = everything above. The value is logged (`events=...`) and written to the summary (`events_mode`)
- `ds-start` passes `--events off` unless `--events` is given: `./ds-start --events on`; run name optional
  (`./ds-start <run-name> --events on`)
- Tests: 7 app test files OK on the PC and the Jetson

## Clear the DB again (approved, pictures of people at home)
Recorder stopped → `DELETE FROM events` (14) + VACUUM, 47 snapshots deleted → recorder started:
`/api/health` events 0, snapshots 0.

## fps while taking snapshots
User saw OSD FPS 26.5–27.5 on the pictures of the live run (normal 29–31).

| Run | Source | Snapshots | fps (5 s windows, start-up skipped) |
|---|---|---|---|
| `viol_clip_02` | clip, realtime, events on | 24 | mean **31.13**, 28.8–33.4 |
| `viol_clip_03_off` | same clip, events off | 0 | mean **31.05**, 28.6–33.4 |
| `live_20261016_0122` | camera, events on, person always in view | 23 (one in almost every window) | mean 27.18, 20.6–30.0 |
| `v3_status_600` (before the violation code) | camera, person in view | — | mean 27.61, 16.0–31.0 |

- Snapshots do not lower fps: same clip on vs off differs by 0.08 fps. The ~27 fps of the live run is the camera
  path itself (it was the same before snapshots existed); the pictures show the 2 s OSD FPS of that moment
- Encode (worker thread, 1280×720 RGBA → 640×360 JPEG q80): live run 23 pictures, median 27 ms, p90 41 ms,
  max 78 ms (mean 27.8); clip run 11–48 ms (mean 26.4). JPEG 42–52 KB
- `viol_clip_03_off`: 0 messages on ds/violation / event / snapshot (MQTT logger), 0 VIOL / SNAP log lines,
  `/api/health` still 0 / 0; no_vest status still changes with the vest (detection unchanged)

## State at the end
`./ds-start` → `live_20261016_1211`, `--events off`, first frame 12:11:36. (`live_20261016_0127`, events off, had
been stopped by SIGINT at 01:29:53.)
