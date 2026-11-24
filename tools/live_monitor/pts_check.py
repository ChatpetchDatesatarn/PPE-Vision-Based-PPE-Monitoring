# -*- coding: utf-8 -*-
"""Count backward PTS steps in an ffprobe packet dump (what MediaMTX's WebRTC source rejects as "B-frames").

Dump on the Jetson (video packets of the DeepStream RTSP out, 120 s):
  timeout 130 ffprobe -v error -rtsp_transport tcp -select_streams v:0 -read_intervals %+120 \
      -show_entries packet=pts,dts,pts_time,flags -of csv=p=0 rtsp://127.0.0.1:8555/cam01 > pts.csv
  (ffprobe writes the columns as pts,pts_time,dts,flags)
Usage:  python pts_check.py pts.csv
"""
import sys


def main(fn):
    pts, ptime, flags = [], [], []
    for line in open(fn):
        p = line.strip().split(",")
        if len(p) < 3 or not p[0].lstrip("-").isdigit():
            continue                       # N/A pts (packets before RTCP sync) and blank lines
        pts.append(int(p[0]))
        ptime.append(float(p[1]))
        flags.append(p[3] if len(p) > 3 else "")
    n = len(pts)
    if n < 2:
        print("packets=%d (too few)" % n)
        return
    span = ptime[-1] - ptime[0]
    keys = [ptime[i] for i in range(n) if "K" in flags[i]]
    gaps = [b - a for a, b in zip(keys, keys[1:])]
    back = [(i, ptime[i], (pts[i - 1] - pts[i]) / 90000.0) for i in range(1, n) if pts[i] < pts[i - 1]]
    # the first packets come before ffprobe's RTCP sync and can jump once: reported, not counted
    start = [b for b in back if b[0] < 5]
    back = [b for b in back if b[0] >= 5]
    span = ptime[-1] - ptime[5] if n > 6 else span
    print("packets=%d span=%.1fs fps=%.2f" % (n, span, (n - 6) / span if span else 0))
    print("startup_jumps(first 5 pkts, not counted)=%d" % len(start))
    print("keyframes=%d interval_mean=%.2fs max=%.2fs" % (len(keys), sum(gaps) / len(gaps) if gaps else 0,
                                                          max(gaps) if gaps else 0))
    print("backward_pts=%d" % len(back))
    for i, t, d in back[:40]:
        print("  pkt=%d pts_time=%.3fs back_by=%.4fs" % (i, t, d))
    if back:
        ds = [d for _, _, d in back]
        print("back_by min=%.4fs max=%.4fs" % (min(ds), max(ds)))


if __name__ == "__main__":
    main(sys.argv[1])
