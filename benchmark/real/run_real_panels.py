#!/usr/bin/env python3
"""run_real_panels.py -- score figure-extractor.html's panel detector on REAL journal figures.

WHAT THIS IS
------------
`detectPanelsCore` has only ever been run on synthetic R-rendered panel mosaics
(benchmark/panels/). This runs the SAME function, unmodified, in the same headless
Chromium, against the 71 real figures of benchmark/real-validation/worklist.json:
real PDFs, real rasterisation, real captions.

figure-extractor.html is never modified. The page is loaded, the rendered PDF page is
pushed into `state.pages` as a decoded Image, the page's image-XObject placements are
pushed into `state.articles[0].imageRects` (so the XObject fast path can fire exactly as
it does on a real article load), and a figure object carrying the real caption and a
candidate bbox is handed to the detector.

WHAT IT CANNOT TELL YOU
-----------------------
There is no panel-level ground truth for these figures. Nobody has drawn the boxes.
So this measures WHAT THE DETECTOR SAID, and its agreement with two comparators whose
own provenance is unrecorded (see --help of score_real_panels.py). It does not measure
accuracy. Every count printed here is "the detector emitted N", never "the figure has N".

The figure bbox is also machine-derived (figure_bbox.py). The tool's real boxing is
MANUAL. Because the bbox is an input the detector cannot check, the run sweeps four bbox
policies and the scorer reports how much the answer moves between them; a policy-sensitive
answer means the number is a property of the boxing heuristic, not of the detector.

RUN
    python3 benchmark/real/run_real_panels.py --out benchmark/real/out/panels_real.json
    python3 benchmark/real/run_real_panels.py --policies xobject --dpi 200      # subset
    python3 benchmark/real/run_real_panels.py --no-caption                      # ablation

Needs: PyMuPDF, Pillow, playwright + chromium.
"""
import argparse, base64, io, json, pathlib, subprocess, sys, time, traceback

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import figure_bbox  # noqa: E402

WORKLIST = REPO / "benchmark" / "real-validation" / "worklist.json"
POLICIES = ["fullpage", "capband", "cluster", "xobject"]

# Runs inside the page. Mirrors benchmark/panels/run_baseline.py's core path exactly so
# the synthetic and real numbers are produced by the same call, then adds the article
# imageRects the real XObject path needs.
JS = """
async ({dataUrl, W, H, bounds, caption, imageRects}) => {
  const img = new Image();
  img.src = dataUrl;
  await img.decode();
  state.pages = [{ pageNum: 1, img: img, wrapper: null }];
  state.articles = [{ name: '__bench__', pageCount: 1, imageRects: [imageRects] }];
  state.currentArticle = '__bench__';
  const fig = { id: 'benchfig', label: 'Figure', pageNum: 1,
                bounds: bounds, caption: caption,
                captionSource: 'textlayer', subfigures: [] };
  const t0 = performance.now();
  try {
    const res = detectPanelsCore(fig, {});
    return { ms: performance.now() - t0, ok_call: true,
      panels: (res.panels || []).map(p => ({ bounds: p.bounds, letter: p.letter || null,
                                             source: p.source || null })),
      count: res.count, method: res.method, confidence: res.confidence,
      flags: res.flags || [], ok: !!res.ok,
      lettersVerified: !!res.lettersVerified, letterSource: res.letterSource,
      expected: res.expected || { count: null, letters: [] },
      pageNaturalSize: { w: img.naturalWidth, h: img.naturalHeight } };
  } catch (e) {
    return { ms: performance.now() - t0, ok_call: false,
             error: String((e && e.stack) || (e && e.message) || e) };
  }
}
"""


def render_page_png(pdf, page0, dpi, cache):
    key = (pdf, page0, dpi)
    if key not in cache:
        import fitz
        doc = fitz.open(pdf)
        pix = doc[page0].get_pixmap(dpi=dpi)
        cache[key] = pix.tobytes("png")
        doc.close()
        if len(cache) > 6:                      # pages are ~5 MB at 200 dpi
            cache.pop(next(iter(cache)))
    return cache[key]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dpi", type=int, default=200,
                    help="page render DPI (200 = what the human annotation session uses)")
    ap.add_argument("--policies", nargs="+", default=POLICIES, choices=POLICIES)
    ap.add_argument("--no-caption", action="store_true",
                    help="ablation: withhold the caption, so the count constraint is gone")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--url", help="use an already-running server instead of starting one")
    ap.add_argument("--out", default=str(HERE / "out" / "panels_real.json"))
    ap.add_argument("--emit-pred", metavar="POLICY",
                    help="also write benchmark/real-validation/pred/<run>.jsonl in the shape "
                         "score_real_validation.py::load_preds expects, using this bbox "
                         "policy. This is the PREDICTION side only -- it is scoreable the "
                         "moment gt/<session>/panels_gt.jsonl exists, and meaningless "
                         "before that.")
    ap.add_argument("--pred-run", default="core_real",
                    help="run name for --emit-pred (default core_real)")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    items = json.loads(WORKLIST.read_text())["items"]
    if a.limit:
        items = items[:a.limit]

    srv, url = None, a.url
    if not url:
        srv = subprocess.Popen([sys.executable, "-m", "http.server", str(a.port)],
                               cwd=str(REPO), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        url = f"http://localhost:{a.port}"
        time.sleep(1.5)

    records, pageerrors, cache = [], [], {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            pg = browser.new_page()
            pg.on("pageerror", lambda e: pageerrors.append(str(e)))
            pg.goto(url + "/figure-extractor.html")
            pg.wait_for_function("() => typeof detectPanelsCore === 'function'", timeout=30000)
            for n, it in enumerate(items, 1):
                t_box = time.time()
                try:
                    bb = figure_bbox.boxes_for(it["pdf"], it["page0"], it["figure_number"],
                                               a.dpi, it["caption"])
                except Exception as e:
                    records.append({"item_id": it["item_id"], "bbox_error": str(e)})
                    print(f"[{n:2}/{len(items)}] {it['item_id']:<24} BBOX ERROR {e}")
                    continue
                box_ms = (time.time() - t_box) * 1000
                png = render_page_png(it["pdf"], it["page0"], a.dpi, cache)
                data = "data:image/png;base64," + base64.b64encode(png).decode()
                rec = {
                    "item_id": it["item_id"], "article": it["article"], "tier": it["tier"],
                    "figure": it["figure"], "page0": it["page0"], "dpi": a.dpi,
                    "caption_given": not a.no_caption,
                    "caption_expected_letters": it.get("caption_expected_letters"),
                    "caption_letter_count": it.get("caption_letter_count"),
                    "visual_tile_count_survey": it.get("visual_tile_count_survey"),
                    "letter_tile_mismatch": it.get("letter_tile_mismatch"),
                    "adversarial_features": it.get("adversarial_features", []),
                    "figure_source": it.get("figure_source"),
                    "n_image_xobjects": it.get("n_image_xobjects"),
                    "caption_found": bb["caption_found"], "caption_how": bb["caption_how"],
                    "page_px": bb["page_px"], "bbox_ms": round(box_ms, 1),
                    "n_image_rects_supplied": len(bb["image_rects_px"]),
                    "policies": {},
                }
                line = [f"[{n:2}/{len(items)}] {it['item_id']:<24}"]
                for pol in a.policies:
                    P = bb["policies"][pol]
                    entry = {"bbox_px": P["bbox_px"], "bbox_flags": P["flags"],
                             "bbox_info": P["info"],
                             "contamination": P.get("contamination", {})}
                    if P["bbox_px"] is None:
                        entry["result"] = {"status": "no-bbox"}
                        records_line = f"{pol}=NOBOX"
                    else:
                        try:
                            r = pg.evaluate(JS, {
                                "dataUrl": data, "W": bb["page_px"][0], "H": bb["page_px"][1],
                                "bounds": P["bbox_px"],
                                "caption": "" if a.no_caption else it["caption"],
                                "imageRects": bb["image_rects_px"]})
                        except Exception as e:
                            r = {"ok_call": False, "error": f"evaluate failed: {e}",
                                 "ms": None}
                        if not r.get("ok_call"):
                            entry["result"] = {"status": "exception", "error": r.get("error"),
                                               "ms": r.get("ms")}
                            records_line = f"{pol}=EXC"
                        else:
                            entry["result"] = {
                                "status": "ok", "count": r["count"], "method": r["method"],
                                "confidence": r["confidence"], "flags": r["flags"],
                                "tool_ok": r["ok"], "lettersVerified": r["lettersVerified"],
                                "letterSource": r["letterSource"],
                                "letters": [p["letter"] for p in r["panels"]],
                                "expected_from_caption": r["expected"],
                                # the detector's own refusal gate, verbatim from
                                # benchmark/panels/run_baseline.py
                                "abstain": (r["count"] < 2 or (r["confidence"] or 0) < 0.35
                                            or not r["ok"]),
                                "ms": round(r["ms"], 1),
                                "panels": [p["bounds"] for p in r["panels"]]}
                            records_line = (f"{pol}={r['count']}/{r['method']}"
                                            f"/{r['confidence']:.2f}"
                                            f"{'' if r['ok'] else '!'}")
                    rec["policies"][pol] = entry
                    line.append(records_line)
                line.append(f"cap={it.get('caption_letter_count')}"
                            f" tiles={it.get('visual_tile_count_survey')}")
                print("  ".join(line), flush=True)
                records.append(rec)
            browser.close()
    finally:
        if srv:
            srv.terminate()

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": "figure-extractor.html detectPanelsCore (unmodified)",
        "dpi": a.dpi, "caption_given": not a.no_caption,
        "policies": a.policies,
        "n_items": len(records),
        "page_js_errors": pageerrors[:20],
        "caveat": ("No panel-level ground truth exists for these figures. Counts are what "
                   "the detector emitted, not what the figures contain. The figure bboxes "
                   "are machine-derived (benchmark/real/figure_bbox.py); the tool's real "
                   "boxing is manual."),
        "records": records}, indent=1))
    print(f"\n[written] {out}   ({len(records)} items)")

    if a.emit_pred:
        # panel bboxes come back relative to the FIGURE box; the scorer's GT bboxes are
        # page-relative, so shift them back onto the page here rather than leaving a
        # coordinate-frame trap for whoever wires the GT side up.
        pd = REPO / "benchmark" / "real-validation" / "pred"
        pd.mkdir(parents=True, exist_ok=True)
        lines = []
        for r in records:
            P = (r.get("policies") or {}).get(a.emit_pred)
            if not P or (P.get("result") or {}).get("status") != "ok":
                continue
            R, fb = P["result"], P["bbox_px"]
            lines.append(json.dumps({
                "id": r["item_id"], "article": r["article"],
                "pageNum": r["page0"] + 1, "dpi": r["dpi"],
                "caption": "", "figureBbox": fb, "nPanels": R["count"],
                "origin": f"detectPanelsCore/bbox={a.emit_pred}",
                "panels": [{"letter": (R["letters"][i] or "").upper() or None,
                            "bbox": {"x": b["x"] + fb["x"], "y": b["y"] + fb["y"],
                                     "width": b["width"], "height": b["height"]}}
                           for i, b in enumerate(R["panels"])]}))
        p = pd / f"{a.pred_run}.jsonl"
        p.write_text("\n".join(lines) + "\n")
        print(f"[written] {p}   ({len(lines)} scoreable predictions, bbox policy "
              f"'{a.emit_pred}') -- NOT scoreable until human panels_gt.jsonl exists")
    if pageerrors:
        print(f"  page-level JS errors: {len(pageerrors)}  e.g. {pageerrors[0][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
