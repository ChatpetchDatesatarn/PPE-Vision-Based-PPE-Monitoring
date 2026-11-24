"""
Send real-time frames + events (with snapshot) to the Dashboard via MQTT per docs/mqtt_spec.md
Used in CiRA CORE's Python node — requires paho-mqtt, opencv-python (cv2), numpy
Supports Python 3.6+ and paho-mqtt 1.x / 2.x

Example:
    pub = SafetyPublisher(host="localhost", camera_id="cam01")
    ...in the per-frame loop...
    vis = draw(frame, detections, monitor.labels(), zones)    # image with boxes drawn
    pub.publish_frame(vis)                                    # throttled to fps automatically
    for ev in monitor.update(detections, w, h):
        pub.publish_event(ev, vis)                            # attaches snapshot automatically
"""
import base64
import json
import threading
import time

import cv2
import paho.mqtt.client as mqtt

COLORS = {"person": (200, 200, 200), "helmet": (0, 200, 255), "vest": (0, 255, 120),
          "gloves": (255, 180, 0), "goggles": (255, 80, 200), "shoes": (180, 120, 60), "mask": (255, 255, 255)}


class SafetyPublisher(object):
    def __init__(self, host="localhost", port=1883, camera_id="cam01",
                 frame_fps=5.0, frame_width=640, frame_quality=70,
                 snap_width=640, snap_quality=80):
        self.cam = camera_id
        self.t_frame = "factory/safety/%s/frame" % camera_id
        self.t_event = "factory/safety/%s/event" % camera_id
        self.t_status = "factory/safety/%s/status" % camera_id
        self.min_dt = 1.0 / frame_fps if frame_fps > 0 else 0
        self.frame_width, self.frame_quality = frame_width, frame_quality
        self.snap_width, self.snap_quality = snap_width, snap_quality
        self._last_frame = 0.0
        self._frames = 0
        self._t0 = time.time()
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="cira-%s" % camera_id)
        except AttributeError:
            self.client = mqtt.Client(client_id="cira-%s" % camera_id)
        self.client.will_set(self.t_status, json.dumps({"camera_id": camera_id, "online": False}), 1, True)
        self.client.reconnect_delay_set(1, 10)
        self.client.connect_async(host, port, 30)
        self.client.loop_start()
        self._hb = threading.Thread(target=self._heartbeat, daemon=True)
        self._hb.start()

    @staticmethod
    def _jpeg(bgr, width, quality):
        h, w = bgr.shape[:2]
        if w > width:
            bgr = cv2.resize(bgr, (width, int(h * width / float(w))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return buf.tobytes() if ok else None

    def publish_frame(self, bgr):
        """Send real-time frame (JPEG bytes) — throttled to frame_fps; frames in between are skipped"""
        now = time.time()
        self._frames += 1
        if now - self._last_frame < self.min_dt:
            return False
        self._last_frame = now
        data = self._jpeg(bgr, self.frame_width, self.frame_quality)
        if data:
            self.client.publish(self.t_frame, data, qos=0, retain=False)
        return True

    def publish_event(self, event, bgr=None):
        """Send event; if an image is given, attach snapshot_b64"""
        ev = dict(event)
        if bgr is not None:
            data = self._jpeg(bgr, self.snap_width, self.snap_quality)
            if data:
                ev["snapshot_b64"] = base64.b64encode(data).decode("ascii")
        self.client.publish(self.t_event, json.dumps(ev), qos=1)

    def _heartbeat(self):
        while True:
            time.sleep(10)
            dt = time.time() - self._t0
            fps = self._frames / dt if dt > 0 else 0
            self._frames, self._t0 = 0, time.time()
            self.client.publish(self.t_status, json.dumps(
                {"camera_id": self.cam, "online": True, "fps": round(fps, 1)}), qos=1, retain=True)


def draw(bgr, detections, person_labels=None, zones=None):
    """Draw boxes on a copy of the image
    detections: [(name, conf, x1, y1, x2, y2)], person_labels: from PPEMonitor.labels(), zones: normalized polygons"""
    import numpy as np
    out = bgr.copy()
    h, w = out.shape[:2]
    for zid, pts in (zones or {}).items():
        poly = np.array([[int(x * w), int(y * h)] for x, y in pts], np.int32)
        overlay = out.copy()
        cv2.fillPoly(overlay, [poly], (0, 0, 180))
        out = cv2.addWeighted(overlay, 0.25, out, 0.75, 0)
        cv2.polylines(out, [poly], True, (0, 0, 255), 2)
        cv2.putText(out, zid, tuple(poly[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    for name, conf, x1, y1, x2, y2 in detections:
        if name == "person":
            continue
        c = COLORS.get(name, (255, 255, 255))
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), c, 2)
        cv2.putText(out, "%s %.2f" % (name, conf), (int(x1) + 3, int(y1) + 13),   # inside the box
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1)
    for box, text, bad in (person_labels or {}).values():
        c = (0, 0, 255) if bad else (0, 170, 0)
        x1, y1, x2, y2 = [int(v) for v in box]
        cv2.rectangle(out, (x1, y1), (x2, y2), c, 2)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        ty = y1 - 8 if y1 - th - 10 > 0 else y2 + th + 8                # above the box, or below if no room
        cv2.rectangle(out, (x1, ty - th - 4), (x1 + tw + 6, ty + 4), c, -1)
        cv2.putText(out, text, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    return out
