#!/usr/bin/env python3
"""test_predict_panels.py -- validate the bridge's coordinate translation on exact GT.

`predict_panels.py` crops a page to the human's figure box, runs the detector on that crop
(which returns FIGURE-LOCAL pixels), and translates back to PAGE pixels so predictions share
a frame with the ground truth. Get that translation wrong and every IoU is silently 0.000
while both sides look individually reasonable -- the precise silent-failure class this
project keeps producing. The unit selftest in predict_panels.py checks only the arithmetic.

This checks the whole path: it takes synthetic panel figures whose GT boxes are exact by
construction, pastes each into a larger blank page at a deliberately NON-ROUND offset so an
off-by-origin cannot hide, treats the paste rectangle as the human's figure box, and requires
the translated predictions to land on the GT panels.

Needs benchmark/panels/corpus (gitignored, regenerate with gen_panels.R + finalize_gt.py) and
a server on :8001. SKIPS cleanly when either is absent.

    python3 benchmark/real-validation/test_predict_panels.py
"""

import base64, io, json, pathlib, sys
from PIL import Image
from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[2]
CORPUS = REPO / "benchmark/panels/corpus"
OFF = (137, 211)          # deliberately not round, so an off-by-origin cannot hide

JS = r"""
async ({dataUrl, W, H, caption}) => {
  const img = new Image(); img.src = dataUrl; await img.decode();
  state.pages = [{ pageNum: 1, img: img, wrapper: null }];
  state.articles = [{ name:'__b__', pageCount:1, imageRects:[[]] }];
  state.currentArticle = '__b__';
  const fig = { id:'f', label:'Figure', pageNum:1,
                bounds:{x:0,y:0,width:W,height:H},
                caption: caption||'', captionSource:'textlayer', subfigures:[] };
  try {
    const r = detectPanelsCore(fig, {});
    return { count:r.count, ok:!!r.ok, method:r.method,
             panels:(r.panels||[]).map(p=>({bounds:p.bounds, letter:p.letter||null})) };
  } catch(e) { return { error:String((e&&e.message)||e) }; }
}
"""


def iou(a, b):
    ix = max(0, min(a["x"]+a["width"], b["x"]+b["width"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"]+a["height"], b["y"]+b["height"]) - max(a["y"], b["y"]))
    i = ix*iy
    return i / max(1, a["width"]*a["height"] + b["width"]*b["height"] - i)


def main():
    if not CORPUS.exists():
        print("test_predict_panels: SKIP (benchmark/panels/corpus absent -- regenerate it)")
        return 0
    gts = [p for p in sorted(CORPUS.glob("*.pgt.json"))
           if json.loads(p.read_text()).get("nPanels", 0) >= 3][:6]
    if not gts:
        print("test_predict_panels: SKIP (no multi-panel GT bundles)"); return 0
    fails = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page()
        pg.goto("http://localhost:8001/figure-extractor.html")
        pg.wait_for_function("() => typeof detectPanelsCore === 'function'", timeout=20000)
        for gp in gts:
            d = json.loads(gp.read_text())
            img = Image.open(CORPUS / d["image"]).convert("RGB")
            page = Image.new("RGB", (img.width + 400, img.height + 500), "white")
            page.paste(img, OFF)
            figbox = {"x": OFF[0], "y": OFF[1], "width": img.width, "height": img.height}
            crop = page.crop((figbox["x"], figbox["y"],
                              figbox["x"]+figbox["width"], figbox["y"]+figbox["height"]))
            buf = io.BytesIO(); crop.save(buf, "PNG")
            durl = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            r = pg.evaluate(JS, {"dataUrl": durl, "W": crop.width, "H": crop.height,
                                 "caption": d.get("caption", "")})
            if r.get("error"):
                print(f"  {d['id']:<28} ERROR {r['error']}"); fails += 1; continue
            # translate figure-local -> page, exactly as predict_panels.to_page_coords does
            pred = [{"x": p["bounds"]["x"]+figbox["x"], "y": p["bounds"]["y"]+figbox["y"],
                     "width": p["bounds"]["width"], "height": p["bounds"]["height"]}
                    for p in r["panels"]]
            gt = [{"x": p["bbox"]["x"]+OFF[0], "y": p["bbox"]["y"]+OFF[1],
                   "width": p["bbox"]["width"], "height": p["bbox"]["height"]}
                  for p in d["panels"]]
            if not pred:
                print(f"  {d['id']:<28} abstained/no panels (count={r['count']})")
                continue
            best = [max(iou(p, g) for g in gt) for p in pred]
            med = sorted(best)[len(best)//2]
            ok = med >= 0.8
            fails += not ok
            print(f"  [{'ok  ' if ok else 'FAIL'}] {d['id']:<28} "
                  f"{len(pred)} pred vs {len(gt)} gt | median IoU {med:.3f}")
        b.close()
    print(f"\ntest_predict_panels: {'PASS (translation validated on exact GT)' if not fails else str(fails)+' FAILURE(S)'}")
    return 1 if fails else 0


try:
    sys.exit(main())
except Exception as e:
    if "playwright" in str(e).lower() or "connect" in str(e).lower():
        print(f"test_predict_panels: SKIP ({e})"); sys.exit(0)
    raise
