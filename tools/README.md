# tools: เครื่องมือประกอบ

สคริปต์ส่วนใหญ่ออกแบบให้รันบน Jetson ที่ `~/safety/tools/` (Python 3.6, ใช้ library มาตรฐานเป็นหลัก)

## จำลองข้อมูล

| ไฟล์ | หน้าที่ |
|---|---|
| `simulate_v3.py` | จำลอง DeepStream + CiRA ส่งข้อมูลครบทุก topic ตาม `docs/mqtt_spec.md` เพื่อพัฒนา Dashboard โดยไม่ต้องมีกล้อง (`--cams 2`, `--cira-down`, `--camera-down`, `--emit ds`, `--once`) |
| `simulate_events.py` | ตัวจำลองรุ่น v2 (ส่งภาพ JPEG + event) |
| `mosquitto.conf` | config broker สำหรับทดสอบในเครื่อง: `mosquitto -c mosquitto.conf -v` |

## Autostart บน Jetson

| ไฟล์ | หน้าที่ |
|---|---|
| `safety-autostart.service` | systemd service: รัน `safety-boot.sh` หลัง docker และ network พร้อม |
| `safety-boot.sh` | รอ broker → เริ่มแอป DeepStream (`~/ds-start`) → เปิด CiRA (`~/cira-up`); log ที่ `~/safety/logs/` |
| `boot.conf.example` | คัดลอกเป็น `~/safety/boot.conf` แล้วตั้ง `BOOT_EVENTS=on` หรือ `off` (ส่ง event ตั้งแต่บูตหรือไม่) |
| `cira-start.sh` | เปิด Xvfb `:99` ใหม่ + CiRA CORE ที่ `nice 19` ใน tmux `cira-gui` |
| `cira-autoload.sh` | เปิดโปรเจกต์และกด Run ใน CiRA แบบ headless (xdotool) แล้วตรวจว่ามี heartbeat |
| `cira-up.sh` | `cira-start.sh` แล้วตามด้วย `cira-autoload.sh` |
| `npj_tool.py` | อ่านและแก้ไฟล์ flow `.npj` ของ CiRA จาก terminal |

ลิงก์ที่สคริปต์เรียกใช้:

```bash
ln -s ~/safety/perception/app/start_person_app.sh ~/ds-start
ln -s ~/safety/perception/app/stop_person_app.sh  ~/ds-stop
ln -s ~/safety/tools/cira-up.sh ~/cira-up
sudo cp ~/safety/tools/safety-autostart.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable safety-autostart.service
```

## Soak test 24 ชั่วโมง

| ไฟล์ | หน้าที่ |
|---|---|
| `soak3_up.sh` | เปิดตัวเก็บข้อมูล soak รอบ 3–4 ใน tmux `soak3` |
| `soak_logger_v3.sh`, `soak_sample_v3.py` | บันทึก `soak.csv` ทุก 60 วิ (fps, CPU/GPU, RAM, อุณหภูมิ, พลังงาน INA3221, สถานะภาพสด ฯลฯ) |
| `soak_mqtt.py` | บันทึก event, `cira/status` และ latency จาก `ds/violation` ถึง event |
| `soak_slow_v3.sh` | ทุก 10 นาที: ความสว่างของภาพ และตัวนับของ MediaMTX |
| `soak_end_v4.sh` | ปิดตัวเก็บข้อมูลและสลับแอปเป็น events off เมื่อครบเวลา |
| `soak_watch_v2.py`, `soak_watch.sh` | เฝ้าดูระหว่าง soak และเขียนคำเตือน |
| `soak_logger.sh`, `soak_logger_v2.sh`, `soak_sample.py`, `soak_slow.sh`, `soak2_up.sh` | รุ่นก่อนหน้า (soak รอบ 1–2) |
| `light.sh` | บันทึกเวลาปิด/เปิดไฟในห้องระหว่าง soak |

## วัดภาพสด

| ไฟล์ | หน้าที่ |
|---|---|
| `live_monitor/live_monitor.js` | เปิด WebRTC (WHEP) ผ่าน nginx แบบเดียวกับ Dashboard แล้วบันทึก connected, fps, ภาพค้าง, การต่อใหม่ ทุกช่วงเวลา |
| `live_monitor/whep_monitor.html` | หน้าเว็บที่ `live_monitor.js` ใช้ |
| `live_monitor/pts_check.py` | นับ PTS ที่ถอยหลังใน packet dump ของ ffprobe |
