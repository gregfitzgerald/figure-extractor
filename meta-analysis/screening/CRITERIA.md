# Title/abstract screening criteria (protocol v1.0)

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
Judge ONLY from title + abstract (this is title/abstract screening).