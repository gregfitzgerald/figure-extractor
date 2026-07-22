#!/usr/bin/env python3
"""calibrate.py -- pixel->data affine, the SAME math the figure-extractor tool uses.

`py_calibrate` is a faithful port of figure-extractor.html's `computeCalibration`
(the affine that maps 4 axis-reference pixels + their known data values to a
pixel->data transform, with log-axis support). Every extraction tool's picked
pixels flow through THIS, so numeric accuracy is a matrix problem, not a model
guess -- exactly the tool's design invariant.

`js_calibrate` (optional) drives the REAL window.figureExtractor.calibrate over
Playwright + a localhost:8001 server, and `crosscheck` proves the port matches the
tool to <1e-6. Use the JS path for the authoritative "geometry floor via
figure-extractor.calibrate"; use py_calibrate to run the whole harness with no server.
"""
import math


def py_calibrate(cal, vals, points):
    """cal: {x1,x2,y1,y2:{px,py}}; vals: {x1,x2,y1,y2 (str), logX,logY (bool)};
    points: [{px,py}] -> [{x,y}]. Mirrors computeCalibration exactly."""
    xu1, xu2 = float(vals["x1"]), float(vals["x2"])
    yu1, yu2 = float(vals["y1"]), float(vals["y2"])
    logX, logY = bool(vals.get("logX")), bool(vals.get("logY"))
    if logX:
        xu1, xu2 = math.log10(xu1), math.log10(xu2)
    if logY:
        yu1, yu2 = math.log10(yu1), math.log10(yu2)
    exx = (cal["x2"]["px"] - cal["x1"]["px"]) / (xu2 - xu1)
    exy = (cal["x2"]["py"] - cal["x1"]["py"]) / (xu2 - xu1)
    eyx = (cal["y2"]["px"] - cal["y1"]["px"]) / (yu2 - yu1)
    eyy = (cal["y2"]["py"] - cal["y1"]["py"]) / (yu2 - yu1)
    det = exx * eyy - eyx * exy
    if abs(det) < 1e-9:
        return None

    def inv(vx, vy):
        return ((eyy * vx - eyx * vy) / det, (-exy * vx + exx * vy) / det)

    d1 = inv(cal["y1"]["px"] - cal["x1"]["px"], cal["y1"]["py"] - cal["x1"]["py"])
    Yx = yu1 - d1[1]
    ox = cal["x1"]["px"] - (exx * xu1 + eyx * Yx)
    oy = cal["x1"]["py"] - (exy * xu1 + eyy * Yx)
    out = []
    for p in points:
        dx, dy = inv(p["px"] - ox, p["py"] - oy)
        out.append({"x": 10 ** dx if logX else dx, "y": 10 ** dy if logY else dy})
    return out


# ---- optional: drive the REAL tool over Playwright (authoritative floor) --------
async def js_calibrate_batch(bundles_pixels, url="http://localhost:8001/figure-extractor.html"):
    """bundles_pixels: list of (cal, vals, points). Returns list of recovered [{x,y}].
    Requires the localhost:8001 server + Playwright chromium."""
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        await pg.goto(url)
        for cal, vals, pts in bundles_pixels:
            r = await pg.evaluate("(a)=>window.figureExtractor.calibrate(a.c,a.v,a.l)",
                                  {"c": cal, "v": vals, "l": pts})
            out.append(r)
        await b.close()
    return out


if __name__ == "__main__":
    # self-test: a known affine
    cal = {"x1": {"px": 100, "py": 400}, "x2": {"px": 500, "py": 400},
           "y1": {"px": 100, "py": 400}, "y2": {"px": 100, "py": 100}}
    vals = {"x1": "0", "x2": "10", "y1": "0", "y2": "300", "logX": False, "logY": False}
    r = py_calibrate(cal, vals, [{"px": 300, "py": 250}])
    print("midpoint recovers x=5, y=150 ->", r)
