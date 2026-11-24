#!/bin/bash
# Bring CiRA fully up with one command: cira-start (fresh Xvfb :99 + CiRA at nice 19) then cira-autoload
# (headless Open Project + Run + verify). Exit code is cira-autoload's (0 = flow running + heartbeat + event).
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
"$DIR/cira-start.sh" || { echo "cira-start failed"; exit 1; }
exec "$DIR/cira-autoload.sh"
