#!/usr/bin/env python3
"""Prove the harness's Python affine == the REAL tool, and produce the authoritative
geometry floor via window.figureExtractor.calibrate. For every GT bundle, feed the GT
calibration + GT landmark pixels through BOTH py_calibrate and the tool's own
calibrate() over Playwright, and report the max disagreement (should be ~0).

Needs: localhost:8001 serving figure-extractor.html + Playwright chromium.
Run (from repo root, server already up):  python3 benchmark/harness/crosscheck_js.py
"""
import asyncio, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from calibrate import py_calibrate  # noqa: E402
from score import load_bundles, tool_geometry_floor  # noqa: E402
URL = "http://localhost:8001/figure-extractor.html"


async def main():
    from playwright.async_api import async_playwright
    bundles = load_bundles()
    worst = 0.0; n = 0
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); pg = await b.new_page(); await pg.goto(URL)
        for bundle in bundles:
            to = tool_geometry_floor(bundle)
            pts = [{"px": l["px"], "py": l["py"]} for l in to["landmarks"]]
            js = await pg.evaluate("(a)=>window.figureExtractor.calibrate(a.c,a.v,a.l)",
                                   {"c": to["calPixels"], "v": to["calVals"], "l": pts})
            py = py_calibrate(to["calPixels"], to["calVals"], pts)
            for a, c in zip(py, js):
                worst = max(worst, abs(a["x"] - c["x"]), abs(a["y"] - c["y"])); n += 1
        await b.close()
    print(f"compared {n} recovered points across {len(bundles)} charts")
    print(f"max |py_calibrate - window.figureExtractor.calibrate| = {worst:.3e}")
    print("PASS: the harness uses the tool's own arithmetic." if worst < 1e-6
          else "FAIL: port diverges from the tool.")


if __name__ == "__main__":
    asyncio.run(main())
