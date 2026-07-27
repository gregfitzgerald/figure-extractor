#!/usr/bin/env python3
"""make_tasks.py -- emit LEAK-FREE, ANONYMISED panel-decomposition tasks.

A task carries only what a real pipeline has at that moment:
  * the figure image, copied to `tasks/img/<anon>.png` under a shuffled name, and
  * the CAPTION, verbatim.

The caption is not a leak -- it is the constraint the job comes with, and exploiting it
("the caption names four panels, so find four") is a large part of doing this well. Some
captions in the corpus deliberately name no letters at all, so a detector that can only
work when told the count is exposed.

Nothing else is given: no panel count field, no layout class, no boxes, no letters.

Predictions are appended one JSON object per line to `predictions/<run>.jsonl`;
`score.py` resolves anon -> id. Filename-keyed evaluation is deliberately impossible.

Run: python3 benchmark/panels/make_tasks.py
"""
import argparse, json, pathlib, random, shutil

HERE = pathlib.Path(__file__).resolve().parent

INSTRUCTION = (
    "You are the PANEL DETECTOR of a scientific-figure extraction pipeline. The image is "
    "ONE journal figure, already cropped. It may contain a single panel or several "
    "sub-panels laid out in a grid, in unequal spans, or in an interlocking "
    "(non-guillotine) arrangement. Panel letters, when present, are drawn PIXELS, not "
    "text.\n"
    "Return one box per panel, in IMAGE PIXELS with the origin (0,0) at the TOP-LEFT, x "
    "right, y DOWN, as {x, y, width, height}. A panel's box is the TIGHT bounding box of "
    "everything that panel draws -- its plotting area, its axes and tick labels, and its "
    "own panel letter -- and nothing else. Do NOT include figure-level furniture that "
    "belongs to no single panel (a shared legend, a colourbar, a figure-level axis "
    "title); those are not panels.\n"
    "Give each box the panel LETTER it corresponds to. If the letter is drawn in the "
    "image, read it: the drawn letters are authoritative and are NOT always in "
    "reading order. If no letters are drawn, letter the panels A, B, C ... in reading "
    "order (top to bottom, then left to right).\n"
    "The caption is given verbatim. If it names panels, that is a hard constraint on how "
    "many panels there are.\n"
    "Set `confidence` in [0,1] that your FULL decomposition is correct, and set "
    "`abstain` to true if you would rather hand this figure to a human than commit to an "
    "answer. Abstention is scored separately: a calibrated abstention beats a confident "
    "mistake, and abstaining on a figure you would have got right costs you."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(HERE / "corpus"))
    ap.add_argument("--tasks", default=str(HERE / "tasks"))
    args = ap.parse_args()
    CORPUS, TASKS = pathlib.Path(args.corpus), pathlib.Path(args.tasks)
    IMG = TASKS / "img"
    IMG.mkdir(parents=True, exist_ok=True)
    (HERE / "predictions").mkdir(exist_ok=True)
    for old in list(TASKS.glob("*.json")) + list(TASKS.glob("*.jsonl")) + list(IMG.glob("*.png")):
        old.unlink()

    ids = json.loads((CORPUS / "manifest.json").read_text())["ids"]
    order = ids[:]
    random.Random(20260726).shuffle(order)

    anon_map, index = {}, []
    for i, cid in enumerate(order, 1):
        g = json.loads((CORPUS / f"{cid}.pgt.json").read_text())
        anon = f"fig_{i:04d}"
        anon_map[anon] = cid
        shutil.copyfile(CORPUS / g["image"], IMG / f"{anon}.png")
        task = {
            "task": anon,
            "image": f"benchmark/panels/{TASKS.name}/img/{anon}.png",
            "imageSize": {"width": g["figure"]["width"], "height": g["figure"]["height"]},
            "caption": g["caption"],
            "instruction": INSTRUCTION,
            "output_schema": {
                "task": anon, "nPanels": 0, "confidence": 0.0, "abstain": False,
                "panels": [{"label": "A", "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
                            "conf": 1.0}],
                "method": "xy-cut | connected-components | vision-model | manual",
            },
        }
        (TASKS / f"{anon}.json").write_text(json.dumps(task, indent=1))
        index.append({"task": anon, "image": task["image"], "caption": g["caption"],
                      "imageSize": task["imageSize"]})

    (TASKS / "anon_map.json").write_text(json.dumps(anon_map, indent=1))
    (TASKS / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in index) + "\n")
    print(f"wrote {len(order)} leak-free anonymised panel tasks -> {TASKS}")
    print(f"  anon images -> {IMG}/fig_XXXX.png")
    print(f"  anon_map    -> {TASKS/'anon_map.json'} (scorer-only)")


if __name__ == "__main__":
    main()
