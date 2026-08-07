#!/usr/bin/env python3
"""overlay_panels_real.py -- draw run_real_panels.py's detected panel boxes on the figure.

Written for the results the detector did NOT abstain on: those are the only ones it asks
to be believed, so they are the ones that must be falsifiable by eye. This produces the
picture; it does not produce a verdict, and nothing here is ground truth.

Usage:
  python3 benchmark/real/overlay_panels_real.py --policy xobject --only-trusted
  python3 benchmark/real/overlay_panels_real.py --policy cluster --ids Zhang2017_F3
"""
import argparse, json, pathlib, sys
import fitz
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out" / "panels_overlay"
COL = [(220, 20, 20), (0, 130, 220), (0, 160, 60), (230, 130, 0),
       (150, 0, 200), (0, 160, 160), (200, 0, 120), (110, 90, 0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(HERE / "out" / "panels_real.json"))
    ap.add_argument("--policy", default="xobject")
    ap.add_argument("--only-trusted", action="store_true",
                    help="only figures where the detector did NOT abstain")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--dpi", type=int, default=110)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    D = json.loads(pathlib.Path(a.inp).read_text())
    wl = {i["item_id"]: i for i in json.loads(
        (HERE.parent / "real-validation" / "worklist.json").read_text())["items"]}
    sheet = []
    for r in D["records"]:
        P = (r["policies"].get(a.policy) or {})
        res = P.get("result") or {}
        if res.get("status") != "ok":
            continue
        if a.only_trusted and res["abstain"]:
            continue
        if a.ids and r["item_id"] not in a.ids:
            continue
        it = wl[r["item_id"]]
        # bbox_px is in run-DPI pixels; rescale to the overlay DPI
        k = a.dpi / r["dpi"]
        fb = P["bbox_px"]
        doc = fitz.open(it["pdf"])
        clip = fitz.Rect(fb["x"], fb["y"], fb["x"] + fb["width"], fb["y"] + fb["height"])
        clip = fitz.Rect(*[v * 72.0 / r["dpi"] for v in clip])
        pix = doc[it["page0"]].get_pixmap(dpi=a.dpi, clip=clip)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGB")
        d = ImageDraw.Draw(im)
        for i, b in enumerate(res["panels"]):
            c = COL[i % len(COL)]
            d.rectangle([b["x"] * k, b["y"] * k,
                         (b["x"] + b["width"]) * k, (b["y"] + b["height"]) * k],
                        outline=c, width=3)
            d.text((b["x"] * k + 5, b["y"] * k + 3),
                   (res["letters"][i] or "?").upper(), fill=c)
        p = OUT / f"{r['item_id']}_{a.policy}.png"
        im.save(p)
        sheet.append((f"{r['item_id']} n={res['count']} {res['method']} "
                      f"conf={res['confidence']}", im))
        doc.close()
        print(f"  {p}")
    if sheet:
        CW, CH, COLS = 460, 380, 3
        rows = (len(sheet) + COLS - 1) // COLS
        s = Image.new("RGB", (COLS * CW, rows * (CH + 18)), (255, 255, 255))
        dr = ImageDraw.Draw(s)
        for k2, (name, im) in enumerate(sheet):
            c = im.copy()
            c.thumbnail((CW - 8, CH - 8))
            x, y = (k2 % COLS) * CW, (k2 // COLS) * (CH + 18)
            s.paste(c, (x + 4, y + 16))
            dr.text((x + 4, y + 3), name, fill=(0, 0, 0))
        p = OUT / f"sheet_{a.policy}{'_trusted' if a.only_trusted else ''}.png"
        s.save(p)
        print(f"[sheet] {p}")


if __name__ == "__main__":
    sys.exit(main())
