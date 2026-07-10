#!/usr/bin/env python3
"""
Screening step (title/abstract). Writes the screening CRITERIA the agents apply, and aggregates
their structured decisions into a PRISMA count + screening.json. Agents read candidates.json +
CRITERIA.md and emit one record per candidate (include/exclude/unsure + coded reason).

  python3 meta-analysis/screen.py criteria   # (re)write CRITERIA.md
  python3 meta-analysis/screen.py aggregate   # after agents write screening/records/*.json
"""
import json, pathlib, sys, collections

D = pathlib.Path(__file__).resolve().parent
SCR = D / "screening"; (SCR / "records").mkdir(parents=True, exist_ok=True)

CRITERIA = """# Title/abstract screening criteria (protocol v1.0)

Decide each candidate: **include** (or unsure) if it PLAUSIBLY meets ALL of these from the
title+abstract; **exclude** if it clearly fails one. When the abstract is ambiguous, prefer
**unsure** (it advances to full-text) over exclude.

INCLUDE if the study appears to be:
- Population: healthy adult rodents (mouse or rat), no disease/lesion/transgenic-pathology model.
- Intervention: voluntary wheel running (chronic).
- Comparator: a sedentary / non-running control group.
- Outcome: hippocampal **BDNF protein** (ELISA or western blot), not mRNA-only.
- Design: primary experimental study (not a review/meta-analysis/protocol/commentary).

EXCLUDE with a coded reason (choose the first that applies):
- `population`  : human, or disease/aged/developmental/transgenic-pathology model.
- `intervention`: not voluntary wheel running (forced treadmill, swimming, drug, diet, EE-only).
- `comparator` : no sedentary control (e.g. only a dose gradient, no control arm).
- `outcome`    : not hippocampal BDNF protein (mRNA only, serum/plasma, non-hippocampal, other marker).
- `design`     : review, meta-analysis, protocol, methods, commentary, non-empirical.
- `duplicate`  : clearly a duplicate of another record.

OUTPUT: write a JSON ARRAY to the given output path; one object per candidate:
{ "pmid": "...", "decision": "include|exclude|unsure",
  "reason": "<coded reason, only if exclude, else ''>", "confidence": 0..1, "note": "one phrase" }
Judge ONLY from title + abstract (this is title/abstract screening)."""


def write_criteria():
    (SCR / "CRITERIA.md").write_text(CRITERIA)
    print("wrote", SCR / "CRITERIA.md")


def aggregate():
    cand = json.loads((D / "corpus" / "candidates.json").read_text())["records"]
    by_pmid = {c["pmid"]: c for c in cand}
    recs = {}
    for f in sorted((SCR / "records").glob("*.json")):
        for r in json.loads(f.read_text()):
            recs[r["pmid"]] = r
    dec = collections.Counter(r["decision"] for r in recs.values())
    reasons = collections.Counter(r.get("reason", "") for r in recs.values() if r["decision"] == "exclude")
    missing = [p for p in by_pmid if p not in recs]
    prisma = {"identified_total_hits": json.loads((D / "corpus" / "candidates.json").read_text())["totalHits"],
              "fetched": len(by_pmid), "screened": len(recs), "not_yet_screened": len(missing),
              "included": dec["include"], "unsure_to_fulltext": dec["unsure"], "excluded": dec["exclude"],
              "exclusion_reasons": dict(reasons)}
    out = {"prisma": prisma, "included": [{**by_pmid[p], **recs[p]} for p in recs if recs[p]["decision"] == "include"],
           "records": [{**{k: by_pmid[p].get(k, "") for k in ("pmid", "title", "year", "journal", "doi")}, **recs[p]}
                       for p in recs]}
    (SCR / "screening.json").write_text(json.dumps(out, indent=2))
    print("PRISMA (title/abstract):")
    for k, v in prisma.items():
        print(f"  {k}: {v}")
    print(f"\n-> {dec['include']} included + {dec['unsure']} unsure advance to full-text; wrote screening.json")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "criteria"
    (write_criteria if cmd == "criteria" else aggregate)()
