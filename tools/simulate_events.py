"""
Simulate CiRA CORE: send real-time frames + events with snapshots to test the Dashboard before the real model is ready

Install:  pip install paho-mqtt pillow
Usage:
    python simulate_events.py --host <JETSON_TAILSCALE_IP>            # frames 5 fps + random event every 8 s
    python simulate_events.py --host <JETSON_LAN_IP> --once no_helmet
    python simulate_events.py --no-frames                     # events only
If Pillow is missing, sends events without images and no frames
"""
import argparse
import base64
import io
import json
import random
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None

TYPES = ["no_helmet", "no_vest", "restricted_zone", "unknown_visibility"]
WEIGHTS = [4, 3, 2, 1]
BKK = timezone(timedelta(hours=7))
W, H = 640, 360


def render(t, label=None):
    """Draw a synthetic image: person walking + restricted zone"""
    if Image is None:
        return None
    im = Image.new("RGB", (W, H), (38, 46, 58))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 250, W, H], fill=(66, 66, 76))
    d.rectangle([450, 210, 630, 350], outline=(255, 40, 40), width=2)
    d.text((455, 214), "RESTRICTED zone-A", fill=(255, 80, 80))
    x = int(60 + (t * 40) % 420)
    bad = label is not None
    c = (255, 60, 60) if bad else (60, 220, 90)
    d.rectangle([x, 90, x + 80, 330], outline=c, width=3)
    d.text((x + 2, 76), "#7 " + (label.upper() if bad else "OK"), fill=c)
    if label != "no_helmet":
        d.rectangle([x + 18, 92, x + 62, 128], outline=(255, 200, 0), width=2)
    if label != "no_vest":
        d.rectangle([x + 8, 150, x + 72, 250], outline=(0, 255, 120), width=2)
    d.text((8, 8), datetime.now(BKK).strftime("cam01  %H:%M:%S") + "  (SIMULATED)", fill=(220, 220, 220))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return buf.getvalue()


def make_event(camera, etype, seq, snap):
    now = datetime.now(BKK)
    ev = {
        "event_id": "%s-%s-%03d" % (camera, now.strftime("%Y%m%d-%H%M%S"), seq),
        "ts": now.isoformat(timespec="seconds"),
        "camera_id": camera,
        "zone_id": "zone-A" if etype == "restricted_zone" else "line-1",
        "type": etype,
        "track_id": 7,
        "confidence": round(random.uniform(0.6, 0.97), 2),
    }
    if snap:
        ev["snapshot_b64"] = base64.b64encode(snap).decode("ascii")
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--camera", default="cam01")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--event-every", type=float, default=8.0, help="seconds between random events")
    ap.add_argument("--no-frames", action="store_true")
    ap.add_argument("--once", choices=TYPES, help="send a single event of this type and exit")
    args = ap.parse_args()
    if Image is None:
        print("! Pillow not installed — sending events without images (pip install pillow)")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sim-%d" % random.randint(0, 9999))
    except AttributeError:
        client = mqtt.Client(client_id="sim-%d" % random.randint(0, 9999))
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()
    t_frame = "factory/safety/%s/frame" % args.camera
    t_event = "factory/safety/%s/event" % args.camera

    seq = 0
    if args.once:
        ev = make_event(args.camera, args.once, 1, render(0, args.once))
        client.publish(t_event, json.dumps(ev), qos=1).wait_for_publish()
        print("-> %s (%s)" % (args.once, ev["event_id"]))
        client.loop_stop()
        client.disconnect()
        return

    t0 = time.time()
    next_event = t0 + 3
    label, label_until = None, 0
    try:
        while True:
            now = time.time()
            if now >= next_event:
                seq += 1
                etype = random.choices(TYPES, WEIGHTS)[0]
                label, label_until = etype, now + 3
                ev = make_event(args.camera, etype, seq, render(now - t0, etype))
                client.publish(t_event, json.dumps(ev), qos=1)
                print("-> event %s (%s)" % (etype, ev["event_id"]))
                next_event = now + args.event_every
            if now > label_until:
                label = None
            if not args.no_frames and Image is not None:
                client.publish(t_frame, render(now - t0, label), qos=0)
                time.sleep(1.0 / args.fps)
            else:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
