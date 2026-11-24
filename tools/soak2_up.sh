#!/bin/bash
# Launch the soak v2 collectors in a tmux session (survives SSH drop). Windows: mqtt, logger, slow, watch.
# Env: SOAK_DIR, SOAK_START (epoch). Arg 1 = session name (default soak2).
set -u
SESS="${1:-soak2}"
DIR="${SOAK_DIR:?}"; START="${SOAK_START:?}"
TOOLS="$HOME/safety/tools"
mkdir -p "$DIR"
tmux kill-session -t "$SESS" 2>/dev/null
tmux new-session -d -s "$SESS" -x 200 -y 50
tmux rename-window -t "$SESS":0 mqtt
tmux send-keys -t "$SESS":mqtt "SOAK_DIR='$DIR' env -u PYTHONPATH nice -n 19 python3 $TOOLS/soak_mqtt.py" Enter
sleep 2
tmux new-window -t "$SESS" -n logger
tmux send-keys -t "$SESS":logger "SOAK_DIR='$DIR' SOAK_START=$START nice -n 19 bash $TOOLS/soak_logger_v2.sh" Enter
tmux new-window -t "$SESS" -n slow
tmux send-keys -t "$SESS":slow "SOAK_DIR='$DIR' SOAK_START=$START nice -n 19 bash $TOOLS/soak_slow.sh" Enter
tmux new-window -t "$SESS" -n watch
tmux send-keys -t "$SESS":watch "SOAK_DIR='$DIR' env -u PYTHONPATH nice -n 19 python3 $TOOLS/soak_watch_v2.py" Enter
tmux list-windows -t "$SESS"
