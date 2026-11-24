# WebRTC Live Video Diagnosis — Soak v2 (2026-10-23)

- อ่านอย่างเดียว ไม่แตะ soak/app/container; ดู Dashboard ผ่าน Tailscale `<JETSON_TAILSCALE_IP>:8080`
- อาการ: ภาพสดวน **"ได้ภาพ 1 เฟรม → ค้าง ~7 วิ → หลุด → ต่อใหม่"**

## 1. หลักฐาน (read-only)

- `docker logs mediamtx --since 30m` (timestamp เป็น **UTC**; 10:44 UTC = 17:44 local): session WebRTC ปิดด้วยเหตุ
  - **46 × `closed: WebRTC doesn't support H264 streams with B-frames`** ใน 30 นาที
  - 5 × `terminated` (client ปิดก่อน), 3 × `read tcp ... connection reset` (RTSP ย่อย)
- `mediamtx.csv` (soak v2): `bframes_lines_total` 0 → 60, `webrtc_sessions_opened` 34→85 ใน ~40 นาที (17:00–17:47) = ช่วงเปิด Dashboard วน reconnect; กลางคืนไม่มีคนดู ≈ 0
- ลำดับต่อ session (จาก log): `created` → `peer connection established` → `is reading from path 'cam01'` → ~2–4 วิ → `closed: ...B-frames`
- Dashboard `web/js/webrtc.js`: `ontrack` แสดงเฟรมแรก; เมื่อ server ปิด session → `connectionState` = disconnected → `DISCONNECT_GRACE_MS = 5000` → `_fail()` → retry หลัง `CONFIG.WEBRTC_RETRY_S`
  - **2–4 วิ (session มีชีวิต) + 5 วิ (grace) ≈ 7 วิ = ตรงอาการ**
- Dashboard JS ไม่ใช่บั๊ก: grace + retry สมเหตุผล; พอ stream หายปัญหา player เล่นต่อได้เอง

## 2. สาเหตุที่แท้จริง (แก้จากการตรวจซอร์ส)

ตรวจซอร์ส **MediaMTX v1.9.3** `internal/protocols/webrtc/from_stream.go`: error `"WebRTC doesn't support H264 streams with B-frames"` ถูกยิงเมื่อ **`tunit.PTS < lastPTS`** (PTS ของ access unit ถอยหลังเทียบอันก่อน) **เท่านั้น** — โค้ด **ไม่ได้ดู SPS / VUI / profile / num_reorder_frames เลย**

⇒ **สาเหตุ = PTS จากกล้องสดถอยหลังเป็นระยะ** MediaMTX ตีความ PTS ที่ลดลงว่าเป็น B-frame reordering แล้วปิด session

### ผลต่อข้อสรุป/ข้อเสนอเดิม (ยกเลิก)
- `insert-vui=1`, บังคับ `profile=constrained-baseline`, เขียน VUI `max_num_reorder_frames=0` — **ไม่ใช่ทางแก้** เพราะ MediaMTX ไม่อ่าน SPS/VUI ในจุดนี้
- `ffprobe` ดู VUI reorder — **ไม่เกี่ยว** ไม่ต้องทำ
- การ verify ครั้งก่อน (republish จาก mp4 ได้ "0 B, Constrained Baseline") **ใช้ไม่ได้เป็นหลักฐาน** เพราะ **clip ไม่เจอปัญหา** (PTS ใน mp4 เรียงจาก container) ส่วน **live มี PTS ถอยหลัง**
- **"0 B-frames ใน 10 ชม." ก่อน soak ไม่ใช่หลักฐานว่าแก้ได้** — ช่วงนั้น **ไม่มีคนเปิด Dashboard** จึงไม่มี session WebRTC ให้ยิง error (error เกิดเฉพาะเมื่อมี consumer WebRTC)

## 3. สาเหตุรอง — ICE (ทำให้ช้า ไม่ใช่ตัวฆ่าหลัก)

- `mediamtx.yml`: `webrtcAdditionalHosts: [<JETSON_LAN_IP>, <JETSON_TAILSCALE_IP>]` ถูก แต่ MediaMTX auto-gather interface เพิ่ม `172.18.0.1`, `172.17.0.1` (docker bridge) — remote browser (Tailscale `100.95.x`) ไปไม่ถึง
- ที่ยังต่อติดเพราะ candidate `<JETSON_TAILSCALE_IP>` ใช้ได้ (log เห็น "peer connection established, local candidate: host/udp/<JETSON_TAILSCALE_IP>/8189"); ICE **สำเร็จ** media ไหลชั่วครู่ แล้วถึงโดน PTS/B-frame ปิด
- ⇒ ICE ไม่ใช่ blocker หลัก แค่เพิ่มดีเลย์/candidate ขยะตอนตั้งต้น

## 4. แผนหลัง soak (ห้ามลงมือจนกว่า soak จบ)

1. **วัด PTS 2 นาทีจาก `rtsp://127.0.0.1:8555/cam01`** นับจำนวนครั้งที่ PTS ถอยหลัง (`PTS < lastPTS`) — ทำ **2 รอบ: ตอนเปิดไฟ (fps ~28) และปิดไฟ (fps ~15)** เพื่อดูว่าความถี่การถอยหลังขึ้นกับ fps/exposure ไหม (เช่น `ffprobe -show_entries frame=pts_time` แล้ว diff; ต้องดึง stream จึงทำตอน soak ไม่ได้)
2. **เสนอวิธีบังคับ PTS ให้เดินหน้าเสมอ** ก่อน encoder/pay:
   - pad probe บน buffer: ถ้า `PTS <= last_pts` ให้ตั้ง `PTS = last_pts + 1` (หรือ frame duration)
   - หรือ retimestamp ด้วย running-time ของ pipeline (เช่น ตั้งใหม่จาก clock ไม่ใช่ PTS ต้นทางจากกล้อง)
   - ใส่ก่อน `nvv4l2h264enc` หรืออย่างน้อยก่อน `rtph264pay`
3. **ตัด config-interval ซ้ำ** ให้เหลือที่เดียว (ตอนนี้ตั้งทั้ง `h264parse parse2 config_interval=-1` และ `rtph264pay pay config_interval=-1`) — เลือกที่เดียวพอ ลดความซ้ำซ้อน
4. **`webrtcIPsFromInterfaces: no`** ใน mediamtx.yml — หยุด auto-gather 172.x/192.168 ให้ใช้เฉพาะ `webrtcAdditionalHosts` (ลด ICE churn)
5. **ทดสอบ: เปิด Dashboard จริง 10 นาที** ผ่าน Tailscale — เกณฑ์ผ่าน = **`docker logs mediamtx` ไม่มี `B-frames` เลย** และภาพไม่หลุด

## 5. หมายเหตุ

- การเปลี่ยนข้อ 2/3/4 ต้องแก้ `person_count_app.py` + `mediamtx.yml` แล้ว restart app/container → **ทำได้เฉพาะหลัง soak จบ** (มี soak_done.txt + logger หยุด)
- ห้ามอัปเกรด MediaMTX เองโดยไม่ขออนุญาต

## 6. หลักฐานเพิ่ม: webrtc-internals dump (20:50, Edge)

- ต่อตรงผ่าน Tailscale `<JETSON_TAILSCALE_IP>` (ไม่ผ่าน relay), RTT 26–39 ms
- `packetsLost 0`, `nackCount 0`, `framesDropped 0`, ถอดรหัสฮาร์ดแวร์ D3D11 → **เครือข่าย/เบราว์เซอร์ปกติ**
- `freezeCount 2` (1.58 + 1.30 วิ) ช่วงที่ fps เหลือ 6 และ 1 **โดยไม่มีแพ็กเก็ตหาย** → **ต้นทางหยุดส่ง** (ตรงกับ PTS ถอยหลังทำ MediaMTX หยุด)
- `keyFramesDecoded = 1` ในราว 10 วิ → **IDR ห่างกว่า `iframeinterval=30`** (ที่ 15 fps IDR ทุก ~2 วิ แต่เห็นห่างกว่านั้น) → ต่อใหม่ต้องรอ IDR นาน = จอดำ
- bitrate ~4.5 Mbps ที่ 1280×720
- ICE candidate มี `172.17.0.1` / `172.18.0.1` (docker) ที่ต่อไม่ได้ (ยืนยันข้อ 3)

## 7. หลักฐานเพิ่ม: คลิปหน้าจอ 20:48–20:49

- 20:48:46 connected → ภาพขึ้น OSD 20:48:54 → **ค้างที่ 20:48:54 นาน ~12 วิ** (ยัง connected)
- ~20:49:02 connected → disconnected → 20:49:08 "เชื่อมต่อวิดีโอไม่ได้"
- 20:49:12 ต่อใหม่ connected แต่ **จอดำ >8 วิ** ทั้งที่มีคนเดินเข้า (แจ้งเตือนขึ้น 20:49:14) → ยืนยัน IDR ห่าง

## 8. สรุปปัญหา (รวมหลักฐานทั้งหมด)

- **หลัก:** MediaMTX หยุดส่งเมื่อ PTS ถอยหลัง (`tunit.PTS < lastPTS`) → ภาพค้าง → หลุด
- **รอง:** IDR ห่าง → ต่อใหม่แล้วจอดำนาน (keyFramesDecoded=1/10s)
- **ไม่ใช่:** เครือข่าย (loss 0, RTT ต่ำ), เบราว์เซอร์ (HW decode ปกติ), B-frame จริง, SPS/VUI, Jetson ประมวลผลไม่ทัน (fps_infer=fps_in), โค้ด Dashboard

## 9. แผนแก้ (หลัง soak v2 + รายงานเสร็จ → ใช้ใน soak v3)

| # | การแก้ | ไฟล์ |
|---|---|---|
| A1 | บังคับ PTS เดินหน้าเสมอ (pad probe / retimestamp running-time) ก่อน encoder/pay | `person_count_app.py` |
| A2 | `idrinterval=30` (IDR ถี่สม่ำเสมอ ลดจอดำตอนต่อใหม่) | `person_count_app.py` |
| A3 | ลด bitrate ~2 Mbps | `person_count_app.py` |
| A4 | `webrtcIPsFromInterfaces: no` + ตัด config-interval ซ้ำให้เหลือที่เดียว | `mediamtx.yml` / `person_count_app.py` |

**เกณฑ์ผ่าน (soak v3):**
- PTS ถอยหลัง **0 ครั้ง** ใน 2 นาที
- เปิด Dashboard **เห็นภาพภายใน 2 วิ**
- OSD เดินต่อเนื่อง **10 นาที**
- `freezeCount` ~0
- `docker logs mediamtx` **ไม่มี "B-frames"**

## Errata (2026-10-25, จาก fixes v4)

- **ข้อ 3 (ICE) — ชี้เหตุผลให้ชัดและแก้แล้ว:** candidate LAN `<JETSON_LAN_IP>` ก็เป็นตัวทำ ICE flap/reconnect ไม่ใช่แค่ docker-bridge 172.x. PC ที่ดู Dashboard อยู่คนละสถานที่กับ Jetson และเข้าผ่าน Tailscale เท่านั้น; Wi-Fi ของ PC (Thongma/Thongma2) บังเอิญเป็นวง `192.168.1.x` เหมือนบ้าน Jetson → เบราว์เซอร์เห็น candidate `<JETSON_LAN_IP>` แล้วลองต่อในวง LAN ของตัวเองที่ไม่มีเครื่องนี้ → ล้ม/สลับไปมา. **ไม่ใช่ AP/client isolation ที่เราเตอร์.**
- **แก้ (2026-10-25):** ตัด `<JETSON_LAN_IP>` ออกจาก `webrtcAdditionalHosts` เหลือ `[<JETSON_TAILSCALE_IP>]` (ตั้งค่าถูกต้องถาวรสำหรับดูผ่าน Tailscale). ติดตั้งในโรงงานที่ดูผ่าน LAN ให้ใส่ IP LAN กลับ. ตรวจด้วย WHEP probe: candidate เหลือ `<JETSON_TAILSCALE_IP>` อย่างเดียว, connected, 100 เฟรม/6 วิ. รายละเอียด `docs/test-results/2026-10-25_fixes_v4/fixes_v4.md` ข้อ 2.
