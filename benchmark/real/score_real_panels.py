#!/usr/bin/env python3
"""score_real_panels.py -- report what run_real_panels.py measured, with epistemic labels.

EPISTEMIC STATUS OF EVERY COMPARATOR USED HERE
----------------------------------------------
There is NO panel-level ground truth for the 71 worklist figures. Nobody has drawn the
boxes. Three quantities get compared against the detector, and none of them is truth:

  caption_letter_count / caption_expected_letters
      UNRECORDED PROVENANCE. worklist.json names a prose doc as its `generator`; no
      producing script exists in the repo or anywhere in git history, and
      SAMPLING-AND-WORKLIST.md declares the survey scripts "working files, not
      deliverables". The values are not reproducible by a plain parenthesised-letter
      regex (37/71 match). They also answer a DIFFERENT question from panel count: they
      are what the caption ENUMERATES, and 19/71 items are flagged `letter_tile_mismatch`
      precisely because that is not the number of visible tiles.
      -> usable as a CAPTION-PARSE reference, not as a panel-count reference.

  visual_tile_count_survey
      UNRECORDED PROVENANCE, NO STORED SUBSTRATE. Same absent generator; and unlike the
      letters there is no source string to re-derive it from. ANALYSIS-PLAN.md calls it
      only "what a survey of the rendered figure counted", agent unnamed. It is closer to
      the thing we want to measure than the caption count is, but scoring a machine
      against a possibly-machine-derived reference is circular.
      -> UNVALIDATED COMPARATOR. Every number computed against it is labelled [UNVAL].

  the detector's own caption parse (res.expected)
      Machine. Compared against caption_expected_letters only to characterise the parser.

WHAT IS ACTUALLY MEASURED WITHOUT A REFERENCE (and is therefore solid):
  crash rate, exception rate, timing, abstention rate, which method fires, flag mix,
  and BBOX SENSITIVITY -- how much the emitted count moves when only the figure box
  changes. Sensitivity needs no ground truth: it is a self-consistency property.

Usage:  python3 benchmark/real/score_real_panels.py [--in benchmark/real/out/panels_real.json]
                                                    [--nocaption <json>]
"""
import argparse, collections, json, pathlib, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
POLS = ["fullpage", "capband", "cluster", "xobject"]


def load(p):
    return json.loads(pathlib.Path(p).read_text())


def res_of(rec, pol):
    P = (rec.get("policies") or {}).get(pol)
    return (P or {}).get("result") or {"status": "missing"}


def h(t):
    print("\n" + t)
    print("-" * len(t))


def pct(k, n):
    return f"{k}/{n} = {100.0*k/n:5.1f}%" if n else f"{k}/0 = n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(HERE / "out" / "panels_real.json"))
    ap.add_argument("--nocaption", default=str(HERE / "out" / "panels_real_nocaption.json"))
    a = ap.parse_args()
    D = load(a.inp)
    R = D["records"]
    N = len(R)
    print(f"=== detectPanelsCore on REAL journal figures ===")
    print(f"source     : {a.inp}")
    print(f"tool       : {D['tool']}")
    print(f"render     : {D['dpi']} dpi, caption {'GIVEN' if D['caption_given'] else 'WITHHELD'}")
    print(f"figures    : {N}   (articles: {len({r['article'] for r in R})})")
    print(f"page JS errors: {len(D.get('page_js_errors') or [])}")

    # ---------------- 1. things that need no ground truth ----------------
    h("1. RELIABILITY -- no ground truth needed, these are facts about the run")
    for pol in POLS:
        st = collections.Counter(res_of(r, pol)["status"] for r in R)
        ok = [r for r in R if res_of(r, pol)["status"] == "ok"]
        ms = [res_of(r, pol)["ms"] for r in ok]
        print(f"  {pol:9} ran={st['ok']:3}  no-bbox={st['no-bbox']:3}  "
              f"EXCEPTION={st['exception']:3}  "
              f"median={statistics.median(ms):7.1f}ms  p90={sorted(ms)[int(.9*len(ms))]:8.1f}ms  "
              f"max={max(ms):8.1f}ms" if ms else f"  {pol:9} {dict(st)}")

    h("2. ABSTENTION -- the tool's own refusal gate (count<2 or conf<0.35 or ok==False)")
    print("   'abstain' means the tool declined to be trusted. It is NOT an error.")
    for pol in POLS:
        ok = [r for r in R if res_of(r, pol)["status"] == "ok"]
        ab = [r for r in ok if res_of(r, pol)["abstain"]]
        nok = [r for r in ok if not res_of(r, pol)["tool_ok"]]
        print(f"  {pol:9} n={len(ok):3}  abstain={pct(len(ab),len(ok))}   "
              f"ok==False={pct(len(nok),len(ok))}")

    h("3. METHOD MIX -- which cascade stage fired (real vs the synthetic benchmark)")
    for pol in POLS:
        ok = [r for r in R if res_of(r, pol)["status"] == "ok"]
        c = collections.Counter(res_of(r, pol)["method"] for r in ok)
        print(f"  {pol:9} " + "  ".join(f"{k}={v}" for k, v in c.most_common()))

    h("4. FLAGS raised (cluster policy), most common first")
    c = collections.Counter()
    for r in R:
        for f in res_of(r, "cluster").get("flags", []):
            c[f] += 1
    for k, v in c.most_common():
        print(f"  {v:3}  {k}")

    # ---------------- 5. bbox sensitivity ----------------
    h("5. BBOX SENSITIVITY -- how much the answer moves when ONLY the figure box changes")
    print("   Needs no ground truth. A count that swings with the box is a property of the")
    print("   boxing heuristic, not of the detector.")
    both = []
    for r in R:
        v = {p: res_of(r, p) for p in POLS}
        cnts = {p: v[p].get("count") for p in POLS if v[p]["status"] == "ok"}
        if len(cnts) >= 2:
            both.append((r["item_id"], cnts))
    agree_all = sum(1 for _, c in both if len(set(c.values())) == 1)
    print(f"  figures with >=2 policies runnable : {len(both)}")
    print(f"  all runnable policies agree on N   : {pct(agree_all, len(both))}")
    spread = [max(c.values()) - min(c.values()) for _, c in both]
    print(f"  spread max-min over policies       : median={statistics.median(spread)}  "
          f"mean={statistics.mean(spread):.2f}  max={max(spread)}")
    for pa, pb in (("cluster", "xobject"), ("cluster", "capband"), ("cluster", "fullpage")):
        pair = [(r["item_id"], res_of(r, pa)["count"], res_of(r, pb)["count"]) for r in R
                if res_of(r, pa)["status"] == "ok" and res_of(r, pb)["status"] == "ok"]
        same = sum(1 for _, x, y in pair if x == y)
        print(f"  {pa:8} vs {pb:8} same count: {pct(same, len(pair))}")
    print("\n  worst swings (cluster vs xobject, both runnable):")
    sw = sorted([(abs(res_of(r, 'cluster')['count'] - res_of(r, 'xobject')['count']),
                  r['item_id'], res_of(r, 'cluster')['count'], res_of(r, 'xobject')['count'],
                  r['caption_letter_count'], r['visual_tile_count_survey'])
                 for r in R if res_of(r, 'cluster')['status'] == 'ok'
                 and res_of(r, 'xobject')['status'] == 'ok'], reverse=True)[:8]
    for d, iid, c1, c2, cl, tl in sw:
        print(f"    {iid:<24} cluster={c1:<3} xobject={c2:<3} (delta {d})   "
              f"[caption={cl} tiles={tl}]")

    # ---------------- 6. bbox quality ----------------
    h("6. FIGURE-BBOX QUALITY -- the input every count above depends on")
    print("   The tool's real figure boxing is MANUAL. These boxes are machine-derived.")
    print("   Flags are DEFECT DETECTORS: no flag means no defect DETECTED, not 'correct'.")
    for pol in POLS:
        got = [r for r in R if (r["policies"].get(pol) or {}).get("bbox_px")]
        fc = sum(1 for r in got
                 if (r["policies"][pol].get("contamination") or {}).get("foreign_caption"))
        pl = sum(1 for r in got
                 if (r["policies"][pol].get("contamination") or {}).get("n_prose_lines", 0) >= 3)
        clean = sum(1 for r in got if not r["policies"][pol]["bbox_flags"])
        print(f"  {pol:9} box produced={len(got):3}/{N}   contains ANOTHER figure's caption="
              f"{fc:3}   >=3 prose lines={pl:3}   no-defect-detected={clean:3}")

    # ---------------- 7. comparators ----------------
    h("7. AGREEMENT WITH THE TWO WORKLIST COMPARATORS -- NEITHER IS GROUND TRUTH")
    print("   [CAP]   vs caption_letter_count      -- unrecorded provenance; measures a")
    print("           DIFFERENT quantity (what the caption enumerates, not visible tiles)")
    print("   [UNVAL] vs visual_tile_count_survey  -- unrecorded provenance, no stored")
    print("           substrate to re-derive from; possibly machine-generated => circular")
    for pol in POLS:
        ok = [r for r in R if res_of(r, pol)["status"] == "ok"]
        cap = [r for r in ok if (r["caption_letter_count"] or 0) >= 2]
        capX = sum(1 for r in cap if res_of(r, pol)["count"] == r["caption_letter_count"])
        til = [r for r in ok if (r["visual_tile_count_survey"] or 0) >= 1]
        tilX = sum(1 for r in til if res_of(r, pol)["count"] == r["visual_tile_count_survey"])
        til1 = sum(1 for r in til
                   if abs(res_of(r, pol)["count"] - r["visual_tile_count_survey"]) <= 1)
        print(f"  {pol:9} [CAP] exact {pct(capX,len(cap)):>18}    "
              f"[UNVAL] tiles exact {pct(tilX,len(til)):>18}   within+-1 {pct(til1,len(til)):>18}")

    h("7b. SAME, RESTRICTED TO THE SUBSET WHERE THE BOX IS LEAST SUSPECT")
    print("    (policy 'xobject': the box is the PDF's own image placement rectangle, read")
    print("     out of the content stream, and no contamination defect was detected on any")
    print("     of them. Available only for flattened-raster figures.)")
    ok = [r for r in R if res_of(r, "xobject")["status"] == "ok"]
    cap = [r for r in ok if (r["caption_letter_count"] or 0) >= 2]
    til = [r for r in ok if (r["visual_tile_count_survey"] or 0) >= 1]
    print(f"    n={len(ok)}   [CAP] exact "
          f"{pct(sum(1 for r in cap if res_of(r,'xobject')['count']==r['caption_letter_count']), len(cap))}"
          f"   [UNVAL] tiles exact "
          f"{pct(sum(1 for r in til if res_of(r,'xobject')['count']==r['visual_tile_count_survey']), len(til))}")
    nomis = [r for r in til if not r["letter_tile_mismatch"]]
    print(f"    of those, letter_tile_mismatch==False (n={len(nomis)}): [UNVAL] tiles exact "
          f"{pct(sum(1 for r in nomis if res_of(r,'xobject')['count']==r['visual_tile_count_survey']), len(nomis))}")

    h("8. DOES THE CAPTION PARSER AGREE WITH THE WORKLIST'S LETTERS? (machine vs machine)")
    print("   detectPanelsCore's expectedPanelsFromCaption vs worklist caption_expected_letters.")
    same = diff = nolet = 0
    ex = []
    for r in R:
        v = res_of(r, "cluster")
        if v["status"] != "ok":
            v = res_of(r, "fullpage")
        if v["status"] != "ok":
            continue
        got = [c.lower() for c in (v["expected_from_caption"].get("letters") or [])]
        want = [c.lower() for c in (r["caption_expected_letters"] or [])]
        if not got:
            nolet += 1
            if want:
                ex.append((r["item_id"], "tool-parsed-nothing", want))
        elif got == want:
            same += 1
        else:
            diff += 1
            ex.append((r["item_id"], "".join(got), "".join(want)))
    print(f"  identical letter set : {pct(same, N)}")
    print(f"  tool found NO usable letter run : {pct(nolet, N)}")
    print(f"  disagreed            : {pct(diff, N)}")
    for e in ex[:14]:
        print(f"    {e[0]:<24} tool={e[1]!s:<20} worklist={e[2]}")

    h("9. DO ABSTENTIONS CONCENTRATE WHERE THE WORKLIST PREDICTS TROUBLE?")
    print("   letter_tile_mismatch and adversarial_features are worklist tags of unrecorded")
    print("   provenance too, so this tests concordance between two unvalidated signals.")
    for pol in ("cluster", "xobject"):
        ok = [r for r in R if res_of(r, pol)["status"] == "ok"]
        for tag, sel in (("letter_tile_mismatch=True", lambda r: r["letter_tile_mismatch"]),
                         ("letter_tile_mismatch=False", lambda r: not r["letter_tile_mismatch"]),
                         ("has adversarial_features", lambda r: bool(r["adversarial_features"])),
                         ("no adversarial_features", lambda r: not r["adversarial_features"])):
            g = [r for r in ok if sel(r)]
            if not g:
                continue
            ab = sum(1 for r in g if res_of(r, pol)["abstain"])
            print(f"  {pol:9} {tag:<28} abstain {pct(ab, len(g))}")

    # ---------------- 10. ablation ----------------
    p = pathlib.Path(a.nocaption)
    if p.exists():
        h("10. CAPTION ABLATION -- same figures, caption withheld")
        D2 = load(p)
        byid = {r["item_id"]: r for r in D2["records"]}
        for pol in ("cluster", "xobject"):
            pairs = [(r, byid[r["item_id"]]) for r in R if r["item_id"] in byid]
            pairs = [(x, y) for x, y in pairs
                     if res_of(x, pol)["status"] == "ok" and res_of(y, pol)["status"] == "ok"]
            same = sum(1 for x, y in pairs
                       if res_of(x, pol)["count"] == res_of(y, pol)["count"])
            abW = sum(1 for x, y in pairs if res_of(x, pol)["abstain"])
            abN = sum(1 for x, y in pairs if res_of(y, pol)["abstain"])
            print(f"  {pol:9} n={len(pairs):3}  same count with/without caption "
                  f"{pct(same,len(pairs))}   abstain WITH cap {pct(abW,len(pairs))}   "
                  f"WITHOUT {pct(abN,len(pairs))}")
    else:
        print(f"\n(no ablation file at {p})")

    h("BOTTOM LINE")
    ok = [r for r in R if res_of(r, "cluster")["status"] == "ok"]
    trusted = [r for r in ok if not res_of(r, "cluster")["abstain"]]
    print(f"  Of {len(ok)} real figures the detector ran on (cluster box), it produced a")
    print(f"  result it is willing to stand behind on {len(trusted)} "
          f"({100.0*len(trusted)/len(ok):.1f}%).")
    print(f"  Whether those {len(trusted)} are CORRECT is not measurable here: no human has")
    print(f"  drawn a panel box on any of these 71 figures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
