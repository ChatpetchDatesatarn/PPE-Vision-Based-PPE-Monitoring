// #/live (v5 rev 5) — NVR-style grid: 1 / 2 / 4 / ทั้งหมด(32) slots (remembered). Real cameras fill the first
// slots; the rest are drawn as empty dark-grey channels so the screen always shows the chosen layout.
// Paging (‹ ›) appears only when there are more cameras than slots. Empty slots are static DOM (no player).
// v6.4: click a camera tile -> it opens as 1 ช่อง; "↩ กลับ" returns to the previous layout.
import { LS_KEYS } from "../config.js";
import { h, lsGet, lsSet, liveGrid, esc } from "../ui.js";

const SIZES = [1, 2, 4, 32];
const SIZE_LABEL = { 1: "1 view", 2: "2 views", 4: "4 views", 32: "All (32)" };
const ICON_NOCAM = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 012-2h9a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2zM16 10l5-3v10l-5-3z" opacity=".55"/><path d="M3.3 2.3l18.4 18.4-1.4 1.4L1.9 3.7z"/></svg>';

function emptySlot(ch) {
  const n = String(ch).padStart(2, "0");
  return h(`
    <div class="tile ph" aria-label="Channel ${n} empty">
      <div class="tile-head"><span class="dot"></span><span class="tile-name">CH ${n}</span><span class="live-badge">Empty</span></div>
      <div class="tile-video ph-video"><div class="ph-msg">${ICON_NOCAM}<span>No camera</span></div></div>
      <div class="tile-foot">Not connected</div>
    </div>`);
}

export function mount(root, ctx) {
  let size = Number(lsGet(LS_KEYS.GRID));
  if (!SIZES.includes(size)) size = 4;
  let pageIdx = 0;

  const page = h(`
    <div class="fit-page">
      <div class="page-head">
        <h2>Live View</h2>
        <div class="row">
          <button class="btn" id="back" type="button" hidden></button>
          <span class="muted small" id="live-range"></span>
          <button class="btn" id="prev" type="button" aria-label="Previous cameras">‹</button>
          <button class="btn" id="next" type="button" aria-label="Next cameras">›</button>
          <div class="seg" role="group" aria-label="Layout">
            ${SIZES.map((n) => `<button type="button" data-size="${n}">${SIZE_LABEL[n]}</button>`).join("")}
          </div>
        </div>
      </div>
      <div class="grid" id="live-grid"></div>
    </div>`);
  root.append(page);
  const $ = (s) => page.querySelector(s);
  const gridEl = $("#live-grid");
  const grid = liveGrid(gridEl, ctx, { detailed: true });
  let slots = []; // empty-slot elements currently on screen
  let backSize = null; // v6.4: layout to return to after a tile was clicked open

  function render() {
    const ids = ctx.camIds();
    const pages = Math.max(1, Math.ceil(ids.length / size));
    pageIdx = Math.min(pageIdx, pages - 1);
    const first = pageIdx * size;
    const shown = ids.slice(first, first + size);
    grid.sync(shown);                         // real tiles (appended in order)
    slots.forEach((el) => el.remove());       // then fill the rest of the layout with empty channels
    slots = [];
    for (let i = shown.length; i < size; i++) {
      const el = emptySlot(first + i + 1);
      slots.push(el);
      gridEl.append(el);
    }
    gridEl.className = `grid g${size}`;
    page.querySelectorAll("[data-size]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.size) === size)));
    const paged = ids.length > size;
    $("#prev").hidden = $("#next").hidden = !paged;
    $("#prev").disabled = pageIdx === 0;
    $("#next").disabled = pageIdx >= pages - 1;
    let range = !ids.length
      ? "No camera status yet"
      : paged
        ? (size === 1 ? `Camera ${first + 1} of ${ids.length}` : `Cameras ${first + 1}–${first + shown.length} of ${ids.length}`)
        : `${ids.length} camera(s) · ${size} view(s)`;
    if (size === 1 && shown[0]) range += ` · ${esc(ctx.camName(shown[0]))}`;
    $("#live-range").innerHTML = range;
    const back = $("#back");
    back.hidden = !(size === 1 && backSize);
    back.textContent = backSize ? `↩ Back to ${SIZE_LABEL[backSize]}` : "";
  }

  // v6.4: click a camera (not its buttons) to open it as 1 ช่อง
  gridEl.addEventListener("click", (e) => {
    if (size === 1 || e.target.closest("button, a, input")) return;
    const tile = e.target.closest(".tile[data-cam]");
    if (!tile) return;
    const idx = ctx.camIds().indexOf(tile.dataset.cam);
    if (idx < 0) return;
    backSize = size;
    size = 1;
    pageIdx = idx;
    render();
  });
  $("#back").addEventListener("click", () => {
    if (!backSize) return;
    size = backSize;
    pageIdx = Math.floor(pageIdx / size);
    backSize = null;
    render();
  });

  page.querySelectorAll("[data-size]").forEach((b) =>
    b.addEventListener("click", () => {
      const firstIdx = pageIdx * size;
      size = Number(b.dataset.size);
      pageIdx = Math.floor(firstIdx / size);
      backSize = null;
      lsSet(LS_KEYS.GRID, String(size));
      render();
    })
  );
  $("#prev").addEventListener("click", () => { pageIdx = Math.max(0, pageIdx - 1); render(); });
  $("#next").addEventListener("click", () => { pageIdx++; render(); });

  render();
  const offs = [
    ctx.on("cameras", render),
    ctx.on("status", () => grid.updateAll()),
    ctx.on("health", () => grid.updateAll()),
  ];
  return () => {
    offs.forEach((off) => off());
    grid.destroy();
    slots.forEach((el) => el.remove());
  };
}
