"""Mock backend for dashboard v3 UI testing (no docker): static files + /api + MQTT-over-WS broker + simulator.

Usage: python mock_server.py <web_dir> [port]
Control: GET /mock/ctl?cira_down=1|0&camera_down=1|0&sim=1|0&mqtt=1|0&whep=1|0&clock_skew=S&burst=N
"""
import asyncio, csv, io, json, random, sys, uuid
from datetime import datetime, timedelta, timezone
from aiohttp import web, WSMsgType

WEB = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
TZ = timezone(timedelta(hours=7))
P = "factory/safety/"
TYPES = ["no_helmet", "no_vest", "restricted_zone", "unknown_visibility"]
SEVS = ["critical", "high", "warning", "info"]

ctl = {"cira_down": False, "camera_down": False, "sim": True, "mqtt": True, "whep": False}
clock_skew_s = 0     # simulated server clock offset (seconds), /mock/ctl?clock_skew=60
whep_sessions = {}   # session id -> stream path (only when whep=1)
events = []          # newest last
snap_ready = {}      # snapshot_id -> ready time
cira = {"received": 0, "published": 0, "filtered": 0}
mqtt_count = 0

def now(): return datetime.now(TZ) + timedelta(seconds=clock_skew_s)
def iso(d): return d.isoformat(timespec="seconds")

# ---------------- MQTT broker (3.1.1 subset) ----------------
clients = set()
retained = {}

def match(flt, topic):
    f, t = flt.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#": return True
        if i >= len(t): return False
        if part != "+" and part != t[i]: return False
    return len(f) == len(t)

def enc_len(n):
    out = bytearray()
    while True:
        b = n % 128; n //= 128
        out.append(b | (0x80 if n else 0))
        if not n: return bytes(out)

def publish_packet(topic, payload, retain=False):
    tb = topic.encode()
    body = len(tb).to_bytes(2, "big") + tb + payload
    return bytes([0x30 | (1 if retain else 0)]) + enc_len(len(body)) + body

class Client:
    def __init__(self, ws): self.ws, self.subs, self.buf = ws, set(), bytearray()
    async def send(self, data):
        try: await self.ws.send_bytes(data)
        except Exception: pass

async def broker_publish(topic, payload, retain=False, origin=None):
    global mqtt_count
    mqtt_count += 1
    if retain:
        if payload: retained[topic] = payload
        else: retained.pop(topic, None)
    on_message(topic, payload)
    pkt = publish_packet(topic, payload)
    for c in list(clients):
        if any(match(f, topic) for f in c.subs): await c.send(pkt)

def on_message(topic, payload):  # recorder role
    if topic == P + "ack":
        try: a = json.loads(payload)
        except Exception: return
        for e in events:
            if e["event_id"] == a.get("event_id"):
                e.update(status=a.get("status"), acked_at=a.get("ts"), ack_by=a.get("by"), note=a.get("note") or None)

async def handle_packets(c):
    while True:
        if len(c.buf) < 2: return
        mult, n, i = 1, 0, 1
        while True:
            if i >= len(c.buf): return
            b = c.buf[i]; n += (b & 127) * mult; mult *= 128; i += 1
            if not b & 128: break
        if len(c.buf) < i + n: return
        h, body = c.buf[0], bytes(c.buf[i:i + n]); del c.buf[:i + n]
        t = h >> 4
        if t == 1: await c.send(b"\x20\x02\x00\x00")
        elif t == 3:
            qos, retain = (h >> 1) & 3, h & 1
            tl = int.from_bytes(body[:2], "big"); topic = body[2:2 + tl].decode(); pos = 2 + tl
            pid = None
            if qos: pid = body[pos:pos + 2]; pos += 2
            await broker_publish(topic, body[pos:], bool(retain), c)
            if qos == 1: await c.send(b"\x40\x02" + pid)
        elif t == 8:
            pid, pos, granted, new = body[:2], 2, bytearray(), []
            while pos < len(body):
                tl = int.from_bytes(body[pos:pos + 2], "big"); f = body[pos + 2:pos + 2 + tl].decode(); pos += 2 + tl + 1
                c.subs.add(f); new.append(f); granted.append(0)
            await c.send(bytes([0x90]) + enc_len(2 + len(granted)) + pid + bytes(granted))
            for topic, payload in list(retained.items()):
                if any(match(f, topic) for f in new): await c.send(publish_packet(topic, payload, True))
        elif t == 10:
            pid, pos = body[:2], 2
            while pos < len(body):
                tl = int.from_bytes(body[pos:pos + 2], "big"); c.subs.discard(body[pos + 2:pos + 2 + tl].decode()); pos += 2 + tl
            await c.send(b"\xb0\x02" + pid)
        elif t == 12: await c.send(b"\xd0\x00")
        elif t == 14: await c.ws.close(); return

async def ws_mqtt(request):
    if not ctl["mqtt"]: return web.Response(status=502)
    ws = web.WebSocketResponse(protocols=("mqtt",))
    await ws.prepare(request)
    c = Client(ws); clients.add(c)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                c.buf += msg.data; await handle_packets(c)
    finally:
        clients.discard(c)
    return ws

# ---------------- simulator ----------------
CAMS = {"cam01": "CAM 01 - Main Entrance", "cam02": "CAM 02 - Factory Floor"}

async def sim_status():
    while True:
        if ctl["sim"] and ctl["mqtt"]:
            for cid, name in CAMS.items():
                persons = random.randint(2, 6); viol = random.randint(0, 2)
                st = dict(camera_id=cid, name=name, ts=iso(now()), online=True,
                          camera_connected=not (ctl["camera_down"] and cid == "cam01"),
                          fps_in=25.0, fps_infer=round(random.uniform(14, 16), 1), last_frame_age_s=0.04,
                          resolution="1920x1080", model="yolov8s-ppe", persons=persons,
                          compliant=persons - viol, violating=viol, stream_path=cid)
                await broker_publish(f"{P}{cid}/status", json.dumps(st).encode(), True)
            if not ctl["cira_down"]:
                await broker_publish(P + "cira/status", json.dumps(dict(online=True, ts=iso(now()), flow="ppe-v3", **cira)).encode(), True)
        await asyncio.sleep(2)

async def make_event(ts=None, live=True):
    cid = random.choice(list(CAMS))
    sid = uuid.uuid4().hex[:12]
    t = random.choice(TYPES)
    sev = {"restricted_zone": "critical", "no_helmet": "high", "no_vest": "warning"}.get(t, "info")
    via = "fallback" if ctl["cira_down"] else "cira"
    e = dict(event_id=uuid.uuid4().hex, ts=iso(ts or now()), camera_id=cid,
             zone_id="zone-a" if t == "restricted_zone" else None, type=t, severity=sev,
             track_id=random.randint(1, 300), confidence=round(random.uniform(.55, .98), 2),
             bbox=[round(random.random() * .6, 3), round(random.random() * .5, 3), .12, .3],
             snapshot_id=sid, via=via)
    cira["received"] += 2; cira["published"] += 1; cira["filtered"] += 1
    snap_ready[sid] = (now() + timedelta(milliseconds=500)) if live else now()
    rec = dict(e, status="open", acked_at=None, ack_by=None, note=None)
    if not live and random.random() < .5:
        rec.update(status=random.choice(["resolved", "false_alarm"]), acked_at=iso(ts), ack_by="dashboard")
    events.append(rec)
    if live: await broker_publish(f"{P}{cid}/event", json.dumps(e).encode())

async def sim_events():
    while True:
        await asyncio.sleep(random.uniform(5, 9))
        if ctl["sim"] and ctl["mqtt"]: await make_event()

async def seed():
    base = now()
    for i in range(140):
        await make_event(base - timedelta(minutes=random.randint(5, 60 * 24 * 9)), live=False)
    events.sort(key=lambda e: e["ts"])

# ---------------- API ----------------
def api_event(e):
    d = dict(e)
    d["snapshot_url"] = f"/data/snapshots/{e['snapshot_id']}.jpg" if e["snapshot_id"] in snap_ready and snap_ready[e["snapshot_id"]] <= now() else None
    return d

def bad(msg): return web.json_response({"detail": msg}, status=400)

def parse_day(s, end=False):
    if not s: return None
    if len(s) == 10:
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=TZ)
        return d + timedelta(days=1) if end else d
    return datetime.fromisoformat(s)

def filtered(q):
    out = events
    for k in ("camera_id", "type", "severity", "status"):
        if q.get(k): out = [e for e in out if e[k] == q[k]]
    f, t = parse_day(q.get("from")), parse_day(q.get("to"), True)
    if f: out = [e for e in out if datetime.fromisoformat(e["ts"]) >= f]
    if t: out = [e for e in out if datetime.fromisoformat(e["ts"]) < t]
    return out

async def h_events(r):
    q = r.query
    try:
        limit = int(q.get("limit", 50)); offset = int(q.get("offset", 0))
        filtered({"from": q.get("from"), "to": q.get("to")})
    except ValueError as ex: return bad(f"invalid parameter: {ex}")
    if not 1 <= limit <= 500: return bad("limit must be 1-500")
    items = sorted(filtered(q), key=lambda e: e["ts"], reverse=True)
    return web.json_response({"total": len(items), "items": [api_event(e) for e in items[offset:offset + limit]]})

async def h_event(r):
    for e in events:
        if e["event_id"] == r.match_info["id"]: return web.json_response(api_event(e))
    return web.json_response({"detail": "not found"}, status=404)

def day_events(d): return [e for e in events if e["ts"][:10] == d]

async def h_summary(r):
    d = r.query.get("date") or now().strftime("%Y-%m-%d")
    try: dd = datetime.strptime(d, "%Y-%m-%d")
    except ValueError: return bad("date must be YYYY-MM-DD")
    es = day_events(d); y = day_events((dd - timedelta(days=1)).strftime("%Y-%m-%d"))
    acked = [e for e in es if e["status"] in ("resolved", "false_alarm")]
    by_cam = {}
    for e in es: by_cam[e["camera_id"]] = by_cam.get(e["camera_id"], 0) + 1
    return web.json_response(dict(
        date=d, total=len(es), yesterday=len(y), open=sum(e["status"] == "open" for e in es),
        by_type={t: sum(e["type"] == t for e in es) for t in TYPES},
        by_severity={s: sum(e["severity"] == s for e in es) for s in SEVS},
        by_camera=by_cam, fallback=sum(e["via"] == "fallback" for e in es), acked=len(acked),
        false_alarm_rate=(sum(e["status"] == "false_alarm" for e in acked) / len(acked)) if acked else None))

async def h_daily(r):
    try: days = int(r.query.get("days", 7))
    except ValueError: return bad("days must be int")
    if not 1 <= days <= 90: return bad("days must be 1-90")
    out = []
    for i in range(days - 1, -1, -1):
        d = (now() - timedelta(days=i)).strftime("%Y-%m-%d"); es = day_events(d)
        out.append(dict(date=d, **{t: sum(e["type"] == t for e in es) for t in TYPES}))
    return web.json_response(out)

async def h_csv(r):
    try: items = sorted(filtered({"from": r.query.get("from"), "to": r.query.get("to")}), key=lambda e: e["ts"])
    except ValueError as ex: return bad(str(ex))
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["event_id", "ts", "camera_id", "type", "ประเภท", "severity", "status", "via"])
    names = {"no_helmet": "ไม่สวมหมวกนิรภัย", "no_vest": "ไม่สวมเสื้อสะท้อนแสง", "restricted_zone": "เข้าเขตอันตราย", "unknown_visibility": "มองเห็นไม่ชัด"}
    for e in items: w.writerow([e["event_id"], e["ts"], e["camera_id"], e["type"], names[e["type"]], e["severity"], e["status"], e["via"]])
    return web.Response(body=("﻿" + buf.getvalue()).encode("utf-8"), content_type="text/csv", charset="utf-8",
                        headers={"Content-Disposition": 'attachment; filename="events.csv"'})

async def h_health(r):
    n = now()
    return web.json_response(dict(ok=True, mqtt="connected" if ctl["mqtt"] else "disconnected", mqtt_messages=mqtt_count,
                                  events=len(events), snapshots=len(snap_ready),
                                  server_time=iso(n), server_epoch_ms=int(n.timestamp() * 1000)))

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200"><rect width="320" height="200" fill="#334155"/>
<rect x="140" y="50" width="40" height="110" fill="none" stroke="#dc2626" stroke-width="4"/><circle cx="160" cy="70" r="12" fill="#cbd5e1"/>
<text x="10" y="190" fill="#fff" font-family="monospace" font-size="14">{sid}</text></svg>"""

async def h_snap(r):
    sid = r.match_info["sid"]
    ready = snap_ready.get(sid)
    if not ready or ready > now(): return web.Response(status=404, text="not found")
    return web.Response(text=SVG.format(sid=sid), content_type="image/svg+xml")

async def h_whep(r):
    # whep=1: behave like MediaMTX signalling (201 + root-relative Location); the SDP answer is fake,
    # so the browser fails, tears down and must DELETE the session before retrying.
    if not ctl["whep"]: return web.Response(status=404, text="no mediamtx in mock")
    sid = uuid.uuid4().hex
    path = r.match_info["path"]
    whep_sessions[sid] = path
    return web.Response(status=201, text="v=0\r\n", content_type="application/sdp",
                        headers={"Location": f"/{path}/whep/{sid}"})

async def h_whep_delete(r):
    sid = r.match_info["sid"]
    found = whep_sessions.pop(sid, None)
    print(f"WHEP DELETE {sid} {'closed' if found else 'unknown'} (open={len(whep_sessions)})", flush=True)
    return web.Response(status=200 if found else 404)

async def h_ctl(r):
    global clock_skew_s
    if "clock_skew" in r.query: clock_skew_s = float(r.query["clock_skew"])
    for k in ctl:
        if k in r.query: ctl[k] = r.query[k] == "1"
    if not ctl["mqtt"]:
        for c in list(clients): await c.ws.close()
    for _ in range(int(r.query.get("burst", 0))): await make_event()
    return web.json_response(dict(ctl, clock_skew=clock_skew_s, whep_sessions=len(whep_sessions)))

async def h_index(r): return web.FileResponse(f"{WEB}/index.html")

async def main():
    await seed()
    app = web.Application()
    app.router.add_get("/mqtt", ws_mqtt)
    app.router.add_get("/api/health", h_health)
    app.router.add_get("/api/events", h_events)
    app.router.add_get("/api/events/{id}", h_event)
    app.router.add_get("/api/stats/summary", h_summary)
    app.router.add_get("/api/stats/daily", h_daily)
    app.router.add_get("/api/export.csv", h_csv)
    app.router.add_get("/data/snapshots/{sid}.jpg", h_snap)
    app.router.add_post("/webrtc/{path:.*}/whep", h_whep)
    app.router.add_delete("/webrtc/{path:.*}/whep/{sid}", h_whep_delete)
    app.router.add_get("/mock/ctl", h_ctl)
    app.router.add_get("/", h_index)
    app.router.add_static("/", WEB)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"mock on http://localhost:{PORT}", flush=True)
    await asyncio.gather(sim_status(), sim_events())

asyncio.run(main())
