#!/bin/bash
# v4 item6: teardown at soak end. Run by soak_logger_v3.sh when the window finishes (or manually).
# (1) stop sibling collectors in the soak tmux session  (2) ds-stop; ds-start (events off)
# (4) verify no collector left + app events off, print result (appended to soak_done.txt).
# NOTE: the PC-side live_monitor (item 3 of soak) stops itself at --minutes; it cannot be reached from
# the Jetson, so (3) is handled by the PC runbook. This script covers (1)(2)(4) on the Jetson.
set -u
SESS="${SOAK_SESS:-soak3}"
echo "=== teardown v4 @ $(date '+%F %T %z') (session=$SESS) ==="

# (1) stop sibling collector windows (not this logger window)
for w in mqtt slow watch; do tmux send-keys -t "$SESS:$w" C-c 2>/dev/null; done
sleep 2
pkill -f 'soak_mqtt.py'    2>/dev/null
pkill -f 'soak_slow_v3.sh' 2>/dev/null
pkill -f 'soak_watch_v2.py' 2>/dev/null
sleep 1

# (2) app -> events off (ds-start default is events off); uses the SIGINT-safe ds-stop
cd "$HOME" || exit 0
./ds-stop  >/dev/null 2>&1
sleep 2
./ds-start >/dev/null 2>&1
sleep 8

# (4) verify
EV=$(ps -o args= -C python3 2>/dev/null | grep person_count | grep -o '\-\-events [a-z]*' | head -1)
LEFT=$(pgrep -af 'soak_mqtt.py|soak_slow_v3.sh|soak_watch_v2.py' 2>/dev/null | grep -v pgrep | wc -l)
echo "app: ${EV:-'(not running)'}"
echo "leftover_collectors: $LEFT"
if [ "$EV" = "--events off" ] && [ "$LEFT" -eq 0 ]; then
  echo "teardown: OK (app events off, no collector left)"
else
  echo "teardown: WARNING (app='$EV' leftover=$LEFT) — check manually"
fi
# kill the soak tmux session LAST (this also ends the logger window). Done here, not in the logger, so the
# logger can launch this detached (setsid) and exit — the teardown then cannot be killed with its window.
tmux kill-session -t "$SESS" 2>/dev/null
