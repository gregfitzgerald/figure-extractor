#!/usr/bin/env python3
"""Geometry floor = the MANUAL CEILING: feed the exact ground-truth landmark pixels through
figure-extractor's real calibration (window.figureExtractor.calibrate) and recover values.
This is the accuracy a WebPlotDigitizer/metaDigitise user achieves with perfect clicks -- the
ceiling the automated vision reader is measured against. Writes bench/floor.json.

Needs the server on :8001 + Playwright.  Run: python3 bench/run_floor.py
"""
import asyncio, json, pathlib, statistics
B = pathlib.Path(__file__).resolve().parent
URL = "http://localhost:8001/figure-extractor.html"
TRUTH = json.loads((B / "truth.json").read_text())


def pct(r, t):
    return 100 * abs(r - t) / abs(t) if t else abs(r - t)


async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); pg = await b.new_page(); await pg.goto(URL)

        async def cal(it):
            lms = [{"px": l["px"], "py": l["py"]} for l in it["landmarks"]]
            return await pg.evaluate("(a)=>window.figureExtractor.calibrate(a.c,a.v,a.l)",
                                     {"c": it["calPixels"], "v": it["calVals"], "l": lms})

        results = []
        for it in TRUTH:
            dv = await cal(it)  # data values for each landmark (same order)
            lm = it["landmarks"]; tr = it["true"]; errs = {}
            if it["chartType"] == "bar":
                per_mean, per_disp = [], []
                for i in (0, 1):
                    top = next(dv[j]["y"] for j, l in enumerate(lm) if l["group"] == i and l["role"] == "top")
                    capd = next(dv[j]["y"] for j, l in enumerate(lm) if l["group"] == i and l["role"] == "cap")
                    per_mean.append(pct(top, tr["means"][i]))
                    per_disp.append(pct(abs(capd - top), tr["sds"][i]))
                errs = {"mean": statistics.mean(per_mean), "dispersion": statistics.mean(per_disp)}
            elif it["chartType"] == "box":
                pm = []
                for i in (0, 1):
                    for role in ("q1", "med", "q3"):
                        rv = next(dv[j]["y"] for j, l in enumerate(lm) if l["group"] == i and l["role"] == role)
                        pm.append(pct(rv, tr["q"][i][role]))
                errs = {"quartiles": statistics.mean(pm)}
            elif it["chartType"] == "scatter":
                xs = [dv[j]["x"] for j in range(len(lm))]; ys = [dv[j]["y"] for j in range(len(lm))]
                import numpy as np
                r = float(np.corrcoef(xs, ys)[0, 1])
                pt = statistics.mean([pct(xs[j], tr["x"][j]) for j in range(len(xs))] +
                                     [pct(ys[j], tr["y"][j]) for j in range(len(ys))])
                errs = {"point": pt, "r": pct(r, tr["r"])}
            results.append({"id": it["id"], "tier": it["tier"], "chartType": it["chartType"],
                            "flags": it["flags"], "errors": errs})
        (B / "floor.json").write_text(json.dumps(results, indent=1))
        await b.close()

        # report
        print(f"{'chart':22s} {'tier':5s} {'type':8s} {'flags':18s} errors(%)")
        allv = []
        for r in results:
            e = " ".join(f"{k}={v:.2f}" for k, v in r["errors"].items())
            allv += list(r["errors"].values())
            print(f"{r['id']:22s} {r['tier']:5s} {r['chartType']:8s} {','.join(r['flags']) or '-':18s} {e}")
        print(f"\nGEOMETRY FLOOR (manual ceiling): worst {max(allv):.2f}%  median {statistics.median(allv):.2f}%")
        print("=> this is the accuracy WPD/metaDigitise achieve with correct clicks; the vision reader is scored vs the same GT.")


if __name__ == "__main__":
    asyncio.run(run())
