#!/usr/bin/env python3
"""Benchmark Cluster 1 (figure digitizers): generate a TIERED labeled chart corpus with
ground-truth landmark PIXELS (from matplotlib's data->display transform) and true values.

Tiers:
  clean : simple bar (SD bars), box (quartiles), scatter (r)   -- where WPD-class tools already win
  hard  : log-y bar, per-animal dot-overlay bar, 2-panel figure -- where manual tools need clicks and
          an automated reader must detect axis scale / dots / the right panel

Output: bench/charts/<id>.png + bench/truth.json  (calibration pts, GT landmark pixels, true values).
The geometry floor (exact pixels -> figure-extractor.calibrate) is the MANUAL CEILING; the vision
reader is scored against the same GT. Run: python3 bench/gen_charts.py
"""
import json, pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

B = pathlib.Path(__file__).resolve().parent
CH = B / "charts"; CH.mkdir(exist_ok=True)
RNG = np.random.default_rng(20260722)


def mapper(fig, ax):
    fig.canvas.draw()
    H = fig.canvas.get_width_height()[1]
    def to_px(x, y):
        dx, dy = ax.transData.transform((x, y))
        return {"px": float(dx), "py": float(H - dy)}
    return to_px


def save(fig, cid):
    fig.savefig(CH / f"{cid}.png", dpi=110, bbox_inches=None); plt.close(fig)


items = []

# ---------- CLEAN ----------
def clean_bar(cid):
    means = [float(x) for x in RNG.uniform(150, 320, 2).round(1)]
    sds = [float(x) for x in RNG.uniform(30, 90, 2).round(1)]
    ns = [int(x) for x in RNG.integers(8, 24, 2)]
    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=110)
    ax.bar([0, 1], means, yerr=sds, capsize=6, width=0.6, color="#5b8def")
    top = max(m + s for m, s in zip(means, sds)) * 1.15
    ax.set_ylim(0, top); ax.set_xlim(-0.6, 1.6); ax.set_ylabel("BDNF (pg/mg)")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Control", "Run"])
    P = mapper(fig, ax)
    ytick = round(top / 4) * 2
    cal = {"x1": P(0, 0), "x2": P(1, 0), "y1": P(0, 0), "y2": P(0, ytick)}
    lms = []
    for i in (0, 1):
        lms += [{"role": "top", "group": i, **P(i, means[i])},
                {"role": "cap", "group": i, **P(i, means[i] + sds[i])}]
    save(fig, cid)
    return {"id": cid, "tier": "clean", "chartType": "bar", "flags": [], "dispersionType": "SD",
            "calPixels": cal, "calVals": {"x1": "0", "x2": "1", "y1": "0", "y2": str(ytick), "logX": False, "logY": False},
            "landmarks": lms, "true": {"means": means, "sds": sds, "ns": ns}}


def clean_box(cid):
    q = []
    for _ in range(2):
        m = RNG.uniform(200, 320); iqr = RNG.uniform(30, 70)
        q.append({"q1": round(m - iqr / 2, 1), "med": round(m, 1), "q3": round(m + iqr / 2, 1)})
    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=110)
    bxp = [{"med": g["med"], "q1": g["q1"], "q3": g["q3"], "whislo": g["q1"] - 25,
            "whishi": g["q3"] + 25, "fliers": [], "label": ["Control", "Run"][i]} for i, g in enumerate(q)]
    ax.bxp(bxp, positions=[0, 1], showfliers=False, patch_artist=True,
           boxprops=dict(facecolor="#7ec07e"))
    lo = min(g["q1"] for g in q) - 45; hi = max(g["q3"] for g in q) + 45
    ax.set_ylim(lo, hi); ax.set_xlim(-0.6, 1.6); ax.set_ylabel("Latency (s)")
    P = mapper(fig, ax)
    y1 = round(lo / 10) * 10 + 10; y2 = round(hi / 10) * 10 - 10
    cal = {"x1": P(0, 0), "x2": P(1, 0), "y1": P(0, y1), "y2": P(0, y2)}
    lms = []
    for i, g in enumerate(q):
        for role in ("q1", "med", "q3"):
            lms.append({"role": role, "group": i, **P(i, g[role])})
    save(fig, cid)
    return {"id": cid, "tier": "clean", "chartType": "box", "flags": [],
            "calPixels": cal, "calVals": {"x1": "0", "x2": "1", "y1": str(y1), "y2": str(y2), "logX": False, "logY": False},
            "landmarks": lms, "true": {"q": q}}


def clean_scatter(cid):
    n = 24; x = RNG.uniform(0, 10, n); r_target = RNG.uniform(0.4, 0.8)
    y = r_target * (x - 5) + RNG.normal(0, 2.2, n) + 15
    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=110)
    ax.scatter(x, y, s=28, color="#d1495b")
    ax.set_xlim(-0.5, 10.5); ax.set_ylim(y.min() - 3, y.max() + 3)
    ax.set_xlabel("Wheel (km/day)"); ax.set_ylabel("BDNF (AU)")
    P = mapper(fig, ax)
    y1 = round(y.min()); y2 = round(y.max())
    cal = {"x1": P(0, 0), "x2": P(10, 0), "y1": P(0, y1), "y2": P(0, y2)}
    pts = [{"role": "pt", "group": 0, **P(float(x[i]), float(y[i]))} for i in range(n)]
    save(fig, cid)
    return {"id": cid, "tier": "clean", "chartType": "scatter", "flags": [],
            "calPixels": cal, "calVals": {"x1": "0", "x2": "10", "y1": str(y1), "y2": str(y2), "logX": False, "logY": False},
            "landmarks": pts, "true": {"x": [round(float(v), 3) for v in x], "y": [round(float(v), 3) for v in y],
                                       "r": round(float(np.corrcoef(x, y)[0, 1]), 4)}}


# ---------- HARD ----------
def hard_logbar(cid):
    means = [float(x) for x in RNG.uniform(20, 90, 2).round(1)]
    fold = [float(f) for f in RNG.uniform(3, 8, 2).round(2)]
    vals = [means[0], means[0] * fold[0]]  # spans a decade -> log axis
    sds = [v * 0.2 for v in vals]
    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=110)
    ax.bar([0, 1], vals, yerr=sds, capsize=6, width=0.6, color="#8e6fd1")
    ax.set_yscale("log"); ax.set_ylim(10, max(vals) * 2); ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("mRNA (log)"); ax.set_xticks([0, 1]); ax.set_xticklabels(["Sed", "Run"])
    P = mapper(fig, ax)
    cal = {"x1": P(0, 1), "x2": P(1, 1), "y1": P(0, 10), "y2": P(0, 100)}
    lms = []
    for i in (0, 1):
        lms += [{"role": "top", "group": i, **P(i, vals[i])},
                {"role": "cap", "group": i, **P(i, vals[i] + sds[i])}]
    save(fig, cid)
    return {"id": cid, "tier": "hard", "chartType": "bar", "flags": ["log-axis"], "dispersionType": "SD",
            "calPixels": cal, "calVals": {"x1": "0", "x2": "1", "y1": "10", "y2": "100", "logX": False, "logY": True},
            "landmarks": lms, "true": {"means": [round(v, 2) for v in vals], "sds": [round(s, 2) for s in sds], "ns": [10, 10]}}


def hard_dotbar(cid):
    means = [float(x) for x in RNG.uniform(150, 300, 2).round(1)]
    sds = [float(x) for x in RNG.uniform(35, 70, 2).round(1)]
    ns = [10, 10]
    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=110)
    ax.bar([0, 1], means, yerr=sds, capsize=6, width=0.6, color="#efc05b", zorder=1)
    for i in (0, 1):  # per-animal dot overlay (the rodent-paper idiom)
        dots = means[i] + RNG.normal(0, sds[i], ns[i])
        ax.scatter(np.full(ns[i], i) + RNG.uniform(-0.12, 0.12, ns[i]), dots,
                   color="black", s=14, zorder=3)
    top = max(m + s for m, s in zip(means, sds)) * 1.25
    ax.set_ylim(0, top); ax.set_xlim(-0.6, 1.6); ax.set_ylabel("BDNF (pg/mg)")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Control", "Run"])
    P = mapper(fig, ax)
    ytick = round(top / 4) * 2
    cal = {"x1": P(0, 0), "x2": P(1, 0), "y1": P(0, 0), "y2": P(0, ytick)}
    lms = []
    for i in (0, 1):
        lms += [{"role": "top", "group": i, **P(i, means[i])},
                {"role": "cap", "group": i, **P(i, means[i] + sds[i])}]
    save(fig, cid)
    return {"id": cid, "tier": "hard", "chartType": "bar", "flags": ["raw-points-present"], "dispersionType": "SD",
            "calPixels": cal, "calVals": {"x1": "0", "x2": "1", "y1": "0", "y2": str(ytick), "logX": False, "logY": False},
            "landmarks": lms, "true": {"means": means, "sds": sds, "ns": ns}}


def hard_panel(cid):
    # 2-panel figure; TARGET is panel B (right). Reader must find the right panel.
    fig, axes = plt.subplots(1, 2, figsize=(8, 4), dpi=110)
    for k, ax in enumerate(axes):
        m = [float(x) for x in RNG.uniform(150, 300, 2).round(1)]
        s = [float(x) for x in RNG.uniform(30, 70, 2).round(1)]
        ax.bar([0, 1], m, yerr=s, capsize=5, width=0.6, color=["#5b8def", "#d1495b"][k])
        ax.set_ylim(0, max(a + b for a, b in zip(m, s)) * 1.2); ax.set_xlim(-0.6, 1.6)
        ax.set_title("AB"[k]); ax.set_xticks([0, 1]); ax.set_xticklabels(["Ctl", "Run"])
        if k == 1:
            means, sds = m, s; tax = ax
    P = mapper(fig, tax)
    top = max(a + b for a, b in zip(means, sds)) * 1.2
    ytick = round(top / 4) * 2
    cal = {"x1": P(0, 0), "x2": P(1, 0), "y1": P(0, 0), "y2": P(0, ytick)}
    lms = []
    for i in (0, 1):
        lms += [{"role": "top", "group": i, **P(i, means[i])},
                {"role": "cap", "group": i, **P(i, means[i] + sds[i])}]
    save(fig, cid)
    return {"id": cid, "tier": "hard", "chartType": "bar", "flags": ["multi-panel"], "dispersionType": "SD",
            "targetPanel": "B (right)",
            "calPixels": cal, "calVals": {"x1": "0", "x2": "1", "y1": "0", "y2": str(ytick), "logX": False, "logY": False},
            "landmarks": lms, "true": {"means": means, "sds": sds, "ns": [10, 10]}}


builders = [clean_bar, clean_bar, clean_box, clean_box, clean_scatter, clean_scatter,
            hard_logbar, hard_logbar, hard_dotbar, hard_dotbar, hard_panel, hard_panel]
for i, b in enumerate(builders):
    items.append(b(f"{b.__name__}_{i:02d}"))

(B / "truth.json").write_text(json.dumps(items, indent=1))
tiers = {}
for it in items:
    tiers[it["tier"]] = tiers.get(it["tier"], 0) + 1
print(f"generated {len(items)} charts -> bench/charts/  ({tiers})")
for it in items:
    print(f"  {it['id']:22s} {it['tier']:5s} {it['chartType']:8s} {','.join(it['flags']) or '-'}")
