#!/usr/bin/env python3
"""
Regression test for the meta-analytic layer of figure-extractor.html.

Covers the fields/guards added when the tool was refit as the vision's visual-only
fallback (permanently-flagged figure-derived output; R does ALL effect sizes — the tool
computes none):
  - dispersion discipline: EXTRACT.bars refuses to emit SD/SE for an unknown dispersion
    type and forces a `dispersion-type-uncertain` flag; the characterization validator
    requires that flag when error bars are present but the type is unknown.
  - provenance: every extraction is stamped figure_derived / Data_Source / Data_Extraction_Method.
  - first-class MA fields: direction (+1/-1), timepoint, nSource carried on the extraction.
  - no effect-size math: the extraction carries NO yi/vi (no sd/se/effects) — landmarks only.
  - multi-panel guard: runExtraction hard-fails on an un-split multi-panel figure.
  - authoritative export: getFigureDerivedRows emits landmarks (no yi/vi).
  - calibration guard: verifyCalibration flags a log axis for human review.
  - export ZIP carries figure-derived-landmarks.csv (and NO preview CSV).

Requires PyMuPDF (fitz) + playwright; SKIPS (exit 0) if either is missing.
Run:  python3 scripts/test_meta_layer.py
"""

import asyncio
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = (REPO / "figure-extractor.html").as_uri()


def make_pdf(path):
    import fitz
    doc = fitz.open()
    p1 = doc.new_page(width=612, height=792)
    p1.draw_rect(fitz.Rect(100, 100, 500, 400), color=(0, 0, 0), width=1)
    p1.insert_text((100, 430), "Figure 1. Cortisol by group, mean +/- SD.", fontsize=11)
    doc.save(path)
    doc.close()


async def run(pdf_path):
    from playwright.async_api import async_playwright
    S = 150 / 72
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        pg = await browser.new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        await pg.goto(TOOL)

        buf = pathlib.Path(pdf_path).read_bytes()
        await pg.evaluate("() => { settings.dpi = '150'; }")
        await pg.set_input_files("#pdfInput", files=[{"name": "m.pdf", "mimeType": "application/pdf", "buffer": buf}])
        for _ in range(80):
            if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                break
            await pg.wait_for_timeout(250)
        assert await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"), "article never loaded"

        async def ev(expr, arg=None):
            return await pg.evaluate(expr, arg)

        # ---- pure EXTRACT.bars dispersion guard ------------------------------
        bad = await ev("() => window.figureExtractor.extract.bars("
                       "[{name:'a',mean:10,errorHalf:2,n:8},{name:'b',mean:8,errorHalf:2,n:8}],'unknown')")
        assert "dispersion-type-uncertain" in (bad.get("flags") or []), f"no uncertain flag: {bad}"
        # tool emits landmarks only — no sd/se (R derives variance from errorHalf + type + n)
        assert "sd" not in bad["groups"][0] and "se" not in bad["groups"][0], f"leaked sd/se: {bad}"
        assert bad["groups"][0]["errorHalf"] == 2 and bad["groups"][0]["dispersionType"] == "unknown", f"landmark fields: {bad}"
        assert "effects" not in bad, f"tool computed an effect: {bad}"
        good = await ev("() => window.figureExtractor.extract.bars("
                        "[{name:'a',mean:10,errorHalf:2,n:8},{name:'b',mean:8,errorHalf:2,n:8}],'SD')")
        assert not (good.get("flags") or []), f"unexpected flag with SD: {good}"
        assert good["groups"][0]["mean"] == 10 and good["groups"][0]["errorHalf"] == 2, f"landmarks not passed through: {good}"

        # box landmarks retained (quartiles), no mean/sd computed ---------------
        bx = await ev("() => window.figureExtractor.extract.boxes([{name:'a',median:5,q1:3,q3:7,n:10}])")
        g0 = bx["groups"][0]
        assert g0["q1"] == 3 and g0["q3"] == 7, f"box quartiles dropped: {g0}"
        assert "mean" not in g0 and "sd" not in g0 and "effects" not in bx, f"box computed mean/sd/effect: {bx}"

        # ---- characterization validator: dispersion discipline ---------------
        fid = (await ev(f"() => window.figureExtractor.addFigure(1, "
                        f"{{x:{round(100*S)},y:{round(100*S)},width:{round(400*S)},height:{round(300*S)}}}, 'Figure 1')"))["figureId"]
        vbad = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                        "{panels:[{charType:'bar', statistics:{dispersion:{present:true, type:'unknown'}}}]})")
        assert vbad["success"] is False and any("dispersion" in e for e in vbad["errors"]), f"validator missed uncertain: {vbad}"
        vok = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                       "{panels:[{charType:'bar', statistics:{dispersion:{present:true, type:'unknown'}}}], "
                       "flags:['dispersion-type-uncertain']})")
        assert vok["success"] is True, f"flagged-uncertain char rejected: {vok}"

        # ---- runExtraction: provenance + direction + fields + preview flip ---
        await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                 "{panels:[{charType:'bar', dataProvenance:'primary', "
                 "statistics:{dispersion:{present:true, type:'SD'}}, extractionPlan:{method:'bar-endpoints'}}]})")
        res = await ev(f"() => window.figureExtractor.runExtraction('{fid}', null, "
                       "{groups:[{name:'ctrl',mean:10,errorHalf:2,n:8},{name:'tx',mean:8,errorHalf:2,n:8}], "
                       "direction:-1, timepoint:'week8', nSource:'caption'})")
        assert res["success"], f"runExtraction failed: {res}"
        e = res["extraction"]
        assert e["figure_derived"] is True and e["Data_Source"] == "figure" and e["Data_Extraction_Method"] == "figure-extractor", f"provenance missing: {e}"
        assert e["direction"] == -1 and e["timepoint"] == "week8" and e["nSource"] == "caption", f"MA fields missing: {e}"
        assert not e["flags"], f"unexpected flags for known SD: {e['flags']}"
        # the tool computes NO effect sizes — direction is carried as a field for R, not applied here
        assert "effects" not in e and "correlation" not in e, f"tool computed an effect size: {e}"
        assert e["groups"][0]["mean"] == 10 and e["groups"][0]["errorHalf"] == 2, f"landmarks missing on extraction: {e}"

        # ---- provenance CANNOT be laundered through setExtraction -------------
        # `setExtraction` is the write path SKILL.md points agents at, and it had zero test
        # coverage. It stamped provenance with the caller spread LAST, so a caller could
        # assert `figure_derived:false, Data_Source:'text'` and that value flowed all the way
        # into the CSV handed to R -- a figure-read number arriving in the analysis claiming
        # to have come from a table, which silently corrupts the figure-vs-text sensitivity
        # split. `runExtraction` always resisted this; only the documented path did not.
        # On its OWN figure, so it cannot disturb the extraction the later assertions read.
        fidL = (await ev("() => window.figureExtractor.addFigure(1, "
                         "{x:60,y:520,width:200,height:120}, 'Figure L')"))["figureId"]
        await ev(f"() => window.figureExtractor.setCharacterization('{fidL}', null, "
                 "{panels:[{charType:'bar', dataProvenance:'primary', "
                 "statistics:{dispersion:{present:true, type:'SD'}}, "
                 "extractionPlan:{method:'bar-endpoints'}}]})")
        laundered = await ev(
            f"() => window.figureExtractor.setExtraction('{fidL}', null, "
            "{groups:[{name:'ctrl',mean:10,errorHalf:2,n:8}], charType:'bar', "
            " dispersionType:'SD', direction:1, "
            " figure_derived:false, Data_Source:'text', "
            " Data_Extraction_Method:'read-from-table'})")
        assert laundered["success"], f"setExtraction failed: {laundered}"
        stored = await ev(f"() => window.figureExtractor.getExtraction('{fidL}', null)")
        assert stored["figure_derived"] is True, f"figure_derived laundered to {stored['figure_derived']!r}"
        assert stored["Data_Source"] == "figure", f"Data_Source laundered to {stored['Data_Source']!r}"
        assert stored["Data_Extraction_Method"] == "figure-extractor", \
            f"Data_Extraction_Method laundered to {stored['Data_Extraction_Method']!r}"
        rows_l = await ev("() => window.figureExtractor.getFigureDerivedRows()")
        bad = [r for r in rows_l if r.get("figure_derived") is not True
               or r.get("Data_Source") != "figure"]
        assert not bad, f"laundered provenance reached the R hand-off: {bad[:2]}"
        csv_l = await ev("() => window.figureExtractor.getFigureDerivedCsv()")
        assert "read-from-table" not in csv_l, "laundered Data_Extraction_Method reached the CSV"
        await ev(f"() => window.figureExtractor.deleteFigure('{fidL}')")

        # ---- multi-panel guard (separate figure) -----------------------------
        fid2 = (await ev(f"() => window.figureExtractor.addFigure(1, "
                         f"{{x:{round(100*S)},y:{round(100*S)},width:200,height:200}}, 'Figure 2')"))["figureId"]
        await ev(f"() => window.figureExtractor.setCharacterization('{fid2}', null, "
                 "{panelCount:2, panels:["
                 "{charType:'bar', statistics:{dispersion:{present:true, type:'SD'}}},"
                 "{charType:'bar', statistics:{dispersion:{present:true, type:'SD'}}}]})")
        mp = await ev(f"() => window.figureExtractor.runExtraction('{fid2}', null, {{groups:[]}})")
        assert mp["success"] is False and "multi-panel" in mp["error"], f"multi-panel guard missing: {mp}"

        # ---- authoritative vs preview export shape ---------------------------
        lm = await ev("() => window.figureExtractor.getFigureDerivedRows()")
        bar_rows = [r for r in lm if r.get("landmarkKind") == "bar-group"]
        assert bar_rows, f"no authoritative bar-group rows: {lm}"
        r0 = bar_rows[0]
        assert r0["figure_derived"] is True and r0["dispersionType"] == "SD" and r0["direction"] == -1, f"authoritative row fields: {r0}"
        assert "mean" in r0 and "errorHalf" in r0, f"authoritative landmarks missing: {r0}"
        assert "variance" not in r0 and "se" not in r0 and "smd" not in r0, f"authoritative row leaked yi/vi: {r0}"
        # the retired preview API is gone entirely (R does effect sizes)
        gone = await ev("() => window.figureExtractor.getMetaAnalysisRows === undefined "
                        "&& window.figureExtractor.getMetaAnalysisCsv === undefined "
                        "&& window.figureExtractor.convert === undefined")
        assert gone, "non-authoritative effect-size API (getMetaAnalysisRows/Csv/convert) should be removed"

        # ---- calibration log-axis -> human-review flag -----------------------
        vc = await ev("() => window.figureExtractor.verifyCalibration("
                      "{x1:{px:0,py:100},x2:{px:100,py:100},y1:{px:0,py:100},y2:{px:0,py:0}}, "
                      "{x1:'1',x2:'1000',y1:'0',y2:'10',logX:false,logY:false})")
        assert vc["ok"] is True and "log-axis-needs-human-review" in vc["flags"], f"log review flag missed: {vc}"

        # ---- export ZIP carries the landmarks CSV, and NO preview CSV ---------
        async with pg.expect_download() as di:
            await pg.click("#exportBtn")
        dl = await di.value
        import zipfile
        z = zipfile.ZipFile(await dl.path())
        names = z.namelist()
        assert "figure-derived-landmarks.csv" in names, f"no landmarks CSV: {names}"
        assert not any("preview" in n or "meta-analysis" in n for n in names), f"preview CSV should be gone: {names}"
        head = z.read("figure-derived-landmarks.csv").decode().splitlines()[0]
        assert "figure_derived" in head and "dispersionType" in head, f"landmark header: {head}"

        assert not errors, f"console errors: {errors}"
        await browser.close()
    print("test_meta_layer: PASS (dispersion guard, provenance flags, direction+fields, "
          "no effect-size math, multi-panel guard, landmarks export, calibration log-review flag)")


def main():
    try:
        import fitz  # noqa: F401
        import playwright  # noqa: F401
    except Exception as e:
        print(f"test_meta_layer: SKIP (missing dependency: {e})")
        return 0
    with tempfile.TemporaryDirectory() as d:
        pdf = str(pathlib.Path(d) / "m.pdf")
        make_pdf(pdf)
        try:
            asyncio.run(run(pdf))
        except Exception as e:
            print(f"test_meta_layer: FAIL ({e})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
