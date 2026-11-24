// Unit tests for the CiRA decide / heartbeat JavaScript nodes, run on Node with `vm`.
// The nodes are ES5 QtScript: they read a free variable `payload`, and call hasGlobal / getGlobal /
// setGlobal / print and Date.now(). This harness provides those, runs each node in an isolated vm
// context (one context = one incoming MQTT message), and keeps a shared global store across runs so
// cooldown and the running counters behave exactly as they do inside CiRA.
//
// Run: node tests/test_decide_es5.js        (exit 0 = all pass, non-zero = a failure)
"use strict";
var fs = require("fs");
var vm = require("vm");
var path = require("path");

var DECIDE = fs.readFileSync(path.join(__dirname, "..", "src", "cira_node_decide.js"), "utf8");
var HEART = fs.readFileSync(path.join(__dirname, "..", "src", "cira_node_heartbeat.js"), "utf8");

// A CiRA-like world: one global store (values are strings, as setGlobal/getGlobal store them) that
// survives between messages, plus a captured print log.
function World() {
  this.globals = {};
  this.prints = [];
}
World.prototype.api = function (nowMs) {
  var self = this;
  // Date wrapper: new Date(ms) behaves normally (getUTC* needed), Date.now() is frozen to nowMs.
  var RealDate = Date;
  function DateWrap(a) { return arguments.length ? new RealDate(a) : new RealDate(nowMs); }
  DateWrap.now = function () { return nowMs; };
  DateWrap.UTC = RealDate.UTC;
  return {
    hasGlobal: function (k) { return Object.prototype.hasOwnProperty.call(self.globals, k); },
    getGlobal: function (k) { return self.globals[k]; },
    setGlobal: function (k, v) { self.globals[k] = v; },
    print: function (s) { self.prints.push(String(s)); },
    Date: DateWrap, JSON: JSON, String: String, Number: Number, Object: Object, Array: Array
  };
};
// Run a node once with the given incoming payload object; returns the payload object after the node ran.
World.prototype.run = function (src, payloadObj, nowMs) {
  var ctx = this.api(nowMs);
  ctx.payload = payloadObj;
  vm.createContext(ctx);
  vm.runInContext(src, ctx, { filename: "node.js" });
  return ctx.payload;
};
World.prototype.state = function () { return JSON.parse(this.globals["decide_state"]); };

// ---- tiny assert runner --------------------------------------------------
var passed = 0, failed = 0;
function ok(name, cond, detail) {
  if (cond) { passed++; console.log("PASS  " + name); }
  else { failed++; console.log("FAIL  " + name + (detail ? "  -> " + detail : "")); }
}
function isEvent(p) { return p && !p.cira_drop && typeof p.event_id === "string"; }

// A real ds/violation payload, as DeepStream sends it.
function viol(o) {
  var v = { camera_id: "cam01", type: "no_helmet", track_id: 7, conf: 0.82,
            zone_id: "", bbox: [0.1, 0.1, 0.2, 0.5], snapshot_id: "", repeat: 0 };
  for (var k in o) if (o.hasOwnProperty(k)) v[k] = o[k];
  return v;
}
// CiRA MqttSub wraps the message as { "<subscribed topic>": <payload> }.
function wrap(v, topic) {
  var o = {}; o[topic || "factory/safety/cam01/ds/violation"] = v; return o;
}
// epoch for 2026-10-21T20:38:02+07:00  (= 13:38:02 UTC)
var T0 = Date.UTC(2026, 9, 21, 13, 38, 2);

// 1. no_helmet conf 0.82 -> one high event, id ...-nh
(function () {
  var w = new World();
  var p = w.run(DECIDE, wrap(viol({ conf: 0.82 })), T0);
  ok("1 no_helmet 0.82 -> event high nh",
     isEvent(p) && p.severity === "high" && p.via === "cira" && /-nh$/.test(p.event_id),
     JSON.stringify(p));
})();

// 2. no_helmet conf 0.39 (< 0.40) -> no event
(function () {
  var w = new World();
  var p = w.run(DECIDE, wrap(viol({ conf: 0.39 })), T0);
  ok("2 no_helmet 0.39 -> filtered", !isEvent(p) && p.cira_drop === true, JSON.stringify(p));
})();

// 3. same person every 5 s for 40 s -> 2 events (cooldown 30 s): fires at 0 s and 30 s, not 5/10/.../25/35
(function () {
  var w = new World(), events = 0;
  for (var t = 0; t <= 40; t += 5) {
    var p = w.run(DECIDE, wrap(viol({ track_id: 7 })), T0 + t * 1000);
    if (isEvent(p)) events++;
  }
  ok("3 repeat 5s for 40s -> 2 events (cooldown 30s)", events === 2, "events=" + events);
})();

// 4. no_helmet + no_vest in the same second -> 2 events, different ids
(function () {
  var w = new World();
  var a = w.run(DECIDE, wrap(viol({ type: "no_helmet", track_id: 7, conf: 0.8 })), T0);
  var b = w.run(DECIDE, wrap(viol({ type: "no_vest", track_id: 7, conf: 0.8 })), T0);
  ok("4 nh+nv same second -> 2 distinct event_id",
     isEvent(a) && isEvent(b) && a.event_id !== b.event_id && /-nh$/.test(a.event_id) && /-nv$/.test(b.event_id),
     a.event_id + " / " + b.event_id);
})();

// 5. two different tracks at once -> 2 events
(function () {
  var w = new World();
  var a = w.run(DECIDE, wrap(viol({ track_id: 7 })), T0);
  var b = w.run(DECIDE, wrap(viol({ track_id: 12 })), T0);
  ok("5 two tracks -> 2 distinct events",
     isEvent(a) && isEvent(b) && a.event_id !== b.event_id && /-007-nh$/.test(a.event_id) && /-012-nh$/.test(b.event_id),
     a.event_id + " / " + b.event_id);
})();

// 6. restricted_zone with zone_id -> critical, zone_id preserved
(function () {
  var w = new World();
  var p = w.run(DECIDE, wrap(viol({ type: "restricted_zone", zone_id: "zone-a", conf: 0.5 })), T0);
  ok("6 restricted_zone -> critical + zone_id",
     isEvent(p) && p.severity === "critical" && p.zone_id === "zone-a" && /-rz$/.test(p.event_id),
     JSON.stringify(p));
})();

// 7. unknown_visibility is disabled -> no event even at high conf
(function () {
  var w = new World();
  var p = w.run(DECIDE, wrap(viol({ type: "unknown_visibility", conf: 0.9 })), T0);
  ok("7 unknown_visibility disabled -> filtered", !isEvent(p) && p.cira_drop === true, JSON.stringify(p));
})();

// 8a. broken JSON string under the topic key -> no event, no crash
(function () {
  var w = new World();
  var p = w.run(DECIDE, wrap("{not valid json", "factory/safety/cam01/ds/violation"), T0);
  var okNoCrash = !isEvent(p) && p.cira_drop === true && w.prints.length === 0; // catch would print ERROR
  // 8b. the very next message still produces an event (flow did not die)
  var p2 = w.run(DECIDE, wrap(viol({ conf: 0.82 })), T0 + 1000);
  ok("8 broken JSON -> filtered, no crash, next msg still works",
     okNoCrash && isEvent(p2), "prints=" + JSON.stringify(w.prints));
})();

// 8c. missing track_id -> no event
(function () {
  var w = new World();
  var v = viol({}); delete v.track_id;
  var p = w.run(DECIDE, wrap(v), T0);
  ok("8c missing track_id -> filtered", !isEvent(p) && p.cira_drop === true, JSON.stringify(p));
})();

// stale: previous event still on top of payload (JS->AutoRun->MqttSub loop), real violation under the topic key
(function () {
  var w = new World();
  var stale = { event_id: "cam01-20261021-203801-007-nh", confidence: 0.9, via: "cira", type: "no_helmet" };
  var msg = wrap(viol({ track_id: 7, conf: 0.82 }));
  for (var k in stale) if (stale.hasOwnProperty(k)) msg[k] = stale[k]; // stale fields at top level
  var p = w.run(DECIDE, msg, T0);
  ok("S stale event on top ignored, real one under ds/violation used",
     isEvent(p) && p.confidence === 0.82 && p.event_id !== stale.event_id, JSON.stringify(p));
})();

// stale only, no real violation -> filtered (the loop echo must not re-fire)
(function () {
  var w = new World();
  var p = w.run(DECIDE, { event_id: "cam01-20261021-203801-007-nh", confidence: 0.9, type: "no_helmet" }, T0);
  ok("S2 stale event alone -> filtered", !isEvent(p) && p.cira_drop === true, JSON.stringify(p));
})();

// 12. ts / event_id are BKK wall-clock with NO milliseconds
(function () {
  var w = new World();
  var p = w.run(DECIDE, wrap(viol({ track_id: 7, conf: 0.82 })), T0);
  ok("12 ts no milliseconds",
     /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$/.test(p.ts), p.ts);
  ok("12 event_id stamp no milliseconds",
     p.event_id === "cam01-20261021-203802-007-nh", p.event_id);
})();

// 11. received == published + filtered after a mixed run
(function () {
  var w = new World();
  w.run(DECIDE, wrap(viol({ track_id: 7, conf: 0.82 })), T0);        // published
  w.run(DECIDE, wrap(viol({ track_id: 7, conf: 0.39 })), T0 + 1000); // filtered (low conf)
  w.run(DECIDE, wrap(viol({ track_id: 8, conf: 0.82 })), T0 + 2000); // published
  var st = w.state();
  ok("11 received == published + filtered",
     st.received === st.published + st.filtered && st.received === 3, JSON.stringify(st));
})();

// heartbeat: reflects the decide counters, online true, ts no ms
(function () {
  var w = new World();
  w.run(DECIDE, wrap(viol({ track_id: 7, conf: 0.82 })), T0);
  w.run(DECIDE, wrap(viol({ track_id: 7, conf: 0.39 })), T0 + 1000);
  var hb = w.run(HEART, {}, T0 + 5000);
  var st = w.state();
  ok("H heartbeat fields + counters match state",
     hb.online === true && hb.flow === "safety_decision_v1" &&
     hb.received === st.received && hb.published === st.published && hb.filtered === st.filtered &&
     /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$/.test(hb.ts), JSON.stringify(hb));
})();

console.log("\n" + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
