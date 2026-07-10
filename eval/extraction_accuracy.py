#!/usr/bin/env python3
"""
Extraction ACCURACY benchmark: prove the numbers, not just the labels.

For each chart type we draw a chart from KNOWN true statistics, read the EXACT pixel
coordinates of the axis-calibration points and the data landmarks (bar tops, error caps,
box quartiles, forest markers/CIs) straight from matplotlib's data->display transform, then
feed those pixels through the tool's real calibration + extraction (figureExtractor.calibrate
+ .extract). We compare recovered values to the truth. Tight agreement => the pixel->data->
stats pipeline is correct end to end.

Run: python3 eval/extraction_accuracy.py    (needs the server on :8001 + Playwright)
"""
import asyncio
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

URL = "http://localhost:8001/figure-extractor.html"


def px_mapper(fig, ax):
    """Return f(x,y)->(px,py) in PNG pixel space (origin top-left)."""
    fig.canvas.draw()
    H = fig.canvas.get_width_height()[1]
    def to_px(x, y):
        dx, dy = ax.transData.transform((x, y))
        return {"px": float(dx), "py": float(H - dy)}
    return to_px


# ---- build charts + landmark pixels from known truth ----
def build_bar():
    means = [312.0, 241.0]; sds = [95.0, 88.0]; ns = [24, 26]
    sems = [s / np.sqrt(n) for s, n in zip(sds, ns)]
    fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
    xs = [0, 1]
    ax.bar(xs, means, yerr=sems, capsize=6, width=0.6)
    ax.set_ylim(0, 400); ax.set_xlim(-0.6, 1.6)
    P = px_mapper(fig, ax)
    cal = {"x1": P(0, 0), "x2": P(1, 0), "y1": P(0, 0), "y2": P(0, 300)}
    vals = {"x1": "0", "x2": "1", "y1": "0", "y2": "300", "logX": False, "logY": False}
    # landmark pixels: per group, the bar top and the upper error cap
    lms = []
    for i, x in enumerate(xs):
        lms.append({"role": "top", "g": i, **P(x, means[i])})
        lms.append({"role": "cap", "g": i, **P(x, means[i] + sems[i])})
    fig.savefig("eval/charts_real/ACC_bar.png"); plt.close(fig)
    return {"kind": "bar", "cal": cal, "vals": vals, "lms": lms, "ns": ns,
            "true": {"means": means, "sds": sds}}


def build_box():
    q = [{"q1": 280.0, "med": 305.0, "q3": 330.0}, {"q1": 205.0, "med": 240.0, "q3": 268.0}]
    fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
    # draw boxes at the known quartiles (bxp lets us set stats exactly)
    bxp = [{"med": g["med"], "q1": g["q1"], "q3": g["q3"], "whislo": g["q1"] - 30,
            "whishi": g["q3"] + 30, "fliers": [], "label": str(i)} for i, g in enumerate(q)]
    ax.bxp(bxp, positions=[0, 1], showfliers=False)
    ax.set_ylim(150, 400); ax.set_xlim(-0.6, 1.6)
    P = px_mapper(fig, ax)
    cal = {"x1": P(0, 0), "x2": P(1, 0), "y1": P(0, 200), "y2": P(0, 350)}
    vals = {"x1": "0", "x2": "1", "y1": "200", "y2": "350", "logX": False, "logY": False}
    lms = []
    for i, g in enumerate(q):
        for role in ("q1", "med", "q3"):
            lms.append({"role": role, "g": i, **P(i, g[role])})
    fig.savefig("eval/charts_real/ACC_box.png"); plt.close(fig)
    return {"kind": "box", "cal": cal, "vals": vals, "lms": lms,
            "true": {"q": q}}


def build_forest():
    rows = [{"est": -0.60, "lo": -1.00, "hi": -0.20}, {"est": -0.45, "lo": -0.80, "hi": -0.10}]
    fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
    ys = [1, 0]
    for yi, r in zip(ys, rows):
        ax.plot([r["lo"], r["hi"]], [yi, yi], "k-"); ax.plot(r["est"], yi, "s")
    ax.axvline(0, ls="--"); ax.set_xlim(-1.4, 0.4); ax.set_ylim(-0.6, 1.6)
    P = px_mapper(fig, ax)
    cal = {"x1": P(-1.0, 0), "x2": P(0.0, 0), "y1": P(-1.0, 0), "y2": P(-1.0, 1)}
    vals = {"x1": "-1.0", "x2": "0.0", "y1": "0", "y2": "1", "logX": False, "logY": False}
    lms = []
    for i, (yi, r) in enumerate(zip(ys, rows)):
        lms.append({"role": "est", "g": i, **P(r["est"], yi)})
        lms.append({"role": "lo", "g": i, **P(r["lo"], yi)})
        lms.append({"role": "hi", "g": i, **P(r["hi"], yi)})
    fig.savefig("eval/charts_real/ACC_forest.png"); plt.close(fig)
    return {"kind": "forest", "cal": cal, "vals": vals, "lms": lms, "true": {"rows": rows}}


async def run():
    from playwright.async_api import async_playwright
    charts = [build_bar(), build_box(), build_forest()]
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); pg = await b.new_page()
        await pg.goto(URL)
        print(f"{'chart':8s} {'quantity':22s} {'true':>10s} {'recovered':>12s} {'err%':>7s}")
        worst = 0.0
        for ch in charts:
            # calibrate all landmark pixels -> data values (the tool's affine)
            data = await pg.evaluate("(a)=>window.figureExtractor.calibrate(a.cal,a.vals,a.lms)",
                                     {"cal": ch["cal"], "vals": ch["vals"], "lms": ch["lms"]})
            for lm, dv in zip(ch["lms"], data):
                lm["y"] = dv["y"]; lm["x"] = dv["x"]

            if ch["kind"] == "bar":
                groups = []
                for i, n in enumerate(ch["ns"]):
                    top = next(l["y"] for l in ch["lms"] if l["g"] == i and l["role"] == "top")
                    cap = next(l["y"] for l in ch["lms"] if l["g"] == i and l["role"] == "cap")
                    groups.append({"name": str(i), "mean": top, "errorHalf": abs(cap - top), "n": n})
                res = await pg.evaluate("(g)=>window.figureExtractor.extract.bars(g,'SEM')", groups)
                for i in range(2):
                    tm, ts = ch["true"]["means"][i], ch["true"]["sds"][i]
                    rm, rs = res["groups"][i]["mean"], res["groups"][i]["sd"]
                    for q, t, r in (("mean", tm, rm), ("SD", ts, rs)):
                        ep = 100 * abs(r - t) / abs(t); worst = max(worst, ep)
                        print(f"{'bar':8s} {('group%d %s'%(i,q)):22s} {t:10.2f} {r:12.2f} {ep:6.2f}%")

            elif ch["kind"] == "box":
                groups = []
                for i in range(2):
                    g = {"name": str(i), "n": 30}
                    for role in ("q1", "med", "q3"):
                        g[{"med": "median"}.get(role, role)] = next(l["y"] for l in ch["lms"] if l["g"] == i and l["role"] == role)
                    groups.append(g)
                res = await pg.evaluate("(g)=>window.figureExtractor.extract.boxes(g)", groups)
                for i in range(2):
                    tq = ch["true"]["q"][i]
                    tmean = (tq["q1"] + tq["med"] + tq["q3"]) / 3; tsd = (tq["q3"] - tq["q1"]) / 1.35
                    rm, rs = res["groups"][i]["mean"], res["groups"][i]["sd"]
                    for qn, t, r in (("mean", tmean, rm), ("SD", tsd, rs)):
                        ep = 100 * abs(r - t) / abs(t); worst = max(worst, ep)
                        print(f"{'box':8s} {('group%d %s'%(i,qn)):22s} {t:10.2f} {r:12.2f} {ep:6.2f}%")

            elif ch["kind"] == "forest":
                rows = []
                for i in range(2):
                    rows.append({"label": str(i),
                                 "estimate": next(l["x"] for l in ch["lms"] if l["g"] == i and l["role"] == "est"),
                                 "ciLo": next(l["x"] for l in ch["lms"] if l["g"] == i and l["role"] == "lo"),
                                 "ciHi": next(l["x"] for l in ch["lms"] if l["g"] == i and l["role"] == "hi")})
                res = await pg.evaluate("(r)=>window.figureExtractor.extract.forest(r,'linear')", rows)
                for i in range(2):
                    tr = ch["true"]["rows"][i]
                    t_se = (tr["hi"] - tr["lo"]) / (2 * 1.959964)
                    for qn, t, r in (("estimate", tr["est"], res["rows"][i]["estimate"]),
                                     ("SE", t_se, res["rows"][i]["se"])):
                        ep = 100 * abs(r - t) / abs(t); worst = max(worst, ep)
                        print(f"{'forest':8s} {('row%d %s'%(i,qn)):22s} {t:10.3f} {r:12.3f} {ep:6.2f}%")

        print(f"\nWorst recovery error: {worst:.2f}%")
        assert worst < 1.0, f"extraction accuracy too low: worst {worst:.2f}%"
        print("EXTRACTION ACCURACY: PASS (all within 1% of truth)")
        await b.close()


if __name__ == "__main__":
    import pathlib
    pathlib.Path("eval/charts_real").mkdir(parents=True, exist_ok=True)
    asyncio.run(run())
