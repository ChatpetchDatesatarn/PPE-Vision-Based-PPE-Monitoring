# Benchmark: CiRA `darknet_` on Jetson Nano (2026-10-15)

Measured YOLOv4-tiny / YOLOv7-tiny speed with the `darknet_` that ships with CiRA CORE on the Jetson, without opening the GUI.

## Test environment
| Item | Value |
|---|---|
| Board | Jetson Nano Developer Kit 4GB, JetPack 4.6.1 (L4T R32.7.1) |
| Power | **5W mode (nvpmodel mode 1)**, micro-USB supply, CPU 2 cores online (other 2 off), governor `schedutil` |
| Clocks | No `jetson_clocks`, no power-mode change |
| Binary | `~/.cira_core_install/cira_libs_ws/install/lib/cira_lib_yolo/darknet_` (CiRA CORE devel 1.9.4@260527) — CUDA 10.2, cuDNN 8.2.1, `CUDNN_HALF=1`, **built without OpenCV** |
| Environment | `LD_LIBRARY_PATH` the same as the CiRA CORE desktop launcher (see `bench_darknet.sh`) |
| Models | `yolov4-tiny` / `yolov7-tiny` (COCO 80 classes) cfg + weights from AlexeyAB/darknet (master / releases) |
| Input | 200 frames 640x360 (JPG q3) extracted from `test_640x360.avi` (MJPEG, 20 s, 30 fps, made from `dog.jpg` with a slow zoom) |
| Other load | Docker: mosquitto, recorder, dashboard running in the background; simulator on the PC still sending frames |

MD5 of the files used (deleted from the Jetson after the run): see `summary.txt`

## Method
- `detector demo` (video) **can't be used** because `darknet_` has no OpenCV → `Demo needs OpenCV for webcam images.` (log in `results_failed_demo/`)
- Use instead: `darknet_ detector test coco.data <cfg> <weights> -dont_show -ext_output < frames.txt` (feeds the image list via stdin)
- **inference FPS** = 1000 / median of "Predicted in X milli-seconds" (first 10 frames dropped as warm-up) = time spent in the network only
- **e2e ≥** = 200 frames / total wall time of the command (includes model load + JPG decode with stb + drawing + writing `predictions.jpg` every frame on the CPU) → a pessimistic lower bound
- tegrastats every 1 s during each run; GPU% = mean of non-zero samples; 30 s cooldown between runs
- cfg changed only `batch=1`, `subdivisions=1`, `width`, `height` (see `cfg/`)

## Results

| Model | Input | ms/frame (median) | p90 ms | **FPS (inference)** | e2e ≥ FPS | GPU% | GPU °C max | CPU °C max |
|---|---|---|---|---|---|---|---|---|
| YOLOv4-tiny | 416x416 | 73.5 | 73.7 | **13.6** | 4.0 | 62 | 32.5 | 33.5 |
| YOLOv4-tiny | 416x256 | 45.3 | 45.4 | **22.1** | 5.2 | 61 | 33.5 | 34.0 |
| YOLOv4-tiny | 320x192 | 33.8 | 33.8 | **29.6** | 5.6 | 42 | 34.0 | 34.5 |
| YOLOv7-tiny | 416x416 | 93.3 | 93.4 | **10.7** | 4.1 | 76 | 36.0 | 36.0 |
| YOLOv7-tiny | 416x256 | 61.8 | 61.9 | **16.2** | 4.8 | 63 | 36.0 | 36.5 |
| YOLOv7-tiny | 320x192 | 40.4 | 40.6 | **24.7** | 5.4 | 51 | 36.5 | 36.5 |

Power (POM_5V_IN) is not shown by tegrastats on this board → not measured

Detections are correct (e.g. dog 83%, bicycle 57%, truck 44% in `results/yolov4-tiny_416x416.log`)

## Interpretation
- YOLOv4-tiny is ~20–35% faster than v7-tiny at every size
- 416x256 vs 416x416 → ~1.5–1.6x FPS, and closer to the 16:9 camera aspect
- Very stable (p90 ≈ median), temperature ≤ 37°C → no thermal throttling
- GPU% below 99% → the GPU waits on CPU work (only 2 cores in 5W)
- Real CiRA pipeline FPS (runs darknet through `libcira_lib_yolo.so`, uses OpenCV, writes no files) should fall **between** the "inference" and "e2e ≥" columns — measure again when the GUI is opened
- To get ≥15 FPS (inference) at 5W → **YOLOv4-tiny 416x256**

## Files
| File | Contents |
|---|---|
| `summary.txt` | Summary table from `bench_parse.py` + MD5 of weights/video |
| `bench_darknet.sh` | Script used to run the benchmark (on the Jetson) |
| `bench_parse.py` | Script that computes the table from logs/tegrastats (Python 3.6) |
| `bench_run.log` | Start/end time and exit code of each run |
| `cfg/*.cfg` | cfg files at each size used |
| `coco.data` | data file (classes=80, names=coco.names) |
| `results/<config>.log` | darknet_ output per frame (Predicted in … ms + detections) |
| `results/<config>.tegra` | Raw tegrastats every 1 s |
| `results/<config>.time` | Start/end timestamps (epoch) |
| `results/env.txt` | Power mode at test time |
| `results/predictions.jpg` | Detection result of the last frame (last run, v7-tiny 320x192) |
| `results/bad.list` | List of label font images (`data/labels/*.png`) that darknet couldn't find — doesn't affect results |
| `results_failed_demo/` | Log of the first attempt with `detector demo`, which failed because there is no OpenCV |
