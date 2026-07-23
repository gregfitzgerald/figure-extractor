#!/usr/bin/env python3
"""make_tasks.py -- emit LEAK-FREE chart-classification tasks.

For each rendered figure, a task carries ONLY the image plus the ALLOWED label
sets (imported from the figure-extractor CHAR_VOCAB, so a passing prediction is a
valid tool input) -- and NO answer. Images are additionally ANONYMISED: each
corpus image `<id>.png` is copied to `tasks/img/<anon>.png` under a shuffled name
so the classifier cannot read the chart type off the filename. `tasks/anon_map.json`
records anon->id; only the scorer consults it (the read stays blind).

A vision agent Reads `tasks/img/<anon>.png`, classifies, and appends one JSON line
to `predictions/<run>.jsonl`:
  {"task":"<anon>","charType":..,"confidence":0..1,"dataProvenance":..,
   "scaleX":..,"scaleY":..,"dispersionPresent":bool,"nonDataElements":[..]}
`score.py` resolves anon->id, joins to GT, and scores.

Run: python3 benchmark/classify/make_tasks.py
"""
import json, pathlib, random, re, shutil

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
TASKS = HERE / "tasks"; IMG = TASKS / "img"
IMG.mkdir(parents=True, exist_ok=True)
(HERE / "predictions").mkdir(exist_ok=True)
HTML = HERE.parent.parent / "figure-extractor.html"


def load_char_vocab():
    """Parse the CHAR_VOCAB object out of figure-extractor.html so the allowed
    label sets stay in lock-step with the tool's validator."""
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const CHAR_VOCAB\s*=\s*\{(.*?)\n\};", txt, re.S)
    if not m:
        raise SystemExit("could not locate CHAR_VOCAB in figure-extractor.html")
    body = m.group(1)
    vocab = {}
    for key in ["charType", "scale", "dispersion", "dataProvenance", "nonDataElement"]:
        km = re.search(key + r"\s*:\s*\[(.*?)\]", body, re.S)
        if not km:
            continue
        vals = re.findall(r"'([^']+)'", km.group(1))
        vocab[key] = vals
    return vocab


def main():
    vocab = load_char_vocab()
    ids = sorted(p.stem[:-6] for p in CORPUS.glob("*.label.json"))
    rng = random.Random(20260722)
    order = ids[:]; rng.shuffle(order)
    anon_map = {}
    tasks_jsonl = []
    for i, cid in enumerate(order, 1):
        anon = f"img_{i:04d}"
        anon_map[anon] = cid
        shutil.copyfile(CORPUS / f"{cid}.png", IMG / f"{anon}.png")
        task = {
            "task": anon,
            "image": f"benchmark/classify/tasks/img/{anon}.png",
            "instruction": (
                "You are the PERCEPTION GATE of a scientific-figure extraction pipeline. "
                "Read ONLY the image. Classify WHAT this figure is before any data is read. "
                "Return: (1) charType -- the single best chart type from the allowed set; "
                "(2) confidence in [0,1] that charType is correct (be calibrated -- a 0.9 must "
                "be right ~90% of the time); use 'unknown' or 'other' rather than guess when "
                "genuinely ambiguous. (3) dataProvenance: 'primary' if the figure shows the "
                "study's OWN measurements, 'derived' if it summarises OTHER studies (forest / "
                "funnel meta-analytic plots), else 'unknown'. (4) scaleX and scaleY: the axis "
                "scales. (5) dispersionPresent: true if the figure visually depicts variability "
                "(error bars, box IQR/whiskers, CI intervals or bands, funnel SE axis). "
                "(6) nonDataElements: the non-data ink actually drawn (to be ignored during "
                "extraction). Use ONLY strings from the allowed sets."),
            "allowed": {
                "charType": vocab["charType"],
                "scale": vocab["scale"],
                "dataProvenance": vocab["dataProvenance"],
                "nonDataElement": vocab["nonDataElement"],
            },
            "output_schema": {
                "task": anon, "charType": "<one of allowed.charType>",
                "confidence": 0.0, "dataProvenance": "<one of allowed.dataProvenance>",
                "scaleX": "<one of allowed.scale>", "scaleY": "<one of allowed.scale>",
                "dispersionPresent": False,
                "nonDataElements": ["<subset of allowed.nonDataElement>"],
            },
        }
        (TASKS / f"{anon}.json").write_text(json.dumps(task, indent=1))
        tasks_jsonl.append({"task": anon, "image": task["image"]})

    (TASKS / "anon_map.json").write_text(json.dumps(anon_map, indent=1))
    (TASKS / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in tasks_jsonl) + "\n")
    print(f"wrote {len(order)} leak-free anonymised tasks -> {TASKS}")
    print(f"  anon images  -> {IMG}/img_XXXX.png")
    print(f"  anon_map     -> {TASKS/'anon_map.json'} (scorer-only)")
    print(f"  vocab sizes  : " + ", ".join(f"{k}={len(v)}" for k, v in vocab.items()))


if __name__ == "__main__":
    main()
