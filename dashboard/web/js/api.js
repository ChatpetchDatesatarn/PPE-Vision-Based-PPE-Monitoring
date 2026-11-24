// Every call to the recorder HTTP API (/api/...). Relative paths only.

const TIMEOUT_MS = 10000;

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

function buildUrl(path, params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const qs = q.toString();
  return qs ? `${path}?${qs}` : path;
}

async function getJson(path, params) {
  return requestJson(buildUrl(path, params), { headers: { Accept: "application/json" } });
}

// v6: POST with a JSON body (used by delete, which also sends the X-Delete-Pin header)
async function postJson(path, body, headers = {}) {
  return requestJson(path, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

async function requestJson(url, init) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    throw new ApiError(0, e.name === "AbortError" ? "API not responding (timeout)" : "Cannot reach the API");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `API returned ${res.status}`);
  }
  try {
    return await res.json();
  } catch {
    throw new ApiError(res.status, "API sent unreadable data");
  }
}

export const api = {
  health: () => getJson("/api/health"),
  events: (params) => getJson("/api/events", params),
  event: (id) => getJson(`/api/events/${encodeURIComponent(id)}`),
  summary: (date) => getJson("/api/stats/summary", { date }),
  daily: (days) => getJson("/api/stats/daily", { days }),
  exportCsvUrl: (from, to) => buildUrl("/api/export.csv", { from, to }),
  // v6: permanent delete (recorder checks the PIN)
  deleteEvents: (eventIds, pin) => postJson("/api/events/delete", { event_ids: eventIds }, { "X-Delete-Pin": pin }),
  deleteRange: (from, to, pin) => postJson("/api/events/delete-range", { from, to }, { "X-Delete-Pin": pin }),
};
