#!/usr/bin/env python3
"""refetch_captions.py -- pull FULL captions from the PDFs, because the worklist's are truncated.

19 of the 71 worklist captions are exactly 1200 characters and 43.7% end mid-word: the
worklist stores a truncated copy. Everything measured against those captions is therefore
measured on mutilated input --

  * the caption parse rate is pessimistic (letters past the cut cannot be found), and
  * worse, `detectPanelsCore` takes the caption's letter count as a HARD CONSTRAINT on the
    geometry, so a truncated caption hands it a short count and the split is wrong or
    refused for a reason that has nothing to do with the figure.

This re-extracts each figure's caption from its PDF text layer and reports how much the
parse rate moves, so the published real-caption numbers describe the parser rather than the
corpus. It writes a sidecar; it does NOT edit worklist.json, which has another owner.

    python3 refetch_captions.py            # extract + report
    python3 refetch_captions.py --score    # ... and re-score the parser on full captions
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
WORKLIST = REPO / "benchmark" / "real-validation" / "worklist.json"
OUT = HERE / "out" / "captions_full.json"


def caption_from_page(page, fignum):
    """Text from the 'Figure N' label to the end of its block, then following blocks until a
    blank line or a new figure label. Deliberately generous: over-reading costs a few stray
    sentences, under-reading loses panel letters, and losing letters is what we are fixing."""
    blocks = page.get_text("blocks")
    blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
    pat = re.compile(rf"(?:supplementary\s+|extended\s+data\s+)?fig(?:ure)?s?\.?\s*{fignum}\b",
                     re.I)
    start = None
    for i, b in enumerate(blocks):
        if pat.search(b[4] or ""):
            start = i
            break
    if start is None:
        return None
    m = pat.search(blocks[start][4])
    parts = [blocks[start][4][m.start():]]
    other = re.compile(r"fig(?:ure)?s?\.?\s*(\d+)", re.I)
    for b in blocks[start + 1:]:
        t = (b[4] or "").strip()
        if not t:
            break
        mm = other.match(t)
        if mm and mm.group(1) != str(fignum):
            break
        parts.append(t)
        if len(" ".join(parts)) > 6000:
            break
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()

    import fitz
    items = json.loads(WORKLIST.read_text())["items"]
    out, longer, failed = [], 0, 0
    for it in items:
        pdf = it.get("pdf")
        if not pdf or not pathlib.Path(pdf).exists():
            failed += 1
            continue
        num = it.get("figure_number") or re.sub(r"\D", "", it.get("figure") or "")
        try:
            doc = fitz.open(pdf)
            cap = caption_from_page(doc[it.get("page0", 0)], num)
            doc.close()
        except Exception as e:
            print(f"  ! {it['item_id']}: {e}", file=sys.stderr)
            failed += 1
            continue
        old = (it.get("caption") or "").strip()
        if not cap:
            failed += 1
            continue
        if len(cap) > len(old):
            longer += 1
        out.append({"id": it["item_id"], "full": cap, "worklist": old,
                    "lenFull": len(cap), "lenWorklist": len(old)})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"schemaVersion": 1, "captions": out}, indent=1),
                   encoding="utf-8")
    print(f"[written] {OUT}")
    print(f"  {len(out)} captions re-extracted, {failed} could not be located")
    print(f"  longer than the worklist copy: {longer}/{len(out)}")
    if out:
        gain = [o["lenFull"] - o["lenWorklist"] for o in out]
        gain.sort()
        print(f"  length delta: median {gain[len(gain)//2]:+d} chars, max {gain[-1]:+d}")

    if not a.score:
        return 0

    from playwright.sync_api import sync_playwright
    JS = ("(caps)=>caps.map(c=>{let r=null;try{r=expectedPanelsFromCaption(c.t)}catch(e){};"
          "return {id:c.id,n:r?r.letters.length:null}})")
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page()
        pg.goto((REPO / "figure-extractor.html").as_uri())
        pg.wait_for_function("() => typeof expectedPanelsFromCaption === 'function'",
                             timeout=20000)
        old_r = {x["id"]: x["n"] for x in pg.evaluate(
            JS, [{"id": o["id"], "t": o["worklist"]} for o in out])}
        new_r = {x["id"]: x["n"] for x in pg.evaluate(
            JS, [{"id": o["id"], "t": o["full"]} for o in out])}
        b.close()
    po = sum(1 for v in old_r.values() if v)
    pn = sum(1 for v in new_r.values() if v)
    print(f"\nPARSE RATE on the same {len(out)} figures")
    print(f"  worklist (truncated) captions : {po}/{len(out)} = {100*po/len(out):.1f}%")
    print(f"  full captions from the PDF    : {pn}/{len(out)} = {100*pn/len(out):.1f}%")
    more = [i for i in new_r if (new_r[i] or 0) > (old_r[i] or 0)]
    print(f"  figures where the full caption yields MORE panels: {len(more)}")
    for i in more[:8]:
        print(f"      {i}: {old_r[i]} -> {new_r[i]}")
    return 0


sys.exit(main())
