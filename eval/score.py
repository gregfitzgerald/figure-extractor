#!/usr/bin/env python3
"""Score agent classifications against ground truth.
Compares eval/results/<id>.json (and optionally eval/results_imgonly/<id>.json) to
eval/charts/<id>.json on: chart type, extract/skip decision, dispersion type."""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
CH = ROOT / "charts"


def load(p):
    try:
        return json.loads(pathlib.Path(p).read_text())
    except Exception:
        return None


def score(results_dir, label):
    gts = sorted(p for p in CH.glob("*.json") if p.name != "manifest.json")
    rows, tt = [], {"type": [0, 0], "decision": [0, 0], "disp": [0, 0], "flag-recall": [0, 0], "provenance": [0, 0]}
    for gp in gts:
        gt = json.loads(gp.read_text())
        rid = gt["id"]
        r = load(pathlib.Path(results_dir) / f"{rid}.json")
        if r is None:
            rows.append((rid, gt["charType"], "MISSING", "", "", "", "")); continue
        t_ok = (r.get("charType") == gt["charType"])
        d_ok = (r.get("extractDecision") == gt["extractDecision"])
        tt["type"][0] += t_ok; tt["type"][1] += 1
        tt["decision"][0] += d_ok; tt["decision"][1] += 1
        gt_disp = gt.get("dispersionType")
        disp_note = ""
        if gt_disp:
            di_ok = (str(r.get("dispersionType", "")).upper() == str(gt_disp).upper())
            tt["disp"][0] += di_ok; tt["disp"][1] += 1
            disp_note = f"{r.get('dispersionType')}~{gt_disp}{'✓' if di_ok else '✗'}"
        # flag recall: did the prediction include each ground-truth flag?
        gt_flags = set(gt.get("flags", []))
        pred_flags = set(f for f in (r.get("flags") or []))
        flag_note = ""
        if gt_flags:
            hit = len(gt_flags & pred_flags)
            tt["flag-recall"][0] += hit; tt["flag-recall"][1] += len(gt_flags)
            flag_note = f"flags {sorted(gt_flags)}{'✓' if gt_flags <= pred_flags else '✗ got '+str(sorted(pred_flags))}"
        # data provenance (primary vs derived) — only graded where GT specifies primary/derived
        gt_prov = gt.get("dataProvenance")
        prov_note = ""
        if gt_prov in ("primary", "derived"):
            pv_ok = (r.get("dataProvenance") == gt_prov)
            tt["provenance"][0] += pv_ok; tt["provenance"][1] += 1
            prov_note = f"{r.get('dataProvenance')}~{gt_prov}{'✓' if pv_ok else '✗'}"
        rows.append((rid, gt["charType"], r.get("charType"), "✓" if t_ok else "✗",
                     f"{r.get('extractDecision')}~{gt['extractDecision']}{'✓' if d_ok else '✗'}",
                     disp_note, (flag_note + " " + prov_note).strip()))

    print(f"\n===== {label} =====")
    print(f"{'id':20s} {'gt type':13s} {'pred type':13s} {'':2s} {'decision':20s} {'dispersion':16s} flags")
    for rid, gtt, pt, ok, dec, disp, fl in rows:
        print(f"{rid:20s} {gtt:13s} {str(pt):13s} {ok:2s} {dec:20s} {disp:16s} {fl}")
    for k, (c, n) in tt.items():
        if n:
            print(f"  {k:11s} {c}/{n} = {100*c/n:.0f}%")
    return tt


if __name__ == "__main__":
    score(ROOT / "results", "WITH ARTICLE CONTEXT")
    if (ROOT / "results_imgonly").exists() and any((ROOT / "results_imgonly").glob("*.json")):
        score(ROOT / "results_imgonly", "IMAGE ONLY (no caption/criteria)")
