#!/usr/bin/env python3
"""score.py -- SERIES / GROUP PARSING scorer.

The headline is a MIS-ASSIGNMENT RATE, not an accuracy, because this error class is
silent and catastrophic: a correctly-read mean+SD bound to the wrong arm computes the
effect backwards, and nothing downstream catches it (WHITE-PAPER-LOG s9/s10).

The scorer deliberately splits parsing into the two halves that WHITE-PAPER-LOG s10
predicts have different owners:

  * STRUCTURE (the candidate ML win) -- did the reader carve the marks into the right
    clusters at all? Measured label-free: `structural mis-assignment` uses the
    permutation of the reader's series ids onto the GT's that maximises agreement, and
    `ARI` (adjusted Rand index) measures the partition itself.
  * NAMING (agent work: legend text -> semantic label) -- having clustered correctly,
    did it read the legend and call each cluster by the right name? Measured by
    `legend label accuracy` + swatch localisation.

  * BOUND MIS-ASSIGNMENT (the headline) = the composition of the two: the fraction of
    marks that end up attached to the WRONG NAMED ARM. That is the quantity a
    meta-analysis actually suffers from, and it is what the end-to-end check scores.

END-TO-END: every mark's GT pixel is pushed through the SAME affine the tool uses
(harness/calibrate.py) to recover data values, then re-aggregated per arm USING THE
READER'S ASSIGNMENT. Localization is held perfect on purpose, so any error is pure
parsing. Reported as per-arm mean/dispersion % error against R's descriptives, plus
the metric that matters: the EFFECT SIGN-FLIP rate (did Control-vs-Treated come out
backwards?).

Run:
  python3 benchmark/series/score.py --run firstpass
  python3 benchmark/series/score.py --tier stress --run firstpass_stress
  python3 benchmark/series/score.py --selftest      # validate the machinery
  python3 benchmark/series/score.py --run firstpass --md benchmark/series/RESULTS_scored.md
"""
import argparse, collections, itertools, json, math, pathlib, re, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
TASKS = HERE / "tasks"
PRED = HERE / "predictions"
sys.path.insert(0, str(HERE.parent / "harness"))
from calibrate import py_calibrate  # noqa: E402


def set_tier(tier):
    """Point the scorer at a tier's corpus + tasks (see make_tasks.tier_dirs)."""
    global CORPUS, TASKS
    sfx = f"_{tier}" if tier else ""
    CORPUS = HERE / f"corpus{sfx}"
    TASKS = HERE / f"tasks{sfx}"

UNKNOWN = {"unknown", "unassigned", "none", "", None}


# ------------------------------------------------------------------ utilities
def norm(s):
    """Label normalisation: case/space/punctuation-insensitive, numeric-aware."""
    if s is None:
        return ""
    t = str(s).strip().lower()
    try:
        return f"{float(t):g}"
    except ValueError:
        pass
    return re.sub(r"[^a-z0-9]+", "", t)


def pct(rec, tru):
    return 100 * abs(rec - tru) / abs(tru) if tru else abs(rec - tru)


def ari(pairs):
    """Adjusted Rand index from [(true_label, pred_label)] -- partition agreement,
    independent of what either side CALLS the clusters."""
    n = len(pairs)
    if n < 2:
        return 1.0
    tab = collections.Counter(pairs)
    a = collections.Counter(t for t, _ in pairs)
    b = collections.Counter(p for _, p in pairs)
    c2 = lambda x: x * (x - 1) / 2
    sij = sum(c2(v) for v in tab.values())
    sa = sum(c2(v) for v in a.values())
    sb = sum(c2(v) for v in b.values())
    exp = sa * sb / c2(n)
    mx = (sa + sb) / 2
    return 1.0 if mx == exp else (sij - exp) / (mx - exp)


def optimal_map(gt_ids, ag_ids, overlap):
    """Injective agent-id -> gt-id map maximising total mark overlap (brute force for
    the small cardinalities this corpus has; greedy fallback if it ever explodes)."""
    if not ag_ids or not gt_ids:
        return {}
    ng, na = len(gt_ids), len(ag_ids)
    space = math.perm(max(ng, na), min(ng, na))
    if space <= 200000:
        best, bestsc = {}, -1
        if na >= ng:
            for perm in itertools.permutations(ag_ids, ng):
                sc = sum(overlap.get((g, a), 0) for g, a in zip(gt_ids, perm))
                if sc > bestsc:
                    bestsc, best = sc, {a: g for g, a in zip(gt_ids, perm)}
        else:
            for perm in itertools.permutations(gt_ids, na):
                sc = sum(overlap.get((g, a), 0) for g, a in zip(perm, ag_ids))
                if sc > bestsc:
                    bestsc, best = sc, {a: g for a, g in zip(ag_ids, perm)}
        return best
    used, out = set(), {}
    for (g, a), _ in sorted(overlap.items(), key=lambda kv: -kv[1]):
        if g in used or a in out:
            continue
        out[a] = g
        used.add(g)
    return out


def ece(pairs, nbins=10):
    bins = [[] for _ in range(nbins)]
    for c, ok in pairs:
        c = min(max(float(c), 0.0), 1.0)
        bins[min(int(c * nbins), nbins - 1)].append((c, ok))
    n = len(pairs) or 1
    e, tab = 0.0, []
    for i, bk in enumerate(bins):
        if not bk:
            continue
        conf = sum(c for c, _ in bk) / len(bk)
        acc = sum(1 for _, ok in bk if ok) / len(bk)
        e += (len(bk) / n) * abs(acc - conf)
        tab.append((f"{i/nbins:.1f}-{(i+1)/nbins:.1f}", len(bk), conf, acc))
    return e, tab


# ------------------------------------------------------------------ loading
def load_gt():
    ids = json.loads((CORPUS / "manifest.json").read_text())["ids"]
    return {i: json.loads((CORPUS / f"{i}.sgt.json").read_text()) for i in ids}


def load_visibility():
    p = CORPUS / "visibility.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_preds(run):
    files = [PRED / f"{run}.jsonl"] if run else sorted(PRED.glob("*.jsonl"))
    rows = {}
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line:
                d = json.loads(line)
                rows[d["task"]] = d
    return rows


# ------------------------------------------------------------------ per-chart scoring
def series_gt_label(s):
    return s.get("legendLabelText") or s.get("directLabelText") or s.get("label")


def series_gt_swatch(s):
    return s.get("legendKeyPx") or s.get("directLabelPx")


def score_chart(b, pred, vis):
    marks = {m["markId"]: m for m in b["marks"]}
    gt_s = [s["seriesId"] for s in b["series"]]
    gt_g = [g["groupId"] for g in b["groups"]]
    ag_series = pred.get("series") or []
    ag_groups = pred.get("groups") or []
    asn = {a["markId"]: a for a in pred.get("assignments", [])}

    # ---- reader series/group id -> GT id, by the reader's own LABELS -------------
    def label_map(gt_defs, gt_key, ag_defs, gt_label_fn, lenient_single=False):
        # a chart with a single un-labelled group (a scatter) has no tick text to read,
        # so a lone reader group binds to the lone GT group by identity, not by string
        if lenient_single and len(gt_defs) == 1 and len(ag_defs) == 1:
            return {ag_defs[0].get("id"): gt_defs[0][gt_key]}
        by_norm = collections.defaultdict(list)
        for a in ag_defs:
            by_norm[norm(a.get("label"))].append(a.get("id"))
        out = {}
        for d in gt_defs:
            hits = by_norm.get(norm(gt_label_fn(d)), [])
            if len(hits) == 1:
                out[hits[0]] = d[gt_key]
        return out

    smap_label = label_map(b["series"], "seriesId", ag_series, series_gt_label)
    gmap_label = label_map(b["groups"], "groupId", ag_groups, lambda g: g["label"],
                           lenient_single=True)

    # ---- reader ids -> GT ids, by best STRUCTURAL overlap ------------------------
    ov_s, ov_g = collections.Counter(), collections.Counter()
    for mid, m in marks.items():
        a = asn.get(mid)
        if not a:
            continue
        if a.get("series") not in UNKNOWN:
            ov_s[(m["seriesId"], a["series"])] += 1
        if a.get("group") not in UNKNOWN:
            ov_g[(m["groupId"], a["group"])] += 1
    ag_sids = sorted({a["series"] for a in asn.values() if a.get("series") not in UNKNOWN})
    ag_gids = sorted({a["group"] for a in asn.values() if a.get("group") not in UNKNOWN})
    smap_opt = optimal_map(gt_s, ag_sids, ov_s)
    gmap_opt = optimal_map(gt_g, ag_gids, ov_g)

    # ---- per-mark verdicts -------------------------------------------------------
    rows = []
    for mid, m in marks.items():
        a = asn.get(mid, {})
        s_raw, g_raw = a.get("series"), a.get("group")
        rec = {
            "markId": mid, "role": m["role"],
            "gt_series": m["seriesId"], "gt_group": m["groupId"],
            "visibility": vis.get(b["id"], {}).get(mid, "visible"),
            "conf": a.get("conf", pred.get("confidence", 0.5)),
            "missing": mid not in asn,
            "abstain_s": s_raw in UNKNOWN, "abstain_g": g_raw in UNKNOWN,
            "bound_series": smap_label.get(s_raw),
            "bound_group": gmap_label.get(g_raw),
            "struct_series": smap_opt.get(s_raw),
            "struct_group": gmap_opt.get(g_raw),
            "raw_series": s_raw, "raw_group": g_raw,
        }
        # a mark nobody assigned is treated as an (implicit) abstention, and reported
        if rec["missing"]:
            rec["abstain_s"] = rec["abstain_g"] = True
        rows.append(rec)

    # ---- legend / naming ---------------------------------------------------------
    ag_by_id = {a.get("id"): a for a in ag_series}
    legend = []
    for s in b["series"]:
        aid = next((k for k, v in smap_opt.items() if v == s["seriesId"]), None)
        a = ag_by_id.get(aid)
        gt_lab = series_gt_label(s)
        ok_lab = bool(a) and norm(a.get("label")) == norm(gt_lab)
        sw_gt = series_gt_swatch(s)
        d_sw = None
        if a and a.get("swatchPx") and sw_gt:
            d_sw = math.dist((a["swatchPx"].get("px", 0), a["swatchPx"].get("py", 0)),
                             (sw_gt["px"], sw_gt["py"]))
        legend.append({"seriesId": s["seriesId"], "gtLabel": gt_lab,
                       "predLabel": (a or {}).get("label"), "labelOk": ok_lab,
                       "swatchDist": d_sw, "hasSwatch": sw_gt is not None})

    counts = {"nSeries_true": len(gt_s), "nSeries_pred": pred.get("nSeries"),
              "nGroups_true": len(gt_g), "nGroups_pred": pred.get("nGroups")}
    counts["nSeries_ok"] = counts["nSeries_pred"] == counts["nSeries_true"]
    counts["nGroups_ok"] = counts["nGroups_pred"] == counts["nGroups_true"]
    return rows, legend, counts, smap_label, gmap_label


# ------------------------------------------------------------------ end-to-end
DISP_FIELD = {"SD": "sd", "SEM": "sem", "SE": "sem", "CI95": "ci_half"}


def recover_values(b):
    cal = b["calibration"]
    pts = [{"px": m["px"], "py": m["py"]} for m in b["marks"]]
    dv = py_calibrate(cal["calPixels"], cal["calVals"], pts)
    return {m["markId"]: dv[i] for i, m in enumerate(b["marks"])}


def arm_estimates(b, values, assign):
    """assign: markId -> (groupId, seriesId) as the READER bound it (None = unbound).
    Returns {arm: {stat: value}} rebuilt from the GT pixels under THAT assignment."""
    ct = b["chartType"]
    buckets = collections.defaultdict(list)
    for m in b["marks"]:
        arm = assign.get(m["markId"])
        if arm:
            buckets[arm].append(m)
    out = {}
    for arm, ms in buckets.items():
        by_role = collections.defaultdict(list)
        for m in ms:
            by_role[m["role"]].append(m)
        e = {}
        if ct in ("grouped-bar", "line"):
            tops, caps = by_role.get("top", []), by_role.get("cap", [])
            if len(tops) == 1:
                e["mean"] = values[tops[0]["markId"]]["y"]
            if len(tops) == 1 and len(caps) == 1:
                e["disp"] = abs(values[caps[0]["markId"]]["y"] - values[tops[0]["markId"]]["y"])
            e["illformed"] = len(tops) != 1 or (bool(caps) and len(caps) != 1)
        elif ct == "box":
            q1, med, q3 = by_role.get("q1", []), by_role.get("med", []), by_role.get("q3", [])
            if len(med) == 1:
                e["median"] = values[med[0]["markId"]]["y"]
            if len(q1) == 1 and len(q3) == 1:
                e["iqr"] = abs(values[q3[0]["markId"]]["y"] - values[q1[0]["markId"]]["y"])
            e["illformed"] = not (len(q1) == len(med) == len(q3) == 1)
        elif ct == "stacked-bar":
            segs = by_role.get("seg", [])
            if len(segs) == 1:
                e["value"] = segs[0]["segTopValue"] - segs[0]["segBotValue"]
            e["illformed"] = len(segs) != 1
        elif ct == "scatter":
            xs = [values[m["markId"]]["x"] for m in ms]
            ys = [values[m["markId"]]["y"] for m in ms]
            if len(xs) >= 3:
                mx, my = statistics.mean(xs), statistics.mean(ys)
                sxy = sum((a - mx) * (bq - my) for a, bq in zip(xs, ys))
                sxx = sum((a - mx) ** 2 for a in xs)
                syy = sum((bq - my) ** 2 for bq in ys)
                if sxx > 0 and syy > 0:
                    e["r"] = sxy / math.sqrt(sxx * syy)
                    e["slope"] = sxy / sxx
            e["illformed"] = len(xs) < 3
        out[arm] = e
    return out


def end_to_end(b, rows, key="bound"):
    """Rebuild each arm from GT pixels under the reader's binding; compare to R."""
    values = recover_values(b)
    assign = {}
    for r in rows:
        s = r[f"{key}_series"]
        g = r[f"{key}_group"]
        if s and g:
            assign[r["markId"]] = f"{g}|{s}"
    truth_assign = {m["markId"]: f'{m["groupId"]}|{m["seriesId"]}' for m in b["marks"]}
    est = arm_estimates(b, values, assign)
    ref = arm_estimates(b, values, truth_assign)
    D = b["descriptives"]
    ct = b["chartType"]
    dfield = DISP_FIELD.get(b.get("dispersionType") or "SD", "sd")

    errs = {"central": [], "dispersion": []}
    illformed = sum(1 for e in est.values() if e.get("illformed"))
    for arm, tru in D.items():
        e = est.get(arm, {})
        if ct in ("grouped-bar", "line"):
            if "mean" in e:
                errs["central"].append(pct(e["mean"], tru["mean"]))
            if "disp" in e and tru.get(dfield):
                errs["dispersion"].append(pct(e["disp"], tru[dfield]))
        elif ct == "box":
            if "median" in e:
                errs["central"].append(pct(e["median"], tru["median"]))
            if "iqr" in e:
                errs["dispersion"].append(pct(e["iqr"], tru["iqr"]))
        elif ct == "stacked-bar":
            if "value" in e:
                errs["central"].append(pct(e["value"], tru["value"]))
        elif ct == "scatter":
            if "r" in e:
                errs["central"].append(100 * abs(e["r"] - tru["r"]))
            if "slope" in e:
                errs["dispersion"].append(pct(e["slope"], tru["slope"]))

    # ---- the meta-analytic catastrophe: does the EFFECT come out backwards? ------
    flips, comps = 0, 0
    if ct == "scatter":
        for arm, tru in D.items():
            e = est.get(arm, {})
            if "r" in e and abs(tru["r"]) > 0.05:
                comps += 1
                flips += (e["r"] * tru["r"] < 0)
    else:
        stat = {"box": "median", "stacked-bar": "value"}.get(ct, "mean")
        est_stat = {"box": "median", "stacked-bar": "value"}.get(ct, "mean")
        for g in b["groups"]:
            base = f'{g["groupId"]}|{b["series"][0]["seriesId"]}'
            if base not in D:
                continue
            for s in b["series"][1:]:
                arm = f'{g["groupId"]}|{s["seriesId"]}'
                if arm not in D:
                    continue
                t = D[arm][stat] - D[base][stat]
                eb, ea = est.get(base, {}), est.get(arm, {})
                if est_stat in eb and est_stat in ea and abs(t) > 1e-9:
                    comps += 1
                    flips += ((ea[est_stat] - eb[est_stat]) * t < 0)
    return {
        "central_median": statistics.median(errs["central"]) if errs["central"] else None,
        "central_worst": max(errs["central"]) if errs["central"] else None,
        "dispersion_median": statistics.median(errs["dispersion"]) if errs["dispersion"] else None,
        "dispersion_worst": max(errs["dispersion"]) if errs["dispersion"] else None,
        "arms_recovered": len([1 for a in D if a in est]), "arms_true": len(D),
        "illformed_arms": illformed, "sign_flips": flips, "sign_comparisons": comps,
        "floor_ok": all(
            (ref.get(a, {}).get("illformed") is False) for a in D) if ref else None,
    }


# ------------------------------------------------------------------ self-test
def synth_predictions(gt, mode, noise=0.15, seed=7):
    """Synthetic readers that prove each metric fires independently:
      oracle  -- perfect: everything must read 0 / 1.0 (also validates that the GT
                 pixels round-trip through the affine back to R's descriptives).
      swapped -- perfect CLUSTERS, two series' legend labels exchanged: structure
                 stays perfect, naming and the bound headline blow up. This is the
                 naming half failing alone.
      noisy   -- correct labels, but a fraction of marks scattered into the wrong
                 cluster: naming stays perfect, structure degrades. This is the
                 structural half failing alone."""
    import random
    rng = random.Random(seed)
    out = []
    for i, (cid, b) in enumerate(sorted(gt.items())):
        smap = {s["seriesId"]: series_gt_label(s) for s in b["series"]}
        if mode == "swapped" and len(b["series"]) >= 2 and i % 2 == 0:
            a, bb = b["series"][0]["seriesId"], b["series"][1]["seriesId"]
            smap[a], smap[bb] = smap[bb], smap[a]
        sids = [s["seriesId"] for s in b["series"]]
        def pick(m):
            if mode == "noisy" and len(sids) > 1 and rng.random() < noise:
                return rng.choice([x for x in sids if x != m["seriesId"]])
            return m["seriesId"]
        out.append({
            "task": cid, "nSeries": len(b["series"]), "nGroups": len(b["groups"]),
            "confidence": 0.95,
            "series": [{"id": s["seriesId"], "label": smap[s["seriesId"]],
                        "swatchPx": series_gt_swatch(s) or {"px": 0, "py": 0}}
                       for s in b["series"]],
            "groups": [{"id": g["groupId"], "label": g["label"]} for g in b["groups"]],
            "assignments": [{"markId": m["markId"], "series": pick(m),
                             "group": m["groupId"], "conf": 0.95} for m in b["marks"]],
            "method": "synthetic",
        })
    return out


# ------------------------------------------------------------------ report
def run_scoring(gt, vis, preds, name, out):
    def pr(*a):
        line = " ".join(str(x) for x in a)
        out.append(line)
        print(line)

    charts = []
    for task, p in preds.items():
        cid = task if task in gt else None
        if cid is None:
            amap = json.loads((TASKS / "anon_map.json").read_text()) if (TASKS / "anon_map.json").exists() else {}
            cid = amap.get(task)
        if cid is None or cid not in gt:
            pr(f"  [warn] prediction '{task}' has no GT match -- skipped")
            continue
        b = gt[cid]
        rows, legend, counts, smap, gmap = score_chart(b, p, vis)
        e2e = end_to_end(b, rows, "bound")
        charts.append({"id": cid, "b": b, "rows": rows, "legend": legend,
                       "counts": counts, "e2e": e2e, "pred": p})
    if not charts:
        pr("no predictions to score.")
        return None

    allrows = [(c, r) for c in charts for r in c["rows"]]
    N = len(allrows)

    def rate(sel, key):
        sub = [r for c, r in allrows if sel(c, r)]
        if not sub:
            return None, 0
        bad = sum(1 for r in sub if not r[f"abstain_{key[0]}"]
                  and r[f"bound_{key}"] != r[f"gt_{key}"])
        return bad / len(sub), len(sub)

    def srate(sel, key):
        sub = [r for c, r in allrows if sel(c, r)]
        if not sub:
            return None, 0
        bad = sum(1 for r in sub if not r[f"abstain_{key[0]}"]
                  and r[f"struct_{key}"] != r[f"gt_{key}"])
        return bad / len(sub), len(sub)

    always = lambda c, r: True
    mis_s, _ = rate(always, "series")
    mis_g, _ = rate(always, "group")
    st_s, _ = srate(always, "series")
    st_g, _ = srate(always, "group")
    arm_bad = sum(1 for _, r in allrows if not r["abstain_s"] and not r["abstain_g"]
                  and (r["bound_series"] != r["gt_series"] or r["bound_group"] != r["gt_group"]))
    abst = sum(1 for _, r in allrows if r["abstain_s"])
    missing = sum(1 for _, r in allrows if r["missing"])
    visible = [(c, r) for c, r in allrows if r["visibility"] != "hidden"]
    mis_s_vis = sum(1 for _, r in visible if not r["abstain_s"]
                    and r["bound_series"] != r["gt_series"]) / len(visible)

    pr(f"SERIES/GROUP PARSING SCORE -- run={name}   charts={len(charts)}/{len(gt)}   marks={N}")
    pr("")
    pr("== HEADLINE: mis-assignment (a mark bound to the WRONG arm) ==")
    pr(f"  series mis-assignment rate (bound, by the reader's own labels) : {mis_s:.4f}"
       f"   ({round(mis_s*N)}/{N} marks)")
    pr(f"    ... excluding marks physically HIDDEN under other ink        : {mis_s_vis:.4f}"
       f"   (n={len(visible)})")
    pr(f"  group  mis-assignment rate                                     : {mis_g:.4f}")
    pr(f"  ARM (group x series) mis-assignment rate                       : {arm_bad/N:.4f}")
    pr(f"  abstained marks (declined, not counted as errors)              : {abst}/{N}"
       f" = {abst/N:.4f}   (of which never returned: {missing})")
    pr("")
    pr("== the two halves (WHITE-PAPER-LOG s10) ==")
    pr(f"  STRUCTURE  structural series mis-assignment (best-permutation) : {st_s:.4f}")
    pr(f"  STRUCTURE  structural group  mis-assignment                    : {st_g:.4f}")
    aris = [ari([(r["gt_series"], r["raw_series"]) for r in c["rows"]
                 if not r["abstain_s"]]) for c in charts]
    pr(f"  STRUCTURE  mean ARI of the mark->series partition              : "
       f"{statistics.mean(aris):.4f}  (median {statistics.median(aris):.4f})")
    leg = [l for c in charts for l in c["legend"]]
    lab_ok = sum(1 for l in leg if l["labelOk"])
    pr(f"  NAMING     legend/direct label read correctly                  : "
       f"{lab_ok}/{len(leg)} = {lab_ok/len(leg):.4f}")
    sw = [l["swatchDist"] for l in leg if l["swatchDist"] is not None]
    if sw:
        pr(f"  NAMING     swatch localisation: median {statistics.median(sw):.1f}px, "
           f"within 20px {sum(1 for d in sw if d <= 20)}/{len(sw)}")

    pr("")
    pr("== counts (did it even see N series?) ==")
    cs = sum(1 for c in charts if c["counts"]["nSeries_ok"])
    cg = sum(1 for c in charts if c["counts"]["nGroups_ok"])
    pr(f"  nSeries exactly right : {cs}/{len(charts)}")
    pr(f"  nGroups exactly right : {cg}/{len(charts)}")
    for c in charts:
        if not (c["counts"]["nSeries_ok"] and c["counts"]["nGroups_ok"]):
            pr(f"    {c['id']}: series {c['counts']['nSeries_pred']} vs "
               f"{c['counts']['nSeries_true']}, groups {c['counts']['nGroups_pred']} vs "
               f"{c['counts']['nGroups_true']}")

    pr("")
    pr("== END-TO-END: does the parsed arm land on the RIGHT arm's numbers? ==")
    cen = [c["e2e"]["central_median"] for c in charts if c["e2e"]["central_median"] is not None]
    dis = [c["e2e"]["dispersion_median"] for c in charts if c["e2e"]["dispersion_median"] is not None]
    flips = sum(c["e2e"]["sign_flips"] for c in charts)
    comps = sum(c["e2e"]["sign_comparisons"] for c in charts)
    ill = sum(c["e2e"]["illformed_arms"] for c in charts)
    lost = sum(c["e2e"]["arms_true"] - c["e2e"]["arms_recovered"] for c in charts)
    if cen:
        pr(f"  per-arm central-tendency error : median {statistics.median(cen):.2f}%  "
           f"worst {max(c['e2e']['central_worst'] for c in charts if c['e2e']['central_worst'] is not None):.2f}%")
    else:
        pr("  per-arm central-tendency error : n/a -- NO arm could be bound to a named "
           "series (this reader names nothing, so nothing reaches a data schema)")
    if dis:
        pr(f"  per-arm dispersion error       : median {statistics.median(dis):.2f}%  "
           f"worst {max(c['e2e']['dispersion_worst'] for c in charts if c['e2e']['dispersion_worst'] is not None):.2f}%")
    pr(f"  EFFECT SIGN FLIPS (the catastrophe): {flips}/{comps} = "
       f"{(flips/comps if comps else 0):.4f}")
    pr(f"  arms never recovered (no marks bound to them) : {lost}")
    pr(f"  ill-formed arms (wrong number of marks bound) : {ill}")

    pr("")
    pr("== calibration / abstention ==")
    pairs = [(r["conf"], (not r["abstain_s"]) and r["bound_series"] == r["gt_series"])
             for _, r in allrows]
    e, tab = ece(pairs)
    mc = statistics.mean(c for c, _ in pairs)
    acc = sum(1 for _, ok in pairs if ok) / N
    pr(f"  mean per-mark confidence {mc:.3f} vs accuracy {acc:.3f}  (gap {mc-acc:+.3f})"
       f"   ECE {e:.3f}")
    for nm, n, cf, ac in tab:
        pr(f"    {nm:<10}{n:>5}{cf:>7.2f}{ac:>7.2f}")

    # ---- stratification -------------------------------------------------------
    def strat(title, keyfn):
        pr("")
        pr(f"== series mis-assignment by {title} ==")
        pr(f"  {'stratum':<22}{'bound':>8}{'struct':>8}{'marks':>7}{'charts':>7}")
        buck = collections.defaultdict(list)
        for c, r in allrows:
            for k in keyfn(c["b"]):
                buck[k].append((c, r))
        res = {}
        for k in sorted(buck):
            sub = buck[k]
            bad = sum(1 for _, r in sub if not r["abstain_s"] and r["bound_series"] != r["gt_series"])
            sbad = sum(1 for _, r in sub if not r["abstain_s"] and r["struct_series"] != r["gt_series"])
            nch = len({c["id"] for c, _ in sub})
            pr(f"  {str(k):<22}{bad/len(sub):>8.3f}{sbad/len(sub):>8.3f}{len(sub):>7}{nch:>7}")
            res[str(k)] = {"bound": bad / len(sub), "structural": sbad / len(sub),
                           "marks": len(sub), "charts": nch}
        return res

    by_type = strat("CHART TYPE", lambda b: [b["chartType"]])
    by_diff = strat("DIFFICULTY (a-priori)", lambda b: [b["difficulty"]])
    by_cue = strat("CUE TYPE", lambda b: [b["cueType"]])
    by_occ = strat("OCCLUSION (measured)", lambda b: [b["occlusion"]["bucket"]])
    by_leg = strat("LEGEND STYLE", lambda b: [b["legendStyle"]])
    by_tr = strat("TRAIT", lambda b: (b.get("traits") or ["-none-"]))
    by_lom = strat("LEGEND ORDER == PLOT ORDER",
                   lambda b: [str(b.get("legendOrderMatchesPlotOrder"))])

    pr("")
    pr("== per chart ==")
    pr(f"  {'chart':<30}{'bound':>7}{'struct':>7}{'ARI':>6}{'labels':>8}{'flips':>9}  notes")
    per_chart = []
    for c in charts:
        rws = c["rows"]
        nb = sum(1 for r in rws if not r["abstain_s"] and r["bound_series"] != r["gt_series"])
        ns = sum(1 for r in rws if not r["abstain_s"] and r["struct_series"] != r["gt_series"])
        a = ari([(r["gt_series"], r["raw_series"]) for r in rws if not r["abstain_s"]])
        lo = sum(1 for l in c["legend"] if l["labelOk"])
        note = []
        if not c["counts"]["nSeries_ok"]:
            note.append("nSeries wrong")
        if c["e2e"]["illformed_arms"]:
            note.append(f"{c['e2e']['illformed_arms']} ill-formed arms")
        labs = f"{lo}/{len(c['legend'])}"
        flp = f"{c['e2e']['sign_flips']}/{c['e2e']['sign_comparisons']}"
        pr(f"  {c['id']:<30}{nb/len(rws):>7.3f}{ns/len(rws):>7.3f}{a:>6.2f}"
           f"{labs:>8}{flp:>9}  {', '.join(note)}")
        per_chart.append({
            "id": c["id"], "chartType": c["b"]["chartType"],
            "difficulty": c["b"]["difficulty"], "cueType": c["b"]["cueType"],
            "legendStyle": c["b"]["legendStyle"], "occlusion": c["b"]["occlusion"]["bucket"],
            "marks": len(rws), "bound_misassign": nb / len(rws),
            "structural_misassign": ns / len(rws), "ari": a,
            "legend_label_ok": lo, "legend_n": len(c["legend"]),
            "nSeries_ok": c["counts"]["nSeries_ok"], "nGroups_ok": c["counts"]["nGroups_ok"],
            **{f"e2e_{k}": v for k, v in c["e2e"].items()},
        })

    return {
        "run": name, "charts": len(charts), "marks": N,
        "misassignment_series_bound": mis_s,
        "misassignment_series_bound_visible_only": mis_s_vis,
        "misassignment_group_bound": mis_g, "misassignment_arm_bound": arm_bad / N,
        "misassignment_series_structural": st_s,
        "misassignment_group_structural": st_g,
        "mean_ari": statistics.mean(aris),
        "legend_label_accuracy": lab_ok / len(leg),
        "swatch_median_px": statistics.median(sw) if sw else None,
        "abstention_rate": abst / N, "unreturned_marks": missing,
        "nSeries_exact": cs / len(charts), "nGroups_exact": cg / len(charts),
        "e2e_central_median": statistics.median(cen) if cen else None,
        "e2e_dispersion_median": statistics.median(dis) if dis else None,
        "e2e_sign_flip_rate": (flips / comps) if comps else None,
        "e2e_sign_flips": flips, "e2e_sign_comparisons": comps,
        "e2e_arms_lost": lost, "e2e_illformed_arms": ill,
        "ece": e, "mean_confidence": mc, "mark_accuracy": acc,
        "by_chart_type": by_type, "by_difficulty": by_diff, "by_cue": by_cue,
        "by_occlusion": by_occ, "by_legend_style": by_leg, "by_trait": by_tr,
        "by_legend_order_match": by_lom, "per_chart": per_chart,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None, help="predictions/<run>.jsonl (default: all)")
    ap.add_argument("--selftest", action="store_true",
                    help="score synthetic oracle + label-swapped readers")
    ap.add_argument("--tier", default="", help="'' (base) or 'stress'")
    ap.add_argument("--md", default=None, help="also write the console report as markdown")
    args = ap.parse_args()
    set_tier(args.tier)

    gt = load_gt()
    vis = load_visibility()
    out = []

    if args.selftest:
        for mode in ("oracle", "swapped", "noisy"):
            preds = {p["task"]: p for p in synth_predictions(gt, mode)}
            print(f"\n########## SELF-TEST: {mode} ##########")
            out.append(f"\n########## SELF-TEST: {mode} ##########")
            run_scoring(gt, vis, preds, f"selftest_{mode}", out)
        if args.md:
            pathlib.Path(args.md).write_text("```\n" + "\n".join(out) + "\n```\n")
        return

    preds = load_preds(args.run)
    summary = run_scoring(gt, vis, preds, args.run or "all", out)
    if summary:
        sp = PRED / (f"summary_{args.run}.json" if args.run else "summary.json")
        sp.write_text(json.dumps(summary, indent=2))
        print(f"\nmachine summary -> {sp}")
    if args.md:
        pathlib.Path(args.md).write_text("```\n" + "\n".join(out) + "\n```\n")
        print(f"markdown -> {args.md}")


if __name__ == "__main__":
    main()
