#!/bin/bash
# Record a room-light change for the soak light log. Linked as ~/light on the Jetson.
#   ~/light on  [note]   lights turned ON
#   ~/light off [note]   lights turned OFF
#   ~/light note <text>  free note, no state change
# Appends to $LIGHT_LOG (default ~/light_log.csv). The soak report ingests this file by time window.
set -u
LOG="${LIGHT_LOG:-$HOME/light_log.csv}"
[ -f "$LOG" ] || printf '\xef\xbb\xbf%s\n' "timestamp,light_on,note" > "$LOG"
TS=$(date '+%Y-%m-%d %H:%M:%S (+07:00)')
case "${1:-}" in
  on)   shift; echo "$TS,1,${*:-}"  >> "$LOG"; echo "logged: lights ON  -> $LOG" ;;
  off)  shift; echo "$TS,0,${*:-}"  >> "$LOG"; echo "logged: lights OFF -> $LOG" ;;
  note) shift; echo "$TS,,${*:-}"   >> "$LOG"; echo "logged: note      -> $LOG" ;;
  *)    echo "usage: ~/light on|off|note [text]"; exit 1 ;;
esac
