#!/usr/bin/env python3
"""make_tasks.py -- emit LEAK-FREE, ANONYMISED series/group PARSING tasks.

A task carries only:
  * the image, copied to `tasks/img/<anon>.png` under a shuffled name (so nothing can
    be inferred from a filename), and
  * the detected MARKS as bare pixel coordinates + role -- the output a landmark
    detector already produces -- in an order that was shuffled at GENERATION time, so
    the listing itself leaks no grouping.

It carries NO series count, NO group count, NO legend labels, NO assignment. The
reader must answer the three structural questions:
    (1) how many series and how many x-axis groups are there?
    (2) which series and which group does EACH mark belong to?
    (3) what does the legend (or the direct label) call each series, and where is its
        swatch?
The chart TYPE is given, because classification is measured separately and is already
at ceiling (WHITE-PAPER-LOG s8); withholding it would only re-measure classification.

Predictions are appended, one JSON object per line, to `predictions/<run>.jsonl`;
`score.py` resolves anon -> id and scores. Filename-keyed evaluation is deliberately
impossible.

Run: python3 benchmark/series/make_tasks.py [--tier stress]
"""
import argparse, json, pathlib, random, re, shutil

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE.parent.parent / "figure-extractor.html"


def tier_dirs(tier):
    """Each tier owns its corpus + task directories, so adding a tier can never
    renumber another tier's anonymised task ids (which would silently invalidate
    predictions already scored against them)."""
    sfx = f"_{tier}" if tier else ""
    return HERE / f"corpus{sfx}", HERE / f"tasks{sfx}"

ROLE_DESC = {
    "top": "the central mark of an arm -- a bar's top edge, or a line's point marker",
    "cap": "the tip of an error bar's UPPER cap (it belongs to the same arm as its bar/point)",
    "seg": "the centre of one filled segment of a stacked bar",
    "pt": "a single scatter data point",
    "q1": "the lower hinge (Q1) of a box", "med": "the median line of a box",
    "q3": "the upper hinge (Q3) of a box",
}


def load_char_vocab():
    """Parse CHAR_VOCAB out of figure-extractor.html so the corpus labels stay in
    lock-step with the tool's own validator (the same discipline as classify/)."""
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const CHAR_VOCAB\s*=\s*\{(.*?)\n\};", txt, re.S)
    if not m:
        raise SystemExit("could not locate CHAR_VOCAB in figure-extractor.html")
    body = m.group(1)
    out = {}
    for key in ("charType", "flags", "role"):
        km = re.search(key + r"\s*:\s*\[(.*?)\]", body, re.S)
        if km:
            out[key] = re.findall(r"'([^']+)'", km.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="", help="'' (base) or 'stress'")
    args = ap.parse_args()
    CORPUS, TASKS = tier_dirs(args.tier)
    IMG = TASKS / "img"
    vocab = load_char_vocab()
    IMG.mkdir(parents=True, exist_ok=True)
    (HERE / "predictions").mkdir(exist_ok=True)
    for old in list(TASKS.glob("*.json")) + list(IMG.glob("*.png")):
        old.unlink()

    ids = json.loads((CORPUS / "manifest.json").read_text())["ids"]
    rng = random.Random(20260724 + len(args.tier))
    order = ids[:]
    rng.shuffle(order)

    anon_map, index, bad = {}, [], []
    for i, cid in enumerate(order, 1):
        b = json.loads((CORPUS / f"{cid}.sgt.json").read_text())
        if b["chartType"] not in vocab["charType"]:
            bad.append(f"{cid}: charType {b['chartType']}")
        for f in b.get("flags", []):
            if f not in vocab["flags"]:
                bad.append(f"{cid}: flag {f}")
        anon = f"fig_{i:04d}"
        anon_map[anon] = cid
        shutil.copyfile(CORPUS / b["image"], IMG / f"{anon}.png")
        roles = sorted({m["role"] for m in b["marks"]})
        task = {
            "task": anon,
            "image": f"{TASKS.relative_to(HERE.parent.parent)}/img/{anon}.png".replace("\\", "/"),
            "chartType": b["chartType"],
            "imageSize": {"width": b["render"]["width"], "height": b["render"]["height"]},
            "instruction": (
                "You are the SERIES/GROUP PARSER of a scientific-figure extraction "
                "pipeline. A landmark detector has already found every drawn mark and "
                "given you its pixel position (origin (0,0) = TOP-LEFT, x right, y DOWN) "
                "and its role. Your job is the structure, not the numbers: recover WHICH "
                "SERIES (the legend entity -- the condition/arm/stratum) and WHICH GROUP "
                "(the x-axis cluster or timepoint) each mark belongs to, and what the "
                "legend calls each series.\n"
                "Answer three things:\n"
                "(1) nSeries and nGroups -- how many distinct series and how many x-axis "
                "groups the figure actually has. For a scatter with no x-axis clusters, "
                "nGroups is 1.\n"
                "(2) assignments -- for EVERY markId listed below, the series and the "
                "group it belongs to, using your own ids. Assign all of them. Use the "
                "string \"unknown\" for a mark you genuinely cannot resolve (abstaining "
                "is scored separately and is better than guessing).\n"
                "(3) series -- one entry per series with the label EXACTLY as the legend "
                "or direct label spells it, and the pixel of its legend swatch/key (or "
                "of its direct label if the figure has no legend).\n"
                "Also give groups[] with each group's x-axis label, in left-to-right "
                "order, and `confidence` in [0,1] that your FULL assignment is correct "
                "(be calibrated). Per-mark `conf` is optional but useful.\n"
                "WARNING: legend order does not always match plotting order. Do not "
                "assume the first legend entry is the leftmost bar, the top line, or the "
                "bottom stack segment -- verify from the drawn colours/shapes."),
            "roles": {r: ROLE_DESC.get(r, r) for r in roles},
            "marks": [{"markId": m["markId"], "role": m["role"],
                       "px": round(m["px"], 1), "py": round(m["py"], 1)}
                      for m in b["marks"]],
            "output_schema": {
                "task": anon, "nSeries": 0, "nGroups": 0, "confidence": 0.0,
                "series": [{"id": "S1", "label": "<legend text, verbatim>",
                            "swatchPx": {"px": 0, "py": 0}}],
                "groups": [{"id": "G1", "label": "<x-axis tick label>"}],
                "assignments": [{"markId": "m001", "series": "S1", "group": "G1",
                                 "conf": 1.0}],
                "method": "visual | pixel-sampled",
            },
        }
        (TASKS / f"{anon}.json").write_text(json.dumps(task, indent=1))
        index.append({"task": anon, "image": task["image"], "nMarks": len(b["marks"])})

    (TASKS / "anon_map.json").write_text(json.dumps(anon_map, indent=1))
    (TASKS / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in index) + "\n")
    if bad:
        print("[warn] labels outside the tool's CHAR_VOCAB:")
        for x in bad:
            print("   ", x)
    print(f"wrote {len(order)} leak-free anonymised parsing tasks -> {TASKS}")
    print(f"  anon images -> {IMG}/fig_XXXX.png   ({sum(t['nMarks'] for t in index)} marks total)")
    print(f"  anon_map    -> {TASKS/'anon_map.json'} (scorer-only)")
    print(f"  CHAR_VOCAB check: chartType + flags all valid" if not bad else "")


if __name__ == "__main__":
    main()
