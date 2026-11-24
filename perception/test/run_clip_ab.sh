#!/bin/bash
# Same recorded clip through 5 model setups (all with --debug-objs), one after the other, 20 s cooldown between.
#   a = COCO alone, interval 0            b = ppe3_416 alone, interval 0     c = ppe3_416 alone, interval 1
#   d = COCO → ppe3_hv (two models)       e = ppe3_hv → COCO (two models, order swapped; gie ids unchanged)
# Usage (run in tmux "ds"):  bash run_clip_ab.sh <clip.mp4> <prefix>      e.g. ... results/cam/clean_ppe_01.mp4 C1
cd "$(dirname "$0")/../app"
CLIP=$(readlink -f "$1"); PRE=$2
[ -f "$CLIP" ] && [ -n "$PRE" ] || { sed -n '5p' "$0"; exit 1; }
COCO=../test/config_infer_cam_person.txt
PPE=../models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_416.txt
HV=../models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_hv.txt
COMMON="--tracker iou --source-file $CLIP --debug-objs"

run() {   # <suffix> <app options...>
  local name=${PRE}$1; shift
  echo "=== $name: $* ($(date '+%T'))"
  bash run_person_app.sh "$name" $COMMON "$@" > /dev/null 2>&1
  grep -E 'stop:|summary' "../test/results/cam/$name.log" | cut -c1-160
  sleep 20
}
run a --interval 0 --person-config $COCO
run b --interval 0 --person-config $PPE
run c --interval 1 --person-config $PPE
run d --interval 0 --person-config $COCO --ppe-config $HV
run e --interval 0 --person-config $COCO --ppe-config $HV --ppe-first
echo "=== CLIP-AB-DONE $PRE $(date '+%T')"
