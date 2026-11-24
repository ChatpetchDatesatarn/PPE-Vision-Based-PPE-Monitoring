# CiRA CORE — how it really works (decision layer notes)

CiRA CORE Horizon 1.9.4 (Education / Study version) on the Jetson. The flow `safety_decision_v1.npj` is the
decision layer: it reads `ds/violation` from DeepStream, decides which become events, and republishes them.

## The flow (9 nodes, one scene "Main")

Two independent chains:

**Decide chain** — `AutoRun(e272839b)` → `MqttSub(a1216de1)` → `JavaScript decide(a822739a)` → `IfElse(aa552471)` → `MqttPub(ab17bc21)`
- `MqttSub` subscribes `factory/safety/+/ds/violation` (qos 1). On each message it **wraps** the parsed
  payload as `{ "<subscribed topic>": <payload> }` and pushes it downstream as `payload`.
- `JavaScript decide` reads `payload`, decides, and **overwrites `payload`** in place: either the event
  fields, or `{cira_drop:true}` when nothing should be sent.
- `IfElse` (js_code `ifelse = ( payload.hasOwnProperty("event_id") )`) sends True only when the JS produced an
  event; the `cira_drop` case goes to False and stops. So only real events reach the MqttPub.
- `MqttPub` publishes to `factory/safety/cam01/event` (qos 1).

**Heartbeat chain** — `AutoRun(fd3ec321)` → `Delay(c645cf1d, 10000 ms)` → `JavaScript heartbeat(00c6c73c)` → `MqttPub(6eb6afbe)`
- `AutoRun` fires once when the flow runs; the `Delay` output loops back to the `Delay` input, so it
  self-repeats every 10 s. Each tick the JS fills `payload` with the status and `MqttPub` sends it to
  `factory/safety/cira/status`.

## Node behaviours worth knowing

- **AutoRun**: emits one token to start a chain. The **toggle** on the node = "auto-fire when the project
  loads"; the grey **Run** button = fire once now. The decide chain does not need AutoRun to keep working
  (MqttSub drives it on every message); the heartbeat chain needs its AutoRun to have fired at least once.
- **MqttSub / MqttPub**: hold their own broker connection and **auto-reconnect** if the broker restarts
  (verified, TEST_RESULTS case 9). Settings live in `model.mqtt_sub` / `model.mqtt_pub` (host, port, qos,
  topic). MqttSub drops a message that is not valid JSON before the JS runs.
- **IfElse**: a tiny JS that sets the boolean `ifelse`; True/False are two output pads.
- **Delay**: passes its input through after `delay_time` ms; used as the 10 s heartbeat timer by looping its
  output back to its input.
- **JavaScript**: QtScript (ES5 only). `payload` is the live message object (read and mutate it). Persistent
  state is through `setGlobal(name, string)` / `getGlobal(name)` / `hasGlobal(name)`; **values must be
  strings** (we `JSON.stringify` / `JSON.parse`). `print(...)` writes to the CiRA log (`/tmp/cira.log`).
  No `Date.prototype.toISOString`, no `setTimeout`, no `console`.

## The 4-bug chain we hit (and the fix now in the code)

1. **Wrong global API names.** First tries used `hasGlobalPayload`/… which do not exist → state never
   persisted. Fix: `hasGlobal` / `getGlobal` / `setGlobal`.
2. **`toISOString` unsupported in QtScript** → the JS threw and dropped the message. Fix: build the BKK
   timestamp by hand from `getUTC*` on a `Date` shifted by +7 h (`isoBkk` / `stampBkk`), no milliseconds.
3. **State stored as an object** came back unusable. Fix: store it as a **JSON string** via
   `setGlobal("decide_state", JSON.stringify(st))`.
4. **The JS→AutoRun→MqttSub echo loop.** After the decide JS writes the event onto `payload`, that object
   can still be sitting on top when the next message arrives, so a naive reader picked up the **old event**
   (which has `event_id`/`confidence`) instead of the new violation (which has `conf`). Fix: `findViolation`
   looks under the `".../ds/violation"` key first, then other keys, then `payload` itself; and `isViolation`
   **rejects any object that has `event_id`**, so a stale event can never re-fire.

## Editing a JavaScript node from the terminal (`npj_tool.py`)

The `.npj` is nested JSON (outer `scene_array[].data` is itself a JSON string). Never hand-edit it. Use
`tools/npj_tool.py` (Python 3.6, stdlib only; it re-serialises exactly the way CiRA/Qt does and backs up
to `<file>.npj.bak-…` first):

```
python3 npj_tool.py list    safety_decision_v1.npj
python3 npj_tool.py get-js  safety_decision_v1.npj a822739a-da67-4f50-9cad-141404225c9c > src/cira_node_decide.js
python3 npj_tool.py set-js  safety_decision_v1.npj a822739a-da67-4f50-9cad-141404225c9c src/cira_node_decide.js
python3 npj_tool.py set     safety_decision_v1.npj MqttPub topic factory/safety/cam01/event
python3 npj_tool.py del-node safety_decision_v1.npj <id>
```

When only one node has a type you may use the type name (`MqttSub`, `JavaScript`); when several share it, use
the `{uuid}`. Node ids: decide `a822739a…`, heartbeat `00c6c73c…`, MqttPub event `ab17bc21…`, MqttPub status
`6eb6afbe…`, MqttSub `a1216de1…`, IfElse `aa552471…`, Delay `c645cf1d…`, AutoRun `e272839b…` (decide) /
`fd3ec321…` (heartbeat).

## The Save-Project trap

CiRA's **Save Project** overwrites the `.npj` with the **in-memory** flow. If you `set-js` on disk but the GUI
still has the old (or empty) node, saving will blank your change. Safe order: edit `src/*.js` → test on Node →
`npj_tool set-js` → in the GUI **Open Project** (so the new code loads into the node) → only then Save, and
only if you must. We normally do **not** press Save; `set-js` + Open Project is enough to run the new code.
