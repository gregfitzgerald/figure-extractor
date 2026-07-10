#!/usr/bin/env python3
"""
META layer core — turn structured article->studies records into effect sizes and an analysis-ready
studies table, per the APPROVED protocol (Hedges' g; RVE clustered by article).

This is the analysis-side counterpart to figure-extractor's `convert`/`extract` helpers: the tool
digitizes figures into per-arm mean/SD/n; this library grains them into STUDIES, computes g, and
emits studies.csv for metafor. Kept dependency-free (pure Python) so it runs in any analysis env.

Schema: see data-model.md.  Tests: test_metalib.py (the approved acceptance cases TC1-TC8).
"""
from __future__ import annotations
import math, csv, io

Z95 = 1.959964


# ---- dispersion -> SD (the load-bearing conversion) ----
def arm_sd(arm: dict) -> float | None:
    """Resolve an arm's SD from its reported dispersion + type (+ n). None if not resolvable."""
    if arm.get("sd") is not None:
        return float(arm["sd"])
    d, dt, n = arm.get("dispersion"), (arm.get("dispersionType") or "").upper(), arm.get("n")
    if d is None:
        return None
    d = float(d)
    if dt == "SD":
        return d
    if dt == "SEM":
        return d * math.sqrt(n) if n else None
    if dt in ("CI95", "CI"):                      # d = half-width of the 95% CI
        return (d / Z95) * math.sqrt(n) if n else None
    return None                                    # unknown -> not resolvable (quarantine)


def box_to_mean_sd(q1: float, median: float, q3: float) -> tuple[float, float]:
    """median + IQR -> mean, SD (Wan 2014 approximation)."""
    return (q1 + median + q3) / 3.0, (q3 - q1) / 1.35


def hedges_g(m1, sd1, n1, m2, sd2, n2) -> dict:
    """Standardized mean difference (small-sample corrected) + variance."""
    sp = math.sqrt(((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp
    J = 1 - 3 / (4 * (n1 + n2) - 9)
    g = J * d
    var = J ** 2 * ((n1 + n2) / (n1 * n2) + d ** 2 / (2 * (n1 + n2 - 2)))
    return {"g": g, "d": d, "variance": var, "se": math.sqrt(var)}


# ---- study-level effect ----
def resolve_arm(arm: dict) -> dict | None:
    """Return {mean, sd, n} for an arm, deriving sd from box landmarks or dispersion type."""
    n = arm.get("n")
    if arm.get("median") is not None and arm.get("q1") is not None and arm.get("q3") is not None:
        mean, sd = box_to_mean_sd(arm["q1"], arm["median"], arm["q3"])
        return {"mean": mean, "sd": sd, "n": n}
    if arm.get("mean") is None or n is None:
        return None
    sd = arm_sd(arm)
    return None if sd is None else {"mean": float(arm["mean"]), "sd": sd, "n": n}


def study_effect(study: dict, measure: str = "SMD") -> dict | None:
    """Compute the effect for a study; None (needs review) if arms aren't resolvable."""
    i, c = resolve_arm(study["arms"]["intervention"]), resolve_arm(study["arms"]["control"])
    if not i or not c:
        return None
    if measure != "SMD":
        raise ValueError("only SMD implemented (approved primary measure)")
    e = hedges_g(i["mean"], i["sd"], i["n"], c["mean"], c["sd"], c["n"])
    return {"measure": "SMD", "value": e["g"], "variance": e["variance"], "se": e["se"],
            "resolved": {"intervention": i, "control": c}}


# ---- corpus -> flat studies table ----
STUDY_COLS = ["articleId", "studyId", "label", "species", "strain", "sex", "ageWeeks",
              "interventionType", "durationWeeks", "assay", "subregion",
              "n_int", "mean_int", "sd_int", "n_ctrl", "mean_ctrl", "sd_ctrl",
              "yi", "vi", "sei", "measure", "source", "extractedBy", "confidence",
              "reviewStatus", "rob_overall", "clusterId", "sharesControlWith"]


def flatten(corpus: dict, include_needs_review: bool = False) -> list[dict]:
    """One row per resolvable study from INCLUDED articles. Rows needing review are excluded from
    the primary table unless include_needs_review=True (a sensitivity option)."""
    rows = []
    for art in corpus.get("articles", []):
        if (art.get("screening", {}).get("status") != "included"):
            continue
        rob = art.get("riskOfBias", {}).get("overall", "")
        for s in art.get("studies", []):
            eff = study_effect(s)
            needs = eff is None or s.get("provenance", {}).get("reviewStatus") == "needs-review"
            if needs and not include_needs_review:
                continue
            mod = s.get("moderators", {}); arms = s["arms"]
            r = {c: "" for c in STUDY_COLS}
            r.update({
                "articleId": art["articleId"], "studyId": s["studyId"], "label": s.get("label", ""),
                "species": mod.get("species", ""), "strain": mod.get("strain", ""), "sex": mod.get("sex", ""),
                "ageWeeks": mod.get("ageWeeks", ""), "interventionType": mod.get("interventionType", ""),
                "durationWeeks": mod.get("durationWeeks", ""), "assay": s.get("outcome", {}).get("assay", ""),
                "subregion": mod.get("subregion", ""),
                "n_int": arms["intervention"].get("n", ""), "n_ctrl": arms["control"].get("n", ""),
                "measure": "SMD", "source": s.get("provenance", {}).get("source", ""),
                "extractedBy": s.get("provenance", {}).get("extractedBy", ""),
                "confidence": s.get("provenance", {}).get("confidence", ""),
                "reviewStatus": s.get("provenance", {}).get("reviewStatus", ""),
                "rob_overall": rob, "clusterId": art["articleId"],
                "sharesControlWith": ";".join(s.get("dependency", {}).get("sharesControlWith", [])),
            })
            if eff:
                ri, rc = eff["resolved"]["intervention"], eff["resolved"]["control"]
                r.update({"mean_int": round(ri["mean"], 4), "sd_int": round(ri["sd"], 4),
                          "mean_ctrl": round(rc["mean"], 4), "sd_ctrl": round(rc["sd"], 4),
                          "yi": round(eff["value"], 4), "vi": round(eff["variance"], 5), "sei": round(eff["se"], 4)})
            rows.append(r)
    return rows


def studies_csv(rows: list[dict]) -> str:
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=STUDY_COLS); w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ---- duplicate-cohort de-duplication (TC8) ----
def dedupe_cohorts(corpus: dict) -> dict:
    """Mark all-but-one article sharing a `cohortKey` as excluded (duplicate cohort)."""
    seen = {}
    for art in corpus.get("articles", []):
        key = art.get("cohortKey")
        if not key:
            continue
        if key in seen:
            art.setdefault("screening", {})
            art["screening"].update({"status": "excluded", "reasonExcluded": "duplicate cohort",
                                     "duplicateOf": seen[key]})
        else:
            seen[key] = art["articleId"]
    return corpus
