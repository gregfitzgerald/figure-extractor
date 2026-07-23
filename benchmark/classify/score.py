#!/usr/bin/env python3
"""score.py -- CHART-TYPE CLASSIFICATION scorer (the perception gate).

Joins vision-agent predictions (predictions/*.jsonl, keyed by anon task name) to
ground-truth labels (corpus/*.label.json) via tasks/anon_map.json, and scores the
classification the way the extraction pipeline actually cares about:

  * per-type accuracy (recall) + precision + F1, with support
  * macro-F1 and weighted-F1  (rare types are where extraction value concentrates)
  * confusion matrix, read STRUCTURALLY:
      - PRIORITY-FLIP errors: a confusion that changes the tool's extractionPriority
        (forest->bar flips derived/low -> primary/high; the catastrophic class)
      - cheap confusions (box<->violin: same priority) reported but discounted
  * calibration / ECE on the confidence field (10-bin reliability)
  * abstention behaviour (unknown/other): rate, and whether used on hard cases
  * auxiliary labels: dataProvenance, scaleY/scaleX accuracy, dispersionPresent
    (bool F1), nonDataElements (micro precision/recall/F1 over the ignore-list)
  * stratification of charType accuracy by library, by grammar, and by TIER
    (the plain-vs-dense contrast: does visual busyness degrade classification?)

Run:  python3 benchmark/classify/score.py                 # all predictions/*.jsonl
      python3 benchmark/classify/score.py --run firstpass # predictions/firstpass.jsonl
      python3 benchmark/classify/score.py --md out.md      # also write a markdown report
"""
import argparse, collections, glob, json, math, pathlib

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
TASKS = HERE / "tasks"
PRED = HERE / "predictions"

# --- extractionPriority, ported byte-for-byte from figure-extractor.html ------
NON_DATA = {"schematic", "micrograph", "flow-diagram"}
DERIVED = {"forest", "funnel"}
ORIGINAL = {"bar", "grouped-bar", "stacked-bar", "histogram", "line", "scatter",
            "box", "violin", "dose-response", "kaplan-meier", "roc", "bland-altman"}


def priority(ct, prov):
    if ct in NON_DATA:
        return "none"
    if ct in DERIVED:
        return "medium" if prov == "primary" else "low"
    if prov == "derived":
        return "low"
    if ct in ORIGINAL:
        return "high"
    return "medium"


def load_gt():
    gt = {}
    for p in CORPUS.glob("*.label.json"):
        d = json.loads(p.read_text())
        gt[d["id"]] = d
    return gt


def load_preds(run):
    files = [PRED / f"{run}.jsonl"] if run else sorted(PRED.glob("*.jsonl"))
    rows = {}
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rows[d["task"]] = d  # last wins
    return rows


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def ece(pairs, nbins=10):
    """pairs = [(confidence, correct_bool)]; returns (ECE, reliability table)."""
    bins = [[] for _ in range(nbins)]
    for c, ok in pairs:
        c = min(max(float(c), 0.0), 1.0)
        idx = min(int(c * nbins), nbins - 1)
        bins[idx].append((c, ok))
    n = len(pairs); e = 0.0; tab = []
    for i, b in enumerate(bins):
        if not b:
            continue
        conf = sum(c for c, _ in b) / len(b)
        acc = sum(1 for _, ok in b if ok) / len(b)
        e += (len(b) / n) * abs(acc - conf)
        tab.append((f"{i/nbins:.1f}-{(i+1)/nbins:.1f}", len(b), conf, acc))
    return e, tab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None, help="predictions/<run>.jsonl (default: all)")
    ap.add_argument("--md", default=None, help="also write a markdown report to this path")
    args = ap.parse_args()

    gt = load_gt()
    anon = json.loads((TASKS / "anon_map.json").read_text())
    preds = load_preds(args.run)

    # resolve anon -> real id, join to GT
    joined = []  # (id, gtdict, pred)
    unresolved = []
    for task, pr in preds.items():
        cid = anon.get(task)
        if cid is None or cid not in gt:
            unresolved.append(task); continue
        joined.append((cid, gt[cid], pr))

    N = len(joined)
    out = []
    def pr_(*a): out.append(" ".join(str(x) for x in a)); print(*a)

    pr_(f"CLASSIFICATION SCORE  ({N}/{len(gt)} corpus images predicted"
        + (f"; run={args.run}" if args.run else "") + ")")
    if unresolved:
        pr_(f"  [warn] {len(unresolved)} predictions had no GT match: {unresolved[:5]}")
    if N == 0:
        pr_("no predictions to score."); return

    # ---- charType: accuracy, per-type PRF, macro/weighted F1 -----------------
    types = sorted({g["charType"] for _, g, _ in joined})
    tp = collections.Counter(); fp = collections.Counter(); fn = collections.Counter()
    support = collections.Counter()
    correct = 0
    confusion = collections.Counter()  # (gt, pred)
    for cid, g, p in joined:
        t = g["charType"]; pc = p.get("charType", "MISSING")
        support[t] += 1
        confusion[(t, pc)] += 1
        if pc == t:
            correct += 1; tp[t] += 1
        else:
            fp[pc] += 1; fn[t] += 1
    acc = correct / N
    pr_(f"\n== charType ==\noverall accuracy: {acc:.3f}  ({correct}/{N})")
    pr_(f"{'type':<15}{'prec':>6}{'rec':>6}{'f1':>6}{'n':>5}")
    macro = []; weighted = 0.0
    allc = sorted(set(list(support) + [p.get('charType') for _,_,p in joined]))
    for t in sorted(support, key=lambda x: (-support[x], x)):
        p_, r_, f_ = prf(tp[t], fp[t], fn[t])
        pr_(f"{t:<15}{p_:>6.2f}{r_:>6.2f}{f_:>6.2f}{support[t]:>5}")
        macro.append(f_); weighted += f_ * support[t]
    macro_f1 = sum(macro) / len(macro) if macro else 0.0
    weighted_f1 = weighted / N
    pr_(f"macro-F1: {macro_f1:.3f}   weighted-F1: {weighted_f1:.3f}")

    # ---- confusion matrix + structural read ----------------------------------
    errs = [(cid, g, p) for cid, g, p in joined if p.get("charType") != g["charType"]]
    pr_(f"\n== confusions ({len(errs)} errors) ==")
    for (t, pc), c in sorted(confusion.items(), key=lambda kv: -kv[1]):
        if t == pc:
            continue
        gpri = priority(t, "primary"); ppri = priority(pc, "primary")
        flip = "  <-- PRIORITY FLIP" if gpri != ppri else "  (same priority)"
        pr_(f"  {t:>14} -> {pc:<14} x{c}{flip}")
    # priority-flip count using each row's actual provenance
    flips = 0
    for cid, g, p in joined:
        gp = priority(g["charType"], g.get("dataProvenance", "unknown"))
        pp = priority(p.get("charType", "?"), p.get("dataProvenance", "unknown"))
        if gp != pp:
            flips += 1
    pr_(f"priority-flip rate (extraction-routing errors): {flips}/{N} = {flips/N:.3f}")

    # ---- calibration / ECE ---------------------------------------------------
    pairs = [(p.get("confidence", 0.5), p.get("charType") == g["charType"]) for _, g, p in joined]
    e, tab = ece(pairs)
    mean_conf = sum(c for c, _ in pairs) / N
    pr_(f"\n== calibration ==\nmean confidence: {mean_conf:.3f}   accuracy: {acc:.3f}   "
        f"(gap {mean_conf-acc:+.3f})   ECE: {e:.3f}")
    pr_(f"  {'bin':<10}{'n':>4}{'conf':>7}{'acc':>7}")
    for name, n, conf, a in tab:
        pr_(f"  {name:<10}{n:>4}{conf:>7.2f}{a:>7.2f}")

    # ---- abstention ----------------------------------------------------------
    ABST = {"unknown", "other"}
    abst = [(cid, g, p) for cid, g, p in joined if p.get("charType") in ABST]
    # true abstention classes in this corpus (schematic/flow are named types, not abstain)
    pr_(f"\n== abstention (unknown/other) ==")
    pr_(f"  used on {len(abst)}/{N} = {len(abst)/N:.3f} of images")
    if abst:
        for cid, g, p in abst:
            pr_(f"    {cid}: true={g['charType']} tier={g['tier']} conf={p.get('confidence')}")

    # ---- auxiliary labels ----------------------------------------------------
    def acc_of(key_gt, key_pred=None):
        key_pred = key_pred or key_gt
        ok = sum(1 for _, g, p in joined if p.get(key_pred) == g.get(key_gt))
        return ok / N
    pr_(f"\n== auxiliary labels ==")
    pr_(f"  dataProvenance accuracy: {acc_of('dataProvenance'):.3f}")
    pr_(f"  scaleY accuracy:         {acc_of('scaleY'):.3f}")
    pr_(f"  scaleX accuracy:         {acc_of('scaleX'):.3f}")
    # dispersionPresent bool F1
    dtp = dfp = dfn = dtn = 0
    for _, g, p in joined:
        gg = bool(g.get("dispersionPresent")); pp = bool(p.get("dispersionPresent"))
        dtp += gg and pp; dfp += (not gg) and pp; dfn += gg and (not pp); dtn += (not gg) and (not pp)
    dp, dr, df = prf(dtp, dfp, dfn)
    pr_(f"  dispersionPresent: acc={(dtp+dtn)/N:.3f}  P={dp:.2f} R={dr:.2f} F1={df:.2f}"
        f"  (TP{dtp} FP{dfp} FN{dfn} TN{dtn})")
    # nonDataElements micro P/R/F1 over the ignore-list
    ntp = nfp = nfn = 0
    for _, g, p in joined:
        gs = set(g.get("nonDataElements", [])); ps = set(p.get("nonDataElements", []))
        ntp += len(gs & ps); nfp += len(ps - gs); nfn += len(gs - ps)
    np_, nr_, nf_ = prf(ntp, nfp, nfn)
    pr_(f"  nonDataElements (micro over ignore-list): P={np_:.2f} R={nr_:.2f} F1={nf_:.2f}")

    # ---- stratification ------------------------------------------------------
    def strat(keyfn, title):
        buck = collections.defaultdict(lambda: [0, 0])
        for cid, g, p in joined:
            k = keyfn(g)
            buck[k][1] += 1
            if p.get("charType") == g["charType"]:
                buck[k][0] += 1
        pr_(f"\n== charType accuracy by {title} ==")
        for k in sorted(buck):
            c, n = buck[k]
            pr_(f"  {k:<14} {c/n:.3f}  ({c}/{n})")
        return {k: (v[0], v[1]) for k, v in buck.items()}
    by_tier = strat(lambda g: g["tier"], "TIER (plain vs dense)")
    strat(lambda g: g["grammar"], "grammar family")
    strat(lambda g: g["library"], "library")

    # ---- machine summary -----------------------------------------------------
    summary = {
        "n_scored": N, "n_corpus": len(gt), "run": args.run,
        "accuracy": acc, "macro_f1": macro_f1, "weighted_f1": weighted_f1,
        "priority_flip_rate": flips / N, "ece": e, "mean_confidence": mean_conf,
        "abstention_rate": len(abst) / N,
        "aux": {"dataProvenance": acc_of("dataProvenance"), "scaleY": acc_of("scaleY"),
                "scaleX": acc_of("scaleX"),
                "dispersionPresent_f1": df, "nonDataElements_f1": nf_},
        "by_tier": {k: {"correct": v[0], "n": v[1], "acc": v[0]/v[1]} for k, v in by_tier.items()},
        "confusions": {f"{t}->{pc}": c for (t, pc), c in confusion.items() if t != pc},
    }
    spath = PRED / (f"summary_{args.run}.json" if args.run else "summary.json")
    spath.write_text(json.dumps(summary, indent=2))
    pr_(f"\nmachine summary -> {spath}")

    if args.md:
        pathlib.Path(args.md).write_text("```\n" + "\n".join(out) + "\n```\n")
        print(f"markdown -> {args.md}")


if __name__ == "__main__":
    main()
