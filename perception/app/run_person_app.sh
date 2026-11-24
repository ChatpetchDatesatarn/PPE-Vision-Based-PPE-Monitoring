#!/bin/bash
# Start person_count_app.py with the camera credentials from ~/safety/.cam.env (sourced only, never printed)
# plus tegrastats; log in <out-dir>/<run>.log, every line passed through the rtsp://***@ / literal-secret redaction.
#
# Usage (run in tmux "ds"):
#   bash run_person_app.sh <run-name> [person_count_app.py options...]
#   e.g. bash run_person_app.sh A_iou --seconds 180 --tracker iou --rtsp-bind 0.0.0.0
cd "$(dirname "$0")"
RUN=$1; shift
[ -n "$RUN" ] || { sed -n '5,7p' "$0"; exit 1; }
OUT=../test/results/cam
mkdir -p "$OUT"

ENVF="$HOME/safety/.cam.env"
[ -f "$ENVF" ] || { echo "missing $ENVF"; exit 1; }
set +x
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$CAM_IP" ] && [ -n "$CAM_USER" ] && [ -n "$CAM_PASS" ] || { echo "CAM_IP/CAM_USER/CAM_PASS not all set in .cam.env"; exit 1; }
# camera may have a new IP (e.g. phone hotspot): find it and override CAM_IP for this process only (.cam.env unchanged)
case " $* " in *" --stream 2 "*) export CAM_STREAM=2 ;; esac
NEW_IP=$(bash "$HOME/safety/perception/cam_discover.sh") && CAM_IP=$NEW_IP
export CAM_IP CAM_USER CAM_PASS

# mawk (Ubuntu default) block-buffers its input from a pipe, so the log would only fill at the end; -W interactive = line by line
AWK="awk"; awk -W version 2>&1 | grep -q mawk && AWK="awk -W interactive"
redact() {
  $AWK 'function rep(s, t, r,   i, o) { o = ""; if (t == "") return s
         while ((i = index(s, t)) > 0) { o = o substr(s, 1, i - 1) r; s = substr(s, i + length(t)) }
         return o s }
       { l = rep($0, ENVIRON["CAM_PASS"], "***"); l = rep(l, ENVIRON["CAM_USER"], "***")
         gsub(/rtsp:\/\/[^@\/ ]*@/, "rtsp://***@", l); print l; fflush() }'
}

LOG=$OUT/$RUN.log; TEG=$OUT/$RUN.tegra
SU=""; sudo -n true 2>/dev/null && SU="sudo -n"
$SU rm -f "$TEG"
# tegrastats ends by itself 24 h later at the latest; normally stopped below
$SU timeout 86400 tegrastats --interval 1000 --logfile "$TEG" &
TP=$!

env -u PYTHONPATH python3 -u person_count_app.py --run-name "$RUN" --out-dir "$OUT" "$@" 2>&1 | redact | tee "$LOG"
RC=${PIPESTATUS[0]}
$SU pkill -f -- "--logfile $TEG" 2>/dev/null; wait $TP 2>/dev/null
echo "rc=$RC end $(date '+%T')" | tee -a "$LOG"
if grep -rqF -e "$CAM_PASS" "$OUT" 2>/dev/null; then echo "!!! password found in $OUT — results must be scrubbed"; else echo "secret check: clean"; fi
echo "=== PERSON-APP-DONE $RUN"
