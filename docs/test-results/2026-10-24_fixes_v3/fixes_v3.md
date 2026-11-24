# Fixes v3 — เก็บกวาด soak v2 + แก้ปัญหา + เตรียม soak v3

วันที่เริ่ม: 2026-10-24
Jetson: `ssh -o HostName=<JETSON_TAILSCALE_IP> jetson` (Tailscale)
Container: recorder / dashboard(nginx) / mediamtx(1.9.3) / mosquitto
App: `/home/jetson/.../person_count_app.py` (DeepStream 6.0.1)
กฎ: ไม่แตะ tmux cira / ไฟล์ CiRA (.npj) / reboot / network / nvpmodel / MediaMTX-DeepStream-JetPack upgrade. pip/apt install = ถามก่อน. backup `.bak-<เวลา>` ก่อนแก้ทุกไฟล์. events off เป็นหลัก. แก้ไม่ผ่าน 3 รอบ = คืนค่า + จด + ไปข้อถัดไป. disk < 3GB = หยุด.

---

## §0 เก็บกวาด soak v2 — เสร็จ (2026-10-24)

ผู้ใช้ยืนยันลบแล้ว. ทำบน Jetson เท่านั้น (ไม่แตะ PC backup).

| รายการ | ก่อน | ลบ | หลัง |
|---|---|---|---|
| Snapshot (/data/snapshots) | 2152 | 1747 (soak v2 window) | 405 (round1) |
| Event DB (events) | 2174 | 1762 | 412 (round1) + VACUUM |

- ลบด้วย list ตรงจาก PC backup (ชื่อไฟล์ 1747 + event_id 1762) — dry-run ยืนยัน present 1747/1747, match 1762/1762 ก่อนลบ.
- Disk ว่างหลังลบ: **7.1G** (`df -h /`: 21G ใช้ / 29G, 75%). VACUUM คืนน้อยเพราะ DB เล็ก.
- DB เหลือ 412 event ช่วง 2026-10-21T23:48:09 → 2026-10-22T22:45:06 — ในหน้าต่าง soak v2 เหลือ **0 แถว** (ตัดสะอาด).
- Dashboard HTTP 200; `/api/events` total 412; รูป round1 เสิร์ฟได้ (`img:200 size:47759`).
- tmux cira ไม่แตะ.

PC backup ครบ (ตรวจ md5):
| ไฟล์ | จำนวน/md5 |
|---|---|
| snapshots/ | 1747 ไฟล์ |
| soak_events_window.csv | 1762 แถว, `ee96530fd66227cf13bf125e0abc1d51` |
| safety.db.bak-20261023-231635 | `04364b7422be3ae26fdef54b6a04adba` (ตรง Jetson) |
| soak.csv | `71e479d2795d841b2fec6d3e88840b03` |
| snapshot manifest (md5-of-md5s, sorted) | `cea0a5bc741cfba32fedb09c00ab8290` |
| snapshot manifest file | tmp scratchpad `pc_snapshot_manifest.txt` 1747 บรรทัด |

---

## §1 ภาพสด (A1–A4)

ไฟล์แก้: `perception/app/person_count_app.py`, `dashboard/mediamtx/mediamtx.yml`
backup: `.bak-20261024-004539` (PC+Jetson). before md5: app `705044d5...`, yml `8e2ffc5b...`.
after md5 (PC=Jetson): app `6ad0a673612594239a120107836c5d24`, yml `37cb911346088a73fd369b4e2977f0d1`.

### ข้อเท็จจริงจากการวัด (ก่อนแก้)
- ffprobe 120 วิ ที่ `rtsp://127.0.0.1:8555/cam01` (ฝั่ง encoder out): 3571 แพ็กเก็ต, 29.75 fps, keyframe 123 (~1/วิ), **PTS ถอยหลัง = 1 ครั้ง เฉพาะแพ็กเก็ตแรกตอน join** (prev 422938 → cur 10010). steady-state ที่เหลือเดินหน้าล้วน.
- mediamtx local ICE candidate = `172.17.0.1/8189` (docker bridge) — remote browser ผ่าน Tailscale เข้าไม่ถึง.
- ไม่มี webrtcIPsFromInterfaces ใน yml → mediamtx auto-gather ทุก interface รวม 172.17.0.1.
- โครงสร้าง pipeline: enc(nvv4l2h264enc, Baseline, SPS/PPS/IDR ทุก 30) → parse2(h264parse config_interval=-1) → rtph264pay(config_interval=-1) → udpsink → RTSPServer.

### สิ่งที่แก้
- **A1** probe บน pad `pay`.sink: ถ้า `pts <= last` ดัน `last + 1 ms` (ns), อัปเดต dts ด้วย, นับ `_pts_fixed`. ไม่กระทบ fps (เฟรมห่าง ~33 ms).
- **A2** เพิ่ม `idrinterval=30` ที่ nvv4l2h264enc (เดิมไม่ได้ตั้ง; iframeinterval=30 มีอยู่แล้ว).
- **A3** bitrate `4000000 → 2000000` (2 Mbps).
- **A4 (app)** ตัด `config_interval=-1` ซ้ำที่ parse2 (เหลือที่ rtph264pay เท่านั้น).
- **A4 (mediamtx)** เพิ่ม `webrtcIPsFromInterfaces: no` → โฆษณาเฉพาะ <JETSON_TAILSCALE_IP> + <JETSON_LAN_IP>.

### ข้อเท็จจริงจากการวัด (หลังแก้ + restart app/mediamtx)
- mediamtx local ICE candidate = `<JETSON_TAILSCALE_IP>/8189` (Tailscale) / `<JETSON_LAN_IP>` — **ไม่มี 172.17.0.1 แล้ว** ✓
- **mediamtx "B-frames" ตั้งแต่ restart = 0** ข้ามหลายรอบ on-demand source start/stop ✓ (เดิม soak v2 = 81 บรรทัด/125 session)
- ffprobe หลังแก้: 28.79 fps, keyframe ~1/วิ, PTS ถอยหลัง = 1 (join artifact เดิม ฝั่ง reader เท่านั้น; publisher สะอาด)
- app log: `Profile = 66` (Baseline) ✓, fps ~29 ที่ 2 Mbps (ไม่ตก)
- **สรุป (ข้อเท็จจริง):** ปัญหา B-frames reject หายแล้ว (0). สาเหตุหลักของการหลุดซ้ำของ remote browser = ICE โฆษณา docker bridge 172.17.0.1 → แก้ด้วย A4.
- **สมมติฐาน:** join artifact (PTS ถอยหลัง 1 ครั้งตอนต่อ) เป็นของ reader-side (ffprobe) ไม่ใช่ publisher; mediamtx (RTSP TCP ordered) ไม่เห็น จึง B-frames=0. A1 เป็นกันชนเผื่อ publisher ส่งถอยหลังจริง.

### live_monitor (B2)
- เครื่องมือ (ไม่ต้องติดตั้งอะไรเพิ่ม): `whep_monitor.html` (WHEP client เลียนแบบ web/js/webrtc.js + getStats) + `live_sink.js` (Node stdlib http sink → live_monitor.csv) + Chrome `--headless=new`. รันบน PC ผ่าน Tailscale.
- คอลัมน์: ts, connected, framesDecoded, freezeCount, totalFreezesDuration, keyFramesDecoded, packetsLost, fps, reconnects, first_frame_s.
- smoke 90 วิ: connected ตลอด, framesDecoded ~29fps, keyframe ~1/วิ, packetsLost 0, reconnects 0, first_frame 2.62 วิ, freezeCount โต 7 (ส่วนใหญ่ช่วงต้น).
- หมายเหตุ: headless `--disable-gpu` = software decode → freeze อาจสูงกว่าที่ browser จริง (hardware decode) ของผู้ใช้. (ผล 10/30 นาที: ดู §5)
- bug ที่แก้ (เครื่องมือ scratchpad ของผม): reconnect เดิม teardown เมื่อ state = disconnected (มักฟื้นเอง) → false reconnect loop. แก้เป็น reconnect เฉพาะ `failed`.

### เครื่องมือ live_monitor ที่เลือกใช้ (task #5)
- **ใช้ `tools/live_monitor/` (ของ pc-session)** เป็นตัวหลักสำหรับ soak v3: `live_monitor.js` + `whep_monitor.html` + `pts_check.py`.
  เหตุผล: อยู่ใน repo, เลือก ephemeral port เอง (ไม่ชน EADDRINUSE), auto หา Chrome/Edge, มี watchdog + last_frame_age, grace 5 วิ/retry 5 วิ เหมือน Dashboard จริง.
  คำสั่ง: `node tools/live_monitor/live_monitor.js --csv <out.csv> --minutes N --interval 10`
- ของผม (scratchpad `whep_monitor.html`+`live_sink.js`+`run_monitor.sh`) = ตัวสำรอง, ไม่ลบ, ไม่ใช้ใน soak v3.

### baseline จาก pc-session (live_fix.md, โค้ดเดิม .bak-20261024-004539, กล้องสด events off, เปิดไฟ, 01:05–01:12)
- ffprobe 120 วิ: PTS ถอยหลัง **0** (ไม่นับ jump แรกก่อน RTCP sync); keyframe ทุก ~1.04 วิ แต่เป็น I-frame ไม่ใช่ IDR.
- `nvv4l2h264enc` เดิม **idrinterval ไม่ตั้ง = default 256** (IDR ทุก ~9 วิ) → ยืนยันอาการจอดำนานหลังต่อใหม่. **A2 (idrinterval=30) คือตัวแก้หลักของอาการนี้.**
- mediamtx 8 นาที "B-frames" = **0** (ตรงกับของผม: เกิดเป็นช่วงๆ; soak v2 เห็น 46/30 นาที).
- live_monitor 5 นาที baseline: reconnects 6, TTFF 1.58/52.7/7.27 วิ, freezeCount 59, packetsLost 5126 — **แต่มีคนดู 2 คน (monitor ซ้อน) + เส้นทาง Tailscale ข้าม internet** → เลขนี้เพี้ยน, ต้องวัดซ้ำคนดูคนเดียว (กำลังทำ).
- **สรุป (ข้อเท็จจริง):** PTS ถอยหลังและ B-frames = 0 ตอนเปิดไฟทั้งโค้ดเดิมและโค้ดแก้ → A1 ยังไม่ได้พิสูจน์ค่าในสภาพแสงน้อย (pts_fixed=0 ตลอดจน mem-debug). **ต้องทดสอบ A1 ช่วงปิดไฟ/แสงน้อย** (ผู้ใช้จะปิดไฟให้เมื่อบอก). อาการหลุดหลัก = idrinterval 256 (แก้ด้วย A2) + ICE 172.x (แก้ด้วย A4) + เส้นทางเครือข่าย (นอก scope).

### เหตุการณ์ session ซ้อน + การคืนสถานะ (01:05–01:30)
- pc-session อีก session ds-stop app, รัน baseline โค้ดเดิม, คืนไฟล์แก้แล้ว (`.bak-20261024-010507` = ตัวแก้แล้ว) แต่ไม่ restart mediamtx รอบสอง → mediamtx รัน config เดิม (ICE ยังมี 172.18.0.1).
- แก้โดย session นี้ (01:29): sync app `f331fc90` (มี --mem-debug) → Jetson, `ds-stop`, `docker restart mediamtx` (โหลด yml แก้แล้ว), `ds-start --mem-debug` (events off, run `live_20261024_0129`).
- ยืนยันหลังแก้: app_JT=`f331fc90` (=PC), yml_JT=`37cb9113` (=PC), **ICE = <JETSON_TAILSCALE_IP> + <JETSON_LAN_IP> เท่านั้น ไม่มี 172.x**, RTSP 8555 serve ปกติ, mem-debug เขียน (rss 1534.6MB, pts_fixed 0).
- ผลทดสอบช่วง 00:58–01:15 (โดนรบกวน) = ทิ้ง.

### §1.7 ผลวัดจริง — 15 นาที คนดูคนเดียว เปิดไฟ (app live_20261024_0139, A1–A4, ไม่มี mem-debug)
เครื่องมือ: `tools/live_monitor/live_monitor.js` → `live_monitor.csv` (90 แถว, interval 10 วิ).

| metric | baseline (โค้ดเดิม เปิดไฟ) | หลังแก้ A1–A4 | เกณฑ์ | ผ่าน |
|---|---|---|---|---|
| TTFF (ภาพแรก) | 1.58/**52.7**/7.27 วิ | **0.96 วิ** | ≤3 | ✓ |
| reconnect | 6 | **0** | 0 | ✓ |
| mediamtx "B-frames" (17 นาที) | 0 | **0** | 0 | ✓ |
| packetsLost | 5126 (2 viewer+เน็ต) | **0** | — | ✓ |
| keyFramesDecoded | ~1/27 วิ (idr 256) | 829/900 วิ ≈ **1/วิ** (idr 30) | ~1/วิ | ✓ |
| fps (เฉลี่ย/ช่วง) | ~28 | 28.4 (21.6–31.2) | ไม่ตก | ✓ |
| connected | — | 90/90 แถว | ต่อตลอด | ✓ |
| freezeCount | 59/5 นาที | 40/15 นาที (~2.7/นาที, รวม 30.9 วิ) | น้อยมาก | ~ |
| session close (mediamtx) | 6 (รวม deadline exceeded) | 3 (peer closed ×2, terminated ×1 = ของ monitor เอง) | — | ✓ |

- **ตัวแก้ที่ได้ผลจริง:** A2 (idrinterval 256→30 → IDR ทุก ~1 วิ, ฟื้นเร็วหลังต่อใหม่, ไม่จอดำนาน), A4 (ICE ตัด docker bridge 172.x → remote Tailscale ต่อติด/นิ่ง).
- **A1/A3:** A1 pts_fixed=0 ตลอด (publisher ไม่ส่ง PTS ถอยหลังตอนเปิดไฟ) → เป็นกันชน; A3 (2 Mbps) ไม่ทำ fps/ภาพแย่ลง.
- **freeze 40:** ค่าเดียวที่ไม่ 0. packetsLost=0 → stream ส่งครบ; freeze มาจาก Chrome headless `--disable-gpu` (software decode) + jitter Tailscale ไม่ใช่ปัญหา stream. Dashboard จริง (hardware decode) คาดค้างน้อยกว่า.
- **สรุป §1: ผ่าน** (เกณฑ์หลักครบ). ไฟล์แก้: app `f331fc90...`, yml `37cb9113...` (PC=Jetson).

---

## §2 หน่วยความจำรั่ว

วัดด้วย `--mem-debug` (log ทุก 60 วิ ลง `live_20261024_0304_mem.csv`): rss จาก `/proc/self/status`, จำนวน object จาก `gc`, tracemalloc current/peak + top3, pts_fixed.

### ผลวัดจริง — app `live_20261024_0304`, events off, 62 นาที (61→3734 วิ, 61 ตัวอย่าง)

| metric | เริ่ม (61 วิ) | จบ (3734 วิ) | เปลี่ยน |
|---|---|---|---|
| rss_mb | 1542.1 | 1547.5 | **+5.4 MB / 62 นาที ≈ +5.2 MB/ชม.** |
| py_objects (gc) | 35307 | 35244 | **−63 (นิ่ง/ลดเล็กน้อย)** |
| tracemalloc current | 3.63 MB | 3.67 MB | +0.04 (นิ่ง) |
| tracemalloc peak | 3.67 MB | 4.38 MB | +0.71 (ไม่โต monotonic) |
| pts_fixed | 0 | 0 | 0 |

- top3 alloc คงที่ทั้งรัน: `importlib._bootstrap_external:487=2424KB` (import ตอน start, static), `_bootstrap:219=154KB`, `stringprep.py:187=18KB` — ไม่มีตัวโต.
- logger soak.csv (events off) ยืนยัน rss_app 1535.1→1545.5 MB สอดคล้องกัน.

### สรุป (§2)
- **ไม่มี leak ฝั่ง Python:** จำนวน object กับ tracemalloc นิ่ง (object ลดลงด้วยซ้ำ) → ตรงกับ audit โค้ด (person_ids evict, ppe_pretrack keep=30, โครงสร้างมี bound ครบ).
- **RSS โตช้ามาก +5 MB/ชม.** มาจากฝั่ง native (GStreamer/allocator fragmentation) ไม่ใช่ Python. ประมาณ 24 ชม. ≈ +125 MB บน baseline ~1.5 GB → รับได้บน 4 GB (ไม่ใกล้ OOM).
- **ไม่ใช่ตัวบล็อก.** เฝ้า rss ต่อใน soak v3 (logger มี rss_app ทุก 60 วิ) เพื่อยืนยันว่าอิ่มตัว ไม่ใช่โตเชิงเส้น.

---

## §3 Latency

### ข้อเท็จจริงจากการวัด (จาก soak v2 latency.csv, n=1758)
- latency_ms = `event_rx_ms − ds_rx_ms` วัดที่ subscriber เดียวกัน = **เวลาไป-กลับฝั่ง CiRA** (รับ ds/violation → CiRA ประมวลผล → publish event). นาฬิกาเดียวกัน จึงไม่มี clock skew.
- min 10, median **263**, mean 350, p90 712, p95 **922**, p99 1421, max 2302 ms.
- การกระจาย: <300 ms = 56.5%, 300–500 = 23.3%, 500–1000 = 16.4%, >1000 = 3.7%.

### วิเคราะห์
- ตัวเลขนี้ **ไม่รวม** ฝั่ง app (detect → publish ds/violation) เพราะเริ่มจับที่ ds_rx (broker รับ ds/violation แล้ว).
- หางที่ยาว (>1 วิ 3.7%) สอดคล้องกับรอบ AutoRun loop ของ CiRA + QoS 1 round-trip บน Jetson 2 คอร์.

### สรุป (§3.3)
- **สาเหตุอยู่ฝั่ง CiRA** (ห้ามแก้) → เสนอเท่านั้น:
  1. วัด component split สดใน §5 (mosquitto_sub จับเวลา ds/violation กับ event, + ให้ app ใส่ timestamp detect ลง ds/violation เพื่อแยกส่วน app).
  2. (CiRA) ลดคาบ AutoRun loop / ใช้ event-driven trigger แทน polling.
  3. (CiRA) ds/violation + event ใช้ QoS 0 ถ้ายอมรับ reliability ได้ (ลด round-trip).
- ฝั่ง app แก้ได้เฉพาะถ้าพบว่า detect→publish กินเวลา (จะวัดใน §5); p95 922 ยังต่ำกว่าเกณฑ์ 1000.

---

## §4 Logger v3 (B1, B3, B4)

ไฟล์ใหม่ (ไม่ทับ v2): `tools/soak_sample_v3.py`, `soak_logger_v3.sh`, `soak_slow_v3.sh`, `light.sh` (→ `~/light`).
md5 (PC=Jetson): sample_v3 `edf333fd...`, logger_v3 `37c6c88d...`, slow_v3 `377f74bb...`, light `2705dfe7...`.

### §4.1 power_mw — แก้แล้ว
- สาเหตุ v2 ว่าง: อ่านจาก tegrastats (`VDD_IN`/`POM_5V_IN`) แต่ tegrastats บอร์ดนี้ **ไม่มี field power เลย**.
- INA3221 sysfs อ่านได้ด้วย **passwordless sudo**: `/sys/bus/iio/devices/iio:device0/in_power{0,1,2}_input`.
  rail0=POM_5V_IN (total), rail1=GPU, rail2=CPU. ทดสอบ 3 ครั้ง: IN 4982–5564, GPU 1174–1294, CPU 850–891 mW (3/3 สำเร็จ).
- dmesg มี `-121` เก่า (ของนานแล้ว) แต่อ่านตอนนี้ได้ปกติ.
- v3 เพิ่มคอลัมน์ `power_mw` (IN), `power_gpu_mw`, `power_cpu_mw`.

### §4.2 brightness — แก้แล้ว
- `soak_slow_v3.sh`: เก็บ **SATAVG ดิบ + YAVG**, crop แถบ OSD บน (`crop=iw:ih*0.80:0:ih*0.15` = ตัดบน 15% + ล่าง 5%), **ตัด is_night ออก**. header: `timestamp,elapsed_h,yavg,satavg,crop`.
- ข้อจำกัด: สตรีมมี OSD เผาในภาพ (box คนขยับ หลบไม่ได้) crop เฉพาะแถบข้อความบน.

### §4.3 light_log — แก้แล้ว
- `~/light on|off|note [ข้อความ]` → ต่อท้าย `~/light_log.csv` (`timestamp,light_on,note`). รายงาน soak ingest ตามหน้าต่างเวลา.

### §4.4 คอลัมน์ว่างที่แก้ได้ — แก้แล้ว (ยืนยันจาก sample row จริง)
- `gpu_freq_mhz` = 614 (`/sys/class/devfreq/57000000.gpu/cur_freq`, user อ่านได้)
- `emc_freq_mhz` = 1600 (`/sys/kernel/debug/clk/emc/clk_rate`, sudo)
- `throttled` = 0 (cpufreq `scaling_cur_freq < scaling_max_freq`)
- `power_mw/power_gpu_mw/power_cpu_mw` = 4673/975/895 (ตัวอย่างจริง)
- ยังว่างโดยธรรมชาติ: event columns (events off), restricted_zone (ไม่มี zone).

### §4.5 CPU ของ logger
- จะวัดใน §5 (รัน logger v3 ขนาน 60 นาที).

### live_monitor merge
- รันบน PC (Chrome headless + Node stdlib sink) → `live_monitor.csv` ในโฟลเดอร์ผล. §5/§6 รวมเข้าชุด soak.

---

## §5 ตรวจรวมระบบ

### §5.1 events off — 60 นาที (app `live_20261024_0304`, logger `sys/soak_eventsoff.csv` 62 แถว, live_monitor `live_60min.csv` 361 แถว)

**ระบบ (logger):**
| metric | ค่า |
|---|---|
| fps_in | ~27 |
| cpu_total max | 97% |
| power_mw | 4828 → 5104 |
| throttled | 0 แถว (ไม่ throttle เลย) |
| rss_app | 1535–1545 MB |
| disk_free | 7.02 GB (>3 ✓) |
| events_sum (helmet+vest+zone) | **0** (events off ยืนยัน) |

**ภาพสด (live_monitor 60 นาที คนดูคนเดียว):**
| metric | ค่า | เกณฑ์ | ผ่าน |
|---|---|---|---|
| TTFF | 1.52 วิ | ≤3 | ✓ |
| connected | 359/361 แถว | ต่อตลอด | ✓ |
| reconnect | 1 (เน็ตสะดุด 20:35 ฟื้นเอง) | น้อย | ✓ |
| fps เฉลี่ย | 26.4 | ไม่ตก | ✓ |
| keyFramesDecoded | 3170/3600 วิ ≈ 1/วิ | ~1/วิ | ✓ |
| packetsLost | 74 (เน็ต 60 นาที) | — | ~ |
| freezeCount | 188 รวม 192 วิ (~3/นาที) | น้อย (sw-decode) | ~ |

- events.log: 1 รายการ `fail connection failed` (20:35) → ฟื้นเองใน interval ถัดไป.
- สรุป §5.1: ระบบนิ่ง 60 นาที ไม่ throttle, disk พอ, ภาพสดต่อตลอด (เทียบ baseline reconnect 6 → 1).

### §5.2 events on — 12 นาที (app `live_20261024_0407`, 04:08–04:21)

วัดจริง:
| metric | ค่า |
|---|---|
| persons / in_frame | **0 ทั้ง 12 นาที** (ไม่มีคนในเฟรม) |
| detected / no_helmet / no_vest | 0 / 0 / 0 |
| events_via_cira / via_fallback | 0 / 0 |
| snapshots (recorder) | 405 → 405 (ไม่เพิ่ม) |
| cira_received / published (สะสม) | 14651 / 3683 (ไม่ขยับ) |
| latency.csv | header อย่างเดียว (ไม่มี event) |
| app / fps | ทำงานปกติ fps 28.4–28.8 |

- **ไม่มี violation จริงให้ตรวจ** (ฉากว่าง ไม่มีคน) → event path ไม่มี stimulus → วัด live latency ไม่ได้รอบนี้.
- **ไม่ใช่ pipeline พัง:** app `--events on` arm ถูกต้อง (snaps=0 เพราะ in_frame=0), broker/CiRA/recorder ยังมีชีวิต (ตัวนับสะสมคงค่า), path เดียวกันเคยผ่าน event จริง 1762 รายการใน soak v2.
- **ไม่ inject ข้อมูลปลอมลง DB** (จะทำให้ DB ที่เพิ่งเก็บกวาด §0 สกปรก + ไม่มีคำสั่งอนุญาต). ตัวเลข latency ที่เชื่อถือได้ยังเป็นของจริง §3 (soak v2, n=1758).
- **วัด live latency จริงควรทำตอนมีคนในเฟรม** (กลางวัน soak v3 มีคนทำงาน) — logger v3 บันทึก latency ให้อัตโนมัติ.

### สรุป §5
- events off 60 นาที: ระบบนิ่ง ไม่ throttle, disk พอ, ภาพสดต่อตลอด (reconnect 1) → **ผ่าน**.
- events on 12 นาที: pipeline arm ปกติแต่ฉากว่าง → ไม่มี event ให้วัด; ไม่มี regression. วัด latency สดเลื่อนไป soak v3 (มีคน).
- end-state: app กลับ events off (`live_20261024_0421`), snapshots 405 คงเดิม, disk 7.1 GB.

---

## §6 เตรียม soak v3 — พร้อม (ยังไม่เริ่ม)

### สถานะความพร้อม (ตรวจแล้ว)
- scripts (md5 PC=Jetson): `soak_sample_v3.py edf333fd`, `soak_logger_v3.sh 37c6c88d`, `soak_slow_v3.sh 377f74bb`, `soak3_up.sh e4ad694e`, `light.sh 2705dfe7`. bash -n/ast ผ่านทั้งหมด.
- `~/light` → `tools/light.sh` symlink ใช้ได้ (`~/light on|off|note` ต่อท้าย `~/light_log.csv`).
- **dry-run (04:23, tmux soak3, 70 วิ แล้ว kill):** 4 หน้าต่าง mqtt/logger/slow/watch รันครบ ไม่มี error.
  - `soak.csv` มี row (power 5330, cpu 98.5, freq 921/614/1600, throttled 0, rss 1516).
  - `brightness.csv` sample ทันที, `mediamtx.csv` + `cira_status.log` มีข้อมูล, `latency.csv/filtered.csv` header (ยังไม่มี event), `watch.log` ว่าง (ไม่ alert = ถูก).
- disk 7.1 GB free (>3 ✓).

### คำสั่งเริ่ม (รอคำว่า "เริ่ม soak v3" — **ยังไม่รัน**)
```bash
# 1) app โหมด soak จริง (แนะนำ events on เพื่อเก็บ latency สด + event จริง):
ssh jetson ./ds-start --events on
# 2) collectors (ssh ผ่าน Tailscale HostName <JETSON_TAILSCALE_IP>):
D=~/safety/docs/test-results/2026-10-25_soak24h_v3
SOAK_DIR=$D SOAK_START=$(date +%s) SOAK_HOURS=24 bash ~/safety/tools/soak3_up.sh soak3
# 3) PC live monitor คู่ขนาน (เลือก live_monitor.js = canonical):
node tools/live_monitor/live_monitor.js --csv <out>/live.csv --minutes 1440 --interval 30
# 4) จดไฟ: ~/light on  (ตอนเปิด) / ~/light off (ตอนปิด)
```
- **หยุดรอ** คำสั่ง "เริ่ม soak v3" ตามกติกา.

---

## §7 สรุป

| § | ปัญหา | แก้ | ผลวัดจริง | สถานะ |
|---|---|---|---|---|
| 0 | เก็บกวาด soak v2 | ลบ snapshot 1747 + event 1762 + VACUUM | disk 7.1 GB, Dashboard 200, event นอกช่วงยังอยู่, PC backup ครบ | ✓ เสร็จ |
| 1 | ภาพสดสะดุด/จอดำ/หลุด | A1 pts guard, A2 idrinterval 256→30, A3 bitrate 2M, A4 ICE ตัด 172.x | TTFF 0.96–1.52 วิ, reconnect 0–1 (baseline 6/52.7 วิ), B-frames 0, keyframe ~1/วิ | ✓ ผ่าน |
| 2 | memory leak | — (audit + วัด mem-debug) | Python heap นิ่ง (object/tracemalloc ไม่โต), RSS +5 MB/ชม. native เท่านั้น | ✓ ไม่ leak |
| 3 | latency | เสนอเท่านั้น (สาเหตุฝั่ง CiRA) | median 263, p95 922 ms (<1000), วัดสดเลื่อนไป soak v3 | ✓ อธิบาย |
| 4 | logger คอลัมน์ว่าง | power (INA3221 sudo), gpu/emc freq, throttled, brightness ดิบ, light.sh | sample จริงครบทุกคอลัมน์ | ✓ แก้ |
| 5 | ตรวจรวมระบบ | — | events off 60 นาที นิ่ง ไม่ throttle; events on 12 นาที ฉากว่าง (ไม่มี event ให้วัด) | ✓/~ |
| 6 | เตรียม soak v3 | scripts + dry-run + runbook | พร้อม, disk 7.1 GB | ✓ พร้อม (ยังไม่เริ่ม) |

### ไฟล์ที่แก้ (PC=Jetson)
- `perception/app/person_count_app.py` md5 `f331fc90d4e7ee1886655ef0ad74988e` (backup `.bak-20261024-004539`)
- `dashboard/mediamtx/mediamtx.yml` md5 `37cb911346088a73fd369b4e2977f0d1` (backup `.bak-20261024-004539`)

### คงค้าง / ข้อเสนอ
- วัด latency สด (component split app vs CiRA) ตอนมีคนในเฟรม — เก็บอัตโนมัติใน soak v3.
- เฝ้า RSS native creep (+5 MB/ชม.) ว่าอิ่มตัวใน soak v3.
- freeze ใน live_monitor เป็นผลของ Chrome headless sw-decode; Dashboard จริง (hw decode) คาดน้อยกว่า.

### end-state
app `live_20261024_0421` **events off**, mem-debug off, snapshots 405 คงเดิม, disk 7.1 GB, tmux cira-gui/ds ไม่ถูกแตะ.
