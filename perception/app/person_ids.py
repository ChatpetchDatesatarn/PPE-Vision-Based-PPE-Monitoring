"""Stable person numbering on top of the DeepStream tracker (pure Python, works on Python 3.6).

Rules
- A person keeps the same number while inside the frame, even if hidden behind someone for a while.
- A person is "gone" only after leaving through a frame edge (or an exit region such as a door).
  Coming back in later counts as a new person — except within regrace_s after the exit, near the place
  where they left (then they get their old uid, entry order and colour back: "rejoin", not "enter").
- Numbers shown on screen follow the order people entered, among the people in the frame now (1..N):
  the earliest is 1. When someone leaves, everyone who entered after them moves up one number
  (A=1 B=2 C=3, A leaves -> B=1 C=2); a new person gets the next number after the others (D=3);
  one person alone is always 1. Hidden people still count as in the frame, so numbers do not shift
  while someone is only hidden. Each person also gets a unique id (uid) that never repeats, for events and logs.
- Each person gets a colour index when they enter: the first index (0..n_colors-1) that nobody in the frame
  uses now. It stays with the person (also after rejoin), so the colour does not change when the number moves.
- in_frame = people currently inside the frame (seen now + hidden for a short while)
  detected = people the detector sees in this frame

How it works
- The tracker gives a tracker id per box. When a tracker id disappears in the middle of the frame
  (someone is hidden), the person is kept as "hidden" for up to hidden_ttl_s seconds.
- When a NEW tracker id appears, it is first matched to a hidden person near the place where that
  person was expected to be, then to someone who exited less than regrace_s ago near the place they left,
  and only then counted as a new person.
- When a tracker id disappears near an edge, the person is treated as having left after edge_ttl_s.

Usage (in the DeepStream probe, once per frame):
    mgr = PersonIds(1280, 720, edge_ttl_s=1.5, regrace_s=2.0)
    out = mgr.update(t_seconds, [(tracker_id, (left, top, width, height)), ...])
    out.labels[tracker_id] -> (number, uid), with .color_index on the same object
    out.in_frame, out.detected, out.events  # events: ("enter"|"exit"|"rejoin", uid, number)
    out.renumbered                          # [(uid, old_number, new_number)] for people whose number moved
    out.event_boxes                         # {uid: (left, top, width, height)} for the uids in out.events
"""
import math


class _Person(object):
    __slots__ = ("uid", "number", "tid", "box", "vel", "last_t", "first_t", "hits", "hidden_since",
                 "color_index", "exit_t")

    def __init__(self, uid, number, tid, box, t, color_index):
        self.uid = uid
        self.number = number
        self.tid = tid
        self.box = box            # (left, top, width, height) in pixels
        self.vel = (0.0, 0.0)     # center velocity, pixels / second (smoothed)
        self.last_t = t
        self.first_t = t
        self.hits = 1
        self.hidden_since = None  # time it stopped being seen, None while visible
        self.color_index = color_index
        self.exit_t = None        # set when the person exits (kept in recently_exited for regrace_s)


class Label(tuple):
    """(number, uid) — compares and unpacks like a plain tuple; also carries .color_index"""

    def __new__(cls, number, uid, color_index):
        obj = tuple.__new__(cls, (number, uid))
        obj.color_index = color_index
        return obj


class Result(object):
    __slots__ = ("labels", "in_frame", "detected", "events", "renumbered", "event_boxes")

    def __init__(self, labels, in_frame, detected, events, renumbered=None, event_boxes=None):
        self.labels = labels
        self.in_frame = in_frame
        self.detected = detected
        self.events = events
        self.renumbered = renumbered or []
        self.event_boxes = event_boxes or {}


def _center(b):
    return (b[0] + b[2] / 2.0, b[1] + b[3] / 2.0)


def _inside(pt, poly):
    """point in polygon (ray casting). poly = [(x, y), ...] in pixels."""
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


class PersonIds(object):
    def __init__(self, width, height, edge_margin=0.04, edge_ttl_s=0.7, hidden_ttl_s=4.0,
                 rejoin_gate=1.2, max_speed_frac=0.6, size_ratio=2.2, exit_regions=None,
                 regrace_s=0.0, n_colors=12):
        """
        edge_margin    : a box within this fraction of the frame size from an edge counts as "at the edge"
        edge_ttl_s     : lost at the edge for this long -> left the frame
        hidden_ttl_s   : lost in the middle for this long -> give up (counted as left)
        rejoin_gate    : a new box may rejoin a hidden person if it is within
                         rejoin_gate x (hidden person's box height) of the expected position
        max_speed_frac : cap on the extra search radius, in frame widths per second
        size_ratio     : box height may change by at most this factor when rejoining
        exit_regions   : extra polygons (pixels) that count like an edge, e.g. a door inside the image
        regrace_s      : someone who exited less than this long ago and comes back near the place they left
                         (same gate as rejoin, measured from the last box, no motion prediction) gets their
                         old uid back. 0 = off (default, the original behaviour)
        n_colors       : size of the colour palette the caller uses for color_index
        """
        self.w, self.h = float(width), float(height)
        self.mx, self.my = edge_margin * self.w, edge_margin * self.h
        self.edge_ttl_s = edge_ttl_s
        self.hidden_ttl_s = hidden_ttl_s
        self.rejoin_gate = rejoin_gate
        self.max_speed = max_speed_frac * self.w
        self.size_ratio = size_ratio
        self.exit_regions = exit_regions or []
        self.regrace_s = regrace_s
        self.n_colors = n_colors
        self.people = {}            # uid -> _Person
        self.by_tid = {}            # tracker id -> uid
        self.recently_exited = []   # _Person objects that exited less than regrace_s ago (not in in_frame)
        self.next_uid = 1
        self.total_entered = 0

    # ---- helpers -------------------------------------------------------
    def at_edge(self, box):
        l, t, w, h = box
        if l <= self.mx or t <= self.my or l + w >= self.w - self.mx or t + h >= self.h - self.my:
            return True
        c = _center(box)
        return any(_inside(c, poly) for poly in self.exit_regions)

    def _renumber(self, skip_uids):
        """number = position in entry order (first_t, then uid) among the people in the frame now.
        Returns [(uid, old, new)] for people whose number changed, except skip_uids (entered/came back this frame)."""
        moved = []
        order = sorted(self.people.values(), key=lambda p: (p.first_t, p.uid))
        for i, p in enumerate(order):
            if p.number != i + 1 and p.uid not in skip_uids:
                moved.append((p.uid, p.number, i + 1))
            p.number = i + 1
        return moved

    def _pick_color(self, prefer=None):
        """first colour index nobody in the frame uses (prefer the old one when it is still free)"""
        used = set(p.color_index for p in self.people.values())
        if prefer is not None and prefer not in used:
            return prefer
        for i in range(self.n_colors):
            if i not in used:
                return i
        return (self.next_uid - 1) % self.n_colors     # more people than colours: reuse

    def _new_person(self, tid, box, t, events):
        # number is final only after _renumber() at the end of update(); start after everyone already here
        p = _Person(self.next_uid, len(self.people) + 1, tid, box, t, self._pick_color())
        self.next_uid += 1
        self.total_entered += 1
        self.people[p.uid] = p
        self.by_tid[tid] = p.uid
        events.append(("enter", p.uid, p.number))
        return p

    def _predict(self, p, t):
        dt = max(0.0, t - p.last_t)
        cx, cy = _center(p.box)
        return cx + p.vel[0] * dt, cy + p.vel[1] * dt, dt

    def _rejoin_cost(self, p, box, t, predict=True):
        """distance (normalised) between a new box and where person p should be, or None if impossible.
        predict=False measures from p's last box (used for people who already exited)."""
        ph = p.box[3]
        if not (1.0 / self.size_ratio <= box[3] / max(ph, 1.0) <= self.size_ratio):
            return None
        if predict:
            px, py, dt = self._predict(p, t)
        else:
            (px, py), dt = _center(p.box), max(0.0, t - p.last_t)
        nx, ny = _center(box)
        d = math.hypot(nx - px, ny - py)
        radius = self.rejoin_gate * ph + min(self.max_speed * dt, 0.5 * self.w) * 0.5
        if d > radius:
            return None
        return d / max(radius, 1.0)

    def _match(self, candidates, new_boxes, used_box, t, predict):
        """best-first matching of unused new boxes to candidate people; returns [(box index, person)]"""
        pairs = []
        for i, (tid, box) in enumerate(new_boxes):
            if i in used_box:
                continue
            for p in candidates:
                c = self._rejoin_cost(p, box, t, predict)
                if c is not None:
                    # someone who appears at the edge is more likely a new person: small penalty
                    pairs.append((c + (0.5 if self.at_edge(box) else 0.0), i, p.uid, p))
        pairs.sort(key=lambda x: x[:3])
        used_person, out = set(), []
        for c, i, uid, p in pairs:
            if i in used_box or uid in used_person:
                continue
            used_box.add(i)
            used_person.add(uid)
            out.append((i, p))
        return out

    # ---- main ------------------------------------------------------------
    def update(self, t, detections):
        """t: seconds (frame time). detections: [(tracker_id, (left, top, width, height)), ...]"""
        events = []
        event_boxes = {}
        seen_tids = set()
        if self.recently_exited:
            self.recently_exited = [p for p in self.recently_exited if t - p.exit_t <= self.regrace_s]

        # 1) boxes whose tracker id we already know
        new_boxes = []
        for tid, box in detections:
            seen_tids.add(tid)
            uid = self.by_tid.get(tid)
            p = self.people.get(uid) if uid is not None else None
            if p is None:
                new_boxes.append((tid, box))
                continue
            dt = t - p.last_t
            if dt > 0:
                (ox, oy), (nx, ny) = _center(p.box), _center(box)
                vx, vy = (nx - ox) / dt, (ny - oy) / dt
                p.vel = (0.7 * p.vel[0] + 0.3 * vx, 0.7 * p.vel[1] + 0.3 * vy)
            p.box, p.last_t, p.hidden_since = box, t, None
            p.hits += 1

        # 2) people not seen in this frame become hidden
        for p in self.people.values():
            if p.tid not in seen_tids and p.hidden_since is None:
                p.hidden_since = p.last_t

        # 3) new tracker ids: hidden people first, then people who exited less than regrace_s ago, else new
        used_box = set()
        hidden = [p for p in self.people.values() if p.hidden_since is not None]
        for i, p in self._match(hidden, new_boxes, used_box, t, predict=True):
            tid, box = new_boxes[i]
            self.by_tid.pop(p.tid, None)
            p.tid, p.box, p.last_t, p.hidden_since = tid, box, t, None
            p.hits += 1
            self.by_tid[tid] = p.uid
            events.append(("rejoin", p.uid, p.number))
            event_boxes[p.uid] = box
        came_back = set()
        for i, p in self._match(self.recently_exited, new_boxes, used_box, t, predict=False):
            tid, box = new_boxes[i]
            self.recently_exited.remove(p)
            p.color_index = self._pick_color(prefer=p.color_index)
            p.tid, p.box, p.last_t, p.hidden_since, p.exit_t = tid, box, t, None, None
            p.vel = (0.0, 0.0)
            p.hits += 1
            self.people[p.uid] = p          # first_t is kept, so the old entry order (number) comes back
            self.by_tid[tid] = p.uid
            came_back.add(p.uid)
            events.append(("rejoin", p.uid, p.number))
            event_boxes[p.uid] = box
        for i, (tid, box) in enumerate(new_boxes):
            if i not in used_box:
                p = self._new_person(tid, box, t, events)
                event_boxes[p.uid] = box

        # 4) hidden people that have left: lost at the edge (short wait) or hidden too long
        for uid in list(self.people):
            p = self.people[uid]
            if p.hidden_since is None:
                continue
            gone_for = t - p.hidden_since
            if (self.at_edge(p.box) and gone_for >= self.edge_ttl_s) or gone_for >= self.hidden_ttl_s:
                del self.people[uid]
                self.by_tid.pop(p.tid, None)
                events.append(("exit", uid, p.number))
                event_boxes[uid] = p.box
                if self.regrace_s > 0:
                    p.exit_t = t
                    self.recently_exited.append(p)

        # 5) numbers follow entry order of the people still here; enter/rejoin events carry the final number
        #    (exit events keep the number the person had while leaving)
        skip = set(uid for k, uid, _ in events if k == "enter") | came_back
        renumbered = self._renumber(skip)
        events = [(k, uid, self.people[uid].number if k != "exit" and uid in self.people else n)
                  for k, uid, n in events]

        labels = {}
        for p in self.people.values():
            if p.hidden_since is None:
                labels[p.tid] = Label(p.number, p.uid, p.color_index)
        return Result(labels, len(self.people), len(labels), events, renumbered, event_boxes)
