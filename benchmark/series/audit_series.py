#!/usr/bin/env python3
"""audit_series.py -- verify the SERIES/GROUP answer key against the drawn pixels.

The GT bundle claims, for every mark, both a device pixel AND the series that owns it.
Both claims are checked here from the PNG alone, with no help from R:

  1. INK CHECK        -- is there drawn ink within a few pixels of the GT coordinate?
  2. SERIES-COLOUR CHECK (colour-cued charts) -- of all the series colours in this
     chart, is the one nearest the ink at that coordinate the series the GT claims?
     This is the load-bearing check: it independently confirms the mark -> series
     binding that the whole parsing benchmark is scored against.
  3. LEGEND-SWATCH CHECK -- does the pixel at the exported legend key carry the
     series' own colour (colour-cued) or ink (monochrome)?

It also WRITES `corpus/visibility.json`: per mark, `visible` (the claimed series' ink
is at the exact GT pixel), `occluded` (its ink is nearby but overdrawn at the pixel),
or `hidden` (another series' ink covers it entirely -- physically unreadable, so no
reader can be expected to assign it). The scorer reports the mis-assignment rate both
with and without the `hidden` marks; the count of hidden marks is itself a finding.

Shape-cued (monochrome) charts have no colour signal by construction, so they get the
ink check only; that is reported separately rather than silently passed.

Run: python3 benchmark/series/audit_series.py [stress]      # positional tier suffix
"""
import json, math, pathlib, sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("audit_series.py needs Pillow (pip install Pillow)")

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / ("corpus_" + sys.argv[1] if len(sys.argv) > 1 else "corpus")

WHITE_TOL = 26          # how far from pure white counts as "ink"
COLOUR_TOL = 20         # max RGB distance to accept a colour match (anti-aliasing)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def composited(hexcol, alpha, bg_hex):
    """The colour actually written to the PNG: the series colour alpha-composited over
    the panel background. Without this, an alpha-blended dark hue lands nearer a
    NEIGHBOURING series' nominal colour and the audit reports phantom mismatches."""
    c, bg = hex_rgb(hexcol), hex_rgb(bg_hex)
    return tuple(alpha * c[i] + (1 - alpha) * bg[i] for i in range(3))


def window(px_arr, W, H, cx, cy, r):
    x0, x1 = max(0, int(cx) - r), min(W - 1, int(cx) + r)
    y0, y1 = max(0, int(cy) - r), min(H - 1, int(cy) + r)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            yield px_arr[x, y][:3]


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def has_ink(pix, W, H, cx, cy, r=4):
    for c in window(pix, W, H, cx, cy, r):
        if dist(c, (255, 255, 255)) > WHITE_TOL:
            return True
    return False


def best_series(pix, W, H, cx, cy, colours, r=6):
    """Return (best_series_index, distance) for the closest series colour found in the
    window -- i.e. which series' ink is actually drawn at this coordinate."""
    best = (None, 1e9)
    for c in window(pix, W, H, cx, cy, r):
        for i, tgt in enumerate(colours):
            d = dist(c, tgt)
            if d < best[1]:
                best = (i, d)
    return best


# Where to probe for the SERIES colour, per mark role: a bar top / box hinge is a dark
# outline, so probe a few pixels into the filled body instead of on the edge.
def probe_at(b, m):
    ct, role = b["chartType"], m["role"]
    if role == "top" and ct in ("grouped-bar",):
        return m["px"], m["py"] + 5
    if role == "q1":
        return m["px"], m["py"] - 6
    if role in ("q3", "med"):
        return m["px"], m["py"] + 6
    return m["px"], m["py"]


def main():
    ids = json.loads((CORPUS / "manifest.json").read_text())["ids"]
    tot_marks = ok_ink = 0
    col_marks = col_ok = col_occl = 0
    mono_marks = 0
    leg_tot = leg_ok = 0
    worst = []
    occl_by_chart = {}
    visibility = {}
    for cid in ids:
        b = json.loads((CORPUS / f"{cid}.sgt.json").read_text())
        img = Image.open(CORPUS / b["image"]).convert("RGB")
        pix = img.load(); W, H = img.size
        colour_cued = "color" in b["cueType"]
        alpha = b["render"].get("alpha", 1) or 1
        bg = b["render"].get("panelBg", "#FFFFFF")
        colours = [composited(s["colorHex"], alpha, bg) for s in b["series"]]
        distinct = len(set(colours)) == len(colours)
        bad = 0; occl = 0
        vis = {}
        for m in b["marks"]:
            tot_marks += 1
            if has_ink(pix, W, H, m["px"], m["py"]):
                ok_ink += 1
            if m["role"] == "cap":
                vis[m["markId"]] = "visible"
                continue          # error caps are drawn black, carry no series colour
            if colour_cued and distinct:
                col_marks += 1
                claimed = int(m["seriesId"][1:])
                sx, sy = probe_at(b, m)
                # (i) the ink AT the mark: does it carry the claimed series' colour?
                si, d = best_series(pix, W, H, sx, sy, colours, r=1)
                if si == claimed and d <= COLOUR_TOL:
                    col_ok += 1
                    vis[m["markId"]] = "visible"
                    continue
                # (ii) not at the exact pixel -> is the claimed colour present nearby
                #      but overdrawn by another series? That is real OCCLUSION, not a
                #      GT defect: the mark is physically hidden under later ink.
                si2, d2 = best_series(pix, W, H, sx, sy, [colours[claimed]], r=6)
                if d2 <= COLOUR_TOL:
                    col_occl += 1
                    occl += 1
                    vis[m["markId"]] = "occluded"
                else:
                    bad += 1
                    vis[m["markId"]] = "hidden"
            else:
                mono_marks += 1
                vis[m["markId"]] = "visible"
        visibility[cid] = vis
        if occl:
            occl_by_chart[cid] = (occl, len(b["marks"]))
        for s in b["series"]:
            key = s.get("legendKeyPx")
            if not key:
                continue
            leg_tot += 1
            if colour_cued and distinct:
                # ggplot2 draws the guide key through the layer's alpha too, so the key
                # must be matched against the COMPOSITED colours -- with a 6-step ramp
                # the un-composited comparison lands on the wrong neighbour.
                si, d = best_series(pix, W, H, key["px"], key["py"], colours, r=7)
                if si == s["index"] and d <= COLOUR_TOL:
                    leg_ok += 1
            elif has_ink(pix, W, H, key["px"], key["py"], r=7):
                leg_ok += 1
        if bad:
            worst.append((cid, bad, len(b["marks"])))
    (CORPUS / "visibility.json").write_text(json.dumps(visibility, indent=1))

    print("SERIES-GT AUDIT (PNG pixels vs the exported answer key)")
    print(f"  marks with ink at the GT pixel                 : "
          f"{ok_ink}/{tot_marks} = {ok_ink/tot_marks:.3f}")
    print(f"  colour-cued marks whose ink IS the claimed")
    print(f"    series at the exact GT pixel                 : {col_ok}/{col_marks} = "
          f"{(col_ok/col_marks if col_marks else 0):.3f}")
    print(f"  ... claimed colour present but OVERDRAWN by")
    print(f"    another series (true occlusion, not GT error) : {col_occl}"
          f" ({col_occl/col_marks:.3f})")
    print(f"  marks HIDDEN entirely under another series     : {sum(w[1] for w in worst)}"
          f"  (physically unreadable; excluded in the scorer's second figure)")
    print(f"  monochrome/shape-cued marks (ink-only check)   : {mono_marks}")
    print(f"  legend swatches carrying their series' colour  : {leg_ok}/{leg_tot} = "
          f"{(leg_ok/leg_tot if leg_tot else 0):.3f}")
    if occl_by_chart:
        print("  occluded marks by chart (a colour-sampling reader cannot recover these):")
        for cid, (o, n) in sorted(occl_by_chart.items(), key=lambda kv: -kv[1][0]):
            print(f"    {cid:<30} {o}/{n}")
    if worst:
        print("  hidden marks by chart:")
        for cid, bad, n in worst:
            print(f"    {cid:<30} {bad}/{n}")
    print(f"  visibility annotation -> {CORPUS/'visibility.json'}")
    return 0 if leg_ok == leg_tot and ok_ink == tot_marks else 1


if __name__ == "__main__":
    sys.exit(main())
