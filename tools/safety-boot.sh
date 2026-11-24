#!/bin/bash
# Boot orchestration for the AI Safety Monitoring stack, run by safety-autostart.service after
# docker.service + network-online.target. Order: wait for the mosquitto broker -> ds-start (events from boot.conf)
# -> cira-up (cira-start + cira-autoload). Logs every step to ~/safety/logs/boot_<ts>.log.
# On a hard failure it logs and exits non-zero (no endless retry). docker containers come up on their own
# via their restart:unless-stopped policy, so this script does not start them.
set -u
HOME=${HOME:-/home/jetson}
mkdir -p "$HOME/safety/logs"
LOG="$HOME/safety/logs/boot_$(date +%Y%m%d-%H%M%S).log"
exec >>"$LOG" 2>&1
echo "=== safety-boot start $(date) ==="

# 1) Wait for the mosquitto broker (docker, host-net 1883) — up to 120 s.
echo "[1] wait for mosquitto (<=120s)"
up=0
for i in $(seq 1 120); do
  if docker exec mosquitto mosquitto_sub -h 127.0.0.1 -t '$SYS/broker/version' -C 1 -W 2 >/dev/null 2>&1; then
    up=1; echo "    mosquitto up after ${i}s"; break
  fi
  sleep 1
done
[ "$up" = 1 ] || { echo "ERROR: mosquitto not up within 120 s — abort"; exit 1; }

# 2) DeepStream live. Events (ds/violation, snapshots, fallback events) from ~/safety/boot.conf: BOOT_EVENTS=on|off.
#    Missing file or any other value -> off (safe default). Prints the chosen value; reason goes to the log.
pick_boot_events() {
  local conf=${BOOT_CONF:-$HOME/safety/boot.conf} BOOT_EVENTS=""
  if [ ! -f "$conf" ]; then echo "    boot.conf: $conf missing -> events off (default)" >&2; echo off; return; fi
  # shellcheck disable=SC1090
  . "$conf"
  case "$BOOT_EVENTS" in
    on|off) echo "    boot.conf: BOOT_EVENTS=$BOOT_EVENTS -> events $BOOT_EVENTS" >&2; echo "$BOOT_EVENTS" ;;
    *)      echo "    boot.conf: BOOT_EVENTS='$BOOT_EVENTS' invalid (on/off only) -> events off (default)" >&2; echo off ;;
  esac
}
EV=$(pick_boot_events)
echo "[2] ds-start --events $EV"
"$HOME/ds-start" --events "$EV" || echo "    WARN: ds-start returned $? (continuing)"

# 3) CiRA up: cira-start + cira-autoload. On failure, log and exit — do NOT retry forever.
echo "[3] cira-up"
if "$HOME/cira-up"; then
  echo "    cira-up OK"
else
  echo "ERROR: cira-up failed (see /tmp/cira_autoload.log and /tmp/autoload_*.png) — exit"
  exit 1
fi

echo "=== safety-boot done $(date) ==="
