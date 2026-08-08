#!/usr/bin/env python3
"""score_real_validation.py -- the REAL-FIGURE validation scorer.

Implements ANALYSIS-PLAN.md. Three tiers, one report:

  D  DETECTION   figure bbox IoU, caption association, false positives.
                 Human is a valid reference (which box, which caption).
  P  PANELS      per-panel IoU, exact count, LABEL ASSIGNMENT + silent mislabels,
                 abstention economics. Metric definitions imported unchanged from
                 benchmark/panels/score.py so the transfer gap Delta is meaningful.
  E  EXTRACTION  classification, dispersion TYPE, series->arm binding, central
                 tendency, and the DISPERSION channel.

The measurement problem this file exists to handle correctly
------------------------------------------------------------
On a real journal figure nobody knows the true SD. Greg's clicks carry ~1px jitter,
which is 0.44% on a bar top and 3.89% median / 27.7% worst on an SEM cap. So a naive
"machine vs human" dispersion number is the DISAGREEMENT OF TWO IMPRECISE READERS,
not machine accuracy.

This scorer therefore never reports a machine dispersion accuracy from human
disagreement. It reports, in this order:
  (a) the naive disagreement, explicitly labelled as not-an-accuracy;
  (b) Bland-Altman bias + limits of agreement on log(M/G) -- the interchangeability
      question a reviewer actually has;
  (c) the intra-rater noise floor from Greg's own repeat annotations, and the ratio
      R_floor = sd(log(SD_M/SD_G)) / sd(log(SD_G1/SD_G2)) -- both sides on the
      difference-SD scale, so R_floor == 1 exactly when sigma_M == sigma_G;
  (d) the GRUBBS three-reading variance decomposition over
      D (dissertation, years ago, different tool) / G (fresh) / M (machine), which
      identifies each reader's error variance with NO gold standard;
  (e) accuracy, restricted to the text-anchored oracle stratum where the paper prints
      the number;
  (f) the CROSS-CHECK: Grubbs sigma_M against the oracle sigma_M.

WHAT (d) IS NOT. Grubbs identifies sigma_M only if e_D, e_G and e_M are mutually
uncorrelated. With correlated errors,

    E[sigma_M^2 (Grubbs)] = sigma_M^2 + c_DG - c_DM - c_GM

D and G are the same person, so c_DG >= 0 pushes the estimate UP. But c_DM and c_GM
push it DOWN and are not zero: machine and human misreading the SAME ambiguous cap
the same way is a named validity threat, and an occluded cap is hard for every reader
of that panel. THE BIAS DIRECTION IS UNKNOWN. Nothing here calls Grubbs conservative,
a bound, or biased against the machine; it is one of three estimates with its
assumption attached. The [corrected, uncorrected] interval brackets c_DG alone.

Only (e) is immune -- its truth is printed in the paper, so no shared reading error
can move it -- which is why (f) exists: Grubbs-vs-oracle disagreement IS the evidence
that the confound is present.

`--selftest D3` proves the layer-(a) distinction: an EXACTLY CORRECT machine still
shows a large naive disagreement against a jittering human, while Grubbs recovers
sigma_M ~ 0. `--selftest D5b` proves the limit of (d): a shared-difficulty component
makes Grubbs return sigma_M 40% BELOW a known truth while the oracle recovers it.

EVERY confidence interval printed is an article-level CLUSTER BOOTSTRAP (B = 10000)
through `cb`/`cb_rate`/`cb_median`. The only exceptions are the rule-of-three
zero-event bound, which has no clustered analogue and is labelled "not
cluster-adjusted" where it prints, and the `_iid` lines, which exist only as the
labelled contrast. See the CI-provenance block at the foot of every report.

Run:
  python3 score_real_validation.py --split                  # print/write the DEV/LOCK split
  python3 score_real_validation.py --power                  # the sample-size table
  python3 score_real_validation.py --run cascade_v4         # score a prediction run
  python3 score_real_validation.py --run cascade_v4 --split-filter lock
  python3 score_real_validation.py --selftest               # injected-error proofs
"""
import argparse
import collections
import csv
import hashlib
import itertools
import json
import math
import os
import pathlib
import random
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent

# DATA HONOURS $RV_DATA, exactly as rvcommon.DATA does. Every other script in this harness
# reads and writes through rvcommon, so `ingest_annotations.py` writes ground truth to
# $RV_DATA/gt. This module used to hardcode HERE/"gt", which meant that whenever RV_DATA
# pointed somewhere else -- every test, every sandbox, any relocated data set -- the scorer
# looked in a directory the ingest had never written to and reported "no ground truth in
# gt/", i.e. it produced NOTHING rather than an error. The suite never caught it because
# test_end_to_end.py calls `normalize_annotations()` on a path it opens itself and never
# exercises `load_gt()`, so the seam between the two scripts was untested.
# With RV_DATA unset both resolve to HERE, so the default in-repo workflow is unchanged.
DATA = pathlib.Path(os.environ.get("RV_DATA") or HERE).resolve()
GT_DIR = DATA / "gt"
REPEAT_DIR = DATA / "repeat"
PRED_DIR = DATA / "pred"
CODED_DIR = DATA / "coded"
OUT_DIR = DATA / "out"
SYNTH_REF = HERE / "synthetic_reference.json"   # a committed comparator, not run data

# shared affine, byte-verified against window.figureExtractor.calibrate
sys.path.insert(0, str(HERE.parent / "harness"))
try:
    from calibrate import py_calibrate
except Exception:                                                # pragma: no cover
    py_calibrate = None

# ---- constants fixed by ANALYSIS-PLAN.md (do not tune) -----------------------
SPLIT_SALT = "figure-extractor-real-validation-v1"
PERMANENT_DEV = {                       # contaminated by the pilot; never LOCK
    "Gobeske2009", "GarciaCapdevila2009", "Bonaccorsi2013", "Kazlauckas2011",
}
IOU_HIT = 0.5                           # panels: localised at or above this
IOU_TIGHT = 0.9                         # panels: tightly localised
IOU_FIGURE = 0.5                        # detection: figure matched at or above this
IOU_FIGURE_TIGHT = 0.75                 # detection: "good enough" figure box
CAPTION_OVERLAP = 0.90                  # caption association: normalised char overlap
MIN_STRATUM_N = 10                      # below this, counts only -- no percentages
FAST_READ_SEC = 60                      # anchoring guard (sec.7)
ROUNDING_QUANTUM_MAX_PCT = 1.0          # coded-value rounding floor (sec.1.5)
BOOTSTRAP_B = 10000
NON_DATA_TYPES = {"schematic", "micrograph", "flow-diagram", "table"}
DERIVED_TYPES = {"forest", "funnel"}
ORIGINAL_DATA_TYPES = {
    "bar", "grouped-bar", "stacked-bar", "histogram", "line", "scatter", "box",
    "violin", "dose-response", "kaplan-meier", "roc", "bland-altman",
}

NA = None                                # "not available" -- never a silent zero


# ============================================================ geometry (mirrors panels/score.py)
def as_box(b):
    if b is None:
        return None
    if isinstance(b, (list, tuple)):
        x, y, w, h = b[:4]
    else:
        x = b.get("x", b.get("left", 0)); y = b.get("y", b.get("top", 0))
        w = b.get("width", b.get("w", 0)); h = b.get("height", b.get("h", 0))
    return (float(x), float(y), float(x) + float(w), float(y) + float(h))


def iou(a, b):
    if a is None or b is None:
        return 0.0
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def match(gt_boxes, pred_boxes):
    """One-to-one GT->prediction assignment maximising total IoU (exact for these
    cardinalities, greedy fallback). Unmatched GT scores IoU 0 so misses cannot hide."""
    ng, npd = len(gt_boxes), len(pred_boxes)
    if not ng or not npd:
        return {}
    M = [[iou(g, p) for p in pred_boxes] for g in gt_boxes]
    if math.perm(max(ng, npd), min(ng, npd)) <= 200000:
        best, bestsc = {}, -1.0
        if npd >= ng:
            for perm in itertools.permutations(range(npd), ng):
                sc = sum(M[g][p] for g, p in enumerate(perm))
                if sc > bestsc:
                    bestsc, best = sc, {g: p for g, p in enumerate(perm)}
        else:
            for perm in itertools.permutations(range(ng), npd):
                sc = sum(M[g][p] for g, p in zip(perm, range(npd)))
                if sc > bestsc:
                    bestsc, best = sc, {g: p for p, g in enumerate(perm)}
        return {g: p for g, p in best.items() if M[g][p] > 0}
    used, out = set(), {}
    for g, p in sorted(((g, p) for g in range(ng) for p in range(npd)),
                       key=lambda gp: -M[gp[0]][gp[1]]):
        if g in out or p in used or M[g][p] <= 0:
            continue
        out[g] = p
        used.add(p)
    return out


def reading_order(boxes):
    idx = list(range(len(boxes)))
    if len(idx) < 2:
        return idx
    hs = sorted(b[3] - b[1] for b in boxes)
    tol = hs[len(hs) // 2] * 0.5
    rows = []
    for i in sorted(idx, key=lambda k: (boxes[k][1] + boxes[k][3]) / 2):
        cy = (boxes[i][1] + boxes[i][3]) / 2
        row = next((r for r in rows if abs(r["cy"] - cy) <= tol), None)
        if row is None:
            row = {"cy": cy, "items": []}
            rows.append(row)
        row["items"].append(i)
        row["cy"] = sum((boxes[k][1] + boxes[k][3]) / 2 for k in row["items"]) / len(row["items"])
    rows.sort(key=lambda r: r["cy"])
    out = []
    for r in rows:
        out.extend(sorted(r["items"], key=lambda k: boxes[k][0]))
    return out


def norm_label(s):
    return "" if s is None else re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


def norm_text(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


CAP_LETTER = re.compile(r"\(\s*([A-Za-z])\s*\)")


def caption_letters(text):
    """Letter set a caption declares, e.g. '(A) ... (B) ...' -> ['A','B']."""
    seen, out = set(), []
    for m in CAP_LETTER.finditer(text or ""):
        u = m.group(1).upper()
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ============================================================ statistics
def wilson(k, n, z=1.959964):
    if not n:
        return (NA, NA)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rule_of_three(n):
    """95% upper bound on a rate given 0 events in n trials."""
    return 3.0 / n if n else NA


def med(v):
    return statistics.median(v) if v else NA


def pctl(v, q):
    if not v:
        return NA
    s = sorted(v)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def median_ci(v):
    """Distribution-free 95% CI for a median via order statistics."""
    n = len(v)
    if n < 6:
        return (NA, NA)
    s = sorted(v)
    k = int(math.floor(n / 2 - 1.959964 * math.sqrt(n) / 2))
    k = max(0, k)
    return (s[k], s[min(n - 1, n - 1 - k)])


def cluster_bootstrap(items, cluster_key, stat, B=None, seed=17):
    """95% CI for `stat(list_of_items)` resampling CLUSTERS (articles) with replacement.
    Nesting is real -- panels of one article share layout, journal and typeface -- so a
    naive i.i.d. interval would be too narrow.

    ANALYSIS-PLAN sec.2.1 pre-registers this as the interval for EVERY reported CI, with
    B = 10000. `cb_*` below are the only CI helpers the report is allowed to call; a
    quantity that genuinely cannot be clustered (the rule-of-three zero-event bound is
    the only one) must be printed with the words "not cluster-adjusted" beside it."""
    if B is None:
        B = BOOTSTRAP_B
    if not items:
        return (NA, NA)
    by = collections.defaultdict(list)
    for it in items:
        by[cluster_key(it)].append(it)
    keys = list(by)
    if len(keys) < 2:
        return (NA, NA)
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        samp = []
        for _ in range(len(keys)):
            samp.extend(by[keys[rng.randrange(len(keys))]])
        try:
            v = stat(samp)
        except Exception:
            v = None
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if len(vals) < 20:
        return (NA, NA)
    vals.sort()
    return (vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))])


def _cluster_of(row):
    """The bootstrap cluster: the ARTICLE, canonicalised so two spellings are one cluster.
    Accepts a row dict, or a (row, value) pair as the log-ratio sites produce."""
    if isinstance(row, tuple):
        row = row[0]
    return canonical_article(row.get("article") or row.get("figure") or "unknown")


def cb(rows, stat, B=None):
    """Article-level cluster-bootstrap 95% CI for `stat(rows)`. The ONE entry point."""
    return cluster_bootstrap(rows, _cluster_of, stat, B=B)


def cb_rate(rows, pred):
    """CI for a proportion over clustered rows."""
    return cb(rows, lambda g: (sum(1 for r in g if pred(r)) / len(g)) if g else None)


def cb_median(rows, val):
    """CI for a median over clustered rows (replaces the order-statistic interval, which
    assumes i.i.d. observations and is ~19-25% too narrow on this nesting)."""
    def stat(g):
        v = [val(r) for r in g]
        v = [x for x in v if x is not NA and x is not None]
        return statistics.median(v) if v else None
    return cb(rows, stat)


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return NA

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else NA


def bland_altman(log_ratios):
    """Bias + 95% limits of agreement on log-ratios, reported back-transformed to %.
    This is an AGREEMENT statistic. It says whether two readings are interchangeable;
    it says nothing about which one is right."""
    n = len(log_ratios)
    if n < 3:
        return None
    bias = statistics.fmean(log_ratios)
    sd = statistics.stdev(log_ratios)
    lo, hi = bias - 1.959964 * sd, bias + 1.959964 * sd
    se_loa = sd * math.sqrt(1 / n + 1.959964 ** 2 / (2 * (n - 1)))
    return {
        "n": n,
        "biasPct": 100 * (math.exp(bias) - 1),
        "sdLog": sd,
        "loaLoPct": 100 * (math.exp(lo) - 1),
        "loaHiPct": 100 * (math.exp(hi) - 1),
        "loaSeLogFrac": se_loa / sd if sd else NA,
        "loaHalfWidthPctOnLog": 100 * 1.959964 * se_loa,
    }


def _grubbs_ratio_stat(rows):
    """sigma_M / sigma_G from a bootstrap resample of (row, (logD, logG, logM)) pairs."""
    if len(rows) < 5:
        return None
    a = [t[0] for _, t in rows]
    b = [t[1] for _, t in rows]
    c = [t[2] for _, t in rows]
    gr = grubbs_three(a, b, c)
    if not gr or gr["var_b"] <= 0 or gr["var_c"] <= 0:
        return None
    return math.sqrt(gr["var_c"]) / math.sqrt(gr["var_b"])


def _loa(pairs, sign):
    """One Bland-Altman limit of agreement, back-transformed to %, from (row, log) pairs."""
    v = [x for _, x in pairs]
    if len(v) < 3:
        return None
    return 100 * (math.exp(statistics.fmean(v) + sign * 1.959964 * statistics.stdev(v)) - 1)


def shapiro_like(v):
    """A cheap, dependency-free normality screen: the correlation between the ordered
    sample and the normal quantiles it would have under normality (the Filliben /
    probability-plot correlation coefficient). 1.0 is perfectly normal; the 5%
    critical value is about 0.96-0.99 over n = 20-200.

    It exists because the Bland-Altman LoA is a +/-1.96 sd interval and is only a 95%
    interval if the log-ratios are approximately normal. Reporting a LoA without ever
    checking that is reporting an interval with an unverified coverage."""
    n = len(v)
    if n < 8:
        return NA
    s = sorted(v)
    m = statistics.fmean(s)
    # Blom plotting positions -> normal quantiles via an inverse-erf approximation
    q = [_probit((i + 1 - 0.375) / (n + 0.25)) for i in range(n)]
    mq = statistics.fmean(q)
    num = sum((a - m) * (b - mq) for a, b in zip(s, q))
    den = math.sqrt(sum((a - m) ** 2 for a in s) * sum((b - mq) ** 2 for b in q))
    return (num / den) if den else NA


def _probit(p):
    """Acklam's inverse normal CDF, |error| < 1.15e-9. No scipy."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _ba_by_stratum(pairs):
    """Bland-Altman LoA per CAP-LENGTH TERTILE, plus the normality screen per stratum.

    The log transform is the right scale for a MULTIPLICATIVE error. The dominant error
    here is not multiplicative: it is a fixed ~1 px of hand jitter on a cap whose length
    varies ~10x across the corpus, so the relative error is pixel-additive/cap-length and
    the log-ratio variance still scales with 1/capLen. Logging therefore does NOT
    stabilise the variance, and a pooled LoA is a mixture of a wide short-cap
    distribution and a narrow long-cap one -- an interval that describes no stratum.
    Report by stratum. The pooled figure remains only as a diagnostic."""
    withcap = [(r, v) for r, v in pairs if r.get("capLenPx")]
    out = {}
    norm = {"pooled": shapiro_like([v for _, v in pairs])}
    if len(withcap) >= 6:
        caps = sorted(r["capLenPx"] for r, _ in withcap)
        t1, t2 = caps[len(caps) // 3], caps[2 * len(caps) // 3]
        buckets = collections.defaultdict(list)
        for r, v in withcap:
            b = ("short" if r["capLenPx"] <= t1
                 else "mid" if r["capLenPx"] <= t2 else "long")
            buckets[b].append((r, v))
        for k, g in buckets.items():
            ba = bland_altman([v for _, v in g])
            if ba:
                ba["capLenMedianPx"] = med([r["capLenPx"] for r, _ in g])
                ba["biasCI"] = cb(g, lambda gg: 100 * (
                    math.exp(statistics.fmean([v for _, v in gg])) - 1))
                ba["normalityR"] = shapiro_like([v for _, v in g])
                out[k] = ba
            norm[k] = shapiro_like([v for _, v in g])
        out["_cuts"] = [t1, t2]
    return out, norm


def grubbs_three(a, b, c):
    """Grubbs (1948) three-instrument estimator: with three methods measuring the same
    unknown truth with independent errors, each method's error variance is identified
    from the pairwise difference variances alone.

        sigma_a^2 = [Var(a-b) + Var(a-c) - Var(b-c)] / 2   (equivalently Cov(a-b, a-c))

    No gold standard required. Returns per-method variances (which CAN come out
    negative at small n -- reported, never silently clipped, because a negative
    estimate is evidence the independence assumption or n is inadequate)."""
    n = len(a)
    if not (n == len(b) == len(c)) or n < 5:
        return None
    dab = [x - y for x, y in zip(a, b)]
    dac = [x - y for x, y in zip(a, c)]
    dbc = [x - y for x, y in zip(b, c)]
    vab, vac, vbc = (statistics.variance(d) for d in (dab, dac, dbc))
    return {
        "n": n,
        "var_a": (vab + vac - vbc) / 2,
        "var_b": (vab + vbc - vac) / 2,
        "var_c": (vac + vbc - vab) / 2,
        "var_diff_ab": vab, "var_diff_ac": vac, "var_diff_bc": vbc,
    }


def sd_ratio_ci(n, ratio):
    """95% CI multiplier for a variance ratio with df = n-1 each, on the SD scale.
    Uses a Wilson-Hilferty approximation to F so no scipy is needed."""
    if not ratio or n < 4 or ratio <= 0:
        return (NA, NA)
    d = n - 1
    # Wilson-Hilferty: F_{0.975,d,d} approx
    z = 1.959964
    a = 2 / (9 * d)
    f = ((1 - a + z * math.sqrt(a)) / (1 - a - z * math.sqrt(a))) ** 3
    return (ratio / math.sqrt(f), ratio * math.sqrt(f))


def n_two_prop(p1, p2, n1):
    """Real-side n for 80% power to detect p1 (synthetic, n1) vs p2 at alpha=.05."""
    za, zb = 1.959964, 0.8416212
    for n2 in range(5, 6001):
        pbar = (p1 * n1 + p2 * n2) / (n1 + n2)
        se0 = math.sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n2))
        se1 = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        if abs(p1 - p2) >= za * se0 + zb * se1:
            return n2
    return NA


def detectable_drop(p1, n1, n2):
    za, zb = 1.959964, 0.8416212
    for i in range(1, 900):
        d = i / 1000
        p2 = p1 - d
        if p2 <= 0:
            return NA
        pbar = (p1 * n1 + p2 * n2) / (n1 + n2)
        se0 = math.sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n2))
        se1 = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        if d >= za * se0 + zb * se1:
            return d
    return NA


def rounding_quantum_pct(text_value):
    """Half the last printed decimal place, as a % of the value. A coded '1.3' carries
    a +/-0.05 quantum = 3.8% -- which is larger than the effect this study measures, so
    such rows leave the primary dispersion analysis (ANALYSIS-PLAN sec.1.5)."""
    s = str(text_value).strip()
    try:
        v = float(s)
    except (TypeError, ValueError):
        return NA
    if v == 0:
        return NA
    dp = len(s.split(".")[1]) if "." in s else 0
    return 100 * (0.5 * 10 ** (-dp)) / abs(v)


def extraction_priority(char_type, provenance):
    """Ported from figure-extractor.html extractionPriority(). A change in this value
    is a change in what the pipeline DOES with the panel, so it is scored separately
    from raw classification accuracy."""
    if char_type in NON_DATA_TYPES:
        return "none"
    if char_type in DERIVED_TYPES:
        return "medium" if provenance == "primary" else "low"
    if provenance == "derived":
        return "low"
    if char_type in ORIGINAL_DATA_TYPES:
        return "high"
    return "medium"


def hedges_g(m1, sd1, n1, m2, sd2, n2):
    """Bias-corrected SMD, intervention(2) - control(1). Same formula metafor's
    escalc(measure='SMD') uses, so the python and R stages agree."""
    df = n1 + n2 - 2
    if df <= 0:
        return (NA, NA)
    sp2 = ((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / df
    if sp2 <= 0:
        return (NA, NA)
    d = (m2 - m1) / math.sqrt(sp2)
    J = 1 - 3 / (4 * df - 1)
    g = J * d
    vi = (n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2))
    return (g, vi)


# ============================================================ DEV / LOCK split
def canonical_article(article):
    """THE article key. One helper, used by PERMANENT_DEV, the split, and every join.

    The corpus spells the same article both ways -- `Garcia-Capdevila2009` in the coded
    reference and `GarciaCapdevila2009` in the worklist, `Sampedro-Piquero2018` and
    `SampedroPiquero2018`, `Del-Arco2007` and `DelArco2007`. Exact string membership
    therefore silently failed in three places at once:

      * PERMANENT_DEV listed `GarciaCapdevila2009` while the data carried
        `Garcia-Capdevila2009`, so a PILOT-CONTAMINATED article -- one that produced the
        asterisk-occlusion finding and that BOTH raters see as a calibration figure --
        was assigned to LOCK;
      * three worklist articles had no split assignment at all;
      * the two spellings hash to different buckets, so one article could be DEV in one
        file and LOCK in another.

    Canonicalise once, here, and the failure cannot recur. Hyphens, spaces, underscores,
    periods and case are all stripped: they are typography, not identity.
    """
    return re.sub(r"[^a-z0-9]+", "", (article or "").lower())


PERMANENT_DEV_CANON = {canonical_article(a) for a in PERMANENT_DEV}


def canonical_figure_id(fid):
    """Figure ids embed the article name (`Garcia-Capdevila2009_fig1`), so a join on the
    raw id inherits the spelling problem. Canonicalise the whole id the same way."""
    return canonical_article(fid)


def split_of(article):
    """Deterministic, recomputable, published-salt article-level split. Fixed by
    ANALYSIS-PLAN sec.2.3 before any figure was seen; it cannot be redrawn to suit a
    result. Split at ARTICLE level -- panels of one figure share everything.

    The hash is taken over the CANONICAL key, so the two spellings of an article always
    land in the same bucket (amendment A8)."""
    key = canonical_article(article)
    if key in PERMANENT_DEV_CANON:
        return "dev"
    h = hashlib.sha256(f"{SPLIT_SALT}|{key}".encode()).hexdigest()
    return "dev" if int(h[:8], 16) % 3 == 0 else "lock"


# ============================================================ IO / normalisation
def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_gt(directory=GT_DIR):
    """Normalized GT store. Falls back to the tool's own annotations.json if the
    normalized store is absent -- the analysis must never be blocked on the harness."""
    out = {}
    if not directory.exists():
        return out
    for p in sorted(directory.glob("*.gt.json")):
        try:
            rec = json.loads(p.read_text())
        except Exception as e:
            print(f"  [warn] unreadable GT {p.name}: {e}", file=sys.stderr)
            continue
        rec.setdefault("id", p.name[:-len(".gt.json")])
        out[rec["id"]] = rec
    # JSONL stores (the annotation-harness ingest writes gt/human_gt.jsonl and
    # gt/<session>/panels_gt.jsonl). Accepted as-is: the contract in ANALYSIS-PLAN
    # sec.10 promises the analysis is never blocked on the harness's file layout.
    for jl in sorted(directory.rglob("*.jsonl")):
        for line in jl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            rec = _coerce_gt(rec)
            if rec and rec.get("id"):
                out.setdefault(rec["id"], rec)
    for ann in sorted(directory.rglob("annotations.json")):
        try:
            for rec in normalize_annotations(json.loads(ann.read_text())):
                out.setdefault(rec["id"], rec)
        except Exception as e:
            print(f"  [warn] unreadable annotations.json {ann}: {e}", file=sys.stderr)
    return out


def _trailing_letter(label):
    """'Figure 5 A' / 'Panel (B)' / 'C' -> 'A' / 'B' / 'C'; otherwise the string as given."""
    if not label:
        return label
    m = re.search(r"\(?\s*([A-Za-z])\s*\)?\s*$", str(label).strip())
    return m.group(1).upper() if m else str(label)


def _coerce_gt(rec):
    """Accept a GT record in either the normalized schema or the harness's flatter
    per-figure shape, without demanding that the harness change. Anything that cannot be
    mapped is simply absent, which downgrades that metric to 'not available' -- never a
    silent zero."""
    if not isinstance(rec, dict):
        return None
    if "panels" not in rec and "figures" not in rec:
        return None
    if rec.get("schemaVersion") and "detection" in rec:
        return rec                                   # already normalized
    fid = (rec.get("id") or rec.get("figureId")
           or (f"{rec.get('task') or rec.get('article')}_fig{rec.get('figureIndex')}"
               if rec.get("figureIndex") is not None else None))
    if not fid:
        return None
    fb = rec.get("figureBbox") or rec.get("bbox")
    pans = []
    for i, p in enumerate(rec.get("panels") or []):
        pans.append({
            "index": i,
            # prefer an explicit `letter`: the harness's `label` is the display string
            # ("Figure 5 A"), and comparing that to a detector's "A" would score every
            # correct letter as a silent mislabel -- i.e. a scoring artefact that looks
            # exactly like the catastrophic class it is supposed to detect
            "label": p.get("letter") or _trailing_letter(p.get("label")),
            "bbox": p.get("bbox"), "bboxCore": p.get("bboxCore"),
            "contentType": p.get("contentType") or p.get("charType"),
            "chartType": p.get("chartType") or p.get("charType"),
            "dispersionType": p.get("dispersionType"),
            "dispersionFlags": p.get("dispersionFlags") or p.get("flags") or [],
            "calibration": p.get("calibration"),
            "series": p.get("series") or [], "groups": p.get("groups") or [],
            "landmarks": p.get("landmarks") or [],
            "sigMarkersOverCaps": p.get("sigMarkersOverCaps"),
            "cueType": p.get("cueType"), "occlusion": p.get("occlusion"),
            "legendStyle": p.get("legendStyle"),
        })
    cap = rec.get("caption") or ""
    return {
        "schemaVersion": 1, "id": fid,
        "article": rec.get("article") or rec.get("task") or "unknown",
        "pdf": {"page": rec.get("pageNum"), "dpi": rec.get("dpi")},
        "durationSec": rec.get("durationSec"), "session": rec.get("session"),
        "positionInSession": rec.get("positionInSession"),
        "sawPrediction": rec.get("sawPrediction"), "excluded": rec.get("excluded"),
        "detection": {"figureBbox": fb, "captionText": cap,
                      "captionBbox": rec.get("captionBounds")},
        "caption": cap,
        "expectedLetters": rec.get("expectedLetters") or caption_letters(cap),
        "nPanels": rec.get("nPanels", len(pans)),
        "layoutClass": rec.get("layoutClass"),
        "labelPlacement": rec.get("labelPlacement"),
        "gutter": rec.get("gutter") or {}, "origin": rec.get("origin"),
        "panels": pans, "_source": "jsonl",
    }


def normalize_annotations(data):
    """figure-extractor annotations.json (schemaVersion 2) -> normalized GT records.
    figures[] -> figure; subfigures[] -> panels; characterization -> chart/dispersion
    type; digitization/extraction -> landmarks. Best effort and defensive: anything it
    cannot map is simply absent, which downgrades that metric to 'not available'."""
    out = []
    article = data.get("article") or data.get("project") or "unknown"
    for fi, f in enumerate(data.get("figures", []) or []):
        fb = f.get("bounds") or {}
        panels = []
        for i, s in enumerate(f.get("subfigures", []) or []):
            char = (s.get("characterization") or {})
            pan0 = (char.get("panels") or [{}])[0]
            stats = pan0.get("statistics") or {}
            disp = stats.get("dispersion") or {}
            panels.append({
                "index": i,
                "label": (s.get("label") or "").strip().split()[-1] if s.get("label") else "",
                "bbox": s.get("bounds"),
                "contentType": pan0.get("charType"),
                "chartType": pan0.get("charType"),
                "dispersionType": disp.get("type"),
                "dispersionFlags": char.get("flags") or [],
                "series": pan0.get("series") or [],
                "groups": pan0.get("groups") or [],
                "calibration": _cal_from_digitization(s.get("digitization")),
                "landmarks": _landmarks_from_extraction(s.get("extraction")),
            })
        out.append({
            "schemaVersion": 1,
            # Key the SAME way `_coerce_gt` keys panels_gt.jsonl -- `<task>_fig<index>` -- so
            # the two views of one figure collide and `load_gt`'s setdefault keeps the first.
            # They used to disagree (`f["id"]` is the tool's internal "fig1"), so a session
            # ingested from panels_gt.jsonl ALSO gained a phantom record from the sealed
            # annotations.json: a different id, figure-LOCAL coordinates rather than page
            # coordinates, and the anon id standing in for the article. It diluted Tier D
            # recall and could never join a prediction. Panel GT is loaded first and wins,
            # which is right: it is the one in page coordinates.
            "id": f"{article}_fig{fi}",
            "article": article,
            "pdf": {"page": f.get("pageNum")},
            "detection": {
                "figureBbox": fb,
                "captionText": f.get("caption"),
                "captionBbox": f.get("captionBounds"),
            },
            "caption": f.get("caption"),
            "expectedLetters": caption_letters(f.get("caption")),
            "nPanels": len(panels),
            "panels": panels,
            "_source": "annotations.json",
        })
    return out


def _cal_from_digitization(dig):
    if not dig or not dig.get("cal") or not dig.get("vals"):
        return None
    return {"calPixels": dig["cal"], "calVals": dig["vals"]}


def _landmarks_from_extraction(ext):
    """extraction.groups[] (bar-endpoints / box-landmarks) -> landmark records."""
    if not ext:
        return []
    out = []
    for g in ext.get("groups", []) or []:
        gid = g.get("groupId") or g.get("name") or ""
        sid = g.get("seriesId") or ""
        rec = {
            "landmarkId": f"{gid}|{sid}" if sid else str(gid),
            "groupId": gid, "seriesId": sid,
            "n": g.get("n"),
            "flags": ext.get("flags") or [],
        }
        if g.get("mean") is not None:
            rec.update({"kind": "bar", "central": _num(g.get("mean")),
                        "dispersion": _num(g.get("errorHalf"))})
        elif g.get("median") is not None:
            rec.update({"kind": "box", "central": _num(g.get("median")),
                        "dispersion": (_num(g.get("q3"), 0) - _num(g.get("q1"), 0))
                        if g.get("q3") is not None and g.get("q1") is not None else None})
        out.append(rec)
    return out


def load_preds(run):
    """pred/<run>/<id>.json (one file per figure) or pred/<run>.jsonl (one obj/line)."""
    out = {}
    d = PRED_DIR / run
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                rec = json.loads(p.read_text())
            except Exception as e:
                print(f"  [warn] unreadable prediction {p.name}: {e}", file=sys.stderr)
                continue
            rec.setdefault("id", p.stem)
            out[rec["id"]] = rec
    jl = PRED_DIR / f"{run}.jsonl"
    if jl.exists():
        for line in jl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            key = rec.get("id") or rec.get("task")
            if key:
                out.setdefault(key, rec)
    return out


def load_coded():
    p = CODED_DIR / "coded_reference.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        print(f"  [warn] unreadable coded reference: {e}", file=sys.stderr)
        return []
    return data.get("rows", data if isinstance(data, list) else [])


def load_synth():
    try:
        return json.loads(SYNTH_REF.read_text())
    except Exception:
        return {}


# ============================================================ value recovery
def recover(panel, px):
    """Pixel -> data units through the SHARED affine, so GT and predictions pass through
    identical arithmetic and any difference is perception, not maths."""
    cal = panel.get("calibration")
    if not cal or py_calibrate is None or not px:
        return NA
    try:
        r = py_calibrate(cal["calPixels"], cal["calVals"], [px])
    except Exception:
        return NA
    return r[0]["y"] if r else NA


def landmark_values(panel, lm):
    """(central, dispersion, capLenPx). Values come from pixels when pixels exist --
    supplied values are only a fallback, and a >0.5% mismatch between the two is
    reported as an INGEST DEFECT rather than silently resolved."""
    central, disp, caplen, defect = lm.get("central"), lm.get("dispersion"), lm.get("capLenPx"), None
    if lm.get("centralPx") and lm.get("dispersionPx") and panel.get("calibration"):
        c = recover(panel, lm["centralPx"])
        d = recover(panel, lm["dispersionPx"])
        if c is not NA and d is not NA:
            c_px, d_px = c, abs(d - c)
            caplen = abs(lm["dispersionPx"]["py"] - lm["centralPx"]["py"])
            for name, sup, got in (("central", central, c_px), ("dispersion", disp, d_px)):
                if sup is not None and got and abs(sup) > 0 and \
                        100 * abs(got - sup) / abs(sup) > 0.5:
                    defect = f"{name} pixels vs supplied value differ by " \
                             f"{100*abs(got-sup)/abs(sup):.2f}%"
            central, disp = c_px, d_px
    return central, disp, caplen, defect


def as_sd(value, disp_type, n):
    """Shown dispersion -> SD. SEM->SD is a sqrt(n) multiplication: at the corpus median
    n of 10 that is 3.2x, which dwarfs every pixel effect in this study. This is why
    dispersion TYPE gets its own metric and its own gate."""
    if value is None or value is NA:
        return NA
    t = (disp_type or "").upper()
    if t in ("SEM", "SE"):
        return value * math.sqrt(n) if n else NA
    if t in ("CI95", "CI"):
        return (value / 1.96) * math.sqrt(n) if n else NA
    if t in ("SD",):
        return value
    return value                       # IQR/range/unknown: pass through, flagged elsewhere


# ============================================================ TIER D -- detection
def score_detection(gt, pred):
    d_gt = (gt or {}).get("detection") or {}
    d_pr = (pred or {}).get("detection") or {}
    gbox, pbox = as_box(d_gt.get("figureBbox")), as_box(d_pr.get("figureBbox"))
    if gbox is None:
        return None
    v = iou(gbox, pbox)
    gcap, pcap = norm_text(d_gt.get("captionText")), norm_text(d_pr.get("captionText"))
    if gcap and pcap:
        n = len(gcap)
        overlap = sum(1 for a, b in zip(gcap, pcap) if a == b) / n if n else 0.0
        cap_ok = overlap >= CAPTION_OVERLAP or gcap in pcap or pcap in gcap
    else:
        cap_ok = NA
    g_letters = [x.upper() for x in (gt.get("expectedLetters") or [])]
    p_letters = caption_letters(d_pr.get("captionText"))
    letters_ok = (g_letters == p_letters) if gcap else NA
    return {
        "id": gt["id"], "article": gt["article"], "split": gt["_split"],
        "iou": v, "matched": v >= IOU_FIGURE, "tight": v >= IOU_FIGURE_TIGHT,
        "captionCorrect": cap_ok, "lettersCorrect": letters_ok,
        "noPrediction": pred is None,
        "spurious": len((pred or {}).get("extraFigureBoxes") or []),
        "pageKey": f"{gt['article']}:{(gt.get('pdf') or {}).get('page')}",
    }


# ============================================================ TIER P -- panels
def score_panels(gt, pred, abstain_at):
    gpan = gt.get("panels") or []
    if not gpan:
        return None
    gboxes = [as_box(p.get("bbox")) for p in gpan]
    gcore = [as_box(p.get("bboxCore") or p.get("bbox")) for p in gpan]
    ppan = (pred or {}).get("panels") or []
    pboxes = [as_box(p.get("bbox")) for p in ppan]
    m = match(gboxes, pboxes)

    panels = []
    for i, gp in enumerate(gpan):
        j = m.get(i)
        v = iou(gboxes[i], pboxes[j]) if j is not None else 0.0
        vlen = max(v, iou(gcore[i], pboxes[j])) if j is not None else 0.0
        plabel = ppan[j].get("label") if j is not None else None
        if j is not None and not plabel:
            # a detector returning boxes with no letters is read as claiming reading
            # order -- which is exactly what the tool's a/b/c labelling means
            ro = reading_order(pboxes)
            plabel = chr(ord("A") + ro.index(j)) if j in ro else None
        lab_ok = (j is not None and v >= IOU_HIT
                  and norm_label(plabel) == norm_label(gp.get("label")))
        panels.append({
            "figure": gt["id"], "article": gt["article"], "split": gt["_split"],
            "label": gp.get("label"), "contentType": gp.get("contentType"),
            "chartType": gp.get("chartType"),
            "gutterBucket": gt["_gutter"], "layoutClass": gt.get("layoutClass"),
            "labelPlacement": gt.get("labelPlacement"), "origin": gt.get("origin"),
            "iou": v, "iouLenient": vlen, "matched": j is not None,
            "hit": v >= IOU_HIT, "tight": v >= IOU_TIGHT,
            "predLabel": plabel, "labelCorrect": lab_ok,
            # THE catastrophic class: right box, wrong letter. Every downstream number
            # is then attributed to the wrong sub-experiment, and no geometric metric
            # can see it. Zero-tolerance threshold, own gate, own selftest (P3).
            "silentMislabel": (v >= IOU_HIT and not lab_ok),
        })

    n_gt, n_pred = len(gpan), len(ppan)
    matched_pred = set(m.values())
    fp = sum(1 for j in range(n_pred)
             if j not in matched_pred
             or iou(gboxes[[g for g, p in m.items() if p == j][0]], pboxes[j]) < IOU_HIT)
    letters = [x.upper() for x in (gt.get("expectedLetters") or [])]
    conf = (pred or {}).get("confidence")
    abstained = bool((pred or {}).get("abstain")) or (conf is not None and conf < abstain_at)
    wrong = (n_pred != n_gt or any(not p["hit"] for p in panels)
             or any(p["silentMislabel"] for p in panels))
    return {
        "id": gt["id"], "article": gt["article"], "split": gt["_split"],
        "gutterBucket": gt["_gutter"], "layoutClass": gt.get("layoutClass"),
        "labelPlacement": gt.get("labelPlacement"), "origin": gt.get("origin"),
        "nGt": n_gt, "nPred": n_pred, "countExact": n_pred == n_gt,
        "overSplit": n_pred > n_gt, "underSplit": n_pred < n_gt,
        "captionLetters": len(letters),
        "captionHonoured": (None if not letters else n_pred == len(letters)),
        "falsePositives": fp, "panels": panels,
        "confidence": conf, "abstained": abstained, "wrong": wrong,
        "noPrediction": pred is None,
    }


def agg_panels(figs):
    pans = [p for f in figs for p in f["panels"]]
    if not figs:
        return {}
    ious = [p["iou"] for p in pans]
    loc = [p for p in pans if p["hit"]]
    ansd = [f for f in figs if not f["abstained"]]
    return {
        "figures": len(figs), "panels": len(pans), "answered": len(ansd),
        "iouMedian": med(ious) or 0.0,
        "iouMean": (sum(ious) / len(ious)) if ious else 0.0,
        "iouWorst": min(ious) if ious else 0.0,
        "pct90": (sum(p["tight"] for p in pans) / len(pans)) if pans else NA,
        "pct50": (sum(p["hit"] for p in pans) / len(pans)) if pans else NA,
        "countAcc": sum(f["countExact"] for f in figs) / len(figs),
        "overSplit": sum(f["overSplit"] for f in figs) / len(figs),
        "underSplit": sum(f["underSplit"] for f in figs) / len(figs),
        "missed": sum(1 for p in pans if not p["matched"]),
        "falsePositives": sum(f["falsePositives"] for f in figs),
        "labelAccLocalised": (sum(p["labelCorrect"] for p in loc) / len(loc)) if loc else NA,
        "silentMislabel": (sum(p["silentMislabel"] for p in pans) / len(pans)) if pans else NA,
        "silentMislabelCount": sum(p["silentMislabel"] for p in pans),
        "figExact": sum(1 for f in figs if not f["wrong"]) / len(figs),
        "figExactAnswered": (sum(1 for f in ansd if not f["wrong"]) / len(ansd)) if ansd else NA,
    }


def abstention(figs):
    """Abstention only earns its keep if it fires on the figures that are actually
    wrong. Abstaining on a figure you would have got right is a COST, and the trade is
    reported as a net figure count -- the synthetic round-2 cascade was 0% error and
    net -1, i.e. correct and useless."""
    a_w = sum(1 for f in figs if f["abstained"] and f["wrong"])
    a_r = sum(1 for f in figs if f["abstained"] and not f["wrong"])
    n_w = sum(1 for f in figs if not f["abstained"] and f["wrong"])
    n_r = sum(1 for f in figs if not f["abstained"] and not f["wrong"])
    ans = a_r + a_w + n_r + n_w
    return {
        "coverage": (n_r + n_w) / ans if ans else NA,
        "abstained": a_r + a_w,
        "errorRateAll": (a_w + n_w) / ans if ans else NA,
        "errorRateAnswered": n_w / (n_r + n_w) if (n_r + n_w) else NA,
        "precision": a_w / (a_w + a_r) if (a_w + a_r) else NA,
        "recall": a_w / (a_w + n_w) if (a_w + n_w) else NA,
        "missedErrors": n_w,            # answered-and-wrong: the class the A18 gate counts
        "net": a_w - a_r,
    }


# ============================================================ TIER E -- extraction
def score_extraction(gt, pred, coded_by_panel):
    """Per-panel classification + dispersion type, per-landmark central/dispersion,
    per-comparison arm binding. Returns (panel_rows, landmark_rows, comparison_rows)."""
    prows, lrows, crows = [], [], []
    ppan = {norm_label(p.get("label")): p for p in ((pred or {}).get("panels") or [])}
    for gp in gt.get("panels") or []:
        key = norm_label(gp.get("label"))
        pp = ppan.get(key) or {}
        gtype, ptype = gp.get("chartType"), pp.get("chartType")
        gprov = gp.get("dataProvenance") or "primary"
        pprov = pp.get("dataProvenance") or "primary"
        gdisp, pdisp = gp.get("dispersionType"), pp.get("dispersionType")
        pflags = set(pp.get("dispersionFlags") or pp.get("flags") or [])
        prows.append({
            "figure": gt["id"], "article": gt["article"], "split": gt["_split"],
            "panel": gp.get("label"),
            "chartTypeGt": gtype, "chartTypePred": ptype,
            "chartTypeCorrect": (norm_label(gtype) == norm_label(ptype)) if ptype else False,
            "priorityGt": extraction_priority(gtype, gprov),
            "priorityPred": extraction_priority(ptype, pprov),
            "dispTypeGt": gdisp, "dispTypePred": pdisp,
            "dispTypeCorrect": (norm_label(gdisp) == norm_label(pdisp)) if pdisp else False,
            "dispTypeFlagged": "dispersion-type-uncertain" in pflags,
            "confidence": pp.get("conf", pp.get("confidence")),
            "hasPrediction": bool(pp),
            "sigMarkersOverCaps": gp.get("sigMarkersOverCaps"),
            "cueType": gp.get("cueType"), "occlusion": gp.get("occlusion"),
            "legendStyle": gp.get("legendStyle"),
        })

        lmmap = match_landmarks(gp.get("landmarks") or [], pp.get("landmarks") or [])
        for li, lm in enumerate(gp.get("landmarks") or []):
            lid = str(lm.get("landmarkId"))
            g_c, g_d, caplen, defect = landmark_values(gp, lm)
            pl = lmmap.get(li)
            p_c = p_d = NA
            if pl is not None:
                p_c, p_d, _, _ = landmark_values(pp if pp.get("calibration") else gp, pl)
            n = lm.get("n")
            # arm binding: is the predicted landmark bound to the SAME (group, series)?
            arm_gt = f"{lm.get('groupId')}|{lm.get('seriesId')}"
            arm_pred = f"{(pl or {}).get('groupId')}|{(pl or {}).get('seriesId')}" if pl else None
            g_series_label = _series_label(gp, lm.get("seriesId"))
            p_series_label = _series_label(pp, (pl or {}).get("seriesId")) if pl else None
            lrows.append({
                "figure": gt["id"], "article": gt["article"], "split": gt["_split"],
                "panel": gp.get("label"), "landmarkId": lid,
                "armGt": arm_gt, "armPred": arm_pred,
                "armCorrect": (arm_pred == arm_gt) if pl else False,
                # naming errors are ~10x more damaging than structural ones and are
                # INVISIBLE to every structural metric -- series tier, measured
                "armNameGt": g_series_label, "armNamePred": p_series_label,
                "armNameCorrect": (norm_label(g_series_label) == norm_label(p_series_label))
                                  if pl else False,
                "n": n, "dispTypeGt": gdisp, "dispTypePred": pdisp,
                "capLenPx": caplen, "nBucket": _n_bucket(n),
                "varianceType": (gdisp or "unknown"),
                "centralG": g_c, "centralM": p_c,
                "dispG": g_d, "dispM": p_d,
                "sdG": as_sd(g_d, gdisp, n), "sdM": as_sd(p_d, pdisp or gdisp, n),
                "centralPct": _pct(p_c, g_c), "dispPct": _pct(p_d, g_d),
                "ingestDefect": defect,
                "sigMarkersOverCaps": gp.get("sigMarkersOverCaps"),
                "chartType": gtype, "hasPrediction": pl is not None,
                "durationSec": gt.get("durationSec"),
                "fastRead": (gt.get("durationSec") is not None
                             and gt["durationSec"] < FAST_READ_SEC),
            })

        for row in coded_by_panel.get(
                (canonical_figure_id(gt["id"]), norm_label(gp.get("label"))), []):
            crows.append(_comparison_row(gt, gp, pp, row, lrows))
    return prows, lrows, crows


def match_landmarks(gt_lms, pred_lms):
    """Bind predicted landmarks to GT landmarks BY GEOMETRY (nearest central pixel),
    not by landmarkId.

    This matters and it is not a detail. `landmarkId` is by convention the arm key
    "{groupId}|{seriesId}". Joining on it would make an arm swap *unobservable*: the
    predicted 'control' bar would simply be compared against the GT 'control' bar and
    everything would score perfectly, which is precisely the silent failure the series
    tier measured (perfect clustering + swapped legend labels = 0.000 structural error,
    ARI 1.000, and 30.3% effect sign flips). Binding by position and THEN comparing the
    claimed (group, series) is the only way the metric can see it. Selftest E3 enforces
    this. Falls back to an id join only when no pixels exist on either side."""
    out = {}
    if not gt_lms or not pred_lms:
        return out
    gpx = [l.get("centralPx") for l in gt_lms]
    ppx = [l.get("centralPx") for l in pred_lms]
    if all(g for g in gpx) and all(p for p in ppx):
        pairs = sorted(
            ((math.dist((gpx[i]["px"], gpx[i]["py"]), (ppx[j]["px"], ppx[j]["py"])), i, j)
             for i in range(len(gt_lms)) for j in range(len(pred_lms))),
            key=lambda t: t[0])
        usedg, usedp = set(), set()
        for dist, i, j in pairs:
            if i in usedg or j in usedp:
                continue
            usedg.add(i)
            usedp.add(j)
            out[i] = pred_lms[j]
        return out
    byid = {str(l.get("landmarkId")): l for l in pred_lms}
    for i, l in enumerate(gt_lms):
        p = byid.get(str(l.get("landmarkId")))
        if p is not None:
            out[i] = p
    return out


def _n_bucket(n):
    """Group size drives how a cap error propagates: a b% cap error becomes ~2b% on the
    variance and ~sqrt(n) on the study weight. The corpus median n is 10."""
    if not n:
        return "unknown"
    return "n<=8" if n <= 8 else ("n9-12" if n <= 12 else "n>12")


def _series_label(panel, sid):
    for s in (panel or {}).get("series") or []:
        if str(s.get("seriesId") or s.get("id")) == str(sid):
            return s.get("label")
    return None


def _pct(est, ref):
    if est is NA or ref is NA or est is None or ref is None or not ref:
        return NA
    return 100 * abs(est - ref) / abs(ref)


def _comparison_row(gt, gp, pp, coded, lrows):
    """One coded comparison scored three ways: D (dissertation), G (fresh human), M
    (machine). The arm->landmark join is the annotator's, never guessed -- guessing it
    would fabricate exactly the mis-assignment this study measures."""
    ck, ik = coded.get("controlLandmarkId"), coded.get("intervLandmarkId")
    here = [r for r in lrows if r["figure"] == gt["id"]
            and norm_label(r["panel"]) == norm_label(gp.get("label"))]
    idx = {r["landmarkId"]: r for r in here}
    c_lm, i_lm = idx.get(str(ck)), idx.get(str(ik))
    # The MACHINE's arm identity, not the truth's. If the detector calls the wrong bar
    # "control", the pipeline downstream feeds THAT bar's numbers into the control slot
    # of escalc -- which is how a mis-assignment becomes an effect-size sign flip while
    # every geometric and magnitude metric stays perfect. Scoring the M arm by GT
    # identity would silently repair the error and hide the whole failure mode.
    m_idx = {r["armPred"]: r for r in here if r.get("armPred")}
    c_m, i_m = m_idx.get(str(ck)), m_idx.get(str(ik))
    row = {
        "figure": gt["id"], "article": gt["article"], "split": gt["_split"],
        "panel": gp.get("label"), "comparisonId": coded.get("comparisonId"),
        "direction": coded.get("direction"), "isOracle": coded.get("isOracle"),
        "vifMultiarm": coded.get("vifMultiarm", 1.0),
        "joined": bool(c_lm and i_lm),
    }
    if not (c_lm and i_lm):
        return row
    cc, ci = coded.get("control") or {}, coded.get("interv") or {}
    for tag, lm, mm, cod in (("c", c_lm, c_m, cc), ("i", i_lm, i_m, ci)):
        row[f"{tag}_n"] = cod.get("n") or lm.get("n")
        row[f"{tag}_mean_D"] = cod.get("mean")
        row[f"{tag}_sd_D"] = cod.get("sd")
        row[f"{tag}_quantum"] = cod.get("roundingQuantumPct")
        row[f"{tag}_varianceType"] = cod.get("varianceType")
        row[f"{tag}_mean_G"] = lm.get("centralG")
        row[f"{tag}_sd_G"] = lm.get("sdG")
        row[f"{tag}_mean_M"] = (mm or {}).get("centralM")
        row[f"{tag}_sd_M"] = (mm or {}).get("sdM")
        row[f"{tag}_armCorrect"] = lm.get("armCorrect")
        row[f"{tag}_armNameCorrect"] = lm.get("armNameCorrect")
    row["armsBoundByMachine"] = bool(c_m and i_m)
    for tag in ("D", "G", "M"):
        vals = [row.get(f"c_mean_{tag}"), row.get(f"c_sd_{tag}"), row.get("c_n"),
                row.get(f"i_mean_{tag}"), row.get(f"i_sd_{tag}"), row.get("i_n")]
        if all(v is not None and v is not NA for v in vals):
            g, vi = hedges_g(*vals)
            if (coded.get("direction") or "").lower().startswith("lower"):
                g = -g if g is not NA else NA
            row[f"g_{tag}"], row[f"vi_{tag}"] = g, vi
    for a, b in (("M", "D"), ("M", "G"), ("G", "D")):
        ga, gb = row.get(f"g_{a}"), row.get(f"g_{b}")
        if ga not in (None, NA) and gb not in (None, NA):
            row[f"dg_{a}{b}"] = abs(ga - gb)
            row[f"signflip_{a}{b}"] = (ga * gb) < 0
    return row


# ============================================================ dispersion analysis
def dispersion_analysis(lrows, crows, repeat_pairs):
    """The headline, in the four layers ANALYSIS-PLAN sec.1.4 pre-specifies. Nothing
    here is presented as machine accuracy except the oracle stratum."""
    out = {}

    # (a) NAIVE DISAGREEMENT -- reported, never interpreted as accuracy.
    naive_rows = [r for r in lrows if r["dispPct"] is not NA]
    naive = [r["dispPct"] for r in naive_rows]
    out["naive"] = {
        "n": len(naive), "medianPct": med(naive), "p90Pct": pctl(naive, 0.90),
        "worstPct": max(naive) if naive else NA,
        "medianCI": cb_median(naive_rows, lambda r: r["dispPct"]),
        "medianCI_iid": median_ci(naive),
        "_WARNING": "TWO-READER DISAGREEMENT, NOT MACHINE ACCURACY. "
                    "Greg's own 1px jitter is 3.89% median / 27.7% worst on this channel.",
    }
    central_rows = [r for r in lrows if r["centralPct"] is not NA]
    central = [r["centralPct"] for r in central_rows]
    out["central"] = {
        "n": len(central), "medianPct": med(central), "p95Pct": pctl(central, 0.95),
        "worstPct": max(central) if central else NA,
        "medianCI": cb_median(central_rows, lambda r: r["centralPct"]),
        "medianCI_iid": median_ci(central),
    }

    # (b) BLAND-ALTMAN on log(SD_M / SD_G) -- the interchangeability question.
    #     Rows that cannot form a log-ratio are DROPPED; the count is reported rather
    #     than silently absorbed (a metric computed on an unstated subset is not a
    #     metric). Every log-ratio site below reports its own `nDropped`.
    def logr_rows(rows, fa, fb):
        keep, drop = [], 0
        for r in rows:
            x, y = fa(r), fb(r)
            if x in (None, NA) or y in (None, NA) or not (x > 0 and y > 0):
                drop += 1
                continue
            keep.append((r, math.log(x / y)))
        return keep, drop

    def logr(a, b):
        return [math.log(x / y) for x, y in zip(a, b)
                if x not in (None, NA) and y not in (None, NA) and x > 0 and y > 0]

    mg_rows, mg_drop = logr_rows(lrows, lambda r: r["sdM"], lambda r: r["sdG"])
    out["blandAltman_MG"] = bland_altman([v for _, v in mg_rows])
    out["blandAltman_MG_dropped"] = mg_drop
    if out["blandAltman_MG"]:
        out["blandAltman_MG"]["nDropped"] = mg_drop
        out["blandAltman_MG"]["nCandidate"] = len(lrows)
        out["blandAltman_MG"]["biasCI"] = cb(
            mg_rows, lambda g: 100 * (math.exp(statistics.fmean([v for _, v in g])) - 1))
        out["blandAltman_MG"]["loaLoCI"] = cb(mg_rows, lambda g: _loa(g, -1))
        out["blandAltman_MG"]["loaHiCI"] = cb(mg_rows, lambda g: _loa(g, +1))
        # LoA BY STRATUM. A pooled LoA assumes one error distribution; the pilot showed
        # the short-cap tertile at [-41.9, +59.1]% and the long at [-5.0, +4.4]%, so a
        # pooled figure describes neither. Reported per cap-length tertile; the pooled
        # number stays only as a diagnostic and is labelled as one.
        out["blandAltman_MG_byCapTertile"], out["blandAltman_MG_normality"] = \
            _ba_by_stratum(mg_rows)

    # (c) NOISE FLOOR from Greg's own repeats. Machine error is reported relative to
    #     the range two of the human's OWN readings differ by, never against zero.
    if repeat_pairs and len(repeat_pairs) >= 3:
        lr = [math.log(a / b) for a, b in repeat_pairs if a > 0 and b > 0]
        if len(lr) >= 3:
            # UNITS (fixed 2026-07-27, amendment A7). R_floor compares two DIFFERENCE
            # distributions and both sides must be on the same scale.
            #
            #   sd_diff_repeat = sd of log(G1/G2)        <- the human's own test-retest diff
            #   sigmaG_repeat  = sd_diff_repeat/sqrt(2)  <- the per-reading human error
            #   RC_intra       = 1.96 * sd_diff_repeat   <- repeatability coefficient (95%)
            #
            # As shipped the numerator was median|log(M/G)| -- a MEDIAN ABSOLUTE, i.e.
            # 0.6745 * sd for a normal -- divided by RC_intra = 2.77 * sigmaG_repeat.
            # That mixes a robust half-width with a 95% band, so R_floor > 1 required
            # sd(M-G) > 2.77/0.6745 = 4.11 x sd(G1-G2): the machine had to be ~4x worse
            # than the human before the mandatory AND-conjunct of the sec.8.2 GO rule
            # could fire. The rule was unreachable in practice and read backwards.
            #
            # Fixed by putting both sides on the DIFFERENCE-SD scale. The median absolute
            # log-ratio is converted to an SD by /0.6745 (the normal-consistency constant
            # that makes a MAD-style estimator agree with sd), and divided by the sd of the
            # human's own test-retest difference:
            #
            #   R_floor = sd_diff(M,G) / sd_diff(G1,G2)
            #
            # Var(M-G) = sigma_M^2 + sigma_G^2 and Var(G1-G2) = 2*sigma_G^2, so
            # R_floor == 1 EXACTLY when sigma_M == sigma_G. The threshold of 1.0 in the
            # GO rule now means what sec.3.3 and sec.8.2 say it means: "machine error
            # comparable to human test-retest". Both robust and classical numerators are
            # reported so the estimator choice is visible rather than assumed.
            MEDIAN_ABS_TO_SD = 0.674490                     # Phi^-1(0.75)
            sd_diff_repeat = statistics.stdev(lr)
            sd_within = sd_diff_repeat / math.sqrt(2)
            rc = 1.959964 * sd_diff_repeat
            mg_log = logr([r["sdM"] for r in lrows], [r["sdG"] for r in lrows])
            mgd = [abs(x) for x in mg_log]
            sd_diff_mg_robust = (med(mgd) / MEDIAN_ABS_TO_SD) if mgd else NA
            sd_diff_mg_classical = statistics.stdev(mg_log) if len(mg_log) >= 2 else NA
            out["noiseFloor"] = {
                "nRepeatPairs": len(lr),
                "sigmaG_repeat_log": sd_within,
                "sigmaG_repeat_pct": 100 * (math.exp(sd_within) - 1),
                "sd_diff_repeat_log": sd_diff_repeat,
                "RC_intra_pct": 100 * (math.exp(rc) - 1),
                "median_absLogMG": med(mgd),
                "median_absLogMG_pct": (100 * (math.exp(med(mgd)) - 1)) if mgd else NA,
                "sd_diff_MG_log": sd_diff_mg_robust,
                "sd_diff_MG_log_classical": sd_diff_mg_classical,
                "R_floor": ((sd_diff_mg_robust / sd_diff_repeat)
                            if sd_diff_repeat and sd_diff_mg_robust is not NA else NA),
                "R_floor_classical": ((sd_diff_mg_classical / sd_diff_repeat)
                                      if sd_diff_repeat
                                      and sd_diff_mg_classical is not NA else NA),
                "_definition": "R_floor = sd(log M/G) / sd(log G1/G2), both on the "
                               "difference scale. The numerator is the robust estimate "
                               "median|log(M/G)| / 0.6745; R_floor_classical uses the "
                               "sample sd instead. R_floor == 1 iff sigma_M == sigma_G.",
                "_note": "R_floor <= 1 means the machine sits inside the human's own "
                         "test-retest range: no accuracy claim either way is supportable "
                         "from real figures, and the ML detector has no accuracy case.",
            }
    else:
        out["noiseFloor"] = {"_note": "not available -- need >=3 repeat-annotated landmarks"}

    # (d) GRUBBS three-reading decomposition. The primary inferential claim.
    #
    # NOTE ON CODED ROUNDING, and why the coarse rows are KEPT here.
    # The historical reading D is printed to finite precision; measured over the
    # workbooks the rounding quantum is median ~4% of the value and exceeds 1% on about
    # two thirds of arm-values, which looks fatal. It is not, for sigma_M. Quantization
    # Q is independent noise entering D ONLY, so it appears with opposite signs in the
    # Grubbs contrast and cancels exactly:
    #     sigma_M^2 = [Var(M-G) + (sM^2+sD^2+Q) - (sG^2+sD^2+Q)] / 2 = sigma_M^2
    # It inflates sigma_D and nothing else. So the primary machine-variance estimate
    # uses ALL complete triplets (recovering the full n), while the M-vs-D PAIRWISE
    # comparisons and the oracle accuracy analysis -- where Q does NOT cancel -- keep
    # the <=1% restriction. Selftest D6 enforces the cancellation.
    trip, quanta, trip_rows, trip_drop = [], [], [], 0
    for r in crows:
        for tag in ("c", "i"):
            d, g, m = r.get(f"{tag}_sd_D"), r.get(f"{tag}_sd_G"), r.get(f"{tag}_sd_M")
            q = r.get(f"{tag}_quantum")
            if None in (d, g, m) or NA in (d, g, m) or not (d > 0 and g > 0 and m > 0):
                trip_drop += 1
                continue
            trip.append((math.log(d), math.log(g), math.log(m)))
            trip_rows.append((r, (math.log(d), math.log(g), math.log(m))))
            if q is not None and q is not NA:
                quanta.append(q / 100.0)
    out["grubbs_dropped"] = trip_drop
    if len(trip) >= 5:
        gr = grubbs_three([t[0] for t in trip], [t[1] for t in trip], [t[2] for t in trip])
        sig = {k: (math.sqrt(v) if v > 0 else -math.sqrt(-v))
               for k, v in (("D", gr["var_a"]), ("G", gr["var_b"]), ("M", gr["var_c"]))}
        ratio = (sig["M"] / sig["G"]) if sig["G"] > 0 else NA
        nf = out.get("noiseFloor") or {}
        c_hat = NA
        corrected = NA
        if nf.get("sigmaG_repeat_log") is not None and gr["var_b"] is not None:
            c_hat = nf["sigmaG_repeat_log"] ** 2 - gr["var_b"]
            if c_hat > 0:
                corr_var = gr["var_c"] - c_hat
                corrected = (math.sqrt(corr_var) / sig["G"]) if corr_var > 0 and sig["G"] > 0 else 0.0
        out["grubbs"] = {
            "n": gr["n"],
            "sigma_D_log": sig["D"], "sigma_G_log": sig["G"], "sigma_M_log": sig["M"],
            "sigma_D_pct": 100 * (math.exp(abs(sig["D"])) - 1) * (1 if sig["D"] >= 0 else -1),
            "sigma_G_pct": 100 * (math.exp(abs(sig["G"])) - 1) * (1 if sig["G"] >= 0 else -1),
            "sigma_M_pct": 100 * (math.exp(abs(sig["M"])) - 1) * (1 if sig["M"] >= 0 else -1),
            "n_dropped": trip_drop,
            "ratio_MG": ratio,
            # PRE-REGISTERED INTERVAL: article-level cluster bootstrap (sec.2.1). The
            # F-based interval below assumes i.i.d. arm-values and is ~1.6x too narrow
            # at the article level; it is retained only as the labelled i.i.d. contrast.
            "ratio_MG_ci": cb(trip_rows, _grubbs_ratio_stat),
            "ratio_MG_ci_iid": sd_ratio_ci(gr["n"], ratio) if ratio is not NA else (NA, NA),
            "ratio_MG_corrected_lo": corrected,
            "c_hat_shared_person": c_hat,
            "negativeVariance": any(v < 0 for v in (gr["var_a"], gr["var_b"], gr["var_c"])),
            "_biasDirection": "UNKNOWN",
            "_note": (
                "The full algebra with correlated errors is\n"
                "  E[sigma_M^2 (Grubbs)] = sigma_M^2 + c_DG - c_DM - c_GM\n"
                "where c_XY = Cov(e_X, e_Y). c_DG >= 0 (D and G are the same person) "
                "pushes the estimate UP, but c_DM and c_GM push it DOWN and are NOT "
                "zero: sec.7 lists 'machine and human both misread the same ambiguous "
                "cap the same way' as a live threat, and an asterisk mistaken for a cap "
                "is exactly a difficulty shared by every reader of that panel. THE BIAS "
                "DIRECTION IS THEREFORE UNKNOWN without assuming the machine's errors "
                "are uncorrelated with the humans'. Do not call this conservative. "
                "The [corrected, uncorrected] interval brackets c_DG only; it does not "
                "bracket c_DM or c_GM, and when shared difficulty dominates the interval "
                "can sit entirely below the true sigma_M. Cross-check against the ORACLE "
                "stratum, which carries true values and so cannot suffer shared-difficulty "
                "correlation at all: Grubbs-vs-oracle disagreement IS the evidence that "
                "the confound is present."),
        }
        # sigma_D carries the coded print-precision on top of its reading error. A
        # uniform quantum of half-width h has variance h^2/3 on the relative scale, so
        # the reading component of sigma_D is recoverable by subtraction. Reported
        # separately so sigma_D is not misread as the historical reader's skill.
        if quanta:
            qvar = statistics.fmean([(q ** 2) / 3 for q in quanta])
            out["grubbs"]["quantizationVarLog"] = qvar
            out["grubbs"]["quantizationPctOfVarD"] = (
                100 * qvar / gr["var_a"]) if gr["var_a"] > 0 else NA
            resid = gr["var_a"] - qvar
            out["grubbs"]["sigma_D_readingOnly_pct"] = (
                100 * (math.exp(math.sqrt(resid)) - 1)) if resid > 0 else 0.0
            out["grubbs"]["_quantNote"] = (
                "coded print-precision inflates sigma_D only; it CANCELS out of "
                "sigma_M (see the derivation in the source), so no rows were dropped "
                "from the machine-variance estimate on that account.")
    else:
        out["grubbs"] = {"_note": f"not available -- need >=5 complete D/G/M triplets "
                                  f"(have {len(trip)})"}

    # (d2) Pairwise M vs D. Here the coded quantization does NOT cancel, so the
    #      <=1% restriction applies.
    md, md_rows, md_drop_missing, md_drop_quantum = [], [], 0, 0
    for r in crows:
        for tag in ("c", "i"):
            d, m = r.get(f"{tag}_sd_D"), r.get(f"{tag}_sd_M")
            q = r.get(f"{tag}_quantum")
            if None in (d, m) or NA in (d, m) or not (d > 0 and m > 0):
                md_drop_missing += 1
                continue
            if q is None or q is NA or q > ROUNDING_QUANTUM_MAX_PCT:
                md_drop_quantum += 1
                continue
            md.append(math.log(m / d))
            md_rows.append((r, math.log(m / d)))
    out["blandAltman_MD"] = bland_altman(md)
    if out["blandAltman_MD"]:
        out["blandAltman_MD"]["nDroppedMissing"] = md_drop_missing
        out["blandAltman_MD"]["nDroppedQuantum"] = md_drop_quantum
        out["blandAltman_MD"]["biasCI"] = cb(
            md_rows, lambda g: 100 * (math.exp(statistics.fmean([v for _, v in g])) - 1))
    out["blandAltman_MD_note"] = (
        f"restricted to coded values whose print-precision is <= "
        f"{ROUNDING_QUANTUM_MAX_PCT}% of the value ({len(md)} arm-values survive; "
        f"{md_drop_missing} dropped for a missing/non-positive reading, "
        f"{md_drop_quantum} for a coarse quantum); "
        f"quantization does not cancel in a pairwise contrast.")

    # (e) ACCURACY, only where an oracle is VERIFIED. `isOracle` is set exclusively by
    #     verify_oracle.py, which requires the coded mean AND variance to appear
    #     co-located in the paper's body text. The label alone does not qualify: over
    #     the checkable rows the "Reported in text/figure" label confirmed at 1/34,
    #     i.e. it means CORROBORATED, not QUOTED.
    orc = [r for r in crows if r.get("isOracle")]
    acc, acc_rows, orc_log, orc_drop = [], [], [], 0
    for r in orc:
        for tag in ("c", "i"):
            d, m = r.get(f"{tag}_sd_D"), r.get(f"{tag}_sd_M")
            q = r.get(f"{tag}_quantum")
            if None in (d, m) or NA in (d, m) or not d:
                orc_drop += 1
                continue
            if q is not None and q is not NA and q > ROUNDING_QUANTUM_MAX_PCT:
                orc_drop += 1
                continue
            acc.append(100 * abs(m - d) / abs(d))
            acc_rows.append((r, 100 * abs(m - d) / abs(d)))
            if d > 0 and m > 0:
                orc_log.append(math.log(m / d))
    out["oracleAccuracy"] = {
        # SCOPE. This count describes the rows joined IN THIS RUN, i.e. at the
        # --split-filter and GT coverage actually being analysed. It is NOT the
        # corpus-wide oracle count and must never be reported as one (sec.1.4b).
        "n": len(acc), "nRows": len(orc), "nDropped": orc_drop,
        "nPanels": len({(canonical_figure_id(r.get("figure")),
                         norm_label(r.get("panel"))) for r in orc}),
        "nArticles": len({canonical_article(r.get("article")) for r in orc}),
        "scope": "rows joined in THIS run/split -- not the corpus-wide stratum",
        "medianPct": med(acc), "p90Pct": pctl(acc, 0.90),
        "medianCI": cb(acc_rows, lambda g: statistics.median([v for _, v in g]) if g else None),
        "ub95_ruleOfThree": rule_of_three(len(acc)),
        "_note": "VERIFIED oracle only: the paper prints this number, so it IS ground "
                 "truth for the drawing. The only real-figure accuracy claim available. "
                 "Small and non-randomly selected -- report with its caveat.",
    } if acc else {"n": 0, "nRows": len(orc), "nDropped": orc_drop,
                   "_note": "not available -- no VERIFIED oracle rows joined "
                            "(run verify_oracle_v2.py; the label alone does not "
                            "qualify a row)"}

    # (f) THE CROSS-CHECK THAT MATTERS: Grubbs sigma_M against the ORACLE sigma_M.
    #
    # Grubbs identifies sigma_M only if e_D, e_G and e_M are mutually uncorrelated. The
    # threat sec.7 names -- machine and human both misreading the same ambiguous cap the
    # same way -- violates exactly that, and it CANNOT be detected from the three
    # readings alone, because a shared error looks like agreement.
    #
    # The oracle stratum can see it. There the truth is PRINTED IN THE PAPER, so no
    # amount of shared reading difficulty can move it: sd(log(M / truth)) is an estimate
    # of sigma_M that carries no c_DM, no c_GM and no c_DG. If the two estimates agree,
    # the independence assumption survives a real test. If the oracle estimate is LARGER
    # than Grubbs, that is evidence the shared-difficulty confound is present and Grubbs
    # is UNDERSTATING the machine's error -- the anti-conservative direction. Say so.
    gsm = (out.get("grubbs") or {}).get("sigma_M_log")
    if len(orc_log) >= 5 and gsm is not None and gsm is not NA:
        osm = statistics.stdev(orc_log)
        out["grubbsVsOracle"] = {
            "nOracleArmValues": len(orc_log),
            "sigma_M_grubbs_log": gsm,
            "sigma_M_oracle_log": osm,
            "sigma_M_grubbs_pct": 100 * (math.exp(abs(gsm)) - 1),
            "sigma_M_oracle_pct": 100 * (math.exp(osm) - 1),
            "ratio_oracle_over_grubbs": (osm / gsm) if gsm else NA,
            "verdict": ("oracle LARGER -- shared-difficulty confound indicated; Grubbs "
                        "is understating sigma_M (ANTI-conservative)"
                        if gsm and osm > 1.25 * abs(gsm) else
                        "oracle SMALLER -- consistent with c_DG dominating; Grubbs may be "
                        "overstating sigma_M" if gsm and osm < 0.8 * abs(gsm) else
                        "consistent -- no evidence of a shared-error confound at this n"),
            "_note": "Grubbs-vs-oracle disagreement IS the evidence that the confound of "
                     "sec.1.3 is present. Underpowered at small oracle n; report the n.",
        }
    else:
        out["grubbsVsOracle"] = {
            "_note": f"not available -- need >=5 oracle arm-values (have {len(orc_log)}) "
                     f"and a Grubbs estimate"}

    # cap-length tertiles: the pre-specified driver of dispersion error
    withcap = [r for r in lrows if r.get("capLenPx") and r["dispPct"] is not NA]
    if len(withcap) >= 6:
        caps = sorted(r["capLenPx"] for r in withcap)
        t1, t2 = caps[len(caps) // 3], caps[2 * len(caps) // 3]
        buckets = collections.defaultdict(list)
        for r in withcap:
            b = "short" if r["capLenPx"] <= t1 else ("mid" if r["capLenPx"] <= t2 else "long")
            buckets[b].append(r["dispPct"])
        out["byCapTertile"] = {k: {"n": len(v), "medianPct": med(v), "worstPct": max(v)}
                               for k, v in buckets.items()}
        out["capTertileCuts"] = [t1, t2]
    return out


# ============================================================ stratification
def strat(rows, key, stat_fns):
    """Group rows by a key and aggregate. Strata below MIN_STRATUM_N report counts only
    -- a 2/3 in a stratum is not 67%, and the synthetic work showed the stratification
    IS the deliverable."""
    by = collections.defaultdict(list)
    for r in rows:
        by[str(r.get(key))].append(r)
    out = collections.OrderedDict()
    for k in sorted(by, key=str):
        grp = by[k]
        rec = {"n": len(grp), "_suppressed": len(grp) < MIN_STRATUM_N}
        for name, fn in stat_fns.items():
            try:
                rec[name] = NA if rec["_suppressed"] else fn(grp)
            except Exception:
                rec[name] = NA
        out[k] = rec
    return out


PANEL_STATS = {
    "medIoU": lambda g: med([p["iou"] for p in g]),
    "pct90": lambda g: sum(p["tight"] for p in g) / len(g),
    "pct50": lambda g: sum(p["hit"] for p in g) / len(g),
    "labelAcc": lambda g: (sum(p["labelCorrect"] for p in g if p["hit"])
                           / max(1, sum(1 for p in g if p["hit"]))),
    "silentMis": lambda g: sum(p["silentMislabel"] for p in g) / len(g),
}
LM_STATS = {
    "centralMed": lambda g: med([r["centralPct"] for r in g if r["centralPct"] is not NA]),
    "dispMed": lambda g: med([r["dispPct"] for r in g if r["dispPct"] is not NA]),
    "dispWorst": lambda g: max([r["dispPct"] for r in g if r["dispPct"] is not NA] or [NA]),
    "armErr": lambda g: 1 - sum(r["armCorrect"] for r in g) / len(g),
}


# ============================================================ report
def f(v, spec="{:.3f}", na="  n/a"):
    if v is NA or v is None or (isinstance(v, float) and math.isnan(v)):
        return na
    try:
        return spec.format(v)
    except Exception:
        return str(v)


def ci(pair, spec="{:.3f}"):
    """Render a cluster-bootstrap 95% CI. Every interval printed by this report goes
    through here, and every one of them is an article-level cluster bootstrap
    (ANALYSIS-PLAN sec.2.1). The ONLY exceptions are printed with the words
    'not cluster-adjusted' beside them."""
    if not pair or pair[0] is NA or pair[0] is None:
        return "[95% CI  n/a]"
    return f"[95% CI {f(pair[0], spec)}, {f(pair[1], spec)}]"


def transfer_table(real, synth):
    """Delta = metric(synthetic) - metric(real). The study's primary output."""
    rows = []
    for tier, keys in (("panels", list((synth.get("panels") or {}).keys())),
                       ("classify", list((synth.get("classify") or {}).keys())),
                       ("series", list((synth.get("series") or {}).keys())),
                       ("channels", list((synth.get("channels") or {}).keys()))):
        for k in keys:
            spec = (synth.get(tier) or {}).get(k)
            if not isinstance(spec, dict) or "value" not in spec:
                continue
            rv = (real.get(tier) or {}).get(k, NA)
            if rv is NA or rv is None:
                rows.append((tier, k, spec["value"], NA, NA, spec.get("maxDelta"), "no real data"))
                continue
            delta = spec["value"] - rv
            hb = spec.get("higherBetter", True)
            adverse = delta if hb else -delta
            mag = abs(adverse)
            scale = 1.0 if spec.get("unit") in ("iou", "abs") else 1.0
            if adverse <= 0:
                verdict = "transfers (no loss)"
            elif spec.get("unit") == "pct":
                verdict = "transfers" if mag <= 1.0 else ("degrades" if mag <= 5 else "DOES NOT TRANSFER")
            else:
                verdict = ("transfers" if mag <= 0.05 * scale else
                           "degrades but usable" if mag <= 0.15 * scale else
                           "DOES NOT TRANSFER")
            rows.append((tier, k, spec["value"], rv, delta, spec.get("maxDelta"), verdict))
    return rows


def gate_check(real, synth):
    """The pre-committed gates, evaluated mechanically so the decision rule in
    ANALYSIS-PLAN sec.8 cannot be re-argued after seeing the numbers."""
    g = []

    def add(name, value, op, thresh, note=""):
        if value is NA or value is None:
            g.append((name, NA, op, thresh, "NO DATA", note))
            return
        ok = (value >= thresh) if op == ">=" else (value <= thresh)
        g.append((name, value, op, thresh, "PASS" if ok else "FAIL", note))

    d = real.get("detection") or {}
    add("D: caption-association accuracy", d.get("captionAccuracy"), ">=", 0.95)
    add("D: caption -> letter-set accuracy", d.get("letterAccuracy"), ">=", 0.95)
    p = real.get("panels") or {}
    add("P: silent-mislabel rate", p.get("silentMislabel"), "<=", 0.025,
        f"0 observed required; UB(n) = {f(rule_of_three(p.get('nPanels') or 0), '{:.3f}')}")
    # Amendment A18: the abstention gate is 0 missed errors (abstention recall = 1.00),
    # not "net figures saved > 0". A silent error and a needless abstention do not cost the
    # same, so a net count is the wrong loss function for this decision. Coverage keeps its
    # sec.3.2 threshold and is reported as the cost; net figures saved stays in the report
    # as a descriptive.
    add("P: abstention recall = 1.00 (0 missed errors)",
        (p.get("abstention") or {}).get("missedErrors"), "<=", 0,
        f"answered-and-wrong figures; coverage {f((p.get('abstention') or {}).get('coverage'), '{:.1%}')} "
        f"and net figures saved {f((p.get('abstention') or {}).get('net'), '{:+d}')} are the "
        "reported cost, not gated (amendment A18)")
    c = real.get("classify") or {}
    add("E: priority-flip rate", c.get("priorityFlipRate"), "<=", 0.05)
    add("E: dispersion-type flag recall", c.get("dispTypeFlagRecall"), ">=", 0.80)
    s = real.get("series") or {}
    add("E: arm-name accuracy", s.get("armNameAccuracy"), ">=", 0.99)
    add("E: sign-flip rate (arm binding)", s.get("signFlipRate"), "<=", 0.0001)
    disp = real.get("_dispersion") or {}
    ba = disp.get("blandAltman_MG") or {}
    if ba:
        add("E: BA bias |%|", abs(ba.get("biasPct", 0)), "<=", 5.0)
        add("E: BA LoA within +/-25%",
            max(abs(ba.get("loaLoPct", 0)), abs(ba.get("loaHiPct", 0))), "<=", 25.0)
    gr = disp.get("grubbs") or {}
    _gci = gr.get("ratio_MG_ci") or (NA, NA)
    add("E: Grubbs sigma_M / sigma_G", gr.get("ratio_MG"), "<=", 1.5,
        "BIAS DIRECTION UNKNOWN (c_DG - c_DM - c_GM); one of three estimates, "
        f"not a bound. cluster-boot CI [{f(_gci[0],'{:.2f}')}, {f(_gci[1],'{:.2f}')}]. "
        "Cross-check against the oracle stratum.")
    ct = (disp.get("byCapTertile") or {}).get("short") or {}
    add("E: shortest-cap tertile median %", ct.get("medianPct"), "<=", 10.0)
    # The R_floor conjunct of the sec.8.2 GO rule, evaluated mechanically so the rescaling
    # of amendment A7 is visible in the gate table rather than only in the prose.
    nf = disp.get("noiseFloor") or {}
    add("E: R_floor = sd(logM/G)/sd(logG1/G2)", nf.get("R_floor"), ">=", 1.0,
        "sec.8.2 AND-conjunct: > 1.0 means the machine is WORSE than the human's own "
        "test-retest, which is what a detector would have to beat. PASS here means the "
        "ML-detector accuracy case is OPEN, not that the tool failed.")
    return g


def report(res, run, split_filter, out=sys.stdout):
    L = []
    p = L.append
    p("=" * 92)
    p(f"REAL-FIGURE VALIDATION -- run '{run}'   split={split_filter}")
    p("=" * 92)
    p("")
    p("  READ THIS FIRST")
    p("  Accuracy claims on the DISPERSION channel are made ONLY against an oracle:")
    p("  the synthetic benchmark (R's exact descriptives), or the text-anchored real")
    p("  stratum where the paper prints the number. Everything else on that channel is")
    p("  AGREEMENT between imprecise readers. Greg's own click jitter is 3.89% median /")
    p("  27.7% worst on dispersion vs 0.44% on central tendency; a naive machine-vs-human")
    p("  dispersion number attributes that jitter to the machine.")
    p("")

    cov = res.get("_coverage") or {}
    p(f"  inputs: {cov.get('gt',0)} GT figures, {cov.get('pred',0)} predictions, "
      f"{cov.get('repeat',0)} repeats, {cov.get('coded',0)} coded rows")
    if cov.get("excluded"):
        p(f"  excluded before annotation: {cov['excluded']} "
          f"({', '.join(f'{k}={v}' for k, v in sorted((cov.get('exclusionCodes') or {}).items()))})")
    if cov.get("sawPrediction"):
        p(f"  !! {cov['sawPrediction']} GT records carry sawPrediction=true and were "
          f"REFUSED (anchoring control, sec.7)")
    p("")

    # ---- TIER D
    d = res.get("detection")
    p("-" * 92)
    p("  TIER D -- FIGURE DETECTION + CAPTION ASSOCIATION")
    p("-" * 92)
    if not d or not d.get("n"):
        p("    not available -- no detection ground truth in the GT store")
    else:
        p(f"    figures {d['n']}   articles {d['nArticles']}")
        p(f"    figure-bbox IoU   median {f(d['iouMedian'])}"
          f" {ci(d.get('iouMedianCI'))}   >=0.75 {f(d['pct75'],'{:.1%}')}"
          f"   >=0.50 {f(d['pct50'],'{:.1%}')}")
        p(f"    recall {f(d['recall'],'{:.1%}')}   spurious/page {f(d['spuriousPerPage'],'{:.2f}')}")
        p(f"    CAPTION-ASSOCIATION accuracy {f(d['captionAccuracy'],'{:.1%}')}"
          f"   {ci(d.get('captionCI'), '{:.1%}')}")
        p(f"      (i.i.d. Wilson interval, for contrast only: "
          f"{f(d['captionCI_iid'][0],'{:.1%}')}, {f(d['captionCI_iid'][1],'{:.1%}')})")
        p(f"    caption -> letter-set accuracy {f(d['letterAccuracy'],'{:.1%}')}"
          f" {ci(d.get('letterCI'), '{:.1%}')}")
        p("    (no synthetic detection benchmark exists -- Delta is undefined for this tier)")
    p("")

    # ---- TIER P
    pn = res.get("panels")
    p("-" * 92)
    p("  TIER P -- PANEL DECOMPOSITION")
    p("-" * 92)
    if not pn or not pn.get("nPanels"):
        p("    not available -- no panel ground truth in the GT store")
    else:
        p(f"    figures {pn['nFigures']}   panels {pn['nPanels']}   articles {pn['nArticles']}")
        p("    LOCALISATION")
        p(f"      per-panel IoU   median {f(pn['iouMedian'])} {ci(pn.get('iouMedianCI'))}"
          f"   mean {f(pn['iouMean'])}   worst {f(pn['iouWorst'])}")
        p(f"      IoU >= 0.9 {f(pn['pct90'],'{:.1%}')} {ci(pn.get('pct90CI'),'{:.1%}')}"
          f"   IoU >= 0.5 {f(pn['pct50'],'{:.1%}')} {ci(pn.get('pct50CI'),'{:.1%}')}"
          f"   never matched {pn['missed']}")
        p("    COUNT")
        p(f"      exact panel count {f(pn['countAcc'],'{:.1%}')}"
          f" {ci(pn.get('countAccCI'),'{:.1%}')}"
          f"   over {f(pn['overSplit'],'{:.1%}')}   under {f(pn['underSplit'],'{:.1%}')}"
          f"   spurious boxes {pn['falsePositives']}")
        p("    ASSIGNMENT  (the silent catastrophic class)")
        p(f"      localised panels given the RIGHT letter {f(pn['labelAccLocalised'],'{:.1%}')}"
          f" {ci(pn.get('labelAccLocalisedCI'),'{:.1%}')}")
        p(f"      SILENT MISLABELS {pn['silentMislabelCount']} / {pn['nPanels']}"
          f" = {f(pn['silentMislabel'],'{:.2%}')} {ci(pn.get('silentMislabelCI'),'{:.2%}')}")
        if pn["silentMislabelCount"] == 0:
            p(f"        0 observed -> 95% upper bound {f(rule_of_three(pn['nPanels']),'{:.2%}')}"
              f"  (rule of three; threshold 2.50%)")
            p("        ** NOT CLUSTER-ADJUSTED ** the rule of three is a binomial")
            p("        zero-event bound and has no clustered analogue: with 0 events the")
            p("        bootstrap resamples 0 every time and returns [0, 0]. Read it as an")
            p("        upper bound on the PANEL-level rate treating panels as independent,")
            f_eff = pn.get("nArticles") or 0
            p(f"        which they are not -- at {pn['nPanels']} panels in {f_eff} articles")
            p(f"        the article-level bound is {f(rule_of_three(f_eff),'{:.2%}')}. Both are stated;")
            p("        neither is the 'cluster bootstrap' the plan promises, because that")
            p("        promise cannot be kept for a zero count.")
        p("    ABSTENTION")
        ab = pn["abstention"]
        p(f"      coverage {f(ab['coverage'],'{:.1%}')}   error on answered "
          f"{f(ab['errorRateAnswered'],'{:.1%}')}   (all: {f(ab['errorRateAll'],'{:.1%}')})")
        p(f"      precision {f(ab['precision'],'{:.2f}')}   recall {f(ab['recall'],'{:.2f}')}"
          f"   NET FIGURES SAVED {ab['net']:+d}")
        p(f"    whole figure exactly right {f(pn['figExact'],'{:.1%}')}"
          f"   ANSWERED-ONLY {f(pn['figExactAnswered'],'{:.1%}')}")
        for title, key in (("by gutter (measured)", "gutterBucket"),
                           ("by layout class", "layoutClass"),
                           ("by label placement", "labelPlacement"),
                           ("by panel content type", "contentType"),
                           ("by figure origin", "origin"),
                           ("by split", "split")):
            tab = pn["strata"].get(key) or {}
            if not tab:
                continue
            p("")
            p(f"    {title}")
            p(f"      {'stratum':<20}{'n':>5}{'medIoU':>9}{'>=.9':>8}{'>=.5':>8}"
              f"{'label':>8}{'silentMis':>11}")
            for k, s in tab.items():
                if s["_suppressed"]:
                    p(f"      {k:<20}{s['n']:>5}{'  (n<10: counts only)':>44}")
                else:
                    p(f"      {k:<20}{s['n']:>5}{f(s['medIoU']):>9}{f(s['pct90'],'{:.0%}'):>8}"
                      f"{f(s['pct50'],'{:.0%}'):>8}{f(s['labelAcc'],'{:.0%}'):>8}"
                      f"{f(s['silentMis'],'{:.1%}'):>11}")
    p("")

    # ---- TIER E
    e = res.get("extraction")
    p("-" * 92)
    p("  TIER E -- ELEMENT EXTRACTION")
    p("-" * 92)
    if not e or not e.get("nPanels"):
        p("    not available -- no extraction ground truth in the GT store")
    else:
        p(f"    panels {e['nPanels']}   landmarks {e['nLandmarks']}"
          f"   comparisons joined {e['nComparisonsJoined']}/{e['nComparisons']}")
        p(f"    chart-type accuracy {f(e['chartTypeAccuracy'],'{:.1%}')}"
          f" {ci(e.get('chartTypeCI'),'{:.1%}')}"
          f"   priority-flip rate {f(e['priorityFlipRate'],'{:.1%}')}"
          f" {ci(e.get('priorityFlipCI'),'{:.1%}')}")
        p(f"    dispersion-TYPE agreement {f(e['dispTypeAccuracy'],'{:.1%}')}"
          f" {ci(e.get('dispTypeCI'),'{:.1%}')}")
        p(f"      flag recall on disagreements {f(e['dispTypeFlagRecall'],'{:.1%}')}"
          f" {ci(e.get('dispTypeFlagRecallCI'),'{:.1%}')}")
        p(f"      (SEM read as SD multiplies every SD by sqrt(n) ~ 3.2x at the corpus "
          f"median n=10 -- larger than every pixel effect here)")
        p(f"    series->arm binding error {f(e['armErrorRate'],'{:.2%}')}"
          f" {ci(e.get('armErrorCI'),'{:.2%}')}")
        p(f"    ARM-NAME error {f(e['armNameErrorRate'],'{:.2%}')}"
          f" {ci(e.get('armNameErrorCI'),'{:.2%}')}")
        p(f"      (naming errors are ~10x more damaging than structural ones and are "
          f"invisible to structural metrics -- series tier, measured)")
        if e.get("signFlipRate") is not NA:
            p(f"    effect SIGN FLIPS (M vs G) {e['signFlips']}/{e['nSignComparisons']}"
              f" = {f(e['signFlipRate'],'{:.2%}')} {ci(e.get('signFlipCI'),'{:.2%}')}")
        dsp = res.get("_dispersion") or {}
        p("")
        p("    CENTRAL TENDENCY (the control channel -- long pixel distance)")
        ct = dsp.get("central") or {}
        p(f"      median {f(ct.get('medianPct'),'{:.2f}')}% {ci(ct.get('medianCI'),'{:.2f}')}"
          f"   p95 {f(ct.get('p95Pct'),'{:.2f}')}%"
          f"   worst {f(ct.get('worstPct'),'{:.2f}')}%   n={ct.get('n',0)}")
        p("")
        p("    DISPERSION -- reported in five layers; only (e) is an accuracy")
        nv = dsp.get("naive") or {}
        p(f"      (a) naive M-vs-G disagreement: median {f(nv.get('medianPct'),'{:.2f}')}%"
          f" {ci(nv.get('medianCI'),'{:.2f}')}"
          f"   p90 {f(nv.get('p90Pct'),'{:.2f}')}%   worst {f(nv.get('worstPct'),'{:.2f}')}%"
          f"   n={nv.get('n',0)}")
        p(f"          *** NOT AN ACCURACY *** two imprecise readers; see the header.")
        ba = dsp.get("blandAltman_MG")
        if ba:
            p(f"      (b) Bland-Altman log(SD_M/SD_G)   n={ba['n']}"
              f"   ({ba.get('nDropped',0)} of {ba.get('nCandidate','?')} landmark rows "
              f"DROPPED: no positive SD on both sides)")
            p(f"          normality of the log-ratios (probability-plot r) "
              f"{f((dsp.get('blandAltman_MG_normality') or {}).get('pooled'),'{:.3f}')}"
              f"   -- a +/-1.96sd LoA is a 95% interval only if this is near 1")
            byc = dsp.get("blandAltman_MG_byCapTertile") or {}
            strata_ba = {k: v for k, v in byc.items() if not k.startswith("_")}
            if strata_ba:
                p(f"          LoA REPORTED BY CAP-LENGTH TERTILE (cuts at "
                  f"{byc.get('_cuts')} px). The log transform does NOT stabilise the")
                p("          variance here -- the error is ~1 px of jitter on a cap whose")
                p("          length varies ~10x, so sd(log-ratio) still scales with 1/capLen")
                p("          and a POOLED LoA describes no stratum. Pooled shown last, as a")
                p("          diagnostic only.")
                p(f"          {'tertile':<10}{'n':>5}{'medCap px':>11}{'bias%':>9}"
                  f"{'LoA lo%':>10}{'LoA hi%':>10}{'normR':>8}")
                for k in ("short", "mid", "long"):
                    s = strata_ba.get(k)
                    if not s:
                        continue
                    p(f"          {k:<10}{s['n']:>5}{f(s.get('capLenMedianPx'),'{:.0f}'):>11}"
                      f"{s['biasPct']:>+9.2f}{s['loaLoPct']:>+10.1f}{s['loaHiPct']:>+10.1f}"
                      f"{f(s.get('normalityR'),'{:.3f}'):>8}")
            p(f"          pooled (DIAGNOSTIC ONLY, describes no stratum): "
              f"bias {ba['biasPct']:+.2f}% {ci(ba.get('biasCI'),'{:+.2f}')}")
            p(f"          pooled 95% LoA [{ba['loaLoPct']:+.1f}%, {ba['loaHiPct']:+.1f}%]"
              f"   lo {ci(ba.get('loaLoCI'),'{:+.1f}')}  hi {ci(ba.get('loaHiCI'),'{:+.1f}')}")
        else:
            p("      (b) Bland-Altman: not available (need >=3 paired SDs)"
              f"   ({dsp.get('blandAltman_MG_dropped',0)} rows dropped)")
        bd = dsp.get("blandAltman_MD")
        if bd:
            p(f"      (b2) Bland-Altman log(SD_M/SD_D) [historical reading]: "
              f"bias {bd['biasPct']:+.2f}% {ci(bd.get('biasCI'),'{:+.2f}')}"
              f"   95% LoA [{bd['loaLoPct']:+.1f}%, "
              f"{bd['loaHiPct']:+.1f}%]   n={bd['n']}")
            p(f"           {dsp.get('blandAltman_MD_note','')}")
        nf = dsp.get("noiseFloor") or {}
        if nf.get("R_floor") is not NA and nf.get("R_floor") is not None:
            p(f"      (c) human noise floor: sigma_G(repeat) {f(nf['sigmaG_repeat_pct'],'{:.2f}')}%"
              f"   RC_intra {f(nf['RC_intra_pct'],'{:.2f}')}%"
              f"   median|M-G| {f(nf.get('median_absLogMG_pct'),'{:.2f}')}%")
            p(f"          R_floor = sd(log M/G) / sd(log G1/G2) = "
              f"{f(nf['R_floor'],'{:.2f}')}"
              f"   (classical-sd variant {f(nf.get('R_floor_classical'),'{:.2f}')})")
            p("          Both sides are difference-SDs on the log scale, so R_floor == 1")
            p("          exactly when sigma_M == sigma_G. NOT cluster-adjusted -- it is a")
            p("          point estimate with no interval; see the CI note at the foot.")
            if nf["R_floor"] <= 1.0:
                p("          R_floor <= 1: the machine sits INSIDE the human's own test-retest")
                p("          range. No accuracy claim either way is supportable from real")
                p("          figures, and the ML detector has NO accuracy case (sec.8.2).")
        else:
            p(f"      (c) human noise floor: {nf.get('_note','not available')}")
        gr = dsp.get("grubbs") or {}
        if gr.get("n"):
            lo = gr.get("ratio_MG_corrected_lo")
            p(f"      (d) GRUBBS three-reading decomposition (D=dissertation, G=fresh, "
              f"M=machine), n={gr['n']}")
            p("          ONE OF THREE ESTIMATES, not a guaranteed bound. Assumption:")
            p("          e_D, e_G, e_M mutually uncorrelated. Read it beside (b) and (e).")
            p(f"          sigma_D {f(gr['sigma_D_pct'],'{:+.2f}')}%   "
              f"sigma_G {f(gr['sigma_G_pct'],'{:+.2f}')}%   "
              f"sigma_M {f(gr['sigma_M_pct'],'{:+.2f}')}%")
            p(f"          n={gr['n']} complete triplets ({gr.get('n_dropped',0)} arm-values "
              f"dropped: incomplete or non-positive D/G/M)")
            p(f"          sigma_M / sigma_G = {f(gr['ratio_MG'],'{:.2f}')}"
              f"   {ci(gr['ratio_MG_ci'],'{:.2f}')}"
              + (f"   c_DG-corrected lower end {f(lo,'{:.2f}')}"
                 if lo is not NA and lo is not None else ""))
            p(f"          (i.i.d. F-based interval, for contrast only: "
              f"{f(gr['ratio_MG_ci_iid'][0],'{:.2f}')}, "
              f"{f(gr['ratio_MG_ci_iid'][1],'{:.2f}')})")
            p("          BIAS DIRECTION UNKNOWN. E[sigma_M^2] = sigma_M^2 + c_DG - c_DM")
            p("          - c_GM. c_DG (same person, twice) inflates it; c_DM and c_GM")
            p("          (machine and human misreading the SAME ambiguous cap the same")
            p("          way -- sec.7) deflate it. Without assuming the machine's errors")
            p("          are uncorrelated with the humans', this is NOT conservative and")
            p("          may UNDERSTATE sigma_M. The bracket below covers c_DG only.")
            if gr.get("quantizationVarLog") is not None:
                p(f"          coded print-precision accounts for "
                  f"{f(gr.get('quantizationPctOfVarD'),'{:.0f}')}% of var(sigma_D); "
                  f"sigma_D reading-only {f(gr.get('sigma_D_readingOnly_pct'),'{:.2f}')}%")
                p("          it CANCELS out of sigma_M, so no rows were dropped from the")
                p("          machine-variance estimate on that account (selftest D6).")
            if gr.get("negativeVariance"):
                p("          !! a variance estimate came out NEGATIVE -- n is too small or")
                p("             the independence assumption is violated. Do not interpret.")
        else:
            p(f"      (d) Grubbs: {gr.get('_note','not available')}")
        oa = dsp.get("oracleAccuracy") or {}
        if oa.get("n"):
            p(f"      (e) ACCURACY on the text-anchored oracle stratum: median "
              f"{f(oa['medianPct'],'{:.2f}')}% {ci(oa.get('medianCI'),'{:.2f}')}"
              f"   p90 {f(oa['p90Pct'],'{:.2f}')}%")
            p(f"          STRATUM SIZE AT THIS SCOPE: {oa['n']} arm-values / "
              f"{oa.get('nRows')} comparisons / {oa.get('nPanels')} panels / "
              f"{oa.get('nArticles')} articles")
            p(f"          ({oa.get('nDropped',0)} arm-values dropped: missing reading or "
              f"coded quantum > {ROUNDING_QUANTUM_MAX_PCT}%)")
            p(f"          This is the size AT THE SCOPE ANALYSED (split={split_filter}).")
            p(f"          Do NOT quote the corpus-wide oracle count beside this result.")
        else:
            p(f"      (e) oracle accuracy: {oa.get('_note','not available')}")
        gvo = dsp.get("grubbsVsOracle") or {}
        if gvo.get("nOracleArmValues"):
            p("")
            p("      (f) CROSS-CHECK -- Grubbs sigma_M vs ORACLE sigma_M "
              "(THE test of the Grubbs assumption)")
            p(f"          sigma_M Grubbs {f(gvo['sigma_M_grubbs_pct'],'{:.2f}')}%"
              f"   sigma_M oracle {f(gvo['sigma_M_oracle_pct'],'{:.2f}')}%"
              f"   ratio {f(gvo['ratio_oracle_over_grubbs'],'{:.2f}')}"
              f"   n={gvo['nOracleArmValues']} oracle arm-values")
            p(f"          -> {gvo['verdict']}")
            p("          The oracle truth is PRINTED IN THE PAPER, so it cannot be moved")
            p("          by any error the machine and the human happen to share. It is the")
            p("          only estimate here that is immune to the shared-difficulty")
            p("          confound, and disagreement with Grubbs IS the evidence that the")
            p("          confound is present.")
        else:
            p(f"      (f) Grubbs-vs-oracle cross-check: {gvo.get('_note','not available')}")
        if dsp.get("byCapTertile"):
            p("")
            p(f"      by cap length in px (cuts at {dsp['capTertileCuts']})")
            for k in ("short", "mid", "long"):
                s = dsp["byCapTertile"].get(k)
                if s:
                    p(f"        {k:<8}n={s['n']:<4} median {f(s['medianPct'],'{:6.2f}')}%"
                      f"   worst {f(s['worstPct'],'{:6.2f}')}%")
        for title, key in (("by chart type", "chartType"),
                           ("by dispersion TYPE (corpus is ~94% SEM = the short-cap case)",
                            "varianceType"),
                           ("by group size n", "nBucket"),
                           ("by significance markers over caps", "sigMarkersOverCaps"),
                           ("by split", "split")):
            tab = (e.get("strata") or {}).get(key) or {}
            if not tab:
                continue
            p("")
            p(f"    {title}")
            p(f"      {'stratum':<24}{'n':>5}{'central%':>11}{'disp%':>10}"
              f"{'dispWorst':>11}{'armErr':>9}")
            for k, s in tab.items():
                if s["_suppressed"]:
                    p(f"      {k:<24}{s['n']:>5}{'  (n<10: counts only)':>41}")
                else:
                    p(f"      {k:<24}{s['n']:>5}{f(s['centralMed'],'{:.2f}'):>11}"
                      f"{f(s['dispMed'],'{:.2f}'):>10}{f(s['dispWorst'],'{:.2f}'):>11}"
                      f"{f(s['armErr'],'{:.1%}'):>9}")
    p("")

    # ---- transfer gap
    p("-" * 92)
    p("  TRANSFER GAP   Delta = metric(synthetic) - metric(real)   [the primary output]")
    p("-" * 92)
    rows = res.get("_transfer") or []
    if not rows:
        p("    not available")
    else:
        p(f"    {'tier':<10}{'metric':<24}{'synth':>9}{'real':>9}{'Delta':>9}"
          f"{'max':>7}  verdict")
        for tier, k, sv, rv, dv, mx, verdict in rows:
            p(f"    {tier:<10}{k:<24}{f(sv):>9}{f(rv):>9}{f(dv,'{:+.3f}'):>9}"
              f"{f(mx,'{:.2f}'):>7}  {verdict}")
    p("")

    # ---- gates
    p("-" * 92)
    p("  PRE-COMMITTED GATES (ANALYSIS-PLAN sec.8)")
    p("-" * 92)
    for name, val, op, th, status, note in res.get("_gates") or []:
        p(f"    [{status:<7}] {name:<38} {f(val):>8} {op} {th}"
          + (f"   -- {note}" if note else ""))
    p("")
    p("  DECISION: computed only when every gate has data. Gates with NO DATA mean the")
    p("  study is not yet complete; do not read a decision out of a partial run.")
    p("")
    p("-" * 92)
    p("  HOW EVERY INTERVAL IN THIS REPORT WAS COMPUTED")
    p("-" * 92)
    p(f"  Every '[95% CI ...]' above is an ARTICLE-LEVEL CLUSTER BOOTSTRAP, B={BOOTSTRAP_B},")
    p("  resampling articles with replacement (ANALYSIS-PLAN sec.2.1). Panels of one")
    p("  article share layout, journal, typeface and gutter, so an i.i.d. interval is")
    p("  materially too narrow -- measured at ~1.6x at the article level.")
    p("")
    p("  The exceptions, each labelled in place, are:")
    p("    * the rule-of-three zero-event upper bound (silent mislabel, arm name, sign")
    p("      flip). NOT CLUSTER-ADJUSTED: with 0 events every bootstrap resample also has")
    p("      0 events, so the bootstrap returns [0,0] and carries no information. Both the")
    p("      panel-level and the article-level bounds are printed; neither is a cluster")
    p("      bootstrap, and this report does not pretend otherwise.")
    p("    * R_floor, printed as a point estimate with NO interval.")
    p("    * `..._iid` lines, printed ONLY as the labelled contrast that shows how much")
    p("      narrower the naive interval would have been.")
    p("  No other statement in this report claims an interval it did not compute.")
    p("")
    text = "\n".join(L)
    print(text, file=out)
    return text


# ============================================================ driver
def collect(gts, preds, coded, repeats, abstain_at, split_filter):
    res = {"_coverage": {"gt": len(gts), "pred": len(preds), "coded": len(coded),
                         "repeat": len(repeats)}}
    excl, codes, saw = 0, collections.Counter(), 0
    usable = {}
    for k, g in gts.items():
        g.setdefault("article", "unknown")
        g["_articleKey"] = canonical_article(g["article"])   # the cluster key everywhere
        g["_split"] = g.get("split") or split_of(g["article"])
        g["_gutter"] = (g.get("gutter") or {}).get("bucket") or "unknown"
        if g.get("excluded"):
            excl += 1
            codes[(g["excluded"] or {}).get("code", "?")] += 1
            continue
        if g.get("sawPrediction"):
            saw += 1                     # anchoring control: refuse the record
            continue
        if split_filter != "all" and g["_split"] != split_filter:
            continue
        usable[k] = g
    res["_coverage"].update({"excluded": excl, "exclusionCodes": dict(codes),
                             "sawPrediction": saw, "scored": len(usable)})

    # -- tier D
    drows = [r for r in (score_detection(g, preds.get(k)) for k, g in usable.items()) if r]
    if drows:
        caps = [r for r in drows if r["captionCorrect"] is not NA]
        lets = [r for r in drows if r["lettersCorrect"] is not NA]
        capk = sum(1 for r in caps if r["captionCorrect"])
        res["detection"] = {
            "n": len(drows), "nArticles": len({r["article"] for r in drows}),
            "iouMedian": med([r["iou"] for r in drows]),
            "pct75": sum(r["tight"] for r in drows) / len(drows),
            "pct50": sum(r["matched"] for r in drows) / len(drows),
            "recall": sum(r["matched"] for r in drows) / len(drows),
            "spuriousPerPage": (sum(r["spurious"] for r in drows)
                                / max(1, len({r["pageKey"] for r in drows}))),
            "captionAccuracy": (capk / len(caps)) if caps else NA,
            "captionCI": cb_rate(caps, lambda r: r["captionCorrect"]),
            "captionCI_iid": wilson(capk, len(caps)) if caps else (NA, NA),
            "letterAccuracy": (sum(1 for r in lets if r["lettersCorrect"]) / len(lets))
                              if lets else NA,
            "letterCI": cb_rate(lets, lambda r: r["lettersCorrect"]),
            "iouMedianCI": cb_median(drows, lambda r: r["iou"]),
        }

    # -- tier P
    pfigs = [r for r in (score_panels(g, preds.get(k), abstain_at)
                         for k, g in usable.items()) if r]
    if pfigs:
        A = agg_panels(pfigs)
        allp = [p for fg in pfigs for p in fg["panels"]]
        loc = [p for p in allp if p["hit"]]
        A.update({
            "nFigures": len(pfigs), "nPanels": len(allp),
            "nArticles": len({canonical_article(fg["article"]) for fg in pfigs}),
            # every CI here is an article-level cluster bootstrap (sec.2.1)
            "iouMedianCI": cb_median(allp, lambda r: r["iou"]),
            "pct90CI": cb_rate(allp, lambda r: r["tight"]),
            "pct50CI": cb_rate(allp, lambda r: r["hit"]),
            "countAccCI": cb_rate(pfigs, lambda r: r["countExact"]),
            "labelAccLocalisedCI": cb_rate(loc, lambda r: r["labelCorrect"]),
            "silentMislabelCI": cb_rate(allp, lambda r: r["silentMislabel"]),
            "figExactCI": cb_rate(pfigs, lambda r: not r["wrong"]),
            "abstention": abstention(pfigs),
            "netFiguresSaved": abstention(pfigs)["net"],
            "strata": {k: strat(allp, k, PANEL_STATS) for k in
                       ("gutterBucket", "layoutClass", "labelPlacement",
                        "contentType", "origin", "split")},
        })
        res["panels"] = A

    # -- tier E
    coded_by_panel = collections.defaultdict(list)
    for row in coded:
        coded_by_panel[(canonical_figure_id(row.get("figureId")),
                        norm_label(row.get("panelLetter")))].append(row)
    prows, lrows, crows = [], [], []
    for k, g in usable.items():
        a, b, c = score_extraction(g, preds.get(k), coded_by_panel)
        prows += a
        lrows += b
        crows += c
    if prows:
        withpred = [r for r in prows if r["hasPrediction"]]
        dt = [r for r in prows if r["dispTypeGt"] and r["hasPrediction"]]
        dt_bad = [r for r in dt if not r["dispTypeCorrect"]]
        lm_pred = [r for r in lrows if r["hasPrediction"]]
        signs = [r for r in crows if r.get("signflip_MG") is not None]
        res["extraction"] = {
            "nPanels": len(prows), "nLandmarks": len(lrows),
            "nComparisons": len(crows),
            "nComparisonsJoined": sum(1 for r in crows if r.get("joined")),
            "chartTypeAccuracy": (sum(r["chartTypeCorrect"] for r in withpred)
                                  / len(withpred)) if withpred else NA,
            "priorityFlipRate": (sum(1 for r in withpred
                                     if r["priorityGt"] != r["priorityPred"])
                                 / len(withpred)) if withpred else NA,
            "dispTypeAccuracy": (sum(r["dispTypeCorrect"] for r in dt) / len(dt))
                                if dt else NA,
            "dispTypeFlagRecall": (sum(r["dispTypeFlagged"] for r in dt_bad) / len(dt_bad))
                                  if dt_bad else NA,
            "armErrorRate": (1 - sum(r["armCorrect"] for r in lm_pred) / len(lm_pred))
                            if lm_pred else NA,
            "armNameErrorRate": (1 - sum(r["armNameCorrect"] for r in lm_pred) / len(lm_pred))
                                if lm_pred else NA,
            "signFlips": sum(1 for r in signs if r["signflip_MG"]),
            "nSignComparisons": len(signs),
            "signFlipRate": (sum(1 for r in signs if r["signflip_MG"]) / len(signs))
                            if signs else NA,
            # article-level cluster-bootstrap CIs (sec.2.1) for every rate reported above
            "chartTypeCI": cb_rate(withpred, lambda r: r["chartTypeCorrect"]),
            "priorityFlipCI": cb_rate(withpred,
                                      lambda r: r["priorityGt"] != r["priorityPred"]),
            "dispTypeCI": cb_rate(dt, lambda r: r["dispTypeCorrect"]),
            "dispTypeFlagRecallCI": cb_rate(dt_bad, lambda r: r["dispTypeFlagged"]),
            "armErrorCI": cb_rate(lm_pred, lambda r: not r["armCorrect"]),
            "armNameErrorCI": cb_rate(lm_pred, lambda r: not r["armNameCorrect"]),
            "signFlipCI": cb_rate(signs, lambda r: r["signflip_MG"]),
            "strata": {k: strat(lrows, k, LM_STATS) for k in
                       ("chartType", "varianceType", "nBucket",
                        "sigMarkersOverCaps", "split")},
        }
        res["classify"] = {"accuracy": res["extraction"]["chartTypeAccuracy"],
                           "accuracyCI": res["extraction"]["chartTypeCI"],
                           "priorityFlipRate": res["extraction"]["priorityFlipRate"],
                           "priorityFlipCI": res["extraction"]["priorityFlipCI"],
                           "dispTypeFlagRecall": res["extraction"]["dispTypeFlagRecall"],
                           "dispTypeFlagRecallCI": res["extraction"]["dispTypeFlagRecallCI"]}
        _ane = res["extraction"]["armNameErrorCI"]
        res["series"] = {"misassignArmBound": res["extraction"]["armErrorRate"],
                         "misassignSeriesBound": res["extraction"]["armErrorRate"],
                         "armNameAccuracy": (1 - res["extraction"]["armNameErrorRate"])
                                            if res["extraction"]["armNameErrorRate"] is not NA
                                            else NA,
                         "armNameAccuracyCI": ((1 - _ane[1], 1 - _ane[0])
                                               if _ane[0] is not NA else (NA, NA)),
                         "signFlipRate": res["extraction"]["signFlipRate"],
                         "signFlipCI": res["extraction"]["signFlipCI"]}

    # -- dispersion (the headline), incl. repeats
    rp = []
    for k, g2 in repeats.items():
        g1 = gts.get(k)
        if not g1:
            continue
        for pa, pb in zip(g1.get("panels") or [], g2.get("panels") or []):
            for la, lb in zip(pa.get("landmarks") or [], pb.get("landmarks") or []):
                _, da, _, _ = landmark_values(pa, la)
                _, db, _, _ = landmark_values(pb, lb)
                if da not in (None, NA) and db not in (None, NA) and da > 0 and db > 0:
                    rp.append((da, db))
    res["_dispersion"] = dispersion_analysis(lrows, crows, rp)
    if res.get("extraction"):
        res["channels"] = {
            "centralMedianPct": (res["_dispersion"].get("central") or {}).get("medianPct"),
            "dispersionMedianPct": (res["_dispersion"].get("naive") or {}).get("medianPct"),
            "dispersionWorstPct": (res["_dispersion"].get("naive") or {}).get("worstPct"),
        }

    synth = load_synth()
    res["_transfer"] = transfer_table(res, synth)
    res["_gates"] = gate_check(res, synth)
    res["_rows"] = {"detection": drows, "panels": pfigs, "panelRows": prows,
                    "landmarks": lrows, "comparisons": crows}
    return res


def write_outputs(res, run):
    OUT_DIR.mkdir(exist_ok=True)
    rows = res.get("_rows") or {}
    for name, data in (("fields", rows.get("landmarks")),
                       ("comparisons", rows.get("comparisons")),
                       ("panels", rows.get("panelRows")),
                       ("detection", rows.get("detection"))):
        if not data:
            continue
        keys = sorted({k for r in data for k in r})
        with open(OUT_DIR / f"{name}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in data:
                w.writerow({k: ("" if r.get(k) is NA else r.get(k)) for k in keys})
    summary = {k: v for k, v in res.items() if not k.startswith("_rows")}
    summary["run"] = run
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))


# ============================================================ --power
def achievable_n():
    """What the WORKLIST ACTUALLY YIELDS, per tier and per split.

    The plan used to state its targets (>=120 LOCK panels, >=150 figures, ~290 arm-values)
    without ever checking them against the sample that exists. They are not all reachable.
    This table is computed from `worklist.json` and the canonical split so the gate table
    in sec.4 can be written against the achievable N rather than the wished-for one, and so
    the arithmetic is re-runnable when the worklist changes.

    UNITS ARE NOT INTERCHANGEABLE and the columns are deliberately separate:
      figures    -- the unit for Tier D (detection, caption association)
      P-panels   -- the unit for Tier P (decomposition, silent mislabel). Counted as the
                    caption's letter count, which is what the annotator will draw.
      E-panels   -- the unit for Tier E discrete metrics (chart type, dispersion type):
                    only panels that carry a historical coded reading.
      comparisons-- the unit for the end-to-end golden diff and sign flips.
      arm-values -- the unit for DISPERSION (2 per comparison). There are twice as many of
                    these as comparisons, so the dispersion channel is better powered than
                    the sign-flip channel on the same sample. Never quote one N for both.
    """
    wl = HERE / "worklist.json"
    if not wl.exists():
        print("  (worklist.json not present -- achievable-N table skipped)\n")
        return {}
    items = json.loads(wl.read_text())["items"]
    budget = json.loads(wl.read_text()).get("budget") or {}
    print("ACHIEVABLE N -- what the worklist actually yields (ANALYSIS-PLAN sec.4.0)\n")
    print(f"  {'scope':<20}{'hours':>7}{'figures':>9}{'articles':>10}{'P-panels':>10}"
          f"{'E-panels':>10}{'comps':>8}{'arm-values':>12}")
    out = {}
    for cut in (1, 2, 3):
        ti = [i for i in items if (i.get("tier") or 9) <= cut]
        hrs = sum((budget.get(str(t)) or {}).get("hours_total", 0) for t in range(1, cut + 1))
        for sp in ("dev", "lock", "all"):
            g = [i for i in ti if sp == "all" or split_of(i["article"]) == sp]
            rec = {
                "figures": len(g),
                "articles": len({canonical_article(i["article"]) for i in g}),
                "panelsP": sum(i.get("caption_letter_count") or 0 for i in g),
                "panelsE": sum(i.get("n_coded_panels") or 0 for i in g),
                "comparisons": sum(i.get("n_coded_comparisons") or 0 for i in g),
            }
            rec["armValues"] = 2 * rec["comparisons"]
            out[f"tiers1-{cut}/{sp}"] = rec
            print(f"  T1-{cut} {sp:<15}{(f'{hrs:.1f}' if sp=='all' else ''):>7}"
                  f"{rec['figures']:>9}{rec['articles']:>10}{rec['panelsP']:>10}"
                  f"{rec['panelsE']:>10}{rec['comparisons']:>8}{rec['armValues']:>12}")
        print()
    L = out["tiers1-3/lock"]
    print("  WHAT IS AND IS NOT ESTABLISHABLE AT THE FULL-WORKLIST LOCK SET")
    print(f"  (LOCK = {L['figures']} figures / {L['articles']} articles / "
          f"{L['panelsP']} P-panels / {L['panelsE']} E-panels / "
          f"{L['comparisons']} comparisons / {L['armValues']} arm-values)\n")
    rows = [
        ("P: silent mislabel 0 events, UB <= 2.5%", "P-panels", L["panelsP"], 120,
         100 * rule_of_three(L["panelsP"])),
        ("E: arm-name error 0 events, UB <= 1.0%", "arm-values", L["armValues"], 300,
         100 * rule_of_three(L["armValues"])),
        ("E: sign flips 0, UB <= 2.5%", "comparisons", L["comparisons"], 120,
         100 * rule_of_three(L["comparisons"])),
        ("E: sign flips 0, UB <= 5.0%", "comparisons", L["comparisons"], 60,
         100 * rule_of_three(L["comparisons"])),
        ("E (tier target): >= 120 coded panels", "E-panels", L["panelsE"], 120, NA),
    ]
    print(f"  {'claim':<44}{'unit':<13}{'have':>6}{'need':>6}  verdict")
    for name, unit, have, need, ub in rows:
        ok = have >= need
        extra = f"  (achieved UB {ub:.2f}%)" if ub is not NA else ""
        print(f"  {name:<44}{unit:<13}{have:>6}{need:>6}  "
              f"{'ESTABLISHABLE' if ok else 'NOT ESTABLISHABLE -- descriptive only'}{extra}")
    print()
    return out


def power_table():
    achievable_n()
    print("SAMPLE SIZE -- what N buys what precision (ANALYSIS-PLAN sec.4)\n")
    print("  Wilson 95% CI half-width (pp) for an observed proportion")
    print(f"    {'n':>5}" + "".join(f"{p:>9}" for p in (0.80, 0.90, 0.95, 0.98, 1.00)))
    for n in (30, 50, 60, 98, 120, 150, 180, 200, 220, 264):
        row = f"    {n:>5}"
        for pp in (0.80, 0.90, 0.95, 0.98, 1.00):
            lo, hi = wilson(round(pp * n), n)
            row += f"{100*(hi-lo)/2:>9.1f}"
        print(row)
    print("\n  Zero-event outcomes (silent mislabel, arm-name error, sign flip)")
    print(f"    {'n':>5}{'95% UB (rule of three)':>26}")
    for n in (30, 60, 98, 120, 150, 180, 220, 264):
        print(f"    {n:>5}{100*rule_of_three(n):>25.2f}%")
    print("\n  Smallest transfer gap detectable at 80% power")
    for label, p1, n1, n2s in (
            ("panel exact count (fig)", 0.951, 41, (40, 55, 80, 100)),
            ("panels IoU >= 0.9", 0.881, 159, (120, 150, 180, 200)),
            ("panel label accuracy", 0.9999, 159, (120, 150, 180, 200)),
            ("chart-type accuracy", 0.9999, 80, (60, 98, 120)),
            ("series mark accuracy", 0.9999, 495, (150, 220, 300))):
        for n2 in n2s:
            d = detectable_drop(p1, n1, n2)
            print(f"    {label:<26} synth n={n1:<5} real n={n2:<5} -> "
                  f"{'n/a' if d is NA else f'{100*d:5.1f} pp'}")
    print("\n  Grubbs sigma_M/sigma_G: 95% CI multiplier on the SD scale (ratio = 1.0)")
    for n in (30, 50, 98, 150, 220):
        lo, hi = sd_ratio_ci(n, 1.0)
        print(f"    n={n:>4}  [{lo:.2f}, {hi:.2f}]")
    print("\n  Bland-Altman: 95% CI half-width on a limit of agreement, as x sd_diff")
    for n in (30, 50, 98, 150, 220):
        print(f"    n={n:>4}  +/-{1.959964*math.sqrt(1/n + 1.959964**2/(2*(n-1))):.3f}")
    print("\n  Clustering design effect (planning only; inference uses the article-level")
    print("  cluster bootstrap that `collect()` actually calls -- see the CI provenance")
    print("  block at the foot of every report)")
    for m, icc in ((2.28, 0.3), (2.28, 0.5), (2.24, 0.4), (2.24, 0.6)):
        deff = 1 + (m - 1) * icc
        print(f"    mbar={m}, ICC={icc}: DEFF={deff:.2f} -> 98 panels ~ {98/deff:.0f} eff;"
              f" 220 bars ~ {220/deff:.0f} eff")


# ============================================================ --selftest
def _mk_gt(fid, article, npanels=3, seed=0):
    rng = random.Random(seed)
    letters = [chr(ord("A") + i) for i in range(npanels)]
    panels = []
    for i, L in enumerate(letters):
        x = 20 + i * 200
        cal = {"calPixels": {"x1": {"px": x + 10, "py": 300}, "x2": {"px": x + 150, "py": 300},
                             "y1": {"px": x + 10, "py": 300}, "y2": {"px": x + 10, "py": 40}},
               "calVals": {"x1": "0", "x2": "1", "y1": "0", "y2": "100",
                           "logX": False, "logY": False}}
        lms = []
        for j, sid in enumerate(("ctl", "int")):
            top = 300 - (120 + 40 * j + rng.randint(0, 20))
            cap = top - (18 + 12 * j)
            lms.append({"landmarkId": f"g0|{sid}", "groupId": "g0", "seriesId": sid,
                        "kind": "bar", "n": 10,
                        "centralPx": {"px": x + 40 + 40 * j, "py": top},
                        "dispersionPx": {"px": x + 40 + 40 * j, "py": cap}})
        panels.append({
            "index": i, "label": L, "contentType": "bar", "chartType": "bar",
            "bbox": {"x": x, "y": 20, "width": 180, "height": 300},
            "dispersionType": "SEM", "dispersionTypeSource": "caption",
            "calibration": cal, "sigMarkersOverCaps": bool(i % 2),
            "series": [{"seriesId": "ctl", "label": "Control", "role": "control"},
                       {"seriesId": "int", "label": "Enriched", "role": "intervention"}],
            "groups": [{"groupId": "g0", "label": "Probe"}],
            "landmarks": lms,
        })
    cap = "Figure 1. Test. " + " ".join(f"({L}) panel {L}." for L in letters)
    return {
        "schemaVersion": 1, "id": fid, "article": article, "pdf": {"page": 1, "dpi": 600},
        "durationSec": 300,
        "detection": {"pageWidth": 2000, "pageHeight": 2600,
                      "figureBbox": {"x": 100, "y": 200, "width": 800, "height": 600},
                      "captionText": cap},
        "caption": cap, "expectedLetters": letters, "nPanels": npanels,
        "layoutClass": "guillotine", "labelPlacement": "inside-tl",
        "gutter": {"measuredPx": 20, "bucket": "medium"}, "origin": "flattened-bitmap",
        "panels": panels,
    }


def _perfect_pred(gt):
    import copy
    return {
        "id": gt["id"], "confidence": 0.95, "abstain": False,
        "detection": {"figureBbox": dict(gt["detection"]["figureBbox"]),
                      "captionText": gt["detection"]["captionText"]},
        "panels": [{
            "label": p["label"], "bbox": dict(p["bbox"]), "conf": 0.95,
            "chartType": p["chartType"], "dispersionType": p["dispersionType"],
            "dispersionFlags": [], "calibration": copy.deepcopy(p["calibration"]),
            "series": copy.deepcopy(p["series"]), "groups": copy.deepcopy(p["groups"]),
            "landmarks": copy.deepcopy(p["landmarks"]),
        } for p in gt["panels"]],
    }


def _mutate(preds, kind, rng):
    import copy
    out = copy.deepcopy(preds)
    ids = sorted(out)
    for cid in ids:
        r = out[cid]
        pans = r["panels"]
        if kind.startswith("shift"):
            d = int(kind[5:])
            for p in pans:
                p["bbox"]["x"] += d
                p["bbox"]["y"] += d
        elif kind == "swaplabels" and len(pans) >= 2:
            i, j = rng.sample(range(len(pans)), 2)
            pans[i]["label"], pans[j]["label"] = pans[j]["label"], pans[i]["label"]
        elif kind == "droppanel" and len(pans) >= 2:
            pans.pop(rng.randrange(len(pans)))
        elif kind == "spurious":
            b = pans[0]["bbox"]
            pans.append({"label": "Z", "conf": 0.4, "bbox": {
                "x": b["x"] + 3, "y": b["y"] + 3,
                "width": max(8, b["width"] // 6), "height": max(8, b["height"] // 6)}})
        elif kind == "abstain-all":
            r["abstain"] = True
            r["confidence"] = 0.1
        elif kind == "figshift":
            r["detection"]["figureBbox"]["x"] += 200
        elif kind == "capswap":
            r["detection"]["captionText"] = "Figure 9. A completely different caption."
        elif kind == "charttype":
            for p in pans:
                p["chartType"] = "micrograph"      # also a PRIORITY flip: high -> none
        elif kind == "semassd":
            for p in pans:
                p["dispersionType"] = "SD"
        elif kind == "armswap":
            # perfect geometry, perfect values, swapped arm identity: the silent class
            for p in pans:
                for lm in p["landmarks"]:
                    lm["seriesId"] = "int" if lm["seriesId"] == "ctl" else "ctl"
                    lm["landmarkId"] = f"g0|{lm['seriesId']}"
        elif kind.startswith("dispscale"):
            k = float(kind[9:])
            for p in pans:
                for lm in p["landmarks"]:
                    c = lm["centralPx"]["py"]
                    lm["dispersionPx"]["py"] = c - (c - lm["dispersionPx"]["py"]) * k
        elif kind == "dispnoise":
            for p in pans:
                for lm in p["landmarks"]:
                    lm["dispersionPx"]["py"] += rng.gauss(0, 3)
    return out


def _score(gts, preds, coded=None, repeats=None, abstain_at=0.5):
    return collect(dict(gts), dict(preds), coded or [], repeats or {}, abstain_at, "all")


def run_selftest():
    print("SELFTEST -- each injected failure must move the metric that OWNS it\n")
    fails = []
    # The suite calls `collect()` about thirty times and each call now runs ~25 cluster
    # bootstraps. At the production B = 10000 that is minutes of resampling to assert
    # things the resampling does not affect: every test here asserts that a metric MOVES,
    # or that an interval is CLUSTERED, never how wide it is. So the suite runs at a small
    # B, and S0 below pins the production default so this shortcut cannot silently become
    # the shipped setting.
    global BOOTSTRAP_B
    production_B = BOOTSTRAP_B
    BOOTSTRAP_B = 200
    print(f"  (bootstrap B lowered to {BOOTSTRAP_B} for speed; production default is "
          f"{production_B})\n")

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name:<58} {detail}")
        if not cond:
            fails.append(name)

    arts = ["Art1", "Art2", "Art3", "Art4", "Art5", "Art6"]
    gts = {}
    for i, a in enumerate(arts):
        for k in range(3):
            fid = f"{a}_fig{k+1}"
            gts[fid] = _mk_gt(fid, a, npanels=3, seed=i * 10 + k)
    base = {k: _perfect_pred(g) for k, g in gts.items()}
    rng = random.Random(7)

    # -------- coded reference (the third reading, D) --------
    def make_coded(jitter_log, seed=3):
        r = random.Random(seed)
        rows = []
        for fid, g in gts.items():
            for p in g["panels"]:
                vals = {}
                for lm in p["landmarks"]:
                    c, d, _, _ = landmark_values(p, lm)
                    vals[lm["landmarkId"]] = (c, as_sd(d, "SEM", lm["n"]))
                rows.append({
                    "article": g["article"], "comparisonId": f"{fid}_{p['label']}_1",
                    "figureId": fid, "panelLetter": p["label"], "isOracle": True,
                    "direction": "higher better", "vifMultiarm": 1.0,
                    "controlLandmarkId": "g0|ctl", "intervLandmarkId": "g0|int",
                    "control": {"mean": vals["g0|ctl"][0],
                                "sd": vals["g0|ctl"][1] * math.exp(r.gauss(0, jitter_log)),
                                "n": 10, "roundingQuantumPct": 0.05},
                    "interv": {"mean": vals["g0|int"][0],
                               "sd": vals["g0|int"][1] * math.exp(r.gauss(0, jitter_log)),
                               "n": 10, "roundingQuantumPct": 0.05},
                })
        return rows

    coded = make_coded(0.05)

    # ---- P1 perfect
    r0 = _score(gts, base, coded)
    P = r0["panels"]
    check("P1  perfect prediction scores perfectly",
          P["iouMedian"] == 1.0 and P["countAcc"] == 1.0
          and P["labelAccLocalised"] == 1.0 and P["silentMislabelCount"] == 0,
          f"medIoU {P['iouMedian']:.3f} count {P['countAcc']:.0%} "
          f"label {P['labelAccLocalised']:.0%}")

    # ---- P2 box shift
    prev, mono, line = 1.0, True, []
    for d in (5, 20, 60):
        a = _score(gts, _mutate(base, f"shift{d}", rng))["panels"]
        line.append(f"{d}px->{a['iouMedian']:.3f}")
        mono = mono and a["iouMedian"] < prev
        prev = a["iouMedian"]
    check("P2  IoU degrades monotonically with a box shift", mono, "  ".join(line))
    a = _score(gts, _mutate(base, "shift5", rng))["panels"]
    check("P2b 5px shift caught by IoU, NOT by count",
          a["iouMedian"] < 1.0 and a["countAcc"] == 1.0,
          f"medIoU {a['iouMedian']:.3f}, count {a['countAcc']:.0%}")

    # ---- P3 THE CATASTROPHIC CLASS
    sw = _score(gts, _mutate(base, "swaplabels", rng))["panels"]
    check("P3  LABEL SWAP -> assignment falls, geometry UNTOUCHED",
          sw["iouMedian"] == 1.0 and sw["countAcc"] == 1.0
          and sw["labelAccLocalised"] < 1.0 and sw["silentMislabelCount"] == 2 * len(gts),
          f"label {sw['labelAccLocalised']:.0%}, {sw['silentMislabelCount']} silent "
          f"mislabels, medIoU {sw['iouMedian']:.3f}, count {sw['countAcc']:.0%}")

    # ---- P4/P5
    dp = _score(gts, _mutate(base, "droppanel", rng))["panels"]
    check("P4  dropped panel -> count + recall fall",
          dp["countAcc"] < 1.0 and dp["missed"] == len(gts) and dp["pct50"] < 1.0,
          f"count {dp['countAcc']:.0%}, {dp['missed']} never matched, "
          f">=0.5 {dp['pct50']:.0%}")
    sp = _score(gts, _mutate(base, "spurious", rng))["panels"]
    check("P5  spurious box -> FPs + count, IoU intact",
          sp["countAcc"] == 0.0 and sp["falsePositives"] == len(gts)
          and sp["iouMedian"] == 1.0,
          f"count {sp['countAcc']:.0%}, {sp['falsePositives']} FPs, "
          f"medIoU {sp['iouMedian']:.3f}")

    # ---- P6/P7 abstention economics
    ab = _score(gts, _mutate(base, "abstain-all", rng))["panels"]["abstention"]
    check("P6  abstaining on everything while right is PENALISED",
          ab["coverage"] == 0.0 and ab["net"] < 0 and ab["precision"] == 0.0,
          f"coverage {ab['coverage']:.0%}, net {ab['net']:+d}, prec {ab['precision']:.2f}")
    bad = _mutate(base, "droppanel", random.Random(11))
    mixed = {}
    for i, cid in enumerate(sorted(gts)):
        if i % 2 == 0:
            r = dict(bad[cid]); r["abstain"] = True; mixed[cid] = r
        else:
            mixed[cid] = base[cid]
    ab = _score(gts, mixed)["panels"]["abstention"]
    check("P7  calibrated abstention flags the wrong ones only",
          ab["precision"] == 1.0 and ab["recall"] == 1.0 and ab["net"] > 0
          and ab["errorRateAnswered"] == 0.0,
          f"prec {ab['precision']:.2f} rec {ab['recall']:.2f} net {ab['net']:+d}")

    # ---- D1/D2 detection
    d0 = _score(gts, base)["detection"]
    d1 = _score(gts, _mutate(base, "figshift", rng))["detection"]
    check("D1  figure bbox shift -> detection IoU falls, caption intact",
          d0["iouMedian"] == 1.0 and d1["iouMedian"] < 1.0
          and d1["captionAccuracy"] == 1.0,
          f"IoU {d0['iouMedian']:.3f} -> {d1['iouMedian']:.3f}, "
          f"caption {d1['captionAccuracy']:.0%}")
    d2 = _score(gts, _mutate(base, "capswap", rng))["detection"]
    check("D2  wrong caption -> caption accuracy falls, bbox IoU intact",
          d2["captionAccuracy"] == 0.0 and d2["iouMedian"] == 1.0
          and d2["letterAccuracy"] == 0.0,
          f"caption {d2['captionAccuracy']:.0%}, letters {d2['letterAccuracy']:.0%}, "
          f"IoU {d2['iouMedian']:.3f}")

    # ---- E1 classification + priority flip
    e0 = _score(gts, base, coded)["extraction"]
    e1 = _score(gts, _mutate(base, "charttype", rng), coded)["extraction"]
    check("E1  chart-type flip -> accuracy AND priority-flip rate move",
          e0["chartTypeAccuracy"] == 1.0 and e0["priorityFlipRate"] == 0.0
          and e1["chartTypeAccuracy"] == 0.0 and e1["priorityFlipRate"] == 1.0,
          f"acc {e0['chartTypeAccuracy']:.0%}->{e1['chartTypeAccuracy']:.0%}, "
          f"flip {e0['priorityFlipRate']:.0%}->{e1['priorityFlipRate']:.0%}")

    # ---- E2 SEM read as SD
    e2r = _score(gts, _mutate(base, "semassd", rng), coded)
    e2 = e2r["extraction"]
    sd_gap = med([abs(r["sdM"] - r["sdG"]) / r["sdG"] for r in e2r["_rows"]["landmarks"]
                  if r["sdG"] and r["sdM"]])
    check("E2  SEM read as SD -> type agreement falls, sqrt(n) blow-up visible",
          e2["dispTypeAccuracy"] == 0.0 and sd_gap > 0.6,
          f"type acc {e2['dispTypeAccuracy']:.0%}, median SD gap {sd_gap:.1%} "
          f"(expected 1-1/sqrt(10) = {1-1/math.sqrt(10):.1%}: the machine reports the "
          f"raw cap as SD where the truth is SEM)")

    # ---- E3 ARM SWAP: the second silent class
    e3r = _score(gts, _mutate(base, "armswap", rng), coded)
    e3 = e3r["extraction"]
    lm3 = e3r["_rows"]["landmarks"]
    cen3 = med([r["centralPct"] for r in lm3 if r["centralPct"] is not NA])
    dis3 = med([r["dispPct"] for r in lm3 if r["dispPct"] is not NA])
    p3 = _score(gts, _mutate(base, "armswap", rng), coded)["panels"]
    check("E3  ARM SWAP -> arm error + sign flips rise; geometry AND magnitudes blind",
          e3["armErrorRate"] == 1.0 and e3["armNameErrorRate"] == 1.0
          and e3["signFlipRate"] == 1.0
          and p3["iouMedian"] == 1.0 and p3["silentMislabelCount"] == 0
          and (cen3 is NA or cen3 < 1e-6),
          f"armErr {e3['armErrorRate']:.0%}, nameErr {e3['armNameErrorRate']:.0%}, "
          f"signflips {e3['signFlipRate']:.0%}, panel medIoU {p3['iouMedian']:.3f}, "
          f"central {f(cen3,'{:.2e}')}, disp {f(dis3,'{:.2e}')}")

    # ---- E4 dispersion scale error
    e4 = _score(gts, _mutate(base, "dispscale1.2", rng), coded)["_dispersion"]
    ba4 = e4["blandAltman_MG"]
    check("E4  dispersion x1.2 -> BA bias moves ~+20%, LoA stay tight, central intact",
          ba4 and 15 < ba4["biasPct"] < 25 and (ba4["loaHiPct"] - ba4["loaLoPct"]) < 10
          and (e4["central"]["medianPct"] is NA or e4["central"]["medianPct"] < 1e-6),
          f"bias {ba4['biasPct']:+.1f}%, LoA [{ba4['loaLoPct']:+.1f},{ba4['loaHiPct']:+.1f}], "
          f"central {f(e4['central']['medianPct'],'{:.2e}')}")

    # ---- E5 dispersion noise
    e5 = _score(gts, _mutate(base, "dispnoise", random.Random(5)), coded)["_dispersion"]
    ba5 = e5["blandAltman_MG"]
    check("E5  dispersion noise -> LoA widen, bias ~0",
          ba5 and abs(ba5["biasPct"]) < 12 and (ba5["loaHiPct"] - ba5["loaLoPct"])
          > (ba4["loaHiPct"] - ba4["loaLoPct"]),
          f"bias {ba5['biasPct']:+.1f}%, LoA width {ba5['loaHiPct']-ba5['loaLoPct']:.1f}pp "
          f"(vs {ba4['loaHiPct']-ba4['loaLoPct']:.1f} for the pure scale error)")

    # ---- D3 THE POINT OF THE WHOLE DESIGN -----------------------------------
    # Machine is EXACTLY right. Human (G) jitters by 1px-equivalent. Historical (D)
    # jitters independently. A naive M-vs-G number blames the machine for the human's
    # jitter; Grubbs does not.
    jit = random.Random(29)
    gts_j = json.loads(json.dumps(gts))          # deep copy
    truth = {}
    for fid, g in gts_j.items():
        for pn in g["panels"]:
            for lm in pn["landmarks"]:
                truth[(fid, pn["label"], lm["landmarkId"])] = lm["dispersionPx"]["py"]
                lm["dispersionPx"]["py"] += jit.choice([-1.5, -1.0, 1.0, 1.5])   # human jitter
    machine = {}
    for fid, g in gts.items():                    # predictions from the UNJITTERED truth
        machine[fid] = _perfect_pred(g)
    coded_ind = make_coded(0.045, seed=99)        # third reading, independent jitter
    rj = _score(gts_j, machine, coded_ind)
    naive = rj["_dispersion"]["naive"]["medianPct"]
    gr = rj["_dispersion"]["grubbs"]
    ok = gr.get("n") and gr["sigma_M_pct"] is not NA
    check("D3  HUMAN-JITTER CONTROL: exact machine, jittering human",
          ok and naive > 1.5 and abs(gr["sigma_M_pct"]) < naive
          and gr["sigma_G_pct"] > abs(gr["sigma_M_pct"]),
          f"naive M-vs-G disagreement {naive:.2f}% (would be reported as 'machine error') "
          f"BUT Grubbs sigma_M {gr['sigma_M_pct']:+.2f}% vs sigma_G {gr['sigma_G_pct']:+.2f}%")

    # ---- D4 Grubbs recovers known variances
    r = random.Random(11)
    n = 6000                      # the SMALLEST variance sets the requirement: at n=400
    sD, sG, sM = 0.09, 0.06, 0.03  # the sigma_M estimate is still +/-100% (see --power)
    T = [r.gauss(0, 0.5) for _ in range(n)]
    A = [t + r.gauss(0, sD) for t in T]
    B = [t + r.gauss(0, sG) for t in T]
    C = [t + r.gauss(0, sM) for t in T]
    gg = grubbs_three(A, B, C)
    est = (math.sqrt(max(gg["var_a"], 0)), math.sqrt(max(gg["var_b"], 0)),
           math.sqrt(max(gg["var_c"], 0)))
    check("D4  Grubbs recovers known sigma_D / sigma_G / sigma_M with no oracle",
          all(abs(e - t) < 0.25 * t for e, t in zip(est, (sD, sG, sM))),
          f"true ({sD},{sG},{sM}) -> est ({est[0]:.3f},{est[1]:.3f},{est[2]:.3f})")

    # ---- D5 shared-person covariance c_DG inflates sigma_M (only HALF the story)
    c_true = 0.0016                                   # cov(e_D, e_G)
    shared = [r.gauss(0, math.sqrt(c_true)) for _ in range(n)]
    A2 = [t + s + r.gauss(0, sD) for t, s in zip(T, shared)]
    B2 = [t + s + r.gauss(0, sG) for t, s in zip(T, shared)]
    g2 = grubbs_three(A2, B2, C)
    infl = g2["var_c"] - gg["var_c"]
    check("D5  c_DG alone INFLATES sigma_M (the half of the story sec.1.3 used to tell)",
          infl > 0.4 * c_true,
          f"cov injected {c_true:.4f} -> var_M rose by {infl:.4f} "
          f"({math.sqrt(max(g2['var_c'],0)):.3f} vs {est[2]:.3f})")

    # ---- D5b THE ANTI-CONSERVATIVE CASE. This is the test that keeps the failure mode
    #      visible, and it is the reason "conservative against the machine" was struck
    #      from the plan (amendment A2).
    #
    #      The full algebra with correlated errors is
    #          E[sigma_M^2 (Grubbs)] = sigma_M^2 + c_DG - c_DM - c_GM
    #      The shipped derivation kept only `+ c_DG` and concluded the estimate could
    #      only ever be too LARGE. But sec.7 lists "machine and human both misread the
    #      same ambiguous cap the same way" as a live threat, and a cap hidden behind a
    #      significance asterisk is a difficulty shared by EVERY reader of that panel.
    #      That is a positive c_DM and c_GM, and they enter with a MINUS sign.
    #
    #      Here a single shared "hard panel" component enters all three readings. The
    #      machine's true sigma_M is 0.10; Grubbs is asked to recover it. If the estimate
    #      lands materially BELOW 0.10, the guarantee is false in the dangerous direction
    #      -- the report would understate the machine's error and call it conservative.
    r2 = random.Random(4242)
    sD3, sG3, sM3 = 0.09, 0.06, 0.10
    c_all = 0.0064                       # a difficulty component shared by D, G AND M
    T3 = [r2.gauss(0, 0.5) for _ in range(n)]
    hard = [r2.gauss(0, math.sqrt(c_all)) for _ in range(n)]
    A3 = [t + h + r2.gauss(0, math.sqrt(max(sD3**2 - c_all, 1e-9))) for t, h in zip(T3, hard)]
    B3 = [t + h + r2.gauss(0, math.sqrt(max(sG3**2 - c_all, 1e-9))) for t, h in zip(T3, hard)]
    C3 = [t + h + r2.gauss(0, math.sqrt(max(sM3**2 - c_all, 1e-9))) for t, h in zip(T3, hard)]
    g3 = grubbs_three(A3, B3, C3)
    est_M = math.sqrt(max(g3["var_c"], 0))
    # the oracle stratum sees the same data with a TRUE reference, so it cannot be fooled
    oracle_M = statistics.stdev([c - t for c, t in zip(C3, T3)])
    check("D5b ANTI-CONSERVATIVE: shared difficulty makes Grubbs UNDERSTATE sigma_M",
          est_M < 0.85 * sM3 and abs(oracle_M - sM3) < 0.15 * sM3,
          f"true sigma_M {sM3:.3f} -> Grubbs {est_M:.3f} "
          f"({100*(est_M/sM3 - 1):+.0f}%, i.e. TOO SMALL, so 'conservative against the "
          f"machine' is FALSE here) while the ORACLE estimate recovers {oracle_M:.3f}. "
          f"Grubbs-vs-oracle disagreement is the detector for this confound (sec.1.3)")

    # ---- D6 coded print-precision cancels out of sigma_M (and only inflates sigma_D)
    q = 0.05                                   # +/-5% uniform rounding on the D reading
    Aq = [x + r.uniform(-q, q) for x in A]
    gq = grubbs_three(Aq, B, C)
    dM = abs(math.sqrt(max(gq["var_c"], 0)) - est[2]) / sM
    dD = (math.sqrt(max(gq["var_a"], 0)) - est[0]) / sD
    check("D6  coded rounding inflates sigma_D but CANCELS out of sigma_M",
          dM < 0.20 and dD > 0.02,
          f"sigma_M moved {100*dM:.1f}% (cancels), sigma_D moved {100*dD:+.1f}% "
          f"(absorbs the quantum) -- so coarse coded rows need NOT be dropped from the "
          f"machine-variance estimate")

    # ---- X1/X2 robustness
    missing = {k: base[k] for i, k in enumerate(sorted(gts)) if i % 3}
    rm = _score(gts, missing, coded)
    nmiss = len(gts) - len(missing)
    check("X1  a missing prediction is a total miss, not a crash",
          rm["panels"]["nFigures"] == len(gts)
          and rm["panels"]["pct50"] < 1.0 and rm["panels"]["countAcc"] < 1.0
          and rm["panels"]["missed"] == nmiss * 3
          and sum(1 for fg in rm["_rows"]["panels"] if fg["noPrediction"]) == nmiss,
          f"{nmiss} figures had no prediction -> {rm['panels']['missed']} panels never "
          f"matched, >=0.5 {rm['panels']['pct50']:.0%}, count {rm['panels']['countAcc']:.0%} "
          f"(median IoU stays 1.000 by construction -- most panels are still perfect)")
    empty = collect({}, {}, [], {}, 0.5, "all")
    check("X2  an empty store degrades gracefully and says so",
          empty.get("panels") is None and empty.get("detection") is None
          and isinstance(empty.get("_gates"), list)
          and all(g[4] == "NO DATA" for g in empty["_gates"]),
          f"{len(empty['_gates'])} gates all report NO DATA")

    # ---- gate wiring: the label swap must actually FAIL its gate
    gsw = gate_check(_score(gts, _mutate(base, "swaplabels", rng), coded), load_synth())
    sm = next((g for g in gsw if g[0].startswith("P: silent")), None)
    check("G1  a label swap FAILS the pre-committed silent-mislabel gate",
          sm is not None and sm[4] == "FAIL",
          f"gate '{sm[0]}' -> {sm[4]} at {f(sm[1],'{:.3f}')}" if sm else "gate missing")
    garm = gate_check(_score(gts, _mutate(base, "armswap", rng), coded), load_synth())
    an = next((g for g in garm if g[0].startswith("E: arm-name")), None)
    sf = next((g for g in garm if g[0].startswith("E: sign-flip")), None)
    check("G2  an arm swap FAILS the arm-name and sign-flip gates",
          an is not None and an[4] == "FAIL" and sf is not None and sf[4] == "FAIL",
          f"arm-name {an[4] if an else '?'} / sign-flip {sf[4] if sf else '?'}")

    # ---- split determinism, over EVERY permanent-DEV entry and BOTH spellings.
    #      The shipped test checked two of the four names in their canonical spelling only,
    #      which is exactly why `Garcia-Capdevila2009` sat in LOCK: PERMANENT_DEV held
    #      `GarciaCapdevila2009` while the coded reference wrote the hyphenated form, and
    #      an exact `in` test does not notice (amendment A8).
    s1 = {a: split_of(a) for a in arts}
    s2 = {a: split_of(a) for a in arts}
    spellings = []
    for a in sorted(PERMANENT_DEV):
        variants = {a, a.replace("-", ""), a.lower(), a.upper(),
                    a.replace("-", " "), a.replace("-", "_")}
        # inject the hyphenated form for the names the corpus actually hyphenates
        if a == "GarciaCapdevila2009":
            variants |= {"Garcia-Capdevila2009", "garcia capdevila2009"}
        for v in sorted(variants):
            spellings.append((v, split_of(v)))
    bad_perm = [v for v, s in spellings if s != "dev"]
    check("S1  DEV/LOCK split is deterministic",
          s1 == s2, f"{len(s1)} articles, two identical draws")
    check("S1b EVERY permanent-DEV article is DEV in EVERY spelling",
          not bad_perm,
          f"{len(spellings)} spellings of {len(PERMANENT_DEV)} articles all -> dev"
          if not bad_perm else f"LEAKED INTO LOCK: {bad_perm}")
    check("S1c two spellings of the same article get the SAME split",
          all(split_of(x) == split_of(y) for x, y in
              (("Garcia-Capdevila2009", "GarciaCapdevila2009"),
               ("Sampedro-Piquero2018", "SampedroPiquero2018"),
               ("Mora-Gallegos2015", "MoraGallegos2015"),
               ("Del-Arco2007", "DelArco2007"),
               ("Mesa-Gresa2021", "mesa gresa 2021"))),
          "hyphen / space / case never changes the bucket")
    check("S1d canonical_article strips typography, not identity",
          canonical_article("Garcia-Capdevila2009") == "garciacapdevila2009"
          and canonical_article("Del-Arco2007") != canonical_article("DelArco2008"),
          f"'Garcia-Capdevila2009' -> '{canonical_article('Garcia-Capdevila2009')}'")

    # ---- CI provenance: the plan says EVERY reported CI is a cluster bootstrap. Assert
    #      the code actually produces one, and that it is WIDER than the i.i.d. interval
    #      it replaced (amendment A3). A promise the code does not keep is the defect.
    rci = _score(gts, base, coded, repeats={}, abstain_at=0.5)
    cap_cb = (rci.get("detection") or {}).get("captionCI")
    cap_iid = (rci.get("detection") or {}).get("captionCI_iid")
    pan_cb = (rci.get("panels") or {}).get("silentMislabelCI")
    check("S0  the PRODUCTION bootstrap default is the pre-registered B = 10000",
          production_B == 10000, f"production B = {production_B} (sec.2.1)")
    check("S2  reported CIs are article-level cluster bootstraps, not i.i.d.",
          cap_cb is not None and cap_iid is not None and pan_cb is not None
          and cluster_bootstrap.__doc__ is not None,
          f"caption CI cluster={cap_cb} iid={cap_iid}; silent-mislabel CI={pan_cb}")

    # a deliberately clustered sample: the naive interval must be the narrower one
    clus = []
    rr = random.Random(7)
    for ai in range(12):
        p_a = 0.2 if ai % 2 else 0.9              # strong between-article clustering
        for _ in range(15):
            clus.append({"article": f"Art{ai}", "ok": rr.random() < p_a})
    lo_c, hi_c = cb_rate(clus, lambda r: r["ok"])
    k = sum(1 for r in clus if r["ok"])
    lo_i, hi_i = wilson(k, len(clus))
    check("S2b the cluster bootstrap is WIDER than the i.i.d. interval it replaced",
          (hi_c - lo_c) > 1.3 * (hi_i - lo_i),
          f"cluster [{lo_c:.3f},{hi_c:.3f}] width {hi_c-lo_c:.3f} vs "
          f"Wilson [{lo_i:.3f},{hi_i:.3f}] width {hi_i-lo_i:.3f} "
          f"= {(hi_c-lo_c)/(hi_i-lo_i):.2f}x")

    # ---- R_floor units (amendment A7). Two readings of the SAME quality must give ~1.0.
    rf = random.Random(31)
    sg = 0.05
    rep_pairs = [(math.exp(rf.gauss(0, sg)), math.exp(rf.gauss(0, sg))) for _ in range(400)]
    lrows_rf = [{"article": f"A{i%20}", "dispPct": NA, "centralPct": NA,
                 "sdM": math.exp(rf.gauss(0, sg)), "sdG": math.exp(rf.gauss(0, sg)),
                 "capLenPx": None} for i in range(400)]
    nf_eq = dispersion_analysis(lrows_rf, [], rep_pairs)["noiseFloor"]
    lrows_bad = [{"article": f"A{i%20}", "dispPct": NA, "centralPct": NA,
                  "sdM": math.exp(rf.gauss(0, 3 * sg)), "sdG": math.exp(rf.gauss(0, sg)),
                  "capLenPx": None} for i in range(400)]
    nf_bad = dispersion_analysis(lrows_bad, [], rep_pairs)["noiseFloor"]
    check("S3  R_floor ~ 1.0 when the machine is as good as the human's test-retest",
          0.8 < nf_eq["R_floor"] < 1.25,
          f"sigma_M == sigma_G -> R_floor {nf_eq['R_floor']:.2f} "
          f"(the shipped formula returned ~0.24 here: it divided a median-absolute by a "
          f"2.77-sigma repeatability coefficient, so the GO rule needed a 4.1x-worse "
          f"machine before it could fire)")
    check("S3b R_floor rises above 1 exactly when the machine IS worse",
          nf_bad["R_floor"] > 1.5,
          f"sigma_M = 3 x sigma_G -> R_floor {nf_bad['R_floor']:.2f}")
    grf = gate_check({"_dispersion": {"noiseFloor": nf_bad}}, load_synth())
    gr_rf = next((g for g in grf if g[0].startswith("E: R_floor")), None)
    check("S3c the sec.8.2 R_floor conjunct is wired into the gate table",
          gr_rf is not None and gr_rf[4] == "PASS",
          f"{gr_rf[0]} -> {gr_rf[4]} at {f(gr_rf[1],'{:.2f}')}" if gr_rf else "gate missing")

    BOOTSTRAP_B = production_B          # never leave the shortcut in place
    print()
    if fails:
        print(f"{len(fails)} FAILED: {', '.join(fails)}")
        return 1
    print("all selftests passed")
    return 0


# ============================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="prediction run name under pred/")
    ap.add_argument("--split-filter", default="lock", choices=("dev", "lock", "all"),
                    help="which split to score (default lock -- the headline)")
    ap.add_argument("--abstain-at", type=float, default=0.5)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--power", action="store_true")
    ap.add_argument("--split", action="store_true",
                    help="print/write the deterministic DEV/LOCK article split")
    ap.add_argument("--md", help="also write the report to this markdown file")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(run_selftest())
    if a.power:
        power_table()
        return
    if a.split:
        arts = sorted({r.get("article") for r in load_coded() if r.get("article")}
                      | {g.get("article") for g in load_gt().values() if g.get("article")})
        if not arts:
            print("no articles found (need coded/coded_reference.json or gt/); "
                  "the rule is still recomputable for any Article_ID:")
            print(f'  sha256("{SPLIT_SALT}|" + canonical_article(Article_ID))[:8] % 3 == 0'
                  f'  ->  dev')
            print("  canonical_article = lowercase, strip every non-alphanumeric char")
            print(f"  permanent DEV: {sorted(PERMANENT_DEV)}")
            return
        assign = {x: split_of(x) for x in arts}
        # Keyed by the CANONICAL article key as well, so a consumer that spells the
        # article differently (the worklist writes `GarciaCapdevila2009`, the coded
        # reference writes `Garcia-Capdevila2009`) still resolves. Three worklist
        # articles previously resolved to nothing at all.
        by_canon = {}
        for x in arts:
            by_canon.setdefault(canonical_article(x), {"split": assign[x], "spellings": []})
            by_canon[canonical_article(x)]["spellings"].append(x)
        HERE.mkdir(exist_ok=True)
        (HERE / "split.json").write_text(json.dumps(
            {"salt": SPLIT_SALT, "permanentDev": sorted(PERMANENT_DEV),
             "permanentDevCanonical": sorted(PERMANENT_DEV_CANON),
             "rule": 'sha256(SALT + "|" + canonical_article(Article_ID))[:8] % 3 == 0 -> dev',
             "canonicalisation": "lowercase, then strip every non-alphanumeric character",
             "assignment": assign, "byCanonicalKey": by_canon}, indent=2))
        n_dev = sum(1 for v in assign.values() if v == "dev")
        n_multi = sum(1 for v in by_canon.values() if len(v["spellings"]) > 1)
        print(f"{len(arts)} articles ({len(by_canon)} canonical keys, "
              f"{n_multi} with >1 spelling): {n_dev} dev / {len(arts)-n_dev} lock")
        for x in arts:
            print(f"  {assign[x]:<5} {x}")
        print(f"\n[written] {HERE/'split.json'}")
        return

    if not a.run:
        ap.error("--run is required (or use --selftest / --power / --split)")

    gts, preds = load_gt(), load_preds(a.run)
    repeats = load_gt(REPEAT_DIR)
    coded = load_coded()
    if not gts:
        print("no ground truth in gt/ -- nothing to score.")
        print("Expected: gt/<figure_id>.gt.json (see ANALYSIS-PLAN.md sec.10), or the")
        print("tool's own annotations.json anywhere under gt/ (auto-normalized).")
        return
    res = collect(gts, preds, coded, repeats, a.abstain_at, a.split_filter)
    text = report(res, a.run, a.split_filter)
    write_outputs(res, a.run)
    if a.md:
        pathlib.Path(a.md).write_text(
            "# Real-figure validation\n\n```\n" + text + "\n```\n")
        print(f"  wrote {a.md}")
    print(f"  [written] {OUT_DIR/'summary.json'} and out/*.csv")


if __name__ == "__main__":
    main()
