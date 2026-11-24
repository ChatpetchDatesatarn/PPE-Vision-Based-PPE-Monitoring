# Soak test รอบแรก — 2026-10-22

ระบบ: DeepStream (`person_count_app.py`, `--events on`, zone-mode overlap) + CiRA CORE (decision) +
Dashboard v3 stack (mosquitto / recorder / mediamtx / nginx) บน Jetson Nano 4GB, กล้อง Tapo C200C สดผ่าน RTSP.

## สรุปสั้น
รันได้จริง **10 ชม. 17 นาที** (เป้า 24 ชม.) แล้วหยุดเพื่อแก้บั๊กวิดีโอสด (MediaMTX ตรวจ B-frame ผิด).
ช่วงที่รัน: เสถียร ไม่มีคอมโพเนนต์ล่ม, CiRA heartbeat ไม่ขาดเลย (0 gap > 15 วิ), event ไป CiRA 100% (fallback 0 ครั้ง),
pipeline รีสตาร์ทเอง 3 ครั้งจากกล้องส่งภาพขาด (กู้คืนอัตโนมัติ), อุณหภูมิและ RAM อยู่ในเกณฑ์.

## เวลาจริงที่ทดสอบได้
| จุด | เวลา | ที่มา |
|---|---|---|
| app เริ่ม (`live_20261022_0059`, events on) | 2026-10-22 **00:59:57** | app log บรรทัดแรก |
| app ถูกหยุด (SIGINT, เพื่อแก้วิดีโอ) | 2026-10-22 **11:17:21** | app log `stop: SIGINT` + summary |
| soak_logger sample สุดท้าย | 2026-10-22 11:16:16 | soak.csv แถวสุดท้าย |
| **ระยะเวลาจริง** | **10 ชม. 17 นาที 24 วิ** (≈ 42.8% ของเป้า 24 ชม.) | |

soak_logger / soak_watch หยุดด้วยการปิด tmux session `soak` (ไม่ได้ปล่อยให้ logger สั่ง `ds-stop; ds-start` เองตอนครบ 24 ชม.).
ไม่มีการลบไฟล์ใด ๆ ของรอบ soak.

## Checklist 12 ข้อ (เฉพาะช่วง 00:59:57–11:17:21)

| # | รายการ | ผลวัด | เกณฑ์ | ผล |
|---|---|---|---|---|
| 1 | Uptime | process เดียวต่อเนื่อง 10h17m, pipeline รีสตาร์ทเอง 3 ครั้ง (ไม่ตาย, ไม่ต้องแตะมือ) | ไม่ crash / ไม่ค้าง | **PASS** |
| 2 | fps (app, per-5s) | mean **22.41**, min **8.0**, max 31.62 (7398 ตัวอย่าง); ช่วงนิ่ง ~28–30 | ~28–29 ตอนนิ่ง | **PASS\*** |
| 2b | fps กลางวัน/กลางคืน (status, per-5min) | คืน 01–06 น. mean 20.6 · วัน 06–11 น. mean 23.5 | — | — |
| 3 | RSS app เริ่ม→จบ | 1527.5 → 1613.5 MB = **+86 MB ใน 10.27 ชม. = 8.4 MB/ชม.** | ไม่โตพุ่ง / ไม่ OOM | **PASS (เฝ้าดู)** |
| 4 | RAM / swap | RAM used 2095→สูงสุด 2200 MB (จาก 3964), swap 20→70 MB | RAM เหลือ, swap ต่ำ | **PASS** |
| 5 | อุณหภูมิสูงสุด | CPU **63.5 °C**, GPU **61.5 °C** | < ~90 °C (ไม่ throttle) | **PASS** |
| 6 | กล้องหลุด | pipeline รีสตาร์ท 3 ครั้ง (no frame >3 วิ): 04:13:59, 06:36:10, 07:45:02 — กู้เอง; cam_connected ไม่เคย False ในตัวอย่าง 5 นาที | กู้คืนได้เอง | **PASS** |
| 7 | CiRA heartbeat | 3693 ข้อความ ทุก ~10 วิ, inter-hb สูงสุด **11 วิ**, **gap > 15 วิ = 0**, hb_age ที่ sample ≤ 3 วิ | ไม่ขาด > 15 วิ | **PASS** |
| 8 | event แยก type / via | รวม **1505**: no_vest 782, no_helmet 723 — **via cira 1505 / fallback 0** | fallback = 0 ตอน CiRA ปกติ | **PASS** |
| 9 | CiRA received/published/filtered | received 1563→7674 (+6111), published 413→1919 (+1506), filtered 1150→5755 (+4605); 6111 = 1506+4605 สมดุล | สมดุล | **PASS** |
| 10 | snapshot + disk | app เข้ารหัส **7187** รูป (skip 0, ~45 KB/รูป), recorder เก็บจริง ~2063 รูป (cap 3000 ยังไม่ถึง, cleanup ทำงาน), disk_free คงที่ **8 GB** ตลอด | ไม่เต็ม disk, cleanup ทำงาน | **PASS** |
| 11 | event_id ซ้ำ / fallback | event_ids_dup **0**, fallback_events **0**, mode_switches = [["01:00:07", cira]] (ไม่เคยสลับ fallback) | 0 | **PASS** |
| 12 | fps ตกต่ำสุด | ต่ำสุด per-5min 13.4 (03:51), และ dip 14.8 ที่ 10:40 | — | ดูหัวข้อถัดไป |

\* fps mean 22.4 ต่ำกว่าค่านิ่ง (~28–30) เพราะโดน dip ช่วงกล้องส่งภาพขาด/ช้า ดึงลง; ตอนภาพปกติได้ ~28–30 สม่ำเสมอ.

### สาเหตุ fps dip (รวม 14.8 ตอน 10:40)
ที่แถว 10:40:04: fps 14.8 **พร้อม CPU core0/1 ตกเหลือ 52/41%** (ปกติ ~90%). CPU ลดตาม fps = **ภาพเข้าน้อย (input starvation)**
ไม่ใช่ CPU ตัน. กล้อง Tapo ผ่าน Wi-Fi 2.4 GHz ส่งเฟรมช้า/สะดุดเป็นช่วง → DeepStream รอเฟรม → fps ลง, CPU ว่าง.
ถ้าขาดเกิน ~3 วิ app จะรีสตาร์ท pipeline (เกิด 3 ครั้ง); ครั้งเบา (เช่น 10:40) แค่ fps ตกแล้วกลับมาเอง. ไม่ใช่ปัญหาการประมวลผลบนบอร์ด.

## ข้อค้นพบ: ภาพสดหลุด ("เชื่อมต่อวิดีโอไม่ได้ จะลองใหม่ใน 5 วินาที")

**อาการ:** Dashboard ภาพสดติด ๆ ดับ ๆ แต่ไฟสถานะ 3 ดวงเขียวและแจ้งเตือนเข้าปกติ (MQTT คนละทางกับวิดีโอ).

**สาเหตุ (ตรวจแบบอ่านอย่างเดียวระหว่าง soak):** MediaMTX v1.9.3 ปฏิเสธทุก WebRTC session ด้วย
`WebRTC doesn't support H264 streams with B-frames` — **ซึ่งเป็น false positive**. stream จริงเป็น
`Constrained Baseline` (ห้ามมี B โดยนิยาม), `has_b_frames=0`, `refs=1`, 0 B-frame, pts==dts (ไม่มี reorder).
MediaMTX ตัดสินจาก **SPS**: `nvv4l2h264enc` เขียน SPS ไม่มี VUI reorder-info → MediaMTX สมมติ worst-case ว่า
stream อาจ reorder → ปฏิเสธ. เริ่มเกิด 01:02:53 (หลัง app นี้ที่ใช้กล้องสดเริ่ม 00:59); ก่อนหน้าทดสอบด้วยคลิป .mp4 ที่ SPS สะอาด จึงไม่เจอ.
อาการแฝง: `rtph264pay` ตั้ง `config-interval=0` (default) ไม่ re-send SPS/PPS → viewer ที่ต่อกลางสตรีมเจอ `non-existing PPS 0`.

**วิธีแก้** (`perception/app/person_count_app.py`, encoder block):
- `nvv4l2h264enc` เพิ่ม `insert-vui=1` (เขียน VUI ลง SPS → MediaMTX เลิกเดา B-frame).
- แทรก `h264parse config-interval=-1` ระหว่าง encoder กับ `rtph264pay` (re-stamp DTS + ส่ง SPS/PPS ทุก IDR).
- `rtph264pay` เพิ่ม `config-interval=-1` (re-send SPS/PPS ในทุก IDR → แก้ `non-existing PPS 0`).
- คง `profile=0` Baseline เหมือนเดิม.

**ผลหลังแก้ (ทดสอบ 2026-10-22 ~11:20, events off):**
- ffprobe stream ยัง `Constrained Baseline`, `has_b_frames=0`, 0 B-frame (ทั้งคลิปและกล้องสด).
- ผ่าน MediaMTX republish (`rtsp://127.0.0.1:8554/cam01`): **PPS error = 0** (SPS/PPS สะอาด).
- fps กล้องสด fps_in 29.0 / fps_infer 28.8 (ไม่ตกจากเดิม).
- **ค้างยืนยัน:** การดูภาพสดผ่าน Dashboard (WebRTC/WHEP) ต่อเนื่อง 5 นาที ว่าไม่มี "B-frames" ใน `docker logs mediamtx`
  — รอผู้ใช้เปิด Dashboard ทดสอบจริง (ยังไม่สรุปว่า PASS จนกว่าจะยืนยันรอบ 5 นาที). **ห้ามอัปเกรด MediaMTX เอง.**

md5 ของ `person_count_app.py` หลังแก้ = `705044d5da3ba1ce3406bd7a1d0023d5` (ตรงกัน PC/Jetson).

## ข้อจำกัด
- ทดสอบได้ **10 ชม. 17 นาที จากเป้า 24 ชม.** เพราะต้องหยุด app เพื่อแก้บั๊กวิดีโอสด (ต้อง `ds-stop; ds-start` รอบใหม่จึงจะมีผล).
- soak.csv เก็บทุก 5 นาที → dip กล้องที่สั้นกว่า 5 นาทีบางครั้งไม่ถูกบันทึก (เห็นจาก app summary fps_min 8.0 ที่ละเอียดกว่า).
- ยังไม่ได้ทดสอบ 24 ชม.เต็ม และยังไม่ยืนยันภาพสดหลังแก้ครบ 5 นาทีผ่าน Dashboard.

## ไฟล์ในโฟลเดอร์นี้
- `soak.csv` — 121 แถว, sample ทุก 5 นาที (fps, CPU, RAM, temp, RSS, heartbeat age, events, snapshots).
- `cam01_event.log` — event ทั้งหมดที่ CiRA ส่ง (1505) พร้อม epoch.
- `cira_status.log` — CiRA heartbeat 3693 ข้อความ.
- `soak_events_window.csv` — export event จาก recorder เฉพาะช่วง 00:59:57–11:17:21 (1505 แถว).
- ยัง**ไม่ลบ** event/snapshot ของรอบ soak.
