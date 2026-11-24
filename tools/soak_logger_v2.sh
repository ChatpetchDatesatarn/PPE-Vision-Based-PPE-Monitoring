#!/bin/bash
# soak v2 logger: one soak.csv row every 60 s via soak_sample.py; stop after 24 h, then
# write soak_done.txt and switch the app to events off (ds-stop; ds-start). Runs at nice 19.
# Env: SOAK_DIR (output folder), SOAK_START (epoch sec). Run inside tmux "soak2".
set -u
DIR="${SOAK_DIR:?SOAK_DIR not set}"
START="${SOAK_START:?SOAK_START not set}"
TOOLS="$HOME/safety/tools"
CSV="$DIR/soak.csv"
mkdir -p "$DIR"
HDR="timestamp,elapsed_h,uptime_app_s,fps_in,fps_infer,cpu_total_pct,cpu0_pct,cpu1_pct,gpu_pct,cpu_freq_mhz,gpu_freq_mhz,emc_freq_mhz,throttled,power_mw,temp_cpu_c,temp_gpu_c,temp_thermal_c,ram_used_mb,swap_used_mb,rss_app_mb,rss_cira_mb,disk_free_gb,snapshot_count,snapshot_size_mb,camera_connected,last_frame_age_s,persons,persons_compliant,persons_violating,unique_tracks_total,events_no_helmet,events_no_vest,events_restricted_zone,events_via_cira,events_via_fallback,cira_received,cira_published,cira_filtered,cira_status_age_s,mqtt_msgs_received_total,mqtt_msgs_sent_total,mqtt_clients,mqtt_dropped_total,container_restarts_total,dmesg_errors_total"
if [ ! -f "$CSV" ]; then printf '\xef\xbb\xbf%s\n' "$HDR" > "$CSV"; fi   # UTF-8 BOM
END=$(( START + 86400 ))
export SOAK_DIR SOAK_START
while [ "$(date +%s)" -lt "$END" ]; do
  t0=$(date +%s)
  env -u PYTHONPATH nice -n 19 python3 "$TOOLS/soak_sample.py" >> "$CSV" 2>/dev/null
  # align to next 60 s
  sleep $(python3 -c "import time;print(max(1,60-(time.time()-$t0)))" 2>/dev/null || echo 60)
done
# 24 h reached
echo "soak v2 start=$(date -d @$START '+%F %T') end=$(date -d @$END '+%F %T') (24h)" > "$DIR/soak_done.txt"
echo "$(date '+%F %T') logger stop; switching app to events off (ds-stop; ds-start)" >> "$DIR/soak_done.txt"
"$HOME/ds-stop" >/dev/null 2>&1; sleep 2; "$HOME/ds-start" >/dev/null 2>&1
echo "$(date '+%F %T') app restarted events off, left running" >> "$DIR/soak_done.txt"
