"""Tests for violations.py. Run: python3 test_violations.py"""
import json
import unittest

from violations import (NO_HELMET, NO_VEST, RESTRICTED_ZONE, Fallback, Person, ViolationTracker, content_rect,
                        event_msg, helmet_judgeable, vest_judgeable,
                        foot_point, make_id, parse_ts, parse_zones, point_in_polygon, violation_msg, zone_at,
                        zone_match, rect_poly_overlap, polygon_area, polygon_self_intersects)

FPS = 10.0
BOX = [0.4, 0.2, 0.2, 0.5]           # foot point (0.5, 0.7)
ZONE = ("zone-a", [[0.3, 0.6], [0.7, 0.6], [0.7, 0.9], [0.3, 0.9]])
EPOCH = 1792112523                   # 2026-10-16 08:02:03 +07:00


def run(tr, t0, t1, helmet=True, vest=True, bbox=BOX, uid=7, present=None):
    """Feed one person every 1/FPS s in [t0, t1); return [(t, type, repeat)] sent."""
    sent = []
    n = int(round((t1 - t0) * FPS))
    for i in range(n):
        t = t0 + i / FPS
        out = tr.update(t, [Person(uid, bbox, 0.9, helmet, vest)], [uid] if present is None else present)
        sent += [(round(t, 1), v.type, v.repeat) for v in out]
    return sent


class THold(unittest.TestCase):
    def test_ppe_hold_2s(self):
        sent = run(ViolationTracker(), 0.0, 2.5, helmet=False)
        self.assertEqual(sent, [(2.0, NO_HELMET, 0)])

    def test_short_x_never_sent(self):
        tr = ViolationTracker()
        sent = run(tr, 0.0, 1.9, vest=False) + run(tr, 1.9, 3.0, vest=True)
        self.assertEqual(sent, [])

    def test_zone_hold_half_second(self):
        tr = ViolationTracker()
        tr.set_zones([ZONE])
        sent = run(tr, 0.0, 1.0)
        self.assertEqual(sent, [(0.5, RESTRICTED_ZONE, 0)])

    def test_unknown_not_counted(self):
        tr = ViolationTracker()
        self.assertEqual(run(tr, 0.0, 10.0, helmet=None, vest=None), [])
        self.assertEqual((tr.compliant, tr.violating), (0, 0))

    def test_unknown_breaks_run(self):
        tr = ViolationTracker()
        sent = run(tr, 0.0, 1.5, helmet=False) + run(tr, 1.5, 1.6, helmet=None) + run(tr, 1.6, 3.0, helmet=False)
        self.assertEqual(sent, [])          # 1.6 + 2.0 = 3.6 not reached
        self.assertEqual(run(tr, 3.0, 3.7, helmet=False), [(3.6, NO_HELMET, 0)])


class TRepeat(unittest.TestCase):
    def test_repeat_every_5s(self):
        sent = run(ViolationTracker(), 0.0, 15.0, vest=False)
        self.assertEqual(sent, [(4.0, NO_VEST, 0), (9.0, NO_VEST, 1), (14.0, NO_VEST, 2)])

    def test_x_check_x_restarts(self):
        tr = ViolationTracker()
        sent = run(tr, 0.0, 8.0, helmet=False) + run(tr, 8.0, 9.0, helmet=True) + run(tr, 9.0, 12.0, helmet=False)
        self.assertEqual(sent, [(2.0, NO_HELMET, 0), (7.0, NO_HELMET, 1), (11.0, NO_HELMET, 0)])

    def test_two_types_independent(self):
        sent = run(ViolationTracker(hold_s={NO_VEST: 2.0}), 0.0, 2.1, helmet=False, vest=False)
        self.assertEqual(sent, [(2.0, NO_HELMET, 0), (2.0, NO_VEST, 0)])



class TVestHold(unittest.TestCase):
    def test_vest_hold_4s_helmet_2s(self):
        sent = run(ViolationTracker(), 0.0, 4.5, helmet=False, vest=False)
        self.assertEqual(sent, [(2.0, NO_HELMET, 0), (4.0, NO_VEST, 0)])

    def test_vest_x_shorter_than_4s_not_sent(self):
        tr = ViolationTracker()
        self.assertEqual(run(tr, 0.0, 3.9, vest=False) + run(tr, 3.9, 5.0, vest=True), [])

    def test_vest_hold_option(self):
        sent = run(ViolationTracker(hold_s={NO_VEST: 6.0}), 0.0, 6.5, helmet=False, vest=False)
        self.assertEqual(sent, [(2.0, NO_HELMET, 0), (6.0, NO_VEST, 0)])


class TPartial(unittest.TestCase):
    FULL = (0.0, 0.0, 1280.0, 720.0)
    PORTRAIT = content_rect(720, 1280, 1280, 720, True)    # picture x 437.5..842.5, y 0..720

    def test_content_rect(self):
        self.assertEqual(content_rect(1920, 1080, 1280, 720, True), self.FULL)
        self.assertEqual(content_rect(720, 1280, 1280, 720, False), self.FULL)   # stretched: whole frame
        self.assertEqual(self.PORTRAIT, (437.5, 0.0, 842.5, 720.0))

    # one box per edge of the 1280x720 frame, each touching only that edge
    EDGE_BOXES = {"left": (5, 100, 200, 500), "right": (1075, 100, 200, 500),
                  "top": (500, 5, 200, 500), "bottom": (500, 210, 200, 505)}
    # (helmet judgeable, vest judgeable) per edge
    EXPECT = {"left": (True, False), "right": (True, False), "top": (False, True), "bottom": (True, True)}

    def test_inside_and_wide_enough(self):
        for box in [(500, 100, 200, 500), (500, 100, 125, 500)]:              # width / height = 0.25 is fine
            self.assertTrue(vest_judgeable(box, self.FULL))
            self.assertTrue(helmet_judgeable(box, self.FULL))

    def test_four_edges_times_helmet_and_vest(self):
        for edge, box in self.EDGE_BOXES.items():
            self.assertEqual((helmet_judgeable(box, self.FULL), vest_judgeable(box, self.FULL)), self.EXPECT[edge], edge)

    def test_four_edges_of_the_padded_picture(self):
        # portrait picture x 437.5..842.5: same rule on its own edges, the black bars do not count
        boxes = {"left": (440, 100, 140, 400), "right": (700, 100, 140, 400),
                 "top": (550, 5, 140, 400), "bottom": (550, 318, 140, 400)}
        for edge, box in boxes.items():
            self.assertEqual((helmet_judgeable(box, self.PORTRAIT), vest_judgeable(box, self.PORTRAIT)),
                             self.EXPECT[edge], edge)
        # the left / right boxes are far from the 1280 frame edges: judgeable without padding
        self.assertTrue(vest_judgeable(boxes["left"], self.FULL))
        self.assertTrue(vest_judgeable(boxes["right"], self.FULL))

    def test_narrow_box(self):
        self.assertFalse(vest_judgeable((600, 100, 50, 300), self.FULL))        # 0.17 < 0.25
        self.assertFalse(vest_judgeable((600, 100, 10, 0), self.FULL))
        self.assertTrue(helmet_judgeable((600, 100, 50, 300), self.FULL))       # narrow: helmet still judged

    def test_head_cut_helmet_unknown_vest_still_judged(self):
        tr = ViolationTracker()
        sent = []
        for i in range(50):        # box at the top edge: the app passes helmet None ("?"), vest as seen
            sent += [(v.type, v.repeat) for v in tr.update(i / FPS, [Person(7, BOX, 0.9, None, False)], [7])]
        self.assertEqual(sent, [(NO_VEST, 0)])

    def test_partial_vest_unknown_no_no_vest_but_helmet_still_judged(self):
        tr = ViolationTracker()
        sent = []
        for i in range(80):        # a person cut by the edge: the app passes vest None ("?"), helmet as seen
            sent += [(v.type, v.repeat) for v in tr.update(i / FPS, [Person(7, BOX, 0.9, False, None)], [7])]
        self.assertEqual(sent, [(NO_HELMET, 0), (NO_HELMET, 1)])


class TLeave(unittest.TestCase):
    def test_left_frame_stops(self):
        tr = ViolationTracker()
        self.assertEqual(run(tr, 0.0, 2.1, helmet=False), [(2.0, NO_HELMET, 0)])
        for i in range(100):                        # gone: not seen, not present
            self.assertEqual(tr.update(2.1 + i / FPS, [], []), [])
        self.assertEqual(tr.runs, {})
        # back as the same uid later: a new run (hold again, repeat 0)
        self.assertEqual(run(tr, 20.0, 22.1, helmet=False), [(22.0, NO_HELMET, 0)])

    def test_hidden_keeps_run_but_sends_nothing(self):
        tr = ViolationTracker()
        run(tr, 0.0, 2.1, helmet=False)
        for i in range(60):                         # hidden 2.1 .. 8.0 s, still held by PersonIds
            self.assertEqual(tr.update(2.1 + i / FPS, [], [7]), [])
        self.assertEqual(run(tr, 8.1, 8.2, helmet=False), [(8.1, NO_HELMET, 1)])


class TZones(unittest.TestCase):
    def test_point_in_polygon(self):
        sq = ZONE[1]
        self.assertTrue(point_in_polygon(0.5, 0.7, sq))
        self.assertFalse(point_in_polygon(0.2, 0.7, sq))
        self.assertFalse(point_in_polygon(0.5, 0.95, sq))
        tri = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        self.assertTrue(point_in_polygon(0.2, 0.2, tri))
        self.assertFalse(point_in_polygon(0.6, 0.6, tri))
        concave = [[0, 0], [1, 0], [1, 1], [0.5, 0.3], [0, 1]]    # notch at the top middle
        self.assertTrue(point_in_polygon(0.1, 0.5, concave))
        self.assertFalse(point_in_polygon(0.5, 0.6, concave))

    def test_foot_point_and_zone_id(self):
        self.assertEqual(foot_point(BOX), (0.5, 0.7))
        self.assertEqual(zone_at(0.5, 0.7, [ZONE]), "zone-a")
        self.assertEqual(zone_at(0.1, 0.1, [ZONE]), "")

    def test_zone_id_on_ppe_violation(self):
        tr = ViolationTracker()
        tr.set_zones([ZONE])
        out = []
        for i in range(25):
            out += tr.update(i / FPS, [Person(7, BOX, 0.9, False, True)], [7])
        self.assertEqual(sorted((v.type, v.zone_id) for v in out),
                         [(NO_HELMET, "zone-a"), (RESTRICTED_ZONE, "zone-a")])
        tr2 = ViolationTracker()
        out = []
        for i in range(25):
            out += tr2.update(i / FPS, [Person(7, BOX, 0.9, False, True)], [7])
        self.assertEqual([v.zone_id for v in out], [""])

    def test_parse_zones(self):
        good = json.dumps({"camera_id": "cam01", "ts": "x", "zones": [
            {"id": "zone-a", "name": "A", "points": [[0.1, 0.55], [0.45, 0.55], [0.45, 0.95], [0.1, 0.95]]},
            {"id": "bad", "points": [[0.1, 0.1], [0.2, 0.2]]}]}).encode()
        self.assertEqual(parse_zones(good, "cam01"), [("zone-a", [[0.1, 0.55], [0.45, 0.55], [0.45, 0.95], [0.1, 0.95]])])
        self.assertIsNone(parse_zones(good, "cam02"))
        self.assertIsNone(parse_zones(b"not json", "cam01"))
        self.assertEqual(parse_zones(b'{"camera_id":"cam01","zones":[]}', "cam01"), [])


# square zone x[0.3,0.7] y[0.6,0.9]; foot of BOX (0.5,0.7) is inside it
SQ = ("zone-a", [[0.3, 0.6], [0.7, 0.6], [0.7, 0.9], [0.3, 0.9]])


class TZoneModes(unittest.TestCase):
    def test_overlap_fraction_values(self):
        sq = [[0.0, 0.0], [0.1, 0.0], [0.1, 0.2], [0.0, 0.2]]        # covers the left half of a 0.2x0.2 box
        self.assertAlmostEqual(rect_poly_overlap((0.0, 0.0, 0.2, 0.2), sq), 0.5, places=6)
        inside = [[0.3, 0.6], [0.7, 0.6], [0.7, 0.9], [0.3, 0.9]]
        self.assertAlmostEqual(rect_poly_overlap((0.4, 0.65, 0.6, 0.85), inside), 1.0, places=6)  # box in zone
        self.assertAlmostEqual(rect_poly_overlap((0.0, 0.0, 0.1, 0.1), inside), 0.0, places=6)    # box outside

    def test_overlap_mode_threshold(self):
        # box mostly above the zone -> small overlap (~9 % < 0.10), not a restricted-zone hit
        lo = [0.4, 0.30, 0.2, 0.33]          # rect(0.4,0.30,0.6,0.63): only y0.60..0.63 is in the zone
        ov_lo = rect_poly_overlap((lo[0], lo[1], lo[0] + lo[2], lo[1] + lo[3]), SQ[1])
        self.assertLess(ov_lo, 0.10)
        zid_lo, ov_got = zone_match(lo, [SQ], "overlap", 0.10)
        self.assertEqual(zid_lo, "")
        self.assertAlmostEqual(ov_got, ov_lo, places=9)
        # box reaching further down -> larger overlap (> 0.15), a hit
        hi = [0.4, 0.30, 0.2, 0.40]          # rect(0.4,0.30,0.6,0.70): y0.60..0.70 is in the zone
        ov_hi = rect_poly_overlap((hi[0], hi[1], hi[0] + hi[2], hi[1] + hi[3]), SQ[1])
        self.assertGreater(ov_hi, 0.15)
        zid, ov = zone_match(hi, [SQ], "overlap", 0.10)
        self.assertEqual(zid, "zone-a")
        self.assertAlmostEqual(ov, ov_hi, places=9)

    def test_fully_inside(self):
        zid, ov = zone_match([0.4, 0.65, 0.2, 0.2], [SQ], "overlap", 0.10)
        self.assertEqual(zid, "zone-a")
        self.assertAlmostEqual(ov, 1.0, places=6)

    def test_outside(self):
        self.assertEqual(zone_match([0.0, 0.0, 0.1, 0.1], [SQ], "overlap", 0.10), ("", 0.0))

    def test_concave_polygon_overlap(self):
        # C-shape (concave): a box in the notch overlaps little; shoelace area of the clip is still correct
        c = [[0.0, 0.0], [0.4, 0.0], [0.4, 0.1], [0.1, 0.1], [0.1, 0.3], [0.4, 0.3], [0.4, 0.4], [0.0, 0.4]]
        self.assertAlmostEqual(polygon_area(c), 0.4 * 0.4 - 0.3 * 0.2, places=6)   # outer minus the notch
        notch = (0.1, 0.1, 0.4, 0.3)                                               # fully in the empty notch
        self.assertAlmostEqual(rect_poly_overlap(notch, c), 0.0, places=6)
        spanning = (0.0, 0.0, 0.2, 0.4)                                            # left arm + part of notch
        self.assertGreater(rect_poly_overlap(spanning, c), 0.0)

    def test_person_in_front_of_zone(self):
        # zone is a band high up; a tall person stands in front: foot is BELOW the zone, body overlaps it a lot
        band = ("z", [[0.2, 0.2], [0.8, 0.2], [0.8, 0.5], [0.2, 0.5]])
        tall = [0.4, 0.1, 0.2, 0.8]                       # foot (0.5, 0.9) is outside the band
        fzid, fov = zone_match(tall, [band], "foot", 0.10)
        self.assertEqual(fzid, "")                        # foot mode: no hit
        self.assertAlmostEqual(fov, rect_poly_overlap((0.4, 0.1, 0.6, 0.9), band[1]), places=9)
        zid, ov = zone_match(tall, [band], "overlap", 0.10)
        self.assertEqual(zid, "z")
        self.assertGreater(ov, 0.10)

    def test_bottom_mode(self):
        # feet occluded: only the bottom 25 % band must overlap the zone
        band = ("z", [[0.3, 0.75], [0.7, 0.75], [0.7, 1.0], [0.3, 1.0]])
        box = [0.4, 0.2, 0.2, 0.7]                        # rect(0.4,0.2,0.6,0.9); bottom band y0.725..0.9
        zid, ov = zone_match(box, [band], "bottom", 0.10)
        self.assertEqual(zid, "z")
        self.assertGreater(ov, 0.10)

    def test_foot_mode_matches_old(self):
        for box, exp in [(BOX, "zone-a"), ([0.0, 0.0, 0.1, 0.1], "")]:
            fx, fy = foot_point(box)
            self.assertEqual(zone_match(box, [SQ], "foot", 0.10)[0], zone_at(fx, fy, [SQ]))
            self.assertEqual(zone_match(box, [SQ], "foot", 0.10)[0], exp)

    def test_foot_mode_tracker_same_as_old(self):
        tr = ViolationTracker(zone_mode="foot")
        tr.set_zones([SQ])
        sent = run(tr, 0.0, 1.0)
        self.assertEqual(sent, [(0.5, RESTRICTED_ZONE, 0)])

    def test_per_zone_override(self):
        payload = json.dumps({"camera_id": "cam01", "zones": [
            {"id": "z1", "points": [[0.3, 0.6], [0.7, 0.6], [0.7, 0.9], [0.3, 0.9]], "mode": "foot"},
            {"id": "z2", "points": [[0.3, 0.6], [0.7, 0.6], [0.7, 0.9], [0.3, 0.9]], "min_overlap": 0.5}]}).encode()
        zones = parse_zones(payload, "cam01")
        self.assertEqual(zones[0][2], {"mode": "foot"})
        self.assertEqual(zones[1][2], {"min_overlap": 0.5})

    def test_self_intersect_detected(self):
        bowtie = [[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]]
        self.assertTrue(polygon_self_intersects(bowtie))
        self.assertFalse(polygon_self_intersects([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]))


class TCounts(unittest.TestCase):
    def test_counts(self):
        tr = ViolationTracker()
        tr.update(0.0, [Person(1, BOX, 0.9, True, True), Person(2, BOX, 0.9, False, True),
                        Person(3, BOX, 0.9, True, None), Person(4, BOX, 0.9, None, False)], [1, 2, 3, 4])
        self.assertEqual((tr.compliant, tr.violating), (1, 2))
        tr.set_zones([ZONE])                           # in a zone: violating even with ✓ ✓
        tr.update(0.1, [Person(1, BOX, 0.9, True, True)], [1])
        self.assertEqual((tr.compliant, tr.violating), (0, 1))


class TMessages(unittest.TestCase):
    def test_ids_and_ts(self):
        self.assertEqual(make_id("cam01", EPOCH + 0.9, 7), "cam01-20261016-080203-007")
        self.assertEqual(make_id("cam01", EPOCH, 1234), "cam01-20261016-080203-234")
        self.assertEqual(parse_ts("2026-10-16T08:02:03+07:00"), EPOCH)
        self.assertEqual(parse_ts("2026-10-16T08:02:03.123+07:00"), EPOCH)
        self.assertEqual(parse_ts("2026-10-16T01:02:03Z"), EPOCH)
        self.assertIsNone(parse_ts("yesterday"))

    def test_violation_and_event_fields(self):
        tr = ViolationTracker()
        out = []
        for i in range(21):
            out += tr.update(i / FPS, [Person(7, BOX, 0.8234, False, True)], [7])
        v = out[0]
        sid = make_id("cam01", EPOCH, v.uid)
        m = violation_msg("cam01", v, EPOCH, sid)
        self.assertEqual(set(m), {"camera_id", "ts", "type", "track_id", "conf", "zone_id", "bbox", "snapshot_id",
                                  "repeat", "zone_overlap"})
        self.assertEqual((m["type"], m["track_id"], m["conf"], m["zone_id"], m["repeat"], m["ts"]),
                         (NO_HELMET, 7, 0.823, "", 0, "2026-10-16T08:02:03+07:00"))
        e = event_msg("cam01", v, EPOCH + 1, sid)
        self.assertEqual(set(e), {"event_id", "ts", "camera_id", "zone_id", "type", "severity", "track_id",
                                  "confidence", "bbox", "snapshot_id", "via"})
        self.assertEqual((e["event_id"], e["severity"], e["via"], e["snapshot_id"]),
                         ("cam01-20261016-080204-007-nh", "high", "fallback", "cam01-20261016-080203-007"))

    def test_event_ids_differ_by_type_same_second(self):
        tr = ViolationTracker()
        tr.set_zones([ZONE])
        out = []
        for i in range(21):
            out += tr.update(i / FPS, [Person(7, BOX, 0.9, False, False)], [7])
        for i in range(21, 41):
            out += tr.update(i / FPS, [Person(7, BOX, 0.9, False, False)], [7])
        out = [v for v in out if v.repeat == 0]
        ids = [event_msg("cam01", v, EPOCH, make_id("cam01", EPOCH, v.uid))["event_id"] for v in out]
        self.assertEqual(sorted(ids), ["cam01-20261016-080203-007-nh", "cam01-20261016-080203-007-nv",
                                       "cam01-20261016-080203-007-rz"])


class TFallback(unittest.TestCase):
    def test_mode(self):
        f = Fallback()
        self.assertEqual(f.mode(EPOCH), "fallback")                      # never received
        f.on_cira_status(json.dumps({"online": True, "ts": "2026-10-16T08:02:03+07:00"}).encode())
        self.assertEqual(f.mode(EPOCH + 15), "cira")
        self.assertEqual(f.mode(EPOCH + 16), "fallback")                 # older than 15 s
        f.on_cira_status(b'{"online": false, "ts": "2026-10-16T08:02:03+07:00"}')
        self.assertEqual(f.mode(EPOCH), "fallback")

    def test_switched(self):
        f = Fallback()
        self.assertEqual(f.switched(EPOCH), (None, "fallback"))
        self.assertIsNone(f.switched(EPOCH + 1))
        f.on_cira_status(json.dumps({"online": True, "ts": "2026-10-16T08:02:05+07:00"}))
        self.assertEqual(f.switched(EPOCH + 3), ("fallback", "cira"))
        self.assertEqual(f.switched(EPOCH + 30), ("cira", "fallback"))

    def test_cooldown_30s(self):
        f = Fallback()
        self.assertTrue(f.allow("cam01", 7, NO_HELMET, 100.0))
        self.assertFalse(f.allow("cam01", 7, NO_HELMET, 105.0))
        self.assertTrue(f.allow("cam01", 7, NO_VEST, 105.0))             # other type
        self.assertTrue(f.allow("cam01", 8, NO_HELMET, 105.0))           # other track
        self.assertFalse(f.allow("cam01", 7, NO_HELMET, 129.9))
        self.assertTrue(f.allow("cam01", 7, NO_HELMET, 130.0))


if __name__ == "__main__":
    unittest.main()
