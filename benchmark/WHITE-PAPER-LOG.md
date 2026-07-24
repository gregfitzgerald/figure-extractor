# White-paper technical log

A running record of the technical findings, design decisions, and caveats behind the figure-extraction
work, kept so the eventual white paper rests on the full argument rather than reconstructed memory.
Append new entries as work lands; every claim here should trace to a committed artifact.

Companion artifacts: `benchmark/` (R-GT benchmark), `benchmark/real/` (real-figure golden diff),
`benchmark/classify/` (perception gate), `meta-analysis/VISION-MODEL-METHODOLOGY.md` (the ML design),
`meta-analysis/COMPETITIVE-LANDSCAPE.md` (prior art).

---

## 1. The central architectural finding: geometry is exact, perception is not

Converting a pixel to a data value is a deterministic affine transform. Given exactly correct pixels,
recovery error is **0.00%** on every chart in the corpus -- clean and hard, including log axes and
multi-panel (`benchmark/RESULTS_geometry_floor.md`). Consequence: **100% of extraction error is
point-picking error.** This is the load-bearing framing for the whole paper, because it converts a
vague "digitization is imprecise" complaint into a precisely localized, improvable perception problem.

Corollary for tool design: a digitizer should never be judged on its arithmetic (all of them are
exact); it should be judged on how the points get picked.

## 2. The two-channel result: central tendency is free, dispersion is not

Every reader tested -- exact-pixel floor, simulated human clicks, a CV auto-reader, and a real vision
agent -- recovers **central tendency (bar means, box medians) to ~0.5%** and fails on **dispersion
(error-bar caps) at 4-18%**. The split is stable across tools, chart types, and (see §5) real figures.

| tool | central median | dispersion median | dispersion worst |
|---|---|---|---|
| geometry floor (exact pixels) | 0.00% | 0.00% | 0.00% |
| human click, 0.5 px jitter | 0.22% | 2.09% | 18.70% |
| human click, 1.0 px jitter | 0.44% | 4.15% | 37.34% |
| human click, 2.0 px jitter | 0.89% | 8.23% | 74.42% |
| CV auto-reader (bars) | 0.45% | 8.89% | 21.45% |
| vision agent (real read) | 1.17% | 8.20% | -- |

## 3. Why dispersion is hard (the mechanism)

A bar top has the full chart height beneath it, so a 1-pixel slip is a tiny fraction of the value. An
error cap sits only a few pixels above the bar top, so **the same 1-pixel slip is a large fraction of
the cap-to-top distance** -- which *is* the dispersion. Short caps (SEM at large n, tight CIs) are
therefore the worst case, and the benchmark confirms it: the largest errors always land on the
shortest caps.

**The consequence chain (state this explicitly in the paper):** a *b%* error in the cap becomes
roughly a *2b%* error in the variance, which mis-weights the study by roughly sqrt(n) in the pooled
model. Dispersion error is not a cosmetic inaccuracy; it propagates into study weights and therefore
into the pooled estimate and its CI.

## 4. The human-in-the-loop claim (the paper's provocative core)

The `human_floor` sweep simulates a *correct* human click carrying only realistic sub-pixel jitter.
At 1 px it yields **4.15% median / 37.3% worst dispersion error** while central tendency stays at
0.44%. This supports a strong claim: **human click imprecision is an irreducible error source on
short marks**, so a sub-pixel deterministic reader can be *more precise than a human*, making "take
the human out of the digitization loop" defensible.

**Prior-art gap that makes this novel.** WebPlotDigitizer's validation base (Drevon 2017; Burda 2017,
ICC > 0.95; Kadic 2016) measures *human-vs-human agreement* and *assumes good clicks* -- and never
isolates the dispersion channel. It therefore cannot detect this error, and the field has been
reporting a precision figure that hides the failure on exactly the quantity meta-analysis depends on.

**Where the human should move (not be removed entirely):** the *dispersion type* (SD vs SEM vs CI95)
is textual -- it lives in the caption -- not visual. Type cannot be read from pixels at all. So the
honest proposal is: machine does the pixel measurement; human confirms the *semantic* fields (type,
Direction, series identity, n), which is where human judgment is actually superior.

## 5. Real-figure transfer: the pattern holds and the conclusion reproduces

Run against a completed dissertation MA where a human expert hand-coded the values
(`benchmark/real/`): 144/161 rodent rows are figure-derived across 43 articles, **all 43 resolve to a
local PDF and crop cleanly** (data access is not the constraint; per-panel labor is).

Pilot (6 panels / 3 articles / 8 comparisons): **central 0.47% median, dispersion 3.67% median /
18.1% worst** -- the synthetic pattern transfers, with a transfer-gap Delta of ~0 against the
synthetic 1px human floor. End-to-end through metafor `escalc`/`rma`: pooled Hedges g **coded +0.487
vs extracted +0.475** (delta -0.013, coincident CIs, **0/8 sign flips**). The automated read
reproduces the hand-coded meta-analytic conclusion.

Scope caveat to state plainly: the reference is *human coding*, so this measures **agreement /
transfer**, not absolute accuracy (the accuracy claim lives in the synthetic benchmark against R's
exact descriptives). And the reader was a general vision model, **not a trained detector** -- so this
establishes the agent baseline and confirms the gap transfers; it does not yet prove a detector beats
the agent.

## 6. Realism findings that only appear on real figures

- **Significance asterisks sit directly over error caps.** A one-shot read confuses them and
  over/undershoots the cap by 30-45 px (**22-36% dispersion error**) until the panel is re-cropped at
  2-3x zoom. This is a concrete, nameable failure mode a specialist detector removes -- good evidence
  for the ML case, observed on real data.
- Real panels also carry anti-aliasing, JPEG compression, and non-flat fills that defeat the
  color-thresholding approach that works trivially on synthetic renders.

## 7. R as the ground-truth engine (methodological contribution)

R simulates the raw data -> computes the full descriptives -> renders the chart *from that data* ->
exports the exact device pixel coordinates of every drawn mark. Ground truth is therefore **what the
chart was made from**, not what a human read off it.

Technical notes worth publishing: `"device"` is not a valid grid unit (the obvious approach fails);
the working path is `ggplot_build()` panel ranges + `grid::deviceLoc()`; log axes require applying the
transform (build data are in native/log10 units). **Independently validated**: detected ink vs R's GT
pixels agree to **median 0.44 px, max 1.75 px** across bars, points, and every multi-panel facet.
The Python affine used by the harness was cross-checked against the browser tool's `calibrate` to
**0.000e+00** over 184 points, so the harness *is* the tool's arithmetic.

## 8. Classification is at ceiling -- which relocates the problem

80 images, **18 chart types across 12 R libraries** (base / ggplot2 / lattice + 9 specialists), each
in a plain and a deliberately cluttered "dense" tier: **charType accuracy 1.000 (80/80), macro-F1
1.000, 0 extraction-priority flips (no forest->bar), ECE 0.072**, and the **dense tier did not
degrade** (40/40 == plain). Aux labels: dispersion-present F1 1.00, non-data-ink micro-F1 0.99.

Interpretation for the paper: *knowing what a chart is* is not the bottleneck. This is a positive
result that **narrows the ML case** to localization + structure, and it validates the
perception/meaning split (the model classifies and locates; the agent interprets).

Honest bound: this is clean synthetic renders. The fragility frontier is the hard pairs
(funnel<->scatter, dose-response<->line) under real-figure noise; the untested quantity is
acc(synthetic) - acc(real).

## 9. The three silent-catastrophic-error classes (design principle)

Errors that are *plausible-looking and uncatchable downstream* deserve mandatory human gates. Three
have been identified, all of which corrupt the result while looking fine:

1. **Dispersion type** (SD vs SEM vs CI95) -- visually identical; wrong type mis-weights by ~sqrt(n).
   The model must **never assert type from pixels**; it reports only `dispersion.present`.
2. **Direction** (+1/-1; latency and error-count outcomes are lower-is-better) -- a wrong sign
   silently cancels real effects in the pool. Carried as a *field*; raw landmarks are never mutated
   (you cannot negate a mean).
3. **Series / group assignment** (new, see §10) -- attaching a correct number to the wrong arm
   computes the effect backwards or mixes conditions.

## 10. Series / group parsing: the missing perception layer (current work)

Perception decomposes into three sub-tasks; two are measured, one is not:

- **Classify** -- what kind of chart is this? (measured: ceiling, §8)
- **Localize** -- where are the marks? (measured: the dispersion problem, §2-3)
- **Parse** -- *which marks belong to which series/group, and what does the legend call them?*
  (**unmeasured**)

A grouped bar chart is "Control vs Run" nested inside "2/4/8 weeks"; a two-color scatter is two IVs.
Until that structure is recovered, a correct mean+SD has no home. Mis-assignment is the third silent
catastrophic error (§9).

**Where ML helps, split by half:**
- *Legend text -> semantic label* ("the blue swatch reads 'Control'"): language+vision reasoning with
  actual words in it; the agent should own this, consistent with §8's result. Probably no bespoke
  model needed.
- *Structural grouping / instance assignment* (each mark -> its series, especially dense/occluded
  scatter, many-series lines, deep grouped/stacked bars): **the genuine ML win.** Implement as a
  *series-aware head on the landmark detector* -- every detected mark carries group id + series id +
  a pointer to its legend swatch -- rather than a separate model.

Division of labor stays clean: **the model outputs structure; the agent binds structure to meaning.**

**Benchmark feasibility (why this is cheap):** the R generator already draws grouped, dodged, and
stacked bars and multi-series scatter/line *from labeled data*, so it already knows each mark's
series/group and the legend mapping. The answer key exists; only the export and the scorer are new.
Metric to lead with: a **mis-assignment rate** (the catastrophic-error metric), not just accuracy.

## 11. Evaluation-integrity practices worth reporting

- **Leak-free tasks**: prompts carry the rubric and the allowed label sets but never the answers.
- **Anonymized images** (shuffled `img_XXXX` map) so chart type cannot be inferred from a filename.
  This caught a real defect: two prediction rows were transposed at serialization; the checksum
  cross-check localized it to write-time (not perception) and it was corrected. **A filename-keyed
  eval would have silently mis-scored it.**
- **Label space imported live from the tool's own vocabulary** (`CHAR_VOCAB`), so a passing prediction
  is by construction a valid tool input and the eval cannot drift from the product.
- Corpora are **seeded and regenerable**; generated artifacts are gitignored, code and labels committed.

## 12. Open questions / what would change the conclusions

- Does a *trained* detector actually beat a general agent-with-CV on real figures' dispersion channel?
  (The one experiment that would justify building the model. Not yet run.)
- What is acc(synthetic) - acc(real) for classification on the hard pairs?
- Does series parsing degrade on dense/occluded charts enough to warrant a detector head? (§10, next)
- Scale: the real-figure pilot is 6 panels; committee-grade is ~120 rows plus a second human reader
  for an accuracy envelope, and the full 3-level `rma.mv(~1|article/row)`.
