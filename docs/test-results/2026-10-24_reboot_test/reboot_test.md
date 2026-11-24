# Reboot autostart test — 2026-10-24

Jetson รีบูตเอง 08:47 (ผู้ใช้สั่ง). ตรวจอ่านอย่างเดียว ไม่แก้/ไม่ restart/ไม่สั่ง start. ssh ผ่าน Tailscale (<JETSON_TAILSCALE_IP>).

## สรุป: ผ่านทุกข้อ (7/7) — ระบบขึ้นเองครบหลังรีบูต

| # | ตรวจ | ผล | ผ่าน |
|---|---|---|---|
| 1 | เวลาบูต + autostart | boot 08:47:25, `safety-autostart.service` Started **08:50:24** (~3 นาที), ExecStart `safety-boot.sh` exit 0/SUCCESS | ✓ |
| 2 | containers | mosquitto, mediamtx, dashboard, recorder(healthy) — Up ~4 นาที ครบ 4 | ✓ |
| 3 | app ขึ้นเอง | `live_20261024_0847` **--events off**, md5 `f331fc90d4e7ee1886655ef0ad74988e` ✓, fps ~28 | ✓ |
| 4 | mediamtx yml + ICE | yml md5 `37cb911346088a73fd369b4e2977f0d1` ✓; ICE local candidate เฉพาะ <JETSON_TAILSCALE_IP> / <JETSON_LAN_IP> **ไม่มี 172.x** (`webrtcIPsFromInterfaces: no`) | ✓ |
| 5 | CiRA | tmux `cira-gui` มี (created 08:48), process `cira_core_run` PID 8386 (10% CPU), `cira/status` `online:true` last_rx 08:50:18 อายุ ≤ ~8 วิ (<15) | ✓ |
| 6 | ภาพสด 3 นาที | TTFF **1.38 วิ** (≤3), connected 18/18, reconnect **0**, packetsLost 0, keyframe 157/180 วิ ≈1/วิ, fps ~28, freeze 14 (sw-decode) | ✓ |
| 7 | disk / อุณหภูมิ | disk **7.1 GB** free (75%), thermal zone0 58.5°C (zone1–5: 48–54°C) | ✓ |

## รายละเอียด

### 1 autostart timeline
- `uptime -s` = 2026-10-24 08:47:25 (บูต).
- `systemctl status safety-autostart.service`: `active (exited)`, Started **08:50:24 +07**, ExecStart `/home/jetson/safety/tools/safety-boot.sh` exit 0/SUCCESS.
- journal (-b): Starting 08:47:39 → Started 08:50:24 → รวม ~2 นาที 45 วิ ตั้งแต่ service เริ่มจนครบ (จาก power-on ~3 นาที).
- CGroup ของ service ถือ tmux `ds` + `run_person_app.sh live_20261024_0847 --events off` + tegrastats + Xvfb :99 → app ถูก start โดย autostart จริง.

### 2 containers
```
recorder   Up 4 minutes (healthy)
dashboard  Up 4 minutes
mediamtx   Up 4 minutes
mosquitto  Up 4 minutes
```

### 4 ICE
- mediamtx log (UTC; 01:47:39 UTC = 08:47:39 local): `configuration loaded`, `[WebRTC] listener opened on 127.0.0.1:8889 (HTTP), :8189 (ICE/UDP/TCP)`.
- session หลังรีบูต local candidate = `<JETSON_TAILSCALE_IP>` และ `<JETSON_LAN_IP>` เท่านั้น ไม่พบ 172.17/172.18.
- yml: `webrtcIPsFromInterfaces: no`, `webrtcAdditionalHosts: [<JETSON_LAN_IP>, <JETSON_TAILSCALE_IP>]`.

### 5 CiRA
- `cira/status` msg: `{"online":true,"flow":"safety_decision_v1","last_rx":"2026-10-24T08:50:18+07:00","published":1,"received":1,...}`.
- heartbeat มาภายใน 8 วิที่ subscribe → อายุ < 15 วิ.

### 6 live 3 นาที (`reboot_live.csv`, 18 แถว, interval 10 วิ)
- TTFF 1.38 วิ, connected 18/18, reconnect 0, packetsLost 0, keyFrames 157/180 วิ, fps ~28, freezeCount 14 (Chrome headless sw-decode — ไม่ใช่ปัญหา stream, packetsLost=0).

## end-state (ไม่แตะอะไร)
app `live_20261024_0847` events off (ขึ้นเอง), ทุก container up, cira-gui/ds ตามเดิม. ไม่ได้สั่ง start/stop/restart/แก้ไฟล์ใด ๆ.
