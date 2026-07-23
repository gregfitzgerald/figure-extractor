#!/usr/bin/env python3
"""grid_overlay.py -- draw a labeled pixel-coordinate grid over a panel PNG so a vision
reader (human or model) can read landmark/calibration pixel coordinates precisely and
reproducibly. The overlaid grid is a READING AID only; the picked coordinates are recorded
in a vision/<id>.json and scored through the shared affine. Grid spacing default 25px, with
labeled major lines every 100px.

Usage: python3 grid_overlay.py panels/<in>.png [--step 25] [--out panels/<in>_grid.png]
"""
import argparse, pathlib
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent


def overlay(src, step, out):
    im = Image.open(src).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    for x in range(0, W, step):
        major = x % 100 == 0
        d.line([(x, 0), (x, H)], fill=(255, 0, 255) if major else (255, 170, 255),
               width=2 if major else 1)
        if major:
            d.text((x + 2, 2), str(x), fill=(200, 0, 200))
            d.text((x + 2, H - 12), str(x), fill=(200, 0, 200))
    for y in range(0, H, step):
        major = y % 100 == 0
        d.line([(0, y), (W, y)], fill=(0, 150, 255) if major else (170, 220, 255),
               width=2 if major else 1)
        if major:
            d.text((2, y + 1), str(y), fill=(0, 90, 200))
            d.text((W - 30, y + 1), str(y), fill=(0, 90, 200))
    im.save(out)
    print(f"[written] {out}  ({W}x{H}, grid step={step}px, major/labels @100px)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=int, default=25)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    src = pathlib.Path(a.src)
    if not src.is_absolute():
        src = HERE / src
    out = a.out or str(src.with_name(src.stem + "_grid.png"))
    overlay(src, a.step, out)
