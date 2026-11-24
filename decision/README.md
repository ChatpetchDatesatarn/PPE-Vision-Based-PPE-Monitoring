# CiRA CORE decision engine — operating guide

CiRA CORE (Horizon 1.9.4) runs the safety decision flow `safety_decision_v1.npj`. It subscribes to
`factory/safety/+/ds/violation` from DeepStream, decides, and republishes to `factory/safety/cam01/event`
(`via: "cira"`), plus a `cira/status` heartbeat every 10 s.

CiRA runs headless on the Jetson: no HDMI, no monitor. A virtual display (Xvfb `:99`) stands in for the
screen, and the GUI is reached over VNC through an SSH tunnel only when a human needs to click. Everything
lives in the tmux session `cira-gui`.

## Start CiRA after a reboot

CiRA has **no working command-line auto-load or auto-run** (see Limitations). The project must be opened and
run by hand in the GUI once, after that it keeps running until stopped. Steps:

1. `./cira-start` — starts a fresh Xvfb `:99` and launches CiRA at `nice -n 19`. (If CiRA is already
   running it does nothing and leaves Xvfb alone.)
2. `./ds-vnc-on` — starts x11vnc on `127.0.0.1:5900` (localhost only).
3. On the PC, open an SSH tunnel and connect a VNC client to `localhost:5900`:
   ```
   ssh -o HostName=<JETSON_TAILSCALE_IP> -L 5900:localhost:5900 jetson
   ```
   (The VNC password was set once with `x11vnc -storepasswd`.)
4. In the GUI: **Open Project** `/home/jetson/safety/decision/safety_decision_v1.npj`.
5. Press **Run** on both **AutoRun** nodes (ids `e272839b…` and `fd3ec321…`).
6. `./ds-vnc-off` — stop x11vnc when you are done looking. CiRA keeps running without it.

Stop CiRA with `./cira-stop` (SIGINT, wait 10 s, then SIGTERM). It does not touch Xvfb, the DeepStream
app, or the tmux session.

## Verify it works

- `mosquitto_sub -h 127.0.0.1 -t factory/safety/cira/status -v` — a heartbeat must arrive **every 10 s**. Its
  JSON shows `online: true`, `flow: "safety_decision_v1"`, and running counts (`received`, `published`,
  `filtered`, `last_rx`). (`docs/mqtt_spec.md` defines the prefix `factory/safety/`, so the spec's
  `cira/status` is exactly this `factory/safety/cira/status` — they match.)
- In the GUI the **Decision** (JavaScript) node and the AutoRun nodes show **green** while running.
- Feed a clip with violations and watch `factory/safety/cam01/event` — events must carry `via: "cira"`.

## Known problem: Xvfb wedged

A long-lived Xvfb `:99` (left running for days) stops accepting new Qt xcb connections. CiRA then aborts at
startup with:

```
qt.qpa.xcb: could not connect to display :99
```

`xdpyinfo` can still connect, so the display looks alive, but new Qt clients cannot attach. Fix: restart
Xvfb fresh. `./cira-start` now does this automatically whenever it starts CiRA (it kills and restarts
`Xvfb :99` first, as long as CiRA is not already running). To do it by hand:

```
pkill -f "Xvfb :99"; ./cira-start
```

A fresh Xvfb (e.g. right after a reboot) does not have this problem.

## Limitations

- **No CLI auto-load / auto-run.** `cira_core_launch` (the only launcher that connects to the display) does
  not accept a `.npj` file argument. `cira_core_run` does accept the file but cannot initialise Qt xcb on its
  own and aborts. There is no `autorun`/headless flag, and the config remembers only the last file-dialog
  folder, not a project to auto-open. So the GUI steps 4–5 above are required after every `cira-start`.
- **Fallback while CiRA is not Run.** Until the project is opened and Run is pressed, CiRA publishes nothing.
  During that window DeepStream's own fallback path (`person_count_app.py`, events on) produces the events
  directly (`via: "fallback"`). Keep DeepStream running so coverage is never lost while CiRA is being brought
  up. When CiRA is Run, it takes over and events become `via: "cira"`.
- `nice -n 19` is re-applied by `cira-start` on every launch; it resets if CiRA is restarted any other way.

## Files

- `safety_decision_v1.npj` — production flow (decide `DEBUG=false`, Debug nodes removed, heartbeat every 10 s).
- `src/cira_node_decide.js`, `src/cira_node_heartbeat.js` — the JavaScript node bodies (ES5 / QtScript), edited
  on disk and pushed into the flow with `../tools/npj_tool.py set-js`. Do not use `toISOString`/`setTimeout`
  (unsupported by QtScript); timestamps are built from `getUTC*`.
- After editing a node with `npj_tool.py`, CiRA must **Open Project** (so the code loads into the GUI) before
  it will **Save Project**; saving with the GUI node empty would blank the pushed code.

`test_flow.npj` is a throwaway scratch flow — not used in production, do not rely on it.
