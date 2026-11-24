#!/bin/bash
# Start person_count_app.py in tmux "ds" with no time limit (stop with ~/ds-stop). Default run name
# live_<date>_<time>, so an earlier log is never overwritten. Extra arguments go to person_count_app.py.
# Events (ds/violation, snapshots, fallback events) are OFF unless asked for: --events on.
# On the Jetson it is linked as ~/ds-start. From the PC:
#   ssh jetson ./ds-start                  status only
#   ssh jetson ./ds-start --events on      also violations / snapshots / events
#   ssh jetson ./ds-start <run-name> ...   own run name (first argument not starting with -)
PAT='^python3 -u person_count_app.py'
if PID=$(pgrep -f "$PAT"); then echo "already running (pid $PID) — stop it first with ./ds-stop"; exit 1; fi
RUN=live_$(date +%Y%m%d_%H%M)
case "$1" in -*|"") ;; *) RUN=$1; shift ;; esac
ARGS="$*"
case " $ARGS " in *" --events "*) ;; *) ARGS="--events off $ARGS" ;; esac
APP="$HOME/safety/perception/app"
LOG="$HOME/safety/perception/test/results/cam/$RUN.log"
tmux has-session -t ds 2>/dev/null || tmux new-session -d -s ds -x 200 -y 50
tmux send-keys -t ds "cd $APP && bash run_person_app.sh $RUN --seconds 0 $ARGS" Enter
echo "starting $RUN ($ARGS) (log: ${LOG#$HOME/})"
for _ in $(seq 1 45); do
  sleep 1
  if grep -q "first frame" "$LOG" 2>/dev/null; then echo "running: $(grep -m1 'first frame' "$LOG")"; exit 0; fi
done
echo "no first frame after 45 s — check: tmux capture-pane -p -t ds | tail"; exit 1
