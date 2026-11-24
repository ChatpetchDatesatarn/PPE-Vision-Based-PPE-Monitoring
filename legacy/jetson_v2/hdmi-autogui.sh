#!/bin/bash
# Turn the GUI on when an HDMI display is plugged in, off when unplugged (frees ~1GB RAM)
# Set default target to multi-user (no display) first:  sudo systemctl set-default multi-user.target
# If the status file isn't found automatically, set HDMI_STATUS_FILE in hdmi-autogui.service

STATUS_FILE="${HDMI_STATUS_FILE:-}"
POLL=2        # seconds between checks
DEBOUNCE=3    # wait until the plug state is stable

find_status() {
  for f in /sys/class/drm/card*-HDMI-A-*/status /sys/class/switch/hdmi/state; do
    [ -r "$f" ] && { echo "$f"; return 0; }
  done
  return 1
}

state() {
  case "$(cat "$STATUS_FILE" 2>/dev/null)" in
    connected|1) echo on ;;
    *) echo off ;;
  esac
}

[ -z "$STATUS_FILE" ] && STATUS_FILE="$(find_status)"
if [ -z "$STATUS_FILE" ]; then
  echo "HDMI status file not found; set HDMI_STATUS_FILE" >&2
  exit 1
fi
echo "watching $STATUS_FILE"

prev=""
while true; do
  cur="$(state)"
  if [ "$cur" != "$prev" ]; then
    sleep "$DEBOUNCE"
    [ "$(state)" != "$cur" ] && continue
    if [ "$cur" = on ]; then
      echo "HDMI connected -> start GUI"
      systemctl isolate --no-block graphical.target
    else
      echo "HDMI disconnected -> stop GUI"
      systemctl isolate --no-block multi-user.target
    fi
    prev="$cur"
  fi
  sleep "$POLL"
done
