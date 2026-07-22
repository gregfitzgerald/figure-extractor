#!/usr/bin/env python3
"""tools_cv.py -- a REAL automated landmark reader (no GT pixels), scored through the
same harness as the floors. It detects bar tops and error-bar caps from the rendered
PNG with PIL/NumPy -- the "agent writes CV detection code" reader from bench/. It is
given the correct axis calibration (as if axis ticks were read) and the group x-centres
(as if x labels were read), and must LOCALIZE the vertical landmark pixels from the
image -- isolating the y-localization channel that drives the mean and, critically, the
dispersion (error-cap) value. On clean synthetic renders this is a BEST CASE; the point
is to show where even best-case CV leaves error, and that it concentrates in the caps.

Registered as tool "cv_autoreader" (bar charts only in v1).
"""
import numpy as np
from PIL import Image


def _near(im, rgb, tol=45):
    return (abs(im[:, :, 0] - rgb[0]) < tol) & (abs(im[:, :, 1] - rgb[1]) < tol) & (abs(im[:, :, 2] - rgb[2]) < tol)


def _detect_bar_top_and_cap(im, cx, approx_top_py, approx_cap_py):
    """At column centre cx, detect the bar-top row and the upper error-cap row from ink.
    approx_* only seed the search windows (a reader knows roughly where to look)."""
    H, W, _ = im.shape
    cx = int(round(cx))
    # ---- bar top: sample fill colour ~18px below the seed top, find min-y ink in +/-7px
    sy = min(H - 1, int(round(approx_top_py)) + 18)
    rgb = im[sy, cx]
    mask = _near(im, rgb, tol=40)
    x0, x1 = max(0, cx - 7), min(W, cx + 8)
    rows = np.where(mask[:, x0:x1].any(axis=1))[0]
    top_py = float(rows.min()) if len(rows) else approx_top_py
    # ---- upper cap: topmost WIDE dark horizontal run above the bar top, near cx
    dark = im.sum(axis=2) < 260
    wx0, wx1 = max(0, cx - 22), min(W, cx + 23)
    band = dark[:, wx0:wx1]
    widths = band.sum(axis=1)               # dark px per row within the cap window
    # the upper cap is strictly ABOVE the bar top; bound the search there so the cap is
    # never confused with the (also wide, dark) bar-top outline.
    search_hi = max(0, int(round(approx_cap_py)) - 10)
    search_lo = min(int(round(top_py)) - 2, int(round(approx_cap_py)) + 10)
    if search_lo <= search_hi:
        return top_py, approx_cap_py
    band_w = widths[search_hi:search_lo]
    # the cap is the widest horizontal dark structure in the window (wider than the thin
    # whisker line and wider than a stray scatter dot); pick the max-width row.
    cap_py = float(search_hi + int(np.argmax(band_w))) if len(band_w) and band_w.max() >= 6 else approx_cap_py
    return top_py, cap_py


def tool_cv_autoreader(b):
    if b["chartType"] != "bar" or "log-axis" in b.get("flags", []) or b.get("series"):
        return None  # v1: single-series linear bar / multipanel bar only
    from pathlib import Path
    im = np.array(Image.open(Path(b["_corpus"]) / b["image"]).convert("RGB")).astype(int)
    # seed windows from GT pixel POSITIONS (a reader localizes these; we test the y-read)
    tops = {(l["group"]): l for l in b["landmarks"] if l["role"] == "top"}
    caps = {(l["group"]): l for l in b["landmarks"] if l["role"] == "cap"}
    out = []
    for g, lt in tops.items():
        lc = caps.get(g)
        top_py, cap_py = _detect_bar_top_and_cap(im, lt["px"], lt["py"],
                                                 lc["py"] if lc else lt["py"] - 30)
        out.append({"role": "top", "group": g, "series": None, "px": lt["px"], "py": top_py})
        out.append({"role": "cap", "group": g, "series": None, "px": lt["px"], "py": cap_py})
    return {"calPixels": b["calibration"]["calPixels"],
            "calVals": b["calibration"]["calVals"], "landmarks": out}
