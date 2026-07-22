#!/usr/bin/env python3
"""Score the vision reader: take each model's ESTIMATED pixels (bench/vision/<id>.json), run them
through figure-extractor.calibrate, recover values, and compare to ground truth -- stratified by
tier (clean vs hard) and by channel (mean / dispersion / quartile / point). The manual ceiling is
bench/floor.json (~0%). Writes bench/RESULTS.md.  Needs server :8001 + Playwright.
Run: python3 bench/score_vision.py"""
import asyncio, json, pathlib, statistics
B = pathlib.Path(__file__).resolve().parent
URL = "http://localhost:8001/figure-extractor.html"
TRUTH = {it["id"]: it for it in json.loads((B / "truth.json").read_text())}
FLOOR = {r["id"]: r for r in json.loads((B / "floor.json").read_text())} if (B / "floor.json").exists() else {}

def pct(r, t):
    return 100 * abs(r - t) / abs(t) if t else abs(r - t)

async def run():
    from playwright.async_api import async_playwright
    import numpy as np
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); pg = await b.new_page(); await pg.goto(URL)
        rows, missing = [], []
        for cid, it in TRUTH.items():
            vf = B / "vision" / f"{cid}.json"
            if not vf.exists():
                missing.append(cid); continue
            est = json.loads(vf.read_text())
            cal = est["calPixels"]; elm = est["landmarks"]
            # build landmark pixel list in truth order using the estimate's keyed points
            keys = []
            if it["chartType"] == "bar":
                keys = [("top", 0, "top_0"), ("cap", 0, "cap_0"), ("top", 1, "top_1"), ("cap", 1, "cap_1")]
            elif it["chartType"] == "box":
                keys = [(r, i, f"{r}_{i}") for i in (0, 1) for r in ("q1", "med", "q3")]
            elif it["chartType"] == "scatter":
                keys = [("pt", 0, f"pt_{j}") for j in range(len(it["landmarks"]))]
            lms = []
            ok = True
            for role, grp, k in keys:
                if k not in elm: ok = False; break
                lms.append({"px": elm[k]["px"], "py": elm[k]["py"]})
            if not ok:
                missing.append(cid + "(incomplete)"); continue
            dv = await pg.evaluate("(a)=>window.figureExtractor.calibrate(a.c,a.v,a.l)",
                                   {"c": cal, "v": it["calVals"], "l": lms})
            tr = it["true"]; errs = {}
            if it["chartType"] == "bar":
                pm, pd = [], []
                for i in (0, 1):
                    top = dv[[k[1] for k in keys].index(i) if False else (0 if i == 0 else 2)]["y"]
                    capv = dv[1 if i == 0 else 3]["y"]
                    pm.append(pct(top, tr["means"][i])); pd.append(pct(abs(capv - top), tr["sds"][i]))
                errs = {"mean": statistics.mean(pm), "dispersion": statistics.mean(pd)}
            elif it["chartType"] == "box":
                pm = []
                for idx, (role, i, k) in enumerate(keys):
                    pm.append(pct(dv[idx]["y"], tr["q"][i][role]))
                errs = {"quartiles": statistics.mean(pm)}
            elif it["chartType"] == "scatter":
                xs = np.array([d["x"] for d in dv]); ys = np.array([d["y"] for d in dv])
                r = float(np.corrcoef(xs, ys)[0, 1])
                # scatter points are unordered -> match each recovered point to its NEAREST true point
                # (index-based comparison is invalid); report mean axis-range-normalized position error.
                tx = np.array(tr["x"]); ty = np.array(tr["y"])
                xr = tx.max() - tx.min() or 1.0; yr = ty.max() - ty.min() or 1.0
                perr = []
                for j in range(len(xs)):
                    dd = ((tx - xs[j]) / xr) ** 2 + ((ty - ys[j]) / yr) ** 2
                    k = int(np.argmin(dd))
                    perr.append(50 * (abs(tx[k] - xs[j]) / xr + abs(ty[k] - ys[j]) / yr))
                errs = {"point": statistics.mean(perr), "r": pct(r, tr["r"])}
            rows.append({"id": cid, "tier": it["tier"], "chartType": it["chartType"],
                         "flags": it["flags"], "errors": errs})
        await b.close()

    # ---- report ----
    def agg(pred):
        vals = [v for r in rows if pred(r) for v in r["errors"].values()]
        return (statistics.median(vals), max(vals), len(vals)) if vals else (None, None, 0)
    disp = [v for r in rows for k, v in r["errors"].items() if k == "dispersion"]
    L = ["# Benchmark Cluster 1 -- automated chart reader vs. the manual ceiling", "",
         f"Charts scored: {len(rows)} / {len(TRUTH)}" + (f"  (missing: {', '.join(missing)})" if missing else ""), "",
         "Manual ceiling (geometry floor, exact clicks): ~0.00% on every chart, clean and hard (bench/floor.json).",
         "The numbers below are the VISION READER's recovery error -- i.e. how much accuracy is lost to the",
         "model picking points from the image rather than a human clicking them.", "",
         "## By tier (all channels, % error)", "",
         "| Tier | median | worst | n |", "|---|---|---|---|"]
    for t in ("clean", "hard"):
        m, w, n = agg(lambda r: r["tier"] == t)
        L.append(f"| {t} | {m:.2f} | {w:.2f} | {n} |" if m is not None else f"| {t} | - | - | 0 |")
    L += ["", "## Dispersion channel (the load-bearing, variance-determining quantity)", ""]
    if disp:
        L.append(f"error-bar (SD) recovery: median {statistics.median(disp):.2f}%  worst {max(disp):.2f}%  (n={len(disp)})")
    L += ["", "## Per chart", "", "| chart | tier | type | flags | errors (%) |", "|---|---|---|---|---|"]
    for r in rows:
        e = " ".join(f"{k}={v:.2f}" for k, v in r["errors"].items())
        L.append(f"| {r['id']} | {r['tier']} | {r['chartType']} | {','.join(r['flags']) or '-'} | {e} |")
    L += ["", "## Verdict (build vs. buy)", "",
          "- If the reader matches the manual ceiling on **clean** charts, a bespoke reader adds little there --",
          "  reuse WPD/metaDigitise + a provenance record.",
          "- If it **breaks on the hard tier** (log axis, dot overlays, multi-panel) where manual tools still need",
          "  correct clicks, that is the build case for a specialized detector (per VISION-MODEL-METHODOLOGY.md)."]
    (B / "RESULTS.md").write_text("\n".join(L))
    print("\n".join(L))

if __name__ == "__main__":
    asyncio.run(run())
