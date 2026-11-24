// ===== JavaScript node: heartbeat (ES5 for CiRA / QtScript), runs every 10 s via Delay -> cira/status =====
function pad2(n) { var s = String(n); return s.length < 2 ? "0" + s : s; }
function isoBkk(ms) {
  var d = new Date(ms + 7 * 3600 * 1000);          // QtScript has no Date.prototype.toISOString
  return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-" + pad2(d.getUTCDate()) + "T" +
         pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) + ":" + pad2(d.getUTCSeconds()) + "+07:00";
}
function clearObject(o) { for (var k in o) if (o.hasOwnProperty(k)) delete o[k]; }

try {
  var st = null;
  if (hasGlobal("decide_state")) st = getGlobal("decide_state");
  if (typeof st === "string") { try { st = JSON.parse(st); } catch (e) { st = null; } }
  if (!st || typeof st !== "object") st = { received: 0, published: 0, filtered: 0, last_rx: "" };
  clearObject(payload);
  payload.online = true;
  payload.ts = isoBkk(Date.now());
  payload.flow = "safety_decision_v1";
  payload.received = st.received || 0;
  payload.published = st.published || 0;
  payload.filtered = st.filtered || 0;
  payload.last_rx = st.last_rx || "";
} catch (e) {
  print("ERROR heartbeat: " + e + "\n");
}
