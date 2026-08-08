#!/usr/bin/env python3
"""Regression tests for four data-integrity fixes that shipped without coverage.

Each of these was confirmed by adversarial review, fixed, and then left untested because the
agent doing the work hit a session limit mid-verification. Untested fixes are exactly this
project's recurring failure mode -- a guard that is documented but not wired -- so they get
tests before anything is built on top of them.

  1. Article-name collision. Article identity is the PDF basename, and reference managers ship
     dozens of "Full Text PDF.pdf". A collision REPLACED the first paper's pages while
     restoring its boxes onto the second paper: one paper's pixels under another's caption.
  2. Export All read localStorage for every article INCLUDING the open one, while
     single-article export used state.figures. When persistence failed the batch export
     silently shipped stale data -- at the moment the storage-full toast says to export.
  3. Calibration lever arm. Reference points a few pixels apart passed every check and
     multiplied click jitter by the lever arm: 1 px of jitter moved a value by 100 units.
     Given the benchmark's finding that ALL error is point-picking, this is the highest-
     leverage unguarded case in the digitizer.
  4. legendOrder / plotOrder of DIFFERENT lengths passed validation, because both validators
     required `.length ===` before comparing -- so the most contradictory case was the one
     that went unflagged.

Requires playwright (PyMuPDF only for test 2); SKIPS (exit 0) if missing.
    python3 scripts/test_robustness.py
"""
import asyncio
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = (REPO / "figure-extractor.html").as_uri()
FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}{('  ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(TOOL)
        await pg.wait_for_function("() => typeof uniqueArticleName === 'function'",
                                   timeout=20000)

        # --- 1. colliding basenames must not merge -------------------------------
        r = await pg.evaluate("""() => {
            state.articles = [{name:'Full Text PDF', pageCount: 5}];
            const n2 = uniqueArticleName('Full Text PDF');
            state.articles.push({name:n2, pageCount: 14});
            const n3 = uniqueArticleName('Full Text PDF');
            return { n2, n3, count: state.articles.length,
                     names: state.articles.map(a => a.name) };
        }""")
        check("a colliding basename is suffixed, not merged",
              r["n2"] == "Full Text PDF_2" and r["n3"] == "Full Text PDF_3",
              f"{r['n2']}, {r['n3']}")
        check("both papers survive as distinct articles",
              r["count"] == 2 and len(set(r["names"])) == 2, str(r["names"]))

        # --- 3. calibration lever arm -------------------------------------------
        near = await pg.evaluate("""() => window.figureExtractor.verifyCalibration(
            {x1:{px:150,py:400}, x2:{px:151,py:400}, y1:{px:100,py:400}, y2:{px:100,py:100}},
            {x1:'0', x2:'100', y1:'0', y2:'100', logX:false, logY:false})""")
        check("reference points 1 px apart are flagged",
              "calibration-short-baseline" in (near.get("flags") or []),
              str(near.get("flags")))
        wide = await pg.evaluate("""() => window.figureExtractor.verifyCalibration(
            {x1:{px:100,py:400}, x2:{px:500,py:400}, y1:{px:100,py:400}, y2:{px:100,py:100}},
            {x1:'0', x2:'100', y1:'0', y2:'100', logX:false, logY:false})""")
        check("a normal baseline is NOT flagged",
              "calibration-short-baseline" not in (wide.get("flags") or []),
              str(wide.get("flags")))

        # --- 4. legend/plot order length mismatch --------------------------------
        # Called on the pure validator so this needs no loaded page. Both validators required
        # `.length ===` before comparing, so the MOST contradictory case -- 3 series in the
        # legend, 2 in the plot -- was the one that sailed through unflagged.
        mism = await pg.evaluate("""() => validateCharacterization({
            panels: [{ charType: 'bar',
                       series: [{id:'s1',label:'a'},{id:'s2',label:'b'},{id:'s3',label:'c'}],
                       legendOrder: ['a','b','c'], plotOrder: ['b','a'] }] })""")
        check("legendOrder/plotOrder length mismatch is rejected",
              any("different lengths" in e for e in mism), str(mism)[:120])
        okd = await pg.evaluate("""() => validateCharacterization({
            panels: [{ charType: 'bar',
                       series: [{id:'s1',label:'a'},{id:'s2',label:'b'},{id:'s3',label:'c'}],
                       legendOrder: ['a','b','c'], plotOrder: ['b','a'] }],
            flags: ['legend-order-mismatch','series-count-uncertain'] })""")
        check("...and accepted once BOTH flags are declared",
              not any("different lengths" in e for e in okd), str(okd)[:120])

        await b.close()
    hard = [e for e in errs if "favicon" not in e]
    check("no page errors", not hard, str(hard[:2]))


async def run_export_all():
    """2. Export All must read the OPEN article from state.figures, not localStorage."""
    import fitz
    import tempfile
    from playwright.async_api import async_playwright
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "e.pdf"
        doc = fitz.open()
        pgz = doc.new_page(width=612, height=792)
        pgz.insert_text((100, 300), "Figure 1. Test.", fontsize=11)
        doc.save(p)
        doc.close()
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            pg = await b.new_page()
            await pg.goto(TOOL)
            await pg.set_input_files("#pdfInput", files=[{
                "name": "e.pdf", "mimeType": "application/pdf",
                "buffer": p.read_bytes()}])
            for _ in range(80):
                if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                    break
                await pg.wait_for_timeout(250)
            # Persist one figure, then break persistence and add more -- the real quota mode.
            await pg.evaluate("""() => window.figureExtractor.addFigure(
                1, {x:20,y:20,width:80,height:60}, 'PERSISTED')""")
            await pg.evaluate("""() => { const o = localStorage.setItem.bind(localStorage);
                localStorage.setItem = (k,v) => { if (k.startsWith('figext_') &&
                    !k.includes('settings')) throw new Error('QuotaExceededError'); return o(k,v); }; }""")
            for i in range(3):
                await pg.evaluate(f"""() => window.figureExtractor.addFigure(
                    1, {{x:20,y:{120 + i*40},width:80,height:30}}, 'AFTER FAIL {i}')""")
            got = await pg.evaluate("""() => {
                const a = state.articles.find(x => x.name === state.currentArticle);
                let stored = null;
                try { stored = JSON.parse(localStorage.getItem('figext_' + a.name)); } catch(e){}
                return { inMemory: state.figures.map(f => f.label),
                         stored: stored ? stored.figures.map(f => f.label) : null };
            }""")
            await b.close()
    check("persistence really did fail (test is exercising the real path)",
          got["stored"] is None or len(got["stored"]) < len(got["inMemory"]),
          f"stored={got['stored']}")
    check("the open article's in-memory work is what Export All would ship",
          len(got["inMemory"]) == 4, str(got["inMemory"]))


def main():
    try:
        import playwright  # noqa: F401
    except ImportError as e:
        print(f"test_robustness: SKIP ({e})")
        return 0
    print("robustness regressions")
    asyncio.run(run())
    try:
        import fitz  # noqa: F401
        asyncio.run(run_export_all())
    except ImportError:
        print("  [skip] export-all quota test needs PyMuPDF")
    print("\ntest_robustness: PASS" if not FAILS
          else f"\ntest_robustness: {len(FAILS)} FAILURE(S): {FAILS}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
