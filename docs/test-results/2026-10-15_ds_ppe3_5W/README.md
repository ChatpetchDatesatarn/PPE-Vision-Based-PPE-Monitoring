# PPE 3-class models on DeepStream 6.0.1, Jetson Nano 5W (2026-10-15)

FP16 engine build + fps of the two PPE 3-class models (person, helmet, vest) from `docs/test-results/2026-10-15_train_ppe3_colab/`, measured exactly like the COCO baseline in `docs/test-results/2026-10-15_ds_yolov8n_coco_5W/`. Only the model changes. No camera in this run, and no other app ran on the Jetson during the test.

## Summary
| Model | interval=0 fps | vs baseline | interval=1 fps | vs baseline | engine build | test mAP50 |
|---|---|---|---|---|---|---|
| Baseline YOLOv8n COCO (80 cls) | 43.89 | — | 88.51 | — | 6 min 28 s | — |
| **yolov8n_ppe3_416** | **47.97** | +9.3 % | **96.65** | +9.2 % | 6 min 27 s | 0.876 |
| yolo11n_ppe3_416 | 45.45 | +3.6 % | 90.42 | +2.2 % | 7 min 46 s | 0.882 |

- Both engines build with no errors on TensorRT 8.2. yolo11n works too (no fallback needed).
- yolov8n_ppe3 is 5.5 % faster than yolo11n_ppe3 at interval=0 (47.97 vs 45.45), even though yolo11n has fewer GFLOPs (1.70 vs 2.28). Its fps is also steadier (min 47.66 vs 44.78), and it uses less CPU (61 % vs 69 %).
- Accuracy is a tie (difference 0.006 mAP50). On this Jetson, yolov8n_ppe3_416 is the better pick on speed.
- Both models keep > 15 fps headroom over a 30 fps camera at interval=0.

## Test environment
Same as the baseline: Jetson Nano 4GB, JetPack 4.6.1, **5W** (`nvpmodel -q`: `NV Power Mode: 5W`, checked after the runs), micro-USB, 2 CPU cores, no `jetson_clocks`. DeepStream 6.0.1 (TensorRT 8.2, CUDA 10.2), DeepStream-Yolo `2894bab`, the same `libnvdsinfer_custom_impl_Yolo.so` as the baseline. Background load: Docker mosquitto, recorder, dashboard only (same as the baseline). tmux `cira` idle.

## Model files (Jetson `~/safety/perception/models/<run>/`)
| run | ONNX md5 (PC = Jetson) | labels | pre-cluster-threshold | engine | engine bytes | engine md5 |
|---|---|---|---|---|---|---|
| yolov8n_ppe3_416 | `efdd6887f84417d4843857238ca1a77f` | person, helmet, vest | 0.52 | `yolov8n_ppe3_416_b1_gpu0_fp16.engine` | 14560420 | `c9098b5b6f52d13a9a0391a4e6e817a6` |
| yolo11n_ppe3_416 | `64b8e766c541b40dfb8dcf7bdd053427` | person, helmet, vest | 0.38 | `yolo11n_ppe3_416_b1_gpu0_fp16.engine` | 10123978 | `491d1bc5baea4f4b49116f91b726efa3` |

- Copied: `.onnx`, `labels.txt`, `info.json`, `run_export.py`, `config_infer_<run>.txt` (no `.pt`).
- `config_infer_<run>.txt` (edited on the PC, then copied): `onnx-file`, `labelfile-path`, `model-engine-file` use absolute paths in the model's own folder. `custom-lib-path` = `/home/jetson/safety/perception/DeepStream-Yolo/nvdsinfer_custom_impl_Yolo/libnvdsinfer_custom_impl_Yolo.so` (the file the baseline config points to with `../DeepStream-Yolo/...`). All other values are as exported: FP16, 3 classes, `maintain-aspect-ratio=1`, `symmetric-padding=1`, NMS IoU 0.45, `pre-cluster-threshold` = best_conf, `topk=300`, `interval=1`.
- The `interval` in the infer config is overridden by `[primary-gie] interval` in the app config. The i1 rounds run at ~2× the i0 rounds, which confirms the override.

## Method
- App configs `perception/test/ds_<run>_i0.txt` / `ds_<run>_i1.txt` = copies of the baseline `ds_yolov8n_app.txt` / `ds_yolov8n_app_i1.txt`. Only `config-file=../models/<run>/config_infer_<run>.txt` and the header comments change. Settings: `sample_720p.mp4` looped, streammux 1280×720 `live-source=0`, OSD on, `fakesink sync=0`.
- Engines were built one at a time in a separate run (`run_smoke.sh <run>_build 1800 ds_<run>_i0.txt`), which was stopped with SIGINT after the first non-zero PERF line. yolo11n was built first.
- fps rounds: `perception/test/run_ppe3_bench.sh` in tmux `ds`. It does 30 s cooldown, then `run_smoke.sh <run>_i<N> 70 ds_<run>_i<N>.txt` (`timeout --foreground -s INT 70`, tegrastats 1 s). Order: v8n i0, v8n i1, 11n i0, 11n i1.
- Every round logs `deserialized trt engine from :…/models/<run>/<run>_b1_gpu0_fp16.engine`, so no round includes a build.
- fps = `**PERF` every 5 s, the first sample (0.00) is dropped → 12 samples per round. tegrastats means cover the whole run (~73 s including start-up). CPU% = mean of the 2 online cores. Parsed with `perception/test/summarize_bench.py`.

## Engine build
| Item | yolov8n_ppe3_416 | yolo11n_ppe3_416 | baseline COCO |
|---|---|---|---|
| Build time (nvinfer `try rebuild` → `buildModel` done) | **6 min 27 s** (3.5 s → 390.9 s) | **7 min 46 s** (4.0 s → 469.5 s) | 6 min 28 s |
| Errors | none | none | none |
| RAM max / mean during build | 2226 / 2100 MB | 2213 / 2131 MB | 2180 / 2075 MB |
| CPU% mean / max | 51.3 / 81.5 | 52.2 / 83.0 | 51.4 / 92.0 |
| CPU / GPU °C max | 41.0 / 40.5 | 41.0 / 41.0 | 39.5 / 39.0 |
| First PERF after build (i0) | 48.17 | 43.96 | — |

Log lines during the build, the same for both models:
- `ERROR: Deserialize engine failed because file path: …/<run>_b1_gpu0_fp16.engine open error` and the two `deserialize … failed, try rebuild` WARNs. These are expected, because no engine existed yet.
- `WARNING: [TRT]: onnx2trt_utils.cpp:366: Your ONNX model has been generated with INT64 weights, while TensorRT does not natively support INT64. Attempting to cast down to INT32.`
- `WARNING: [TRT]: onnx2trt_utils.cpp:392: One or more weights outside the range of INT32 was clamped`
- `WARNING: [TRT]: Tensor DataType is determined at build time for tensors not marked as input or output.`
- Engine I/O: `input` 3x256x416 → `output` 2184x6 (both models).
- As in the baseline, nvinfer wrote the engine to `test/model_b1_gpu0_fp16.engine`, not to `model-engine-file`. Each engine was moved by hand to `models/<run>/<run>_b1_gpu0_fp16.engine` right after its build, before the next build started.

## Results
| Model | Round | `interval` | fps mean | min | max | last PERF avg | RAM max / mean | GPU% mean / max | CPU% mean / max | CPU °C max | GPU °C max | rc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline COCO | A | 0 | 43.89 | 43.58 | 44.15 | 43.89 | 1740 / 1684 MB | 84.1 / 99 | 64.9 / 88.0 | 41.5 | 41.0 | 124 |
| baseline COCO | B | 1 | 88.51 | 87.88 | 88.87 | 88.48 | 1741 / 1685 MB | 82.8 / 99 | 69.9 / 84.5 | 43.5 | 43.5 | 124 |
| yolov8n_ppe3_416 | A | 0 | **47.97** | 47.66 | 48.11 | 47.97 | 1987 / 1886 MB | 80.8 / 99 | 61.1 / 86.0 | 43.5 | 43.0 | 124 (timeout) |
| yolov8n_ppe3_416 | B | 1 | **96.65** | 94.97 | 97.16 | 96.73 | 1974 / 1868 MB | 80.2 / 99 | 63.2 / 89.0 | 44.5 | 44.5 | 124 (timeout) |
| yolo11n_ppe3_416 | A | 0 | **45.45** | 44.78 | 45.78 | 45.47 | 1975 / 1881 MB | 82.1 / 99 | 68.6 / 89.0 | 46.0 | 45.5 | 124 (timeout) |
| yolo11n_ppe3_416 | B | 1 | **90.42** | 87.58 | 91.61 | 90.53 | 1973 / 1865 MB | 79.3 / 99 | 77.6 / 91.0 | 46.5 | 45.5 | 124 (timeout) |

Raw PERF samples (5 s each):
- v8n A: 47.66, 48.11, 48.04, 48.07, 48.03, 47.86, 47.93, 47.92, 48.01, 48.01, 48.03, 47.98
- v8n B: 94.97, 96.59, 97.08, 96.49, 97.16, 96.96, 96.93, 96.80, 96.87, 96.30, 96.89, 96.80
- 11n A: 44.78, 44.87, 45.70, 45.68, 45.54, 45.59, 45.55, 44.88, 45.66, 45.62, 45.78, 45.72
- 11n B: 87.58, 91.21, 91.27, 91.32, 90.35, 89.10, 91.41, 91.14, 91.16, 91.61, 91.04, 87.85

## Notes
- Both PPE models are faster than the COCO baseline at the same input size. A likely cause is the 3-class head and fewer boxes in post-processing and OSD, but this was not checked separately.
- yolo11n is slower than v8n despite lower GFLOPs. A likely cause is that its C2PSA attention and depthwise convs run less efficiently on TensorRT 8.2 / Maxwell. This was not profiled.
- RAM during the runs is ~200 MB higher than in the baseline (1886 vs 1684 MB mean). The idle RAM before the runs was also higher (887 MB used at 20:08 vs not recorded for the baseline), so this is not attributed to the model.
- The yolo11n rounds ran last and were 2–3 °C warmer. No throttling was seen.
- Not checked here: detection quality on real Tapo frames, the RTSP camera, nvtracker, the pyds probe and MQTT. All of these add load.
- Raw logs on the Jetson: `~/safety/perception/test/results/{yolov8n,yolo11n}_ppe3_build.*`, `{yolov8n,yolo11n}_ppe3_416_i{0,1}.*`, `ppe3_bench.out`.
- `.onnx` and `.engine` files are not stored here.
