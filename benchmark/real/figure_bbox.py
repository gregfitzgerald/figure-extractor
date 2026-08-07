#!/usr/bin/env python3
"""figure_bbox.py -- locate the figure region on a real journal page, three ways.

WHY THIS FILE EXISTS AND WHAT IT CANNOT DO
------------------------------------------
figure-extractor.html's figure boxing is MANUAL: a human drags a rectangle around the
figure and the panel detector partitions what is inside it. To score the detector on real
articles without a human in the loop, something has to supply that rectangle. This module
supplies it -- and every panel number downstream inherits whatever bias it has.

There is NO human-drawn figure bbox for the 71 worklist figures. So the bboxes here are
UNVALIDATED MACHINE OUTPUT, not ground truth. The only defensible use is to run all three
policies and report how much the detector's answer moves when the box moves. If the answer
is policy-sensitive, the honest conclusion is that real-figure panel detection cannot be
scored until a human draws the boxes.

POLICIES
  fullpage   bounds = the whole page. Deliberately wrong, kept as the floor: it is what
             the detector sees if figure boxing is skipped entirely. Its failures are
             attributable to the box, not the detector.
  capband    caption-anchored band. The full text-column width, from the caption's top
             edge up to the bottom of the nearest prose block above the figure content.
             Cheap, no image/vector analysis, over-includes horizontally.
  cluster    content clustering. Image XObject placements + vector drawing bboxes on the
             caption's side of the caption, merged by proximity, then grown to swallow
             the short text runs (axis labels, panel letters, tick numbers) that sit in or
             beside the cluster. Tightest box; the one most likely to CLIP a panel whose
             content is faint, and the one that can swallow a neighbouring figure.

All rectangles are returned in RENDERED PNG PIXELS at the requested DPI, matching the
page raster the browser tool is handed, so they can be used as `fig.bounds` directly.
"""
import re
import fitz

# --- tunables, all in PDF points (1/72 in) unless noted -----------------------
MERGE_GAP      = 14.0   # two content primitives closer than this merge into one cluster
TEXT_GROW_GAP  = 10.0   # a short text run this close to the cluster is figure furniture
PROSE_CHARS    = 180    # a text block longer than this is prose, never figure furniture
MIN_PRIM_AREA  = 4.0    # pt^2; drop true hairline/degenerate drawing ops
LOGO_FRAC      = 0.004  # image smaller than this fraction of page area is an ornament
PAD            = 4.0    # padding added to the final cluster box


def _rect(t):
    return fitz.Rect(t[0], t[1], t[2], t[3])


def _merge_close(rects, gap):
    """Union-merge rectangles whose expanded copies intersect. Repeats to a fixpoint."""
    boxes = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        for b in boxes:
            hit = None
            for i, o in enumerate(out):
                if fitz.Rect(b) + (-gap, -gap, gap, gap) & o:
                    hit = i
                    break
            if hit is None:
                out.append(fitz.Rect(b))
            else:
                out[hit] |= b
                changed = True
        boxes = out
    return boxes


def find_caption_rect(page, figure_number, caption_text=""):
    """Locate the caption block for 'Figure <n>' on this page.

    Returns (rect, how) or (None, reason). Prefers a block whose FIRST 40 chars open with
    a figure label for this number -- captions are labelled, in-text cross references
    ('as shown in Figure 3') are not, and 40 chars is short enough that a mid-sentence
    reference cannot masquerade as a caption opener.
    """
    n = figure_number
    pat = re.compile(r"^\W{0,4}(figure|fig\.?|abbildung)\s*0*%d\b" % n, re.I)
    blocks = [b for b in page.get_text("blocks") if b[6] == 0]  # text blocks only
    cands = [b for b in blocks if pat.search((b[4] or "").lstrip()[:40])]
    if cands:
        # longest such block: journals sometimes split the label into its own block
        b = max(cands, key=lambda b: len(b[4]))
        return _rect(b), "block-label"
    # fall back: a raw text search for the label token, take the widest hit
    hits = []
    for tok in (f"Figure {n}", f"Fig. {n}", f"FIGURE {n}", f"Fig {n}"):
        hits += list(page.search_for(tok))
    if hits:
        h = max(hits, key=lambda r: r.width)
        # grow to the block that contains it
        for b in blocks:
            if _rect(b).contains(h):
                return _rect(b), "search-in-block"
        return h, "search-bare"
    return None, "caption-not-found"


def _content_primitives(page):
    """Image placements and vector drawing bboxes, minus ornaments and hairlines."""
    parea = page.rect.get_area()
    prims, imgs = [], []
    for im in page.get_images(full=True):
        try:
            rs = page.get_image_rects(im[0])
        except Exception:
            rs = []
        for r in rs:
            if r.get_area() >= LOGO_FRAC * parea:
                prims.append(fitz.Rect(r))
                imgs.append(fitz.Rect(r))
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.get_area() >= MIN_PRIM_AREA and r.width < 0.98 * page.rect.width:
            prims.append(r)
    return prims, imgs


def bbox_cluster(page, cap_rect):
    """Content cluster adjacent to the caption. Returns (rect, info) or (None, info)."""
    info = {}
    prims, imgs = _content_primitives(page)
    info["n_prims"] = len(prims)
    info["n_image_rects"] = len(imgs)
    if not prims:
        return None, dict(info, reason="no-content-primitives")

    above = [p for p in prims if p.y1 <= cap_rect.y0 + 2]
    below = [p for p in prims if p.y0 >= cap_rect.y1 - 2]
    a_area = sum(p.get_area() for p in above)
    b_area = sum(p.get_area() for p in below)
    side, pool = ("above", above) if a_area >= b_area else ("below", below)
    info["caption_side"] = side          # figure sits ABOVE the caption (usual) or below
    info["area_above"], info["area_below"] = round(a_area), round(b_area)
    if not pool:
        return None, dict(info, reason="no-content-on-either-side")

    clusters = _merge_close(pool, MERGE_GAP)
    # the figure is the cluster that is both big and near the caption
    def score(c):
        gap = (cap_rect.y0 - c.y1) if side == "above" else (c.y0 - cap_rect.y1)
        return c.get_area() / (1.0 + max(0.0, gap))
    best = max(clusters, key=score)
    info["n_clusters"] = len(clusters)
    info["cluster_gap_to_caption_pt"] = round(
        (cap_rect.y0 - best.y1) if side == "above" else (best.y0 - cap_rect.y1), 1)

    # Grow to swallow figure furniture: SHORT text runs touching or inside the cluster.
    # Prose blocks are excluded by length so a body paragraph cannot pull the box open.
    tblocks = [(_rect(b), (b[4] or "").strip()) for b in page.get_text("blocks") if b[6] == 0]
    grown, swallowed = True, 0
    while grown:
        grown = False
        for r, txt in tblocks:
            if len(txt) > PROSE_CHARS:
                continue
            if r & cap_rect:            # never absorb the caption itself
                continue
            if side == "above" and r.y1 > cap_rect.y0 + 2:
                continue
            if side == "below" and r.y0 < cap_rect.y1 - 2:
                continue
            if best.contains(r):
                continue
            if fitz.Rect(r) + (-TEXT_GROW_GAP, -TEXT_GROW_GAP, TEXT_GROW_GAP, TEXT_GROW_GAP) & best:
                best |= r
                swallowed += 1
                grown = True
    info["text_runs_swallowed"] = swallowed
    out = fitz.Rect(best) + (-PAD, -PAD, PAD, PAD)
    out &= page.rect
    return out, info


def bbox_capband(page, cap_rect):
    """Column-width band from the caption up to the prose block above the figure."""
    blocks = [(_rect(b), (b[4] or "").strip()) for b in page.get_text("blocks") if b[6] == 0]
    prims, _ = _content_primitives(page)
    above_prims = [p for p in prims if p.y1 <= cap_rect.y0 + 2]
    top_content = min((p.y0 for p in above_prims), default=cap_rect.y0 - 1)
    # the last prose block that ends above the topmost figure content sets the ceiling
    ceiling = page.rect.y0
    for r, txt in blocks:
        if len(txt) > PROSE_CHARS and r.y1 <= top_content + 2:
            ceiling = max(ceiling, r.y1)
    x0 = min([cap_rect.x0] + [p.x0 for p in above_prims] or [cap_rect.x0])
    x1 = max([cap_rect.x1] + [p.x1 for p in above_prims] or [cap_rect.x1])
    out = fitz.Rect(x0 - PAD, ceiling + 2, x1 + PAD, cap_rect.y0 - 1) & page.rect
    if out.is_empty or out.height < 20:
        return None, {"reason": "capband-degenerate"}
    return out, {"ceiling_pt": round(ceiling, 1), "top_content_pt": round(top_content, 1)}


def bbox_xobject(page, cap_rect):
    """The single dominant image XObject placement on the caption's side.

    For a figure shipped as one flattened bitmap -- the majority case in this corpus --
    the PDF's own image placement rectangle IS the figure box, read out of the content
    stream rather than inferred. That makes this the only policy here whose box is not a
    heuristic. It is unavailable whenever the figure is vector-drawn or split across
    several images, and it says nothing about panels inside the bitmap.
    """
    prims, imgs = _content_primitives(page)
    parea = page.rect.get_area()
    side_imgs = [r for r in imgs if r.get_area() >= 0.05 * parea]
    above = [r for r in side_imgs if r.y1 <= cap_rect.y0 + 2]
    below = [r for r in side_imgs if r.y0 >= cap_rect.y1 - 2]
    pool = above if sum(r.get_area() for r in above) >= sum(r.get_area() for r in below) else below
    if len(pool) != 1:
        return None, {"reason": f"not-exactly-one-dominant-image ({len(pool)})",
                      "n_dominant_images": len(pool)}
    return fitz.Rect(pool[0]), {"n_dominant_images": 1,
                                "gap_to_caption_pt": round(abs(cap_rect.y0 - pool[0].y1), 1)}


def _text_lines(page):
    out = []
    d = page.get_text("dict")
    for blk in d.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            txt = "".join(sp.get("text", "") for sp in ln.get("spans", []))
            if txt.strip():
                out.append((fitz.Rect(ln["bbox"]), txt.strip()))
    return out


def contamination(rect, page, cap_rect, figure_number):
    """How much of this box is NOT the figure. Two crisp signals plus one soft one.

    `foreign_caption` is the strong one: if the box contains the caption LABEL of a
    DIFFERENT figure, the box provably spans more than one figure, and every panel count
    taken from it is a count over two figures. No judgement call is involved.

    `prose_lines` counts running-text lines: >=9 words AND spanning >=55% of the box
    width. Axis labels, tick numbers, legends and panel letters are short or narrow, so
    they do not qualify; a body paragraph does. It is a heuristic and is reported as a
    count, not as a verdict.
    """
    out = {"foreign_caption": [], "n_prose_lines": 0, "prose_word_frac": 0.0}
    if rect is None:
        return out
    lines = _text_lines(page)
    figpat = re.compile(r"^\W{0,4}(figure|fig\.?)\s*0*(\d+)", re.I)
    fw = tw = 0
    for r, txt in lines:
        if (r & rect).get_area() < 0.5 * max(1.0, r.get_area()):
            continue
        if cap_rect is not None and (r & cap_rect).get_area() > 0.5 * r.get_area():
            continue                                    # this figure's own caption
        m = figpat.match(txt)
        if m and int(m.group(2)) != figure_number:
            out["foreign_caption"].append(txt[:50])
        nw = len(txt.split())
        tw += nw
        if nw >= 9 and r.width >= 0.55 * rect.width:
            out["n_prose_lines"] += 1
            fw += nw
    out["prose_word_frac"] = round(fw / tw, 3) if tw else 0.0
    out["n_words_in_box"] = tw
    return out


def sanity(rect, page, cap_rect, figure_number=None):
    """Cheap red flags on a candidate box. These are DEFECT DETECTORS, not a validity
    proof: an empty flag list says only that no defect was DETECTED, never that the box
    is on the right figure or that it did not clip a panel off the edge."""
    f = []
    if rect is None:
        return ["no-box"]
    parea = page.rect.get_area()
    if rect.get_area() > 0.85 * parea:
        f.append("box-covers-page")
    if rect.get_area() < 0.02 * parea:
        f.append("box-tiny")
    if cap_rect is not None and (rect & cap_rect).get_area() > 0.25 * cap_rect.get_area():
        f.append("box-overlaps-caption")
    if rect.width < 40 or rect.height < 40:
        f.append("box-degenerate")
    if figure_number is not None and cap_rect is not None:
        c = contamination(rect, page, cap_rect, figure_number)
        if c["foreign_caption"]:
            f.append("contains-other-figure-caption")
        if c["n_prose_lines"] >= 3:
            f.append(f"contains-{c['n_prose_lines']}-prose-lines")
    return f


def boxes_for(pdf_path, page0, figure_number, dpi, caption_text=""):
    """All three policies for one worklist item, in rendered-PNG pixels at `dpi`."""
    doc = fitz.open(pdf_path)
    page = doc[page0]
    scale = dpi / 72.0
    cap, how = find_caption_rect(page, figure_number, caption_text)
    res = {"caption_found": cap is not None, "caption_how": how,
           "page_rect_pt": [round(v, 1) for v in page.rect],
           "page_px": [round(page.rect.width * scale), round(page.rect.height * scale)],
           "policies": {}}
    if cap is not None:
        res["caption_rect_pt"] = [round(v, 1) for v in cap]

    def px(r):
        return None if r is None else {
            "x": round(r.x0 * scale), "y": round(r.y0 * scale),
            "width": round(r.width * scale), "height": round(r.height * scale)}

    full = fitz.Rect(page.rect)
    res["policies"]["fullpage"] = {"bbox_px": px(full), "bbox_pt": [round(v, 1) for v in full],
                                   "info": {}, "flags": ["by-construction-not-a-figure-box"]}
    res["policies"]["fullpage"]["contamination"] = contamination(
        full, page, cap, figure_number) if cap is not None else {}
    for name, fn in (("capband", bbox_capband), ("cluster", bbox_cluster),
                     ("xobject", bbox_xobject)):
        if cap is None:
            res["policies"][name] = {"bbox_px": None, "bbox_pt": None,
                                     "info": {"reason": "no-caption"}, "flags": ["no-box"],
                                     "contamination": {}}
            continue
        try:
            r, info = fn(page, cap)
        except Exception as e:
            r, info = None, {"reason": f"exception: {e}"}
        res["policies"][name] = {"bbox_px": px(r),
                                 "bbox_pt": None if r is None else [round(v, 1) for v in r],
                                 "info": info, "flags": sanity(r, page, cap, figure_number),
                                 "contamination": contamination(r, page, cap, figure_number)}
    # Image XObject placements in rendered px -- the faithful equivalent of the tool's
    # `article.imageRects`, which pdf.js builds by walking the operator list and applying
    # the CTM to each paintImageXObject, keeping placements >= 4px on a side. PyMuPDF's
    # get_image_rects reads the same placements out of the same content stream, so the
    # XObject fast path in detectPanelsCore sees what it would see on a real load.
    allrects = []
    for im in page.get_images(full=True):
        try:
            allrects += list(page.get_image_rects(im[0]))
        except Exception:
            pass
    res["image_rects_px"] = [{"x": round(r.x0 * scale), "y": round(r.y0 * scale),
                              "width": round(r.width * scale), "height": round(r.height * scale)}
                             for r in allrects
                             if r.width * scale >= 4 and r.height * scale >= 4]
    doc.close()
    return res
