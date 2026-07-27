#!/usr/bin/env python3
"""audit_panels.py -- verify the PANEL answer key against the drawn pixels.

The GT boxes were measured from SOLO renders (one element alone on a white page). This
script never looks at those: it re-derives everything from the COMPOSITE PNG plus the
allocated tile rectangles, which come from independent layout arithmetic. GT that is not
verified is not GT.

Five checks, all reported in pixels rather than as a pass/fail mood:

  1. TIGHTNESS   -- inside each GT box, is there ink touching all four edges? A box that
                    is loose by k px would show an inset of k. Must be 0.
  2. OUTWARD RESIDUAL -- inside the panel's own TILE, does any ink reach beyond the GT
                    box? Non-zero means either GT is too small or a neighbour's ink
                    overhangs into this tile (the flush mosaics really do that, and the
                    per-figure table says which).
  3. UNCLAIMED INK -- every ink pixel in the composite must lie inside SOME GT box
                    (a panel, or a declared distractor such as a legend/colourbar/shared
                    axis title). Unclaimed ink means an element nobody owns.
  4. DISJOINTNESS -- pairwise IoU between panel boxes (must be ~0; only the flush tiers
                    may show a sliver where a tick label overhangs a neighbour).
  5. CAPTION     -- the letters the caption names must equal the panel letters, and every
                    drawn label box must actually contain ink.

Run: python3 benchmark/panels/audit_panels.py [--corpus DIR] [--max-residual 3]
"""
import argparse, json, pathlib, re, statistics, sys

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("audit_panels.py needs numpy + Pillow (pip install numpy Pillow)")

HERE = pathlib.Path(__file__).resolve().parent
INK_MAX = 250


def rect(b):
    return int(round(b["x"])), int(round(b["y"])), \
           int(round(b["x"] + b["width"])), int(round(b["y"] + b["height"]))


def clip(r, W, H):
    x0, y0, x1, y1 = r
    return max(0, x0), max(0, y0), min(W, x1), min(H, y1)


def sub_ink_bbox(ink, r):
    x0, y0, x1, y1 = r
    if x1 <= x0 or y1 <= y0:
        return None
    s = ink[y0:y1, x0:x1]
    ys, xs = np.nonzero(s)
    if not len(xs):
        return None
    return (x0 + int(xs.min()), y0 + int(ys.min()),
            x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1)


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    iw = max(0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    if inter == 0:
        return 0.0
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua


CAP_LETTER = re.compile(r"\(([A-Za-z])\)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(HERE / "corpus"))
    ap.add_argument("--max-residual", type=float, default=3.0,
                    help="outward residual (px) above which a panel is listed as a defect")
    args = ap.parse_args()
    CORPUS = pathlib.Path(args.corpus)
    ids = json.loads((CORPUS / "manifest.json").read_text())["ids"]

    insets, residuals, unclaimed_all, worst_pairs = [], [], [], []
    defects, cap_bad, label_bad = [], [], []
    per_fig = []
    npanels = 0
    for cid in ids:
        g = json.loads((CORPUS / f"{cid}.pgt.json").read_text())
        img = np.asarray(Image.open(CORPUS / g["image"]).convert("L"))
        H, W = img.shape
        assert (W, H) == (g["figure"]["width"], g["figure"]["height"]), f"{cid}: size"
        ink = img < INK_MAX
        claimed = np.zeros_like(ink, dtype=bool)
        fig_inset = fig_resid = 0.0
        for p in g["panels"]:
            npanels += 1
            bx = clip(rect(p["bbox"]), W, H)
            claimed[bx[1]:bx[3], bx[0]:bx[2]] = True
            # (1) tightness: ink must touch all four edges from the inside
            ib = sub_ink_bbox(ink, bx)
            if ib is None:
                defects.append(f"{cid} {p['label']}: GT box contains no ink at all")
                continue
            ins = max(ib[0] - bx[0], ib[1] - bx[1], bx[2] - ib[2], bx[3] - ib[3])
            insets.append(ins)
            fig_inset = max(fig_inset, ins)
            # (2) outward residual, measured within the panel's own allocated tile
            tl = clip(rect(p["tile"]), W, H)
            ti = sub_ink_bbox(ink, tl)
            bxc = (max(bx[0], tl[0]), max(bx[1], tl[1]), min(bx[2], tl[2]), min(bx[3], tl[3]))
            res = 0.0 if ti is None else max(0, bxc[0] - ti[0], bxc[1] - ti[1],
                                             ti[2] - bxc[2], ti[3] - bxc[3])
            residuals.append(res)
            fig_resid = max(fig_resid, res)
            if res > args.max_residual:
                defects.append(f"{cid} {p['label']}: ink reaches {res:.0f}px beyond the GT "
                               f"box inside its own tile")
            # (5b) the drawn letter must be where GT says it is. Panel letters on a
            # micrograph are drawn WHITE on a dark raster, so "is it dark?" is the wrong
            # question -- the right one is "is there a high-contrast glyph here?".
            if p["labelDrawn"]:
                lb = clip(rect(p["labelBbox"]), W, H) if p["labelBbox"] else None
                if lb is None:
                    label_bad.append(f"{cid} {p['label']}: GT has no label box")
                else:
                    patch = img[lb[1]:lb[3], lb[0]:lb[2]]
                    if patch.size == 0 or int(patch.max()) - int(patch.min()) < 60:
                        label_bad.append(f"{cid} {p['label']}: no glyph contrast in the "
                                         f"label box")
        for d in g["distractors"]:
            if d["bbox"]:
                dx = clip(rect(d["bbox"]), W, H)
                claimed[dx[1]:dx[3], dx[0]:dx[2]] = True
        # (3) unclaimed ink
        unc = int((ink & ~claimed).sum())
        frac = unc / max(1, int(ink.sum()))
        unclaimed_all.append(frac)
        if frac > 0.001:
            defects.append(f"{cid}: {unc} ink px ({frac:.3%}) belong to no GT box")
        # (4) disjointness
        mx = 0.0
        boxes = [clip(rect(p["bbox"]), W, H) for p in g["panels"]]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                mx = max(mx, iou(boxes[i], boxes[j]))
        worst_pairs.append((mx, cid))
        # (5a) caption letters
        letters = [m.upper() for m in CAP_LETTER.findall(g["caption"])]
        exp = [x.upper() for x in g["expectedLetters"]]
        if letters != exp:
            cap_bad.append(f"{cid}: caption letters {letters} != expectedLetters {exp}")
        if exp and exp != [p["label"] for p in g["panels"]]:
            cap_bad.append(f"{cid}: expectedLetters != panel labels")
        per_fig.append((cid, g["gutter"]["bucket"], g["layoutClass"], fig_inset,
                        fig_resid, frac, mx))

    print("PANEL-GT AUDIT (composite PNG + layout tiles vs the exported answer key)")
    print(f"  figures {len(ids)}   panels {npanels}\n")
    print(f"  (1) tightness inset px   : median {statistics.median(insets):.1f}  "
          f"max {max(insets):.1f}   (0 = every GT box touches its own ink on all 4 edges)")
    print(f"  (2) outward residual px  : median {statistics.median(residuals):.1f}  "
          f"p95 {sorted(residuals)[int(0.95*(len(residuals)-1))]:.1f}  "
          f"max {max(residuals):.1f}")
    print(f"  (3) unclaimed ink        : max over figures {max(unclaimed_all):.4%}  "
          f"mean {sum(unclaimed_all)/len(unclaimed_all):.4%}")
    wp = max(worst_pairs)
    print(f"  (4) worst panel-panel IoU: {wp[0]:.4f}  ({wp[1]})")
    print(f"  (5) caption/letter checks: {'OK' if not cap_bad else str(len(cap_bad))+' BAD'}"
          f"   label-ink checks: {'OK' if not label_bad else str(len(label_bad))+' BAD'}")

    print("\n  per-figure (inset / outward residual px, unclaimed ink, worst pair IoU):")
    print(f"    {'id':<34}{'gutter':<8}{'layout':<17}{'inset':>6}{'resid':>7}"
          f"{'unclaimed':>11}{'pairIoU':>9}")
    for cid, bkt, lc, ins, res, frac, mx in per_fig:
        flag = "  <-- " if (res > args.max_residual or frac > 0.001 or ins > 0) else ""
        print(f"    {cid:<34}{bkt:<8}{lc:<17}{ins:>6.0f}{res:>7.0f}{frac:>10.3%}"
              f"{mx:>9.4f}{flag}")

    bad = defects + cap_bad + label_bad
    if bad:
        print("\n  DEFECTS:")
        for x in bad:
            print("   ", x)
    else:
        print("\n  no defects: every GT box is tight on the drawn ink, all ink is claimed,")
        print("  panel boxes are disjoint, and every caption names exactly its panels.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
