# Dashboard live-player — แก้ + ทดสอบ (2026-10-24)

เงื่อนไขเริ่ม: live fix A1–A4 ผ่าน (2026-10-24) + reboot test ผ่าน 7/7 → ทำต่อได้.
แก้ 3 ไฟล์ (เฉพาะส่วนภาพสด): `web/js/webrtc.js`, `web/js/ui.js`, `web/css/app.css`. รายละเอียด: `dashboard/CHANGELOG.md`.
backup: `dashboard/web.bak-20261024-085855`. deploy: scp 3 ไฟล์ + `docker restart dashboard` (web เป็น bind-mount ro).

md5 (PC=Jetson, ยืนยันจาก `curl /js/...` ที่ nginx เสิร์ฟ):
- webrtc.js `5f4d7635e9e77fade2f1948d74a32a72`
- ui.js `5c27d9dde5cca095888d4ee6cc817289`
- app.css `aa65536a33b806ed0efafb2ebe93a5ff`

## วิธีทดสอบ
Headless Chrome/Edge + CDP (DevTools Protocol, Node global WebSocket — ไม่มี library นอก) โหลด Dashboard จริง `http://<JETSON_TAILSCALE_IP>:8080/#/live` ผ่าน Tailscale, อ่าน DOM/`getStats` ของตัวเล่นจริง + screenshot. จำลองปัญหาด้วย `docker pause/stop mediamtx` (ข้อทดสอบ). เทียบกับ `tools/live_monitor/live_monitor.js`.

## ตารางทดสอบ

| รายการทดสอบ | ผล | ผ่าน |
|---|---|---|
| ภาพปกติ: เห็นภาพ ≤ 2 วิ | TTFF 0.76–1.5 วิ, video readyState 4 | ✓ |
| ป้ายคุณภาพตรงกับ live_monitor (±10%) | badge fps ~29 / lost 0 vs live_monitor avg 26.8 / lost 0 (พร้อมกัน) | ✓ |
| badge แสดงครบ | ดี/พอใช้/แย่, fps, 1280×720, ~2 Mbps, หน่วง ~100–170 ms, สูญหาย, ค้าง(5น.), ต่อเนื่อง | ✓ |
| fps ใต้ภาพ = WebRTC จริง | footer ~25–31 fps (WebRTC); fps กล้องอยู่ใน tooltip | ✓ |
| จำลองค้าง: `docker pause` 5 วิ | ขึ้น "ภาพค้าง — กำลังต่อใหม่" ที่ ~3.5 วิ, คงเฟรมค้าง (ไม่จอดำ), กลับมามีภาพ ~6 วิ หลัง unpause | ✓ |
| จำลองหลุดนาน: `docker stop` 30 วิ | ขึ้น "เชื่อมต่อไม่ได้ — ลองใหม่ใน N วิ", backoff 1→2→5→10 (ต่อ client), คงเฟรมค้าง, กลับมาเองหลัง start | ✓ |
| backoff ไม่ยิงถี่ | 1 client ต่อใหม่ถึงคาบ 10 วิ (ไม่ใช่ถี่ราย <1 วิ). raw log 16/30วิ = **มี 2 viewer** (headless + เบราว์เซอร์ผู้ใช้) ไม่ใช่ flood ต่อ client | ✓ |
| mediamtx หลัง stop/start | yml `37cb911346088a73fd369b4e2977f0d1` คงเดิม, ICE session ล่าสุดมีแต่ <JETSON_TAILSCALE_IP> / <JETSON_LAN_IP> (**172.x = 0**) | ✓ |
| ไม่มี session ค้าง | ปิด viewer → session 2→1 (ปล่อยเอง); หลัง stop/start ยัง 2; ไม่สะสม | ✓ |
| สลับแท็บ 3 ครั้ง (รัว) | session คงที่ = 2 (ไม่ซ้อน) | ✓ |
| ซ่อนแท็บ > 30 วิ → ตัด, กลับมา → ต่อ | hidden: session คง 30 วิ แล้วตกเป็น 1 ที่ ~35 วิ; visible: ต่อใหม่ทันที กลับเป็น 2 | ✓ |
| Edge | โหลดได้, metrics ครบ, ไม่มี error | ✓ |
| Chrome | โหลดได้, metrics ครบ, ไม่มี error | ✓ |
| มือถือ (390×844) | layout ไม่พัง (tile เต็มกว้าง, badge มุมขวา, nav ล่างปกติ) | ✓ |
| ส่วนอื่นของ Dashboard | ไม่แตะโค้ด (แจ้งเตือน/MQTT/รายงาน/ตั้งค่า/ตัวเลขสรุป/เหตุการณ์) — แก้แค่ 3 ไฟล์ส่วน player | ✓ |
| CPU เบราว์เซอร์ | getStats 1 ครั้ง/วิ + วาด canvas 1 ครั้ง/วิ ต่อ tile; ไม่มี loop/timer ถี่, ไม่มี library เพิ่ม → เพิ่มเล็กน้อย | ✓ (เชิงคุณภาพ) |
| console error | ไม่มี (CDP Runtime: ERRORS none ทุกรอบ) | ✓ |

ยังไม่ได้ทำ: ให้ผู้ใช้ดูด้วยตา 5 นาที (ขั้นสุดท้าย) — ต้องบอกผู้ใช้.

## ภาพหน้าจอ (`screenshots/`)
- `01_normal_quality.png` — ภาพปกติ + ป้ายคุณภาพ "ดี" (fps, ความละเอียด, bitrate, หน่วง, สูญหาย, ค้าง, ต่อเนื่อง)
- `02_stalled_frozen.png` — "ภาพค้าง — กำลังต่อใหม่" คงเฟรมสุดท้าย (ไม่จอดำ)
- `03_backoff.png` — "เชื่อมต่อไม่ได้ — ลองใหม่ใน 2 วิ" (ตอน mediamtx หยุด) + เฟรมค้าง + badge ค้าง(5น.)=1
- `04_edge.png` — Edge แสดงผลถูกต้อง
- `05_mobile.png` — จอมือถือ

`live_monitor_compare.csv` = ข้อมูล live_monitor ที่รันพร้อม badge (ใช้เทียบ ±10%).

## end-state
- app `live_20261024_0847` **events off** (ไม่ถูกแตะตลอดงานนี้), containers ครบ (mediamtx up ด้วย yml 37cb9113), disk 7.1 GB.
- Dashboard รันโค้ดใหม่. tmux cira-gui ไม่ถูกแตะ. person_count_app.py / mediamtx.yml ไม่ถูกแก้.
- หยุดรอ — ยังไม่เริ่ม soak v3.
