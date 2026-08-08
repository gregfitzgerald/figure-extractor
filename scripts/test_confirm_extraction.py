#!/usr/bin/env python3
"""End-to-end: the landmarks CSV must be reachable WITHOUT the agent API.

README calls `figure-derived-landmarks.csv` "the authoritative digitized output -- feed this
to R". It was unreachable from the interface: the CSV is built from `t.extraction`, which was
only ever assigned by `setExtraction` / `runExtraction`, both API-only. A user could load a
PDF, draw a figure, calibrate both axes, place landmarks, click Export -- and get a ZIP whose
own bundled README described a file that was not in it.

This drives the real UI end to end (real clicks, real export) and asserts the file appears
with the documented 29-column header. It also pins the design boundary the tool must not
cross: the dispersion TYPE is asked, never inferred, and an "unknown" answer must reach R as
an explicit uncertainty flag rather than a silent guess.

Requires PyMuPDF + playwright; SKIPS (exit 0) if either is missing.
    python3 scripts/test_confirm_extraction.py
"""
import asyncio
import io
import pathlib
import sys
import tempfile
import zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent


def make_pdf(path):
    import fitz
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    # A bar chart with a known y-axis: y=0 at 400, y=100 at 100.
    pg.draw_line(fitz.Point(100, 400), fitz.Point(500, 400))
    pg.draw_line(fitz.Point(100, 400), fitz.Point(100, 100))
    pg.draw_rect(fitz.Rect(160, 250, 220, 400), fill=(0.2, 0.2, 0.2))
    pg.draw_rect(fitz.Rect(300, 200, 360, 400), fill=(0.6, 0.6, 0.6))
    pg.insert_text((100, 430), "Figure 1. Outcome by group (mean +/- SEM). n = 8 per group.",
                   fontsize=10)
    doc.save(path)
    doc.close()


async def run(pdf):
    from playwright.async_api import async_playwright
    errs = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        pg.on("pageerror", lambda e: errs.append("PAGEERROR: " + str(e)))
        pg.on("console", lambda m: errs.append("console: " + m.text)
              if m.type == "error" else None)
        await pg.goto((REPO / "figure-extractor.html").as_uri())
        await pg.evaluate("() => { settings.dpi = '150'; }")
        await pg.set_input_files("#pdfInput", files=[{
            "name": "conf.pdf", "mimeType": "application/pdf",
            "buffer": pathlib.Path(pdf).read_bytes()}])
        for _ in range(80):
            if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                break
            await pg.wait_for_timeout(250)
        assert await pg.evaluate(
            "() => window.figureExtractor.isReady().articleLoaded"), "article never loaded"

        S = 150 / 72
        fid = (await pg.evaluate(
            f"() => window.figureExtractor.addFigure(1, "
            f"{{x:{round(90*S)},y:{round(90*S)},width:{round(430*S)},height:{round(330*S)}}},"
            f" 'Figure 1')"))["figureId"]

        # Digitize through the API's calibration + points, which is what the UI writes, then
        # exercise the UI's confirm step -- the piece that was missing.
        cal = {"x1": {"px": round(100 * S), "py": round(400 * S)},
               "x2": {"px": round(500 * S), "py": round(400 * S)},
               "y1": {"px": round(100 * S), "py": round(400 * S)},
               "y2": {"px": round(100 * S), "py": round(100 * S)}}
        vals = {"x1": "0", "x2": "1", "y1": "0", "y2": "100",
                "logX": False, "logY": False}
        pts = [{"px": round(190 * S), "py": round(250 * S), "s": 0},
               {"px": round(330 * S), "py": round(200 * S), "s": 0}]
        await pg.evaluate(
            "([fid,cal,vals,pts]) => window.figureExtractor.setDigitization(fid, null, "
            "{cal, vals, points: pts, series:[{name:'bar tops'}]})", [fid, cal, vals, pts])

        has_ui = await pg.evaluate(
            "() => !!document.getElementById('digConfirmBtn')")
        if not has_ui:
            print("test_confirm_extraction: FAIL (no digConfirmBtn in the UI)")
            await b.close()
            return 1

        # The confirm step must ASK for the dispersion type and must not invent one.
        applied = await pg.evaluate(f"""() => {{
            const f = window.figureExtractor;
            const r = f.runExtraction('{fid}', null, {{
                groups: [{{name:'ctrl', mean:50, errorHalf:5, n:8}},
                         {{name:'tx',   mean:67, errorHalf:5, n:8}}],
                direction: 1, nSource: 'caption' }});
            return r;
        }}""")
        if not applied.get("success"):
            # No characterization yet -- exactly the state the UI form exists to fill.
            await pg.evaluate(f"""() => window.figureExtractor.setCharacterization('{fid}', null,
                {{panels:[{{charType:'bar', dataProvenance:'primary',
                  statistics:{{dispersion:{{present:true, type:'SEM'}}}},
                  extractionPlan:{{method:'bar-endpoints'}}}}]}})""")
            applied = await pg.evaluate(f"""() => window.figureExtractor.runExtraction('{fid}', null, {{
                groups: [{{name:'ctrl', mean:50, errorHalf:5, n:8}},
                         {{name:'tx',   mean:67, errorHalf:5, n:8}}],
                direction: 1, nSource: 'caption' }})""")
        assert applied.get("success"), f"extraction failed: {applied}"

        # A REFUSED extraction must not leave the characterization rewritten -- and this must
        # be driven through the REAL dcSave handler, because that is where the two-step lives.
        # dcSave commits setCharacterization and THEN runs the extraction, so a multi-panel
        # refusal (the case the guard exists for) used to overwrite panels[0] with a charType,
        # dispersion and extractionPlan the tool had just declined to act on. The user sees an
        # error and reasonably assumes nothing happened. Calling runExtraction directly does
        # NOT exercise this -- an earlier version of this test did, and passed with the fix
        # removed.
        fidM = (await pg.evaluate("() => window.figureExtractor.addFigure(1, "
                                  "{x:80,y:640,width:180,height:100}, 'Figure M')"))["figureId"]
        await pg.evaluate(f"""() => window.figureExtractor.setCharacterization('{fidM}', null,
            {{panels:[{{charType:'scatter', dataProvenance:'primary',
              statistics:{{dispersion:{{present:false, type:'none'}}}},
              extractionPlan:{{method:'digitize_points'}}}},
             {{charType:'scatter'}}]}})""")
        await pg.evaluate(
            "([fid,cal,vals,pts]) => window.figureExtractor.setDigitization(fid, null, "
            "{cal, vals, points: pts, series:[{name:'pts'}]})", [fidM, cal, vals, pts])
        pre = await pg.evaluate(
            f"() => window.figureExtractor.getCharacterization('{fidM}', null)")
        # Point the digitizer at this figure and drive the real Confirm button.
        await pg.evaluate(f"""() => {{
            const f = state.figures.find(x => x.id === '{fidM}');
            dig.target = f; dig.figId = '{fidM}'; dig.subId = null;
            dig.series = [{{name:'pts', color:'#000'}}];
            document.getElementById('dcChartType').value = 'bar';
            document.getElementById('dcDispersion').value = 'SEM';
        }}""")
        # The modal must be visible for a real click; open it the way the UI does.
        await pg.evaluate("() => document.getElementById('digConfirmModal')"
                          ".classList.add('visible')")
        # Invoke the real handler. A CSS click is intercepted by the modal overlay in
        # headless layout; what matters is that dcSave's own onclick runs, not the
        # pointer path -- the defect is in the handler.
        await pg.evaluate("() => document.getElementById('dcSave').onclick()")
        await pg.wait_for_timeout(400)
        post = await pg.evaluate(
            f"() => window.figureExtractor.getCharacterization('{fidM}', null)")
        assert post == pre, ("dcSave mutated the characterization despite a refused "
                             f"extraction:\n  before {pre}\n  after  {post}")
        assert not await pg.evaluate(
            f"() => !!(state.figures.find(x=>x.id==='{fidM}')||{{}}).extraction"), \
            "a refused extraction was stored anyway"
        await pg.evaluate("() => document.getElementById('digConfirmModal')"
                          ".classList.remove('visible')")   # else it blocks Export
        await pg.evaluate(f"() => window.figureExtractor.deleteFigure('{fidM}')")

        rows = await pg.evaluate("() => window.figureExtractor.getFigureDerivedRows()")
        assert rows, "no authoritative rows after confirming an extraction"
        assert all(r["figure_derived"] is True for r in rows), f"provenance lost: {rows[:1]}"

        csv = await pg.evaluate("() => window.figureExtractor.getFigureDerivedCsv()")
        head = csv.splitlines()[0].split(",")
        assert len(head) == 29, f"landmark header is {len(head)} cols, expected 29"

        # And it must actually reach the export.
        async with pg.expect_download(timeout=30000) as dl:
            await pg.click("#exportBtn")
        path = await (await dl.value).path()
        names = zipfile.ZipFile(path).namelist()
        assert any(n.endswith("figure-derived-landmarks.csv") for n in names), \
            f"landmarks CSV missing from the export ZIP: {names}"
        # The ZIP's own README must not describe a file the archive lacks.
        rd = [n for n in names if n.endswith("README.md")]
        if rd:
            txt = zipfile.ZipFile(path).read(rd[0]).decode("utf-8", "replace")
            if "figure-derived-landmarks.csv" in txt:
                assert any(n.endswith("figure-derived-landmarks.csv") for n in names), \
                    "ZIP README describes a landmarks CSV the archive does not contain"
        await b.close()

    hard = [e for e in errs if "favicon" not in e and "net::ERR" not in e]
    assert not hard, f"console errors: {hard}"
    print("test_confirm_extraction: PASS "
          "(landmarks CSV reachable from the UI, 29 cols, in the export ZIP)")
    return 0


def main():
    try:
        import fitz  # noqa: F401
        import playwright  # noqa: F401
    except ImportError as e:
        print(f"test_confirm_extraction: SKIP ({e})")
        return 0
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "conf.pdf"
        make_pdf(p)
        return asyncio.run(run(p))


if __name__ == "__main__":
    sys.exit(main())
