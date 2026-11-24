#!/bin/bash
# Find where fps drops: build the live pipeline one stage at a time with gst-launch-1.0 (not deepstream-app)
# Credentials come from ~/safety/.cam.env (sourced only, passed as rtspsrc properties, never in the URL or a log)
# Every output line goes through redact(), so logs only show rtsp://***@<ip>/stream1
#
# Usage (run in tmux "ds"):
#   bash stage_probe.sh <S1..S8> [secs]     # one stage (default 90 s)
#   bash stage_probe.sh all [secs]          # S1..S7 with 20 s cooldown between stages
# Stages:
#   S1 rtspsrc(tcp, latency 200, drop-on-latency=true) → rtph264depay → h264parse → nvv4l2decoder
#   S2 S1 with drop-on-latency=false, latency 500
#   S3 S1 + nvstreammux 1280x720 live-source=1
#   S4 S3 + nvinfer (config_infer_cam_person.txt, interval=0)
#   S5 S4 + nvtracker (IOU, 640x384)
#   S6 S5 + nvvideoconvert(RGBA) → nvdsosd → nvvideoconvert(I420) → nvv4l2h264enc (no RTSP out)
#   S7 S6 with nvinfer interval=1
#   S8 S6 + tee: one branch rtph264pay → udpsink 127.0.0.1:5400 (sync=false async=false), the other the fps sink
#   every stage ends in fpsdisplaysink video-sink=fakesink sync=false text-overlay=false
cd "$(dirname "$0")"
TEST_DIR=$(pwd)
OUT=results/cam/stages
mkdir -p "$OUT"

ENVF="$HOME/safety/.cam.env"
[ -f "$ENVF" ] || { echo "missing $ENVF"; exit 1; }
set +x
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$CAM_IP" ] && [ -n "$CAM_USER" ] && [ -n "$CAM_PASS" ] || { echo "CAM_IP/CAM_USER/CAM_PASS not all set in .cam.env"; exit 1; }
export CAM_USER CAM_PASS
# the pipeline is word-split into gst-launch arguments, so credentials must not contain whitespace
case "$CAM_USER$CAM_PASS" in *[[:space:]]*) echo "CAM_USER/CAM_PASS contain whitespace: not supported by stage_probe.sh"; exit 1 ;; esac
set -f   # no glob expansion of the word-split pipeline

# literal (not regex) replacement of user and password, then mask any user-info left in rtsp URLs
redact() {
  awk 'function rep(s, t, r,   i, o) { o = ""; if (t == "") return s
         while ((i = index(s, t)) > 0) { o = o substr(s, 1, i - 1) r; s = substr(s, i + length(t)) }
         return o s }
       { l = rep($0, ENVIRON["CAM_PASS"], "***"); l = rep(l, ENVIRON["CAM_USER"], "***")
         gsub(/rtsp:\/\/[^@\/ ]*@/, "rtsp://***@", l); print l; fflush() }'
}
stamp() { while IFS= read -r l; do printf '%(%T)T %s\n' -1 "$l"; done; }

DS=/opt/nvidia/deepstream/deepstream-6.0
INFER_CFG=$TEST_DIR/config_infer_cam_person.txt
TRK="nvtracker ll-lib-file=$DS/lib/libnvds_nvmultiobjecttracker.so ll-config-file=$DS/samples/configs/deepstream-app/config_tracker_IOU.yml tracker-width=640 tracker-height=384 enable-batch-process=1 enable-past-frame=1"
MUX="nvstreammux name=m width=1280 height=720 batch-size=1 live-source=1 batched-push-timeout=40000"
# nvdsosd on Jetson needs RGBA, and the encoder takes I420 — same converters deepstream-app puts around the OSD
OSD_ENC="nvvideoconvert ! video/x-raw(memory:NVMM),format=RGBA ! nvdsosd ! nvvideoconvert ! video/x-raw(memory:NVMM),format=I420 ! nvv4l2h264enc bitrate=4000000 iframeinterval=30 insert-sps-pps=1"
SINK="fpsdisplaysink video-sink=fakesink sync=false text-overlay=false"

src() {   # $1 latency, $2 drop-on-latency
  echo "rtspsrc location=rtsp://${CAM_IP}:554/stream1 user-id=$CAM_USER user-pw=$CAM_PASS protocols=tcp latency=$1 drop-on-latency=$2 ! rtph264depay ! h264parse ! nvv4l2decoder"
}

stage_pipeline() {
  case "$1" in
    S1) echo "$(src 200 true) ! $SINK" ;;
    S2) echo "$(src 500 false) ! $SINK" ;;
    S3) echo "$(src 200 true) ! m.sink_0 $MUX ! $SINK" ;;
    S4) echo "$(src 200 true) ! m.sink_0 $MUX ! nvinfer config-file-path=$INFER_CFG interval=0 ! $SINK" ;;
    S5) echo "$(src 200 true) ! m.sink_0 $MUX ! nvinfer config-file-path=$INFER_CFG interval=0 ! $TRK ! $SINK" ;;
    S6) echo "$(src 200 true) ! m.sink_0 $MUX ! nvinfer config-file-path=$INFER_CFG interval=0 ! $TRK ! $OSD_ENC ! $SINK" ;;
    S7) echo "$(src 200 true) ! m.sink_0 $MUX ! nvinfer config-file-path=$INFER_CFG interval=1 ! $TRK ! $OSD_ENC ! $SINK" ;;
    # fpsdisplaysink cannot wrap a udpsink with properties from gst-launch, so a tee feeds both
    S8) echo "$(src 200 true) ! m.sink_0 $MUX ! nvinfer config-file-path=$INFER_CFG interval=0 ! $TRK ! $OSD_ENC ! tee name=t t. ! queue ! rtph264pay ! udpsink host=127.0.0.1 port=5400 sync=false async=false t. ! queue ! $SINK" ;;
    *) return 1 ;;
  esac
}

# per-core CPU (online cores), GR3D% and RAM from tegrastats
tegra_summary() {
  awk '{ if (match($0, /CPU \[[^]]*\]/)) { c = substr($0, RSTART + 5, RLENGTH - 6); k = split(c, a, ",")
           for (i = 1; i <= k; i++) if (a[i] != "off") { split(a[i], b, "%"); v = b[1] + 0; s[i] += v; n[i]++; if (v > m[i]) m[i] = v; if (v >= 99) full[i]++ } }
         if (match($0, /GR3D_FREQ [0-9]+%/)) { g = substr($0, RSTART + 10, RLENGTH - 11) + 0; gs += g; gn++; if (g > gm) gm = g }
         if (match($0, /RAM [0-9]+/)) { r = substr($0, RSTART + 4, RLENGTH - 4) + 0; if (r > rm) rm = r } }
       END { for (i = 1; i <= 4; i++) if (n[i]) printf "cpu%d mean=%.1f max=%d samples>=99%%=%d  ", i - 1, s[i] / n[i], m[i], full[i]
             if (gn) printf "\nGR3D%% mean=%.1f max=%d  RAM max=%dMB  samples=%d\n", gs / gn, gm, rm, gn }' "$1"
}

fps_summary() {
  grep -o 'rendered: [0-9]*, dropped: [0-9]*, current: [0-9.]*, average: [0-9.]*' "$1" | tail -1 | sed 's/^/last: /'
  grep -o 'current: [0-9.]*' "$1" | awk '{ v = $2 + 0; if (NR > 4) { s += v; n++; if (min == "" || v < min) min = v; if (v > mx) mx = v; if (v < 25) lo++ } }
      END { if (n) printf "current fps (first 2 s dropped): n=%d mean=%.2f min=%.2f max=%.2f below25=%d\n", n, s / n, min, mx, lo }'
  printf 'DPB warnings: %s  ERROR lines: %s  camera errors (Could not read/receive): %s  EOS: %s\n' \
    "$(grep -c 'reference in DPB was never decoded' "$1")" "$(grep -c 'ERROR' "$1")" \
    "$(grep -cE 'Could not (read|receive)' "$1")" "$(grep -c 'Got EOS' "$1")"
}

run_stage() {   # $1 stage, $2 secs
  local st=$1 secs=$2 pipe log="$OUT/$1.log" teg="$OUT/$1.tegra"
  pipe=$(stage_pipeline "$st") || { sed -n '7,19p' "$0"; exit 1; }
  echo "=== $st ${secs}s rtsp://***@${CAM_IP}:554/stream1 ($(date '+%F %T'))" | tee "$log"
  echo "pipeline: $pipe" | redact | tee -a "$log"
  local SU=""; sudo -n true 2>/dev/null && SU="sudo -n"
  $SU rm -f "$teg"
  $SU timeout $((secs + 20)) tegrastats --interval 1000 --logfile "$teg" &
  local tp=$!
  # word splitting of $pipe is intended (gst-launch takes the pipeline as separate arguments)
  # shellcheck disable=SC2086
  timeout -k 10 -s INT "$secs" env -u PYTHONPATH gst-launch-1.0 -e -v $pipe 2>&1 | redact | stamp >> "$log"
  local rc=${PIPESTATUS[0]}
  $SU pkill -f -- "--logfile $teg" 2>/dev/null; wait $tp 2>/dev/null
  echo "rc=$rc end $(date '+%T')" >> "$log"
  { echo "--- summary $st (rc=$rc)"; fps_summary "$log"; tegra_summary "$teg"; } | tee "$OUT/$st.summary"
}

SECS=${2:-90}
case "$1" in
  S[1-8]) run_stage "$1" "$SECS" ;;
  all) for s in S1 S2 S3 S4 S5 S6 S7; do run_stage $s "$SECS"; [ $s = S7 ] || sleep 20; done ;;
  *) sed -n '7,19p' "$0"; exit 1 ;;
esac
if grep -rqF -e "$CAM_PASS" "$OUT" 2>/dev/null; then echo "!!! password found in $OUT — results must be scrubbed"; else echo "secret check: clean"; fi
echo "=== STAGE-PROBE-DONE $1"
