"""Tests for status_mqtt.py. Run: python3 test_status_mqtt.py"""
import json
import re
import unittest

from status_mqtt import LWT_PAYLOAD, PPE_KEYS, build_status, iso07, make_client, ppe_breakdown, ppe_counts, status_topic

FIELDS = {"camera_id", "name", "ts", "online", "camera_connected", "fps_in", "fps_infer", "last_frame_age_s",
          "resolution", "model", "persons", "compliant", "violating", "stream_path"}


class TStatus(unittest.TestCase):
    def test_iso07_no_ms(self):
        # 2026-10-16 01:02:03.456 UTC
        self.assertEqual(iso07(1792112523.456), "2026-10-16T08:02:03+07:00")
        self.assertRegex(iso07(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+07:00$")

    def test_topic_and_lwt(self):
        self.assertEqual(status_topic("cam01"), "factory/safety/cam01/status")
        self.assertEqual(json.loads(LWT_PAYLOAD), {"online": False})

    def test_ppe_counts(self):
        states = [(True, True), (False, True), (True, None), (None, None), (False, False), (True, False)]
        self.assertEqual(ppe_counts(states), (1, 3))
        self.assertEqual(ppe_counts([]), (0, 0))

    def test_build_status(self):
        s = build_status("cam01", "CAM 01", True, True, 29.84, 14.92, 0.04, "1920x1080", "m", 3, 2, 1, "cam01",
                         epoch=1792112523)
        self.assertEqual(set(s), FIELDS)
        self.assertEqual((s["fps_in"], s["fps_infer"], s["last_frame_age_s"]), (29.8, 14.9, 0.0))
        self.assertEqual(s["ts"], "2026-10-16T08:02:03+07:00")
        self.assertEqual(json.loads(json.dumps(s)), s)

    def test_build_status_no_frame_yet(self):
        s = build_status("cam01", "CAM 01", True, False, 0, 0, None, None, "m", 0, 0, 0, "cam01")
        self.assertIsNone(s["last_frame_age_s"])
        self.assertFalse(s["camera_connected"])
        self.assertTrue(re.match(r".*\+07:00$", s["ts"]))

    def test_ppe_breakdown(self):
        states = [(True, True), (True, False), (False, True), (False, False), (True, None), (None, None), (True, True)]
        self.assertEqual(ppe_breakdown(states), {"ppe_both": 2, "ppe_helmet_only": 1, "ppe_vest_only": 1,
                                                 "ppe_none": 1, "ppe_unknown": 2})
        self.assertEqual(sum(ppe_breakdown(states).values()), len(states))
        self.assertEqual(set(ppe_breakdown([])), set(PPE_KEYS))

    def test_build_status_with_ppe(self):
        s = build_status("cam01", "CAM 01", True, True, 29.8, 14.9, 0.0, "1920x1080", "m", 2, 1, 1, "cam01",
                         ppe=ppe_breakdown([(True, True), (False, True)]))
        self.assertEqual(set(s), FIELDS | set(PPE_KEYS))
        self.assertEqual((s["ppe_both"], s["ppe_vest_only"]), (1, 1))

    def test_make_client(self):
        try:
            import paho.mqtt.client  # noqa: F401
        except ImportError:
            self.skipTest("paho-mqtt not installed")
        c = make_client("t-status", "cam01")
        self.assertIsNotNone(c)


if __name__ == "__main__":
    unittest.main()
