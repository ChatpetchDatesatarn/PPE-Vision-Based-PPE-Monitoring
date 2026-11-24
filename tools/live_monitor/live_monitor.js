// Headless live-video monitor for the Dashboard stream (PC side, Node stdlib only + installed Chrome/Edge).
// Opens a WebRTC (WHEP) session through nginx like the Dashboard does and writes one row every <interval> s.
//
// Usage:
//   node live_monitor.js --csv <out.csv> [--minutes 30] [--interval 10] [--base http://<JETSON_TAILSCALE_IP>:8080]
//                        [--path cam01] [--browser <chrome.exe or msedge.exe>]
//   --minutes 0 = run until Ctrl-C.
// Columns: timestamp, connected, time_to_first_frame_s (current session), framesDecoded, framesPerSecond
// (average over the interval), freezeCount, totalFreezesDuration_s, keyFramesDecoded, packetsLost (all
// cumulative across reconnects), reconnects, last_frame_age_s (seconds since the picture last changed).
// Session failures go to <out>.events.log.
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execSync } = require("child_process");

function arg(name, def) {
  const i = process.argv.indexOf("--" + name);
  return i > 0 && i + 1 < process.argv.length ? process.argv[i + 1] : def;
}
const CSV = arg("csv");
if (!CSV) { console.error("usage: node live_monitor.js --csv <out.csv> [--minutes N] [--interval S] [--base URL] [--path cam01]"); process.exit(2); }
const MINUTES = parseFloat(arg("minutes", "30"));
const INTERVAL_S = parseFloat(arg("interval", "30"));   // v4 item4: 30 s default (lighter on the PC)
const BASE = arg("base", "http://<JETSON_TAILSCALE_IP>:8080").replace(/\/$/, "");
const STREAM = arg("path", "cam01");
const BROWSERS = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
];
const BROWSER = arg("browser", BROWSERS.find((b) => fs.existsSync(b)));
const HTML = path.join(__dirname, "whep_monitor.html");
const EVENTS = CSV.replace(/\.csv$/, "") + ".events.log";
const COLS = ["timestamp", "connected", "time_to_first_frame_s", "framesDecoded", "framesPerSecond", "freezeCount",
  "totalFreezesDuration_s", "keyFramesDecoded", "packetsLost", "reconnects", "last_frame_age_s",
  "stalled", "stalled_total_s", "decoded_fps_10s"];   // v4 item4: stall tracking

// v4 item4: kill any leftover headless Chrome/Edge from a previous monitor run (matched by its temp profile)
try {
  execSync('powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \'*live_monitor_*\' -and ($_.Name -eq \'chrome.exe\' -or $_.Name -eq \'msedge.exe\') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"',
    { stdio: "ignore" });
} catch (e) {}

if (!fs.existsSync(CSV) || fs.statSync(CSV).size === 0) fs.writeFileSync(CSV, COLS.join(",") + "\n");
let rows = 0, lastRowAt = Date.now(), browser = null;
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "live_monitor_"));

const srv = http.createServer((req, res) => {
  if (req.method === "POST" && req.url === "/log") {
    let b = "";
    req.on("data", (d) => (b += d));
    req.on("end", () => {
      try {
        const o = JSON.parse(b);
        if (o.event) {
          fs.appendFileSync(EVENTS, o.ts + " " + o.event + " " + o.detail + "\n");
          console.log(o.ts, o.event, o.detail);
        } else {
          fs.appendFileSync(CSV, COLS.map((c) => (o[c] === undefined ? "" : o[c])).join(",") + "\n");
          rows++; lastRowAt = Date.now();
          console.log(COLS.map((c) => c + "=" + o[c]).join(" "));
        }
      } catch (e) {}
      res.writeHead(204); res.end();
    });
    return;
  }
  res.writeHead(200, { "Content-Type": "text/html" });
  res.end(fs.readFileSync(HTML));
});

srv.listen(0, "127.0.0.1", () => {
  const port = srv.address().port;
  const target = BASE + "/webrtc/" + STREAM + "/whep";
  const url = "http://127.0.0.1:" + port + "/?target=" + encodeURIComponent(target) +
    "&sink=" + encodeURIComponent("http://127.0.0.1:" + port + "/log") + "&interval=" + INTERVAL_S * 1000;
  // --disable-web-security: the page on 127.0.0.1 posts WHEP to the Jetson origin (isolated temp profile only)
  browser = spawn(BROWSER, ["--headless=new", "--disable-gpu", "--disable-web-security", "--user-data-dir=" + profile,
    "--autoplay-policy=no-user-gesture-required", "--no-first-run", "--no-default-browser-check", url],
  { stdio: "ignore" });
  console.log("monitor " + target + " -> " + CSV + " (" + (MINUTES ? MINUTES + " min" : "until Ctrl-C") + ", browser pid " + browser.pid + ")");
});

// a dead page (browser crash) shows up as a row with connected=no-report instead of a silent gap
const watchdog = setInterval(() => {
  if (Date.now() - lastRowAt > 3 * INTERVAL_S * 1000) {
    fs.appendFileSync(CSV, [new Date().toISOString(), "no-report"].concat(COLS.slice(2).map(() => "")).join(",") + "\n");
    lastRowAt = Date.now();
  }
}, INTERVAL_S * 1000);

function stop() {
  clearInterval(watchdog);
  if (browser && browser.exitCode === null) {
    try { execSync("taskkill /PID " + browser.pid + " /T /F", { stdio: "ignore" }); } catch (e) { browser.kill(); }
  }
  srv.close();
  setTimeout(() => { try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {} console.log("done, rows=" + rows); process.exit(0); }, 1500);
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
if (MINUTES > 0) setTimeout(stop, MINUTES * 60 * 1000 + 2000);
