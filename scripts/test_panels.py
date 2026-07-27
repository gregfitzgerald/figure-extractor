#!/usr/bin/env python3
"""
Panel-detection cascade tests for figure-extractor.html (detectPanels API).

Generates a synthetic multi-figure PDF in-test (no external fixtures) covering:
  p1  wide gutters, 2x2, labels + caption      -> clean high-confidence split
  p2  tight 4pt gutters (defeats the legacy detector) -> still splits
  p3  stacked panels with a shared x-axis label INSIDE the gutter -> still splits
  p4  flush photo montage (no gutter, labels unrecoverable) -> ABSTAINS, flagged
  p5  flush white panels + labels -> label-seeded cut
  p6  non-guillotine pinwheel (gapped) -> detected + carved from label anchors, flagged
  p7  4 image XObjects, NO letters drawn -> exact boxes, letters UNVERIFIABLE -> flagged
  p8  caption says 6 panels, image has 2 -> panel-count-mismatch abstention

Letter identity is the second half of the answer: a panel whose box is right but whose
LETTER is wrong routes the wrong caption (and everything downstream) to the wrong picture,
while every structural metric still reads perfect. These cases exist because every fixture
above draws its labels in reading-order-consistent positions, so none of them can tell a
verified letter from an assumed one:
  p9  2x2 grid, COLUMN-MAJOR labels (A C / B D)  -> anchors must CORRECT the letters, ok=false
  p10 XObject 2x2 with column-major letters      -> the fast path must verify too
  p11 XObject 2x2 with reading-order letters     -> the verified fast path (ok=true)
  p12 single-panel figure, caption cites "(a) and (b)" of ANOTHER paper -> no invented panels
  p13 2x2 grid, caption groups "(C,D)"           -> N=4, no forced merge of real panels
  p14 3x2 grid, caption range "(A-F)"            -> N=6 from a range
  p15 2x2 grid with NO labels drawn              -> legitimately unverified, flagged not wrong

Verification proves that each box owns one distinct expected letter. It does NOT prove
those glyphs are panel LABELS -- any stray letter-shaped glyph of the right identity looks
identical to one. Adversarial round 2 turned that gap into three runnable exploits, and
each of these cases encodes one of them verbatim, plus the two coverage holes found at the
same time:
  p16 stray in-panel annotation letters, crossed -> was ok=true with the naming INVERTED
  p17 crossed parenthesised axis units (B)/(A)   -> was ok=true with the naming INVERTED
  p18 real 'A' + a stray key near A's edge       -> the boundary repair moved the true cut
                                                    silently, conf 0.92, zero flags
  p19 3x3 grid A-I ('I' is a bare stem)          -> every figure reaching (I) abstained
  p20 serif-italic labels                        -> unreadable to upright-only templates

Requires: PyMuPDF (fitz), playwright (+ chromium). SKIPS (exit 0) if missing.

Run:  python3 scripts/test_panels.py
"""

import asyncio
import json
import pathlib
import random
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = (REPO / "figure-extractor.html").as_uri()
S = 150 / 72  # render DPI scale (PDF pt -> page px at 150 dpi)


def iou(a, b):
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(1, a[2] * a[3] + b[2] * b[3] - inter)


def rel_px(rect_pt, origin_pt):
    """Panel rect in pt -> figure-relative px [x, y, w, h] at 150 dpi."""
    x0, y0, x1, y1 = rect_pt
    ox, oy = origin_pt
    return [round((x0 - ox) * S), round((y0 - oy) * S),
            round((x1 - x0) * S), round((y1 - y0) * S)]


def make_pdf(path):
    import fitz
    doc = fitz.open()

    def panel(pg, x0, y0, x1, y1, letter=None, dots=90, seed=None, smudge=False, clear=(),
              font="hebo"):
        """A bordered scatter panel. Data dots keep clear of the label corner so that the
        glyph stays readable -- what these fixtures vary is WHICH letter sits where, not
        whether it can be read. `smudge` fuses a blob to the glyph on purpose (p15): the
        label is then unreadable and the letters must end unverified, never guessed.
        `clear` lists (x, y, radius) zones to keep free of dots, so a stray annotation
        letter dropped there (p16-p18) is as readable as a real label would be."""
        pg.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
        rnd = random.Random(seed if seed is not None else int(x0 * 7 + y0))
        for _ in range(dots):
            px = x0 + 12 + rnd.random() * (x1 - x0 - 24)
            py = y0 + 12 + rnd.random() * (y1 - y0 - 24)
            if letter and px < x0 + 42 and py < y0 + 42:
                continue
            if any(abs(px - zx) < zr and abs(py - zy) < zr for zx, zy, zr in clear):
                continue
            pg.draw_circle(fitz.Point(px, py), 1.2, color=(0.1, 0.1, 0.6), fill=(0.1, 0.1, 0.6))
        if letter:
            pg.insert_text((x0 + 8, y0 + 26), letter, fontsize=20, fontname=font)
            if smudge:
                c = (0.1, 0.1, 0.6)
                pg.draw_circle(fitz.Point(x0 + 18, y0 + 28), 4, color=c, fill=c)

    def photo(pg, x0, y0, x1, y1, base, seed, label=None):
        pg.draw_rect(fitz.Rect(x0, y0, x1, y1), color=base, fill=base)
        rnd = random.Random(seed)
        for _ in range(500):
            px = x0 + rnd.random() * (x1 - x0 - 6)
            py = y0 + rnd.random() * (y1 - y0 - 6)
            c = (rnd.random() * 0.5, rnd.random() * 0.5, rnd.random() * 0.5)
            pg.draw_rect(fitz.Rect(px, py, px + 5, py + 5), color=c, fill=c)
        if label:
            pg.insert_text((x0 + 8, y0 + 26), label, fontsize=20, fontname="hebo", color=(1, 1, 1))

    def scatter_png(w=240, h=180, color=(0.8, 0.2, 0.2), seed=0):
        tmp = fitz.open()
        pg = tmp.new_page(width=w, height=h)
        pg.draw_rect(fitz.Rect(2, 2, w - 2, h - 2), color=(0, 0, 0), width=1)
        rnd = random.Random(seed)
        for _ in range(60):
            px, py = 8 + rnd.random() * (w - 16), 8 + rnd.random() * (h - 16)
            if px < 0.22 * w and py < 0.28 * h:
                continue   # keep the label corner clear (see `panel`)
            pg.draw_circle(fitz.Point(px, py), 1.5, color=color, fill=color)
        data = pg.get_pixmap(dpi=150).tobytes("png")
        tmp.close()
        return data

    # p1: wide gutters (30pt), 2x2 grid, labels A-D
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 285, 285, "A"); panel(p, 315, 50, 550, 285, "B")
    panel(p, 50, 315, 285, 550, "C"); panel(p, 315, 315, 550, 550, "D")

    # p2: tight gutters (4pt), 2x2 grid, labels A-D
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 298, 298, "A"); panel(p, 302, 50, 550, 298, "B")
    panel(p, 50, 302, 298, 550, "C"); panel(p, 302, 302, 550, 550, "D")

    # p3: two stacked panels; the gutter holds tick numbers AND a shared x-axis title
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 550, 330, "A"); panel(p, 50, 370, 550, 650, "B")
    for i, t in enumerate(["5", "15", "25", "35", "45"]):
        p.insert_text((90 + i * 100, 344), t, fontsize=9)
    p.insert_text((210, 360), "Time since randomization (weeks)", fontsize=10)

    # p4: flush photo montage, labels drawn ON the photos (unrecoverable) -> must abstain
    p = doc.new_page(width=612, height=792)
    photo(p, 50, 50, 300, 350, (0.45, 0.5, 0.6), 7, "A")
    photo(p, 300, 50, 550, 350, (0.6, 0.5, 0.45), 8, "B")

    # p5: flush white panels sharing an edge, isolated labels -> label-seeded cut
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 300, 350, "A", dots=70); panel(p, 300, 50, 550, 350, "B", dots=70)

    # p6: non-guillotine pinwheel with 10pt gaps, labels A-D
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 345, 195, "A", dots=60)      # top-left, wide
    panel(p, 355, 50, 500, 345, "B", dots=60)     # right, tall
    panel(p, 50, 205, 195, 500, "C", dots=60)     # left, tall
    panel(p, 205, 355, 500, 500, "D", dots=60)    # bottom, wide

    # p7: figure composed of 4 image XObjects (2x2, 20pt gutters)
    p = doc.new_page(width=612, height=792)
    p.insert_image(fitz.Rect(50, 50, 290, 230), stream=scatter_png(color=(0.8, 0.2, 0.2), seed=1))
    p.insert_image(fitz.Rect(310, 50, 550, 230), stream=scatter_png(color=(0.2, 0.6, 0.2), seed=2))
    p.insert_image(fitz.Rect(50, 250, 290, 430), stream=scatter_png(color=(0.2, 0.2, 0.8), seed=3))
    p.insert_image(fitz.Rect(310, 250, 550, 430), stream=scatter_png(color=(0.7, 0.5, 0.1), seed=4))

    # p8: two obvious panels but the caption will claim SIX -> count-mismatch abstention
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 285, 285, "A"); panel(p, 315, 50, 550, 285, "B")

    # p9: 2x2 grid labelled COLUMN-MAJOR (A top-left, B BELOW it, C top-right, D bottom-right)
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 285, 285, "A"); panel(p, 315, 50, 550, 285, "C")
    panel(p, 50, 315, 285, 550, "B"); panel(p, 315, 315, 550, 550, "D")

    # p10: XObject 2x2 with column-major letters painted on top of the images
    p = doc.new_page(width=612, height=792)
    for rect, seed, col in [((50, 50, 290, 230), 1, (0.8, 0.2, 0.2)), ((310, 50, 550, 230), 2, (0.2, 0.6, 0.2)),
                            ((50, 250, 290, 430), 3, (0.2, 0.2, 0.8)), ((310, 250, 550, 430), 4, (0.7, 0.5, 0.1))]:
        p.insert_image(fitz.Rect(*rect), stream=scatter_png(color=col, seed=seed))
    for xy, ch in [((58, 78), "A"), ((318, 78), "C"), ((58, 278), "B"), ((318, 278), "D")]:
        p.insert_text(xy, ch, fontsize=20, fontname="hebo")

    # p11: the same XObject figure with reading-order letters -> the verified fast path
    p = doc.new_page(width=612, height=792)
    for rect, seed, col in [((50, 50, 290, 230), 1, (0.8, 0.2, 0.2)), ((310, 50, 550, 230), 2, (0.2, 0.6, 0.2)),
                            ((50, 250, 290, 430), 3, (0.2, 0.2, 0.8)), ((310, 250, 550, 430), 4, (0.7, 0.5, 0.1))]:
        p.insert_image(fitz.Rect(*rect), stream=scatter_png(color=col, seed=seed))
    for xy, ch in [((58, 78), "A"), ((318, 78), "B"), ((58, 278), "C"), ((318, 278), "D")]:
        p.insert_text(xy, ch, fontsize=20, fontname="hebo")

    # p12: ONE plot plus a boxed legend -- a single-panel figure whose caption cites (a)/(b)
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 400, 350, None, dots=120)
    p.draw_rect(fitz.Rect(430, 120, 550, 280), color=(0, 0, 0), width=1)
    for i, t in enumerate(["placebo", "low dose", "high dose"]):
        c = [(0.8, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.8)][i]
        p.draw_rect(fitz.Rect(440, 140 + i * 40, 452, 152 + i * 40), color=c, fill=c)
        p.insert_text((458, 150 + i * 40), t, fontsize=10)

    # p13: plain 2x2 A-D grid; the caption groups the last two as "(C,D)"
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 285, 285, "A"); panel(p, 315, 50, 550, 285, "B")
    panel(p, 50, 315, 285, 550, "C"); panel(p, 315, 315, 550, 550, "D")

    # p14: 3x2 grid A-F; the caption names the run as a range "(A-F)"
    p = doc.new_page(width=612, height=792)
    for i, ch in enumerate("ABCDEF"):
        cx, cy = 50 + (i % 3) * 170, 50 + (i // 3) * 200
        panel(p, cx, cy, cx + 150, cy + 170, ch, dots=50)

    # p15: 2x2 A-D grid whose labels are FUSED to a data blob -> unreadable glyphs
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 285, 285, "A", smudge=True); panel(p, 315, 50, 550, 285, "B", smudge=True)
    panel(p, 50, 315, 285, 550, "C", smudge=True); panel(p, 315, 315, 550, 550, "D", smudge=True)

    # ---- EXPLOIT REGRESSIONS (adversarial round 2) --------------------------------
    # p16 encodes exploit k1-swapped-annot. Two gutter-separated panels, NO panel labels
    # drawn at all; panel A carries an isolated annotation 'b' in the middle of its data and
    # panel B an isolated 'a'. Both glyphs are perfectly readable and between them they are
    # exactly the expected letter set, so "every box owns one distinct expected letter"
    # holds -- and the cascade shipped ok=true conf=0.80 with letters ['b','a'], routing the
    # (A) and (B) caption segments to the wrong pictures at IoU 1.0. Nothing structural was
    # wrong, which is what made it silent.
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 285, 285, None, clear=[(155, 160, 34)])
    panel(p, 315, 50, 550, 285, None, clear=[(425, 160, 34)])
    p.insert_text((148, 168), "b", fontsize=20, fontname="hebo")
    p.insert_text((418, 168), "a", fontsize=20, fontname="hebo")

    # p17 encodes exploit k11-crossed-units. The same inversion built out of parenthesised
    # axis units instead of annotation letters: the TOP panel is marked "(B)", the BOTTOM
    # one "(A)", at mid-height against the y axis. The glyph templates deliberately carry
    # the "(X)" label form, so these matched as labels and produced ok=true conf=0.80 with
    # letters ['b','a'].
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 550, 190, None, dots=120, clear=[(80, 115, 40)])
    panel(p, 50, 230, 550, 370, None, dots=120, clear=[(80, 295, 40)])
    p.insert_text((62, 122), "(B)", fontsize=16, fontname="hebo")
    p.insert_text((62, 302), "(A)", fontsize=16, fontname="hebo")

    # p18 encodes exploit k3-repair-poison. Panel A has its REAL 'A' at the top left plus a
    # stray legend-key 'b' near its right edge; panel B is unlabelled. Box A then owned two
    # anchors and box B none, so repairAnchorBoxAssignment dragged the A/B boundary onto the
    # stray glyph: box A shrank, box B swallowed a strip of A's content (IoU 0.85 / 0.77),
    # and the result shipped at confidence 0.92 with an EMPTY flag list.
    p = doc.new_page(width=612, height=792)
    panel(p, 50, 50, 300, 285, "A", clear=[(268, 160, 34)])
    panel(p, 330, 50, 550, 285, None)
    p.insert_text((262, 168), "b", fontsize=20, fontname="hebo")

    # p19: 3x3 grid A-I. 'I' is a bare vertical stem, so no shape test can separate it from
    # a lowercase 'l' and the label-size gates reject a solid stem outright -- every figure
    # whose letters reached (I) lost an anchor and abstained.
    p = doc.new_page(width=612, height=792)
    for i, ch in enumerate("ABCDEFGHI"):
        cx, cy = 50 + (i % 3) * 175, 50 + (i // 3) * 175
        panel(p, cx, cy, cx + 155, cy + 155, ch, dots=45)

    # p20: 2x2 grid whose labels are set in SERIF ITALIC (Times-Italic), which correlated
    # against upright-only templates at 0.58-0.80 and left the figure unverified.
    p = doc.new_page(width=612, height=792)
    for i, ch in enumerate("ABCD"):
        cx, cy = 50 + (i % 2) * 265, 50 + (i // 2) * 265
        panel(p, cx, cy, cx + 235, cy + 235, ch, font="tiit")

    doc.save(path)
    doc.close()


CAP4 = "Figure 1. Overview. (A) alpha panel. (B) beta panel. (C) gamma panel. (D) delta panel."
CAP2 = "Figure 1. Overview. (A) alpha panel. (B) beta panel."
CAP6 = ("Figure 1. Overview. (A) one. (B) two. (C) three. (D) four. (E) five. (F) six.")
CAPCITE = "As shown in (a) and (b) of Smith et al. (2019), serum levels rise with dose."
CAPCD = "Figure 1. (A) one thing. (B) another thing. (C,D) both things combined."
CAPRANGE = "Figure 1. (A-F) Dose response across six conditions."
CAP9 = "Figure 1. (A) a1. (B) a2. (C) a3. (D) a4. (E) a5. (F) a6. (G) a7. (H) a8. (I) a9."

CASES = [
    dict(name="p1-wide", page=1, region=(50, 50, 550, 550), caption=CAP4,
         truth=[(50, 50, 285, 285), (315, 50, 550, 285), (50, 315, 285, 550), (315, 315, 550, 550)]),
    dict(name="p2-tight", page=2, region=(50, 50, 550, 550), caption=CAP4,
         truth=[(50, 50, 298, 298), (302, 50, 550, 298), (50, 302, 298, 550), (302, 302, 550, 550)]),
    dict(name="p3-gutter-label", page=3, region=(50, 50, 550, 650), caption=CAP2,
         truth=[(50, 50, 550, 330), (50, 370, 550, 650)]),
    dict(name="p4-flush-photos", page=4, region=(50, 50, 550, 350), caption=CAP2, truth=None),
    dict(name="p5-flush-labels", page=5, region=(50, 50, 550, 350), caption=CAP2,
         truth=[(50, 50, 300, 350), (300, 50, 550, 350)]),
    dict(name="p6-pinwheel", page=6, region=(50, 50, 500, 500), caption=CAP4,
         truth=[(50, 50, 345, 195), (355, 50, 500, 345), (50, 205, 195, 500), (205, 355, 500, 500)]),
    dict(name="p7-xobjects", page=7, region=(50, 50, 550, 430), caption=CAP4,
         truth=[(50, 50, 290, 230), (310, 50, 550, 230), (50, 250, 290, 430), (310, 250, 550, 430)]),
    dict(name="p8-abstain", page=8, region=(50, 50, 550, 285), caption=CAP6, truth=None),
    dict(name="p9-colmajor", page=9, region=(50, 50, 550, 550), caption=CAP4,
         truth=[(50, 50, 285, 285), (315, 50, 550, 285), (50, 315, 285, 550), (315, 315, 550, 550)]),
    dict(name="p10-xobj-colmajor", page=10, region=(50, 50, 550, 430), caption=CAP4,
         truth=[(50, 50, 290, 230), (310, 50, 550, 230), (50, 250, 290, 430), (310, 250, 550, 430)]),
    dict(name="p11-xobj-labelled", page=11, region=(50, 50, 550, 430), caption=CAP4,
         truth=[(50, 50, 290, 230), (310, 50, 550, 230), (50, 250, 290, 430), (310, 250, 550, 430)]),
    dict(name="p12-cite-poison", page=12, region=(50, 50, 550, 350), caption=CAPCITE, truth=None),
    dict(name="p13-grouped-cd", page=13, region=(50, 50, 550, 550), caption=CAPCD,
         truth=[(50, 50, 285, 285), (315, 50, 550, 285), (50, 315, 285, 550), (315, 315, 550, 550)]),
    dict(name="p14-range", page=14, region=(50, 50, 550, 420), caption=CAPRANGE,
         truth=[(50, 50, 200, 220), (220, 50, 370, 220), (390, 50, 540, 220),
                (50, 250, 200, 420), (220, 250, 370, 420), (390, 250, 540, 420)]),
    dict(name="p15-smudged-labels", page=15, region=(50, 50, 550, 550), caption=CAP4,
         truth=[(50, 50, 285, 285), (315, 50, 550, 285), (50, 315, 285, 550), (315, 315, 550, 550)]),
    dict(name="p16-stray-annot-swap", page=16, region=(50, 50, 550, 285), caption=CAP2,
         truth=[(50, 50, 285, 285), (315, 50, 550, 285)]),
    dict(name="p17-crossed-units", page=17, region=(50, 50, 550, 370), caption=CAP2,
         truth=[(50, 50, 550, 190), (50, 230, 550, 370)]),
    dict(name="p18-stray-key-repair", page=18, region=(50, 50, 550, 285), caption=CAP2,
         truth=[(50, 50, 300, 285), (330, 50, 550, 285)]),
    dict(name="p19-nine-panels", page=19, region=(50, 50, 555, 555), caption=CAP9, truth=None),
    dict(name="p20-serif-italic", page=20, region=(50, 50, 550, 550), caption=CAP4, truth=None),
]


async def run(pdf_path):
    from playwright.async_api import async_playwright
    errors = []
    results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context()
        pg = await ctx.new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        await pg.goto(TOOL)

        buf = pathlib.Path(pdf_path).read_bytes()
        await pg.evaluate("() => { settings.dpi = '150'; }")
        await pg.set_input_files("#pdfInput", files=[{
            "name": "panels.pdf", "mimeType": "application/pdf", "buffer": buf}])
        for _ in range(120):
            if await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"):
                break
            await pg.wait_for_timeout(250)
        assert await pg.evaluate("() => window.figureExtractor.isReady().articleLoaded"), "article never loaded"

        for case in CASES:
            x0, y0, x1, y1 = case["region"]
            b = {"x": round(x0 * S), "y": round(y0 * S),
                 "width": round((x1 - x0) * S), "height": round((y1 - y0) * S)}
            fid = (await pg.evaluate(
                f"() => window.figureExtractor.addFigure({case['page']}, {json.dumps(b)}, 'Figure {case['page']}')"
            ))["figureId"]
            await pg.evaluate(
                f"() => {{ const f = state.figures.find(x => x.id === '{fid}'); "
                f"f.caption = {json.dumps(case['caption'])}; f.captionSource = 'manual'; }}")
            res = await pg.evaluate(
                f"() => window.figureExtractor.detectPanels('{fid}', {{ apply: true }})")
            legacy = await pg.evaluate(
                f"() => window.figureExtractor.suggestSubfiguresLegacy('{fid}')")
            subs = await pg.evaluate(
                f"() => state.figures.find(x => x.id === '{fid}').subfigures"
                f".map(s => ({{ label: s.label, caption: s.caption }}))")
            results[case["name"]] = dict(res=res, legacy=legacy, subs=subs, fid=fid)

        # schema round-trip: panelDetection persists, schemaVersion stays 2
        j = await pg.evaluate("() => window.figureExtractor.getAnnotationsJSON()")
        assert j["schemaVersion"] == 2, "schemaVersion changed"
        assert any(f.get("panelDetection") for f in j["figures"]), "panelDetection not serialized"

        # BLINDING: annotationMode must stop the detectors at the SOURCE, not just at the
        # API wrapper. The bare global `suggestSubfiguresLegacy` stays reachable from a
        # devtools console after every wrapper refuses, and because it returns bare boxes
        # it writes no `panelDetection` and no `captionSource:'panel-split'` -- so boxes
        # taken from it are INVISIBLE to rvcommon.blinding_violations after the fact.
        # An after-the-fact audit structurally cannot catch this one; only the guard can.
        # Regression-test the bare global directly, the way the threat model does.
        blind_fid = results[CASES[0]["name"]]["fid"]
        await pg.evaluate("() => { settings.annotationMode = true; }")
        bare = await pg.evaluate(
            f"() => {{ const f = state.figures.find(x => x.id === '{blind_fid}'); "
            f"const w = []; const o = console.warn; console.warn = (...a) => w.push(a.join(' ')); "
            f"const boxes = suggestSubfiguresLegacy(f, 2); console.warn = o; "
            f"return {{ n: (boxes || []).length, warned: w.some(m => m.includes('refused')) }}; }}")
        wrapped = await pg.evaluate(
            f"() => window.figureExtractor.suggestSubfiguresLegacy('{blind_fid}')")
        core = await pg.evaluate(
            f"() => window.figureExtractor.detectPanels('{blind_fid}', {{ apply: true }})")
        await pg.evaluate("() => { settings.annotationMode = false; }")
        results["_blinding"] = dict(bare=bare, wrapped=wrapped, core=core)

        await browser.close()

    hard_errors = [e for e in errors if "favicon" not in e and "net::ERR" not in e]
    assert not hard_errors, f"console errors: {hard_errors}"
    return results


def check(results):
    failures = []

    def expect(name, cond, msg):
        status = "ok " if cond else "FAIL"
        print(f"  [{status}] {name}: {msg}")
        if not cond:
            failures.append(f"{name}: {msg}")

    def boxes_of(res):
        return [[p["bounds"]["x"], p["bounds"]["y"], p["bounds"]["width"], p["bounds"]["height"]]
                for p in res["panels"]]

    def match_truth(case, res, min_iou):
        origin = case["region"][:2]
        truth = [rel_px(t, origin) for t in case["truth"]]
        got = boxes_of(res)
        if len(got) != len(truth):
            return False, f"count {len(got)} != {len(truth)}"
        ious = [round(iou(g, t), 2) for g, t in zip(got, truth)]
        return all(v >= min_iou for v in ious), f"IoUs {ious}"

    for case in CASES:
        name = case["name"]
        r = results[name]
        res = r["res"]
        print(f"{name}: method={res['method']} count={res['count']} conf={res['confidence']} "
              f"flags={res['flags']} ok={res['ok']} legacy_n={len(r['legacy'])}")

        if name == "p1-wide":
            expect(name, res["count"] == 4 and res["ok"], f"4 verified panels (got {res['count']}, ok={res['ok']})")
            expect(name, res["confidence"] >= 0.8, f"confidence {res['confidence']} >= 0.8")
            good, msg = match_truth(case, res, 0.7)
            expect(name, good, msg)
            expect(name, [p["letter"] for p in res["panels"]] == ["a", "b", "c", "d"], "letters a-d in reading order")
            expect(name, r["res"]["applied"] and "alpha" in (r["subs"][0]["caption"] or ""),
                   "applied with per-panel caption text")
        elif name == "p2-tight":
            expect(name, res["count"] == 4 and res["ok"], f"4 verified panels (got {res['count']}, ok={res['ok']})")
            good, msg = match_truth(case, res, 0.7)
            expect(name, good, msg)
            expect(name, len(r["legacy"]) != 4, f"legacy fails on tight gutters (got {len(r['legacy'])})")
        elif name == "p3-gutter-label":
            expect(name, res["count"] == 2, f"2 panels despite label text in the gutter (got {res['count']})")
            if res["count"] == 2:
                good, msg = match_truth(case, res, 0.7)
                expect(name, good, msg)
        elif name == "p4-flush-photos":
            expect(name, not res["ok"] and res["confidence"] < 0.5,
                   f"abstains (ok={res['ok']}, conf={res['confidence']})")
            expect(name, "panel-count-mismatch" in res["flags"] or res["count"] != 2,
                   f"flags carry the failure: {res['flags']}")
            expect(name, res.get("applied") is False, "not auto-applied")
        elif name == "p5-flush-labels":
            expect(name, res["count"] == 2, f"flush panels split via labels (got {res['count']})")
            if res["count"] == 2:
                good, msg = match_truth(case, res, 0.6)
                expect(name, good, msg)
                expect(name, res["method"] in ("gutter", "gutter+labels", "seam"), f"method {res['method']}")
        elif name == "p6-pinwheel":
            # The carve names every panel from its drawn label; full letter verification is
            # independent evidence for the partition, so a verified carve is ok=true. An
            # UNVERIFIED non-guillotine result must still abstain (covered by p4/p15).
            if res["count"] == 4:
                good, msg = match_truth(case, res, 0.5)
                expect(name, good, f"carved boxes {msg}")
                expect(name, res["lettersVerified"] and res["ok"],
                       f"verified carve is trusted (ok={res['ok']}, verified={res['lettersVerified']})")
            else:
                expect(name, not res["ok"] and res["confidence"] < 0.5,
                       f"or abstains (ok={res['ok']}, conf={res['confidence']})")
        elif name == "p7-xobjects":
            # Exact geometry, but nothing in the image says which panel is (A): the fast path
            # gets no free pass on naming just because its boxes are perfect.
            expect(name, res["method"] == "xobject", f"fast path used (method={res['method']})")
            expect(name, res["count"] == 4, f"4 boxes (got {res['count']})")
            if res["count"] == 4:
                good, msg = match_truth(case, res, 0.9)
                expect(name, good, msg)
            expect(name, "panel-labels-unverified" in res["flags"] and not res["lettersVerified"],
                   f"unlabelled panels are not silently named: {res['flags']}")
            expect(name, not res["ok"] and res.get("applied") is False,
                   f"unverified letters block apply (ok={res['ok']})")
        elif name == "p8-abstain":
            expect(name, "panel-count-mismatch" in res["flags"], f"mismatch flagged: {res['flags']}")
            expect(name, not res["ok"] and res["confidence"] < 0.5 and res.get("applied") is False,
                   f"abstains, not applied (ok={res['ok']}, conf={res['confidence']})")
        elif name in ("p9-colmajor", "p10-xobj-colmajor"):
            # The boxes are in reading order; the LABELS run down the columns. Reading order is
            # only a prior -- the glyph anchors are the evidence and must overrule it.
            expect(name, res["count"] == 4, f"4 panels (got {res['count']})")
            if res["count"] == 4:
                good, msg = match_truth(case, res, 0.7)
                expect(name, good, msg)
            expect(name, [p["letter"] for p in res["panels"]] == ["a", "c", "b", "d"],
                   f"anchors correct the letters (got {[p['letter'] for p in res['panels']]})")
            expect(name, "label-order-mismatch" in res["flags"], f"mismatch flagged: {res['flags']}")
            # The correction is fully anchor-verified (every box owns exactly one expected
            # letter), so the CORRECTED letters ship as ok -- never the reading-order guess.
            expect(name, res["lettersVerified"] and res["letterSource"] == "anchors",
                   f"correction is evidence-backed (verified={res['lettersVerified']})")
            expect(name, res["ok"] and res.get("applied") is True,
                   f"verified correction is trusted (ok={res['ok']}, applied={res.get('applied')})")
        elif name == "p11-xobj-labelled":
            expect(name, res["method"] == "xobject", f"fast path used (method={res['method']})")
            expect(name, res["count"] == 4 and res["ok"] and res["confidence"] >= 0.9,
                   f"exact verified boxes (ok={res['ok']}, conf={res['confidence']})")
            expect(name, res["lettersVerified"] and [p["letter"] for p in res["panels"]] == list("abcd"),
                   "letters verified against the drawn labels")
            if res["count"] == 4:
                good, msg = match_truth(case, res, 0.9)
                expect(name, good, msg)
        elif name == "p12-cite-poison":
            # "(a) and (b) of Smith et al. (2019)" names panels of ANOTHER paper's figure.
            expect(name, res["expected"]["count"] is None,
                   f"citation does not pin a panel count (got {res['expected']['count']})")
            expect(name, not res["ok"] and res.get("applied") is False,
                   f"no confident split on a single-panel figure (ok={res['ok']})")
            expect(name, not r["subs"], f"annotations untouched (subfigures={len(r['subs'])})")
        elif name == "p13-grouped-cd":
            expect(name, res["expected"]["count"] == 4, f"(C,D) counts as two panels (got {res['expected']['count']})")
            expect(name, res["count"] == 4 and res["ok"], f"4 real panels kept (got {res['count']}, ok={res['ok']})")
            if res["count"] == 4:
                good, msg = match_truth(case, res, 0.7)
                expect(name, good, msg)
            caps = [s["caption"] for s in r["subs"]]
            expect(name, len(caps) == 4 and caps[2] == caps[3] == "both things combined.",
                   f"grouped segment goes to both panels (got {caps})")
        elif name == "p14-range":
            expect(name, res["expected"]["count"] == 6, f"(A-F) expands to 6 (got {res['expected']['count']})")
            expect(name, res["count"] == 6 and res["ok"], f"6 verified panels (got {res['count']}, ok={res['ok']})")
            expect(name, [p["letter"] for p in res["panels"]] == list("abcdef"), "letters a-f")
            if res["count"] == 6:
                good, msg = match_truth(case, res, 0.7)
                expect(name, good, msg)
        elif name == "p15-smudged-labels":
            # The labels are there but unreadable. Ending unverified is the CORRECT outcome;
            # forcing a match on a letter-shaped blob is the failure mode being guarded.
            expect(name, res["count"] == 4, f"boxes still found (got {res['count']})")
            expect(name, "panel-labels-unverified" in res["flags"] and not res["lettersVerified"],
                   f"unreadable labels end unverified: {res['flags']}")
            expect(name, not res["ok"] and res.get("applied") is False,
                   f"flagged, not applied (ok={res['ok']}, applied={res.get('applied')})")
            expect(name, not r["subs"], "no subfigures written")
        elif name in ("p16-stray-annot-swap", "p17-crossed-units"):
            # THE EXPLOIT: letter identity alone "verified" a swapped naming. The repair is
            # that a glyph must also be PLACED like a label -- both of these sit mid-panel,
            # so the anchor set is rejected, the letters fall back to the reading-order
            # prior, and the figure abstains instead of shipping an inversion.
            letters = [p["letter"] for p in res["panels"]]
            expect(name, letters != ["b", "a"],
                   f"stray glyphs never invert the naming (got {letters})")
            expect(name, "label-placement-implausible" in res["flags"],
                   f"the mid-panel placement is named in the flags: {res['flags']}")
            expect(name, not res["lettersVerified"] and not res["ok"]
                   and res.get("applied") is False,
                   f"abstains rather than routing captions (ok={res['ok']}, "
                   f"verified={res['lettersVerified']})")
            expect(name, not r["subs"], f"annotations untouched ({len(r['subs'])} subfigures)")
        elif name == "p18-stray-key-repair":
            # THE EXPLOIT: a stray key next to a real label made box A own two anchors, and
            # the boundary repair moved the A/B cut onto the stray glyph -- silently, at
            # conf 0.92 with no flags. The repair may now only run on a placement-plausible
            # anchor set, and must flag `boundary-repaired` when it moves anything. So the
            # boxes are either untouched or the move is loud; a silent move is the failure.
            expect(name, res["count"] == 2, f"2 panels (got {res['count']})")
            good, msg = match_truth(case, res, 0.95)
            moved = "boundary-repaired" in res["flags"]
            expect(name, good or moved or not res["ok"],
                   f"the true boundary is kept, flagged, or abstained -- never moved "
                   f"silently ({msg}, flags={res['flags']}, ok={res['ok']})")
            expect(name, not (res["ok"] and not good),
                   f"never ok=true on corrupted boxes ({msg}, ok={res['ok']})")
            expect(name, not res["ok"] and res.get("applied") is False,
                   f"a box owning two anchors is unresolved evidence -> abstain "
                   f"(ok={res['ok']})")
        elif name == "p19-nine-panels":
            # 'I' is a bare stem: unnameable by shape and rejected by the label-size gates,
            # so every figure whose letters reached (I) used to abstain.
            expect(name, res["count"] == 9, f"9 panels (got {res['count']})")
            expect(name, [p["letter"] for p in res["panels"]] == list("abcdefghi"),
                   f"letters a-i (got {[p['letter'] for p in res['panels']]})")
            expect(name, res["lettersVerified"] and res["ok"],
                   f"the 'I' anchor completes the set (ok={res['ok']}, "
                   f"verified={res['lettersVerified']})")
        elif name == "p20-serif-italic":
            expect(name, res["count"] == 4, f"4 panels (got {res['count']})")
            expect(name, res["lettersVerified"] and res["ok"]
                   and [p["letter"] for p in res["panels"]] == list("abcd"),
                   f"serif-italic labels are read (ok={res['ok']}, "
                   f"verified={res['lettersVerified']})")

    # Global invariant: `apply` may only ever write a VERIFIED result, and `applied` must say
    # so truthfully. The old suite passed apply:true everywhere and checked `applied` twice,
    # so results with ok=false were silently mutating the annotations during a green run.
    for case in CASES:
        res = results[case["name"]]["res"]
        applied = res.get("applied")
        expect(case["name"], applied is (res["ok"] and res["count"] >= 2),
               f"applied={applied} matches ok={res['ok']} (count={res['count']})")
        if not res["ok"]:
            expect(case["name"], not results[case["name"]]["subs"],
                   f"ok=false wrote nothing (subfigures={len(results[case['name']]['subs'])})")

    # BLINDING: every detector entry point must refuse in annotationMode. The bare global
    # is the one that matters -- it leaves no fingerprint, so rvcommon.blinding_violations
    # cannot detect its output after the fact. Guarding only the wrapper (the state this
    # suite shipped in previously) left a hole that no downstream audit could ever see.
    b = results.get("_blinding")
    if b:
        expect("blinding", b["bare"]["n"] == 0,
               f"bare global suggestSubfiguresLegacy refuses (got {b['bare']['n']} boxes)")
        expect("blinding", b["bare"]["warned"], "bare global warns on refusal")
        expect("blinding", b["wrapped"]["flags"] == ["annotation-mode"] and not b["wrapped"]["panels"],
               f"API wrapper refuses (flags={b['wrapped']['flags']})")
        expect("blinding", b["core"]["flags"] == ["annotation-mode"] and not b["core"]["panels"],
               f"detectPanels refuses (flags={b['core']['flags']})")
    else:
        failures.append("blinding: no annotationMode results captured")

    return failures


def main():
    try:
        import fitz  # noqa: F401
        import playwright  # noqa: F401
    except ImportError as e:
        print(f"SKIP: missing dependency ({e.name}); install PyMuPDF + playwright to run")
        return 0
    with tempfile.TemporaryDirectory() as td:
        pdf = pathlib.Path(td) / "panels.pdf"
        make_pdf(pdf)
        try:
            results = asyncio.run(run(pdf))
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                print("SKIP: chromium not installed (python -m playwright install chromium)")
                return 0
            raise
    failures = check(results)
    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print("  -", f)
        return 1
    print("\nAll panel-detection tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
