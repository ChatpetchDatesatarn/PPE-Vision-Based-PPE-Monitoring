"""MQTT <cam>/status heartbeat for person_count_app.py (pure Python, 3.6-compatible, paho-mqtt 1.x and 2.x).

docs/mqtt_spec.md v3 section 3: published every 5 s, QoS 1, retained; LWT {"online":false} on the same topic.
Fields: camera_id, name, ts (+07:00, no milliseconds), online, camera_connected, fps_in, fps_infer,
last_frame_age_s, resolution, model, persons, compliant, violating, stream_path
(+ v7.1 optional: ppe_both, ppe_helmet_only, ppe_vest_only, ppe_none, ppe_unknown).
"""
import json
import time

TOPIC_PREFIX = "factory/safety/"
STATUS_EVERY_S = 5
LWT_PAYLOAD = json.dumps({"online": False})
PPE_KEYS = ("ppe_both", "ppe_helmet_only", "ppe_vest_only", "ppe_none", "ppe_unknown")


def status_topic(camera_id):
    return "%s%s/status" % (TOPIC_PREFIX, camera_id)


def iso07(epoch=None):
    """ISO 8601 in +07:00 without milliseconds, independent of the machine's timezone: 2026-10-16T08:02:03+07:00"""
    t = time.time() if epoch is None else epoch
    return time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.gmtime(int(t) + 7 * 3600))


def ppe_counts(states):
    """states: [(helmet, vest)] with True / False / None (None = not known yet).
    compliant = both True; violating = at least one False; a person with only "?" is neither."""
    compliant = sum(1 for h, v in states if h is True and v is True)
    violating = sum(1 for h, v in states if h is False or v is False)
    return compliant, violating


def ppe_breakdown(states):
    """v7.1: what the people in view wear. states: [(helmet, vest)] with True / False / None.
    A person with any "?" (None) counts as unknown; otherwise exactly one of both / helmet_only / vest_only / none."""
    out = {"ppe_both": 0, "ppe_helmet_only": 0, "ppe_vest_only": 0, "ppe_none": 0, "ppe_unknown": 0}
    for h, v in states:
        if h is None or v is None:
            out["ppe_unknown"] += 1
        elif h and v:
            out["ppe_both"] += 1
        elif h:
            out["ppe_helmet_only"] += 1
        elif v:
            out["ppe_vest_only"] += 1
        else:
            out["ppe_none"] += 1
    return out


def build_status(camera_id, name, online, camera_connected, fps_in, fps_infer, last_frame_age_s,
                 resolution, model, persons, compliant, violating, stream_path, epoch=None, ppe=None):
    r = lambda x: None if x is None else round(float(x), 1)  # noqa: E731
    d = {
        "camera_id": camera_id, "name": name, "ts": iso07(epoch),
        "online": bool(online), "camera_connected": bool(camera_connected),
        "fps_in": r(fps_in), "fps_infer": r(fps_infer), "last_frame_age_s": r(last_frame_age_s),
        "resolution": resolution, "model": model,
        "persons": int(persons), "compliant": int(compliant), "violating": int(violating),
        "stream_path": stream_path,
    }
    if ppe is not None:          # v7.1: only when known (keeps the old field set otherwise)
        d.update({k: int(ppe.get(k, 0)) for k in PPE_KEYS})
    return d


def make_client(client_id, camera_id):
    """paho client with the LWT set (not connected). Works on paho-mqtt 1.6.x (Jetson) and 2.x (PC)."""
    import paho.mqtt.client as mqtt
    if hasattr(mqtt, "CallbackAPIVersion"):     # 2.x: keep the 1.x callback signatures
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    else:
        c = mqtt.Client(client_id=client_id)
    c.will_set(status_topic(camera_id), LWT_PAYLOAD, qos=1, retain=True)
    c.reconnect_delay_set(min_delay=1, max_delay=10)
    return c
