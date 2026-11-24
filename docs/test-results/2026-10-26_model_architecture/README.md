# รายงานสถาปัตยกรรมโมเดลและชุดข้อมูลที่ใช้จริง (2026-10-26)

สรุปว่าระบบ AI Smart Safety Monitoring ที่รันจริง (ขณะ soak v4) ใช้โมเดลอะไร ตั้งค่าอย่างไร จับคู่ helmet/vest กับคนด้วยวิธีไหน และชุดข้อมูลมาจากไหน — ทุกตัวเลขมีหลักฐาน `[E-xx]`.

## ไฟล์
- `model_architecture_report.docx` — รายงานหลัก (ภาษาไทย, กราฟสี, 11 หัวข้อ + ภาคผนวก)
- `EVIDENCE_INDEX.md` — ดัชนี [E-xx] → ไฟล์/บรรทัด/วิธีตรวจซ้ำ + sha256 ทุกไฟล์
- `evidence/` — สำเนาไฟล์หลักฐาน (คัดลอกตรง ห้ามแก้)
- `report_scripts/` — `gen_figures.py` (สร้างรูป), `build_report.py` (สร้าง docx)
- `figures/` — รูป fig1–fig5 (PNG 150 dpi)

## สร้างใหม่ (reproducible)
```
cd report_scripts
python gen_figures.py      # → figures/
python build_report.py     # → model_architecture_report.docx
```
แก้รายงาน = แก้สคริปต์แล้วรันใหม่ (ห้ามแก้ docx ตรง).

## ข้อสรุปหลัก
- **คน** = YOLOv8n COCO สำเร็จรูป 320×192 FP16 (ไม่เทรนเอง, กรองเหลือ person) — nvinfer #1.
- **helmet/vest** = custom yolov8n_ppe3_416 416×256 FP16 interval=1 (ตัด person ของตัวเอง) — nvinfer #2.
- สองโมเดลตรวจ **เต็มเฟรมคู่ขนาน** (ไม่ใช่ secondary/crop); จับคู่ helmet/vest↔คนด้วยตำแหน่ง (helmet 0–35%, vest 20–75% ของกรอบคน).
- เลือก way A เพราะ person ของ ppe3 เป็น pseudo-label ไม่น่าเชื่อถือ + ชั่วคราว.

## ข้อจำกัดการจัดทำ
- merged/ (7 คลาส) **นับจาก label จริง** = train 4,771 / valid 744 / test 468 ภาพ (ยืนยัน).
- merged3 (3 คลาสที่เทรนจริง) **สร้างซ้ำบน PC ไม่ได้** (ไม่มีโฟลเดอร์เต็ม + ขั้น pseudo-label ต้องใช้ YOLOv8x+GPU; ไม่ pip install โดยไม่ขออนุญาต). ตัวเลข merged3 ในรายงานอ้าง Colab log และกำกับส่วนต่างไว้ในหัวข้อ "ข้อแก้ไข".
- ไม่มี LibreOffice/soffice บน PC → ตรวจ docx ด้วย python-docx + ดูรูปเป็น PNG แยก (ไม่ได้แปลงเป็น PDF).
- เก็บหลักฐาน Jetson แบบอ่านอย่างเดียว (soak v4 กำลังรัน — ไม่ restart/แก้/kill).
