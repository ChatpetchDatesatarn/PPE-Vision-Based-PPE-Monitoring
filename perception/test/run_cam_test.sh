#!/bin/bash
# Live Tapo test: RTSP stream1 → NVDEC → mux 1280x720 → nvinfer (YOLOv8n person) → tracker → OSD → NVENC RTSP :8555/ds-test
# Credentials come from ~/safety/.cam.env (sourced only, never printed). The real config with the camera URI is written to
# /dev/shm/ds_cam_run.txt (chmod 600 before writing) and deleted on exit. Every deepstream-app line passes the
# rtsp://***@ sed before it reaches the screen or a log.
#
# Usage (run in tmux "ds"):
#   bash run_cam_test.sh <interval> <iou|nvdcf> <seconds> [tag] [record]
#     tag    = name for results/cam/<tag>.* (default cam_i<interval>_<tracker>)
#     record = also write results/cam/<tag>.mp4 (sink1)
cd "$(dirname "$0")"
TEST_DIR=$(pwd)
OUT=results/cam
mkdir -p "$OUT"

INTERVAL=$1; TRK=$2; SECS=$3; TAG=${4:-cam_i${1}_${2}}; REC=$5
case "$INTERVAL" in ''|*[!0-9]*) sed -n '7,10p' "$0"; exit 1 ;; esac
case "$SECS" in ''|*[!0-9]*) sed -n '7,10p' "$0"; exit 1 ;; esac
SAMPLES=/opt/nvidia/deepstream/deepstream-6.0/samples/configs/deepstream-app
case "$TRK" in
  iou)   TRK_CFG=$SAMPLES/config_tracker_IOU.yml ;;
  nvdcf) TRK_CFG=$SAMPLES/config_tracker_NvDCF_perf.yml ;;
  *) sed -n '7,10p' "$0"; exit 1 ;;
esac
SINK1=0; MP4=$TEST_DIR/$OUT/$TAG.mp4
[ "$REC" = record ] && SINK1=1

ENVF="$HOME/safety/.cam.env"
[ -f "$ENVF" ] || { echo "missing $ENVF"; exit 1; }
set +x
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$CAM_IP" ] && [ -n "$CAM_USER" ] && [ -n "$CAM_PASS" ] || { echo "CAM_IP/CAM_USER/CAM_PASS not all set in .cam.env"; exit 1; }

RUNCFG=/dev/shm/ds_cam_run.txt
LOG=$OUT/$TAG.log; TEG=$OUT/$TAG.tegra
trap 'rm -f "$RUNCFG"' EXIT
trap 'exit 130' INT TERM HUP

# percent-encode user/password so characters like @ : / # in them cannot break the URI
export CAM_USER CAM_PASS
ENC_USER=$(env -u PYTHONPATH python3 -c 'import os, urllib.parse as u; print(u.quote(os.environ["CAM_USER"], safe=""))')
ENC_PASS=$(env -u PYTHONPATH python3 -c 'import os, urllib.parse as u; print(u.quote(os.environ["CAM_PASS"], safe=""))')
export CAM_URI="rtsp://${ENC_USER}:${ENC_PASS}@${CAM_IP}:554/stream1"
export TEST_DIR INTERVAL TRK_CFG SINK1 MP4

# create the file 600 first, then fill it; literal (not regex) replacement, so no special character in the URI is interpreted
umask 077
: > "$RUNCFG"; chmod 600 "$RUNCFG"
awk 'function rep(s, t, r,   i, o) { o = ""; while ((i = index(s, t)) > 0) { o = o substr(s, 1, i - 1) r; s = substr(s, i + length(t)) } return o s }
     { l = $0
       l = rep(l, "__CAM_URI__", ENVIRON["CAM_URI"]); l = rep(l, "__TEST_DIR__", ENVIRON["TEST_DIR"])
       l = rep(l, "__INTERVAL__", ENVIRON["INTERVAL"]); l = rep(l, "__TRACKER_CFG__", ENVIRON["TRK_CFG"])
       l = rep(l, "__SINK1_ENABLE__", ENVIRON["SINK1"]); l = rep(l, "__OUTPUT_FILE__", ENVIRON["MP4"])
       print l }' ds_cam_template.txt > "$RUNCFG"
umask 022
# comments in the template name the placeholders, so only check setting lines
grep -v '^#' "$RUNCFG" | grep -q '__[A-Z_0-9]*__' && { echo "placeholder left in $RUNCFG"; exit 1; }

echo "=== $TAG interval=$INTERVAL tracker=$TRK ${SECS}s record=$SINK1 rtsp://***@${CAM_IP}:554/stream1 ($(date '+%F %T'))" | tee "$LOG"

# tegrastats shows NVDEC/NVENC only as root; timeout ends it even if the pkill below misses
SU=""; sudo -n true 2>/dev/null && SU="sudo -n"
$SU rm -f "$TEG"
$SU timeout $((SECS + 20)) tegrastats --interval 1000 --logfile "$TEG" &
TP=$!

# --foreground: deepstream-app reads keyboard commands from the TTY (SIGTTIN without it)
timeout --foreground -s INT "$SECS" env -u PYTHONPATH deepstream-app -c "$RUNCFG" 2>&1 \
  | sed -u -E 's#rtsp://[^@ ]*@#rtsp://***@#g' | while IFS= read -r l; do printf '%(%T)T %s\n' -1 "$l"; done | tee -a "$LOG"
RC=${PIPESTATUS[0]}
$SU pkill -f -- "--logfile $TEG" 2>/dev/null; wait $TP 2>/dev/null
echo "rc=$RC end $(date '+%T')" | tee -a "$LOG"

# final check: neither the password nor the encoded password may be in the results
if grep -rqF -e "$CAM_PASS" -e "$ENC_PASS" "$OUT" 2>/dev/null; then echo "!!! password found in $OUT — results must be scrubbed"; else echo "secret check: clean"; fi
echo "=== CAM-TEST-DONE $TAG"
