#!/usr/bin/env python3
"""predict_panels.py -- run the panel detector over the figures a HUMAN already boxed,
and emit predictions in the shape `score_real_validation.py` consumes.

WHY THIS EXISTS
---------------
The whole point of collecting human panel ground truth is to score the detector against it
on REAL journal figures -- the one thing the 95.1% synthetic result cannot tell you.
`score_real_validation.py` reads machine predictions from `pred/<run>.jsonl` and human GT
from `gt/<session>/panels_gt.jsonl`. Until now NOTHING produced that `pred/` run for real
figures: the scorer had a socket with no plug, so a completed annotation session would have
yielded ground truth with no way to compare a machine against it.

WHY IT IS A FAIR COMPARISON
---------------------------
Two confounds are removed by construction:
  * FIGURE LOCALISATION. The detector is handed exactly the figure box the human drew, so
    this measures panel DECOMPOSITION only. Scoring a detector that also had to find the
    figure would conflate two different failures.
  * RENDERING. It reads the very same `projectA/<id>/0001.png` the rater looked at, at the
    same DPI, so no resampling difference can explain a disagreement.

COORDINATES -- the trap
-----------------------
`detectPanelsCore` returns boxes in FIGURE-NATURAL pixels (relative to the crop). The GT in
panels_gt.jsonl is in PAGE pixels. They must be translated by the figure box origin before
they can be compared. Forget it and every IoU is 0.000 while both sides look individually
reasonable -- a silent failure, which is the exact class this project keeps producing. The
translation is asserted below, not assumed.

USAGE
-----
    python3 predict_panels.py --session S01 --run core_real
    python3 predict_panels.py --session S01 --run core_real --no-caption   # ablation
    python3 predict_panels.py --selftest

Then:
    python3 score_real_validation.py --run core_real
"""
import argparse
import base64
import json
import pathlib
import sys

import rvcommon as rv

TOOL = pathlib.Path(__file__).resolve().parents[2] / "figure-extractor.html"

# Runs detectPanelsCore against a data-URL crop, exactly as run_baseline.py does for the
# synthetic tier, so the two corpora are scored through the identical code path.
JS = r"""
({dataUrl, W, H, caption}) => new Promise((resolve) => {
  const img = new Image();
  img.onload = () => {
    state.pages = [{ pageNum: 1, img: img, wrapper: null }];
    const fig = { id: 'predfig', label: 'Figure 1', pageNum: 1,
                  bounds: { x: 0, y: 0, width: W, height: H },
                  caption: caption || '', captionSource: caption ? 'textlayer' : '',
                  subfigures: [] };
    const t0 = performance.now();
    try {
      const res = detectPanelsCore(fig, {});
      resolve({ ms: performance.now() - t0,
                panels: (res.panels || []).map(p => ({
                    bounds: p.bounds, letter: p.letter || null, source: p.source || null })),
                count: res.count, method: res.method, confidence: res.confidence,
                flags: res.flags || [], ok: !!res.ok,
                lettersVerified: !!res.lettersVerified });
    } catch (e) {
      resolve({ error: String((e && e.message) || e), ms: performance.now() - t0 });
    }
  };
  img.onerror = () => resolve({ error: 'image failed to load' });
  img.src = dataUrl;
})
"""


def crop_to_dataurl(png_path, box):
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    x, y = int(box["x"]), int(box["y"])
    w, h = int(box["width"]), int(box["height"])
    x, y = max(0, x), max(0, y)
    w, h = min(w, im.width - x), min(h, im.height - y)
    if w <= 1 or h <= 1:
        return None, 0, 0
    crop = im.crop((x, y, x + w, y + h))
    import io
    buf = io.BytesIO()
    crop.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), w, h


def to_page_coords(b, origin):
    """Figure-natural -> page pixels. See the COORDINATES note in the module docstring."""
    return {"x": b["x"] + origin["x"], "y": b["y"] + origin["y"],
            "width": b["width"], "height": b["height"]}


def captions_for(session):
    """Caption per task, from the sealed GT annotations the ingest wrote."""
    out = {}
    gdir = rv.GT / session
    for ann in sorted(gdir.rglob("annotations.json")):
        try:
            d = json.loads(ann.read_text())
        except Exception:
            continue
        for f in d.get("figures", []):
            if f.get("caption"):
                out.setdefault(d.get("article") or ann.parent.name, f["caption"])
    return out


def selftest():
    ok = True

    def check(name, cond, note=""):
        nonlocal ok
        print(f"  [{'ok ' if cond else 'FAIL'}] {name}{('  ' + note) if note else ''}")
        ok = ok and bool(cond)

    o = {"x": 100, "y": 50}
    got = to_page_coords({"x": 10, "y": 5, "width": 30, "height": 20}, o)
    check("translation adds the figure origin",
          got == {"x": 110, "y": 55, "width": 30, "height": 20}, str(got))
    check("translation leaves size alone", got["width"] == 30 and got["height"] == 20)
    ident = to_page_coords({"x": 7, "y": 8, "width": 1, "height": 2}, {"x": 0, "y": 0})
    check("a zero origin is the identity", ident == {"x": 7, "y": 8, "width": 1, "height": 2})

    # THE JOIN. Translation was correct all along; the ids were not, and nothing tested them.
    # Ask the scorer's own coercion how it keys a GT record shaped exactly as
    # ingest_annotations.py writes it, and require this module to emit the same key.
    import importlib
    try:
        srv = importlib.import_module("score_real_validation")
        gt_rec = {"task": "it01_420d", "figureIndex": 0, "nPanels": 2,
                  "panels": [{"label": "A", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
                             {"label": "B", "bbox": {"x": 10, "y": 0, "width": 10, "height": 10}}]}
        coerced = srv._coerce_gt(dict(gt_rec))
        gt_id = coerced.get("id") if coerced else None
        ours = f"{gt_rec['task']}_fig{gt_rec['figureIndex']}"
        check("prediction id matches the scorer's GT key", gt_id == ours,
              f"scorer={gt_id!r} ours={ours!r}")
    except ImportError as e:
        check("scorer importable for the join check", False, str(e))
    print("\nselftest OK" if ok else "\nSELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="session whose human GT to predict against, e.g. S01")
    ap.add_argument("--run", help="prediction run name -> pred/<run>.jsonl")
    ap.add_argument("--no-caption", action="store_true",
                    help="withhold the caption (ablation: it is the load-bearing input)")
    ap.add_argument("--url", default="http://localhost:8001",
                    help="origin serving figure-extractor.html")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.session or not a.run:
        ap.error("--session and --run are required")

    gt_path = rv.GT / a.session / "panels_gt.jsonl"
    if not gt_path.exists():
        raise SystemExit(f"no human panel GT at {gt_path} -- ingest the session first")
    recs = [json.loads(l) for l in gt_path.read_text().splitlines() if l.strip()]
    caps = captions_for(a.session)
    print(f"{len(recs)} figure(s) with human panel GT in {a.session}")

    from playwright.sync_api import sync_playwright
    out, skipped = [], []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"{a.url}/figure-extractor.html")
        pg.wait_for_function("() => typeof detectPanelsCore === 'function'", timeout=20000)
        for r in recs:
            task = r.get("task") or r.get("id")
            png = rv.SESSIONS / a.session / "projectA" / task / "0001.png"
            if not png.exists():
                skipped.append(f"{task}: no page render at {png}")
                continue
            box = r.get("figureBbox")
            if not box:
                skipped.append(f"{task}: GT record has no figureBbox")
                continue
            durl, w, h = crop_to_dataurl(png, box)
            if not durl:
                skipped.append(f"{task}: degenerate figure box {box}")
                continue
            cap = "" if a.no_caption else caps.get(task, "")
            res = pg.evaluate(JS, {"dataUrl": durl, "W": w, "H": h, "caption": cap})
            if res.get("error"):
                skipped.append(f"{task}: detector error {res['error']}")
                continue
            panels = [{"label": p["letter"], "bbox": to_page_coords(p["bounds"], box),
                       "conf": round(res.get("confidence") or 0, 4)}
                      for p in res["panels"]]
            # A predicted panel must lie inside the figure the human drew. If it does not,
            # the translation above is wrong and every downstream IoU would be a silent 0.
            for p in panels:
                assert (p["bbox"]["x"] >= box["x"] - 2
                        and p["bbox"]["y"] >= box["y"] - 2), \
                    f"{task}: predicted panel outside the figure box -- bad translation"
            # The id MUST match how the scorer keys ground truth. `_coerce_gt` builds
            # `f"{task}_fig{figureIndex}"` for records that carry no explicit `id`, which is
            # every record `ingest_annotations.py` writes into panels_gt.jsonl. Writing the
            # bare task here meant NOTHING ever joined: every figure scored as pred=None,
            # printing a confident median IoU of 0.000 and a coverage line that looked
            # healthy, and -- because a missing prediction counts as answered-and-wrong --
            # spuriously FAILING the A18 abstention gate the moment a real session was
            # scored. The join is asserted below; a silent zero is the failure mode here.
            fig_i = r.get("figureIndex", 0)
            out.append({"id": f"{task}_fig{fig_i}", "task": task, "figureIndex": fig_i,
                        "nPanels": res["count"], "panels": panels,
                        "confidence": res.get("confidence"), "method": res.get("method"),
                        "abstain": not res.get("ok"),
                        "lettersVerified": res.get("lettersVerified"),
                        "flags": res.get("flags") or [],
                        "captionGiven": bool(cap), "ms": round(res.get("ms", 0), 1)})
        b.close()

    rv.PRED.mkdir(parents=True, exist_ok=True) if hasattr(rv, "PRED") else None
    pred_dir = rv.DATA / "pred"
    pred_dir.mkdir(parents=True, exist_ok=True)
    p = pred_dir / f"{a.run}.jsonl"
    p.write_text("\n".join(json.dumps(o) for o in out) + "\n", encoding="utf-8")
    print(f"[written] {p}  ({len(out)} prediction(s))")

    # JOIN CHECK. The predictions and the GT are keyed independently, so a key-format drift
    # on either side produces a scoring run where every figure silently misses and the report
    # prints median IoU 0.000 with a healthy-looking coverage line. Verify the join HERE,
    # against the same ids the GT actually carries, rather than discovering it in a report.
    gt_ids = set()
    for line in (gt_path.read_text().splitlines()):
        if not line.strip():
            continue
        g = json.loads(line)
        gt_ids.add(g.get("id") or f"{g.get('task')}_fig{g.get('figureIndex', 0)}")
    joined = sum(1 for o in out if o["id"] in gt_ids)
    print(f"[join]    {joined}/{len(out)} prediction(s) match a GT id")
    if out and not joined:
        raise SystemExit(
            "NO prediction joins the ground truth -- scoring this run would report IoU 0.000 "
            "for every figure and read as a total detector failure.\n"
            f"  prediction ids look like: {out[0]['id']}\n"
            f"  GT ids look like:         {sorted(gt_ids)[:1]}")
    if skipped:
        print(f"\n{len(skipped)} skipped -- reported, never silently dropped:")
        for s in skipped:
            print("  !", s)
    answered = sum(1 for o in out if not o["abstain"])
    print(f"\nanswered {answered}/{len(out)}; "
          f"caption {'WITHHELD' if a.no_caption else 'given'}")
    print(f"Next: python3 score_real_validation.py --run {a.run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
