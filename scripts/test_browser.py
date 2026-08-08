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


def make_pdf2(path):
    """A one-page PDF that is clearly a DIFFERENT paper than make_pdf's (for the
    same-basename collision test)."""
    import fitz
    doc = fitz.open()
    p1 = doc.new_page(width=612, height=792)
    p1.draw_rect(fitz.Rect(150, 150, 450, 350), color=(0, 0, 0), width=1)
    p1.insert_text((150, 380), "Figure 1. A caption from an entirely different paper.", fontsize=11)
    doc.save(path)
    doc.close()


async def run(pdf_path, pdf2_path):
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
        await pg.evaluate("""() => { const o=localStorage.setItem.bind(localStorage); window._origSetItem = o;
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

        # the bundled README must not describe a file the archive does not contain: nothing
        # was confirmed as an extraction, so there is no figure-derived-landmarks.csv and the
        # README has to say so instead of advertising it
        assert "figure-derived-landmarks.csv" not in z.namelist(), f"unexpected landmarks CSV: {z.namelist()}"
        readme = z.read("README.md").decode()
        assert "NO `figure-derived-landmarks.csv`" in readme, \
            "ZIP README describes a landmarks CSV the archive does not contain"

        # ---- same basename, different paper: must NOT merge into one article ----
        # Article identity was `file.name` minus `.pdf`; reference managers ship dozens of
        # identically-named PDFs ("Full Text PDF.pdf"), and a collision replaced the first
        # paper's pages while restoring ITS boxes onto the second paper. A second load of the
        # same basename must become a distinct article with no inherited annotations.
        # (First, narrow the quota sabotage to the ANNOTATION keys: loading an article also
        # writes incidental figext_ keys (e.g. figext_articleFit) outside any try/catch, and
        # those are not part of the storage-failure scenario under test.)
        await pg.evaluate("""() => { localStorage.setItem=(k,v)=>{
            if(/^figext_synthetic/.test(String(k))) throw new DOMException('q','QuotaExceededError');
            return window._origSetItem(k,v); }; }""")
        buf2 = pathlib.Path(pdf2_path).read_bytes()
        await pg.set_input_files("#pdfInput", files=[{"name": "synthetic.pdf", "mimeType": "application/pdf", "buffer": buf2}])
        for _ in range(80):
            r = await pg.evaluate("() => window.figureExtractor.isReady()")
            if r["articleLoaded"] and r["articleName"] != "synthetic":
                break
            await pg.wait_for_timeout(250)
        arts = await pg.evaluate("() => window.figureExtractor.listArticles()")
        assert [a["name"] for a in arts] == ["synthetic", "synthetic_2"], \
            f"basename collision merged two papers: {arts}"
        assert [a["pageCount"] for a in arts] == [2, 1], f"first paper's pages were replaced: {arts}"
        cur = await pg.evaluate("() => window.figureExtractor.isReady()")
        assert cur["articleName"] == "synthetic_2", f"second paper not opened: {cur}"
        assert cur["figureCount"] == 0, \
            f"first paper's boxes restored onto the second paper: {cur['figureCount']} figures"

        # ---- batch export must read the OPEN article from live state ------------
        # localStorage.setItem still throws for figext_ keys (quota sabotage above), which is
        # exactly the situation the storage-full toast tells the user to export in. The open
        # article ('synthetic_2') has one figure in state.figures and NOTHING in localStorage;
        # reading localStorage here silently dropped it from the batch export.
        await pg.evaluate("() => window.figureExtractor.addFigure(1, {x:300,y:300,width:400,height:300}, 'Figure B1')")
        assert await pg.evaluate("() => window.figureExtractor.getState().figures.length") == 1, "setup figure"
        async with pg.expect_download() as di2:
            await pg.click("#exportAllBtn")
        dl2 = await di2.value
        z2 = zipfile.ZipFile(await dl2.path())
        assert "synthetic_2/annotations.json" in z2.namelist(), \
            f"open article silently missing from batch export (stale localStorage read): {z2.namelist()}"
        import json
        ann2 = json.loads(z2.read("synthetic_2/annotations.json").decode())
        assert len(ann2["figures"]) == 1 and ann2["figures"][0]["label"] == "Figure B1", \
            f"open article's live figures not exported: {ann2['figures']}"

        assert not errors, f"console errors: {errors}"
        await browser.close()
    print("test_browser: PASS (caption+footer-strip, schema v2, page badge, undo/redo, "
          "box resize, storage resilience, panel split, csv, truthful README, "
          "basename collision, batch export live-state, no console errors)")


async def run_offline():
    """PDF.js/JSZip come from a CDN; when it is unreachable the tool must SAY so at load
    (a visible banner), not let the first PDF click die silently."""
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        pg = await browser.new_page()

        async def block(route):
            await route.abort()
        await pg.route("https://cdnjs.cloudflare.com/**", block)
        await pg.goto(TOOL)
        await pg.wait_for_timeout(400)
        assert await pg.evaluate("() => typeof pdfjsLib === 'undefined'"), "CDN block did not take"
        banner = await pg.evaluate("""() => { const b = document.getElementById('cdnBanner');
            return b ? { text: b.textContent, visible: b.offsetHeight > 0 } : null; }""")
        assert banner, "no #cdnBanner shown with the CDN unreachable"
        assert banner["visible"], "banner exists but is not visible"
        assert "PDF.js" in banner["text"] and "JSZip" in banner["text"], f"banner names neither library: {banner}"
        await browser.close()
    print("test_browser: PASS (offline banner when the CDN is unreachable)")


def main():
    try:
        import fitz  # noqa: F401
        import playwright  # noqa: F401
    except Exception as e:
        print(f"test_browser: SKIP (missing dependency: {e})")
        return 0
    with tempfile.TemporaryDirectory() as d:
        pdf = str(pathlib.Path(d) / "synthetic.pdf")
        pdf2 = str(pathlib.Path(d) / "synthetic2.pdf")
        make_pdf(pdf)
        make_pdf2(pdf2)
        try:
            asyncio.run(run(pdf, pdf2))
            asyncio.run(run_offline())
        except Exception as e:
            print(f"test_browser: FAIL ({e})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
