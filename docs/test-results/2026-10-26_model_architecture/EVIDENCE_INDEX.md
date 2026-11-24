# EVIDENCE_INDEX — รายงานสถาปัตยกรรมโมเดล (2026-10-26)

ทุกตัวเลข/ข้อความในรายงานอ้างด้วยรหัส `[E-xx]`. ไฟล์หลักฐานอยู่ใน `evidence/` (คัดลอกตรง ห้ามแก้เนื้อหา).
Jetson = `ssh -o HostName=<JETSON_TAILSCALE_IP> jetson` (อ่านอย่างเดียว ระหว่าง soak v4). sha256 ของทุกไฟล์อยู่ท้ายเอกสาร.

| รหัส | ข้อความ/ตัวเลขในรายงาน | ไฟล์ใน evidence/ | บรรทัด/cell | วิธีตรวจซ้ำ (คำสั่ง) |
|---|---|---|---|---|
| E-01 | config โมเดลคน (COCO 320×192, filter 1–79, thr 0.35) | configs/config_infer_cam_person_320.txt | ทั้งไฟล์ | `cat evidence/configs/config_infer_cam_person_320.txt` |
| E-02 | config helmet/vest (ppe3, interval=1, filter 0, thr 0.40/0.35) | configs/yolov8n_ppe3_hv.txt | ทั้งไฟล์ | `cat evidence/configs/yolov8n_ppe3_hv.txt` |
| E-03 | comment way A (:15), pipeline (:4), assign (:582), put (:514), smoother update (:594) | code/person_count_app.py | 4,15,356,514,578–594,1177–1186 | `sed -n '14,21p;1177,1186p;510,515p;578,595p' evidence/code/person_count_app.py` |
| E-04 | เกณฑ์จับคู่ helmet 0–35% / vest 20–75% / tie-break | code/ppe_assign.py | 11–37 | `sed -n '11,37p' evidence/code/ppe_assign.py` |
| E-05 | อ่านกรอบ ppe ก่อน tracker + จับคู่ด้วย key (frame_num,pts) | code/ppe_pretrack.py | ทั้งไฟล์ (38–41) | `cat evidence/code/ppe_pretrack.py` |
| E-06 | PpeSmoother WINDOW 20 / ON 0.30 / OFF 0.10 / MIN 8 | code/ppe_smooth.py | 13–16 | `sed -n '13,16p' evidence/code/ppe_smooth.py` |
| E-07 | ตัดตอนโค้ดสำคัญพร้อมเลขบรรทัด | code/code_excerpts.md | ทั้งไฟล์ | `cat evidence/code/code_excerpts.md` |
| E-08 | md5 onnx/engine/config/py บน Jetson (ตัวโหลดจริง) | md5_jetson.txt | ทั้งไฟล์ | `ssh … 'cd ~/safety/perception && md5sum …'` (คำสั่งอยู่หัวไฟล์) |
| E-09 | md5 ฝั่ง PC + ตรงกันไหม (ppe3 onnx/config/py ตรง; engine ไม่มีบน PC) | md5_pc.txt | ทั้งไฟล์ | `md5sum perception/{models,test,app}/…` |
| E-10 | process รันจริง ไม่มี override + log โหลด engine | process/running_process.txt | ทั้งไฟล์ | `ssh … 'ps -o pid,lstart,args -C python3 | grep person_count_app'` |
| E-11 | สภาพแวดล้อมเทรน, mAP, pseudo-label, night recall | training/train_ppe3_colab_README.md | ทั้งไฟล์ | `cat evidence/training/train_ppe3_colab_README.md` |
| E-12 | ตารางเทียบ v8n/11n (mAP50 0.876/0.882, helmet 0.816, vest 0.880) | training/compare_models.csv | ทั้งไฟล์ | `cat evidence/training/compare_models.csv` |
| E-13 | รวม 7 คลาสเป็น merged/ | dataset/merge_ppe.py | ทั้งไฟล์ | `cat evidence/dataset/merge_ppe.py` |
| E-14 | remap 3 คลาส, ตัด 4 คลาส, bg ≤10%, gray 15% | dataset/make_ppe3.py | 1–10 | `sed -n '1,10p' evidence/dataset/make_ppe3.py` |
| E-15 | path/นิยาม train/val/test, nc=7 | dataset/data.yaml | ทั้งไฟล์ | `cat evidence/dataset/data.yaml` |
| E-16 | สรุป merged ต่อคลาส (ยืนยันกับ E-21) | dataset/summary.txt | ทั้งไฟล์ | `cat evidence/dataset/summary.txt` |
| E-17 | 4 ชุด Roboflow + CC BY 4.0 | dataset/README.txt | ทั้งไฟล์ | `cat evidence/dataset/README.txt` |
| E-18 | notebook เทรน (ไม่มี output cells) | dataset/train_ppe3_jetson.ipynb | cell 2,6,10,12,14 | `python -c "import json;…"` (ดูว่า outputs ว่าง) |
| E-19 | merged3 stats รุ่นเก่า (train 3245/bg324/gray486, valid 744, test 468) | dataset/merged3_stats_OLD_RUN.json | ทั้งไฟล์ | `cat evidence/dataset/merged3_stats_OLD_RUN.json` |
| E-20 | ชื่อ/เวอร์ชัน/license 4 ชุด | dataset/roboflow_sources/test1..4/ | README.* | `cat evidence/dataset/roboflow_sources/*/README.roboflow.txt` |
| E-21 | นับ merged จริง: train 4771/valid 744/test 468 + กรอบต่อคลาส | counts/count_merged.py + count_merged_output.txt | output | `python evidence/counts/count_merged.py "<merged>"` |
| E-22 | อนุมาน merged3: keep/drop/pseudo-target จาก merged | counts/derive_merged3.py + derive_merged3_output.txt | output | `python evidence/counts/derive_merged3.py "<merged>"` |
| E-23 | way A: COCO320→ppe3_hv 32.44 fps, ไม่ขวางกัน | way_a/clip_ab_README.md | 3,7,10 | `sed -n '1,12p' evidence/way_a/clip_ab_README.md` |
| E-24 | default --person-config/--ppe-config เป็น way A | way_a/stack_v3_migration_README.md | 58 | `sed -n '55,60p' evidence/way_a/stack_v3_migration_README.md` |

## sha256 ของทุกไฟล์ใน evidence/
(ตรวจซ้ำ: `cd docs/test-results/2026-10-26_model_architecture && find evidence -type f -exec sha256sum {} \;`)

```
66dd4ada0e520ac8c611a6af267ad957f9cb3fcc247b8f367e1c6a2b7240f27d *code/code_excerpts.md
020fb237f5ecdce372c80dd7c917ad11bc187b64374d7e5a3539142bfa4d203a *code/person_count_app.py
d5f67a8b2c533a9e90bc17c08bcfa3046582a895ae3edd71a5bbc2949e00d4df *code/ppe_assign.py
c055d55cde7f4ed697cbc2bd3e4975c6af4a6740dd8b222baffcf27ec8eb9e8f *code/ppe_pretrack.py
92da780f0c4e956160b9b3dc9ebb1efd76f5b80112fe2a4760973272986f3dab *code/ppe_smooth.py
8ea86337f2ab979358bedf7155cf082a605a24f2dfbb11f231196172e5971eb2 *configs/config_infer_cam_person_320.txt
d4b17a365565cd255d2021a19c50ca230220aae8ebebff0fb1e6e1362820a2e9 *configs/yolov8n_ppe3_hv.txt
9daf77aaf9a734d9dea4e34ecc25430f0bad8eb35c07ac0ac6dee1c4fdd06f85 *counts/count_merged.py
23eafac1cc89844c3e8f964cea3599b36b62dc01a3dbd91c3b0f7383932e0bd1 *counts/count_merged_output.txt
ebbd99b0c0f4ec97f8bcbe3448cde95dc143307f19462fc0667a79b87e5ac244 *counts/derive_merged3.py
54a903ab5fad3c137c939203355f258f9ff72d6b8f9eb1766e4ca31a21384f65 *counts/derive_merged3_output.txt
34e4973bd26c28a7d75a9c011a63d2848dd7f7b671c236081621c3e6416a27b9 *dataset/README.txt
f43751ea842dd63853a6801041912f99f49a91a893d06cba17ceda3c806b8e99 *dataset/classes.txt
f8ce56732a88ae4328164a456e753f4bf6f45c53337c4e55cbc07627644d5919 *dataset/data.yaml
e51512234f25cb68479c3583288b4685c3d4ae815d0cf9c9ac1ebc4e46b3c156 *dataset/make_ppe3.py
14739b302c29b5fd71434a9c9498cdbe087104238a31f1f84c0b22e771b52d18 *dataset/merge_ppe.py
978b368bf2fee77877ea231b7eef2bd968a9bd4d3d974dc30fa16ecc804f77e4 *dataset/merged3_stats_OLD_RUN.json
42a0be321200584217b9635beaa46c844a20b68e0467ffac9a9da7f4e75e2cfe *dataset/roboflow_sources/test1/README.dataset.txt
c5492f7bc63082a79642af84a160a29a1abe0e0c6fd2f5ff2fb55aeeba1cf408 *dataset/roboflow_sources/test1/README.roboflow.txt
45f820639c6f89daa12c06a12a58ac9edeaf8c78be3f3a2996079110e6ecbebe *dataset/roboflow_sources/test2/README.dataset.txt
238d0c7b0c67ed7095b8bd2441583359b9de37054915d984980bbf1307796d7e *dataset/roboflow_sources/test2/README.roboflow.txt
7f875f8edf68faff89c0aeddead9ed69e64a7dbaea88769bd8389a58e26fbc56 *dataset/roboflow_sources/test3/README.dataset.txt
2511da23f6c56a32805c0e37eceffe1331a03ce144e5e46c8bb71d35ee01c717 *dataset/roboflow_sources/test3/README.roboflow.txt
e43d5b55a86163f04b57d60c6a48ae41778fe77c0660d504963a6b08e642ecb6 *dataset/roboflow_sources/test4/README.dataset.txt
6f42c91df4a6ef74ff494ddf6b6de44ecb5a612eab766424fc7be0d20fe6380a *dataset/roboflow_sources/test4/README.roboflow.txt
7e635cdb5b925db4f92168dc02300cfe08904206cded3eabbf518923da829c23 *dataset/summary.txt
e97c270890a21b7cbe7c89549caf2e9bc17b82e21f03260dddd67f5accad783c *dataset/train_ppe3_jetson.ipynb
30034063068a9dbb55ec1e1dc75409ca96bbf13c5523c086f2b7c2ae15e3e076 *md5_jetson.txt
f5fca6580cc6c7bff4473668d7d9d93203070daad1f9e97edf40e2565b793c52 *md5_pc.txt
1deb6a3efbb1591a7f1e1d198dd0266d920c542e9bd31fc3a0e22a8cc85e8dc8 *process/running_process.txt
2cef6f1ad92f29bc2876d34eab3fbe0f05f6033a0e4d195a92cc104ac7ceb618 *training/compare_models.csv
c6be72a66a50f06e4414d6ed90564e6ea43b49a94c789101aef1df04a16da067 *training/train_ppe3_colab_README.md
92453ba5d714e72b8895f13688f94b6a2941fa9a651281cb6d4363de29f8bf3b *way_a/clip_ab_README.md
e3f10ca3c9f64c7788523ebb4f0135cd72dc9f31e98108e8df6566630b1f7a71 *way_a/stack_v3_migration_README.md
```
