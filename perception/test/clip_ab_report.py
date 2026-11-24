#!/usr/bin/env python3
"""Per-frame object counts from <run>_objs.jsonl (app --debug-objs), for the clip A/B runs (Python 3.6).

  python3 clip_ab_report.py timeline <run> [<run> ...]          # per 2 s of clip time: % of frames with each key
  python3 clip_ab_report.py table <segments> <run> [<run> ...]  # % of frames per key, whole clip + per segment
      segments = "name:start-end,name:start-end,..." in clip seconds (pts), e.g. "vest:10-28,novest:32-48"
Keys are (unique_component_id, class_id) before nvtracker. fps / frames come from <run>_summary.json.
"""
import json
import os
import sys

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "cam")


def load(run):
    frames = []
    with open(os.path.join(DIR, run + "_objs.jsonl")) as f:
        for line in f:
            d = json.loads(line)
            frames.append((d["pts"], set((o[0], o[1]) for o in d["o"])))
    with open(os.path.join(DIR, run + "_summary.json")) as f:
        summ = json.load(f)
    return frames, summ


def pct(frames, key):
    if not frames:
        return None
    return 100.0 * sum(1 for _, ks in frames if key in ks) / len(frames)


def keys_of(runs):
    ks = set()
    for frames, _ in runs.values():
        for _, k in frames:
            ks |= k
    return sorted(ks)


def timeline(names):
    runs = dict((n, load(n)) for n in names)
    keys = keys_of(runs)
    end = max(fr[-1][0] for fr, _ in runs.values())
    print("t(s)  " + "  ".join("%s%s" % (n, "".join("(%d,%d)" % k for k in keys)) for n in names))
    t = 0.0
    while t < end:
        cells = []
        for n in names:
            seg = [x for x in runs[n][0] if t <= x[0] < t + 2.0]
            cells.append(" ".join("%3.0f" % (pct(seg, k) or 0) for k in keys))
        print("%4.0f  %s" % (t, "  |  ".join(cells)))
        t += 2.0


def table(spec, names):
    segs = []
    for part in spec.split(","):
        name, rng = part.split(":")
        a, b = rng.split("-")
        segs.append((name, float(a), float(b)))
    runs = dict((n, load(n)) for n in names)
    keys = keys_of(runs)
    cols = [("all", None, None)] + segs
    print("| run | frames | fps | key | " + " | ".join(
        "%s%s" % (c[0], "" if c[1] is None else " %g-%g s" % (c[1], c[2])) for c in cols) + " |")
    print("|" + "---|" * (4 + len(cols)))
    for n in names:
        frames, summ = runs[n]
        for k in keys:
            row = []
            for _, a, b in cols:
                seg = frames if a is None else [x for x in frames if a <= x[0] < b]
                p = pct(seg, k)
                row.append("%.1f %% (%d)" % (p, len(seg)) if p is not None else "--")
            print("| %s | %d | %s | (%d,%d) | %s |" % (n, len(frames), summ.get("fps_mean"), k[0], k[1], " | ".join(row)))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "timeline":
        timeline(sys.argv[2:])
    elif len(sys.argv) >= 4 and sys.argv[1] == "table":
        table(sys.argv[2], sys.argv[3:])
    else:
        print(__doc__)
        sys.exit(1)
