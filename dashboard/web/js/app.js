// Boot, hash router, and the central state shared by all pages.
import { CONFIG, LS_KEYS } from "./config.js";
import { SOUND_SEVERITIES, typeLabel, severityColor, severityLabel } from "./labels.js";
import { mqttBus, connectMqtt } from "./mqtt-client.js";
import { api } from "./api.js";
import {
  esc, lsGet, lsSet, clockTh, todayTh, normalizeEvent, tsValue, openEventModal, closeModal, toast,
  soundEnabled, setSoundEnabled, unlockAudio, beep, fmtTime,
} from "./ui.js";
import * as dashboard from "./pages/dashboard.js";
import * as live from "./pages/live.js";
import * as events from "./pages/events.js";
import * as report from "./pages/report.js";
import * as settings from "./pages/settings.js";

const PAGES = { dashboard, live, events, report, settings };

// ---------- central state ----------
const state = {
  cams: new Map(), // camera_id -> { status }
  cira: null,      // last cira/status payload
  mqttConnected: false,
  alerts: [],      // recent events, newest first (≤ RECENT_ALERTS_MAX)
  summary: null,   // today's /api/stats/summary
  summaryError: null,
  apiOk: null,
  live: new Map(), // v4: camera_id -> live-video light level ("ok"|"warn"|"bad"|"unknown") from the tiles
  deleteEnabled: false, // v6: recorder has a DELETE_PIN set (from /api/health)
};

// ---------- tiny pub/sub ----------
const listeners = new Map();
function on(type, fn) {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type).add(fn);
  return () => listeners.get(type)?.delete(fn);
}
function emit(type, data) {
  listeners.get(type)?.forEach((fn) => {
    try {
      fn(data);
    } catch (e) {
      console.error(`[app] listener for "${type}" failed`, e);
    }
  });
}

// ---------- server clock offset ----------
// The viewer's clock may differ from the Jetson's; ts ages are measured on the server's clock.
const CLOCK_SYNC_S = 60;
const CLOCK_WARN_MS = 5000;
let clockOffsetMs = 0; // server - local; keeps the last good value if a sync fails

async function syncClock() {
  const t0 = Date.now();
  try {
    const hres = await api.health();
    const t1 = Date.now();
    const server = Number(hres?.server_epoch_ms);
    const del = !!hres?.delete_enabled;
    if (del !== state.deleteEnabled) {
      state.deleteEnabled = del;
      emit("deleteEnabled", del);
    }
    if (Number.isFinite(server)) clockOffsetMs = server - (t0 + t1) / 2;
  } catch (e) {
    console.debug("[app] clock sync failed, keeping offset", clockOffsetMs, e.message);
  }
  renderClockSkew();
}

const serverNow = () => Date.now() + clockOffsetMs;

function renderClockSkew() {
  const el = $("#clock-skew");
  if (!el) return;
  const s = Math.round(clockOffsetMs / 1000);
  el.hidden = Math.abs(clockOffsetMs) <= CLOCK_WARN_MS;
  el.textContent = `This device clock is off by ${Math.abs(s)} s (corrected)`;
  el.title = s > 0 ? "This device clock is behind the system" : "This device clock is ahead of the system";
}

// ---------- health ----------
const ageS = (ts) => {
  const t = Date.parse(ts);
  return Number.isFinite(t) ? (serverNow() - t) / 1000 : Infinity;
};

/** { perception: ok|bad, camera: ok|bad|unknown, age } for one camera */
function health(camId) {
  const st = state.cams.get(camId)?.status;
  if (!st) return { perception: "bad", camera: "unknown", age: Infinity };
  const age = ageS(st.ts);
  const perception = st.online === true && age <= CONFIG.STATUS_STALE_S ? "ok" : "bad";
  let camera = "unknown";
  if (st.camera_connected === false) camera = "bad";
  else if (st.camera_connected === true && perception === "ok") camera = "ok";
  return { perception, camera, age };
}

function ciraHealth() {
  const c = state.cira;
  if (!c) return "bad";
  return c.online !== false && ageS(c.ts) <= CONFIG.CIRA_STALE_S ? "ok" : "bad";
}

const camIds = () => [...state.cams.keys()].sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
const camName = (id) => state.cams.get(id)?.status?.name || id || "—";
const streamPath = (id) => state.cams.get(id)?.status?.stream_path || id;

function overallLights() {
  const ids = camIds();
  const hs = ids.map(health);
  const agg = (key) => {
    if (!hs.length) return { level: "unknown", text: "No cameras yet" };
    const ok = hs.filter((x) => x[key] === "ok").length;
    const bad = hs.filter((x) => x[key] === "bad").length;
    return { level: bad ? "bad" : ok === hs.length ? "ok" : "unknown", text: `${ok}/${hs.length}` };
  };
  const detail = (key) => ids.map((id, i) => `${camName(id)}: ${hs[i][key]}`).join("\n");
  const cira = ciraHealth();
  // v4: live-video light, aggregated from what the tiles report (bad wins, then warn, then ok)
  const lv = ids.map((id) => state.live.get(id)).filter(Boolean);
  const okL = lv.filter((x) => x === "ok").length;
  const live = !lv.length
    ? { level: "unknown", text: "—", title: "Live video not open" }
    : {
        level: lv.includes("bad") ? "bad" : lv.includes("warn") ? "warn" : okL === lv.length ? "ok" : "warn",
        text: `${okL}/${lv.length}`,
        title: ids.filter((id) => state.live.get(id)).map((id) => `${camName(id)}: ${state.live.get(id)}`).join("\n"),
      };
  return {
    camera: { ...agg("camera"), title: detail("camera") },
    perception: { ...agg("perception"), title: detail("perception") },
    decision: {
      level: cira,
      text: state.cira ? (cira === "ok" ? "OK" : "Stopped") : "No data",
      title: state.cira ? `cira/status ts: ${state.cira.ts}\nflow: ${state.cira.flow ?? "—"}` : "No cira/status received yet",
    },
    livevideo: live,
  };
}

// ---------- alerts ----------
function mergeAlerts(list) {
  const byId = new Map(state.alerts.map((e) => [e.event_id, e]));
  for (const e of list) {
    const prev = byId.get(e.event_id);
    // An API copy (has status from DB) wins over a bare MQTT copy
    byId.set(e.event_id, prev ? { ...prev, ...e } : e);
  }
  state.alerts = [...byId.values()]
    .sort((a, b) => tsValue(b.ts) - tsValue(a.ts))
    .slice(0, CONFIG.RECENT_ALERTS_MAX);
  emit("alerts", state.alerts);
}

async function loadInitialAlerts() {
  try {
    // v5: load a full page so the dashboard can show up to 20 alerts that have a snapshot
    const res = await api.events({ limit: CONFIG.RECENT_ALERTS_MAX });
    mergeAlerts((res.items || []).map(normalizeEvent));
    setApiOk(true);
  } catch (e) {
    console.warn("[app] initial alerts failed:", e.message);
    setApiOk(false);
    setTimeout(loadInitialAlerts, CONFIG.SUMMARY_REFRESH_S * 1000);
  }
}

// ---------- summary (today) ----------
let summaryTimer = null;
let summaryInflight = false;
let lastSummaryAt = 0;
const SUMMARY_MIN_GAP_MS = 2000; // collapse bursts of events/acks into one request

async function refreshSummary() {
  clearTimeout(summaryTimer);
  const wait = lastSummaryAt + SUMMARY_MIN_GAP_MS - Date.now();
  if (summaryInflight || wait > 0) {
    summaryTimer = setTimeout(refreshSummary, Math.max(wait, 300));
    return;
  }
  summaryInflight = true;
  lastSummaryAt = Date.now();
  try {
    state.summary = await api.summary(todayTh());
    state.summaryError = null;
    setApiOk(true);
  } catch (e) {
    state.summaryError = e.message;
    setApiOk(false);
  } finally {
    summaryInflight = false;
    emit("summary", state.summary);
    summaryTimer = setTimeout(refreshSummary, CONFIG.SUMMARY_REFRESH_S * 1000);
  }
}

function setApiOk(ok) {
  if (state.apiOk === ok) return;
  state.apiOk = ok;
  renderBanner();
}

// ---------- context handed to pages ----------
const ctx = {
  state,
  on,
  health,
  ciraHealth,
  camIds,
  camName,
  streamPath,
  refreshSummary,
  // v4: a live tile reports its video light level here (null clears it when the tile is destroyed)
  reportLive(id, level) {
    if (level == null) state.live.delete(id);
    else state.live.set(id, level);
  },
  openEvent: (ev) => openEventModal(ev, ctx),
  // v6: after a delete, drop the events from the in-memory lists and refresh today's numbers
  removeEvents(ids) {
    const gone = new Set(ids);
    state.alerts = state.alerts.filter((e) => !gone.has(e.event_id));
    emit("alerts", state.alerts);
    emit("deleted", [...gone]);
    refreshSummary();
  },
  setSound(on) {
    unlockAudio();
    setSoundEnabled(on);
    renderSoundBtn();
    emit("sound", on);
  },
};

// ---------- MQTT wiring ----------
mqttBus.addEventListener("connection", ({ detail }) => {
  state.mqttConnected = detail.connected;
  renderBanner();
  emit("connection", detail.connected);
});

mqttBus.addEventListener("status", ({ detail }) => {
  const id = detail.camera_id;
  const isNew = !state.cams.has(id);
  state.cams.set(id, { status: detail.data });
  emit("status", id);
  if (isNew) emit("cameras", camIds());
  renderLights();
});

mqttBus.addEventListener("cira", ({ detail }) => {
  state.cira = detail.data;
  emit("cira", state.cira);
  renderLights();
});

mqttBus.addEventListener("event", ({ detail }) => {
  const ev = normalizeEvent(detail.data);
  const known = state.alerts.some((a) => a.event_id === ev.event_id);
  mergeAlerts([ev]);
  emit("event", ev);
  if (known) return;
  refreshSummary();
  if (SOUND_SEVERITIES.has(ev.severity)) {
    if (soundEnabled()) beep(ev.severity);
    toast(
      `<b>${esc(typeLabel(ev.type))}</b><span>${esc(camName(ev.camera_id))} · ${esc(fmtTime(ev.ts))} · ${esc(severityLabel(ev.severity))}</span>`,
      { color: severityColor(ev.severity), onClick: () => ctx.openEvent(ev) }
    );
  }
});

mqttBus.addEventListener("ack", ({ detail }) => {
  const a = detail.data;
  let changed = false;
  state.alerts = state.alerts.map((e) => {
    if (e.event_id !== a.event_id) return e;
    changed = true;
    return { ...e, status: a.status, ack_by: a.by, acked_at: a.ts, note: a.note ?? e.note };
  });
  if (changed) emit("alerts", state.alerts);
  emit("ack", a);
  refreshSummary();
});

// ---------- top bar ----------
const $ = (sel) => document.querySelector(sel);
let lastLightsSig = "";

function renderLights() {
  const L = overallLights();
  const sig = JSON.stringify(L);
  if (sig === lastLightsSig) return;
  const healthChanged = lastLightsSig !== "";
  lastLightsSig = sig;
  for (const key of ["camera", "perception", "decision", "livevideo"]) {
    const el = document.querySelector(`.light[data-light="${key}"]`);
    if (!el) continue;
    el.dataset.level = L[key].level;
    el.querySelector(".light-val").textContent = L[key].text;
    el.title = L[key].title || "";
  }
  if (healthChanged) emit("health", L);
}

function renderBanner() {
  const b = $("#conn-banner");
  if (!b) return;
  const msgs = [];
  // Give the first connection a moment before warning
  if (!state.mqttConnected && Date.now() - bootAt > 3000) msgs.push("Lost connection to the system, reconnecting…");
  if (state.apiOk === false) msgs.push("Cannot reach the API; summary/history may be out of date");
  b.textContent = msgs.join("  ·  ");
  b.hidden = msgs.length === 0;
}

function renderSoundBtn() {
  const btn = $("#sound-btn");
  const onNow = soundEnabled();
  btn.setAttribute("aria-pressed", String(onNow));
  btn.title = onNow ? "Alarm sound: on (click to mute)" : "Alarm sound: off (click to unmute)";
  btn.querySelector(".snd-on").style.display = onNow ? "" : "none";
  btn.querySelector(".snd-off").style.display = onNow ? "none" : "";
}

// ---------- router ----------
let current = null; // { name, cleanup }

function routeName() {
  const m = /^#\/([a-z]+)/.exec(location.hash);
  return m && PAGES[m[1]] ? m[1] : null;
}

function navigate() {
  let name = routeName();
  if (!name) {
    const saved = lsGet(LS_KEYS.PAGE);
    name = saved && PAGES[saved] ? saved : "dashboard";
    history.replaceState(null, "", `#/${name}`);
  }
  if (current?.name === name) return;
  closeModal();
  try {
    current?.cleanup?.();
  } catch (e) {
    console.error("[app] page cleanup failed", e);
  }
  const root = $("#page");
  root.replaceChildren();
  root.scrollTop = 0;
  window.scrollTo(0, 0);
  let cleanup = null;
  try {
    cleanup = PAGES[name].mount(root, ctx);
  } catch (e) {
    console.error(`[app] page "${name}" failed to render`, e);
    root.innerHTML = `<div class="card error-box">Cannot show this page: ${esc(e.message)}</div>`;
  }
  current = { name, cleanup };
  lsSet(LS_KEYS.PAGE, name);
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const active = a.dataset.nav === name;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

// ---------- boot ----------
const bootAt = Date.now();

function boot() {
  const tick = () => {
    $("#clock").textContent = clockTh();
    $("#clock-date").textContent = todayTh();
    renderLights(); // re-evaluates staleness of retained/old status every second
    renderBanner();
  };
  tick();
  setInterval(tick, 1000);

  $("#sound-btn").addEventListener("click", () => ctx.setSound(!soundEnabled()));
  renderSoundBtn();
  // Browsers only allow audio after a user gesture
  const unlockOnce = () => {
    unlockAudio();
    document.removeEventListener("pointerdown", unlockOnce);
    document.removeEventListener("keydown", unlockOnce);
  };
  document.addEventListener("pointerdown", unlockOnce);
  document.addEventListener("keydown", unlockOnce);

  document.addEventListener("visibilitychange", () => emit("visibility", !document.hidden));
  window.addEventListener("hashchange", navigate);

  // Any element with data-event-id opens the detail dialog
  document.addEventListener("click", (e) => {
    const target = e.target.closest("[data-event-id]");
    if (!target || target.closest(".modal")) return;
    const id = target.dataset.eventId;
    const ev = state.alerts.find((a) => a.event_id === id) || target._event || { event_id: id };
    ctx.openEvent(ev);
  });

  state.mqttConnected = false;
  renderBanner();
  syncClock();
  setInterval(syncClock, CLOCK_SYNC_S * 1000);
  connectMqtt();
  loadInitialAlerts();
  refreshSummary();
  navigate();
}

boot();
