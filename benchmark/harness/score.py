#!/usr/bin/env python3
"""score.py -- the tool-comparison harness. Scores any extraction tool against R's
AUTHORITATIVE descriptives, with the DISPERSION (error-bar) channel reported as a
first-class, separate headline.

Common tool interface -- a tool is a function  bundle -> tool_output  where
    tool_output = {
      "calPixels": {x1,x2,y1,y2:{px,py}},   # 4 axis-reference pixels the tool picked
      "calVals":   {x1,x2,y1,y2,logX,logY}, # their known data values (from the task)
      "landmarks": [{role,group,series?,px,py}]  # picked landmark pixels
    }
Every tool's picked pixels flow through the SAME affine (calibrate.py, a port of the
tool's computeCalibration) -> data values -> compared to R's descriptives. This makes
tools commensurable: they differ only in the pixels they pick, never in the arithmetic.

Built-in tools:
  geometry_floor : uses the GT's own calibration + GT landmark pixels = perfect clicks.
                   This is the MANUAL CEILING (what WPD/metaDigitise achieve with correct
                   clicks) and also validates that the GT bundle round-trips to R's numbers.
  vision         : reads agent pixel estimates from benchmark/vision/<id>.json.
Adapter hooks for WebPlotDigitizer / metaDigitise are stubbed in tools_external.py.

Dispersion metric framing: a b% error in the error-cap -> ~2b% error in variance ->
~sqrt(n) study mis-weighting. So the cap channel is where meta-analytic risk concentrates.

Run: python3 benchmark/harness/score.py [--tool geometry_floor|vision] [--engine py|js]
"""
import argparse, json, pathlib, statistics, sys, zlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus"
VISION = HERE.parent / "vision"
sys.path.insert(0, str(HERE))
from calibrate import py_calibrate  # noqa: E402


def pct(r, t):
    return 100 * abs(r - t) / abs(t) if t else abs(r - t)


def load_bundles(ids=None):
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    ids = ids or manifest["ids"]
    out = []
    for i in ids:
        b = json.loads((CORPUS / f"{i}.gt.json").read_text())
        b["_corpus"] = str(CORPUS)
        out.append(b)
    return out


# ---- descriptives-key mapping (landmark group/series -> R descriptives key) -----
def desc_key(b, lm):
    ct = b["chartType"]
    g = lm["group"]; groups = b.get("groups") or []
    if ct == "line":
        return f"{lm['series']}@{b['doses'][g]}"
    if b.get("series") and lm.get("series") not in (None, "s1", "NA"):
        return f"{groups[g]}/{lm['series']}"
    return groups[g] if groups else str(g)


def disp_field(b):
    dt = b.get("dispersionType")
    return {"SD": "sd", "SEM": "sem", "SE": "sem", "CI95": "ci_half"}.get(dt, "sd")


# ============================ TOOLS ============================================
def tool_geometry_floor(b):
    """Perfect clicks: the GT's own calibration + GT landmark pixels."""
    return {
        "calPixels": b["calibration"]["calPixels"],
        "calVals": b["calibration"]["calVals"],
        "landmarks": [{"role": l["role"], "group": l["group"],
                       "series": l.get("series"), "px": l["px"], "py": l["py"]}
                      for l in b["landmarks"]],
    }


def tool_vision(b):
    """Agent pixel estimates from benchmark/vision/<id>.json (leak-free task output).
    Schema: {calPixels:{x1..y2:{px,py}}, landmarks:{"<role>_<group>[_<series>]":{px,py}}}."""
    vf = VISION / f"{b['id']}.json"
    if not vf.exists():
        return None
    est = json.loads(vf.read_text())
    elm = est["landmarks"]
    out = []
    for l in b["landmarks"]:
        key = f"{l['role']}_{l['group']}"
        if l.get("series") and l["series"] not in (None, "s1", "NA"):
            key += f"_{l['series']}"
        if key not in elm:
            return None  # incomplete estimate -> counted as missing
        out.append({"role": l["role"], "group": l["group"], "series": l.get("series"),
                    "px": elm[key]["px"], "py": elm[key]["py"]})
    return {"calPixels": est["calPixels"], "calVals": b["calibration"]["calVals"],
            "landmarks": out}


def make_human_floor(sigma=1.0, seed=0):
    """Realistic manual ceiling: perturb every calibration + landmark pixel by Gaussian
    noise (sigma px) to emulate a human clicking (WPD/metaDigitise). Unlike the exact-pixel
    floor (0%), this shows what ~1px click jitter actually costs each channel -- and it
    costs the dispersion channel most, because short SEM/CI caps have the worst
    pixel-to-value leverage. Seeded per chart for reproducibility."""
    import random

    def tool(b):
        # crc32, NOT hash(). CPython salts str hashing per process (PYTHONHASHSEED), so
        # `hash(b["id"])` gave a different jitter stream on every run -- which made this
        # function, whose own docstring promises "seeded per chart for reproducibility",
        # the one thing in the benchmark that could not be reproduced. Re-running the
        # published table moved the dispersion-worst column by tens of percentage points
        # while the medians stayed put, so the headline row nobody could reproduce was the
        # WORST-case column. crc32 is stable across processes, machines and versions.
        rng = random.Random((zlib.crc32(b["id"].encode()) & 0xffffffff)
                            ^ (seed * 2654435761 & 0xffffffff))

        def jit(p):
            return {"px": p["px"] + rng.gauss(0, sigma), "py": p["py"] + rng.gauss(0, sigma)}

        cp = b["calibration"]["calPixels"]
        return {"calPixels": {k: jit(v) for k, v in cp.items()},
                "calVals": b["calibration"]["calVals"],
                "landmarks": [{"role": l["role"], "group": l["group"], "series": l.get("series"),
                               **jit(l)} for l in b["landmarks"]]}
    return tool


TOOLS = {"geometry_floor": tool_geometry_floor, "vision": tool_vision,
         "human_floor": make_human_floor(1.0)}
try:
    from tools_cv import tool_cv_autoreader
    TOOLS["cv_autoreader"] = tool_cv_autoreader
except Exception:
    pass
try:
    from tools_external import make_external_tool
    TOOLS["webplotdigitizer"] = make_external_tool("webplotdigitizer")
    TOOLS["metadigitise"] = make_external_tool("metadigitise")
except Exception:
    pass


# ============================ CALIBRATION ENGINE ===============================
def recover(tool_out, engine="py"):
    """pixels -> data values, in landmark order. engine 'py' (default) or 'js' (real tool)."""
    cal, vals = tool_out["calPixels"], tool_out["calVals"]
    pts = [{"px": l["px"], "py": l["py"]} for l in tool_out["landmarks"]]
    if engine == "js":
        import asyncio
        from calibrate import js_calibrate_batch
        return asyncio.get_event_loop().run_until_complete(
            js_calibrate_batch([(cal, vals, pts)]))[0]
    return py_calibrate(cal, vals, pts)


# ============================ SCORING =========================================
def score_bundle(b, tool_out, engine="py"):
    dv = recover(tool_out, engine)
    lm = tool_out["landmarks"]
    ct = b["chartType"]; D = b["descriptives"]
    idx = {}
    for j, l in enumerate(lm):
        idx.setdefault((l["role"], l["group"], l.get("series")), j)
    ch = {}

    if ct in ("bar", "line"):
        means, disps = [], []
        df = disp_field(b) if ct == "bar" else "sem"
        seen = set()
        for l in lm:
            key = (l["group"], l.get("series"))
            if key in seen:
                continue
            seen.add(key)
            jt = idx.get(("top", l["group"], l.get("series")))
            jc = idx.get(("cap", l["group"], l.get("series")))
            if jt is None or jc is None:
                continue
            top = dv[jt]["y"]; cap = dv[jc]["y"]
            k = desc_key(b, l)
            if k not in D:
                continue
            means.append(pct(top, D[k]["mean"]))
            disps.append(pct(abs(cap - top), D[k][df]))
        ch = {"central": statistics.mean(means), "dispersion": statistics.mean(disps)}

    elif ct == "box":
        cent, disps = [], []
        for gi, gname in enumerate(b["groups"]):
            vals = {}
            for role in ("q1", "med", "q3"):
                j = idx.get((role, gi, None))
                if j is not None:
                    vals[role] = dv[j]["y"]
            if "med" in vals:
                cent.append(pct(vals["med"], D[gname]["median"]))
            if "q1" in vals and "q3" in vals:
                cent.append(pct(vals["q1"], D[gname]["q1"]))
                cent.append(pct(vals["q3"], D[gname]["q3"]))
                disps.append(pct(vals["q3"] - vals["q1"], D[gname]["iqr"]))
        ch = {"central": statistics.mean(cent), "dispersion": statistics.mean(disps)}

    elif ct == "scatter":
        xs = np.array([d["x"] for d in dv]); ys = np.array([d["y"] for d in dv])
        tx = np.array([v for v in b["data"]["x"]]); ty = np.array([v for v in b["data"]["y"]])
        xr = tx.max() - tx.min() or 1.0; yr = ty.max() - ty.min() or 1.0
        perr = []
        for j in range(len(xs)):  # unordered -> nearest true point
            dd = ((tx - xs[j]) / xr) ** 2 + ((ty - ys[j]) / yr) ** 2
            k = int(np.argmin(dd))
            perr.append(50 * (abs(tx[k] - xs[j]) / xr + abs(ty[k] - ys[j]) / yr))
        r = float(np.corrcoef(xs, ys)[0, 1])
        slope = float(np.polyfit(xs, ys, 1)[0])
        ch = {"point": statistics.mean(perr), "r": pct(r, D["r"]),
              "slope": pct(slope, D["slope"])}

    return ch


# ============================ RUN + REPORT =====================================
def run(tool_name, engine, ids=None):
    bundles = load_bundles(ids)
    tool = TOOLS[tool_name]
    rows, missing = [], []
    for b in bundles:
        to = tool(b)
        if to is None:
            missing.append(b["id"]); continue
        ch = score_bundle(b, to, engine)
        rows.append({"id": b["id"], "tier": b["tier"], "type": b["chartType"],
                     "flags": b.get("flags", []), "channels": ch})
    return rows, missing


def report(tool_name, rows, missing, engine):
    def vals(pred, chan=None):
        out = []
        for r in rows:
            if not pred(r):
                continue
            for k, v in r["channels"].items():
                if chan is None or k == chan:
                    out.append(v)
        return out

    disp = vals(lambda r: True, "dispersion")
    cent = vals(lambda r: True, "central") + vals(lambda r: True, "point")
    L = [f"# R-GT benchmark -- {tool_name} vs R's authoritative descriptives", "",
         f"Engine: `{engine}` ({'real window.figureExtractor.calibrate' if engine=='js' else 'faithful port of the tool affine'}).  "
         f"Charts scored: {len(rows)}" + (f" (missing: {', '.join(missing)})" if missing else "") + ".", "",
         "All errors are % vs the values R computed from the raw simulated data. The chart was",
         "rendered FROM that data, so the ground truth is what R drew, not an eyeballed re-read.", "",
         "## Headline channels (% error)", "",
         "| channel | median | worst | n |", "|---|---|---|---|"]
    if cent:
        L.append(f"| central tendency (mean/median/point) | {statistics.median(cent):.2f} | {max(cent):.2f} | {len(cent)} |")
    if disp:
        L.append(f"| **dispersion (error-bar / IQR)** | **{statistics.median(disp):.2f}** | **{max(disp):.2f}** | {len(disp)} |")
    L += ["", "The dispersion row is the load-bearing one: a b% cap error -> ~2b% variance error ->",
          "~sqrt(n) study mis-weighting in a meta-analysis.", "",
          "## By tier (all channels)", "", "| tier | median | worst | n |", "|---|---|---|---|"]
    for t in ("clean", "hard"):
        v = vals(lambda r: r["tier"] == t)
        L.append(f"| {t} | {statistics.median(v):.2f} | {max(v):.2f} | {len(v)} |" if v else f"| {t} | - | - | 0 |")
    L += ["", "## Per chart", "", "| chart | tier | type | flags | errors (%) |", "|---|---|---|---|---|"]
    for r in rows:
        e = " ".join(f"{k}={v:.2f}" for k, v in r["channels"].items())
        L.append(f"| {r['id']} | {r['tier']} | {r['type']} | {','.join(r['flags']) or '-'} | {e} |")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", default="geometry_floor", choices=list(TOOLS))
    ap.add_argument("--engine", default="py", choices=["py", "js"])
    ap.add_argument("--sigma", type=float, default=None, help="human_floor click jitter (px)")
    ap.add_argument("--seed", type=int, default=0, help="human_floor RNG seed")
    ap.add_argument("--out", default=None, help="write report to this path")
    args = ap.parse_args()
    if args.tool == "human_floor" and args.sigma is not None:
        TOOLS["human_floor"] = make_human_floor(args.sigma, args.seed)
    rows, missing = run(args.tool, args.engine)
    rep = report(args.tool, rows, missing, args.engine)
    print(rep)
    outp = args.out or (HERE.parent / f"RESULTS_{args.tool}.md")
    pathlib.Path(outp).write_text(rep)
    print(f"\n[written] {outp}")
