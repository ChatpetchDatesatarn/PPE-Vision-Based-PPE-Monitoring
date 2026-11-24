// WHEP player for MediaMTX (via nginx at /webrtc/<stream_path>/whep).
// Detection boxes are already drawn into the video, so nothing is drawn here.
//
// Fast recovery (2026-10-24, live-player fix):
//   - polls getStats() every 1 s; if the connection says "connected" but framesDecoded
//     stops growing for STALL_MS, the picture is frozen -> reconnect at once (do not wait
//     for "disconnected").
//   - only "failed" / "closed" or a detected stall trigger a reconnect; a short
//     "disconnected" is given DISCONNECT_GRACE_MS to recover on its own first.
//   - reconnect delay backs off BACKOFF_S (1,2,5,10 s, capped) and resets once a frame decodes.
//   - the old peer connection + WHEP session are always closed before a new one opens.
//   - the last frame is kept on screen during a reconnect (video is not blanked), so there
//     is no black flash; the caller shows a small status bar instead.
// Live quality (getStats only, no extra library): fps, resolution, bitrate, approx latency,
//   packetsLost, stalls in the last 5 min, continuous connected time. Exposed via .stats + onstats.
import { CONFIG } from "./config.js";

const ICE_GATHER_MAX_MS = 2000;
const DISCONNECT_GRACE_MS = 2000; // was 5000
const STALL_MS = 3000; // connected but no new frame this long = frozen picture
const FIRST_FRAME_MS = 8000; // v4: connected but no first frame this long -> reconnect (backoff)
const STATS_INTERVAL_MS = 1000;
const BACKOFF_S = [1, 2, 5, 10]; // reconnect delay, capped at the last value
const STALL_WINDOW_MS = 5 * 60 * 1000; // "stalls in the last 5 minutes"

function waitIceGathering(pc) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = () => pc.iceGatheringState === "complete" && done();
    const timer = setTimeout(done, ICE_GATHER_MAX_MS);
    pc.addEventListener("icegatheringstatechange", check);
  });
}

const WEBRTC_PREFIX = "/webrtc";
const whepUrl = (path) => `${WEBRTC_PREFIX}/${String(path).split("/").map(encodeURIComponent).join("/")}/whep`;

/**
 * Absolute URL of the WHEP session from the 201 Location header, resolved against the WHEP URL.
 * MediaMTX answers with a root path ("/cam01/whep/<id>") that doesn't know about the nginx
 * prefix, so the prefix is added back when missing.
 */
function sessionUrl(location, whep) {
  if (!location) return null;
  try {
    const u = new URL(location, new URL(whep, window.location.href));
    if (u.origin === window.location.origin && !u.pathname.startsWith(`${WEBRTC_PREFIX}/`)) {
      u.pathname = WEBRTC_PREFIX + u.pathname;
    }
    return u.href;
  } catch {
    return null;
  }
}

function deleteSession(url) {
  // keepalive lets the request finish even while the tab is closing
  fetch(url, { method: "DELETE", keepalive: true }).catch((e) =>
    console.debug("[webrtc] WHEP DELETE failed (ignored)", url, e?.message || e)
  );
}

// Players with an open session, so their sessions can be released when the tab closes
const activePlayers = new Set();
window.addEventListener("pagehide", () => activePlayers.forEach((p) => p._releaseSession()));

const EMPTY_STATS = {
  fps: null, width: null, height: null, bitrateMbps: null, latencyMs: null,
  packetsLost: null, stalls5min: 0, connectedMs: 0,
};

export class WhepPlayer {
  /** state: "connecting" | "playing" | "failed" | "stopped"
   *  live (fine-grained, for the on-video message): "connecting" | "first-frame"
   *       | "playing" | "stalled" | "failed" */
  constructor(videoElement, streamPath) {
    this.video = videoElement;
    this.streamPath = streamPath;
    this.state = "stopped";
    this.live = "stopped";
    this.onstate = null;
    this.onstats = null;
    this.stats = { ...EMPTY_STATS };
    this.statusText = "";
    this.quality = "unknown"; // "good" | "fair" | "bad" | "unknown"
    this._pc = null;
    this._abort = null;
    this._retryTimer = null;
    this._graceTimer = null;
    this._statsTimer = null;
    this._session = null; // WHEP session URL (from Location), released with DELETE
    this._wanted = false;
    this._gen = 0;
    this._connecting = false; // single-flight guard: one connect attempt at a time
    this._backoffIdx = 0;
    this._retrySecs = 0;
    this._hadFrame = false;
    this._fromStall = false;
    this._lastFrames = 0;
    this._lastProgressAt = 0;
    this._connectedAt = 0; // v4: when connectionState last became "connected" (first-frame timeout)
    this.lastFrameWall = 0; // v4: epoch ms of the last decoded-frame progress (0 = never); survives reconnect
    this._playingSince = 0;
    this._stallTimes = []; // epoch ms of recent stalls (last 5 min)
    this._prevBytes = null;
    this._prevBytesAt = 0;
    this._prevJbDelay = null;
    this._prevJbCount = null;
    const v = this.video;
    v.muted = true;
    v.autoplay = true;
    v.playsInline = true;
    v.setAttribute("muted", "");
    v.setAttribute("autoplay", "");
    v.setAttribute("playsinline", "");
  }

  /** true once at least one video frame has decoded on the current connection. */
  get hasFrame() {
    return this._hadFrame;
  }

  _setState(s) {
    if (this.state === s) return;
    this.state = s;
    this._emitState();
  }

  _setLive(l) {
    if (this.live === l) return;
    this.live = l;
    this._refreshStatusText();
    this._emitState();
  }

  _emitState() {
    try {
      this.onstate?.(this.state);
    } catch (e) {
      console.error("[webrtc] onstate handler error", e);
    }
  }

  _refreshStatusText() {
    switch (this.live) {
      // after a frozen picture, keep the "stalled" wording through the reconnect until a frame returns
      case "connecting": this.statusText = this._fromStall ? "Video stalled — reconnecting" : "Connecting…"; break;
      case "first-frame": this.statusText = "Waiting for first frame…"; break;
      case "stalled": this.statusText = "Video stalled — reconnecting"; break;
      case "failed": this.statusText = `Cannot connect — retrying in ${this._retrySecs} s`; break;
      default: this.statusText = ""; // playing / stopped
    }
  }

  start() {
    if (this._wanted) return;
    this._wanted = true;
    this._backoffIdx = 0;
    this._fromStall = false;
    this._connect();
  }

  stop() {
    this._wanted = false;
    this._teardown({ keepVideo: false });
    this._setLive("stopped");
    this._setState("stopped");
  }

  setStreamPath(path) {
    if (path === this.streamPath) return;
    this.streamPath = path;
    if (this._wanted) {
      this._teardown({ keepVideo: false });
      this._connect();
    }
  }

  /** Tell MediaMTX to drop our session (before closing the peer connection). */
  _releaseSession() {
    const url = this._session;
    this._session = null;
    activePlayers.delete(this);
    if (url) deleteSession(url);
  }

  _teardown({ keepVideo = true } = {}) {
    this._gen++;
    clearTimeout(this._retryTimer);
    clearTimeout(this._graceTimer);
    clearInterval(this._statsTimer);
    this._retryTimer = this._graceTimer = this._statsTimer = null;
    this._abort?.abort();
    this._abort = null;
    this._connecting = false;
    this._releaseSession();
    if (this._pc) {
      this._pc.ontrack = this._pc.onconnectionstatechange = null;
      try {
        this._pc.close();
      } catch {
        /* already closed */
      }
      this._pc = null;
    }
    // Keep the last frame visible during a reconnect; only blank on a real stop / stream switch.
    if (!keepVideo && this.video.srcObject) this.video.srcObject = null;
    this._prevBytes = this._prevJbDelay = this._prevJbCount = null;
  }

  /** Reconnect now, keeping the frozen frame on screen. reason: "stalled" | "disconnected" | ... */
  _reconnect(reason) {
    if (!this._wanted) return;
    console.info(`[webrtc] ${this.streamPath}: ${reason}; reconnecting`);
    this._teardown({ keepVideo: true });
    this._connect();
  }

  _fail(reason) {
    if (!this._wanted) return;
    const secs = BACKOFF_S[Math.min(this._backoffIdx, BACKOFF_S.length - 1)];
    this._backoffIdx++;
    this._retrySecs = secs;
    if (reason) console.info(`[webrtc] ${this.streamPath}: ${reason}; retry in ${secs}s`);
    this._teardown({ keepVideo: true });
    this._setLive("failed");
    this._setState("failed");
    this._retryTimer = setTimeout(() => this._wanted && this._connect(), secs * 1000);
  }

  async _connect() {
    if (this._connecting) return; // another attempt is already in flight
    this._teardown({ keepVideo: true });
    this._connecting = true;
    const gen = this._gen;
    this._hadFrame = false;
    this._lastFrames = 0;
    this._lastProgressAt = Date.now();
    this.stats = { ...EMPTY_STATS };
    this._setLive("connecting");
    this._setState("connecting");
    if (typeof RTCPeerConnection === "undefined") return this._fail("WebRTC not supported");
    try {
      const pc = new RTCPeerConnection({ iceServers: [] });
      this._pc = pc;
      pc.addTransceiver("video", { direction: "recvonly" });
      pc.addTransceiver("audio", { direction: "recvonly" });
      pc.ontrack = (ev) => {
        if (ev.track.kind !== "video") return;
        this.video.srcObject = ev.streams[0] || new MediaStream([ev.track]);
        this.video.play?.().catch(() => {});
      };
      pc.onconnectionstatechange = () => {
        if (gen !== this._gen) return;
        const s = pc.connectionState;
        if (s === "connected") {
          clearTimeout(this._graceTimer);
          this._lastProgressAt = Date.now();
          this._connectedAt = Date.now();
          // frames confirm "playing"; until the first frame, show "first-frame"
          this._setLive(this._hadFrame ? "playing" : "first-frame");
          this._setState("playing");
        } else if (s === "failed" || s === "closed") {
          this._fail(`connection ${s}`);
        } else if (s === "disconnected") {
          // usually transient: wait the grace period before giving up
          clearTimeout(this._graceTimer);
          this._graceTimer = setTimeout(
            () => gen === this._gen && this._fail("disconnected"),
            DISCONNECT_GRACE_MS
          );
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitIceGathering(pc);
      if (gen !== this._gen) return;

      this._abort = new AbortController();
      const url = whepUrl(this.streamPath);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: pc.localDescription.sdp,
        signal: this._abort.signal,
      });
      if (gen !== this._gen) {
        // stopped while the request was in flight: release the session it just created
        const late = res.ok && sessionUrl(res.headers.get("Location"), url);
        if (late) deleteSession(late);
        return;
      }
      if (!res.ok) return this._fail(`WHEP HTTP ${res.status}`);
      this._session = sessionUrl(res.headers.get("Location"), url);
      if (this._session) activePlayers.add(this);
      const answer = await res.text();
      if (gen !== this._gen) return;
      await pc.setRemoteDescription({ type: "answer", sdp: answer });
      this._connecting = false; // handshake done; allow a future reconnect
      this._startStatsLoop(gen);
    } catch (e) {
      if (gen !== this._gen || e?.name === "AbortError") return;
      this._fail(e?.message || String(e));
    }
  }

  _startStatsLoop(gen) {
    clearInterval(this._statsTimer);
    this._statsTimer = setInterval(() => {
      if (gen !== this._gen || !this._pc) return;
      this._sampleStats(gen).catch(() => {});
    }, STATS_INTERVAL_MS);
  }

  async _sampleStats(gen) {
    const pc = this._pc;
    if (!pc) return;
    let inbound = null;
    let rttS = null;
    const reports = await pc.getStats();
    if (gen !== this._gen || !this._pc) return;
    reports.forEach((r) => {
      if (r.type === "inbound-rtp" && (r.kind === "video" || r.mediaType === "video")) inbound = r;
      if (r.type === "candidate-pair" && (r.nominated || r.selected) && r.currentRoundTripTime != null)
        rttS = r.currentRoundTripTime;
    });
    if (!inbound) return;
    const now = Date.now();
    const frames = inbound.framesDecoded ?? 0;

    // fps: prefer the browser figure, else derive from the frame delta
    let fps = inbound.framesPerSecond;
    if (fps == null && this._prevBytesAt) {
      const dt = (now - this._prevBytesAt) / 1000;
      if (dt > 0) fps = (frames - this._lastFrames) / dt;
    }

    // bitrate from the bytes delta
    let bitrateMbps = null;
    if (inbound.bytesReceived != null && this._prevBytes != null && this._prevBytesAt) {
      const dt = (now - this._prevBytesAt) / 1000;
      if (dt > 0) bitrateMbps = ((inbound.bytesReceived - this._prevBytes) * 8) / dt / 1e6;
    }
    this._prevBytes = inbound.bytesReceived ?? this._prevBytes;
    this._prevBytesAt = now;

    // latency ~= jitter-buffer delay (avg over interval) + RTT/2
    let jbMs = null;
    if (inbound.jitterBufferDelay != null && inbound.jitterBufferEmittedCount != null) {
      if (this._prevJbDelay != null && inbound.jitterBufferEmittedCount > this._prevJbCount) {
        jbMs = ((inbound.jitterBufferDelay - this._prevJbDelay) /
          (inbound.jitterBufferEmittedCount - this._prevJbCount)) * 1000;
      } else if (inbound.jitterBufferEmittedCount > 0) {
        jbMs = (inbound.jitterBufferDelay / inbound.jitterBufferEmittedCount) * 1000;
      }
      this._prevJbDelay = inbound.jitterBufferDelay;
      this._prevJbCount = inbound.jitterBufferEmittedCount;
    }
    let latencyMs = null;
    if (jbMs != null || rttS != null) latencyMs = (jbMs || 0) + (rttS != null ? (rttS * 1000) / 2 : 0);

    // progress / first-frame / stall detection
    if (frames > this._lastFrames) {
      if (!this._hadFrame) {
        this._hadFrame = true;
        this._fromStall = false; // a fresh frame cleared the freeze
        this._playingSince = now;
        this._backoffIdx = 0; // a decoded frame means the path works again
      }
      this._lastProgressAt = now;
      this.lastFrameWall = now; // v4: survives reconnect (used by the quality badge's "no picture Xs")
      if (this.live !== "playing" && pc.connectionState === "connected") this._setLive("playing");
    }
    this._lastFrames = frames;

    this._stallTimes = this._stallTimes.filter((t) => now - t < STALL_WINDOW_MS);
    this.stats = {
      fps: fps != null ? Math.round(fps * 10) / 10 : null,
      width: inbound.frameWidth ?? null,
      height: inbound.frameHeight ?? null,
      bitrateMbps: bitrateMbps != null ? Math.round(bitrateMbps * 100) / 100 : null,
      latencyMs: latencyMs != null ? Math.round(latencyMs) : null,
      packetsLost: inbound.packetsLost ?? null,
      stalls5min: this._stallTimes.length,
      connectedMs: this._hadFrame ? now - this._playingSince : 0,
    };
    this._updateQuality();
    try {
      this.onstats?.(this.stats);
    } catch (e) {
      console.error("[webrtc] onstats handler error", e);
    }

    // frozen picture: connected, had a frame, but no new frame for STALL_MS -> reconnect now
    if (
      this._hadFrame &&
      pc.connectionState === "connected" &&
      now - this._lastProgressAt >= STALL_MS
    ) {
      this._stallTimes.push(now);
      this._fromStall = true;
      this._setLive("stalled");
      this._reconnect("stalled");
      return;
    }
    // v4: connected but never got a first frame within FIRST_FRAME_MS -> reconnect (backoff)
    if (
      !this._hadFrame &&
      pc.connectionState === "connected" &&
      this._connectedAt &&
      now - this._connectedAt >= FIRST_FRAME_MS
    ) {
      this._fail("no first frame");
    }
  }

  _updateQuality() {
    const { fps, stalls5min } = this.stats;
    if (!this._hadFrame || fps == null) {
      this.quality = "unknown";
    } else if (fps >= 25 && stalls5min === 0) {
      this.quality = "good";
    } else if (fps >= 15 || stalls5min <= 2) {
      this.quality = "fair";
    } else {
      this.quality = "bad";
    }
  }
}
