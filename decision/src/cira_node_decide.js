// ===== JavaScript node: decide (ES5 for CiRA / QtScript) =====
var CONFIG = {
  minConf: { no_helmet: 0.40, no_vest: 0.35, restricted_zone: 0.30, unknown_visibility: 0.30 },
  enabled: { no_helmet: true, no_vest: true, restricted_zone: true, unknown_visibility: false },
  cooldownS: 30,
  severity: { restricted_zone: "critical", no_helmet: "high", no_vest: "warning", unknown_visibility: "info" },
  code: { no_helmet: "nh", no_vest: "nv", restricted_zone: "rz", unknown_visibility: "uv" }
};
var DEBUG = false;

function pad2(n) { var s = String(n); return s.length < 2 ? "0" + s : s; }
function pad3(n) { var s = String(n); while (s.length < 3) s = "0" + s; return s; }

// BKK (+07:00) wall-clock parts of an epoch, built by hand (QtScript has no Date.prototype.toISOString).
function bkkParts(ms) {
  var d = new Date(ms + 7 * 3600 * 1000);          // shift, then read UTC fields = BKK local fields
  return { Y: String(d.getUTCFullYear()), Mo: pad2(d.getUTCMonth() + 1), D: pad2(d.getUTCDate()),
           H: pad2(d.getUTCHours()), Mi: pad2(d.getUTCMinutes()), S: pad2(d.getUTCSeconds()) };
}
function isoBkk(ms) {
  var b = bkkParts(ms);
  return b.Y + "-" + b.Mo + "-" + b.D + "T" + b.H + ":" + b.Mi + ":" + b.S + "+07:00";
}
function stampBkk(ms) {                              // YYYYMMDD-HHMMSS for event_id, no regex
  var b = bkkParts(ms);
  return b.Y + b.Mo + b.D + "-" + b.H + b.Mi + b.S;
}

function decide(v, lastSent, nowMs) {
  if (!v || typeof v.camera_id !== "string" || typeof v.type !== "string" ||
      typeof v.track_id !== "number" || typeof v.conf !== "number" ||
      !CONFIG.code.hasOwnProperty(v.type)) return null;
  if (v.conf < CONFIG.minConf[v.type]) return null;
  if (CONFIG.enabled[v.type] !== true) return null;
  var key = v.camera_id + "|" + v.track_id + "|" + v.type;
  if (lastSent.hasOwnProperty(key) && nowMs - lastSent[key] < CONFIG.cooldownS * 1000) return null;
  lastSent[key] = nowMs;
  return {
    event_id: v.camera_id + "-" + stampBkk(nowMs) + "-" + pad3(v.track_id) + "-" + CONFIG.code[v.type],
    ts: isoBkk(nowMs), camera_id: v.camera_id, zone_id: v.zone_id || "", type: v.type,
    severity: CONFIG.severity[v.type], track_id: v.track_id, confidence: v.conf,
    bbox: v.bbox || [], snapshot_id: v.snapshot_id || "", via: "cira"
  };
}

// A real violation: has conf (not a stale event, which carries event_id / confidence from the JS->AutoRun->MqttSub loop).
function isViolation(x) {
  return !!x && typeof x === "object" && !x.hasOwnProperty("event_id") &&
         typeof x.camera_id === "string" && typeof x.type === "string" &&
         typeof x.track_id === "number" && typeof x.conf === "number";
}
function endsWithDsViolation(k) {
  var suf = "/ds/violation";
  return k.length >= suf.length && k.substring(k.length - suf.length) === suf;
}
// CiRA MqttSub wraps the new message as { "<subscribed topic>": <parsed payload> }. The loop leaves the previous
// event at the top level, so look under a ".../ds/violation" key first, then other keys, then p itself last.
function findViolation(p) {
  var c = [];
  if (p && typeof p === "object") {
    for (var k in p) if (p.hasOwnProperty(k) && endsWithDsViolation(k)) c.push(p[k]);
    for (var k2 in p) if (p.hasOwnProperty(k2) && !endsWithDsViolation(k2)) c.push(p[k2]);
  }
  c.push(p);
  for (var j = 0; j < c.length; j++) {
    var x = c[j];
    if (typeof x === "string") { try { x = JSON.parse(x); } catch (e) { continue; } }
    if (isViolation(x)) return x;
  }
  return null;
}

function loadState() {
  var s = null;
  if (hasGlobal("decide_state")) s = getGlobal("decide_state");
  if (typeof s === "string") { try { s = JSON.parse(s); } catch (e) { s = null; } }
  if (!s || typeof s !== "object") s = { lastSent: {}, received: 0, published: 0, filtered: 0, last_rx: "" };
  return s;
}

function clearObject(o) { for (var k in o) if (o.hasOwnProperty(k)) delete o[k]; }

var stage = "start";
try {
  var now = Date.now();
  stage = "load_state"; var st = loadState();
  st.received = st.received + 1;
  st.last_rx = isoBkk(now);
  stage = "find"; var v = findViolation(payload);
  stage = "decide"; var ev = decide(v, st.lastSent, now);
  if (ev) st.published = st.published + 1; else st.filtered = st.filtered + 1;
  stage = "save_state";
  for (var ck in st.lastSent) {
    if (st.lastSent.hasOwnProperty(ck) && now - st.lastSent[ck] > CONFIG.cooldownS * 1000) delete st.lastSent[ck];
  }
  setGlobal("decide_state", JSON.stringify(st));
  if (DEBUG) print((ev ? "EVENT " + ev.event_id : "filtered") +
                   "  rx=" + st.received + " pub=" + st.published + " filt=" + st.filtered + "\n");
  stage = "write_payload";
  clearObject(payload);
  if (ev) {
    for (var f in ev) if (ev.hasOwnProperty(f)) payload[f] = ev[f];
  } else {
    payload.cira_drop = true;
  }
} catch (e) {
  clearObject(payload);
  payload.cira_drop = true;
  print("ERROR decide: " + e + " line=" + e.lineNumber + " stage=" + stage + "\n");
}
