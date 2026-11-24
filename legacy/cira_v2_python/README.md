# legacy/cira_v2_python — connecting CiRA CORE to the Dashboard

```
Camera → CiRA CORE (detect: helmet, vest, gloves, goggles, shoes, mask, person)
        → ppe_logic.PPEMonitor     pair PPE with person, check zones, count persistence → events
        → safety_publisher         send real-time frame + event with snapshot via MQTT
        → mosquitto (Docker) → recorder (stores history) + Dashboard http://<Jetson>:8080
```

| File | Purpose |
|---|---|
| `ppe_logic.py` | Decision logic (no_helmet / no_vest / restricted_zone / unknown_visibility); standard library only, Python 3.6+ |
| `safety_publisher.py` | Send frames (JPEG 5 fps) and events (+ snapshot) via MQTT, plus `draw()` for drawing boxes |
| `pc_demo_detector.py` | Test the whole pipeline on the PC with a webcam + YOLO before CiRA is ready |

## Using it in CiRA CORE (Python node)
Requires `paho-mqtt` and `opencv` in the Python that CiRA uses. In the node's code:

```python
import sys; sys.path.append("/home/jetson/safety/legacy/cira_v2_python")
from ppe_logic import PPEMonitor
from safety_publisher import SafetyPublisher, draw

ZONES = {"zone-A": [(0.70, 0.55), (0.98, 0.55), (0.98, 0.98), (0.70, 0.98)]}  # normalized 0-1
monitor = PPEMonitor(camera_id="cam01", zones=ZONES)          # create once
pub = SafetyPublisher(host="localhost", camera_id="cam01")      # mosquitto on the same machine

# --- per frame ---
# frame = BGR image from the camera, dets = [(name, conf, x1, y1, x2, y2), ...] from the detection node
events = monitor.update(dets, frame.shape[1], frame.shape[0])
vis = draw(frame, dets, monitor.labels(), ZONES)
pub.publish_frame(vis)
for ev in events:
    pub.publish_event(ev, vis)
```

> The data format CiRA passes between nodes (image + detection results) must be checked after installation;
> all that is needed is to convert it to `dets` in the format above — the rest needs no changes

## Main tunable values (`PPEMonitor`)
| Value | Default | Meaning |
|---|---|---|
| `hold_s` | 2.0 | missing PPE for this many seconds before an event is fired |
| `zone_hold_s` | 0.5 | inside the restricted zone for this many seconds before an event is fired |
| `cooldown_s` | 30 | same person + same type is not fired again within this many seconds |
| `min_person_h` | 0.12 | person shorter than 12% of the frame -> "cannot be checked" |
| `require` | helmet, vest | PPE that must be worn (add "mask", "gloves" etc. as needed) |
