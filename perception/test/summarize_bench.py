"""Summarize deepstream-app PERF + tegrastats logs from run_smoke.sh (copied to the PC).

Usage: python summarize_bench.py <results dir> <tag> [<tag> ...]
fps: **PERF samples, first sample (pipeline start, 0.00) dropped.
tegrastats: whole run; CPU% = mean of online cores per sample.
"""
import re
import statistics as st
import sys
from pathlib import Path


def perf(log):
    vals = [float(m.group(1)) for m in re.finditer(r"^\*\*PERF:\s+([\d.]+) \(([\d.]+)\)", log, re.M)]
    avgs = re.findall(r"^\*\*PERF:\s+[\d.]+ \(([\d.]+)\)", log, re.M)
    return vals[1:], (float(avgs[-1]) if avgs else None)


def tegra(text, lo=0, hi=None):
    rows = text.splitlines()[lo:hi]
    ram, cpu, gpu, tc, tg = [], [], [], [], []
    for r in rows:
        m = re.search(r"RAM (\d+)/", r)
        if m:
            ram.append(int(m.group(1)))
        m = re.search(r"CPU \[([^\]]+)\]", r)
        if m:
            cores = [int(x) for x in re.findall(r"(\d+)%@", m.group(1))]
            if cores:
                cpu.append(sum(cores) / len(cores))
        m = re.search(r"GR3D_FREQ (\d+)%", r)
        if m:
            gpu.append(int(m.group(1)))
        m = re.search(r"CPU@([\d.]+)C", r)
        if m:
            tc.append(float(m.group(1)))
        m = re.search(r"GPU@([\d.]+)C", r)
        if m:
            tg.append(float(m.group(1)))
    return dict(n=len(rows), ram_max=max(ram), ram_mean=st.mean(ram), gpu_mean=st.mean(gpu), gpu_max=max(gpu),
                cpu_mean=st.mean(cpu), cpu_max=max(cpu), tc_max=max(tc), tg_max=max(tg))


def main():
    d = Path(sys.argv[1])
    for tag in sys.argv[2:]:
        log = (d / f"{tag}.log").read_text(errors="replace")
        t = tegra((d / f"{tag}.tegra").read_text(errors="replace"))
        rc = (d / f"{tag}.time").read_text().split()
        v, last = perf(log)
        print(f"## {tag}  {' '.join(rc)}")
        if v:
            print(f"fps n={len(v)} mean={st.mean(v):.2f} min={min(v):.2f} max={max(v):.2f} last_avg={last}")
            print("samples:", ", ".join(f"{x:.2f}" for x in v))
        print("tegra n={n} RAM {ram_max}/{ram_mean:.0f} MB, GPU% {gpu_mean:.1f}/{gpu_max}, CPU% {cpu_mean:.1f}/{cpu_max:.1f}, "
              "CPU {tc_max}C GPU {tg_max}C".format(**t))
        eng = re.findall(r"deserialized trt engine from :(\S+)", log)
        print("engine:", eng[0] if eng else "NOT deserialized (rebuilt?)")


if __name__ == "__main__":
    main()
