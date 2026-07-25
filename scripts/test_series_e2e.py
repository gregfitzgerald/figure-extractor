#!/usr/bin/env python3
"""
End-to-end series test on REAL benchmark ground truth.

Pushes a committed grouped-bar GT bundle (3 groups x 2 series = 6 arms) from benchmark/series/
through the tool's series-aware path and asserts every emitted row lands on the RIGHT arm's
numbers, with its legend label resolved and the B4 gate binding correct. This is the headline
claim of the series work: before the fix this chart exported as structureless rows and arm
identity was unrecoverable downstream (which also makes the multi-arm shared-control variance
correction impossible).

Requires PyMuPDF + playwright + a server on :8001; SKIPS (exit 0) if anything is missing.
Run:  python3 scripts/test_series_e2e.py
"""
import asyncio, json, glob, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
URL = "http://localhost:8001/figure-extractor.html"


async def main():
    from playwright.async_api import async_playwright
    f = sorted(glob.glob(str(REPO / "benchmark/series/corpus/gbar_*.sgt.json")))[0]
    d = json.loads(pathlib.Path(f).read_text())
    series = d["series"]; desc = d["descriptives"]

    # build (group x series) cells straight from GT values -- the structure the reader would supply
    cells = []
    tops = {(m["groupId"], m["seriesId"]): m for m in d["marks"] if m["role"] == "top"}
    caps = {(m["groupId"], m["seriesId"]): m for m in d["marks"] if m["role"] == "cap"}
    for (g, s), t in sorted(tops.items()):
        c = caps.get((g, s))
        if not c:
            continue
        cells.append({"name": f"{g} {s}", "groupId": g, "seriesId": s,
                      "mean": t["value_y"], "errorHalf": abs(c["value_y"] - t["value_y"]),
                      "n": desc.get(f"{g}|{s}", {}).get("n")})

    # a real one-page PDF, so the app renders a real canvas (addFigure -> renderAnnotations)
    import fitz, tempfile
    tmp = pathlib.Path(tempfile.mkdtemp()) / "e2e.pdf"
    doc = fitz.open(); pg1 = doc.new_page(width=612, height=792)
    pg1.draw_rect(fitz.Rect(100, 100, 500, 400), color=(0, 0, 0), width=1)
    pg1.insert_text((100, 430), "Figure 1. Outcome by group.", fontsize=11)
    doc.save(str(tmp)); doc.close()

    async with async_playwright() as pw:
        b = await pw.chromium.launch(); pg = await b.new_page(); await pg.goto(URL)
        await pg.evaluate("() => { settings.dpi = '150'; }")
        await pg.set_input_files("#pdfInput", files=[{"name": "e2e.pdf", "mimeType": "application/pdf",
                                                      "buffer": tmp.read_bytes()}])
        for _ in range(80):
            if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                break
            await pg.wait_for_timeout(250)
        fid = (await pg.evaluate("() => window.figureExtractor.addFigure(1,{x:200,y:200,width:800,height:600},'Figure 1')"))["figureId"]
        char = {"panels": [{"charType": "grouped-bar", "dataProvenance": "primary",
                            "series": [{"id": s["seriesId"], "label": s["label"],
                                        "role": "control" if "ontrol" in s["label"] else "intervention",
                                        "encoding": "fill", "labelSource": "legend"} for s in series],
                            "statistics": {"dispersion": {"present": True, "type": d.get("dispersionType", "SD")}},
                            "extractionPlan": {"method": "bar-endpoints"}}]}
        r = await pg.evaluate("(a)=>window.figureExtractor.setCharacterization(a.f,null,a.c)", {"f": fid, "c": char})
        assert r["success"], r
        r = await pg.evaluate("(a)=>window.figureExtractor.runExtraction(a.f,null,{groups:a.g})", {"f": fid, "g": cells})
        assert r["success"], r
        rows = await pg.evaluate("() => window.figureExtractor.getFigureDerivedRows()")
        prev = await pg.evaluate("(f)=>window.figureExtractor.previewAssignment(f,null)", fid)
        await b.close()

    print(f"chart: {pathlib.Path(f).name}  ({len(series)} series x {len({c['groupId'] for c in cells})} groups)")
    print(f"emitted rows: {len(rows)}")
    bad = 0
    for row in rows:
        key = f"{row['groupId']}|{row['seriesId']}"
        truth = desc.get(key)
        if not truth:
            print(f"  UNMATCHED row {key}"); bad += 1; continue
        tm = truth.get("mean")
        err = 100 * abs(row["mean"] - tm) / abs(tm)
        lab = row["seriesLabel"]
        exp_lab = next(s["label"] for s in series if s["seriesId"] == row["seriesId"])
        ok = err < 0.5 and lab == exp_lab
        if not ok: bad += 1
        print(f"  {key:9s} label={lab:8s} mean={row['mean']:.2f} truth={tm:.2f} err={err:.3f}%  {'OK' if ok else 'MISMATCH'}")
    print(f"\narm mis-assignment: {bad}/{len(rows)}")
    print(f"gate ok={prev['ok']}  bindings={[(b['label'],b['role'],b['marksBound']) for b in prev['bindings']]}")
    assert bad == 0, f"{bad} arm mis-assignments"
    assert prev["ok"], f"gate not ok: {prev.get('problems')}"
    print("test_series_e2e: PASS (6 arms from real GT, 0 mis-assignment, labels resolved, gate ok)")


def _run():
    try:
        import fitz, playwright  # noqa: F401
    except Exception as e:
        print(f"test_series_e2e: SKIP (missing dependency: {e})"); return 0
    if not glob.glob(str(REPO / "benchmark/series/corpus/gbar_*.sgt.json")):
        print("test_series_e2e: SKIP (no series GT; run Rscript benchmark/series/gen_series.R)"); return 0
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"test_series_e2e: FAIL ({e})"); return 1
    return 0


if __name__ == "__main__":
    import sys; sys.exit(_run())
