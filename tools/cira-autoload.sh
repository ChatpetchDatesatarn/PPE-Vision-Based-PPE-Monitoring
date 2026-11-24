#!/bin/bash
# Headless-load the CiRA flow via xdotool on Xvfb :99:
#   1) click "Open Project", type the path, Enter  -> loads AND auto-runs the flow (decide works from MqttSub)
#   2) click "fit to view" -> normalises the canvas to a DETERMINISTIC layout (independent of the previous
#      pan/zoom), so the heartbeat AutoRun button is always at the same screen pixel
#   3) click the heartbeat AutoRun "Run" button -> starts the 10 s heartbeat loop (a global run does NOT
#      fire AutoRun source nodes, and node_enable alone does not either; the node's own Run must be pressed)
# Then verify the heartbeat and a fake event. Retries up to 3 times.
# NEVER presses Save Project and NEVER clicks the toolbar Run/STOP. Exit 0 on success, !=0 on failure.
export DISPLAY=:99
NPJ=/home/jetson/safety/decision/safety_decision_v1.npj
LOG=/tmp/cira_autoload.log
OPEN_X=452; OPEN_Y=213      # "Open Project" toolbar button (fixed)
FN_X=790;  FN_Y=568         # "File name" field in the (fixed, centred) Open dialog
FIT_X=1285; FIT_Y=356       # "fit to view" button (fixed)
DEC_X=613; DEC_Y=476        # decide   AutoRun "Run" button AFTER fit-to-view (starts MqttSub / decide chain)
HB_X=526;  HB_Y=700         # heartbeat AutoRun "Run" button AFTER fit-to-view (starts the 10 s heartbeat)
log(){ echo "$(date +%T) $*" | tee -a "$LOG"; }
shot(){ scrot "/tmp/autoload_$1.png" 2>/dev/null; }

hb_ok(){ # one heartbeat within $1 s?
  timeout "$1" mosquitto_sub -h 127.0.0.1 -t factory/safety/cira/status -C 1 >/dev/null 2>&1; }
event_ok(){ # fake violation track 990 -> event via:cira within 6 s?
  ( timeout 7 mosquitto_sub -h 127.0.0.1 -t factory/safety/cam01/event -C 1 > /tmp/al_ev.txt 2>&1 & )
  sleep 1
  docker exec mosquitto mosquitto_pub -h 127.0.0.1 -t factory/safety/cam01/ds/violation \
    -m '{"camera_id":"cam01","type":"no_helmet","track_id":990,"conf":0.9,"zone_id":"","bbox":[0.1,0.1,0.2,0.5],"snapshot_id":"","repeat":0}'
  sleep 5
  grep -q '"track_id":990' /tmp/al_ev.txt && grep -q '"via":"cira"' /tmp/al_ev.txt; }
cleanup_test(){ docker exec recorder python3 -c "import sqlite3;c=sqlite3.connect('/data/safety.db');c.execute('delete from events where track_id=990');c.commit()" 2>/dev/null; }

attempt(){
  log "attempt $1: wait for CiRA window"
  for i in $(seq 1 30); do xdotool search --name "cira_core_run" >/dev/null 2>&1 && break; sleep 1; done
  # cira_core_run shows a "Starting..." splash for ~30-45 s before the main GUI (with the toolbar) appears;
  # clicking during the splash does nothing. Let the first attempt wait the splash out.
  [ "$1" = 1 ] && { log "settle 45s (wait out the Starting... splash)"; sleep 45; }
  log "click Open Project ($OPEN_X,$OPEN_Y)"
  xdotool mousemove $OPEN_X $OPEN_Y click 1; sleep 3; shot "${1}a_dialog"
  # The Open dialog is centred and fixed-size: click its "File name" field directly to focus it, then type.
  log "focus File name field ($FN_X,$FN_Y) + type path + Enter"
  xdotool mousemove $FN_X $FN_Y click 1; sleep 0.5
  xdotool key --clearmodifiers ctrl+a; sleep 0.3
  xdotool type --clearmodifiers "$NPJ"; sleep 0.6; shot "${1}b_typed"
  xdotool key --clearmodifiers Return; sleep 4; shot "${1}c_loaded"   # project loads and auto-runs here
  log "click fit-to-view ($FIT_X,$FIT_Y)"
  xdotool mousemove $FIT_X $FIT_Y click 1; sleep 2; shot "${1}d_fit"
  log "click decide AutoRun Run ($DEC_X,$DEC_Y)"
  xdotool mousemove $DEC_X $DEC_Y click 1; sleep 1
  log "click heartbeat AutoRun Run ($HB_X,$HB_Y)"
  xdotool mousemove $HB_X $HB_Y click 1; sleep 2; shot "${1}e_runs"
  log "verify heartbeat <=30s"
  if hb_ok 30; then log "heartbeat OK"; else log "no heartbeat"; return 1; fi
  log "verify fake event track 990"
  if event_ok; then cleanup_test; log "event via:cira OK"; return 0; else cleanup_test; log "no event via:cira"; return 1; fi
}

: > "$LOG"
for try in 1 2 3; do
  if attempt $try; then log "SUCCESS on attempt $try"; exit 0; fi
  log "attempt $try FAILED"
done
log "ALL 3 ATTEMPTS FAILED (see /tmp/autoload_*.png)"
exit 1
