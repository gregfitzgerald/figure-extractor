#!/usr/bin/env python3
"""caption_corpus.py -- a REAL-journal caption corpus for the panel-caption parser, and a
harness that scores the live parser against it in the browser.

WHY
---
`expectedPanelsFromCaption` is the load-bearing input to panel detection: withhold the
caption and exact-count collapses from 80.5% to 7.3% on synthetic figures. It was only ever
exercised against captions written by the same R script that drew the figures, where it
fails on 7.3% of cases. Measured against 71 real journal captions it finds no usable letter
run on 50.7% -- and 31 of those 36 misses go straight to abstention. That single function is
why real-figure panel detection abstains on 93% of figures.

This corpus makes that measurable and regression-proof. It reads captions out of the
real-validation worklist (real captions, from real papers) and pairs each with the letters
the worklist says that figure has.

EPISTEMIC STATUS OF THE LABELS -- read before trusting any number here
---------------------------------------------------------------------
`caption_expected_letters` in worklist.json has UNRECORDED PROVENANCE: it is consumed by
scripts but produced by none, and a plain parenthesised-letter regex reproduces it on only
37/71 items. It is therefore an UNVALIDATED COMPARATOR, not ground truth. What this harness
measures honestly is:

  * PARSE RATE -- does the parser return a letter run at all? This needs no labels and is
    exact. It is the number that matters, because a null goes straight to abstention.
  * DISAGREEMENT -- when the parser returns a run AND the worklist has an expectation, do
    they differ? A disagreement is a candidate SILENT ERROR and must be inspected by hand.
    Zero disagreements is the property to preserve. The live run currently prints ONE
    (Hullinger2015_F4): the parser reads a-f, the worklist claims 8 panels. Root cause is
    input truncation, not the parser -- even the refetched caption ends mid-sentence at
    "(F) MPEP does not diminish the synaptic" -- but it is a live undercount input class
    and it must be inspected, not assumed away.

Never report agreement-with-the-worklist as accuracy. The worklist is not a gold standard.

USAGE
-----
    python3 caption_corpus.py --build          # write out/caption_corpus.json
    python3 caption_corpus.py --score          # score the live parser in chromium
    python3 caption_corpus.py --score --show-misses
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
WORKLIST = REPO / "benchmark" / "real-validation" / "worklist.json"
OUT = HERE / "out" / "caption_corpus.json"

# Hand-written cases distilled from the real misses, each a FORM the parser must eventually
# handle. These carry an explicit `expect` because the form -- not a worklist label -- is the
# thing under test. Sources are named so each can be checked against the actual paper.
FORMS = [
    {"id": "form_noun_marker", "source": "Baraldi2013 F1",
     "caption": "Figure 1. Novel object recognition at 2 months of age (A), 5 months of age (B), "
                "and 12 months of age (C). Data are mean +/- SEM.",
     "expect": None, "status": "open",
     "why": "KNOWN OPEN. Markers follow a noun, not clause punctuation. A relaxed pass that "
            "accepted these was tried and REVERTED: it was worth 4.2pp of parse rate and "
            "invented panels from twelve classes of ordinary prose, most damagingly the "
            "significance-letter convention ('bars with different letters (a-c) differ'), "
            "which is ubiquitous in this corpus. Abstaining is safe; inventing a panel count "
            "is not, because the count is a hard constraint on the geometry."},
    {"id": "form_no_open_paren", "source": "Morgan2018 F7",
     "caption": "Figure 7. Latency to platform in A), Y mice B), M mice, and C) O mice.",
     "expect": None, "status": "open",
     "why": "KNOWN OPEN. Closing paren only; the scanner requires a balanced (X). Recognising "
            "bare `A)` markers risks colliding with outline numbering and reference lists, and "
            "this shape is 4 of 71 real captions -- not worth the false-positive risk without a "
            "corroborating signal from the figure geometry. Abstains today, which is safe."},
    {"id": "form_prose_enumeration", "source": "Harburger2007b F3",
     "caption": "Figure 3. Performance for young (A and E), middle-aged (B and F), "
                "and aged (C and G) mice.",
     "expect": None,
     "why": "GENUINELY AMBIGUOUS in reading order -- a,e then b,f is not ascending. Must stay "
            "null; recovering this would require guessing the panel layout"},
    {"id": "form_bare_letters", "source": "Gattas2022 F4",
     "caption": "Figure 4. a, Task schematic. ai, Trial timeline. aii, Response window. "
                "b, Accuracy across sessions.",
     "expect": None,
     "why": "bare markers with roman sub-indices; 'ai'/'aii' are not single letters and the "
            "run a,a,a,b does not ascend"},
    {"id": "form_hierarchical", "source": "Lee2024 F2",
     "caption": "Figure 2. (A-a) Baseline. (A-b) After training. (B) Control group. "
                "(C-a) Probe trial.",
     "expect": None,
     "why": "hierarchical labels; (A-a) is not a range and the top-level run repeats"},
    {"id": "form_primes", "source": "Chrusch2023 F2",
     "caption": "Figure 2. (A) Sham condition. (A') Magnified view. (B) Lesion condition. "
                "(B') Magnified view.",
     "expect": None,
     "why": "primes make the run non-increasing -> ambiguous -> null"},
    # Controls: forms the parser already handles. If a change breaks these it is a regression.
    {"id": "ctrl_canonical", "source": "synthetic",
     "caption": "Figure 1. (A) Control group. (B) Running group. (C) Enriched group.",
     "expect": ["a", "b", "c"], "why": "canonical form -- must never break"},
    {"id": "ctrl_range", "source": "synthetic",
     "caption": "Figure 2A-D shows the behavioural battery.",
     "expect": ["a", "b", "c", "d"], "why": "range welded to the figure number"},
    {"id": "ctrl_group", "source": "synthetic",
     "caption": "Figure 3. (A) Baseline. (B,C) Both training phases. (D) Probe.",
     "expect": ["a", "b", "c", "d"], "why": "grouped marker"},
    {"id": "ctrl_citation_three", "source": "adversarial",
     "caption": "Figure 6. Consistent with earlier reports (A), later work (B), and a "
                "replication (C), enrichment improved recall.",
     "expect": None,
     "why": "THREE citation letters in prose. The relaxed pass is gated at >=3 markers, and "
            "prose cites three things as readily as two -- so the threshold alone does not "
            "separate a citation list from a panel list. Found by adversarial probing AFTER "
            "the relaxed pass shipped: this produced three panels out of nothing. A wrong "
            "panel count is handed to the geometry as a hard constraint, so inventing panels "
            "is worse than missing them."},
    {"id": "ctrl_as_previously_shown", "source": "adversarial",
     "caption": "Figure 6b. As previously shown (A), and in related work (B), and a "
                "replication (C), recall improved.",
     "expect": None, "why": "same class, different reference phrasing"},
    {"id": "ctrl_stats_parens", "source": "adversarial",
     "caption": "Figure 5. Performance differed by group (P < 0.05), with a main effect of "
                "housing (F1,50 = 5.24, P = 0.026) and no interaction (P = 0.963).",
     "expect": None, "why": "statistical parentheticals must never read as panel markers"},
    {"id": "ctrl_unit_abbrevs", "source": "adversarial",
     "caption": "Figure 8. Standard housing (S), isolated (I), and enriched (E) groups were "
                "compared.",
     "expect": None,
     "why": "three single-letter GROUP abbreviations in a row -- shaped exactly like a panel "
            "run but not starting at 'a'"},
    {"id": "ctrl_panels_with_stats", "source": "adversarial",
     "caption": "Figure 11. (A) Latency (P < 0.05). (B) Path length (n = 8). (C) Speed (cm/s).",
     "expect": ["a", "b", "c"],
     "why": "real panels INTERLEAVED with statistical parentheticals -- must still parse, or "
            "the fix for the false positives would have cost the true positives"},
    {"id": "ctrl_working_memory", "source": "adversarial",
     "caption": "Figure 12. Working memory at 2 months (A), 5 months (B), and 12 months (C).",
     "expect": None, "status": "open",
     "why": "KNOWN OPEN, same class as form_noun_marker. Real panels, but the markers attach "
            "to a noun rather than to punctuation. Only the reverted relaxed pass read these; "
            "abstaining costs coverage and is safe."},
    # False-positive battery. Every one of these parsed as panels under the reverted relaxed
    # pass. They are ordinary caption prose, and inventing a panel count from them hands the
    # geometry a hard constraint that is simply wrong -- strictly worse than abstaining.
    {"id": "fp_sig_letters_range", "source": "adversarial",
     "caption": "Bars with different letters (a-c) indicate significant differences (P < 0.05).",
     "expect": None,
     "why": "THE killer class. Tukey/Duncan significance-letter conventions are ubiquitous in "
            "animal-study bar charts -- this tool's exact target -- and the letters are also "
            "DRAWN in the figure, so the glyph finder corroborates the invention. A one-panel "
            "bar chart with this caption was split into 3 'verified' panels at conf 0.79."},
    {"id": "fp_sig_letters_list", "source": "adversarial",
     "caption": "Columns with different letters (a, b, c) differ significantly at P < 0.05 (Tukey HSD).",
     "expect": None, "why": "same convention, list form"},
    {"id": "fp_sig_upper", "source": "adversarial",
     "caption": "Different uppercase letters (A-C) denote differences among diets.",
     "expect": None, "why": "same convention, uppercase range -- one token yields three letters"},
    {"id": "fp_lane_enum", "source": "adversarial",
     "caption": "Lane (a) marker, (b) control, (c) treated cells, (d) knockout.",
     "expect": None, "why": "gel LANES enumerated like panels; a real 4-way enumeration of "
                            "something that is not panels"},
    {"id": "fp_hypotheses", "source": "adversarial",
     "caption": "We tested whether (a) latency increased, (b) amplitude decreased, and (c) speed fell.",
     "expect": None, "why": "enumerated hypotheses -- prose produces (a)(b)(c) runs routinely"},
    {"id": "fp_criteria", "source": "adversarial",
     "caption": "Animals were excluded if (a) they failed the cue test, (b) they were ill, or (c) data were lost.",
     "expect": None, "why": "enumerated criteria, same shape"},
    {"id": "fp_citation_multi", "source": "adversarial",
     "caption": "Reconstruction follows the method of Smith (a), Jones (b), and Lee (c).",
     "expect": None, "why": "author-letter citations"},
    {"id": "ctrl_citation_poison", "source": "synthetic",
     "caption": "Figure 4. As reported previously (A) and in related work (B), performance "
                "improved. See Smith et al. (2019) for details.",
     "expect": None,
     "why": "citation-shaped; must NOT be read as panels. A silent error here is the worst "
            "outcome available to this function"},
]


def build():
    wl = json.loads(WORKLIST.read_text())
    items = wl.get("items") or wl.get("worklist") or []
    # Prefer full PDF-extracted captions over the worklist's truncated copies -- see
    # refetch_captions.py. Measuring a parser against mutilated input measures the corpus.
    full = HERE / "out" / "captions_full.json"
    by_id = ({c["id"]: c["full"] for c in json.loads(full.read_text())["captions"]}
             if full.exists() else {})
    if by_id:
        print(f"[captions] full PDF captions available for {len(by_id)} items")
    recs = []
    for it in items:
        cap = (it.get("caption") or "").strip()
        wl_cap = cap
        full_cap = by_id.get(it["item_id"])
        if full_cap and len(full_cap) > len(cap):
            cap = full_cap
        if not cap:
            continue
        recs.append({
            "id": it["item_id"],
            "source": "pdf-full" if cap is not wl_cap else "worklist",
            "caption": cap,
            "captionWorklist": wl_cap,
            "captionTruncatedInWorklist": bool(full_cap and len(full_cap) > len(wl_cap)),
            # UNVALIDATED comparator -- see the module docstring.
            "worklistLetters": it.get("caption_expected_letters"),
            "worklistLetterCount": it.get("caption_letter_count"),
            "tiles": it.get("visual_tile_count_survey"),
            "letterTileMismatch": it.get("letter_tile_mismatch"),
            "tier": it.get("tier"),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schemaVersion": 1,
               "note": "worklistLetters has UNRECORDED provenance -- unvalidated comparator, "
                       "never an accuracy denominator. See module docstring.",
               "forms": FORMS, "real": recs}
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[written] {OUT}")
    print(f"  {len(recs)} real captions + {len(FORMS)} distilled form cases")
    return payload


JS = r"""
(caps) => caps.map(c => {
  let r = null, err = null;
  try { r = expectedPanelsFromCaption(c.caption); }
  catch (e) { err = String((e && e.message) || e); }
  return { id: c.id, parsed: r ? r.letters : null, count: r ? r.count : null, error: err };
})
"""


def score(show_misses=False):
    if not OUT.exists():
        build()
    data = json.loads(OUT.read_text())
    from playwright.sync_api import sync_playwright
    payload = [{"id": r["id"], "caption": r["caption"]} for r in data["real"]] + \
              [{"id": f["id"], "caption": f["caption"]} for f in data["forms"]]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.goto((REPO / "figure-extractor.html").as_uri())
        pg.wait_for_function("() => typeof expectedPanelsFromCaption === 'function'",
                             timeout=20000)
        res = {x["id"]: x for x in pg.evaluate(JS, payload)}
        b.close()

    real = data["real"]
    parsed = [r for r in real if res[r["id"]]["parsed"]]
    print(f"\nREAL CAPTIONS  n={len(real)}")
    print(f"  parse rate (returns a letter run): {len(parsed)}/{len(real)} "
          f"= {100*len(parsed)/max(1,len(real)):.1f}%")
    print(f"  null (-> abstention):              {len(real)-len(parsed)}/{len(real)} "
          f"= {100*(len(real)-len(parsed))/max(1,len(real)):.1f}%")

    # Disagreements are candidate SILENT ERRORS. This is the number that must stay at zero.
    dis = []
    for r in real:
        got = res[r["id"]]["parsed"]
        exp = r.get("worklistLetters")
        if got and exp:
            e = [str(x).lower() for x in exp] if isinstance(exp, list) else None
            if e and got != e:
                dis.append((r["id"], got, e))
    print(f"  disagreements with the unvalidated comparator: {len(dis)}"
          f"   {'<-- INSPECT EACH BY HAND' if dis else '(none)'}")
    for d in dis[:12]:
        print(f"      {d[0]}: parser {d[1]} vs worklist {d[2]}")

    errs = [r["id"] for r in real if res[r["id"]]["error"]]
    print(f"  exceptions: {len(errs)} {errs[:5] if errs else ''}")

    print(f"\nDISTILLED FORMS  n={len(data['forms'])}")
    ok = 0
    for f in data["forms"]:
        got = res[f["id"]]["parsed"]
        want = f["expect"]
        good = (got == want)
        ok += good
        mark = "ok " if good else "MISS"
        print(f"  [{mark}] {f['id']:<24} got={got} want={want}")
        if not good and show_misses:
            print(f"         why: {f['why']}")
            print(f"         cap: {f['caption'][:110]}")
    print(f"\n  forms handled: {ok}/{len(data['forms'])}")
    print("\nNOTE: parse rate is exact and needs no labels. Agreement with the worklist is NOT "
          "accuracy -- that column has unrecorded provenance. Disagreements are the signal.")
    return 0


def test():
    """Regression gate. Fails on the two things that must never come back.

    1. Any distilled FORM regressing -- especially the controls. `ctrl_citation_poison` is the
       one that matters most: reading citation letters as panels would invent panels out of
       prose, and the relaxed second pass is exactly the change that could cause it.
    2. Any real caption where the parser returns MORE letters than it did at the baseline is
       fine; returning a SHORT run for a caption whose markers it can see is the undercount
       failure, and that is what the form cases pin down.

    Parse RATE is deliberately not asserted. It is a quality metric that should move, and
    freezing it would punish honest improvements; the forms pin the behaviour instead.
    """
    if not OUT.exists():
        build()
    data = json.loads(OUT.read_text())
    from playwright.sync_api import sync_playwright
    payload = [{"id": f["id"], "caption": f["caption"]} for f in data["forms"]]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.goto((REPO / "figure-extractor.html").as_uri())
        pg.wait_for_function("() => typeof expectedPanelsFromCaption === 'function'",
                             timeout=20000)
        res = {x["id"]: x for x in pg.evaluate(JS, payload)}
        b.close()
    fails = []
    for f in data["forms"]:
        got, want = res[f["id"]]["parsed"], f["expect"]
        ok = (got == want)
        tag = 'ok ' if ok else ('open' if f.get('status') == 'open' else 'FAIL')
        print(f"  [{tag}] {f['id']:<24} got={got} want={want}")
        if not ok and f.get('status') == 'open':
            continue
        if not ok:
            fails.append(f"{f['id']}: got {got}, want {want}")
        if res[f["id"]]["error"]:
            fails.append(f"{f['id']}: exception {res[f['id']]['error']}")
    print("\ncaption-parser regression: PASS" if not fails
          else f"\ncaption-parser regression: {len(fails)} FAILURE(S)")
    for x in fails:
        print("  !", x)
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--test", action="store_true", help="regression gate (exit 1 on failure)")
    ap.add_argument("--show-misses", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
        return 0
    if a.test:
        return test()
    if a.score:
        return score(a.show_misses)
    ap.error("pass --build, --score or --test")


if __name__ == "__main__":
    sys.exit(main())
