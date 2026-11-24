#!/bin/bash
# soak v3 logger: one soak.csv row every 60 s via soak_sample_v3.py. Runs at nice 19 in tmux "soak3".
# Env: SOAK_DIR (output folder), SOAK_START (epoch sec), SOAK_HOURS (default 24).
# Does NOT stop the app itself; on finish writes soak_done.txt (leave app as-is, events off).
set -u
DIR="${SOAK_DIR:?SOAK_DIR not set}"
START="${SOAK_START:?SOAK_START not set}"
HOURS="${SOAK_HOURS:-24}"
TOOLS="$HOME/safety/tools"
CSV="$DIR/soak.csv"
mkdir -p "$DIR"
HDR="timestamp,elapsed_h,uptime_app_s,fps_in,fps_infer,cpu_total_pct,cpu0_pct,cpu1_pct,gpu_pct,cpu_freq_mhz,gpu_freq_mhz,emc_freq_mhz,throttled,power_mw,power_gpu_mw,power_cpu_mw,temp_cpu_c,temp_gpu_c,temp_thermal_c,ram_used_mb,swap_used_mb,rss_app_mb,rss_cira_mb,disk_free_gb,snapshot_count,snapshot_size_mb,camera_connected,last_frame_age_s,persons,persons_compliant,persons_violating,unique_tracks_total,events_no_helmet,events_no_vest,events_restricted_zone,events_via_cira,events_via_fallback,cira_received,cira_published,cira_filtered,cira_status_age_s,mqtt_msgs_received_total,mqtt_msgs_sent_total,mqtt_clients,mqtt_dropped_total,container_restarts_total,dmesg_errors_total,app_restarts,pts_fixed,pts_rebase,live_status"
if [ ! -f "$CSV" ]; then printf '\xef\xbb\xbf%s\n' "$HDR" > "$CSV"; fi   # UTF-8 BOM
END=$(python3 -c "print(int($START + $HOURS*3600))")
export SOAK_DIR SOAK_START
while [ "$(date +%s)" -lt "$END" ]; do
  t0=$(date +%s)
  env -u PYTHONPATH nice -n 19 python3 "$TOOLS/soak_sample_v3.py" >> "$CSV" 2>/dev/null
  sleep $(python3 -c "import time;print(max(1,60-(time.time()-$t0)))" 2>/dev/null || echo 60)
done
echo "soak start=$(date -d @$START '+%F %T') end=$(date -d @$END '+%F %T') (${HOURS}h)" > "$DIR/soak_done.txt"
echo "$(date '+%F %T') logger stopped" >> "$DIR/soak_done.txt"
# v4 item6: run the full teardown DETACHED (setsid) so it survives ds-stop's signals and killing this
# tmux window. soak_end_v4.sh stops the sibling collectors, sets the app to events off, verifies, and
# kills the soak session itself at the end.
setsid nohup bash "$TOOLS/soak_end_v4.sh" >> "$DIR/soak_done.txt" 2>&1 &
disown 2>/dev/null || true
