# Soak v3 — 24 ชม. (2026-10-24)

เริ่มจาก runbook `docs/test-results/2026-10-24_fixes_v3/fixes_v3.md §6`. โฟลเดอร์นี้ = ผลจริง.

> **Errata (2026-10-26):** (ก) `rss_cira_mb` มีข้อมูลจริง 1096/1440 แถว (254→195 MB, ลดลง = ไม่รั่ว) — `09_summary.csv` ที่เขียน "NO DATA" ผิด (แก้แล้ว). (ข) RSS slope คิดใหม่ด้วย regression ทุกรอบเป็นค่าหลัก: v1 8.82 / v2 4.31 / v3 6.68 MB/ชม. (ต้น-ปลาย 8.37/3.92/5.08). ดูรายละเอียดในตาราง Errata ของ `soak_v3_report.docx`.
>
> **Errata (2026-10-25):** WebRTC session churn / reconnect ใน soak นี้ (`mediamtx_soak.log` local candidate `<JETSON_LAN_IP>`) เกิดจาก ICE โฆษณา LAN IP `<JETSON_LAN_IP>` ที่เบราว์เซอร์ฝั่ง PC (อยู่คนละสถานที่ ดูผ่าน Tailscale, Wi-Fi บังเอิญวง `192.168.1.x` เดียวกัน) ไปไม่ถึง — **ไม่ใช่ AP/client isolation ที่เราเตอร์**. แก้แล้วใน fixes v4 ข้อ 2 (ตัด `<JETSON_LAN_IP>` ออกจาก `webrtcAdditionalHosts` เหลือ `[<JETSON_TAILSCALE_IP>]`).

## เงื่อนไขการทดสอบ
- เปิดไฟตลอด 24 ชม. (จำลองสายผลิต). เปิด/ปิดไฟจดด้วย `~/light on|off` → `~/light_log.csv`.
- กล้องสด, app `--events on`, nvpmodel **5W**.
- cooldown แบบเดิมเหมือน v2 (เทียบผลได้).
- คนในบ้านเดินผ่านกล้องเป็นระยะช่วงกลางวัน (ใส่/ไม่ใส่ PPE).

## §0 ตรวจก่อนเริ่ม (ผ่านทั้งหมด)
| check | result |
|---|---|
| Dashboard md5 PC=Jetson | webrtc 5f4d7635… / ui 5c27d9dd… / app.css aa65536a… ✓ |
| person_count_app.py | f331fc90d4e7ee1886655ef0ad74988e ✓ |
| mediamtx.yml | 37cb911346088a73fd369b4e2977f0d1 ✓ |
| ICE 172.x (docker logs 5m) | 0 ✓ |
| disk free (Jetson) | 7.1 GB (≥6) ✓ |
| docker | mosquitto / mediamtx / dashboard / recorder — up ✓ |
| CiRA | cira/status online:true, ts สด (≤15s) ✓ |
| collector/live_monitor/soak3 เก่า (Jetson+PC) | none ✓ |
| light_log last | `2026-10-24 14:48:01,1,` = light on ✓ |
| nvpmodel | 5W ✓ |

## การเริ่ม
1. `./ds-stop; ./ds-start --events on` (ไม่มี `--mem-debug`)
2. รอ fps คงที่
3. `SOAK_DIR=~/safety/docs/test-results/2026-10-24_soak24h_v3 SOAK_START=$(date +%s) SOAK_HOURS=24 bash ~/safety/tools/soak3_up.sh soak3`
4. PC: `node tools/live_monitor/live_monitor.js --csv <PCdir>/live.csv --minutes 1440 --interval 30` (background)

## ครบ 24 ชม. (อัตโนมัติ)
- เขียน `soak_done.txt`
- `ds-stop; ds-start` (events off)
- หยุด collector ทุกตัวใน tmux soak3 (ไม่ค้างแบบ v2)

## เริ่มจริง
- app: `live_20261024_1450` (events on), restart 14:50:24 +07
- tmux soak3 สร้าง 14:51:15 +07 → ครบ 24h ~**2026-10-25 14:51 +07**
- PC live_monitor: PID 35004, `live.csv`, logs `live_monitor.{out,err}.log`

### ค่าเริ่มต้น (soak.csv row แรก 14:51:24 + live.csv + board)
| metric | value |
|---|---|
| fps (live WebRTC / infer) | 25.7 / 28.2 |
| CPU total | 71.5% (startup) |
| RAM / swap | 2118 MB / 0 |
| RSS app | 1515 MB |
| temp (cpu / thermal) | 59 / 57.75 °C |
| power | 4164 mW (→ ~4518) |
| disk free | 7.07 GB |
| TTFF live | 0.71 s |
| collector CPU (รวม) | ~0% (วัด /proc 3s; ps lifetime-avg = 3.1% เป็น startup burst) |
| throttled | 0 |

### §3 verify (ภายใน 10 นาที)
- soak.csv: row ทุก 60s, power_mw/freq/throttled/rss_app ครบ ✓ — **rss_cira ว่าง** (sampler ไม่เจอ cira RSS; ไม่อยู่ในรายการ col ที่ต้องมี; ไม่แก้โค้ดระหว่าง soak)
- live.csv: connected, TTFF 0.71s ≤3 ✓
- watch.log: 0 WARNING ✓
- collector CPU ≤2% ✓
- walk-past no-helmet → event via=cira + latency.csv row: **รอผู้ใช้เดินผ่านกล้อง**

### วิธีหยุด (ฉุกเฉิน)
- PC live_monitor: `Stop-Process -Id 35004` (PID ใน `live_monitor.pid`)
- collectors: `ssh jetson "tmux kill-session -t soak3"` (ปกติหยุดเองครบ 24h แล้วเขียน soak_done.txt + ds-start events off)

## วิเคราะห์ fps ตก 28→15 (2026-10-25, อ่านอย่างเดียว)
ผู้ใช้แจ้ง: ไฟในห้องเปิดตลอด, Tapo ตั้ง Night Vision ไว้ (ไม่ auto). fps ตกจาก 28 (00:34) เหลือ ~15 (04:20).

### ไทม์ไลน์ fps_in (soak.csv ทีละนาที)
ปกติ ~28–30 ตลอด มี dip สั้น ๆ กระจาย (noise ~1 นาที). มี **2 ช่วง sustained ล็อกที่ ~15 fps** (= ครึ่งของ 30), **เข้า/ออกฉับพลัน ไม่ค่อย ๆ ลด**:
- **#1: 02:20 → 02:49** (~29 นาที). 02:19=23.2 → 02:20=15.0; 02:49=15.0 → 02:50=28.8
- **#2: 03:54 → 04:20** (~26 นาที). 03:53=29.2 → 03:54=14.8; 04:20=15.0 → 04:21=29.6

### เหตุการณ์พร้อมกัน
- **#1 ตรงกับ camera-side RTSP stream reset:** `docker logs mediamtx` ที่ 2026/10/24 19:20:14 UTC (= 02:20 +07):
  `[path cam01] [RTSP source] 12108 RTP packets lost` ตามด้วย `received packet with wrong SSRC 3715769366, expected 605853154` (ซ้ำ). SSRC เปลี่ยน = กล้องรีสตาร์ท RTP stream ใหม่. app DeepStream restart ตาม (`restarts` 0→1, เห็นที่ 02:49). หลัง reset กล้องส่งมา 15 fps.
- **#2 ไม่มีร่องรอยฝั่ง server:** ไม่มี RTP-loss/SSRC/`ready` ใน mediamtx log ช่วง 20:54–21:20 UTC, และ `restarts` คง 1 (app ไม่ restart). fps ยังตก 15 แล้วกลับเอง.
- `light_log.csv`: ไฟ ON ตั้งแต่ 14:48 ไม่มี toggle.
- **brightness.csv เสียตั้งแต่ 02:29 +07:** yavg/satavg ว่างทุกแถวหลัง 02:19 → soak_slow frame-grab (ffmpeg) ล้มเหลวครึ่งหลังของ soak (คนละปัญหา, ควรดู root cause หลัง soak — อาจกระทบ brightness logging อย่างเดียว ไม่กระทบ detection).

### สี vs IR/ขาวดำ (วัด saturation, crop overlay ih*0.15..ih*0.95)
- **ไม่มี snapshot ช่วง plateau ทั้งสอง** (snaps=0, ไม่มีคนเดินผ่าน) และ brightness satavg ว่าง → **วัดเฟรมตอน plateau โดยตรงไม่ได้**.
- เฟรม event ที่ขนาบ plateau (วัดด้วย OpenCV HSV S-channel + chroma เฉลี่ย):
  - `cam01-20261025-042617` (หลัง #2, กลางคืน ไฟเปิด): satavg 36.64, chroma 15.53 → **COLOR**
  - `cam01-20261024-201956` (เย็น): satavg 31.79, chroma 23.86 → COLOR
  - `cam01-20261024-231211`: satavg 32.32, chroma 19.68 → COLOR
- → เฟรมก่อน/หลัง plateau เป็นสีทั้งหมด กล้อง**ไม่ได้สลับเป็น IR ขาวดำ**. แต่ยืนยันได้แค่ก่อน/หลัง ไม่ใช่ตอน plateau เอง (ไม่มีเฟรม).

### สรุป (ตามข้อมูล ไม่เดา)
- fps halving เป็น **camera-side framerate drop** 2 ช่วง sustained, ไม่ใช่ CPU (ตกฉับพลัน ล็อก 15, dip CPU เป็น noise คนละแบบ), ไม่ใช่ไฟ (ON คงที่), **ไม่ใช่ IR-switch** (เฟรมขนาบเป็นสี).
- **#1**: สาเหตุชัด = camera RTSP stream reset (RTP loss + SSRC เปลี่ยน) แล้ว stream กลับมาที่ 15 fps.
- **#2**: **ไม่ทราบสาเหตุจาก log** (ไม่มี reset/restart ฝั่ง server). สอดคล้องกับกล้องเปลี่ยน encode fps เอง แต่ไม่มีหลักฐานฝั่ง Jetson/mediamtx ยืนยัน — ไม่สรุปเกินข้อมูล.
- ของที่ควรตรวจต่อ (หลัง soak): ตั้งค่า Frame Rate/Night ของ Tapo ในแอป, Wi-Fi ของกล้อง (RTP loss 12108 = สัญญาณกล้องตก), และ root cause ที่ brightness.csv ว่างตั้งแต่ 02:29.
