"""Tests for ppe_smooth.py. Run: python3 test_ppe_smooth.py"""
import unittest
from ppe_smooth import PpeSmoother

FPS = 29     # camera rate measured on the Jetson (stream1, 5W)


def feed(s, uid, pattern, n):
    """Feed n frames; pattern(i) -> (has_helmet, has_vest). Returns the list of results."""
    return [s.update(uid, *pattern(i)) for i in range(n)]


class TPpeSmoother(unittest.TestCase):
    def test_new_person_is_unknown_first(self):
        s = PpeSmoother()
        out = feed(s, 1, lambda i: (True, True), 8)
        self.assertEqual(out[:7], [(None, None)] * 7)        # fewer than 8 frames: "?"
        self.assertEqual(out[7], (True, True))               # 8th frame: decided

    def test_new_person_without_items_is_unknown_then_cross(self):
        s = PpeSmoother()
        out = feed(s, 1, lambda i: (False, False), 8)
        self.assertEqual(out[6], (None, None))
        self.assertEqual(out[7], (False, False))

    def test_flicker_one_in_three_stays_tick(self):
        # item detected only in 1 of every 3 frames (33 %), for 10 s
        s = PpeSmoother()
        out = feed(s, 1, lambda i: (i % 3 == 0, i % 3 == 0), 10 * FPS)
        self.assertTrue(all(r == (True, True) for r in out[8:]), "must stay ✓ once decided")

    def test_flicker_missing_one_in_three_stays_tick(self):
        s = PpeSmoother()
        out = feed(s, 1, lambda i: (i % 3 != 0, i % 3 != 0), 10 * FPS)
        self.assertTrue(all(r == (True, True) for r in out[8:]))

    def test_really_removed_turns_cross_within_one_second(self):
        s = PpeSmoother()
        feed(s, 1, lambda i: (True, True), 3 * FPS)
        self.assertEqual(s.status(1), (True, True))
        out = feed(s, 1, lambda i: (False, False), FPS)       # helmet and vest off for 1 s
        self.assertEqual(out[-1], (False, False))
        first_cross = next(i for i, r in enumerate(out) if r == (False, False))
        self.assertLess(first_cross, FPS)

    def test_only_helmet_removed(self):
        s = PpeSmoother()
        feed(s, 1, lambda i: (True, True), 2 * FPS)
        out = feed(s, 1, lambda i: (False, True), FPS)
        self.assertEqual(out[-1], (False, True))

    def test_hysteresis_band_keeps_previous(self):
        s = PpeSmoother()
        feed(s, 1, lambda i: (True, False), 20)               # helmet ✓, vest ✗
        # then 20 frames with the item in 1 of 5 frames (20 %): inside 10-30 %, keep both
        out = feed(s, 1, lambda i: (i % 5 == 0, i % 5 == 0), 40)
        self.assertTrue(all(r == (True, False) for r in out))

    def test_band_edges(self):
        s = PpeSmoother(window=20)
        feed(s, 1, lambda i: (False, False), 20)
        feed(s, 1, lambda i: (i < 6, False), 20)              # helmet 6/20 = 30 % exactly: ✓
        self.assertEqual(s.status(1), (True, False))
        s = PpeSmoother(window=20)
        feed(s, 2, lambda i: (True, True), 20)
        feed(s, 2, lambda i: (i < 2, False), 20)              # 2/20 = 10 %: not below 10 %, keep ✓
        self.assertEqual(s.status(2), (True, False))
        feed(s, 2, lambda i: (False, False), 1)               # 1/20 = 5 %: ✗
        self.assertEqual(s.status(2), (False, False))

    def test_people_are_separate_and_forget(self):
        s = PpeSmoother()
        feed(s, 1, lambda i: (True, True), 10)
        feed(s, 2, lambda i: (False, False), 10)
        self.assertEqual(s.status(1), (True, True))
        self.assertEqual(s.status(2), (False, False))
        s.forget([2])
        self.assertEqual(s.status(1), (None, None))
        self.assertEqual(s.status(2), (False, False))

    def test_status_does_not_add_a_frame(self):
        s = PpeSmoother()
        feed(s, 1, lambda i: (True, True), 7)
        for _ in range(5):
            self.assertEqual(s.status(1), (None, None))
        self.assertEqual(s.update(1, True, True), (True, True))


    def test_vest_unknown_frames_leave_vest_alone(self):
        s = PpeSmoother()
        for _ in range(20):
            s.update(1, True, True)
        self.assertEqual(s.status(1), (True, True))
        for _ in range(40):        # seen only in part: vest not judged, helmet removed meanwhile
            h, v = s.update(1, False, None)
        self.assertEqual((h, v), (False, True))
        self.assertEqual(list(s.tracks[1].v), [1] * 20)

    def test_vest_unknown_from_the_start_stays_unknown(self):
        s = PpeSmoother()
        for _ in range(30):
            h, v = s.update(1, True, None)
        self.assertEqual((h, v), (True, None))


    def test_helmet_unknown_frames_leave_helmet_alone(self):
        s = PpeSmoother()
        for _ in range(20):
            s.update(1, True, True)
        for _ in range(40):        # head cut by the top edge: helmet not judged, vest removed meanwhile
            h, v = s.update(1, None, False)
        self.assertEqual((h, v), (True, False))
        self.assertEqual(list(s.tracks[1].h), [1] * 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
