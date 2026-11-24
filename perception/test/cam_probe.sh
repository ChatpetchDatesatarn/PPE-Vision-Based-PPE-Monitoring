#!/bin/bash
# Probe the Tapo C200C RTSP camera from the Jetson; results in ./results/cam/
# Credentials come from ~/safety/.cam.env (CAM_IP, CAM_USER, CAM_PASS) — sourced only, never printed.
# Every output line goes through redact(): user/password -> ***, so logs only show rtsp://***@<ip>/streamN
#
# Usage (run in tmux "ds"):
#   bash cam_probe.sh ping                         # a) 20 pings
#   bash cam_probe.sh discover                     # b) gst-discoverer on stream1 + stream2
#   bash cam_probe.sh fps <1|2> <tcp|udp> [secs]   # c/d) NVDEC decode fps + tegrastats (default 60 s)
#   bash cam_probe.sh reconnect <1|2> <tcp|udp> [secs]   # e) same with a timestamp on every line (default 150 s)
#   bash cam_probe.sh videowatch [1|2] [secs]      # e) 5 s pulls (tcp) until >= 10 video buffers arrive (default 1, 240 s)
#   bash cam_probe.sh all                          # a + b + c (tcp 1,2) + d (udp 1,2)
cd "$(dirname "$0")"
OUT=results/cam
mkdir -p "$OUT"

ENVF="${CAM_ENV:-$HOME/safety/.cam.env}"   # CAM_ENV = override for dry tests only
[ -f "$ENVF" ] || { echo "missing $ENVF"; exit 1; }
set +x
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$CAM_IP" ] && [ -n "$CAM_USER" ] && [ -n "$CAM_PASS" ] || { echo "CAM_IP/CAM_USER/CAM_PASS not all set in .cam.env"; exit 1; }
export CAM_USER CAM_PASS

# literal (not regex) replacement of user and password, then mask any user-info left in rtsp URLs
redact() {
  awk 'function rep(s, t, r,   i, o) { o = ""; if (t == "") return s
         while ((i = index(s, t)) > 0) { o = o substr(s, 1, i - 1) r; s = substr(s, i + length(t)) }
         return o s }
       { l = rep($0, ENVIRON["CAM_PASS"], "***"); l = rep(l, ENVIRON["CAM_USER"], "***")
         gsub(/rtsp:\/\/[^@\/ ]*@/, "rtsp://***@", l); print l; fflush() }'
}
url()     { echo "rtsp://${CAM_USER}:${CAM_PASS}@${CAM_IP}:554/stream$1"; }   # never echo to a log
safeurl() { echo "rtsp://***@${CAM_IP}:554/stream$1"; }
stamp()   { while IFS= read -r l; do printf '%(%T)T %s\n' -1 "$l"; done; }

do_ping() {
  echo "=== ping $CAM_IP x20 ($(date '+%F %T'))"
  ping -c 20 -i 0.5 "$CAM_IP" 2>&1
}

do_discover() {
  for s in 1 2; do
    echo "=== gst-discoverer $(safeurl $s) ($(date '+%F %T'))"
    timeout -k 5 30 env -u PYTHONPATH gst-discoverer-1.0 -v -t 20 "$(url $s)" 2>&1
    echo "rc=$?"
  done
}

# summary from tegrastats: mean CPU% of online cores, max, and NVDEC samples (non-zero = decoder active)
tegra_summary() {
  awk '{ n = 0; s = 0
         if (match($0, /CPU \[[^]]*\]/)) { c = substr($0, RSTART + 5, RLENGTH - 6); k = split(c, a, ",")
           for (i = 1; i <= k; i++) if (a[i] != "off") { split(a[i], b, "%"); s += b[1]; n++ } }
         if (n) { cpu = s / n; tot += cpu; cnt++; if (cpu > mx) mx = cpu }
         if (match($0, /NVDEC [0-9]+/)) { nv++; f = substr($0, RSTART + 6, RLENGTH - 6) + 0; if (f > nvmax) nvmax = f }
         if (match($0, /GR3D_FREQ [0-9]+%/)) { g = substr($0, RSTART + 10, RLENGTH - 11) + 0; gt += g }
         if (match($0, /RAM [0-9]+/)) { r = substr($0, RSTART + 4, RLENGTH - 4) + 0; if (r > rmax) rmax = r } }
       END { if (cnt) printf "tegrastats: samples=%d CPU%%(online cores) mean=%.1f max=%.1f  NVDEC active=%d/%d max=%dMHz  GPU%% mean=%.1f  RAM max=%dMB\n",
             cnt, tot / cnt, mx, nv, cnt, nvmax, gt / cnt, rmax }' "$1"
}

# fpsdisplaysink -v prints "last-message = rendered: R, dropped: D, current: C, average: A"
fps_summary() {
  grep -o 'rendered: [0-9]*, dropped: [0-9]*, current: [0-9.]*, average: [0-9.]*' "$1" | tail -1 | sed 's/^/last: /'
  grep -o 'current: [0-9.]*' "$1" | awk '{ v = $2 + 0; if (NR > 4) { s += v; n++; if (min == "" || v < min) min = v; if (v > mx) mx = v } }
      END { if (n) printf "current fps (first 2 s dropped): n=%d mean=%.2f min=%.2f max=%.2f\n", n, s / n, min, mx }'
  printf 'ERROR lines: %s  WARNING lines: %s\n' "$(grep -c 'ERROR' "$1")" "$(grep -c 'WARNING' "$1")"
}

# run beside "reconnect" to time when the camera serves video again after a power loss
# only a buffer count (grep -c) leaves the gst pipe, so the -v output with credentials is never stored
do_videowatch() {   # $1 stream, $2 max secs
  local s=$1 end=$((SECONDS + $2)) t n log="$OUT/videowatch_stream$1.log"
  echo "=== videowatch $(safeurl $s) max ${2}s ($(date '+%F %T'))" | tee -a "$log"
  while [ $SECONDS -lt $end ]; do
    t=$(date +%T.%3N)
    n=$(timeout -k 2 -s INT 5 env -u PYTHONPATH gst-launch-1.0 -e -v \
      rtspsrc location="rtsp://${CAM_IP}:554/stream$s" user-id="$CAM_USER" user-pw="$CAM_PASS" protocols=tcp latency=200 \
      ! rtph264depay ! h264parse ! fakesink silent=false 2>&1 | grep -c 'chain')
    echo "$t try buffers=$n end=$(date +%T.%3N)" | tee -a "$log"
    if [ "${n:-0}" -ge 10 ]; then echo "$(date +%T.%3N) VIDEO-OK" | tee -a "$log"; return 0; fi
    sleep 1
  done
  echo "$(date +%T.%3N) GAVE-UP" | tee -a "$log"
}

do_fps() {   # $1 stream, $2 proto, $3 secs, $4 mode (fps|reconnect)
  local s=$1 p=$2 secs=$3 mode=$4 tag="${4}_stream$1_$2"
  local log="$OUT/$tag.log" teg="$OUT/$tag.tegra"
  echo "=== $mode $(safeurl $s) protocols=$p ${secs}s ($(date '+%F %T'))" | tee "$log"
  # tegrastats shows the NVDEC field only when run as root; timeout ends it even if the kill below misses
  local SU=""; sudo -n true 2>/dev/null && SU="sudo -n"
  $SU rm -f "$teg"   # tegrastats appends to an existing logfile
  $SU timeout $((secs + 20)) tegrastats --interval 1000 --logfile "$teg" &
  local tp=$!
  if [ "$mode" = reconnect ]; then
    echo ">>> unplug the camera for 10 s after ~30 s, then plug it back in" | tee -a "$log"
  fi
  # credentials passed as rtspsrc properties (not in the URL); -e = send EOS on SIGINT
  timeout -k 10 -s INT "$secs" env -u PYTHONPATH gst-launch-1.0 -e -v \
    rtspsrc location="rtsp://${CAM_IP}:554/stream$s" user-id="$CAM_USER" user-pw="$CAM_PASS" latency=200 protocols="$p" \
    ! rtph264depay ! h264parse ! nvv4l2decoder \
    ! fpsdisplaysink video-sink=fakesink text-overlay=false sync=false 2>&1 | redact | stamp >> "$log"
  local rc=${PIPESTATUS[0]}
  # signalling sudo does not reach tegrastats, so stop it by its unique logfile argument
  $SU pkill -f -- "--logfile $teg" 2>/dev/null; wait $tp 2>/dev/null
  echo "rc=$rc end $(date '+%T')" >> "$log"
  { echo "--- summary $tag (rc=$rc)"; fps_summary "$log"; tegra_summary "$teg"; } | tee "$OUT/$tag.summary"
}

case "$1" in
  ping)      do_ping 2>&1 | redact | tee "$OUT/ping.log" ;;
  discover)  do_discover 2>&1 | redact | tee "$OUT/discover.log" ;;
  fps)       do_fps "${2:-1}" "${3:-tcp}" "${4:-60}" fps ;;
  reconnect) do_fps "${2:-1}" "${3:-tcp}" "${4:-150}" reconnect ;;
  videowatch) do_videowatch "${2:-1}" "${3:-240}" ;;
  all)
    do_ping 2>&1 | redact | tee "$OUT/ping.log"
    do_discover 2>&1 | redact | tee "$OUT/discover.log"
    for p in tcp udp; do for s in 1 2; do do_fps $s $p 60 fps; sleep 10; done; done ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
# final check: no secret may remain in the results
if grep -rqF -e "$CAM_PASS" "$OUT" 2>/dev/null; then echo "!!! password found in $OUT — results must be scrubbed"; else echo "secret check: clean"; fi
echo "=== CAM-PROBE-DONE $1"
