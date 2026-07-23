#!/usr/bin/env python3
"""render.py -- locate a figure in an article PDF and render/crop it to PNG for reading.

Two jobs:
  locate  -- text-search the PDF for a figure's caption ("Fig. 3", "Figure 3") and report
             which page(s) mention it, so we know which page carries the panel.
  render  -- rasterise a page at high DPI (default 200) to panels/<article>_p<page>.png,
             optionally cropping a pixel box to isolate one panel.

Rendering real journal figures at high DPI is what surfaces the realism gap the synthetic
benchmark cannot: anti-aliasing, JPEG blocking, hand-drawn error caps, thin whiskers.

Usage:
  python3 render.py locate <article> [--fig N]
  python3 render.py render <article> --page P [--dpi D] [--crop x0,y0,x1,y1] [--out name.png]
"""
import argparse, json, pathlib, re, sys
import fitz  # PyMuPDF

HERE = pathlib.Path(__file__).resolve().parent
PANELS = HERE / "panels"
PANELS.mkdir(exist_ok=True)


def pdf_for(article):
    m = json.loads((HERE / "pdf_map.json").read_text())
    rec = m.get(article)
    if not rec or rec["status"] != "ok":
        sys.exit(f"no resolved PDF for {article}: {rec}")
    return rec["pdf"]


def locate(article, fig=None):
    doc = fitz.open(pdf_for(article))
    pats = ([rf"fig(?:ure|\.)?\s*{fig}\b"] if fig else [r"fig(?:ure|\.)?\s*\d+"])
    print(f"{article}: {doc.page_count} pages, {pdf_for(article)}")
    for pno in range(doc.page_count):
        text = doc[pno].get_text()
        hits = set()
        for pat in pats:
            for m in re.finditer(pat, text, re.I):
                hits.add(m.group(0).strip())
        if hits:
            print(f"  page {pno}: {sorted(hits)[:8]}")


def render(article, page, dpi, crop, out):
    doc = fitz.open(pdf_for(article))
    pg = doc[page]
    pix = pg.get_pixmap(dpi=dpi)
    outp = PANELS / (out or f"{article}_p{page}_{dpi}dpi.png")
    if crop:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(pix.tobytes("png")))
        x0, y0, x1, y1 = crop
        im = im.crop((x0, y0, x1, y1))
        im.save(outp)
        print(f"[written] {outp}  crop=({x0},{y0},{x1},{y1}) size={im.size} (from {pix.width}x{pix.height} @ {dpi}dpi)")
    else:
        pix.save(outp)
        print(f"[written] {outp}  {pix.width}x{pix.height} @ {dpi}dpi")
    win = str(outp).replace('/mnt/c/', 'C:/').replace('/', '\\')
    print(f"WINDOWS: {win}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    lo = sub.add_parser("locate"); lo.add_argument("article"); lo.add_argument("--fig", type=int)
    re_ = sub.add_parser("render"); re_.add_argument("article")
    re_.add_argument("--page", type=int, required=True); re_.add_argument("--dpi", type=int, default=200)
    re_.add_argument("--crop", type=str, default=None); re_.add_argument("--out", type=str, default=None)
    a = ap.parse_args()
    if a.cmd == "locate":
        locate(a.article, a.fig)
    else:
        crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
        render(a.article, a.page, a.dpi, crop, a.out)
