# Live pipeline built stage by stage: Tapo C200C stream1 → YOLOv8n person on Jetson Nano, 5W (2026-10-15)

`deepstream-app` with the Tapo camera gave only 19–26 fps (camera sends ~29). This test rebuilds the same pipeline one stage at a time with `gst-launch-1.0` to find where fps drops.

## Conclusion
- **No stage drops fps**: S1 (decode only) to S8 (inference + tracker + OSD + NVENC + RTP/UDP out) all run at **29.0–29.4 fps**, 0 dropped, 0 camera drops — the camera rate
- **No CPU core is pegged**: per-core mean ≤ 50%; 100% only in single 1 s samples (≤ 4 of ~90 per stage)
- GPU (GR3D) mean 55–62% with inference every frame, 29% with `interval=1`
- The same pipeline in `deepstream-app` (V0, R1) runs at 22–26 fps with many more DPB warnings, so the loss is in `deepstream-app` itself (its source bin / sink bins / RTSP server), not in the elements
- **Decision: do not use `deepstream-app` in production.** The production app builds its own pipeline (Python + pyds, `perception/app/`)

## Test environment
| Item | Value |
|---|---|
| Board | Jetson Nano 4GB, JetPack 4.6.1, DeepStream 6.0.1, **5W** (`nvpmodel` unchanged, no `jetson_clocks`) |
| Camera | Tapo C200C stream1 1920×1080 @30 fps (set in the app), RTSP over TCP, Wi-Fi 2.4 GHz |
| Light | evening/dark (stages 19:04–19:24; deepstream-app runs 18:29–18:52). Camera alone at 18:56: 28.98 fps (`cam_probe.sh fps 1 tcp 60`), daytime 29.25 |
| Model | YOLOv8n COCO 416×256 FP16 engine, `config_infer_cam_person.txt` (person only, threshold 0.35) |
| Tracker | `config_tracker_IOU.yml`, 640×384 |
| Script | `perception/test/stage_probe.sh` (credentials as rtspsrc properties; logs show `rtsp://***@…`, `secret check: clean`) |

## Method
- Each stage: 90 s, `gst-launch-1.0 -e -v`, ends in `fpsdisplaysink video-sink=fakesink sync=false text-overlay=false`; 20 s cooldown between stages
- fps = fpsdisplaysink `current` (2 samples/s, first 2 s dropped); tegrastats as root every 1 s (per online core, GR3D%, RAM); means include the ~8 s engine load in S4–S8
- DPB = count of `reference in DPB was never decoded`; camera drops = `Could not read/receive` errors (gst-launch does not reconnect)
- No `queue` elements between stages (plain gst-launch chain); S8 uses a `tee` because fpsdisplaysink cannot wrap a configured udpsink from gst-launch

| Stage | Pipeline |
|---|---|
| S1 | rtspsrc (tcp, latency 200, drop-on-latency=true) → rtph264depay → h264parse → nvv4l2decoder |
| S2 | S1 with drop-on-latency=false, latency 500 |
| S3 | S1 + nvstreammux 1280×720 live-source=1 |
| S4 | S3 + nvinfer interval=0 |
| S5 | S4 + nvtracker IOU |
| S6 | S5 + nvvideoconvert (RGBA) → nvdsosd → nvvideoconvert (I420) → nvv4l2h264enc (4 Mbit/s, iframeinterval 30) |
| S7 | S6 with nvinfer interval=1 |
| S8 | S6 → tee → [queue → rtph264pay → udpsink 127.0.0.1:5400 sync=false async=false] + [queue → fps sink] |

## Results
| Stage | fps mean / min / max | fps samples < 25 | rendered / dropped | cpu0 mean / max (s ≥ 99%) | cpu1 mean / max (s ≥ 99%) | GR3D% mean / max | RAM max | DPB warnings | Camera drops | rc |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | 28.97 / 23.34 / 32.70 | 2 / 168 | 2586 / 0 | 29.7 / 46 (0) | 12.5 / 29 (0) | 0.0 / 0 | 1036 MB | 0 | 0 | 124 |
| S2 | 29.31 / 23.06 / 35.26 | 1 / 167 | 2618 / 0 | 30.2 / 38 (0) | 13.1 / 38 (0) | 0.0 / 0 | 1034 MB | 0 | 0 | 124 |
| S3 | 29.16 / 23.98 / 32.84 | 2 / 167 | 2601 / 0 | 30.8 / 54 (0) | 14.9 / 32 (0) | 0.0 / 0 | 1045 MB | 0 | 0 | 124 |
| S4 | 29.29 / 23.04 / 33.83 | 2 / 150 | 2354 / 0 | 38.3 / 76 (0) | 45.5 / 98 (0) | 59.5 / 99 | 1746 MB | 0 | 0 | 124 |
| S5 | 29.19 / 24.00 / 32.50 | 2 / 147 | 2291 / 0 | 46.1 / 100 (2) | 37.3 / 91 (0) | 55.8 / 99 | 1765 MB | 1 | 0 | 124 |
| S6 | 29.07 / 21.23 / 35.07 | 4 / 147 | 2279 / 0 | 43.5 / 69 (0) | 46.1 / 99 (1) | 61.5 / 99 | 1812 MB | 1 | 0 | 124 |
| S7 | 29.19 / 23.19 / 32.34 | 3 / 146 | 2299 / 0 | 41.4 / 100 (4) | 29.6 / 98 (0) | 28.7 / 99 | 1820 MB | 1 | 0 | 124 |
| S8 | 29.37 / 23.10 / 34.00 | 2 / 146 | 2301 / 0 | 50.2 / 98 (0) | 44.5 / 99 (1) | 55.3 / 99 | 1826 MB | 1 | 0 | 124 |

### For comparison: the same pipeline in `deepstream-app` (`run_cam_test.sh`, template `ds_cam_template.txt`)
fps here = `**PERF` every 5 s (first sample dropped), not fpsdisplaysink.

| Run | Setup | fps mean / min / max | PERF samples < 25 | cpu0 mean / max (s ≥ 99%) | cpu1 mean / max (s ≥ 99%) | GR3D% mean / max | RAM max | DPB warnings | Camera drops / reconnects |
|---|---|---|---|---|---|---|---|---|---|
| R1 (18:29, 120 s) | interval 0, IOU, RTSP out + mp4 file | 22.19 / 3.22 / 31.53 | 12 / 22 | 46.2 / 100 (2) | 38.7 / 90 (0) | 49.4 / 99 | 1822 MB | 16 | 0 |
| V0 (18:42, 600 s) | interval 0, IOU, RTSP out, `rtsp-reconnect-interval-sec=5` | 26.29 / 10.58 / 33.49 | 34 / 118 | 48.9 / 98 (0) | 45.5 / 98 (0) | 58.7 / 99 | 1807 MB | 32 | 1 (18:42:59, back in ~2 s) |

- The earlier V0 (18:33, no reconnect key) lost the camera after 49 s and `deepstream-app` exited
- V0 seen in VLC (`rtsp://<JETSON_LAN_IP>:8555/ds-test`): **people are detected well; when 2–3 people cross, IDs swap or a new number is given (IOU tracker)**
- R1–R4 with `deepstream-app` were dropped after this result (production will not use `deepstream-app`)

## Files
- Logs: Jetson `~/safety/perception/test/results/cam/stages/S1…S8.{log,tegra,summary}`, deepstream-app runs in `~/safety/perception/test/results/cam/{R1_i0_iou,V0_view,V0_view2}.*`
- R1 recording: Jetson `~/safety/perception/test/results/cam/R1_i0_iou.mp4` (stays on the Jetson; not committed, not copied off the machine)
