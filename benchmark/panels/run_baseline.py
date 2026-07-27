#!/usr/bin/env python3
"""run_baseline.py -- drive figure-extractor.html's panel detector over the task set.

Runs in headless Chromium exactly as the "Auto-panels" button does. figure-extractor.html
is never modified: the task image is pushed into `state.pages` as a decoded Image and a
synthetic figure covering the whole image is handed to the detector.

Two detectors, so BEFORE and AFTER are measured by the same yardstick:
  --detector legacy  the recursive XY-cut (`suggestSubfigures` /`suggestSubfiguresLegacy`).
                     Bare boxes: no letters, no confidence. Its only refusal signal is
                     finding fewer than 2 boxes, recorded as `abstain: true` with the box
                     it did find kept so the geometry is still scored.
  --detector core    the cascade detector (`detectPanelsCore`), which returns letters,
                     a confidence and verification flags. `abstain` follows the tool's own
                     gate: fewer than 2 panels, confidence < 0.35, or ok == false.

And two caption modes:
  --expected caption  the caption is given (the count constraint is available)
  --expected none     the caption is withheld, so the raw geometric cut is measured

Run:
  python3 benchmark/panels/run_baseline.py --run legacy_caption --detector legacy
  python3 benchmark/panels/run_baseline.py --run legacy_nocap   --detector legacy --expected none
  python3 benchmark/panels/run_baseline.py --run core_caption   --detector core
"""
import argparse, base64, json, pathlib, re, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
TASKS = HERE / "tasks"
PRED = HERE / "predictions"

CAP_LETTER = re.compile(r"\(([A-Za-z])\)")

JS = """
async ({dataUrl, W, H, expected, caption, detector}) => {
  const img = new Image();
  img.src = dataUrl;
  await img.decode();
  state.pages = [{ pageNum: 1, img: img, wrapper: null }];
  const fig = { id: 'benchfig', label: 'Figure 1', pageNum: 1,
                bounds: { x: 0, y: 0, width: W, height: H },
                caption: caption, captionSource: 'textlayer', subfigures: [] };
  const t0 = performance.now();
  try {
    if (detector === 'core') {
      const res = detectPanelsCore(fig, {});
      return { ms: performance.now() - t0, core: {
        panels: (res.panels || []).map(p => ({ bounds: p.bounds, letter: p.letter || null,
                                               source: p.source || null })),
        count: res.count, method: res.method, confidence: res.confidence,
        flags: res.flags || [], ok: !!res.ok,
        expected: res.expected || { count: null, letters: [] } } };
    }
    const fn = (typeof suggestSubfigures === 'function') ? suggestSubfigures
             : (typeof suggestSubfiguresLegacy === 'function') ? suggestSubfiguresLegacy
             : null;
    if (!fn) return { error: 'no legacy detector in this build' };
    return { boxes: fn(fig, expected), ms: performance.now() - t0 };
  } catch (e) { return { error: String(e && e.message || e), ms: performance.now() - t0 }; }
}
"""


def run(url, tasks, expected_mode, detector, headless=True):
    from playwright.sync_api import sync_playwright
    out, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        pg = browser.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/figure-extractor.html")
        pg.wait_for_function(
            "() => typeof detectPanelsCore === 'function' "
            "|| typeof suggestSubfigures === 'function' "
            "|| typeof suggestSubfiguresLegacy === 'function'", timeout=20000)
        for t in tasks:
            img = (HERE.parent.parent / t["image"])
            data = "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()
            letters = CAP_LETTER.findall(t["caption"])
            give_caption = expected_mode == "caption"
            expected = len(letters) if (give_caption and len(letters) >= 2) else 0
            res = pg.evaluate(JS, {"dataUrl": data, "W": t["imageSize"]["width"],
                                   "H": t["imageSize"]["height"], "expected": expected,
                                   "caption": t["caption"] if give_caption else "",
                                   "detector": detector})
            if res.get("error"):
                errors.append(f"{t['task']}: {res['error']}")
            rec = {"task": t["task"], "expectedCountGiven": expected,
                   "ms": round(res.get("ms", 0), 1)}
            if detector == "core":
                c = res.get("core") or {"panels": [], "confidence": 0, "method": "error",
                                        "flags": ["exception"], "ok": False}
                pans = c["panels"]
                rec.update({
                    "nPanels": len(pans),
                    "panels": [{"label": (p["letter"] or chr(ord("A") + k)).upper(),
                                "bbox": p["bounds"], "source": p["source"]}
                               for k, p in enumerate(pans)],
                    "confidence": c["confidence"],
                    # the tool's own refusal gate, verbatim
                    "abstain": len(pans) < 2 or (c["confidence"] or 0) < 0.35 or not c["ok"],
                    "method": c["method"], "flags": c["flags"], "ok": c["ok"],
                    "expectedFromCaption": c.get("expected"),
                })
                print(f"  {t['task']}  panels={len(pans):<2} conf={c['confidence']:.2f} "
                      f"{c['method']:<14} ok={c['ok']}  {','.join(c['flags'][:3])}")
            else:
                boxes = res.get("boxes") or []
                rec.update({
                    "nPanels": len(boxes),
                    "panels": [{"label": chr(ord("A") + k),
                                "bbox": {"x": b["x"], "y": b["y"],
                                         "width": b["width"], "height": b["height"]}}
                               for k, b in enumerate(boxes)],
                    # the XY-cut exposes no confidence; its only refusal signal is finding
                    # fewer than two boxes, which the UI reports as "none detected"
                    "confidence": None,
                    "abstain": len(boxes) < 2,
                    "method": "xy-cut (suggestSubfigures)",
                })
                print(f"  {t['task']}  boxes={len(boxes)}  expected={expected}  "
                      f"{res.get('ms', 0):.0f}ms")
            out.append(rec)
        browser.close()
    return out, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--expected", choices=["caption", "none"], default="caption")
    ap.add_argument("--detector", choices=["legacy", "core"], default="legacy")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--url", help="use an already-running server instead of starting one")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    try:
        import playwright  # noqa: F401
    except ImportError:
        sys.exit("run_baseline.py needs playwright (pip install playwright; "
                 "python3 -m playwright install chromium)")

    tasks = [json.loads(l) for l in (TASKS / "tasks.jsonl").read_text().splitlines() if l.strip()]
    srv = None
    url = args.url
    if not url:
        srv = subprocess.Popen([sys.executable, "-m", "http.server", str(args.port)],
                               cwd=str(REPO), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        url = f"http://localhost:{args.port}"
        time.sleep(1.2)
    try:
        preds, errors = run(url, tasks, args.expected, args.detector,
                            headless=not args.headed)
    finally:
        if srv:
            srv.terminate()
    PRED.mkdir(exist_ok=True)
    path = PRED / f"{args.run}.jsonl"
    path.write_text("\n".join(json.dumps(p) for p in preds) + "\n")
    print(f"\nwrote {len(preds)} predictions -> {path}")
    print(f"  median detect time {sorted(p['ms'] for p in preds)[len(preds)//2]:.0f}ms")
    if errors:
        print(f"  page errors: {errors[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
