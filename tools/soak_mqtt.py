#!/usr/bin/env python3
# soak v2 MQTT recorder (single Jetson clock, ms). Writes cam01_event.log, cira_status.log,
# latency.csv (ds/violation <-> event paired by snapshot_id) and filtered.csv (ds dropped by CiRA).
# Env: SOAK_DIR. paho 1.x/2.x compatible. Run at nice 19 in tmux "soak2".
import os, time, json, threading
import paho.mqtt.client as mqtt

DIR = os.environ.get("SOAK_DIR", ".")
EVLOG  = open(os.path.join(DIR, "cam01_event.log"), "a", buffering=1, encoding="utf-8")
HBLOG  = open(os.path.join(DIR, "cira_status.log"), "a", buffering=1, encoding="utf-8")
def openbom(name, header):
    path = os.path.join(DIR, name); new = not os.path.exists(path) or os.path.getsize(path) == 0
    f = open(path, "a", buffering=1, encoding="utf-8")
    if new: f.write("﻿" + header + "\n")
    return f
LAT = openbom("latency.csv", "snapshot_id,event_id,ds_rx_ms,event_rx_ms,latency_ms,type,confidence,track_id,zone_id")
FIL = openbom("filtered.csv", "ds_rx_ms,type,confidence,track_id,reason")

PRE = "factory/safety/"
pend = {}                 # snapshot_id -> (ds_rx_ms, type, conf, track, zone)
last_event = {}           # (track, type) -> event_rx_ms
lock = threading.Lock()

def now_ms(): return int(time.time() * 1000)

def on_connect(c, u, f, rc, *a):
    c.subscribe([(PRE + "cam01/ds/violation", 0), (PRE + "cam01/event", 0), (PRE + "cira/status", 0)])

def on_message(c, u, msg):
    rx = now_ms(); topic = msg.topic
    try: d = json.loads(msg.payload.decode("utf-8", "replace"))
    except Exception: d = None
    if topic.endswith("/cira/status"):
        HBLOG.write("%d %s %s\n" % (rx, topic, msg.payload.decode("utf-8", "replace"))); return
    if d is None: return
    if topic.endswith("/ds/violation"):
        sid = d.get("snapshot_id", "")
        with lock:
            pend[sid] = (rx, d.get("type", ""), d.get("conf", ""), d.get("track_id", ""), d.get("zone_id", ""))
    elif topic.endswith("/event"):
        EVLOG.write("%d %s %s\n" % (rx, topic, msg.payload.decode("utf-8", "replace")))
        sid = d.get("snapshot_id", ""); eid = d.get("event_id", "")
        typ = d.get("type", ""); tr = d.get("track_id", "")
        with lock:
            last_event[(tr, typ)] = rx
            if sid in pend:
                dsrx = pend[sid][0]
                LAT.write("%s,%s,%d,%d,%d,%s,%s,%s,%s\n" % (
                    sid, eid, dsrx, rx, rx - dsrx, typ, d.get("confidence", ""), tr, d.get("zone_id", "")))
                del pend[sid]

def sweeper():
    while True:
        time.sleep(1); cut = now_ms() - 35000
        with lock:
            for sid in [k for k, v in pend.items() if v[0] < cut]:
                dsrx, typ, conf, tr, zone = pend.pop(sid)
                le = last_event.get((tr, typ))
                reason = "cooldown" if (le is not None and dsrx - le < 30000) else ""
                FIL.write("%d,%s,%s,%s,%s\n" % (dsrx, typ, conf, tr, reason))

cli = None
try:
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)   # paho 2.x
except Exception:
    cli = mqtt.Client()                                   # paho 1.x
cli.on_connect = on_connect; cli.on_message = on_message
cli.connect("127.0.0.1", 1883, 60)
threading.Thread(target=sweeper, daemon=True).start()
cli.loop_forever()
