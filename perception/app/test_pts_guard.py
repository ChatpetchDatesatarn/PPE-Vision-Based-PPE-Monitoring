# -*- coding: utf-8 -*-
"""Unit test for pts_guard.PtsGuard (v4 item 1). Run on PC: python test_pts_guard.py
Verifies output PTS is non-decreasing and that after a camera reset the spacing returns to ~33/66 ms,
NOT pinned at 1 ms/frame (the v3 A1 bug)."""
import pts_guard as pg

MS = 1_000_000

def deltas(outs):
    return [round((b - a) / MS, 2) for a, b in zip(outs, outs[1:])]

def run(seq_ms):
    g = pg.PtsGuard()
    outs = [g.feed(int(t * MS)) for t in seq_ms]
    assert all(b > a for a, b in zip(outs, outs[1:])), "output not strictly increasing"
    return g, outs

def approx(d, lo=20, hi=90):
    return lo <= d <= hi

fail = 0
def check(name, cond):
    global fail
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fail += 1

# 1) normal 30 fps (33 ms) -> deltas ~33
g, o = run([i * 33 for i in range(10)])
d = deltas(o)
check("normal spacing ~33ms", all(approx(x) for x in d) and g.rebase == 0 and g.fixed == 0 and o[0] == 0)

# 2) small backward wobble (one frame goes back 5 ms) -> nudged, recovers
g, o = run([0, 33, 66, 61, 99, 132])   # 4th sample dips below 3rd
d = deltas(o)
check("small wobble nudged +1ms, no rebase", g.rebase == 0 and g.fixed >= 1 and all(x > 0 for x in d))

# 3) camera reset to ~0 mid-stream -> rebase, spacing ~33 after (NOT 1 ms)
#    first run long enough (>200 ms) so the drop to 0 is a real reset, not a wobble
seq = [i * 33 for i in range(60)] + [j * 33 for j in range(60)]  # second run restarts at 0
g, o = run(seq)
post = deltas(o)[60:]       # deltas after the reset point
check("reset->rebase once", g.rebase == 1)
check("post-reset spacing ~33ms (not 1ms)", all(approx(x) for x in post))
check("no +1ms pinning after reset", sum(1 for x in post if x <= 2) == 0)

# 4) large forward jump (>2 s) -> rebase, continues ~one frame later
g, o = run([0, 33, 66, 66 + 5000, 66 + 5033, 66 + 5066])  # +5 s jump
d = deltas(o)
check("forward jump rebased", g.rebase == 1 and approx(d[2]) and approx(d[3]))

# 5) multiple resets -> each rebases, spacing stays ~33
seq = []
for _ in range(3):
    seq += [i * 33 for i in range(20)]
g, o = run(seq)
d = deltas(o)
check("3 resets -> 2 rebases (first run is not a reset)", g.rebase == 2)
check("spacing ~33 across all resets", all(approx(x) for x in d))

# 6) restart() across a camera reboot: output timeline stays continuous (monotonic across the boundary),
#    even when the new stream's source PTS restarts LOW. This is the fix for the live-freeze: with a fixed
#    rtph264pay ssrc MediaMTX keeps the source, so the RTP timestamp must not step backward across restart.
g = pg.PtsGuard()
o1 = [g.feed(int(i * 33 * MS)) for i in range(60)]                   # 60 frames @33ms
last = o1[-1]
g.restart()                                                         # camera reboot -> pipeline restart
o2 = [g.feed(int(j * 33 * MS)) for j in range(60)]                  # new stream, source PTS back to 0
allout = o1 + o2
check("restart: output strictly increasing across reboot", all(b > a for a, b in zip(allout, allout[1:])))
check("restart: first post-reboot frame ~one frame after last", approx((o2[0] - last) / MS))
check("restart: counted as one rebase", g.rebase == 1)
check("restart: post-reboot spacing ~33ms (not 1ms)", all(approx(x) for x in deltas(o2)) )

# 7) restart() before any frame emitted behaves like a cold reset (first frame passes through = raw)
g = pg.PtsGuard()
g.restart()
first = g.feed(1234 * MS)
check("restart before first frame = cold start (passthrough)", first == 1234 * MS and g.rebase == 0)

print("\nrebase/fixed counters example (case 5): rebase=%d fixed=%d" % (g.rebase, g.fixed))
print("RESULT:", "ALL PASS" if fail == 0 else "%d FAILED" % fail)
import sys; sys.exit(1 if fail else 0)
