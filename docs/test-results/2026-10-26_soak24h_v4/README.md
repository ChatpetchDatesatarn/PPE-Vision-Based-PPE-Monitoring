# Soak v4 — 24 ชม. (2026-10-26)

เริ่มตาม runbook `docs/test-results/2026-10-25_fixes_v4/fixes_v4.md §8`. โฟลเดอร์นี้ = ผลจริง.
เป้าหมาย: ยืนยัน fixes v4 (ภาพสดฟื้นเองหลังกล้องรีเซ็ต, PtsGuard rebase/restart, ssrc คงที่, logger ครบคอลัมน์, teardown ครบ) ภายใต้ 24 ชม.

## เงื่อนไข
- เปิดไฟตลอด 24 ชม. (บันทึก `~/light on|off` → `~/light_log.csv`); ไฟ ON ตั้งแต่ `2026-10-26 07:22:10 +07`.
- กล้องสด, app `--events on`, nvpmodel **5W** (ยืนยัน: NV Power Mode 5W), cooldown แบบเดิมเหมือน v2/v3 (เทียบผลได้).
- Tapo Night Vision = อัตโนมัติ → กล้องอาจสลับ IR/ขาวดำเองตามแสง (บันทึก `satavg` ทุก 600 วิใน `brightness.csv` เพื่อระบุสี vs ขาวดำตลอด soak).
- คนในบ้านเดินผ่านกล้องเป็นระยะช่วงกลางวัน (ใส่/ไม่ใส่ PPE).

## §0 ตรวจก่อนเริ่ม (ผ่านทั้งหมด, 2026-10-26 07:2x +07)
| check | result |
|---|---|
| md5 `person_count_app.py` | `810ad1d5` ✓ |
| md5 `mediamtx.yml` | `0dae11d9` (ตัด LAN IP, เหลือ <JETSON_TAILSCALE_IP>) ✓ |
| Dashboard web v4 md5 | webrtc `6ee90de3` / ui `eaef66fd` / app `ed025d4e` / dashboard `2ebd97ab` / index `952fac61` / css `bdde26a8` ✓ |
| disk free (Jetson) | 7 GB (≥6) ✓ |
| docker | mosquitto / mediamtx / dashboard / recorder — up ✓ |
| nvpmodel | 5W ✓ |
| ICE 172.x (mediamtx 5m) | 0 ✓ |
| CiRA | `online:true`, flow `safety_decision_v1`, ts ปัจจุบัน (07:23–07:25 สด, age 1s) ✓ |
| collector/live_monitor/soak3 เก่า (Jetson+PC) | none ✓ |
| light_log last | `2026-10-26 07:22:10 (+07:00),1,` = light on ✓ |

## การเริ่ม
1. `~/ds-stop; ~/ds-start --events on` — app เฟรช (PtsGuard reset): run `live_20261026_0725`, restart **07:25:57 +07**
2. `SOAK_DIR=$D SOAK_START=$(date +%s) SOAK_HOURS=24 bash ~/safety/tools/soak3_up.sh soak3` — collectors เริ่ม **07:26:06 +07**
3. PC: `node tools/live_monitor/live_monitor.js --csv live.csv --minutes 1440 --interval 30 --base http://<JETSON_TAILSCALE_IP>:8080` (background)

## เวลา
- app restart (events on, soak run): **2026-10-26 07:25:57 +07**
- tmux soak3 สร้าง: **2026-10-26 07:26:06 +07** → ครบ 24h ~**2026-10-27 07:26 +07**
- PC live_monitor: `live.csv`, logs `live_monitor.{out,err}.log`, หยุดเองที่ `--minutes 1440`

## ช่วง pre-soak (ไม่นับรวม soak v4)
app เปิด events on ทดสอบสดช่วง **2026-10-26 02:30:28 → 07:25:57 +07** (run `live_20261026_0230`). event/snapshot/latency ที่เกิดในช่วงนี้ = pre-soak **ไม่นับรวม soak v4**. soak v4 เริ่มนับจาก 07:26:06 +07.

## CiRA counters = สะสม (ใช้ผลต่างตั้งแต่เริ่ม soak)
baseline ณ เริ่ม soak (soak.csv row แรก 07:26:14): `cira_received=269`, `cira_published=104`, `cira_filtered=165`. ค่าระหว่าง soak ให้ลบ baseline นี้ออก.

## ค่าเริ่มต้น (soak.csv row แรก 07:26:14, 51 คอลัมน์ครบ)
| metric | value |
|---|---|
| fps_in / fps_infer | 15.0 / 14.8 (กล้องอยู่ช่วง plateau 15 fps) |
| cpu_total (cpu0/cpu1/gpu) | 63.5% (64/63/79) |
| power_mw | 3338 |
| ram / swap | 2151 MB / 157 MB |
| rss_app | 1514.6 MB |
| **rss_cira** | **115.8 MB** (มีข้อมูล ✓ — แก้ปัญหา v3 ที่ว่าง) |
| temp (cpu/gpu/thermal) | 46.5 / 42.5 / 44.5 °C |
| throttled | 0 |
| disk free | 6.99 GB |
| snapshot_count / size | 408 / 19 MB |
| camera_connected / last_frame_age | 1 / 0.0 s |
| app_restarts / pts_fixed / pts_rebase | 1 / 0 / 1 (startup self-heal, ภาพ ok) |
| **live_status** | **ok** ✓ |
| cira_status_age_s | 1 (CiRA สด) |

### brightness/saturation (brightness.csv row แรก 07:26:12)
- yavg 91.18, **satavg 2.50** → ภาพเกือบไม่มีสี = **IR/ขาวดำ** ขณะนี้ (เทียบ soak v3 เฟรมสี satavg 30–36). Night Vision อัตโนมัติทำงาน. จะติดตาม satavg ตลอด soak.

## ข้อจำกัด — live_monitor ฝั่งเบราว์เซอร์มีข้อมูลแค่ 07:26–07:55
PC live_monitor (ผู้ชม WHEP ฝั่งเบราว์เซอร์) ถูก Claude Code หยุดเองตอน ~07:55 +07 เพราะเครื่อง PC หน่วยความจำต่ำ (background-shell memory reap — ไม่ใช่คำสั่งล้ม). **ไม่เริ่มใหม่** (ต้องใช้ PC; ห้ามรัน live_monitor จาก Claude Code ซ้ำ).
- `live.csv` มีข้อมูลเฉพาะ **07:26–07:55 +07** (58 แถว @30 วิ): connected ตลอด, stalled 0, reconnects 0, decoded_fps ~17–22 (กล้องแกว่ง).
- **เส้นทางภาพสดช่วงที่เหลือของ soak** พิสูจน์จากฝั่ง Jetson แทน: `soak.csv live_status` (ควร = ok เกือบตลอด), `pts_rebase`/`app_restarts` (ฟื้นเองหลังกล้องรีเซ็ต), และ `mediamtx.csv` (B-frames=0, WebRTC session เปิด/ปิด) ตลอด 24 ชม.
- ผู้ใช้เปิด Dashboard ดูเป็นระยะ — บันทึกเวลา+ผลด้านล่าง.

### บันทึกผู้ใช้ดู Dashboard (เวลา +07 / ผล)
| เวลา | ภาพสดขึ้น? | หมายเหตุ |
|---|---|---|
| (รอผู้ใช้แจ้ง) | | |

### ผู้ชมที่แชร์ผ่าน Tailscale (ผู้ใช้แจ้ง, ไม่ใช่ความผิดปกติ)
ผู้ใช้แชร์เครื่อง Jetson ใน Tailscale ให้เพื่อนดู Dashboard (จำกัดสิทธิ์เหลือ `tcp:8080` + `udp:8189` ผ่าน Tailscale grant ตั้งใน admin console). ผู้ใช้ตั้งเอง — ไม่แตะ mediamtx/network/Tailscale จากฝั่งนี้.
- ผลที่คาดเห็น: **จำนวน WebRTC session ใน `mediamtx.csv` (`webrtc_sessions_opened_total`) อาจเพิ่ม** จากผู้ชมเพิ่ม = **ปกติ ไม่ใช่ความผิดปกติ**.
- IP Tailscale ของผู้ใช้ = `<TAILSCALE_IP>`. session จาก IP Tailscale อื่น = **ผู้ชมที่แชร์ (เพื่อน)** ไม่ใช่ปัญหา.
- เวลาที่เพื่อนเริ่มเข้าดู Dashboard: **~14:40 +07** (ผู้ใช้แจ้ง). session WebRTC ที่เพิ่มหลังเวลานี้ = ผู้ชมที่แชร์.

## เกณฑ์ผ่าน v4 (= v3 + เพิ่ม)
- ทุกเกณฑ์ v3 (uptime/fps/RSS/RAM/temp+throttle/กล้อง/CiRA/latency/disk/restart/power).
- ภาพสด: ไม่มี `stalled` นานเกิน 30 วิ ตลอด 24 ชม. (`live.csv stalled_total_s` ไม่พุ่ง; `soak.csv live_status` = ok เกือบตลอด).
- ฟื้นเองหลังกล้องรีเซ็ตทุกครั้ง (`pts_rebase` เพิ่มแล้วภาพกลับ ≤10 วิ; ไม่มีช่วง PTS 1ms/เฟรม).
- teardown ครบ (`soak_done.txt` = app events off + ไม่มี collector ค้าง).
- brightness/rss_cira มีข้อมูลครบ 24 ชม. (ไม่มีช่องว่างยาว).

## สิ่งที่ผู้ใช้ทำระหว่าง soak
- เดินผ่านกล้องเป็นระยะ (ใส่/ไม่ใส่ PPE) → ยืนยัน event via=cira + latency.csv.
- บังคับกล้องรีเซ็ต 1 ครั้ง (Privacy Mode) เพื่อยืนยัน pts_rebase + ฟื้นเอง.
- จดเปิด/ปิดไฟด้วย `~/light`.

## ครบ 24 ชม. (อัตโนมัติ)
`soak_logger_v3` เรียก `soak_end_v4.sh`: หยุด collector ทุกตัว + `ds-stop; ds-start` (events off) + kill soak3 + เขียน `soak_done.txt`. PC live_monitor หยุดเองที่ `--minutes 1440`.

## วิธีหยุด (ฉุกเฉิน)
- collectors: `ssh jetson "tmux kill-session -t soak3"`
- PC live_monitor: kill process node (`live_monitor.out.log`)

## สำหรับรายงาน v4 (Errata ของ v3)
ข้อสรุป soak v3 "fps 15 ไม่ใช่ IR (เฟรมขนาบเป็นสี)" **ยืนยันไม่ได้** เพราะกล้องตั้ง Night Vision อัตโนมัติ และ v3 ไม่มีเฟรมตอน plateau โดยตรง. soak v4 บันทึก satavg ต่อเนื่อง — row แรกแล้วได้ satavg 2.5 (ขาวดำ) ที่ fps 15 → จะสรุปความสัมพันธ์ fps↔IR ด้วยข้อมูล v4 จริง.

---

## ผลสรุป soak v4 (จบแล้ว 2026-10-27 07:26:13 +07)

รายงานเต็ม: `soak_v4_report.docx` (สี, 23 รูป, 6 ตาราง, 14 หัวข้อ + ภาคผนวก) และ `soak_v4_report_bw.docx` (ขาวดำ). สร้างด้วย `report_scripts/gen_v4_graphs.py` + `build_v4_docx.py` (reproducible; แก้รายงาน = แก้สคริปต์แล้วรันใหม่). ข้อมูลดิบใน `data/`.

**teardown อัตโนมัติครบ** (`soak_done.txt`): app `--events off` (run `live_20261027_0726`), leftover_collectors = 0, OK. start 2026-10-26 07:26:06 → end 2026-10-27 07:26:06 (24h / 1440 แถว).

### ผ่านทุกเกณฑ์ 14/14 (รวมข้อ 14 ภาพสด ที่ v2/v3 FAIL)
| # | รายการ | v4 |
|---|---|---|
| 1 | Uptime | 24.0 ชม. (100%), app_restarts 0 |
| 3 | fps_in เฉลี่ย | 25.33 (ตก ~15 เป็นระยะ) |
| 4 | RSS app (regression) | 0.79 MB/ชม. (R² 0.60), ต้น-ปลาย 1.25 — แทบคงที่ ไม่รั่ว |
| 5 | RAM / swap | สูงสุด 2213 MB (56%) / 157 MB คงที่ |
| 6 | อุณหภูมิ / throttle | thermal สูงสุด 67°C / throttled 0 |
| 7 | กล้อง | camera_connected 1440/1440; frame_age สูงสุด 1.3 วิ |
| 8 | CiRA heartbeat / fallback | age ≤3 วิ / fallback 0 |
| 9 | received=published+filtered (Δ soak) | 52 = 26 + 26 |
| 10 | latency p95 | 805 ms (n=25; mean 319 / median 220 / max 1185) |
| 11 | disk | 7.0 GB คงที่ |
| 12 | container restart / dmesg ใหม่ | 0 / 0 (คงที่ 18) |
| 13 | กำลังไฟ | เฉลี่ย ~4509 / สูงสุด 6280 mW; 108.15 Wh/24ชม. |
| 14 | **ภาพสด** | **live_status=ok 1440/1440; stalled 0; pts_rebase 26 โดยไม่ค้าง → PASS** |

### event + walk test
- event ช่วง soak = **26** (no_helmet 17, no_vest 9, restricted 0); **via cira 26, via fallback 0** (ผ่าน CiRA 100%); unique_tracks 18.
- walk test: event แรก `cam01-20261026-125000` (12:50:00) type=no_helmet, **via=cira**, confidence 0.906, latency 170 ms — ยืนยันทุกคอลัมน์ latency.csv ครบ (zone_id ว่าง เพราะไม่มี restricted_zone).
- filtered 24 รายการ (ส่วนใหญ่ cooldown).

### A1 pts_guard ยืนยันแก้บั๊ก v3 สำเร็จ
pts_rebase 26 ครั้งตลอด 24 ชม. (กล้องรีเซ็ต/กระตุก) — ทุกครั้ง live_status ยังคง ok, ภาพไม่ค้าง. pts_fixed สะสม 13949. B-frame reject 0. (v3: A1 เก่าทำ timeline 1ms พังถาวร — v4 ไม่เกิดอีก).

### mediamtx / Tailscale
WebRTC sessions opened 78 / closed 79 ใน 24 ชม. = ผู้ใช้ (`<TAILSCALE_IP>`) + ผู้ชมแชร์ (เข้า ~14:40) — ปกติ. B-frames 0 ตลอด.

### Errata v3 (fps 15 = IR) — ตรวจเฟรมกลางวันแล้ว = ขาวดำ
- **ตรวจเฟรมกลางวัน 2026-10-27 12:13** (3 เฟรมห่าง 10 วิ จาก `rtsp://127.0.0.1:8554/cam01` localhost, ไม่เปิด RTSP ตรงกล้อง) → `evidence/frames_20261027_daytime/f1–f3.png`.
- กลางวันสว่าง (yavg 94.7/100.5/99.0) แต่ **satavg 1.3/1.4/2.5** (สูตรเดิม signalstats); ตรวจซ้ำ PIL/numpy: ระนาบ chroma YCbCr แบนที่ 128 (|Cb−128| ~1.5–2.5, |Cr−128| ~1–1.3), chroma พื้นหลัง ~3–5 → **ภาพกล้องเป็นขาวดำแม้กลางวัน = กล้องอยู่โหมด IR/Night Vision**.
- ∴ satavg ต่ำทั้ง soak (132/143 แถว <5) **ถูกต้อง** (ภาพขาวดำจริง) ไม่ใช่สูตรวัดผิด. fps ~15 **สอดคล้องกับ** โหมด IR (fps ยังตกฝั่งกล้อง/เครือข่ายด้วย ยังพิสูจน์สาเหตุเดียวไม่ได้ — ไม่ฟันธง).
- **ข้อเสนอ:** ตั้ง Night Vision = **Off** ช่วงทดสอบ หรือเพิ่มแสง แล้ว soak ซ้ำ. **แก้วิธีวัด:** satavg เดิมวัดจากสตรีม overlay (กรอบสีดัน satavg ตอนมีคน) + ย่อ 160 + crop OSD บน — soak หน้าให้ดึง **ก่อน overlay**.

### ข้อจำกัดเพิ่ม
- events_via_cira counter = 26 แต่ latency.csv 25 แถว (ขาด 1 — น่าจะ no_vest: counter 9 vs latency 8).
- ภาพสดเบราว์เซอร์มีแค่ 07:27–07:55; ไม่มีภาพ no-overlay ตอน fps~15; บันทึกเวลาผู้ใช้ดู Dashboard ยังว่าง.
