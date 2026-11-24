// v6: small stacked dialogs (confirm / PIN / forms). Sits above the event modal. No imports (avoids cycles).
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

/**
 * Generic dialog. onOk(form, msgEl) may be async; return false to keep it open, anything else closes
 * and resolves with that value (true if undefined). Throwing shows the error and keeps it open.
 * Resolves null on cancel / Esc / backdrop click.
 */
export function dialog({ title, html, okText = "OK", danger = false, onOk = () => true }) {
  return new Promise((resolve) => {
    const el = h(`
      <div class="dlg-backdrop">
        <form class="dlg" role="dialog" aria-modal="true" aria-label="${esc(title)}" novalidate>
          <h3 class="dlg-title">${esc(title)}</h3>
          <div class="dlg-body">${html}</div>
          <p class="dlg-msg" role="status"></p>
          <div class="dlg-actions">
            <button type="button" class="btn" data-cancel>Cancel</button>
            <button type="submit" class="btn ${danger ? "btn-danger-solid" : "btn-primary"}">${esc(okText)}</button>
          </div>
        </form>
      </div>`);
    document.body.append(el);
    const form = el.querySelector("form");
    const msg = el.querySelector(".dlg-msg");
    const ok = form.querySelector('[type="submit"]');
    let busy = false;
    const close = (v) => {
      document.removeEventListener("keydown", onKey, true);
      el.remove();
      resolve(v);
    };
    // capture phase: Esc closes only this dialog, not the event modal underneath
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      if (!busy) close(null);
    };
    document.addEventListener("keydown", onKey, true);
    el.addEventListener("click", (e) => {
      if (busy) return;
      if (e.target === el || e.target.closest("[data-cancel]")) close(null);
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      busy = true;
      ok.disabled = true;
      msg.className = "dlg-msg";
      msg.textContent = "Working…";
      try {
        const r = await onOk(form, msg);
        if (r === false) {
          busy = false;
          ok.disabled = false;
          return;
        }
        close(r === undefined ? true : r);
      } catch (err) {
        msg.className = "dlg-msg error";
        msg.textContent = err?.detail || err?.message || String(err);
        busy = false;
        ok.disabled = false;
      }
    });
    (form.querySelector("input:not([type=hidden]), select, textarea") || ok).focus();
  });
}

// PIN is kept in memory only (never in storage) for 10 minutes so several deletes need one entry.
let pinCache = { pin: "", until: 0 };
const PIN_KEEP_MS = 10 * 60 * 1000;

/** Ask for the delete PIN and run doDelete(pin). Resolves the API result, or null if cancelled. */
export function deleteWithPin({ title, summaryHtml, doDelete }) {
  const cached = pinCache.until > Date.now() ? pinCache.pin : "";
  return dialog({
    title,
    danger: true,
    okText: "Delete permanently",
    html: `${summaryHtml}
      <p class="dlg-warn">This cannot be undone — the event data and snapshot images are deleted</p>
      <label class="field">Delete PIN
        <input type="password" name="pin" inputmode="numeric" autocomplete="off" required maxlength="32" value="${esc(cached)}">
      </label>`,
    onOk: async (form) => {
      const pin = form.pin.value.trim();
      if (!pin) throw new Error("Please enter the PIN");
      try {
        const res = await doDelete(pin);
        pinCache = { pin, until: Date.now() + PIN_KEEP_MS };
        return res;
      } catch (e) {
        if (e.status === 401 || e.status === 429 || e.status === 403) pinCache = { pin: "", until: 0 };
        // the recorder answers in Thai; show English on the dashboard
        if (e.status === 401) throw new Error("Wrong PIN");
        if (e.status === 429) {
          const sec = /(\d+)/.exec(String(e.detail || ""))?.[1];
          throw new Error(`Too many wrong PINs — try again${sec ? ` in ${sec} s` : " later"}`);
        }
        if (e.status === 403) throw new Error("Delete is disabled: no DELETE_PIN set on the device");
        throw e;
      }
    },
  });
}
