"""
Test the whole system before CiRA CORE is ready: webcam -> YOLO (Ultralytics) -> PPE logic -> MQTT -> Dashboard
Runs on the PC/laptop (Python 3.8+)

Install:  pip install ultralytics paho-mqtt opencv-python
Usage:
    python pc_demo_detector.py --host <JETSON_TAILSCALE_IP> --model best.pt      # model trained on Colab (7 classes)
    python pc_demo_detector.py --host <JETSON_LAN_IP> --model yolov8n.pt  # standard model (detects person only)
    python pc_demo_detector.py --source rtsp://user:pass@ip/stream     # IP camera
Press q in the window to quit
"""
import argparse

import cv2
from ultralytics import YOLO

from ppe_logic import PPEMonitor
from safety_publisher import SafetyPublisher, draw

# Example restricted zone (normalized 0-1): lower-right corner of the frame — adjust to the real site
ZONES = {"zone-A": [(0.70, 0.55), (0.98, 0.55), (0.98, 0.98), (0.70, 0.98)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost", help="IP of the Jetson running mosquitto")
    ap.add_argument("--model", default="best.pt")
    ap.add_argument("--source", default="0", help="0 = webcam, or an RTSP URL / video file")
    ap.add_argument("--camera", default="cam01")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--no-window", action="store_true")
    args = ap.parse_args()

    model = YOLO(args.model)
    names = model.names
    monitor = PPEMonitor(camera_id=args.camera, zones=ZONES)
    pub = SafetyPublisher(host=args.host, camera_id=args.camera, frame_fps=5)

    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit("Cannot open camera/video: %s" % args.source)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        r = model.predict(frame, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
        dets = []
        for b in r.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            dets.append((names[int(b.cls)], float(b.conf), x1, y1, x2, y2))

        events = monitor.update(dets, w, h)
        vis = draw(frame, dets, monitor.labels(), ZONES)
        pub.publish_frame(vis)
        for ev in events:
            pub.publish_event(ev, vis)
            print("-> %s track %s" % (ev["type"], ev["track_id"]))

        if not args.no_window:
            cv2.imshow("PPE demo", vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
