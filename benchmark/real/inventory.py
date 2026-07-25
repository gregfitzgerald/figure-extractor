#!/usr/bin/env python3
"""inventory.py -- build the REAL-FIGURE golden-diff population from the dissertation's
hand-coded meta-analysis, and report feasibility honestly.

Population = every coded row whose data provenance is a FIGURE (the study's numbers were
read off a chart, not a table/text). This is the exact subset for which an automated
chart-reader could have substituted for the human digitizer -- so it is the population on
which the "automated reader vs human on the dispersion channel" claim must be tested.

Provenance rule (matches the dissertation codebook's Data_Source / Data_Extraction_Method):
  figure-derived  <=>  Data_Source begins with "figure"
                        OR Data_Extraction_Method names a figure-reading act
                        ("estimated from figure", "extracted from figure",
                         "direct from figure", "figure analysis",
                         "reported in figure", "re-extracted ...").

Outputs (written next to this file):
  population.json  -- one record per figure-derived row with the fields the golden diff
                      needs: article, panel, group means/SDs/Ns, Direction, coded Hedges g.
  articles.json    -- article -> {doi, panels[], n_rows} (the panel-matching worklist).
Prints a feasibility table (rows, articles, completeness, dispersion/outcome mix).

Reads the dissertation CSVs read-only; writes nothing outside benchmark/real/.
"""
import csv, json, re, pathlib, statistics
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
# Hand-coded reference data from the companion meta-analysis, used as the real-figure gold standard:
#   https://github.com/gregfitzgerald/GSF-dissertation-meta-analysis
# Default expects that repo cloned as a SIBLING of this one; override with RODENT_CSV / HUMAN_CSV.
import os
_SIBLING = pathlib.Path(__file__).resolve().parents[2].parent / "GSF-dissertation-meta-analysis" / "data" / "raw"
RODENT = os.environ.get("RODENT_CSV", str(_SIBLING / "rodent_data.csv"))
HUMAN = os.environ.get("HUMAN_CSV", str(_SIBLING / "human_data.csv"))

_FIG_METHODS = ("estimated from figure", "extracted from figure", "direct from figure",
                "figure analysis", "visual analysis of figure", "reported in figure",
                "re-extracted")


def is_figure_derived(row):
    ds = (row.get("Data_Source") or "")
    dm = (row.get("Data_Extraction_Method") or "").lower()
    return bool(re.match(r"^\s*figure", ds, re.I)) or any(k in dm for k in _FIG_METHODS)


def _f(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def _panel(ds):
    """Normalise 'Figure 3D' / 'figure 2-b' / 'Fig 2B' -> 'fig3d' token; None if unnamed."""
    m = re.search(r"figure\s*([0-9]+)\s*[-\s]?\s*([a-z]?)", (ds or ""), re.I)
    if not m:
        return None
    num, let = m.group(1), (m.group(2) or "").lower()
    return f"fig{num}{let}"


def load_rodent():
    with open(RODENT, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for i, r in enumerate(rows):
        if not is_figure_derived(r):
            continue
        c_sd = _f(r.get("Control_Group_SD")) or _f(r.get("Control_Group_Variance_Value"))
        i_sd = _f(r.get("Intervention_Group_Variance_Value")) or _f(r.get("Enriched_Group_SD"))
        rec = {
            "row_id": f"{r['Article_ID']}__r{i}",
            "article": r.get("Article_ID", ""),
            "doi": (r.get("DOI") or "").strip().replace("https://doi.org/", ""),
            "data_source": (r.get("Data_Source") or "").strip(),
            "panel": _panel(r.get("Data_Source")),
            "test": (r.get("Test_Name") or "").strip(),
            "variable": (r.get("Variable_Name") or "").strip(),
            "unit": (r.get("Variable_Unit") or "").strip(),
            "direction": (r.get("Direction") or "").strip(),
            "control_n": _f(r.get("Control_N")),
            "control_mean": _f(r.get("Control_Group_Mean")),
            "control_sd": c_sd,
            "interv_n": _f(r.get("Intervention_N")),
            "interv_mean": _f(r.get("Intervention_Group_Mean")),
            "interv_sd": i_sd,
            "variance_source": (r.get("Variance_Source") or "").strip(),
            "hedges_g": _f(r.get("Hedges_g_corrected")),
            "vi": _f(r.get("vi_adjusted_multiarm")),
            "domain": (r.get("Cognitive_Domain") or "").strip(),
            "species": (r.get("Species") or "").strip(),
        }
        rec["complete"] = all(rec[k] is not None for k in
            ("control_n", "control_mean", "control_sd", "interv_n", "interv_mean", "interv_sd"))
        out.append(rec)
    return out


def main():
    pop = load_rodent()
    (HERE / "population.json").write_text(json.dumps(pop, indent=2))

    arts = defaultdict(lambda: {"doi": "", "panels": Counter(), "n_rows": 0})
    for r in pop:
        a = arts[r["article"]]
        a["doi"] = r["doi"]
        a["panels"][r["data_source"]] += 1
        a["n_rows"] += 1
    articles = {k: {"doi": v["doi"], "n_rows": v["n_rows"],
                    "panels": dict(v["panels"])} for k, v in sorted(arts.items())}
    (HERE / "articles.json").write_text(json.dumps(articles, indent=2))

    complete = [r for r in pop if r["complete"]]
    named = [r for r in pop if r["panel"]]
    print("=== REAL-FIGURE golden-diff population (rodent MA) ===")
    print(f"figure-derived rows        : {len(pop)}")
    print(f"  with complete C/I m,sd,n : {len(complete)}")
    print(f"  with a named panel       : {len(named)}")
    print(f"distinct articles          : {len(articles)}")
    print(f"\nDirection : {dict(Counter(r['direction'] for r in pop))}")
    print(f"Variance  : {dict(Counter(r['variance_source'] for r in pop))}")
    print(f"Domain    : {dict(Counter(r['domain'] for r in pop))}")
    ns = [r['control_n'] for r in complete if r['control_n']]
    print(f"Control_N : median={statistics.median(ns):.0f} range={min(ns):.0f}-{max(ns):.0f}"
          f"  (short-n studies are where cap error hurts variance most)")
    print(f"\n[written] {HERE/'population.json'}  ({len(pop)} rows)")
    print(f"[written] {HERE/'articles.json'}    ({len(articles)} articles)")


if __name__ == "__main__":
    main()
