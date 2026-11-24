# คู่มือโครงสร้างโฟลเดอร์

คู่มือนี้อธิบายว่าแต่ละโฟลเดอร์ใน repo คืออะไร มีไว้ทำไม ข้างในมีอะไร และถ้าอยากทำงานอย่างหนึ่งควรเปิดโฟลเดอร์ไหน อ่านหัวข้อ 1–3 ก่อนเพื่อเห็นภาพรวม แล้วค่อยเปิดหัวข้อของโฟลเดอร์ที่จะทำงานด้วย

---

## 1. ภาพรวมในหนึ่งนาที

ระบบแบ่งเป็น 3 ส่วนหลักที่คุยกันผ่าน MQTT (broker ชื่อ mosquitto) ทุกส่วนรันอยู่บน Jetson Nano เครื่องเดียว

```
กล้อง Tapo (RTSP)
   │
   ▼
perception/   "ตา"    DeepStream ตรวจคน หมวก เสื้อ แล้วบอกว่าใครน่าจะผิดกฎ
   │  ds/violation + snapshot (MQTT)
   ▼
decision/     "สมอง"  CiRA CORE ตัดสินว่าเรื่องไหนควรแจ้งเตือนจริง
   │  event (MQTT)
   ▼
dashboard/    "จอ"    เก็บประวัติลงฐานข้อมูล และแสดงหน้าเว็บให้เจ้าหน้าที่
```

ภาพสดใช้อีกเส้นทางหนึ่ง: `perception/` ส่งวิดีโอที่วาดกรอบแล้วออกทาง RTSP → MediaMTX (อยู่ใน `dashboard/`) แปลงเป็น WebRTC → เบราว์เซอร์

ส่วนที่เหลือเป็นของประกอบ: `tools/` เครื่องมือ, `training/` ที่มาของโมเดล, `docs/` เอกสาร, `legacy/` โค้ดรุ่นเก่า

---

## 2. แผนผังโฟลเดอร์

```
PPE-Vision-Based-PPE-Monitoring/
├── README.md              หน้าแรกของ repo: ภาพรวม ผลลัพธ์ วิธีเริ่มใช้งาน
├── .gitignore             รายการไฟล์ที่ห้ามขึ้น GitHub (รหัส, โมเดล, log)
├── .cam.env.example       ตัวอย่างไฟล์รหัสกล้อง
│
├── perception/            ส่วนตรวจจับ (DeepStream บน Jetson)
│   ├── app/               แอปหลัก + โมดูลย่อย + unit test
│   ├── test/              config ที่แอปใช้จริง + สคริปต์ทดสอบ/benchmark
│   ├── models/            config ของแต่ละโมเดล (ไม่มีไฟล์ weight)
│   ├── export/            สคริปต์แปลงโมเดลเป็น ONNX
│   └── cam_discover.sh    หา IP กล้องเองเมื่อ IP เปลี่ยน
│
├── decision/              ส่วนตัดสินใจ (CiRA CORE)
│   ├── safety_decision_v1.npj   ไฟล์ flow ที่เปิดใน CiRA
│   ├── src/               โค้ด JavaScript ของ node ใน flow
│   └── tests/             test ของโค้ดตัดสินใจ
│
├── dashboard/             หน้าเว็บ + ระบบเก็บข้อมูล (Docker)
│   ├── web/               หน้าเว็บ (HTML/CSS/JS)
│   ├── recorder/          backend เก็บเหตุการณ์ (FastAPI + SQLite)
│   ├── nginx/             เว็บเซิร์ฟเวอร์ + ทางเข้าเดียวของทุกบริการ
│   ├── mediamtx/          แปลงภาพสด RTSP เป็น WebRTC
│   ├── mosquitto/         MQTT broker
│   ├── dev_mock/          backend ปลอมสำหรับทดสอบหน้าเว็บ
│   └── media/             ที่วางคลิปทดสอบบน PC
│
├── tools/                 เครื่องมือ: จำลองข้อมูล, autostart, soak test, วัดภาพสด
├── training/              ข้อมูลการเทรนโมเดล PPE
├── docs/                  เอกสารออกแบบ, สเปก MQTT, ผลทดสอบทุกครั้ง, รูปประกอบ
└── legacy/                โค้ดรุ่น v1/v2 ที่เลิกใช้แล้ว
```

---

## 3. ชื่อใน repo กับชื่อเดิมบน PC และ Jetson

โฟลเดอร์ทำงานเดิมบน PC และ `~/safety` บน Jetson ยังใช้ชื่อแบบมีเลข ใช้ตารางนี้เทียบเวลาสลับไปมา

| ใน repo | ชื่อเดิม |
|---|---|
| `perception/` | `13_deepstream/` |
| `decision/` | `04_cira_workflows/` |
| `dashboard/` | `14_dashboard_v3/` |
| `tools/` | `09_tools/` |
| `training/remap_construction_ppe.py` | `09_tools/remap_construction_ppe.py` |
| `training/results/` | `06_final_report/evidence/colab_export/` |
| `docs/` | `08_docs/` |
| `docs/test-results/` | `05_test_results/` (เฉพาะไฟล์ .md) |
| `perception/cam_discover.sh` | `cam_discover.sh` (ที่ root) |
| `tools/boot.conf.example` | `boot.conf` (ที่ root) |
| `dashboard/CHANGELOG.md` | `14_dashboard_v3/CHANGES_FOR_GUY.md` |
| `legacy/esp32_alert_node/` | `06_firmware_esp32/` |
| `legacy/dashboard_v2/` | `07_dashboard/` |
| `legacy/jetson_v2/` | `10_jetson/` |
| `legacy/docker_v2/` | `11_docker/` |
| `legacy/cira_v2_python/` | `12_cira/` |

path ในสคริปต์และ config ของ repo ถูกแก้เป็นชื่อใหม่แล้ว ถ้าจะติดตั้งจาก repo นี้ ให้ clone เป็น `~/safety` แล้วใช้ชื่อใหม่ทั้งหมด อย่าใช้ปนกับชื่อเดิม

---

## 4. ไฟล์ที่ root

| ไฟล์ | คืออะไร | มีไว้ทำไม |
|---|---|---|
| `README.md` | หน้าแรกที่ GitHub แสดง | ให้คนที่เข้ามาครั้งแรกรู้ว่าโปรเจกต์ทำอะไร ได้ผลเท่าไร และเริ่มตรงไหน |
| `.gitignore` | รายการไฟล์ที่ git จะไม่เอาขึ้น | กันรหัสกล้อง, PIN, ไฟล์โมเดลขนาดใหญ่, ฐานข้อมูล, log และไฟล์สำรองหลุดขึ้น GitHub |
| `.cam.env.example` | ตัวอย่างไฟล์รหัสกล้อง (`CAM_IP`, `CAM_USER`, `CAM_PASS`) | ให้รู้ว่าต้องสร้าง `~/safety/.cam.env` บน Jetson อย่างไร โดยไม่ต้องเปิดเผยรหัสจริง |

---

## 5. `perception/` : ตาของระบบ

**คืออะไร** แอป Python ที่สร้าง pipeline ของ DeepStream บน Jetson: รับภาพจากกล้อง → ตรวจคนด้วย YOLOv8n COCO → ตรวจหมวกและเสื้อด้วยโมเดล ppe3 ที่เทรนเอง → ติดตามคนข้ามเฟรม → จับคู่หมวก/เสื้อกับคน → ส่งผลทาง MQTT และส่งภาพสดออกทาง RTSP

**มีไว้ทำไม** การตรวจจับต้องใช้ GPU ของ Jetson ผ่าน TensorRT จึงต้องเป็นโปรแกรมแยกที่รันใกล้กล้องที่สุด ส่วนนี้ทำหน้าที่ "เห็น" อย่างเดียว ไม่ตัดสินว่าควรแจ้งเตือนไหม (เป็นหน้าที่ของ `decision/`) ยกเว้นตอนที่ CiRA ไม่ตอบเกิน 15 วินาที จึงส่ง event เองแบบ fallback

**ข้างในมีอะไร**

| ไฟล์ / โฟลเดอร์ | หน้าที่ |
|---|---|
| `app/person_count_app.py` | แอปหลัก: สร้าง pipeline, วาดกรอบ, ต่อกล้องใหม่เมื่อหลุด, ส่ง MQTT ปรับพฤติกรรมได้ด้วย argument เช่น `--events on`, `--camera-id`, `--camera-name`, `--zone-mode` |
| `app/obj_route.py` | บอกว่าวัตถุแต่ละชิ้นมาจากโมเดลไหน (ทั้งสองโมเดลนับคลาสจาก 0 เหมือนกัน) |
| `app/person_ids.py` | ให้เลขคนคงที่ตลอดที่อยู่ในภาพ แม้ถูกบังชั่วคราว |
| `app/ppe_pretrack.py` | เก็บกรอบหมวก/เสื้อไว้ก่อนเข้า tracker (tracker ส่งต่อเฉพาะคน) |
| `app/ppe_assign.py` | จับคู่หมวก (ช่วงบน 35% ของกรอบคน) และเสื้อ (ช่วง 20–75%) กับคน |
| `app/ppe_smooth.py` | ดูหลายเฟรมย้อนหลังก่อนสรุปว่าคนนี้ใส่ (✓) ไม่ใส่ (✗) หรือยังไม่แน่ใจ (?) |
| `app/violations.py` | นับเวลาที่ผิดกฎต่อเนื่อง: ไม่ใส่หมวก 2 วินาที, ไม่ใส่เสื้อ 4 วินาที, เข้าเขตอันตราย 0.5 วินาที แล้วส่ง `ds/violation` ซ้ำทุก 5 วินาที รวมถึงตรรกะโซนเฝ้าระวังและ event แบบ fallback |
| `app/status_mqtt.py` | ส่งสถานะกล้อง `<cam>/status` ทุก 5 วินาที (fps, จำนวนคน, ใส่ครบกี่คน ฯลฯ) |
| `app/pts_guard.py` | แก้เวลาของเฟรมไม่ให้ภาพสดค้างเมื่อกล้องรีสตาร์ต |
| `app/run_person_app.sh` / `start_person_app.sh` / `stop_person_app.sh` | สคริปต์รัน/หยุดแอปใน tmux `ds` บน Jetson ลิงก์ไว้เป็น `~/ds-start` และ `~/ds-stop` |
| `app/test_*.py` | unit test ของโมดูลย่อย รันบน PC ได้โดยไม่ต้องมี DeepStream |
| `test/` | **ไม่ได้มีแค่ test**: เก็บ config ที่แอปใช้จริงด้วย เช่น `config_infer_cam_person_320.txt` (ตัวตรวจคน) และ `tracker_nvdcf_tuned.yml` รวมถึงสคริปต์ probe กล้อง, benchmark และ config ของ `deepstream-app` ที่ใช้ทดลอง |
| `models/yolov8n_ppe3_416/` | config ของโมเดล PPE ที่ใช้งานจริง (`config_infer_yolov8n_ppe3_hv.txt`), `labels.txt` (person, helmet, vest), `info.json`, `run_export.py` |
| `models/yolo11n_ppe3_416/` | config ของโมเดลตัวเปรียบเทียบ (ไม่ได้ใช้งานจริง) |
| `export/` | สคริปต์แปลงไฟล์ `.pt` ของ Ultralytics เป็น ONNX ให้ DeepStream-Yolo อ่านได้ |
| `cam_discover.sh` | ถ้าต่อกล้องไม่ได้หลายครั้ง แอปจะเรียกสคริปต์นี้สแกนหา IP ใหม่ของกล้อง |

**ใช้เมื่อไหร่** แก้วิธีตรวจจับ, ปรับเกณฑ์ความมั่นใจของโมเดล, เปลี่ยนโมเดล, แก้ปัญหาภาพสดฝั่งต้นทาง, เพิ่มกติกา violation

**ข้อควรระวัง**
- โค้ดต้องรันได้บน Python 3.6 (Jetson): ห้ามใช้ `:=`, `dataclasses`, `match`
- รันคำสั่ง `python3` / `deepstream-app` แบบ `env -u PYTHONPATH ...` เพราะ CiRA ใส่ path ของ Python 2.7 ไว้
- ไฟล์ TensorRT `.engine` ต้อง build บน Jetson เท่านั้น
- ห้ามพิมพ์หรือ log รหัสกล้อง สคริปต์อ่าน `~/safety/.cam.env` ด้วย `source` เท่านั้น

---

## 6. `decision/` : สมองที่ตัดสินใจ

**คืออะไร** flow ใน CiRA CORE ที่รับ `ds/violation` จาก perception แล้วตัดสินว่าเรื่องไหนควรเป็นการแจ้งเตือนจริง จากนั้นส่ง `event` (`via: "cira"`) ไปให้ dashboard และส่ง heartbeat `cira/status` ทุก 10 วินาที

**มีไว้ทำไม** แยก "เห็น" ออกจาก "ตัดสิน": perception รายงานทุกอย่างที่น่าสงสัย ส่วน CiRA กรองตามความมั่นใจขั้นต่ำและไม่แจ้งเรื่องเดิมซ้ำภายใน 30 วินาที (cooldown) ทำให้ปรับกติกาการแจ้งเตือนได้โดยไม่ต้องแตะ pipeline ของ DeepStream

**ข้างในมีอะไร**

| ไฟล์ | หน้าที่ |
|---|---|
| `safety_decision_v1.npj` | ไฟล์ flow ที่เปิดใน CiRA CORE (9 node, 2 สาย: สายตัดสินใจ และสาย heartbeat) |
| `src/cira_node_decide.js` | โค้ดของ node ตัดสินใจ: ความมั่นใจขั้นต่ำ no_helmet 0.40, no_vest 0.35, restricted_zone 0.30 และ cooldown 30 วินาที |
| `src/cira_node_heartbeat.js` | โค้ดของ node ที่สร้าง `cira/status` |
| `tests/test_decide_es5.js` | test 15 ข้อของโค้ดตัดสินใจ รันด้วย `node tests/test_decide_es5.js` |
| `README.md` | วิธีเปิด CiRA แบบไม่มีจอ (Xvfb + VNC ผ่าน SSH) และตรวจว่าทำงาน |
| `CIRA_NOTES.md` | บันทึกว่า node ต่าง ๆ ของ CiRA ทำงานจริงอย่างไร |
| `TEST_RESULTS.md` | ผลทดสอบ flow บน Jetson จริง |

**ใช้เมื่อไหร่** เปลี่ยนเกณฑ์การแจ้งเตือน, เปลี่ยน cooldown, เปลี่ยนระดับความรุนแรง, เปิด CiRA หลังรีบูต

**ข้อควรระวัง**
- JavaScript ใน CiRA เป็น ES5 (QtScript) ห้ามใช้ `let`, `const`, arrow function
- โค้ดใน `src/` เป็นสำเนาของโค้ดที่ฝังอยู่ใน node ของ `.npj` แก้แล้วต้องอัปเดตทั้งสองที่ (`tools/npj_tool.py` ช่วยอ่านและแก้ `.npj` ได้)

---

## 7. `dashboard/` : จอของเจ้าหน้าที่

**คืออะไร** ทุกอย่างที่ทำให้เจ้าหน้าที่เห็นและจัดการเหตุการณ์ได้ รันเป็น Docker container 4 ตัวบน Jetson: `mosquitto`, `recorder`, `mediamtx` และ `dashboard` (nginx ที่พอร์ต 8080)

**มีไว้ทำไม** perception และ decision ส่งข้อมูลออกมาเป็นข้อความ MQTT ซึ่งคนอ่านไม่ได้และหายไปทันที ส่วนนี้เก็บข้อมูลไว้เป็นประวัติ และแสดงเป็นหน้าเว็บที่เปิดจากเบราว์เซอร์ไหนก็ได้ในวง LAN/VPN

**ข้างในมีอะไร**

| ไฟล์ / โฟลเดอร์ | หน้าที่ |
|---|---|
| `web/index.html`, `web/css/app.css` | โครงหน้าและหน้าตาทั้งหมด |
| `web/js/app.js` | จุดเริ่มของเว็บ: เปลี่ยนหน้า (`#/dashboard`, `#/live` ...), เก็บสถานะกลาง, คำนวณไฟสถานะ 4 ดวง |
| `web/js/pages/` | หนึ่งไฟล์ต่อหนึ่งหน้า: `dashboard.js` (Overview), `live.js`, `events.js`, `report.js`, `settings.js` (รวม zone editor) |
| `web/js/mqtt-client.js` | ต่อ MQTT ผ่าน WebSocket, รับสถานะ/เหตุการณ์, ส่ง ack และโซน |
| `web/js/api.js` | เรียก API ของ recorder |
| `web/js/webrtc.js` | ตัวเล่นภาพสด (ต่อใหม่เมื่อภาพค้าง, วัดคุณภาพ) |
| `web/js/ui.js`, `web/js/dialogs.js` | ส่วนประกอบที่ใช้ร่วมกัน (ช่องภาพสด, หน้าต่างรายละเอียด, เสียง) และหน้าต่างยืนยัน/ใส่ PIN |
| `web/js/labels.js`, `web/js/config.js` | ข้อความและสีของแต่ละประเภท/ระดับ, ค่าคงที่ที่ปรับได้ |
| `web/lib/` | library ภายนอก (mqtt.js, Chart.js) เก็บไว้ในเครื่องเพื่อให้ใช้ได้โดยไม่มีอินเทอร์เน็ต ห้ามแก้ |
| `recorder/app.py` | รับข้อความ MQTT แล้วบันทึก และให้บริการ API `/api/...` |
| `recorder/store.py`, `recorder/test_store.py` | ฐานข้อมูล SQLite และรูป snapshot (ลบรูปเก่าเอง) พร้อม unit test |
| `nginx/` | ทางเข้าเดียวที่พอร์ต 8080: เว็บ, `/mqtt`, `/api/`, `/webrtc/`, `/data/snapshots/` ไฟล์ `.conf` ใช้บน Jetson ส่วน `.dev.conf` ใช้บน PC |
| `mediamtx/` | รับภาพสดจาก perception แล้วส่งเป็น WebRTC (`mediamtx.yml` = Jetson, `mediamtx.dev.yml` = PC) |
| `mosquitto/` | config ของ MQTT broker |
| `dev_mock/` | backend ปลอม ใช้ทดสอบหน้าเว็บได้แม้ไม่มี Docker |
| `media/` | ที่วางคลิป `test.mp4` เพื่อทดสอบภาพสดบน PC |
| `docker-compose.yml` / `docker-compose.dev.yml` | สั่งรันทุก container บน Jetson / บน PC |
| `.env.example` | ตัวอย่างไฟล์ตั้ง PIN สำหรับลบเหตุการณ์ |
| `CHANGELOG.md` | ประวัติทุกรุ่นของหน้าเว็บ (v3 ถึง v7.3) พร้อมวิธีย้อนกลับ |
| `TEST_RESULTS.md` | ผลทดสอบตามเกณฑ์รับงาน 13 ข้อ |

**ใช้เมื่อไหร่** แก้หน้าเว็บ, แก้ API หรือการเก็บข้อมูล, เปลี่ยน IP ที่ภาพสดใช้, ทดลองระบบบน PC โดยไม่มีกล้อง

**ข้อควรระวัง**
- หน้าเว็บห้ามโหลดอะไรจากอินเทอร์เน็ต และห้ามใส่ IP ในโค้ด (ใช้ path แบบ relative)
- แก้ `web/` แล้วแค่ `docker restart dashboard` ส่วนแก้ `recorder/` ต้อง build ใหม่
- ไม่มีระบบ login ห้ามเปิดพอร์ตออกอินเทอร์เน็ต

---

## 8. `tools/` : เครื่องมือประกอบ

**มีไว้ทำไม** รวมสคริปต์ที่ไม่ใช่ตัวระบบ แต่จำเป็นต่อการพัฒนาและดูแลระบบ แบ่งเป็น 4 กลุ่ม (รายละเอียดทุกไฟล์อยู่ใน [`tools/README.md`](../tools/README.md))

| กลุ่ม | ไฟล์หลัก | ใช้ทำอะไร |
|---|---|---|
| จำลองข้อมูล | `simulate_v3.py` | ส่งข้อมูลปลอมทุก topic ให้ Dashboard ทำงานได้โดยไม่มีกล้อง |
| Autostart บน Jetson | `safety-autostart.service`, `safety-boot.sh`, `cira-up.sh`, `boot.conf.example` | เปิดทั้งระบบเองหลังบูต: รอ broker → เริ่ม perception → เปิด CiRA |
| Soak test | `soak3_up.sh`, `soak_logger_v3.sh`, `soak_sample_v3.py`, `soak_mqtt.py` | เก็บค่าทุกนาทีตลอด 24 ชม. เพื่อพิสูจน์ความเสถียร |
| วัดภาพสด | `live_monitor/` | เปิดภาพสดแบบเดียวกับ Dashboard แล้วบันทึกว่าค้างหรือหลุดไหม |

ไฟล์ที่มีเลขรุ่นเก่ากว่า (เช่น `soak_logger.sh`, `soak_logger_v2.sh`) เก็บไว้เพื่อให้ผลทดสอบรอบก่อนหน้าทำซ้ำได้

---

## 9. `training/` : ที่มาของโมเดล

**คืออะไร** ข้อมูลว่าโมเดลตรวจหมวก/เสื้อถูกเทรนมาอย่างไร: ใช้ชุดข้อมูลอะไร, แปลงคลาสอย่างไร, ตั้งค่าอะไร และได้ผลเท่าไร

**มีไว้ทำไม** ภาพและไฟล์ weight ใหญ่เกินกว่าจะใส่ใน repo แต่ต้องมีหลักฐานพอให้คนอื่นเทรนซ้ำหรือตรวจผลได้ และต้องให้เครดิตชุดข้อมูลตาม license (CC BY 4.0)

**ข้างในมีอะไร**
- `README.md`: ชุดข้อมูล 4 ชุดจาก Roboflow, กติกาแปลงเป็น 3 คลาส, hyperparameter, ตารางผล
- `results/yolov8n_ppe3_416/`, `results/yolo11n_ppe3_416/`: `args.yaml` (ค่าที่ใช้เทรน) และ `results.csv` (ผลทุก epoch)
- `remap_construction_ppe.py`: สคริปต์จากการทดลองช่วงแรก ไม่ได้ใช้กับโมเดลสุดท้าย

---

## 10. `docs/` : เอกสาร

| ไฟล์ / โฟลเดอร์ | เนื้อหา | ใช้เมื่อไหร่ |
|---|---|---|
| `mqtt_spec.md` | สเปก topic และ payload ทั้งหมด | **ก่อน**แก้อะไรที่ส่งหรือรับ MQTT เพราะเป็นข้อตกลงกลางของทุกส่วน |
| `design_v3_low_latency.md` | เหตุผลการออกแบบ v3 และการเลือกกล้อง | อยากรู้ว่าทำไมระบบเป็นแบบนี้ |
| `proposal/` | ข้อเสนอโครงการ | ดูเป้าหมายและขอบเขตตั้งต้น |
| `test-results/` | สรุปผลทดสอบทุกครั้ง เรียงตามวันที่ (ดูรายการใน [`docs/README.md`](README.md)) | ดูว่าเคยลองอะไร ได้ผลเท่าไร ปัญหาเคยแก้อย่างไร |
| `images/` | รูปที่ README ใช้ | — |
| `FOLDER_GUIDE.md` | คู่มือนี้ | — |

ในไฟล์ผลทดสอบมีการอ้างถึง log หรือรูปที่ไม่ได้อยู่ใน repo (ดูหัวข้อ 12) และ IP ถูกแทนด้วย `<JETSON_LAN_IP>`, `<JETSON_TAILSCALE_IP>`

---

## 11. `legacy/` : โค้ดรุ่นเก่า

**มีไว้ทำไม** เก็บประวัติการพัฒนาไว้ให้เห็นว่าเปลี่ยนจากอะไร และเพราะอะไร ไม่ได้ใช้ในระบบปัจจุบันและไม่ได้ดูแลต่อ

| โฟลเดอร์ | รุ่น | เดิมเป็นอะไร |
|---|---|---|
| `esp32_alert_node/` | v1 | ESP32 คุมไฟเตือนและ buzzer หน้างาน (ตัดออกจากขอบเขต ให้ Dashboard แจ้งเตือนแทน) |
| `jetson_v2/` | v1–v2 | ตัวแจ้งเตือนบน Jetson และ recorder รุ่นแรก |
| `docker_v2/` | v2 | Docker stack รุ่นก่อน |
| `dashboard_v2/` | v2 | Dashboard หน้าเดียวที่รับภาพ JPEG ทาง MQTT |
| `cira_v2_python/` | v2 | โค้ดตอนที่ให้ CiRA ตรวจจับเอง |

---

## 12. สิ่งที่ไม่อยู่ใน repo และอยู่ที่ไหน

| สิ่งที่ขาด | ทำไมไม่ใส่ | อยู่ที่ไหน / ทำอย่างไร |
|---|---|---|
| รหัสกล้อง | ความลับ | `~/safety/.cam.env` บน Jetson (สร้างจาก `.cam.env.example`, `chmod 600`) |
| PIN ลบเหตุการณ์ | ความลับ | `dashboard/.env` บน Jetson (สร้างจาก `dashboard/.env.example`) |
| ไฟล์โมเดล PPE (`.pt`, `.onnx`) | ใหญ่ | ผลเทรนจาก Colab; วาง ONNX ไว้ที่ `perception/models/yolov8n_ppe3_416/` |
| โมเดลตรวจคน COCO (`yolov8n_coco_320x192.onnx`, `labels_coco.txt`) | ใหญ่ / ไฟล์มาตรฐาน | วางไว้ที่ `perception/models/` ตามที่ `perception/test/config_infer_cam_person_320.txt` อ้างถึง |
| TensorRT `.engine` | ต้อง build บนเครื่องที่ใช้ | DeepStream build ให้เองตอนรันครั้งแรกบน Jetson |
| DeepStream-Yolo | เป็น repo ของคนอื่น | clone ไว้ที่ `perception/DeepStream-Yolo` บน Jetson แล้ว build (ดู `perception/README.md`) |
| log ดิบ, CSV, ภาพหน้าจอของการทดสอบ | ใหญ่ และบางภาพมีคน | โฟลเดอร์ `05_test_results/` ในโฟลเดอร์ทำงานเดิม |
| รายงานฉบับสมบูรณ์ (.docx) | มีรูปคน | `06_final_report/` ในโฟลเดอร์ทำงานเดิม |
| ลิงก์ `~/ds-start`, `~/ds-stop`, `~/cira-up` | เป็น symlink ในเครื่อง | สร้างตาม `tools/README.md` |

---

## 13. อยากทำอะไร ไปที่ไหน

| อยากทำ | เปิดที่ |
|---|---|
| ลองระบบบน PC โดยไม่มีกล้อง | `dashboard/docker-compose.dev.yml` + `tools/simulate_v3.py` |
| แก้หน้าตาหรือข้อความบนหน้าเว็บ | `dashboard/web/js/pages/<หน้า>.js`, `dashboard/web/css/app.css`, `dashboard/web/js/labels.js` |
| แก้ API หรือวิธีเก็บข้อมูล | `dashboard/recorder/` |
| ปรับเกณฑ์ความมั่นใจของโมเดลหมวก/เสื้อ (ตอนนี้ 0.40 / 0.35) | `perception/models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_hv.txt` |
| ปรับเกณฑ์ความมั่นใจของตัวตรวจคน (ตอนนี้ 0.35) | `perception/test/config_infer_cam_person_320.txt` |
| ปรับเกณฑ์ที่ใช้ตัดสินว่าจะแจ้งเตือน หรือ cooldown | `decision/src/cira_node_decide.js` และ node เดียวกันใน `decision/safety_decision_v1.npj` |
| ปรับเวลาที่ต้องผิดกฎต่อเนื่องก่อนนับ หรือโหมดของโซน | `perception/app/violations.py` (หรือ argument `--vest-hold`, `--zone-mode`) |
| เปลี่ยนชื่อหรือ ID ของกล้องที่แสดง | argument `--camera-name`, `--camera-id` ของ `perception/app/person_count_app.py` |
| เพิ่มหรือเปลี่ยน topic / ฟิลด์ MQTT | `docs/mqtt_spec.md` ก่อน แล้วแก้ `perception/`, `decision/`, `dashboard/` ให้ตรงกัน |
| เปลี่ยนโมเดล | เทรนตาม `training/` → แปลงด้วย `perception/export/` → ใส่ config ใน `perception/models/` |
| ภาพสดต่อไม่ติดเพราะ IP เปลี่ยน | `webrtcAdditionalHosts` ใน `dashboard/mediamtx/mediamtx.yml` |
| ตั้งให้ระบบเปิดเองหลังบูต | `tools/safety-autostart.service`, `tools/safety-boot.sh`, `~/safety/boot.conf` |
| ทดสอบความเสถียร 24 ชม. | `tools/soak3_up.sh` และไฟล์ `soak_*` |
| ดูว่าเคยทดสอบอะไร ได้ผลเท่าไร | `docs/test-results/` |

---

## 14. กติกาสั้น ๆ ที่ทุกคนควรรู้

1. ห้าม commit `.cam.env`, `.env`, ไฟล์โมเดล และฐานข้อมูล (`.gitignore` กันไว้ให้แล้ว แต่ให้ตรวจ `git status` ก่อน commit ทุกครั้ง)
2. ชื่อ topic และฟิลด์ MQTT ต้องตรงกับ `docs/mqtt_spec.md` ถ้าจะเปลี่ยน ให้ตกลงกันและแก้ spec ก่อน
3. แก้โค้ดบน PC ก่อน แล้วค่อยคัดลอกไป Jetson อย่าแก้บน Jetson ตรง ๆ ไม่อย่างนั้นสองที่จะไม่ตรงกัน
4. โค้ดที่รันตรงบน Jetson ต้องเป็น Python 3.6 ส่วนโค้ดใน container ของ recorder เป็น Python 3.11
5. แก้แล้วให้รัน test ของส่วนนั้นให้ผ่านก่อน commit: `perception/app` → `python3 -m unittest`, `dashboard/recorder` → `python3 -m unittest test_store`, `decision/tests` → `node test_decide_es5.js`
