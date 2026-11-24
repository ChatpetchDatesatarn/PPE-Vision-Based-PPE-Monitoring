# Person counting test app on Jetson Nano, 5W (2026-10-15)

`perception/app/person_count_app.py` (Python 3.6 + pyds 1.1.1, own GStreamer pipeline, no `deepstream-app`, no MQTT yet) with the stable numbering in `perception/app/person_ids.py`, tested live on the Tapo C200C while a person walked in front of the camera and watched the result in VLC.

## Conclusion
- **Use the IOU tracker** — 0 of 5 crossings gave a wrong number in every version; NvDCF is not needed for now (round B with `tracker_nvdcf_tuned.yml` was not run)
- **`interval=0` runs at ~29 fps at 5W** (camera rate) with the full pipeline incl. RTSP out; no CPU core pegged (mean 52–57%), GR3D mean ~62%
- **v3 numbering passes all user checks** and is the default of the app: numbers follow entry order, colour stays with the person, `--edge-ttl 1.5`, `--regrace 2.0`

## Setup
| Item | Value |
|---|---|
| Board | Jetson Nano 4GB, JetPack 4.6.1, DeepStream 6.0.1, **5W** (`nvpmodel` unchanged, no `jetson_clocks`) |
| Camera | Tapo C200C stream1 1920×1080 @30, RTSP over TCP, latency 200, drop-on-latency, video only (`select-stream`); evening/dark (19:36–20:05) |
| Pipeline | rtspsrc → rtph264depay → h264parse → nvv4l2decoder → queue → nvstreammux 1280×720 → nvinfer → nvtracker (IOU, 640×384) → nvvideoconvert (RGBA) → nvdsosd [probe] → nvvideoconvert (I420) → queue → nvv4l2h264enc (4 Mbit/s, iframeinterval 30) → rtph264pay → udpsink 127.0.0.1:5400 → GstRtspServer `rtsp://<jetson>:8555/ds-test` (bind 0.0.0.0 for the test) |
| Model | YOLOv8n COCO 416×256 FP16, `config_infer_cam_person.txt` (person only, threshold 0.35), `interval=0` |
| Run | `bash run_person_app.sh A_iou --seconds 600 --tracker iou --interval 0 --rtsp-bind 0.0.0.0` in tmux `ds` (sources `~/safety/.cam.env`; logs show `rtsp://***@…`, `secret check: clean`); stopped with SIGINT after the user's check |
| Measures | fps = frames through the probe per 5 s (first window after start dropped); tegrastats as root every 1 s (means include ~10 s engine load) |
| Unit tests | `app/test_person_ids.py`: 17 tests pass on the PC (Python 3.12) and the Jetson (Python 3.6.9) |

## Versions
| | v1 | v2 | v3 (current) |
|---|---|---|---|
| Numbering rule | smallest free number, kept until the person leaves | entry order among people in the frame (1..N): when someone leaves, later people move up; one person alone = 1 | as v2 |
| Colour | by number (8 colours) | by `uid mod 8` | `color_index` from PersonIds: first of 12 colours unused in the frame, kept by the person (also on rejoin) |
| Leaving at the edge | lost at the edge 0.7 s → exit; coming back = new person | as v1 | lost at the edge **1.5 s** → exit; back near the exit point within **2.0 s** → old uid (rejoin, not enter) |
| Events in jsonl | enter / exit / rejoin | + renumber (uid, old, new) | + box (left, top, w, h) on enter / exit / rejoin |
| Run (wall time) | 19:36:51–19:45:36 | 19:49:35–19:54:17 | 19:59:49–20:05:38 |
| User check | crossing: wrong number **0/5**; problem: one person alone shown as P2/P4 (5 times in the log: P1 left, the other kept P2) | numbers move up correctly, alone = P1, crossing **0** wrong; problem: box colour changed when the number moved | **all pass**: standing at the edge keeps the same person, colour stays when the number moves, no repeated colours, out 5 s then back = new person, crossing **0** wrong |
| Cause found | rule (numbers kept) | (1) same person re-counted near the edge: 8 new uids in 16 s at P1 (lost > 0.7 s at the edge); (2) `uid mod 8` gave two people the same colour (uid 13 and 21) | — |
| fps mean / min / max | 28.96 / 27.0 / 30.0 | 29.03 / 28.0 / 30.0 | 29.16 / 28.0 / 30.0 |
| fps samples (5 s) / frames | 102 / 14889 | 53 / 7854 | 66 / 9851 |
| cpu0 mean / max (s ≥ 99%) | 56.2 / 97 (0) | 55.6 / 100 (1) | 57.1 / 100 (1) |
| cpu1 mean / max (s ≥ 99%) | 55.0 / 98 (0) | 51.7 / 90 (0) | 54.4 / 97 (0) |
| GR3D% mean / max | 62.6 / 99 | 62.6 / 99 | 61.6 / 99 |
| RAM max | 1845 MB | 1853 MB | 1853 MB |
| CPU / GPU °C max | 53.0 / 53.0 | 53.0 / 53.0 | 51.0 / 50.5 |
| enter / exit / rejoin / renumber | 21 / 20 / 9 / – | 21 / 20 / 3 / 9 | 11 / 11 / 4 (3 hidden + 1 regrace) / 5 |
| Camera reconnects | 0 | 0 | 0 |

## v3 settings (app defaults)
| Setting | Value | Where |
|---|---|---|
| `--edge-margin` | 0.04 (51 px left/right, 29 px top/bottom; yellow lines in the video) | app |
| `--edge-ttl` | **1.5 s** | app default (PersonIds default stays 0.7) |
| `--regrace` | **2.0 s** | app default (PersonIds default stays 0 = off) |
| `--hidden-ttl` | 4.0 s | app |
| rejoin gate | 1.2 × box height + up to 0.25 × frame width (grows 0.3 × frame width per second lost); box height within ×2.2 | PersonIds |
| `--tracker` | `iou` (`config_tracker_IOU.yml`); `nvdcf` = `test/tracker_nvdcf_tuned.yml` (NvDCF_perf with `maxShadowTrackingAge` 30 → 60), not tested | app |
| `--interval` | 0 | app |

Note: with v3, someone who disappears at the edge and comes back at the same place within 3.5 s (1.5 s until exit + 2.0 s regrace) is the same person; after that, a new person.

## Files (Jetson `~/safety/perception/test/results/cam/`)
- v1 `A_iou_v1.*`, v2 `A_iou_v2.*`, v3 `A_iou_v3.*` (`.log`, `.tegra`, `_events.jsonl`, `_summary.json`)
- Not counted: `app_smoke.*` (45 s nvdcf start-up check, nobody in view), `A_iou_aborted.*` (stopped: log was not live), `A_iou_180s.*` (ended before the walk test)

## P1–P3: PPE 3-class model in the app (21:04–21:30, evening/dark)
Same app, pipeline and camera as v3, with the PPE model `yolov8n_ppe3_416` (person, helmet, vest; see `../2026-10-15_ds_ppe3_5W/`) instead of COCO. Helmets / vests are drawn as thin boxes and given to people by `app/ppe_assign.py` (helmet centre in the top 35 % of the person box, vest centre in 20–75 %). Run: `bash run_person_app.sh P<n> --seconds 600 --tracker iou --interval 0 --rtsp-bind 0.0.0.0`.

### What changed per round
| | P1 | P2 | P3 |
|---|---|---|---|
| Person label | `P1 H✓ V✗` (H/V from this frame only) | `P1 0.87 H✓ V✗` (`obj_meta.confidence` of the person box, 2 decimals; outside 0..1 → `--`) | as P2, H/V from `PpeSmoother` (`H?` / `V?` at first) |
| Helmet / vest label | `H` / `V` | `H 0.72` / `V 0.65` | as P2 |
| Log every 5 s | fps line | + `conf` line: n / mean / min / invalid per class | + `held=` in the fps line |
| `pre-cluster-threshold` | 0.52 all classes | 0.52 all classes | **person 0.30, helmet 0.40, vest 0.35** (NMS 0.45, topk 300 unchanged) |
| Hidden person | box disappears | box disappears | last box kept up to **0.6 s** (`--hold`), thin line, `P1 -- H✓ V✗` |
| Run (wall time) | 21:04:22–21:10:43 | 21:11:13–21:17:25 | 21:19:57–21:29:57 |
| Stopped by | Ctrl-C in tmux (rc=1, see note) | `kill -INT` python (rc=0) | time limit 600 s (rc=0) |
| fps mean / min / max | 29.05 / 27.81 / 30.0 | 29.12 / 24.0 / 30.0 | 29.11 / 27.8 / 30.0 |
| fps samples / frames | 72 / 10643 | 71 / 10444 | 117 / 17098 |
| cpu0 mean / max | 58.5 / 100 | 53.7 / 99 | 57.4 / 95 |
| cpu1 mean / max | 53.0 / 99 | 51.5 / 98 | 55.5 / 99 |
| GR3D% mean / max | 57.9 / 99 | 56.8 / 99 | 57.8 / 99 |
| RAM max | 2040 MB | 2047 MB | 2041 MB |
| CPU / GPU °C max | 42.0 / 41.5 | 47.5 / 47.0 | 47.0 / 46.0 |
| enter / exit / rejoin / renumber | 11 / 18 / 7 / 0 | 3 / 6 / 3 / 0 | 21 / 31 / 14 / 7 |
| Camera reconnects | 0 | 0 | 0 |

Note P1: Ctrl-C in tmux also stopped the redaction `awk` and `tee`, so `P1.log` has no `stop:` / summary lines and the script skipped its secret check. `P1_summary.json` and `P1_events.jsonl` are complete, and a manual check of the P1 files found no password. Later rounds stop only the python process (`kill -INT <pid>`).

### Confidence measured (`obj_meta.confidence`)
| Class | P2 (threshold 0.52): n / mean / min | P3 (per-class threshold): n / mean / min | P3 floor = threshold? |
|---|---|---|---|
| person | 632 / 0.866 / 0.524 | 7039 / 0.692 / 0.301 | yes (0.30) |
| helmet | 9 / 0.657 / 0.582 | 189 / 0.648 / 0.402 | yes (0.40) |
| vest | 850 / 0.734 / 0.521 | 4335 / 0.610 / 0.350 | yes (0.35) |

- **nvinfer reads the per-class values:** the log has no unknown-key warnings, and each class stops at its own threshold in P3 (0.301 / 0.402 / 0.350). The DeepStream-Yolo parser filters with `perClassPreclusterThreshold[class]` (`nvdsparsebbox_Yolo.cpp:82`).
- **P2:** with threshold 0.52 everything below 0.52 was cut inside nvinfer, so the confidence at the moment a person or vest was lost cannot be seen. Just before a person was lost, one 5 s window had mean 0.62 / min 0.53.
- **P3:** the lower thresholds keep more weak boxes (person n ×11, vest ×5), and the mean drops (person 0.87 → 0.69).
- **Invalid values:** 0 in every round. The IOU tracker passes on only boxes from the detector, so `--` never showed on a detector box. Hidden people are covered by the 0.6 s hold.
- **Vest without a person:** in P3, several 5 s windows have 30–140 vests and 0 persons (e.g. 21:27:26–21:27:41, 21:28:31–21:29:16). The person was in view but not detected.

### Hold 0.6 s and PpeSmoother (P3)
- **Hold:** people `PersonIds` keeps as hidden for at most `--hold` s (default 0.6) are drawn from `mgr.people` with their last box (border 1, same colour) and `P<n> -- H.. V..`. `person_ids.py` is not changed, and `In frame` is not changed (hidden people were already counted). `held=1` in 14 of 119 log samples.
- **`app/ppe_smooth.py` `PpeSmoother`:** keeps a per-uid window of the last 20 frames in which that person was seen.
  - ✓ when the item is present in ≥ 30 % of the window, ✗ when it is below 10 %; in between the last status is kept.
  - `?` until the person has 8 frames; if the first decision falls in the 10–30 % band it stays `?`.
  - Status is kept while the person is hidden and after a regrace rejoin, and dropped when the person has left.
  - `No helmet` / `No vest` (top left) count people in the frame with ✗; `?` is not counted.
- **Tests:** `app/test_ppe_smooth.py` has 10 tests: 1-in-3 flicker stays ✓, removed for 1 s turns ✗ (before 29 frames), a new person is `?` for the first 7 frames, plus 10 % / 30 % edges and hysteresis. Pass on the PC (Python 3.14) and the Jetson (3.6.9); `test_ppe_assign.py` 16/16, `test_person_ids.py` 17/17.

### Problems seen (user's GIFs from the RTSP output)
| | Problem | Seen |
|---|---|---|
| (a) | ppe3 does not find a person who bends down, sits, or is behind a desk | P2: person sitting behind the desk at conf 0.52–0.77, then lost; P3 log has many windows with vests and no person |
| (b) | A knitted beanie is detected as a helmet | conf 0.76 |
| (c) | The overlay text at the top left covered the Tapo date / time | **fixed**: overlay moved down 40 px (`person_count_app.py`, `y_offset = 50 + 32 * i`); compiles on the PC and on the Jetson (Python 3.6), md5 `f3ea9d71…` both sides; not run on the camera yet |

(a) and (b) come from the model's training data, not the app. Model tuning is skipped for now: the team will retrain ppe3 with frames from the real camera.

### Conclusion P1–P3
- **Keep the app and `PpeSmoother`:** 29 fps at 5W with the ppe3 model, per-class thresholds, the 0.6 s hold and steady H/V; no camera drop in 3 rounds.
- **Wait for the next ppe3 model before judging PPE results:** people sitting / bending / behind furniture are missed, and beanies count as helmets. Re-check the per-class thresholds with the new model (P3 values are a first guess, not tuned).

### Files (Jetson `~/safety/perception/test/results/cam/`)
`P1.*`, `P2.*`, `P3.*` (`.log`, `.tegra`, `_events.jsonl`, `_summary.json`). Config before P3: `pre-cluster-threshold=0.52` in `[class-attrs-all]`.
