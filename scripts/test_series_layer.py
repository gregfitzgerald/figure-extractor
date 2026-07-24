#!/usr/bin/env python3
"""
Regression test for the SERIES/GROUP layer of figure-extractor.html.

Locks in the four defects found by the series-parsing audit, each of which let a silent error
through (see benchmark/WHITE-PAPER-LOG.md s10a):
  - the digitizer's series index survived runExtraction but was DROPPED by authoritativeRows,
    so a two-colour scatter exported as one undifferentiated cloud;
  - extraction flags never reached the CSV, so `dispersion-type-uncertain` -- the flag whose whole
    purpose is non-silence -- was invisible in the artifact R receives;
  - CHAR_VOCAB.role was defined but never validated or read;
  - digAutoTrace scanned the legend, so a swatch of the traced colour injected phantom points.
Plus the deterministic series guards that feed the B4 human gate (unlabeled series, legend-order
mismatch, near-identical hues, series-count mismatch).

Requires PyMuPDF (fitz) + playwright; SKIPS (exit 0) if either is missing.
Run:  python3 scripts/test_series_layer.py
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
    p1.insert_text((100, 430), "Figure 1. Outcome by group and timepoint.", fontsize=11)
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
        await pg.set_input_files("#pdfInput", files=[{"name": "s.pdf", "mimeType": "application/pdf", "buffer": buf}])
        for _ in range(80):
            if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                break
            await pg.wait_for_timeout(250)
        assert await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"), "article never loaded"

        async def ev(expr, arg=None):
            return await pg.evaluate(expr, arg)

        fid = (await ev(f"() => window.figureExtractor.addFigure(1, "
                        f"{{x:{round(100*S)},y:{round(100*S)},width:{round(400*S)},height:{round(300*S)}}}, 'Figure 1')"))["figureId"]

        # ---- vocab: the new series keys exist -------------------------------
        vocab = await ev("() => window.figureExtractor.charVocab()")
        assert "seriesEncoding" in vocab and "labelSource" in vocab, "series vocab missing"
        for fl in ("series-assignment-uncertain", "legend-order-mismatch", "series-count-uncertain",
                   "similar-series-colors", "series-unlabeled"):
            assert fl in vocab["flags"], f"missing series flag {fl}"

        # ---- role is now VALIDATED (was defined but never checked) ----------
        bad_role = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                            "{panels:[{charType:'bar', series:[{id:'s1', label:'Ctl', role:'not-a-role'}]}]})")
        assert bad_role["success"] is False and any("role" in e for e in bad_role["errors"]), \
            f"unknown role accepted: {bad_role}"
        ok_role = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                           "{panels:[{charType:'bar', series:[{id:'s1', label:'Ctl', role:'control'},"
                           "{id:'s2', label:'Run', role:'intervention'}]}]})")
        assert ok_role["success"] is True, f"valid roles rejected: {ok_role}"

        # duplicate / missing series ids are join-key errors
        dup = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                       "{panels:[{charType:'bar', series:[{id:'s1',label:'A'},{id:'s1',label:'B'}]}]})")
        assert dup["success"] is False and any("duplicate" in e for e in dup["errors"]), f"dup id accepted: {dup}"

        # ---- unlabeled series must be flagged, not silently emitted ---------
        unl = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                       "{panels:[{charType:'bar', series:[{id:'s1',label:'Ctl'},{id:'s2'}]}]})")
        assert unl["success"] is False and any("label" in e for e in unl["errors"]), f"unlabeled series accepted: {unl}"
        unl_ok = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                          "{panels:[{charType:'bar', series:[{id:'s1',label:'Ctl'},{id:'s2'}]}], "
                          "flags:['series-unlabeled']})")
        assert unl_ok["success"] is True, f"flagged-unlabeled rejected: {unl_ok}"

        # ---- legend order != plot order must be declared, never auto-fixed --
        mism = await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                        "{panels:[{charType:'bar', series:[{id:'a',label:'A'},{id:'b',label:'B'}], "
                        "legendOrder:['a','b'], plotOrder:['b','a']}]})")
        assert mism["success"] is False and any("legendOrder" in e for e in mism["errors"]), \
            f"legend/plot order mismatch accepted silently: {mism}"

        # ---- deterministic guards for the B4 gate ---------------------------
        await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                 "{panels:[{charType:'bar', seriesCount:3, series:["
                 "{id:'a',label:'A',color:'#1f77b4'},{id:'b',label:'B',color:'#1f78b6'}], "
                 "legendOrder:['a','b'], plotOrder:['b','a']}], "
                 "flags:['legend-order-mismatch']})")
        vs = await ev(f"() => window.figureExtractor.validateSeries('{fid}', null)")
        assert vs["ok"] is False, "validateSeries should fail on this panel"
        for fl in ("legend-order-mismatch", "similar-series-colors", "series-count-uncertain"):
            assert fl in vs["flags"], f"validateSeries missed {fl}: {vs}"

        # ---- flags + series reach the CSV (were dropped entirely) -----------
        await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                 "{panels:[{charType:'bar', dataProvenance:'primary', "
                 "series:[{id:'ctl',label:'Control',role:'control'},{id:'run',label:'Run',role:'intervention'}], "
                 "statistics:{dispersion:{present:true, type:'unknown'}}, "
                 "extractionPlan:{method:'bar-endpoints'}}], flags:['dispersion-type-uncertain']})")
        res = await ev(f"() => window.figureExtractor.runExtraction('{fid}', null, "
                       "{groups:[{name:'wk2 Control',mean:10,errorHalf:2,n:8,groupId:'wk2',seriesId:'ctl'},"
                       "{name:'wk2 Run',mean:8,errorHalf:2,n:8,groupId:'wk2',seriesId:'run'}]})")
        assert res["success"], f"runExtraction failed: {res}"
        assert "dispersion-type-uncertain" in res["extraction"]["flags"], f"guard flag lost: {res['extraction']}"

        rows = await ev("() => window.figureExtractor.getFigureDerivedRows()")
        bar = [r for r in rows if r.get("landmarkKind") == "bar-group"]
        assert bar, f"no bar rows: {rows}"
        assert "flags" in bar[0] and "dispersion-type-uncertain" in bar[0]["flags"], \
            f"FLAG NOT IN CSV ROW (the guard fires into a void): {bar[0]}"
        assert bar[0]["groupId"] == "wk2", f"groupId missing: {bar[0]}"
        assert {r["seriesId"] for r in bar} == {"ctl", "run"}, f"seriesId missing/wrong: {bar}"
        # seriesLabel is resolved from the characterization's series[] (model-read legend text)
        assert {r["seriesLabel"] for r in bar} == {"Control", "Run"}, f"seriesLabel not resolved: {bar}"

        csv = await ev("() => window.figureExtractor.getFigureDerivedCsv()")
        head = csv.splitlines()[0]
        for col in ("groupId", "seriesId", "seriesLabel", "flags"):
            assert col in head, f"CSV header missing {col}: {head}"

        # ---- scatter: the digitizer's series index must survive to the CSV --
        fid2 = (await ev(f"() => window.figureExtractor.addFigure(1, "
                         f"{{x:{round(100*S)},y:{round(100*S)},width:200,height:200}}, 'Figure 2')"))["figureId"]
        await ev(f"() => window.figureExtractor.setCharacterization('{fid2}', null, "
                 "{panels:[{charType:'scatter', dataProvenance:'primary', "
                 "series:[{id:'0',label:'Male'},{id:'1',label:'Female'}], "
                 "extractionPlan:{method:'digitize_points'}}]})")
        await ev("() => window.figureExtractor.setDigitization('" + fid2 + "', null, {"
                 "cal:{x1:{px:0,py:100},x2:{px:100,py:100},y1:{px:0,py:100},y2:{px:0,py:0}},"
                 "vals:{x1:'0',x2:'10',y1:'0',y2:'10',logX:false,logY:false},"
                 "points:[{px:10,py:90,s:0},{px:20,py:80,s:1},{px:30,py:70,s:0}]})")
        r2 = await ev("() => window.figureExtractor.runExtraction('" + fid2 + "', null, {})")
        assert r2["success"], f"scatter runExtraction failed: {r2}"
        pts = [r for r in (await ev("() => window.figureExtractor.getFigureDerivedRows()"))
               if r.get("landmarkKind") == "point"]
        assert len(pts) == 3, f"expected 3 point rows, got {len(pts)}"
        got = sorted(str(p["seriesId"]) for p in pts)
        assert got == ["0", "0", "1"], f"SERIES INDEX DROPPED (two-colour scatter -> one cloud): {pts}"
        assert {p["seriesLabel"] for p in pts} == {"Male", "Female"}, f"scatter seriesLabel not resolved: {pts}"

        # ---- B4 gate preview: naming first (the dangerous half) -------------
        prev = await ev(f"() => window.figureExtractor.previewAssignment('{fid}', null)")
        assert len(prev["affirmations"]) == 3 and "arm role" in prev["affirmations"][1], \
            f"gate affirmations missing/mis-ordered: {prev.get('affirmations')}"
        binds = {b["seriesId"]: b for b in prev["bindings"]}
        assert set(binds) == {"ctl", "run"}, f"bindings missing: {prev['bindings']}"
        assert binds["ctl"]["role"] == "control" and binds["run"]["role"] == "intervention", \
            f"roles not surfaced for confirmation: {binds}"
        assert binds["ctl"]["marksBound"] == 1 and binds["run"]["marksBound"] == 1, f"marks not counted: {binds}"
        assert "dispersion-type-uncertain" in prev["reviewFlags"], f"review flags incomplete: {prev['reviewFlags']}"
        assert prev["rows"], "gate preview must show the literal emitted rows"
        # an unassigned role must block the gate (the arm meaning is unconfirmed)
        await ev(f"() => window.figureExtractor.setCharacterization('{fid}', null, "
                 "{panels:[{charType:'bar', series:[{id:'ctl',label:'Control'},{id:'run',label:'Run'}], "
                 "statistics:{dispersion:{present:true,type:'SD'}}, extractionPlan:{method:'bar-endpoints'}}]})")
        prev2 = await ev(f"() => window.figureExtractor.previewAssignment('{fid}', null)")
        assert prev2["ok"] is False and any("no role" in p for p in prev2["problems"]), \
            f"unassigned role should block the gate: {prev2['problems']}"

        # ---- auto-trace must not scan the legend ----------------------------
        ex = await ev("() => window.figureExtractor.setTraceExclusions([{x0:400,y0:0,x1:500,y1:60}])")
        assert ex["success"] and ex["count"] == 1, f"setTraceExclusions failed: {ex}"
        diag = await ev("() => window.figureExtractor.getTraceDiagnostics()")
        assert "skippedExcluded" in diag and diag["exclusions"] == 1, f"trace diagnostics missing: {diag}"

        assert not errors, f"console errors: {errors}"
        await browser.close()
    print("test_series_layer: PASS (role validated, series ids+labels+flags reach the CSV, "
          "scatter series index survives, legend-order/unlabeled/hue/count guards, B4 gate preview, "
          "trace exclusions)")


def main():
    try:
        import fitz  # noqa: F401
        import playwright  # noqa: F401
    except Exception as e:
        print(f"test_series_layer: SKIP (missing dependency: {e})")
        return 0
    with tempfile.TemporaryDirectory() as d:
        pdf = str(pathlib.Path(d) / "s.pdf")
        make_pdf(pdf)
        try:
            asyncio.run(run(pdf))
        except Exception as e:
            print(f"test_series_layer: FAIL ({e})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
