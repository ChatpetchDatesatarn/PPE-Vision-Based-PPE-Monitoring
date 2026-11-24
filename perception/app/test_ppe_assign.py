"""Tests for ppe_assign.py. Run: python3 test_ppe_assign.py"""
import unittest
from ppe_assign import assign_ppe, owner, HELMET_BAND, VEST_BAND

PERSON = (100, 100, 100, 400)       # left 100..200, top 100..500, height 400


def at(cx, cy, w=20, h=20):
    """Item box with its centre at (cx, cy)."""
    return (cx - w / 2.0, cy - h / 2.0, w, h)


def y_rel(r, p=PERSON):
    return p[1] + r * p[3]


class TOwner(unittest.TestCase):
    def test_helmet_top_of_person(self):
        self.assertEqual(owner(at(150, y_rel(0.10)), [(1, PERSON)], HELMET_BAND), 1)

    def test_helmet_band_edges(self):
        self.assertEqual(owner(at(150, y_rel(0.35)), [(1, PERSON)], HELMET_BAND), 1)    # 35 % exactly: in
        self.assertIsNone(owner(at(150, y_rel(0.36)), [(1, PERSON)], HELMET_BAND))      # just below: out

    def test_helmet_centre_above_person_box(self):
        # helmet box overlaps the person, but its centre is above the top edge
        self.assertIsNone(owner(at(150, 95, h=30), [(1, PERSON)], HELMET_BAND))

    def test_helmet_held_in_hand_low(self):
        self.assertIsNone(owner(at(150, y_rel(0.55)), [(1, PERSON)], HELMET_BAND))

    def test_centre_outside_left_right(self):
        self.assertIsNone(owner(at(99, y_rel(0.1)), [(1, PERSON)], HELMET_BAND))
        self.assertIsNone(owner(at(201, y_rel(0.1)), [(1, PERSON)], HELMET_BAND))
        self.assertEqual(owner(at(200, y_rel(0.1)), [(1, PERSON)], HELMET_BAND), 1)     # on the edge: in

    def test_vest_band(self):
        self.assertIsNone(owner(at(150, y_rel(0.19)), [(1, PERSON)], VEST_BAND))
        self.assertEqual(owner(at(150, y_rel(0.20)), [(1, PERSON)], VEST_BAND), 1)
        self.assertEqual(owner(at(150, y_rel(0.45)), [(1, PERSON)], VEST_BAND), 1)
        self.assertEqual(owner(at(150, y_rel(0.75)), [(1, PERSON)], VEST_BAND), 1)
        self.assertIsNone(owner(at(150, y_rel(0.76)), [(1, PERSON)], VEST_BAND))

    def test_overlap_closest_vertical_centre_line_wins(self):
        a = (100, 100, 100, 400)          # centre line x = 150
        b = (160, 120, 100, 400)          # centre line x = 210, overlaps a in x 160..200
        # helmet at x 190: inside both, 40 from a's line, 20 from b's line -> b
        self.assertEqual(owner(at(190, 150), [(1, a), (2, b)], HELMET_BAND), 2)
        # helmet at x 170: 20 from a, 40 from b -> a
        self.assertEqual(owner(at(170, 150), [(1, a), (2, b)], HELMET_BAND), 1)

    def test_band_decides_before_distance(self):
        # near person (front, big box) and far person (small box higher up) both contain the vest centre;
        # only the far one has it in the vest band, so the far one gets it even though it is farther from the line
        near = (100, 100, 200, 600)       # centre line x = 200; y 160 is at 10 % -> not in vest band
        far = (150, 100, 40, 120)         # centre line x = 170; y 160 is at 50 %
        # x 190: 10 from near's line, 20 from far's line
        self.assertEqual(owner(at(190, 160), [(1, near), (2, far)], VEST_BAND), 2)

    def test_tie_first_listed(self):
        a = (100, 100, 100, 400)
        b = (100, 100, 100, 400)
        self.assertEqual(owner(at(150, 150), [(7, a), (3, b)], HELMET_BAND), 7)

    def test_zero_size_person_ignored(self):
        self.assertIsNone(owner(at(150, 150), [(1, (100, 100, 0, 400))], HELMET_BAND))

    def test_no_persons(self):
        self.assertIsNone(owner(at(150, 150), [], HELMET_BAND))


class TAssign(unittest.TestCase):
    def test_all_cases(self):
        p1 = (100, 100, 100, 400)
        p2 = (400, 100, 100, 400)
        p3 = (700, 100, 100, 400)
        helmets = [at(150, y_rel(0.1, p1)), at(450, y_rel(0.1, p2))]
        vests = [at(150, y_rel(0.5, p1)), at(750, y_rel(0.5, p3)), at(1000, 300)]   # last one: nobody
        r = assign_ppe([(1, p1), (2, p2), (3, p3)], helmets, vests)
        self.assertEqual(r, {1: (True, True), 2: (True, False), 3: (False, True)})

    def test_no_items(self):
        self.assertEqual(assign_ppe([(1, PERSON)], [], []), {1: (False, False)})

    def test_no_persons(self):
        self.assertEqual(assign_ppe([], [at(150, 150)], [at(150, 300)]), {})

    def test_item_goes_to_one_person_only(self):
        a = (100, 100, 100, 400)
        b = (160, 100, 100, 400)
        r = assign_ppe([(1, a), (2, b)], [at(185, 150)], [])
        self.assertEqual(r, {1: (False, False), 2: (True, False)})

    def test_two_helmets_one_person(self):
        r = assign_ppe([(1, PERSON)], [at(140, 130), at(160, 140)], [])
        self.assertEqual(r, {1: (True, False)})


if __name__ == "__main__":
    unittest.main(verbosity=2)
