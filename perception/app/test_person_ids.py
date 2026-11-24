"""Tests for person_ids.py with simulated tracker output at 30 fps. Run: python3 test_person_ids.py"""
import unittest
from person_ids import PersonIds

FPS = 30.0
W, H = 1280, 720


def box(cx, cy=400, w=80, h=220):
    return (cx - w / 2.0, cy - h / 2.0, w, h)


class T(unittest.TestCase):
    def run_frames(self, mgr, frames):
        out = []
        for i, dets in enumerate(frames):
            out.append(mgr.update(i / FPS, dets))
        return out

    def test_crossing_keeps_numbers(self):
        """A walks right, B walks left; at the crossing both lose their tracker ids for 12 frames
        and come back with new ids. Numbers must stay A=1, B=2."""
        mgr = PersonIds(W, H)
        frames = []
        for f in range(120):
            ax, bx = 300 + f * 6, 1000 - f * 6
            dets = []
            hidden = 54 <= f < 66                    # crossing around f=58
            if not hidden:
                dets.append((1 if f < 54 else 11, box(ax)))
                dets.append((2 if f < 54 else 12, box(bx, cy=410)))
            frames.append(dets)
        res = self.run_frames(mgr, frames)
        self.assertEqual(res[10].labels, {1: (1, 1), 2: (2, 2)})
        self.assertEqual(res[60].in_frame, 2)        # hidden but still in the frame
        self.assertEqual(res[60].detected, 0)
        last = res[-1].labels
        self.assertEqual(last[11][0], 1, "A must keep number 1")
        self.assertEqual(last[12][0], 2, "B must keep number 2")
        self.assertEqual(mgr.total_entered, 2)

    def test_one_hidden_behind_other(self):
        """B stands still, A walks in front of B: only B is hidden (its tracker id is lost), then B returns."""
        mgr = PersonIds(W, H)
        frames = []
        for f in range(100):
            ax = 300 + f * 8
            dets = [(1, box(ax))]
            if not (40 <= f < 60):
                dets.append((2 if f < 40 else 7, box(640, cy=405)))
            frames.append(dets)
        res = self.run_frames(mgr, frames)
        self.assertEqual(res[-1].labels[7], (2, 2))
        self.assertEqual(res[50].in_frame, 2)
        self.assertEqual(res[50].detected, 1)

    def test_exit_edge_then_back_is_new_person(self):
        mgr = PersonIds(W, H)
        frames = []
        for f in range(60):                           # walks out through the right edge
            frames.append([(1, box(1000 + f * 6))] if 1000 + f * 6 < W - 30 else [])
        frames += [[] for _ in range(30)]
        for f in range(10):                           # comes back
            frames.append([(5, box(W - 60 - f * 5))])
        res = self.run_frames(mgr, frames)
        exits = [e for r in res for e in r.events if e[0] == "exit"]
        self.assertEqual(len(exits), 1)
        num, uid = res[-1].labels[5]
        self.assertEqual(uid, 2, "comes back as a new person")
        self.assertEqual(num, 1, "number 1 is free again, so it is reused")
        self.assertEqual(res[-1].in_frame, 1)

    def test_numbers_follow_count(self):
        mgr = PersonIds(W, H)
        r = mgr.update(0, [(1, box(300)), (2, box(600)), (3, box(900))])
        self.assertEqual(sorted(n for n, _ in r.labels.values()), [1, 2, 3])
        # person 2 walks out at the top edge
        mgr.update(0.1, [(1, box(300)), (2, (560, 5, 80, 220)), (3, box(900))])
        r = mgr.update(1.0, [(1, box(300)), (3, box(900))])
        self.assertEqual(r.in_frame, 2)
        self.assertEqual(r.labels[3][0], 2, "person 3 moves up to number 2 when person 2 leaves")
        r = mgr.update(1.1, [(1, box(300)), (3, box(900)), (9, box(640, cy=600))])
        self.assertEqual(r.labels[1][0], 1)
        self.assertEqual(r.labels[3][0], 2)
        self.assertEqual(r.labels[9][0], 3, "new person gets the number after everyone already here")
        self.assertEqual(r.labels[9][1], 4, "and a new unique id")

    def test_numbers_move_up_in_entry_order(self):
        """A=1 B=2 C=3; A leaves -> B=1 C=2; D enters -> 3; B and C leave -> D alone is 1."""
        mgr = PersonIds(W, H)
        mgr.update(0, [(1, box(300)), (2, box(600)), (3, box(900))])
        mgr.update(0.1, [(1, (5, 290, 80, 220)), (2, box(600)), (3, box(900))])   # A at the left edge
        r = mgr.update(1.0, [(2, box(600)), (3, box(900))])                        # A lost at the edge -> left
        self.assertEqual(r.labels, {2: (1, 2), 3: (2, 3)})
        self.assertEqual(sorted(r.renumbered), [(2, 2, 1), (3, 3, 2)], "(uid, old, new) for B and C")
        r = mgr.update(1.1, [(2, box(600)), (3, box(900)), (4, box(400, cy=600))])
        self.assertEqual(r.labels[4], (3, 4))
        self.assertEqual(r.renumbered, [], "a new person is an enter event, not a renumber")
        enter = [e for e in r.events if e[0] == "enter"]
        self.assertEqual(enter, [("enter", 4, 3)], "enter event carries the final number")
        mgr.update(1.2, [(2, (1195, 290, 80, 220)), (3, (1195, 290, 80, 220)), (4, box(400, cy=600))])  # B, C at right edge
        r = mgr.update(2.0, [(4, box(400, cy=600))])
        self.assertEqual(r.in_frame, 1)
        self.assertEqual(r.labels, {4: (1, 4)}, "one person alone is number 1")

    def test_hidden_person_keeps_place(self):
        """B is hidden (not gone): C behind B must not move up while B is only hidden."""
        mgr = PersonIds(W, H)
        mgr.update(0, [(1, box(300)), (2, box(600)), (3, box(900))])
        r = mgr.update(1.0, [(1, box(300)), (3, box(900))])     # B hidden in the middle, 1 s
        self.assertEqual(r.in_frame, 3)
        self.assertEqual(r.labels[3][0], 3)
        self.assertEqual(r.renumbered, [])

    def test_hidden_too_long_in_middle(self):
        mgr = PersonIds(W, H, hidden_ttl_s=4.0)
        mgr.update(0, [(1, box(640))])
        r = mgr.update(3.9, [])
        self.assertEqual(r.in_frame, 1)
        r = mgr.update(4.1, [])
        self.assertEqual(r.in_frame, 0)
        self.assertEqual(r.events[0][0], "exit")

    def test_new_person_far_away_not_rejoined(self):
        """someone hidden on the left must not be 'rejoined' by a stranger appearing on the right."""
        mgr = PersonIds(W, H)
        mgr.update(0, [(1, box(300))])
        mgr.update(0.5, [])
        r = mgr.update(0.6, [(2, box(1000))])
        self.assertEqual(r.labels[2], (2, 2))
        self.assertEqual(r.in_frame, 2)

    def test_door_region_counts_as_edge(self):
        door = [(600, 200), (700, 200), (700, 600), (600, 600)]
        mgr = PersonIds(W, H, exit_regions=[door])
        mgr.update(0, [(1, box(650))])
        r = mgr.update(1.0, [])
        self.assertEqual(r.in_frame, 0, "lost inside the door region -> left quickly")


def at_left(h=220):
    """standing in the left edge zone (edge_margin 0.04 x 1280 = 51 px)"""
    return (5, 400 - h / 2.0, 80, h)


def at_right(h=220):
    return (W - 85, 400 - h / 2.0, 80, h)


class TApp(unittest.TestCase):
    """values the app uses: edge_ttl_s=1.5, regrace_s=2.0"""

    def mgr(self):
        return PersonIds(W, H, edge_ttl_s=1.5, regrace_s=2.0)

    def play(self, mgr, timeline):
        """timeline: [(t, detections)]; returns all results"""
        return [mgr.update(t, d) for t, d in timeline]

    def frames(self, t0, t1, dets):
        n = int(round((t1 - t0) * FPS))
        return [(t0 + i / FPS, dets) for i in range(n)]

    def test_a_edge_lost_1_2s_same_uid(self):
        """(ก) stands at the edge, box gone for 1.2 s, comes back: hidden rejoin, same uid, entered once"""
        mgr = self.mgr()
        res = self.play(mgr, self.frames(0, 1.0, [(1, at_left())]) + self.frames(1.0, 2.2, [])
                        + self.frames(2.2, 3.0, [(2, at_left())]))
        self.assertEqual(res[-1].labels[2][1], 1, "same uid")
        self.assertEqual(mgr.total_entered, 1)
        self.assertEqual([e[0] for r in res for e in r.events], ["enter", "rejoin"])

    def test_b_edge_lost_1_8s_back_same_place_same_uid(self):
        """(ข) gone 1.8 s at the edge (exit after 1.5 s), back at the same place: recently_exited → same uid"""
        mgr = self.mgr()
        res = self.play(mgr, self.frames(0, 1.0, [(1, at_left())]) + self.frames(1.0, 2.8, [])
                        + self.frames(2.8, 3.5, [(2, at_left())]))
        kinds = [e[0] for r in res for e in r.events]
        self.assertEqual(kinds, ["enter", "exit", "rejoin"])
        self.assertEqual(res[-1].labels[2], (1, 1), "old uid, number 1")
        self.assertEqual(mgr.total_entered, 1, "a regrace rejoin is not a new entry")
        self.assertEqual(res[-1].in_frame, 1)

    def test_b2_recently_exited_not_in_frame(self):
        mgr = self.mgr()
        res = self.play(mgr, self.frames(0, 1.0, [(1, at_left())]) + self.frames(1.0, 2.7, []))
        self.assertEqual(res[-1].in_frame, 0, "exited people waiting for regrace do not count")

    def test_c_back_3s_after_exit_new_uid(self):
        """(ค) leaves through the left edge; comes back 3 s after the exit event → new uid"""
        mgr = self.mgr()
        res = self.play(mgr, self.frames(0, 1.0, [(1, at_left())]) + self.frames(1.0, 2.6, []))
        exit_t = [r for r in res if any(e[0] == "exit" for e in r.events)]
        self.assertEqual(len(exit_t), 1)
        t_exit = 1.0 + 1.5
        res = self.play(mgr, self.frames(2.6, t_exit + 3.0, []) + self.frames(t_exit + 3.0, t_exit + 3.5, [(2, at_left())]))
        self.assertEqual(res[-1].labels[2][1], 2, "new uid")
        self.assertEqual(mgr.total_entered, 2)

    def test_d_other_side_within_1s_new_uid(self):
        """(ง) A leaves through the left edge; someone enters at the right edge within 1 s → new uid (outside the gate)"""
        mgr = self.mgr()
        res = self.play(mgr, self.frames(0, 1.0, [(1, at_left())]) + self.frames(1.0, 2.6, [])
                        + self.frames(2.6, 3.2, [(2, at_right())]))
        self.assertEqual(res[-1].labels[2][1], 2, "new uid")
        self.assertEqual(mgr.total_entered, 2)

    def test_colors_unique_and_kept_after_renumber(self):
        mgr = self.mgr()
        r = mgr.update(0, [(1, box(300)), (2, box(600)), (3, box(900))])
        colors = dict((lab[1], lab.color_index) for lab in r.labels.values())
        self.assertEqual(len(set(colors.values())), 3, "3 people, 3 different colours")
        mgr.update(0.1, [(1, at_left()), (2, box(600)), (3, box(900))])
        r = mgr.update(2.0, [(2, box(600)), (3, box(900))])               # uid 1 left
        self.assertEqual(r.labels[2], (1, 2), "number moved up")
        self.assertEqual(r.labels[2].color_index, colors[2], "same colour after the number moved")
        self.assertEqual(r.labels[3].color_index, colors[3])
        r = mgr.update(2.1, [(2, box(600)), (3, box(900)), (4, box(400, cy=600))])
        cs = [lab.color_index for lab in r.labels.values()]
        self.assertEqual(len(set(cs)), 3, "a new person takes a colour nobody in the frame uses")

    def test_color_kept_on_rejoin(self):
        mgr = self.mgr()
        r = mgr.update(0, [(1, box(300)), (2, box(600))])
        c2 = r.labels[2].color_index
        mgr.update(1.0, [(1, box(300))])                                  # uid 2 hidden in the middle
        r = mgr.update(1.5, [(1, box(300)), (7, box(610))])               # comes back with a new tracker id
        self.assertEqual(r.labels[7][1], 2)
        self.assertEqual(r.labels[7].color_index, c2)

    def test_event_boxes(self):
        mgr = self.mgr()
        r = mgr.update(0, [(1, box(300))])
        self.assertEqual(r.event_boxes[1], box(300))


if __name__ == "__main__":
    unittest.main(verbosity=2)
