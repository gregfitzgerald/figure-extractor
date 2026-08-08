#!/usr/bin/env python3
"""make_synthetic_reference.py -- emits `synthetic_reference.json` from the LIVE scorer.

Why this script exists. The panels block of `synthetic_reference.json` used to be
hand-copied from `benchmark/panels/RESULTS.md`. When the cascade's abstention numbers
changed (precision 0.88 -> 0.14, recall 0.94 -> 1.00, net figures saved +13 -> -10), the
committed artifact kept the superseded values -- and because the analysis plan validates
against that artifact, the stale numbers would have been laundered into the
pre-registration unchallenged (amendment A18). A comparator that a human has to remember
to update is a comparator that will drift; this script removes the human from the loop.

The PANELS block is computed by importing `benchmark/panels/score.py` and scoring the
committed prediction run with the scorer's own functions -- the same `score_figure` /
`agg` / `abstention` code paths as `python3 score.py --run post_fix_ext --abstain-at 0.35`.
The remaining blocks (classify, series, channels, goldenDiff, thresholds) are frozen
numbers from benchmarks whose scorers live elsewhere; they are carried here as data, with
their sources named, so this file is the single place they are written down.

Run (from benchmark/real-validation/):

  python3 make_synthetic_reference.py            # regenerate synthetic_reference.json
  python3 make_synthetic_reference.py --check    # exit 1 if the committed file is stale

Re-run whenever the panels prediction run or `--abstain-at` gate changes, and commit the
result. `--check` makes staleness mechanical to detect.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PANELS_DIR = HERE.parent / "panels"
OUT = HERE / "synthetic_reference.json"

# The run and gate the synthetic comparators are defined on. `post_fix_ext` is the final
# cascade over the full 41-figure corpus; 0.35 is the cascade's own abstention gate
# (benchmark/panels/RESULTS.md sec.7).
PANELS_RUN = "post_fix_ext"
ABSTAIN_AT = 0.35


def _load_panels_scorer():
    spec = importlib.util.spec_from_file_location("panels_score", PANELS_DIR / "score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _r3(x):
    return round(x, 3)


def live_panels_block():
    """The panels comparators, computed by the panel scorer's own code paths."""
    sc = _load_panels_scorer()
    gts = sc.load_gt()
    preds = sc.load_preds(PANELS_RUN)
    figs = [sc.score_figure(gts[c], preds.get(c), ABSTAIN_AT) for c in gts]
    A = sc.agg(figs)
    ab = sc.abstention(figs)
    n_figs, n_pans, n_ans = A["figures"], A["panels"], A["answered"]
    n_wrong = sum(1 for f in figs if f["wrong"])
    return {
        "n_figures": n_figs,
        "n_panels": n_pans,
        "iouMedian":            {"value": _r3(A["iouMedian"]), "unit": "iou",  "higherBetter": True,  "maxDelta": 0.10, "threshold": 0.90},
        "pct90":                {"value": _r3(A["pct90"]), "unit": "prop", "higherBetter": True,  "maxDelta": 0.23, "threshold": 0.65, "n": n_pans},
        "pct50":                {"value": _r3(A["pct50"]), "unit": "prop", "higherBetter": True,  "maxDelta": None, "threshold": 0.90, "n": n_pans},
        "countAcc":             {"value": _r3(A["countAcc"]), "unit": "prop", "higherBetter": True,  "maxDelta": 0.10, "threshold": 0.85, "n": n_figs},
        "labelAccLocalised":    {"value": _r3(A["labelAccLocalised"]), "unit": "prop", "higherBetter": True,  "maxDelta": 0.02, "threshold": 0.98, "n": n_pans},
        "silentMislabel":       {"value": _r3(A["silentMislabel"]), "unit": "prop", "higherBetter": False, "maxDelta": 0.025, "threshold": 0.025, "n": n_pans, "zeroEvent": True},
        "figExactAnswered":     {"value": _r3(A["figExactAnswered"]), "unit": "prop", "higherBetter": True,  "maxDelta": 0.15, "threshold": 0.85, "n": n_ans},
        "errorRateAnswered":    {"value": _r3(ab["errorRateAnswered"]), "unit": "prop", "higherBetter": False, "maxDelta": 0.10, "threshold": 0.10, "n": n_ans, "zeroEvent": True},
        "coverage":             {"value": _r3(ab["coverage"]), "unit": "prop", "higherBetter": True,  "maxDelta": 0.16, "threshold": 0.50, "n": n_figs},
        "abstentionPrecision":  {"value": _r3(ab["precision"]), "unit": "prop", "higherBetter": True,  "maxDelta": None, "threshold": None,
                                 "note": "descriptive since amendment A18 (the pre-A18 threshold was >= 0.60); the cost side of the recall gate"},
        "abstentionRecall":     {"value": _r3(ab["recall"]), "unit": "prop", "higherBetter": True,  "maxDelta": None, "threshold": 1.0, "gate": True, "n": n_wrong,
                                 "note": "GATE since amendment A18, stated as 0 missed errors (answered-and-wrong figures); "
                                         "n is the number of wrong figures the recall was computed on"},
        "netFiguresSaved":      {"value": ab["net"], "unit": "count", "higherBetter": True, "maxDelta": None, "threshold": None,
                                 "note": "descriptive since amendment A18. The pre-A18 gate was > 0 and this value FAILS it; "
                                         "recorded, not hidden -- see ANALYSIS-PLAN.md A18"},
    }


# ---------------------------------------------------------------------------------------
# Frozen blocks. Sources are named in `sources` below; these numbers are not computable
# from this directory (their scorers and runs live in benchmark/classify, benchmark/series
# and benchmark/real) and are transcribed ONCE, here, instead of directly in the JSON.
# ---------------------------------------------------------------------------------------
STATIC = {
    "classify": {
        "n": 80,
        "accuracy":          {"value": 1.000, "unit": "prop", "higherBetter": True,  "maxDelta": 0.10, "threshold": 0.90, "n": 80},
        "macroF1":           {"value": 1.000, "unit": "prop", "higherBetter": True,  "maxDelta": None, "threshold": 0.85},
        "priorityFlipRate":  {"value": 0.000, "unit": "prop", "higherBetter": False, "maxDelta": 0.05, "threshold": 0.05, "n": 80, "zeroEvent": True, "gate": True},
        "ece":               {"value": 0.072, "unit": "abs",  "higherBetter": False, "maxDelta": None, "threshold": 0.15},
    },
    "series": {
        "n_marks_base": 495, "n_marks_stress": 229, "n_series_base": 57,
        "misassignSeriesBound": {"value": 0.000, "unit": "prop", "higherBetter": False, "maxDelta": 0.02, "threshold": 0.02, "n": 495, "zeroEvent": True,
                                 "stress": 0.048},
        "misassignArmBound":    {"value": 0.000, "unit": "prop", "higherBetter": False, "maxDelta": 0.02, "threshold": 0.02, "n": 495, "zeroEvent": True,
                                 "stress": 0.048},
        "misassignStructural":  {"value": 0.000, "unit": "prop", "higherBetter": False, "maxDelta": 0.05, "threshold": 0.05, "n": 495, "zeroEvent": True},
        "meanARI":              {"value": 1.000, "unit": "abs",  "higherBetter": True,  "maxDelta": None, "threshold": 0.90, "stress": 0.930},
        "armNameAccuracy":      {"value": 1.000, "unit": "prop", "higherBetter": True,  "maxDelta": 0.01, "threshold": 0.99, "n": 57, "gate": True},
        "signFlipRate":         {"value": 0.000, "unit": "prop", "higherBetter": False, "maxDelta": 0.05, "threshold": 0.05, "n": 145, "zeroEvent": True, "gate": True},
    },
    "channels": {
        "_comment": "human_floor = Greg's own 1px click jitter measured against R's exact descriptives.",
        "centralMedianPct":     {"value": 0.44,  "unit": "pct", "higherBetter": False, "maxDelta": -0.6, "threshold": 1.0,
                                 "alt": {"cv_autoreader": 0.45, "vision_agent": 1.17, "real_pilot_n16": 0.47}},
        "dispersionMedianPct":  {"value": 3.89,  "unit": "pct", "higherBetter": False, "maxDelta": None, "threshold": None,
                                 "alt": {"cv_autoreader": 8.89, "vision_agent": 8.20, "real_pilot_n16": 3.67},
                                 "note": "NOT an accuracy threshold on real figures -- see ANALYSIS-PLAN sec.1. Context only."},
        "dispersionWorstPct":   {"value": 27.7,  "unit": "pct", "higherBetter": False, "maxDelta": None, "threshold": None,
                                 "alt": {"cv_autoreader": 21.5, "real_pilot_n16": 18.11}},
    },
    "goldenDiff": {
        "_comment": "the 8-comparison real pilot, for reference; not a synthetic comparator",
        "pilot": {"g_coded": 0.487, "g_ext": 0.475, "delta": -0.0125, "signFlips": 0, "nComparisons": 8,
                  "median_abs_dg": 0.017, "max_abs_dg": 0.078},
        "thresholds": {"absDeltaG": 0.05, "relDeltaG": 0.10, "ciOverlap": 0.90,
                       "tau2RatioLo": 0.80, "tau2RatioHi": 1.25, "i2AbsDiffPP": 10.0,
                       "medianAbsDg": 0.05, "maxAbsDg": 0.30,
                       "signFlipRate": 0.0, "weightRho": 0.95, "tostMargin": 0.10},
    },
    "dispersionAgreement": {
        "_comment": "no synthetic comparator exists for these -- they are real-figure-only constructs",
        "baBiasPct":        {"threshold": 5.0,  "gate": True},
        "baLoAPct":         {"threshold": 25.0, "gate": True},
        "grubbsRatioMG":    {"threshold": 1.5,  "gate": True, "target": 1.0},
        "shortCapTertilePct": {"threshold": 10.0, "gate": True},
        "midLongCapTertilePct": {"threshold": 5.0},
        "oracleMedianPct":  {"threshold": 5.0},
        "oracleP90Pct":     {"threshold": 15.0},
        "rFloor":           {"threshold": 1.0, "note": "R_floor <= 1 is the ML-detector NO-GO condition"},
    },
    "detection": {
        "_comment": "no synthetic detection benchmark exists; absolute thresholds only, Delta undefined",
        "figureIouMedian":      {"threshold": 0.90},
        "figureIouPct75":       {"threshold": 0.90},
        "figureRecall":         {"threshold": 0.95},
        "figurePrecision":      {"threshold": 0.90},
        "spuriousPerPage":      {"threshold": 0.15, "higherBetter": False},
        "captionAssocAccuracy": {"threshold": 0.95, "gate": True},
        "captionLetterAccuracy":{"threshold": 0.95, "gate": True},
    },
    "extraction": {
        "dispersionTypeAgreement":  {"threshold": 0.90},
        "dispersionTypeFlagRecall": {"threshold": 0.80, "gate": True},
        "centralMedianPct":         {"threshold": 1.0},
        "centralP95Pct":            {"threshold": 5.0},
        "centralWorstPct":          {"threshold": 10.0},
    },
}

# The comparators an earlier detector build produced, kept per this file's own rule
# ("if a synthetic tier is re-run, add a new dated block and keep this one"). These are the
# values the stale hand-maintained artifact silently preserved; amendment A18 is the record
# of what that cost.
SUPERSEDED = {
    "2026-07-27": {
        "panels": {
            "pct50":               {"value": 0.881, "note": "was a lower bound copied from the >=0.9 line; now measured directly"},
            "abstentionPrecision": {"value": 0.88, "threshold": 0.60},
            "abstentionRecall":    {"value": 0.94, "threshold": 0.50},
            "netFiguresSaved":     {"value": 13, "threshold": 0.0001, "gate": True,
                                    "note": "the pre-A18 gate (net > 0); the current build measures -10 and FAILS it"},
        },
    },
}


def build():
    doc = {
        "_comment": [
            "FROZEN synthetic comparators for the real-figure transfer gap Delta = synthetic - real.",
            "GENERATED by make_synthetic_reference.py -- do not edit by hand. The panels block is",
            "computed from benchmark/panels/score.py on the committed prediction run, so it cannot",
            "drift from the live scorer; re-run `python3 make_synthetic_reference.py` and commit",
            "whenever that run or its abstention gate changes (`--check` detects staleness).",
            "If a synthetic tier is re-run, the displaced values move to `superseded` under a date.",
            "'n' is the denominator the synthetic number was computed on -- needed for the",
            "rule-of-three bound on any 0.0/1.0 entry.",
        ],
        "frozenAt": "2026-08-08",
        "generatedBy": f"make_synthetic_reference.py (panels: run '{PANELS_RUN}', --abstain-at {ABSTAIN_AT})",
        "sources": {
            "panels": f"computed live from benchmark/panels/score.py, run '{PANELS_RUN}' at --abstain-at {ABSTAIN_AT} "
                      "(matches benchmark/panels/RESULTS.md sec.7)",
            "classify": "benchmark/classify/RESULTS.md (summary_firstpass, n=80)",
            "series": "benchmark/series/RESULTS.md (firstpass base 19 charts/495 marks; stress 4/229)",
            "channels": "benchmark/RESULTS_geometry_floor.md + benchmark/real/RESULTS.md sec.3",
        },
        "panels": live_panels_block(),
    }
    doc.update(STATIC)
    doc["superseded"] = SUPERSEDED
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="regenerate in memory and exit 1 if the committed file differs")
    args = ap.parse_args()
    doc = build()
    text = json.dumps(doc, indent=2) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"STALE: {OUT.name} does not match the live scorer -- "
                  f"re-run python3 {pathlib.Path(__file__).name}", file=sys.stderr)
            return 1
        print(f"{OUT.name} is current")
        return 0
    OUT.write_text(text)
    p = doc["panels"]
    print(f"wrote {OUT}")
    print(f"  panels ({p['n_figures']} figs / {p['n_panels']} panels): "
          f"iouMedian {p['iouMedian']['value']}  pct90 {p['pct90']['value']}  "
          f"countAcc {p['countAcc']['value']}  coverage {p['coverage']['value']}")
    print(f"  abstention: precision {p['abstentionPrecision']['value']}  "
          f"recall {p['abstentionRecall']['value']}  net {p['netFiguresSaved']['value']:+d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
