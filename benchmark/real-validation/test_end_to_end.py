#!/usr/bin/env python3
"""test_end_to_end.py -- drive the whole human-validation pipeline on real PDFs.

Simulates the rater: plan -> Stage A materials -> a synthetic Stage A export ->
Stage B materials -> filled coding forms + a synthetic Stage B export -> ingest ->
audit -> a second (repeat) session -> intra-rater report. Everything runs in a
temp directory via RV_DATA, so the repo is untouched.

It also asserts the properties the protocol depends on:
  * an export bearing the panel detector's fingerprints is REFUSED;
  * a session cannot be built before its predecessor is sealed;
  * the emitted CSV has the tool's exact 29-column header;
  * a repeat item carries a different anon id from its original;
  * the seal detects tampering.

Run: python3 test_end_to_end.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REAL = HERE.parent / "real"
FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAILED.append(name)


def run(args, data, expect_fail=False):
    env = dict(os.environ, RV_DATA=str(data))
    r = subprocess.run([sys.executable] + args, cwd=HERE, env=env,
                       capture_output=True, text=True)
    if (r.returncode != 0) != expect_fail:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"unexpected exit {r.returncode} from {args}")
    return r


def fake_stage_a(sdir, anon_id, page_w, page_h, n_panels=2, poisoned=False):
    """What figure-extractor writes after the rater draws a figure box and n panel boxes."""
    fw, fh = int(page_w * 0.6), int(page_h * 0.28)
    fx, fy = int(page_w * 0.15), int(page_h * 0.12)
    subs = []
    for i in range(n_panels):
        subs.append({"id": f"fig1_s{i+1}", "label": f"Figure 1{chr(65+i)}",
                     "bounds": {"x": i * (fw // n_panels), "y": 0,
                                "width": fw // n_panels - 8, "height": fh},
                     "caption": "", "captionSource": "panel-split" if poisoned else "",
                     "createdAt": "2026-07-27T10:00:00.000Z"})
    fig = {"id": "fig1", "label": "Figure 1", "pageNum": 1,
           "bounds": {"x": fx, "y": fy, "width": fw, "height": fh},
           "caption": "Figure 1. (A) ... (B) ... Data are mean +/- SEM, n = 8 per group.",
           "captionSource": "textlayer", "notes": "", "locked": False, "finishedAt": None,
           "createdAt": "2026-07-27T10:00:00.000Z",
           "digitization": None, "characterization": None, "extraction": None,
           "panelDetection": ({"method": "gutter", "confidence": 0.9, "flags": []}
                              if poisoned else None),
           "subfigures": subs}
    d = sdir / "exports" / "passA" / anon_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "annotations.json").write_text(json.dumps(
        {"schemaVersion": 2, "project": "S01", "article": anon_id,
         "exportedAt": "2026-07-27T10:30:00.000Z",
         "pages": [{"pageNum": 1, "width": page_w, "height": page_h}],
         "figures": [fig]}, indent=2))


def fill_form(path, jitter=0.0):
    f = json.loads(path.read_text())
    f.update({
        "charType": "bar", "extractable": True, "dataProvenance": "primary",
        "axes": {"x": {"scale": "categorical", "unit": ""},
                 "y": {"scale": "linear", "unit": "s"}},
        "dispersion": {"present": True, "type": "SEM",
                       "evidence": "caption: 'Data are mean +/- SEM'"},
        "series": [
            {"id": "s1", "label": "Control", "role": "control", "encoding": "fill",
             "labelSource": "legend", "n": 8, "nSource": "caption", "evidence": "n = 8 per group"},
            {"id": "s2", "label": "Enriched", "role": "intervention", "encoding": "fill",
             "labelSource": "legend", "n": 8, "nSource": "caption", "evidence": "n = 8 per group"}],
        "marks": [{"group": "probe", "seriesId": "s1"}, {"group": "probe", "seriesId": "s2"}],
        "direction": 1, "timepoint": "", "nonDataElements": ["axis-ticks", "legend"],
        "flags": [], "ambiguities": [], "notes": ""})
    path.write_text(json.dumps(f, indent=2))


def fake_stage_b(sdir, pid, jitter=0.0):
    """Axis refs + two bar tops + two error caps, clicked in the documented order."""
    cal = {"x1": {"px": 400, "py": 1500}, "x2": {"px": 800, "py": 1500},
           "y1": {"px": 200, "py": 1500}, "y2": {"px": 200, "py": 200}}
    vals = {"x1": "0", "x2": "1", "y1": "0", "y2": "30", "logX": False, "logY": False}
    j = jitter
    pts = [{"px": 400, "py": 900 + j, "s": 0}, {"px": 800, "py": 700 - j, "s": 0},
           {"px": 400, "py": 780 - j, "s": 1}, {"px": 800, "py": 560 + j, "s": 1}]
    d = sdir / "exports" / "passB" / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "annotations.json").write_text(json.dumps(
        {"schemaVersion": 2, "project": "S01", "article": pid,
         "exportedAt": "2026-07-27T14:00:00.000Z",
         "pages": [{"pageNum": 1, "width": 1200, "height": 1700}],
         "figures": [{"id": "fig1", "label": pid, "pageNum": 1,
                      "bounds": {"x": 0, "y": 0, "width": 1200, "height": 1650},
                      "caption": "", "captionSource": "", "notes": "",
                      "createdAt": "2026-07-27T13:00:00.000Z",
                      "digitization": {"cal": cal, "vals": vals, "points": pts,
                                       "series": [{"name": "top"}, {"name": "cap"}],
                                       "notes": "", "updatedAt": "2026-07-27T14:00:00.000Z"},
                      "characterization": None, "extraction": None,
                      "panelDetection": None, "subfigures": []}]}, indent=2))


def main():
    pdf_map = json.loads((REAL / "pdf_map.json").read_text())
    pdfs = [(k, v["pdf"]) for k, v in sorted(pdf_map.items())
            if v.get("status") == "ok" and pathlib.Path(v["pdf"]).exists()][:4]
    if len(pdfs) < 4:
        raise SystemExit("need 4 resolvable PDFs for the end-to-end test")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rv-e2e-"))
    print(f"end-to-end test in {tmp}\n")
    try:
        wl = {"schemaVersion": 1, "items": [
            {"item_id": f"{a}_fig1", "article": a, "pdf": p, "page": 1,
             "figure": "Figure 1", "difficulty": ["easy", "medium", "hard", "medium"][i],
             "row_ids": [f"{a}__r0"]}
            for i, (a, p) in enumerate(pdfs)]}
        wlp = tmp / "wl.json"
        wlp.write_text(json.dumps(wl))

        # --- plan: 2 items/session so we get several sessions plus repeat sessions ---
        run(["prepare_session.py", "plan", "--worklist", str(wlp), "--per-session", "2"], tmp)
        plan = json.loads((tmp / "plan.json").read_text())
        key = json.loads((tmp / "keys" / "plan.key.json").read_text())
        check("plan covers every item",
              sum(s["nItems"] for s in plan["sessions"] if not
                  next(k for k in key["sessions"] if k["session"] == s["session"])["isRepeatSession"])
              == len(pdfs))
        check("repeat subset is non-empty", len(key["repeatIds"]) >= 1,
              f"{len(key['repeatIds'])} repeats")
        anon_by_item = {}
        for s in key["sessions"]:
            for it in s["items"]:
                anon_by_item.setdefault(it["item_id"], []).append(it["anon_id"])
        reissued = [v for v in anon_by_item.values() if len(v) > 1]
        check("a repeat gets a fresh anon id", all(len(set(v)) == len(v) for v in reissued),
              f"{len(reissued)} reissued item(s)")
        check("the public plan never states the panel count",
              all(i["expectPanels"] is None for s in plan["sessions"] for i in s["items"]))
        check("the key is outside the session tree",
              (tmp / "keys" / "plan.key.json").exists()
              and not list((tmp / "sessions").glob("**/plan.key.json"))
              if (tmp / "sessions").exists() else True)

        # --- Stage A build ---
        run(["prepare_session.py", "build", "S01"], tmp)
        s01 = tmp / "sessions" / "S01"
        sess = json.loads((s01 / "session.json").read_text())
        check("Stage A renders one page per item", len(sess["items"]) == 2)
        check("page PNGs land where the tool expects them",
              all((s01 / "projectA" / i["anon_id"] / "0001.png").exists() for i in sess["items"]))
        check("caption sidecar is present",
              all((s01 / "projectA" / i["anon_id"] / "text.json").exists() for i in sess["items"]))
        check("session materials carry no machine output",
              not list((s01 / "projectA").glob("**/panelDetection*"))
              and not list((s01 / "projectA").glob("**/*pred*")))
        check("worksheet written", (s01 / "A-WORKSHEET.md").exists())

        # --- ordering gate: S02 cannot be built before S01 is sealed ---
        r = run(["prepare_session.py", "build", "S02"], tmp, expect_fail=True)
        check("a later session is blocked until the previous is sealed",
              "not ingested" in r.stderr or "prerequisites" in r.stderr)

        # --- blinding: a poisoned Stage A export is refused at build-b ---
        a0, a1 = [i["anon_id"] for i in sess["items"]]
        fake_stage_a(s01, a0, sess["items"][0]["pageW"], sess["items"][0]["pageH"], poisoned=True)
        fake_stage_a(s01, a1, sess["items"][1]["pageW"], sess["items"][1]["pageH"])
        r = run(["prepare_session.py", "build-b", "S01"], tmp, expect_fail=True)
        check("detector fingerprints in an export are REFUSED",
              "blinding violated" in r.stderr and "panelDetection" in r.stderr)

        # --- clean export -> Stage B ---
        fake_stage_a(s01, a0, sess["items"][0]["pageW"], sess["items"][0]["pageH"])
        run(["prepare_session.py", "build-b", "S01", "--force"], tmp)
        sb = json.loads((s01 / "sessionB.json").read_text())
        check("one Stage B panel per drawn subfigure", len(sb["items"]) == 4,
              f"{len(sb['items'])} panels")
        check("panels are re-rendered at working magnification",
              all(max(i["panelPx"]) >= 1200 for i in sb["items"]),
              f"long edges {[max(i['panelPx']) for i in sb['items']]}")
        check("Stage B DPI exceeds Stage A DPI", all(i["dpi"] > 200 for i in sb["items"]))
        check("a whole-image figure box is pre-seeded",
              all((s01 / "projectB" / i["panel_item"] / "annotations.json").exists()
                  for i in sb["items"]))
        check("a coding form exists per panel",
              all((s01 / "coding" / f"{i['panel_item']}.form.json").exists() for i in sb["items"]))
        form0 = json.loads((s01 / "coding" / f"{sb['items'][0]['panel_item']}.form.json").read_text())
        check("the coding form ships the tool's live vocabulary",
              "SEM" in form0["_allowed"]["dispersion"] and "control" in form0["_allowed"]["role"])
        check("the coding form starts empty (nothing pre-answered)",
              form0["charType"] is None and form0["dispersion"]["type"] is None)

        # --- rater fills forms + digitizes ---
        for i in sb["items"]:
            fill_form(s01 / "coding" / f"{i['panel_item']}.form.json")
            fake_stage_b(s01, i["panel_item"])

        # --- an incomplete form must block ingest ---
        bad = s01 / "coding" / f"{sb['items'][0]['panel_item']}.form.json"
        keep = bad.read_text()
        f = json.loads(keep); f["series"][1]["role"] = None; bad.write_text(json.dumps(f))
        r = run(["ingest_annotations.py", "ingest", "S01"], tmp, expect_fail=True)
        check("an unassigned arm role blocks ingest", "silent catastrophic" in r.stderr)
        bad.write_text(keep)

        # --- ingest ---
        run(["ingest_annotations.py", "ingest", "S01"], tmp)
        gt = tmp / "gt" / "S01"
        csv = (gt / "figure-derived-landmarks.csv").read_bytes().decode("utf-8")
        head = csv.split("\r\n")[0]
        html = (HERE.parent.parent / "figure-extractor.html").read_text(errors="replace")
        import re
        want = ",".join(re.findall(r"'([^']+)'", re.search(
            r"const LANDMARK_HEADER\s*=\s*\[(.*?)\];", html, re.S).group(1)))
        check("CSV header is byte-identical to the tool's LANDMARK_HEADER", head == want)
        check("CSV uses CRLF", "\r\n" in csv)
        rows = csv.split("\r\n")[1:]
        check("one CSV row per bar per panel", len(rows) == 8, f"{len(rows)} rows")
        check("dispersion TYPE is carried", all('"SEM"' in r for r in rows))
        check("arm labels are carried", sum('"Control"' in r for r in rows) == 4)
        gt_files = sorted(gt.glob("*/annotations.json"))
        check("one GT file per FIGURE, not per panel", len(gt_files) == 2,
              f"{len(gt_files)} files for 2 figures / 4 panels")
        ann = json.loads(gt_files[0].read_text())
        check("GT annotations.json is schema v2", ann["schemaVersion"] == 2)
        fg = ann["figures"][0]
        check("panels are carried as subfigures (the tool's own model)",
              len(fg["subfigures"]) == 2 and fg["subfigures"][0]["label"].endswith("A"))
        sub = fg["subfigures"][0]
        check("GT record carries characterization + extraction on the panel",
              sub["characterization"]["panels"][0]["charType"] == "bar"
              and sub["extraction"]["method"] == "bar-endpoints")
        check("the panel bbox from Stage A survives", set(sub["bounds"]) ==
              {"x", "y", "width", "height"})
        check("the Stage B coordinate space is recorded",
              sub["digitization"]["renderSpace"]["stage"] == "B")
        check("extraction priority matches the tool's routing",
              sub["extraction"]["priority"] == "high")
        check("provenance fields match the tool's",
              sub["extraction"]["Data_Source"] == "figure"
              and sub["extraction"]["figure_derived"] is True)
        mean0 = sub["extraction"]["groups"][0]["mean"]
        check("mean recovers through the tool's affine",
              abs(mean0 - (1500 - 900) / (1500 - 200) * 30) < 1e-6, f"{mean0:.4f}")
        pj = [json.loads(l) for l in (gt / "panels_gt.jsonl").read_text().splitlines()]
        check("panel GT is in benchmark/panels prediction shape",
              pj and set(pj[0]["panels"][0]["bbox"]) == {"x", "y", "width", "height"}
              and pj[0]["panels"][0]["label"] == "A")
        sys.path.insert(0, str(HERE))
        try:
            import score_real_validation as srv
            recs = srv.normalize_annotations(json.loads(gt_files[0].read_text()))
            check("the sibling scorer normalizes this GT",
                  bool(recs) and recs[0]["nPanels"] == 2
                  and recs[0]["panels"][0]["chartType"] == "bar"
                  and len(recs[0]["panels"][0]["landmarks"]) == 2,
                  f"{recs[0]['nPanels'] if recs else 0} panels")
        except ImportError:
            print("  SKIP  sibling scorer not present")

        seal = json.loads((gt / "seal.json").read_text())
        check("session is sealed with a timestamp and hashes",
              seal["sealedAt"] and len(seal["files"]) > 4)

        run(["ingest_annotations.py", "verify-seal"], tmp)
        (gt / "figure-derived-landmarks.csv").write_bytes((csv + "\r\n\"tampered\"").encode())
        r = run(["ingest_annotations.py", "verify-seal"], tmp, expect_fail=True)
        check("seal detects a modified artifact", "TAMPERED" in r.stdout)
        (gt / "figure-derived-landmarks.csv").write_bytes(csv.encode())

        run(["ingest_annotations.py", "audit", "--session", "S01"], tmp)
        audit = (tmp / "gt" / "audit-S01.md").read_text()
        check("audit reports both channels",
              "central" in audit and "dispersion" in audit and "Zoom discipline" in audit)
        check("audit reports the abstention count", "recorded ambiguities" in audit)

        # --- a repeat session, with jittered clicks, then the intra-rater report ---
        repsess = [s["session"] for s in key["sessions"] if s["isRepeatSession"]]
        check("the plan schedules repeat sessions", bool(repsess))
        rs = repsess[0]
        r = run(["prepare_session.py", "build", rs], tmp, expect_fail=True)
        check("a repeat is blocked until the calendar gap has passed",
              "wait" in r.stderr or "not sealed" in r.stderr or "rest" in r.stderr)
        run(["prepare_session.py", "build", rs, "--force"], tmp)
        rsd = tmp / "sessions" / rs
        rsess = json.loads((rsd / "session.json").read_text())
        for i in rsess["items"]:
            fake_stage_a(rsd, i["anon_id"], i["pageW"], i["pageH"])
        run(["prepare_session.py", "build-b", rs, "--force"], tmp)
        rsb = json.loads((rsd / "sessionB.json").read_text())
        for i in rsb["items"]:
            fill_form(rsd / "coding" / f"{i['panel_item']}.form.json")
            fake_stage_b(rsd, i["panel_item"], jitter=3.0)   # a realistic re-read slip
        run(["ingest_annotations.py", "ingest", rs], tmp)
        run(["ingest_annotations.py", "intra"], tmp)
        intra = json.loads((tmp / "gt" / "intra_rater.json").read_text())
        check("intra-rater pairs the two reads", intra["nPairs"] >= 1, f"{intra['nPairs']} pairs")
        check("semantic channels agree across reads",
              intra["categorical"]["charType"]["agreement"] == 100.0)
        num = intra["numeric"]
        check("dispersion is less repeatable than central tendency",
              num["dispersion"]["median_pct"] > num["central"]["median_pct"],
              f"central {num['central']['median_pct']}% vs dispersion "
              f"{num['dispersion']['median_pct']}%")
        check("a repeatability coefficient is reported for dispersion",
              num["dispersion"]["rc_pct"] > 0, f"RC = {num['dispersion']['rc_pct']}%")
        check("intra-rater markdown written", (tmp / "gt" / "intra-rater.md").exists())

        run(["prepare_session.py", "status"], tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILURE(S): " + "; ".join(FAILED))
        return 1
    print("end-to-end OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
