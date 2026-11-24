#!/bin/bash
# Record the Tapo stream1 H.264 as-is into an mp4 (no decode, no inference) for repeatable app tests.
# Credentials come from ~/safety/.cam.env (sourced only, passed as rtspsrc properties, never in the URL or a log).
# The mp4 stays on the Jetson: not committed, not copied off the machine (*.mp4 is in .gitignore).
#
# Usage (run in tmux "ds"):
#   bash record_clip.sh <out.mp4> [seconds]      # default 90 s; refuses to overwrite an existing file
cd "$(dirname "$0")"
OUTF=$1; SECS=${2:-90}
[ -n "$OUTF" ] || { sed -n '6,7p' "$0"; exit 1; }
[ -e "$OUTF" ] && { echo "exists, not overwritten: $OUTF"; exit 1; }

ENVF="$HOME/safety/.cam.env"
[ -f "$ENVF" ] || { echo "missing $ENVF"; exit 1; }
set +x
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$CAM_IP" ] && [ -n "$CAM_USER" ] && [ -n "$CAM_PASS" ] || { echo "CAM_IP/CAM_USER/CAM_PASS not all set in .cam.env"; exit 1; }
export CAM_USER CAM_PASS

redact() {
  awk 'function rep(s, t, r,   i, o) { o = ""; if (t == "") return s
         while ((i = index(s, t)) > 0) { o = o substr(s, 1, i - 1) r; s = substr(s, i + length(t)) }
         return o s }
       { l = rep($0, ENVIRON["CAM_PASS"], "***"); l = rep(l, ENVIRON["CAM_USER"], "***")
         gsub(/rtsp:\/\/[^@\/ ]*@/, "rtsp://***@", l); print l; fflush() }'
}

echo "=== record rtsp://***@${CAM_IP}:554/stream1 -> $OUTF, $SECS s (start $(date '+%T'))"
# -e: SIGINT from timeout becomes EOS, so mp4mux writes its index and the file is playable
timeout -s INT "$SECS" env -u PYTHONPATH gst-launch-1.0 -e \
  rtspsrc location="rtsp://${CAM_IP}:554/stream1" user-id="$CAM_USER" user-pw="$CAM_PASS" protocols=tcp latency=200 \
  ! rtph264depay ! h264parse ! mp4mux ! filesink location="$OUTF" 2>&1 | redact | grep -v '^Progress\|^0:'
echo "=== end $(date '+%T'), rc=${PIPESTATUS[0]}"
ls -l "$OUTF"
env -u PYTHONPATH gst-discoverer-1.0 "$OUTF" 2>&1 | grep -i 'duration\|video\|width\|height\|frame rate' | head -6
echo "=== RECORD-DONE $OUTF"
