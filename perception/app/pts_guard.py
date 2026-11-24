# -*- coding: utf-8 -*-
"""v4 A1: retime the PTS stream going into rtph264pay so MediaMTX's WHEP source never sees a backward
step (it drops the WebRTC session on one) and never gets pinned at ~1 ms/frame after a camera reset.

Pure Python (no Gst / pyds) so it can be unit-tested on the PC. The Gst pad probe in
person_count_app.py owns one PtsGuard and feeds it each buffer's raw PTS (ns), using the returned value
as the outgoing PTS.

Rules:
  * small backward wobble (<= BIG_BACK_NS): nudge output to last + NUDGE_NS (+1 ms), keep spacing ~real.
  * large backward step (> BIG_BACK_NS) or large forward jump (> BIG_FWD_NS) in the SOURCE timeline =
    the camera reset its stream -> rebase a running offset so output continues one frame (~FRAME_NS)
    after the last emitted PTS, then subsequent frames advance at their real ~33/66 ms spacing.
  * reset() clears all state (cold start / first play).
  * restart() is called on a pipeline RESTART (camera reboot -> source reconnect). It keeps the OUTPUT
    timeline: the next frame is placed ~one frame after the last emitted PTS (a forced rebase), so the
    RTP timestamp never steps backward across our restart. This matters because rtph264pay keeps a FIXED
    ssrc across NULL->PLAYING (person_count_app sets ssrc=), so MediaMTX stays on the same RTP source and
    would drop a backward timestamp the same way it drops a backward PTS.
"""

BIG_BACK_NS = 200_000_000     # source PTS backward step bigger than this = stream reset
BIG_FWD_NS  = 2_000_000_000   # source PTS forward jump bigger than this = stream reset
FRAME_NS    = 33_000_000      # ~1 frame at 30 fps (used to continue the timeline after a rebase)
NUDGE_NS    = 1_000_000       # +1 ms for a small backward wobble


class PtsGuard(object):
    def __init__(self):
        self.reset()
        # cumulative counters survive reset() so the 60 s log sees lifetime totals
        self.fixed = 0        # small-wobble +1 ms corrections
        self.rebase = 0       # stream-reset rebases

    def reset(self):
        """Cold start / first play: forget the timeline, keep cumulative counters."""
        self._last_pay = None   # None = no frame emitted yet (first frame passes through untouched)
        self._offset = 0
        self._last_in = None
        self._force_rebase = False
        self.dmin = None      # min/max output delta since last stats_window_reset (ns)
        self.dmax = None

    def restart(self):
        """Pipeline restart (camera reset): keep the output timeline continuous. The next frame is forced
        to rebase to ~one frame after the last emitted PTS, so the RTP timestamp stays monotonic across the
        restart (rtph264pay keeps a fixed ssrc, so MediaMTX stays on the same source). Falls back to a cold
        reset() when no frame has been emitted yet."""
        if self._last_pay is None:
            self.reset()
            return
        self._offset = 0
        self._last_in = None
        self._force_rebase = True

    def stats_window_reset(self):
        self.dmin = None
        self.dmax = None

    def feed(self, raw):
        """raw = incoming buffer PTS in ns; returns the outgoing PTS in ns (non-decreasing)."""
        reset = self._force_rebase     # forced by restart(): next frame continues the timeline
        self._force_rebase = False
        if not reset and self._last_in is not None:
            d_in = int(raw) - int(self._last_in)
            if d_in < -BIG_BACK_NS or d_in > BIG_FWD_NS:
                reset = True
        self._last_in = raw

        adj = raw + self._offset
        if self._last_pay is not None and (reset or adj <= self._last_pay):
            if reset or (self._last_pay - adj) > BIG_BACK_NS:
                self._offset = (self._last_pay + FRAME_NS) - raw
                adj = raw + self._offset
                self.rebase += 1
            else:
                adj = self._last_pay + NUDGE_NS
                self._offset = adj - raw
                self.fixed += 1

        if self._last_pay is not None:
            d = adj - self._last_pay
            self.dmin = d if self.dmin is None else min(self.dmin, d)
            self.dmax = d if self.dmax is None else max(self.dmax, d)

        self._last_pay = adj
        return adj

    def window_ms(self):
        """(min,max) output delta this window in ms, or ('','') if no data."""
        f = lambda x: "" if x is None else round(x / 1e6, 1)
        return f(self.dmin), f(self.dmax)
