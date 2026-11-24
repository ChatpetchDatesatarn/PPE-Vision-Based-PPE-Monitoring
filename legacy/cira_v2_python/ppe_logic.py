"""
PPE decision logic — turns detection results from each frame into events per docs/mqtt_spec.md
Used in CiRA CORE's Python node (or any program) — supports Python 3.6+, standard library only

Input per frame: detection list [(name, conf, x1, y1, x2, y2), ...] in pixels
Model classes: helmet, vest, gloves, goggles, shoes, mask, person

What it does
1. Track people across frames (simple IoU matching) -> track_id
2. Pair PPE with a person: helmet must be at the top of the person box, vest in the torso area
3. Fire an event only when a condition persists past the threshold (hold), then wait for cooldown before repeating
4. Check restricted zones from the foot point (bottom-center of the person box) inside the zone polygon
5. If the person is too small/cut off by the frame edge -> unknown_visibility instead of concluding "not wearing"
"""
import time
from datetime import datetime, timedelta, timezone

BKK = timezone(timedelta(hours=7))


def _iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _in_region(pt, box):
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def _in_poly(pt, poly):
    """Ray casting; poly = [(x, y), ...] in pixels"""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


class _Track(object):
    def __init__(self, tid, box, conf, now):
        self.id = tid
        self.box = box
        self.conf = conf
        self.last_seen = now
        self.since = {}      # condition -> time it started
        self.fired = {}      # condition -> time the last event was fired
        self.state = {}      # summary for drawing labels


class PPEMonitor(object):
    def __init__(self, camera_id="cam01", zones=None, require=("helmet", "vest"),
                 hold_s=2.0, zone_hold_s=0.5, cooldown_s=30.0,
                 min_person_h=0.12, iou_match=0.3, track_ttl=1.5,
                 conf_person=0.45, conf_ppe=0.35, default_zone="line-1"):
        """
        zones: {"zone-A": [(x, y), ...]} in normalized 0-1 coordinates (restricted zones)
        require: PPE that must be worn
        min_person_h: person height as a fraction of the frame; smaller -> cannot verify
        """
        self.camera_id = camera_id
        self.zones = zones or {}
        self.require = tuple(require)
        self.hold_s = hold_s
        self.zone_hold_s = zone_hold_s
        self.cooldown_s = cooldown_s
        self.min_person_h = min_person_h
        self.iou_match = iou_match
        self.track_ttl = track_ttl
        self.conf_person = conf_person
        self.conf_ppe = conf_ppe
        self.default_zone = default_zone
        self.tracks = {}
        self._next_id = 1
        self._seq = 0

    # ---------- tracking ----------
    def _match(self, persons, now):
        unmatched = list(range(len(persons)))
        pairs = []
        for tid, tr in self.tracks.items():
            for i in unmatched:
                pairs.append((_iou(tr.box, persons[i][1]), tid, i))
        pairs.sort(reverse=True)
        used_t, used_p = set(), set()
        for score, tid, i in pairs:
            if score < self.iou_match or tid in used_t or i in used_p:
                continue
            used_t.add(tid)
            used_p.add(i)
            tr = self.tracks[tid]
            tr.box, tr.conf, tr.last_seen = persons[i][1], persons[i][0], now
        for i in range(len(persons)):
            if i not in used_p:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = _Track(tid, persons[i][1], persons[i][0], now)
        for tid in [t for t, tr in self.tracks.items() if now - tr.last_seen > self.track_ttl]:
            del self.tracks[tid]

    # ---------- per person checks ----------
    def _has(self, name, person_box, items):
        x1, y1, x2, y2 = person_box
        h = y2 - y1
        if name == "helmet":
            region = (x1, y1 - 0.10 * h, x2, y1 + 0.30 * h)   # head area
        elif name == "vest":
            region = (x1, y1 + 0.15 * h, x2, y1 + 0.75 * h)   # torso area
        else:
            region = (x1, y1, x2, y2)
        return any(_in_region(_center(b), region) for b in items)

    def _condition(self, tr, cond, active, hold, now, events, extra=None):
        if not active:
            tr.since.pop(cond, None)
            return
        start = tr.since.setdefault(cond, now)
        if now - start < hold:
            return
        last = tr.fired.get(cond)
        if last is not None and now - last < self.cooldown_s:
            return
        tr.fired[cond] = now
        events.append(self._event(tr, cond, extra or {}))

    def _event(self, tr, etype, extra):
        self._seq = (self._seq + 1) % 1000
        ts = datetime.now(BKK)
        x1, y1, x2, y2 = tr.box
        W, H = self._wh
        ev = {
            "event_id": "%s-%s-%03d-t%d" % (self.camera_id, ts.strftime("%Y%m%d-%H%M%S"), self._seq, tr.id),
            "ts": ts.isoformat(timespec="seconds"),
            "camera_id": self.camera_id,
            "zone_id": self.default_zone,
            "type": etype,
            "track_id": tr.id,
            "confidence": round(float(tr.conf), 2),
            "bbox": [round(x1 / W, 4), round(y1 / H, 4), round((x2 - x1) / W, 4), round((y2 - y1) / H, 4)],
        }
        ev.update(extra)
        return ev

    # ---------- main ----------
    def update(self, detections, frame_w, frame_h, now=None):
        """detections: [(name, conf, x1, y1, x2, y2), ...] -> returns list of events (dict)"""
        now = time.time() if now is None else now
        self._wh = (float(frame_w), float(frame_h))
        persons, ppe = [], {}
        for name, conf, x1, y1, x2, y2 in detections:
            box = (float(x1), float(y1), float(x2), float(y2))
            if name == "person":
                if conf >= self.conf_person:
                    persons.append((conf, box))
            elif conf >= self.conf_ppe:
                ppe.setdefault(name, []).append(box)

        self._match(persons, now)
        events = []
        zones_px = {z: [(x * frame_w, y * frame_h) for x, y in pts] for z, pts in self.zones.items()}

        for tr in self.tracks.values():
            if tr.last_seen != now:
                continue  # not seen this frame
            x1, y1, x2, y2 = tr.box
            h = y2 - y1
            visible = h >= self.min_person_h * frame_h and y1 > 2  # not too small, head not cut off at the top edge
            tr.state = {"visible": visible}

            # restricted zone: foot point inside polygon
            foot = ((x1 + x2) / 2.0, y2)
            in_zone = None
            for zid, poly in zones_px.items():
                if _in_poly(foot, poly):
                    in_zone = zid
                    break
            tr.state["zone"] = in_zone
            self._condition(tr, "restricted_zone", in_zone is not None, self.zone_hold_s, now, events,
                            {"zone_id": in_zone} if in_zone else None)

            # PPE checks
            if not visible:
                for name in self.require:
                    tr.since.pop("no_" + name, None)
                self._condition(tr, "unknown_visibility", True, self.hold_s * 2, now, events)
                continue
            tr.since.pop("unknown_visibility", None)
            for name in self.require:
                ok = self._has(name, tr.box, ppe.get(name, []))
                tr.state[name] = ok
                self._condition(tr, "no_" + name, not ok, self.hold_s, now, events)
        return events

    def labels(self):
        """Labels for each person for drawing: {track_id: (box, text, is_violation)}"""
        out = {}
        for tr in self.tracks.values():
            s = tr.state
            missing = [n for n in self.require if s.get(n) is False]
            bad = bool(missing) or bool(s.get("zone"))
            if not s.get("visible", True):
                text = "#%d ?" % tr.id
            elif bad:
                text = "#%d " % tr.id + " ".join(["NO " + m.upper() for m in missing] + (["ZONE"] if s.get("zone") else []))
            else:
                text = "#%d OK" % tr.id
            out[tr.id] = (tr.box, text, bad)
        return out
