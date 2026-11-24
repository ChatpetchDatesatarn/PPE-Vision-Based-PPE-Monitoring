#!/usr/bin/env python3
"""
Jetson Nano Alert Controller
Subscribe to events from CiRA CORE via MQTT (same topics as ESP32, see docs/mqtt_spec.md)
and drive the warning light / buzzer / relay directly from the Jetson's 40-pin header.

Works with Python 3.6 (JetPack 4.x) and paho-mqtt 1.x or 2.x

Install on Jetson:
    sudo apt install mosquitto mosquitto-clients python3-pip
    sudo pip3 install Jetson.GPIO paho-mqtt
    sudo groupadd -f -r gpio && sudo usermod -a -G gpio $USER   # then log out/in

Run:
    python3 jetson_alert.py --host localhost

Wiring (BOARD pin numbering on the 40-pin header):
    pin 31 -> warning light  (via relay module / MOSFET)
    pin 33 -> buzzer         (via NPN transistor)
    pin 35 -> relay          (extra signaling only)
    pin 37 <- ack button to GND + external 10k pull-up resistor to 3.3V (pin 1)
    The Jetson GPIO is 3.3V and supplies only a few mA: never drive a lamp/buzzer/relay coil directly
NOTE: the relay is for signaling only; do not use it to stop machines or as part of an E-Stop
"""
import argparse
import json
import signal
import time

import paho.mqtt.client as mqtt

try:
    import Jetson.GPIO as GPIO
except ImportError:  # allow testing on a PC
    GPIO = None

PIN_LIGHT, PIN_BUZZER, PIN_RELAY, PIN_BTN = 31, 33, 35, 37
RELAY_ACTIVE_LOW = True
HOLD = {"warning": 5.0, "danger": 10.0}
LEVEL_OF = {"no_helmet": "warning", "no_vest": "warning", "restricted_zone": "danger"}
RANK = {"idle": 0, "warning": 1, "danger": 2}


class Alarm:
    def __init__(self):
        self.level = "idle"
        self.until = 0.0
        self.muted = False
        self.last_event_id = ""

    def raise_level(self, level, hold):
        if RANK[level] > RANK[self.level]:
            self.muted = False
        if RANK[level] >= RANK[self.level]:
            self.level = level
        self.until = max(self.until, time.time() + hold)

    def clear(self):
        self.level, self.until, self.muted = "idle", 0.0, False


class Controller:
    def __init__(self, args):
        self.args = args
        self.alarm = Alarm()
        self.connected = False
        self.last_ok = time.time()
        self.t_event = "factory/safety/%s/event" % args.camera
        self.t_cmd = "factory/safety/%s/cmd" % args.device
        self.t_status = "factory/safety/%s/status" % args.device
        self.started = time.time()
        self.btn_prev = 1

        if GPIO:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup([PIN_LIGHT, PIN_BUZZER], GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(PIN_RELAY, GPIO.OUT, initial=GPIO.HIGH if RELAY_ACTIVE_LOW else GPIO.LOW)
            GPIO.setup(PIN_BTN, GPIO.IN)

        try:  # paho-mqtt 2.x
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=args.device)
        except AttributeError:  # paho-mqtt 1.x
            self.client = mqtt.Client(client_id=args.device)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.will_set(self.t_status, json.dumps({"device_id": args.device, "online": False}), 1, True)
        self.client.reconnect_delay_set(1, 10)

    # ---------- MQTT ----------
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe([(self.t_event, 1), (self.t_cmd, 1)])
            self.publish_status()
            print("[mqtt] connected")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print("[mqtt] disconnected rc=%s" % rc)

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except ValueError:
            return
        if msg.topic == self.t_event:
            etype = data.get("type", "")
            self.alarm.last_event_id = data.get("event_id", "")
            level = LEVEL_OF.get(etype)
            if level:  # unknown_visibility -> Dashboard only
                self.alarm.raise_level(level, HOLD[level])
                self.publish_status()
            print("[event] %s -> %s" % (etype, self.alarm.level))
        elif msg.topic == self.t_cmd:
            action = data.get("action")
            if action == "silence":
                self.alarm.muted = True
            elif action == "clear":
                self.alarm.clear()
            elif action == "test":
                self.alarm.raise_level("danger", 3.0)
            self.publish_status()
            print("[cmd] %s" % action)

    def publish_status(self):
        if not self.connected:
            return
        self.client.publish(self.t_status, json.dumps({
            "device_id": self.args.device, "online": True, "state": self.alarm.level,
            "muted": self.alarm.muted, "uptime_s": int(time.time() - self.started),
        }), 1, True)

    # ---------- GPIO ----------
    def write(self, light, buzzer, relay):
        if not GPIO:
            return
        GPIO.output(PIN_LIGHT, GPIO.HIGH if light else GPIO.LOW)
        GPIO.output(PIN_BUZZER, GPIO.HIGH if (buzzer and not self.alarm.muted) else GPIO.LOW)
        GPIO.output(PIN_RELAY, GPIO.HIGH if (relay != RELAY_ACTIVE_LOW) else GPIO.LOW)

    def poll_button(self):
        if not GPIO:
            return
        v = GPIO.input(PIN_BTN)
        if self.btn_prev == 1 and v == 0 and self.alarm.level != "idle":
            self.alarm.muted = True
            if self.connected and self.alarm.last_event_id:
                self.client.publish("factory/safety/ack", json.dumps({
                    "event_id": self.alarm.last_event_id, "status": "resolved",
                    "by": "button", "device_id": self.args.device}), 1)
            self.publish_status()
            print("[btn] ack -> buzzer muted")
        self.btn_prev = v

    def drive(self):
        now = time.time()
        a = self.alarm
        if a.level != "idle" and now >= a.until:
            a.clear()
            self.publish_status()
        if self.connected:
            self.last_ok = now
        ms = int(now * 1000)
        if a.level == "danger":
            self.write(True, (ms // 200) % 2 == 0, True)
        elif a.level == "warning":
            self.write((ms // 500) % 2 == 0, (ms % 1000) < 100, False)
        else:
            offline = now - self.last_ok > 30
            self.write(offline and (ms % 3000) < 80, False, False)

    # ---------- Main ----------
    def run(self):
        self.client.connect_async(self.args.host, self.args.port, 30)
        self.client.loop_start()
        last_hb = 0.0
        running = [True]
        signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
        try:
            while running[0]:
                self.poll_button()
                self.drive()
                if time.time() - last_hb > 10:
                    last_hb = time.time()
                    self.publish_status()
                time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        finally:
            self.write(False, False, False)
            self.client.loop_stop()
            if GPIO:
                GPIO.cleanup()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--camera", default="cam01")
    ap.add_argument("--device", default="jetson-alert-01")
    Controller(ap.parse_args()).run()
