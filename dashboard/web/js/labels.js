// Thai labels and severity colours. Unknown values fall back to the raw value.

export const TYPES = {
  no_helmet: "No helmet",
  no_vest: "No safety vest",
  restricted_zone: "Restricted zone",
  unknown_visibility: "Unclear view",
};

export const SEVERITIES = {
  critical: { text: "Critical", color: "#DC2626" },
  high: { text: "High", color: "#EA580C" },
  warning: { text: "Warning", color: "#CA8A04" },
  info: { text: "Info", color: "#64748B" },
};

export const STATUSES = {
  open: "Pending",
  resolved: "Resolved",
  false_alarm: "False alarm",
};

export const FALLBACK_BADGE = "FALLBACK";

// Severities that trigger the alarm sound
export const SOUND_SEVERITIES = new Set(["critical", "high"]);

const raw = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));

export const typeLabel = (t) => TYPES[t] ?? raw(t);
export const statusLabel = (s) => STATUSES[s] ?? raw(s);
export const severityLabel = (s) => SEVERITIES[s]?.text ?? raw(s);
export const severityColor = (s) => SEVERITIES[s]?.color ?? SEVERITIES.info.color;
export const isFallback = (via) => via === "fallback";
export const viaLabel = (via) => (via === "fallback" ? FALLBACK_BADGE : via === "cira" ? "CiRA" : raw(via));
