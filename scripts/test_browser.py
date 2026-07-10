#!/usr/bin/env python3
"""
Self-contained browser regression test for figure-extractor.html.

Generates a tiny synthetic PDF (with a real text layer) so it needs no external
fixtures, loads the tool in headless Chromium, and verifies the core pipeline:
caption auto-detection, schema-v2 export, and the figures.csv summary.

Requires: PyMuPDF (fitz), playwright (+ `python -m playwright install chromium`).
If either is missing the test SKIPS (exit 0) so it never blocks a bare checkout.

Run:  python3 scripts/test_browser.py
"""

import asyncio
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = (REPO / "figure-extractor.html").as_uri()


def make_pdf(path):
    import fitz  # PyMuPDF
    doc = fitz.open()
    # Page 1: a "figure" rectangle with a caption below it.
    p1 = doc.new_page(width=612, height=792)
    p1.draw_rect(fitz.Rect(100, 100, 500, 400), color=(0, 0, 0), width=1)
    p1.insert_text((100, 430), "Figure 1. Test caption alpha beta gamma delta.", fontsize=11)
    p1.insert_text((100, 448), "(A) first panel. (B) second panel description here.", fontsize=11)
    # a running footer that must NOT leak into the caption (bottom margin)
    p1.insert_text((100, 780), "J. Synthetic Res. 1, 1-10, 2026", fontsize=8)
    # Page 2: a second figure + caption.
    p2 = doc.new_page(width=612, height=792)
    p2.draw_rect(fitz.Rect(120, 120, 480, 360), color=(0, 0, 0), width=1)
    p2.insert_text((120, 390), "Figure 2. Another caption for the second figure.", fontsize=11)
    doc.save(path)
    doc.close()


async def run(pdf_path):
    from playwright.async_api import async_playwright
    S = 150 / 72  # DPI scale used by the test (150 DPI)
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(accept_downloads=True)
        pg = await ctx.new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        await pg.goto(TOOL)

        buf = pathlib.Path(pdf_path).read_bytes()
        # Loading is now prompt-free: set the DPI default, then dropping a file into the
        # hidden input renders immediately (no modal). Force 150 to keep the coord math.
        await pg.evaluate("() => { settings.dpi = '150'; }")
        await pg.set_input_files("#pdfInput", files=[{"name": "synthetic.pdf", "mimeType": "application/pdf", "buffer": buf}])
        for _ in range(80):
            if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                break
            await pg.wait_for_timeout(250)
        assert await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"), "article never loaded"

        # box the page-1 figure rectangle (PDF pts 100..500 x 100..400 -> natural px * scale)
        fid = (await pg.evaluate(
            f"() => window.figureExtractor.addFigure(1, "
            f"{{x:{round(100*S)}, y:{round(100*S)}, width:{round(400*S)}, height:{round(300*S)}}}, 'Figure 1')"
        ))["figureId"]
        f = await pg.evaluate(f"() => window.figureExtractor.getState().figures.find(x=>x.id=='{fid}')")
        cap = f.get("caption") or ""
        assert cap.lower().startswith("figure 1"), f"caption not detected: {cap!r}"
        assert "alpha beta gamma" in cap, f"caption body missing: {cap!r}"
        assert "Synthetic Res" not in cap, f"footer leaked into caption: {cap!r}"

        # schema v2 export
        j = await pg.evaluate("() => window.figureExtractor.getAnnotationsJSON()")
        assert j["schemaVersion"] == 2, "schemaVersion"
        assert any(p["pageNum"] == 1 for p in j["pages"]), "pages header"
        jf = j["figures"][0]
        assert jf["pageNum"] == 1 and jf["boundsNorm"] and 0 < jf["boundsNorm"]["x"] < 1, "boundsNorm"
        assert jf["caption"] == cap and jf["captionSource"] == "textlayer", "caption not serialized"

        # page badge reflects the figure count on page 1
        badge = await pg.evaluate("() => state.pages.find(p=>p.pageNum===1).wrapper.querySelector('.page-number').textContent")
        assert badge == "1 · 1 fig", f"page badge: {badge!r}"

        # undo removes the figure, redo restores it
        await pg.keyboard.press("Control+z")
        await pg.wait_for_timeout(100)
        assert await pg.evaluate("() => window.figureExtractor.getState().figures.length") == 0, "undo failed"
        await pg.keyboard.press("Control+y")
        await pg.wait_for_timeout(100)
        assert await pg.evaluate("() => window.figureExtractor.getState().figures.length") == 1, "redo failed"

        # move + resize the figure box by mouse: select, drag SE handle outward
        b0 = await pg.evaluate(f"() => ({{...window.figureExtractor.getState().figures.find(x=>x.id=='{fid}').bounds}})")
        await pg.evaluate("() => state.pages.find(p=>p.pageNum===1).wrapper.scrollIntoView()")
        await pg.wait_for_timeout(150)
        r = await pg.evaluate(f"""() => {{ const b=document.querySelector('#articleScroll [data-figure-id="{fid}"]').getBoundingClientRect();
            return {{x:b.x, y:b.y, w:b.width, h:b.height}}; }}""")
        await pg.mouse.click(r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)  # select
        await pg.wait_for_timeout(80)
        h = await pg.evaluate(f"""() => {{ const b=document.querySelector('#articleScroll [data-figure-id="{fid}"] .resize-handle[data-dir="se"]').getBoundingClientRect();
            return {{x:b.x+b.width/2, y:b.y+b.height/2}}; }}""")
        await pg.mouse.move(h["x"], h["y"]); await pg.mouse.down()
        await pg.mouse.move(h["x"] + 50, h["y"] + 50, steps=8); await pg.mouse.up()
        await pg.wait_for_timeout(120)
        b1 = await pg.evaluate(f"() => ({{...window.figureExtractor.getState().figures.find(x=>x.id=='{fid}').bounds}})")
        assert b1["width"] > b0["width"] + 20 and b1["height"] > b0["height"] + 20, f"resize failed: {b0} -> {b1}"

        # storage resilience: a full quota must not throw mid-commit
        await pg.evaluate("""() => { const o=localStorage.setItem.bind(localStorage);
            localStorage.setItem=(k,v)=>{ if(String(k).startsWith('figext_')) throw new DOMException('q','QuotaExceededError'); return o(k,v); }; }""")
        await pg.evaluate("() => window.figureExtractor.addFigure(2, {x:250,y:250,width:400,height:300}, 'Figure 2')")
        assert await pg.evaluate("() => window.figureExtractor.getState().figures.length") == 2, "storage failure broke add"
        await pg.evaluate("""() => { /* restore */ }""")

        # panel-caption split routes (A)/(B) to subfigures
        await pg.evaluate(f"() => window.figureExtractor.addSubfigure('{fid}', {{x:10,y:10,width:100,height:100}}, 'Figure 1a')")
        await pg.evaluate(f"() => window.figureExtractor.addSubfigure('{fid}', {{x:120,y:10,width:100,height:100}}, 'Figure 1b')")
        split = await pg.evaluate(f"""() => {{
            const card=document.querySelector('#figuresScroll [data-figure-id="{fid}"]');
            const s=[...card.querySelectorAll('.caption-btn')].find(x=>x.textContent.includes('Split'));
            if(!s||s.disabled) return false; s.click(); return true;
        }}""")
        await pg.wait_for_timeout(120)
        subs = await pg.evaluate(f"() => window.figureExtractor.getState().figures.find(x=>x.id=='{fid}').subfigures.map(s=>s.caption)")
        assert split and subs[0] and subs[1], f"panel split failed: {subs}"

        # figures.csv is present in the export ZIP
        async with pg.expect_download() as di:
            await pg.click("#exportBtn")
        dl = await di.value
        import zipfile
        z = zipfile.ZipFile(await dl.path())
        assert "figures.csv" in z.namelist(), f"no figures.csv: {z.namelist()}"
        csv_text = z.read("figures.csv").decode()
        assert "Figure 1" in csv_text and "subfigure" in csv_text, "csv content"

        assert not errors, f"console errors: {errors}"
        await browser.close()
    print("test_browser: PASS (caption+footer-strip, schema v2, page badge, undo/redo, "
          "box resize, storage resilience, panel split, csv, no console errors)")


def main():
    try:
        import fitz  # noqa: F401
        import playwright  # noqa: F401
    except Exception as e:
        print(f"test_browser: SKIP (missing dependency: {e})")
        return 0
    with tempfile.TemporaryDirectory() as d:
        pdf = str(pathlib.Path(d) / "synthetic.pdf")
        make_pdf(pdf)
        try:
            asyncio.run(run(pdf))
        except Exception as e:
            print(f"test_browser: FAIL ({e})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
