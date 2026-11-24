"""Tests for ppe_pretrack.py. Run: python3 test_ppe_pretrack.py"""
import unittest

from ppe_pretrack import PreTrackerPpe

PERSON = (500.0, 100.0, 200.0, 500.0)      # left, top, width, height (pixels)
HELMET = (570.0, 105.0, 60.0, 50.0)        # centre in the top 35 % of PERSON
VEST = (540.0, 250.0, 120.0, 150.0)        # centre between 20 % and 75 %


class TPreTracker(unittest.TestCase):
    def test_bound_to_person_in_same_frame(self):
        c = PreTrackerPpe()
        c.put((10, 333), [HELMET], [VEST])
        ppe, helmets, vests = c.assign((10, 333), [(7, PERSON)])
        self.assertEqual(ppe, {7: (True, True)})
        self.assertEqual((helmets, vests), ([HELMET], [VEST]))

    def test_no_person_nothing_counted(self):
        c = PreTrackerPpe()
        c.put((10, 333), [HELMET], [VEST])
        ppe, helmets, vests = c.assign((10, 333), [])
        self.assertEqual(ppe, {})
        self.assertEqual(len(vests), 1)           # still returned for drawing

    def test_item_outside_person_not_counted(self):
        c = PreTrackerPpe()
        c.put((1, 0), [], [(10.0, 10.0, 50.0, 50.0)])
        ppe, _, _ = c.assign((1, 0), [(7, PERSON)])
        self.assertEqual(ppe, {7: (False, False)})

    def test_matched_by_key_not_by_order(self):
        c = PreTrackerPpe()
        c.put((1, 100), [], [VEST])
        c.put((2, 133), [], [])
        c.put((3, 166), [HELMET], [])
        self.assertEqual(c.assign((2, 133), [(7, PERSON)])[0], {7: (False, False)})
        self.assertEqual(c.assign((3, 166), [(7, PERSON)])[0], {7: (True, False)})
        # frame 1 was older than 2: dropped, not handed to a later frame
        self.assertEqual(c.assign((1, 100), [(7, PERSON)])[0], {7: (False, False)})
        self.assertEqual(c.missed, 1)

    def test_same_frame_num_other_pts_after_restart(self):
        c = PreTrackerPpe()
        c.put((0, 900), [], [VEST])
        c.put((0, 0), [], [])                      # pipeline restarted: frame_num 0 again, new pts
        self.assertEqual(c.assign((0, 0), [(7, PERSON)])[0], {7: (False, False)})

    def test_keep_limit(self):
        c = PreTrackerPpe(keep=3)
        for i in range(10):
            c.put((i, i), [], [])
        self.assertEqual(c.take((5, 5)), ([], []))
        self.assertEqual(c.missed, 1)
        self.assertEqual(c.take((9, 9)), ([], []))
        self.assertEqual(c.missed, 1)


if __name__ == "__main__":
    unittest.main()
