#!/usr/bin/env python3
"""cv_parser.py -- a DETERMINISTIC structural parser, the hand-built stand-in for a
"series-aware head" on a landmark detector.

It answers only the STRUCTURE half of parsing, using nothing but the image and the mark
coordinates the task already provides:

  * series  -- sample the ink colour at each mark (role-aware probe: a bar top is an
               outline, so probe into the fill) and mode-seed cluster those colours.
               Error caps carry no series colour, so each is inherited from the nearest
               central mark, exactly as a detector head would have to.
  * groups  -- distinct x levels for line/stacked charts (every series shares an x);
               widest-gap splitting for dodged bar/box; one group for a scatter.

It CANNOT name a series: the legend's meaning lives in text, and reading text is the
agent's job (WHITE-PAPER-LOG s10). So it emits placeholder labels and the scorer's
`bound` mis-assignment is ~1.0 by construction -- that is the finding, not a bug. Read
its STRUCTURAL mis-assignment and ARI columns, and compare them to the agent's.

Run: python3 benchmark/series/cv_parser.py [stress]   # -> predictions/cv_cluster[_stress].jsonl
"""
import collections, json, math, pathlib, sys

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
TIER = sys.argv[1] if len(sys.argv) > 1 else ""
TASKS = HERE / (f"tasks_{TIER}" if TIER else "tasks")
PRED = HERE / "predictions"

CENTRAL = {"top", "pt", "seg", "med"}


def probe_offset(chart_type, role):
    if role == "top" and chart_type in ("grouped-bar", "stacked-bar"):
        return 0, 5
    if role == "q1":
        return 0, -6
    if role in ("q3", "med"):
        return 0, 6
    return 0, 0


def sample(pix, W, H, x, y, r=1):
    """Modal-ish colour in a tiny window: the darkest-from-white pixel, which is the
    mark's own ink rather than the anti-aliased rim."""
    best, bd = (255, 255, 255), -1
    for yy in range(max(0, int(y) - r), min(H, int(y) + r + 1)):
        for xx in range(max(0, int(x) - r), min(W, int(x) + r + 1)):
            c = pix[xx, yy][:3]
            d = math.dist(c, (255, 255, 255))
            if d > bd:
                bd, best = d, c
    return best


def colour_cluster(cols, thresh=26):
    """Mode-seeded colour clustering: colours that recur are the series' true ink;
    single blended pixels (anti-aliasing at a crossing / an overplotted marker) are
    then snapped to the NEAREST series rather than becoming clusters of their own.
    Snapping to the wrong neighbour at an overlap is exactly the occlusion failure
    this baseline exists to expose -- it is not smoothed away."""
    if not cols:
        return []
    counts = collections.Counter(cols)
    floor = max(2, int(0.04 * len(cols)))
    seeds = [c for c, n in counts.most_common() if n >= floor] or [counts.most_common(1)[0][0]]
    merged = []
    for c in seeds:
        for grp in merged:
            if math.dist(c, grp[0]) <= thresh:
                grp.append(c)
                break
        else:
            merged.append([c])
    cent = [tuple(sum(v[i] for v in g) / len(g) for i in range(3)) for g in merged]
    return [min(range(len(cent)), key=lambda k: math.dist(c, cent[k])) for c in cols]


def x_groups(chart_type, marks):
    """x-axis clusters. A line or stacked bar puts every series at the SAME x, so a
    group is a distinct x. A dodged bar/box offsets each series inside its category,
    so the categories are recovered by splitting at the widest x gaps (categorical
    axes are evenly spaced, which makes that split well posed)."""
    xs = [m["px"] for m in marks]
    if chart_type == "scatter":
        return [0] * len(xs)
    if chart_type in ("line", "stacked-bar"):
        lev = []
        for x in sorted(set(round(v, 1) for v in xs)):
            if not lev or x - lev[-1] > 3:
                lev.append(x)
        return [min(range(len(lev)), key=lambda k: abs(x - lev[k])) for x in xs]
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    sx = [xs[i] for i in order]
    gaps = [sx[i + 1] - sx[i] for i in range(len(sx) - 1)]
    pos = sorted({round(g, 1) for g in gaps if g > 1})
    if not pos:
        return [0] * len(xs)
    # split where the gap distribution itself jumps: the within-category dodge spacing
    # and the between-category spacing are two distinct scales (2 series make them
    # close, so a fixed fraction of the max gap is not enough -- use the ratio).
    ratios = [(pos[i + 1] / pos[i], i) for i in range(len(pos) - 1)]
    best = max(ratios, default=(1.0, -1))
    if best[0] < 1.25:
        return [0] * len(xs)
    cut = math.sqrt(pos[best[1]] * pos[best[1] + 1])
    lab = [0] * len(xs)
    k = 0
    lab[order[0]] = 0
    for i in range(1, len(sx)):
        if gaps[i - 1] > cut:
            k += 1
        lab[order[i]] = k
    return lab


def parse_one(task):
    img = Image.open(HERE.parent.parent / task["image"]).convert("RGB")
    pix = img.load()
    W, H = img.size
    ct = task["chartType"]
    marks = task["marks"]

    central = [m for m in marks if m["role"] in CENTRAL or m["role"] in ("q1", "q3")]
    cols = []
    for m in central:
        dx, dy = probe_offset(ct, m["role"])
        cols.append(sample(pix, W, H, m["px"] + dx, m["py"] + dy))
    lab = colour_cluster(cols)
    smap = {m["markId"]: lab[i] for i, m in enumerate(central)}

    # error caps carry no series colour -> inherit from the nearest central mark
    for m in marks:
        if m["markId"] in smap:
            continue
        best, bd = None, 1e18
        for c in central:
            d = (c["px"] - m["px"]) ** 2 + 0.15 * (c["py"] - m["py"]) ** 2
            if d < bd:
                bd, best = d, c
        smap[m["markId"]] = smap[best["markId"]] if best else 0

    gl = x_groups(ct, marks)
    gmap = {m["markId"]: gl[i] for i, m in enumerate(marks)}

    nseries = len(set(smap.values()))
    ngroups = len(set(gmap.values()))
    return {
        "task": task["task"], "nSeries": nseries, "nGroups": ngroups,
        "confidence": 0.7,
        # placeholder names: this parser reads no text, so it can bind no meaning
        "series": [{"id": f"C{k}", "label": f"__cluster{k}__", "swatchPx": {"px": 0, "py": 0}}
                   for k in sorted(set(smap.values()))],
        "groups": [{"id": f"X{k}", "label": f"__x{k}__"} for k in sorted(set(gmap.values()))],
        "assignments": [{"markId": m["markId"], "series": f"C{smap[m['markId']]}",
                         "group": f"X{gmap[m['markId']]}", "conf": 0.7} for m in marks],
        "method": "pixel-sampled",
    }


def main():
    PRED.mkdir(exist_ok=True)
    tasks = [json.loads(p.read_text()) for p in sorted(TASKS.glob("fig_*.json"))]
    if not tasks:
        sys.exit("no tasks -- run make_tasks.py first")
    out = [parse_one(t) for t in tasks]
    name = f"cv_cluster_{TIER}.jsonl" if TIER else "cv_cluster.jsonl"
    (PRED / name).write_text("\n".join(json.dumps(o) for o in out) + "\n")
    print(f"cv_parser: {len(out)} charts -> {PRED/name}")
    for o in out:
        print(f"  {o['task']}  nSeries={o['nSeries']} nGroups={o['nGroups']}")


if __name__ == "__main__":
    main()
