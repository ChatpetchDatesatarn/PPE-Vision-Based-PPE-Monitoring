#!/bin/bash
# soak v2 slow sampler (every 600 s): brightness.csv (1 low-res frame -> signalstats) and
# mediamtx.csv (cumulative WebRTC/B-frame/PPS counts since soak start). nice 19. tmux "soak2".
set -u
DIR="${SOAK_DIR:?}"; START="${SOAK_START:?}"
mkdir -p "$DIR"
BR="$DIR/brightness.csv"; MM="$DIR/mediamtx.csv"
[ -f "$BR" ] || printf '\xef\xbb\xbf%s\n' "timestamp,elapsed_h,brightness_mean,is_night" > "$BR"
[ -f "$MM" ] || printf '\xef\xbb\xbf%s\n' "timestamp,elapsed_h,bframes_lines_total,webrtc_sessions_opened_total,webrtc_sessions_closed_total,pps_errors_total" > "$MM"
URL="rtsp://127.0.0.1:8554/cam01"
while true; do
  now=$(date +%s)
  TS=$(date '+%Y-%m-%d %H:%M:%S (+07:00)')
  EH=$(python3 -c "print('%.2f'%(($now-$START)/3600.0))" 2>/dev/null)
  # brightness
  rm -f /tmp/sig.txt
  timeout 20 nice -n 19 ffmpeg -nostdin -y -rtsp_transport tcp -i "$URL" -frames:v 1 \
      -vf "scale=160:-1,signalstats,metadata=print:file=/tmp/sig.txt" -f null - >/dev/null 2>&1
  YAVG=$(grep -oE 'YAVG=[0-9.]+' /tmp/sig.txt 2>/dev/null | head -1 | cut -d= -f2)
  SAT=$(grep -oE 'SATAVG=[0-9.]+' /tmp/sig.txt 2>/dev/null | head -1 | cut -d= -f2)
  NIGHT=""
  if [ -n "$SAT" ]; then NIGHT=$(python3 -c "print(1 if float('$SAT')<16 else 0)" 2>/dev/null); fi
  echo "$TS,$EH,${YAVG:-},${NIGHT:-}" >> "$BR"
  # mediamtx cumulative since soak start
  SINCE=$(( now - START )); [ "$SINCE" -lt 1 ] && SINCE=1
  LOG=$(docker logs mediamtx --since ${SINCE}s 2>&1)
  BF=$(echo "$LOG" | grep -c 'B-frames')
  OP=$(echo "$LOG" | grep -c 'WebRTC.*created by')
  CL=$(echo "$LOG" | grep -c 'WebRTC.*closed')
  PP=$(echo "$LOG" | grep -c 'PPS')
  echo "$TS,$EH,$BF,$OP,$CL,$PP" >> "$MM"
  sleep 600
done
