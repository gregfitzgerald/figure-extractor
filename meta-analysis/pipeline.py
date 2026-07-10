#!/usr/bin/env python3
"""
Pipeline orchestrator — runs the meta-analysis as a staged state machine with explicit HUMAN GATES
and an append-only decision log. Nothing advances past a gate until a human resolves its checkpoint.

Stages (see PIPELINE.md):
  1 identify        auto   corpus.py            -> corpus/candidates.json
  2 screen-ta       agent  screen.py aggregate  -> screening/screening.json
  3 adjudicate-ta   HUMAN  gate                 resolve every 'unsure'; override any decision
  4 screen-ft       agent  full-text screen     -> fulltext/fulltext.json
  5 adjudicate-ft   HUMAN  gate                 confirm final included set
  6 extract         agent  figure-extractor     -> extraction/<articleId>.json
  7 confirm-extract HUMAN  gate                 confirm dispersionType + n on figure-derived arms
  8 synthesize      auto   metalib + RVE        -> studies.csv, forest, PRISMA
  9 approve         HUMAN  gate                 sign off on the synthesis

Two auditable records, both append-only / human-readable:
  decisions/log.jsonl        one line per decision (automated OR human): who, what, why, when.
  checkpoints/<stage>.md     editable file the pipeline writes at a gate; human fills in decisions
                             inline, then `pipeline.py resolve <stage>` ingests + logs them.

Usage:
  python3 pipeline.py status                 # where are we; what needs a human
  python3 pipeline.py advance                # run the next automatable stage (or open the next gate)
  python3 pipeline.py open <stage>           # (re)write a gate's checkpoint file for the human
  python3 pipeline.py resolve <stage>        # ingest the human's edited checkpoint, log, unblock
  python3 pipeline.py log <stage> <actor> <action> <subject> [detail...]   # manual audit entry
"""
import json, pathlib, sys, subprocess, datetime, collections

D = pathlib.Path(__file__).resolve().parent
STATE = D / "pipeline_state.json"
LOG = D / "decisions" / "log.jsonl"
CKPT = D / "checkpoints"

# (name, actor, is_gate). Gates HALT the pipeline for a human.
STAGES = [
    ("identify",        "auto",  False),
    ("screen-ta",       "agent", False),
    ("adjudicate-ta",   "human", True),
    ("screen-ft",       "agent", False),
    ("adjudicate-ft",   "human", True),
    ("extract",         "agent", False),
    ("confirm-extract", "human", True),
    ("synthesize",      "auto",  False),
    ("approve",         "human", True),
]
STAGE_NAMES = [s[0] for s in STAGES]
STAGE = {s[0]: s for s in STAGES}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"created": _now(), "stages": {n: {"status": "pending"} for n in STAGE_NAMES}}


def save_state(st):
    st["updated"] = _now()
    STATE.write_text(json.dumps(st, indent=2))


def log_decision(stage, actor, action, subject, detail="", rationale=""):
    """Append one immutable line to the audit trail."""
    LOG.parent.mkdir(exist_ok=True)
    rec = {"ts": _now(), "stage": stage, "actor": actor, "action": action,
           "subject": subject, "detail": detail, "rationale": rationale}
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _set(st, stage, status, **extra):
    st["stages"].setdefault(stage, {}).update({"status": status, **extra})


# ---------- stage: identify (auto) ----------
def run_identify(st):
    subprocess.run([sys.executable, str(D / "corpus.py")], check=True)
    cand = json.loads((D / "corpus" / "candidates.json").read_text())
    _set(st, "identify", "done", fetched=cand["fetched"], totalHits=cand["totalHits"])
    log_decision("identify", "auto", "search",
                 f"{cand['fetched']} of {cand['totalHits']} hits fetched", cand["query"])


# ---------- stage: screen-ta (agent) — aggregate whatever agents wrote ----------
def run_screen_ta(st):
    subprocess.run([sys.executable, str(D / "screen.py"), "aggregate"], check=True)
    scr = json.loads((D / "screening" / "screening.json").read_text())
    p = scr["prisma"]
    _set(st, "screen-ta", "done", included=p["included"], unsure=p["unsure_to_fulltext"],
         excluded=p["excluded"])
    log_decision("screen-ta", "agent", "screen-title-abstract",
                 f"{p['included']} include / {p['unsure_to_fulltext']} unsure / {p['excluded']} exclude",
                 json.dumps(p.get("exclusion_reasons", {})))


# ---------- gate: adjudicate-ta — human resolves 'unsure' + reviews includes ----------
def open_adjudicate_ta():
    scr = json.loads((D / "screening" / "screening.json").read_text())
    by = {r["pmid"]: r for r in scr["records"]}
    cand = {c["pmid"]: c for c in json.loads((D / "corpus" / "candidates.json").read_text())["records"]}
    unsure = [p for p in by if by[p]["decision"] == "unsure"]
    incl = [p for p in by if by[p]["decision"] == "include"]
    CKPT.mkdir(exist_ok=True)
    L = ["# HUMAN GATE — adjudicate title/abstract screening",
         "",
         "The agents flagged these as **unsure**. For each, change `DECISION:` to `include` or `exclude`",
         "(add a coded reason for excludes: population/intervention/comparator/outcome/design/duplicate).",
         "You may also override any auto-**include** in the second section. Then run:",
         "`python3 pipeline.py resolve adjudicate-ta`",
         "", f"_Generated {_now()} — {len(unsure)} unsure to resolve, {len(incl)} includes to review._",
         "", "---", "", f"## UNSURE — resolve all {len(unsure)}", ""]
    for p in sorted(unsure):
        c, r = cand.get(p, {}), by[p]
        L += [f"### {p} — {c.get('title','(no title)')}",
              f"- {c.get('journal','')} {c.get('year','')}  doi:{c.get('doi','')}",
              f"- agent note: {r.get('note','')}  (confidence {r.get('confidence','')})",
              f"- abstract: {(c.get('abstract','') or '')[:600]}",
              "- DECISION: unsure   REASON:   NOTE:", ""]
    L += ["---", "", f"## AUTO-INCLUDES — override only if wrong ({len(incl)})", ""]
    for p in sorted(incl):
        c = cand.get(p, {})
        L += [f"- {p} — {c.get('title','')}  [{c.get('journal','')} {c.get('year','')}]",
              "  - DECISION: include   REASON:   NOTE:", ""]
    (CKPT / "adjudicate-ta.md").write_text("\n".join(L))
    return CKPT / "adjudicate-ta.md"


def _parse_checkpoint_decisions(path):
    """Pull (pmid, decision, reason, note) triples from an edited checkpoint file."""
    out, cur = [], None
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if s.startswith("### "):
            cur = s[4:].split(" ")[0].strip()
        elif s.startswith("- ") and s[2:].startswith(("DECISION:",)) is False and " — " in s and s[2:3].isdigit():
            cur = s[2:].split(" ")[0].strip()
        if "DECISION:" in s:
            body = s.split("DECISION:", 1)[1]
            dec = body.split("REASON:")[0].strip().strip("-").strip()
            reason = ""
            note = ""
            if "REASON:" in body:
                reason = body.split("REASON:", 1)[1].split("NOTE:")[0].strip()
            if "NOTE:" in body:
                note = body.split("NOTE:", 1)[1].strip()
            if cur and dec:
                out.append((cur, dec.lower(), reason, note))
                cur = None
    return out


def resolve_adjudicate_ta(st):
    path = CKPT / "adjudicate-ta.md"
    if not path.exists():
        print("no checkpoint file; run: python3 pipeline.py open adjudicate-ta"); return
    decisions = _parse_checkpoint_decisions(path)
    unresolved = [d for d in decisions if d[1] == "unsure"]
    if unresolved:
        print(f"STILL {len(unresolved)} unsure — resolve them in {path.name} before resolving:")
        for pmid, *_ in unresolved:
            print("  ", pmid)
        return
    scr = json.loads((D / "screening" / "screening.json").read_text())
    by = {r["pmid"]: r for r in scr["records"]}
    changed = 0
    for pmid, dec, reason, note in decisions:
        if pmid in by and (by[pmid]["decision"] != dec or by[pmid].get("reason", "") != reason):
            prev = by[pmid]["decision"]
            by[pmid]["decision"] = dec
            by[pmid]["reason"] = reason
            by[pmid]["adjudicated"] = True
            log_decision("adjudicate-ta", "human", "adjudicate", pmid,
                         f"{prev} -> {dec}" + (f" ({reason})" if reason else ""), note)
            changed += 1
    scr["records"] = list(by.values())
    dec_ct = collections.Counter(r["decision"] for r in by.values())
    scr["adjudicated"] = {"at": _now(), "changed": changed, "final_included": dec_ct["include"]}
    (D / "screening" / "screening.json").write_text(json.dumps(scr, indent=2))
    _set(st, "adjudicate-ta", "done", changed=changed, final_included=dec_ct["include"])
    log_decision("adjudicate-ta", "human", "gate-passed",
                 f"{dec_ct['include']} advance to full-text", f"{changed} overrides")
    print(f"adjudicated: {changed} changes; {dec_ct['include']} articles advance to full-text.")


ADVANCERS = {"identify": run_identify, "screen-ta": run_screen_ta}
OPENERS = {"adjudicate-ta": open_adjudicate_ta}
RESOLVERS = {"adjudicate-ta": resolve_adjudicate_ta}


def current_stage(st):
    for n in STAGE_NAMES:
        if st["stages"].get(n, {}).get("status") != "done":
            return n
    return None


def cmd_status(st):
    print("META-ANALYSIS PIPELINE\n")
    cur = current_stage(st)
    for n, actor, gate in STAGES:
        s = st["stages"].get(n, {})
        mark = {"done": "[x]", "blocked-on-human": "[!]", "pending": "[ ]"}.get(s.get("status"), "[ ]")
        tag = " (HUMAN GATE)" if gate else ""
        extra = " ".join(f"{k}={v}" for k, v in s.items() if k != "status")
        here = "  <- next" if n == cur else ""
        print(f"  {mark} {n:<16}{tag:<13} {extra}{here}")
    n_log = sum(1 for _ in LOG.open()) if LOG.exists() else 0
    print(f"\n  decisions logged: {n_log}   (decisions/log.jsonl)")
    if cur and STAGE[cur][2]:
        print(f"\n  NEXT: human gate '{cur}'. Open it with:  python3 pipeline.py open {cur}")
    elif cur:
        print(f"\n  NEXT: run '{cur}' with:  python3 pipeline.py advance")
    else:
        print("\n  pipeline complete.")


def cmd_advance(st):
    cur = current_stage(st)
    if cur is None:
        print("pipeline complete."); return
    if STAGE[cur][2]:
        _set(st, cur, "blocked-on-human")
        if cur in OPENERS:
            path = OPENERS[cur]()
            print(f"HUMAN GATE '{cur}' — wrote {path}\n  edit it, then: python3 pipeline.py resolve {cur}")
        else:
            print(f"HUMAN GATE '{cur}' — no auto-opener yet; resolve manually.")
        return
    if cur in ADVANCERS:
        ADVANCERS[cur](st)
        print(f"ran '{cur}'.")
    else:
        print(f"stage '{cur}' has no automated runner yet (agent-driven). Mark done when its artifacts exist.")


def main():
    st = load_state()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        cmd_status(st)
    elif cmd == "advance":
        cmd_advance(st); save_state(st)
    elif cmd == "open":
        stage = sys.argv[2]
        path = OPENERS[stage]()
        _set(st, stage, "blocked-on-human"); save_state(st)
        print("wrote", path)
    elif cmd == "resolve":
        stage = sys.argv[2]
        RESOLVERS[stage](st); save_state(st)
    elif cmd == "log":
        stage, actor, action, subject = sys.argv[2:6]
        detail = " ".join(sys.argv[6:])
        print(log_decision(stage, actor, action, subject, detail))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
