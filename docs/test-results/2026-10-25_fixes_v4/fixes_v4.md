# Fixes v4 — แก้ปัญหาจาก soak v1–v3 + เตรียม soak v4

อ้างอิง: `soak_v3_report.docx`, `2026-10-24_soak24h_v3/README.md`, `webrtc_diagnosis.md`, `fps_drop_analysis.md`, `fixes_v3.md`.
กฎ: backup ก่อนแก้ (.bak-เวลา), sync PC↔Jetson + md5, ทดสอบ events off, จบทุกขั้น app events off, ไม่แตะ CiRA/reboot/upgrade, pip/apt + ลบไฟล์ = ถามก่อน, network ผู้ใช้ทำเอง, แก้ไม่ผ่าน 3 รอบ = คืน backup.

สถานะ ณ เริ่ม: app events off (`live_20261025_1617`), mediamtx yml 37cb9113, recorder events 412 (หลัง cleanup v3).

> **ช่วง pre-soak (events on ก่อนเริ่ม soak v4):** เปิด events on เวลา **2026-10-26 02:30:28 +07** (run `live_20261026_0230`, md5 `810ad1d5`) เพื่อทดสอบสด ก่อนสั่ง "เริ่ม soak v4". **event/snapshot ใด ๆ ที่เกิดระหว่าง 02:30:28 +07 → เวลาที่ soak v4 เริ่ม = ข้อมูล pre-soak ไม่นับรวมใน soak v4** (ตัดออกตอนวิเคราะห์ด้วยช่วงเวลา soak v4 จริง). หมายเหตุ: CiRA core process ขึ้น (pid 8223/8386) แต่ heartbeat `factory/safety/cira/status` **ยังไม่ publish** = flow ใน CiRA GUI ยังไม่รัน → ผู้ใช้ต้องสั่งรัน flow ใน GUI ก่อน event via=cira จะทำงาน (ไม่แตะ tmux cira-gui).

---

## ข้อ 1 — ภาพสดค้างถาวรหลังกล้องรีเซ็ต stream (บั๊ก A1 จาก v3)

**ปัญหา:** v3 A1 (`_pay_pts_probe`) บังคับ `pts = last+1ms` ทุกครั้งที่ `pts<=last`. เมื่อกล้องรีเซ็ต PTS (02:20 ใน v3, SSRC เปลี่ยน) PTS ถอยไปไกล → ทุกเฟรม `pts<=last` จริงตลอด → +1ms ไม่เลิก → RTP timeline เดิน 1 ms/เฟรม → WebRTC decoder ค้าง → ภาพสดค้างถาวรจนจบ soak. source restart ไม่รีเซ็ต `_last_pay_pts`.

**ก่อน:** ffprobe rtsp 8555 ช่วงบั๊ก = PTS delta 1.0 ms ทุกเฟรม; live.csv framesDecoded ค้าง 1078519 ตั้งแต่ 02:20.

**แก้:** แยก logic เป็นโมดูล `perception/app/pts_guard.py` (pure python, unit-test บน PC ได้):
- ถอยเล็กน้อย (≤200 ms) → nudge +1 ms เดิม (`fixed`++).
- ถอยมาก (>200 ms) หรือกระโดดหน้า (>2 s) ใน PTS ต้นทาง = stream reset → rebase offset ให้ output ต่อ ~1 เฟรม (33 ms) จาก last ที่ส่ง (`rebase`++) → เฟรมถัดไปเดิน ~33/66 ms ปกติ ไม่ติด 1 ms.
- ตรวจ reset จากผลต่าง PTS ต้นทาง (ก่อนใส่ offset).
- `reset()` ล้าง timeline (cold start). `restart()` (เรียกตอน pipeline restart) **คง timeline ต่อเนื่อง**: เฟรมแรกหลัง restart ถูกบังคับ rebase ไปต่อ ~1 เฟรมจาก last ที่ส่ง → RTP timestamp ไม่ถอยหลังข้าม restart.

**ปัญหาที่ 2 ที่เจอตอนทดสอบจริง (2026-10-26): SSRC เปลี่ยนตอน restart**
- กล้องรีบูต → pipeline restart (NULL→PLAYING) → `rtph264pay` สุ่ม SSRC ใหม่ (2458161920 → 225395077).
- mediamtx ล็อก SSRC แรกบน RTSP source → ทิ้งทุกแพ็กเก็ต SSRC ใหม่ (`received packet with wrong SSRC ... expected ...`) → ภาพสดค้าง/รอภาพแรก, F5 ไม่ช่วย, ต้อง restart mediamtx เท่านั้นถึงกู้ได้.
- **แก้:** ล็อก `rtph264pay ... ssrc=2779096485` (คงที่ ไม่สุ่มใหม่ข้าม NULL→PLAYING) → mediamtx คง source เดิม. + `restart()` คง RTP timestamp monotonic (ถ้า timestamp ถอยหลังข้าม restart mediamtx จะทิ้งแบบ PTS-backward เหมือนเดิม). สองอย่างคู่กันทำให้ภาพสด**ฟื้นเอง**หลังกล้องรีบูต โดยไม่ต้อง restart mediamtx/ไม่ต้อง F5.

ไฟล์ที่แก้:
- `perception/app/pts_guard.py` (ใหม่): คลาส `PtsGuard` (feed/reset/stats_window_reset/window_ms + counters fixed, rebase).
- `perception/app/person_count_app.py`: import PtsGuard; `__init__` ใช้ `self._pts_guard=PtsGuard()`; `_pay_pts_probe` เรียก `guard.feed(pts)`; `_play()` เรียก `guard.restart()` (เดิม reset); `rtph264pay` เพิ่ม `ssrc=2779096485`; บรรทัด log fps ทุก 60 วิ เพิ่ม `pts_fixed/pts_rebase/pts_dmin_ms/pts_dmax_ms/app_restarts`; mem.csv ใช้ `guard.fixed`.
- `perception/app/test_pts_guard.py` (ใหม่): unit test.

**unit test (บน PC + Jetson py3.6):** 13/13 PASS — ปกติ ~33ms; wobble nudge; reset→rebase 1, delta หลัง reset ~33ms (ไม่ใช่ 1ms); กระโดดหน้า 5s rebase; 3 รีเซ็ต→2 rebase; ไม่มี 1ms pinning; **restart() ต่อ timeline ข้ามกล้องรีบูต (output เพิ่มขึ้นต่อเนื่อง, เฟรมแรกหลังรีบูต ~1 เฟรมจาก last, นับเป็น 1 rebase, spacing ~33ms); restart() ก่อนมีเฟรม = cold start (passthrough)**.

**cam01/status:** ไม่ใส่ (เลี่ยงแก้ status_mqtt; "ถ้าทำได้"). logger v4 (ข้อ5) อ่าน pts_fixed/pts_rebase/app_restarts จากบรรทัด log fps แทน.

**ทดสอบจริง (2026-10-26, events off):**
- **รอบ 0 (Privacy Mode):** Tapo ส่งภาพดำ "Privacy Mode is on" ต่อเนื่อง ~30 fps — **ไม่รีเซ็ต stream** (ไม่มี SSRC เปลี่ยน, pts_rebase คงที่, ไฟภาพสดเขียวถูกต้อง). ใช้ทดสอบ A1 ไม่ได้ → เปลี่ยนเป็นรีบูตกล้องจากแอป Tapo.
- **รอบ 1 (รีบูตกล้อง 23:37:50):** พบปัญหาที่ 2 — SSRC เปลี่ยน, mediamtx flood `wrong SSRC expected 2458161920`, ภาพค้าง F5 ไม่ขึ้น. app ฝั่งดี (PTS สะอาด dmin 2.9/dmax 91 ms ไม่ติด 1ms). กู้ด้วย `docker restart mediamtx`. → ใส่ fix ล็อก ssrc + restart() แล้ว deploy ใหม่.
- **รอบ 2 (รีบูตกล้อง หลัง fix): ไม่นับ** — เผลอ restart mediamtx ก่อน WHEP probe และ fps 28.99 เป็นฝั่ง app ไม่ได้พิสูจน์ว่าภาพถึงเบราว์เซอร์ ("กลับ2" ที่ผู้ใช้พิมพ์ตอนกล้องยังดับ).
- **รอบ 3 (รีบูตกล้อง สะอาด, 2026-10-26): ผ่าน.** รัน `live_monitor` (WHEP ในเบราว์เซอร์จริง, interval 2s) ตลอด, **ไม่ restart mediamtx/app**. หลักฐาน (`item1_live_round3/round3_live.csv`):
  - mediamtx `StartedAt 2026-10-25T17:03:42Z` + path `readyTime 17:03:45Z` **ไม่เปลี่ยนเลย** (ไม่ได้ restart, source ไม่หลุด ready); `wrong SSRC` delta 3 นาที = **0**.
  - app `pts_rebase 2→3` (forced rebase), restart 2 ครั้งช่วงกล้องบูต, PTS สะอาด (dmin 2.4–7.1 ms).
  - **เวลาตามลำดับ (+07):** กดรีบูต ~00:13:38 (กล้องตัด stream ~00:13:28) → app เห็นกล้องหลุด 00:13:31 `RESTART #3 no frame 3.1s` (+ 00:13:55 `RESTART #4 camera error` ระหว่างกล้องบูต) → app ต่อกล้องใหม่ ~00:14:02 → **ภาพถึง live_monitor (เบราว์เซอร์) 17:14:02Z** (framesDecoded 2466→2468→climb, stalled 1→0, reconnects=1 = WHEP เจรจาใหม่อัตโนมัติ ไม่ใช่ F5) → ภาพถึง Dashboard ของผู้ใช้ ~00:14:1x ("กลับภาพ3", ไม่กด F5).
  - stall ~26–32 วิ = ช่วงกล้องดับ/บูต (ข้อจำกัดกล้อง), framesDecoded กลับเพิ่มทันทีที่กล้อง stream กลับ (<2 วิ, ≤30 วิหลังบูตเสร็จ). fps หลังบูตแกว่ง 9–29 = กล้อง Tapo settle เอง เฟรมไหลต่อเนื่อง.

**deploy + verify (events off):** sync Jetson, md5 ตรง (pts_guard `25a3ca5b…`, person_count_app `810ad1d5…`, test `c6dfc92a…`). backup `.bak-20261025-234936`. unit test บน Jetson py3.6 = 13/13 PASS.

---

## ข้อ 4 — live_monitor รายงาน connected ทั้งที่ภาพค้าง

**ปัญหา (v3):** whep_monitor ไม่ตรวจภาพค้าง → framesDecoded ค้างตั้งแต่ 02:20 แต่ยัง "connected" ไม่ต่อใหม่ (reconnects ค้าง 16).

**แก้:**
- `tools/live_monitor/whep_monitor.html`: poll getStats ทุก 1 วิ; ถ้า `connectionState==="connected"` แต่ framesDecoded ไม่ขยับ ≥ `STALL_MS`(5000) = stalled → `stallReconnect()` (teardown + ต่อใหม่ 1 วิ). นับ `stalledTotalS`, ring `fps10` สำหรับ decoded_fps_10s.
- คอลัมน์เพิ่ม: `stalled`(1/0), `stalled_total_s`, `decoded_fps_10s`.
- `tools/live_monitor/live_monitor.js`: interval default 30 วิ; kill headless Chrome/Edge เก่า (match `*live_monitor_*` ผ่าน PowerShell) ก่อนเริ่ม; COLS +3.

**ทดสอบ (docker pause 12 วิ, events off):** ก่อน pause fd เดิน fps ~22–27. pause → stall ที่ 6.0 วิ (events.log: "stall ... -> reconnect"), `stalled=1 stalled_total_s 7→12 reconnects 0→2 decoded_fps_10s=0.0`. unpause → fd 685→762→1001→1283, fps ~28, stalled=0. **ผ่าน.** (PC-side tool; ไม่ sync Jetson)

---

## ข้อ 5 — logger ข้อมูลว่าง/ล่ม (brightness, rss_cira)

**ปัญหา (v3):** brightness.csv ว่างตั้งแต่ 02:29 (frame-grab ล้มหลังกล้องรีเซ็ต ไม่ retry); rss_cira_mb ว่างทั้งไฟล์.

**แก้:**
- `tools/soak_slow_v3.sh`: brightness frame-grab retry 3 ครั้ง (sleep 3 ระหว่าง) — ทนกล้องรีเซ็ต; ล้มติดกัน ≥3 → เขียน `WARNING` ลง watch.log.
- `tools/soak_sample_v3.py`: `rss_mb()` เลือก match RSS มากสุด (process หลัก) — rss_cira ใช้ `cira_core_run`; เพิ่มคอลัมน์ `app_restarts,pts_fixed,pts_rebase,live_status` อ่านจากบรรทัด log fps ของ app (`tmux capture-pane -pt ds`); `live_status` = stalled ถ้า `pts_dmax_ms<5` (PTS pinned/บั๊ก A1) ไม่งั้น ok, unknown ถ้าอ่าน log ไม่ได้.
- `tools/soak_logger_v3.sh`: HDR +4 คอลัมน์.

**ทดสอบ (sampler 1 แถว, events off):** 51 คอลัมน์, `rss_cira=142.9` (เติมแล้ว), `app_restarts=0 pts_fixed=0 pts_rebase=1 live_status=ok`. collector CPU ยังเบา (sampler ครั้งเดียว/60วิ). **ผ่าน** (brightness retry + WARNING ตรวจตอน dry-run/60นาที).

---

## ข้อ 6 — teardown ตอนจบ soak ไม่ครบ (เกิดซ้ำ v2, v3)

**ปัญหา:** auto หยุดแค่ logger; collectors (mqtt/slow/watch) + app events-off ค้าง ต้องทำมือ.

**แก้:**
- `tools/soak_end_v4.sh` (ใหม่): (1) หยุด collector พี่น้องใน tmux session (C-c + pkill) (2) `./ds-stop; ./ds-start` (events off) (4) ตรวจ app events off + ไม่มี collector ค้าง เขียนผล. (3) live_monitor บน PC หยุดเองที่ `--minutes` (เข้าถึงจาก Jetson ไม่ได้ → runbook ครอบ).
- `tools/soak_logger_v3.sh`: จบ while แล้วเรียก `soak_end_v4.sh` (ผลต่อท้าย soak_done.txt) แล้ว `tmux kill-session`.
- `tools/soak3_up.sh`: ส่ง `SOAK_SESS` ให้ logger.

**ทดสอบ dry-run `SOAK_HOURS=0.1`:**
- รอบ 1 (inline call ใน logger): teardown ถูกฆ่ากลางคัน (soak_done.txt มีแค่ header, session ไม่ถูก kill) — soak_end_v4 รันใน process group ของ tmux window เดียวกับ logger, สัญญาณ/ds ops ทำให้ตาย. (soak_end_v4 รันเดี่ยวสมบูรณ์ exit 0).
- **แก้:** logger launch teardown แบบ **detached** (`setsid nohup ... &`), ย้าย `tmux kill-session` ไปไว้ท้าย soak_end_v4.sh เอง → teardown ไม่ขึ้นกับ window ที่กำลังจะตาย.
- รอบ 2 (detached, end-to-end): soak_done.txt = "teardown: OK (app events off, no collector left)", session **GONE**, leftover collectors **0**, app **--events off**, soak.csv **51 คอลัมน์** live_status=ok rss_cira=142.9. **ผ่าน.**
- ทดสอบ detached กับ dummy session แยก: session GONE, output ครบ. ผ่าน.

md5 sync (final): sampler `08b01428`, logger `5c9cc997`, slow `1376901d`, soak3_up `cae0c964`, end `2c848de6`.

---

## ข้อ 3 — Dashboard ส่วนภาพสด (webrtc.js / ui.js / app.js / dashboard.js / index.html / app.css)

**แก้ (เฉพาะ player/ภาพสด + แถบสถานะ + KPI ฝ่าฝืน; ไม่แตะแจ้งเตือน/รายงาน/ตั้งค่า; ไม่เพิ่ม library):**
- (a) `webrtc.js`: timeout "รอภาพแรก" `FIRST_FRAME_MS=8000` — connected แต่ไม่ได้เฟรมแรกใน 8 วิ → `_fail()` (backoff เดิม). เพิ่ม `lastFrameWall` (epoch เฟรมล่าสุด อยู่ข้าม reconnect) + `_connectedAt`.
- (b) `ui.js` renderQuality: ไม่มีเฟรมใหม่ขณะไม่ playing (≥3 วิ) → `ไม่มีภาพ X วิ` + ระดับ **แย่** (แทน "—"); `app.css .q-noframe` แดง. tick 1 วิ ให้ตัวเลขเดินแม้ peer ดับ.
- (c) ไฟ "ภาพสด" ข้าง Camera/Perception/Decision: `index.html` เพิ่ม light `livevideo`; `app.css` level `warn`=เหลือง; `app.js overallLights()` รวมจาก tiles (เขียว=เฟรมเดิน, เหลือง=ต่อใหม่/รอภาพแรก, แดง=ไม่มีภาพ>30วิ) ผ่าน `ctx.reportLive()`+`state.live`; tile รายงานทุก 1 วิ.
- (d) `dashboard.js` "การฝ่าฝืนวันนี้": เมื่อวาน < 10 → `+N จากเมื่อวาน (y)` แทน %.

**ทดสอบ (CDP headless Chrome, docker pause mediamtx 40 วิ, events off):**
- ปกติ: 4 ไฟ, livevideo `ok` "1/1", badge "ดี fps 28 1280×720 2.16Mbps หน่วง 96ms สูญหาย 0 ค้าง 0 ต่อเนื่อง 17วิ", todaySub "+0 จากเมื่อวาน (0)", ERRORS none.
- pause 8 วิ: livevideo **warn(เหลือง)** "0/1", badge "แย่ ไม่มีภาพ 7 วิ".
- pause 35 วิ: livevideo **bad(แดง)**, "ไม่มีภาพ 42 วิ" (dash_v4_nopic.png).
- unpause 12 วิ: livevideo **ok(เขียว)** "1/1", badge "พอใช้ ... ต่อเนื่อง 11วิ" — กลับเองอัตโนมัติ.
- ไม่มี console error ทุกช่วง. first-frame 8วิ timeout: โค้ดพร้อม (ยิงเมื่อ connected แต่ decode ไม่ได้ เช่น A1 1ms-PTS). Edge/มือถือ: `.lights` responsive เดิม wrap เต็มกว้าง — layout ไม่พัง.

md5 served=PC: webrtc `6ee90de3`, ui `eaef66fd`, app `ed025d4e`, dashboard `2ebd97ab`, index `952fac61`, app.css `bdde26a8`. deploy=scp+`docker restart dashboard`. screenshots: dash_v4_normal.png, dash_v4_nopic.png. backup `web.bak-20261025-190346`.

---

## ข้อ 8 — เตรียม soak v4 (runbook, ยังไม่เริ่ม)

โฟลเดอร์: `docs/test-results/2026-10-2X_soak24h_v4/` (X = วันที่เริ่มจริง).
เงื่อนไข: เปิดไฟตลอด (บันทึก `~/light on`/`off`), `--events on`, cooldown แบบเดิม, nvpmodel 5W, คนเดินผ่านเป็นระยะช่วงกลางวัน.

### คำสั่งเริ่ม (รอ "เริ่ม soak v4")
```bash
# §0 ตรวจก่อน (เหมือน v3): Dashboard md5, person_count_app.py f331fc90, mediamtx.yml 37cb9113, ICE ไม่มี 172.x,
#    disk ≥6GB, docker ครบ, CiRA online, ไม่มี collector/live_monitor/soak3 เก่า, light_log แถวล่าสุด on, nvpmodel 5W
ssh jetson ./ds-start --events on          # app โหมด soak (เฟรช → PtsGuard reset)
# รอ fps คงที่ แล้ว:
D=~/safety/docs/test-results/2026-10-2X_soak24h_v4
SOAK_DIR=$D SOAK_START=$(date +%s) SOAK_HOURS=24 bash ~/safety/tools/soak3_up.sh soak3
# PC live_monitor (interval 30, อยู่รอดหน้าต่างหลุด; หยุดเองที่ --minutes=1440 = ครบ 24h พอดีกับ teardown):
node tools/live_monitor/live_monitor.js --csv <PCdir>/live.csv --minutes 1440 --interval 30
# จบ 24 ชม.: soak_logger_v3 เรียก soak_end_v4.sh อัตโนมัติ → หยุด collector + ds-start events off + kill soak3 + เขียน soak_done.txt
```
teardown อัตโนมัติครบแล้ว (ข้อ 6). PC live_monitor หยุดเองที่ `--minutes`.

### เกณฑ์ผ่าน v4 (= เกณฑ์ v3 + เพิ่ม)
- ทุกเกณฑ์ v3 (uptime/fps/RSS/RAM/temp+throttle/กล้อง/CiRA/latency/disk/restart/power).
- **ภาพสด: ไม่มี stalled นานเกิน 30 วิ ตลอด 24 ชม.** (live.csv `stalled_total_s` ไม่พุ่ง; soak.csv `live_status` = ok เกือบตลอด).
- **ฟื้นเองหลังกล้องรีเซ็ตทุกครั้ง** (`pts_rebase` เพิ่มแล้วภาพกลับ ≤10 วิ; ไม่มีช่วง PTS 1ms/เฟรม).
- **teardown ครบ** (soak_done.txt = app events off + ไม่มี collector ค้าง).
- **brightness/rss_cira มีข้อมูลครบ 24 ชม.** (ไม่มีช่องว่างยาว; WARNING brightness = 0 หรืออธิบายได้).

### สิ่งที่ผู้ใช้ต้องทำระหว่าง soak v4
- เดินผ่านกล้องเป็นระยะ (ใส่/ไม่ใส่ PPE).
- บังคับกล้องรีเซ็ต 1 ครั้ง (Privacy Mode) เพื่อยืนยัน pts_rebase + ฟื้นเอง.
- จดเปิด/ปิดไฟด้วย `~/light`.

---

## ข้อ 2 — ICE เสนอ LAN IP ที่เบราว์เซอร์คนละที่ไปไม่ถึง — แก้แล้ว (2026-10-25)

**เหตุผลจริง (แก้ข้อสันนิษฐานเดิม "client isolation"):** PC ที่ดู Dashboard อยู่คนละสถานที่กับ Jetson และเข้าถึง Jetson ผ่าน Tailscale เท่านั้น. Wi-Fi ที่ PC ใช้ (Thongma/Thongma2) บังเอิญเป็นวง `192.168.1.x` เหมือนบ้านที่ Jetson อยู่. MediaMTX โฆษณา ICE candidate `<JETSON_LAN_IP>` → เบราว์เซอร์ลองต่อ `<JETSON_LAN_IP>` ในวง LAN ของตัวเอง ซึ่งไม่มีเครื่องนี้ → ต่อล้ม/ICE สลับไปมา (= อาการ "reconnect" ใน soak v3). ไม่ใช่ client isolation ที่เราเตอร์.

**แก้ (ผู้ใช้อนุมัติ):** ตัด `<JETSON_LAN_IP>` ออกจาก `webrtcAdditionalHosts` ใน `dashboard/mediamtx/mediamtx.yml` เหลือ `[<JETSON_TAILSCALE_IP>]`. เป็นการตั้งค่าที่ถูกต้องถาวรสำหรับการดูผ่าน Tailscale (ไม่ใช่ทางชั่วคราว).

**จดไว้:** ติดตั้งในโรงงานที่ดู Dashboard ผ่าน LAN ให้ใส่ IP LAN กลับเข้า `webrtcAdditionalHosts`.

- backup PC `mediamtx.yml.bak-20261025-225910`, Jetson `mediamtx.yml.bak-20261025-225910`.
- `docker restart mediamtx` (restart 2026-10-25 16:00:17 UTC = 23:00 local).
- ตรวจด้วย WHEP CDP probe จาก PC ผ่าน `http://<JETSON_TAILSCALE_IP>:8080`: `candIPs=["<JETSON_TAILSCALE_IP>"]` อย่างเดียว, `state=connected`, `framesDecoded=100` ใน 6 วิ → ภาพสดปกติ, ไม่มี candidate LAN.
- yml md5 ใหม่ `0dae11d9446cd385a92079aa549c17ee` (PC = Jetson ตรง).

## ข้อ 7 — ตรวจรวมทั้งระบบ

### 60 นาที (events off) — ผ่าน (2026-10-26)
live_monitor (เบราว์เซอร์ WHEP เหมือน Dashboard) interval 10 วินาที, 17:19:55→18:19:45 UTC (00:19→01:19 +07), 360 แถว.

| metric | ค่า | เกณฑ์ |
|---|---|---|
| connected | 360/360 แถว | ต่อตลอด ✓ |
| reconnects | 0 | 0 ✓ |
| stalled (เฟรมค้าง ≥5 วิ) | 0 แถว, stalled_total_s 0 | ไม่มี ✓ |
| TTFF | 0.86 วินาที | ≤3 ✓ |
| fps (instant) | เฉลี่ย 27.8 (ต่ำสุด 17.0 = แถวแรก warmup, สูงสุด 30.2) | ~ camera fps ✓ |
| decoded_fps_10s | เฉลี่ย 27.8; 262/360 แถว ≥27, มีเพียง 1 แถว <20 | คงที่ ✓ |
| packetsLost | 2 สะสมทั้งชั่วโมง | ต่ำ ✓ |

- **B-frames = 0** ยืนยันจาก config ไม่ใช่การเดา: `person_count_app.py` ตั้ง `nvv4l2h264enc profile=0` (Baseline) + `insert_vui=1` → MediaMTX ไม่ reorder/ไม่ตีความว่ามี B-frames. ไม่มี packet reorder ใน 60 นาที.
- `freezeCount` 224 / รวม 164.4 วินาที ตลอด 60 นาที = micro-freeze เฉลี่ย 0.73 วินาที/ครั้ง, **ไม่มีครั้งใด ≥5 วินาที** (stalled=0). สาเหตุ = กล้อง Tapo jitter/ช่วง 15 fps (ข้อจำกัดกล้อง, soak v3 plateau#2) ไม่ใช่ B-frame reorder และไม่ใช่ปัญหา pipeline.
- หลักฐาน: `item1_live_round3/` (รอบ 3) + CSV 60 นาที ที่ scratchpad `item7_live.csv` (360 แถว).

### walk test (events-on) — ข้าม, ยืนยันตอน soak v4
ข้ามการเดินผ่านกล้อง events-on 10 นาที: ระบบตรวจจับ/แจ้งเตือน (event via=cira + latency.csv) **ผ่านแล้วในรอบก่อน (soak v2/v3)** และการแก้ไขรอบ v4 ทั้งหมดอยู่ใน **เส้นทางภาพสด (live/WebRTC) เท่านั้น** ไม่แตะ path ตรวจจับ/ส่ง event. จะยืนยัน `event via=cira` + latency อีกครั้งในชั่วโมงแรกของ soak v4.
- dry run soak สั้น (ข้อ 6): **ผ่านแล้ว** (ไม่ต้องทำซ้ำ).

## ข้อ 9 — สรุปการแก้

| ปัญหา | พบใน | แก้อะไร | ก่อน | หลัง | ผล |
|---|---|---|---|---|---|
| 1 ภาพสดค้างถาวรหลังกล้องรีเซ็ต (PTS 1ms + SSRC เปลี่ยน) | v3 + พบใหม่ v4 | pts_guard.py rebase + `restart()` ต่อ timeline + ล็อก `rtph264pay ssrc` คงที่ + log pts stats | PTS 1ms/เฟรม ค้างถาวร; รีบูตกล้อง = wrong-SSRC flood ภาพค้าง F5 ไม่ขึ้น | unit 13/13; รอบ3 สะอาด: live_monitor framesDecoded กลับเพิ่ม 17:14:02, wrong-SSRC delta=0, mediamtx StartedAt/readyTime ไม่เปลี่ยน, Dashboard กลับเองไม่ F5 | **ผ่าน** (code+unit+deploy+live round3) |
| 3 Dashboard player | v2/v3 | first-frame 8วิ→ต่อใหม่, "ไม่มีภาพ Xวิ"+แย่, ไฟ "ภาพสด", ฝ่าฝืน <10 แสดงจำนวน | — | CDP: เขียว→เหลือง→แดง→เขียว, no error | **ผ่าน** |
| 4 live_monitor รายงาน connected ตอนค้าง | v3 | stall-detect 5วิ + reconnect + คอลัมน์ stalled | ค้างไม่รู้ตัว | pause→stalled=1 reconnect, กลับเอง | **ผ่าน** |
| 5 logger ว่าง (brightness/rss_cira) | v3 | brightness retry+WARNING, rss_cira max-match, +4 คอลัมน์ | brightness ว่าง, rss_cira ว่าง | rss_cira=142.9, 51 คอลัมน์ | **ผ่าน** |
| 6 teardown ไม่ครบ | v2/v3 | soak_end_v4.sh (detached) หยุด collector+events off+kill session | collector/app ค้าง | dry-run: session GONE, events off, 0 ค้าง | **ผ่าน** |
| 2 ICE เสนอ LAN IP ที่เบราว์เซอร์คนละที่ไปไม่ถึง | v3 | ตัด <JETSON_LAN_IP> ออก webrtcAdditionalHosts เหลือ [<JETSON_TAILSCALE_IP>] | ICE flap/reconnect | WHEP probe: candIPs=[<JETSON_TAILSCALE_IP>], connected, 100 frames/6วิ | **ผ่าน** |
| 7 ตรวจรวม 60น. (events off) | — | live_monitor เฝ้า stall + B-frames + fps | — | 360/360 connected, stalled 0, reconnect 0, TTFF 0.86, fps 27.8, B-frames 0 | **ผ่าน** |
| 7 walk test (events on) | — | event via=cira + latency | — | ข้าม (path ตรวจจับไม่แตะในรอบนี้) | **ยืนยันตอน soak v4** |

### ไฟล์ที่แก้ + md5 (sync PC=Jetson แล้ว)
- `perception/app/pts_guard.py` `25a3ca5b` (ใหม่; +restart()), `person_count_app.py` `810ad1d5` (+ssrc คงที่, _play ใช้ restart()), `test_pts_guard.py` `c6dfc92a` (ใหม่; 13 tests)
- `tools/soak_sample_v3.py` `08b01428`, `soak_logger_v3.sh` `5c9cc997`, `soak_slow_v3.sh` `1376901d`, `soak3_up.sh` `cae0c964`, `soak_end_v4.sh` `2c848de6` (ใหม่)
- `tools/live_monitor/live_monitor.js` + `whep_monitor.html` (PC-only)
- `dashboard/web/`: webrtc.js `6ee90de3`, ui.js `eaef66fd`, app.js `ed025d4e`, pages/dashboard.js `2ebd97ab`, index.html `952fac61`, css/app.css `bdde26a8`
- `dashboard/mediamtx/mediamtx.yml` `0dae11d9` (ข้อ 2 ตัด LAN IP; backup `.bak-20261025-225910`)
- `CLAUDE.md` (PC+Jetson) อัปเดตกฎ soak v4. backups: `.bak-<เวลา>` ทุกไฟล์, `web.bak-20261025-190346`.

### สิ่งที่ต้องให้ผู้ใช้ทำ
1. ~~ข้อ 1 live~~ — **เสร็จ 2026-10-26** (รีบูตกล้อง 2 รอบ; Privacy Mode ไม่รีเซ็ต stream จึงใช้รีบูตแทน). เจอ+แก้ปัญหา SSRC. ผ่าน.
2. ~~ข้อ 2 ตรวจเราเตอร์~~ — **ยกเลิก**: เหตุผลจริงคือ ICE LAN candidate ไม่ใช่ client isolation, แก้ที่ yml แล้ว.
3. ~~ข้อ 7 60 นาที~~ — **เสร็จ 2026-10-26** (connected 360/360, stalled 0, reconnect 0, B-frames 0). walk test events-on **ข้าม** → ยืนยัน event via=cira ในชั่วโมงแรก soak v4.

### หมายเหตุ (ไม่แก้)
- RSS +5 MB/ชม. เป็น native ไม่นิ่ง → แนะนำใช้งานจริง: รีสตาร์ท app วันละครั้งช่วงไม่มีคน (`./ds-stop; ./ds-start --events on`).
- กล้อง Tapo ส่ง 15 fps บางช่วงโดยไม่ทราบสาเหตุ (soak v3 plateau#2) → ข้อจำกัดของกล้อง.
- เบลอหน้าอัตโนมัติ (haar) จับได้ 7/83 ที่เหลือใช้ fallback เบลอหัวจาก bbox → ผู้ใช้ตรวจรูปเองก่อนใช้.

### end-state (ตรวจ 2026-10-26 01:2x +07)
- app: `person_count_app.py --run-name live_20261026_0019 --events off` (ทำงาน, events off) ✓
- ไม่มี collector/soak3/live_monitor ค้าง (Jetson `pgrep` = none; PC ไม่มี node/headless chrome) ✓ — tmux เหลือเฉพาะ `cira-gui` + `ds` (ไม่แตะ)
- docker: recorder / dashboard / mediamtx / mosquitto — up ครบ ✓
- mediamtx yml `0dae11d9` (ข้อ 2 ตัด LAN IP, restart แล้ว), Dashboard โค้ด v4
- พร้อมเริ่ม soak v4 (รอคำสั่ง "เริ่ม soak v4")
