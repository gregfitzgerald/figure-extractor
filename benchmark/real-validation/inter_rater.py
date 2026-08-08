#!/usr/bin/env python3
"""inter_rater.py -- the G vs H2 comparison. Genuine INTER-rater reliability.

`ingest_annotations.py intra` pairs two reads by `(item_id, panelLetter)` with no rater
filter, which is correct for one person re-reading and WRONG across two people: it would
label a Greg/Dan pair "intra-rater". This script is the inter-rater counterpart. It reads
the two GT stores, never writes to either, and pairs G against H2.

Three things it does that `intra` cannot:

  1. **Matches marks by INDEX, not by name.** `intra` matches groups on
     `"<group> <seriesLabel>"`, which is fine when the same person typed both labels and
     useless when two people did. The ingest already enforces left-to-right click order
     against the coding form's `marks[]` roster, so the i-th group of a panel is the i-th
     bar from the left in BOTH readings. Index is the convention-free join.

  2. **Reports letter disagreement as a RESULT, not as a join failure.** Two raters
     labelling the same box `B` and `C` is the Tier-P silent-mislabel class occurring
     between humans. Panels are joined on the letter first and on maximum box IoU second;
     the two joins are reported separately so a letter disagreement is visible instead of
     silently dropping the panel.

  3. **Cohen's kappa on the categorical channels.** Raw percent agreement (all `intra`
     offers) is uninterpretable when one category dominates -- and ~91% of this corpus is
     SEM, so dispersion-type agreement is exactly that case.

Usage
    python3 inter_rater.py                       # default tree locations
    python3 inter_rater.py --run cascade_v4      # also fit Grubbs on {G, H2, M}
    python3 inter_rater.py --selftest
"""
import argparse
import json
import math
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
NA = float("nan")


# ============================================================ small statistics
def icc_a1(pairs):
    """ICC(A,1) -- two-way random effects, ABSOLUTE agreement, single measurement.

    Absolute, not consistency: a constant offset between two raters (one clicks the centre
    of the cap, the other its upper edge) is a real error here, because the number goes
    into `escalc` as it stands and is never mean-centred. Single measurement, not average:
    the study will use ONE rater's reading, not the mean of two. Two-way RANDOM, not mixed:
    the claim is about "a competent human annotator", not about these two men specifically.

    Identical to `ingest_annotations._icc_a1`, restated here so the inter- and intra-rater
    numbers are produced by the same estimator and are directly comparable."""
    n = len(pairs)
    if n < 3:
        return NA
    grand = sum(a + b for a, b in pairs) / (2 * n)
    msr = 2 * sum(((a + b) / 2 - grand) ** 2 for a, b in pairs) / (n - 1)
    cm = [sum(p[j] for p in pairs) / n for j in (0, 1)]
    msc = n * sum((c - grand) ** 2 for c in cm)
    sse = sum((p[j] - (p[0] + p[1]) / 2 - cm[j] + grand) ** 2 for p in pairs for j in (0, 1))
    mse = sse / (n - 1) if n > 1 else NA
    den = msr + mse + 2 * (msc - mse) / n
    return (msr - mse) / den if den else NA


def cohen_kappa(pairs):
    """Cohen's kappa for two raters over nominal categories. `pairs` is [(a, b), ...]."""
    n = len(pairs)
    if n < 2:
        return NA
    cats = sorted({str(x) for p in pairs for x in p})
    po = sum(1 for a, b in pairs if str(a) == str(b)) / n
    ma = {c: sum(1 for a, _ in pairs if str(a) == c) / n for c in cats}
    mb = {c: sum(1 for _, b in pairs if str(b) == c) / n for c in cats}
    pe = sum(ma[c] * mb[c] for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else NA


def bland_altman_log(pairs):
    """Bias and 95% limits of agreement on log(H2 / G), back-transformed to percent.

    Log scale because dispersion error is proportional (ANALYSIS-PLAN sec.1.3), so
    log(SD_H2 / SD_G) is the natural difference and its LoA is directly comparable to the
    pre-registered [-25%, +25%] gate on log(SD_M / SD_G)."""
    lr = [math.log(b / a) for a, b in pairs if a and b and a > 0 and b > 0]
    n = len(lr)
    if n < 3:
        return None
    bias = statistics.mean(lr)
    sd = statistics.stdev(lr)
    lo, hi = bias - 1.959964 * sd, bias + 1.959964 * sd
    return {
        "n": n,
        "biasPct": 100 * (math.exp(bias) - 1),
        "loaLoPct": 100 * (math.exp(lo) - 1),
        "loaHiPct": 100 * (math.exp(hi) - 1),
        "sdLog": sd,
        # 95% CI half-widths, in percent, on the bias and on each limit
        "biasCiHalfPct": 100 * 1.959964 * sd / math.sqrt(n),
        "loaCiHalfPct": 100 * 1.959964 * sd * math.sqrt(3.0 / n),
    }


def rel_stats(pairs):
    """The same summary `intra` reports, so RC_inter and RC_intra are the same quantity.

    `s_w` is the within-subject SD of the relative difference; RC = 2.77 * s_w is the
    repeatability (here: reproducibility) coefficient -- the interval inside which two
    readings of the same panel agree 95% of the time."""
    if not pairs:
        return None
    rel = [100 * abs(a - b) / ((abs(a) + abs(b)) / 2) for a, b in pairs
           if (abs(a) + abs(b)) > 0]
    if not rel:
        return None
    sw = math.sqrt(sum(r ** 2 for r in rel) / (2 * len(rel)))
    return {"n": len(rel), "medianPct": statistics.median(rel), "worstPct": max(rel),
            "swPct": sw, "rcPct": 2.77 * sw, "iccA1": icc_a1(pairs)}


def iou(a, b):
    if not a or not b:
        return NA
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0.0, min(ax2, bx2) - max(a["x"], b["x"]))
    iy = max(0.0, min(ay2, by2) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else NA


def grubbs_three(a, b, c):
    """Grubbs (1948), imported in spirit from score_real_validation.grubbs_three.
    Negative variances are reported, never clipped -- a negative estimate is evidence that
    n is too small or the independence assumption is violated, and hiding it hides that."""
    n = len(a)
    if not (n == len(b) == len(c)) or n < 5:
        return None
    vab = statistics.variance([x - y for x, y in zip(a, b)])
    vac = statistics.variance([x - y for x, y in zip(a, c)])
    vbc = statistics.variance([x - y for x, y in zip(b, c)])
    return {"n": n, "var_a": (vab + vac - vbc) / 2, "var_b": (vab + vbc - vac) / 2,
            "var_c": (vac + vbc - vab) / 2,
            "var_diff_ab": vab, "var_diff_ac": vac, "var_diff_bc": vbc}


def sd_ratio_ci(n, ratio):
    """95% CI multiplier on an SD ratio, Wilson-Hilferty approximation to F (no scipy).
    Same function as score_real_validation.sd_ratio_ci."""
    if not ratio or n < 4 or ratio <= 0 or ratio != ratio:
        return (NA, NA)
    d = n - 1
    z, a = 1.959964, 2 / (9 * (n - 1))
    f = ((1 - a + z * math.sqrt(a)) / (1 - a - z * math.sqrt(a))) ** 3
    return (ratio / math.sqrt(f), ratio * math.sqrt(f))


# ============================================================ loading and joining
def load_store(root):
    p = pathlib.Path(root) / "gt" / "human_gt.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_key(root):
    """`anon_id -> item_id`, from that rater's own sealed key.

    Needed because of an asymmetry in the store. `ingest_annotations.py:423` writes a panel
    marked `extractable: false` as a short record carrying `panel_item`, `anon_id`,
    `charType`, the ambiguities and nothing else -- no `item_id`, no `panelLetter`, no
    `reader`. Joining on `item_id` therefore dropped precisely the records that carry an
    ABSTENTION, so the `extractable` channel could report agreement but never disagreement,
    and `Lyst2012_F7` -- put in the subset specifically because the correct answer there is
    to abstain -- would have contributed nothing.

    Reading the key is not an unblinding: this runs at analysis time, after both readings
    are sealed, on the analyst's own machine, and it is the same key `ingest` already used
    to stamp `item_id` into every extractable record."""
    p = pathlib.Path(root) / "keys" / "plan.key.json"
    if not p.exists():
        return {}
    key = json.loads(p.read_text(encoding="utf-8"))
    return {i["anon_id"]: i.get("item_id")
            for s in key.get("sessions", []) for i in s.get("items", [])
            if i.get("anon_id")}


# `dn03_9c1a_pB` -> `B`. prepare_session.py builds every Stage B panel id as
# f"{anon_id}_p{slug(letter)}", so the letter survives on a record that has no other copy
# of it.
_PANEL_SUFFIX = re.compile(r"_p([^_]+)$")


def panel_identity(rec, keymap):
    """`(item_id, letter)` for ANY record, extractable or not, or None if unrecoverable.

    This is the join key: the (figure, panel-letter) identity both raters necessarily
    share, reconstructed from whichever fields the record happens to carry."""
    item = rec.get("item_id") or keymap.get(rec.get("anon_id"))
    letter = (rec.get("panelLetter") or "").upper()
    if not letter:
        m = _PANEL_SUFFIX.search(rec.get("panel_item") or "")
        letter = m.group(1).upper() if m else ""
    return (item, letter) if item and letter else None


def _panels_of(rec):
    """Page-space panel boxes from a record's Stage A structure, keyed by letter.

    First occurrence wins. A rater who gives two boxes the same letter has committed the
    mislabel class this study exists to bound, and last-wins would quietly discard the
    evidence -- reading order is at least the convention PROTOCOL sec.8.6 specifies."""
    out = {}
    for f in rec.get("structure") or []:
        fb = f.get("bbox") or {}
        for p in f.get("panels") or []:
            pb = p.get("bbox") or {}
            L = (p.get("letter") or "").upper()
            if not pb or L in out:
                continue
            out[L] = {
                "x": fb.get("x", 0) + pb.get("x", 0), "y": fb.get("y", 0) + pb.get("y", 0),
                "width": pb.get("width"), "height": pb.get("height")}
    return out


def join_panels(g_recs, h_recs, g_key=None, h_key=None):
    """Pair panels across raters on the (figure, panel-letter) identity.

    The identity is rebuilt by `panel_identity`, so a record with `extractable: false` --
    which carries neither `item_id` nor `panelLetter` -- joins exactly like any other. That
    is the whole point: "Greg says extractable, Dan says not" has to land in the report as a
    disagreement, not vanish as a missing row.

    Letter join first; panels the letter join misses then get a maximum-IoU join within the
    same figure, and the two routes are counted separately so a letter disagreement shows up
    as a number. Panels that survive neither are returned in `orphans` WITH their record, so
    the caller can score them rather than drop them."""
    g_key, h_key = g_key or {}, h_key or {}
    gi, hi = {}, {}
    for recs, keymap, bucket in ((g_recs, g_key, gi), (h_recs, h_key, hi)):
        for r in recs:
            ident = panel_identity(r, keymap)
            if ident:
                bucket.setdefault(ident[0], {}).setdefault(ident[1], r)

    # Only figures BOTH raters read. Greg's store covers the whole Tier-1 worklist and Dan's
    # covers the seven-figure subset (rule C1), so unioning the figures would fill the
    # orphan list with every panel Dan was never given -- which says nothing about either
    # rater. Within a shared figure an orphan is informative, and that is where they come
    # from below.
    pairs, by_letter, by_iou, unmatched, orphans = [], 0, 0, [], []
    for item in sorted(set(gi) & set(hi)):
        gp, hp = gi[item], hi[item]
        used_h = set()
        for L, gr in sorted(gp.items()):
            if L in hp:
                pairs.append((gr, hp[L], "letter"))
                used_h.add(L)
                by_letter += 1
        gbox = {L: b for r in gp.values() for L, b in _panels_of(r).items()}
        hbox = {L: b for r in hp.values() for L, b in _panels_of(r).items()}
        for L, gr in sorted(gp.items()):
            if L in hp:
                continue
            cands = [(iou(gbox.get(L), hbox.get(M)), M) for M in hp if M not in used_h]
            cands = [c for c in cands if c[0] == c[0] and c[0] >= 0.5]
            if cands:
                best = max(cands)
                pairs.append((gr, hp[best[1]], f"iou:{L}->{best[1]}"))
                used_h.add(best[1])
                by_iou += 1
            else:
                unmatched.append((item, L, "G only"))
                orphans.append({"item": item, "letter": L, "side": "G", "rec": gr})
        for M, hr in sorted(hp.items()):
            if M not in used_h:
                unmatched.append((item, M, "H2 only"))
                orphans.append({"item": item, "letter": M, "side": "H2", "rec": hr})
    return pairs, {"byLetter": by_letter, "byIoU": by_iou, "unmatched": unmatched,
                   "orphans": orphans,
                   "itemsG": len(gi), "itemsH2": len(hi),
                   "itemsBoth": len(set(gi) & set(hi))}


def _groups(rec):
    return ((rec.get("extraction") or {}).get("groups")) or []


def _panel_char(rec):
    ps = ((rec.get("characterization") or {}).get("panels")) or []
    if ps:
        return ps[0]
    # A non-extractable record has no `characterization` block at all; its `charType` sits
    # at the top level (ingest_annotations.py:423). Without this fallback the charType
    # channel would score a real abstention -- "this is a micrograph" -- as None vs None,
    # i.e. as agreement between two blanks.
    return {"charType": rec.get("charType")}


# ============================================================ the report
def analyse(g_root, h_root, run=None):
    g_recs, h_recs = load_store(g_root), load_store(h_root)
    if not g_recs:
        raise SystemExit(f"no GT store under {g_root}/gt/human_gt.jsonl -- ingest G first")
    if not h_recs:
        raise SystemExit(f"no GT store under {h_root}/gt/human_gt.jsonl -- ingest H2 first")
    # Test the readers that are PRESENT. A non-extractable record carries no `reader` field
    # at all (ingest_annotations.py:423), so a per-record `reader is None` test would refuse
    # a perfectly good store the moment it contained an abstention -- and abstentions are
    # what `Lyst2012_F7` is in the subset to produce.
    readers = {r.get("reader") for r in h_recs if r.get("reader")}
    if not readers or "GF-human" in readers:
        raise SystemExit(
            f"the H2 store at {h_root} carries reader={sorted(readers) or None}. Refusing: "
            f"either the wrong tree was passed or Dan's session was ingested without "
            f"`--reader`. An inter-rater number computed from one person's two reads "
            f"is the exact error this script exists to prevent.")

    gkey, hkey = load_key(g_root), load_key(h_root)
    pairs, jinfo = join_panels(g_recs, h_recs, gkey, hkey)
    out = {"join": jinfo, "nPairs": len(pairs)}

    # ---- structure: panel count and letters, per figure
    gfig, hfig = {}, {}
    # Keyed by the rebuilt identity, so an abstention record does not open a `None` figure.
    # Its `structure` is empty anyway -- only its extractable sibling carries the Stage A
    # boxes -- hence `or` rather than an unconditional overwrite.
    for recs, keymap, bucket in ((g_recs, gkey, gfig), (h_recs, hkey, hfig)):
        for r in recs:
            ident = panel_identity(r, keymap)
            if ident:
                bucket[ident[0]] = bucket.get(ident[0]) or _panels_of(r)
    cnt, lets, ious = [], [], []
    for item in sorted(set(gfig) & set(hfig)):
        cnt.append((len(gfig[item]), len(hfig[item])))
        lets.append((",".join(sorted(gfig[item])), ",".join(sorted(hfig[item]))))
        for L in set(gfig[item]) & set(hfig[item]):
            v = iou(gfig[item][L], hfig[item][L])
            if v == v:
                ious.append(v)
    out["structure"] = {
        "nFigures": len(cnt),
        "panelCountAgreementPct": 100 * sum(1 for a, b in cnt if a == b) / len(cnt) if cnt else NA,
        "letterSetAgreementPct": 100 * sum(1 for a, b in lets if a == b) / len(lets) if lets else NA,
        "panelIoUMedian": statistics.median(ious) if ious else NA,
        "panelIoUWorst": min(ious) if ious else NA,
        "panelIoUn": len(ious),
        "letterDisagreements": jinfo["byIoU"],
    }

    # ---- categorical channels
    cat = {"charType": [], "dispersionType": [], "extractable": [], "roles": []}
    joined_extractable, dis = [], []
    for gr, hr, route in pairs:
        gc, hc = _panel_char(gr), _panel_char(hr)
        cat["charType"].append((gc.get("charType"), hc.get("charType")))
        ge, he = gr.get("extractable"), hr.get("extractable")
        joined_extractable.append((ge, he))
        if ge != he:
            dis.append({"item": gr.get("item_id") or hr.get("item_id"),
                        "letter": (gr.get("panelLetter") or hr.get("panelLetter")
                                   or "").upper(),
                        "route": route, "G": ge, "H2": he})
        gd = ((gc.get("statistics") or {}).get("dispersion") or {}).get("type")
        hd = ((hc.get("statistics") or {}).get("dispersion") or {}).get("type")
        cat["dispersionType"].append((gd, hd))
        cat["roles"].append((str([s.get("role") for s in gc.get("series") or []]),
                             str([s.get("role") for s in hc.get("series") or []])))

    # `extractable` is the abstention channel, and until the identity join above it was the
    # one channel that could not disagree at all: a non-extractable record carried no
    # `item_id`, so it never reached the join and "Greg says extractable, Dan says not"
    # scored as a missing row. Panels only ONE rater has a Stage B record for now enter the
    # channel as the explicit value "absent" rather than being dropped -- inside a figure
    # both of them read, "I coded this panel" against "I did not" is a fact about the panel.
    absent = []
    for o in jinfo["orphans"]:
        val = o["rec"].get("extractable")
        pair = (val, "absent") if o["side"] == "G" else ("absent", val)
        absent.append(pair)
        dis.append({"item": o["item"], "letter": o["letter"], "route": "one-sided",
                    "G": pair[0], "H2": pair[1]})
    cat["extractable"] = joined_extractable + absent

    out["categorical"] = {
        k: {"n": len(v),
            "agreementPct": 100 * sum(1 for a, b in v if a == b) / len(v) if v else NA,
            "kappa": cohen_kappa(v)}
        for k, v in cat.items() if v}

    out["abstention"] = {
        "nJoined": len(joined_extractable), "nOneSided": len(absent),
        "agreementJoinedPct": (100 * sum(1 for a, b in joined_extractable if a == b)
                               / len(joined_extractable)) if joined_extractable else NA,
        "kappaJoined": cohen_kappa(joined_extractable),
        "disagreements": dis,
        "note": "`absent` means the panel is in one rater's Stage B roster and not the "
                "other's, inside a figure both of them read. The pre-registered per-figure "
                "cap (prepare_dan_session._cap_stage_b) can produce that without either "
                "rater having judged anything, so the joined and the one-sided counts are "
                "reported separately instead of pooled into one agreement number."}

    # ---- numeric channels, matched by mark INDEX
    chans = {"central": [], "dispersion": []}
    for gr, hr, _ in pairs:
        gg, hg = _groups(gr), _groups(hr)
        for i in range(min(len(gg), len(hg))):
            a, b = gg[i], hg[i]
            for fld in ("mean", "median"):
                if a.get(fld) and b.get(fld):
                    chans["central"].append((a[fld], b[fld]))
            if a.get("errorHalf") and b.get("errorHalf"):
                chans["dispersion"].append((a["errorHalf"], b["errorHalf"]))
            if all(a.get(k) is not None and b.get(k) is not None for k in ("q1", "q3")) \
                    and a["q3"] != a["q1"] and b["q3"] != b["q1"]:
                chans["dispersion"].append((a["q3"] - a["q1"], b["q3"] - b["q1"]))
    out["numeric"] = {}
    for chan, ps in chans.items():
        if not ps:
            continue
        rec = rel_stats(ps) or {}
        rec["blandAltman"] = bland_altman_log(ps)
        out["numeric"][chan] = rec

    # ---- Grubbs on {G, H2, M}: three instruments, only two of which share a person
    out["grubbs"] = _grubbs_block(pairs, run)
    out["cHat"] = {"available": False,
                   "note": "c_hat = sigma_G^2{D,G,M} - sigma_G^2{G,H2,M} needs the coded "
                           "landmark join (coded_reference controlLandmarkId / "
                           "intervLandmarkId), which is filled in by the annotator and is "
                           "not present yet. Reported as not-available rather than guessed."}
    return out


def _grubbs_block(pairs, run):
    if not run:
        return {"available": False, "note": "no --run given; {G,H2,M} needs machine predictions"}
    pdir = HERE / "pred" / run
    preds = {}
    if pdir.is_dir():
        for p in pdir.glob("*.json"):
            try:
                preds[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    if not preds:
        return {"available": False, "note": f"no predictions under pred/{run}/"}
    G, H, M = [], [], []
    for gr, hr, _ in pairs:
        pr = preds.get(gr.get("item_id")) or preds.get(gr.get("panel_item"))
        if not pr:
            continue
        pg = None
        for panel in pr.get("panels") or []:
            if (panel.get("label") or "").upper() == (gr.get("panelLetter") or "").upper():
                pg = panel
                break
        if not pg:
            continue
        mm = [lm.get("dispersion") for lm in (pg.get("landmarks") or [])]
        gg, hh = _groups(gr), _groups(hr)
        for i in range(min(len(gg), len(hh), len(mm))):
            a, b, c = gg[i].get("errorHalf"), hh[i].get("errorHalf"), mm[i]
            if a and b and c and a > 0 and b > 0 and c > 0:
                G.append(math.log(a)); H.append(math.log(b)); M.append(math.log(c))
    gr3 = grubbs_three(G, H, M)
    if not gr3:
        return {"available": False, "note": f"only {len(G)} complete G/H2/M triplets (need >= 5)"}
    sg = math.sqrt(gr3["var_a"]) if gr3["var_a"] > 0 else NA
    sh = math.sqrt(gr3["var_b"]) if gr3["var_b"] > 0 else NA
    sm = math.sqrt(gr3["var_c"]) if gr3["var_c"] > 0 else NA
    ratio = sm / sg if sg and sg == sg else NA
    lo, hi = sd_ratio_ci(gr3["n"], ratio)
    return {"available": True, "n": gr3["n"], "sigma_G": sg, "sigma_H2": sh, "sigma_M": sm,
            "sigma_M_over_G": ratio, "ci": [lo, hi],
            "varRaw": {k: gr3[k] for k in gr3 if k.startswith("var")},
            "note": "G and H2 are DIFFERENT PEOPLE, so this triple carries no shared-person "
                    "covariance and needs no c-correction. Compare it against the {D,G,M} "
                    "triple in the main scorer; the difference IS c_hat."}


def render(out):
    f = lambda v: "n/a" if v != v else f"{v:.3f}"          # noqa: E731
    p = lambda v: "n/a" if v != v else f"{v:.1f}%"          # noqa: E731
    L = ["# Inter-rater reliability -- G vs H2", "",
         f"Panels paired: **{out['nPairs']}** "
         f"({out['join']['byLetter']} by letter, {out['join']['byIoU']} by box overlap after a "
         f"letter disagreement). Figures read by both: {out['join']['itemsBoth']}.", ""]
    if out["join"]["unmatched"]:
        L += [f"Unmatched panels: {len(out['join']['unmatched'])} -- "
              + ", ".join(f"{i}/{l} ({w})" for i, l, w in out["join"]["unmatched"][:10]), ""]

    s = out["structure"]
    L += ["## Structure (Tier P, two humans)", "",
          "| quantity | value | n |", "|---|---|---|",
          f"| panel-count agreement | {p(s['panelCountAgreementPct'])} | {s['nFigures']} figs |",
          f"| letter-set agreement | {p(s['letterSetAgreementPct'])} | {s['nFigures']} figs |",
          f"| per-letter box IoU, median | {f(s['panelIoUMedian'])} | {s['panelIoUn']} |",
          f"| per-letter box IoU, worst | {f(s['panelIoUWorst'])} | |",
          f"| letters assigned differently | {s['letterDisagreements']} | |", "",
          "A non-zero last row is the silent-mislabel class occurring **between two humans**, "
          "and it is the number that says how much of any machine-vs-human letter "
          "disagreement is convention rather than error.", ""]

    L += ["## Categorical channels (percent agreement AND kappa)", "",
          "| channel | agreement | kappa | n |", "|---|---|---|---|"]
    for k, v in out["categorical"].items():
        L.append(f"| {k} | {p(v['agreementPct'])} | {f(v['kappa'])} | {v['n']} |")
    L += ["", "Kappa is reported because ~91% of this corpus is SEM: on a channel that "
              "degenerate, 90% raw agreement can be worse than chance.", ""]

    ab = out["abstention"]
    L += ["## Abstention (`extractable`)", "",
          f"- panels both raters have a Stage B record for: **{ab['nJoined']}**, "
          f"agreement {p(ab['agreementJoinedPct'])}, kappa {f(ab['kappaJoined'])}",
          f"- panels only one rater has a record for: **{ab['nOneSided']}**", ""]
    if ab["disagreements"]:
        L += ["| figure | panel | route | G | H2 |", "|---|---|---|---|---|"]
        for d in ab["disagreements"][:20]:
            L.append(f"| {d['item']} | {d['letter']} | {d['route']} | {d['G']} | {d['H2']} |")
        L.append("")
    else:
        L += ["No `extractable` disagreements.", ""]
    L += [ab["note"], "",
          "This channel is the reason `Lyst2012_F7` is in the subset: the paper states no "
          "dispersion type, the correct answer is to abstain, and whether two people abstain "
          "in the same place is the behaviour least likely to be shared.", ""]

    L += ["## Numeric channels (marks matched by index, not by label)", "",
          "| channel | median | worst | s_w | RC = 2.77 s_w | ICC(A,1) | n |",
          "|---|---|---|---|---|---|---|"]
    for k, v in out["numeric"].items():
        L.append(f"| {k} | {p(v['medianPct'])} | {p(v['worstPct'])} | {p(v['swPct'])} | "
                 f"{p(v['rcPct'])} | {f(v['iccA1'])} | {v['n']} |")
    L += ["", "**RC here is the inter-rater reproducibility coefficient.** The pre-registered "
              "noise-floor ratio `R_floor = median|M-G| / RC_intra` should be recomputed "
              "against this RC as well; the two answer different questions and the write-up "
              "needs both.", ""]

    for k, v in out["numeric"].items():
        ba = v.get("blandAltman")
        if not ba:
            continue
        L += [f"### Bland-Altman, log(H2/G), {k}", "",
              f"- bias **{ba['biasPct']:+.1f}%** (95% CI +/-{ba['biasCiHalfPct']:.1f} pp)",
              f"- 95% limits of agreement **[{ba['loaLoPct']:+.1f}%, {ba['loaHiPct']:+.1f}%]** "
              f"(each limit +/-{ba['loaCiHalfPct']:.1f} pp)",
              f"- n = {ba['n']}", ""]

    g = out["grubbs"]
    L += ["## Grubbs on {G, H2, M}", ""]
    if not g.get("available"):
        L += [f"Not available: {g.get('note')}", ""]
    else:
        L += [f"- n = {g['n']} log-dispersion triplets",
              f"- sigma_G = {f(g['sigma_G'])}, sigma_H2 = {f(g['sigma_H2'])}, "
              f"sigma_M = {f(g['sigma_M'])}",
              f"- **sigma_M / sigma_G = {f(g['sigma_M_over_G'])}** "
              f"(95% CI [{f(g['ci'][0])}, {f(g['ci'][1])}])", "", g["note"], ""]

    L += ["## c_hat (shared-person covariance)", "", out["cHat"]["note"], ""]
    return "\n".join(L) + "\n"


# ============================================================ selftest
def selftest():
    failed = []

    def check(name, cond, detail=""):
        print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
        if not cond:
            failed.append(name)

    print("inter_rater selftest")

    # a perfectly agreeing pair
    same = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0), (5.0, 5.0)]
    check("ICC(A,1) = 1 when the raters agree exactly", abs(icc_a1(same) - 1.0) < 1e-9)
    check("RC = 0 when the raters agree exactly", rel_stats(same)["rcPct"] < 1e-9)

    # a pure constant multiplicative offset: consistency perfect, ABSOLUTE agreement is not
    off = [(a, b * 1.20) for a, b in same]
    check("ICC(A,1) penalises a constant +20% offset", icc_a1(off) < 0.98, f"{icc_a1(off):.4f}")
    ba = bland_altman_log(off)
    check("Bland-Altman recovers the +20% bias", abs(ba["biasPct"] - 20.0) < 0.5,
          f"{ba['biasPct']:.2f}")
    check("Bland-Altman LoA collapse when the offset is constant",
          abs(ba["loaHiPct"] - ba["loaLoPct"]) < 1e-6)

    # kappa: 90% raw agreement on a degenerate channel is near-worthless
    deg = [("SEM", "SEM")] * 18 + [("SD", "SEM"), ("SEM", "SD")]
    k = cohen_kappa(deg)
    check("kappa exposes a degenerate channel that scores 90% raw",
          sum(1 for a, b in deg if a == b) / len(deg) == 0.9 and k < 0.1, f"kappa={k:.3f}")
    check("kappa = 1 on perfect agreement",
          abs(cohen_kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")]) - 1.0) < 1e-9)

    # IoU
    b1 = {"x": 0, "y": 0, "width": 10, "height": 10}
    check("IoU of identical boxes is 1", abs(iou(b1, b1) - 1.0) < 1e-9)
    check("IoU of disjoint boxes is 0",
          iou(b1, {"x": 100, "y": 0, "width": 10, "height": 10}) == 0)

    # Grubbs recovers injected variances, and the ratio behaves
    import random as _r
    rng = _r.Random(7)
    T = [rng.gauss(0, 1) for _ in range(400)]
    A = [t + rng.gauss(0, 0.10) for t in T]
    B = [t + rng.gauss(0, 0.10) for t in T]
    C = [t + rng.gauss(0, 0.05) for t in T]
    g = grubbs_three(A, B, C)
    check("Grubbs recovers sigma_a ~ 0.10", abs(math.sqrt(g["var_a"]) - 0.10) < 0.03,
          f"{math.sqrt(g['var_a']):.4f}")
    check("Grubbs recovers sigma_c ~ 0.05", abs(math.sqrt(g["var_c"]) - 0.05) < 0.03,
          f"{math.sqrt(g['var_c']):.4f}")
    check("Grubbs refuses n < 5", grubbs_three(A[:4], B[:4], C[:4]) is None)

    # the shared-person confound: one TERM of the sec.1.3 algebra -- a component shared by
    # two instruments inflates the third's Grubbs variance. The net bias direction of the
    # full estimator is unknown (amendment A2); this asserts the c' term in isolation.
    shared = [rng.gauss(0, 0.08) for _ in range(400)]
    A2 = [t + s + rng.gauss(0, 0.06) for t, s in zip(T, shared)]
    B2 = [t + s + rng.gauss(0, 0.06) for t, s in zip(T, shared)]
    g2 = grubbs_three(A2, B2, C)
    check("shared error between the first two instruments INFLATES the third's variance",
          g2["var_c"] > g["var_c"],
          f"{g2['var_c']:.5f} vs {g['var_c']:.5f}")

    # the join reports a letter disagreement instead of dropping the panel
    def rec(item, letter, reader, box, mean, eh):
        return {"item_id": item, "panelLetter": letter, "reader": reader, "extractable": True,
                "structure": [{"bbox": {"x": 0, "y": 0, "width": 100, "height": 100},
                               "panels": [{"letter": letter, "bbox": box}]}],
                "characterization": {"panels": [{"charType": "bar", "series": [{"role": "control"}],
                                                 "statistics": {"dispersion": {"type": "SEM"}}}]},
                "extraction": {"method": "bar-endpoints",
                               "groups": [{"name": "x", "mean": mean, "errorHalf": eh}]}}
    box = {"x": 0, "y": 0, "width": 40, "height": 40}
    gs = [rec("F1", "A", "GF-human", box, 10.0, 2.0)]
    hs = [rec("F1", "B", "DK-human", box, 10.1, 2.1)]
    prs, info = join_panels(gs, hs)
    check("a letter disagreement still pairs, via box overlap", len(prs) == 1 and info["byIoU"] == 1,
          f"{len(prs)} pairs, byIoU={info['byIoU']}")
    check("the letter disagreement is counted, not hidden", info["byLetter"] == 0)

    # The abstention channel. `ingest_annotations.py:423` writes a non-extractable panel as
    # a short record with `panel_item` and `anon_id` and NO `item_id` and NO `panelLetter`,
    # so the identity has to be rebuilt from the key and the panel-item suffix or the
    # record never joins -- which made `extractable` a channel that could only ever agree.
    def flat(anon, letter, extractable=False):
        return {"panel_item": f"{anon}_p{letter}", "anon_id": anon, "session": "S01",
                "extractable": extractable, "charType": "micrograph",
                "ambiguities": [], "notes": ""}

    gs2 = [rec("F2", "A", "GF-human", box, 10.0, 2.0)]
    hs2 = [flat("dn07_beef", "A")]
    hkey = {"dn07_beef": "F2"}
    prs2, info2 = join_panels(gs2, hs2, {}, hkey)
    check("a non-extractable record joins on the rebuilt (figure, letter) identity",
          len(prs2) == 1, f"{len(prs2)} pairs")
    check("panel_identity recovers the letter from the panel_item suffix",
          panel_identity(hs2[0], hkey) == ("F2", "A"),
          str(panel_identity(hs2[0], hkey)))
    check("panel_identity gives up rather than guess when the key is missing",
          panel_identity(hs2[0], {}) is None)

    # end to end: G calls panel B extractable, H2 abstains on it. That has to be a scored
    # disagreement, and the abstention record must not take the reader guard down with it.
    import shutil as _sh
    import tempfile as _tf
    tmp = pathlib.Path(_tf.mkdtemp(prefix="ir-selftest-"))
    try:
        gstore = [rec("F2", "A", "GF-human", box, 10.0, 2.0),
                  rec("F2", "B", "GF-human", box, 11.0, 2.0)]
        hstore = [rec("F2", "A", "DK-human", box, 10.1, 2.1), flat("dn07_beef", "B")]
        for who, recs in (("greg", gstore), ("dan", hstore)):
            (tmp / who / "gt").mkdir(parents=True, exist_ok=True)
            (tmp / who / "gt" / "human_gt.jsonl").write_text(
                "\n".join(json.dumps(x) for x in recs) + "\n", encoding="utf-8")
        (tmp / "dan" / "keys").mkdir(parents=True, exist_ok=True)
        (tmp / "dan" / "keys" / "plan.key.json").write_text(json.dumps(
            {"sessions": [{"session": "S01",
                           "items": [{"anon_id": "dn07_beef", "item_id": "F2"}]}]}),
            encoding="utf-8")
        rep = analyse(tmp / "greg", tmp / "dan")
        check("a store mixing coded panels with abstentions is accepted", rep["nPairs"] == 2,
              f"{rep['nPairs']} pairs")
        ex = rep["categorical"]["extractable"]
        check("the extractable channel can now disagree",
              ex["n"] == 2 and ex["agreementPct"] == 50.0,
              f"n={ex['n']} agreement={ex['agreementPct']}")
        d = rep["abstention"]["disagreements"]
        check("the abstention is reported as G=True / H2=False on the right panel",
              len(d) == 1 and d[0]["letter"] == "B" and d[0]["G"] is True
              and d[0]["H2"] is False, str(d))
        check("charType still reads off a non-extractable record",
              rep["categorical"]["charType"]["n"] == 2)
    finally:
        _sh.rmtree(tmp, ignore_errors=True)

    print(("\nFAILED: " + ", ".join(failed)) if failed else "\nall checks passed")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--greg", default=str(HERE), help="Greg's data root (default: this dir)")
    ap.add_argument("--dan", default=str(HERE / "dan"), help="Dan's data root")
    ap.add_argument("--run", help="prediction run under pred/, to fit Grubbs on {G,H2,M}")
    ap.add_argument("--out", help="write the markdown here (default: <dan>/inter-rater.md)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())

    out = analyse(a.greg, a.dan, a.run)
    md = render(out)
    dest = pathlib.Path(a.out) if a.out else pathlib.Path(a.dan) / "inter-rater.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(md, encoding="utf-8")
    dest.with_suffix(".json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(md)
    print(f"[written] {dest}")


if __name__ == "__main__":
    main()
