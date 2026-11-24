# v7.3 (2026-10-28) Recent Alerts เห็น 4 รายการ ให้การ์ด PPE อยู่ในจอ (ไฟล์เดียว: app.css)

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28). เปลี่ยนไฟล์เดียว `web/css/app.css` (ไม่แตะ recorder/compose/DeepStream). ต่อจาก v7.2.

สรุป (จาก `v7_3_alerts4/CHANGES.md`):
- Recent Alerts เห็น 4 รายการ (เลื่อนเมาส์ดูได้ถึง 20) เพื่อให้การ์ด "PPE Worn · People Now" อยู่ในจอ ไม่ต้องเลื่อน (เหลือที่ว่างใต้การ์ดมากขึ้น: 1906×917 ~90 px, 1920×1080 ~182 px, 1366×768 ~62 px).

ไฟล์ที่เปลี่ยน (1 ไฟล์):

| ไฟล์ | md5 (v7.3) |
|---|---|
| `web/css/app.css` | `3e477dd88159aea69da6e03861015188` |

ตรวจหลังติดตั้ง: `/` 200 · css เสิร์ฟมี "v7.3".

วิธีย้อนกลับเป็น v7.2:
- สำรองอยู่ที่ `web/css/app.css.bak-20261028_082154` (PC และ Jetson).
- คืนไฟล์ (PC → scp ขึ้น Jetson ตำแหน่งเดิม) → `docker restart dashboard` (ห้าม restart อย่างอื่น). md5 กลับเป็น v7.2 (`46031f90`).

---

# v7.2 (2026-10-28) การ์ด PPE Worn·People Now + ตัวนับ ppe_* ใน DeepStream

ติดตั้งแล้วบน Jetson (2026-10-28). สองส่วน: A = หน้าเว็บ 3 ไฟล์ (docker restart dashboard), B = DeepStream app 3 ไฟล์ (restart app ตรวจจับ). ต่อจาก v7 (ข้าม v7.1). ไม่แตะ recorder/compose/CiRA/mediamtx/mosquitto.

สรุป (จาก `v7_2_ppe_card/CHANGES.md`):
- A: Today's Detection Summary กลับเป็นแบบ v6.6 (วงซ้าย + รายการขวา, "Violations today"); เพิ่มการ์ด "PPE Worn · People Now" แทน Event Log (Event Log ยังดูที่หน้า Events). วง PPE อ่าน `ppe_*` จาก DeepStream = Helmet+vest / Helmet only / Vest only / No PPE / Checking. Settings เป็นอังกฤษ.
- B: `status_mqtt.py` เพิ่มตัวนับใน `cam01/status`: `ppe_both`, `ppe_helmet_only`, `ppe_vest_only`, `ppe_none`, `ppe_unknown`. ต้อง restart app ตรวจจับให้มีผล.

ไฟล์ที่เปลี่ยน + md5 ใหม่:

| ส่วน | ไฟล์ | md5 (v7.2) |
|---|---|---|
| A | `web/css/app.css` | `46031f9099fbfb123b4ebae29e720adc` |
| A | `web/js/pages/dashboard.js` | `7bd50d1dfa6ca2c0d1532c85b3935a8e` |
| A | `web/js/pages/settings.js` | `e43c8482f5a5bc719b4f3d99753a2d16` |
| B | `perception/app/person_count_app.py` | `65b7c18842ef990a13ade6ab7d0279f4` |
| B | `perception/app/status_mqtt.py` | `47b04341f24234b4c21bb29d6ed57891` |
| B | `perception/app/test_status_mqtt.py` | `e0c2c1674dd449429a7c7497e160830b` |

ตรวจหลังติดตั้ง: A `/` 200. B `test_status_mqtt.py` 8/8 ผ่าน; `mosquitto_sub -t factory/safety/cam01/status -C 1` มี `ppe_both/ppe_helmet_only/ppe_vest_only/ppe_none/ppe_unknown`; app online, camera_connected true.

วิธีย้อนกลับ (สำรอง TS 20261028_061440, PC และ Jetson):
- ส่วน A: คืน `web.bak-20261028_061440` ทั้งโฟลเดอร์ (PC → scp ขึ้น Jetson) → `docker restart dashboard`. md5 กลับเป็น v7 (app.css `06e32c95`, dashboard.js `1d032698`, settings.js `bea911a9`).
- ส่วน B: คืน `perception/app/{person_count_app.py,status_mqtt.py,test_status_mqtt.py}.bak-20261028_061440` (PC → scp ขึ้น Jetson) → บน Jetson `./ds-stop && ./ds-start` (default `--events off` = arg เดิม). md5 กลับเป็น `810ad1d5/adf3bdca/6db2e3de`.

---

# v7 (2026-10-28) หน้า Dashboard เป็นภาษาอังกฤษ

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28; รอบเดียวกับ v6.6). เปลี่ยนเฉพาะหน้าเว็บ 13 ไฟล์ (ไม่แตะ recorder/compose/settings.js/config.js/css). ต่อจาก v6.6.

สรุป (จาก `v7_english/CHANGES.md`):
- ทุกหน้าเป็นอังกฤษ: Overview / Live View / Events / Reports + เมนูซ้าย + แถบบน + หน้าต่างรายละเอียด/ลบ/CSV + ข้อความสถานะภาพสด + ชื่อประเภท/ระดับ/สถานะ.
- เนื้อหาหน้า Settings ยังเป็นไทย (ไม่แก้ settings.js) แต่เมนู "Settings" + ชื่อประเภทเหตุการณ์ (labels.js) เป็นอังกฤษ.
- ข้อความผิดพลาด PIN จาก recorder แปลงเป็นอังกฤษที่หน้าเว็บ (Wrong PIN / Too many wrong PINs / Delete is disabled) — ไม่แก้ recorder. webrtc.js แก้เฉพาะข้อความ statusText 4 บรรทัด.

ไฟล์ที่เปลี่ยน (13 ไฟล์) + md5 ใหม่:

| ไฟล์ | md5 (v7) |
|---|---|
| `web/index.html` | `b7fdbd1f9ac857ecedb506cfd863e4d8` |
| `web/js/api.js` | `db6d6e1a235919ac0d178bb2a2924ba8` |
| `web/js/app.js` | `dced29700c2edaeb3ec374e115eb360f` |
| `web/js/dialogs.js` | `751c415e4b3814ff8f38b742fabed837` |
| `web/js/labels.js` | `8301e48e5f02e8c9feff80419880879f` |
| `web/js/mqtt-client.js` | `219d28fe55e06954b469d1a16b797a0c` |
| `web/js/ui.js` | `47ae540ee891c4ad833b8b6695252840` |
| `web/js/webrtc.js` | `31cac6afbe95d4e0df1efb42485dc95e` |
| `web/js/pages/dashboard.js` | `1d0326982b844e81e32e6db5b0aff236` |
| `web/js/pages/events.js` | `26fc2b54d78b3f320fc0253e3b659ece` |
| `web/js/pages/live.js` | `69e704dfb5ce7239a38d7a1d674ee3fc` |
| `web/js/pages/report.js` | `c02862b4dfe7f5675ac28e79032ca22d` |
| `web/img/no-snapshot.svg` | `f60908baa9f42a427df39d3a01194432` |

หมายเหตุ svg: ไม่ใช้ไฟล์ svg ในชุด v7 (มี metadata C2PA, md5 `d17ce7ac`) — สร้างจากไฟล์เดิม `9c926fec` โดยแทน `>ไม่มีภาพ</text>` → `>No image</text>` (UTF-8, LF) → ได้ `f60908ba`.

ตรวจหลังติดตั้ง: `/` 200 · หน้ามีคำว่า "Overview".

วิธีย้อนกลับเป็น v6.6: สำรอง `web/` ทั้งโฟลเดอร์อยู่ที่ `web.bak-20261028_055548` (PC และ Jetson). คืนทั้งโฟลเดอร์ (PC → scp ขึ้น Jetson) → `docker restart dashboard`.

---

# v6.6 (2026-10-28) ตัวหนังสือใหญ่ขึ้น ~12–15% บนจอคอม (ไฟล์เดียว: app.css)

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28; รอบเดียวกับ v7). เปลี่ยนไฟล์เดียว `web/css/app.css` (layout 80% เท่า v6.5). ต่อจาก v6.5.

สรุป (จาก `v6_delete_csv_proposal/CHANGES.md`):
- ตัวหนังสือใหญ่ขึ้น ~12–15% บนจอคอม: เมนู, หัวการ์ด, KPI, ชื่อกล้อง, แจ้งเตือน, โดนัท, ตาราง, ฟอร์ม; KPI สูง 112 px (เดิม 100).

ไฟล์ที่เปลี่ยน (1 ไฟล์):

| ไฟล์ | md5 (v6.6) |
|---|---|
| `web/css/app.css` | `06e32c95e172499fafd68be3d921081c` |

ตรวจหลังติดตั้ง: css เสิร์ฟมี "v6.6".

วิธีย้อนกลับเป็น v6.5: สำรองอยู่ที่ `web/css/app.css.bak-20261028_055548` (PC และ Jetson). คืนไฟล์ → `docker restart dashboard`. md5 กลับเป็น v6.5 (`2149a72a`).

---

# v6.5 (2026-10-28) ย่อทั้งหน้า 80% บนจอคอม (ไฟล์เดียว: app.css)

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28). เปลี่ยนไฟล์เดียว `web/css/app.css` (ไม่แตะ recorder/compose). ต่อจาก v6.4.

สรุป (จาก `v6_delete_csv_proposal/CHANGES.md`):
- ทั้งหน้าแสดงที่ 80% บนจอคอม (กว้าง ≥1280 และสูง ≥700) เหมือนกด zoom out แต่ตัวหนังสือใหญ่กว่า 67%; ปรับได้ที่ตัวแปร `--ui-zoom` บนสุดของบล็อก v6.5 (1 = ขนาดเดิม).
- ชดเชยความสูง (`100vh / zoom`) ให้เต็มหน้าต่างพอดี; มือถือ/จอเล็กไม่เปลี่ยน.

ไฟล์ที่เปลี่ยน (1 ไฟล์):

| ไฟล์ | md5 (v6.5) |
|---|---|
| `web/css/app.css` | `2149a72a22758ba5a7c2867135a1b5dd` |

ตรวจหลังติดตั้ง: `/` 200 · css เสิร์ฟมี "v6.5".

วิธีย้อนกลับเป็น v6.4:
- สำรองอยู่ที่ `web/css/app.css.bak-20261028_054007` (PC และ Jetson).
- คืนไฟล์ (PC → scp ขึ้น Jetson ตำแหน่งเดิม) → `docker restart dashboard` (ห้าม restart อย่างอื่น). md5 กลับเป็น v6.4 (`de023c9b`).

---

# v6.4 (2026-10-28) ภาพสด: คลิกช่องเพื่อซูม 1 กล้อง + จัดคอลัมน์หน้าภาพรวม

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28). เปลี่ยน 2 ไฟล์ เฉพาะหน้าเว็บ (ไม่แตะ recorder/compose). ต่อจาก v6.3.

สรุป (จาก `v6_delete_csv_proposal/CHANGES.md`):
- ภาพสด: คลิกช่องกล้องในโหมด 2/4/32 ช่อง → เปิดเป็น 1 ช่องของกล้องนั้น + ปุ่ม "↩ กลับ <โหมดเดิม>"; คลิกช่องว่าง/ปุ่มบนภาพไม่ทำอะไร; เมาส์บนกล้องเป็นรูปแว่นขยาย.
- ภาพรวม: คอลัมน์ซ้าย (KPI 5 ช่อง + กล้อง) กว้างเท่าภาพกล้องพอดี; คอลัมน์ขวา (แจ้งเตือน/สรุป/บันทึก) ขยายกินที่เหลือ (ขั้นต่ำ 360 px).

ไฟล์ที่เปลี่ยน (2 ไฟล์) + md5 ใหม่ (dashboard.js คง `cae6918a`):

| ไฟล์ | md5 (v6.4) |
|---|---|
| `web/css/app.css` | `de023c9b5271a6b236d898789ab885e2` |
| `web/js/pages/live.js` | `6c3f810d7d2b06615b1f31aaae0f4d97` |

ตรวจหลังติดตั้ง: `/` 200 · css เสิร์ฟมี "v6.4".

วิธีย้อนกลับเป็น v6.3:
- สำรองอยู่ที่ `web/css/app.css.bak-20261028_052640`, `web/js/pages/live.js.bak-20261028_052640` (PC และ Jetson).
- คืนไฟล์ (PC → scp ขึ้น Jetson ตำแหน่งเดิม) → `docker restart dashboard` (ห้าม restart อย่างอื่น). md5 กลับเป็น v6.3 (app.css `43e85648`, live.js `408483d8`).

---

# v6.3 (2026-10-28) หน้าภาพรวม: สลับกล้องในการ์ดภาพสด

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28). เปลี่ยน 2 ไฟล์ เฉพาะหน้าเว็บ (ไม่แตะ recorder/compose). ต่อจาก v6.2.

สรุป (จาก `v6_delete_csv_proposal/CHANGES.md`):
- หน้าภาพรวม: กล้อง 1 ตัวแทนการ์ด "ภาพสด" (หัว = ชื่อกล้อง + ตำแหน่ง 1/N + LIVE); ปุ่ม ‹ › จาง ๆ สองข้างภาพ (+ ลูกศรซ้าย/ขวาบนคีย์บอร์ด) เลื่อนดูกล้องอื่นแบบวน; จำกล้องล่าสุดใน localStorage `safety.v6.dashcam`; มีกล้องเดียว = ปุ่มจางมาก กดไม่ได้.
- โดนัท: ซ่อน "มองเห็นไม่ชัด" ถ้าไม่มีเหตุการณ์ประเภทนั้น.

ไฟล์ที่เปลี่ยน (2 ไฟล์) + md5 ใหม่:

| ไฟล์ | md5 (v6.3) |
|---|---|
| `web/css/app.css` | `43e85648b5e5260f667d0495e0e0e389` |
| `web/js/pages/dashboard.js` | `cae6918acfb02671973103445a59f945` |

ตรวจหลังติดตั้ง: `/` 200 · css เสิร์ฟมี "v6.3".

วิธีย้อนกลับเป็น v6.2:
- สำรองอยู่ที่ `web/css/app.css.bak-20261028_051110`, `web/js/pages/dashboard.js.bak-20261028_051110` (PC และ Jetson).
- คืนไฟล์ (PC → scp ขึ้น Jetson ตำแหน่งเดิม) → `docker restart dashboard` (ห้าม restart อย่างอื่น). md5 กลับเป็น v6.2 (app.css `e1a065b6`, dashboard.js `3fdda082`).

---

# v6.2 (2026-10-28) ลบเหตุการณ์ด้วย PIN + CSV เลือกช่วงวัน + กรอบภาพสด 16:9

ติดตั้งแล้วบน Jetson (docker-compose up -d --build recorder + docker restart dashboard, 2026-10-28). ต่อจาก v5.

สรุป (จาก `v6_delete_csv_proposal/CHANGES.md`):
- หน้าเหตุการณ์: ปุ่ม 'ดาวน์โหลด CSV' เลือกวันเดียว/ทั้งเดือน/ช่วงวัน/ทั้งหมด (ชื่อไฟล์บอกช่วงวัน เช่น `safety_events_2026-10-01_2026-10-31.csv`).
- ลบเหตุการณ์ 3 แบบ (ต้องใส่ PIN): ทีละรายการ / ติ๊กหลายรายการ / ตามช่วงวัน (แสดงจำนวนก่อนยืนยัน). ลบทั้งแถว DB + ไฟล์ภาพ (ภาพที่คู่ nh/nv อื่นยังใช้จะไม่ถูกลบ). ใส่ PIN ผิด 5 ครั้งล็อก 5 นาที; จำ PIN ในเว็บ 10 นาที (ไม่เก็บลงเครื่อง). recorder log ทุกการลบ (จำนวน + IP).
- PIN เก็บใน `.env` บน Jetson เท่านั้น (`DELETE_PIN`, chmod 600). ไม่มี PIN = ปุ่มลบไม่แสดง (`/api/health` → `delete_enabled:false`).
- v6.1/v6.2: กรอบภาพสดพอดี 16:9 ไม่มีแถบว่าง/ไม่ครอป; 2/4/32 ช่องเรียงชิดกันกลางจอ.
- backend: recorder เพิ่ม `/api/events/delete`, `/api/export.csv`; unittest 11 ข้อผ่าน (รวม DeleteTest 3 ข้อ + กัน path traversal).

ไฟล์ที่เปลี่ยน (12 ไฟล์; `web/js/dialogs.js` = ไฟล์ใหม่) + md5 ใหม่:

| ไฟล์ | md5 ใหม่ |
|---|---|
| `web/css/app.css` | `e1a065b6a9d50c706b8a8049aa386d48` |
| `web/js/app.js` | `d8441cb6c9447b7f927f9af1ed05be76` |
| `web/js/api.js` | `6f42ad83517abbd595c4d6e9a975b615` |
| `web/js/ui.js` | `333322f20ad6751baacb83d04b154845` |
| `web/js/dialogs.js` (ใหม่) | `4bca296dd990d23cb4581b07c730624c` |
| `web/js/pages/dashboard.js` | `3fdda0821f2b2b5f3df627f9af59cac4` |
| `web/js/pages/events.js` | `b3ddc33fbbd14501bafa11663255ba6e` |
| `web/js/pages/live.js` | `408483d811948767384f5dccb629aefb` |
| `recorder/app.py` | `f7ef390e47f808ea6df93924eccf93cf` |
| `recorder/store.py` | `5bb2e2aff3b3bde38dc9104771560351` |
| `recorder/test_store.py` | `337ced464b792290f29ebe157f919bfc` |
| `docker-compose.yml` | `4988a5157a6b8f4f5d12af9f3b6606c2` |

หมายเหตุ compose: `docker-compose.yml` ต่างจาก md5 ในข้อเสนอเดิม (ae873e0d) เพราะ docker-compose บน Jetson = 1.17.1 ไม่รองรับ `${DELETE_PIN:-}` → แก้เป็น `${DELETE_PIN}` (อ่านจาก .env; ไม่มี .env = ว่าง = delete disabled).

ตรวจหลังติดตั้ง: `/` 200 · css เสิร์ฟมี "v6.2" · `/api/health` `delete_enabled:true` · `POST /api/events/delete` ไม่มี PIN = 401 · `GET /api/export.csv?from=..&to=..` = 200 + Content-Disposition ชื่อไฟล์ตามช่วงวัน · recorder log ไม่มี error.

วิธีย้อนกลับเป็น v5:
- สำรองอยู่ที่ `.bak-20261028_045211` (PC และ Jetson): `web/`, `recorder/`, `docker-compose.yml`. DB สำรอง: `/data/safety_backup_20261028_045211.db` (ในคอนเทนเนอร์ recorder).
- คืนไฟล์จาก `.bak-20261028_045211` ทับ (PC → scp ขึ้น Jetson ตำแหน่งเดิม), แล้วบน Jetson: `docker-compose up -d --build recorder && docker restart dashboard` (ห้าม restart อย่างอื่น).
- ยืนยัน md5 กลับเป็นชุด v5.

---

# v5 (2026-10-28) fit-to-screen + แถบขวาใหม่

ติดตั้งแล้วบน Jetson (docker restart dashboard, 2026-10-28). เปลี่ยนเลย์เอาต์หน้า Dashboard ให้พอดีหน้าจอ ไม่ต้องเลื่อน และปรับแถบขวาใหม่ตามภาพ mock-up (rev 4).

สรุปการเปลี่ยน (จาก `v5_fit_proposal/CHANGES.md`):
- เลย์เอาต์ 2 คอลัมน์: ซ้าย = KPI + ภาพสด (1 กล้อง = ภาพเดียวเต็ม), ขวาชิดใต้แถบบน.
- แถบขวา: แจ้งเตือนล่าสุด (เห็น 5 รายการ, เลื่อนเมาส์ดูได้ถึง 20 รายการที่มี snapshot) / สรุปวันนี้แบบโดนัท + บรรทัด CiRA / ตารางบันทึกเหตุการณ์ 5 แถว.
- Responsive: จอสูง ≤900px ซ่อนตารางบันทึกเหตุการณ์ + ย่อโดนัท; จอกว้าง ≤1024px เลื่อนแบบเดิม.
- `app.js`: โหลดแจ้งเตือนเริ่มต้น 50 รายการ (เดิม 20) เพื่อให้มีรายการที่มีภาพครบ 20.
- rev 4: ตกแต่งตาม mock-up (ไอคอนหัวการ์ด, การ์ดไล่เฉด, ไฟสถานะไม่แสดงตัวเลข, กรอบภาพสดมุมมน, แถวแจ้งเตือนแบน, โดนัทวงหนา).

ไฟล์ที่เปลี่ยน (4 ไฟล์) + md5 (เต็ม):

| ไฟล์ | base (v4) md5 | v5 md5 |
|---|---|---|
| `web/css/app.css` | `bdde26a8d28b0d44b9bcc86efd31cda2` | `283d1fe70a798ba71b7eb115957c44c0` |
| `web/js/pages/dashboard.js` | `2ebd97ab386722868464aa3ba488f356` | `1592b65ad9f4905ef96bc5e9d1da3945` |
| `web/js/pages/live.js` | `bb05b7658b65d534189f8f91e4c32b00` | `ca2cc95cca0b71b2ffa4f8d8b6dcf53a` |
| `web/js/app.js` | `ed025d4ec7f96167dc838bbe44aa9d86` | `e7e487dfc55c4020a1c31eb5ede08d33` |

ตรวจหลังติดตั้ง: `curl http://localhost:8080/` = 200, `curl "http://localhost:8080/api/events?limit=50"` = 200, `curl http://localhost:8080/css/app.css | grep "v5 rev 4"` เจอ.

วิธีย้อนกลับเป็น v4:
- สำรอง v4 ทั้งโฟลเดอร์ `web/` อยู่ที่ `dashboard/web.bak-20261028_041807` (บน PC).
- บน PC: `cp web.bak-20261028_041807/css/app.css web/css/app.css` (และอีก 3 ไฟล์: `js/pages/dashboard.js`, `js/pages/live.js`, `js/app.js`).
- scp 4 ไฟล์ขึ้น `jetson:~/safety/dashboard/web/` ตำแหน่งเดิม → `docker restart dashboard` (ห้าม restart อย่างอื่น).
- ยืนยัน md5 บน Jetson กลับเป็นชุด base (v4) ข้างบน.

---

# Dashboard live-player changes (2026-10-24)

แก้เฉพาะ **ตัวเล่นภาพสด** 2 เรื่อง: (1) ฟื้นตัวเร็วเมื่อภาพค้าง/หลุด (2) ป้ายคุณภาพภาพสด.
ไม่แตะส่วนแจ้งเตือน / MQTT / รายงาน / ตั้งค่า / ตัวเลขสรุป / หน้าเหตุการณ์.
ใช้ WebRTC `getStats()` ของเบราว์เซอร์อย่างเดียว ไม่เพิ่ม library ภายนอก.

## ไฟล์ที่แก้ (3 ไฟล์)

### 1. `web/js/webrtc.js` — คลาส `WhepPlayer` (ตัวเล่น)
เพิ่มการฟื้นตัว + สถิติ โดยคง public API เดิม (`start/stop/setStreamPath/onstate/state`). ของใหม่: `onstats`, `stats`, `live`, `statusText`, `quality`, getter `hasFrame`.
- **ตรวจภาพค้าง:** `_sampleStats()` อ่าน `getStats()` ทุก 1 วิ. ถ้า `connectionState==="connected"` แต่ `framesDecoded` ไม่เพิ่มเกิน `STALL_MS` → ถือว่าภาพค้าง → `_reconnect()` ทันที (ไม่รอ `disconnected`).
- **grace สั้นลง:** `DISCONNECT_GRACE_MS` 5000 → **2000** (เฉพาะสถานะ `disconnected` ที่มักฟื้นเอง).
- **reconnect เฉพาะ** `failed`/`closed` หรือภาพค้างตามเกณฑ์. `disconnected` รอ grace ก่อน.
- **backoff:** `_fail()` หน่วงต่อใหม่ตาม `BACKOFF_S` = `[1,2,5,10]` วิ (ค้างที่ 10). รีเซ็ตเป็น 0 เมื่อ decode เฟรมได้.
- **ปิด peer/เซสชันเก่าก่อนต่อใหม่เสมอ:** `_teardown()` ทำ WHEP `DELETE` + `pc.close()` (กัน session ค้างฝั่ง mediamtx). มี `_connecting` เป็น single-flight กันต่อซ้อน (ถ้าไม่มีกันนี้ จะยิง request ซ้อนเป็น 2 สาย).
- **คงภาพสุดท้าย:** `_teardown({keepVideo:true})` ตอน reconnect ไม่ล้าง `srcObject` (ฝั่ง UI วาดเฟรมค้างทับอีกชั้น ดูหัวข้อ ui.js).
- **สถิติ (`stats`)** ต่อ 1 วิ: `fps` (`framesPerSecond` หรือ delta เฟรม), `width/height` (`frameWidth/Height`), `bitrateMbps` (delta `bytesReceived`), `latencyMs` (`jitterBufferDelay` เฉลี่ย + `currentRoundTripTime`/2), `packetsLost`, `stalls5min` (นับภาพค้างใน `STALL_WINDOW_MS`), `connectedMs` (ต่อเนื่องตั้งแต่เฟรมแรก).
- **`quality`**: `good` = fps≥25 และไม่ค้างใน 5 นาที; `fair` = fps≥15 หรือค้าง ≤2 ครั้ง; `bad` = ต่ำกว่านั้น.
- **ข้อความบนภาพ (`statusText`)**: `กำลังเชื่อมต่อ…` / `รอภาพแรก…` / `ภาพค้าง — กำลังต่อใหม่` / `เชื่อมต่อไม่ได้ — ลองใหม่ใน N วิ`.

### 2. `web/js/ui.js` — `createLiveTile()` + `liveGrid()`
- **แสดงสถานะ 2 ชั้น:** ปัญหาหนัก (กล้องหลุด/ตรวจจับล่ม/ต่อครั้งแรกยังไม่เคยมีเฟรม) = overlay ทึบคลุมเต็ม. ภาพค้าง/ต่อใหม่หลังเคยมีเฟรมแล้ว = แถบบาง `.tile-status` ด้านล่าง + คงเฟรมค้าง (ไม่จอดำ). ใช้ตัวแปร `everFrame` ต่อ tile.
- **เฟรมค้าง (`grabFrame`)**: ขณะ `playing` คัดลอกเฟรมล่าสุดลง `<canvas class="tile-freeze">` ทุก 1 วิ; ตอนค้าง/ต่อใหม่โชว์ canvas นั้น (เพราะ `pc.close()` ทำให้ track จบ วิดีโอจะดำ).
- **ป้ายคุณภาพ** (`.tile-quality`, มุมขวาบน): กดจุดสีเพื่อ **ซ่อน/แสดง** รายละเอียด, จำค่าใน `localStorage` คีย์ `safety.v3.qbadge` (ครอบ try/catch ผ่าน `lsGet/lsSet`). แสดง: สถานะ ดี/พอใช้/แย่, fps, ความละเอียด, bitrate, หน่วง, สูญหาย, ค้าง(5น.), เวลาต่อเนื่อง.
- **fps ใต้ภาพ** เปลี่ยนเป็น **fps จริงจาก WebRTC** (เดิมใช้ `fps_in` จาก `cam01/status`); fps กล้องย้ายไป tooltip (`title`). ถ้ายังไม่มีค่า WebRTC จะ fallback เป็น fps กล้อง.
- **แท็บถูกซ่อน (`liveGrid` visibility):** ซ่อนเกิน `HIDDEN_DISCONNECT_MS` (30000) → หยุดตัวเล่น (ปล่อย session). กลับมา → ต่อใหม่ทันที. (เดิมหยุดทันทีที่สลับแท็บ).

### 3. `web/css/app.css` — เฉพาะบล็อก `.tile-*` (ส่วนภาพสด)
เพิ่ม `.tile-freeze` (เฟรมค้าง), `.tile-status` (แถบข้อความล่าง), `.tile-quality/.tile-q-toggle/.q-dot/.tile-q-body` (ป้ายคุณภาพ + 3 สี ดี=เขียว พอใช้=ส้ม แย่=แดง). ไม่แตะ CSS ส่วนอื่น.

## ค่าคงที่ที่ปรับได้
| ค่า | ไฟล์ | ปัจจุบัน | ความหมาย |
|---|---|---|---|
| `STALL_MS` | webrtc.js | 3000 | ไม่มีเฟรมใหม่เกินนี้ (ขณะ connected) = ภาพค้าง → ต่อใหม่ |
| `DISCONNECT_GRACE_MS` | webrtc.js | 2000 | รอ `disconnected` ฟื้นเองก่อนยอมแพ้ |
| `BACKOFF_S` | webrtc.js | `[1,2,5,10]` | ลำดับหน่วงต่อใหม่ (วิ), ค้างที่ค่าสุดท้าย |
| `STATS_INTERVAL_MS` | webrtc.js | 1000 | คาบอ่าน getStats |
| `STALL_WINDOW_MS` | webrtc.js | 300000 | หน้าต่างนับ "ค้างใน 5 นาที" |
| `HIDDEN_DISCONNECT_MS` | ui.js | 30000 | ซ่อนแท็บนานเกินนี้จึงตัดการเชื่อมต่อ |
| `QBADGE_LS` | ui.js | `"safety.v3.qbadge"` | คีย์จำสถานะซ่อน/แสดงป้าย |

## วิธีย้อนกลับ
สำรองทั้งโฟลเดอร์ไว้ที่ `dashboard/web.bak-20261024-085855` (บน PC).
```bash
cd ~/safety/dashboard
cp web.bak-20261024-085855/js/webrtc.js web/js/webrtc.js
cp web.bak-20261024-085855/js/ui.js     web/js/ui.js
cp web.bak-20261024-085855/css/app.css  web/css/app.css
docker restart dashboard
```
(บน PC คัดลอกจาก `web.bak-20261024-085855/` ทับ `web/` แล้ว scp 3 ไฟล์กลับ Jetson + `docker restart dashboard`.)
web ถูก bind-mount read-only เข้า nginx → แก้ไฟล์แล้ว `docker restart dashboard` พอ ไม่ต้อง rebuild.

---

# Dashboard live-player changes v4 (2026-10-25)

ต่อจาก v3 — แก้เพิ่ม 4 เรื่องในส่วนภาพสด (ไม่แตะแจ้งเตือน/MQTT/รายงาน/ตั้งค่า/ตัวเลขสรุปอื่น, ไม่เพิ่ม library):

## ไฟล์ที่แก้ (6)
- `web/js/webrtc.js`: เพิ่ม `FIRST_FRAME_MS=8000` — ถ้า connected แต่ไม่ได้ "เฟรมแรก" ใน 8 วิ → ต่อใหม่ (backoff เดิม). เพิ่ม public `lastFrameWall` (เวลาเฟรมล่าสุด, คงข้าม reconnect) ให้ป้าย/ไฟใช้.
- `web/js/ui.js`: ป้ายคุณภาพเมื่อไม่มีเฟรมใหม่ (ขณะไม่ playing ≥3 วิ) → แสดง "ไม่มีภาพ X วิ" + ระดับ "แย่"; tile tick 1 วิ (ป้าย/ไฟเดินต่อแม้ peer ดับ) + รายงานสถานะไฟ "ภาพสด" ผ่าน `ctx.reportLive`.
- `web/js/app.js`: รวมสถานะไฟ "ภาพสด" จากทุก tile (`state.live` + `ctx.reportLive`), เพิ่มใน `overallLights()` + loop renderLights.
- `web/js/pages/dashboard.js`: KPI "การฝ่าฝืนวันนี้" — ถ้าเมื่อวาน < 10 แสดง "+N จากเมื่อวาน" แทน %.
- `web/index.html`: เพิ่มไฟ `data-light="livevideo"` (ชื่อ "ภาพสด") ข้าง Decision.
- `web/css/app.css`: level ไฟ `warn` (เหลือง) + `.q-noframe` (แดง).

## ค่าคงที่ปรับได้ (เพิ่มจาก v3)
| ค่า | ไฟล์ | ปัจจุบัน | ความหมาย |
|---|---|---|---|
| `FIRST_FRAME_MS` | webrtc.js | 8000 | connected แต่ไม่มีเฟรมแรกเกินนี้ → ต่อใหม่ |

ไฟ "ภาพสด": เขียว=เฟรมเดินปกติ, เหลือง=กำลังต่อใหม่/รอภาพแรก, แดง=ไม่มีภาพเกิน 30 วิ.

## วิธีย้อนกลับ
สำรอง `dashboard/web.bak-20261025-190346`. คืนไฟล์ 6 ตัว + scp กลับ Jetson + `docker restart dashboard`.
md5 (v4): webrtc `6ee90de3…`, ui `eaef66fd…`, app `ed025d4e…`, dashboard `2ebd97ab…`, index `952fac61…`, app.css `bdde26a8…`.
