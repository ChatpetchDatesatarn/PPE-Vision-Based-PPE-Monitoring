#!/usr/bin/env python3
# soak v2 watcher: every 60 s read the latest soak.csv (+ mediamtx.csv) row and log WARNINGs to
# watch.log. The ONLY action it takes is: disk_free_gb < 3 -> switch app to events off (ds-stop;
# ds-start) once. Everything else is log-only. nice 19, tmux "soak2". Env: SOAK_DIR.
import os, time, csv, subprocess as sp
DIR = os.environ.get("SOAK_DIR", ".")
WLOG = open(os.path.join(DIR, "watch.log"), "a", buffering=1, encoding="utf-8")
def warn(msg): WLOG.write("%s WARNING %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S (+07:00)"), msg))

def last_row(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return rows[-1] if rows else None
    except Exception:
        return None

def fnum(r, k):
    try: return float(r.get(k, "")) if r.get(k, "") != "" else None
    except Exception: return None

prev_restart = prev_dmesg = prev_bframes = None
low_fps_streak = 0
disk_fired = False

while True:
    r = last_row(os.path.join(DIR, "soak.csv"))
    m = last_row(os.path.join(DIR, "mediamtx.csv"))
    if r:
        v = lambda k: fnum(r, k)
        sc = v("snapshot_count")
        if sc is not None and sc > 3300: warn("snapshot_count=%d > 3300" % sc)
        df = v("disk_free_gb")
        if df is not None and df < 3 and not disk_fired:
            warn("disk_free_gb=%.2f < 3 -> ds-stop; ds-start (events off)" % df)
            try:
                sp.call([os.path.expanduser("~/ds-stop")]); time.sleep(2)
                sp.call([os.path.expanduser("~/ds-start")])
                warn("app restarted events off (disk safety)")
            except Exception as e:
                warn("disk-safety restart failed: %s" % e)
            disk_fired = True
        cc = r.get("camera_connected", ""); lfa = v("last_frame_age_s")
        if cc == "0": warn("camera_connected=0")
        if lfa is not None and lfa > 3: warn("last_frame_age_s=%.1f > 3" % lfa)
        ca = v("cira_status_age_s")
        if ca is not None and ca > 30: warn("cira_status_age_s=%d > 30" % ca)
        fi = v("fps_in")
        if fi is not None and fi < 20:
            low_fps_streak += 1
            if low_fps_streak >= 2: warn("fps_in<20 for >1min (fps_in=%.1f)" % fi)
        else:
            low_fps_streak = 0
        th = r.get("throttled", "")
        if th == "1": warn("throttled=1")
        tc = v("temp_cpu_c")
        if tc is not None and tc > 75: warn("temp_cpu_c=%.1f > 75" % tc)
        rs = v("container_restarts_total")
        if rs is not None:
            if prev_restart is not None and rs > prev_restart: warn("container_restarts_total %d->%d" % (prev_restart, rs))
            prev_restart = rs
        dm = v("dmesg_errors_total")
        if dm is not None:
            if prev_dmesg is not None and dm > prev_dmesg: warn("dmesg_errors_total %d->%d" % (prev_dmesg, dm))
            prev_dmesg = dm
    if m:
        bf = fnum(m, "bframes_lines_total")
        if bf is not None:
            if prev_bframes is not None and bf > prev_bframes: warn("mediamtx B-frames %d->%d" % (prev_bframes, bf))
            prev_bframes = bf
    time.sleep(60)
