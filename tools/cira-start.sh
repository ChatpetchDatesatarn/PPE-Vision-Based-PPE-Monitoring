#!/bin/bash
# Start Xvfb :99 (fresh) + CiRA (cira_core_launch) at nice 19 in tmux cira-gui. No x11vnc.
# A long-lived Xvfb :99 wedges new Qt xcb clients ("could not connect to display :99"), so whenever
# CiRA is not already running this restarts Xvfb :99 fresh before launching CiRA. If CiRA is already
# running it does nothing and leaves Xvfb untouched.
# Note: the project must be opened and Run pressed in the GUI (via ds-vnc-on) - no working CLI auto-load/auto-run.
tmux has-session -t cira-gui 2>/dev/null || tmux new-session -d -s cira-gui -x 200 -y 50
if pgrep -f cira_core_run >/dev/null; then echo "CiRA already running - Xvfb left untouched"; exit 0; fi
# CiRA not running: restart Xvfb :99 fresh to avoid the wedged-display problem
pkill -f "Xvfb :99"; sleep 1
tmux send-keys -t cira-gui:0 "Xvfb :99 -screen 0 1600x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &" Enter
sleep 3
cat > /tmp/cira_env_launch.sh <<"INNER"
#!/bin/bash
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/lib
source /opt/ros/melodic/setup.bash
source ~/.cira_core_install/cira_libs_ws/install/setup.bash --extend
export LD_LIBRARY_PATH=$(find /usr/lib -iname nvidia-* -type d 2>&1 | sed "{:q;N;s/\n/:/g;t q}"):${LD_LIBRARY_PATH}
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/opt/qt511/lib
export DISPLAY=:99
# Keep ROS (roscore/rosmaster/rosout and cira_core_run's XML-RPC ports) on loopback so they are not
# reachable on the LAN. Everything here is on one box, so localhost is enough.
export ROS_IP=127.0.0.1
export ROS_HOSTNAME=localhost
export ROS_MASTER_URI=http://127.0.0.1:11311
exec rosrun cira_core cira_core_launch
INNER
chmod +x /tmp/cira_env_launch.sh
tmux list-windows -t cira-gui -F "#{window_name}" | grep -qx cira || tmux new-window -t cira-gui -n cira
tmux send-keys -t cira-gui:cira "nice -n 19 bash /tmp/cira_env_launch.sh >/tmp/cira.log 2>&1" Enter
echo "launching CiRA (nice 19) ... open the project + press Run in the GUI via ds-vnc-on"
for i in $(seq 1 30); do sleep 1; pgrep -f cira_core_run >/dev/null && break; done
sleep 3
for p in $(pgrep -f "cira_core_run|cira_core_launch|rosmaster|roscore|rosout|Xvfb :99"); do
  ni=$(ps -o ni= -p $p 2>/dev/null | tr -d " "); [ "$ni" = "19" ] || renice -n 19 -p $p >/dev/null 2>&1
done
ps -eo pid,ni,comm | grep -E "cira_core|roscore|rosmaster|rosout|Xvfb" | grep -v grep
