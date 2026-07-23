#!/usr/bin/env python3
"""score_real.py -- the REAL-FIGURE golden-diff scorer.

For each real panel we have:
  tasks/<id>.json    -- the panel task: image, axis calibration VALUES, and the coded
                        comparisons (control vs each intervention arm) with the
                        hand-coded mean/sd/n the dissertation recorded from this figure.
  vision/<id>.json   -- a reader's PICKED pixels: 4 axis-reference pixels + per-bar
                        {top, cap} pixels. (Here: a genuine model-in-the-loop read; the
                        same slot a trained detector or a WPD/human export would fill.)

The picked pixels flow through the SHARED affine (harness/calibrate.py -- the exact math
window.figureExtractor.calibrate uses, byte-verified against the JS tool) to recover:
  bar-top  -> mean         (central-tendency channel, a LONG pixel distance = easy)
  |cap-top|-> dispersion   (error-bar channel, a SHORT pixel distance = load-bearing)

Dispersion-type is resolved from TEXT (caption/convention), never pixels: these papers
plot mean +/- SEM, so extracted SD = (cap-top units) * sqrt(n). The % transfer gap on the
dispersion channel is invariant to that choice (the sqrt(n) cancels in the ratio); the
choice only matters for the absolute SD fed to escalc.

Outputs:
  out/fields.csv      -- per bar: coded vs extracted mean & SD, % transfer gaps.
  out/comparisons.csv -- per comparison: coded vs extracted g (recomputed via the SAME
                         Hedges-g formula), ready for the R end-to-end golden diff.
  out/summary.json    -- channel medians/worst (central vs DISPERSION) + coverage.
Prints the dispersion-first headline.

Reuses benchmark/harness/calibrate.py; does NOT modify it.
"""
import csv, json, math, pathlib, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
HARNESS = HERE.parent / "harness"
sys.path.insert(0, str(HARNESS))
from calibrate import py_calibrate  # noqa: E402

TASKS = HERE / "tasks"
VISION = HERE / "vision"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)


def pct(est, ref):
    return 100 * abs(est - ref) / abs(ref) if ref else float("nan")


def hedges_g(m1, sd1, n1, m2, sd2, n2):
    """Standard bias-corrected SMD (escalc measure='SMD'): (m2-m1)/s_pooled * J.
    Sign convention here: intervention (2) minus control (1). Returns (g, vi)."""
    df = n1 + n2 - 2
    sp = math.sqrt(((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / df)
    d = (m2 - m1) / sp
    J = 1 - 3 / (4 * df - 1)
    g = J * d
    vi = (n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2))  # metafor SMD large-sample vi
    return g, vi


def recover_bar(cal_px, cal_vals, top_px, cap_px):
    pts = py_calibrate(cal_px, cal_vals, [top_px, cap_px])
    top_v, cap_v = pts[0]["y"], pts[1]["y"]
    return top_v, abs(cap_v - top_v)  # (mean, dispersion in data units == cap length)


def score_panel(task, vision):
    cal_px = vision["calPixels"]
    cal_vals = task["calVals"]
    shown = task.get("dispersion_shown", "SEM").upper()
    bars_v = vision["bars"]

    # recover each bar once (mean + cap-length in data units)
    rec = {}
    for key, pk in bars_v.items():
        mean, caplen = recover_bar(cal_px, cal_vals, pk["top"], pk["cap"])
        rec[key] = {"mean": mean, "caplen": caplen}

    field_rows, comp_rows = [], []
    for comp in task["comparisons"]:
        for role in ("control", "interv"):
            bar_key = comp[role + "_bar"]
            g = comp[role]
            n = g["n"]
            r = rec[bar_key]
            sd_ext = r["caplen"] * math.sqrt(n) if shown == "SEM" else r["caplen"]
            field_rows.append({
                "id": task["id"], "row_id": comp["row_id"], "bar": bar_key, "role": role,
                "n": n, "mean_coded": g["mean"], "mean_ext": round(r["mean"], 4),
                "sd_coded": g["sd"], "sd_ext": round(sd_ext, 4),
                "caplen_units": round(r["caplen"], 4),
                "mean_gap_pct": round(pct(r["mean"], g["mean"]), 3),
                "sd_gap_pct": round(pct(sd_ext, g["sd"]), 3),
            })
        c, i = comp["control"], comp["interv"]
        ck, ik = comp["control_bar"], comp["interv_bar"]
        c_sd_ext = rec[ck]["caplen"] * (math.sqrt(c["n"]) if shown == "SEM" else 1)
        i_sd_ext = rec[ik]["caplen"] * (math.sqrt(i["n"]) if shown == "SEM" else 1)
        g_cod, vi_cod = hedges_g(c["mean"], c["sd"], c["n"], i["mean"], i["sd"], i["n"])
        g_ext, vi_ext = hedges_g(rec[ck]["mean"], c_sd_ext, c["n"],
                                 rec[ik]["mean"], i_sd_ext, i["n"])
        comp_rows.append({
            "id": task["id"], "row_id": comp["row_id"], "article": task["article"],
            "direction": comp.get("direction", ""),
            "c_mean_coded": c["mean"], "c_sd_coded": c["sd"], "c_n": c["n"],
            "i_mean_coded": i["mean"], "i_sd_coded": i["sd"], "i_n": i["n"],
            "c_mean_ext": round(rec[ck]["mean"], 4), "c_sd_ext": round(c_sd_ext, 4),
            "i_mean_ext": round(rec[ik]["mean"], 4), "i_sd_ext": round(i_sd_ext, 4),
            "g_coded": round(g_cod, 4), "vi_coded": round(vi_cod, 5),
            "g_ext": round(g_ext, 4), "vi_ext": round(vi_ext, 5),
            "g_abs_diff": round(abs(g_ext - g_cod), 4),
        })
    return field_rows, comp_rows


def main():
    task_files = sorted(TASKS.glob("*.json"))
    all_fields, all_comps, scored, skipped = [], [], [], []
    for tf in task_files:
        task = json.loads(tf.read_text())
        vf = VISION / tf.name
        if not vf.exists():
            skipped.append(task["id"]); continue
        vision = json.loads(vf.read_text())
        fr, cr = score_panel(task, vision)
        all_fields += fr; all_comps += cr; scored.append(task["id"])

    if all_fields:
        with open(OUT / "fields.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_fields[0].keys())); w.writeheader(); w.writerows(all_fields)
    if all_comps:
        with open(OUT / "comparisons.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_comps[0].keys())); w.writeheader(); w.writerows(all_comps)

    mean_gaps = [r["mean_gap_pct"] for r in all_fields]
    sd_gaps = [r["sd_gap_pct"] for r in all_fields]
    g_diffs = [r["g_abs_diff"] for r in all_comps]
    summary = {
        "panels_scored": scored, "panels_unread": skipped,
        "n_bars": len(all_fields), "n_comparisons": len(all_comps),
        "central_channel": {"median_pct": _med(mean_gaps), "worst_pct": _mx(mean_gaps)},
        "dispersion_channel": {"median_pct": _med(sd_gaps), "worst_pct": _mx(sd_gaps)},
        "golden_diff_field": {"median_abs_g": _med(g_diffs), "worst_abs_g": _mx(g_diffs)},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))

    print("=== REAL-FIGURE golden diff -- pilot ===")
    print(f"panels scored : {len(scored)}  ({', '.join(scored)})")
    if skipped:
        print(f"panels unread : {', '.join(skipped)}")
    print(f"bars: {len(all_fields)}  comparisons: {len(all_comps)}\n")
    print("channel                         | median % | worst % | n")
    print(f"central tendency (bar mean)     | {_med(mean_gaps):7.2f}  | {_mx(mean_gaps):6.2f}  | {len(mean_gaps)}")
    print(f"DISPERSION (error-bar -> SD)    | {_med(sd_gaps):7.2f}  | {_mx(sd_gaps):6.2f}  | {len(sd_gaps)}")
    print(f"\ngolden diff (Hedges g, field): median |dg|={_med(g_diffs):.3f}  worst |dg|={_mx(g_diffs):.3f}  (n={len(g_diffs)})")
    print(f"\n[written] {OUT/'fields.csv'}\n[written] {OUT/'comparisons.csv'}\n[written] {OUT/'summary.json'}")


def _med(v): return round(statistics.median(v), 3) if v else None
def _mx(v): return round(max(v), 3) if v else None


if __name__ == "__main__":
    main()
