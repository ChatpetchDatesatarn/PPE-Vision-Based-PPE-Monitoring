# Live video fix — WebRTC ภาพสดลื่น ไม่ค้าง ไม่หลุด (2026-10-24)

อ้างอิง: `docs/test-results/2026-10-22_soak24h_v2/webrtc_diagnosis.md`
สาเหตุ: MediaMTX v1.9.3 `internal/protocols/webrtc/from_stream.go` ปิด session เมื่อ `PTS < lastPTS` ("B-frames"); รอง: IDR ห่าง

## การเข้าถึง
- `ssh jetson` (LAN <JETSON_LAN_IP>) จาก PC **timeout** (01:00) — ใช้ `ssh jetson-remote` (Tailscale <JETSON_TAILSCALE_IP>) แทน; ไม่แก้ network
- Tailscale ssh timeout ครั้งเดียวชั่วคราว (retry แล้วต่อได้)
- tmux `cira-gui` (= "cira" ในกฎ) ไม่แตะ; ใช้ tmux `ds` ตามปกติ

## สถานะตอนเริ่ม (01:00)
- session ก่อนหน้า (00:45) แก้ไว้แล้ว + sync PC↔Jetson (md5 ตรง) แต่ **ไม่มี baseline**:
  | ไฟล์ | เดิม (.bak-20261024-004539) | แก้แล้ว |
  |---|---|---|
  | `perception/app/person_count_app.py` | `705044d5da3ba1ce3406bd7a1d0023d5` | `6ad0a673612594239a120107836c5d24` |
  | `dashboard/mediamtx/mediamtx.yml` | `8e2ffc5bd3c2cc8cd0a65b37bc5f2f1b` | `37cb911346088a73fd369b4e2977f0d1` |
- การแก้ที่อยู่ใน "แก้แล้ว":
  - 2.1 pad probe บน `rtph264pay` sink: `pts <= last_pts` → `pts = last_pts + 1 ms`, dts ตาม (ถ้า dts > pts หรือ NONE)
  - 2.2 `nvv4l2h264enc idrinterval=30` (iframeinterval=30 เดิม)
  - 2.3 bitrate 4000000 → 2000000
  - 2.4 `parse2` เอา `config_interval=-1` ออก เหลือที่ `rtph264pay config_interval=-1` ที่เดียว (insert-vui=1 เก็บไว้ — **ไม่ใช่ตัวแก้**, MediaMTX ไม่อ่าน VUI)
  - 2.5 `webrtcIPsFromInterfaces: no` (เหลือ `webrtcAdditionalHosts: [<JETSON_LAN_IP>, <JETSON_TAILSCALE_IP>]`)
- app ไม่ได้รัน; mediamtx restart ~00:50 (โดย session ก่อน)

## เครื่องมือ (ใหม่, ใช้ต่อใน soak v3)
- `tools/live_monitor/live_monitor.js` + `whep_monitor.html` — Chrome headless + WHEP ผ่าน nginx เหมือน Dashboard (grace 5 วิ, retry 5 วิ), Node stdlib ไม่ต้องติดตั้งอะไร
  `node tools/live_monitor/live_monitor.js --csv <out.csv> --minutes 30`
- `tools/live_monitor/pts_check.py` — นับ PTS ถอยหลังจาก ffprobe packet dump

## 1. Baseline — โค้ดเดิม (.bak-20261024-004539), กล้องสด, events off, เปิดไฟ (01:05–01:12)

คำสั่ง (Jetson):
```
TS=20261024-010507; cp -p $A $A.bak-$TS; cp -p $M $M.bak-$TS        # backup ตัวแก้แล้ว
cp -p $A.bak-20261024-004539 $A; cp -p $M.bak-20261024-004539 $M      # ใส่ตัวเดิม
docker restart mediamtx; ~/ds-stop; ~/ds-start baseline_20261024-010507
```
- md5 หลังสลับ: app `705044d5…` / yml `8e2ffc5b…` (= เดิม) ; backup ตัวแก้แล้ว `.bak-20261024-010507` = `6ad0a673…` / `37cb9113…`
- พบว่า app **รันอยู่แล้ว** ตั้งแต่ 00:48 (`live_20261024_0048`, โค้ดแก้แล้ว, fps_mean 28.49) → `ds-stop` ก่อน แล้วค่อย start baseline
- `ssh` หลุด (connection reset) ตอน `docker restart mediamtx` — ต่อใหม่ได้

| รายการ | ค่า baseline |
|---|---|
| ffprobe 120 วิ `rtsp://127.0.0.1:8555/cam01` | 3364 pkt, 27.5 fps, **PTS ถอยหลัง 0** (ไม่นับ 1 jump ที่ packet แรกก่อน RTCP sync) |
| ffprobe keyframe flag (K) | ทุก ~1.04 วิ (= I-frame ทุก 30; ไม่ใช่ IDR) |
| `nvv4l2h264enc` | bitrate 4000000, iframeinterval 30, **idrinterval ไม่ตั้ง = default 256 (~9 วิที่ 28 fps)**, profile Baseline(0), control-rate CBR |
| mediamtx log 8 นาที | **"B-frames" = 0**; session ปิด 6: `peer connection closed` ×3, `terminated` ×2, `deadline exceeded while waiting connection` ×1 |
| live_monitor 5 นาที (`live_monitor_baseline.csv`) | reconnects **6**, TTFF 1.58 / **52.7** / 7.27 วิ, freezeCount **59** (75.8 วิ), keyFramesDecoded 11 ใน ~5 นาที (~1/27 วิ), **packetsLost 5126**, WHEP POST "Failed to fetch" ×4 |
| fps_in (app log) | 26.4–30.8 (~28) |
| CPU เฉลี่ย (tegrastats, รวม ffprobe 2 นาที) | 42.9% |

ข้อสังเกต baseline:
- รอบนี้ **PTS ไม่ถอยหลัง + ไม่มี B-frames** → ปัญหาหลักของ soak v2 ไม่เกิดใน 5 นาทีนี้ (เกิดเป็นช่วงๆ; soak v2 เห็น 46 ครั้ง/30 นาที)
- session หลุดรอบนี้มาจาก **เส้นทาง PC↔Jetson**: packetsLost หลักพัน, WHEP HTTP fail, ssh timeout/reset — PC อยู่นอก LAN (LAN timeout) ต่อผ่าน Tailscale direct ทาง internet
- `keyFramesDecoded` ~1/27 วิ ยืนยัน IDR ห่าง (idrinterval 256)

## ⚠ หยุดชั่วคราว 01:15 — พบอีก session ทำงานซ้อน

- คืนตัวแก้แล้วบน Jetson: `ds-stop` (baseline) → `cp .bak-20261024-010507` → md5 app `6ad0a673…` / yml `37cb9113…` ✔ (mediamtx ยังไม่ restart, app ยังไม่ start)
- แต่ PC `perception/app/person_count_app.py` = **`f331fc90d4e7ee1886655ef0ad74988e`** (แก้เวลา 01:06:34 โดยไม่ใช่ session นี้): เพิ่ม `--mem-debug` / `_mem_debug_loop` (fixes_v3 §2)
- Claude Code peer `pc-session` (busy, เริ่ม 10/16) ยังทำงาน + `live_sink.js` ของ scratchpad `fb4e3814…` รันตั้งแต่ 00:54 → น่าจะมี WHEP viewer อีกตัวตอน baseline (อาจเพิ่ม packetsLost)
- app `live_20261024_0048` ที่ session นี้ ds-stop ตอน 01:05 อาจเป็นรันของ session นั้น
- ไม่ sync PC→Jetson, ไม่ทดสอบต่อ จนกว่าผู้ใช้ตัดสิน

