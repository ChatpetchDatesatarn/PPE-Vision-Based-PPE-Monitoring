#!/bin/bash
# PPE 3-class fps benchmark, same method as the COCO baseline (docs/test-results/2026-10-15_ds_yolov8n_coco_5W):
# sample_720p.mp4 loop, fakesink sync=0, 70 s per round, 30 s cooldown before each round, tegrastats 1 s
# Engines must already exist (built in a separate run). Run in tmux ds.
# Usage: bash run_ppe3_bench.sh [run ...]   (default: yolov8n_ppe3_416 yolo11n_ppe3_416)
cd "$(dirname "$0")"
RUNS=${*:-yolov8n_ppe3_416 yolo11n_ppe3_416}
for r in $RUNS; do
  for i in 0 1; do
    sleep 30
    bash run_smoke.sh ${r}_i$i 70 ds_${r}_i$i.txt
  done
done
echo "=== BENCH-DONE"
