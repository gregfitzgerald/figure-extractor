# Where we are — meta-analysis pipeline status

A plain-language map of what exists, what it does, what's done, what's not, and the exact decisions
waiting on you. Written to clear up confusion so we can address each point systematically.

---

## 0. THE CORPUS MUST BE RE-FETCHED BEFORE ANY RESULT IS REPORTED

**The screened corpus is not the search result.** `corpus.py` capped `retmax` at 120 against
204 hits, and PubMed's esearch returns **most-recent-first** -- so the 85 records it dropped
were the 85 **oldest**. The fetched corpus spans 2013-2026; everything before mid-2013 is
absent, including the foundational Neeper / Russo-Neustadt-era exercise-BDNF studies this
question is built on. Verified by re-running the identical query live and diffing: 85 hits
present in PubMed, absent from `candidates.json`, PMIDs 9795193 (1998) through 23411461 (2013).

Nothing flagged it. This document called the 120 "the tightened set"; PIPELINE.md wrote
"204 identified -> 120 fetched" as though it were a filter; the PRISMA block recorded
`fetched: 120` with no `not_fetched`. It reads like a deliberate restriction and was an
off-by-cap.

This is a **recency selection bias baked into the sample before a single figure is read**, and
it would propagate into any pooled estimate. The screening decisions already made are still
valid for the 120 they cover -- nothing needs undoing -- but the corpus is incomplete.

`corpus.py` is fixed: esearch now paginates to completion and *refuses* to write a partial
corpus. What it cannot do for you is decide the research question:

- **Re-run `python3 corpus.py`**, then screen the ~85 added records (title/abstract) and
  re-open the adjudication gate. This is the correct action if the review is meant to cover
  the literature.
- **Or** deliberately restrict the protocol by date and say so in the PRISMA diagram and the
  write-up -- a defensible choice, but it must be a stated inclusion criterion, not an artifact
  of a fetch limit.

Left for you because re-running the search changes your sample, and that is a research
decision, not a code fix.

---

## 1. The big picture (what we're building and why)

You asked for two things to eventually work in concert:

1. **figure-extractor** (the browser app) — digitizes charts in PDFs into numbers.
2. **A real meta-analysis** that consumes those numbers — with **human input at the load-bearing
   steps** and **a written record of every decision** for you to review.

This document is about #2 and how it plugs into #1. The meta-analysis topic (locked in `PROTOCOL.md`)
is deliberately narrow:

> **Does voluntary wheel-running raise hippocampal BDNF protein in healthy adult rodents, vs.
> sedentary controls?**

Narrow on purpose: the data is usually locked in bar-chart figures (exactly what figure-extractor
reads), and one paper often reports several comparisons — which forces the rule you insisted on:
**the unit of analysis is the *study*, and one article can contain several studies.**

---

## 2. The core idea I just implemented: a pipeline with human gates

A meta-analysis is a conveyor belt: find papers → screen them → pull the numbers → combine them.
The danger in automating it is that a wrong call early on (wrong paper included, wrong error-bar
type read) silently poisons the final number and can't be caught later.

So I built the conveyor belt as a **state machine with four stop points ("human gates")**. At a gate,
the pipeline **physically halts** and will not continue until you make a decision. Everything the
machine or you decide is written to an **append-only log** so nothing is silent.

That's the whole concept. The rest is detail.

---

## 3. The nine stages (and the four gates)

| # | Stage | Who does it | Gate? | What it means |
|---|-------|-------------|:-----:|---------------|
| 1 | `identify` | machine | | Run the PubMed search, download candidate papers. |
| 2 | `screen-ta` | AI agents | | Read each **title + abstract**, sort into include / exclude / unsure. |
| 3 | `adjudicate-ta` | **YOU** | ● | Resolve every "unsure"; override any AI call you disagree with. |
| 4 | `screen-ft` | AI agents | | Read the **full text** of survivors, drop with a coded reason. |
| 5 | `adjudicate-ft` | **YOU** | ● | Confirm the final list of included papers. |
| 6 | `extract` | agents + figure-extractor | | Pull each study's numbers (mean, error bar, n) from figures. |
| 7 | `confirm-extract` | **YOU** | ● | Confirm the **error-bar type (SD/SEM/CI) and n** on every figure. |
| 8 | `synthesize` | machine | | Combine into effect sizes, forest plot, PRISMA diagram. |
| 9 | `approve` | **YOU** | ● | Sign off on the final result. |

**Why those four are gates (not the others):**
- **Stages 3 & 5 (inclusion):** which papers are in *defines the answer*. An AI "unsure" is it asking
  you to judge — not guess.
- **Stage 7 (error-bar type):** our accuracy tests showed the app reads *means* almost perfectly, but
  whether an error bar is SD vs SEM is easy to get wrong — and getting it wrong changes a study's
  weight by roughly √n. So a human confirms it every time.
- **Stage 9 (final):** someone should read the heterogeneity / bias story before the number ships.

---

## 4. The two record files (this is the "records of all decisions" part)

| File | What it is |
|------|------------|
| `decisions/log.jsonl` | The **audit trail**. One line per decision, by machine or human: timestamp, stage, who, what, and why. This answers "who decided what, when, and why" for every paper. |
| `checkpoints/<stage>.md` | The **worksheet** the pipeline hands you at a gate. It lists exactly what needs your call (e.g. the 18 unsure abstracts). You edit decisions right in the file; `resolve` reads them back, logs each, and unblocks the next stage. |

`pipeline_state.json` just remembers which stage we're on.

---

## 5. What actually ran, and the result so far

The search + title/abstract screening **have already run on real PubMed data**:

```
204 papers found by the search
120 downloaded (the tightened set)
        |
        v  AI agents read title + abstract
  6 include   +   18 unsure   +   96 exclude
                                   (96 broke down as: 60 wrong population,
                                    24 wrong outcome, 10 wrong intervention, 2 reviews)
```

The pipeline is now **parked at Gate 3 (`adjudicate-ta`)**, waiting for you.

---

## 6. What is built vs. NOT built (honest inventory)

**Built and tested:**
- `pipeline.py` — the state machine, the decision log, the gate open/resolve mechanism.
- Stage 1 `identify` (`corpus.py`) — the PubMed search, already run.
- Stage 2 `screen-ta` (`screen.py`) — title/abstract screening, already run.
- Gate 3 `adjudicate-ta` — opens the worksheet; refuses to advance while any "unsure" remain (tested).
- `metalib.py` — a Python effect-size prototype (Hedges' g); passes its 8 toy test cases. **Corrected
  after review (see AUTOMATED-MA-VISION.md §7): NOT the math core.** It cannot reproduce a real MA
  (no `Direction` sign-flip → wrong-signed effects; no Morris pre-post; CI→SD uses 1.96 at n≈8; box
  conversion drops the Wan correction). Inference is being moved to **R (metafor/clubSandwich)**;
  metalib survives only as a non-authoritative sanity check.

**NOT built yet (the honest gaps — they have gate slots but no runner):**
- Stage 4 `screen-ft` — full-text screening pass.
- Stage 6 `extract` — the bridge that drives figure-extractor over the included BDNF figures and
  writes each study's mean/SD/n. **This is the seam where the two halves of the project meet.**
- Stage 7 `confirm-extract` worksheet generator.
- Stage 8 `synthesize` wiring (the math exists; it's not hooked to the pipeline).
- Stage 9 `approve`.

---

## 7. The decisions actually waiting on YOU

Nothing here is urgent or one-way, but these are the open points:

1. **Adjudicate the 18 "unsure" papers (Gate 3).** This is the live one. Open
   `checkpoints/adjudicate-ta.md`, change each `DECISION: unsure` to `include` or `exclude`, then
   we run `resolve`. (Several look like edge cases — e.g. adolescent rats, disease-model papers with
   a healthy control arm, mRNA-vs-protein ambiguity — genuinely your call.)
2. **Do you want to walk that gate yourself, or have me pre-fill a recommendation** for each unsure
   paper (with reasoning) that you then just approve or edit? Either fits the design.
3. **Which runner do I build next** — `screen-ft` (full-text screening) or jump to `extract` (the
   figure-extractor bridge, the most novel part)?
4. **Is the topic itself still what you want?** Everything is topic-agnostic; swapping it is cheap
   now, expensive after extraction.

---

## 8. How to see it yourself

```
cd /mnt/c/Users/gregs/figure-extractor/meta-analysis
python3 pipeline.py status        # the stage map + where we're parked
```

Key files, all under `C:\Users\gregs\figure-extractor\meta-analysis\`:
- `PROTOCOL.md` — the locked study plan (the "what").
- `PIPELINE.md` — the machine design (the "how"); this STATUS.md is the plain-language version.
- `pipeline.py` — the orchestrator.
- `checkpoints\adjudicate-ta.md` — the worksheet waiting for your decisions.
- `decisions\log.jsonl` — the audit trail so far.
- `data-model.md`, `test-cases.md` — the article→studies data structure and its approved tests.
