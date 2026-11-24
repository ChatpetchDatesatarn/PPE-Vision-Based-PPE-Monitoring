#!/bin/bash
# Launch the soak v3 collectors in a tmux session (survives SSH drop). Windows: mqtt, logger, slow, watch.
# Reuses soak_mqtt.py (latency) + soak_watch_v2.py (disk<3GB guard) unchanged; v3 logger+slow add
# power/freq/throttle + raw SATAVG. Env: SOAK_DIR, SOAK_START (epoch), SOAK_HOURS (default 24).
# Arg 1 = session name (default soak3). The PC-side live_monitor (run_monitor.sh) runs separately.
set -u
SESS="${1:-soak3}"
DIR="${SOAK_DIR:?}"; START="${SOAK_START:?}"; HOURS="${SOAK_HOURS:-24}"
TOOLS="$HOME/safety/tools"
mkdir -p "$DIR"
tmux kill-session -t "$SESS" 2>/dev/null
tmux new-session -d -s "$SESS" -x 200 -y 50
tmux rename-window -t "$SESS":0 mqtt
tmux send-keys -t "$SESS":mqtt "SOAK_DIR='$DIR' env -u PYTHONPATH nice -n 19 python3 $TOOLS/soak_mqtt.py" Enter
sleep 2
tmux new-window -t "$SESS" -n logger
tmux send-keys -t "$SESS":logger "SOAK_DIR='$DIR' SOAK_START=$START SOAK_HOURS=$HOURS SOAK_SESS='$SESS' nice -n 19 bash $TOOLS/soak_logger_v3.sh" Enter
tmux new-window -t "$SESS" -n slow
tmux send-keys -t "$SESS":slow "SOAK_DIR='$DIR' SOAK_START=$START nice -n 19 bash $TOOLS/soak_slow_v3.sh" Enter
tmux new-window -t "$SESS" -n watch
tmux send-keys -t "$SESS":watch "SOAK_DIR='$DIR' env -u PYTHONPATH nice -n 19 python3 $TOOLS/soak_watch_v2.py" Enter
tmux list-windows -t "$SESS"
