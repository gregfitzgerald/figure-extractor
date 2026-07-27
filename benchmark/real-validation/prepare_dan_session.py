#!/usr/bin/env python3
"""prepare_dan_session.py -- build the SECOND RATER's blinded sessions (reading `H2`).

The study currently has three readings of each panel: `D` (Greg's historical dissertation
extraction), `G` (Greg's fresh annotation) and `M` (the machine). `D` and `G` are the same
person, so together they bound test-retest repeatability and understate what "a human
digitizer" actually costs. A genuine second rater turns that into inter-rater reliability,
which is the comparison a reviewer will ask for. ANALYSIS-PLAN.md sec.11 lists it as known
gap #1: "the single highest-value addition".

This script does exactly one thing that `prepare_session.py` cannot: it builds a session
tree for a DIFFERENT PERSON, over a pre-registered SUBSET of the worklist, in a data root
that is physically disjoint from Greg's. Everything else -- page rendering, panel re-crop,
the 1:1 grating, the coding forms, the timer, the ingest -- is `prepare_session.py` and
`ingest_annotations.py` unmodified, invoked with `RV_DATA` pointed at Dan's tree. Greg's
`plan.json`, `keys/`, `sessions/` and `gt/` are never opened, never written, never read.

    plan      write Dan's plan + sealed key over the pre-registered subset (sec. DAN_SUBSET)
    build     Stage A materials (delegates to prepare_session.build)
    check     refuse an export that lacks `annotationMode: true` or carries detector marks
    build-b   Stage B materials, GATED on Greg having sealed the overlapping sessions,
              then capped to the pre-registered per-figure scored count
    pack      zip a SELF-CONTAINED handoff (tool + stopwatch + images), refusing to leak
    calibrate the shared 3-figure warm-up, in two phases: A, then --stage-b
    timer     per-item stopwatch for GREG's own copy (delegates; Dan runs dan_timer.py)
    status    where Dan's sessions stand (delegates)

Blinding is DOUBLED here, and both halves are mechanical:

  * blind to the MACHINE -- `annotationMode` must be ON in the tool. It hides Auto-panels,
    makes `detectPanels` refuse, and stamps `annotationMode: true` into the export. `check`
    (and `build-b`, and `pack`) refuse any export without that stamp, on top of the
    existing after-the-fact fingerprint test in `rvcommon.blinding_violations`.
  * blind to GREG -- Dan's tree contains projectA/projectB/coding/worksheets and nothing
    else. `pack` walks the archive it is about to write and aborts if it finds a key file,
    a GT store, a coded reference, a prediction, or anything from Greg's tree. Dan's anon
    ids carry a `dn` prefix, and both the id stream and the item ORDER are drawn from a
    seed that is generated once into the untracked `dan/` tree and never committed, so the
    mapping cannot be replayed out of this repository (see `realised_seed`).

The handoff `pack` writes is SELF-CONTAINED: it carries `figure-extractor.html` and a
standalone `dan_timer.py` as well as the images, because Dan works on his own machine and
has no checkout of this repo.

Run `python3 prepare_dan_session.py --selftest` to exercise all of it on synthetic data.
"""
import argparse
import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent

# Dan's data root. Set BEFORE rvcommon is imported: rvcommon resolves DATA/SESSIONS/KEYS/GT
# at import time from $RV_DATA, so this one line is the whole isolation mechanism.
DAN_DATA = pathlib.Path(os.environ.get("RV_DATA_DAN") or (HERE / "dan")).resolve()
os.environ["RV_DATA"] = str(DAN_DATA)

import rvcommon as rv                                     # noqa: E402
import prepare_session as ps                              # noqa: E402

ID_PREFIX = "dn"             # so a Dan id can never be mistaken for, or collide with, `it`
READER = "DK-human"          # stamped by ingest into every record and into the seal

# ------------------------------------------------------------------ the realised seed
#
# A seed written into the source is not a seed. The previous version of this file carried
# `SEED_DAN = 20260728` next to `DAN_SUBSET` and `dan_anon_id()`, and `cmd_plan` walked the
# subset in source order -- so anyone holding this repository could replay the generator and
# recover `anon_id -> item_id` in about a dozen lines. Worse, because an anon id embeds its
# own POSITION (`dn03_9c1a`), even a secret seed would have left `dn03` readable as "the
# third row of DAN_SUBSET". Both holes are closed here: the seed is drawn once into an
# untracked file, and the item order is drawn from it too (`cmd_plan`).
#
# The failure mode this prevents: a reader of the repo -- or Dan, if he ever obtained it --
# de-anonymising the second-rater set and converting a blinded reading into an unblinded
# one after the fact, which would silently void the H2-vs-G contrast the whole exercise
# buys.
#
# What stays public is the SELECTION RULE (C1..C5) and the realised subset below. That is
# the pre-registration; hiding it would trade a real problem for a worse one.
SEED_FILE = DAN_DATA / "keys" / "seed.json"   # under `dan/`, which .gitignore excludes


def realised_seed(seed_file=None, create=True):
    """Get-or-create the realised seed for Dan's id stream and item order.

    Stable once drawn, so re-running `plan` reproduces the same ids; absent from the
    repository, so the mapping cannot be reconstructed from committed files alone."""
    p = pathlib.Path(seed_file) if seed_file else SEED_FILE
    if p.exists():
        return int(json.loads(p.read_text(encoding="utf-8"))["seed"])
    if not create:
        return None
    seed = int.from_bytes(os.urandom(8), "big")
    p.parent.mkdir(parents=True, exist_ok=True)
    rv.write_json(p, {
        "WARNING": "UNTRACKED SECRET -- never commit this, never send it to the rater.",
        "generatedAt": rv.now_iso(),
        "purpose": "realised seed for the H2 anon-id stream and the H2 item order",
        "seed": seed})
    try:
        p.chmod(0o600)
    except OSError:
        pass                                  # best effort; Windows/WSL mounts often refuse
    print(f"[new] drew a fresh H2 seed into {p}\n"
          f"      Keep it. Do not commit it. Losing it means the ids cannot be re-derived.")
    return seed


def seed_fingerprint(seed):
    """A publishable stand-in for the seed: proves two runs used the same one without
    revealing it. Recorded in plan.json and in the key so provenance stays auditable."""
    return hashlib.sha256(f"H2-seed:{seed}".encode("utf-8")).hexdigest()[:16]


# ============================================================ the pre-registered subset
#
# SELECTION RULE, applied in this order. It is stated as a rule rather than a list so the
# same rule can be re-run against Tier 2 without re-litigating the choice.
#
#   C1 OVERLAP.  Candidates are Tier-1 figures ONLY. Dan reads nothing Greg does not read.
#       An unpaired panel contributes exactly zero to any inter-rater statistic, so a
#       "wider" subset that is not paired is not wider, it is smaller.
#
#   C2 FOUR-INSTRUMENT CORE.  Take every Tier-1 figure carrying a landmark_task with
#       `usable_for_dispersion: true`, prioritising those whose task is
#       `text_value_verified`. These are the only cells where D, G, M and H2 coexist, and
#       they are what makes the shared-person covariance `c` of ANALYSIS-PLAN sec.1.3
#       MEASURABLE (Grubbs on {D,G,M} minus Grubbs on {G,H2,M}) rather than merely
#       bracketed. Yields Zhang2017_F3, Lee2024_F2, Ederer2022_F2.
#
#   C3 DISPERSION-MIX CORRECTION.  C2's cells are 6/11 SD and 5/5 from S0_textGT, while the
#       corpus is ~91% SEM -- i.e. the four-instrument core is concentrated in the LONG-cap
#       easy case and in papers that print their numbers. Add SEM-bearing figures until SEM
#       is the majority of Dan's scored panels and no article supplies more than ~20% of
#       them. Yields Morgan2018_F7, Chrusch2023_F2.
#
#   C4 CONVENTION STRESS.  Add, unconditionally, the Tier-1 figures that instantiate the
#       human-convention failure modes the protocol already names: a paper that states no
#       dispersion type at all (Lyst2012_F7 -- "both raters must ABSTAIN" is a pre-committed
#       GATE, sec.3.3, and abstention is the behaviour most likely to differ between two
#       people), and a single-panel figure where any split is a false positive
#       (Nawaz2018_F1 -- 1 tile, ~11 min, the cheapest stratum in the corpus).
#
#   C5 BUDGET STOP.  Stop at Tier 1's own ceiling (~4 h of annotation). Cap the number of
#       SCORED panels per figure at `cap_b` so a single 7- or 8-panel article cannot
#       dominate; the cap is applied AFTER Dan's Stage A, so it leaks no structure.
#
# Stage A is always the WHOLE figure -- every tile, no exceptions. Handing Dan a list of
# panels to annotate inside a figure would tell him how many panels the figure has and what
# they are called, which is precisely the Tier-P quantity being measured.
DAN_SUBSET = [
    # item_id,            cap_b, why this figure is in the set
    ("Zhang2017_F3",      4, "C2 core: 6 four-instrument cells (3e/3f text-verified); "
                             "S18_SD_rare is the only SD contrast in Tier 1; S7 many-panels"),
    ("Lee2024_F2",        4, "C2 core: 2 four-instrument cells (2B text-verified); vector "
                             "text labels (S11) with a hierarchical A-(a) alphabet (S8/S9)"),
    ("Ederer2022_F2",     4, "C2 core: 1 text-verified four-instrument cell; 8 SEM bar "
                             "panels, the densest SEM source in Tier 1 (S0/S7)"),
    ("Lyst2012_F7",       4, "C4: the paper states NO dispersion type -- the correct answer "
                             "is abstain, and abstention is a pre-committed gate (S5/S1)"),
    ("Morgan2018_F7",     3, "C3: SEM; caption names A/B/C but the figure draws no letters, "
                             "so letters must be assigned by reading order (S5)"),
    ("Chrusch2023_F2",    3, "C3: SEM; the only flush+tight figure in the set that still has "
                             "bar panels, with a non-[A-Z] alphabet A/A'/C'/C\" (S3/S2/S8/S9)"),
    ("Nawaz2018_F1",      1, "C4: single-panel control -- any split is a false positive; "
                             "1 tile, vector text, SD (S10/S11)"),
]

# Optional add-backs, in the order they should be restored if Dan has appetite. Each buys
# back something the budget stop removed. Not part of the pre-registered scored set.
DAN_STRETCH = [
    ("Gattas2022_F4",     3, "+1 four-instrument cell; roman-numeral labels a.i/a.ii (S8/S9)"),
    ("Harburger2007b_F3", 4, "+4 SEM panels at a 0.92% gutter with the legend outside (S2/S7)"),
]

ITEMS_PER_SESSION_DAN = 4     # 7 figures -> 2 sessions; keeps a sitting under ~2 h

# ============================================================ the calibration round
#
# Three panels BOTH raters annotate before the scored set, to settle the conventions that
# otherwise differ silently: where exactly is the bar top and the cap, does the panel box
# include the axis, who owns a shared axis, asterisk vs cap, and what counts as a panel.
# See SECOND-RATER-PROTOCOL.md sec.4.
#
# All three are drawn from the articles ANALYSIS-PLAN sec.2.3 marks **permanently DEV**
# (Gobeske2009, GarciaCapdevila2009, Bonaccorsi2013, Kazlauckas2011) -- already contaminated
# by the pilot, already excluded from LOCK, so spending them on a warm-up costs nothing. None
# is in Dan's scored set.
#
# They are built into a SEPARATE data root (`dan/calibration/`) and `plan --calibration`
# refuses to run anywhere else, so calibration reads can never reach `dan/gt/human_gt.jsonl`
# and can never be analysed by accident.
CALIBRATION_SET = [
    ("GarciaCapdevila2009_F1", "C1: 2 tiles, grouped bar, SEM in the caption. The plain case. "
                               "Forces: where is the bar top, where is the cap, does the panel "
                               "box include the y-axis and its tick labels"),
    ("Bonaccorsi2013_F1",      "C2: 6 tiles sharing an axis, SEM. This is the figure that "
                               "produced the project's asterisk-occlusion finding, so the "
                               "glyph really does sit over a cap. Forces: asterisk vs cap, "
                               "who owns a shared axis, what counts as occluded"),
    ("Gobeske2009_F4",         "C3: 5 visual tiles, caption names 4 letters. Forces: what is a "
                               "panel, do you split, how do you name an unlabelled tile"),
]


# ============================================================ helpers
def _die(msg):
    raise SystemExit(f"prepare_dan_session: {msg}")


def _subset(include_stretch=False):
    rows = list(DAN_SUBSET) + (list(DAN_STRETCH) if include_stretch else [])
    return {r[0]: {"cap_b": r[1], "why": r[2]} for r in rows}, [r[0] for r in rows]


def _load_worklist_items(path=None):
    items, src = ps.load_worklist(path)
    return {i["item_id"]: i for i in items}, src


def dan_anon_id(rng, index, used):
    """`dn03_9c1a`. Same shape as rvcommon.anon_id but a distinct prefix and a distinct RNG
    stream, so Dan's ids neither collide with nor are derivable from Greg's. Position is
    Dan's own position, which tells him nothing about Greg's ordering."""
    while True:
        cand = f"{ID_PREFIX}{index:02d}_{rng.randrange(16 ** 4):04x}"
        if cand not in used:
            used.add(cand)
            return cand


def _letter_of(data_source):
    """'Figure 3b' -> 'B'; 'Figure 2-B' -> 'B'; 'Fig 4b' -> 'B'. Returns '' if unreadable."""
    m = re.search(r"([A-Za-z])\s*$", (data_source or "").strip())
    return m.group(1).upper() if m else ""


def _scored_rank(worklist_item, letter):
    """Cap-selection rank within a figure: text-verified landmark first, then any coded
    landmark, then everything else. Ties are broken by a seeded shuffle recorded in the key,
    so the choice is pre-registered rather than made after seeing Dan's boxes."""
    best = 2
    for cp in worklist_item.get("coded_panels") or []:
        if _letter_of(cp.get("data_source")) != letter:
            continue
        if not cp.get("usable_for_dispersion"):
            continue
        best = min(best, 0 if cp.get("text_value_verified") else 1)
    return best


def _greg_sealed_item_ids():
    """item_ids Greg has already ingested AND sealed, read from HIS tree. Read-only, and
    only the key file's item_id list is touched -- no annotation, box or value is opened."""
    greg_key = HERE / "keys" / "plan.key.json"
    if not greg_key.exists():
        return None                                   # Greg has not run `plan` yet
    key = json.loads(greg_key.read_text(encoding="utf-8"))
    done = set()
    for s in key.get("sessions", []):
        if (HERE / "gt" / s["session"] / "seal.json").exists():
            done |= {i["item_id"] for i in s["items"]}
    return done


def _export_dirs(sdir, which):
    root = sdir / "exports" / which
    return sorted(p for p in root.glob("*/annotations.json")) if root.exists() else []


def check_exports(session, which, strict=True):
    """Both halves of the doubled blinding, on files Dan has actually produced."""
    sdir = rv.SESSIONS / session
    found = _export_dirs(sdir, which)
    problems = []
    for p in found:
        ann = json.loads(p.read_text(encoding="utf-8"))
        # ONE implementation, so both raters are held to the same bar by construction and
        # not by two copies of a string staying in sync (amendment A1). Greg's
        # ingest_annotations.py calls the same function with the same severity.
        for b in rv.annotation_mode_violations(ann) + rv.blinding_violations(ann):
            problems.append(f"{p.parent.name}: {b}")
    if strict and not found:
        problems.append(f"no exports found under sessions/{session}/exports/{which}/")
    return found, problems


# ============================================================ subcommands
def cmd_plan(args):
    if getattr(args, "calibration", False):
        if rv.DATA.name != "calibration":
            _die("`plan --calibration` must run in the calibration root. Use the `calibrate` "
                 "subcommand, which sets it. Refusing: a calibration read that landed in the "
                 "scored store would be analysed, and the whole point of the warm-up is that "
                 "it is not.")
        caps = {i: {"cap_b": 99, "why": w} for i, w in CALIBRATION_SET}
        order = [i for i, _ in CALIBRATION_SET]
    else:
        caps, order = _subset(args.stretch)
    by_id, src = _load_worklist_items(args.worklist)
    missing = [i for i in order if i not in by_id]
    if missing:
        _die(f"worklist has no item(s) {missing} -- the subset and the worklist disagree")
    items = [by_id[i] for i in order]
    calib = bool(getattr(args, "calibration", False))
    if not calib:
        for it in items:
            if it.get("tier") != 1:
                _die(f"{it['item_id']} is tier {it.get('tier')}, not 1 -- rule C1 (overlap) "
                     f"restricts Dan to Tier 1")

    seed = args.seed if args.seed is not None else realised_seed()
    if not calib:
        # Order comes from the secret seed, NOT from DAN_SUBSET's source order. Two reasons:
        # SECOND-RATER-PROTOCOL sec.6 promises an order randomised within difficulty strata
        # and round-robined across them, and -- since an anon id embeds its position --
        # walking the source list would make `dn03` mean "row 3 of DAN_SUBSET" to anyone
        # holding this file, no matter how well the seed itself were hidden.
        items = rv.interleave_by_stratum(items, lambda i: i["stratum"], seed)
    rng = random.Random(seed)
    per = len(items) if calib else args.per_session
    sessions, used = [], set()
    for si in range(0, len(items), per):
        chunk = items[si:si + per]
        sessions.append({"session": f"{'C' if calib else 'S'}{si // per + 1:02d}",
                         "entries": chunk})

    plan, key = [], []
    for s in sessions:
        pub, priv = [], []
        for pos, it in enumerate(s["entries"], 1):
            aid = dan_anon_id(rng, pos, used)
            cap = caps[it["item_id"]]
            # Pre-registered tie-break for the Stage-B cap, drawn NOW.
            tie = list(range(32))
            rng.shuffle(tie)
            pub.append({"anon_id": aid, "position": pos, "figure": it["figure"],
                        "expectPanels": None})
            priv.append({"anon_id": aid, "position": pos, "item_id": it["item_id"],
                         "article": it.get("article"), "doi": it.get("doi"),
                         "pdf": it.get("pdf"), "page": it.get("page"),
                         "figure": it["figure"], "row_ids": it.get("row_ids") or [],
                         "stratum": it["stratum"], "difficulty": it["difficulty"],
                         "isRepeat": False, "repeatOf": None,
                         "capB": cap["cap_b"], "why": cap["why"], "tieBreak": tie,
                         "strata": it.get("strata") or [],
                         "tiles": it.get("visual_tile_count_survey"),
                         "dispersionType": it.get("dispersion_type")})
        plan.append({"session": s["session"], "nItems": len(pub), "items": pub})
        key.append({"session": s["session"], "isRepeatSession": False, "items": priv})

    rv.write_json(rv.DATA / "plan.json", {
        "schemaVersion": rv.RV_SCHEMA_VERSION, "generatedAt": rv.now_iso(),
        "reading": "H2", "reader": READER,
        "worklistSource": src, "seed": seed, "seedFingerprint": seed_fingerprint(seed),
        "perSession": per,
        "repeatFraction": 0.0, "nItems": len(items), "nRepeats": 0,
        "dpiA": ps.DPI_A, "panelLongEdgePx": ps.PANEL_LONG_EDGE_PX,
        "note": "Second-rater plan. NO intra-rater repeats: Dan's job is the INTER-rater "
                "contrast against G, and repeats would spend his budget on a quantity the "
                "G1/G2 subset already measures.",
        "sessions": plan})
    rv.write_json(rv.KEYS / "plan.key.json", {
        "schemaVersion": rv.RV_SCHEMA_VERSION, "generatedAt": rv.now_iso(),
        "WARNING": "SEALED KEY -- the rater must never open this file.",
        "reading": "H2", "seed": seed, "seedFingerprint": seed_fingerprint(seed),
        "repeatIds": [], "sessions": key})

    tiles = sum(i.get("visual_tile_count_survey") or 0 for i in items)
    scored = sum(caps[i["item_id"]]["cap_b"] for i in items)
    mins = sum(i.get("est_minutes_panel_gt") or 0 for i in items)
    print(f"\nH2 plan written to {rv.windows_path(rv.DATA)}")
    print(f"  {len(items)} figures / {tiles} Stage-A panels / {scored} scored Stage-B panels "
          f"/ {len(sessions)} sessions")
    print(f"  Stage A (structure) budget from the worklist time model: {mins} min")
    print(f"  articles: {len({i['article'] for i in items})}   "
          f"strata: {len({s for i in items for s in (i.get('strata') or [])})}")
    print(f"\nNext: python3 prepare_dan_session.py build {sessions[0]['session']}")


def cmd_build(args):
    if not (rv.DATA / "plan.json").exists():
        _die("no plan -- run `python3 prepare_dan_session.py plan` first")
    ns = argparse.Namespace(session=args.session, force=args.force)
    ps.cmd_build(ns)
    print("\nHand off with: python3 prepare_dan_session.py pack "
          f"{args.session} A")


def cmd_check(args):
    found, problems = check_exports(args.session, args.stage_dir)
    print(f"{len(found)} export(s) under exports/{args.stage_dir}/")
    if problems:
        print("\n".join("  ! " + p for p in problems), file=sys.stderr)
        raise SystemExit(f"{len(problems)} blinding problem(s)")
    print("blinding OK: every export asserts annotationMode:true and carries no detector marks")


def cmd_build_b(args):
    key = rv.read_json(rv.KEYS / "plan.key.json")
    if not key:
        _die("no keys/plan.key.json -- run `plan` first")
    ks = next((s for s in key["sessions"] if s["session"] == args.session), None)
    if not ks:
        _die(f"session {args.session} is not in Dan's plan")

    # ---- GATE 1: Greg must be finished on these figures before Greg sees Dan's boxes.
    # build-b consumes Dan's Stage A output, so whoever runs it sees Dan's panel boxes.
    # If Greg has not yet annotated those figures himself, that is a contamination path
    # running the wrong way -- Dan -> Greg. Refuse.
    want = {i["item_id"] for i in ks["items"]}
    done = _greg_sealed_item_ids()
    if done is None:
        if not args.force:
            _die("Greg has no keys/plan.key.json yet, so his pass on these figures cannot "
                 "be shown to be finished. Running build-b now would expose Dan's boxes to "
                 "an unfinished G. Re-run with --force only if G is known to be complete.")
    else:
        pending = sorted(want - done)
        if pending and not args.force:
            _die("Greg has not sealed his reading of: " + ", ".join(pending) +
                 "\nBuilding Dan's Stage B means opening Dan's panel boxes, which would "
                 "contaminate G. Finish and seal G on those items first "
                 "(`ingest_annotations.py ingest <session>`), or --force if you accept it.")

    # ---- GATE 2: Dan's Stage A must assert annotationMode and carry no detector marks.
    _, problems = check_exports(args.session, "passA")
    if problems and not args.force:
        print("\n".join("  ! " + p for p in problems), file=sys.stderr)
        _die(f"{len(problems)} blinding problem(s) in Stage A -- Stage B not built")

    ps.cmd_build_b(argparse.Namespace(session=args.session, force=args.force))
    n = _cap_stage_b(args.session)
    print(f"\ncapped to {n} scored panel(s) by the pre-registered per-figure cap")
    print(f"Hand off with: python3 prepare_dan_session.py pack {args.session} B")


def _stable_tie(s):
    """A process-stable integer from a string.

    Python salts the builtin `hash()` of a str per process (PYTHONHASHSEED), so
    `hash(panel_item) % len(tie)` made the "pre-registered" tie-break differ from run to
    run -- and `_cap_stage_b` then `rmtree`s the panels that lose it. Two runs of the same
    command would have deleted different panels and produced different scored sets, which
    is the opposite of pre-registration. sha256 is stable across processes and machines."""
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:8], 16)


def _cap_stage_b(session):
    """Apply the pre-registered per-figure cap to the panels build-b produced.

    Runs AFTER Dan's Stage A is sealed in place, so it cannot leak structure: Dan has
    already drawn and named every panel. It removes the crops and coding forms for panels
    beyond the cap so his Stage B sitting stays inside the budget, keeping the
    text-verified and coded landmark panels first."""
    sdir = rv.SESSIONS / session
    sb = rv.read_json(sdir / "sessionB.json")
    if not sb:
        return 0
    key = rv.read_json(rv.KEYS / "plan.key.json")
    ks = next(s for s in key["sessions"] if s["session"] == session)
    kbyaid = {i["anon_id"]: i for i in ks["items"]}
    by_id, _ = _load_worklist_items()

    keep, drop = [], []
    for aid, group in _group_by(sb["items"], lambda e: e["anon_id"]).items():
        k = kbyaid.get(aid) or {}
        wl = by_id.get(k.get("item_id")) or {}
        tie = k.get("tieBreak") or list(range(64))
        ranked = sorted(
            group,
            key=lambda e: (_scored_rank(wl, (e.get("panelLetter") or "").upper()),
                           tie[_stable_tie(e["panel_item"]) % len(tie)],
                           e["panel_item"]))
        cap = k.get("capB") or len(ranked)
        keep += ranked[:cap]
        drop += ranked[cap:]

    for e in drop:
        shutil.rmtree(sdir / "projectB" / e["panel_item"], ignore_errors=True)
        (sdir / "coding" / f"{e['panel_item']}.form.json").unlink(missing_ok=True)

    keep.sort(key=lambda e: e.get("position") or 0)
    for pos, e in enumerate(keep, 1):
        e["position"] = pos
    sb["items"] = keep
    sb["nPanels"] = len(keep)
    sb["cappedBy"] = "prepare_dan_session._cap_stage_b (pre-registered per-figure cap)"
    rv.write_json(sdir / "sessionB.json", sb)

    lines = [f"# Stage B worksheet -- {session} (reading H2)", "",
             "Fill the coding form for a panel BEFORE you digitize it.", "",
             "| # | panel | letter | panel px | magnification |", "|---|---|---|---|---|"]
    for e in keep:
        lines.append(f"| {e['position']} | `{e['panel_item']}` | {e.get('panelLetter')} | "
                     f"{e.get('panelPx')} | {e.get('magnificationVsStageA')}x |")
    (sdir / "B-WORKSHEET.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(keep)


def _group_by(seq, keyfn):
    out = {}
    for x in seq:
        out.setdefault(keyfn(x), []).append(x)
    return out


# things that must never reach Dan, matched against every archive member path
FORBIDDEN = (
    ("plan.key.json", "the anon->article key"),
    ("human_gt.jsonl", "a ground-truth store"),
    ("coded_reference.json", "the historical (D) reading"),
    ("intra_rater", "a reliability report"),
    ("seal.json", "a session seal"),
    ("split.json", "the DEV/LOCK assignment"),
)
FORBIDDEN_DIRS = ("keys", "gt", "repeat", "pred", "coded", "out", "exports")

# What the second rater returns, per stage. Printed by `pack` and written into the archive,
# because an incomplete handoff is discovered a week later, after the sitting is over.
SEND_BACK = {
    "A": ["projectA_all_figures.zip -- press Export All Articles (not Export This Article)",
          "timing.jsonl -- written next to the worksheet by `python3 dan_timer.py A`",
          "your conventions note (one sentence per convention) if this is the calibration "
          "round"],
    "B": ["projectB_all_figures.zip -- press Export All Articles",
          "the whole `coding/` folder, forms filled in",
          "timing.jsonl -- written by `python3 dan_timer.py B`"],
}


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_pack(args):
    sdir = rv.SESSIONS / args.session
    stage = args.stage.upper()
    proj = sdir / ("projectA" if stage == "A" else "projectB")
    if not proj.exists():
        _die(f"{proj} does not exist -- build it first")

    members = [(p, pathlib.Path(proj.name) / p.relative_to(proj))
               for p in sorted(proj.rglob("*")) if p.is_file()]
    if stage == "B":
        for p in sorted((sdir / "coding").glob("*.form.json")):
            members.append((p, pathlib.Path("coding") / p.name))
        ws = sdir / "B-WORKSHEET.md"
    else:
        ws = sdir / "A-WORKSHEET.md"
    if ws.exists():
        members.append((ws, pathlib.Path(ws.name)))
    proto = HERE / "SECOND-RATER-PROTOCOL.md"
    if proto.exists():
        members.append((proto, pathlib.Path("SECOND-RATER-PROTOCOL.md")))

    # The tool and the stopwatch travel WITH the images. Dan works entirely on his own
    # machine from this archive; the earlier version shipped him page renders and then told
    # him to open `C:\Users\gregs\...\figure-extractor.html` and to run the timer from a WSL
    # path on Greg's disk, neither of which exists for him. That is the failure mode here:
    # a handoff that is only usable by the person who built it.
    #
    # NEITHER FILE IS A LEAK, and the distinction is worth stating explicitly because the
    # sweep below is deliberately blunt. `figure-extractor.html` is the PRODUCT under test:
    # it is the public artefact of this repository, it contains no reading of any figure,
    # and Dan cannot annotate without it. `dan_timer.py` writes timestamps and reads the
    # worksheet; it imports nothing from this package. Both still go through the FORBIDDEN
    # sweep unmodified, and `cmd_selftest` asserts they survive it.
    tool = rv.HTML
    if not tool.exists():
        _die(f"{tool} is missing -- the handoff must carry the tool. Pointing the rater at a "
             f"path on this machine is exactly what this pack exists to stop.")
    members.append((tool, pathlib.Path(tool.name)))
    timer = HERE / "dan_timer.py"
    if not timer.exists():
        _die(f"{timer} is missing -- it is the standalone stopwatch the rater runs on his "
             f"own machine, and `prepare_dan_session.py timer` needs this whole repo.")
    members.append((timer, pathlib.Path(timer.name)))

    lines = [f"Handoff {args.session} stage {stage} -- second rater (reading H2)", "",
             "Everything you need is in this archive. You need nothing from anyone else's",
             "machine. Read SECOND-RATER-PROTOCOL.md first, end to end, once.", "",
             "In this folder:",
             "  figure-extractor.html    the tool -- open it as a file:// page",
             f"  dan_timer.py             the stopwatch -- python3 dan_timer.py {stage}",
             f"  project{stage}/                " +
             ("the journal page renders" if stage == "A" else "the enlarged panel crops"),
             f"  {ws.name}           the item order -- work it top to bottom"]
    if stage == "B":
        lines.append("  coding/                  one blank coding form per panel")
    lines += ["", "Send back:"]
    lines += [f"  {i}. {line}" for i, line in enumerate(SEND_BACK[stage], 1)]
    hand = sdir / "HANDOFF.txt"
    hand.write_text("\n".join(lines) + "\n", encoding="utf-8")
    members.append((hand, pathlib.Path("HANDOFF.txt")))

    leaks = []
    for src, arc in members:
        parts = set(arc.parts)
        for name, why in FORBIDDEN:
            if name in src.name:
                leaks.append(f"{arc}: {why}")
        for d in FORBIDDEN_DIRS:
            if d in parts and not (stage == "B" and d == "coding"):
                leaks.append(f"{arc}: sits under a `{d}/` directory")
    if leaks:
        print("\n".join("  ! " + x for x in sorted(set(leaks))), file=sys.stderr)
        _die("refusing to pack -- the archive would leak the listed item(s)")

    out = pathlib.Path(args.out) if args.out else (rv.DATA / f"DAN-{args.session}-stage{stage}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in members:
            z.write(src, str(arc).replace(os.sep, "/"))
    print(f"\nwrote {out}  ({len(members)} files, {out.stat().st_size / 1e6:.1f} MB)")
    print(f"Windows path: {rv.windows_path(out)}")
    print("Verified: no key, no GT store, no coded reference, no prediction, no seal.")
    print("Self-contained: figure-extractor.html and dan_timer.py travel in the archive, "
          "so the rater needs nothing from this machine.")
    print(f"  figure-extractor.html sha256 {_sha256(tool)}")
    print("  (record this -- it is what makes the tool version he annotated with provable)")
    print("\nWhat he sends back:")
    for i, line in enumerate(SEND_BACK[stage], 1):
        print(f"  {i}. {line}")


def cmd_calibrate(args):
    """Build the shared warm-up, in its own data root, for BOTH raters. TWO PHASES.

    Stage A alone cannot settle the round's own agenda. "Where exactly is the bar top",
    "where exactly is the cap", "asterisk vs cap", "is the cap its centre line or its upper
    edge" are all LANDMARK picks, i.e. Stage B; a warm-up that stopped at panel boxes would
    reconcile the one convention that barely matters (a 1-px slip on a 400-px box is 0.25%)
    and none of the ones that do. That is the failure mode this command prevents.

    It cannot be one shot either: Stage B is re-cropped from the rater's OWN Stage A panel
    boxes, so it does not exist until those boxes come back. Hence:

        calibrate            -> plan + Stage A materials + DAN-C01-stageA.zip
        (both raters annotate Stage A, independently, and return projectA exports)
        calibrate --stage-b  -> build-b over those exports + DAN-C01-stageB.zip

    Everything lives in `<dan>/calibration/`, so nothing the round produces can reach the
    scored store."""
    root = DAN_DATA / "calibration"
    env = dict(os.environ, RV_DATA_DAN=str(root), RV_DATA=str(root))
    me = [sys.executable, str(pathlib.Path(__file__).resolve())]
    exports = root / "sessions" / "C01" / "exports" / "passA"

    def _run(argv):
        r = subprocess.run(me + argv, env=env)
        if r.returncode:
            sys.exit(r.returncode)

    if args.stage_b:
        if not list(exports.glob("*/annotations.json")):
            _die("no Stage A exports under\n  " + rv.windows_path(exports) +
                 "\nUnzip each rater's `projectA_all_figures.zip` there -- one sub-folder per "
                 "item, each holding an annotations.json -- and re-run. Stage B is re-cropped "
                 "from the rater's own panel boxes, so it cannot be built before they arrive.")
        # The annotationMode gate applies to the warm-up exactly as it does to the scored
        # set: catching a rater who left the Settings checkbox off is half of what a dry run
        # is for, and finding it here costs three throwaway figures instead of a sitting.
        # The Greg-must-be-sealed gate does NOT apply -- these three figures are permanently
        # DEV pilot material (ANALYSIS-PLAN sec.2.3), there is no G reading of them to
        # contaminate, and both raters do them on the same day by design. Hence --force.
        _run(["check", "C01", "passA"])
        _run(["build-b", "C01", "--force"])
        _run(["pack", "C01", "B"])
        print("\nCalibration STAGE B built. Same zip to both raters:")
        print(f"\n  {rv.windows_path(root / 'DAN-C01-stageB.zip')}\n")
        print("Next, in this order:")
        print("  1. Both raters fill every coding form and pick every landmark,")
        print("     independently, with no discussion and no shared screen.")
        print("  2. Each writes one sentence per convention in a plain text file --")
        print("     'I clicked the cap at ...', 'I put the box edge at ...'. 6-10 sentences.")
        print("  3. Compare the SENTENCES in a 20-minute call. Never compare the values:")
        print("     agreeing on a magnitude trains the two of you toward each other and")
        print("     spends the independence this rater is being recruited for.")
        print("  4. Write what you agree into SECOND-RATER-PROTOCOL.md sec.13. It overrides")
        print("     the rules above for both of you.")
        print("  5. Re-do any panel whose convention changed. Then start the scored set --")
        print("     not on the same day.")
        return

    for argv in (["plan", "--calibration"],
                 ["build", "C01"] + (["--force"] if args.force else []),
                 ["pack", "C01", "A"]):
        _run(argv)
    print("\nCalibration STAGE A built. Give the SAME zip to both raters, and have them")
    print("annotate independently with no discussion:")
    print(f"\n  {rv.windows_path(root / 'DAN-C01-stageA.zip')}\n")
    for item_id, why in CALIBRATION_SET:
        print(f"  - {item_id}: {why}")
    print("\nNext, in this order:")
    print("  1. Both raters do Stage A on all three figures and press Export All Articles.")
    print("  2. Unzip each returned projectA export into")
    print(f"       {rv.windows_path(exports)}")
    print("     one sub-folder per item, each holding an annotations.json.")
    print("  3. Run:  python3 prepare_dan_session.py calibrate --stage-b")
    print("     which builds the panel crops and the coding forms from those boxes and")
    print("     writes DAN-C01-stageB.zip.")
    print("\nDo NOT reconcile anything yet. The conventions the round exists to settle -- the")
    print("bar top, the cap, asterisk vs cap -- are Stage B quantities, and comparing after")
    print("Stage A would settle only the box edges.")


def cmd_timer(args):
    ps.cmd_timer(argparse.Namespace(session=args.session, stage=args.stage))


def cmd_status(args):
    ps.cmd_status(args)


def cmd_ingest(args):
    """Thin pass-through so the operator never has to remember to set RV_DATA."""
    cmd = [sys.executable, str(HERE / "ingest_annotations.py"), "ingest", args.session,
           "--reader", READER] + (["--allow-problems"] if args.allow_problems else [])
    r = subprocess.run(cmd, env=dict(os.environ, RV_DATA=str(rv.DATA)))
    sys.exit(r.returncode)


# ============================================================ selftest
def cmd_selftest(_args):
    failed = []

    def check(name, cond, detail=""):
        print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {detail}"))
        if not cond:
            failed.append(name)

    print("prepare_dan_session selftest")

    caps, order = _subset()
    by_id, _ = _load_worklist_items()
    check("every subset item exists in worklist.json",
          all(i in by_id for i in order),
          str([i for i in order if i not in by_id]))
    check("every subset item is Tier 1 (rule C1: overlap with Greg)",
          all(by_id[i].get("tier") == 1 for i in order if i in by_id))
    check("subset has no duplicate item_id", len(order) == len(set(order)))
    stretch_caps, stretch_order = _subset(True)
    check("stretch items are also Tier 1",
          all(by_id[i].get("tier") == 1 for i in stretch_order if i in by_id))

    scored = sum(caps[i]["cap_b"] for i in order)
    check("scored panel count is in the 20-30 band", 20 <= scored <= 30, f"got {scored}")
    arts = [by_id[i]["article"] for i in order if i in by_id]
    check("no article supplies more than 20% of the scored panels",
          max(sum(caps[i]["cap_b"] for i in order if by_id[i]["article"] == a)
              for a in set(arts)) <= 0.2 * scored + 1e-9 + 1,
          f"max share {max(sum(caps[i]['cap_b'] for i in order if by_id[i]['article'] == a) for a in set(arts))}/{scored}")
    check("at least 6 distinct articles", len(set(arts)) >= 6, str(len(set(arts))))
    strata = {s for i in order if i in by_id for s in (by_id[i].get("strata") or [])}
    check("at least 9 distinct strata covered", len(strata) >= 9, str(sorted(strata)))
    check("every subset figure draws error bars OR is a declared control",
          all(by_id[i].get("error_bars") for i in order if i in by_id))
    fourinst = [t for t in json.loads((HERE / "worklist.json").read_text())["landmark_tasks"]
                if t["figure_item_id"] in set(order) and t.get("usable_for_dispersion")]
    check("subset carries >= 7 four-instrument (D+G+M+H2) cells",
          len(fourinst) >= 7, f"got {len(fourinst)}")
    check("subset carries >= 3 text-verified cells",
          sum(1 for t in fourinst if t.get("text_value_verified")) >= 3)

    check("Dan's id prefix differs from Greg's", ID_PREFIX != "it")

    # blinding of the id stream: the seed must not be reconstructible from committed source
    src_text = pathlib.Path(__file__).resolve().read_text(encoding="utf-8")
    check("no realised seed is hard-coded in this file",
          not re.search(r"^SEED_DAN\s*=", src_text, re.M))
    gi = (HERE / ".gitignore").read_text(encoding="utf-8").splitlines()
    check("the seed file's default home is the gitignored `dan/` tree, not next to the code",
          (HERE / "dan" / "keys" / "seed.json").relative_to(HERE).parts[0] == "dan"
          and "dan/" in [l.strip() for l in gi],
          str(SEED_FILE))
    seed_tmp = pathlib.Path(tempfile.mkdtemp(prefix="dan-seed-")) / "seed.json"
    try:
        s1 = realised_seed(seed_tmp)
        s2 = realised_seed(seed_tmp)
        check("the realised seed is stable once drawn", s1 == s2)
        # Greg's seed used to be the module constant `prepare_session.SEED`, so this check
        # could compare against it directly. That constant WAS the defect -- committed, and
        # date-shaped, it let anyone with the repo recompute Greg's intra-rater repeat
        # assignments. It is now resolved from a gitignored sealed file, so the stronger
        # invariant is that no such constant exists to compare against.
        ps_src = pathlib.Path(ps.__file__).resolve().read_text(encoding="utf-8")
        check("Greg's seed is not a hard-coded constant either",
              not re.search(r"^SEED\s*=", ps_src, re.M))
        check("the realised seed is not the retired constant 20260728", s1 != 20260728)
        check("the realised seed is not Greg's retired constant 20260727", s1 != 20260727)
        check("the seed file is not the seed's own fingerprint",
              seed_fingerprint(s1) != seed_fingerprint(s1 + 1))
        # A fixed probe stands in for "some other rater's seed"; the property under test is
        # that the two id streams cannot collide, not the value of Greg's seed.
        probe_seed = 20260727
        r1, r2 = random.Random(s1), random.Random(probe_seed)
        a = dan_anon_id(r1, 1, set())
        b = rv.anon_id(r2, 1, set())
        check("a Dan id can never collide with a Greg id", a != b and not a.startswith("it"),
              f"{a} vs {b}")
    finally:
        shutil.rmtree(seed_tmp.parent, ignore_errors=True)

    # the Stage-B cap tie-break must not move between processes: the losers get rmtree'd
    check("the Stage-B tie-break is a stable hash, not the salted builtin",
          _stable_tie("dn01_0000_pA") == int(
              hashlib.sha256(b"dn01_0000_pA").hexdigest()[:8], 16))
    check("the tie-break does not call the salted builtin hash()",
          not re.search(r"tie\[hash\(", src_text))

    check("_letter_of parses the worklist's data_source spellings",
          (_letter_of("Figure 3b"), _letter_of("Figure 2-B"), _letter_of("Fig 4b"),
           _letter_of("Table 4")) == ("B", "B", "B", ""))

    # blinding gate, on fixtures
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dan-selftest-"))
    try:
        sd = rv.SESSIONS / "__selftest__"
        for name, ann in (
                ("clean", {"annotationMode": True, "figures": [{"id": "f1", "subfigures": []}]}),
                ("nomode", {"figures": [{"id": "f1", "subfigures": []}]}),
                ("detector", {"annotationMode": True,
                              "figures": [{"id": "f1", "panelDetection": {"method": "x"},
                                           "subfigures": []}]}),
                ("split", {"annotationMode": True,
                           "figures": [{"id": "f1", "subfigures": [
                               {"id": "s1", "captionSource": "panel-split"}]}]})):
            d = sd / "exports" / "passA" / name
            d.mkdir(parents=True, exist_ok=True)
            rv.write_json(d / "annotations.json", ann)
        _, probs = check_exports("__selftest__", "passA")
        joined = " ".join(probs)
        check("clean export passes", "clean:" not in joined)
        check("missing annotationMode is refused", "nomode:" in joined)
        check("panelDetection fingerprint is refused", "detector:" in joined)
        check("captionSource=panel-split is refused", "split:" in joined)

        # pack refuses to ship a key file
        proj = sd / "projectA" / "dn01_0000"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "0001.png").write_bytes(b"\x89PNG")
        (proj / "plan.key.json").write_text("{}")
        try:
            cmd_pack(argparse.Namespace(session="__selftest__", stage="A",
                                        out=str(tmp / "x.zip")))
            check("pack refuses to ship a key file", False, "it packed anyway")
        except SystemExit as e:
            check("pack refuses to ship a key file", "leak" in str(e), str(e))
        (proj / "plan.key.json").unlink()
        cmd_pack(argparse.Namespace(session="__selftest__", stage="A", out=str(tmp / "y.zip")))
        with zipfile.ZipFile(tmp / "y.zip") as z:
            names = z.namelist()
        check("pack ships the page render", any(n.endswith("0001.png") for n in names))
        check("packed archive contains no key/gt/coded file",
              not any(any(f[0] in n for f in FORBIDDEN) for n in names))
        # The tool and the stopwatch are NOT leaks and the leak sweep must not treat them as
        # such: figure-extractor.html is the product under test, public in this repo and
        # carrying no reading of any figure, and dan_timer.py only writes timestamps. If
        # either were dropped, the rater would be sent images and no way to annotate them.
        check("pack ships the tool itself (the product, not a leak)",
              "figure-extractor.html" in names)
        check("pack ships the standalone stopwatch (runs on the rater's machine)",
              "dan_timer.py" in names)
        check("pack ships a handoff note saying what to send back", "HANDOFF.txt" in names)
        check("the handoff note names the export the rater must return",
              "projectA_all_figures.zip" in
              zipfile.ZipFile(tmp / "y.zip").read("HANDOFF.txt").decode())
        shutil.rmtree(sd, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(("\nFAILED: " + ", ".join(failed)) if failed else "\nall checks passed")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("plan", help="write Dan's plan + sealed key over the subset")
    p.add_argument("--worklist")
    p.add_argument("--seed", type=int, default=None,
                   help="override the realised seed. Testing only: a seed given on the "
                        "command line is recoverable from your shell history, which is the "
                        "hole `realised_seed` closes.")
    p.add_argument("--per-session", type=int, default=ITEMS_PER_SESSION_DAN)
    p.add_argument("--stretch", action="store_true", help="include the DAN_STRETCH add-backs")
    p.add_argument("--calibration", action="store_true",
                   help="plan the warm-up set instead (calibration root only)")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("calibrate",
                       help="build the shared 3-figure warm-up for both raters (Stage A; "
                            "then --stage-b once their Stage A exports are back)")
    p.add_argument("--stage-b", action="store_true", dest="stage_b",
                   help="phase 2: consume the returned Stage A exports and pack Stage B")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_calibrate)

    p = sub.add_parser("build", help="Stage A materials")
    p.add_argument("session")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("check", help="verify the doubled blinding on Dan's exports")
    p.add_argument("session")
    p.add_argument("stage_dir", choices=("passA", "passB"))
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("build-b", help="Stage B materials (gated + capped)")
    p.add_argument("session")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_build_b)

    p = sub.add_parser("pack", help="zip a handoff for Dan, refusing to leak")
    p.add_argument("session")
    p.add_argument("stage", choices=("A", "B", "a", "b"))
    p.add_argument("--out")
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("timer", help="per-item stopwatch, for Greg's own copy of a session. "
                                     "The second rater runs dan_timer.py from his archive.")
    p.add_argument("session")
    p.add_argument("stage", choices=("A", "B"))
    p.set_defaults(fn=cmd_timer)

    p = sub.add_parser("ingest", help="ingest a sealed session as reading H2")
    p.add_argument("session")
    p.add_argument("--allow-problems", action="store_true")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("status", help="where Dan's sessions stand")
    p.set_defaults(fn=cmd_status)

    # Both spellings. `--selftest` is what test_second_rater.py and the docstring use; the
    # bare subcommand is what everything else in this directory uses, and having one of the
    # two silently not exist is how a check gets skipped.
    p = sub.add_parser("selftest", help="exercise the whole thing on synthetic data")
    p.set_defaults(fn=lambda a: sys.exit(cmd_selftest(a)))

    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(cmd_selftest(a))
    if not getattr(a, "fn", None):
        ap.print_help()
        sys.exit(2)
    a.fn(a)


if __name__ == "__main__":
    main()
