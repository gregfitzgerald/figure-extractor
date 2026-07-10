#!/usr/bin/env python3
"""Ground-truth scoring harness for the figure-extractor pipeline.

Scores a tool's PREDICTED figure/subfigure/caption annotations
(``annotations.json``, schema v2) against hand-corrected GROUND TRUTH
(``ground-truth.json``) for a meta-analysis figure-extraction pipeline.

Pure standard library only -- IoU matching and Levenshtein edit distance are
implemented in plain Python so the harness runs with a bare ``python3`` on any
platform.

Subcommands
-----------
  datasets   List every article dir and whether it has predicted / truth / both.
  score      Score one article dir; print report + write score-results.json.
  score-all  Score every article that has both files; per-article table + aggregate.
  gate       Regression gate: append aggregate to scores.jsonl, fail on drop.

Coordinate conventions
----------------------
Everything is compared in a normalized [0, 1] space.

  * FIGURES live in a per-page coordinate space and are only matched against GT
    figures on the SAME pageNum. Their normalized rectangle is taken from
    ``boundsNorm`` if present, else ``bounds`` divided by that page's
    width/height (from the top-level ``pages[]`` header, else metadata.json).
  * SUBFIGURES are expressed as a fraction of their PARENT FIGURE. Prefer
    ``boundsNorm``; else divide the (figure-relative, natural px) ``bounds`` by
    the parent figure's natural ``bounds`` width/height.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

DEFAULT_IOU = 0.5
# Threshold sweep for the mAP-style mean-F1 metric.
SWEEP_THRESHOLDS = [round(0.5 + 0.05 * i, 2) for i in range(9)]  # 0.5 .. 0.9
CAPTION_MISS_THRESHOLD = 0.5  # caption similarity below this counts as a miss


def projects_root(cli_value=None):
    """Resolve the projects root directory.

    Precedence: explicit CLI value, then ``$FIGURE_PROJECTS_DIR``, then
    ``$HOME/figure-extraction-projects``.
    """
    if cli_value:
        return Path(cli_value).expanduser()
    env = os.environ.get("FIGURE_PROJECTS_DIR")
    if env:
        return Path(env).expanduser()
    return Path(os.path.expanduser("~")) / "figure-extraction-projects"


# --------------------------------------------------------------------------- #
# Geometry: IoU in normalized space
# --------------------------------------------------------------------------- #

def iou(a, b):
    """Intersection-over-union of two axis-aligned rects.

    Each rect is a mapping with ``x``, ``y``, ``width``, ``height`` in the same
    coordinate space. Returns 0.0 for degenerate (non-positive area) rects.
    """
    aw, ah = a["width"], a["height"]
    bw, bh = b["width"], b["height"]
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return 0.0

    ax0, ay0 = a["x"], a["y"]
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx0, by0 = b["x"], b["y"]
    bx1, by1 = bx0 + bw, by0 + bh

    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = ix1 - ix0, iy1 - iy0
    if iw <= 0 or ih <= 0:
        return 0.0

    inter = iw * ih
    union = aw * ah + bw * bh - inter
    if union <= 0:
        return 0.0
    return inter / union


def greedy_match(pred_boxes, gt_boxes, threshold):
    """Greedy 1:1 assignment by descending IoU (deterministic).

    ``pred_boxes`` / ``gt_boxes`` are lists of normalized rects. Repeatedly take
    the highest remaining IoU pair whose IoU >= threshold.

    Returns ``(matches, unmatched_pred, unmatched_gt, overlaps)`` where:
      * ``matches`` is a list of ``(pred_idx, gt_idx, iou)`` tuples,
      * ``unmatched_pred`` / ``unmatched_gt`` are lists of indices,
      * ``overlaps`` is a list of ``(pred_idx, gt_idx, iou)`` for every pair with
        IoU > 0 (used by the mislocated error bucket).
    """
    candidates = []
    overlaps = []
    for pi, pb in enumerate(pred_boxes):
        for gi, gb in enumerate(gt_boxes):
            score = iou(pb, gb)
            if score > 0:
                overlaps.append((pi, gi, score))
            if score >= threshold:
                candidates.append((score, pi, gi))

    # Sort by IoU desc; break ties deterministically by (pred_idx, gt_idx).
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))

    matched_pred = set()
    matched_gt = set()
    matches = []
    for score, pi, gi in candidates:
        if pi in matched_pred or gi in matched_gt:
            continue
        matched_pred.add(pi)
        matched_gt.add(gi)
        matches.append((pi, gi, score))

    unmatched_pred = [i for i in range(len(pred_boxes)) if i not in matched_pred]
    unmatched_gt = [i for i in range(len(gt_boxes)) if i not in matched_gt]
    return matches, unmatched_pred, unmatched_gt, overlaps


# --------------------------------------------------------------------------- #
# Text similarity
# --------------------------------------------------------------------------- #

def edit_distance(a, b):
    """Levenshtein edit distance between two strings (pure Python, O(len_a*len_b))."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(
                prev[j] + 1,        # deletion
                cur[j - 1] + 1,     # insertion
                prev[j - 1] + cost,  # substitution
            ))
        prev = cur
    return prev[-1]


def normalize_text(s):
    """Lowercase and collapse whitespace."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().lower()


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def tokenize(s):
    """Lowercase, strip punctuation, split on whitespace -> token list."""
    if not s:
        return []
    cleaned = _PUNCT_RE.sub(" ", s.lower())
    return cleaned.split()


_LABEL_PREFIX_RE = re.compile(
    r"^(?:fig(?:ure)?|table|scheme)\b[.:)\s]*", re.IGNORECASE
)


def strip_label_prefix(label):
    """Strip the leading 'Fig(ure)?/Table/Scheme' word (and separators),
    keeping the identifier (e.g. '2', '2a'), casefolded.

    'Figure 2' and 'Fig. 2' both reduce to '2'; 'Figure 2' and 'Figure 3'
    stay distinct."""
    if not label:
        return ""
    stripped = _LABEL_PREFIX_RE.sub("", label.strip())
    return stripped.strip().casefold()


def levenshtein_similarity(a, b):
    """Normalized Levenshtein similarity in [0, 1] on normalized text.

    Defined as 1 - editdistance / max(len_a, len_b); 1.0 if both empty.
    """
    a, b = normalize_text(a), normalize_text(b)
    if not a and not b:
        return 1.0
    denom = max(len(a), len(b))
    if denom == 0:
        return 1.0
    return 1.0 - edit_distance(a, b) / denom


def token_set_f1(a, b):
    """Token-set F1 over lowercased, punctuation-stripped, whitespace tokens."""
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    if inter == 0:
        return 0.0
    precision = inter / len(sa)
    recall = inter / len(sb)
    return 2 * precision * recall / (precision + recall)


def label_exact_match(a, b):
    """Label exact match after casefold + stripping a label prefix."""
    return strip_label_prefix(a) == strip_label_prefix(b)


# --------------------------------------------------------------------------- #
# Loading + normalization of annotation files
# --------------------------------------------------------------------------- #

def _get_page_num(fig):
    """Return the figure's page number, tolerating the legacy 'page' key."""
    if "pageNum" in fig and fig["pageNum"] is not None:
        return fig["pageNum"]
    return fig.get("page")


def _page_dims(doc, page_num):
    """Look up (width, height) for a page from the top-level pages[] header."""
    for p in doc.get("pages") or []:
        if p.get("pageNum") == page_num or p.get("page") == page_num:
            w, h = p.get("width"), p.get("height")
            if w and h:
                return float(w), float(h)
    return None


def _norm_rect(bounds, w, h):
    """Divide a natural-px rect by (w, h) into a [0,1] fraction rect."""
    return {
        "x": bounds["x"] / w,
        "y": bounds["y"] / h,
        "width": bounds["width"] / w,
        "height": bounds["height"] / h,
    }


def _copy_rect(b):
    return {"x": b["x"], "y": b["y"], "width": b["width"], "height": b["height"]}


def normalize_document(doc, metadata=None, warnings=None):
    """Return a flat list of normalized figure records ready for matching.

    Each record::

        {
          "id", "label", "pageNum",
          "norm": <normalized page rect in [0,1]>,
          "caption", "captionSource",
          "subfigures": [ {"id","label","norm","caption","captionSource"}, ... ],
        }

    Figures whose normalized rect cannot be resolved are skipped with a warning.
    """
    if warnings is None:
        warnings = []
    meta_dims = None
    if metadata and metadata.get("width") and metadata.get("height"):
        meta_dims = (float(metadata["width"]), float(metadata["height"]))

    out = []
    for fig in doc.get("figures") or []:
        page_num = _get_page_num(fig)

        # Resolve normalized page rect for the figure.
        norm = None
        if fig.get("boundsNorm"):
            norm = _copy_rect(fig["boundsNorm"])
        elif fig.get("bounds"):
            dims = _page_dims(doc, page_num) or meta_dims
            if dims:
                norm = _norm_rect(fig["bounds"], dims[0], dims[1])
        if norm is None:
            warnings.append(
                "skipping figure {0!r} (page {1}): cannot resolve normalized "
                "bounds (no boundsNorm, no page dims, no metadata)".format(
                    fig.get("id"), page_num
                )
            )
            continue

        # Subfigures: fraction of the parent figure.
        fig_bounds = fig.get("bounds")
        subs = []
        for sub in fig.get("subfigures") or []:
            snorm = None
            if sub.get("boundsNorm"):
                snorm = _copy_rect(sub["boundsNorm"])
            elif sub.get("bounds") and fig_bounds and fig_bounds.get("width") \
                    and fig_bounds.get("height"):
                snorm = _norm_rect(
                    sub["bounds"], fig_bounds["width"], fig_bounds["height"]
                )
            if snorm is None:
                warnings.append(
                    "skipping subfigure {0!r} of figure {1!r}: cannot resolve "
                    "normalized bounds".format(sub.get("id"), fig.get("id"))
                )
                continue
            subs.append({
                "id": sub.get("id"),
                "label": sub.get("label", "") or "",
                "norm": snorm,
                "caption": sub.get("caption", "") or "",
                "captionSource": sub.get("captionSource", "") or "",
            })

        out.append({
            "id": fig.get("id"),
            "label": fig.get("label", "") or "",
            "pageNum": page_num,
            "norm": norm,
            "caption": fig.get("caption", "") or "",
            "captionSource": fig.get("captionSource", "") or "",
            "subfigures": subs,
        })
    return out


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def _pages_of(figs):
    pages = set()
    for f in figs:
        pages.add(f["pageNum"])
    return pages


def _match_figures(pred_figs, gt_figs, threshold):
    """Match predicted vs GT figures per-page. Returns aggregated results.

    Returns a dict with:
      tp, fp, fn, matches (list of (pred_fig, gt_fig, iou)),
      unmatched_pred (list of pred_fig), unmatched_gt (list of gt_fig),
      overlaps (list of (pred_fig, gt_fig, iou) with iou>0).
    """
    matches = []
    unmatched_pred = []
    unmatched_gt = []
    overlaps = []

    for page in sorted(_pages_of(pred_figs) | _pages_of(gt_figs),
                       key=lambda x: (x is None, x)):
        p_on_page = [f for f in pred_figs if f["pageNum"] == page]
        g_on_page = [f for f in gt_figs if f["pageNum"] == page]
        p_boxes = [f["norm"] for f in p_on_page]
        g_boxes = [f["norm"] for f in g_on_page]

        m, up, ug, ov = greedy_match(p_boxes, g_boxes, threshold)
        for pi, gi, score in m:
            matches.append((p_on_page[pi], g_on_page[gi], score))
        for pi in up:
            unmatched_pred.append(p_on_page[pi])
        for gi in ug:
            unmatched_gt.append(g_on_page[gi])
        for pi, gi, score in ov:
            overlaps.append((p_on_page[pi], g_on_page[gi], score))

    return {
        "tp": len(matches),
        "fp": len(unmatched_pred),
        "fn": len(unmatched_gt),
        "matches": matches,
        "unmatched_pred": unmatched_pred,
        "unmatched_gt": unmatched_gt,
        "overlaps": overlaps,
    }


def _prf(tp, fp, fn):
    """Precision, recall, F1 from counts."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return precision, recall, f1


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def caption_metrics(pairs):
    """Compute caption metrics over a list of (pred_text, gt_text) pairs."""
    if not pairs:
        return {
            "levenshtein": 0.0,
            "tokenF1": 0.0,
            "count": 0,
        }
    lev = [levenshtein_similarity(p, g) for p, g in pairs]
    tok = [token_set_f1(p, g) for p, g in pairs]
    return {
        "levenshtein": _mean(lev),
        "tokenF1": _mean(tok),
        "count": len(pairs),
    }


def score_article(pred_figs, gt_figs, threshold=DEFAULT_IOU):
    """Score one article's normalized figures. Returns a results dict.

    Includes per-threshold detection, localization, subfigure-count accuracy,
    caption similarity, and the error taxonomy.
    """
    result = {"iouThreshold": threshold}

    # Detection at primary threshold + @0.75 + sweep.
    fig_match = _match_figures(pred_figs, gt_figs, threshold)
    p, r, f1 = _prf(fig_match["tp"], fig_match["fp"], fig_match["fn"])
    result["detection"] = {
        "iou@{0}".format(threshold): {
            "tp": fig_match["tp"], "fp": fig_match["fp"], "fn": fig_match["fn"],
            "precision": p, "recall": r, "f1": f1,
        }
    }

    m75 = _match_figures(pred_figs, gt_figs, 0.75)
    p75, r75, f175 = _prf(m75["tp"], m75["fp"], m75["fn"])
    result["detection"]["iou@0.75"] = {
        "tp": m75["tp"], "fp": m75["fp"], "fn": m75["fn"],
        "precision": p75, "recall": r75, "f1": f175,
    }

    sweep = {}
    sweep_f1 = []
    sweep_prec = []
    for t in SWEEP_THRESHOLDS:
        mt = _match_figures(pred_figs, gt_figs, t)
        pt, rt, ft = _prf(mt["tp"], mt["fp"], mt["fn"])
        sweep[str(t)] = {"precision": pt, "recall": rt, "f1": ft}
        sweep_f1.append(ft)
        sweep_prec.append(pt)
    result["detection"]["sweep"] = sweep
    result["detection"]["meanF1_sweep"] = _mean(sweep_f1)
    result["detection"]["meanPrecision_sweep"] = _mean(sweep_prec)

    # Localization: IoU of matched figure pairs (at primary threshold).
    match_ious = [score for _, _, score in fig_match["matches"]]
    result["localization"] = {
        "meanIoU": _mean(match_ious),
        "medianIoU": _median(match_ious),
        "matchedPairs": len(match_ious),
    }

    # Subfigure-count accuracy + subfigure matching over matched figures.
    exact_count = 0
    count_abs_err = []
    sub_caption_pairs = []
    fig_caption_pairs = []
    fig_label_exact = 0
    sub_match_stats = {"tp": 0, "fp": 0, "fn": 0}

    for pred_f, gt_f, _score in fig_match["matches"]:
        pn = len(pred_f["subfigures"])
        gn = len(gt_f["subfigures"])
        if pn == gn:
            exact_count += 1
        count_abs_err.append(abs(pn - gn))

        # Figure caption + label pairs.
        fig_caption_pairs.append((pred_f["caption"], gt_f["caption"]))
        if label_exact_match(pred_f["label"], gt_f["label"]):
            fig_label_exact += 1

        # Match subfigures within this matched figure pair.
        sp_boxes = [s["norm"] for s in pred_f["subfigures"]]
        sg_boxes = [s["norm"] for s in gt_f["subfigures"]]
        sm, sup, sug, _ov = greedy_match(sp_boxes, sg_boxes, threshold)
        sub_match_stats["tp"] += len(sm)
        sub_match_stats["fp"] += len(sup)
        sub_match_stats["fn"] += len(sug)
        for spi, sgi, _s in sm:
            sub_caption_pairs.append((
                pred_f["subfigures"][spi]["caption"],
                gt_f["subfigures"][sgi]["caption"],
            ))

    n_matched = len(fig_match["matches"])
    result["subfigureCount"] = {
        "exactMatchRate": (exact_count / n_matched) if n_matched else 0.0,
        "meanAbsError": _mean(count_abs_err),
        "matchedFigures": n_matched,
    }

    sp, sr, sf1 = _prf(sub_match_stats["tp"], sub_match_stats["fp"],
                       sub_match_stats["fn"])
    result["subfigureDetection"] = {
        "tp": sub_match_stats["tp"], "fp": sub_match_stats["fp"],
        "fn": sub_match_stats["fn"],
        "precision": sp, "recall": sr, "f1": sf1,
    }

    # Caption metrics.
    result["caption"] = {
        "figures": caption_metrics(fig_caption_pairs),
        "subfigures": caption_metrics(sub_caption_pairs),
        "figureLabelExactRate": (fig_label_exact / n_matched) if n_matched else 0.0,
    }

    # Error taxonomy.
    matched_pairs = {(id(pf), id(gf)) for pf, gf, _ in fig_match["matches"]}
    matched_pred_ids = {id(pf) for pf, _, _ in fig_match["matches"]}
    matched_gt_ids = {id(gf) for _, gf, _ in fig_match["matches"]}

    mislocated = 0
    for pf, gf, ov in fig_match["overlaps"]:
        # A predicted and GT figure overlap but were NOT matched, and the
        # overlap is below threshold -> mislocated.
        if (id(pf), id(gf)) in matched_pairs:
            continue
        if id(pf) in matched_pred_ids or id(gf) in matched_gt_ids:
            continue
        if 0 < ov < threshold:
            mislocated += 1

    subfig_count_mismatch = sum(
        1 for pf, gf, _ in fig_match["matches"]
        if len(pf["subfigures"]) != len(gf["subfigures"])
    )
    caption_miss = sum(
        1 for pf, gf, _ in fig_match["matches"]
        if levenshtein_similarity(pf["caption"], gf["caption"]) < CAPTION_MISS_THRESHOLD
    )

    result["errorTaxonomy"] = {
        "missed-figure": fig_match["fn"],
        "spurious-figure": fig_match["fp"],
        "mislocated": mislocated,
        "subfigure-count-mismatch": subfig_count_mismatch,
        "caption-miss": caption_miss,
    }

    # Raw counts for micro-aggregation across articles.
    result["_raw"] = {
        "fig_tp": fig_match["tp"], "fig_fp": fig_match["fp"],
        "fig_fn": fig_match["fn"],
        "fig75_tp": m75["tp"], "fig75_fp": m75["fp"], "fig75_fn": m75["fn"],
        "match_ious": match_ious,
        "count_abs_err": count_abs_err,
        "exact_count": exact_count, "n_matched": n_matched,
        "fig_caption_pairs": fig_caption_pairs,
        "sub_caption_pairs": sub_caption_pairs,
        "fig_label_exact": fig_label_exact,
        "sub_tp": sub_match_stats["tp"], "sub_fp": sub_match_stats["fp"],
        "sub_fn": sub_match_stats["fn"],
        "sweep_counts": {
            str(t): _match_counts(pred_figs, gt_figs, t) for t in SWEEP_THRESHOLDS
        },
    }
    return result


def _match_counts(pred_figs, gt_figs, threshold):
    m = _match_figures(pred_figs, gt_figs, threshold)
    return {"tp": m["tp"], "fp": m["fp"], "fn": m["fn"]}


# --------------------------------------------------------------------------- #
# Aggregation (micro + macro)
# --------------------------------------------------------------------------- #

def aggregate(per_article):
    """Aggregate a list of per-article result dicts into micro + macro rows."""
    raws = [a["_raw"] for a in per_article]

    # ---- MICRO: pool all boxes ----
    tp = sum(r["fig_tp"] for r in raws)
    fp = sum(r["fig_fp"] for r in raws)
    fn = sum(r["fig_fn"] for r in raws)
    mp, mr, mf1 = _prf(tp, fp, fn)

    tp75 = sum(r["fig75_tp"] for r in raws)
    fp75 = sum(r["fig75_fp"] for r in raws)
    fn75 = sum(r["fig75_fn"] for r in raws)
    mp75, mr75, mf175 = _prf(tp75, fp75, fn75)

    all_match_ious = [x for r in raws for x in r["match_ious"]]
    all_abs_err = [x for r in raws for x in r["count_abs_err"]]
    exact_count = sum(r["exact_count"] for r in raws)
    n_matched = sum(r["n_matched"] for r in raws)
    fig_cap_pairs = [x for r in raws for x in r["fig_caption_pairs"]]
    sub_cap_pairs = [x for r in raws for x in r["sub_caption_pairs"]]
    fig_label_exact = sum(r["fig_label_exact"] for r in raws)

    sub_tp = sum(r["sub_tp"] for r in raws)
    sub_fp = sum(r["sub_fp"] for r in raws)
    sub_fn = sum(r["sub_fn"] for r in raws)
    sp, sr, sf1 = _prf(sub_tp, sub_fp, sub_fn)

    # Micro sweep mean-F1.
    micro_sweep_f1 = []
    for t in SWEEP_THRESHOLDS:
        stp = sum(r["sweep_counts"][str(t)]["tp"] for r in raws)
        sfp = sum(r["sweep_counts"][str(t)]["fp"] for r in raws)
        sfn = sum(r["sweep_counts"][str(t)]["fn"] for r in raws)
        _, _, ff = _prf(stp, sfp, sfn)
        micro_sweep_f1.append(ff)

    micro = {
        "detection@0.5": {"tp": tp, "fp": fp, "fn": fn,
                          "precision": mp, "recall": mr, "f1": mf1},
        "detection@0.75": {"tp": tp75, "fp": fp75, "fn": fn75,
                           "precision": mp75, "recall": mr75, "f1": mf175},
        "meanF1_sweep": _mean(micro_sweep_f1),
        "localization": {"meanIoU": _mean(all_match_ious),
                         "medianIoU": _median(all_match_ious)},
        "subfigureCount": {
            "exactMatchRate": (exact_count / n_matched) if n_matched else 0.0,
            "meanAbsError": _mean(all_abs_err),
        },
        "subfigureDetection": {"precision": sp, "recall": sr, "f1": sf1},
        "caption": {
            "figures": caption_metrics(fig_cap_pairs),
            "subfigures": caption_metrics(sub_cap_pairs),
            "figureLabelExactRate": (fig_label_exact / n_matched) if n_matched else 0.0,
        },
    }

    # ---- MACRO: mean of per-article scores ----
    def art_f1(a):
        key = "iou@{0}".format(a["iouThreshold"])
        return a["detection"][key]["f1"]

    macro = {
        "detection@0.5": {
            "precision": _mean([a["detection"]["iou@{0}".format(a["iouThreshold"])]["precision"]
                                for a in per_article]),
            "recall": _mean([a["detection"]["iou@{0}".format(a["iouThreshold"])]["recall"]
                             for a in per_article]),
            "f1": _mean([art_f1(a) for a in per_article]),
        },
        "detection@0.75": {
            "precision": _mean([a["detection"]["iou@0.75"]["precision"] for a in per_article]),
            "recall": _mean([a["detection"]["iou@0.75"]["recall"] for a in per_article]),
            "f1": _mean([a["detection"]["iou@0.75"]["f1"] for a in per_article]),
        },
        "meanF1_sweep": _mean([a["detection"]["meanF1_sweep"] for a in per_article]),
        "localization": {
            "meanIoU": _mean([a["localization"]["meanIoU"] for a in per_article]),
            "medianIoU": _mean([a["localization"]["medianIoU"] for a in per_article]),
        },
        "subfigureCount": {
            "exactMatchRate": _mean([a["subfigureCount"]["exactMatchRate"] for a in per_article]),
            "meanAbsError": _mean([a["subfigureCount"]["meanAbsError"] for a in per_article]),
        },
        "subfigureDetection": {
            "f1": _mean([a["subfigureDetection"]["f1"] for a in per_article]),
        },
        "caption": {
            "figures": {
                "levenshtein": _mean([a["caption"]["figures"]["levenshtein"] for a in per_article]),
                "tokenF1": _mean([a["caption"]["figures"]["tokenF1"] for a in per_article]),
            },
            "figureLabelExactRate": _mean([a["caption"]["figureLabelExactRate"] for a in per_article]),
        },
    }

    macro_f1 = macro["detection@0.5"]["f1"]
    micro_f1 = mf1
    return {"micro": micro, "macro": macro,
            "macroF1": macro_f1, "microF1": micro_f1}


# --------------------------------------------------------------------------- #
# Dataset discovery + IO
# --------------------------------------------------------------------------- #

def load_json(path):
    with open(str(path), "r", encoding="utf-8") as fh:
        return json.load(fh)


def discover_articles(root):
    """Return a sorted list of (name, dir, has_pred, has_truth) tuples."""
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        has_pred = (entry / "annotations.json").is_file()
        has_truth = (entry / "ground-truth.json").is_file()
        if has_pred or has_truth:
            out.append((entry.name, entry, has_pred, has_truth))
    return out


def load_article(article_dir, pred_path=None, truth_path=None):
    """Load + normalize predicted and truth figures for one article dir.

    Returns ``(pred_figs, gt_figs, warnings)``.
    """
    article_dir = Path(article_dir)
    pred_path = Path(pred_path) if pred_path else article_dir / "annotations.json"
    truth_path = Path(truth_path) if truth_path else article_dir / "ground-truth.json"
    meta_path = article_dir / "metadata.json"

    metadata = load_json(meta_path) if meta_path.is_file() else None
    warnings = []

    pred_doc = load_json(pred_path)
    gt_doc = load_json(truth_path)
    pred_figs = normalize_document(pred_doc, metadata, warnings)
    gt_figs = normalize_document(gt_doc, metadata, warnings)
    return pred_figs, gt_figs, warnings


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

TUNING_GUIDE = [
    ("missed-figure (FN)", "detector recall too low -> lower detection "
                           "confidence threshold / box score cutoff"),
    ("spurious-figure (FP)", "detector precision too low -> raise confidence "
                             "threshold / add non-max suppression"),
    ("mislocated", "boxes overlap but IoU too low -> tune box-regression / "
                   "padding / snap-to-content margins"),
    ("subfigure-count-mismatch", "panel splitter over/under-segmenting -> tune "
                                 "gutter-detection sensitivity / min panel size"),
    ("caption-miss", "wrong caption region or OCR -> adjust caption search "
                     "radius / prefer textlayer over OCR"),
]


def _fmt(x):
    return "{0:.3f}".format(x)


def print_article_report(name, result, warnings):
    print("=" * 70)
    print("ARTICLE: {0}".format(name))
    print("=" * 70)
    thr = result["iouThreshold"]
    d = result["detection"]["iou@{0}".format(thr)]
    d75 = result["detection"]["iou@0.75"]
    print("\nDetection (figures)")
    print("  IoU@{0:<5} TP={1} FP={2} FN={3}  P={4} R={5} F1={6}".format(
        thr, d["tp"], d["fp"], d["fn"], _fmt(d["precision"]),
        _fmt(d["recall"]), _fmt(d["f1"])))
    print("  IoU@0.75  TP={0} FP={1} FN={2}  P={3} R={4} F1={5}".format(
        d75["tp"], d75["fp"], d75["fn"], _fmt(d75["precision"]),
        _fmt(d75["recall"]), _fmt(d75["f1"])))
    print("  mean-F1 over sweep {0}..{1}: {2}".format(
        SWEEP_THRESHOLDS[0], SWEEP_THRESHOLDS[-1],
        _fmt(result["detection"]["meanF1_sweep"])))

    loc = result["localization"]
    print("\nLocalization (matched pairs={0})".format(loc["matchedPairs"]))
    print("  mean IoU={0}  median IoU={1}".format(
        _fmt(loc["meanIoU"]), _fmt(loc["medianIoU"])))

    sc = result["subfigureCount"]
    print("\nSubfigure count (over {0} matched figures)".format(sc["matchedFigures"]))
    print("  exact-count-match rate={0}  mean|pred_n-gt_n|={1}".format(
        _fmt(sc["exactMatchRate"]), _fmt(sc["meanAbsError"])))
    sd = result["subfigureDetection"]
    print("  subfigure detection  P={0} R={1} F1={2}".format(
        _fmt(sd["precision"]), _fmt(sd["recall"]), _fmt(sd["f1"])))

    cap = result["caption"]
    print("\nCaption similarity (matched pairs)")
    print("  figures    : levenshtein={0} tokenF1={1} (n={2})".format(
        _fmt(cap["figures"]["levenshtein"]), _fmt(cap["figures"]["tokenF1"]),
        cap["figures"]["count"]))
    print("  subfigures : levenshtein={0} tokenF1={1} (n={2})".format(
        _fmt(cap["subfigures"]["levenshtein"]), _fmt(cap["subfigures"]["tokenF1"]),
        cap["subfigures"]["count"]))
    print("  figure label exact-match rate={0}".format(
        _fmt(cap["figureLabelExactRate"])))

    print("\nError taxonomy")
    for bucket, count in result["errorTaxonomy"].items():
        print("  {0:<26} {1}".format(bucket, count))

    if warnings:
        print("\nWarnings ({0}):".format(len(warnings)))
        for w in warnings:
            print("  ! {0}".format(w))

    print("\nTuning guide")
    for bucket, knob in TUNING_GUIDE:
        print("  {0:<22} -> {1}".format(bucket.split(" ")[0], knob))
    print()


def print_aggregate(agg):
    print("#" * 70)
    print("AGGREGATE")
    print("#" * 70)
    for kind in ("micro", "macro"):
        a = agg[kind]
        d = a["detection@0.5"]
        print("\n[{0}]".format(kind.upper()))
        print("  detection@0.5  P={0} R={1} F1={2}".format(
            _fmt(d["precision"]), _fmt(d["recall"]), _fmt(d["f1"])))
        print("  detection@0.75 F1={0}".format(_fmt(a["detection@0.75"]["f1"])))
        print("  mean-F1 sweep  {0}".format(_fmt(a["meanF1_sweep"])))
        print("  localization   meanIoU={0} medianIoU={1}".format(
            _fmt(a["localization"]["meanIoU"]), _fmt(a["localization"]["medianIoU"])))
        print("  subfig count   exactRate={0} meanAbsErr={1}".format(
            _fmt(a["subfigureCount"]["exactMatchRate"]),
            _fmt(a["subfigureCount"]["meanAbsError"])))
        print("  caption(fig)   levenshtein={0} tokenF1={1}".format(
            _fmt(a["caption"]["figures"]["levenshtein"]),
            _fmt(a["caption"]["figures"]["tokenF1"])))
    print("\n==> macroF1={0}  microF1={1}".format(
        _fmt(agg["macroF1"]), _fmt(agg["microF1"])))
    print()


# --------------------------------------------------------------------------- #
# Subcommand handlers
# --------------------------------------------------------------------------- #

def cmd_datasets(args):
    root = projects_root(getattr(args, "projects_dir", None))
    articles = discover_articles(root)
    print("Projects root: {0}".format(root))
    if not articles:
        print("(no article directories found)")
        return 0
    print("{0:<40} {1:>9} {2:>12} {3:>6}".format(
        "article", "predicted", "ground-truth", "both"))
    print("-" * 70)
    for name, _dir, has_pred, has_truth in articles:
        print("{0:<40} {1:>9} {2:>12} {3:>6}".format(
            name, "yes" if has_pred else "-",
            "yes" if has_truth else "-",
            "yes" if (has_pred and has_truth) else "-"))
    return 0


def _resolve_article_dir(root, article):
    """Resolve an article argument to a directory path."""
    p = Path(article)
    if p.is_dir():
        return p
    candidate = Path(root) / article
    if candidate.is_dir():
        return candidate
    return p  # let downstream IO raise a clear error


def _clean_result(result):
    """Drop the internal ``_raw`` key before serializing to disk."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


def cmd_score(args):
    root = projects_root(getattr(args, "projects_dir", None))
    if getattr(args, "all", False):
        return cmd_score_all(args)

    if not args.article:
        print("error: 'score' requires an <article> (or use --all).",
              file=sys.stderr)
        return 2

    article_dir = _resolve_article_dir(root, args.article)
    pred_figs, gt_figs, warnings = load_article(
        article_dir, args.pred, args.truth)
    result = score_article(pred_figs, gt_figs, args.iou)

    print_article_report(article_dir.name, result, warnings)

    out_path = Path(article_dir) / "score-results.json"
    payload = _clean_result(result)
    payload["article"] = article_dir.name
    payload["warnings"] = warnings
    with open(str(out_path), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print("Wrote {0}".format(out_path))
    return 0


def _score_all_articles(root, iou):
    """Score every article with both files. Returns (per_article, names, warns)."""
    per_article = []
    names = []
    all_warnings = {}
    for name, adir, has_pred, has_truth in discover_articles(root):
        if not (has_pred and has_truth):
            continue
        pred_figs, gt_figs, warnings = load_article(adir)
        result = score_article(pred_figs, gt_figs, iou)
        per_article.append(result)
        names.append(name)
        if warnings:
            all_warnings[name] = warnings
    return per_article, names, all_warnings


def cmd_score_all(args):
    root = projects_root(getattr(args, "projects_dir", None))
    per_article, names, warns = _score_all_articles(root, args.iou)
    if not per_article:
        print("No articles with both annotations.json and ground-truth.json "
              "under {0}".format(root), file=sys.stderr)
        return 1

    # Per-article table sorted worst-F1 first.
    rows = []
    for name, res in zip(names, per_article):
        f1 = res["detection"]["iou@{0}".format(res["iouThreshold"])]["f1"]
        rows.append((f1, name, res))
    rows.sort(key=lambda t: t[0])

    print("{0:<36} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8}".format(
        "article", "F1", "F1@75", "swpF1", "meanIoU", "capLev"))
    print("-" * 74)
    for f1, name, res in rows:
        thr = res["iouThreshold"]
        print("{0:<36} {1:>6} {2:>6} {3:>6} {4:>8} {5:>8}".format(
            name[:36], _fmt(f1),
            _fmt(res["detection"]["iou@0.75"]["f1"]),
            _fmt(res["detection"]["meanF1_sweep"]),
            _fmt(res["localization"]["meanIoU"]),
            _fmt(res["caption"]["figures"]["levenshtein"])))

    agg = aggregate(per_article)
    print()
    print_aggregate(agg)

    if warns:
        print("Warnings:")
        for name, wl in warns.items():
            for w in wl:
                print("  [{0}] {1}".format(name, w))

    args._agg = agg  # stash for gate reuse
    args._n_articles = len(per_article)
    return 0


def _git_sha():
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip()
    except Exception:
        return None


def _read_best_macro_f1(scores_path):
    """Return the best macroF1 among prior runs in scores.jsonl, or None."""
    best = None
    if not Path(scores_path).is_file():
        return None
    with open(str(scores_path), "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            f1 = rec.get("macroF1")
            if isinstance(f1, (int, float)):
                if best is None or f1 > best:
                    best = f1
    return best


def cmd_gate(args):
    root = projects_root(getattr(args, "projects_dir", None))

    # Run score-all silently-ish (it prints its table).
    rc = cmd_score_all(args)
    if rc != 0:
        return rc
    agg = getattr(args, "_agg", None)
    if agg is None:
        print("error: no aggregate produced", file=sys.stderr)
        return 1

    scores_path = args.baseline_from
    if scores_path:
        scores_path = Path(scores_path)
    else:
        scores_path = Path(root) / "scores.jsonl"

    prev_best = _read_best_macro_f1(scores_path)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gitSha": _git_sha(),
        "macroF1": agg["macroF1"],
        "microF1": agg["microF1"],
        "config": {
            "iou": args.iou,
            "sweep": SWEEP_THRESHOLDS,
            "nArticles": getattr(args, "_n_articles", None),
            "projectsRoot": str(root),
        },
    }
    # Append the run record (scores.jsonl doubles as the baseline history).
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(scores_path), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print("Appended run to {0}".format(scores_path))

    # Determine the regression bar.
    threshold = None
    reason = None
    if args.min_f1 is not None:
        threshold = args.min_f1
        reason = "--min-f1"
    elif prev_best is not None:
        threshold = prev_best
        reason = "previous best macroF1"

    print("\nGATE: macroF1={0}".format(_fmt(agg["macroF1"])))
    if threshold is None:
        print("  no baseline yet (this is the first recorded run) -> PASS")
        return 0

    print("  bar={0} ({1})".format(_fmt(threshold), reason))
    if agg["macroF1"] + 1e-9 < threshold:
        print("  REGRESSION: macroF1 dropped below bar -> FAIL")
        return 1
    print("  macroF1 meets/exceeds bar -> PASS")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    # Shared parent so --projects-dir works before OR after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS default so that supplying it before the subcommand is not
    # clobbered by the subparser re-parsing its own default.
    common.add_argument("--projects-dir", default=argparse.SUPPRESS,
                        help="Projects root (default: $FIGURE_PROJECTS_DIR or "
                             "~/figure-extraction-projects).")

    parser = argparse.ArgumentParser(
        parents=[common],
        description="Ground-truth scoring harness for the figure-extractor pipeline.")
    sub = parser.add_subparsers(dest="command")

    p_ds = sub.add_parser("datasets", parents=[common],
                          help="List article dirs and their files.")
    p_ds.set_defaults(func=cmd_datasets)

    p_score = sub.add_parser("score", parents=[common],
                             help="Score one article dir.")
    p_score.add_argument("article", nargs="?", help="Article dir name or path.")
    p_score.add_argument("--all", action="store_true",
                         help="Score all articles (alias for score-all).")
    p_score.add_argument("--iou", type=float, default=DEFAULT_IOU)
    p_score.add_argument("--truth", default=None, help="Override ground-truth path.")
    p_score.add_argument("--pred", default=None, help="Override annotations path.")
    p_score.set_defaults(func=cmd_score)

    p_all = sub.add_parser("score-all", parents=[common],
                           help="Score every article with both files.")
    p_all.add_argument("--iou", type=float, default=DEFAULT_IOU)
    p_all.set_defaults(func=cmd_score_all)

    p_gate = sub.add_parser("gate", parents=[common],
                            help="Regression gate against scores.jsonl.")
    p_gate.add_argument("--baseline-from", default=None,
                        help="scores.jsonl to read/append (default: "
                             "<projects_root>/scores.jsonl).")
    p_gate.add_argument("--min-f1", type=float, default=None,
                        help="Explicit minimum macro-F1 bar.")
    p_gate.add_argument("--iou", type=float, default=DEFAULT_IOU)
    p_gate.set_defaults(func=cmd_gate)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
