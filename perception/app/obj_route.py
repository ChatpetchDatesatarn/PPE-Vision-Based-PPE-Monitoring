"""Which role a DeepStream object has, from the model that made it (pure Python, 3.6-compatible).

Two models ("way A"): nvinfer #1 = COCO person only, nvinfer #2 = ppe3 helmet / vest. Both number their classes
from 0 (COCO 0 = person, ppe3 0 = person / 1 = helmet / 2 = vest), so class_id alone is not enough: the object's
unique_component_id (= gie-unique-id of the nvinfer that made it) says which model it came from.
One model (no --ppe-config): the ppe3 model alone gives person / helmet / vest, as before.
"""
import configparser
import io

PERSON, HELMET, VEST = "person", "helmet", "vest"
ROLES = (PERSON, HELMET, VEST)

# class ids inside each model
COCO_PERSON = 0
PPE_PERSON, PPE_HELMET, PPE_VEST = 0, 1, 2


class Router(object):
    def __init__(self, person_gie, ppe_gie=None):
        """person_gie: gie-unique-id of the person model; ppe_gie: of the helmet / vest model, None = one model."""
        if ppe_gie is not None and ppe_gie == person_gie:
            raise ValueError("person and PPE models need different gie-unique-id (both %d)" % person_gie)
        self.person_gie = person_gie
        self.ppe_gie = ppe_gie

    def role(self, component_id, class_id):
        """PERSON / HELMET / VEST, or None for an object the app does not use."""
        if self.ppe_gie is None:                       # one model: ppe3 gives all three
            if component_id != self.person_gie:
                return None
            return {PPE_PERSON: PERSON, PPE_HELMET: HELMET, PPE_VEST: VEST}.get(class_id)
        if component_id == self.person_gie:
            return PERSON if class_id == COCO_PERSON else None
        if component_id == self.ppe_gie:
            return {PPE_HELMET: HELMET, PPE_VEST: VEST}.get(class_id)    # ppe3 person is not used
        return None


def gie_unique_id(config_path):
    """gie-unique-id from an nvinfer config file ([property]); nvinfer's default is 1 when the key is missing."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    with io.open(config_path, encoding="utf-8") as f:
        cp.read_file(f)
    return cp.getint("property", "gie-unique-id", fallback=1)
