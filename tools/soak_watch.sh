#!/bin/bash
# Soak safety watcher — runs beside soak_logger (own tmux window) so the logger's 24 h clock is untouched.
# Every 2 min: (a) if snapshots stay near MAX_SNAPSHOTS=3000 that is fine; if they pass 3300, log a WARNING
# once (cleanup not keeping up). (b) if disk free < 3 GB, switch the app to events off (ds-stop; ds-start)
# at once and exit. Only touches the app on the disk fire; nothing else.
DIR="$HOME/safety/docs/test-results/2026-10-22_soak24h"
mkdir -p "$DIR"
WARNED=0
while true; do
  HL=$(curl -s --max-time 6 127.0.0.1:8000/api/health)
  SN=$(echo "$HL" | python3 -c "import sys,json
try: print(int(json.load(sys.stdin).get('snapshots',0)))
except Exception: print(0)" 2>/dev/null)
  DISK=$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')
  if [ "$WARNED" = 0 ] && [ -n "$SN" ] && [ "$SN" -gt 3300 ] 2>/dev/null; then
    echo "$(date +%Y-%m-%dT%H:%M:%S) WARNING snapshots=$SN > 3300 (MAX_SNAPSHOTS=3000 cleanup not keeping up)" >> "$DIR/soak_done.txt"
    WARNED=1
  fi
  if [ -n "$DISK" ] && [ "$DISK" -lt 3 ] 2>/dev/null; then
    echo "$(date +%Y-%m-%dT%H:%M:%S) SAFETY disk_free=${DISK}GB < 3GB -> ds-stop; ds-start (events off)" >> "$DIR/soak_done.txt"
    "$HOME/ds-stop" >/dev/null 2>&1
    sleep 2
    "$HOME/ds-start" >/dev/null 2>&1          # events off
    echo "$(date +%Y-%m-%dT%H:%M:%S) app restarted events off (disk safety); watcher exit" >> "$DIR/soak_done.txt"
    break
  fi
  sleep 120
done
