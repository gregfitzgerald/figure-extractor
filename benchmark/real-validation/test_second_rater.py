#!/usr/bin/env python3
"""test_second_rater.py -- drive the SECOND RATER (H2) pipeline end to end on real PDFs.

Same style and the same fixture builders as `test_end_to_end.py`: everything runs in a
temp tree via RV_DATA_DAN, so the repo is untouched. It simulates Dan --
plan -> Stage A materials -> a synthetic Stage A export -> Stage B materials -> filled
coding forms + a synthetic Stage B export -> ingest as H2 -> inter-rater report -- and
asserts the properties the second-rater design actually depends on:

  * a Stage A export WITHOUT `annotationMode: true` is refused, even when it carries no
    detector fingerprints (blinding asserted, not merely un-disproven);
  * the detector fingerprints are still refused on top of that;
  * `pack` refuses to build a handoff archive that would leak a key, a GT store, a coded
    reference, a prediction or a seal;
  * Dan's anon ids neither collide with nor are derivable from Greg's;
  * ingesting H2 leaves Greg's store byte-identical -- the two trees are disjoint, so the
    `human_gt.jsonl` session-replace at ingest_annotations.py:553 cannot reach across;
  * `inter_rater.py` REFUSES a store whose `reader` is Greg's, so a mislabelled ingest
    cannot be reported as inter-rater agreement;
  * a letter disagreement between the two raters is paired and counted, not dropped;
  * the pre-registered per-figure Stage-B cap is applied and keeps the coded/text-verified
    landmark panels.

Run: python3 test_second_rater.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
FAILED = []

sys.path.insert(0, str(HERE))
from test_end_to_end import fake_stage_a, fill_form, fake_stage_b   # noqa: E402


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAILED.append(name)


def run(args, dan_root, expect_fail=False, extra_env=None):
    env = dict(os.environ, RV_DATA_DAN=str(dan_root))
    env.pop("RV_DATA", None)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable] + args, cwd=HERE, env=env,
                       capture_output=True, text=True)
    if (r.returncode != 0) != expect_fail:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"unexpected exit {r.returncode} from {args}")
    return r


def stamp_mode(sdir, anon_id, which="passA", on=True):
    p = sdir / "exports" / which / anon_id / "annotations.json"
    ann = json.loads(p.read_text())
    if on:
        ann["annotationMode"] = True
    else:
        ann.pop("annotationMode", None)
    p.write_text(json.dumps(ann, indent=2))


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rv-h2-"))
    dan = tmp / "dan"
    greg = tmp / "greg"
    print(f"second-rater test in {tmp}\n")
    repo_before = {p.name for p in HERE.iterdir()}
    try:
        print("[selftests]")
        run(["prepare_dan_session.py", "--selftest"], dan)
        check("prepare_dan_session --selftest passes", True)
        run(["inter_rater.py", "--selftest"], dan)
        check("inter_rater --selftest passes", True)
        shutil.rmtree(dan, ignore_errors=True)

        print("\n[plan]")
        r = run(["prepare_dan_session.py", "plan"], dan)
        plan = json.loads((dan / "plan.json").read_text())
        key = json.loads((dan / "keys" / "plan.key.json").read_text())
        aids = [i["anon_id"] for s in plan["sessions"] for i in s["items"]]
        n_items = sum(s["nItems"] for s in plan["sessions"])
        check("plan covers the whole pre-registered subset", n_items == 7, str(n_items))
        check("the plan declares itself reading H2", plan.get("reading") == "H2")
        check("no intra-rater repeats are scheduled for H2", plan.get("nRepeats") == 0)
        check("every anon id carries the `dn` prefix", all(a.startswith("dn") for a in aids))
        check("no anon id could be one of Greg's", not any(a.startswith("it") for a in aids))
        check("the public plan does not reveal the panel count",
              all(i["expectPanels"] is None for s in plan["sessions"] for i in s["items"]))
        check("the public plan does not name the article",
              not any("article" in i for s in plan["sessions"] for i in s["items"]))
        check("the key is stored outside the session tree",
              (dan / "keys" / "plan.key.json").exists()
              and not list((dan / "sessions").rglob("*.key.json")) if (dan / "sessions").exists()
              else True)
        caps = {i["item_id"]: i["capB"] for s in key["sessions"] for i in s["items"]}
        check("the Stage-B cap is pre-registered in the key, not decided later",
              sum(caps.values()) == 23, str(sum(caps.values())))

        print("\n[Stage A materials]")
        run(["prepare_dan_session.py", "build", "S01"], dan)
        sdir = dan / "sessions" / "S01"
        s1 = json.loads((sdir / "session.json").read_text())
        check("one page render per item",
              all((sdir / "projectA" / i["anon_id"] / "0001.png").exists() for i in s1["items"]))
        check("no machine output ships in the materials",
              not any(p.name in ("panels_gt.jsonl", "coded_reference.json")
                      for p in sdir.rglob("*")))
        check("Stage A ships no annotations.json (blank slate)",
              not list((sdir / "projectA").rglob("annotations.json")))

        print("\n[blinding: annotationMode must be asserted]")
        # `fake_stage_a` now defaults to a CORRECTLY configured rater (annotationMode on),
        # which is what every other fixture wants; this one deliberately builds the export
        # a rater with the Settings checkbox OFF would produce.
        for it in s1["items"]:
            fake_stage_a(sdir, it["anon_id"], it["pageW"], it["pageH"], n_panels=3,
                         annotation_mode=False)
        r = run(["prepare_dan_session.py", "check", "S01", "passA"], dan, expect_fail=True)
        check("an export with no annotationMode stamp is refused",
              "annotationMode is not true" in r.stderr)
        for it in s1["items"]:
            stamp_mode(sdir, it["anon_id"])
        r = run(["prepare_dan_session.py", "check", "S01", "passA"], dan)
        check("the same export passes once annotationMode is stamped",
              "blinding OK" in r.stdout)

        poisoned = s1["items"][0]["anon_id"]
        fake_stage_a(sdir, poisoned, s1["items"][0]["pageW"], s1["items"][0]["pageH"],
                     n_panels=3, poisoned=True)
        stamp_mode(sdir, poisoned)
        r = run(["prepare_dan_session.py", "check", "S01", "passA"], dan, expect_fail=True)
        check("detector fingerprints are refused even with annotationMode on",
              "panelDetection present" in r.stderr and "panel-split" in r.stderr)
        fake_stage_a(sdir, poisoned, s1["items"][0]["pageW"], s1["items"][0]["pageH"], n_panels=3)
        stamp_mode(sdir, poisoned)

        print("\n[handoff packing refuses to leak]")
        run(["prepare_dan_session.py", "pack", "S01", "A"], dan)
        import zipfile
        with zipfile.ZipFile(dan / "DAN-S01-stageA.zip") as z:
            names = z.namelist()
        check("the handoff archive contains the page renders",
              any(n.endswith("0001.png") for n in names))
        for bad in ("plan.key.json", "human_gt.jsonl", "coded_reference.json", "seal.json",
                    "split.json"):
            check(f"the handoff archive contains no {bad}",
                  not any(bad in n for n in names))
        check("the handoff archive contains nothing from Greg's tree",
              not any("sessions/" in n or n.startswith("gt/") for n in names))

        print("\n[Stage B is gated on Greg being finished]")
        r = run(["prepare_dan_session.py", "build-b", "S01"], dan, expect_fail=True)
        check("build-b refuses while G's reading of these figures is unsealed",
              "Greg" in r.stderr and ("sealed" in r.stderr or "finished" in r.stderr))
        run(["prepare_dan_session.py", "build-b", "S01", "--force"], dan)
        sb = json.loads((sdir / "sessionB.json").read_text())
        want = sum(min(caps[i["item_id"]], 3) for s in key["sessions"] if s["session"] == "S01"
                   for i in s["items"])
        check("the pre-registered per-figure cap is applied to Stage B",
              len(sb["items"]) == want, f"{len(sb['items'])} panels, expected {want}")
        check("a dropped panel's crop and coding form are both removed",
              all((sdir / "projectB" / e["panel_item"]).exists()
                  and (sdir / "coding" / f"{e['panel_item']}.form.json").exists()
                  for e in sb["items"])
              and len(list((sdir / "coding").glob("*.form.json"))) == len(sb["items"]))
        check("every Stage B crop carries the 1:1 grating strip",
              all((sdir / "projectB" / e["panel_item"] / "0001.png").exists()
                  for e in sb["items"]))

        print("\n[Dan annotates and is ingested as H2]")
        for e in sb["items"]:
            fill_form(sdir / "coding" / f"{e['panel_item']}.form.json")
            fake_stage_b(sdir, e["panel_item"], jitter=2.0)
            stamp_mode(sdir, e["panel_item"], "passB")
        run(["prepare_dan_session.py", "ingest", "S01"], dan)
        store = [json.loads(l) for l in
                 (dan / "gt" / "human_gt.jsonl").read_text().splitlines() if l.strip()]
        check("H2's records land in H2's own store", len(store) == len(sb["items"]))
        check("every H2 record is attributed to the second rater",
              all(r_["reader"] == "DK-human" for r_ in store),
              str({r_["reader"] for r_ in store}))
        check("H2's store is sealed", (dan / "gt" / "S01" / "seal.json").exists())
        seal = json.loads((dan / "gt" / "S01" / "seal.json").read_text())
        check("the seal names the second rater", seal.get("reader") == "DK-human")

        print("\n[Greg's tree is untouched]")
        check("ingesting H2 wrote nothing into the repo directory",
              {p.name for p in HERE.iterdir()} - repo_before <= {"__pycache__", "dan"})
        check("H2's tree and Greg's tree share no path",
              not str(dan).startswith(str(HERE / "gt")))

        print("\n[inter-rater report]")
        # Build a synthetic G store over the same item_ids: same values with a small offset,
        # and one deliberate LETTER disagreement so the join is exercised.
        (greg / "gt").mkdir(parents=True, exist_ok=True)
        grecs = []
        # Pick an item that actually HAS a panel labelled A. store[0] does not always --
        # the store's order follows the session manifest, so on some runs the first record's
        # panels start at B and the mislabel is never planted, making both checks below fail
        # for a reason that has nothing to do with the code under test. A flaky test in a
        # validation harness is worse than no test: it teaches you to re-run until green.
        def _has_A(rec):
            if (rec.get("panelLetter") or "").upper() == "A":
                return True
            return any((p.get("letter") or "").upper() == "A"
                       for f in (rec.get("structure") or []) for p in (f.get("panels") or []))
        _cand = next((r_ for r_ in store if _has_A(r_)), None)
        check("a record with a panel 'A' exists to plant the mislabel on", _cand is not None)
        mislabel_item = (_cand or store[0])["item_id"]
        for r_ in store:
            g = json.loads(json.dumps(r_))
            g["reader"] = "GF-human"
            g["session"] = "S01"
            for grp in (g.get("extraction") or {}).get("groups") or []:
                for fld in ("mean", "errorHalf"):
                    if grp.get(fld):
                        grp[fld] = grp[fld] * (1.05 if fld == "errorHalf" else 1.002)
            # One silent-mislabel-shaped case: on ONE figure, G called the box that H2
            # called `A` a `Z` instead. The rename has to appear in every record of that
            # figure, because each record carries the whole figure's structure.
            if g["item_id"] == mislabel_item:
                if (g.get("panelLetter") or "").upper() == "A":
                    g["panelLetter"] = "Z"
                for f in g.get("structure") or []:
                    for p in f.get("panels") or []:
                        if (p.get("letter") or "").upper() == "A":
                            p["letter"] = "Z"
            grecs.append(g)
        (greg / "gt" / "human_gt.jsonl").write_text(
            "\n".join(json.dumps(x) for x in grecs) + "\n")

        r = run(["inter_rater.py", "--greg", str(greg), "--dan", str(dan)], dan)
        rep = json.loads((dan / "inter-rater.json").read_text())
        check("the report pairs the panels", rep["nPairs"] == len(store), str(rep["nPairs"]))
        check("the letter disagreement is paired via box overlap, not dropped",
              rep["join"]["byIoU"] >= 1, str(rep["join"]))
        check("the letter disagreement is counted in the structure channel",
              rep["structure"]["letterDisagreements"] >= 1)
        check("the dispersion channel is populated",
              rep["numeric"].get("dispersion", {}).get("n", 0) > 0)
        check("Bland-Altman recovers the injected -5% dispersion offset",
              abs(rep["numeric"]["dispersion"]["blandAltman"]["biasPct"] + 4.76) < 1.0,
              f"{rep['numeric']['dispersion']['blandAltman']['biasPct']:.2f}%")
        check("the central channel disagrees far less than the dispersion channel",
              rep["numeric"]["central"]["medianPct"] < rep["numeric"]["dispersion"]["medianPct"],
              f"{rep['numeric']['central']['medianPct']:.2f}% vs "
              f"{rep['numeric']['dispersion']['medianPct']:.2f}%")
        check("RC (reproducibility coefficient) is reported for both channels",
              all(rep["numeric"][c]["rcPct"] > 0 for c in ("central", "dispersion")))
        check("kappa is reported alongside raw agreement",
              "kappa" in rep["categorical"]["dispersionType"])
        check("Grubbs reports not-available rather than guessing without predictions",
              rep["grubbs"]["available"] is False)
        check("c_hat reports not-available rather than guessing",
              rep["cHat"]["available"] is False)
        check("the markdown report is written", (dan / "inter-rater.md").exists()
              and "Inter-rater" in (dan / "inter-rater.md").read_text())

        print("\n[a mislabelled ingest cannot masquerade as inter-rater]")
        bad = tmp / "bad"
        (bad / "gt").mkdir(parents=True, exist_ok=True)
        shutil.copy(greg / "gt" / "human_gt.jsonl", bad / "gt" / "human_gt.jsonl")
        r = run(["inter_rater.py", "--greg", str(greg), "--dan", str(bad)], dan,
                expect_fail=True)
        check("inter_rater refuses a store whose reader is Greg's",
              "Refusing" in r.stderr, r.stderr.strip()[-160:])

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: " + ", ".join(FAILED))
        return 1
    print("all second-rater checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
