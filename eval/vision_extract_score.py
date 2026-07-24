#!/usr/bin/env python3
"""Score vision-in-the-loop extraction: feed each agent's estimated landmark PIXELS through
the tool's real calibration + extraction, compare recovered LANDMARKS to truth. Reports the
realistic error when an AGENT (not exact geometry) picks the landmarks. (The tool emits
landmarks — mean + error-cap half-width, box quartiles, forest estimate+CI — not effect sizes;
SD/variance is R's job, so we score the landmark channels the tool actually produces.)"""
import asyncio, json, pathlib

R = pathlib.Path(__file__).resolve().parent
URL = "http://localhost:8001/figure-extractor.html"
TRUTH = json.loads((R / "vtruth.json").read_text())


def load(k):
    p = R / "vresults" / f"{k}.json"
    return json.loads(p.read_text()) if p.exists() else None


async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); pg = await b.new_page(); await pg.goto(URL)

        async def cal(est, vals, pts):
            c = {"x1": est["x1"], "x2": est["x2"], "y1": est["y1"], "y2": est["y2"]}
            v = {**vals, "logX": False, "logY": False}
            return await pg.evaluate("(a)=>window.figureExtractor.calibrate(a.c,a.v,a.p)", {"c": c, "v": v, "p": pts})

        print(f"{'chart':10s} {'quantity':16s} {'true':>9s} {'recovered':>11s} {'err%':>7s}")
        errs = []
        for k, tr in TRUTH.items():
            est = load(k)
            if not est:
                print(f"{k:10s} MISSING agent estimate"); continue
            vals = tr["calVals"]

            if tr["kind"] == "bar":
                pts = [b["top"] for b in est["bars"]] + [b["cap"] for b in est["bars"]]
                dv = await cal(est, vals, pts)
                nb = len(est["bars"]); groups = []
                for i in range(nb):
                    mean = dv[i]["y"]; cap = dv[nb + i]["y"]
                    groups.append({"name": str(i), "mean": mean, "errorHalf": abs(cap - mean), "n": tr["ns"][i]})
                res = await pg.evaluate("(g)=>window.figureExtractor.extract.bars(g,'SEM')", groups)
                for i in range(nb):
                    # landmarks only: mean + error-cap half-width (data units). True errorHalf is the
                    # drawn SEM; SD derivation is R's job (tool no longer emits sd/se).
                    teh = tr["sds"][i] / (tr["ns"][i] ** 0.5)
                    for q, t, r in (("mean", tr["means"][i], res["groups"][i]["mean"]),
                                    ("errorHalf(SEM)", teh, res["groups"][i]["errorHalf"])):
                        e = 100 * abs(r - t) / abs(t); errs.append(e)
                        print(f"{k:10s} {('g%d %s'%(i,q)):16s} {t:9.2f} {r:11.2f} {e:6.1f}%")

            elif tr["kind"] == "box":
                pts = []
                for bx in est["boxes"]:
                    pts += [bx["q1"], bx["med"], bx["q3"]]
                dv = await cal(est, vals, pts)
                groups = []
                for i in range(len(est["boxes"])):
                    q1, med, q3 = dv[3*i]["y"], dv[3*i+1]["y"], dv[3*i+2]["y"]
                    groups.append({"name": str(i), "q1": q1, "median": med, "q3": q3, "n": 30})
                res = await pg.evaluate("(g)=>window.figureExtractor.extract.boxes(g)", groups)
                for i in range(len(tr["q"])):
                    # landmarks only: quartiles (Wan/Hozo median->mean/SD is R's job)
                    q = tr["q"][i]
                    for qn, t, r in (("q1", q["q1"], res["groups"][i]["q1"]),
                                     ("median", q["med"], res["groups"][i]["median"]),
                                     ("q3", q["q3"], res["groups"][i]["q3"])):
                        e = 100 * abs(r - t) / abs(t); errs.append(e)
                        print(f"{k:10s} {('g%d %s'%(i,qn)):16s} {t:9.2f} {r:11.2f} {e:6.1f}%")

            elif tr["kind"] == "forest":
                pts = []
                for rw in est["rows"]:
                    pts += [rw["est"], rw["lo"], rw["hi"]]
                dv = await cal(est, vals, pts)
                rows = []
                for i in range(len(est["rows"])):
                    rows.append({"label": str(i), "estimate": dv[3*i]["x"], "ciLo": dv[3*i+1]["x"], "ciHi": dv[3*i+2]["x"]})
                res = await pg.evaluate("(r)=>window.figureExtractor.extract.forest(r,'linear')", rows)
                for i in range(len(tr["rows"])):
                    # landmarks only: estimate + CI as printed (SE from the CI is R's job)
                    t = tr["rows"][i]
                    for qn, tv, r in (("estimate", t["est"], res["rows"][i]["estimate"]),
                                      ("ciLo", t["lo"], res["rows"][i]["ciLo"]),
                                      ("ciHi", t["hi"], res["rows"][i]["ciHi"])):
                        e = 100 * abs(r - tv) / abs(tv); errs.append(e)
                        print(f"{k:10s} {('r%d %s'%(i,qn)):16s} {tv:9.3f} {r:11.3f} {e:6.1f}%")

        if errs:
            import statistics
            print(f"\nvision-in-the-loop recovery error: median {statistics.median(errs):.1f}%  mean {statistics.mean(errs):.1f}%  max {max(errs):.1f}%")
        await b.close()


if __name__ == "__main__":
    asyncio.run(run())
