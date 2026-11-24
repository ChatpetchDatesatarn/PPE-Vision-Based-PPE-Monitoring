#!/bin/bash
# soak v3 slow sampler (every 600 s): brightness.csv (raw SATAVG + YAVG from 1 frame, OSD strip cropped,
# is_night dropped) and mediamtx.csv (cumulative WebRTC/B-frame/PPS counts). nice 19. tmux "soak3".
set -u
DIR="${SOAK_DIR:?}"; START="${SOAK_START:?}"
INTERVAL="${SOAK_SLOW_S:-600}"
mkdir -p "$DIR"
BR="$DIR/brightness.csv"; MM="$DIR/mediamtx.csv"
# v3: store raw SATAVG + YAVG; the top OSD strip is cropped out before signalstats. No is_night.
[ -f "$BR" ] || printf '\xef\xbb\xbf%s\n' "timestamp,elapsed_h,yavg,satavg,crop" > "$BR"
[ -f "$MM" ] || printf '\xef\xbb\xbf%s\n' "timestamp,elapsed_h,bframes_lines_total,webrtc_sessions_opened_total,webrtc_sessions_closed_total,pps_errors_total" > "$MM"
URL="rtsp://127.0.0.1:8554/cam01"
CROP="crop=iw:ih*0.80:0:ih*0.15"   # drop top 15% (OSD text) + bottom 5%
BRFAIL=0                            # v4 item5: consecutive brightness-grab failures
while true; do
  now=$(date +%s)
  TS=$(date '+%Y-%m-%d %H:%M:%S (+07:00)')
  EH=$(python3 -c "print('%.2f'%(($now-$START)/3600.0))" 2>/dev/null)
  # v4 item5: retry the frame-grab (survives a camera stream reset); blank only after 3 tries
  YAVG=""; SAT=""
  for try in 1 2 3; do
    rm -f /tmp/sig.txt
    timeout 20 nice -n 19 ffmpeg -nostdin -y -rtsp_transport tcp -i "$URL" -frames:v 1 \
        -vf "${CROP},scale=160:-1,signalstats,metadata=print:file=/tmp/sig.txt" -f null - >/dev/null 2>&1
    YAVG=$(grep -oE 'YAVG=[0-9.]+' /tmp/sig.txt 2>/dev/null | head -1 | cut -d= -f2)
    SAT=$(grep -oE 'SATAVG=[0-9.]+' /tmp/sig.txt 2>/dev/null | head -1 | cut -d= -f2)
    [ -n "$YAVG" ] && break
    sleep 3
  done
  if [ -n "$YAVG" ]; then BRFAIL=0; else BRFAIL=$((BRFAIL+1)); fi
  if [ "$BRFAIL" -ge 3 ]; then
    echo "$TS WARNING brightness frame-grab failed ${BRFAIL}x in a row (camera reset / RTSP down?)" >> "$DIR/watch.log"
  fi
  echo "$TS,$EH,${YAVG:-},${SAT:-},${CROP}" >> "$BR"
  SINCE=$(( now - START )); [ "$SINCE" -lt 1 ] && SINCE=1
  LOG=$(docker logs mediamtx --since ${SINCE}s 2>&1)
  BF=$(echo "$LOG" | grep -c 'B-frames')
  OP=$(echo "$LOG" | grep -c 'WebRTC.*created by')
  CL=$(echo "$LOG" | grep -c 'WebRTC.*closed')
  PP=$(echo "$LOG" | grep -c 'PPS')
  echo "$TS,$EH,$BF,$OP,$CL,$PP" >> "$MM"
  sleep "$INTERVAL"
done
