# 2026-10-16 — person_count_app on two YouTube clips (internal test only)

Clips are from YouTube: internal tests only. **Never commit the clips or the pictures** (`*.mp4` and
`docs/test-results/2026-10-16_yt_clips/*.jpg` are in `.gitignore`). On the Jetson only:

| Name on the Jetson (`perception/test/results/cam/`) | Source file (project folder, PC) | Video | md5 |
|---|---|---|---|
| `yt_workers_ppe.mp4` | `Amazing Skill Worker #russia … #music.mp4` | 720×1280 portrait, 30 fps, 383 frames (12.9 s), H.264 High + AAC | a34533a3e0074988c891a10ce3ca7ec1 |
| `yt_drone_site.mp4` | `SiteCloud AERIAL Drone Photography and Video of Construction Site.mp4` | 1280×720, 29.97 fps, 931 frames (31 s), H.264 Main + AAC | 7a5fc2ba31074356ba5d6fc94a5be474 |

## App changes for this test
- `--mux-padding` (only with `--source-file`): nvstreammux `enable-padding=1`, so the portrait clip keeps its shape
  with black bars (picture = x 437–843 of the 1280×720 frame, scale 0.5625) instead of being stretched
- `--source-file` takes the video only: the AAC pad of qtdemux stays unlinked (was already so, now documented)
- `--debug-objs` dump now has the box of each object (`[comp, class, conf, l, t, w, h]`, nvstreammux px) and a
  second file `<run>_ppe.jsonl` with the H / V state of every labelled person per frame
- Tests: 7 app test files OK on the PC and the Jetson

## Runs
`--source-file --realtime --mux-padding --events on --debug-objs`, 3 runs per clip back to back
(`yt_workers_ppe_r1..3`, `yt_drone_site_r1..3`), 12:22:51–12:26:35, all rc=0, secret check clean.
Default models (COCO 320×192 person → ppe3_hv helmet / vest, interval 0 / 1), tracker IOU, fallback mode (no CiRA).
The 3 runs of a clip gave the same numbers (± 0.3 % of frames), so one set is shown.

## Workers clip (`yt_workers_ppe`) — 4–5 workers, all with helmet and vest, close up
| Item | Value |
|---|---|
| Frames with person (1,0) / helmet (2,1) / vest (2,2) | **54.8 %** / **35.8 %** / **34.5 %** (before the tracker) |
| Objects per frame | person 0.77, helmet 0.48, vest 0.47 (there are 2–5 people in view: most are missed, crowded / overlapping / cut by the frame edge) |
| Confidence (median) | person 0.53 (min 0.35), helmet 0.58, vest 0.57 |
| fps | r1 29.6, r2 31.6, r3 31.2 (whole clip shorter than two 5 s windows) |
| Events | **2 per run, both `no_vest`** (6 in total), 0 no_helmet |

H / V labels (% of the frames the person was labelled; same in all runs):

| Person | Frames | Helmet ✓ / ✗ / ? | Vest ✓ / ✗ / ? |
|---|---|---|---|
| uid 1 | 201 | 89 / 7 / 3 % | 80 / 14 / 6 % |
| uid 2 | 62 | 89 / 0 / 11 % | 31 / 58 / 11 % |
| (+1 track shorter than 15 frames) | | | |

Both `no_vest` events are **false alarms** (everybody wears a vest):
- uid 1 (`…-001-nv`, conf 0.575): wears a vest, but the vest box was missed for > 2 s while he bent over
  (`workers_snapshot_122317-001.jpg`, label `H✓ V✗`)
- uid 2 (`…-002-nv`, conf 0.36–0.41): a worker cut by the right edge of the picture, box 0.04–0.09 wide — the vest is
  not visible (`workers_snapshot_122311-002.jpg`). PersonIds' edge zone is measured on the 1280×720 frame, not on the
  padded picture, so this person is not treated as "at the edge"
- Helmet / vest are also found on people the person model misses (frame 314: 1 helmet + 3 vests, 0 persons);
  `assign_ppe` cannot use them

## Drone clip (`yt_drone_site`) — aerial view, workers small, several excavators
| Item | Value |
|---|---|
| Frames with person / helmet / vest | **0.6 %** (6 frames) / 0 % / 1.2 % (11 frames) |
| Events / violations / snapshots | 0 / 0 / 0 (no person track lasted long enough for a ✗ status) |
| fps | 32.3 / 32.4 / 32.7 |

All detections (run 1, boxes drawn in `drone_f*.jpg`):
- Person, **correct**: frame 196, h 54 px, conf 0.39 — a worker in the lower left (`drone_f0196.jpg`)
- Person, **false**: frames 567–572 (5 frames), h 80–87 px, conf 0.35–0.41 — a pile of pipes / material
  (`drone_f0570.jpg`)
- Vest (2,2), **all false**: 11 frames, h 29–80 px, conf 0.36–0.50 — on the yellow excavators (arm / cab)
  (`drone_f0362.jpg`, frame 906 h 80 conf 0.36)
- No person detection on an excavator; the yellow excavators only produce false vests

Estimated person height in the drone picture (1280×720, by eye): workers in the foreground 35–55 px,
mid field 15–25 px, background < 15 px. Most real workers are never detected.

## Size limits (box height in the 1280×720 frame)
| | Workers clip (scale 0.5625) | Drone clip |
|---|---|---|
| Smallest person found | 153 px (conf 0.41); p10 195, median 313 | 54 px (conf 0.39), one frame only |
| Smallest helmet found | 31 px (conf 0.49); p10 41, median 58 | none |
| Smallest vest found | 55 px (conf 0.39); p10 88, median 121 | only false ones (29–80 px) |

Conclusion (rough, 2 clips, YOLOv8n COCO 320×192 + ppe3 416):
- **Person:** reliable only from about **150 px** tall; 50–90 px is found rarely (1 of hundreds of frames in the
  drone clip) and at conf ≈ 0.35–0.4, the same level as the false detections
- **Helmet / vest:** need the person to be about **150 px or more** (helmet box ≥ ~30 px, vest box ≥ ~55 px);
  below that (drone clip) none are found, only false vests on yellow machines
- The Tapo camera should be placed so that a worker is at least ~150–200 px tall in the 1280×720 frame
  (≈ 1/4 of the image height) where PPE must be checked

## Pictures (not committed)
- `workers_snapshot_122317-001.jpg`, `workers_snapshot_122311-002.jpg`: event snapshots (640 px, OSD)
- `workers_f0136.jpg`, `workers_f0358.jpg`: pre-tracker boxes (P red / H white / V orange, with height)
- `drone_f0196.jpg` (correct person 54 px), `drone_f0570.jpg` (false person on pipes), `drone_f0362.jpg` (false vest on an excavator)

## Clean-up after the user's Dashboard check
13:02: recorder stopped → `DELETE FROM events` (6) + VACUUM, 6 snapshots deleted → `/api/health` events 0, snapshots 0.

## Fewer false no_vest (2026-10-16, helmet logic unchanged)
- `no_vest` hold 2 → **4 s** (`violations.HOLD_S`, app option `--vest-hold`, default 4.0); no_helmet stays 2 s
- Person seen only in part → **vest "?"** for that frame (not judged, no no_vest, not counted compliant); helmet judged
  as before (`violations.vest_judgeable`, options `--partial-edge` 0.02 / `--partial-aspect` 0.25):
  - box within 2 % of the picture's width / height from any edge of the **picture** — with `--mux-padding` the
    picture rect is computed from the decoded size (`content_rect`: here x 437.5–842.5, not the black bars)
  - or box width / height < 0.25
- `PpeSmoother.update(uid, helmet, None)`: a "?" frame adds nothing to the vest history (the vest state stays as it
  was, the label shows V? for that frame); the helmet history is updated as before
- Tests: `test_violations.py` 30 (vest hold 4 s / 2 s helmet / option, content rect, edge with and without padding,
  narrow box, partial person still gets no_helmet), `test_ppe_smooth.py` +2; 3 old tests updated to the 4 s default.
  All 7 app test files OK on the PC and the Jetson

### Workers clip again (`yt_workers_v2_r1..3`, same options as before: `--realtime --mux-padding --events on --debug-objs`)
| Run | no_vest violations / events | uid 1 H ✓/✗/? | uid 1 V ✓/✗/? | uid 2 H ✓/✗/? | uid 2 V ✓/✗/? | fps |
|---|---|---|---|---|---|---|
| before (`yt_workers_ppe_r1..3`) | **2 / 2 per run** | 89 / 7 / 3 | 80 / 14 / 6 | 89 / 0 / 11 | 31 / 58 / 11 | 29.6–31.6 |
| after (`yt_workers_v2_r1..3`) | **0 / 0 per run** | 89 / 7 / 3 | 47 / **0** / 53 | 89 / 0 / 11 | 42 / **0** / 58 | 29.9–32.2 |

- All 3 runs the same; MQTT logger: 0 ds/violation, 0 event, 0 snapshot → nothing to delete (`/api/health` 0 / 0)
- Helmet labels identical to before (no helmet change)
- Cost: vest is "?" for about half of the frames of these two people (close-up portrait clip: they stand at the left /
  right edge of the narrow picture). A worker who really has no vest but is cut by an edge is not reported either

`./ds-start` (events off) afterwards.

## Edge rules split by body part (2026-10-16, replaces the 4-edge vest rule above)
- **Vest "?"**: box at the **left / right** edge of the picture (within 2 % of its width) or width / height < 0.25.
  Top and bottom edges no longer matter for the vest (feet cut at the bottom is common with a close camera)
- **Helmet "?"**: box at the **top** edge (within 2 % of the picture height): the head may be cut off. Other edges do
  not matter for the helmet
- Edges are still those of the real picture with `--mux-padding` (`content_rect`)
- `PpeSmoother.update`: helmet `None` now also leaves the helmet history alone (same as vest `None`)
- `violations.helmet_judgeable` (new) / `vest_judgeable`; tests: 4 edges × helmet / vest on the 1280×720 frame and on
  the padded portrait picture, narrow box (vest ? / helmet judged), head cut (helmet ? but no_vest still sent),
  smoother helmet-None. `test_violations.py` 31, `test_ppe_smooth.py` 13; all 7 app test files OK on the PC and the Jetson

### Check runs (`--realtime --events on --debug-objs`, 1 run each, 13:17–13:19)
| Clip | no_helmet events | no_vest events | ds/violation | Labels (% of labelled frames ✓ / ✗ / ?) | fps |
|---|---|---|---|---|---|
| `yt_workers_ppe.mp4` (`edge_workers`, `--mux-padding`), all wear PPE | **0** | **0** | 0 | uid 1 (201 fr): H 89 / 7 / 3, V 47 / 0 / 53 · uid 2 (62 fr): H 89 / 0 / 11, V 42 / 0 / 58 | 31.02 |
| `clean_ppe_01.mp4` (`edge_home`), no helmet, vest off 38–58 s | **3** (5.0, 36.5, 67.3 s) | **3** (7.0, **46.6**, 77.2 s) | 23 (no_helmet 14, no_vest 9) | uid 1 (2072 fr): H 0 / 83 / 17, V 25 / 65 / 11 | 28.7 |

- Workers clip: no false alarm; labels the same as with the previous rule (nobody touches the top edge there)
- Home clip: **no_vest in the vest-off segment** (run starts 46.6 s, event `…131848-001-nv`) and no_helmet events all
  through → people without PPE are still reported. Helmet "?" 17 %: the standing person's box touches the top edge
  (head close to the top of the picture), which also restarts the no_helmet run a few times (repeat 0 at 5.0, 31.4,
  53.2, 62.3, 72.4 s). no_vest also at 63.4 s (sitting, vest seen in few frames, as before) and 71–87 s (walking out)
- MQTT logger: 6 events, 23 violations, 23 snapshots (20 files: two types share a picture when sent in the same frame)
- Clean-up: recorder stopped → 6 events + 20 snapshots deleted → `/api/health` 0 / 0. `./ds-start` (events off):
  `live_20261016_1320`, first frame 13:20:32
