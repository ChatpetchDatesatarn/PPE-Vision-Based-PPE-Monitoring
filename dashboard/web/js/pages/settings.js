// #/settings — alarm sound, system info, and the zone editor (retained MQTT config/zones).
import { CONFIG } from "../config.js";
import { api } from "../api.js";
import { publishZones, subscribeTemp, isConnected } from "../mqtt-client.js";
import { WhepPlayer } from "../webrtc.js";
import { esc, h, soundEnabled, unlockAudio, beep, fmtNum, fmtDateTime } from "../ui.js";

const ZONE_COLORS = ["#3b82f6", "#14b8a6", "#a855f7", "#0ea5e9", "#ec4899", "#84cc16"];
const HIT_PX = 14; // vertex grab radius (CSS px)

const round4 = (n) => Math.round(n * 10000) / 10000;
const clamp01 = (n) => Math.min(1, Math.max(0, n));

/** Keep only well-formed zones from a payload we didn't write. */
function sanitizeZones(payload) {
  const list = Array.isArray(payload?.zones) ? payload.zones : [];
  return list
    .filter((z) => z && Array.isArray(z.points))
    .map((z, i) => ({
      id: String(z.id ?? `zone-${i + 1}`),
      name: String(z.name ?? z.id ?? `Zone ${i + 1}`),
      points: z.points
        .filter((p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(+p[0]) && Number.isFinite(+p[1]))
        .map((p) => [clamp01(+p[0]), clamp01(+p[1])]),
    }))
    .filter((z) => z.points.length >= 3);
}

function nextZoneId(zones) {
  const used = new Set(zones.map((z) => z.id));
  for (let i = 0; i < 26; i++) {
    const id = `zone-${String.fromCharCode(97 + i)}`;
    if (!used.has(id)) return id;
  }
  let n = zones.length + 1;
  while (used.has(`zone-${n}`)) n++;
  return `zone-${n}`;
}

function pointInPolygon([x, y], pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i];
    const [xj, yj] = pts[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function mount(root, ctx) {
  const page = h(`
    <div>
      <div class="page-head"><h2>Settings</h2></div>
      <div class="settings-grid">
        <div class="dash-side">
          <section class="card">
            <h3 class="card-title">Alarm sound</h3>
            <label class="switch"><input type="checkbox" id="snd"> Play alarm sound (Critical and High)</label>
            <div class="row" style="margin-top:12px">
              <button class="btn" type="button" data-test="critical">Test sound: Critical</button>
              <button class="btn" type="button" data-test="high">Test sound: High</button>
            </div>
            <p class="hint">The browser allows sound only after you click on the page at least once</p>
          </section>
          <section class="card">
            <h3 class="card-title">System status <button class="btn" type="button" id="health-refresh">Refresh</button></h3>
            <dl class="kv" id="sysinfo"></dl>
          </section>
        </div>

        <section class="card">
          <h3 class="card-title">Restricted zones (Zone editor)</h3>
          <div class="row">
            <label class="field" style="flex:1;min-width:160px">Camera<select id="z-cam"></select></label>
            <label class="field" style="flex:1;min-width:160px" id="z-cam-manual-wrap" hidden>Camera ID<input type="text" id="z-cam-manual" placeholder="e.g. cam01"></label>
          </div>
          <div class="zone-stage" id="z-stage" style="margin-top:12px">
            <video muted autoplay playsinline></video>
            <canvas tabindex="0" aria-label="Zone drawing area, click to add a point"></canvas>
            <div class="tile-overlay"></div>
          </div>
          <div class="zone-toolbar">
            <button class="btn btn-primary" type="button" id="z-new">+ Draw new zone</button>
            <button class="btn" type="button" id="z-finish" hidden>Finish (close shape)</button>
            <button class="btn" type="button" id="z-undo" hidden>Undo last point</button>
            <button class="btn" type="button" id="z-cancel" hidden>Cancel drawing</button>
          </div>
          <p class="hint" id="z-hint"></p>
          <div class="zone-list" id="z-list"></div>
          <div class="zone-toolbar">
            <button class="btn btn-primary" type="button" id="z-save">Save zones</button>
            <button class="btn" type="button" id="z-revert">Revert to saved</button>
          </div>
          <p class="hint" id="z-status" role="status"></p>
        </section>
      </div>
    </div>`);
  root.append(page);
  const $ = (s) => page.querySelector(s);

  // ---------- sound ----------
  const snd = $("#snd");
  snd.checked = soundEnabled();
  snd.addEventListener("change", () => ctx.setSound(snd.checked));
  page.querySelectorAll("[data-test]").forEach((b) =>
    b.addEventListener("click", () => {
      unlockAudio();
      beep(b.dataset.test);
    })
  );

  // ---------- system info ----------
  let healthData = null;
  let healthErr = "";
  function renderSysinfo() {
    const c = ctx.state.cira;
    const rows = [
      ["MQTT (browser)", ctx.state.mqttConnected ? "Connected" : `<span class="error-text">Disconnected</span>`],
      ["MQTT URL", esc(CONFIG.MQTT_URL())],
      ["Known cameras", esc(ctx.camIds().join(", ") || "—")],
      ["CiRA", c ? `${ctx.ciraHealth() === "ok" ? "Running" : `<span class="error-text">Stopped</span>`} · received ${fmtNum(c.received)} · forwarded ${fmtNum(c.published)} · filtered ${fmtNum(c.filtered)}` : "No status yet"],
    ];
    if (healthData) {
      rows.push(
        ["Recorder API", healthData.ok ? "OK" : `<span class="error-text">Error</span>`],
        ["Recorder ↔ MQTT", esc(healthData.mqtt ?? "—")],
        ["MQTT messages recorded", fmtNum(healthData.mqtt_messages)],
        ["Events in database", fmtNum(healthData.events)],
        ["Snapshot images", fmtNum(healthData.snapshots)]
      );
    } else if (healthErr) {
      rows.push(["Recorder API", `<span class="error-text">${esc(healthErr)}</span>`]);
    }
    $("#sysinfo").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  }
  async function loadHealth() {
    try {
      healthData = await api.health();
      healthErr = "";
    } catch (e) {
      healthData = null;
      healthErr = e.detail || e.message;
    }
    if (alive) renderSysinfo();
  }
  $("#health-refresh").addEventListener("click", loadHealth);

  // ---------- zone editor ----------
  const stage = $("#z-stage");
  const canvas = stage.querySelector("canvas");
  const video = stage.querySelector("video");
  const overlay = stage.querySelector(".tile-overlay");
  const g = canvas.getContext("2d");
  let alive = true;
  let camId = "";
  let player = null;
  let unsub = null;
  let zones = [];
  let saved = null;      // last retained payload (sanitized zones) or null if none
  let savedTs = null;
  let gotRetained = false;
  let dirty = false;
  let selected = -1;
  let drawing = null;    // array of points while drawing
  let drag = null;       // { zi, pi }
  let hover = null;      // [x,y] normalized cursor while drawing

  const setStatus = (html, cls = "") => {
    const el = $("#z-status");
    el.className = `hint ${cls}`;
    el.innerHTML = html;
  };

  function camOptions() {
    const sel = $("#z-cam");
    const ids = ctx.camIds();
    $("#z-cam-manual-wrap").hidden = ids.length > 0;
    sel.parentElement.hidden = ids.length === 0;
    const want = ids.map((id) => `<option value="${esc(id)}">${esc(ctx.camName(id))} (${esc(id)})</option>`).join("");
    if (sel.innerHTML !== want) {
      sel.innerHTML = want;
      if (camId && ids.includes(camId)) sel.value = camId;
    }
    if (!camId && ids.length) selectCamera(ids[0]);
  }

  function selectCamera(id) {
    id = String(id || "").trim();
    if (id === camId) return;
    if (dirty && !confirm("Zone changes are not saved. Switch camera anyway?")) {
      $("#z-cam").value = camId;
      return;
    }
    unsub?.();
    unsub = null;
    player?.stop();
    player = null;
    camId = id;
    zones = [];
    saved = null;
    savedTs = null;
    gotRetained = false;
    dirty = false;
    selected = -1;
    drawing = null;
    if (!camId) {
      renderAll();
      return;
    }
    $("#z-cam").value = camId;
    player = new WhepPlayer(video, ctx.streamPath(camId));
    player.onstate = renderOverlay;
    if (!document.hidden) player.start();
    unsub = subscribeTemp(`${CONFIG.TOPIC_PREFIX}${camId}/config/zones`, onRetained);
    setStatus(isConnected() ? "Loading saved zones…" : "MQTT disconnected — cannot load saved zones");
    // No retained message within a moment means nothing saved yet
    setTimeout(() => {
      if (alive && !gotRetained && camId === id && isConnected()) setStatus("No saved zones for this camera yet");
    }, 1500);
    renderAll();
  }

  function onRetained(payload) {
    gotRetained = true;
    const incoming = payload ? sanitizeZones(payload) : [];
    saved = incoming;
    savedTs = payload?.ts ?? null;
    if (!dirty && !drawing) {
      zones = structuredClone(incoming);
      selected = Math.min(selected, zones.length - 1);
      setStatus(savedTs ? `Saved zones loaded (saved ${esc(fmtDateTime(savedTs))})` : "No saved zones for this camera yet", "");
    } else {
      setStatus("Zones were updated from another device — click “Revert to saved” to load them", "error-text");
    }
    renderAll();
  }

  function markDirty() {
    dirty = true;
    setStatus("Unsaved changes");
  }

  function renderOverlay() {
    const st = ctx.state.cams.get(camId)?.status || {};
    let text = "";
    if (!camId) text = "No cameras yet";
    else if (st.camera_connected === false) text = "Camera disconnected (you can still draw zones)";
    else if (player?.state === "connecting") text = "Connecting video…";
    else if (player?.state === "failed") text = "Cannot connect video (you can still draw zones)";
    overlay.textContent = text;
    overlay.classList.toggle("show", !!text);
  }

  function renderList() {
    const list = $("#z-list");
    if (!zones.length) {
      list.innerHTML = `<div class="notice">No zones yet — click “Draw new zone”, then click on the picture to place points</div>`;
      return;
    }
    list.replaceChildren(
      ...zones.map((z, i) => {
        const item = h(`
          <div class="zone-item ${i === selected ? "sel" : ""}">
            <span class="swatch" style="background:${ZONE_COLORS[i % ZONE_COLORS.length]}"></span>
            <input type="text" value="${esc(z.name)}" aria-label="Zone name ${esc(z.id)}" maxlength="60">
            <span class="zid">${esc(z.id)} · ${z.points.length} points</span>
            <button class="btn btn-danger" type="button" aria-label="Delete zone ${esc(z.name)}">Delete</button>
          </div>`);
        const input = item.querySelector("input");
        input.addEventListener("focus", () => {
          if (selected !== i) {
            selected = i;
            draw();
            page.querySelectorAll(".zone-item").forEach((el, k) => el.classList.toggle("sel", k === i));
          }
        });
        input.addEventListener("input", () => {
          z.name = input.value;
          markDirty();
        });
        item.querySelector("button").addEventListener("click", () => {
          if (!confirm(`Delete zone “${z.name}”?`)) return;
          zones.splice(i, 1);
          selected = -1;
          markDirty();
          renderAll();
        });
        return item;
      })
    );
  }

  function renderToolbar() {
    const isDrawing = !!drawing;
    $("#z-new").hidden = isDrawing;
    $("#z-finish").hidden = $("#z-undo").hidden = $("#z-cancel").hidden = !isDrawing;
    $("#z-finish").disabled = !isDrawing || drawing.length < 3;
    $("#z-undo").disabled = !isDrawing || drawing.length === 0;
    $("#z-new").disabled = !camId;
    $("#z-save").disabled = !camId;
    $("#z-revert").disabled = !camId || !dirty;
    $("#z-hint").textContent = isDrawing
      ? `Click on the picture to place points (${drawing.length}) · click the first point or “Finish” to close the shape · Esc = cancel`
      : camId ? "Click inside a zone to select it, then drag its corner points to reshape" : "";
  }

  function renderAll() {
    renderOverlay();
    renderList();
    renderToolbar();
    draw();
  }

  // ----- canvas -----
  function resizeCanvas() {
    const r = stage.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(r.width * dpr));
    const hh = Math.max(1, Math.round(r.height * dpr));
    if (canvas.width !== w || canvas.height !== hh) {
      canvas.width = w;
      canvas.height = hh;
    }
    draw();
  }

  function draw() {
    const W = canvas.width, H = canvas.height;
    const dpr = window.devicePixelRatio || 1;
    g.clearRect(0, 0, W, H);
    const px = ([x, y]) => [x * W, y * H];
    zones.forEach((z, i) => {
      const color = ZONE_COLORS[i % ZONE_COLORS.length];
      const sel = i === selected;
      g.beginPath();
      z.points.forEach((p, k) => (k ? g.lineTo(...px(p)) : g.moveTo(...px(p))));
      g.closePath();
      g.fillStyle = color + (sel ? "55" : "33");
      g.fill();
      g.lineWidth = (sel ? 3 : 2) * dpr;
      g.strokeStyle = color;
      g.stroke();
      // label
      const cx = z.points.reduce((s, p) => s + p[0], 0) / z.points.length;
      const cy = z.points.reduce((s, p) => s + p[1], 0) / z.points.length;
      g.font = `600 ${14 * dpr}px system-ui, sans-serif`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      const label = z.name || z.id;
      const tw = g.measureText(label).width + 12 * dpr;
      g.fillStyle = "rgba(10,18,32,.8)";
      g.fillRect(cx * W - tw / 2, cy * H - 11 * dpr, tw, 22 * dpr);
      g.fillStyle = "#fff";
      g.fillText(label, cx * W, cy * H);
      if (sel) z.points.forEach((p) => handle(px(p), color, dpr));
    });
    if (drawing) {
      const color = ZONE_COLORS[zones.length % ZONE_COLORS.length];
      g.beginPath();
      drawing.forEach((p, k) => (k ? g.lineTo(...px(p)) : g.moveTo(...px(p))));
      if (hover && drawing.length) g.lineTo(...px(hover));
      g.lineWidth = 2 * dpr;
      g.setLineDash([8 * dpr, 6 * dpr]);
      g.strokeStyle = color;
      g.stroke();
      g.setLineDash([]);
      drawing.forEach((p, k) => handle(px(p), k === 0 && drawing.length >= 3 ? "#ffffff" : color, dpr));
    }
  }

  function handle([x, y], color, dpr) {
    g.beginPath();
    g.arc(x, y, 6 * dpr, 0, Math.PI * 2);
    g.fillStyle = color;
    g.fill();
    g.lineWidth = 2 * dpr;
    g.strokeStyle = "#0a1220";
    g.stroke();
  }

  function toNorm(ev) {
    const r = canvas.getBoundingClientRect();
    return [clamp01((ev.clientX - r.left) / r.width), clamp01((ev.clientY - r.top) / r.height)];
  }
  function nearPx(a, b) {
    const r = canvas.getBoundingClientRect();
    return Math.hypot((a[0] - b[0]) * r.width, (a[1] - b[1]) * r.height) <= HIT_PX;
  }

  function finishDrawing() {
    if (!drawing || drawing.length < 3) return;
    const id = nextZoneId(zones);
    const name = prompt("Zone name", `Zone ${id.replace("zone-", "").toUpperCase()}`);
    if (name === null) return; // keep drawing
    zones.push({ id, name: name.trim() || id, points: drawing.map(([x, y]) => [round4(x), round4(y)]) });
    selected = zones.length - 1;
    drawing = null;
    hover = null;
    markDirty();
    renderAll();
  }

  canvas.addEventListener("pointerdown", (ev) => {
    if (!camId) return;
    const p = toNorm(ev);
    if (drawing) {
      if (drawing.length >= 3 && nearPx(p, drawing[0])) return finishDrawing();
      drawing.push(p);
      renderToolbar();
      draw();
      return;
    }
    if (selected >= 0) {
      const pi = zones[selected].points.findIndex((q) => nearPx(p, q));
      if (pi >= 0) {
        drag = { zi: selected, pi };
        canvas.setPointerCapture(ev.pointerId);
        return;
      }
    }
    // select topmost zone under the pointer
    let hit = -1;
    for (let i = zones.length - 1; i >= 0; i--) {
      if (pointInPolygon(p, zones[i].points)) {
        hit = i;
        break;
      }
    }
    selected = hit;
    renderList();
    draw();
  });
  canvas.addEventListener("pointermove", (ev) => {
    if (drag) {
      const [x, y] = toNorm(ev);
      zones[drag.zi].points[drag.pi] = [round4(x), round4(y)];
      draw();
    } else if (drawing) {
      hover = toNorm(ev);
      draw();
    }
  });
  const endDrag = () => {
    if (!drag) return;
    drag = null;
    markDirty();
    renderList();
    renderToolbar();
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  canvas.addEventListener("pointerleave", () => {
    if (drawing) {
      hover = null;
      draw();
    }
  });
  canvas.addEventListener("keydown", (ev) => {
    if (!drawing) return;
    if (ev.key === "Escape") $("#z-cancel").click();
    else if (ev.key === "Enter") finishDrawing();
    else if (ev.key === "Backspace") {
      ev.preventDefault();
      $("#z-undo").click();
    }
  });

  $("#z-new").addEventListener("click", () => {
    drawing = [];
    selected = -1;
    renderAll();
    canvas.focus();
  });
  $("#z-finish").addEventListener("click", finishDrawing);
  $("#z-undo").addEventListener("click", () => {
    drawing?.pop();
    renderToolbar();
    draw();
  });
  $("#z-cancel").addEventListener("click", () => {
    drawing = null;
    hover = null;
    renderAll();
  });
  $("#z-revert").addEventListener("click", () => {
    zones = structuredClone(saved || []);
    dirty = false;
    selected = -1;
    drawing = null;
    setStatus(saved ? "Reverted to saved zones" : "No saved zones yet");
    renderAll();
  });
  $("#z-save").addEventListener("click", async () => {
    if (!camId) return;
    if (drawing) return setStatus("Finish or cancel the zone you are drawing before saving", "error-text");
    const payloadZones = zones.map((z) => ({
      id: z.id,
      name: z.name.trim() || z.id,
      points: z.points.map(([x, y]) => [round4(x), round4(y)]),
    }));
    $("#z-save").disabled = true;
    setStatus("Saving…");
    try {
      await publishZones(camId, payloadZones);
      dirty = false; // the retained echo will confirm and refresh the list
      setStatus(`Saved ${payloadZones.length} zone(s) (retained) — topic ${esc(CONFIG.TOPIC_PREFIX + camId)}/config/zones`, "");
    } catch (e) {
      setStatus(`Save failed: ${esc(e.message)}`, "error-text");
    }
    renderToolbar();
  });

  $("#z-cam").addEventListener("change", (e) => selectCamera(e.target.value));
  $("#z-cam-manual").addEventListener("change", (e) => selectCamera(e.target.value));

  video.addEventListener("loadedmetadata", () => {
    if (video.videoWidth && video.videoHeight) {
      stage.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
      resizeCanvas();
    }
  });
  const ro = new ResizeObserver(resizeCanvas);
  ro.observe(stage);

  const onBeforeUnload = (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  };
  window.addEventListener("beforeunload", onBeforeUnload);

  renderSysinfo();
  loadHealth();
  camOptions();
  renderAll();

  const offs = [
    ctx.on("cameras", () => { camOptions(); renderSysinfo(); }),
    ctx.on("status", (id) => id === camId && renderOverlay()),
    ctx.on("cira", renderSysinfo),
    ctx.on("connection", (c) => {
      renderSysinfo();
      if (c && camId && !gotRetained) setStatus("Loading saved zones…");
    }),
    ctx.on("sound", (on) => (snd.checked = on)),
    ctx.on("visibility", (v) => (v ? player?.start() : player?.stop())),
  ];
  return () => {
    alive = false;
    offs.forEach((off) => off());
    ro.disconnect();
    window.removeEventListener("beforeunload", onBeforeUnload);
    unsub?.();
    player?.stop();
  };
}
