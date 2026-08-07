#!/usr/bin/env python3
"""render_bbox_overlays.py -- render what each bbox policy hands the panel detector.

Two products, both written to benchmark/real/out/bbox/:
  <item>_page.png    the whole page with the caption (green), capband (blue) and
                     cluster (red) rectangles drawn on it
  <item>_crop.png    the cluster-policy crop alone -- i.e. exactly the pixels the panel
                     detector partitions

and contact sheets sheet_NN.png of the crops, so a human can check in one pass whether
the automatic figure boxing isolated the figure. The bboxes are machine output; these
images exist so that claim can be falsified by eye rather than asserted.

Usage:  python3 benchmark/real/render_bbox_overlays.py [--dpi 200] [--sheet-dpi 72]
"""
import argparse, json, pathlib, sys
import fitz
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import figure_bbox

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out" / "bbox"
WORKLIST = REPO / "benchmark" / "real-validation" / "worklist.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--sheet-dpi", type=int, default=70)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    items = json.loads(WORKLIST.read_text())["items"]
    if a.limit:
        items = items[:a.limit]
    from PIL import Image, ImageDraw
    crops = []
    for it in items:
        b = figure_bbox.boxes_for(it["pdf"], it["page0"], it["figure_number"],
                                  a.dpi, it["caption"])
        doc = fitz.open(it["pdf"])
        pg = doc[it["page0"]]
        # page overlay at sheet dpi (small)
        s = a.sheet_dpi / 72.0
        pix = pg.get_pixmap(dpi=a.sheet_dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        d = ImageDraw.Draw(im)
        if b.get("caption_rect_pt"):
            d.rectangle([v * s for v in b["caption_rect_pt"]], outline=(0, 160, 0), width=2)
        for pol, col in (("capband", (0, 80, 255)), ("cluster", (230, 0, 0))):
            pt = b["policies"][pol]["bbox_pt"]
            if pt:
                d.rectangle([v * s for v in pt], outline=col, width=2)
        im.save(OUT / f"{it['item_id']}_page.png")
        # cluster crop at sheet dpi for the contact sheet
        pt = b["policies"]["cluster"]["bbox_pt"]
        if pt:
            cp = pg.get_pixmap(dpi=a.sheet_dpi, clip=fitz.Rect(*pt))
            ci = Image.frombytes("RGB", (cp.width, cp.height), cp.samples)
        else:
            ci = Image.new("RGB", (200, 200), (255, 200, 200))
        crops.append((it["item_id"], ci))
        doc.close()
        print(f"  {it['item_id']:<24} cluster={pt} flags={b['policies']['cluster']['flags']}")
    # contact sheets, 3x4
    from PIL import ImageFont
    CW, CH, COLS, ROWS = 380, 300, 3, 4
    per = COLS * ROWS
    for si in range(0, len(crops), per):
        chunk = crops[si:si + per]
        sheet = Image.new("RGB", (COLS * CW, ROWS * (CH + 18)), (255, 255, 255))
        dr = ImageDraw.Draw(sheet)
        for k, (name, ci) in enumerate(chunk):
            c = ci.copy()
            c.thumbnail((CW - 8, CH - 8))
            x, y = (k % COLS) * CW, (k // COLS) * (CH + 18)
            sheet.paste(c, (x + 4, y + 16))
            dr.text((x + 4, y + 3), name, fill=(0, 0, 0))
            dr.rectangle([x + 2, y + 14, x + CW - 2, y + CH + 16], outline=(180, 180, 180))
        p = OUT / f"sheet_{si//per:02d}.png"
        sheet.save(p)
        print(f"[sheet] {p}")


if __name__ == "__main__":
    main()
