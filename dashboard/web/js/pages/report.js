// #/report — daily chart by type, false alarm rate, by camera / severity, fallback count.
import { TYPES, SEVERITIES, typeLabel, severityLabel, severityColor } from "../labels.js";
import { api } from "../api.js";
import { esc, h, todayTh, fmtNum, fmtPct } from "../ui.js";

// Category colours for event types (not severity colours, which carry meaning elsewhere)
const TYPE_COLORS = {
  no_helmet: "#3b82f6",
  no_vest: "#14b8a6",
  restricted_zone: "#a855f7",
  unknown_visibility: "#94a3b8",
};
const EXTRA_COLORS = ["#0ea5e9", "#ec4899", "#84cc16", "#f472b6"];

let days = 7;
let date = null; // selected summary date, null = today

function bars(entries, colorOf) {
  if (!entries.length) return `<div class="notice">No data</div>`;
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return entries
    .map(([label, n, key]) =>
      `<div class="bar-row" style="--c:${colorOf ? colorOf(key) : "var(--accent)"}"><span>${esc(label)}</span><span class="num">${fmtNum(n)}</span><span class="bar"><i style="width:${(n / max) * 100}%"></i></span></div>`)
    .join("");
}

export function mount(root, ctx) {
  const today = todayTh();
  if (!date) date = today;
  const page = h(`
    <div>
      <div class="page-head">
        <h2>Reports</h2>
        <label class="field" style="flex-direction:row;align-items:center;gap:8px">Date <input type="date" id="r-date" style="width:auto"></label>
      </div>
      <div id="r-error" class="card error-box" hidden></div>
      <section class="report-grid">
        <div class="card kpi"><span class="kpi-label">Total violations</span><span class="kpi-value" id="r-total">—</span><span class="kpi-sub" id="r-total-sub">&nbsp;</span></div>
        <div class="card kpi"><span class="kpi-label">False alarm rate</span><span class="kpi-value" id="r-far">—</span><span class="kpi-sub" id="r-far-sub">&nbsp;</span></div>
        <div class="card kpi"><span class="kpi-label">Handled</span><span class="kpi-value" id="r-acked">—</span><span class="kpi-sub" id="r-open">&nbsp;</span></div>
        <div class="card kpi"><span class="kpi-label">Decided by FALLBACK</span><span class="kpi-value" id="r-fallback">—</span><span class="kpi-sub">not decided by CiRA</span></div>
      </section>
      <section class="card" style="margin-bottom:16px">
        <h3 class="card-title">Daily violations by type
          <span class="seg" role="group" aria-label="Period">
            <button type="button" data-days="7">7 days</button><button type="button" data-days="30">30 days</button>
          </span>
        </h3>
        <div class="chart-box"><canvas id="daily-chart" aria-label="Daily bar chart" role="img"></canvas></div>
        <div id="daily-msg" class="notice" hidden></div>
      </section>
      <div class="two-col">
        <section class="card"><h3 class="card-title">By camera</h3><div class="bars" id="by-cam"></div></section>
        <section class="card"><h3 class="card-title">By severity</h3><div class="bars" id="by-sev"></div></section>
      </div>
    </div>`);
  root.append(page);
  const $ = (s) => page.querySelector(s);
  const dateInput = $("#r-date");
  dateInput.value = date;
  dateInput.max = today;
  let chart = null;
  let alive = true;
  let summarySeq = 0;
  let dailySeq = 0;

  function showError(msg) {
    $("#r-error").hidden = !msg;
    $("#r-error").textContent = msg ? `Failed to load: ${msg}` : "";
  }

  async function loadSummary() {
    const seq = ++summarySeq;
    try {
      const s = await api.summary(date);
      if (!alive || seq !== summarySeq) return;
      showError("");
      renderSummary(s);
    } catch (e) {
      if (!alive || seq !== summarySeq) return;
      showError(e.detail || e.message);
      renderSummary(null);
    }
  }

  function renderSummary(s) {
    $("#r-total").textContent = s ? fmtNum(s.total) : "—";
    $("#r-total-sub").textContent = s ? `yesterday ${fmtNum(s.yesterday)}` : " ";
    if (s && s.false_alarm_rate !== null && s.false_alarm_rate !== undefined) {
      $("#r-far").textContent = fmtPct(Number(s.false_alarm_rate), 1);
      $("#r-far-sub").textContent = "false alarms ÷ handled";
    } else {
      $("#r-far").textContent = "—";
      $("#r-far-sub").textContent = s ? "nothing handled yet" : " ";
    }
    $("#r-acked").textContent = s ? fmtNum(s.acked) : "—";
    $("#r-open").textContent = s ? `pending ${fmtNum(s.open)}` : " ";
    $("#r-fallback").textContent = s ? fmtNum(s.fallback) : "—";

    const byCam = Object.entries(s?.by_camera || {})
      .sort(([a], [b]) => a.localeCompare(b, "en", { numeric: true }))
      .map(([id, n]) => [ctx.camName(id) === id ? id : `${ctx.camName(id)} (${id})`, Number(n) || 0]);
    $("#by-cam").innerHTML = s ? bars(byCam) : "";
    const bySevRaw = s?.by_severity || {};
    const sevKeys = [...new Set([...Object.keys(SEVERITIES), ...Object.keys(bySevRaw)])];
    $("#by-sev").innerHTML = s ? bars(sevKeys.map((k) => [severityLabel(k), Number(bySevRaw[k]) || 0, k]), severityColor) : "";
  }

  async function loadDaily() {
    const seq = ++dailySeq;
    page.querySelectorAll("[data-days]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.days) === days)));
    const msg = $("#daily-msg");
    try {
      const rows = await api.daily(days);
      if (!alive || seq !== dailySeq) return;
      msg.hidden = true;
      renderChart(Array.isArray(rows) ? rows : []);
    } catch (e) {
      if (!alive || seq !== dailySeq) return;
      msg.hidden = false;
      msg.className = "notice error-text";
      msg.textContent = `Failed to load chart: ${e.detail || e.message}`;
    }
  }

  function renderChart(rows) {
    const Chart = window.Chart;
    if (!Chart) {
      $("#daily-msg").hidden = false;
      $("#daily-msg").textContent = "Cannot load Chart.js (lib/chart.umd.min.js)";
      return;
    }
    const typeKeys = [...Object.keys(TYPES)];
    rows.forEach((r) => Object.keys(r).forEach((k) => k !== "date" && !typeKeys.includes(k) && typeKeys.push(k)));
    const labels = rows.map((r) => String(r.date ?? "").slice(5)); // MM-DD
    const datasets = typeKeys.map((k, i) => ({
      label: typeLabel(k),
      data: rows.map((r) => Number(r[k]) || 0),
      backgroundColor: TYPE_COLORS[k] || EXTRA_COLORS[i % EXTRA_COLORS.length],
      borderRadius: 3,
      maxBarThickness: 48,
    }));
    if (chart) {
      chart.data.labels = labels;
      chart.data.datasets = datasets;
      chart.update();
      return;
    }
    const grid = "rgba(148,163,184,.15)";
    chart = new Chart($("#daily-chart"), {
      type: "bar",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { stacked: true, ticks: { color: "#94a3b8" }, grid: { color: grid } },
          y: { stacked: true, beginAtZero: true, ticks: { color: "#94a3b8", precision: 0 }, grid: { color: grid } },
        },
        plugins: {
          legend: { labels: { color: "#e6edf7", boxWidth: 14 } },
          tooltip: { callbacks: { title: (items) => rows[items[0].dataIndex]?.date ?? "" } },
        },
      },
    });
  }

  dateInput.addEventListener("change", () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateInput.value)) return;
    date = dateInput.value;
    loadSummary();
  });
  page.querySelectorAll("[data-days]").forEach((b) =>
    b.addEventListener("click", () => {
      days = Number(b.dataset.days);
      loadDaily();
    })
  );

  loadSummary();
  loadDaily();

  // Today's numbers follow the app-wide summary refresh (timer + new events/acks); no extra polling.
  const offs = [
    ctx.on("summary", (s) => {
      if (s && date === s.date) {
        showError("");
        renderSummary(s);
      }
    }),
  ];
  // Daily chart changes slowly; refresh once a minute while the page is open
  const dailyTimer = setInterval(loadDaily, 60000);
  return () => {
    alive = false;
    offs.forEach((off) => off());
    clearInterval(dailyTimer);
    chart?.destroy();
  };
}
