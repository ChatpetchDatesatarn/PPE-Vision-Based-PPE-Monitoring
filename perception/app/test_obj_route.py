"""Tests for obj_route.py. Run: python3 test_obj_route.py"""
import os
import unittest
from obj_route import Router, gie_unique_id, PERSON, HELMET, VEST

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.normpath(os.path.join(HERE, ".."))


class TTwoModels(unittest.TestCase):
    def setUp(self):
        self.r = Router(person_gie=1, ppe_gie=2)

    def test_coco_person(self):
        self.assertEqual(self.r.role(1, 0), PERSON)

    def test_same_class_id_different_model(self):
        # class 1 / 2 from COCO (bicycle / car) must not become helmet / vest
        self.assertIsNone(self.r.role(1, 1))
        self.assertIsNone(self.r.role(1, 2))
        self.assertEqual(self.r.role(2, 1), HELMET)
        self.assertEqual(self.r.role(2, 2), VEST)

    def test_ppe_person_not_used(self):
        # class 0 from ppe3 is a person too, but people come only from the COCO model
        self.assertIsNone(self.r.role(2, 0))

    def test_unknown_component(self):
        self.assertIsNone(self.r.role(3, 0))
        self.assertIsNone(self.r.role(0, 1))     # e.g. an object added by something else

    def test_same_gie_id_rejected(self):
        with self.assertRaises(ValueError):
            Router(person_gie=1, ppe_gie=1)


class TOneModel(unittest.TestCase):
    def test_ppe3_alone_as_before(self):
        r = Router(person_gie=1)
        self.assertEqual([r.role(1, c) for c in (0, 1, 2, 3)], [PERSON, HELMET, VEST, None])
        self.assertIsNone(r.role(2, 1))


class TConfigs(unittest.TestCase):
    def test_gie_ids_of_the_real_configs(self):
        self.assertEqual(gie_unique_id(os.path.join(DS, "test", "config_infer_cam_person.txt")), 1)
        self.assertEqual(gie_unique_id(os.path.join(DS, "models", "yolov8n_ppe3_416",
                                                    "config_infer_yolov8n_ppe3_hv.txt")), 2)
        self.assertEqual(gie_unique_id(os.path.join(DS, "models", "yolov8n_ppe3_416",
                                                    "config_infer_yolov8n_ppe3_416.txt")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
