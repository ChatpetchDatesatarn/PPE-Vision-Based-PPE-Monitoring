# Baseline: DeepStream 6.0.1 + YOLOv8n COCO 416×256 FP16 on Jetson Nano, 5W (2026-10-15)

Pipeline capacity of the v3 perception part with a stock COCO model, before the 3-class PPE model exists. No camera in this run (file source only, so no camera credentials in any config).

## Test environment
| Item | Value |
|---|---|
| Board | Jetson Nano Developer Kit 4GB, JetPack 4.6.1 (L4T R32.7) |
| Power | **5W (`nvpmodel -q`: `NV Power Mode: 5W`, mode 1)**, micro-USB supply, CPU 2 cores online, no `jetson_clocks` |
| DeepStream | 6.0.1 (TensorRT 8.2, CUDA 10.2) |
| DeepStream-Yolo | commit `2894babce8e75c49115dbe0c7b516289ed853565`, `libnvdsinfer_custom_impl_Yolo.so` built with `CUDA_VER=10.2` |
| Model | `yolov8n.pt` (Ultralytics release v8.4.0, md5 `95a2449609c73cd69a072b09daaff0cc`), COCO 80 classes |
| Other load | Docker: mosquitto, recorder, dashboard running in the background |

## ONNX export (PC)
| Item | Value |
|---|---|
| venv | `perception/export/.venv` (Python 3.12): torch 2.14.1+cpu, ultralytics 8.4.177, onnx 1.23.2, onnxslim 0.1.98, onnxruntime 1.31.0 |
| Script | `utils/export_yoloV8.py` at commit 2894bab (md5 `d30e5a8032d7750d134186dda6fae093`, same as the Jetson clone) |
| Wrapper | `perception/export/export_ds_yolov8.py` — forces `torch.onnx.export(dynamo=False)` (torch 2.14 has the parameter) |
| Command | `python -I ../export_ds_yolov8.py -w yolov8n.pt -s 256 416 --opset 12 --simplify` (no `--dynamic`) |
| Output | `yolov8n_coco_416x256.onnx` (12711570 bytes, md5 `ccc402ca261db05d9cffea67949196a0`), opset 12, IR 7 |
| onnxruntime check | input `input` [1, 3, 256, 416] float → output `output` [1, 2184, 6] float; class column 0…79 |
| Labels | `labels_coco.txt`, 80 lines (`person` … `toothbrush`), md5 `3c642e9cc4a35f5b40f4bb37c43926be` |
| Ops | Add, ArgMax, Cast, Concat, Conv, MaxPool, Mul, ReduceMax, Reshape, Resize, Sigmoid, Slice, Softmax, Split, Sub, Transpose |

## Method
- `deepstream-app` with `perception/test/ds_yolov8n_app.txt` (round A) / `ds_yolov8n_app_i1.txt` (round B): `sample_720p.mp4` looped (`file-loop=1`), streammux 1280×720 `live-source=0`, OSD on, `fakesink sync=0` → measures processing capacity, not real-time playback
- nvinfer `config_infer_yolov8n_coco.txt`: FP16 (`network-mode=2`), batch 1, 80 classes, `maintain-aspect-ratio=1`, `symmetric-padding=1`, NMS IoU 0.45, threshold 0.25
- Run with `run_smoke.sh` in tmux `ds`: `timeout --foreground -s INT 70 env -u PYTHONPATH deepstream-app -c …`, tegrastats every 1 s (not root → no NVDEC field)
- Engine built in a separate first run (stopped after the first PERF line), so the 70 s rounds do not include the build; both rounds log `deserialized trt engine from :…/models/yolov8n_coco_416x256_b1_gpu0_fp16.engine`
- fps = deepstream-app `**PERF` every 5 s; the first sample (0.00, pipeline start) is dropped → 12 samples per round; 30 s cooldown before each round
- tegrastats means cover the whole run, including ~9 s of start-up

## Engine build
| Item | Value |
|---|---|
| Build time | **6 min 28 s** (`Building the TensorRT Engine` 17:16:54 → `Building complete` 17:23:22) |
| Engine file | `models/yolov8n_coco_416x256_b1_gpu0_fp16.engine`, **14632313 bytes**, md5 `5cb66362f586e4609e058989d895b532` |
| Where nvinfer wrote it | `test/model_b1_gpu0_fp16.engine` (DeepStream-Yolo builds the engine itself, so `model-engine-file` is not used as the output name) → moved to the `model-engine-file` path by hand |
| Build errors | none; the `Deserialize engine failed … open error` at start is expected (no engine yet) |
| RAM max / mean during build | 2180 MB / 2075 MB |
| CPU% mean / max (2 cores) | 51.4 / 92.0 |
| CPU / GPU °C max | 39.5 / 39.0 |
| Opset 11 fallback | not needed |

## Results
| Round | nvinfer `interval` | fps mean | fps min | fps max | fps average (last PERF) | RAM max / mean | GPU% mean / max | CPU% mean / max | CPU °C max | GPU °C max | rc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0 (infer every frame) | **43.89** | 43.58 | 44.15 | 43.89 | 1740 / 1684 MB | 84.1 / 99 | 64.9 / 88.0 | 41.5 | 41.0 | 124 (timeout) |
| B | 1 (infer every 2nd frame) | **88.51** | 87.88 | 88.87 | 88.48 | 1741 / 1685 MB | 82.8 / 99 | 69.9 / 84.5 | 43.5 | 43.5 | 124 (timeout) |

Raw PERF samples (5 s each):
- A: 43.58, 44.15, 43.85, 43.93, 43.77, 43.95, 43.84, 43.95, 43.94, 43.85, 43.89, 43.92
- B: 87.88, 88.59, 88.78, 88.32, 88.87, 88.24, 88.72, 88.01, 88.64, 88.77, 88.60, 88.69

## Notes
- B is almost exactly 2× A and GPU% stays ~83%, so the pipeline is bound by inference; at 5W, `interval=0` leaves ~14 fps headroom over a 30 fps camera
- Not checked here: detection quality (fakesink, no output video), RTSP camera input, nvtracker, the pyds probe and MQTT — all add load
- Raw logs on the Jetson: `~/safety/perception/test/results/yolo_build.*`, `yolo_A_i0.*`, `yolo_B_i1.*`
- `.pt`, `.onnx`, `.engine` are git-ignored and not stored here
