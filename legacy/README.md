# legacy: โค้ดรุ่น v1 และ v2 (เลิกใช้แล้ว)

เก็บไว้เพื่อดูประวัติการพัฒนาเท่านั้น ไม่ได้ดูแลต่อ และไม่ได้ทดสอบกับระบบปัจจุบัน

| โฟลเดอร์ | รุ่น | เนื้อหา |
|---|---|---|
| `esp32_alert_node/` | v1 | firmware ESP32 รับ event ทาง MQTT แล้วสั่งไฟเตือนและ buzzer (ต้องใส่ Wi-Fi และ MQTT host เอง) |
| `jetson_v2/` | v1–v2 | `jetson_alert.py` (v1), `recorder.py` เก็บเหตุการณ์และรูป (v2), service เปิด GUI ผ่าน HDMI |
| `docker_v2/` | v2 | docker-compose ของ mosquitto, recorder และ nginx รุ่น v2 |
| `dashboard_v2/` | v2 | Dashboard หน้าเดียวที่รับภาพ JPEG ทาง MQTT |
| `cira_v2_python/` | v2 | โค้ด Python ฝั่ง CiRA (`ppe_logic.py`, `safety_publisher.py`) และตัวตรวจจับทดสอบบน PC |

## ทำไมเปลี่ยน

- **v1** ใช้ ESP32 ควบคุมไฟและ buzzer หน้างาน ภายหลังตัดออกจากขอบเขต เพื่อเน้นระบบ AI และชั้นตัดสินใจ โดยให้ Dashboard แจ้งเตือนแทน (ไฟสถานะ, รายการเหตุการณ์, เสียง)
- **v2** ให้ CiRA CORE ตรวจจับเอง (YOLOv4-tiny/YOLOv7-tiny แบบ darknet) และส่งภาพ JPEG ประมาณ 5 fps ทาง MQTT
- **v3** (ตัดสินใจ 2026-10-15) แยกการตรวจจับไปที่ DeepStream + TensorRT, ให้ CiRA ทำหน้าที่ตัดสินใจ และส่งภาพสดผ่าน WebRTC ดูเหตุผลใน [`docs/design_v3_low_latency.md`](../docs/design_v3_low_latency.md) และผล benchmark ใน [`docs/test-results/2026-10-15_darknet_bench_jetson/`](../docs/test-results/2026-10-15_darknet_bench_jetson/)
