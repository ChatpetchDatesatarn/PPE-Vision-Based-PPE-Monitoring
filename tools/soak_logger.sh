#!/bin/bash
# 24-hour soak sampler: every 5 min append one CSV row of system + pipeline health, then stop after 24 h.
# Touches nothing (read-only sampling). Run inside tmux session "soak".
DIR="$HOME/safety/docs/test-results/2026-10-22_soak24h"
CSV="$DIR/soak.csv"
mkdir -p "$DIR"
H="ts,fps_in,fps_infer,cam_connected,persons,cpu0,cpu1,cpu2,cpu3,ram_used_mb,ram_total_mb,swap_used_mb,cpu_tempC,gpu_tempC,disk_free_gb,rss_app_kb,rss_cira_kb,rss_mosq_kb,rss_rec_kb,hb_age_s,events,snapshots"
[ -f "$CSV" ] || echo "$H" > "$CSV"

rss(){ p=$(pgrep -f "$1" | head -1); [ -n "$p" ] && ps -o rss= -p "$p" 2>/dev/null | tr -d ' ' || echo ""; }

END=$(( $(date +%s) + 86400 ))
while [ "$(date +%s)" -lt "$END" ]; do
  TS=$(date +%Y-%m-%dT%H:%M:%S)
  # cam01/status (retained, every 5 s)
  ST=$(timeout 8 mosquitto_sub -h 127.0.0.1 -t factory/safety/cam01/status -C 1 2>/dev/null)
  read FPIN FPINF CAMC PERS < <(echo "$ST" | python3 -c "import sys,json
try:
 d=json.load(sys.stdin); print(d.get('fps_in',''),d.get('fps_infer',''),d.get('camera_connected',''),d.get('persons',''))
except Exception: print('  ')" 2>/dev/null)
  # tegrastats one line
  TG=$(timeout 3 tegrastats --interval 1000 2>/dev/null | head -1)
  CPUS=$(echo "$TG" | grep -oE "CPU \[[^]]*\]" | grep -oE "[0-9]+%@[0-9]+|off" | sed 's/%@.*//')
  C0=$(echo "$CPUS" | sed -n 1p); C1=$(echo "$CPUS" | sed -n 2p); C2=$(echo "$CPUS" | sed -n 3p); C3=$(echo "$CPUS" | sed -n 4p)
  RAMU=$(echo "$TG" | grep -oE "RAM [0-9]+/[0-9]+" | grep -oE "[0-9]+" | sed -n 1p)
  RAMT=$(echo "$TG" | grep -oE "RAM [0-9]+/[0-9]+" | grep -oE "[0-9]+" | sed -n 2p)
  SWAPU=$(echo "$TG" | grep -oE "SWAP [0-9]+/[0-9]+" | grep -oE "[0-9]+" | sed -n 1p)
  CPUT=$(echo "$TG" | grep -oE "CPU@[0-9.]+" | grep -oE "[0-9.]+")
  GPUT=$(echo "$TG" | grep -oE "GPU@[0-9.]+" | grep -oE "[0-9.]+")
  DISK=$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')
  RAPP=$(rss "person_count_app.py"); RCIRA=$(rss "cira_core_run")
  RMOSQ=$(pgrep -x mosquitto | head -1 | xargs -r ps -o rss= -p 2>/dev/null | tr -d ' ')
  RECPID=$(docker inspect -f '{{.State.Pid}}' recorder 2>/dev/null); RREC=$(ps -o rss= -p "$RECPID" 2>/dev/null | tr -d ' ')
  # CiRA heartbeat age
  HBTS=$(timeout 13 mosquitto_sub -h 127.0.0.1 -t factory/safety/cira/status -C 1 2>/dev/null | python3 -c "import sys,json
try: print(json.load(sys.stdin).get('ts',''))
except Exception: print('')" 2>/dev/null)
  HBAGE=$(python3 -c "import time,calendar
ts='$HBTS'
try:
 b=time.strptime(ts[:19],'%Y-%m-%dT%H:%M:%S'); print(int(time.time()-(calendar.timegm(b)-7*3600)))
except Exception: print('')" 2>/dev/null)
  HL=$(curl -s --max-time 6 127.0.0.1:8000/api/health | python3 -c "import sys,json
try: d=json.load(sys.stdin); print(d.get('events',''),d.get('snapshots',''))
except Exception: print(' ')" 2>/dev/null)
  EV=$(echo "$HL" | awk '{print $1}'); SN=$(echo "$HL" | awk '{print $2}')
  echo "$TS,$FPIN,$FPINF,$CAMC,$PERS,$C0,$C1,$C2,$C3,$RAMU,$RAMT,$SWAPU,$CPUT,$GPUT,$DISK,$RAPP,$RCIRA,$RMOSQ,$RREC,$HBAGE,$EV,$SN" >> "$CSV"
  sleep 300
done
# 24 h reached: stop the logger (this script ends here) and leave the app RUNNING but not saving pictures,
# i.e. restart it with events off (ds-stop; ds-start). The app is never left stopped; nothing else is touched.
echo "$(date +%Y-%m-%dT%H:%M:%S) soak 24h done -> logger stop; switching app to events off (keeps running)" >> "$DIR/soak_done.txt"
"$HOME/ds-stop" >/dev/null 2>&1
sleep 2
"$HOME/ds-start" >/dev/null 2>&1          # no --events -> events off (status only, no snapshots)
echo "$(date +%Y-%m-%dT%H:%M:%S) app restarted with events off and left running" >> "$DIR/soak_done.txt"
