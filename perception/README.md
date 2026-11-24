# perception: แอป DeepStream บน Jetson Nano

ชั้นมองเห็นของระบบ: ดึงภาพจากกล้อง RTSP ตรวจคน หมวก และเสื้อสะท้อนแสง ติดตามคนข้ามเฟรม จับคู่ PPE กับแต่ละคน แล้วส่งผลทาง MQTT (`<cam>/status`, `ds/violation`, `snapshot`) และส่งภาพสดที่วาดกรอบแล้วออกทาง RTSP พอร์ต 8555 ให้ MediaMTX

```
rtspsrc (Tapo stream1 1080p) → nvstreammux 1280×720 → nvinfer #1 (YOLOv8n COCO person 320×192)
  → nvinfer #2 (ppe3 helmet/vest 416×256) → nvtracker → nvdsosd → encoder → RTSP :8555
```

## โครงสร้าง

| ไฟล์ / โฟลเดอร์ | หน้าที่ |
|---|---|
| `app/person_count_app.py` | แอปหลัก (pyds): สร้าง pipeline, วาดผล, ส่ง MQTT, ต่อกล้องใหม่เมื่อหลุด |
| `app/obj_route.py` | แยกว่าวัตถุมาจากโมเดลไหน (COCO person หรือ ppe3) จาก `unique_component_id` |
| `app/person_ids.py` | ให้เลขคนคงที่ระหว่างอยู่ในภาพ แม้ถูกบังชั่วคราว |
| `app/ppe_pretrack.py` | เก็บกรอบหมวก/เสื้อก่อนเข้า nvtracker (tracker ส่งออกเฉพาะคน) |
| `app/ppe_assign.py` | จับคู่หมวก (ช่วงบน 35% ของกรอบคน) และเสื้อ (20–75%) กับคน |
| `app/ppe_smooth.py` | สถานะหมวก/เสื้อของแต่ละคนจากหลายเฟรมล่าสุด (✓ / ✗ / ?) |
| `app/violations.py` | ตัดสิน violation ตามเวลาค้าง (no_helmet 2 วิ, no_vest 4 วิ, restricted_zone 0.5 วิ) ส่งซ้ำทุก 5 วิ, โซนเฝ้าระวัง และ event แบบ fallback เมื่อ CiRA เงียบเกิน 15 วิ |
| `app/status_mqtt.py` | heartbeat `<cam>/status` ทุก 5 วิ (QoS 1, retained, LWT `online:false`) |
| `app/pts_guard.py` | ปรับ PTS ก่อน rtph264pay ไม่ให้ภาพสดค้างเมื่อกล้องรีเซ็ต |
| `app/run_person_app.sh`, `start_person_app.sh`, `stop_person_app.sh` | รัน/หยุดแอปใน tmux `ds` (อ่านรหัสกล้องจาก `~/safety/.cam.env` และปิดบังรหัสใน log) |
| `app/test_*.py` | unit test (Python ล้วน ไม่ต้องมี DeepStream) |
| `test/` | config ของ nvinfer และ tracker ที่แอปใช้ (เช่น `config_infer_cam_person_320.txt`, `tracker_nvdcf_tuned.yml`) และสคริปต์ benchmark/probe กล้อง |
| `models/<ชื่อโมเดล>/` | `config_infer_*.txt`, `labels.txt` (person, helmet, vest), `info.json`, `run_export.py` (ไม่มีไฟล์ weight) |
| `export/` | สคริปต์ export โมเดล Ultralytics เป็น ONNX สำหรับ DeepStream-Yolo |
| `cam_discover.sh` | หา IP ของกล้องเองเมื่อ IP เปลี่ยน (สแกน subnet แล้วยืนยันด้วย RTSP DESCRIBE) |

## สิ่งที่ต้องมีบน Jetson

- JetPack 4.6.1, DeepStream 6.0.1 (`/opt/nvidia/deepstream/deepstream-6.0`), pyds 1.1.1, paho-mqtt (1.x หรือ 2.x)
- โค้ดทั้งหมดต้องรันได้บน Python 3.6 (ห้ามใช้ `:=`, `dataclasses`, `match`)
- clone DeepStream-Yolo ไว้ที่ `~/safety/perception/DeepStream-Yolo` แล้ว build ไลบรารี:
  ```bash
  cd ~/safety/perception/DeepStream-Yolo && git checkout 2894bab
  CUDA_VER=10.2 make -C nvdsinfer_custom_impl_Yolo
  ```
- รหัสกล้องใน `~/safety/.cam.env` (`CAM_IP`, `CAM_USER`, `CAM_PASS`, `chmod 600`) ห้ามพิมพ์หรือ commit ไฟล์นี้

## โมเดล

ไฟล์ weight ไม่อยู่ใน repo ให้วาง ONNX ไว้ใน `models/yolov8n_ppe3_416/` (export จาก `.pt` ด้วย `export/export_ds_yolov8.py` หรือ `models/*/run_export.py`) และใช้ YOLOv8n COCO 320×192 สำหรับตรวจคน TensorRT engine จะถูก build บน Jetson ตอนรันครั้งแรก (build บน PC แล้วคัดลอกมาใช้ไม่ได้) ผลเทรนของโมเดลดูที่ [`../training/`](../training/)

## รัน

```bash
ln -s ~/safety/perception/app/start_person_app.sh ~/ds-start
ln -s ~/safety/perception/app/stop_person_app.sh  ~/ds-stop
~/ds-start                  # สถานะ + ภาพสดเท่านั้น (events off)
~/ds-start --events on      # ส่ง ds/violation, snapshot และ fallback event ด้วย
~/ds-stop
```

- คำสั่ง `python3` และ `deepstream-app` ให้รันแบบ `env -u PYTHONPATH ...` เพราะ ROS ของ CiRA ใส่ path ของ Python 2.7 ไว้
- งานยาว (build engine, ทดสอบ) ให้รันใน tmux `ds`
- อย่าเปลี่ยน `nvpmodel` หรือรัน `jetson_clocks` ถ้ายังจ่ายไฟผ่าน micro-USB

## ทดสอบ

```bash
cd perception/app
python3 -m unittest -v
```
