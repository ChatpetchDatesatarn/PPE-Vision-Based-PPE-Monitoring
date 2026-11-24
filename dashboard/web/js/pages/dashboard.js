// #/dashboard (v5 fit-to-screen) — KPIs, live camera (v6.3: one camera fills the area, ‹ › to switch), recent alerts (20 with snapshot, scroll), donut summary + CiRA line, PPE-worn donut (v7.2: replaces the event log).
import { TYPES, typeLabel, severityLabel, severityColor, isFallback } from "../labels.js";
import { esc, h, fmtNum, fmtTime, liveGrid, snapshotImg, lsGet, lsSet } from "../ui.js";

const CAM_LS = "safety.v6.dashcam"; // v6.3: last camera shown on the dashboard (per browser)
const MAX_ALERTS = 20; // v5: up to 20 latest alerts that have a snapshot (5 visible, wheel-scroll for the rest)
const LOG_ROWS = 5;    // v5: "บันทึกเหตุการณ์" table rows (all events, with or without snapshot)
// v5: colours for the donut / legend (by violation type)
const TYPE_COLORS = { no_helmet: "#f97316", no_vest: "#eab308", restricted_zone: "#ef4444", unknown_visibility: "#64748b" };
const TYPE_SHORT = { no_helmet: "Helmet", no_vest: "Vest", restricted_zone: "Zone", unknown_visibility: "Unclear" };
const ICON_BELL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22a2 2 0 002-2h-4a2 2 0 002 2zm6-6V11a6 6 0 00-5-5.9V4h-2v1.1A6 6 0 006 11v5l-2 2v1h16v-1z"/></svg>';
const ICON_CAM = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 012-2h9a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2zM16 10l5-3v10l-5-3z"/></svg>';
const ICON_LOG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 2h6a1 1 0 011 1v1h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2V3a1 1 0 011-1zm0 2v2h6V4zM7 11h10v2H7zm0 4h7v2H7z"/></svg>';
const ICON_PPE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a8 8 0 00-8 8v1h16v-1a8 8 0 00-8-8zm-9 10h18v2H3zm4 4h10l-1 4H8z"/></svg>';
const ICON_CHART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 20h18v2H3zM4 17l5-6 4 3 6-8 1.6 1.2-7.2 9.6-4-3-3.8 4.6z"/></svg>';
const shortCam = (name) => String(name ?? "").split(" - ")[0];

export function mount(root, ctx) {
  const page = h(`
    <div class="fit-page">
      <div class="dash">
        <div class="dash-main">
          <section class="kpis" aria-label="Key figures">
            <div class="card kpi" data-k="cams" style="--ic:#3b82f6"><span class="kpi-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 7h12v10H3z M15 10l6-3v10l-6-3z"/></svg></span><span class="kpi-label">Cameras online</span><span class="kpi-value">—</span><span class="kpi-sub">&nbsp;</span></div>
            <div class="card kpi" data-k="persons" style="--ic:#14b8a6"><span class="kpi-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7z"/></svg></span><span class="kpi-label">People now</span><span class="kpi-value">—</span><span class="kpi-sub">&nbsp;</span></div>
            <div class="card kpi" data-k="compliance" style="--ic:#22c55e"><span class="kpi-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 2l8 3v6c0 5-3.4 9.4-8 11-4.6-1.6-8-6-8-11V5z"/></svg></span><span class="kpi-label">PPE compliant</span><span class="kpi-value">—</span><span class="kpi-sub">&nbsp;</span></div>
            <div class="card kpi" data-k="today" style="--ic:#ef4444"><span class="kpi-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 2L1 21h22zM11 9h2v6h-2zm0 8h2v2h-2z"/></svg></span><span class="kpi-label">Violations today</span><span class="kpi-value">—</span><span class="kpi-sub">&nbsp;</span></div>
            <div class="card kpi" data-k="open" style="--ic:#f59e0b"><span class="kpi-ic" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 22a2 2 0 002-2h-4a2 2 0 002 2zm6-6V11a6 6 0 00-5-5.9V4h-2v1.1A6 6 0 006 11v5l-2 2v1h16v-1z"/></svg></span><span class="kpi-label">Pending</span><span class="kpi-value">—</span><span class="kpi-sub">&nbsp;</span></div>
          </section>
          <section class="cam-stage" id="cam-stage" tabindex="0" aria-label="Live view (use ‹ › or the left/right arrow keys to switch camera)">
            <div class="grid g1" id="dash-grid"></div>
            <div class="empty-grid" id="dash-empty">No camera status yet<br><span class="small">(waiting for factory/safety/&lt;cam&gt;/status)</span></div>
          </section>
        </div>
        <div class="dash-side">
          <section class="card alerts-card">
            <h2 class="card-title"><span class="ct"><span class="ct-ic">${ICON_BELL}</span>Recent Alerts</span><a href="#/events">View all →</a></h2>
            <div class="ra-list" id="alert-list" tabindex="0" aria-label="Recent alerts with snapshots (scroll for up to 20)"></div>
          </section>
          <section class="card sum-card">
            <h2 class="card-title">Today's Detection Summary</h2>
            <div class="donut-wrap">
              <div class="donut" id="donut"><div class="donut-hole"><b id="donut-total">—</b><span>today</span></div></div>
              <div class="legend" id="type-legend"></div>
            </div>
            <div class="cira-line"><span class="cl-ic">${ICON_CHART}</span><span id="cira-box">No CiRA status yet</span></div>
          </section>
          <section class="card ppe-card">
            <h2 class="card-title"><span class="ct"><span class="ct-ic ct-ppe">${ICON_PPE}</span>PPE Worn · People Now</span></h2>
            <div class="donut-wrap">
              <div class="donut" id="donut-ppe"><div class="donut-hole"><b id="ppe-total">—</b><span>people</span></div></div>
              <div class="legend" id="ppe-legend"></div>
            </div>
          </section>
        </div>
      </div>
    </div>`);
  root.append(page);

  const $ = (s) => page.querySelector(s);
  const grid = liveGrid($("#dash-grid"), ctx);
  const seenIds = new Set();

  function setKpi(k, value, sub = " ", alarm = false) {
    const card = page.querySelector(`.kpi[data-k="${k}"]`);
    card.querySelector(".kpi-value").innerHTML = value;
    card.querySelector(".kpi-sub").innerHTML = sub;
    card.classList.toggle("alarm", alarm);
  }

  function renderLiveKpis() {
    const ids = ctx.camIds();
    const online = ids.filter((id) => ctx.health(id).camera === "ok").length;
    setKpi("cams", ids.length ? `${online}<small> / ${ids.length}</small>` : "—", ids.length ? "cameras reporting" : "No cameras yet", ids.length > 0 && online < ids.length);

    // Only count cameras whose Perception is alive (stale numbers would mislead)
    let persons = 0, compliant = 0, fresh = 0;
    for (const id of ids) {
      if (ctx.health(id).perception !== "ok") continue;
      const st = ctx.state.cams.get(id).status;
      fresh++;
      persons += Number(st.persons) || 0;
      compliant += Number(st.compliant) || 0;
    }
    setKpi("persons", fresh ? fmtNum(persons) : "—", fresh ? `from ${fresh} camera(s)` : "No live data");
    if (persons > 0) {
      const pct = Math.round((compliant / persons) * 100);
      setKpi("compliance", `${pct}<small>%</small>`, `${compliant} of ${persons} people`);
    } else {
      setKpi("compliance", "—", fresh ? "Nobody in the area" : "No live data");
    }
  }

  // v7.1: second donut — what the people in view are wearing right now (from <cam>/status).
  // With the v7.1 DeepStream status (ppe_both …) it shows helmet+vest / helmet only / vest only / none;
  // with an older status it falls back to full PPE / missing PPE / checking.
  const PPE_ROWS_DETAIL = [
    ["ppe_both", "Helmet + vest", "#22c55e"], ["ppe_helmet_only", "Helmet only", "#3b82f6"],
    ["ppe_vest_only", "Vest only", "#a855f7"], ["ppe_none", "No PPE", "#ef4444"], ["ppe_unknown", "Checking", "#64748b"],
  ];
  function donutFill(el, parts) {
    const sum = parts.reduce((a, p) => a + p[1], 0);
    let acc = 0;
    el.style.background = sum
      ? `conic-gradient(${parts.map(([, n, c]) => { const f = acc; acc += (n / sum) * 360; return `${c} ${f}deg ${acc}deg`; }).join(",")})`
      : "var(--panel-2)";
    return sum;
  }
  function legendHtml(parts, sum) {
    return parts.map(([label, n, c]) => `<div class="lg-row"><i style="--c:${c}"></i><span class="lg-name">${esc(label)}</span><b class="mono">${fmtNum(n)}</b><span class="lg-pct mono">${sum ? ((n / sum) * 100).toFixed(0) : 0}%</span></div>`).join("");
  }
  function renderPpe() {
    const totals = {};
    let persons = 0, compliant = 0, violating = 0, fresh = 0, detail = true;
    for (const id of ctx.camIds()) {
      if (ctx.health(id).perception !== "ok") continue;
      const st = ctx.state.cams.get(id).status || {};
      fresh++;
      persons += Number(st.persons) || 0;
      compliant += Number(st.compliant) || 0;
      violating += Number(st.violating) || 0;
      if (st.ppe_both === undefined) detail = false;
      for (const [k] of PPE_ROWS_DETAIL) totals[k] = (totals[k] || 0) + (Number(st[k]) || 0);
    }
    const parts = detail && fresh
      ? PPE_ROWS_DETAIL.map(([k, label, c]) => [label, totals[k] || 0, c])
      : [["Full PPE", compliant, "#22c55e"], ["Missing PPE", violating, "#ef4444"],
         ["Checking", Math.max(0, persons - compliant - violating), "#64748b"]];
    const sum = donutFill($("#donut-ppe"), parts.map(([l, n, c]) => [l, n, c]));
    $("#ppe-total").textContent = fresh ? fmtNum(persons) : "—";
    $("#ppe-legend").innerHTML = fresh ? legendHtml(parts, sum) : `<div class="notice">No live data</div>`;
  }

  function renderSummary() {
    const s = ctx.state.summary;
    if (!s) {
      const err = ctx.state.summaryError;
      setKpi("today", "—", err ? `<span class="error-text">${esc(err)}</span>` : "Loading…");
      setKpi("open", "—");
      $("#type-legend").innerHTML = `<div class="notice ${err ? "error-text" : ""}">${esc(err || "Loading…")}</div>`;
      return;
    }
    const total = Number(s.total) || 0;
    const y = Number(s.yesterday) || 0;
    let cmp;
    if (y >= 10) {
      // enough base for a percentage to be meaningful
      const pct = Math.round(((total - y) / y) * 100);
      cmp = `${pct >= 0 ? "+" : ""}${pct}% vs yesterday (${fmtNum(y)})`;
    } else {
      // small/zero base: a percentage is misleading, show the raw change instead
      const diff = total - y;
      cmp = `${diff >= 0 ? "+" : ""}${fmtNum(diff)} vs yesterday (${fmtNum(y)})`;
    }
    setKpi("today", fmtNum(total), cmp);
    const open = Number(s.open) || 0;
    setKpi("open", fmtNum(open), open ? "click an alert to handle it" : "Nothing pending", open > 0);

    const byType = s.by_type || {};
    const keys = [...new Set([...Object.keys(TYPES), ...Object.keys(byType)])]
      .filter((k) => k !== "unknown_visibility" || Number(byType[k]) > 0); // v6.3: hide the disabled type unless used
    const counts = keys.map((k) => Number(byType[k]) || 0);
    const sum = counts.reduce((x, y) => x + y, 0);
    $("#donut-total").textContent = fmtNum(sum);
    let acc = 0;
    const stops = keys.map((k, i) => {
      const from = acc;
      acc += sum ? (counts[i] / sum) * 360 : 0;
      return `${TYPE_COLORS[k] || "#94a3b8"} ${from}deg ${acc}deg`;
    });
    $("#donut").style.background = sum ? `conic-gradient(${stops.join(",")})` : "var(--panel-2)";
    $("#type-legend").innerHTML = keys
      .map((k, i) => {
        const pct = sum ? ((counts[i] / sum) * 100).toFixed(0) : "0";
        return `<div class="lg-row"><i style="--c:${TYPE_COLORS[k] || "#94a3b8"}"></i><span class="lg-name">${esc(typeLabel(k))}</span><b class="mono">${fmtNum(counts[i])}</b><span class="lg-pct mono">${pct}%</span></div>`;
      })
      .join("");
  }

  function alertItem(ev) {
    const sev = ev.severity;
    const row = h(`
      <button type="button" class="ra-row" data-event-id="${esc(ev.event_id)}" style="--c:${severityColor(sev)}">
        <span class="ra-thumb"></span>
        <span class="ra-ic" aria-hidden="true">!</span>
        <span class="ra-body">
          <span class="ra-top"><span class="mono">${esc(fmtTime(ev.ts))}</span><span class="ra-sep">|</span><span>${esc(shortCam(ctx.camName(ev.camera_id)))}</span></span>
          <span class="ra-type">${esc(typeLabel(ev.type))}</span>
        </span>
        <span class="ra-badges"><span class="ra-pill">${esc(severityLabel(sev))}</span>${isFallback(ev.via) ? '<span class="badge fallback">FALLBACK</span>' : ""}</span>
      </button>`);
    row.querySelector(".ra-thumb").append(snapshotImg(ev.snapshot_url));
    return row;
  }

  function renderAlerts() {
    const list = $("#alert-list");
    const alerts = ctx.state.alerts.filter((ev) => ev.snapshot_url).slice(0, MAX_ALERTS);
    if (!alerts.length) {
      list.innerHTML = `<div class="notice">${ctx.state.apiOk === false ? "Cannot load history (API down) — waiting for new alerts over MQTT" : "No alerts with snapshots yet"}</div>`;
      return;
    }
    const firstRender = seenIds.size === 0;
    const keepTop = list.scrollTop; // don't jump while someone is scrolling back
    list.replaceChildren(
      ...alerts.map((ev) => {
        const row = alertItem(ev);
        if (!firstRender && !seenIds.has(ev.event_id)) row.classList.add("fresh");
        seenIds.add(ev.event_id);
        return row;
      })
    );
    list.scrollTop = keepTop;
    if (seenIds.size > 500) seenIds.clear();
  }

  function renderCira() {
    const c = ctx.state.cira;
    const box = $("#cira-box");
    if (!c) {
      box.textContent = "No CiRA status yet";
      return;
    }
    const ok = ctx.ciraHealth() === "ok";
    box.innerHTML = `CiRA filtered <b>${fmtNum(c.filtered)}</b> of ${fmtNum(c.received)} · forwarded ${fmtNum(c.published)}${ok ? "" : ` · <span class="error-text">Decision stopped</span>`}`;
  }

  // v6.3: one camera at a time; faint ‹ › on both sides of the picture switch cameras (wraps around)
  let camId = lsGet(CAM_LS) || "";
  function step(d) {
    const ids = ctx.camIds();
    if (ids.length < 2) return;
    const i = Math.max(0, ids.indexOf(camId));
    camId = ids[(i + d + ids.length) % ids.length];
    lsSet(CAM_LS, camId);
    renderGrid();
  }
  function renderGrid() {
    const ids = ctx.camIds();
    if (!ids.includes(camId)) camId = ids[0] || "";
    grid.sync(camId ? [camId] : []);
    $("#dash-empty").hidden = ids.length > 0;
    $("#dash-grid").hidden = ids.length === 0;
    const tile = $("#dash-grid .tile");
    if (!tile) return;
    const vid = tile.querySelector(".tile-video");
    if (!vid.querySelector(".cam-nav")) {
      const mk = (cls, d, label, ch) => {
        const b = h(`<button type="button" class="cam-nav ${cls}" aria-label="${label}">${ch}</button>`);
        b.addEventListener("click", (e) => { e.stopPropagation(); step(d); });
        return b;
      };
      vid.append(mk("prev", -1, "Previous camera", "‹"), mk("next", 1, "Next camera", "›"));
      tile.querySelector(".tile-head .live-badge").before(h('<span class="cam-pos"></span>'));
    }
    const multi = ids.length > 1;
    vid.querySelectorAll(".cam-nav").forEach((b) => {
      b.disabled = !multi;
      b.title = multi ? b.getAttribute("aria-label") : "Only one camera";
    });
    tile.querySelector(".cam-pos").textContent = `${ids.indexOf(camId) + 1} / ${ids.length}`;
  }
  $("#cam-stage").addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") step(-1);
    else if (e.key === "ArrowRight") step(1);
  });

  renderGrid();
  renderLiveKpis();
  renderPpe();
  renderSummary();
  renderAlerts();
  renderCira();

  const offs = [
    // camera names arrive with status, possibly after the alerts were drawn
    ctx.on("cameras", () => { renderGrid(); renderLiveKpis(); renderPpe(); renderAlerts(); }),
    ctx.on("status", () => { grid.updateAll(); renderLiveKpis(); renderPpe(); }),
    ctx.on("health", () => { grid.updateAll(); renderLiveKpis(); renderPpe(); renderCira(); }),
    ctx.on("summary", renderSummary),
    ctx.on("alerts", renderAlerts),
    ctx.on("cira", renderCira),
  ];
  return () => {
    offs.forEach((off) => off());
    grid.destroy();
  };
}
