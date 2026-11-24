#!/bin/bash
# Run DeepStream smoke test + tegrastats; results in ./results/
# Usage: bash run_smoke.sh <tag> <seconds> [app config, default ds_smoke_app.txt]
cd "$(dirname "$0")"
TAG=${1:-run}; SECS=${2:-60}; APP=${3:-ds_smoke_app.txt}
mkdir -p results
tegrastats --interval 1000 --logfile results/$TAG.tegra &
TP=$!
sleep 1
echo "start $(date +%T)" > results/$TAG.time
# --foreground: deepstream-app reads keyboard commands from the TTY; without it, it gets SIGTTIN and stops (state T)
timeout --foreground -s INT $SECS env -u PYTHONPATH deepstream-app -c $APP > results/$TAG.log 2>&1
echo "rc=$? end $(date +%T)" >> results/$TAG.time
kill $TP 2>/dev/null; wait $TP 2>/dev/null
echo "=== SMOKE-DONE $TAG"
