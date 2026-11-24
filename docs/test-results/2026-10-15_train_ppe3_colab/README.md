# Training PPE 3 classes (person, helmet, vest) — Colab A100, 2026-10-15

Notebook: `Desktop\PPE Detection\train_ppe3_jetson.ipynb` (with YOLOv8x person pseudo-labels, t1_boot/glove/goggle dropped)
Ultralytics 8.4.177, imgsz 416, export 416x256 (H 256, W 416), opset 12, DeepStream-Yolo 2894babce8e7

| run | epochs | GFLOPs@416x256 | params M | test mAP50 | mAP50-95 | person | helmet | vest | night(gray) mAP50 | helmet night | best_conf |
|---|---|---|---|---|---|---|---|---|---|---|---|
| yolov8n_ppe3_416 | 150 (full) | 2.28 | 3.14 | 0.876 | 0.634 | 0.932 | 0.816 | 0.880 | 0.839 | 0.789 | 0.52 |
| yolo11n_ppe3_416 | 137 (early stop, best 107) | 1.70 | 2.61 | 0.882 | 0.633 | 0.938 | 0.819 | 0.891 | 0.842 | 0.798 | 0.38 |

Valid set: v8n mAP50 0.896 (helmet R 0.803), 11n mAP50 0.892 (helmet R 0.843).

Notes
- Accuracy is a tie (differences < 0.01). Choice depends on Jetson: TensorRT 8.2 engine build + fps.
- Night vest recall is weak (gray: v8n 0.73, 11n 0.68). Gray copies are not real IR; collect real Tapo night frames → extra_tapo.zip.
- Person scores are partly measured against YOLOv8x pseudo-labels, so they may be a bit optimistic.
- ONNX md5: yolov8n efdd6887f84417d4843857238ca1a77f, yolo11n 64b8e766c541b40dfb8dcf7bdd053427
- Files: perception/models/<run>/ (onnx, pt, labels.txt, config_infer_<run>.txt, info.json), zips in models/archive/
