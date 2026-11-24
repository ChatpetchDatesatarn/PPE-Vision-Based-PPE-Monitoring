#!/usr/bin/env python3
"""
Event recorder — saves events + snapshot images from CiRA CORE so the Dashboard can show history
- Subscribe factory/safety/+/event  -> decode snapshot_b64 -> data/snapshots/<event_id>.jpg
- Subscribe factory/safety/ack      -> update event status
- Write data/events.json (latest first, at most MAX_EVENTS) for nginx to serve at /data/events.json
See docs/mqtt_spec.md
"""
import base64
import json
import os
import re
import signal
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
DATA = os.environ.get("DATA_DIR", "/data")
MAX_EVENTS = int(os.environ.get("MAX_EVENTS", "1000"))
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
SNAP_DIR = os.path.join(DATA, "snapshots")
EVENTS_FILE = os.path.join(DATA, "events.json")
BKK = timezone(timedelta(hours=7))

lock = threading.Lock()
dirty = threading.Event()
events = []  # newest first


def now_iso():
    return datetime.now(BKK).isoformat(timespec="seconds")


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)[:120]


def load():
    global events
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            events = json.load(f)
        print("[rec] loaded %d events" % len(events), flush=True)
    except (OSError, ValueError):
        events = []


def save():
    tmp = EVENTS_FILE + ".tmp"
    with lock:
        data = json.dumps(events, ensure_ascii=False)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, EVENTS_FILE)


def trim():
    """Drop the oldest events beyond MAX_EVENTS and delete their snapshots."""
    while len(events) > MAX_EVENTS:
        old = events.pop()
        snap = old.get("snapshot")
        if snap:
            try:
                os.remove(os.path.join(DATA, os.path.relpath(snap, "data")))
            except OSError:
                pass


def handle_event(topic, payload):
    try:
        ev = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        print("[rec] bad JSON on", topic, flush=True)
        return
    if not isinstance(ev, dict):
        return
    cam = topic.split("/")[2]
    ev.setdefault("camera_id", cam)
    ev.setdefault("ts", now_iso())
    eid = str(ev.get("event_id") or "%s-%d" % (cam, int(time.time() * 1000)))
    ev["event_id"] = eid

    b64 = ev.pop("snapshot_b64", None)
    if b64:
        try:
            raw = base64.b64decode(b64)
            if len(raw) <= MAX_SNAPSHOT_BYTES and raw[:2] == b"\xff\xd8":
                fname = safe_name(eid) + ".jpg"
                with open(os.path.join(SNAP_DIR, fname), "wb") as f:
                    f.write(raw)
                ev["snapshot"] = "data/snapshots/" + fname
        except (ValueError, OSError) as e:
            print("[rec] snapshot error:", e, flush=True)

    ev.setdefault("status", "open")
    with lock:
        if any(e.get("event_id") == eid for e in events):
            return
        events.insert(0, ev)
        trim()
    dirty.set()
    print("[rec] %s %s" % (ev.get("type"), eid), flush=True)


def handle_ack(payload):
    try:
        a = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return
    with lock:
        for e in events:
            if e.get("event_id") == a.get("event_id"):
                e["status"] = a.get("status", "resolved")
                e["ack_by"] = a.get("by", "")
                e["ack_ts"] = a.get("ts") or now_iso()
                e["note"] = a.get("note", "")
                dirty.set()
                break


def on_connect(client, userdata, flags, rc, properties=None):
    print("[rec] connected rc=%s" % rc, flush=True)
    client.subscribe([("factory/safety/+/event", 1), ("factory/safety/ack", 1)])


def on_message(client, userdata, msg):
    if msg.topic.endswith("/event"):
        handle_event(msg.topic, msg.payload)
    elif msg.topic == "factory/safety/ack":
        handle_ack(msg.payload)


def main():
    os.makedirs(SNAP_DIR, exist_ok=True)
    load()
    save()
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="safety-recorder")
    except AttributeError:
        client = mqtt.Client(client_id="safety-recorder")
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(1, 10)
    client.connect_async(HOST, PORT, 30)
    client.loop_start()

    running = [True]
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
    try:
        while running[0]:
            if dirty.wait(1.0):
                dirty.clear()
                save()
    except KeyboardInterrupt:
        pass
    finally:
        save()
        client.loop_stop()


if __name__ == "__main__":
    main()
