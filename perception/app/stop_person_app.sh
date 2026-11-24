#!/bin/bash
# Stop person_count_app.py cleanly: SIGINT to the python process only (not tmux C-c), so the app publishes
# status online:false and writes its summary, and run_person_app.sh still does its secret check.
# On the Jetson it is linked as ~/ds-stop. From the PC:  ssh jetson ./ds-stop
# The ^ anchor keeps pgrep from matching the ssh shell whose command line contains the pattern.
PAT='^python3 -u person_count_app.py'
PID=$(pgrep -f "$PAT")
[ -n "$PID" ] || { echo "person_count_app is not running"; exit 0; }
echo "stopping person_count_app (pid $PID)"
kill -INT $PID
for _ in $(seq 1 30); do
  pgrep -f "$PAT" >/dev/null || { echo "stopped"; exit 0; }
  sleep 1
done
echo "still running after 30 s (pid $PID)"; exit 1
