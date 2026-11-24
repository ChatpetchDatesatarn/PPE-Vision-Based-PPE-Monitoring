#!/bin/bash
# COCO 416x256 vs 320x192 on the recorded clip, file (as fast as possible) and real time (--realtime), all with
# --debug-objs, one after the other, 20 s cooldown between:
#   Ra   = COCO 416 alone, real time           Rd   = COCO 416 → ppe3_hv, real time
#   a320 = COCO 320 alone, file                d320 = COCO 320 → ppe3_hv, file        Rd320 = d320 in real time
# Usage (run in tmux "ds"):  bash run_clip_320.sh <clip.mp4> <prefix>      e.g. ... results/cam/clean_ppe_01.mp4 C1
cd "$(dirname "$0")/../app"
CLIP=$(readlink -f "$1"); PRE=$2
[ -f "$CLIP" ] && [ -n "$PRE" ] || { sed -n '6p' "$0"; exit 1; }
C416=../test/config_infer_cam_person.txt
C320=../test/config_infer_cam_person_320.txt
HV=../models/yolov8n_ppe3_416/config_infer_yolov8n_ppe3_hv.txt
COMMON="--tracker iou --interval 0 --source-file $CLIP --debug-objs"

run() {   # <suffix> <app options...>
  local name=${PRE}$1; shift
  echo "=== $name: $* ($(date '+%T'))"
  bash run_person_app.sh "$name" $COMMON "$@" > /dev/null 2>&1
  grep -E 'stop:|deserialized|Building' "../test/results/cam/$name.log" | cut -c1-160
  sleep 20
}
run Ra    --person-config $C416 --realtime
run Rd    --person-config $C416 --ppe-config $HV --realtime
run a320  --person-config $C320
run d320  --person-config $C320 --ppe-config $HV
run Rd320 --person-config $C320 --ppe-config $HV --realtime
echo "=== CLIP-320-DONE $PRE $(date '+%T')"
