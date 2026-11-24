// #/events — filterable, paginated event history from /api/events + CSV export.
// v6: CSV dialog (วัน / เดือน / ช่วงวันที่ / ทั้งหมด) and PIN-protected delete (เลือกหลายรายการ / ตามช่วงวันที่).
import { CONFIG } from "../config.js";
import { TYPES, SEVERITIES, STATUSES, typeLabel, viaLabel } from "../labels.js";
import { api } from "../api.js";
import {
  esc, h, normalizeEvent, snapshotImg, severityBadge, fallbackBadge, statusBadge, fmtDateTime, applyStatusToDom,
  todayTh, toast,
} from "../ui.js";
import { dialog, deleteWithPin } from "../dialogs.js";

const ICON_DL = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3v12m0 0l-5-5m5 5l5-5M4 19h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_BIN = '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4zM6 9h12l-1 12H7z" fill="currentColor"/></svg>';

// v6: YYYY-MM -> first / last day
function monthBounds(ym) {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return [`${ym}-01`, `${ym}-${String(last).padStart(2, "0")}`];
}
const fmtCount = (n) => Number(n || 0).toLocaleString("en-US");

// Filters survive navigation between pages (module scope), not reloads.
const filters = { camera_id: "", type: "", severity: "", status: "", from: "", to: "" };
let offset = 0;

const options = (map, labelOf) =>
  `<option value="">All</option>` +
  Object.keys(map).map((k) => `<option value="${esc(k)}">${esc(labelOf(k))}</option>`).join("");

export function mount(root, ctx) {
  const page = h(`
    <div>
      <div class="page-head">
        <h2>Event History</h2>
        <button class="btn btn-danger" id="del-range" type="button" hidden>${ICON_BIN} Delete by date range</button>
        <button class="btn" id="csv" type="button">${ICON_DL} Download CSV</button>
      </div>
      <form class="card filters" id="filters">
        <label class="field">Camera<select name="camera_id"></select></label>
        <label class="field">Type<select name="type">${options(TYPES, typeLabel)}</select></label>
        <label class="field">Severity<select name="severity">${options(SEVERITIES, (k) => SEVERITIES[k].text)}</select></label>
        <label class="field">Status<select name="status">${options(STATUSES, (k) => STATUSES[k])}</select></label>
        <label class="field">From<input type="date" name="from"></label>
        <label class="field">To<input type="date" name="to"></label>
        <div class="field-actions">
          <button class="btn btn-primary" type="submit">Search</button>
          <button class="btn" type="button" id="reset">Clear</button>
        </div>
      </form>
      <div class="card" style="margin-top:16px">
        <button class="btn new-banner" id="new-banner" type="button" hidden></button>
        <div class="sel-bar" id="sel-bar" hidden>
          <span id="sel-count"></span>
          <button class="btn btn-danger" id="del-sel" type="button">${ICON_BIN} Delete selected</button>
          <button class="btn" id="sel-clear" type="button">Clear selection</button>
        </div>
        <div id="ev-error" class="error-box card" hidden></div>
        <div class="table-wrap">
          <table class="data">
            <thead><tr>
              <th class="sel-col"><input type="checkbox" id="sel-all" aria-label="Select all on this page"></th>
              <th>Time</th><th>Camera</th><th>Zone</th><th>Type</th><th>Severity</th>
              <th>Confidence</th><th>Via</th><th>Status</th><th>Snapshot</th>
            </tr></thead>
            <tbody id="rows"></tbody>
          </table>
        </div>
        <div class="pager">
          <span id="range" class="muted"></span>
          <div class="row">
            <button class="btn" id="prev" type="button">‹ Previous</button>
            <button class="btn" id="next" type="button">Next ›</button>
          </div>
        </div>
      </div>
    </div>`);
  root.append(page);
  const $ = (s) => page.querySelector(s);
  const form = $("#filters");
  let total = 0;
  let items = [];
  let newCount = 0;
  let reqSeq = 0;
  const selected = new Set(); // v6: ticked event_ids on the current page

  function renderSelection() {
    const canDel = !!ctx.state.deleteEnabled;
    page.classList.toggle("can-delete", canDel);
    $("#del-range").hidden = !canDel;
    $("#sel-bar").hidden = !canDel || selected.size === 0;
    $("#sel-count").textContent = `${selected.size} selected`;
    const all = $("#sel-all");
    all.checked = items.length > 0 && items.every((ev) => selected.has(ev.event_id));
    all.indeterminate = selected.size > 0 && !all.checked;
  }

  function fillCameraOptions() {
    const sel = form.camera_id;
    const ids = new Set([...ctx.camIds(), ...Object.keys(ctx.state.summary?.by_camera || {})]);
    if (filters.camera_id) ids.add(filters.camera_id);
    const sorted = [...ids].sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
    const want = `<option value="">All</option>` +
      sorted.map((id) => `<option value="${esc(id)}">${esc(ctx.camName(id) === id ? id : `${ctx.camName(id)} (${id})`)}</option>`).join("");
    if (sel.innerHTML !== want) {
      sel.innerHTML = want;
      sel.value = filters.camera_id;
    }
  }

  function writeForm() {
    for (const k of Object.keys(filters)) form[k].value = filters[k];
  }
  function readForm() {
    for (const k of Object.keys(filters)) filters[k] = form[k].value;
  }

  function updateCsvLink() { /* v6: CSV goes through the dialog (openCsvDialog) */ }

  // ---------- v6: CSV dialog ----------
  async function openCsvDialog() {
    const today = todayTh();
    await dialog({
      title: "Download CSV",
      okText: "Download",
      html: `
        <div class="csv-modes">
          <label class="radio"><input type="radio" name="mode" value="day" checked> One day
            <input type="date" name="day" value="${esc(filters.from || today)}"></label>
          <label class="radio"><input type="radio" name="mode" value="month"> Whole month
            <input type="month" name="month" value="${esc((filters.from || today).slice(0, 7))}"></label>
          <label class="radio"><input type="radio" name="mode" value="range"> Date range
            <span class="row"><input type="date" name="from" value="${esc(filters.from)}"> to <input type="date" name="to" value="${esc(filters.to)}"></span></label>
          <label class="radio"><input type="radio" name="mode" value="all"> All</label>
        </div>
        <p class="hint" id="csv-count"></p>`,
      onOk: (form) => {
        const r = csvRange(form);
        if (r.error) throw new Error(r.error);
        const a = document.createElement("a");
        a.href = api.exportCsvUrl(r.from, r.to);
        a.download = "";
        document.body.append(a);
        a.click();
        a.remove();
        return true;
      },
    });
  }
  function csvRange(form) {
    const mode = form.mode.value;
    if (mode === "all") return { from: "", to: "" };
    if (mode === "day") return form.day.value ? { from: form.day.value, to: form.day.value } : { error: "Pick a date" };
    if (mode === "month") return form.month.value ? (([f, t]) => ({ from: f, to: t }))(monthBounds(form.month.value)) : { error: "Pick a month" };
    const f = form.from.value, t = form.to.value;
    if (!f || !t) return { error: "Pick a start and end date" };
    if (f > t) return { error: "Start date must not be after end date" };
    return { from: f, to: t };
  }

  // ---------- v6: delete ----------
  async function deleteSelected() {
    const ids = [...selected];
    if (!ids.length) return;
    const res = await deleteWithPin({
      title: `Delete ${ids.length} selected event(s)`,
      summaryHtml: `<p><b>${ids.length}</b> ticked event(s) on this page</p>`,
      doDelete: (pin) => api.deleteEvents(ids, pin),
    });
    if (!res) return;
    selected.clear();
    ctx.removeEvents(ids); // emits "deleted" -> load()
    toast(`<b>Deleted</b><span>${fmtCount(res.events)} event(s) · ${fmtCount(res.snapshots)} image(s)</span>`, { color: "#64748b" });
  }

  async function deleteRangeFlow() {
    let picked = null;
    const ok = await dialog({
      title: "Delete by date range",
      okText: "Next",
      danger: true,
      html: `
        <div class="row">
          <label class="field">From<input type="date" name="from" value="${esc(filters.from)}" required></label>
          <label class="field">To<input type="date" name="to" value="${esc(filters.to)}" required></label>
        </div>
        <p class="hint">Deletes every event in this range (all cameras, all types), start and end days included</p>`,
      onOk: async (form) => {
        const f = form.from.value, t = form.to.value;
        if (!f || !t) throw new Error("Pick a start and end date");
        if (f > t) throw new Error("Start date must not be after end date");
        const res = await api.events({ from: f, to: t, limit: 1 });
        const n = Number(res.total) || 0;
        if (!n) throw new Error("No events in this range");
        picked = { from: f, to: t, n };
        return true;
      },
    });
    if (!ok || !picked) return;
    const res = await deleteWithPin({
      title: "Confirm delete by date range",
      summaryHtml: `<p>${esc(picked.from)} to ${esc(picked.to)} · <b>${fmtCount(picked.n)}</b> event(s) will be deleted</p>`,
      doDelete: (pin) => api.deleteRange(picked.from, picked.to, pin),
    });
    if (!res) return;
    selected.clear();
    offset = 0;
    // the in-memory "recent alerts" may hold some of them: refetch is simplest, drop any that match the range
    ctx.removeEvents(ctx.state.alerts.filter((e) => {
      const d = String(e.ts || "").slice(0, 10);
      return d >= picked.from && d <= picked.to;
    }).map((e) => e.event_id));
    toast(`<b>Deleted</b><span>${fmtCount(res.events)} event(s) · ${fmtCount(res.snapshots)} image(s)</span>`, { color: "#64748b" });
  }

  function showError(msg) {
    const box = $("#ev-error");
    box.hidden = !msg;
    box.textContent = msg ? `Failed to load: ${msg}` : "";
  }

  function renderRows() {
    const tbody = $("#rows");
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="10" class="notice">No events match the filters</td></tr>`;
    } else {
      tbody.replaceChildren(
        ...items.map((ev) => {
          const conf = Number(ev.confidence);
          const tr = h(`<table><tr data-event-id="${esc(ev.event_id)}">
            <td class="sel-col" data-label="Select"><input type="checkbox" aria-label="Select this event" ${selected.has(ev.event_id) ? "checked" : ""}></td>
            <td data-label="Time" class="mono">${esc(fmtDateTime(ev.ts))}</td>
            <td data-label="Camera" data-cam-name="${esc(ev.camera_id)}">${esc(ctx.camName(ev.camera_id))}</td>
            <td data-label="Zone">${esc(ev.zone_id ?? "—")}</td>
            <td data-label="Type">${esc(typeLabel(ev.type))}</td>
            <td data-label="Severity">${severityBadge(ev.severity)}</td>
            <td data-label="Confidence" class="mono">${ev.confidence !== null && Number.isFinite(conf) ? `${(conf * 100).toFixed(0)}%` : "—"}</td>
            <td data-label="Via">${fallbackBadge(ev.via) || esc(viaLabel(ev.via))}</td>
            <td data-label="Status">${statusBadge(ev.status)}</td>
            <td class="thumb-cell"></td>
          </tr></table>`).querySelector("tr");
          tr._event = ev;
          const cell = tr.querySelector(".sel-col");
          // clicking the tick box must not open the detail dialog (document-level handler)
          cell.addEventListener("click", (e) => e.stopPropagation());
          cell.querySelector("input").addEventListener("change", (e) => {
            if (e.target.checked) selected.add(ev.event_id);
            else selected.delete(ev.event_id);
            renderSelection();
          });
          tr.querySelector(".thumb-cell").append(snapshotImg(ev.snapshot_url));
          return tr;
        })
      );
    }
    renderSelection();
    const from = total ? offset + 1 : 0;
    const to = offset + items.length;
    $("#range").textContent = `${from}–${to} of ${total.toLocaleString("en-US")}`;
    $("#prev").disabled = offset === 0;
    $("#next").disabled = offset + CONFIG.EVENTS_PAGE_SIZE >= total;
  }

  async function load() {
    const seq = ++reqSeq;
    selected.clear();
    newCount = 0;
    $("#new-banner").hidden = true;
    $("#range").textContent = "Loading…";
    try {
      const res = await api.events({ ...filters, limit: CONFIG.EVENTS_PAGE_SIZE, offset });
      if (seq !== reqSeq) return;
      total = Number(res.total) || 0;
      items = (res.items || []).map(normalizeEvent);
      showError("");
    } catch (e) {
      if (seq !== reqSeq) return;
      items = [];
      total = 0;
      showError(e.detail || e.message);
    }
    renderRows();
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    readForm();
    if (filters.from && filters.to && filters.from > filters.to) {
      showError("Start date must not be after end date");
      return;
    }
    offset = 0;
    updateCsvLink();
    load();
  });
  form.addEventListener("change", (e) => {
    if (e.target.name === "from" || e.target.name === "to") {
      readForm();
      updateCsvLink();
    }
  });
  $("#reset").addEventListener("click", () => {
    for (const k of Object.keys(filters)) filters[k] = "";
    writeForm();
    offset = 0;
    updateCsvLink();
    load();
  });
  $("#prev").addEventListener("click", () => {
    offset = Math.max(0, offset - CONFIG.EVENTS_PAGE_SIZE);
    load();
  });
  $("#next").addEventListener("click", () => {
    offset += CONFIG.EVENTS_PAGE_SIZE;
    load();
  });
  $("#csv").addEventListener("click", openCsvDialog);
  $("#del-range").addEventListener("click", deleteRangeFlow);
  $("#del-sel").addEventListener("click", deleteSelected);
  $("#sel-clear").addEventListener("click", () => {
    selected.clear();
    page.querySelectorAll("#rows .sel-col input").forEach((c) => (c.checked = false));
    renderSelection();
  });
  $("#sel-all").addEventListener("change", (e) => {
    items.forEach((ev) => (e.target.checked ? selected.add(ev.event_id) : selected.delete(ev.event_id)));
    page.querySelectorAll("#rows .sel-col input").forEach((c) => (c.checked = e.target.checked));
    renderSelection();
  });
  $("#new-banner").addEventListener("click", () => {
    offset = 0;
    load();
  });

  fillCameraOptions();
  writeForm();
  updateCsvLink();
  load();

  const offs = [
    ctx.on("deleteEnabled", renderSelection),
    ctx.on("deleted", () => load()), // v6: deleted here or from the detail dialog -> reload this page
    ctx.on("cameras", fillCameraOptions),
    ctx.on("summary", fillCameraOptions),
    // camera names arrive with status, possibly after the rows were drawn
    ctx.on("status", (id) => {
      const name = ctx.camName(id);
      page.querySelectorAll(`[data-cam-name="${CSS.escape(id)}"]`).forEach((td) => {
        if (td.textContent !== name) td.textContent = name;
      });
      fillCameraOptions();
    }),
    // Don't reshuffle the page under the user's cursor; offer a reload instead.
    ctx.on("event", () => {
      newCount++;
      const b = $("#new-banner");
      b.hidden = false;
      b.textContent = `${newCount} new event(s) — click to reload`;
    }),
    ctx.on("ack", (a) => {
      const ev = items.find((x) => x.event_id === a.event_id);
      if (!ev) return;
      ev.status = a.status;
      applyStatusToDom(page, a.event_id, a.status);
    }),
  ];
  return () => offs.forEach((off) => off());
}
