# Recorded-clip A/B: one model vs two models, COCO 416 vs 320, file vs real time (2026-10-15, 22:39–23:13)

Why: in the live two-model runs D1/D2 (COCO person → ppe3 helmet / vest), people were seen in only ~1/3 of the frames before the tracker, and vests never appeared (`(2,*)` = 0 even with a vest worn in front of the camera). To get a repeatable scene, the camera was recorded once and the same clip was run through every setup.

## Conclusion
- **Use COCO 320 → ppe3_hv as the main setup for now.** On the clip, it sees people as often as COCO 416. Vest detection is the same (47 % standing, ppe3 runs every other frame). Its results are identical frame by frame between runs and between file and real-time mode. It runs at 31–32 fps against the camera's ~29.
- **The 38 fps target is not met:** COCO 320 → ppe3_hv reaches **32.44 fps** at most (file). COCO 320 alone does 48.3 fps, but two models gain only +1.8 fps over 416. GR3D mean is 67 % and CPU mean 78–84 %, so the limit now looks like CPU, not GPU (not profiled).
- **COCO 416 is not repeatable:** the same clip gave people in **72.1 %** of frames in one run and **98.9 %** in another (COCO 416 alone, file vs real time). 680 frames differ, and conf differs by up to 0.163. COCO 320 gives the same result every time (0 frames differ, conf diff 0.000). The cause is unknown. The live D1/D2 runs used COCO 416.
- **Real-time playback did not reproduce the live failure:** COCO 416 → ppe3_hv played at clip speed gave people 81.6 % and vests 47.0 %, the same as file mode. So "the Jetson is too slow" is not confirmed as the cause of the live D1/D2 result.
- **Two models do not block each other** on the clip, and their order makes no difference ((ง) vs (จ)).
- **ppe3 finds people poorly:** 17–48 % of frames while the person stands or sits; COCO finds 75–100 %. This confirms problem (a) in `../2026-10-15_person_count_app/`.

## Setup
| Item | Value |
|---|---|
| Board | Jetson Nano 4GB, JetPack 4.6.1, DeepStream 6.0.1, **5W** (`nvpmodel` unchanged, no `jetson_clocks`) |
| Clip | `test/results/cam/clean_ppe_01.mp4` (Jetson only, not committed, not copied off the machine): Tapo stream1 H.264 1920×1080 recorded as-is with `test/record_clip.sh` (rtspsrc → rtph264depay → h264parse → mp4mux, no decode, no inference), 22:39:58–22:41:28, **87.0 s, 2531 frames (~29.1 fps)**, 15.7 MB, evening / indoor light |
| What the user did | walk in, stand with vest 20 s → stand without vest 20 s → vest on and sit 20 s → bend → walk out |
| App | `app/person_count_app.py` with `--source-file` (filesrc → qtdemux → h264parse → nvv4l2decoder; no watchdog / reconnect; stops at EOS), IOU tracker, `--debug-objs` |
| File mode | no clock sync, nvstreammux `live-source=0` → fps = most the pipeline can do |
| Real-time mode | `--realtime`: `identity sync=true` before the decoder (frames released at their own times, ~29.1 fps), nvstreammux `live-source=1` like the camera |
| Measure | `--debug-objs` writes every frame's objects **before nvtracker** as `(unique_component_id, class_id, conf)` to `<run>_objs.jsonl`; `test/clip_ab_report.py` gives % of frames with each key; fps from the app's 5 s samples; tegrastats 1 s |
| Scripts | `test/run_clip_ab.sh` (C1a–C1e), `test/run_clip_320.sh` (C1Ra, C1Rd, C1a320, C1d320, C1Rd320), 20 s cooldown between runs |

Models / configs
| Name | Config | gie | interval |
|---|---|---|---|
| COCO 416 | `test/config_infer_cam_person.txt` (YOLOv8n COCO 416×256, person only, threshold 0.35) | 1 | 0 |
| COCO 320 | `test/config_infer_cam_person_320.txt` (same, model files 320×192) | 1 | 0 |
| ppe3 | `models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_416.txt` (person 0.30 / helmet 0.40 / vest 0.35) | 1 | 0 or 1 |
| ppe3_hv | `models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_hv.txt` (same engine, person filtered out, no `onnx-file` so it cannot rebuild) | 2 | 1 (own config) |

### Clip segments
Taken from where ppe3 alone sees the vest (C1b). The video was not watched, so the edges are approximate.
| Segment | Clip time |
|---|---|
| before the sequence (COCO sees a person 100 %) | 0–12 s |
| standing, vest on | 14–38 s |
| standing, vest off | 38–58 s |
| sitting, vest on | 58–68 s |
| bending, walking out | 68–88 s |

## COCO 320×192 model
| Item | Value |
|---|---|
| Export (PC) | same as the baseline: `perception/export/.venv`, `export_ds_yolov8.py` (forces `dynamo=False`), `python -I ../export_ds_yolov8.py -w yolov8n.pt -s 192 320 --opset 12 --simplify` (yolov8n.pt md5 `95a2449609c73cd69a072b09daaff0cc`) |
| ONNX | `yolov8n_coco_320x192.onnx`, 12700474 bytes, md5 `3eae234185024d8f5c201f700114388c`, opset 12, IR 7 |
| onnxruntime check | input `input` [1, 3, 192, 320] float → output `output` [1, 1260, 6] float; class column 0…79; same op set as 416 |
| Engine (Jetson) | built by nvinfer on the first run (`B320_build`): **6 min 26 s** (4.3 s → 390.7 s), written to `app/model_b1_gpu0_fp16.engine`, moved by hand to `models/yolov8n_coco_320x192_b1_gpu0_fp16.engine`, **12406057 bytes**, md5 `c938a5d38b748e738a5acd6da084aa12`; every later run logs `deserialized trt engine` |

## Results: % of frames with each object before the tracker (2531 frames per run)
Person = `(1,0)`; vest = `(1,2)` for ppe3 alone, `(2,2)` for ppe3_hv. No helmet in any run (none worn).

| Run | Setup | Mode | Person all | before | vest stand | no-vest stand | sit | bend / out | Vest stand | sit | no-vest |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1a (ก) | COCO 416 | file | 72.1 | 99.7 | 74.9 | 89.6 | 90.3 | 30.9 | – | – | – |
| C1Ra (R-ก) | COCO 416 | real time | **98.9** | 100 | 98.1 | 100 | 95.8 | 100 | – | – | – |
| C1a320 (ก320) | COCO 320 | file | 82.0 | 100 | 67.8 | 84.6 | 82.6 | 83.9 | – | – | – |
| C1b (ข) | ppe3, interval 0 | file | 20.1 | 4.2 | 16.7 | 38.6 | 47.9 | 3.0 | 93.8 | 31.9 | 0 |
| C1c (ค) | ppe3, interval 1 | file | 20.0 | 23.7 | 19.9 | 27.5 | 37.2 | 3.4 | 46.8 | 16.7 | 0 |
| C1d (ง) | COCO 416 → ppe3_hv | file | 82.1 | 100 | 84.3 | 94.6 | 91.0 | 56.2 | 47.0 | 16.7 | 0 |
| C1e (จ) | ppe3_hv → COCO 416 (order swapped) | file | 78.7 | 100 | 79.5 | 92.7 | 91.7 | 48.8 | 47.0 | 17.0 | 0 |
| C1Rd (R-ง) | COCO 416 → ppe3_hv | real time | 81.6 | 100 | 81.0 | 93.3 | 91.7 | 58.7 | 47.0 | 16.7 | 0 |
| C1d320 (ง320) | COCO 320 → ppe3_hv | file | 82.0 | 100 | 67.8 | 84.6 | 82.6 | 83.9 | 46.8 | 17.0 | 0 |
| C1Rd320 (R-ง320) | COCO 320 → ppe3_hv | real time | 82.0 | 100 | 67.8 | 84.6 | 82.6 | 83.9 | 47.0 | 16.7 | 0 |

- **ppe3 vest:** 93.8 % standing with the vest, 0 % without it (no false vest), 31.9 % sitting. At interval 1 these halve exactly (46.8 / 16.7 %), and the two-model runs match that.
- **COCO 320 vs 416 while standing with the vest:** 320 sees the person less (67.8 vs 74.9–98.1 %), but more while bending / walking out (83.9 vs 30.9–100 %).

## Speed and load
| Run | fps mean / min / max | cpu0 mean / max | cpu1 mean / max | GR3D% mean / max |
|---|---|---|---|---|
| C1a COCO 416, file | 43.62 / 43.4 / 43.8 | 85.0 / 100 | 77.1 / 95 | 85.1 / 99 |
| C1Ra COCO 416, real time | 30.0 / 30.0 / 30.0 | 56.9 / 100 | 52.7 / 82 | 62.7 / 99 |
| C1a320 COCO 320, file | **48.29** / 46.99 / 48.8 | 89.6 / 100 | 80.5 / 99 | 59.7 / 99 |
| C1b ppe3 i0, file | 47.18 / 46.0 / 47.8 | 83.9 / 99 | 83.2 / 98 | 79.6 / 99 |
| C1c ppe3 i1, file | 65.6 / 62.8 / 69.8 | 77.7 / 100 | 80.5 / 97 | 52.5 / 99 |
| C1d COCO 416 → hv, file | 30.61 / 29.8 / 31.19 | 78.8 / 100 | 75.5 / 99 | 81.7 / 99 |
| C1e hv → COCO 416, file | 30.16 / 28.8 / 30.8 | 80.4 / 100 | 72.3 / 99 | 79.0 / 99 |
| C1Rd COCO 416 → hv, real time | 30.45 / 30.0 / 30.81 | 75.6 / 89 | 78.7 / 98 | 82.2 / 99 |
| C1d320 COCO 320 → hv, file | **32.44** / 31.2 / 34.01 | 84.1 / 99 | 78.1 / 93 | 67.1 / 99 |
| C1Rd320 COCO 320 → hv, real time | 31.05 / 30.0 / 34.0 | 79.8 / 100 | 69.2 / 98 | 66.5 / 99 |

Notes:
- In real-time mode fps is capped by the clip, so it is not a maximum.
- In file mode the whole pipeline is measured: decode 1080p, mux, inference, tracker, Python probe, OSD and H.264 encode to RTSP. These are full-app numbers, not inference-only like `../2026-10-15_ds_ppe3_5W/`.

## COCO 416 is not repeatable
Per-frame comparison of "person before the tracker" on the same clip:
| Pair | both | only first | only second | neither | conf diff median / max |
|---|---|---|---|---|---|
| C1a vs C1Ra (COCO 416 alone, file vs real time) | 1824 | 1 | **680** | 26 | 0.002 / **0.163** |
| C1a vs C1d (COCO 416 alone vs with ppe3_hv) | 1803 | 22 | 275 | 431 | 0.000 / 0.163 |
| C1d vs C1Rd (two models, file vs real time) | 1901 | 177 | 164 | 289 | 0.000 / 0.163 |
| C1a320 vs C1Rd320 (COCO 320 alone vs two models real time) | 2076 | **0** | **0** | 455 | **0.000 / 0.000** |

- **Same input, different output:** the frames are identical and the engine is deterministic, so COCO 416 should give the same result every time. COCO 320 does.
- **Where to look next (cause unknown):** the 416×256 preprocessing (1280×720 letterboxed to 416×234 + padding) or the 416 engine (built 17:23 for the baseline).
- **Possible link to the live problem:** the live D1/D2 drop (people in ~1/3 of frames) used COCO 416. This is not proven.

## Not done / next
- Live check of COCO 320 → ppe3_hv with `--debug-objs` (5 min): do people / vests appear about as often as on the clip?
- Reaching ≥ 38 fps needs more than a smaller COCO model. Options: ppe3 `interval=2`, or less CPU work (OSD / encode / probe). Measure which part is the limit first.
- Cause of the COCO 416 variation (above).
- Temporary debug items still in place: app `--debug-objs` (off by default), `test/config_infer_ppe3_hv_nofilter_DEBUG.txt` (D3d).

## Files (Jetson `~/safety/perception/test/results/cam/`)
- Clip runs: `C1a`–`C1e`, `C1Ra`, `C1Rd`, `C1a320`, `C1d320`, `C1Rd320` (`.log`, `.tegra`, `_objs.jsonl`, `_summary.json`, `_events.jsonl`)
- Engine build `B320_build.*`; test of `--source-file` `T_src.*`
- Live debug runs before the clip: `D1`, `D2a` (first D2, ended before the vest test), `D2`, `D3` (ppe3_hv alone, interval 1: nothing at all), `D3c` (ppe3 alone control), `D3d` (two models, ppe3_hv without the person filter: `(2,0)` in only 4 of ~1300 frames)
- Clip `clean_ppe_01.mp4` (stays on the Jetson)
