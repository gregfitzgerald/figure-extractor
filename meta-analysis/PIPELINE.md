# Pipeline — staged meta-analysis with human gates and a decision log

The protocol (`PROTOCOL.md`) says *what* we're doing; this says *how the machine runs it* so that a
human is in the loop at the load-bearing moments and **every decision is written down for review**.

Run by `pipeline.py` as a state machine. Four of the nine stages are **HUMAN GATES**: the pipeline
halts and refuses to advance until a person resolves the gate's checkpoint file.

## Stages

| # | Stage | Actor | Produces | Gate |
|---|-------|-------|----------|:----:|
| 1 | `identify` | auto — `corpus.py` | `corpus/candidates.json` | |
| 2 | `screen-ta` | agents — `screen.py aggregate` | `screening/screening.json` | |
| 3 | `adjudicate-ta` | **human** | resolves every `unsure`; may override any include/exclude | ● |
| 4 | `screen-ft` | agents | `fulltext/fulltext.json` (coded reason per drop) | |
| 5 | `adjudicate-ft` | **human** | confirms the final included set | ● |
| 6 | `extract` | agents + figure-extractor | `extraction/<articleId>.json` (per-study arms) | |
| 7 | `confirm-extract` | **human** | confirms `dispersionType` + `n` on every figure-derived arm | ● |
| 8 | `synthesize` | auto — `metalib` + RVE | `studies.csv`, forest, PRISMA | |
| 9 | `approve` | **human** | signs off on the synthesis | ● |

**Why these four gates.** They are the points where a wrong automated call silently biases the
result and can't be caught downstream:
- **adjudicate-ta / -ft** — inclusion decisions define the sample. An agent's `unsure` is an
  explicit request for human judgment, not a coin flip.
- **confirm-extract** — the accuracy benchmark showed means/effects digitize well but the
  **dispersion type (SD vs SEM vs CI)** and **n** are the error-prone, variance-determining fields.
  Wrong dispersion type changes a study's weight by ~√n. Every figure-derived arm is human-confirmed.
- **approve** — heterogeneity, publication bias, and clustering choices need a human read before the
  number leaves the building.

## Records for human consideration

Two append-only, human-readable artifacts underpin auditability:

- **`decisions/log.jsonl`** — one immutable line per decision, automated *or* human:
  `{ts, stage, actor, action, subject, detail, rationale}`. This is the audit trail — it answers
  "who decided what, when, and why" for every article and every arm.
- **`checkpoints/<stage>.md`** — when the pipeline reaches a gate it writes an editable file listing
  exactly what needs a human call (e.g. the 18 `unsure` abstracts, each with the agent's note and a
  `DECISION:` line). The human edits decisions inline; `pipeline.py resolve <stage>` ingests them,
  logs each to the trail, and unblocks the next stage. Nothing is decided *for* the human silently.

`pipeline_state.json` holds the current stage and per-stage status
(`pending` / `blocked-on-human` / `done`).

## Commands

```
python3 pipeline.py status                # where are we; what needs a human
python3 pipeline.py advance               # run the next auto stage, or open the next gate
python3 pipeline.py open   <stage>        # (re)write a gate's checkpoint for the human
python3 pipeline.py resolve <stage>       # ingest the human's edits, log them, advance
python3 pipeline.py log <stage> <actor> <action> <subject> [detail...]   # manual audit entry
```

## Current position

`identify` and `screen-ta` are done (204 identified → 120 fetched → 6 include / 18 unsure / 96
exclude). The pipeline is parked at the **`adjudicate-ta`** gate: `checkpoints/adjudicate-ta.md`
lists the 18 unsure abstracts for a human to resolve into include/exclude, plus the 6 auto-includes
to spot-check. `resolve` refuses to advance while any `unsure` remain.

## Not yet wired (honest gaps)

Stages 4–9 have state-machine slots and gates but not their runners yet: `screen-ft` (full-text
agent pass), `extract` (drive figure-extractor on the included BDNF figures → per-arm mean/SD/n),
`confirm-extract` opener (list each figure-derived arm with its dispersionType/n for confirmation),
`synthesize` (metalib flatten + RVE forest/PRISMA), `approve`. Built next, in order, behind the
same gate discipline.
