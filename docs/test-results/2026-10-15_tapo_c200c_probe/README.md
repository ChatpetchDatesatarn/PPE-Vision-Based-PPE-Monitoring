# Probe: Tapo C200C RTSP on Jetson Nano (2026-10-15)

Checked the Tapo C200C over RTSP from the Jetson: reachability, stream format, NVDEC decode fps, and what happens when the camera loses power. Used to pick the main stream and the reconnect values for the DeepStream app.

## Test environment
| Item | Value |
|---|---|
| Board | Jetson Nano Developer Kit 4GB, JetPack 4.6.1 (L4T R32.7), 5W mode, micro-USB supply, no `jetson_clocks` |
| GStreamer | 1.14.5, decode with `nvv4l2decoder` (NVDEC) |
| Camera | TP-Link Tapo C200C, Wi-Fi 2.4 GHz, IP <LAN_IP> (DHCP), H.264 + PCMA audio |
| Camera setting | round 1: frame rate as shipped; round 2 and step e: 30 fps set in the Tapo app |
| Script | `perception/test/cam_probe.sh` (credentials sourced from `~/safety/.cam.env`, never logged; every result passed `secret check: clean`) |
| Raw logs | on the Jetson in `~/safety/perception/test/results/cam/` (round 1 copied to `run1_2026-10-15_1635/`) |

## Method
- a) `ping` 20× at 0.5 s
- b) `gst-discoverer-1.0` on stream1 and stream2
- c/d) `rtspsrc latency=200 protocols=<tcp|udp> ! rtph264depay ! h264parse ! nvv4l2decoder ! fpsdisplaysink video-sink=fakesink sync=false`, 60 s, tegrastats every 1 s
- e) same pipeline for 150–180 s while the camera power is unplugged; a 1 s ping + `nc -z` port 554 logger (`e_net.log`) and a video-ready check (`cam_probe.sh videowatch`, buffers counted in 5 s pulls) run beside it
- fps "mean/min/max" = fpsdisplaysink `current` samples, first 2 s dropped

## a) ping
| Item | Value |
|---|---|
| Sent / received | 20 / 20 |
| Packet loss | 0% |
| rtt min / avg / max / mdev | 1.868 / 9.994 / 69.121 / 14.955 ms |

## b) Stream format
| Item | stream1 | stream2 |
|---|---|---|
| Video | H.264 High, level 4 | H.264 High, level 3.1 |
| Resolution | 1920×1080 | 1280×720 |
| Frame rate (SPS, round 1) | 15/1 | 15/1 |
| Audio | PCMA 8000 Hz | PCMA 8000 Hz |

## c/d) Decode fps (60 s each, dropped 0 and ERROR/WARNING 0 in every run)
| Run | Camera fps setting | caps framerate | rendered | average fps | current mean / min / max | CPU% mean / max | NVDEC active | RAM max |
|---|---|---|---|---|---|---|---|---|
| stream1 tcp | shipped | 15/1 | 880 | 14.89 | 14.85 / 1.98 / 30.94 | 17.5 / 29.0 | 59/59 | 1046 MB |
| stream2 tcp | shipped | 15/1 + 30/1 | 899 | 15.19 | 15.15 / 5.88 / 23.91 | 15.7 / 29.5 | 59/59 | 1048 MB |
| stream1 udp | shipped | 30/1 | 1668 | 28.24 | 28.10 / 17.73 / 36.01 | 20.1 / 45.5 | 59/59 | 1055 MB |
| stream2 udp | shipped | 15/1 | 883 | 14.95 | 14.90 / 7.51 / 22.73 | 13.6 / 28.0 | 59/59 | 1053 MB |
| stream2 tcp | 30 fps | 30/1 | 1136 | **19.12** | 19.04 / 3.69 / 37.91 | 16.7 / 28.5 | 59/59 | 1049 MB |
| stream1 tcp | 30 fps | 30/1 | 1730 | **29.25** | 29.23 / 16.24 / 56.04 | 21.4 / 31.0 | 59/59 | 1052 MB |

- With the shipped setting the camera switched between 15 and 30 fps by itself, so the round 1 TCP vs UDP difference is the camera, not the protocol
- With 30 fps set, stream2 still delivers only 17–20 fps while caps say 30/1 → **stream1 is the main stream**, nvstreammux scales it to 1280×720
- NVDEC max 716 MHz, GPU% 0.0 in every run

## e) Camera unplugged
### stream2 tcp, 150 s (16:46:55) — not valid
No gap in the video at all (rendered 2559, average 17.18, ERROR 0): the camera was not unplugged inside the window. Kept only as a stream2 fps sample.

### stream1 tcp, 180 s (16:55:05)
| Item | Result |
|---|---|
| fps before unplug | average 29.38, current mean 29.34 / min 19.99 / max 37.83, dropped 0 |
| Camera power lost (first ping down, last frame) | 16:57:08, rendered 3566 (unplugged at second ~123) |
| ERROR / WARNING in the pipeline | 0 / 0 |
| EOS | **yes**, 16:57:33 = **25 s** after the last frame; gst-launch ended with rc=0 |
| Likely cause of the EOS | rtspsrc `tcp-timeout` default 20000000 µs (20 s) — not confirmed |
| Pipeline hang | no frames and no message for 25 s, then EOS |
| Recovers by itself | **no** — the pipeline is gone; rtspsrc does not reconnect |
| NVDEC active | 120/145 samples (idle while the camera was off) |
| CPU% mean / max, RAM max | 18.6 / 31.5, 1051 MB |
| Port 554 first open | 17:01:53 (ping still down) |
| First video | 17:01:53 – 17:01:58: 67 buffers in 5 s |
| Drop again during boot | port 554 closed 17:02:02 – 17:02:14, ping down 17:02:06 – 17:02:14 |
| Stable | from 17:02:15 (port open on every later sample), 132 buffers in 5 s at 17:03:05 |
| Boot, first sign to stable | 22 s (17:01:53 → 17:02:15) |
| Boot, power-on to video | not measured (plug-in time not recorded; not needed) |
| Failed connect attempt while the camera is off | ~2 s each |

## Values chosen for the DeepStream app
| Setting | Value | Reason |
|---|---|---|
| Stream | `stream1` (1920×1080 @30), nvstreammux 1280×720 | stream2 gives only 17–20 fps |
| `protocols` | `tcp` | dropped 0 and ERROR 0 in every TCP run |
| `latency` | `200` ms | dropped 0 in every run; lower values not tested yet |
| `drop-on-latency` | `true` | keep latency bounded instead of queueing old frames |
| Audio | `select-stream` returns `TRUE` only for `media=video` (fallback: link only the video pad in `pad-added`) | camera always sends PCMA; `select-stream` exists in GStreamer 1.14.5 |
| Camera lost | no frame for **3 s** (watchdog in a probe) | normal runs never had a 1 s gap; waiting for EOS took 25 s |
| `tcp-timeout` | `5000000` (5 s), backup to the watchdog | the 20 s default gave EOS after 25 s |
| Bus messages | handle **EOS and ERROR** | camera loss arrived as EOS, not ERROR |
| Reconnect | rebuild the source every **2 s** for the first 60 s, then every **5 s**, max **10 s**, no limit on attempts | a failed attempt costs ~2 s; a long backoff would add up to 30 s after the camera is back |
| Backoff reset / `camera_connected=true` | only after **10 s** of continuous frames | the camera came up and dropped again within 9 s while booting |
| `camera_connected=false` | when the 3 s watchdog fires | same rule as "camera lost" |
