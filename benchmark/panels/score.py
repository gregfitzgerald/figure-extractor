#!/usr/bin/env python3
"""score.py -- PANEL-DECOMPOSITION scorer.

Panel detection fails in four distinguishable ways, and lumping them into one accuracy
number hides which one you have:

  * LOCALISATION -- the boxes are in roughly the right places but loose or clipped.
    Measured by per-panel IoU (median, worst, and the share of panels at >=0.9 and >=0.5).
  * COUNT        -- the figure was split into the wrong number of pieces. Measured
    directly, and against the CAPTION's own count, because the caption states it.
  * ASSIGNMENT   -- the box called "B" is not panel B. This is the silent one: every
    downstream number is then attributed to the wrong sub-experiment, exactly the failure
    the series tier found for mark->arm binding. Reported as its own rate, restricted to
    panels that WERE localised, so it cannot hide behind a localisation failure.
  * CALIBRATION  -- when the detector says it is unsure, is it? Abstention is only worth
    anything if it fires on the figures that are actually wrong; abstaining on figures you
    would have got right is a cost, and that trade is reported as a net figure count.

Every metric is stratified by measured gutter bucket, layout class (guillotine vs
non-guillotine), label placement and panel content type. The stratification IS the
deliverable: it says WHERE a detector breaks, which is what you fix.

Run:
  python3 benchmark/panels/score.py --run baseline_caption
  python3 benchmark/panels/score.py --run baseline_caption --md benchmark/panels/RESULTS_scored.md
  python3 benchmark/panels/score.py --selftest        # prove the metrics catch each failure
"""
import argparse, collections, itertools, json, math, pathlib, random, re, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
TASKS = HERE / "tasks"
PRED = HERE / "predictions"

IOU_HIT = 0.5          # a panel counts as LOCALISED at or above this
IOU_TIGHT = 0.9        # ... and as TIGHTLY localised at or above this


# ------------------------------------------------------------------ geometry
def as_box(b):
    """Accept {x,y,width,height} or [x,y,w,h]; return (x0,y0,x1,y1) floats."""
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
    """One-to-one GT->prediction assignment maximising total IoU. Exact for the small
    cardinalities a figure has; greedy fallback if the permutation space explodes."""
    ng, npd = len(gt_boxes), len(pred_boxes)
    if not ng or not npd:
        return {}
    M = [[iou(g, p) for p in pred_boxes] for g in gt_boxes]
    space = math.perm(max(ng, npd), min(ng, npd))
    if space <= 200000:
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
        out[g], _ = p, used.add(p)
    return out


def norm_label(s):
    if s is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


CAP_LETTER = re.compile(r"\(([A-Za-z])\)")


# ------------------------------------------------------------------ scoring core
def score_figure(gt, pred, abstain_at):
    """All per-figure and per-panel facts for one figure. `pred` may be None (no answer)."""
    gpan = gt["panels"]
    gboxes = [as_box(p["bbox"]) for p in gpan]
    gcore = [as_box(p["bboxCore"]) for p in gpan]
    ppan = (pred or {}).get("panels") or []
    pboxes = [as_box(p.get("bbox")) for p in ppan]
    m = match(gboxes, pboxes)

    panels = []
    for i, gp in enumerate(gpan):
        j = m.get(i)
        v = iou(gboxes[i], pboxes[j]) if j is not None else 0.0
        # lenient variant: some detectors trim the panel letter off an outside-placed
        # label; scoring against the label-free box too keeps that from masquerading as a
        # localisation failure (reported alongside, never instead of, the strict number)
        vlen = max(v, iou(gcore[i], pboxes[j])) if j is not None else 0.0
        plabel = ppan[j].get("label") if j is not None else None
        # reading-order fallback: a detector that returns boxes without letters is read
        # as claiming reading order, which is what the tool's a/b/c labelling means
        if j is not None and (plabel is None or plabel == ""):
            plabel = chr(ord("A") + reading_order(pboxes).index(j))
        lab_ok = (j is not None and v >= IOU_HIT
                  and norm_label(plabel) == norm_label(gp["label"]))
        panels.append({
            "label": gp["label"], "contentType": gp["contentType"],
            "labelDrawn": gp["labelDrawn"], "labelContrast": gp.get("labelContrast"),
            "iou": v, "iouLenient": vlen, "matched": j is not None,
            "hit": v >= IOU_HIT, "tight": v >= IOU_TIGHT,
            "predLabel": plabel, "labelCorrect": lab_ok,
            "silentMislabel": (v >= IOU_HIT and not lab_ok),
        })

    n_gt, n_pred = len(gpan), len(ppan)
    fp = [j for j in range(n_pred) if j not in set(m.values())
          or iou(gboxes[[g for g, p in m.items() if p == j][0]], pboxes[j]) < IOU_HIT]
    letters = [x.upper() for x in gt["expectedLetters"]]
    conf = (pred or {}).get("confidence")
    abstained = bool((pred or {}).get("abstain")) or (conf is not None and conf < abstain_at)
    wrong = (n_pred != n_gt or any(not p["hit"] for p in panels)
             or any(p["silentMislabel"] for p in panels))
    return {
        "id": gt["id"], "level": gt["level"], "layoutClass": gt["layoutClass"],
        "layoutName": gt["layoutName"], "gutterBucket": gt["gutter"]["bucket"],
        "gutterPx": gt["gutter"]["measuredPx"], "labelPlacement": gt["labelPlacement"],
        "sharedAxes": gt["sharedAxes"], "hasDistractors": bool(gt["distractors"]),
        "nGt": n_gt, "nPred": n_pred, "countExact": n_pred == n_gt,
        "overSplit": n_pred > n_gt, "underSplit": n_pred < n_gt,
        "captionLetters": len(letters), "captionHonoured": (
            None if not letters else n_pred == len(letters)),
        "falsePositives": len(fp), "panels": panels,
        "confidence": conf, "abstained": abstained, "answered": not abstained,
        "wrong": wrong, "noPrediction": pred is None,
    }


def reading_order(boxes):
    """Indices of `boxes` in panel reading order: rows top-to-bottom (a row = boxes whose
    vertical centres sit within half a median height), left-to-right within a row."""
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


# ------------------------------------------------------------------ aggregation
def agg(figs):
    pans = [p for f in figs for p in f["panels"]]
    ious = [p["iou"] for p in pans]
    loc = [p for p in pans if p["hit"]]
    # `figExact` below counts an abstained figure as right whenever the answer it declined
    # to give would have been right -- which flatters a detector that abstains a lot. The
    # answered-only variant is the one that says what shipping this detector buys you.
    ansd = [f for f in figs if not f["abstained"]]
    return {
        "answered": len(ansd),
        "figExactAnswered": (sum(1 for f in ansd if not f["wrong"]) / len(ansd))
                            if ansd else float("nan"),
        "figures": len(figs), "panels": len(pans),
        "iouMedian": statistics.median(ious) if ious else 0.0,
        "iouMean": sum(ious) / len(ious) if ious else 0.0,
        "iouWorst": min(ious) if ious else 0.0,
        "pct90": sum(p["tight"] for p in pans) / len(pans) if pans else 0.0,
        "pct50": sum(p["hit"] for p in pans) / len(pans) if pans else 0.0,
        "iouLenientMedian": statistics.median([p["iouLenient"] for p in pans]) if pans else 0.0,
        "countAcc": sum(f["countExact"] for f in figs) / len(figs) if figs else 0.0,
        "overSplit": sum(f["overSplit"] for f in figs) / len(figs) if figs else 0.0,
        "underSplit": sum(f["underSplit"] for f in figs) / len(figs) if figs else 0.0,
        "missed": sum(1 for p in pans if not p["matched"]),
        "falsePositives": sum(f["falsePositives"] for f in figs),
        "labelAccLocalised": (sum(p["labelCorrect"] for p in loc) / len(loc)) if loc else 0.0,
        "silentMislabel": sum(p["silentMislabel"] for p in pans) / len(pans) if pans else 0.0,
        "figExact": sum(1 for f in figs if not f["wrong"]) / len(figs) if figs else 0.0,
    }


def strata(figs, key, panel_key=None):
    """Group figures (or panels) by a key and aggregate each group."""
    out = collections.OrderedDict()
    if panel_key:
        by = collections.defaultdict(list)
        for f in figs:
            for p in f["panels"]:
                by[p[panel_key]].append(p)
        for k in sorted(by):
            pans = by[k]
            ious = [p["iou"] for p in pans]
            loc = [p for p in pans if p["hit"]]
            out[k] = {"panels": len(pans), "iouMedian": statistics.median(ious),
                      "pct90": sum(p["tight"] for p in pans) / len(pans),
                      "pct50": sum(p["hit"] for p in pans) / len(pans),
                      "labelAccLocalised": (sum(p["labelCorrect"] for p in loc) / len(loc))
                                           if loc else float("nan"),
                      "silentMislabel": sum(p["silentMislabel"] for p in pans) / len(pans)}
        return out
    by = collections.defaultdict(list)
    for f in figs:
        by[f[key]].append(f)
    for k in sorted(by, key=str):
        out[k] = agg(by[k])
    return out


def abstention(figs):
    """Is the detector's low-confidence flag worth anything? An abstention is USEFUL when
    the answer would have been wrong and WASTED when it would have been right."""
    a_w = sum(1 for f in figs if f["abstained"] and f["wrong"])
    a_r = sum(1 for f in figs if f["abstained"] and not f["wrong"])
    n_w = sum(1 for f in figs if not f["abstained"] and f["wrong"])
    n_r = sum(1 for f in figs if not f["abstained"] and not f["wrong"])
    ans = a_r + a_w + n_r + n_w
    return {
        "coverage": (n_r + n_w) / ans if ans else 0.0,
        "abstained": a_r + a_w,
        "errorRateAll": (a_w + n_w) / ans if ans else 0.0,
        "errorRateAnswered": n_w / (n_r + n_w) if (n_r + n_w) else 0.0,
        "precision": a_w / (a_w + a_r) if (a_w + a_r) else float("nan"),
        "recall": a_w / (a_w + n_w) if (a_w + n_w) else float("nan"),
        "net": a_w - a_r,  # errors caught minus correct answers thrown away
    }


# ------------------------------------------------------------------ reporting
def fmt_row(name, a):
    return (f"    {name:<18}{a['figures']:>5}{a['panels']:>7}{a['iouMedian']:>9.3f}"
            f"{a['pct90']:>8.0%}{a['pct50']:>8.0%}{a['countAcc']:>8.0%}"
            f"{a['labelAccLocalised']:>8.0%}{a['figExact']:>9.0%}")


HDR = (f"    {'stratum':<18}{'figs':>5}{'pans':>7}{'medIoU':>9}{'>=.9':>8}{'>=.5':>8}"
       f"{'count':>8}{'label':>8}{'exact':>9}")


def report(figs, run, out=sys.stdout, md=None):
    A = agg(figs)
    L = []
    p = L.append
    p(f"PANEL-DECOMPOSITION SCORE -- run '{run}'")
    p(f"  figures {A['figures']}   panels {A['panels']}"
      f"   (no prediction for {sum(f['noPrediction'] for f in figs)})")
    p("")
    p("  LOCALISATION")
    p(f"    per-panel IoU     median {A['iouMedian']:.3f}   mean {A['iouMean']:.3f}"
      f"   worst {A['iouWorst']:.3f}")
    p(f"    panels IoU >= 0.9 {A['pct90']:.1%}      IoU >= 0.5 {A['pct50']:.1%}"
      f"      never matched {A['missed']}")
    p(f"    lenient median IoU (panel letter excluded from the GT box) "
      f"{A['iouLenientMedian']:.3f}")
    p("  COUNT")
    p(f"    exact panel count {A['countAcc']:.1%}   over-split {A['overSplit']:.1%}"
      f"   under-split {A['underSplit']:.1%}   spurious boxes {A['falsePositives']}")
    cap = [f for f in figs if f["captionHonoured"] is not None]
    if cap:
        p(f"    caption states the count for {len(cap)} figures; matched for "
          f"{sum(f['captionHonoured'] for f in cap) / len(cap):.1%} of them")
    p("  ASSIGNMENT (the silent failure)")
    p(f"    localised panels given the RIGHT letter {A['labelAccLocalised']:.1%}")
    p(f"    silent mislabels (well-localised, wrong letter) {A['silentMislabel']:.1%}"
      f" of all panels")
    p(f"  WHOLE FIGURE EXACTLY RIGHT  {A['figExact']:.1%}"
      f"   (all figures; an abstention that would have been right still counts here)")
    p(f"    ANSWERED-ONLY exactly right {A['figExactAnswered']:.1%}"
      f"   over the {A['answered']} figures actually answered")
    ab = abstention(figs)
    p("  ABSTENTION")
    p(f"    coverage {ab['coverage']:.1%}   abstained on {ab['abstained']} figures")
    p(f"    error rate: all figures {ab['errorRateAll']:.1%} -> answered only "
      f"{ab['errorRateAnswered']:.1%}")
    p(f"      ('wrong' = wrong panel count, or any panel below the IoU >= {IOU_HIT} "
      f"localisation threshold, or any silent mislabel)")
    p(f"    abstention precision {ab['precision']:.2f}  recall {ab['recall']:.2f}"
      f"   net figures saved {ab['net']:+d}")
    for title, key, pkey in (("by gutter (measured)", "gutterBucket", None),
                             ("by layout class", "layoutClass", None),
                             ("by label placement", "labelPlacement", None),
                             ("by difficulty level", "level", None)):
        p("")
        p(f"  {title}")
        p(HDR)
        for k, a in strata(figs, key, pkey).items():
            p(fmt_row(str(k), a))
    p("")
    p("  by panel content type (panel-level)")
    p(f"    {'content':<18}{'pans':>7}{'medIoU':>9}{'>=.9':>8}{'>=.5':>8}{'label':>8}"
      f"{'silentMis':>11}")
    for k, s in strata(figs, None, "contentType").items():
        p(f"    {str(k):<18}{s['panels']:>7}{s['iouMedian']:>9.3f}{s['pct90']:>8.0%}"
          f"{s['pct50']:>8.0%}{s['labelAccLocalised']:>8.0%}{s['silentMislabel']:>11.0%}")
    p("")
    p("  worst figures (lowest median panel IoU)")
    ranked = sorted(figs, key=lambda f: statistics.median([q["iou"] for q in f["panels"]]))
    p(f"    {'id':<34}{'gutter':<8}{'layout':<17}{'gt':>3}{'pred':>5}{'medIoU':>9}"
      f"{'label':>7}")
    for f in ranked[:12]:
        med = statistics.median([q["iou"] for q in f["panels"]])
        lok = sum(q["labelCorrect"] for q in f["panels"])
        p(f"    {f['id']:<34}{f['gutterBucket']:<8}{f['layoutName']:<17}{f['nGt']:>3}"
          f"{f['nPred']:>5}{med:>9.3f}{lok:>4}/{len(f['panels'])}")
    text = "\n".join(L)
    print(text, file=out)
    if md:
        pathlib.Path(md).write_text("# Panel-decomposition score\n\n```\n" + text + "\n```\n")
        print(f"\n  wrote {md}")
    return A


# ------------------------------------------------------------------ IO
def load_gt(ids=None):
    man = json.loads((CORPUS / "manifest.json").read_text())
    ids = ids or man["ids"]
    return {i: json.loads((CORPUS / f"{i}.pgt.json").read_text()) for i in ids}


def load_preds(run):
    path = PRED / f"{run}.jsonl"
    if not path.exists():
        sys.exit(f"no predictions at {path}")
    amap = json.loads((TASKS / "anon_map.json").read_text())
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        key = rec.get("task") or rec.get("id")
        cid = amap.get(key, key)
        out[cid] = rec
    return out


# ------------------------------------------------------------------ selftest
def perfect_predictions(gts):
    out = {}
    for cid, g in gts.items():
        out[cid] = {"task": cid, "confidence": 0.95, "abstain": False,
                    "panels": [{"label": p["label"], "bbox": dict(p["bbox"]), "conf": 0.95}
                               for p in g["panels"]]}
    return out


def mutate(preds, kind, rng):
    import copy
    out = copy.deepcopy(preds)
    for cid, r in out.items():
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
            pans.append({"label": "Z", "conf": 0.5, "bbox": {
                "x": b["x"] + 3, "y": b["y"] + 3, "width": max(8, b["width"] // 6),
                "height": max(8, b["height"] // 6)}})
        elif kind == "merge2" and len(pans) >= 2:
            a, b = pans[0]["bbox"], pans[1]["bbox"]
            x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
            x1 = max(a["x"] + a["width"], b["x"] + b["width"])
            y1 = max(a["y"] + a["height"], b["y"] + b["height"])
            pans[0]["bbox"] = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
            pans.pop(1)
        elif kind == "abstain-all":
            r["abstain"] = True
            r["confidence"] = 0.1
    return out


def run_selftest():
    gts = load_gt()
    rng = random.Random(7)
    base = perfect_predictions(gts)

    def sc(preds, abstain_at=0.5):
        return [score_figure(gts[c], preds.get(c), abstain_at) for c in gts]

    fails = []

    def check(name, cond, detail):
        print(f"    {'PASS' if cond else 'FAIL'}  {name:<46} {detail}")
        if not cond:
            fails.append(name)

    print("SELFTEST -- injected failures must move the metric that owns them\n")
    A0 = agg(sc(base))
    check("perfect prediction scores perfectly",
          A0["iouMedian"] == 1.0 and A0["countAcc"] == 1.0
          and A0["labelAccLocalised"] == 1.0 and A0["pct90"] == 1.0,
          f"medIoU {A0['iouMedian']:.3f} count {A0['countAcc']:.0%} "
          f"label {A0['labelAccLocalised']:.0%}")

    prev = 1.0
    mono = True
    line = []
    for d in (5, 20, 60):
        a = agg(sc(mutate(base, f"shift{d}", rng)))
        line.append(f"{d}px->{a['iouMedian']:.3f}")
        mono = mono and a["iouMedian"] < prev
        prev = a["iouMedian"]
    check("IoU degrades monotonically with a box shift", mono, "  ".join(line))

    a = agg(sc(mutate(base, "shift5", rng)))
    check("a 5px shift is caught by IoU but not by count",
          a["iouMedian"] < 1.0 and a["countAcc"] == 1.0,
          f"medIoU {a['iouMedian']:.3f}, count still {a['countAcc']:.0%}")

    sw = sc(mutate(base, "swaplabels", rng))
    a = agg(sw)
    nmulti = sum(1 for f in sw if f["nGt"] >= 2)
    check("swapped panel letters -> assignment falls, geometry does not",
          a["iouMedian"] == 1.0 and a["labelAccLocalised"] < 1.0
          and sum(f["countExact"] for f in sw) == len(sw)
          and sum(p["silentMislabel"] for f in sw for p in f["panels"]) == 2 * nmulti,
          f"label {a['labelAccLocalised']:.0%}, {2*nmulti} silent mislabels, "
          f"medIoU {a['iouMedian']:.3f}")

    dp = sc(mutate(base, "droppanel", rng))
    a = agg(dp)
    check("a dropped panel -> count + recall fall",
          a["countAcc"] < 1.0 and a["missed"] == sum(1 for f in dp if f["nGt"] >= 2)
          and a["pct50"] < 1.0,
          f"count {a['countAcc']:.0%}, {a['missed']} panels never matched, "
          f">=0.5 {a['pct50']:.0%}")

    sp = sc(mutate(base, "spurious", rng))
    a = agg(sp)
    check("a spurious box -> count + false positives, IoU intact",
          a["countAcc"] == 0.0 and a["falsePositives"] == len(sp) and a["iouMedian"] == 1.0,
          f"count {a['countAcc']:.0%}, {a['falsePositives']} FPs, "
          f"medIoU {a['iouMedian']:.3f}")

    mg = sc(mutate(base, "merge2", rng))
    a = agg(mg)
    check("two panels merged -> under-split and IoU collapse",
          a["underSplit"] > 0 and a["pct50"] < A0["pct50"],
          f"under-split {a['underSplit']:.0%}, >=0.5 {a['pct50']:.0%} "
          f"(was {A0['pct50']:.0%})")

    ab = abstention(sc(mutate(base, "abstain-all", rng)))
    check("abstaining on everything while being right is penalised",
          ab["coverage"] == 0.0 and ab["net"] < 0 and ab["precision"] == 0.0,
          f"coverage {ab['coverage']:.0%}, net {ab['net']:+d}, "
          f"precision {ab['precision']:.2f}")

    # calibrated abstention: wrong on half the figures, and flags exactly those
    half = dict(base)
    bad = mutate(base, "droppanel", random.Random(11))
    mixed = {}
    for k, cid in enumerate(gts):
        if k % 2 == 0 and gts[cid]["nPanels"] >= 2:
            r = dict(bad[cid]); r["abstain"] = True
            mixed[cid] = r
        else:
            mixed[cid] = half[cid]
    figs = sc(mixed)
    ab = abstention(figs)
    check("calibrated abstention: flags the wrong ones only",
          ab["precision"] == 1.0 and ab["recall"] == 1.0 and ab["net"] > 0
          and ab["errorRateAnswered"] == 0.0,
          f"precision {ab['precision']:.2f} recall {ab['recall']:.2f} "
          f"net {ab['net']:+d}, answered-error {ab['errorRateAnswered']:.0%}")

    nolab = {c: {"task": c, "confidence": 0.9,
                 "panels": [{"bbox": dict(p["bbox"])} for p in gts[c]["panels"]]}
             for c in gts}
    figs = sc(nolab)
    ng = [f for f in figs if f["layoutClass"] == "non-guillotine"]
    gu = [f for f in figs if f["layoutClass"] == "guillotine"]
    check("unlabelled boxes are read as READING ORDER (right for grids, wrong for pinwheels)",
          agg(gu)["labelAccLocalised"] > 0.95 and agg(ng)["labelAccLocalised"] < 0.8,
          f"guillotine {agg(gu)['labelAccLocalised']:.0%} vs "
          f"non-guillotine {agg(ng)['labelAccLocalised']:.0%}")

    missing = {c: base[c] for i, c in enumerate(gts) if i % 3}
    figs = sc(missing)
    check("a missing prediction scores as a total miss, not a crash",
          sum(f["noPrediction"] for f in figs) == len(gts) - len(missing)
          and agg(figs)["pct50"] < 1.0,
          f"{sum(f['noPrediction'] for f in figs)} figures unanswered")

    print(f"\n  {len(fails)} failed" if fails else "\n  all selftests passed")
    return 1 if fails else 0


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="predictions/<run>.jsonl")
    ap.add_argument("--md", help="also write the report to this markdown file")
    ap.add_argument("--abstain-at", type=float, default=0.5,
                    help="confidence below this counts as an abstention")
    # Selection only -- it changes WHICH figures are reported, never how any of them is
    # scored. Used to report the pre-existing L1-L5 ladder separately from the L6-L8
    # figures added later, so a corpus extension cannot be mistaken for a metric change.
    ap.add_argument("--ids-matching", metavar="REGEX",
                    help="score only corpus ids matching this regex (e.g. '^(L[1-5]|C_)')")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return run_selftest()
    if not args.run:
        ap.error("--run RUN or --selftest")
    gts = load_gt()
    if args.ids_matching:
        rx = re.compile(args.ids_matching)
        gts = {c: g for c, g in gts.items() if rx.search(c)}
        if not gts:
            sys.exit(f"--ids-matching {args.ids_matching!r} selected no corpus figures")
    preds = load_preds(args.run)
    figs = [score_figure(gts[c], preds.get(c), args.abstain_at) for c in gts]
    label = args.run if not args.ids_matching else f"{args.run}  [ids matching {args.ids_matching}]"
    report(figs, label, md=args.md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
