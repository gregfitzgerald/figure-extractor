#!/usr/bin/env python3
"""ingest_annotations.py -- turn a human annotation session into a normalized GT store.

Takes the two things the rater produces -- figure-extractor.html exports (geometry +
axis calibration + landmark pixels) and the per-panel semantic coding forms -- and
emits records that are SCHEMA-IDENTICAL to what the tool itself would have written:

  gt/<session>/<panel_item>/annotations.json   schema v2, with `characterization` and
                                               `extraction` built exactly as
                                               runExtraction/EXTRACT build them
  gt/<session>/figure-derived-landmarks.csv    the tool's 29-column LANDMARK_HEADER,
                                               bare header row, quoted cells, CRLF
  gt/<session>/panels_gt.jsonl                 panel boxes in benchmark/panels'
                                               prediction shape, so score.py applies
  gt/human_gt.jsonl                            the analysis-facing normalized store
  gt/<session>/seal.json                       sha256 + UTC timestamp of everything
                                               ingested; the machine pass must run after

Pixels become data through `benchmark/harness/calibrate.py::py_calibrate` -- the same
affine the tool uses -- so a human-vs-machine difference is a difference in PERCEPTION,
never in arithmetic.

Three things it refuses to do:
  * ingest an export bearing the panel detector's fingerprints (blinding violated);
  * accept a coding-form value outside the tool's live CHAR_VOCAB;
  * silently guess when the landmark click order does not match the declared roster.

Subcommands: ingest, audit, intra, verify-seal.  `--selftest` runs an end-to-end
round trip on synthetic data.
"""
import argparse
import json
import math
import pathlib
import statistics
import sys

import rvcommon as rv

# Landmark slots per extraction method. The digitizer series NAME is the slot; the click
# ORDER within a slot is the panel's left-to-right mark order (top-to-bottom for forest).
SLOTS = {
    "bar-endpoints": ["top", "cap"],
    "box-landmarks": ["median", "q1", "q3", "min", "max"],
    "forest-rows": ["estimate", "ciLo", "ciHi"],
    "digitize_points": ["points"],
    "auto_trace": ["points"],
}
OPTIONAL_SLOTS = {"cap", "min", "max"}
ZOOM_FLOOR_PX = 100     # cap-to-top separation below this cannot support a <=1% read


# ================================================================= coding form

def validate_form(form, vocab, where):
    """Mirror of figure-extractor.html::validateCharacterization, plus the fields the
    tool cannot hold (n, evidence, ambiguities). Returns a list of problems."""
    e, ct = [], form.get("charType")
    if ct is None:
        e.append(f"{where}: charType is null and no ambiguity recorded"
                 if not form.get("ambiguities") else None)
    elif ct not in vocab["charType"]:
        e.append(f"{where}: unknown charType {ct!r}")
    for ax in ("x", "y"):
        sc = ((form.get("axes") or {}).get(ax) or {}).get("scale")
        if sc is not None and sc not in vocab["scale"]:
            e.append(f"{where}: unknown {ax}-axis scale {sc!r}")
    d = form.get("dispersion") or {}
    if d.get("type") is not None and d["type"] not in vocab["dispersion"]:
        e.append(f"{where}: unknown dispersion type {d['type']!r}")
    if d.get("present") and d.get("type") in (None, "unknown") \
            and "dispersion-type-uncertain" not in (form.get("flags") or []):
        e.append(f"{where}: dispersion shown but type unresolved -- add the "
                 f"'dispersion-type-uncertain' flag or record an abstention")
    if d.get("present") and d.get("type") and not (d.get("evidence") or "").strip():
        e.append(f"{where}: dispersion type {d['type']!r} asserted with no quoted evidence")
    ids = []
    for i, s in enumerate(form.get("series") or []):
        if not s.get("id"):
            e.append(f"{where}: series[{i}] has no id")
        ids.append(s.get("id"))
        for k, vk in (("role", "role"), ("encoding", "seriesEncoding"),
                      ("labelSource", "labelSource")):
            if s.get(k) is not None and s[k] not in vocab[vk]:
                e.append(f"{where}: series[{i}] unknown {k} {s[k]!r}")
        if s.get("role") in (None, "unknown") and not form.get("ambiguities"):
            e.append(f"{where}: series[{i}] ({s.get('label') or 'unlabelled'}) has no role -- "
                     f"an unassigned arm is the silent catastrophic error; assign it or abstain")
        if not (s.get("label") or "").strip() and "series-unlabeled" not in (form.get("flags") or []):
            e.append(f"{where}: series[{i}] has no legend text -- add it or flag 'series-unlabeled'")
    if len(set(ids)) != len(ids):
        e.append(f"{where}: duplicate series ids {ids}")
    for m in form.get("marks") or []:
        if m.get("seriesId") not in ids:
            e.append(f"{where}: mark references unknown seriesId {m.get('seriesId')!r}")
    dp = form.get("dataProvenance")
    if dp is not None and dp not in vocab["dataProvenance"]:
        e.append(f"{where}: unknown dataProvenance {dp!r}")
    for fl in form.get("flags") or []:
        if fl not in vocab["flags"]:
            e.append(f"{where}: flag {fl!r} is not in the tool's vocabulary")
    for el in form.get("nonDataElements") or []:
        if el not in vocab["nonDataElement"]:
            e.append(f"{where}: unknown nonDataElement {el!r}")
    for a in form.get("ambiguities") or []:
        if not a.get("field") or not a.get("why"):
            e.append(f"{where}: an ambiguity entry needs both `field` and `why`")
    return [x for x in e if x]


# ================================================================= landmark decoding

def decode_landmarks(dig, form, method, where):
    """Digitizer points -> named landmark slots, with integrity checks.

    The tool stores a digitized point as {px, py, s} where `s` indexes
    `digitization.series`. The protocol makes the series NAME the landmark slot and the
    click ORDER the roster order, which is decodable without any tool change and -- more
    importantly -- self-checking: a slot whose length, left-to-right monotonicity, or
    top/cap x-alignment disagrees with the declared roster is an ERROR, not a guess.
    """
    errs = []
    names = [(s.get("name") or "").strip() for s in (dig.get("series") or [])]
    slots = {}
    for i, nm in enumerate(names):
        key = nm.split("|")[0].strip()
        slots.setdefault(key, []).extend(
            [p for p in (dig.get("points") or []) if int(p.get("s") or 0) == i])
    want = SLOTS[method]
    marks = form.get("marks") or []
    nmarks = len(marks)
    forest = method == "forest-rows"
    sortkey = (lambda p: p["py"]) if forest else (lambda p: p["px"])

    for slot in want:
        pts = slots.get(slot)
        if not pts:
            if slot in OPTIONAL_SLOTS:
                continue
            if slot == "points":
                continue
            errs.append(f"{where}: no digitizer series named {slot!r} "
                        f"(found {sorted(slots) or 'none'})")
            continue
        ordered = sorted(pts, key=sortkey)
        if [id(p) for p in ordered] != [id(p) for p in pts]:
            errs.append(f"{where}: series {slot!r} was not clicked in "
                        f"{'top-to-bottom' if forest else 'left-to-right'} order")
        slots[slot] = ordered
        if slot != "points" and nmarks and len(ordered) != nmarks:
            errs.append(f"{where}: series {slot!r} has {len(ordered)} points but the "
                        f"coding form declares {nmarks} marks")
    if method == "bar-endpoints":
        present = (form.get("dispersion") or {}).get("present")
        if present and "cap" not in slots:
            errs.append(f"{where}: dispersion is present but no 'cap' series was picked")
        if not present and slots.get("cap"):
            errs.append(f"{where}: 'cap' points picked but the form says no dispersion")
        tops, caps = slots.get("top", []), slots.get("cap", [])
        if tops and caps and len(tops) == len(caps):
            span = max(p["px"] for p in tops) - min(p["px"] for p in tops)
            tol = max(6.0, 0.06 * max(span, 1))
            for i, (t, c) in enumerate(zip(tops, caps)):
                if abs(t["px"] - c["px"]) > tol:
                    errs.append(f"{where}: mark {i} cap x={c['px']:.0f} is {abs(t['px']-c['px']):.0f} px "
                                f"from its bar top x={t['px']:.0f} (tol {tol:.0f}) -- "
                                f"click order probably slipped")
                if c["py"] >= t["py"] and "error-bars-one-sided" not in (form.get("flags") or []):
                    errs.append(f"{where}: mark {i} cap is not above its bar top; if the bar "
                                f"points downward flag 'error-bars-one-sided'")
    return slots, errs


def _y(cal, vals, p):
    return rv.to_data(cal, vals, [p])[0]


def build_extraction(dig, form, method, where):
    """Pixels -> data -> the tool's `extraction` object (EXTRACT.bars/.boxes/.forest)."""
    cal, vals = dig.get("cal") or {}, dig.get("vals") or {}
    if rv.to_data(cal, vals, [{"px": 0, "py": 0}]) is None:
        return None, [f"{where}: calibration is incomplete or degenerate"]
    slots, errs = decode_landmarks(dig, form, method, where)
    if errs:
        return None, errs
    marks = form.get("marks") or []
    series_by_id = {s["id"]: s for s in (form.get("series") or [])}
    disp = (form.get("dispersion") or {}).get("type")
    dwv = rv.load_dispersion_with_variance()

    def meta(i):
        m = marks[i] if i < len(marks) else {}
        s = series_by_id.get(m.get("seriesId"), {})
        nm = " ".join(x for x in [m.get("group") or "", s.get("label") or ""] if x).strip() \
            or f"mark{i + 1}"
        return {"name": nm, "groupId": m.get("group") or "", "seriesId": m.get("seriesId") or "",
                "seriesLabel": s.get("label") or "", "n": s.get("n")}

    if method == "bar-endpoints":
        groups = []
        for i, t in enumerate(slots.get("top", [])):
            g = meta(i)
            mean = _y(cal, vals, t)["y"]
            caps = slots.get("cap", [])
            eh = abs(_y(cal, vals, caps[i])["y"] - mean) if i < len(caps) else None
            g.update({"mean": mean, "errorHalf": eh, "dispersionType": disp})
            groups.append(g)
        flags = [] if disp in dwv else ["dispersion-type-uncertain"]
        return {"method": method, "groups": groups, "flags": flags}, []
    if method == "box-landmarks":
        groups = []
        for i, med in enumerate(slots.get("median", [])):
            g = meta(i)
            g["median"] = _y(cal, vals, med)["y"]
            for k in ("q1", "q3", "min", "max"):
                pts = slots.get(k, [])
                g[k] = _y(cal, vals, pts[i])["y"] if i < len(pts) else None
            if g["q1"] is not None and g["q3"] is not None and g["q1"] > g["q3"]:
                return None, [f"{where}: mark {i} has q1 > q3 -- the two series are swapped"]
            groups.append(g)
        return {"method": method, "groups": groups}, []
    if method == "forest-rows":
        rows = []
        for i, est in enumerate(slots.get("estimate", [])):
            m = meta(i)
            lo = slots.get("ciLo", []); hi = slots.get("ciHi", [])
            rows.append({"label": m["name"],
                         "estimate": _y(cal, vals, est)["y"],
                         "ciLo": _y(cal, vals, lo[i])["y"] if i < len(lo) else None,
                         "ciHi": _y(cal, vals, hi[i])["y"] if i < len(hi) else None,
                         "scale": ((form.get("axes") or {}).get("y") or {}).get("scale") or "linear"})
        return {"method": method, "rows": rows,
                "scale": rows[0]["scale"] if rows else "linear"}, []
    pts = rv.to_data(cal, vals, dig.get("points") or []) or []
    return {"method": method,
            "points": [{"x": p["x"], "y": p["y"], "s": q.get("s", 0)}
                       for p, q in zip(pts, dig.get("points") or [])]}, []


def build_characterization(form):
    """The human's semantics in the tool's `characterization` shape."""
    d = form.get("dispersion") or {}
    series = [{"id": s["id"], "label": s.get("label") or "", "role": s.get("role"),
               "encoding": s.get("encoding"), "labelSource": s.get("labelSource"),
               "nSource": s.get("nSource") or "", "evidence": s.get("evidence") or "",
               "labelConfidence": 1.0, "roleConfidence": 1.0}
              for s in (form.get("series") or [])]
    panel = {
        "charType": form.get("charType"),
        "axes": {"x": {"scale": ((form.get("axes") or {}).get("x") or {}).get("scale")},
                 "y": {"scale": ((form.get("axes") or {}).get("y") or {}).get("scale")}},
        "statistics": {"dispersion": {"present": d.get("present"), "type": d.get("type")},
                       "timepoint": form.get("timepoint") or "",
                       "nSource": (series[0]["nSource"] if series else "")},
        "series": series, "seriesCount": len(series),
        "legendOrder": [s["id"] for s in series], "plotOrder": [s["id"] for s in series],
        "extractionPlan": {"method": None},
        "dataProvenance": form.get("dataProvenance"),
        "ignoredElements": form.get("nonDataElements") or [],
    }
    return {"panels": [panel], "flags": form.get("flags") or [], "panelCount": 1,
            "producedAt": rv.now_iso()}


def landmark_rows(article, target, extraction, char, header):
    """Port of figure-extractor.html::authoritativeRows for one target."""
    rows = []
    e = extraction
    prov = {"direction": e.get("direction") if e.get("direction") is not None else "",
            "timepoint": e.get("timepoint") or "", "nSource": e.get("nSource") or "",
            "flags": ";".join(e.get("flags") or []),
            "figure_derived": e.get("figure_derived", True),
            "Data_Source": e.get("Data_Source", "figure"),
            "Data_Extraction_Method": e.get("Data_Extraction_Method", "figure-extractor")}
    series = ((char or {}).get("panels") or [{}])[0].get("series") or []

    def slabel(sid):
        if sid in ("", None):
            return ""
        hit = next((s for s in series if str(s.get("id")) == str(sid)), None)
        return (hit or {}).get("label") or ""

    def push(o):
        r = rv.blank_landmark_row(header)
        r.update({"article": article, "target": target, "chartType": e.get("charType") or ""})
        r.update(o)
        r.update(prov)
        if r.get("seriesLabel") == "" and r.get("seriesId") != "":
            r["seriesLabel"] = slabel(r["seriesId"])
        rows.append(r)

    m = e.get("method")
    if m == "bar-endpoints":
        for g in e.get("groups") or []:
            push({"landmarkKind": "bar-group", "group": g.get("name"),
                  "groupId": g.get("groupId", ""), "seriesId": g.get("seriesId", ""),
                  "seriesLabel": g.get("seriesLabel", ""), "mean": g.get("mean"),
                  "errorHalf": g.get("errorHalf"),
                  "dispersionType": g.get("dispersionType") or e.get("dispersionType") or "",
                  "n": g.get("n")})
    elif m == "box-landmarks":
        for g in e.get("groups") or []:
            push({"landmarkKind": "box-group", "group": g.get("name"),
                  "groupId": g.get("groupId", ""), "seriesId": g.get("seriesId", ""),
                  "seriesLabel": g.get("seriesLabel", ""), "median": g.get("median"),
                  "q1": g.get("q1"), "q3": g.get("q3"), "min": g.get("min"),
                  "max": g.get("max"), "n": g.get("n")})
    elif m == "forest-rows":
        for r_ in e.get("rows") or []:
            push({"landmarkKind": "forest-row", "group": r_.get("label"),
                  "estimate": r_.get("estimate"), "ciLo": r_.get("ciLo"), "ciHi": r_.get("ciHi")})
    elif isinstance(e.get("points"), list):
        for p in e["points"]:
            push({"landmarkKind": "point", "x": p.get("x"), "y": p.get("y"),
                  "seriesId": p.get("s", "")})
    return rows


# ================================================================= jitter accounting

def jitter_report(dig, extraction):
    """What a 1-IMAGE-pixel slip is worth, per channel, on this panel.

    Directly comparable to the synthetic human-click floor (0.44% central / 4.15%
    dispersion median at 1 px). The rater is instructed to work at >=1:1 display
    magnification -- verified by the grating burned into every Stage B crop -- so one
    image pixel is an upper bound on one screen pixel, which is what makes this a
    conservative estimate of his actual hand jitter rather than an optimistic one.
    """
    cal, vals = dig.get("cal") or {}, dig.get("vals") or {}
    probe = rv.to_data(cal, vals, [{"px": 0, "py": 0}, {"px": 0, "py": 1}])
    if not probe:
        return None
    upp = abs(probe[1]["y"] - probe[0]["y"])
    # MAGNIFICATION, so the audit can work in the unit the human rule is written in.
    # PROTOCOL sec.7.2: the rater's floor is 100 SCREEN px; the stored geometry is in
    # IMAGE px; screen = k * image. `k` is exported by persistDig (and per point). When it
    # is absent -- an export from before the tool recorded it -- fall back to k = 1, which
    # is the 1:1 grating's guarantee and therefore a LOWER bound on the true screen span.
    ks = [p["k"] for p in (dig.get("points") or [])
          if isinstance(p, dict) and isinstance(p.get("k"), (int, float)) and p["k"] > 0]
    k = (statistics.median(ks) if ks
         else (dig.get("k") if isinstance(dig.get("k"), (int, float)) and dig.get("k") > 0
               else None))
    out = {"unitsPerPixel": upp, "central": [], "dispersion": [], "capTopPx": [],
           "k": k, "kSource": ("per-point" if ks else "digitization" if k else "assumed-1.0"),
           "kAssumed": k is None}
    if extraction.get("method") == "bar-endpoints":
        for g in extraction.get("groups") or []:
            if g.get("mean"):
                out["central"].append(100 * upp / abs(g["mean"]))
            if g.get("errorHalf"):
                out["dispersion"].append(100 * upp / abs(g["errorHalf"]))
                out["capTopPx"].append(abs(g["errorHalf"]) / upp if upp else float("nan"))
    elif extraction.get("method") == "box-landmarks":
        for g in extraction.get("groups") or []:
            if g.get("median"):
                out["central"].append(100 * upp / abs(g["median"]))
            if g.get("q1") is not None and g.get("q3") is not None and g["q3"] != g["q1"]:
                out["dispersion"].append(100 * upp / abs(g["q3"] - g["q1"]))
                out["capTopPx"].append(abs(g["q3"] - g["q1"]) / upp if upp else float("nan"))
    return out


# ================================================================= ingest

def cmd_ingest(args):
    session = args.session
    sdir = rv.SESSIONS / session
    vocab = rv.load_vocab()
    header = rv.load_landmark_header()
    chart_method = rv.load_chart_method()
    keyfile = rv.read_json(rv.KEYS / "plan.key.json") or {"sessions": []}
    keyed = {}
    for s in keyfile["sessions"]:
        for it in s["items"]:
            keyed[it["anon_id"]] = dict(it, session=s["session"])

    sessB = rv.read_json(sdir / "sessionB.json")
    if not sessB:
        raise SystemExit(f"no sessionB.json for {session} -- run `prepare_session.py build-b`")
    expA, expB = sdir / "exports" / "passA", sdir / "exports" / "passB"

    problems, records, csv_rows, panel_rows, sealed = [], [], [], [], []

    # ---- Stage A: figure + panel geometry (human annotation IS ground truth here) ----
    structure, stage_a_raw = {}, {}
    for aid in {i["anon_id"] for i in sessB["items"]}:
        ann = rv.read_json(expA / aid / "annotations.json")
        if ann is None:
            problems.append(f"{aid}: missing Stage A export")
            continue
        bad = rv.annotation_mode_violations(ann) + rv.blinding_violations(ann)
        if bad:
            problems += [f"BLINDING {aid}: {b}" for b in bad]
            continue
        sealed.append(expA / aid / "annotations.json")
        stage_a_raw[aid] = ann
        figs = []
        for f in ann.get("figures", []):
            figs.append({
                "figureLabel": f.get("label"), "pageNum": f.get("pageNum"),
                "bbox": f.get("bounds"), "caption": f.get("caption") or "",
                "captionSource": f.get("captionSource") or "", "notes": f.get("notes") or "",
                "createdAt": f.get("createdAt"),
                "panels": [{"label": s.get("label"), "letter": (s.get("label") or "")[-1:].upper(),
                            "bbox": s.get("bounds"), "caption": s.get("caption") or "",
                            "createdAt": s.get("createdAt")}
                           for s in f.get("subfigures", [])]})
        structure[aid] = figs
        for fi, f in enumerate(figs):
            panel_rows.append({
                "task": aid, "figureIndex": fi, "nPanels": len(f["panels"]),
                "confidence": 1.0, "abstain": False, "method": "human",
                "figureBbox": f["bbox"],
                "panels": [{"label": p["letter"],
                            "bbox": {"x": (f["bbox"] or {}).get("x", 0) + (p["bbox"] or {}).get("x", 0),
                                     "y": (f["bbox"] or {}).get("y", 0) + (p["bbox"] or {}).get("y", 0),
                                     "width": (p["bbox"] or {}).get("width"),
                                     "height": (p["bbox"] or {}).get("height")},
                            "conf": 1.0} for p in f["panels"]]})

    # ---- Stage B: semantics + landmarks, per panel ----
    payload = {}          # (anon_id, panel letter) -> what Stage B learned about that panel
    for entry in sessB["items"]:
        pid, aid = entry["panel_item"], entry["anon_id"]
        where = pid
        form = rv.read_json(sdir / "coding" / f"{pid}.form.json")
        if form is None:
            problems.append(f"{pid}: missing coding form")
            continue
        form = {k: v for k, v in form.items() if not k.startswith("_")}
        problems += validate_form(form, vocab, where)
        if form.get("extractable") is False:
            records.append({"panel_item": pid, "anon_id": aid, "session": session,
                            "extractable": False,
                            "charType": form.get("charType"),
                            "ambiguities": form.get("ambiguities") or [],
                            "notes": form.get("notes") or ""})
            sealed.append(sdir / "coding" / f"{pid}.form.json")
            continue
        ann = rv.read_json(expB / pid / "annotations.json")
        if ann is None:
            problems.append(f"{pid}: missing Stage B export")
            continue
        bad = rv.annotation_mode_violations(ann) + rv.blinding_violations(ann)
        if bad:
            problems += [f"BLINDING {pid}: {b}" for b in bad]
            continue
        fig = (ann.get("figures") or [{}])[0]
        dig = fig.get("digitization")
        if not dig or not dig.get("points"):
            problems.append(f"{pid}: no digitization in the Stage B export")
            continue
        method = chart_method.get(form.get("charType") or "", "not_extractable")
        if method not in SLOTS:
            problems.append(f"{pid}: charType {form.get('charType')!r} routes to "
                            f"{method!r} -- mark it extractable:false instead")
            continue
        result, errs = build_extraction(dig, form, method, where)
        problems += errs
        if result is None:
            continue
        char = build_characterization(form)
        char["panels"][0]["extractionPlan"]["method"] = method
        disp = (form.get("dispersion") or {}).get("type")
        extraction = dict(result)
        extraction.update({
            "charType": form.get("charType"), "dispersionType": disp,
            "dataProvenance": form.get("dataProvenance"),
            "priority": rv.extraction_priority(form.get("charType"), form.get("dataProvenance")),
            "direction": form.get("direction"), "timepoint": form.get("timepoint") or None,
            "nSource": char["panels"][0]["statistics"]["nSource"] or None,
            "flags": result.get("flags", []),
            "figure_derived": True, "Data_Source": "figure",
            "Data_Extraction_Method": "figure-extractor", "producedAt": rv.now_iso()})

        # Stage B pixels live in the Stage B CROP's coordinate space, not the Stage A page's.
        # The calibration is self-contained (refs and points share that space), so every
        # consumer that goes through the affine is correct; recording the space explicitly
        # stops anyone joining these pixels to the Stage A boxes by mistake.
        dig = dict(dig, renderSpace={"stage": "B", "dpi": entry["dpi"],
                                     "panelPx": entry["panelPx"], "panelItem": pid})
        payload[(aid, entry["panelLetter"])] = {
            "characterization": char, "extraction": extraction, "digitization": dig,
            "panelItem": pid, "entry": entry}
        sealed += [sdir / "coding" / f"{pid}.form.json", expB / pid / "annotations.json"]

        k = keyed.get(aid, {})
        records.append({
            "panel_item": pid, "anon_id": aid, "session": session,
            "item_id": k.get("item_id"), "article": k.get("article"), "doi": k.get("doi"),
            "figure": k.get("figure"), "row_ids": k.get("row_ids", []),
            "isRepeat": k.get("isRepeat"), "stratum": k.get("stratum"),
            "panelLetter": entry["panelLetter"], "dpi": entry["dpi"],
            "panelPx": entry["panelPx"], "position": entry.get("position"),
            "extractable": True, "reader": args.reader,
            "structure": structure.get(aid), "characterization": char,
            "extraction": extraction, "digitization": dig,
            "jitter": jitter_report(dig, extraction),
            "ambiguities": form.get("ambiguities") or [], "notes": form.get("notes") or ""})

    if problems and not args.allow_problems:
        print("\n".join("  ! " + p for p in problems), file=sys.stderr)
        raise SystemExit(f"\n{len(problems)} problem(s) -- fix and re-run "
                         f"(or --allow-problems to ingest the rest)")
    for p in problems:
        print("  ! " + p, file=sys.stderr)

    gdir = rv.GT / session
    gdir.mkdir(parents=True, exist_ok=True)

    # ---- Assemble: one annotations.json per FIGURE, panels as subfigures ----
    # This is the tool's own model (a panel IS a subfigure) rather than one file per
    # panel, so the record round-trips through figuresFromJSON and any consumer that
    # walks `figures[].subfigures[]` -- including score_real_validation.py's
    # normalize_annotations -- reads it without special-casing.
    for aid, raw in stage_a_raw.items():
        figures = []
        for f in raw.get("figures", []):
            subs = []
            for s in f.get("subfigures", []):
                letter = (s.get("label") or "")[-1:].upper()
                pl = payload.get((aid, letter), {})
                subs.append({
                    "id": s.get("id"), "label": s.get("label"), "bounds": s.get("bounds"),
                    "boundsNorm": s.get("boundsNorm"),
                    "caption": s.get("caption") or "",
                    "captionSource": s.get("captionSource") or "",
                    "createdAt": s.get("createdAt"),
                    "digitization": pl.get("digitization"),
                    "characterization": pl.get("characterization"),
                    "extraction": pl.get("extraction")})
                if pl.get("extraction"):
                    csv_rows += landmark_rows(aid, s.get("label") or letter,
                                              pl["extraction"], pl["characterization"], header)
            figures.append({**{k: f.get(k) for k in
                               ("id", "label", "pageNum", "bounds", "boundsNorm", "caption",
                                "captionSource", "captionBounds", "captionConfidence",
                                "notes", "createdAt", "locked", "finishedAt")},
                            "digitization": None, "characterization": None,
                            "extraction": None, "panelDetection": None,
                            "subfigures": subs})
        out_ann = {"schemaVersion": rv.SCHEMA_VERSION, "project": session, "article": aid,
                   "exportedAt": rv.now_iso(), "pages": raw.get("pages", []),
                   "figures": figures}
        rv.write_json(gdir / aid / "annotations.json", out_ann)
        sealed.append(gdir / aid / "annotations.json")
        # Mirror repeat-session GT into repeat/ as well, which is where
        # score_real_validation.py looks for the second read.
        if (keyed.get(aid, {}) or {}).get("isRepeat"):
            rv.write_json(rv.DATA / "repeat" / session / aid / "annotations.json", out_ann)
    (gdir / "figure-derived-landmarks.csv").write_text(
        rv.landmarks_csv(csv_rows, header), encoding="utf-8", newline="")
    print(f"[written] {gdir / 'figure-derived-landmarks.csv'}  ({len(csv_rows)} rows)")
    with open(gdir / "panels_gt.jsonl", "w") as f:
        for r in panel_rows:
            f.write(json.dumps(r) + "\n")
    print(f"[written] {gdir / 'panels_gt.jsonl'}  ({len(panel_rows)} figures)")

    rv.GT.mkdir(parents=True, exist_ok=True)
    store = rv.GT / "human_gt.jsonl"
    keep = [json.loads(l) for l in store.read_text().splitlines() if l.strip()] \
        if store.exists() else []

    # RE-INGEST IS DESTRUCTIVE, AND IT USED TO BE SILENT.
    # Replacing every record of this session is right when the session is being redone in
    # full; it is a data-loss bug when the second run produces FEWER panels than the first
    # -- which is exactly what a `--allow-problems` run after a clean one does. Measured on
    # a sandbox session: 4 sealed panels -> 3, no warning, no trace of the missing one, and
    # PROTOCOL sec.10 promises "nothing is written until it all passes". So: name the
    # panels that would disappear and REFUSE, unless the operator says --reingest.
    prior = [r for r in keep if r.get("session") == session]
    prior_ids = {r.get("panel_item") for r in prior}
    new_ids = {r.get("panel_item") for r in records}
    lost = sorted(x for x in prior_ids - new_ids if x)
    if lost:
        msg = [f"RE-INGEST WOULD DESTROY {len(lost)} PANEL RECORD(S) already in "
               f"{store.name}:"] + [f"    - {x}" for x in lost] + [
            f"  prior: {len(prior)} records for {session}; this run produced {len(records)}.",
            "  A panel that ingested cleanly before and does not now is a REGRESSION, not",
            "  a correction -- most often a --allow-problems run over a session that had",
            "  already passed, or a missing export directory."]
        if not getattr(args, "reingest", False):
            print("\n".join("  ! " + m for m in msg), file=sys.stderr)
            raise SystemExit(
                "\nrefusing to write. Nothing has been changed in human_gt.jsonl.\n"
                "Re-run with --reingest if the loss is intended (e.g. the panels were "
                "genuinely withdrawn), or fix the exports and re-run without it.")
        print("\n".join("  !! " + m for m in msg), file=sys.stderr)
        print("  !! --reingest given: writing anyway and DISCARDING the records above.",
              file=sys.stderr)

    keep = [r for r in keep if r.get("session") != session] + records
    with open(store, "w") as f:
        for r in keep:
            f.write(json.dumps(r) + "\n")
    print(f"[written] {store}  ({len(records)} this session, {len(keep)} total"
          + (f", replacing {len(prior)} prior records for {session}" if prior else "") + ")")

    sealed += [gdir / "figure-derived-landmarks.csv", gdir / "panels_gt.jsonl"]
    tl = sdir / "timing" / "passA.jsonl"
    if tl.exists():
        sealed.append(tl)
    tl = sdir / "timing" / "passB.jsonl"
    if tl.exists():
        sealed.append(tl)
    rec = rv.seal([p for p in sealed if pathlib.Path(p).exists()],
                  {"session": session, "reader": args.reader,
                   "nPanels": len(records), "nProblems": len(problems),
                   "note": "Any machine run compared against this session MUST start "
                           "after sealedAt. The human pass could not have seen it."})
    rv.write_json(gdir / "seal.json", rec)
    print(f"\nSealed {len(rec['files'])} artifacts at {rec['sealedAt']}.")
    print(f"The machine pass may now run on {session}.")


# ================================================================= audit

def _spearman(a, b):
    try:
        from scipy.stats import spearmanr
        r = spearmanr(a, b)
        return float(r.statistic), float(r.pvalue)
    except Exception:
        return float("nan"), float("nan")


def cmd_audit(args):
    recs = [json.loads(l) for l in (rv.GT / "human_gt.jsonl").read_text().splitlines() if l.strip()]
    if args.session:
        recs = [r for r in recs if r["session"] == args.session]
    if not recs:
        raise SystemExit("nothing ingested yet")
    L = ["# Human annotation audit", "", f"Generated {rv.now_iso()} over {len(recs)} panel records.", ""]

    cen, dis, capdist, low = [], [], [], []
    for r in recs:
        j = r.get("jitter") or {}
        cen += j.get("central", [])
        dis += j.get("dispersion", [])
        kk = j.get("k") or 1.0
        for c in j.get("capTopPx", []):
            if c == c:
                capdist.append(c)
                if c < ZOOM_FLOOR_PX:
                    low.append((r["panel_item"], c, kk, c * kk, j.get("kSource")))
    L += ["## Zoom discipline / implied click jitter", "",
          "What a 1-image-pixel slip is worth on each channel. Compare with the synthetic",
          "human-click floor: 0.44% central / 4.15% dispersion median at 1 px.", "",
          "| channel | median | p90 | worst | n |", "|---|---|---|---|---|"]
    for nm, xs in (("central", cen), ("dispersion", dis)):
        if xs:
            xs2 = sorted(xs)
            L.append(f"| {nm} | {statistics.median(xs2):.3f}% | "
                     f"{xs2[min(len(xs2) - 1, int(0.9 * len(xs2)))]:.3f}% | "
                     f"{xs2[-1]:.3f}% | {len(xs2)} |")
    if capdist:
        L += ["", f"Dispersion span in image px: median {statistics.median(capdist):.0f}, "
                  f"min {min(capdist):.0f} (floor for a <=1% read is {ZOOM_FLOOR_PX})."]
    if low:
        # UNITS (PROTOCOL sec.7.2). The floor above is in IMAGE px; the rater's rule is in
        # SCREEN px, and screen = k * image. Both columns are printed so the two are never
        # confused again: act on the SCREEN column, which is the one the rule is about.
        # Where k had to be assumed 1.0 (an export from before the tool recorded it), the
        # screen span shown is a LOWER bound -- the 1:1 grating guarantees k >= 1.
        hard = [x for x in low if x[3] < ZOOM_FLOOR_PX]
        L += ["", f"**{len(low)} landmark(s) below the {ZOOM_FLOOR_PX}-IMAGE-px floor**, of which",
              f"**{len(hard)} are also below {ZOOM_FLOOR_PX} SCREEN px** and must be re-picked at",
              "higher magnification. The rest cleared the screen-pixel rule by zooming past 1:1;",
              "they are listed because the image-pixel floor is deliberately conservative.", "",
              "| landmark | image px | k | screen px | k source | action |",
              "|---|---|---|---|---|---|"]
        for p, c, kk, scr, ksrc in sorted(low, key=lambda t: t[3])[:20]:
            L.append(f"| `{p}` | {c:.0f} | {kk:.2f}x | **{scr:.0f}** | {ksrc} | "
                     + ("**RE-PICK**" if scr < ZOOM_FLOOR_PX else "ok on the screen rule") + " |")

    L += ["", "## Abstentions and flags", ""]
    amb = [(r["panel_item"], a) for r in recs for a in (r.get("ambiguities") or [])]
    L.append(f"- {len(amb)} recorded ambiguities over {len(recs)} panels "
             f"({100 * len({p for p, _ in amb}) / len(recs):.0f}% of panels).")
    byfield = {}
    for p, a in amb:
        byfield.setdefault(a.get("field", "?"), []).append(p)
    for f, ps in sorted(byfield.items(), key=lambda t: -len(t[1])):
        L.append(f"  - `{f}`: {len(ps)}")
    flg = {}
    for r in recs:
        for f in ((r.get("characterization") or {}).get("flags") or []):
            flg[f] = flg.get(f, 0) + 1
    for f, n in sorted(flg.items(), key=lambda t: -t[1]):
        L.append(f"- flag `{f}`: {n}")
    nx = [r for r in recs if r.get("extractable") is False]
    L.append(f"- {len(nx)} panel(s) marked not extractable.")

    L += ["", "## Fatigue", ""]
    pos, sec = [], []
    for sdir in sorted(rv.SESSIONS.glob("S*")):
        for stage in ("A", "B"):
            tl = sdir / "timing" / f"pass{stage}.jsonl"
            if not tl.exists():
                continue
            rows = [json.loads(l) for l in tl.read_text().splitlines() if l.strip()]
            rows = [r for r in rows if r.get("item") != "__break__"]
            if not rows:
                continue
            s = [r["seconds"] for r in rows]
            L.append(f"- {sdir.name} stage {stage}: {len(rows)} items, "
                     f"median {statistics.median(s):.0f}s, total {sum(s) / 60:.0f} min")
            pos += [r["position"] for r in rows]
            sec += s
    if len(pos) > 4:
        rho, p = _spearman(pos, sec)
        L.append(f"- time-vs-serial-position rho = {rho:+.3f} (p = {p:.3f}); "
                 f"a strong negative value means later items got rushed.")
    key = rv.read_json(rv.KEYS / "plan.key.json")
    if key:
        rank = {"easy": 1, "medium": 2, "hard": 3}
        dp, pp = [], []
        for s in key["sessions"]:
            for it in s["items"]:
                if it.get("difficulty") in rank:
                    dp.append(rank[it["difficulty"]]); pp.append(it["position"])
        if len(dp) > 4:
            rho, p = _spearman(dp, pp)
            L.append(f"- difficulty-vs-position rho = {rho:+.3f} (p = {p:.3f}); "
                     f"near zero means fatigue is not confounded with difficulty.")

    out = rv.GT / (f"audit-{args.session}.md" if args.session else "audit.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[written] {out}")
    print("\n".join(L[:24]))


# ================================================================= intra-rater

def _icc_a1(pairs):
    """ICC(A,1), two-way random, absolute agreement, k=2 replicates."""
    n = len(pairs)
    if n < 3:
        return float("nan")
    grand = sum(a + b for a, b in pairs) / (2 * n)
    msr = 2 * sum(((a + b) / 2 - grand) ** 2 for a, b in pairs) / (n - 1)
    cm = [sum(p[j] for p in pairs) / n for j in (0, 1)]
    msc = n * sum((c - grand) ** 2 for c in cm)
    sse = sum((p[j] - (p[0] + p[1]) / 2 - cm[j] + grand) ** 2 for p in pairs for j in (0, 1))
    mse = sse / (n - 1) if n > 1 else float("nan")
    den = msr + mse + 2 * (msc - mse) / n
    return (msr - mse) / den if den else float("nan")


def cmd_intra(args):
    recs = [json.loads(l) for l in (rv.GT / "human_gt.jsonl").read_text().splitlines() if l.strip()]
    key = rv.read_json(rv.KEYS / "plan.key.json")
    if not key:
        raise SystemExit("no keys/plan.key.json")
    # anon_id -> item_id, then pair first-read vs repeat-read on (item_id, panel letter).
    byitem = {}
    for r in recs:
        if not r.get("extractable") or not r.get("item_id"):
            continue
        byitem.setdefault((r["item_id"], r["panelLetter"]), []).append(r)
    pairs = [(v[0], v[1]) for v in byitem.values() if len(v) >= 2]
    if not pairs:
        raise SystemExit("no repeat pairs ingested yet -- the intra-rater sessions come later")

    L = ["# Intra-rater repeatability", "",
         f"Generated {rv.now_iso()}. {len(pairs)} panels read twice, blind to the first read.",
         "",
         "This is what gives the human reference an error bar. Without it, a human-vs-machine",
         "agreement number cannot be read: you cannot tell a machine error from the rater's own",
         "jitter. The dispersion row here is the honest ceiling on what this reference can",
         "adjudicate.", ""]

    cat = {"charType": [], "dispersionType": [], "nPanels": [], "roles": []}
    for a, b in pairs:
        ca = (a["characterization"]["panels"][0], b["characterization"]["panels"][0])
        cat["charType"].append(ca[0]["charType"] == ca[1]["charType"])
        cat["dispersionType"].append(
            ca[0]["statistics"]["dispersion"]["type"] == ca[1]["statistics"]["dispersion"]["type"])
        cat["roles"].append([s.get("role") for s in ca[0]["series"]] ==
                            [s.get("role") for s in ca[1]["series"]])
        na = len((a.get("structure") or [{}])[0].get("panels", []))
        nb = len((b.get("structure") or [{}])[0].get("panels", []))
        cat["nPanels"].append(na == nb)
    L += ["## Semantic channels (human is authoritative here)", "",
          "| channel | agreement | n |", "|---|---|---|"]
    for k, v in cat.items():
        if v:
            L.append(f"| {k} | {100 * sum(v) / len(v):.1f}% | {len(v)} |")

    chans = {"central": [], "dispersion": []}
    for a, b in pairs:
        ga = {g["name"]: g for g in a["extraction"].get("groups", [])}
        gb = {g["name"]: g for g in b["extraction"].get("groups", [])}
        for nm in set(ga) & set(gb):
            for chan, fld in (("central", "mean"), ("central", "median"),
                              ("dispersion", "errorHalf")):
                x, y = ga[nm].get(fld), gb[nm].get(fld)
                if x and y:
                    chans[chan].append((x, y))
            q1a, q3a = ga[nm].get("q1"), ga[nm].get("q3")
            q1b, q3b = gb[nm].get("q1"), gb[nm].get("q3")
            if None not in (q1a, q3a, q1b, q3b) and q3a != q1a and q3b != q1b:
                chans["dispersion"].append((q3a - q1a, q3b - q1b))
    L += ["", "## Numeric channels (human is a SECOND READER, not an oracle)", "",
          "`RC` is the repeatability coefficient 2.77*s_w: two reads by this rater differ by",
          "less than RC 95% of the time. A machine-vs-human difference smaller than RC is",
          "inside the reference's own noise and must not be called a machine error.", "",
          "| channel | median %diff | worst %diff | s_w (%) | RC (%) | ICC(A,1) | n |",
          "|---|---|---|---|---|---|---|"]
    summary = {}
    for chan, ps in chans.items():
        if not ps:
            continue
        rel = [100 * abs(x - y) / ((abs(x) + abs(y)) / 2) for x, y in ps]
        sw = math.sqrt(sum(r ** 2 for r in rel) / (2 * len(rel)))
        L.append(f"| {chan} | {statistics.median(rel):.2f}% | {max(rel):.2f}% | "
                 f"{sw:.2f}% | {2.77 * sw:.2f}% | {_icc_a1(ps):.3f} | {len(ps)} |")
        summary[chan] = {"n": len(ps), "median_pct": round(statistics.median(rel), 3),
                         "worst_pct": round(max(rel), 3), "sw_pct": round(sw, 3),
                         "rc_pct": round(2.77 * sw, 3), "icc_a1": round(_icc_a1(ps), 4)}

    ious = []
    for a, b in pairs:
        pa = ((a.get("structure") or [{}])[0].get("panels") or [])
        pb = ((b.get("structure") or [{}])[0].get("panels") or [])
        m = {p["letter"]: p["bbox"] for p in pb if p.get("bbox")}
        for p in pa:
            q = m.get(p["letter"])
            if p.get("bbox") and q:
                ious.append(_iou(p["bbox"], q))
    if ious:
        L += ["", "## Panel box repeatability", "",
              f"- median IoU {statistics.median(ious):.4f}, worst {min(ious):.4f}, n={len(ious)}",
              "- Human panel boxes are the ground truth for the detector; this is the",
              "  precision floor any IoU comparison against them inherits."]
        summary["panelIoU"] = {"median": round(statistics.median(ious), 4),
                               "worst": round(min(ious), 4), "n": len(ious)}

    out = rv.GT / "intra-rater.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[written] {out}")
    rv.write_json(rv.GT / "intra_rater.json",
                  {"schemaVersion": rv.RV_SCHEMA_VERSION, "generatedAt": rv.now_iso(),
                   "nPairs": len(pairs), "categorical":
                       {k: {"agreement": round(100 * sum(v) / len(v), 2), "n": len(v)}
                        for k, v in cat.items() if v},
                   "numeric": summary})
    print("\n".join(L))


def _iou(a, b):
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    iw = max(0, min(ax2, bx2) - max(a["x"], b["x"]))
    ih = max(0, min(ay2, by2) - max(a["y"], b["y"]))
    inter = iw * ih
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union else 0.0


# ================================================================= verify-seal

def cmd_verify_seal(args):
    bad_any = False
    for sd in sorted(rv.GT.glob("S*")):
        rec = rv.read_json(sd / "seal.json")
        if not rec:
            continue
        bad = rv.verify_seal(rec)
        print(f"{sd.name}: sealed {rec['sealedAt']}, {len(rec['files'])} files -- "
              f"{'OK' if not bad else 'TAMPERED'}")
        for b in bad:
            print("  ! " + b)
        bad_any = bad_any or bool(bad)
    sys.exit(1 if bad_any else 0)


# ================================================================= selftest

def cmd_selftest(args):
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
        ok = ok and cond

    print("ingest_annotations selftest")
    vocab = rv.load_vocab()
    header = rv.load_landmark_header()

    # A synthetic panel: y axis 0..25 over py 920..35, two bars, known means and caps.
    cal = {"x1": {"px": 395, "py": 920}, "x2": {"px": 533, "py": 920},
           "y1": {"px": 125, "py": 920}, "y2": {"px": 125, "py": 35}}
    vals = {"x1": "0", "x2": "1", "y1": "0", "y2": "25", "logX": False, "logY": False}
    dig = {"cal": cal, "vals": vals,
           "series": [{"name": "top"}, {"name": "cap"}],
           "points": [{"px": 395, "py": 566, "s": 0}, {"px": 533, "py": 460, "s": 0},
                      {"px": 395, "py": 495, "s": 1}, {"px": 533, "py": 390, "s": 1}]}
    form = {"charType": "bar", "extractable": True, "dataProvenance": "primary",
            "axes": {"x": {"scale": "categorical"}, "y": {"scale": "linear"}},
            "dispersion": {"present": True, "type": "SEM", "evidence": "caption: mean +/- SEM"},
            "series": [{"id": "s1", "label": "SC", "role": "control", "encoding": "fill",
                        "labelSource": "axis", "n": 5, "nSource": "caption"},
                       {"id": "s2", "label": "EE", "role": "intervention", "encoding": "fill",
                        "labelSource": "axis", "n": 5, "nSource": "caption"}],
            "marks": [{"group": "target", "seriesId": "s1"}, {"group": "target", "seriesId": "s2"}],
            "direction": 1, "timepoint": "", "nonDataElements": ["axis-ticks"],
            "flags": [], "ambiguities": [], "notes": ""}
    check("valid form passes validation", validate_form(form, vocab, "t") == [])

    res, errs = build_extraction(dig, form, "bar-endpoints", "t")
    check("bar extraction decodes", res is not None and errs == [], str(errs))
    m0 = res["groups"][0]["mean"]
    check("mean recovers from the tool's affine", abs(m0 - 10.0) < 0.05, f"{m0:.4f}")
    eh0 = res["groups"][0]["errorHalf"]
    check("errorHalf = |cap - top| in data units", abs(eh0 - 2.0) < 0.05, f"{eh0:.4f}")
    check("arm identity survives to the group", res["groups"][0]["seriesLabel"] == "SC"
          and res["groups"][1]["seriesLabel"] == "EE")
    check("known dispersion type raises no uncertainty flag", res["flags"] == [])

    f2 = dict(form, dispersion={"present": True, "type": "IQR", "evidence": "x"})
    r2, _ = build_extraction(dig, f2, "bar-endpoints", "t")
    check("non-variance dispersion forces the uncertainty flag",
          r2["flags"] == ["dispersion-type-uncertain"])

    swapped = dict(dig, points=[{"px": 533, "py": 460, "s": 0}, {"px": 395, "py": 566, "s": 0},
                                {"px": 395, "py": 495, "s": 1}, {"px": 533, "py": 390, "s": 1}])
    _, e3 = build_extraction(swapped, form, "bar-endpoints", "t")
    check("out-of-order clicks are refused, not guessed", any("order" in x for x in e3))

    slipped = dict(dig, points=[{"px": 395, "py": 566, "s": 0}, {"px": 533, "py": 460, "s": 0},
                                {"px": 533, "py": 495, "s": 1}, {"px": 700, "py": 390, "s": 1}])
    _, e4 = build_extraction(slipped, form, "bar-endpoints", "t")
    check("a cap detached from its bar top is caught", any("from its bar top" in x for x in e4))

    below = dict(dig, points=[{"px": 395, "py": 566, "s": 0}, {"px": 533, "py": 460, "s": 0},
                              {"px": 395, "py": 600, "s": 1}, {"px": 533, "py": 500, "s": 1}])
    _, e5 = build_extraction(below, form, "bar-endpoints", "t")
    check("a cap below its bar top is caught", any("not above" in x for x in e5))

    nocount = dict(dig, points=dig["points"][:3])
    _, e6 = build_extraction(nocount, form, "bar-endpoints", "t")
    check("roster/click count mismatch is caught", any("coding form declares" in x for x in e6))

    bad = dict(form, charType="barchart")
    check("invalid charType is rejected", any("unknown charType" in x
                                              for x in validate_form(bad, vocab, "t")))
    bad = dict(form, series=[dict(form["series"][0], role=None), form["series"][1]])
    check("an unassigned arm role is rejected",
          any("silent catastrophic" in x for x in validate_form(bad, vocab, "t")))
    bad = dict(form, dispersion={"present": True, "type": "SD", "evidence": ""})
    check("dispersion type with no quoted evidence is rejected",
          any("no quoted evidence" in x for x in validate_form(bad, vocab, "t")))
    bad = dict(form, flags=["made-up-flag"])
    check("a flag outside the tool vocabulary is rejected",
          any("not in the tool" in x for x in validate_form(bad, vocab, "t")))

    char = build_characterization(form)
    char["panels"][0]["extractionPlan"]["method"] = "bar-endpoints"
    ext = dict(res, charType="bar", dispersionType="SEM", dataProvenance="primary",
               direction=1, timepoint=None, nSource="caption", flags=[],
               figure_derived=True, Data_Source="figure",
               Data_Extraction_Method="figure-extractor")
    rows = landmark_rows("it01_aaaa_pA", "panel A", ext, char, header)
    check("one CSV row per bar", len(rows) == 2)
    check("every row has all 29 columns", all(set(r) == set(header) for r in rows))
    csv = rv.landmarks_csv(rows, header)
    check("CSV header is bare and first", csv.split("\r\n")[0] == ",".join(header))
    check("CSV data cells are quoted", csv.split("\r\n")[1].startswith('"it01_aaaa_pA"'))
    check("dispersion TYPE reaches the CSV", '"SEM"' in csv.split("\r\n")[1])
    check("arm label reaches the CSV", '"SC"' in csv.split("\r\n")[1])

    j = jitter_report(dig, res)
    check("jitter report computes units per pixel", j and j["unitsPerPixel"] > 0)
    check("dispersion jitter exceeds central jitter",
          j["dispersion"][0] > j["central"][0],
          f"{j['central'][0]:.3f}% vs {j['dispersion'][0]:.3f}%")
    check("cap-top span is reported in image px", abs(j["capTopPx"][0] - 71) < 2,
          f"{j['capTopPx'][0]:.0f} px")

    perfect = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0)]
    noisy = [(1.0, 1.4), (2.0, 1.7), (3.0, 3.5), (4.0, 3.4)]
    check("ICC is 1 for identical re-reads", abs(_icc_a1(perfect) - 1.0) < 1e-9)
    check("ICC drops with re-read noise", _icc_a1(noisy) < 0.95, f"{_icc_a1(noisy):.3f}")
    check("IoU of identical boxes is 1",
          abs(_iou({"x": 0, "y": 0, "width": 10, "height": 10},
                   {"x": 0, "y": 0, "width": 10, "height": 10}) - 1.0) < 1e-9)
    check("IoU of half-overlapping boxes",
          abs(_iou({"x": 0, "y": 0, "width": 10, "height": 10},
                   {"x": 5, "y": 0, "width": 10, "height": 10}) - 1 / 3) < 1e-9)

    box_dig = {"cal": cal, "vals": vals,
               "series": [{"name": "median"}, {"name": "q1"}, {"name": "q3"}],
               "points": [{"px": 395, "py": 566, "s": 0},
                          {"px": 395, "py": 640, "s": 1}, {"px": 395, "py": 500, "s": 2}]}
    box_form = dict(form, charType="box", marks=[{"group": "g", "seriesId": "s1"}],
                    series=[form["series"][0]],
                    dispersion={"present": True, "type": "IQR", "evidence": "caption"})
    rb, eb = build_extraction(box_dig, box_form, "box-landmarks", "t")
    check("box landmarks decode with q1 < median < q3",
          rb and eb == [] and rb["groups"][0]["q1"] < rb["groups"][0]["median"] < rb["groups"][0]["q3"])

    print("OK" if ok else "FAILURES")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("ingest", help="validate + normalize one session into the GT store")
    p.add_argument("session")
    p.add_argument("--reader", default="GF-human")
    p.add_argument("--allow-problems", action="store_true",
                   help="ingest what is valid and only warn about the rest")
    p.add_argument("--reingest", action="store_true",
                   help="permit a re-ingest that DESTROYS panel records already in "
                        "human_gt.jsonl. Without it, an ingest that would lose a panel "
                        "names the panel and refuses.")
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("audit", help="zoom discipline, abstentions, fatigue")
    p.add_argument("--session")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("intra", help="intra-rater repeatability from the repeat subset")
    p.set_defaults(fn=cmd_intra)
    p = sub.add_parser("verify-seal", help="re-check every sealed session")
    p.set_defaults(fn=cmd_verify_seal)
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
