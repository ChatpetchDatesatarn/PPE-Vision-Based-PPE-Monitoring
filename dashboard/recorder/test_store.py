"""Unit tests for store.py (standard library only): python3 -m unittest test_store.py"""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta

from store import BKK, Store

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def event(i, etype="no_helmet", day="2026-10-15", **kw):
    ev = {"event_id": "cam01-%s-%03d" % (day.replace("-", ""), i), "ts": "%sT10:%02d:00+07:00" % (day, i % 60),
          "camera_id": "cam01", "zone_id": "line-1", "type": etype, "track_id": i, "confidence": 0.8,
          "bbox": [0.1, 0.2, 0.3, 0.4], "snapshot_id": "snap-%03d" % i, "via": "cira"}
    ev.update(kw)
    return ev


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = Store(self.dir, max_snapshots=3, orphan_grace_s=600)

    def test_event_roundtrip_and_default_severity(self):
        self.assertTrue(self.s.add_event(json.dumps(event(1)).encode()))
        ev = self.s.get_event("cam01-20261015-001")
        self.assertEqual(ev["severity"], "high")          # default for no_helmet
        self.assertEqual(ev["bbox"], [0.1, 0.2, 0.3, 0.4])
        self.assertIsNone(ev["snapshot_url"])             # no file yet
        self.assertTrue(self.s.save_snapshot("snap-001", JPEG))
        self.assertEqual(self.s.get_event("cam01-20261015-001")["snapshot_url"], "/data/snapshots/snap-001.jpg")

    def test_rejects_bad_input(self):
        self.assertIsNone(self.s.add_event(b"not json"))
        self.assertIsNone(self.s.add_event(json.dumps(event(1, etype="no_gloves"))))
        self.assertIsNone(self.s.add_event(json.dumps(event(1, event_id="../../etc/passwd"))))
        self.assertFalse(self.s.save_snapshot("../x", JPEG))
        self.assertFalse(self.s.save_snapshot("ok", b"PNG..."))
        self.assertFalse(self.s.apply_ack(json.dumps({"event_id": "x", "status": "maybe"})))

    def test_duplicate_event_ignored(self):
        self.s.add_event(event(1))
        with self.assertLogs("recorder", level="WARNING") as cm:
            self.s.add_event(event(1, severity="critical"))
        self.assertIn("duplicate event_id cam01-20261015-001", cm.output[0])
        self.assertEqual(self.s.query_events()["total"], 1)
        self.assertEqual(self.s.get_event("cam01-20261015-001")["severity"], "high")

    def test_two_types_same_person_same_second_both_kept(self):
        # event_id = <cam>-YYYYMMDD-HHMMSS-<uid>-<type code> (mqtt_spec v3 section 2)
        sid = "cam01-20261016-010109-001"
        self.s.add_event(event(1, event_id=sid + "-nh", snapshot_id=sid))
        self.s.add_event(event(1, etype="no_vest", event_id=sid + "-nv", snapshot_id=sid))
        items = self.s.query_events()["items"]
        self.assertEqual(sorted((e["event_id"], e["type"]) for e in items),
                         [(sid + "-nh", "no_helmet"), (sid + "-nv", "no_vest")])

    def test_filters_paging_and_ack(self):
        for i in range(1, 6):
            self.s.add_event(event(i, etype="no_vest" if i % 2 else "no_helmet"))
        self.s.add_event(event(7, day="2026-10-14"))
        r = self.s.query_events(type="no_vest")
        self.assertEqual(r["total"], 3)
        r = self.s.query_events(date_from="2026-10-15", date_to="2026-10-15", limit=2)
        self.assertEqual((r["total"], len(r["items"])), (5, 2))
        self.assertGreaterEqual(r["items"][0]["ts"], r["items"][1]["ts"])  # newest first
        self.assertTrue(self.s.apply_ack({"event_id": "cam01-20261015-002", "status": "false_alarm", "by": "t"}))
        self.assertTrue(self.s.apply_ack({"event_id": "cam01-20261015-004", "status": "resolved"}))
        summ = self.s.summary("2026-10-15")
        self.assertEqual(summ["total"], 5)
        self.assertEqual(summ["yesterday"], 1)
        self.assertEqual(summ["by_type"]["no_vest"], 3)
        self.assertEqual(summ["false_alarm_rate"], 0.5)
        self.assertEqual(summ["open"], 4)
        with self.assertRaises(ValueError):
            self.s.query_events(date_from="15/10/2026")

    def test_daily_and_csv(self):
        today = datetime.now(BKK).strftime("%Y-%m-%d")
        self.s.add_event(event(1, day=today))
        self.s.add_event(event(2, etype="restricted_zone", day=today))
        d = self.s.daily(7)
        self.assertEqual(len(d), 7)
        self.assertEqual(d[-1], {"date": today, "no_helmet": 1, "no_vest": 0, "restricted_zone": 1,
                                 "unknown_visibility": 0})
        csv_text = self.s.export_csv()
        self.assertTrue(csv_text.startswith("﻿event_id"))
        self.assertEqual(len(csv_text.strip().splitlines()), 3)

    def test_cleanup_orphans_age_and_limit(self):
        now = time.time()
        for i in range(1, 6):
            self.s.add_event(event(i))
            self.s.save_snapshot("snap-%03d" % i, JPEG)
            os.utime(self.s.snapshot_path("snap-%03d" % i), (now - 100 * (6 - i),) * 2)
        self.s.save_snapshot("orphan-new", JPEG)
        self.s.save_snapshot("orphan-old", JPEG)
        os.utime(self.s.snapshot_path("orphan-old"), (now - 3600,) * 2)
        removed = self.s.cleanup(now=now)
        self.assertEqual(removed["orphan"], 1)
        self.assertEqual(removed["over_limit"], 3)        # 6 kept candidates -> max 3
        left = sorted(os.listdir(os.path.join(self.dir, "snapshots")))
        self.assertEqual(left, ["orphan-new.jpg", "snap-004.jpg", "snap-005.jpg"])
        self.assertEqual(self.s.counts()["events"], 5)    # event rows are kept

    def test_migrate_v2_events_json(self):
        old = [dict(event(1), snapshot="data/snapshots/cam01-20261015-001.jpg", status="resolved"),
               {"event_id": "bad id!", "type": "no_helmet"}]
        for ev in old:
            ev.pop("snapshot_id", None)
        path = os.path.join(self.dir, "events.json")
        with open(path, "w") as f:
            json.dump(old, f)
        self.assertEqual(self.s.migrate_events_json(path), 1)
        ev = self.s.get_event("cam01-20261015-001")
        self.assertEqual((ev["snapshot_id"], ev["status"]), ("cam01-20261015-001", "resolved"))
        self.assertTrue(os.path.exists(path + ".migrated"))
        self.assertEqual(self.s.migrate_events_json(path), 0)


class DeleteTest(unittest.TestCase):
    """v6: delete by id / by date range; shared snapshots survive while another event still uses them."""
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.s = Store(self.dir, max_snapshots=100)
        for i in (1, 2, 3):
            self.s.add_event(json.dumps(event(i)))
            self.s.save_snapshot("snap-%03d" % i, JPEG)
        # nh + nv pair sharing snap-001 (as DeepStream does for one person)
        self.s.add_event(json.dumps(event(1, etype="no_vest", event_id="cam01-20261015-001-nv")))
        self.s.add_event(json.dumps(event(9, day="2026-10-20")))
        self.s.save_snapshot("snap-009", JPEG)

    def exists(self, sid):
        return os.path.exists(self.s.snapshot_path(sid))

    def test_delete_one_keeps_shared_snapshot(self):
        r = self.s.delete_events(["cam01-20261015-001"])
        self.assertEqual(r, {"events": 1, "snapshots": 0})
        self.assertTrue(self.exists("snap-001"))            # still used by the -nv event
        r = self.s.delete_events(["cam01-20261015-001-nv"])
        self.assertEqual(r, {"events": 1, "snapshots": 1})
        self.assertFalse(self.exists("snap-001"))

    def test_delete_many_and_bad_ids(self):
        r = self.s.delete_events(["cam01-20261015-002", "cam01-20261015-003", "../etc/passwd", "nope"])
        self.assertEqual(r, {"events": 2, "snapshots": 2})
        with self.assertRaises(ValueError):
            self.s.delete_events(["../x"])
        with self.assertRaises(ValueError):
            self.s.delete_events("cam01-20261015-002")

    def test_delete_range(self):
        r = self.s.delete_range("2026-10-15", "2026-10-15")
        self.assertEqual(r["events"], 4)
        self.assertEqual(self.s.query_events()["total"], 1)  # 2026-10-20 kept
        self.assertTrue(self.exists("snap-009"))
        with self.assertRaises(ValueError):
            self.s.delete_range("2026-10-15", None)
        with self.assertRaises(ValueError):
            self.s.delete_range("2026-10-20", "2026-10-15")

if __name__ == "__main__":
    unittest.main()
