"""Assign helmet / vest detections to people (pure Python, 3.6-compatible, no DeepStream imports).

Boxes are (left, top, width, height) in pixels.
- helmet belongs to a person if its centre is inside the person box and in the top 35 % of the box height
- vest belongs to a person if its centre is inside the person box and between 20 % and 75 % of the box height
- several people fit: the one whose vertical centre line is closest to the item centre (horizontal distance) wins;
  on a tie, the person listed first
One person can get several items; each item goes to at most one person.
"""

HELMET_BAND = (0.0, 0.35)
VEST_BAND = (0.20, 0.75)


def _center(b):
    return b[0] + b[2] / 2.0, b[1] + b[3] / 2.0


def owner(item_box, persons, band):
    """Key of the person that owns item_box, or None. persons = [(key, box)], band = (lo, hi) of person height."""
    cx, cy = _center(item_box)
    lo, hi = band
    best, best_d = None, None
    for key, (l, t, w, h) in persons:
        if w <= 0 or h <= 0:
            continue
        if not (l <= cx <= l + w and t <= cy <= t + h):
            continue
        rel = (cy - t) / float(h)
        if not (lo <= rel <= hi):
            continue
        d = abs(cx - (l + w / 2.0))
        if best_d is None or d < best_d:
            best, best_d = key, d
    return best


def assign_ppe(persons, helmets, vests):
    """persons = [(key, box)], helmets / vests = [box]. Returns {key: (has_helmet, has_vest)} for every person."""
    has_h = set()
    has_v = set()
    for b in helmets:
        k = owner(b, persons, HELMET_BAND)
        if k is not None:
            has_h.add(k)
    for b in vests:
        k = owner(b, persons, VEST_BAND)
        if k is not None:
            has_v.add(k)
    return dict((k, (k in has_h, k in has_v)) for k, _ in persons)
