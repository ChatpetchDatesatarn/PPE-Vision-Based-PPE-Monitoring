// Shared UI helpers: escaping, formatting, badges, snapshots, modal, toasts, sound, live tiles.
import { CONFIG, LS_KEYS, NO_SNAPSHOT } from "./config.js";
import {
  typeLabel, statusLabel, severityLabel, severityColor, isFallback, viaLabel, FALLBACK_BADGE,
} from "./labels.js";
import { publishAck, isConnected } from "./mqtt-client.js";
import { api } from "./api.js";
import { WhepPlayer } from "./webrtc.js";
import { deleteWithPin } from "./dialogs.js";

// ---------- basics ----------
export const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export const lsGet = (k) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
export const lsSet = (k, v) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* storage unavailable */
  }
};

// ---------- time (shown as received, never converted to the viewer's timezone) ----------
export function fmtTime(ts) {
  const m = /T?(\d{2}:\d{2}:\d{2})/.exec(String(ts ?? ""));
  return m ? m[1] : esc(ts ?? "—");
}
export function fmtDateTime(ts) {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})/.exec(String(ts ?? ""));
  return m ? `${m[1]} ${m[2]}` : String(ts ?? "—");
}
const bkkDate = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok", year: "numeric", month: "2-digit", day: "2-digit" });
const bkkTime = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Bangkok", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
/** Today in Thailand as YYYY-MM-DD */
export const todayTh = () => bkkDate.format(new Date());
export const clockTh = () => bkkTime.format(new Date());

export const fmtPct = (x, digits = 0) => (Number.isFinite(x) ? `${(x * 100).toFixed(digits)}%` : "—");
export const fmtNum = (x) => (Number.isFinite(Number(x)) && x !== null && x !== "" ? Number(x).toLocaleString("en-US") : "—");

// ---------- events ----------
/** Make API/MQTT events look the same. MQTT events have no status/snapshot_url. */
export function normalizeEvent(ev) {
  const e = { ...ev };
  if (!e.status) e.status = "open";
  if (e.snapshot_url === undefined) {
    e.snapshot_url = e.snapshot_id ? `/data/snapshots/${encodeURIComponent(e.snapshot_id)}.jpg` : null;
  }
  return e;
}

export const tsValue = (ts) => {
  const t = Date.parse(ts);
  return Number.isFinite(t) ? t : 0;
};

export function severityBadge(sev) {
  return `<span class="badge sev" style="--c:${severityColor(sev)}">${esc(severityLabel(sev))}</span>`;
}
export function fallbackBadge(via) {
  return isFallback(via) ? `<span class="badge fallback" title="Not decided by CiRA">${FALLBACK_BADGE}</span>` : "";
}
export function statusBadge(status) {
  return `<span class="badge status st-${esc(status)}" data-status>${esc(statusLabel(status))}</span>`;
}

/** <img> that retries once (snapshots may land after the event), then shows a placeholder. */
export function snapshotImg(url, cls = "thumb", alt = "Event snapshot") {
  const img = document.createElement("img");
  img.className = cls;
  img.alt = alt;
  img.loading = "lazy";
  img.decoding = "async";
  if (!url) {
    img.src = NO_SNAPSHOT;
    return img;
  }
  let tries = 0;
  img.onerror = () => {
    tries++;
    if (tries === 1) {
      setTimeout(() => {
        img.src = url + (url.includes("?") ? "&" : "?") + "r=1";
      }, CONFIG.SNAPSHOT_RETRY_MS);
    } else {
      img.onerror = null;
      img.src = NO_SNAPSHOT;
    }
  };
  img.src = url;
  return img;
}

/** Compact alert row used by the dashboard list. */
export function alertRow(ev, camName) {
  const row = h(`
    <button type="button" class="alert-row" data-event-id="${esc(ev.event_id)}" style="--c:${severityColor(ev.severity)}">
      <span class="alert-thumb"></span>
      <span class="alert-body">
        <span class="alert-top"><span class="mono">${esc(fmtTime(ev.ts))}</span><span class="muted">${esc(camName(ev.camera_id))}</span></span>
        <span class="alert-type">${esc(typeLabel(ev.type))}</span>
        <span class="alert-badges">${severityBadge(ev.severity)}${fallbackBadge(ev.via)}${statusBadge(ev.status)}</span>
      </span>
    </button>`);
  row.querySelector(".alert-thumb").append(snapshotImg(ev.snapshot_url));
  return row;
}

/** Update every status badge for this event that is currently on screen. */
export function applyStatusToDom(root, eventId, status) {
  root.querySelectorAll(`[data-event-id="${CSS.escape(eventId)}"] [data-status]`).forEach((b) => {
    b.className = `badge status st-${status}`;
    b.textContent = statusLabel(status);
  });
}

// ---------- modal ----------
let modalCleanup = null;

export function closeModal() {
  modalCleanup?.();
  modalCleanup = null;
}

export function openEventModal(evIn, ctx) {
  closeModal();
  let ev = normalizeEvent(evIn);
  const root = document.getElementById("modal-root");
  const dlg = h(`
    <div class="modal-backdrop">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <header class="modal-head">
          <h2 id="modal-title"></h2>
          <button type="button" class="icon-btn" data-close aria-label="Close">
            <svg viewBox="0 0 24 24" width="22" height="22"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
          </button>
        </header>
        <div class="modal-body">
          <div class="modal-img"></div>
          <div class="modal-info">
            <dl class="fields"></dl>
            <div class="ack-box">
              <label for="ack-note">Note</label>
              <textarea id="ack-note" rows="2" maxlength="500" placeholder="(optional)"></textarea>
              <div class="ack-actions">
                <button type="button" class="btn btn-primary" data-ack="resolved">Resolved</button>
                <button type="button" class="btn" data-ack="false_alarm">False alarm</button>
              </div>
              <p class="ack-msg" role="status"></p>
              <button type="button" class="btn btn-danger del-btn" data-del hidden>
                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4zM6 9h12l-1 12H7z" fill="currentColor"/></svg>
                Delete this event</button>
            </div>
          </div>
        </div>
      </div>
    </div>`);
  root.append(dlg);
  const msg = dlg.querySelector(".ack-msg");

  const render = () => {
    dlg.querySelector("#modal-title").innerHTML =
      `${esc(typeLabel(ev.type))} ${severityBadge(ev.severity)} ${fallbackBadge(ev.via)}`;
    const conf = Number(ev.confidence);
    const rows = [
      ["Status", statusBadge(ev.status)],
      ["Time", esc(fmtDateTime(ev.ts))],
      ["Camera", esc(ctx.camName(ev.camera_id))],
      ["Zone", esc(ev.zone_id ?? "—")],
      ["Type", esc(typeLabel(ev.type))],
      ["Severity", esc(severityLabel(ev.severity))],
      ["Confidence", Number.isFinite(conf) && ev.confidence !== null ? `${(conf * 100).toFixed(0)}%` : "—"],
      ["Via", esc(viaLabel(ev.via))],
      ["Track ID", esc(ev.track_id ?? "—")],
      ["BBox", esc(Array.isArray(ev.bbox) ? ev.bbox.map((n) => (typeof n === "number" ? +n.toFixed(3) : n)).join(", ") : ev.bbox ?? "—")],
      ["Event ID", `<span class="mono small">${esc(ev.event_id)}</span>`],
      ["Snapshot ID", `<span class="mono small">${esc(ev.snapshot_id ?? "—")}</span>`],
    ];
    if (ev.acked_at || ev.ack_by) rows.push(["Handled by", `${esc(ev.ack_by ?? "—")} · ${esc(fmtDateTime(ev.acked_at))}`]);
    if (ev.note) rows.push(["Previous note", esc(ev.note)]);
    dlg.querySelector(".fields").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  };
  render();
  dlg.querySelector(".modal-img").append(snapshotImg(ev.snapshot_url, "big", "Event snapshot (large)"));

  // Fetch the stored copy (status, ack info, snapshot_url) when available
  api.event(ev.event_id).then(
    (full) => {
      if (!dlg.isConnected || !full) return;
      ev = normalizeEvent({ ...ev, ...full });
      render();
    },
    () => {} // 404 / API down: keep what we have
  );

  const buttons = [...dlg.querySelectorAll("[data-ack]")];
  let ackEchoed = false;
  buttons.forEach((b) =>
    b.addEventListener("click", async () => {
      const status = b.dataset.ack;
      buttons.forEach((x) => (x.disabled = true));
      msg.className = "ack-msg";
      msg.textContent = "Sending…";
      ackEchoed = false;
      try {
        await publishAck(ev.event_id, status, dlg.querySelector("#ack-note").value.trim());
        // The broker may deliver our own ack back before PUBACK; don't overwrite that result
        if (!ackEchoed) msg.textContent = "Sent, waiting for confirmation…";
      } catch (e) {
        msg.className = "ack-msg error";
        msg.textContent = `Send failed: ${e.message}`;
        buttons.forEach((x) => (x.disabled = false));
      }
    })
  );
  const syncConn = () => {
    if (!isConnected()) {
      msg.className = "ack-msg error";
      msg.textContent = "Not connected to the system — cannot confirm yet";
    }
  };
  syncConn();

  const offAck = ctx.on("ack", (a) => {
    if (a.event_id !== ev.event_id) return;
    ackEchoed = true;
    ev = { ...ev, status: a.status, ack_by: a.by, acked_at: a.ts, note: a.note || ev.note };
    render();
    msg.className = "ack-msg ok";
    msg.textContent = `Updated: ${statusLabel(a.status)}`;
    buttons.forEach((x) => (x.disabled = false));
  });

  // v6: permanent delete (needs PIN; hidden when the recorder has no DELETE_PIN)
  const delBtn = dlg.querySelector("[data-del]");
  delBtn.hidden = !ctx.state.deleteEnabled;
  delBtn.addEventListener("click", async () => {
    const res = await deleteWithPin({
      title: "Delete this event",
      summaryHtml: `<p>${esc(typeLabel(ev.type))} · ${esc(fmtDateTime(ev.ts))} · ${esc(ctx.camName(ev.camera_id))}</p>`,
      doDelete: (pin) => api.deleteEvents([ev.event_id], pin),
    });
    if (!res) return;
    ctx.removeEvents([ev.event_id]);
    toast(`<b>Deleted</b><span>1 event · ${res.snapshots ?? 0} image(s)</span>`, { color: "#64748b" });
    closeModal();
  });

  const onKey = (e) => e.key === "Escape" && closeModal();
  document.addEventListener("keydown", onKey);
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg || e.target.closest("[data-close]")) closeModal();
  });
  dlg.querySelector("[data-close]").focus();

  modalCleanup = () => {
    offAck();
    document.removeEventListener("keydown", onKey);
    dlg.remove();
  };
}

// ---------- toasts (in-page alerts; no Notification API on http) ----------
export function toast(html, { onClick, color, timeout = 6000 } = {}) {
  const box = document.getElementById("toast-root");
  if (!box) return;
  const t = h(`<div class="toast" role="alert" ${color ? `style="--c:${color}"` : ""}>${html}</div>`);
  if (onClick) {
    t.classList.add("clickable");
    t.addEventListener("click", () => {
      onClick();
      t.remove();
    });
  }
  box.prepend(t);
  while (box.children.length > 4) box.lastElementChild.remove();
  setTimeout(() => t.remove(), timeout);
}

// ---------- sound (WebAudio, generated) ----------
let audioCtx = null;
export function soundEnabled() {
  return lsGet(LS_KEYS.SOUND) !== "off";
}
export function setSoundEnabled(on) {
  lsSet(LS_KEYS.SOUND, on ? "on" : "off");
}
/** Must be called from a user gesture once before sound can play. */
export function unlockAudio() {
  try {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      audioCtx = new AC();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return true;
  } catch {
    return false;
  }
}
export const audioReady = () => !!audioCtx && audioCtx.state === "running";

export function beep(severity = "high") {
  if (!audioCtx) return;
  const tones = severity === "critical" ? [880, 660, 880, 660] : [740, 740];
  const now = audioCtx.currentTime;
  tones.forEach((f, i) => {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "square";
    osc.frequency.value = f;
    const t0 = now + i * 0.22;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.18, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.18);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(t0);
    osc.stop(t0 + 0.2);
  });
}

// ---------- live video tile ----------
/**
 * Creates a tile that plays one camera and shows its status overlays.
 * Returns { el, update(), start(), stop(), destroy() }.
 */
const QBADGE_LS = "safety.v3.qbadge"; // "1" show details / "0" collapsed
const QUALITY_TH = { good: "Good", fair: "Fair", bad: "Poor", unknown: "—" };

function fmtDur(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
}

export function createLiveTile(camId, ctx, { detailed = false } = {}) {
  const el = h(`
    <div class="tile" data-cam="${esc(camId)}">
      <div class="tile-head"><span class="dot"></span><span class="tile-name"></span><span class="live-badge">LIVE</span></div>
      <div class="tile-video">
        <video muted autoplay playsinline></video>
        <canvas class="tile-freeze" hidden></canvas>
        <div class="tile-overlay"></div>
        <div class="tile-status" hidden></div>
        <div class="tile-quality">
          <button class="tile-q-toggle" type="button" aria-label="Live video quality"><span class="q-dot"></span></button>
          <div class="tile-q-body"></div>
        </div>
      </div>
      <div class="tile-foot"></div>
    </div>`);
  const video = el.querySelector("video");
  const freeze = el.querySelector(".tile-freeze");
  const overlay = el.querySelector(".tile-overlay");
  const statusBar = el.querySelector(".tile-status");

  // Keep a fresh copy of the last good frame while playing, so a stall/reconnect can show it
  // instead of a black video (the peer connection closes and the track ends on reconnect).
  function grabFrame() {
    if (!video.videoWidth) return;
    if (freeze.width !== video.videoWidth) { freeze.width = video.videoWidth; freeze.height = video.videoHeight; }
    try { freeze.getContext("2d").drawImage(video, 0, 0, freeze.width, freeze.height); } catch { /* not ready */ }
  }
  const qWrap = el.querySelector(".tile-quality");
  const qDot = el.querySelector(".q-dot");
  const qBody = el.querySelector(".tile-q-body");
  const player = new WhepPlayer(video, ctx.streamPath(camId));
  player.onstate = () => update();
  player.onstats = () => renderQuality();

  let everFrame = false; // a frame has shown at least once -> keep it on screen during a reconnect
  let qExpanded = lsGet(QBADGE_LS) !== "0"; // default shown
  qWrap.classList.toggle("open", qExpanded);
  el.querySelector(".tile-q-toggle").addEventListener("click", () => {
    qExpanded = !qExpanded;
    qWrap.classList.toggle("open", qExpanded);
    lsSet(QBADGE_LS, qExpanded ? "1" : "0");
  });

  function renderQuality() {
    if (player.live === "playing") grabFrame();
    const s = player.stats;
    // v4: no new frame while not playing -> show "ไม่มีภาพ X วิ" and force level "แย่"
    const noFrameS = player.lastFrameWall ? Math.round((Date.now() - player.lastFrameWall) / 1000) : null;
    const stale = player.live !== "playing" && player.live !== "stopped" && noFrameS != null && noFrameS >= 3;
    const dispQ = stale ? "bad" : player.quality;
    qDot.className = `q-dot q-${dispQ}`;
    const st = ctx.state.cams.get(camId)?.status || {};
    const camFps = Number.isFinite(st.fps_in) ? `${Number(st.fps_in).toFixed(1)} fps (camera)` : "";
    const rows = [
      `<b>${QUALITY_TH[dispQ]}</b>`,
    ];
    if (stale) rows.push(`<b class="q-noframe">No video ${noFrameS} s</b>`);
    rows.push(
      `fps ${s.fps != null ? s.fps : "—"}`,
      `${s.width && s.height ? `${s.width}×${s.height}` : "—"}`,
      `${s.bitrateMbps != null ? s.bitrateMbps.toFixed(2) : "—"} Mbps`,
      `latency ${s.latencyMs != null ? s.latencyMs : "—"} ms`,
      `lost ${s.packetsLost != null ? s.packetsLost : "—"}`,
      `stalls (5 min) ${s.stalls5min}`,
      `uptime ${fmtDur(s.connectedMs)}`,
    );
    qBody.innerHTML = rows.map((r) => `<span>${r}</span>`).join("");
    qBody.title = camFps;
  }

  // v4: live-video light level for the top status bar (green flowing / amber reconnecting / red no-pic)
  function liveLevel() {
    if (player.state === "stopped") return "unknown";
    const age = player.lastFrameWall ? Date.now() - player.lastFrameWall : Infinity;
    if (player.live === "playing" && age < 5000) return "ok";
    if (age > 30000) return "bad";
    return "warn";
  }

  function update() {
    const st = ctx.state.cams.get(camId)?.status || {};
    const hl = ctx.health(camId);
    el.querySelector(".tile-name").textContent = ctx.camName(camId);
    el.querySelector(".dot").className = `dot ${hl.camera}`;
    const playing = player.state === "playing" && player.live === "playing";
    el.querySelector(".live-badge").classList.toggle("on", playing);

    // Hard problems (camera / perception) cover the frame; so does the very first connect before
    // any frame has ever shown. Once a frame has shown, a later stall / reconnect keeps the frozen
    // frame and shows only a thin status bar, so there is no black flash.
    if (player.hasFrame) everFrame = true;
    if (player.state === "stopped") everFrame = false;
    let hardText = "";
    let softText = "";
    const alarm = st.camera_connected === false || hl.perception !== "ok";
    if (st.camera_connected === false) hardText = "Camera disconnected";
    else if (hl.perception !== "ok") hardText = "Detection stopped";
    else if (!everFrame && player.statusText) hardText = player.statusText;
    else softText = player.statusText;

    overlay.textContent = hardText;
    overlay.classList.toggle("show", !!hardText);
    overlay.classList.toggle("alarm", alarm);
    statusBar.textContent = softText;
    statusBar.hidden = !softText;
    // show the frozen last frame while a kept-frame status (stall/reconnect) is up; hide when playing
    const showFreeze = !!softText && player.live !== "playing";
    freeze.hidden = !showFreeze;

    const foot = [];
    if (st.resolution) foot.push(esc(st.resolution));
    // fps under the video = the real WebRTC fps; camera (cam01/status) fps stays in the tooltip.
    const webrtcFps = player.stats.fps;
    if (webrtcFps != null) {
      const tip = Number.isFinite(st.fps_in) ? ` title="camera ${Number(st.fps_in).toFixed(1)} fps"` : "";
      foot.push(`<span${tip}>${webrtcFps.toFixed(detailed ? 1 : 0)} fps</span>`);
    } else if (Number.isFinite(st.fps_in)) {
      foot.push(`${Number(st.fps_in).toFixed(detailed ? 1 : 0)} fps`);
    }
    foot.push(`people ${fmtNum(st.persons)} / violations <b class="${st.violating > 0 ? "viol" : ""}">${fmtNum(st.violating)}</b>`);
    if (detailed && st.model) foot.push(`<span class="muted">${esc(st.model)}</span>`);
    el.querySelector(".tile-foot").innerHTML = foot.join('<span class="sep">·</span>');
    player.setStreamPath(ctx.streamPath(camId));
  }
  update();
  renderQuality();
  // v4: 1 s tick keeps "ไม่มีภาพ X วิ" counting and the live light fresh even when the peer is down
  const tick = setInterval(() => {
    renderQuality();
    update();
    ctx.reportLive?.(camId, liveLevel());
  }, 1000);
  ctx.reportLive?.(camId, liveLevel());
  return {
    el,
    update,
    start: () => player.start(),
    stop: () => player.stop(),
    destroy: () => {
      clearInterval(tick);
      ctx.reportLive?.(camId, null);
      player.stop();
      el.remove();
    },
  };
}

/**
 * Keeps a set of live tiles inside `container` in sync with the camera list,
 * starts/stops players with page visibility. Returns { sync(camIds), updateAll(), destroy() }.
 */
export function liveGrid(container, ctx, opts = {}) {
  const tiles = new Map();
  let visible = !document.hidden;
  function sync(camIds) {
    for (const [id, t] of tiles) {
      if (!camIds.includes(id)) {
        t.destroy();
        tiles.delete(id);
      }
    }
    camIds.forEach((id) => {
      let t = tiles.get(id);
      if (!t) {
        t = createLiveTile(id, ctx, opts);
        tiles.set(id, t);
        if (visible) t.start();
      }
      container.append(t.el); // keeps order
    });
  }
  // Keep streaming through a brief tab switch; only disconnect if hidden for a while, so a quick
  // peek away does not drop (and re-create) sessions. Coming back reconnects at once.
  const HIDDEN_DISCONNECT_MS = 30000;
  let hideTimer = null;
  const offVis = ctx.on("visibility", (v) => {
    visible = v;
    clearTimeout(hideTimer);
    hideTimer = null;
    if (v) {
      tiles.forEach((t) => t.start());
    } else {
      hideTimer = setTimeout(() => tiles.forEach((t) => t.stop()), HIDDEN_DISCONNECT_MS);
    }
  });
  return {
    sync,
    updateAll: () => tiles.forEach((t) => t.update()),
    size: () => tiles.size,
    destroy() {
      clearTimeout(hideTimer);
      offVis();
      tiles.forEach((t) => t.destroy());
      tiles.clear();
    },
  };
}
