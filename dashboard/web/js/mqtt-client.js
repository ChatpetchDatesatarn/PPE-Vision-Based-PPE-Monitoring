// MQTT over WebSocket: connect, subscribe, route messages, publish ack/zones.
// Emits on the returned EventTarget:
//   "connection" {connected}      "status" {camera_id, data}
//   "cira" {data}                 "event" {data}
//   "ack" {data}
import { CONFIG } from "./config.js";

const P = CONFIG.TOPIC_PREFIX;
const SUBSCRIPTIONS = {
  [`${P}+/status`]: { qos: 1 },
  [`${P}+/event`]: { qos: 1 },
  [`${P}ack`]: { qos: 1 },
};

export const mqttBus = new EventTarget();
const emit = (type, detail) => mqttBus.dispatchEvent(new CustomEvent(type, { detail }));

let client = null;
let connected = false;
// Temporary exact-topic subscriptions (zone editor). topic -> Set<handler>
const tempSubs = new Map();

function randomId(n) {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let s = "";
  const buf = new Uint8Array(n);
  crypto.getRandomValues(buf);
  for (const b of buf) s += chars[b % chars.length];
  return s;
}

/** ISO 8601 timestamp in +07:00 (system timezone), independent of the viewer's timezone. */
export function nowIso07() {
  const d = new Date(Date.now() + 7 * 3600 * 1000);
  return d.toISOString().replace(/\.\d{3}Z$/, "+07:00");
}

function setConnected(v) {
  if (connected === v) return;
  connected = v;
  emit("connection", { connected: v });
}

export const isConnected = () => connected;

function parse(topic, payload) {
  const text = new TextDecoder().decode(payload);
  try {
    return JSON.parse(text);
  } catch (e) {
    console.warn("[mqtt] ignored unparsable payload on", topic, e.message);
    return undefined;
  }
}

function route(topic, payload) {
  const handlers = tempSubs.get(topic);
  if (handlers) {
    const data = payload.length ? parse(topic, payload) : null; // empty retained = cleared
    if (data !== undefined) handlers.forEach((h) => safeCall(h, data, topic));
    return;
  }
  if (!topic.startsWith(P)) return;
  const parts = topic.slice(P.length).split("/");
  if (!payload.length) return;
  const data = parse(topic, payload);
  if (!data || typeof data !== "object") {
    if (data !== undefined) console.warn("[mqtt] ignored non-object payload on", topic);
    return;
  }
  if (parts.length === 1 && parts[0] === "ack") {
    if (data.event_id) emit("ack", { data });
  } else if (parts.length === 2 && parts[1] === "status") {
    if (parts[0] === "cira") emit("cira", { data });
    else emit("status", { camera_id: data.camera_id || parts[0], data });
  } else if (parts.length === 2 && parts[1] === "event") {
    if (data.event_id) emit("event", { data });
    else console.warn("[mqtt] event without event_id ignored", data);
  }
}

function safeCall(fn, ...args) {
  try {
    fn(...args);
  } catch (e) {
    console.error("[mqtt] handler error", e);
  }
}

export function connectMqtt() {
  if (client) return;
  if (!window.mqtt?.connect) {
    console.error("[mqtt] lib/mqtt.min.js not loaded");
    setConnected(false);
    return;
  }
  client = window.mqtt.connect(CONFIG.MQTT_URL(), {
    clientId: `dashboard-${randomId(6)}`,
    reconnectPeriod: 2000,
    connectTimeout: 5000,
    clean: true,
    resubscribe: false, // we subscribe ourselves on every connect
  });
  client.on("connect", () => {
    setConnected(true);
    const all = { ...SUBSCRIPTIONS };
    for (const topic of tempSubs.keys()) all[topic] = { qos: 1 };
    client.subscribe(all, (err) => err && console.warn("[mqtt] subscribe failed", err.message));
  });
  client.on("message", (topic, payload) => {
    try {
      route(topic, payload);
    } catch (e) {
      console.error("[mqtt] message handling error", topic, e);
    }
  });
  client.on("close", () => setConnected(false));
  client.on("offline", () => setConnected(false));
  // Connection errors are expected while the broker is down; reconnect handles them.
  client.on("error", (e) => console.warn("[mqtt]", e?.message || e));
}

function publish(topic, obj, opts) {
  return new Promise((resolve, reject) => {
    if (!client || !connected) return reject(new Error("Not connected to MQTT"));
    client.publish(topic, JSON.stringify(obj), opts, (err) => (err ? reject(err) : resolve()));
  });
}

/** status: "resolved" | "false_alarm" */
export function publishAck(eventId, status, note = "") {
  return publish(
    `${P}ack`,
    { event_id: eventId, status, by: "dashboard", note: note || "", ts: nowIso07() },
    { qos: 1, retain: false }
  );
}

export function publishZones(cameraId, zones) {
  return publish(
    `${P}${cameraId}/config/zones`,
    { camera_id: cameraId, ts: nowIso07(), zones },
    { qos: 1, retain: true }
  );
}

/** Subscribe to one exact topic for a while (retained value arrives immediately). Returns unsubscribe(). */
export function subscribeTemp(topic, handler) {
  let set = tempSubs.get(topic);
  const isNew = !set;
  if (!set) tempSubs.set(topic, (set = new Set()));
  set.add(handler);
  if (isNew && client && connected) client.subscribe(topic, { qos: 1 });
  return () => {
    set.delete(handler);
    if (set.size === 0) {
      tempSubs.delete(topic);
      if (client && connected) client.unsubscribe(topic);
    }
  };
}
