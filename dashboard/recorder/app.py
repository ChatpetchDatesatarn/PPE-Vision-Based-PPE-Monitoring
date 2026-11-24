"""
Recorder v3 = MQTT subscriber + SQLite + HTTP API (FastAPI), one process.
Spec: docs/mqtt_spec.md (v3). Data logic: store.py.

MQTT in : factory/safety/+/event, factory/safety/+/snapshot/+, factory/safety/ack
HTTP out: /api/health, /api/events, /api/events/{id}, /api/stats/summary, /api/stats/daily, /api/export.csv
          POST /api/events/delete, POST /api/events/delete-range  (v6, need header X-Delete-Pin = DELETE_PIN)
Docs    : /api/docs (Swagger UI, for development)
"""
import hmac
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import Response

from store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [rec] %(message)s")
log = logging.getLogger("recorder")

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", "/data")
CLEANUP_INTERVAL_S = int(os.environ.get("CLEANUP_INTERVAL_S", "600"))
# v6: deleting from the Dashboard needs this PIN (set in .env next to docker-compose.yml). Empty = delete disabled.
DELETE_PIN = os.environ.get("DELETE_PIN", "").strip()
PIN_MAX_FAILS, PIN_LOCK_S = 5, 300

store = Store(DATA_DIR,
              max_snapshots=int(os.environ.get("MAX_SNAPSHOTS", "3000")),
              snapshot_max_age_days=int(os.environ.get("SNAPSHOT_MAX_AGE_DAYS", "30")))
mqtt_state = {"connected": False, "received": 0}

app = FastAPI(title="Safety recorder v3", docs_url="/api/docs", openapi_url="/api/openapi.json")


def bad_request(e):
    raise HTTPException(status_code=400, detail=str(e))


TZ_BKK = timezone(timedelta(hours=7))  # spec: all times are ISO 8601 with +07:00


@app.get("/api/health")
def health():
    # server_time / server_epoch_ms let the Dashboard correct a viewer clock that is off (round 2, item 2a)
    return dict(ok=True, mqtt="connected" if mqtt_state["connected"] else "disconnected",
                mqtt_messages=mqtt_state["received"],
                server_time=datetime.now(TZ_BKK).isoformat(timespec="seconds"),
                server_epoch_ms=int(time.time() * 1000),
                delete_enabled=bool(DELETE_PIN),
                **store.counts())


@app.get("/api/events")
def list_events(camera_id: str = None, type: str = None, severity: str = None, status: str = None,
                date_from: str = Query(None, alias="from"), date_to: str = Query(None, alias="to"),
                limit: int = 50, offset: int = 0):
    try:
        return store.query_events(camera_id, type, severity, status, date_from, date_to, limit, offset)
    except ValueError as e:
        bad_request(e)


@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    ev = store.get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    return ev


@app.get("/api/stats/summary")
def stats_summary(date: str = None):
    try:
        return store.summary(date)
    except ValueError as e:
        bad_request(e)


@app.get("/api/stats/daily")
def stats_daily(days: int = 7):
    return store.daily(days)


@app.get("/api/export.csv")
def export_csv(date_from: str = Query(None, alias="from"), date_to: str = Query(None, alias="to")):
    try:
        body = store.export_csv(date_from, date_to)
    except ValueError as e:
        bad_request(e)
    # v6: file name tells the range, e.g. safety_events_2026-10-01_2026-10-31.csv
    span = "_".join(x for x in (date_from, date_to) if x and len(x) == 10 and x[4] == "-") or "all"
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="safety_events_%s.csv"' % span})


# ---------------- delete (v6) ----------------
_pin_state = {"fails": 0, "locked_until": 0.0}


def check_pin(pin):
    if not DELETE_PIN:
        raise HTTPException(status_code=403, detail="ยังไม่ได้ตั้ง DELETE_PIN บนเครื่อง จึงลบไม่ได้")
    now = time.time()
    if now < _pin_state["locked_until"]:
        raise HTTPException(status_code=429, detail="ใส่ PIN ผิดหลายครั้ง ลองใหม่ใน %d วินาที"
                            % int(_pin_state["locked_until"] - now + 1))
    if not pin or not hmac.compare_digest(pin.encode("utf-8"), DELETE_PIN.encode("utf-8")):
        _pin_state["fails"] += 1
        if _pin_state["fails"] >= PIN_MAX_FAILS:
            _pin_state.update(fails=0, locked_until=now + PIN_LOCK_S)
        raise HTTPException(status_code=401, detail="PIN ไม่ถูกต้อง")
    _pin_state["fails"] = 0


def client_of(request):
    return request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")


@app.post("/api/events/delete")
def delete_events(request: Request, payload: dict = Body(...), x_delete_pin: str = Header(None)):
    check_pin(x_delete_pin)
    try:
        res = store.delete_events(payload.get("event_ids"))
    except ValueError as e:
        bad_request(e)
    log.warning("DELETE by id: %d events, %d snapshots (client %s)", res["events"], res["snapshots"], client_of(request))
    return res


@app.post("/api/events/delete-range")
def delete_range(request: Request, payload: dict = Body(...), x_delete_pin: str = Header(None)):
    check_pin(x_delete_pin)
    try:
        res = store.delete_range(payload.get("from"), payload.get("to"))
    except ValueError as e:
        bad_request(e)
    log.warning("DELETE range %s..%s: %d events, %d snapshots (client %s)", payload.get("from"), payload.get("to"),
                res["events"], res["snapshots"], client_of(request))
    return res


# ---------------- MQTT ----------------
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        mqtt_state["connected"] = True
        client.subscribe([("factory/safety/+/event", 1), ("factory/safety/+/snapshot/+", 1),
                          ("factory/safety/ack", 1)])
        log.info("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
    else:
        log.warning("MQTT connect failed: %s", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    mqtt_state["connected"] = False
    log.warning("MQTT disconnected (%s), retrying", reason_code)


def on_message(client, userdata, msg):
    mqtt_state["received"] += 1
    parts = msg.topic.split("/")  # factory/safety/<cam>/event | factory/safety/<cam>/snapshot/<id> | factory/safety/ack
    try:
        if len(parts) == 4 and parts[3] == "event":
            if not store.add_event(msg.payload, topic_camera=parts[2]):
                log.warning("rejected event on %s", msg.topic)
        elif len(parts) == 5 and parts[3] == "snapshot":
            if not store.save_snapshot(parts[4], msg.payload):
                log.warning("rejected snapshot on %s", msg.topic)
        elif msg.topic == "factory/safety/ack":
            store.apply_ack(msg.payload)
    except Exception:  # never let one bad message kill the MQTT thread
        log.exception("error handling %s", msg.topic)


def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="recorder-v3")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(1, 10)
    client.connect_async(MQTT_HOST, MQTT_PORT, 30)
    client.loop_start()
    return client


def cleanup_loop():
    while True:
        try:
            removed = store.cleanup()
            if any(removed.values()):
                log.info("cleanup removed %s", removed)
        except Exception:
            log.exception("cleanup failed")
        time.sleep(CLEANUP_INTERVAL_S)


if __name__ == "__main__":
    n = store.migrate_events_json(os.path.join(DATA_DIR, "events.json"))
    if n:
        log.info("migrated %d events from v2 events.json", n)
    start_mqtt()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")
