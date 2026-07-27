#!/usr/bin/env python3
"""prepare_session.py -- build blinded annotation sessions for the human real-figure pass.

The human annotates INSIDE figure-extractor.html, so his clicks go through the same
`computeCalibration` affine the agent's do and his export has the same schema. This
script produces the materials that make that pass a controlled measurement rather than
an afternoon of clicking:

  plan     assign worklist items to sessions, pick the intra-rater repeat subset, mint
           fresh anonymous ids, and write the sealed key (kept OUTSIDE the session tree)
  build    Stage A materials: one page PNG per item at a fixed DPI, in the folder layout
           figure-extractor's "Select Project Folder" expects
  build-b  Stage B materials: re-crop the panels the human drew in Stage A at a working
           magnification, seed a whole-image figure box, and emit a pre-structured
           semantic coding form with one entry per panel he actually found
  timer    per-item stopwatch (fatigue is a real confound in click-precision work)
  status   what is planned / built / annotated / ingested

Blinding is structural, not a promise:
  * session materials contain no machine output of any kind, and the anon->real key
    lives in `keys/` which the human never opens;
  * a repeat item is reissued under a NEW anon id in a LATER session, interleaved with
    fresh items, so it cannot be recognised as a repeat;
  * `build` refuses to prepare a session until every prerequisite session has been
    ingested and sealed, and refuses a repeat until the required calendar gap elapsed;
  * `ingest_annotations.py` hard-rejects any export bearing the detector's fingerprints.

Run `python3 prepare_session.py --selftest` to exercise everything with synthetic data.
"""
import argparse
import json
import math
import pathlib
import random
import shutil
import sys
from datetime import datetime, timezone

import rvcommon as rv

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# ---- fixed measurement constants (change these and you have a different instrument) ----
DPI_A = 200               # Stage A page render. Structure only; 1 px on a 400 px box = 0.25%.
PANEL_LONG_EDGE_PX = 2200  # Stage B target: re-render the panel this big on its long edge.
DPI_B_MIN, DPI_B_MAX = 300, 1200
RULER_STRIP_H = 46        # zoom-check strip appended under every Stage B panel crop
ITEMS_PER_SESSION = 20
REPEAT_FRACTION = 0.18
REPEAT_MIN = 3
REPEAT_MIN_SESSION_GAP = 1   # a repeat never lands in the session after its original
REPEAT_MIN_DAYS = 3          # ... nor within 3 days of it
SESSION_MIN_HOURS = 12       # minimum rest between any two sessions
SEED = 20260727              # project convention: the date as an int


# =============================================================== worklist ingestion

def load_worklist(explicit=None):
    """Consume `worklist.json` if a parallel agent has written it; otherwise derive a
    fallback from benchmark/real/population.json and write it as `worklist.derived.json`
    (this script never writes `worklist.json` -- that file has another owner).

    Schema consumed (tolerant on field names; only `article` is truly required):
      {"schemaVersion":1, "seed":int, "items":[{
         "item_id"|"id":   str    unique key, e.g. "Bonaccorsi2013_fig1b"
         "article":        str    key into benchmark/real/pdf_map.json
         "doi":            str    optional
         "pdf"|"pdf_path": str    optional; else resolved from pdf_map.json
         "page":           int    1-based page holding the figure; else located by caption
         "figure":         str    human-facing target, e.g. "Figure 1"
         "row_ids":        [str]  population.json rows this figure supplies
         "difficulty":     str|num  easy|medium|hard, or a number; else derived
         "stratum":        str    optional explicit stratum; else difficulty
         "caption":        str    optional pre-extracted caption
      }]}
    """
    p = pathlib.Path(explicit) if explicit else (rv.HERE / "worklist.json")
    if p.exists():
        wl = rv.read_json(p)
        items = wl.get("items") or wl.get("worklist") or []
        print(f"[worklist] {p} -- {len(items)} items")
        return _normalise_items(items), str(p)

    pop = rv.read_json(rv.REAL / "population.json", [])
    if not pop:
        raise SystemExit(f"no {p} and no benchmark/real/population.json to derive from")
    byfig = {}
    for r in pop:
        if not r.get("complete"):
            continue
        src = (r.get("data_source") or "")
        if not src.lower().startswith("fig"):
            continue                      # tables are not a figure-reading task
        key = f"{r['article']}_{rv.slug(r.get('panel') or src).lower()}"
        it = byfig.setdefault(key, {"item_id": key, "article": r["article"],
                                    "doi": r.get("doi"), "figure": src,
                                    "row_ids": [], "difficulty": "medium"})
        it["row_ids"].append(r["row_id"])
    items = _normalise_items(list(byfig.values()))
    rv.write_json(rv.DATA / "worklist.derived.json",
                  {"schemaVersion": 1, "derivedFrom": "benchmark/real/population.json",
                   "note": "fallback only -- worklist.json (owned elsewhere) takes precedence",
                   "generatedAt": rv.now_iso(), "items": items})
    print(f"[worklist] derived {len(items)} items from population.json "
          f"(no worklist.json present)")
    return items, "worklist.derived.json"


def _normalise_items(items):
    out = []
    pdf_map = rv.read_json(rv.REAL / "pdf_map.json", {}) or {}
    for raw in items:
        it = dict(raw)
        it["item_id"] = it.get("item_id") or it.get("id")
        if not it["item_id"]:
            raise SystemExit(f"worklist item without item_id/id: {raw}")
        it["pdf"] = it.get("pdf") or it.get("pdf_path") or \
            (pdf_map.get(it.get("article"), {}) or {}).get("pdf")
        if it.get("page0") is not None and it.get("page") is None:
            it["page"] = int(it["page0"]) + 1
        it["figure"] = it.get("figure") or it.get("panel") or "the target figure"
        d = it.get("difficulty")
        if isinstance(d, (int, float)):
            d = "easy" if d < 1.5 else ("medium" if d < 2.5 else "hard")
        it["difficulty"] = d or "medium"
        it["stratum"] = it.get("stratum") or it["difficulty"]
        it["row_ids"] = it.get("row_ids") or []
        out.append(it)
    seen = set()
    for it in out:
        if it["item_id"] in seen:
            raise SystemExit(f"duplicate item_id in worklist: {it['item_id']}")
        seen.add(it["item_id"])
    return out


# ==================================================================== plan

def cmd_plan(args):
    items, src = load_worklist(args.worklist)
    if not items:
        raise SystemExit("worklist is empty")
    rng = random.Random(args.seed)

    # Repeat subset FIRST, stratified, so the re-read sample is representative of the
    # difficulty mix rather than of whatever happened to be quick.
    k = max(REPEAT_MIN, int(round(REPEAT_FRACTION * len(items))))
    k = min(k, len(items))
    by_stratum = {}
    for it in items:
        by_stratum.setdefault(it["stratum"], []).append(it)
    repeats = []
    for s in sorted(by_stratum):
        b = list(by_stratum[s])
        rng.shuffle(b)
        take = max(1, int(round(k * len(b) / len(items))))
        repeats += b[:take]
    repeats = repeats[:k]
    repeat_ids = {it["item_id"] for it in repeats}

    ordered = rv.interleave_by_stratum(items, lambda i: i["stratum"], args.seed)
    per = args.per_session
    n_first = math.ceil(len(ordered) / per)

    used_anon, sessions = set(), []
    for si in range(n_first):
        chunk = ordered[si * per:(si + 1) * per]
        sessions.append({"session": f"S{si + 1:02d}", "pass": "A+B", "entries": chunk})

    # Repeats go into trailing sessions, at least REPEAT_MIN_SESSION_GAP sessions after
    # their original, interleaved with each other so no session is "the repeat session".
    origin_session = {}
    for s in sessions:
        for it in s["entries"]:
            origin_session[it["item_id"]] = int(s["session"][1:])
    rep_order = rv.interleave_by_stratum(repeats, lambda i: i["stratum"], args.seed + 1)
    slots = {}                                     # session index -> [items]
    for it in rep_order:
        earliest = origin_session[it["item_id"]] + REPEAT_MIN_SESSION_GAP + 1
        n = max(earliest, n_first + 1)
        while len(slots.setdefault(n, [])) >= per:
            n += 1
        slots[n].append(it)
    rep_sessions = [{"session": f"S{n:02d}", "pass": "A+B", "entries": slots[n]}
                    for n in sorted(slots)]
    sessions += rep_sessions

    plan, key = [], []
    for s in sessions:
        sn = s["session"]
        pub, priv = [], []
        for pos, it in enumerate(s["entries"], 1):
            aid = rv.anon_id(rng, pos, used_anon)
            is_rep = sn in {x["session"] for x in rep_sessions}
            pub.append({"anon_id": aid, "position": pos,
                        "figure": it["figure"],
                        "expectPanels": None})          # deliberately unknown to the rater
            priv.append({"anon_id": aid, "position": pos, "item_id": it["item_id"],
                         "article": it.get("article"), "doi": it.get("doi"),
                         "pdf": it.get("pdf"), "page": it.get("page"),
                         "figure": it["figure"], "row_ids": it["row_ids"],
                         "stratum": it["stratum"], "difficulty": it["difficulty"],
                         "isRepeat": is_rep, "repeatOf": it["item_id"] if is_rep else None})
        plan.append({"session": sn, "nItems": len(pub), "items": pub})
        key.append({"session": sn, "isRepeatSession": sn in {x["session"] for x in rep_sessions},
                    "items": priv})

    rv.write_json(rv.DATA / "plan.json", {
        "schemaVersion": rv.RV_SCHEMA_VERSION, "generatedAt": rv.now_iso(),
        "worklistSource": src, "seed": args.seed, "perSession": per,
        "repeatFraction": REPEAT_FRACTION, "nItems": len(items), "nRepeats": len(repeats),
        "dpiA": DPI_A, "panelLongEdgePx": PANEL_LONG_EDGE_PX,
        "sessions": plan})
    rv.write_json(rv.KEYS / "plan.key.json", {
        "schemaVersion": rv.RV_SCHEMA_VERSION, "generatedAt": rv.now_iso(),
        "WARNING": "SEALED KEY -- the rater must never open this file.",
        "seed": args.seed, "repeatIds": sorted(repeat_ids), "sessions": key})
    print(f"\n{len(items)} items -> {len(sessions)} sessions "
          f"({n_first} first-pass + {len(rep_sessions)} carrying {len(repeats)} repeats)")
    print("Next: python3 prepare_session.py build S01")


# ============================================================== Stage A build

def _key_for(session):
    kp = rv.KEYS / "plan.key.json"
    k = rv.read_json(kp)
    if not k:
        raise SystemExit(f"no {kp} -- run `prepare_session.py plan` first")
    for s in k["sessions"]:
        if s["session"] == session:
            return k, s
    raise SystemExit(f"session {session} not in the plan")


def _sealed(session):
    return rv.read_json(rv.GT / session / "seal.json")


def _gate_prerequisites(session, force=False):
    """Just-in-time build: a session cannot be prepared until the previous one is
    ingested+sealed, and a repeat cannot be prepared until its original is old enough.
    This is what turns "annotate the repeats later, blind" from an instruction into a
    property of the harness."""
    plan = rv.read_json(rv.DATA / "plan.json")
    names = [s["session"] for s in plan["sessions"]]
    i = names.index(session)
    problems = []
    for prev in names[:i]:
        sl = _sealed(prev)
        if not sl:
            problems.append(f"{prev} is not ingested/sealed yet "
                            f"(run: python3 ingest_annotations.py ingest {prev})")
            continue
        t = datetime.strptime(sl["sealedAt"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - t).total_seconds() / 3600
        if prev == names[i - 1] and age_h < SESSION_MIN_HOURS:
            problems.append(f"{prev} was sealed {age_h:.1f} h ago; "
                            f"rest {SESSION_MIN_HOURS} h between sessions")
    _, ks = _key_for(session)
    if ks["isRepeatSession"]:
        key = rv.read_json(rv.KEYS / "plan.key.json")
        origin = {}
        for s in key["sessions"]:
            for it in s["items"]:
                if not it["isRepeat"]:
                    origin[it["item_id"]] = s["session"]
        for it in ks["items"]:
            o = origin.get(it["item_id"])
            sl = _sealed(o) if o else None
            if not sl:
                problems.append(f"repeat {it['anon_id']}: original session {o} not sealed")
                continue
            t = datetime.strptime(sl["sealedAt"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - t).total_seconds() / 86400
            if days < REPEAT_MIN_DAYS:
                problems.append(f"repeat {it['anon_id']}: original read {days:.1f} d ago; "
                                f"wait {REPEAT_MIN_DAYS} d so the re-read is blind to memory")
    if problems and not force:
        print("\n".join("  ! " + p for p in problems), file=sys.stderr)
        raise SystemExit("prerequisites not met (use --force only to rebuild materials)")
    return problems


def _render_page(pdf, page1, dpi, out_png):
    if fitz is None:
        raise SystemExit("PyMuPDF (fitz) is required: pip install pymupdf")
    doc = fitz.open(pdf)
    pg = doc[page1 - 1]
    scale = dpi / 72.0
    pix = pg.get_pixmap(matrix=fitz.Matrix(scale, scale))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out_png))
    items = []
    for x0, y0, x1, y1, word, *_ in pg.get_text("words"):
        if word.strip():
            items.append({"str": word + " ", "x": round(x0 * scale, 1), "y": round(y0 * scale, 1),
                          "w": round((x1 - x0) * scale, 1), "h": round((y1 - y0) * scale, 1)})
    text = pg.get_text()
    doc.close()
    return pix.width, pix.height, items, text


def _locate_page(pdf, figure_label):
    """Find the 1-based page whose text mentions the target figure caption."""
    import re
    m = re.search(r"(\d+)", figure_label or "")
    if fitz is None or not m:
        return 1
    n = m.group(1)
    doc = fitz.open(pdf)
    best = 1
    for i in range(doc.page_count):
        t = doc[i].get_text()
        if re.search(rf"fig(?:ure|\.)?\s*{n}\b", t, re.I):
            best = i + 1
            break
    doc.close()
    return best


def cmd_build(args):
    _gate_prerequisites(args.session, args.force)
    _, ks = _key_for(args.session)
    sdir = rv.SESSIONS / args.session
    proj = sdir / "projectA"
    if proj.exists() and args.force:
        shutil.rmtree(proj)
    manifest = []
    for it in ks["items"]:
        aid = it["anon_id"]
        pdf = it.get("pdf")
        if not pdf or not pathlib.Path(pdf).exists():
            print(f"  ! {aid}: no PDF ({pdf}) -- skipped", file=sys.stderr)
            continue
        page = it.get("page") or _locate_page(pdf, it["figure"])
        d = proj / aid
        w, h, words, text = _render_page(pdf, page, DPI_A, d / "0001.png")
        rv.write_json(d / "text.json", {"schemaVersion": 1, "source": aid, "dpi": DPI_A,
                                        "ocrPages": 0,
                                        "pages": [{"pageNum": 1, "width": w, "height": h,
                                                   "items": words, "ocr": False}]}, indent=None)
        rv.write_json(d / "metadata.json", {"source": aid, "pages": 1, "dpi": DPI_A,
                                            "width": w, "height": h})
        (d / "TARGET.txt").write_text(
            f"Item {aid}  (position {it['position']} of {len(ks['items'])})\n"
            f"Annotate: {it['figure']}\n"
            f"Page render: {w} x {h} px at {DPI_A} dpi\n", encoding="utf-8")
        manifest.append({"anon_id": aid, "position": it["position"], "figure": it["figure"],
                         "pageW": w, "pageH": h, "dpi": DPI_A})
    rv.write_json(sdir / "session.json", {
        "schemaVersion": rv.RV_SCHEMA_VERSION, "session": args.session, "stage": "A",
        "builtAt": rv.now_iso(), "dpi": DPI_A, "nItems": len(manifest), "items": manifest})
    for sub in ("exports/passA", "exports/passB", "coding", "timing"):
        (sdir / sub).mkdir(parents=True, exist_ok=True)
    _worksheet_a(sdir, args.session, manifest)
    print(f"\nStage A ready. Open in Windows:\n  {rv.windows_path(proj)}")
    print(f"Worksheet:\n  {rv.windows_path(sdir / 'A-WORKSHEET.md')}")


def _worksheet_a(sdir, session, manifest):
    L = [f"# {session} -- Stage A worksheet (structure pass)", "",
         f"Built {rv.now_iso()}. {len(manifest)} items, page renders at {DPI_A} dpi.", "",
         "Full instructions: `benchmark/real-validation/PROTOCOL.md`. Short version:",
         "",
         "1. Start the stopwatch:  `python3 prepare_session.py timer " + session + " A`",
         "2. In figure-extractor.html (opened as a **file://** page), press",
         "   **Select Project Folder** and choose `projectA`.",
         "3. Work the items **in the order below**. For each one: draw the figure box,",
         "   then draw one subfigure box per panel and rename each to its caption letter.",
         "4. **Never press the `Auto-panels` button.** The ingest will reject the session.",
         "5. Break for 15 minutes after item 10; stop after item 20 whatever happens.",
         "6. Press **Export All Articles**, unzip into `exports/passA/`, then run",
         f"   `python3 prepare_session.py build-b {session}`.",
         "", "| # | item | annotate | page px |", "|---|---|---|---|"]
    for m in manifest:
        L.append(f"| {m['position']} | `{m['anon_id']}` | {m['figure']} | "
                 f"{m['pageW']}x{m['pageH']} |")
    L += ["", "Tick each item off here as you finish it; the timer log is the record that counts."]
    (sdir / "A-WORKSHEET.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[written] {sdir / 'A-WORKSHEET.md'}")


# ============================================================== Stage B build

def _ruler_strip(width, dpi_b):
    """A zoom self-check burned into the crop.

    The left patch is a 1-px-on / 1-px-off line pair grating. Below 1:1 display
    magnification it aliases to flat grey; at or above 1:1 it resolves into separate
    black and white lines. That gives an unambiguous, physically grounded "am I zoomed
    in far enough" test with no tool change and no guesswork -- and because >=1:1 means
    one screen pixel is at most one image pixel, the image-pixel distances in the export
    become a valid LOWER BOUND on the screen-pixel distances the rater actually saw,
    which is what `ingest_annotations.py audit` checks.
    """
    from PIL import Image, ImageDraw
    strip = Image.new("RGB", (width, RULER_STRIP_H), "white")
    d = ImageDraw.Draw(strip)
    for x in range(10, min(210, width - 10), 2):
        d.line([(x, 6), (x, 28)], fill="black", width=1)
    d.text((10, 30), "1:1 check - must show separate lines", fill="black")
    x0 = 260
    if width > x0 + 140:
        d.rectangle([x0, 10, x0 + 100, 22], fill="black")
        d.text((x0, 26), f"100 image px @ {dpi_b} dpi", fill="black")
    d.line([(0, 0), (width, 0)], fill="black", width=1)
    return strip


def _panel_boxes(annotations):
    """Figure box + subfigure boxes (converted to page coordinates) from a Stage A export."""
    out = []
    for f in annotations.get("figures", []):
        fb = f.get("bounds") or {}
        subs = f.get("subfigures") or []
        if not subs:
            out.append({"label": f.get("label") or "figure", "letter": "",
                        "page": f.get("pageNum") or 1, "bounds": fb, "figureLabel": f.get("label")})
            continue
        for s in subs:
            b = s.get("bounds") or {}
            out.append({"label": s.get("label") or "", "letter": (s.get("label") or "")[-1:],
                        "page": f.get("pageNum") or 1,
                        "bounds": {"x": fb.get("x", 0) + b.get("x", 0),
                                   "y": fb.get("y", 0) + b.get("y", 0),
                                   "width": b.get("width", 0), "height": b.get("height", 0)},
                        "figureLabel": f.get("label")})
    return out


def _blank_form(panel_item, letter, vocab):
    return {
        "_README": [
            "Fill every null. Leave a value null ONLY if you are abstaining, and then add",
            "an entry to `ambiguities` saying which field and why. An abstention is data.",
            "`marks` is the LEFT-TO-RIGHT roster of the marks you will click in the tool;",
            "its order must match your click order exactly (forest plots: top to bottom).",
        ],
        "_allowed": {k: vocab[k] for k in ("charType", "scale", "role", "dispersion",
                                           "seriesEncoding", "labelSource", "dataProvenance",
                                           "nonDataElement", "flags")},
        "panel_item": panel_item,
        "panelLetter": letter,
        "charType": None,
        "extractable": None,
        "dataProvenance": None,
        "axes": {"x": {"scale": None, "unit": ""}, "y": {"scale": None, "unit": ""}},
        "dispersion": {"present": None, "type": None, "evidence": ""},
        "series": [
            {"id": "s1", "label": "", "role": None, "encoding": None, "labelSource": None,
             "n": None, "nSource": "", "evidence": ""},
            {"id": "s2", "label": "", "role": None, "encoding": None, "labelSource": None,
             "n": None, "nSource": "", "evidence": ""},
        ],
        "marks": [{"group": "", "seriesId": "s1"}, {"group": "", "seriesId": "s2"}],
        "direction": None,
        "timepoint": "",
        "nonDataElements": [],
        "flags": [],
        "ambiguities": [],
        "notes": "",
    }


def cmd_build_b(args):
    _, ks = _key_for(args.session)
    sdir = rv.SESSIONS / args.session
    exp = sdir / "exports" / "passA"
    if not exp.exists():
        raise SystemExit(f"unzip the Stage A export into {rv.windows_path(exp)} first")
    vocab = rv.load_vocab()
    projb = sdir / "projectB"
    if projb.exists() and args.force:
        shutil.rmtree(projb)
    bykey = {it["anon_id"]: it for it in ks["items"]}
    from PIL import Image

    entries, refused = [], []
    for aid, it in bykey.items():
        ann = rv.read_json(exp / aid / "annotations.json")
        if ann is None:
            print(f"  . {aid}: no Stage A export -- skipped", file=sys.stderr)
            continue
        bad = rv.blinding_violations(ann)
        if bad:
            refused += [f"{aid}: {b}" for b in bad]
            continue
        for pb in _panel_boxes(ann):
            b = pb["bounds"]
            if not b or b.get("width", 0) < 20 or b.get("height", 0) < 20:
                continue
            letter = (pb["letter"] or "x").upper()
            pid = f"{aid}_p{rv.slug(letter) or 'x'}"
            # page px @ DPI_A -> PDF points -> a DPI that makes the long edge ~2200 px
            long_pt = max(b["width"], b["height"]) * 72.0 / DPI_A
            dpi_b = int(min(DPI_B_MAX, max(DPI_B_MIN, round(PANEL_LONG_EDGE_PX * 72.0 / long_pt))))
            page = pb["page"]
            tmp = projb / pid / "_page.png"
            w, h, _, _ = _render_page(it["pdf"], page, dpi_b, tmp)
            k = dpi_b / DPI_A
            box = (max(0, int(b["x"] * k)), max(0, int(b["y"] * k)),
                   min(w, int((b["x"] + b["width"]) * k)), min(h, int((b["y"] + b["height"]) * k)))
            im = Image.open(tmp).convert("RGB").crop(box)
            canvas = Image.new("RGB", (im.width, im.height + RULER_STRIP_H), "white")
            canvas.paste(im, (0, 0))
            canvas.paste(_ruler_strip(im.width, dpi_b), (0, im.height))
            (projb / pid).mkdir(parents=True, exist_ok=True)
            canvas.save(projb / pid / "0001.png")
            tmp.unlink()
            # Seed a figure box over the panel content (NOT the ruler strip) so the rater
            # opens the digitizer in one click. This is derived from HIS OWN Stage A boxes,
            # so it leaks nothing from the detector.
            rv.write_json(projb / pid / "annotations.json", {
                "schemaVersion": rv.SCHEMA_VERSION, "project": args.session, "article": pid,
                # STALE-WORK GUARD (amendment A12). localStorage is keyed by article name
                # and a rebuild reuses the name, so without this the browser serves the
                # PREVIOUS build's boxes over this file and says nothing. The tool honours
                # the flag by discarding its cache for this item and telling the rater.
                "forceCleanLoad": True,
                "exportedAt": rv.now_iso(),
                "pages": [{"pageNum": 1, "width": canvas.width, "height": canvas.height}],
                "figures": [{"id": "fig1", "label": pid, "pageNum": 1,
                             "bounds": {"x": 0, "y": 0, "width": im.width, "height": im.height},
                             "caption": "", "captionSource": "", "notes": "",
                             "createdAt": rv.now_iso(), "subfigures": []}]})
            rv.write_json(projb / pid / "metadata.json",
                          {"source": pid, "pages": 1, "dpi": dpi_b,
                           "width": canvas.width, "height": canvas.height})
            form = sdir / "coding" / f"{pid}.form.json"
            if not form.exists() or args.force:
                rv.write_json(form, _blank_form(pid, letter, vocab))
            entries.append({"panel_item": pid, "anon_id": aid, "panelLetter": letter,
                            "sourcePanelLabel": pb["label"], "dpi": dpi_b,
                            "panelPx": [im.width, im.height],
                            "magnificationVsStageA": round(k, 3)})
    if refused:
        print("\nREFUSED (detector fingerprints in the Stage A export):", file=sys.stderr)
        print("\n".join("  ! " + r for r in refused), file=sys.stderr)
        raise SystemExit("blinding violated -- re-annotate those items by hand")

    order = rv.interleave_by_stratum(entries, lambda e: e["panelLetter"], SEED + 7)
    for i, e in enumerate(order, 1):
        e["position"] = i
    rv.write_json(sdir / "sessionB.json", {
        "schemaVersion": rv.RV_SCHEMA_VERSION, "session": args.session, "stage": "B",
        "builtAt": rv.now_iso(), "panelLongEdgePx": PANEL_LONG_EDGE_PX,
        "nItems": len(order), "items": order})
    _worksheet_b(sdir, args.session, order)
    print(f"\nStage B ready ({len(order)} panels). Open in Windows:\n  {rv.windows_path(projb)}")


def _worksheet_b(sdir, session, entries):
    L = [f"# {session} -- Stage B worksheet (semantics + landmarks)", "",
         f"Built {rv.now_iso()}. {len(entries)} panels, each re-rendered so its long edge is",
         f"~{PANEL_LONG_EDGE_PX} px -- the 2-3x re-crop that removes the measured 22-36%",
         "dispersion error on real figures.", "",
         "For each panel, **in this order**:",
         "",
         "1. Fill `coding/<panel_item>.form.json` -- chart type, series->arm with the legend",
         "   text, dispersion type + n with the quoted caption/methods evidence. Semantics",
         "   BEFORE pixels: deciding what a bar means after you have measured it is anchoring.",
         "2. Open the panel in the tool, click **Digitize**, set the 4 axis references,",
         "   then pick the landmarks using the series-name convention in PROTOCOL.md §7.",
         "3. Before any landmark click, zoom until the striped patch at the bottom of the",
         "   image shows **separate black and white lines**, not grey. That is 1:1.",
         "", "| # | panel item | letter | dpi | panel px |", "|---|---|---|---|---|"]
    for e in entries:
        L.append(f"| {e['position']} | `{e['panel_item']}` | {e['panelLetter']} | "
                 f"{e['dpi']} | {e['panelPx'][0]}x{e['panelPx'][1]} |")
    L += ["", "Then: **Export All Articles**, unzip into `exports/passB/`, and run",
          f"`python3 ingest_annotations.py ingest {session}`."]
    (sdir / "B-WORKSHEET.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[written] {sdir / 'B-WORKSHEET.md'}")


# ==================================================================== timer

def cmd_timer(args):
    sdir = rv.SESSIONS / args.session
    manifest = rv.read_json(sdir / ("sessionB.json" if args.stage == "B" else "session.json"))
    if not manifest:
        raise SystemExit(f"build stage {args.stage} for {args.session} first")
    key = "panel_item" if args.stage == "B" else "anon_id"
    log = sdir / "timing" / f"pass{args.stage}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["item"] for l in log.read_text().splitlines() if l.strip()} \
        if log.exists() else set()
    todo = [i for i in manifest["items"] if i[key] not in done]
    print(f"{args.session} stage {args.stage}: {len(todo)} of {manifest['nItems']} left.")
    print("ENTER starts an item, ENTER again ends it. 'b' logs a break, 'q' quits.\n")
    for it in todo:
        name = it[key]
        cmd = input(f"[{it['position']}/{manifest['nItems']}] {name}  START> ").strip().lower()
        if cmd == "q":
            break
        if cmd == "b":
            with open(log, "a") as f:
                f.write(json.dumps({"item": "__break__", "at": rv.now_iso()}) + "\n")
            input("  break logged -- ENTER when back> ")
            cmd = input(f"[{it['position']}/{manifest['nItems']}] {name}  START> ").strip().lower()
            if cmd == "q":
                break
        t0 = datetime.now(timezone.utc)
        note = input("  DONE> ").strip()
        t1 = datetime.now(timezone.utc)
        rec = {"item": name, "stage": args.stage, "position": it["position"],
               "startedAt": t0.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
               "endedAt": t1.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
               "seconds": round((t1 - t0).total_seconds(), 1), "note": note}
        with open(log, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"  {rec['seconds']:.0f}s logged\n")
        if it["position"] % 10 == 0 and it is not todo[-1]:
            print("  --- scheduled 15 minute break: stop clicking now. ---\n")
    print(f"[written] {log}")


# ==================================================================== status

def cmd_status(args):
    plan = rv.read_json(rv.DATA / "plan.json")
    if not plan:
        print("no plan.json -- run `prepare_session.py plan`")
        return
    print(f"{plan['nItems']} items, {plan['nRepeats']} repeats, "
          f"{len(plan['sessions'])} sessions, seed {plan['seed']}\n")
    print(f"{'session':<9}{'items':>6}  {'A built':<8}{'A export':<9}"
          f"{'B built':<8}{'B export':<9}{'sealed':<8}")
    for s in plan["sessions"]:
        d = rv.SESSIONS / s["session"]
        y = lambda b: "yes" if b else "-"
        print(f"{s['session']:<9}{s['nItems']:>6}  "
              f"{y((d / 'session.json').exists()):<8}"
              f"{y(any((d / 'exports/passA').glob('*/annotations.json')) if (d / 'exports/passA').exists() else False):<9}"
              f"{y((d / 'sessionB.json').exists()):<8}"
              f"{y(any((d / 'exports/passB').glob('*/annotations.json')) if (d / 'exports/passB').exists() else False):<9}"
              f"{y(_sealed(s['session'])):<8}")


# ==================================================================== selftest

def cmd_selftest(args):
    import tempfile
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
        ok = ok and cond

    print("prepare_session selftest")
    v = rv.load_vocab()
    check("CHAR_VOCAB parsed live", "bar" in v["charType"] and "SEM" in v["dispersion"])
    check("LANDMARK_HEADER is 29 cols", len(rv.load_landmark_header()) == 29)

    items = [{"item_id": f"a{i}", "article": f"Art{i}", "figure": "Figure 1",
              "difficulty": ["easy", "medium", "hard"][i % 3]} for i in range(24)]
    items = _normalise_items(items)
    o = rv.interleave_by_stratum(items, lambda i: i["stratum"], SEED)
    check("interleave preserves every item", sorted(x["item_id"] for x in o) ==
          sorted(x["item_id"] for x in items))
    pos = {"easy": [], "medium": [], "hard": []}
    for i, x in enumerate(o):
        pos[x["stratum"]].append(i)
    spread = max(abs(sum(p) / len(p) - (len(o) - 1) / 2) for p in pos.values())
    check("difficulty is spread over serial position", spread < len(o) * 0.12,
          f"max mean-position offset {spread:.2f}")

    clean = {"figures": [{"id": "f1", "subfigures": [{"id": "s1", "captionSource": ""}]}]}
    dirty = {"figures": [{"id": "f1", "panelDetection": {"method": "gutter", "confidence": 0.9},
                          "subfigures": [{"id": "s1", "captionSource": "panel-split"}]}]}
    check("blinding check passes a hand pass", rv.blinding_violations(clean) == [])
    check("blinding check catches the detector", len(rv.blinding_violations(dirty)) == 2)

    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "x.json"
        p.write_text('{"a":1}')
        s = rv.seal([p])
        check("seal verifies clean", rv.verify_seal(s, pathlib.Path(td)) == [])
        p.write_text('{"a":2}')
        check("seal detects tampering", len(rv.verify_seal(s, pathlib.Path(td))) == 1)

    strip = _ruler_strip(400, 600)
    px = strip.load()
    row = [px[x, 12] for x in range(10, 30)]
    check("1:1 grating alternates black/white",
          any(c == (0, 0, 0) for c in row) and any(c == (255, 255, 255) for c in row))

    f = _blank_form("it01_abcd_pA", "A", v)
    check("coding form exposes the live vocabulary",
          f["_allowed"]["dispersion"] == v["dispersion"] and f["charType"] is None)

    cal = {"x1": {"px": 100, "py": 400}, "x2": {"px": 500, "py": 400},
           "y1": {"px": 100, "py": 400}, "y2": {"px": 100, "py": 100}}
    vals = {"x1": "0", "x2": "10", "y1": "0", "y2": "300", "logX": False, "logY": False}
    r = rv.to_data(cal, vals, [{"px": 300, "py": 250}])[0]
    check("pixel->data uses the tool's affine", abs(r["x"] - 5) < 1e-9 and abs(r["y"] - 150) < 1e-9)

    print("OK" if ok else "FAILURES")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan", help="assign items to sessions and pick the repeat subset")
    p.add_argument("--worklist"); p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--per-session", type=int, default=ITEMS_PER_SESSION)
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("build", help="Stage A materials for one session")
    p.add_argument("session"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("build-b", help="Stage B panel crops + coding forms from the Stage A export")
    p.add_argument("session"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_build_b)
    p = sub.add_parser("timer", help="per-item stopwatch")
    p.add_argument("session"); p.add_argument("stage", choices=["A", "B"])
    p.set_defaults(fn=cmd_timer)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(cmd_selftest(a))
    if not getattr(a, "fn", None):
        ap.print_help()
        sys.exit(1)
    a.fn(a)


if __name__ == "__main__":
    main()
