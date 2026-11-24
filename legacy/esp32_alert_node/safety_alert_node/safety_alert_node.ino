/*
 * Safety Alert Node — ESP32 (Arduino core)
 * Subscribes to AI events from CiRA CORE via MQTT and drives the warning light / buzzer / relay
 * See the topic + payload specification in docs/mqtt_spec.md
 *
 * Libraries (Arduino Library Manager):
 *   - PubSubClient  (Nick O'Leary)
 *   - ArduinoJson   (Benoit Blanchon) v7
 *
 * Wiring (change as needed):
 *   GPIO26 -> Warning light (via MOSFET/relay module, do not drive a 12V/24V lamp directly)
 *   GPIO25 -> Active buzzer (via transistor)
 *   GPIO27 -> Relay module (extra signaling only, e.g. tower light)
 *   GPIO33 -> Ack button to GND (uses INPUT_PULLUP)
 *
 * NOTE: The relay in this project is for signaling only. Do not use it to stop machines
 *       or as part of a safety function. The Emergency Stop system must remain separate.
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---------- Config ----------
const char* WIFI_SSID     = "YOUR_WIFI";
const char* WIFI_PASS     = "YOUR_PASSWORD";
const char* MQTT_HOST     = "<LAN_IP>";   // IP of the machine running Mosquitto
const uint16_t MQTT_PORT  = 1883;
const char* DEVICE_ID     = "alert-node-01";
const char* CAMERA_ID     = "cam01";

const int PIN_LIGHT   = 26;
const int PIN_BUZZER  = 25;
const int PIN_RELAY   = 27;
const int PIN_ACK_BTN = 33;
const bool RELAY_ACTIVE_LOW = true;            // most relay modules are active-low

const uint32_t HOLD_WARNING_MS = 5000;         // keep alarm on after the last event
const uint32_t HOLD_DANGER_MS  = 10000;
const uint32_t HEARTBEAT_MS    = 10000;
const uint32_t OFFLINE_WARN_MS = 30000;        // if MQTT is down this long, show offline pattern

// ---------- State ----------
enum Level { LV_IDLE = 0, LV_WARNING = 1, LV_DANGER = 2 };
Level level = LV_IDLE;
uint32_t alertUntil = 0;
bool muted = false;
String lastEventId = "";

WiFiClient net;
PubSubClient mqtt(net);
String tEvent, tCmd, tStatus;
const char* T_ACK = "factory/safety/ack";

uint32_t lastHeartbeat = 0;
uint32_t lastMqttOk = 0;
uint32_t lastReconnectTry = 0;

// ---------- Outputs ----------
void setRelay(bool on) {
  digitalWrite(PIN_RELAY, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

void outputs(bool light, bool buzzer, bool relay) {
  digitalWrite(PIN_LIGHT, light ? HIGH : LOW);
  digitalWrite(PIN_BUZZER, (buzzer && !muted) ? HIGH : LOW);
  setRelay(relay);
}

const char* levelName(Level l) {
  return l == LV_DANGER ? "danger" : l == LV_WARNING ? "warning" : "idle";
}

// ---------- MQTT publish helpers ----------
void publishStatus() {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["online"]    = true;
  doc["state"]     = levelName(level);
  doc["muted"]     = muted;
  doc["rssi"]      = WiFi.RSSI();
  doc["uptime_s"]  = millis() / 1000;
  char buf[200];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(tStatus.c_str(), (const uint8_t*)buf, n, true);
}

void publishAck(const String& eventId) {
  JsonDocument doc;
  doc["event_id"] = eventId;
  doc["status"]   = "resolved";
  doc["by"]       = "button";
  doc["device_id"] = DEVICE_ID;
  char buf[200];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(T_ACK, (const uint8_t*)buf, n, false);
}

// ---------- Alarm logic ----------
void raise(Level l, uint32_t holdMs) {
  uint32_t now = millis();
  if (l > level) muted = false;          // higher severity re-enables buzzer
  if (l >= level) level = l;
  uint32_t until = now + holdMs;
  if ((int32_t)(until - alertUntil) > 0) alertUntil = until;
  publishStatus();
}

void clearAlarm() {
  level = LV_IDLE;
  muted = false;
  alertUntil = 0;
  publishStatus();
}

void handleEvent(JsonDocument& doc) {
  const char* type = doc["type"] | "";
  lastEventId = String((const char*)(doc["event_id"] | ""));

  if (!strcmp(type, "restricted_zone")) {
    raise(LV_DANGER, HOLD_DANGER_MS);
  } else if (!strcmp(type, "no_helmet") || !strcmp(type, "no_vest")) {
    raise(LV_WARNING, HOLD_WARNING_MS);
  }
  // unknown_visibility / others: no on-site alarm
  Serial.printf("[event] %s id=%s -> %s\n", type, lastEventId.c_str(), levelName(level));
}

void handleCmd(JsonDocument& doc) {
  const char* action = doc["action"] | "";
  Serial.printf("[cmd] %s\n", action);
  if (!strcmp(action, "silence")) { muted = true; publishStatus(); }
  else if (!strcmp(action, "clear")) clearAlarm();
  else if (!strcmp(action, "test")) raise(LV_DANGER, 3000);
}

void onMessage(char* topic, byte* payload, unsigned int len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("[mqtt] bad JSON, ignored");
    return;
  }
  String t(topic);
  if (t == tEvent) handleEvent(doc);
  else if (t == tCmd) handleCmd(doc);
}

// ---------- Connectivity (non-blocking) ----------
void ensureWifi() {
  static uint32_t lastTry = 0;
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastTry < 5000) return;
  lastTry = millis();
  Serial.println("[wifi] connecting...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void ensureMqtt() {
  if (mqtt.connected()) { lastMqttOk = millis(); return; }
  if (WiFi.status() != WL_CONNECTED) return;
  if (millis() - lastReconnectTry < 3000) return;
  lastReconnectTry = millis();

  char lwt[80];
  snprintf(lwt, sizeof(lwt), "{\"device_id\":\"%s\",\"online\":false}", DEVICE_ID);
  Serial.println("[mqtt] connecting...");
  if (mqtt.connect(DEVICE_ID, nullptr, nullptr, tStatus.c_str(), 1, true, lwt)) {
    mqtt.subscribe(tEvent.c_str(), 1);
    mqtt.subscribe(tCmd.c_str(), 1);
    publishStatus();
    lastMqttOk = millis();
    Serial.println("[mqtt] connected");
  }
}

// ---------- Ack button (debounced) ----------
void pollButton() {
  static bool lastStable = HIGH, lastRead = HIGH;
  static uint32_t changedAt = 0;
  bool r = digitalRead(PIN_ACK_BTN);
  if (r != lastRead) { lastRead = r; changedAt = millis(); }
  if (millis() - changedAt > 30 && r != lastStable) {
    lastStable = r;
    if (r == LOW && level != LV_IDLE) {       // pressed
      muted = true;
      if (mqtt.connected() && lastEventId.length()) publishAck(lastEventId);
      publishStatus();
      Serial.println("[btn] ack -> buzzer muted");
    }
  }
}

// ---------- Output patterns ----------
void drivePatterns() {
  uint32_t now = millis();

  if (level != LV_IDLE && (int32_t)(now - alertUntil) >= 0) {
    clearAlarm();                              // event no longer refreshed -> stop
  }

  bool offline = (now - lastMqttOk) > OFFLINE_WARN_MS;

  switch (level) {
    case LV_DANGER: {                          // solid light, fast beeping, relay on
      bool beep = (now / 200) % 2 == 0;
      outputs(true, beep, true);
      break;
    }
    case LV_WARNING: {                         // blink light, one short beep per second
      bool light = (now / 500) % 2 == 0;
      bool beep  = (now % 1000) < 100;
      outputs(light, beep, false);
      break;
    }
    default: {
      // Offline indicator: short flash every 3 s (no buzzer)
      bool flash = offline && (now % 3000) < 80;
      outputs(flash, false, false);
    }
  }
}

// ---------- Arduino ----------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_ACK_BTN, INPUT_PULLUP);
  outputs(false, false, false);

  tEvent  = String("factory/safety/") + CAMERA_ID + "/event";
  tCmd    = String("factory/safety/") + DEVICE_ID + "/cmd";
  tStatus = String("factory/safety/") + DEVICE_ID + "/status";

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(512);
  lastMqttOk = millis();

  // Power-on self test: short flash + beep
  outputs(true, true, false); delay(150); outputs(false, false, false);
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();
  pollButton();
  drivePatterns();

  if (mqtt.connected() && millis() - lastHeartbeat > HEARTBEAT_MS) {
    lastHeartbeat = millis();
    publishStatus();
  }
}
