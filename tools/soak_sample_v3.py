#!/usr/bin/env python3
# Emit one soak v3 data row (no header). Reads env SOAK_DIR, SOAK_START (epoch sec).
# v3 vs v2: power from INA3221 sysfs via sudo (3 rails), gpu/emc freq + throttle filled,
# is_night dropped (brightness lives in the slow sampler). Every metric best-effort: blank on failure.
import os, sys, re, time, json, subprocess as sp

DIR   = os.environ.get("SOAK_DIR", ".")
START = float(os.environ.get("SOAK_START", "0"))
EVLOG = os.path.join(DIR, "cam01_event.log")
IIO   = "/sys/bus/iio/devices/iio:device0"   # ina3221x: rail0 POM_5V_IN, rail1 GPU, rail2 CPU

def run(cmd, t=8):
    try:
        return sp.check_output(cmd, shell=True, stderr=sp.DEVNULL, timeout=t).decode("utf-8", "replace")
    except Exception:
        return ""

def sub1(topic, t=8):
    return run("timeout %d mosquitto_sub -h 127.0.0.1 -t '%s' -C 1" % (t, topic), t + 2).strip()

def readnum(path, sudo=False):
    v = run(("sudo -n cat %s" if sudo else "cat %s") % path, 4).strip()
    return v if v.lstrip("-").isdigit() else ""

now = time.time()
ts  = time.strftime("%Y-%m-%d %H:%M:%S (+07:00)", time.localtime(now))
elapsed_h = "%.2f" % ((now - START) / 3600.0) if START else ""

C = {}

# ---- app uptime ----
try:
    pid = run("pgrep -f 'python3 -u person_count_app.py'").split()
    C["uptime_app_s"] = run("ps -o etimes= -p %s" % pid[0]).strip() if pid else ""
except Exception:
    C["uptime_app_s"] = ""

# ---- cam01/status ----
try:
    d = json.loads(sub1("factory/safety/cam01/status"))
    C["fps_in"]=d.get("fps_in",""); C["fps_infer"]=d.get("fps_infer","")
    C["camera_connected"]=1 if d.get("camera_connected") else 0
    C["last_frame_age_s"]=d.get("last_frame_age_s","")
    C["persons"]=d.get("persons",""); C["persons_compliant"]=d.get("compliant","")
    C["persons_violating"]=d.get("violating","")
except Exception:
    pass

# ---- tegrastats (cpu %, gpu %, ram, swap, temps) ----
tg = run("timeout 3 tegrastats --interval 1000 | head -1", 6)
try:
    pcts=[]; freq=""
    for m in re.finditer(r"(\d+)%@(\d+)", tg.split("CPU [")[1].split("]")[0]):
        pcts.append(int(m.group(1))); freq=m.group(2)
    if pcts:
        C["cpu_total_pct"]=round(sum(pcts)/len(pcts),1)
        C["cpu0_pct"]=pcts[0]; C["cpu1_pct"]=pcts[1] if len(pcts)>1 else ""
        C["cpu_freq_mhz"]=freq
    g=re.search(r"GR3D_FREQ (\d+)%", tg);  C["gpu_pct"]=g.group(1) if g else ""
    r=re.search(r"RAM (\d+)/(\d+)MB", tg); C["ram_used_mb"]=r.group(1) if r else ""
    s=re.search(r"SWAP (\d+)/(\d+)MB", tg);C["swap_used_mb"]=s.group(1) if s else ""
    for key,pat in [("temp_cpu_c","CPU@([0-9.]+)C"),("temp_gpu_c","GPU@([0-9.]+)C"),
                    ("temp_thermal_c","thermal@([0-9.]+)C")]:
        mm=re.search(pat,tg); C[key]=mm.group(1) if mm else ""
except Exception:
    pass

# ---- power: INA3221 sysfs via sudo (v3 fix; tegrastats on this board has no power field) ----
C["power_mw"]     = readnum(IIO + "/in_power0_input", sudo=True)   # POM_5V_IN (total)
C["power_gpu_mw"] = readnum(IIO + "/in_power1_input", sudo=True)
C["power_cpu_mw"] = readnum(IIO + "/in_power2_input", sudo=True)

# ---- gpu / emc freq + throttle (v3 fix) ----
gf = readnum("/sys/class/devfreq/57000000.gpu/cur_freq")            # Hz (user-readable)
C["gpu_freq_mhz"] = int(round(int(gf)/1e6)) if gf else ""
ef = readnum("/sys/kernel/debug/clk/emc/clk_rate", sudo=True)       # Hz (needs sudo)
C["emc_freq_mhz"] = int(round(int(ef)/1e6)) if ef else ""
cur = readnum("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
mx  = readnum("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
C["throttled"] = (1 if (cur and mx and int(cur) < int(mx)) else 0) if (cur and mx) else ""

# ---- rss ----
def rss_mb(pat):
    # v4: pick the largest-RSS match (the main process, not a short-lived child)
    best=""
    for pid in run("pgrep -f '%s'"%pat).split():
        r=run("ps -o rss= -p %s"%pid).strip()
        if r.isdigit():
            v=round(int(r)/1024.0,1)
            if best=="" or v>best: best=v
    return best
C["rss_app_mb"]=rss_mb("person_count_app.py")
C["rss_cira_mb"]=rss_mb("cira_core_run")

# ---- disk / snapshots ----
dfree=run("df -BM --output=avail / | tail -1").strip().rstrip("M")
C["disk_free_gb"]=round(int(dfree)/1024.0,2) if dfree.isdigit() else ""
try:
    h=json.loads(run("curl -s --max-time 6 127.0.0.1:8000/api/health"))
    C["snapshot_count"]=h.get("snapshots","")
except Exception:
    C["snapshot_count"]=""
sz=run("docker exec recorder du -sm /data/snapshots | cut -f1").strip()
C["snapshot_size_mb"]=sz if sz.isdigit() else ""

# ---- events from cam01_event.log (cumulative) ----
try:
    txt=open(EVLOG,encoding="utf-8",errors="replace").read() if os.path.exists(EVLOG) else ""
    C["events_no_helmet"]=txt.count('"type":"no_helmet"')
    C["events_no_vest"]=txt.count('"type":"no_vest"')
    C["events_restricted_zone"]=txt.count('"type":"restricted_zone"')
    C["events_via_cira"]=txt.count('"via":"cira"')
    C["events_via_fallback"]=txt.count('"via":"fallback"')
    C["unique_tracks_total"]=len(set(re.findall(r'"track_id":(\d+)',txt)))
except Exception:
    pass

# ---- cira/status ----
try:
    d=json.loads(sub1("factory/safety/cira/status",13))
    C["cira_received"]=d.get("received",""); C["cira_published"]=d.get("published","")
    C["cira_filtered"]=d.get("filtered","")
    b=time.strptime(d["ts"][:19],"%Y-%m-%dT%H:%M:%S")
    C["cira_status_age_s"]=int(time.time()-time.mktime(b))
except Exception:
    pass

# ---- mosquitto $SYS ----
try:
    out=run("timeout 12 mosquitto_sub -h 127.0.0.1 -C 4 -v "
            "-t '$SYS/broker/messages/received' -t '$SYS/broker/messages/sent' "
            "-t '$SYS/broker/clients/connected' -t '$SYS/broker/publish/messages/dropped'", 14)
    sysd={}
    for ln in out.splitlines():
        p=ln.rsplit(" ",1)
        if len(p)==2 and p[1].strip().lstrip("-").isdigit(): sysd[p[0].strip()]=p[1].strip()
    C["mqtt_msgs_received_total"]=sysd.get("$SYS/broker/messages/received","")
    C["mqtt_msgs_sent_total"]=sysd.get("$SYS/broker/messages/sent","")
    C["mqtt_clients"]=sysd.get("$SYS/broker/clients/connected","")
    C["mqtt_dropped_total"]=sysd.get("$SYS/broker/publish/messages/dropped","")
except Exception:
    pass

# ---- app PTS/restart stats + live_status (v4 item5) from the app's 60 s fps log line ----
appln = run("tmux capture-pane -pt ds 2>/dev/null | grep -E 'pts_fixed=' | tail -1")
def _f(name):
    m = re.search(name + r"=([0-9.]+)", appln)
    return m.group(1) if m else ""
C["app_restarts"] = _f("app_restarts")
C["pts_fixed"]    = _f("pts_fixed")
C["pts_rebase"]   = _f("pts_rebase")
dmax = _f("pts_dmax_ms")
if appln == "":
    C["live_status"] = "unknown"           # app log not readable
else:
    try:
        # pts_dmax ~1 ms = PTS pinned (A1 bug / stream broken); healthy stream is ~33/66 ms
        C["live_status"] = "stalled" if float(dmax) < 5 else "ok"
    except Exception:
        C["live_status"] = "unknown"

# ---- container restarts / dmesg ----
tot=0; ok=True
for c in ["mosquitto","mediamtx","dashboard","recorder"]:
    v=run("docker inspect -f '{{.RestartCount}}' %s"%c).strip()
    if v.isdigit(): tot+=int(v)
    else: ok=False
C["container_restarts_total"]=tot if ok else ""
dm=run("dmesg --level=err 2>/dev/null | wc -l").strip()
C["dmesg_errors_total"]=dm if dm.isdigit() else ""

COLS=["fps_in","fps_infer","cpu_total_pct","cpu0_pct","cpu1_pct","gpu_pct","cpu_freq_mhz",
 "gpu_freq_mhz","emc_freq_mhz","throttled","power_mw","power_gpu_mw","power_cpu_mw",
 "temp_cpu_c","temp_gpu_c","temp_thermal_c",
 "ram_used_mb","swap_used_mb","rss_app_mb","rss_cira_mb","disk_free_gb","snapshot_count","snapshot_size_mb",
 "camera_connected","last_frame_age_s","persons","persons_compliant","persons_violating","unique_tracks_total",
 "events_no_helmet","events_no_vest","events_restricted_zone","events_via_cira","events_via_fallback",
 "cira_received","cira_published","cira_filtered","cira_status_age_s",
 "mqtt_msgs_received_total","mqtt_msgs_sent_total","mqtt_clients","mqtt_dropped_total",
 "container_restarts_total","dmesg_errors_total",
 "app_restarts","pts_fixed","pts_rebase","live_status"]
row=[ts,elapsed_h,str(C.get("uptime_app_s",""))]+[str(C.get(k,"")) for k in COLS]
sys.stdout.write(",".join(row)+"\n")
