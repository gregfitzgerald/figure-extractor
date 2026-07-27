#!/usr/bin/env python3
"""finalize_gt.py -- turn gen_panels.R's partial bundles into the PANEL ground truth.

R knows, exactly, which rectangle it ALLOCATED to each panel (`tile`) and where the
inner axes landed (`plotRect`). What a detector can actually reach, though, is the tight
box around the ink a panel DRAWS -- a tile has slack on the sides where nothing is
plotted. So the scoring target `bbox` is measured, not asserted: gen_panels.R re-rendered
every element alone on a white page with byte-identical geometry, and this script takes
the ink bounding box of that solo render.

It also measures the gutter that actually exists between neighbouring panels (which is
always >= the nominal gutter, because a panel's ink stops short of its tile), and buckets
every figure on the measured value -- the scorer stratifies on that, not on the knob.

Run:  python3 benchmark/panels/finalize_gt.py
      python3 benchmark/panels/finalize_gt.py --corpus benchmark/panels/corpus
"""
import argparse, json, pathlib, sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("finalize_gt.py needs numpy + Pillow (pip install numpy Pillow)")

HERE = pathlib.Path(__file__).resolve().parent
INK_MAX = 250          # luminance strictly below this counts as ink (catches grey92 grid)
FLUSH_PX = 2.0         # measured gap at or below this = panels are flush/abutting
# The gap is normalised by the figure dimension it is measured ALONG (a column gutter by
# width, a row gutter by height) because that is what a projection-profile detector
# thresholds against. 1.5% sits just under the current detector's 2.5% minimum gutter.
TIGHT_FRAC = 0.015
MED_FRAC = 0.040
ESCAPE_MAX = 15.0      # ink outside its own tile by more than this = a geometry bug


def ink_mask(path):
    a = np.asarray(Image.open(path).convert("L"))
    return a < INK_MAX


def ink_bbox(path):
    m = ink_mask(path)
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    return {"x": int(xs.min()), "y": int(ys.min()),
            "width": int(xs.max() - xs.min() + 1), "height": int(ys.max() - ys.min() + 1)}


def union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
    x1 = max(a["x"] + a["width"], b["x"] + b["width"])
    y1 = max(a["y"] + a["height"], b["y"] + b["height"])
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def overlap1d(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def measured_gutter(boxes):
    """Smallest gap between ADJACENT panels, where adjacency means the pair overlaps by
    >=30% (of the smaller extent) on the perpendicular axis -- i.e. true neighbours in a
    row or a column. Returns (gap_px, (i, j), axis) or (None, None, None)."""
    best, pair, axis = None, None, None
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ax1, ay1 = a["x"] + a["width"], a["y"] + a["height"]
            bx1, by1 = b["x"] + b["width"], b["y"] + b["height"]
            ovy = overlap1d(a["y"], ay1, b["y"], by1)
            ovx = overlap1d(a["x"], ax1, b["x"], bx1)
            gap, ax = None, None
            if ovy >= 0.30 * min(a["height"], b["height"]):
                gap = (b["x"] - ax1) if a["x"] < b["x"] else (a["x"] - bx1)
                ax = "x"
            elif ovx >= 0.30 * min(a["width"], b["width"]):
                gap = (b["y"] - ay1) if a["y"] < b["y"] else (a["y"] - by1)
                ax = "y"
            if gap is None:
                continue
            if best is None or gap < best:
                best, pair, axis = float(gap), (i, j), ax
    return best, pair, axis


def bucket(gap, denom):
    if gap is None:
        return "n/a"
    if gap <= FLUSH_PX:
        return "flush"
    if gap / denom <= TIGHT_FRAC:
        return "tight"
    if gap / denom <= MED_FRAC:
        return "medium"
    return "wide"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(HERE / "corpus"))
    args = ap.parse_args()
    CORPUS = pathlib.Path(args.corpus)
    ISO = CORPUS / "_iso"
    parts = sorted(CORPUS.glob("*.part.json"))
    if not parts:
        sys.exit(f"no *.part.json in {CORPUS} -- run: Rscript benchmark/panels/gen_panels.R")
    for old in CORPUS.glob("*.pgt.json"):
        old.unlink()

    ids, problems = [], []
    print(f"{'id':<34}{'layout':<20}{'gutter px':>10}  {'bucket':<8}{'panels':>7}")
    for p in parts:
        b = json.loads(p.read_text())
        W, H = b["figure"]["width"], b["figure"]["height"]
        comp = np.asarray(Image.open(CORPUS / b["image"]).convert("L"))
        panels = []
        for pan in b["panels"]:
            core = ink_bbox(ISO / pan["iso"]["content"])
            lab = ink_bbox(ISO / pan["iso"]["label"]) if pan["iso"].get("label") else None
            box = union(core, lab)
            if box is None:
                problems.append(f"{b['id']} panel {pan['label']}: solo render has NO ink")
                continue
            # How far a panel's ink reaches OUTSIDE the rectangle it was allocated. A few
            # px is normal and realistic (ggplot2 centres the last tick label on the axis
            # end, so it overhangs); a large value would mean the compositor is broken.
            t = pan["tile"]
            escape = round(max(t["x"] - box["x"], t["y"] - box["y"],
                               box["x"] + box["width"] - (t["x"] + t["width"]),
                               box["y"] + box["height"] - (t["y"] + t["height"])), 1)
            if escape > ESCAPE_MAX:
                problems.append(f"{b['id']} panel {pan['label']}: ink escapes its tile "
                                f"by {escape}px")
            panels.append({
                "index": pan["index"], "label": pan["label"],
                "contentType": pan["contentType"], "labelDrawn": pan["labelDrawn"],
                "bbox": box, "bboxCore": core, "labelBbox": lab, "inkEscapePx": escape,
                # how legible the drawn letter is against whatever it sits on, so a
                # scorer can separate "the detector could not read it" from "it is there"
                "labelContrast": (None if lab is None else int(np.ptp(
                    comp[lab["y"]:lab["y"] + lab["height"],
                         lab["x"]:lab["x"] + lab["width"]]))),
                "tile": {k: round(v, 2) for k, v in t.items()},
                "plotRect": (None if not pan.get("plotRect") else
                             {k: round(v, 2) for k, v in pan["plotRect"].items()}),
            })
        dist = []
        for d in b.get("distractors", []):
            dist.append({"kind": d["kind"], "bbox": ink_bbox(ISO / d["iso"]),
                         "rect": {k: round(v, 2) for k, v in d["rect"].items()}})
        gap, pair, gaxis = measured_gutter([q["bbox"] for q in panels])
        denom = W if gaxis == "x" else H
        bkt = bucket(gap, denom)
        gt = {
            "id": b["id"], "image": b["image"], "level": b["level"],
            "figure": b["figure"],
            "layoutName": b["layoutName"], "layoutClass": b["layoutClass"],
            "gutter": {"nominalPx": b["gutterNominalPx"],
                       "bucketNominal": b["gutterBucketNominal"],
                       "measuredPx": None if gap is None else round(gap, 1),
                       "measuredFrac": None if gap is None else round(gap / denom, 4),
                       "measuredAxis": gaxis, "bucket": bkt,
                       "tightestPair": None if pair is None else
                                       [panels[pair[0]]["label"], panels[pair[1]]["label"]]},
            "labelPlacement": b["labelPlacement"], "labelFormat": b["labelFormat"],
            "sharedAxes": bool(b["sharedAxes"]), "caption": b["caption"],
            "expectedLetters": b["expectedLetters"], "notes": b.get("notes", []),
            "nPanels": len(panels), "panels": panels, "distractors": dist,
            "gtMethod": ("bbox = ink bounding box of a solo render of that element with "
                         "geometry identical to the composite; tile = allocated rectangle; "
                         "plotRect = grid::deviceLoc of the inner axes"),
        }
        (CORPUS / f"{b['id']}.pgt.json").write_text(json.dumps(gt, indent=1))
        ids.append(b["id"])
        print(f"{b['id']:<34}{b['layoutName']:<20}"
              f"{('-' if gap is None else f'{gap:.1f}'):>10}  {bkt:<8}{len(panels):>7}")

    (CORPUS / "manifest.json").write_text(json.dumps(
        {"count": len(ids), "ids": ids,
         "nPanels": sum(json.loads((CORPUS / f"{i}.pgt.json").read_text())["nPanels"]
                        for i in ids)}, indent=1))
    tot = sum(json.loads((CORPUS / f"{i}.pgt.json").read_text())["nPanels"] for i in ids)
    print(f"\nwrote {len(ids)} GT bundles ({tot} panels) -> {CORPUS}/<id>.pgt.json")
    if problems:
        print("\nPROBLEMS:")
        for x in problems:
            print("  ", x)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
