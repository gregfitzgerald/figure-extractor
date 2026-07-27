#!/usr/bin/env python3
"""overlay_reads.py -- draw the reader's actual picks back onto each real panel.

The scored output (`out/fields.csv`) is a table of numbers; this puts those numbers back
where they came from, so the picks can be judged BY EYE against the printed chart:

  solid green   the pixel the reader called the bar top      -> extracted mean
  dashed amber  where the HAND-CODED mean says that top is   -> the central-channel gap
  solid red     the pixel the reader called the error cap    -> extracted dispersion
  dashed violet where the hand-coded SD says that cap is     -> the dispersion-channel gap
  blue crosses  the four axis reference pixels the calibration was built from

Two lines nearly touching means the read was good. A visible gap on the cap lines while the
bar-top lines coincide IS the dispersion-channel finding, drawn rather than asserted.

    python3 overlay_reads.py            # writes out/overlays/<id>.png
"""
import csv
import glob
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out" / "overlays"

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("needs Pillow: pip install Pillow")

GREEN, AMBER, RED, VIOLET, BLUE = ((22, 163, 74), (217, 119, 6), (220, 38, 38),
                                   (147, 51, 234), (37, 99, 235))


def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def dashed(d, y, x0, x1, colour, w=3, dash=14):
    x = x0
    while x < x1:
        d.line([(x, y), (min(x + dash, x1), y)], fill=colour, width=w)
        x += dash * 2


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fields = {}
    for r in csv.DictReader(open(HERE / "out" / "fields.csv")):
        fields[(r["id"], r["bar"])] = r

    made = []
    for tf in sorted(glob.glob(str(HERE / "tasks" / "*.json"))):
        t = json.loads(pathlib.Path(tf).read_text())
        vid = t["id"]
        vp = HERE / "vision" / f"{vid}.json"
        if not vp.exists():
            continue
        v = json.loads(vp.read_text())
        img = Image.open(HERE / t["image"]).convert("RGB")
        scale = max(1, int(1400 / img.width)) if img.width < 900 else 1
        if scale > 1:
            img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        f_lab = font(max(15, img.width // 62))

        cp, cv = v["calPixels"], t["calVals"]
        y1p, y2p = cp["y1"]["py"] * scale, cp["y2"]["py"] * scale
        y1v, y2v = float(cv["y1"]), float(cv["y2"])
        to_val = lambda py: y1v + (py - y1p) * (y2v - y1v) / (y2p - y1p)
        to_py = lambda val: y1p + (val - y1v) * (y2p - y1p) / (y2v - y1v)

        for k in ("x1", "x2", "y1", "y2"):                      # axis references
            x, y = cp[k]["px"] * scale, cp[k]["py"] * scale
            d.line([(x - 11, y), (x + 11, y)], fill=BLUE, width=3)
            d.line([(x, y - 11), (x, y + 11)], fill=BLUE, width=3)

        half = max(30, img.width // 22)
        for bar, b in v["bars"].items():
            row = fields.get((vid, bar))
            if not row:
                continue
            n = float(row["n"])
            bx = b["top"]["px"] * scale
            x0, x1 = bx - half, bx + half

            top_py = b["top"]["py"] * scale
            d.line([(x0, top_py), (x1, top_py)], fill=GREEN, width=4)
            dashed(d, to_py(float(row["mean_coded"])), x0, x1, AMBER)

            cap_py = b["cap"]["py"] * scale
            d.line([(x0, cap_py), (x1, cap_py)], fill=RED, width=4)
            # coded cap sits one SEM above the coded mean; these papers plot mean +/- SEM
            coded_cap_val = float(row["mean_coded"]) + float(row["sd_coded"]) / math.sqrt(n)
            dashed(d, to_py(coded_cap_val), x0, x1, VIOLET)

            # Just the bar name, under the axis. The numbers live in the HTML table beside
            # the image -- drawn on the chart they collide with each other on adjacent bars
            # and with the printed significance asterisks.
            d.text((bx, y1p + 10), bar, fill=(0, 0, 0), font=f_lab, anchor="ma",
                   stroke_width=4, stroke_fill=(255, 255, 255))

        p = OUT / f"{vid}.png"
        img.save(p)
        made.append(p)
        print(f"[written] {p.relative_to(HERE)}  ({img.width}x{img.height})")
    print(f"\n{len(made)} overlay(s)")


if __name__ == "__main__":
    main()
