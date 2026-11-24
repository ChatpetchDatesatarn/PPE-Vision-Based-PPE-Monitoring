"""
Event store for the v3 recorder (SQLite + snapshot files). Standard library only.
Spec: docs/mqtt_spec.md (v3). The FastAPI/MQTT layer lives in app.py.
"""
import csv
import io
import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

BKK = timezone(timedelta(hours=7))
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
TYPES = ("no_helmet", "no_vest", "restricted_zone", "unknown_visibility")
SEVERITIES = ("critical", "high", "warning", "info")
ACK_STATUSES = ("resolved", "false_alarm")
DEFAULT_SEVERITY = {"restricted_zone": "critical", "no_helmet": "high",
                    "no_vest": "warning", "unknown_visibility": "info"}
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
log = logging.getLogger("recorder")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    ts_epoch    REAL NOT NULL,
    day         TEXT NOT NULL,
    camera_id   TEXT NOT NULL,
    zone_id     TEXT,
    type        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    track_id    INTEGER,
    confidence  REAL,
    bbox        TEXT,
    snapshot_id TEXT,
    via         TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    acked_at    TEXT,
    ack_by      TEXT,
    note        TEXT,
    received_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts_epoch);
CREATE INDEX IF NOT EXISTS idx_events_day  ON events(day);
CREATE INDEX IF NOT EXISTS idx_events_cam  ON events(camera_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
"""

COLUMNS = ("event_id", "ts", "camera_id", "zone_id", "type", "severity", "track_id",
           "confidence", "bbox", "snapshot_id", "via", "status", "acked_at", "ack_by", "note")


def parse_ts(value):
    """ISO 8601 -> aware datetime (naive = Bangkok). Returns None if unparsable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=BKK)


def parse_bound(value, end=False):
    """'YYYY-MM-DD' or ISO datetime -> epoch. A bare date as an upper bound means end of that day."""
    if not value:
        return None
    if len(value) == 10:
        try:
            d = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=BKK)
        except ValueError:
            raise ValueError("bad date: %s" % value)
        return (d + timedelta(days=1)).timestamp() - 0.001 if end else d.timestamp()
    dt = parse_ts(value)
    if dt is None:
        raise ValueError("bad datetime: %s" % value)
    return dt.timestamp()


class Store(object):
    def __init__(self, data_dir="/data", max_snapshots=3000, snapshot_max_age_days=30,
                 orphan_grace_s=600):
        self.data_dir = data_dir
        self.snap_dir = os.path.join(data_dir, "snapshots")
        os.makedirs(self.snap_dir, exist_ok=True)
        self.max_snapshots = max_snapshots
        self.snapshot_max_age_s = snapshot_max_age_days * 86400
        self.orphan_grace_s = orphan_grace_s
        self.lock = threading.Lock()
        self.db = sqlite3.connect(os.path.join(data_dir, "safety.db"), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ---------- helpers ----------
    def snapshot_path(self, snapshot_id):
        return os.path.join(self.snap_dir, snapshot_id + ".jpg")

    def _row(self, r):
        d = {k: r[k] for k in COLUMNS}
        d["bbox"] = json.loads(d["bbox"]) if d["bbox"] else None
        sid = d["snapshot_id"]
        d["snapshot_url"] = ("/data/snapshots/%s.jpg" % sid
                             if sid and os.path.exists(self.snapshot_path(sid)) else None)
        return d

    # ---------- writers (called from MQTT) ----------
    def add_event(self, payload, topic_camera=None):
        """Insert one event (JSON bytes/str/dict). Returns event_id, or None if rejected."""
        try:
            ev = payload if isinstance(payload, dict) else json.loads(payload)
        except (ValueError, TypeError):
            return None
        if not isinstance(ev, dict):
            return None
        eid = ev.get("event_id")
        etype = ev.get("type")
        if not isinstance(eid, str) or not ID_RE.match(eid) or etype not in TYPES:
            return None
        dt = parse_ts(ev.get("ts")) or datetime.now(BKK)
        local = dt.astimezone(BKK)
        sev = ev.get("severity")
        if sev not in SEVERITIES:
            sev = DEFAULT_SEVERITY[etype]
        sid = ev.get("snapshot_id")
        if not (isinstance(sid, str) and ID_RE.match(sid)):
            sid = None
        bbox = ev.get("bbox")
        bbox = json.dumps(bbox) if isinstance(bbox, list) and len(bbox) == 4 else None

        def num(v, cast):
            try:
                return cast(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        row = (eid, local.isoformat(timespec="seconds"), dt.timestamp(), local.strftime("%Y-%m-%d"),
               str(ev.get("camera_id") or topic_camera or "unknown"), ev.get("zone_id"), etype, sev,
               num(ev.get("track_id"), int), num(ev.get("confidence"), float), bbox, sid,
               ev.get("via") if ev.get("via") in ("cira", "fallback") else None, time.time())
        with self.lock:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO events (event_id, ts, ts_epoch, day, camera_id, zone_id, type,"
                " severity, track_id, confidence, bbox, snapshot_id, via, received_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            self.db.commit()
        if cur.rowcount == 0:
            log.warning("duplicate event_id %s (type %s) ignored, the first one is kept", eid, etype)
        return eid

    def save_snapshot(self, snapshot_id, data):
        """Write a JPEG atomically. Rejects bad ids, non-JPEG data and oversize files."""
        if not ID_RE.match(snapshot_id or "") or not data or len(data) > MAX_SNAPSHOT_BYTES:
            return False
        if data[:2] != b"\xff\xd8":
            return False
        path = self.snapshot_path(snapshot_id)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return True

    def apply_ack(self, payload):
        try:
            a = payload if isinstance(payload, dict) else json.loads(payload)
        except (ValueError, TypeError):
            return False
        if not isinstance(a, dict) or a.get("status") not in ACK_STATUSES:
            return False
        eid = a.get("event_id")
        if not isinstance(eid, str) or not ID_RE.match(eid):
            return False
        acked = (parse_ts(a.get("ts")) or datetime.now(BKK)).astimezone(BKK).isoformat(timespec="seconds")
        with self.lock:
            cur = self.db.execute("UPDATE events SET status=?, acked_at=?, ack_by=?, note=? WHERE event_id=?",
                                  (a["status"], acked, str(a.get("by") or ""), str(a.get("note") or ""), eid))
            self.db.commit()
        return cur.rowcount > 0

    # ---------- readers (called from the API) ----------
    def query_events(self, camera_id=None, type=None, severity=None, status=None,
                     date_from=None, date_to=None, limit=50, offset=0):
        where, args = [], []
        for col, val in (("camera_id", camera_id), ("type", type), ("severity", severity), ("status", status)):
            if val:
                where.append("%s = ?" % col)
                args.append(val)
        lo, hi = parse_bound(date_from), parse_bound(date_to, end=True)
        if lo is not None:
            where.append("ts_epoch >= ?")
            args.append(lo)
        if hi is not None:
            where.append("ts_epoch <= ?")
            args.append(hi)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        with self.lock:
            total = self.db.execute("SELECT COUNT(*) FROM events" + clause, args).fetchone()[0]
            rows = self.db.execute("SELECT * FROM events" + clause + " ORDER BY ts_epoch DESC LIMIT ? OFFSET ?",
                                   args + [limit, offset]).fetchall()
        return {"total": total, "items": [self._row(r) for r in rows]}

    def get_event(self, event_id):
        with self.lock:
            r = self.db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return self._row(r) if r else None

    def summary(self, date=None):
        day = date or datetime.now(BKK).strftime("%Y-%m-%d")
        prev = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        with self.lock:
            total = self.db.execute("SELECT COUNT(*) FROM events WHERE day=?", (day,)).fetchone()[0]
            yesterday = self.db.execute("SELECT COUNT(*) FROM events WHERE day=?", (prev,)).fetchone()[0]
            open_now = self.db.execute("SELECT COUNT(*) FROM events WHERE status='open'").fetchone()[0]
            by_type = dict(self.db.execute("SELECT type, COUNT(*) FROM events WHERE day=? GROUP BY type",
                                           (day,)).fetchall())
            by_sev = dict(self.db.execute("SELECT severity, COUNT(*) FROM events WHERE day=? GROUP BY severity",
                                          (day,)).fetchall())
            by_cam = dict(self.db.execute("SELECT camera_id, COUNT(*) FROM events WHERE day=? GROUP BY camera_id",
                                          (day,)).fetchall())
            acked = dict(self.db.execute("SELECT status, COUNT(*) FROM events WHERE day=? AND status!='open'"
                                         " GROUP BY status", (day,)).fetchall())
            fallback = self.db.execute("SELECT COUNT(*) FROM events WHERE day=? AND via='fallback'",
                                       (day,)).fetchone()[0]
        n_acked = sum(acked.values())
        return {"date": day, "total": total, "yesterday": yesterday, "open": open_now,
                "by_type": {t: by_type.get(t, 0) for t in TYPES},
                "by_severity": {s: by_sev.get(s, 0) for s in SEVERITIES},
                "by_camera": by_cam, "fallback": fallback,
                "acked": n_acked, "false_alarm_rate": round(acked.get("false_alarm", 0) / float(n_acked), 3)
                if n_acked else None}

    def daily(self, days=7):
        days = max(1, min(int(days), 90))
        today = datetime.now(BKK).date()
        first = (today - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        with self.lock:
            rows = self.db.execute("SELECT day, type, COUNT(*) FROM events WHERE day >= ? GROUP BY day, type",
                                   (first,)).fetchall()
        out = {}
        for i in range(days):
            d = (today - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            out[d] = dict({"date": d}, **{t: 0 for t in TYPES})
        for d, t, n in rows:
            if d in out and t in TYPES:
                out[d][t] = n
        return list(out.values())

    def export_csv(self, date_from=None, date_to=None):
        res = self.query_events(date_from=date_from, date_to=date_to, limit=500)
        total = res["total"]
        items = list(res["items"])
        while len(items) < total:
            more = self.query_events(date_from=date_from, date_to=date_to, limit=500, offset=len(items))["items"]
            if not more:
                break
            items.extend(more)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(list(COLUMNS) + ["snapshot_url"])
        for it in reversed(items):
            w.writerow([json.dumps(it[c]) if c == "bbox" and it[c] else ("" if it[c] is None else it[c])
                        for c in COLUMNS] + [it["snapshot_url"] or ""])
        return "﻿" + buf.getvalue()  # BOM so Excel shows Thai correctly

    def counts(self):
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        snaps = [f for f in os.listdir(self.snap_dir) if f.endswith(".jpg")]
        return {"events": n, "snapshots": len(snaps)}

    # ---------- deletion (v6; the API layer checks the PIN) ----------
    def _delete_where(self, clause, args):
        """Delete matching events, then their snapshot files that no remaining event uses
        (an nh + nv pair can share one snapshot). Returns counts."""
        with self.lock:
            rows = self.db.execute("SELECT event_id, snapshot_id FROM events" + clause, args).fetchall()
            ids = [r[0] for r in rows]
            sids = set(r[1] for r in rows if r[1])
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                self.db.execute("DELETE FROM events WHERE event_id IN (%s)" % ",".join("?" * len(chunk)), chunk)
            self.db.commit()
            still = set()
            sl = list(sids)
            for i in range(0, len(sl), 500):
                chunk = sl[i:i + 500]
                still.update(r[0] for r in self.db.execute(
                    "SELECT DISTINCT snapshot_id FROM events WHERE snapshot_id IN (%s)" % ",".join("?" * len(chunk)),
                    chunk))
        removed = 0
        for sid in sids - still:
            if not ID_RE.match(sid):
                continue
            try:
                os.remove(self.snapshot_path(sid))
                removed += 1
            except FileNotFoundError:
                pass
        return {"events": len(ids), "snapshots": removed}

    def delete_events(self, event_ids):
        if not isinstance(event_ids, list):
            raise ValueError("event_ids must be a list")
        ids = list(dict.fromkeys(e for e in event_ids if isinstance(e, str) and ID_RE.match(e)))
        if not ids:
            raise ValueError("no valid event_ids")
        if len(ids) > 1000:
            raise ValueError("too many event_ids (max 1000 per request)")
        return self._delete_where(" WHERE event_id IN (%s)" % ",".join("?" * len(ids)), ids)

    def delete_range(self, date_from, date_to):
        """Delete every event between two dates (inclusive, Bangkok days). Both bounds are required."""
        lo, hi = parse_bound(date_from), parse_bound(date_to, end=True)
        if lo is None or hi is None:
            raise ValueError("from and to are both required")
        if lo > hi:
            raise ValueError("from must not be after to")
        return self._delete_where(" WHERE ts_epoch >= ? AND ts_epoch <= ?", [lo, hi])

    # ---------- housekeeping ----------
    def cleanup(self, now=None):
        """Delete orphan snapshots (no event after grace), snapshots older than max age,
        and the oldest snapshots beyond max_snapshots. Event rows are kept."""
        now = now or time.time()
        with self.lock:
            referenced = set(r[0] for r in self.db.execute(
                "SELECT snapshot_id FROM events WHERE snapshot_id IS NOT NULL").fetchall())
        files = []
        for f in os.listdir(self.snap_dir):
            p = os.path.join(self.snap_dir, f)
            if f.endswith(".tmp") and now - os.path.getmtime(p) > 60:
                os.remove(p)
                continue
            if f.endswith(".jpg"):
                files.append((os.path.getmtime(p), f[:-4], p))
        removed = {"orphan": 0, "old": 0, "over_limit": 0}
        keep = []
        for mtime, sid, p in files:
            age = now - mtime
            if sid not in referenced and age > self.orphan_grace_s:
                os.remove(p)
                removed["orphan"] += 1
            elif age > self.snapshot_max_age_s:
                os.remove(p)
                removed["old"] += 1
            else:
                keep.append((mtime, p))
        keep.sort()
        for mtime, p in keep[:max(0, len(keep) - self.max_snapshots)]:
            os.remove(p)
            removed["over_limit"] += 1
        return removed

    def migrate_events_json(self, path):
        """One-time import of the v2 recorder's events.json (snapshot file = <event_id>.jpg)."""
        if not os.path.exists(path):
            return 0
        with self.lock:
            if self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]:
                return 0
        try:
            with open(path) as f:
                old = json.load(f)
        except (ValueError, OSError):
            return 0
        n = 0
        for ev in old if isinstance(old, list) else []:
            if not isinstance(ev, dict):
                continue
            ev = dict(ev)
            if ev.get("snapshot") and not ev.get("snapshot_id"):
                ev["snapshot_id"] = os.path.basename(ev["snapshot"]).rsplit(".", 1)[0]
            if self.add_event(ev):
                n += 1
                if ev.get("status") in ACK_STATUSES:
                    self.apply_ack({"event_id": ev["event_id"], "status": ev["status"],
                                    "by": ev.get("ack_by", "migrated"), "ts": ev.get("acked_at")})
        os.replace(path, path + ".migrated")
        return n
