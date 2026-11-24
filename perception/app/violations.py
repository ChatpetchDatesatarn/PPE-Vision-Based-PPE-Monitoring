"""Candidate violations, restricted zones and the fallback event path (pure Python, 3.6-compatible, no pyds).

docs/mqtt_spec.md v3:
- 1) ds/violation: sent when a condition has held >= its hold time (no_helmet 2 s, no_vest 4 s (2026-10-16, fewer
  false no_vest; the app's --vest-hold changes it), restricted_zone 0.5 s), then re-sent every 5 s while it persists (repeat = 0, 1, 2, ...). No cooldown here (that is CiRA's job).
- 2) event: only when cira/status is missing or its ts is older than 15 s, the app publishes the event itself with
  via "fallback", the default severity and a 30 s cooldown per (camera, track_id, type), like CiRA.
  event_id = <cam>-YYYYMMDD-HHMMSS-<uid 3 digits>-<type code> (nh / nv / rz / uv), so two types of one person
  in the same second do not collide; snapshot_id = <cam>-YYYYMMDD-HHMMSS-<uid 3 digits> (time of that picture).
- 6) config/zones: polygons in 0..1. The restricted-zone check has three modes (ViolationTracker zone_mode,
  app --zone-mode, or a per-zone "mode" field): "overlap" (default) = area(bbox & polygon)/area(bbox) >=
  min_overlap (default 0.10, app --zone-overlap or per-zone "min_overlap"); "foot" = the old rule, foot point
  (bottom-centre) inside the polygon; "bottom" = the bottom 25 % band of the box overlaps the polygon >=
  min_overlap. ds/violation carries the measured fraction as "zone_overlap" (0..1), for debug only.

Helmet / vest state per person comes from ppe_smooth.PpeSmoother: True (✓), False (✗), None (?). Only ✗ counts;
"?" breaks a ✗ run like ✓ does. track_id = PersonIds uid.
A person seen only in part gets "?" for that frame for the item that may be out of view (no decision, no violation):
- vest "?" when the box touches the left / right edge of the picture or is unusually narrow (width / height < 0.25)
  (vest_judgeable); the top and bottom edges do not matter for the vest
- helmet "?" when the box touches the top edge (the head may be cut off) (helmet_judgeable); other edges do not matter
"""
import calendar
import json
import logging
import time

log = logging.getLogger(__name__)

NO_HELMET, NO_VEST, RESTRICTED_ZONE = "no_helmet", "no_vest", "restricted_zone"
HOLD_S = {NO_HELMET: 2.0, NO_VEST: 4.0, RESTRICTED_ZONE: 0.5}
EDGE_FRAC = 0.02          # box within 2 % of the picture's width / height from its edge = cut by the edge
MIN_ASPECT = 0.25         # box width / height below this = only a slice of the person is visible
REPEAT_S = 5.0
CIRA_STALE_S = 15.0
COOLDOWN_S = 30.0
SEVERITY = {RESTRICTED_ZONE: "critical", NO_HELMET: "high", NO_VEST: "warning", "unknown_visibility": "info"}
TYPE_CODE = {NO_HELMET: "nh", NO_VEST: "nv", RESTRICTED_ZONE: "rz", "unknown_visibility": "uv"}
TZ_S = 7 * 3600


def iso07(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.gmtime(int(epoch) + TZ_S))


def make_id(camera_id, epoch, uid):
    """<cam>-YYYYMMDD-HHMMSS-<uid, 3 digits> in +07:00 (snapshot_id; event_id adds -<type code>)."""
    return "%s-%s-%03d" % (camera_id, time.strftime("%Y%m%d-%H%M%S", time.gmtime(int(epoch) + TZ_S)), uid % 1000)


def parse_ts(ts):
    """'2026-10-15T10:15:10+07:00' (or +HH:MM / Z, optional .fff) -> epoch seconds, None if unreadable."""
    if not isinstance(ts, str) or len(ts) < 19:
        return None
    try:
        base = time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    rest = ts[19:]
    if rest.startswith("."):
        i = 1
        while i < len(rest) and rest[i].isdigit():
            i += 1
        rest = rest[i:]
    if rest in ("Z", ""):
        off = 0 if rest == "Z" else TZ_S          # no zone given: the system's +07:00
    elif len(rest) == 6 and rest[0] in "+-" and rest[3] == ":" and rest[1:3].isdigit() and rest[4:].isdigit():
        off = (int(rest[1:3]) * 3600 + int(rest[4:]) * 60) * (1 if rest[0] == "+" else -1)
    else:
        return None
    return calendar.timegm(base) - off


# ---- zones -----------------------------------------------------------------------------------------
def point_in_polygon(x, y, pts):
    """Ray casting; pts = [[x, y], ...] (>= 3 points)."""
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i][0], pts[i][1]
        xj, yj = pts[j][0], pts[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / float(yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def parse_zones(payload, camera_id):
    """config/zones JSON -> [(zone_id, points)]; bad zones are skipped. None if the payload is unusable
    (not JSON / for another camera), [] for a valid empty list (all zones removed)."""
    try:
        d = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict) or d.get("camera_id", camera_id) != camera_id or not isinstance(d.get("zones"), list):
        return None
    out = []
    for z in d["zones"]:
        if not isinstance(z, dict) or not isinstance(z.get("id"), str) or not isinstance(z.get("points"), list):
            continue
        pts = []
        for p in z["points"]:
            if isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p):
                pts.append([float(p[0]), float(p[1])])
        if len(pts) < 3:
            continue
        if polygon_self_intersects(pts):
            log.warning("zone %s polygon self-intersects (edges cross); overlap area may be wrong", z["id"])
        # Keep the old 2-tuple shape unless this zone carries its own overrides, so existing callers and the
        # config/zones format are unchanged (the extra fields are optional, read-only additions).
        over = {}
        if z.get("mode") in ("overlap", "foot", "bottom"):
            over["mode"] = z["mode"]
        if isinstance(z.get("min_overlap"), (int, float)) and not isinstance(z.get("min_overlap"), bool):
            over["min_overlap"] = float(z["min_overlap"])
        out.append((z["id"], pts, over) if over else (z["id"], pts))
    return out


def zone_at(x, y, zones):
    """id of the first zone containing (x, y), "" if none."""
    for zid, pts in zones:
        if point_in_polygon(x, y, pts):
            return zid
    return ""


def foot_point(bbox):
    """bbox [x, y, w, h] (0..1) -> bottom-centre."""
    return bbox[0] + bbox[2] / 2.0, bbox[1] + bbox[3]


def _bbox_rect(bbox):
    """bbox [x, y, w, h] -> (left, top, right, bottom)."""
    return bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]


def polygon_area(pts):
    """Shoelace absolute area of a polygon (pts = [[x, y], ...]); 0 for < 3 points."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _clip_half(poly, keep, cut):
    """One Sutherland-Hodgman pass: keep(p) True = inside; cut(a, b) = crossing point of edge a->b."""
    out = []
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        prv = poly[i - 1]
        cin = keep(cur)
        pin = keep(prv)
        if cin:
            if not pin:
                out.append(cut(prv, cur))
            out.append(cur)
        elif pin:
            out.append(cut(prv, cur))
    return out


def clip_polygon_rect(pts, rect):
    """Sutherland-Hodgman clip of a (possibly concave) polygon by the axis-aligned rect (l, t, r, b),
    which is convex, so the result is correct. Returns the clipped polygon ([] if nothing is inside)."""
    l, t, r, b = rect

    def ix(p1, p2, xc):
        if p2[0] == p1[0]:
            return [xc, p1[1]]
        m = (p2[1] - p1[1]) / (p2[0] - p1[0])
        return [xc, p1[1] + m * (xc - p1[0])]

    def iy(p1, p2, yc):
        if p2[1] == p1[1]:
            return [p1[0], yc]
        m = (p2[0] - p1[0]) / (p2[1] - p1[1])
        return [p1[0] + m * (yc - p1[1]), yc]

    poly = [[p[0], p[1]] for p in pts]
    poly = _clip_half(poly, lambda p: p[0] >= l, lambda a, c: ix(a, c, l))
    if poly:
        poly = _clip_half(poly, lambda p: p[0] <= r, lambda a, c: ix(a, c, r))
    if poly:
        poly = _clip_half(poly, lambda p: p[1] >= t, lambda a, c: iy(a, c, t))
    if poly:
        poly = _clip_half(poly, lambda p: p[1] <= b, lambda a, c: iy(a, c, b))
    return poly


def rect_poly_overlap(rect, pts):
    """area(rect & polygon) / area(rect), clamped to 0..1."""
    ra = (rect[2] - rect[0]) * (rect[3] - rect[1])
    if ra <= 0:
        return 0.0
    ov = polygon_area(clip_polygon_rect(pts, rect)) / ra
    return 1.0 if ov > 1.0 else (0.0 if ov < 0.0 else ov)


def _segments_cross(a, b, c, d):
    """True if segments a-b and c-d properly cross (used only to warn about a self-intersecting polygon)."""
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (side(a, b, c) > 0) != (side(a, b, d) > 0) and (side(c, d, a) > 0) != (side(c, d, b) > 0)


def polygon_self_intersects(pts):
    """True if any two non-adjacent edges of the closed polygon cross."""
    n = len(pts)
    if n < 4:
        return False
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or j == (i + 1) % n or (i == 0 and j == n - 1):
                continue
            if _segments_cross(a, b, pts[j], pts[(j + 1) % n]):
                return True
    return False


def _zone_hit(bbox, pts, mode, min_overlap):
    """(matched, overlap 0..1) for one zone polygon under a mode. "foot" reports the full-box overlap for
    debug but decides by the foot point; "overlap"/"bottom" decide by the fraction >= min_overlap."""
    if mode == "foot":
        fx, fy = foot_point(bbox)
        return point_in_polygon(fx, fy, pts), rect_poly_overlap(_bbox_rect(bbox), pts)
    if mode == "bottom":
        l, t = bbox[0], bbox[1] + bbox[3] * 0.75          # bottom 25 % band of the box
        ov = rect_poly_overlap((l, t, l + bbox[2], bbox[1] + bbox[3]), pts)
        return ov >= min_overlap, ov
    ov = rect_poly_overlap(_bbox_rect(bbox), pts)          # "overlap" (default)
    return ov >= min_overlap, ov


def zone_match(bbox, zones, mode="overlap", min_overlap=0.10):
    """First zone the bbox is in, under mode; a zone's own "mode"/"min_overlap" (3rd tuple element, a dict)
    override the globals. Returns (zone_id, overlap 0..1); ("", best_overlap_seen) if no zone matched."""
    best = 0.0
    for z in zones:
        zid, pts = z[0], z[1]
        zmode, zov = mode, min_overlap
        if len(z) > 2 and isinstance(z[2], dict):
            m = z[2].get("mode")
            if m in ("overlap", "foot", "bottom"):
                zmode = m
            mo = z[2].get("min_overlap")
            if isinstance(mo, (int, float)) and not isinstance(mo, bool):
                zov = float(mo)
        hit, ov = _zone_hit(bbox, pts, zmode, zov)
        if hit:
            return zid, ov
        if ov > best:
            best = ov
    return "", best


# ---- partly visible people ---------------------------------------------------------------------------
def content_rect(src_w, src_h, mux_w, mux_h, padding):
    """Where the picture is inside the nvstreammux frame, in mux px (left, top, right, bottom).
    padding (enable-padding=1): scaled to fit and centred, black bars around; else stretched to the whole frame."""
    if not padding or not src_w or not src_h:
        return 0.0, 0.0, float(mux_w), float(mux_h)
    sc = min(mux_w / float(src_w), mux_h / float(src_h))
    w, h = src_w * sc, src_h * sc
    x0, y0 = (mux_w - w) / 2.0, (mux_h - h) / 2.0
    return x0, y0, x0 + w, y0 + h


def vest_judgeable(box, rect, edge_frac=EDGE_FRAC, min_aspect=MIN_ASPECT):
    """False when the person box (left, top, width, height, mux px) touches the left or right edge of the picture
    rect, or is narrower than min_aspect × its height: the vest may be out of view, so it is "?" for this frame."""
    l, t, w, h = box[:4]
    x0, _, x1, _ = rect
    mx = edge_frac * (x1 - x0)
    if l <= x0 + mx or l + w >= x1 - mx:
        return False
    return h > 0 and w / float(h) >= min_aspect


def helmet_judgeable(box, rect, edge_frac=EDGE_FRAC):
    """False when the person box touches the top edge of the picture rect: the head may be cut off ("?")."""
    _, y0, _, y1 = rect
    return box[1] > y0 + edge_frac * (y1 - y0)


# ---- violations ------------------------------------------------------------------------------------
class Person(object):
    """One person seen in this frame: uid, bbox [x, y, w, h] 0..1, conf (person box), helmet / vest True/False/None."""
    __slots__ = ("uid", "bbox", "conf", "helmet", "vest")

    def __init__(self, uid, bbox, conf, helmet, vest):
        self.uid, self.bbox, self.conf, self.helmet, self.vest = uid, bbox, conf, helmet, vest


class _Run(object):
    __slots__ = ("since", "last_sent", "repeat")

    def __init__(self, since):
        self.since, self.last_sent, self.repeat = since, None, -1


class Violation(object):
    """One message to send now (every one, repeats too, goes out after a new snapshot of its frame)."""
    __slots__ = ("type", "uid", "conf", "zone_id", "bbox", "repeat", "since", "zone_overlap")

    def __init__(self, vtype, uid, conf, zone_id, bbox, run, zone_overlap=0.0):
        self.type, self.uid, self.conf, self.zone_id, self.bbox = vtype, uid, conf, zone_id, bbox
        self.repeat, self.since, self.zone_overlap = run.repeat, run.since, zone_overlap


class ViolationTracker(object):
    def __init__(self, hold_s=None, repeat_s=REPEAT_S, zone_mode="overlap", zone_overlap=0.10):
        self.hold_s = dict(HOLD_S, **(hold_s or {}))
        self.repeat_s = repeat_s
        self.zone_mode = zone_mode        # "overlap" (default) | "foot" | "bottom"
        self.zone_overlap = zone_overlap  # min_overlap for "overlap" / "bottom"
        self.zones = []          # [(zone_id, points[, overrides])]; replaced as a whole (read by probe thread)
        self.runs = {}           # (uid, type) -> _Run
        self.compliant = 0
        self.violating = 0

    def set_zones(self, zones):
        self.zones = list(zones)

    def update(self, t, persons, present_uids):
        """t: seconds (monotonic per stream); persons: [Person] seen in this frame; present_uids: everyone
        PersonIds still holds (seen or briefly hidden). Runs of people not in present_uids end (left the frame);
        people present but not seen this frame keep their runs and send nothing. Returns [Violation] to send now."""
        zones = self.zones
        present = set(present_uids)
        for key in [k for k in self.runs if k[0] not in present]:
            del self.runs[key]
        out = []
        compliant = violating = 0
        for p in persons:
            zid, zov = zone_match(p.bbox, zones, self.zone_mode, self.zone_overlap) if zones else ("", 0.0)
            active = {NO_HELMET: p.helmet is False, NO_VEST: p.vest is False, RESTRICTED_ZONE: zid != ""}
            if any(active.values()):
                violating += 1
            elif p.helmet is True and p.vest is True:
                compliant += 1
            for vtype, on in active.items():
                key = (p.uid, vtype)
                run = self.runs.get(key)
                if not on:
                    if run is not None:
                        del self.runs[key]
                    continue
                if run is None:
                    run = self.runs[key] = _Run(t)
                if t - run.since + 1e-9 < self.hold_s[vtype]:
                    continue
                if run.last_sent is not None and t - run.last_sent + 1e-9 < self.repeat_s:
                    continue
                run.repeat += 1
                run.last_sent = t
                out.append(Violation(vtype, p.uid, p.conf, zid, p.bbox, run, zov))
        self.compliant, self.violating = compliant, violating
        out.sort(key=lambda v: (v.uid, v.type))
        return out


def violation_msg(camera_id, v, epoch, snapshot_id):
    """ds/violation payload (spec section 1)."""
    return {"camera_id": camera_id, "ts": iso07(epoch), "type": v.type, "track_id": v.uid,
            "conf": round(float(v.conf), 3), "zone_id": v.zone_id, "bbox": [round(float(b), 4) for b in v.bbox],
            "snapshot_id": snapshot_id, "repeat": v.repeat, "zone_overlap": round(float(v.zone_overlap), 4)}


# ---- fallback --------------------------------------------------------------------------------------
class Fallback(object):
    """Decides cira / fallback from cira/status and applies the 30 s cooldown for fallback events."""

    def __init__(self, stale_s=CIRA_STALE_S, cooldown_s=COOLDOWN_S):
        self.stale_s = stale_s
        self.cooldown_s = cooldown_s
        self.cira_epoch = None    # ts of the last cira/status with online true, None = never / offline
        self.last_mode = None
        self.sent = {}            # (camera, track_id, type) -> epoch of the last fallback event

    def on_cira_status(self, payload):
        try:
            d = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(d, dict):
            return
        self.cira_epoch = parse_ts(d.get("ts")) if d.get("online", True) is not False else None

    def mode(self, now):
        """"cira" or "fallback" at epoch now."""
        ok = self.cira_epoch is not None and now - self.cira_epoch <= self.stale_s
        return "cira" if ok else "fallback"

    def switched(self, now):
        """(old, new) when the mode changed since the last call, else None (first call: (None, mode))."""
        m = self.mode(now)
        if m != self.last_mode:
            old, self.last_mode = self.last_mode, m
            return old, m
        return None

    def allow(self, camera_id, uid, vtype, now):
        """Cooldown per (camera, track_id, type); records the send when allowed."""
        key = (camera_id, uid, vtype)
        last = self.sent.get(key)
        if last is not None and now - last < self.cooldown_s:
            return False
        self.sent[key] = now
        for k in [k for k, e in self.sent.items() if now - e >= self.cooldown_s]:
            del self.sent[k]
        return True


def event_msg(camera_id, v, epoch, snapshot_id):
    """Fallback event payload (spec section 2): event_id = <cam>-YYYYMMDD-HHMMSS-<uid>-<type code>, via "fallback"."""
    return {"event_id": "%s-%s" % (make_id(camera_id, epoch, v.uid), TYPE_CODE[v.type]), "ts": iso07(epoch), "camera_id": camera_id,
            "zone_id": v.zone_id, "type": v.type, "severity": SEVERITY[v.type], "track_id": v.uid,
            "confidence": round(float(v.conf), 3), "bbox": [round(float(b), 4) for b in v.bbox],
            "snapshot_id": snapshot_id, "via": "fallback"}
