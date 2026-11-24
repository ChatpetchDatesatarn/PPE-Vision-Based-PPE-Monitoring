# Dashboard v3 (web) — ผลทดสอบ

> **รอบ 2 ยังทำไม่ครบ** เพราะเครื่องนี้ยังไม่มี `guy_repo_base_2026-10-15.zip` และไม่มี Docker Desktop / WSL2
> (`wsl --status` → `Class not registered`) ตาม PROMPT รอบ 2 ขั้นที่ 3 จึงหยุดไว้ก่อน
> คอลัมน์ "รอบ 2 (backend จริง)" จะกรอกหลังได้ zip และติดตั้ง Docker แล้ว ส่วนข้อ 2a/2b ทดสอบกับ mock ไปก่อน

## เวอร์ชัน library (`web/lib/VERSIONS.txt`)
| ไฟล์ | เวอร์ชัน | ต้นทาง |
|---|---|---|
| `web/lib/mqtt.min.js` | mqtt.js 5.10.1 (browser build, `window.mqtt`) | https://cdn.jsdelivr.net/npm/mqtt@5.10.1/dist/mqtt.min.js |
| `web/lib/chart.umd.min.js` | Chart.js 4.4.4 (UMD, `window.Chart`) | https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.js |

## ผลทดสอบตามเกณฑ์ข้อ 11
| # | เกณฑ์ | รอบ 1 (mock) | รอบ 2 (backend จริง) |
|---|---|---|---|
| 1 | ไฟ 3 ดวงเขียว, KPI, แจ้งเตือนพร้อมรูป < 1 วินาที | ✅ | ⏳ รอ Docker + repo |
| 2 | `--cira-down` → Decision แดง ≤ 30 วินาที + FALLBACK | ✅ | ⏳ |
| 3 | `--camera-down` → Camera แดง + "กล้องขาดการเชื่อมต่อ" | ✅ | ⏳ |
| 4 | หยุด simulator → Perception แดง ≤ 15 วินาที | ✅ | ⏳ |
| 5 | หยุด mosquitto → แถบขาดการเชื่อมต่อ แล้วกลับมาเอง | ✅ (mock ปิด WS) | ⏳ |
| 6 | "แจ้งผิด" ใน A → B เห็นทันที + Report เปลี่ยน | ✅ | ⏳ |
| 7 | Live View เล่นภาพจาก MediaMTX | ⚠️ ไม่มี MediaMTX | ⏳ |
| 8 | ตัวกรอง / แบ่งหน้า / CSV ใน Excel | ✅ / ✅ / ⚠️ | ⏳ |
| 9 | รีเฟรชแล้วประวัติอยู่ครบ | ✅ | ⏳ |
| 10 | มือถือ 360 px | ✅ จำลอง (scrollWidth = 360 ทุกหน้า) | ⏳ |
| 11 | ไม่มีอินเทอร์เน็ตแล้วยังโหลดครบ | ✅ (grep ไม่พบ URL ภายนอก) | ⏳ |
| 12 | Console ไม่มี error สีแดง | ✅ ไม่มี JS error (มีแค่ 404 ของ WHEP ใน mock) | ⏳ |
| 13 | Zone editor + retain | ✅ | ⏳ (`mosquitto_sub`) |
| 2a | นาฬิกาเครื่องต่างจากระบบ → ไฟยังเขียว + ข้อความชดเชย | — | ✅ **mock** `clock_skew=60`: ไฟเขียวครบ 3 ดวง, ขึ้น "นาฬิกาเครื่องนี้ต่างจากระบบ 60 วินาที (ชดเชยแล้ว)" · ⏳ เลื่อนนาฬิกา Windows + backend จริง |
| 2b | สลับหน้า Live 5 ครั้งแล้วไม่มี session ค้าง | — | ✅ **mock** `whep=1`: DELETE 11 ครั้ง ทุกครั้งเจอ session (`unknown` = 0), เหลือ `whep_sessions = 0` หลังออกจากหน้า · ⏳ MediaMTX จริง (`/v3/webrtcsessions/list`) |
| — | Firefox (Dashboard + Live) | — | ⏳ ยังไม่ได้ทดสอบ |
| — | `python -m unittest test_store` | — | ⏳ ยังไม่มีไฟล์ recorder |

## ภาพหน้าจอ
`test_screenshots/` ตอนนี้เป็นภาพจากรอบ 1 (mock, 1536×1000) ยังไม่ใช่ของจริง ต้องถ่ายใหม่กับ backend จริงพร้อมภาพมือถือ 360 px

## วิธีทดสอบด้วย mock
```
pip install aiohttp
python dashboard/dev_mock/mock_server.py dashboard/web 8080
```
ควบคุมผ่าน `http://localhost:8080/mock/ctl?cira_down=1&camera_down=1&sim=0&mqtt=0&whep=1&clock_skew=60&burst=3`
(`whep=1` = ตอบ 201 + `Location` แบบ MediaMTX พร้อม SDP ปลอม เพื่อทดสอบว่าส่ง DELETE ครบ ภาพจะไม่เล่น)
