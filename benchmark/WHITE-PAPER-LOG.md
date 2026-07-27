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

## 10a. Series parsing: audit findings (verified in code, 2026-07-24)

A code audit ahead of building the series tier found that series structure is **not absent from the
tool -- it exists in five places, each stopping one step short.** All four checkable claims were
independently verified:

1. **The series index is computed and then dropped.** `runExtraction` carefully preserves each
   digitized point's series index (`s: p.s || 0`, figure-extractor.html:4820), but
   `authoritativeRows` emits only `{landmarkKind:'point', x, y}` (line 4134) -- so a two-colour
   scatter exports as **one undifferentiated cloud**. The information survives the whole pipeline and
   dies at the last step. Cheapest high-value fix in the project.
2. **Extraction flags never reach the CSV.** `LANDMARK_HEADER` (line 4118) has **zero flag columns**,
   so `dispersion-type-uncertain` -- the flag whose entire purpose is to make uncertainty non-silent
   -- is invisible in the artifact handed to R. A guard that fires into a void is not a guard. This
   directly undercuts the design principle in section 9.
3. **`CHAR_VOCAB.role`** (control/intervention/comparison/...) is defined but **never validated and
   never read** -- `validateCharacterization` ignores it entirely. The vocabulary for arm identity
   already exists and is inert.
4. **`panel.series[]`** is documented in the extraction skill but read exactly once (for `nSource`),
   unvalidated, unkeyed, and unlinked to any landmark.

Plus a live defect worth reporting: `digAutoTrace` scans the whole crop **including the legend**, so a
legend swatch of the traced colour injects phantom data points.

**Scope correction to section 5 (important, and it qualifies a headline).** The real-figure golden-diff
tasks (`benchmark/real/tasks/*.json`) **pre-declare `control_bar` and `interv_bar`** -- the reader was
*handed* the arm assignment. So that experiment measured reading accuracy (the dispersion channel and
the end-to-end reproduction) but **did not measure series parsing at all**; the "0/8 sign flips" result
demonstrates correct *measurement*, not correct *arm identification*. Those same pre-declared fields
are, conveniently, a ready-made answer key for scoring parsing on real figures later.

**The modeling decision that falls out of the audit:** there are **two** structuring dimensions, not
one -- `group` (categorical-axis position; usually a moderator/timepoint) and `series` (legend entry;
usually an arm). Every landmark should declare `(groupId, seriesId)`, with a plain bar chart as the
degenerate case. Keep `id` (join key), `label` (printed text, model-read), and `role` (meaning,
agent-assigned) as three separate fields with separate confidences -- the same model-reads-glyphs /
agent-assigns-meaning boundary already used for dispersion type.

**Why this is a precondition, not a nicety:** without recovered series structure there is no way to
know that two rows share a control arm, so the multi-arm variance correction (`VIF_multiarm`) cannot
be applied and those studies are **silently over-weighted**. Series parsing is upstream of a
correctness property in the statistics, not just a labelling convenience.

**Why `Direction` does not save you:** `Direction` fixes outcome *polarity*, not arm *order*. A
swapped assignment produces a legitimate-looking negative `g`; no range check, residual check, or
downstream test detects it. This is what makes mis-assignment a silent catastrophic error rather than
a detectable one -- and it is why the guard must never *auto-repair* a suspected order mismatch by
swapping labels, which would convert a detectable error into an undetectable one.

Full design: `benchmark/SERIES-PIPELINE-INTEGRATION.md`.

**Implemented (2026-07-24, commits 003b159 + gate preview).** All four defects fixed and the
"make mis-assignment visible" half of the design shipped: `LANDMARK_HEADER` gains
`groupId`/`seriesId`/`seriesLabel`/`flags`; `EXTRACT.bars`/`.boxes` pass structure through instead of
stripping it; point rows carry the digitizer's series index; `validateCharacterization` enforces
`role`/`encoding`/`labelSource`, unique+present series ids, refuses an unlabeled series, and refuses a
silent legend/plot order mismatch; `validateSeries()` supplies four deterministic review triggers
(legend-order-mismatch, similar-series-colors, series-count-uncertain, series-unlabeled) with no model
in the loop; `previewAssignment()` emits the B4 gate artifact **ordered by the measured danger** --
swatch->label->role binding first, structure as secondary context -- and blocks on an unassigned role;
`digAutoTrace` gained `excludeRects` + diagnostics so the legend is no longer scanned.
Locked in by `scripts/test_series_layer.py`; full suite green; benchmark geometry floor still 0.00%.

## 10b. Series parsing: measured (2026-07-24) -- and the ML case here is COST, not accuracy

Built `benchmark/series/` (GT engine `sgt.R`, corpus generator, audit, leak-free anonymized tasks,
a deterministic colour-clustering baseline, scorer with self-test). **Legend ground truth turns out to
be free and exact**: after `grid.force()`, ggplot2 places every legend key in a viewport
`key-<r>-<c>-bg` and its label in `label-<r>-<c>`, so `seekViewport` + `grid::deviceLoc` yields swatch
and label pixels in the same convention as marks, **and the label string is read off the drawn text
grob**. Mark->series binding is recovered from the *drawn aesthetics* (dodged x + fill/colour/shape),
never row order. Audit: 495/495 and 229/229 marks on ink; 53/53 and 22/22 legend swatches correct.

| reader | corpus | **bound mis-assignment** | structural | ARI | naming | sign flips |
|---|---|---|---|---|---|---|
| vision agent | base (19 charts, 495 marks) | **0.000** (0/495) | 0.000 | 1.00 | 57/57 | 0/145 |
| vision agent | stress (4 charts, 229 marks) | **0.048** (11/229) | 0.048 | 0.93 | 22/22 | 0/67 |
| colour-clustering head | base | 1.000 *(names nothing)* | 0.143 | 0.75 | 0/57 | -- |
| colour-clustering head | stress | 1.000 | 0.459 | 0.43 | 0/22 | -- |

Base tier was **zero in every stratum** -- chart type, difficulty, cue (colour/shape/both/position),
occlusion including `severe`, legend style including inside-panel and direct-labelled, and all three
legend-order traps. By the rule of three the 95% upper bounds are 0.61%/mark, 5.3%/label, 2.1%/effect.
A stress tier was added because the base did not break the reader; **all 11 errors and all 10
abstentions fall on a single chart** (six levels of one sequential blue at ~6 px overlapping markers).
Repeated hues (8 series/4 colours x filled-open x solid-dashed), a 5-step grey ramp, and 1.5 pt
monochrome glyphs all scored 0.000.

**Revision to section 10's prediction.** I expected dense/occluded scatter to break the agent and
therefore justify a series-aware detector head *on accuracy*. It does not: the agent is at 0.000
across the base corpus and 3 of 4 stress charts, and on the one chart where it fails it is still
**4.6x better than the colour head** (0.115 vs 0.531). The head also fails *complementarily* (56.8% on
shape-cued monochrome), so it would have to be glyph-aware, not colour-clustering. **What survives is
a cost argument** -- the agent's clean score cost ~51 tool calls / ~122k tokens on the hardest chart,
because it crops and upscales 8-29x rather than glancing -- **and the unmeasured real-figure transfer
gap**, which remains the only thing that could still justify a head on accuracy.

**The danger asymmetry (new, and it relocates the gate).** The scorer's injected-error self-test:

| injected error | structural metrics | ill-formed arms | **effect sign flips** |
|---|---|---|---|
| two legend labels swapped (clustering perfect) | **perfect** (0.000, ARI 1.000) | 0 | **44/145 = 30.3%** |
| 15% random structural noise | visibly degraded (0.168, ARI 0.559) | 41 (detectable) | 3/103 = 2.9% |

**Naming errors are ~10x more damaging than structural errors and are invisible to every structural
metric, while structural errors are less damaging and self-announcing** (ill-formed arms). Therefore
the mandatory human gate belongs on **swatch -> arm-name binding**, not on clustering -- which is
exactly the half the model should *not* own (section 10: model reads glyphs, agent assigns meaning).

**Selective prediction already works.** On the stress tier every mark above 0.5 confidence was correct
(133/133); all 11 errors sat at 0.18-0.30 confidence and abstentions landed on alpha-blended pixels. A
`conf <= 0.5` gate converts the residual failure into *flagged coverage loss* rather than silent
corruption -- the abstain-and-escalate property the pipeline is built around.

**Caveat to state in the paper:** these readers did not glance at images -- they cropped, upscaled
8-29x, and built seam montages. The claim is "an agent allowed to inspect adaptively parses this
corpus", not "VLMs parse series perfectly". Everything here is synthetic.

## 10c. Subfigure (panel) detection: measured diagnosis (2026-07-26)

Panel decomposition -- splitting a compound figure into A/B/C -- is the weakest link in the tool.
Investigated by probing the real corpus rather than reasoning from intuition. Four findings:

**1. Every PDF in the corpus is born-digital (43/43).** A text layer exists throughout, which
initially suggested panel structure could be recovered exactly from PDF vector objects instead of
pixels.

**2. That hypothesis is FALSE for these papers, and the negative result is the important one.**
Inside Docling-identified figure regions there are **zero panel-label text spans** -- the only text
is the page header/footer. The figures are **flattened bitmaps**: e.g. Chandler 2020 Fig. 2 is a
single 2012x1402 px image XObject covering the entire 483x336 pt figure, with the letters A-F baked
into pixels. Authors export from Illustrator/GraphPad and the labels stop being text. So panel
localization **cannot** be read off the PDF; it is genuinely a computer-vision problem. (Partial
exception worth exploiting: some figures are composed of *several* image XObjects -- Chandler Fig. 4
is 8 -- and those boundaries are exact and free when present.)

**3. Docling solves the OUTER problem well, but not the panel problem.** In 33 s it returned exact
figure bounding boxes *and correctly associated each caption* (the genuinely hard part) for all 4
figures. What it does not do is decompose a compound figure -- DocLayNet's classes are page-level
(Picture, Caption, Text...), so "Picture" is the whole multi-panel figure. Docling is the right tool
for figure+caption detection and the wrong tool for panels.

**4. The current detector's failure modes are specific and code-level.** `suggestSubfigures`
(recursive XY-cut projection) (a) downsamples to 480 px on the long edge, so an 8 px gutter in a
2000 px figure survives as ~2 px; (b) requires a gutter >= 2.5% of the dimension, i.e. ~12 px at that
scale, so tight journal gutters never split; (c) thresholds ink at grey < 205, so light axes vanish
and tinted backgrounds read as solid ink; (d) requires a gutter to hold <= 6% of peak ink, so a
legend or shared axis label sitting in the gutter blocks the cut; (e) only recurses into regions
>= ~19% of the figure; and (f) being XY-cut, it can only express **guillotine** partitions, so any
non-guillotine layout is unreachable in principle.

**The lever that is being underused: the caption is ground truth.** "(A) ... (B) ... (F)" states the
panel count and letters exactly. Today that count is used only to *merge* an over-split result; it
should be a **hard constraint** that turns unconstrained detection into constrained assignment
(find exactly N panels; if the detector disagrees with the caption, that is a flag, not a silent
answer). Combined with the panel-label glyphs (detectable by OCR/detector since they are pixels) and
the existing chart classifier as a verifier -- a correct crop classifies confidently, a bad split
classifies "unknown" -- this is the path from ~80% to near-perfect on chart panels.

**Free training data already exists:** the R generator knows the exact pixel box of every panel it
draws, so a panel-detector training/eval set with exact ground truth costs nothing to produce.

**Honest bound:** near-perfect is reachable for *chart* panels with gutters and captions. Flush
micrograph montages with no gutters and no labels are ambiguous even to a human reader, and no
method will resolve them without the caption's help.

## 10d. Panel detection rebuilt: the measured arc, and the limit of pixel-level verification (2026-07-26)

Rebuilt subfigure decomposition as a **cascade with verification and abstention**, driven by three
adversarial rounds. Independently re-measured at every step against `benchmark/panels` (41 figures /
159 panels, GT audited to 0.0 px with all ink claimed).

| metric | legacy XY-cut | final cascade |
|---|---|---|
| median panel IoU | 0.407 | **1.000** |
| IoU >= 0.9 | 10.1% | **88.1%** |
| exact panel count | 75.8% | **95.1%** |
| label accuracy | 87.5% | **100.0%** |
| silent mislabels | -- | **0.0%** |
| answered-only exactly right | -- | **100.0%** |
| error rate on answered | 66.7% | **0.0%** |
| coverage | -- | 65.9% (75.8% on the original corpus) |

Strata that were completely dead now work: **flush (zero-gutter) 0.000 -> 0.997 medIoU**,
**bottom-right labels 0% -> 100%**, **non-guillotine 0.107 -> 0.925**.

**The caption is the single biggest lever, quantified.** Removing the caption prior drops exact-count
from 75.8% to **9.1%** and raises spurious boxes from 69 to **226** (a single-panel control shatters
into 7). Panel decomposition is not really unconstrained detection; it is constrained assignment, and
the constraint is free text the paper already gives you.

**The adversarial arc is the finding.** Each round's fix created the next round's exploit:
- *Round 1* found 7 defects, all of one class: **letter identity was never verified on any `ok=true`
  path**. The XObject fast path invented letters by reading order at conf 0.95 with zero flags;
  `label-order-mismatch` was non-critical so the detector saw the mislabel and shipped it; a caption
  citing *another paper's* "(a) and (b)" manufactured a 2-panel split of a single-panel figure; and
  the glyph matcher could not discriminate at all (cross-letter Dice >= 0.7 for nearly every pair,
  b<->h 0.94) -- the "verification" was noise.
- *Round 2* fixed those and reached 0.0% error on answered -- but **abstained on 31 of 33 figures**
  (coverage 6.1%, abstention precision 0.48, net figures saved -1). Correct and useless. The dominant
  cause was mundane: a single scatter dot touching a glyph merges the connected component.
- *Round 3* recovered coverage to 72.7% at unchanged 0.0% error -- and an adversary then **broke it
  with three runnable kills**, because the safety argument was unsound. "Every box owns exactly one
  distinct expected letter" proves nothing about whether those glyphs are *labels*. Stray
  compact-letter-display letters, crossed axis units "(A)"/"(B)", and legend keys all forged the
  verification and shipped swapped names at conf 0.8-0.92.

**The repair, and the general principle.** Verification now tests **label plausibility over the anchor
SET**, not letter identity per glyph: every anchor must sit in its panel's edge band, at a consistent
position and size *across the whole figure*. Real-world distractors (CLD letters, axis units, legend
keys, inset letters) all fail this because none of them sit at panel corners. Coverage went **up**
(72.7% -> 75.8%) while the exploits died -- the gate cost nothing on real figures (0
`label-placement-implausible` flags across the original 33).

**The irreducible limit, stated honestly.** A deliberately forged stray letter placed *at a panel
corner, at label size, consistently across panels* remains indistinguishable from a real label --
because at the pixel level it **is** one. No geometric predicate can separate them; only semantics can
(does panel A's content match what the caption says "(A)" shows?). That is precisely the
model-reads-glyphs / agent-assigns-meaning boundary this project already draws elsewhere, and the
escalation path already exists: the meaning-aware agent and the human gate. The detector should not
claim to solve it.

**A benchmark lesson worth publishing.** Round 3's exploits scored **100% on the benchmark** before
they were found, because the corpus contained no figure with a stray expected-letter glyph. A metric
that cannot see a failure mode reports its absence as success. The corpus was extended (L6 stray
letters, L7 9-and-12-panel, L8 serif-italic) and the pre-fix detector scores 5.0% silent mislabels /
50% error-on-answered on those 8 -- the corpus now proves itself. `score.py` also gained an
**answered-only** exactness figure, because the headline "whole figure exactly right" counts
abstained-but-would-have-been-right figures and therefore flatters.

**Still open (all abstain honestly -- coverage cost, not correctness):** two flush pinwheels need true
rectangle-tiling inference from anchors (the pixel-vote carve provably produces overlapping boxes, and
grid seams cannot express a pinwheel -- a different algorithm, not a threshold); figures with mixed
label conventions (A-C top-left, D bottom-right) are rejected by the consistency requirement; and two
12px bold-sans glyphs (G, D) fail the runner-up margin, which was deliberately *not* loosened.

## 10e. Known limitation to address later: one caption letter, several visual tiles

Real journal captions frequently write "(A)" for something drawn as **several separate tiles** --
present in **8 of the 14 Tier-1 real-validation figures**, and in **zero** of the 41 synthetic ones.
This attacks the cascade's single biggest lever directly: the caption-count constraint (removing which
drops exact-count from 95.1% to 9.1%). When the caption says 5 letters and the image shows 12 tiles,
the hard constraint is *correct about arms and wrong about geometry*.

**Decision taken for now: flag and escalate, do not silently reconcile.** Teaching the cascade that one
letter may span k tiles would weaken the very constraint that makes everything else accurate, so the
detector should detect the mismatch and abstain rather than guess a grouping. The Tier-1 human
annotation will measure how often this actually bites, and that number decides whether it is worth
building a letter-spans-tiles model.

Related real-corpus gaps with no synthetic counterpart (all found by surveying 222 real figures):
non-`[A-Z]` label systems (primes, `A-(a)`, `a.i`), caption formats (`A)`, `A,`, `Panel A`, letters
buried in prose), positional-only captions ("left", "top row"), tables/blots/equations serving as
panels, section-heading bands inside figures, and **non-bar central-tendency landmarks** (a mean line
over a point cloud -- increasingly the modern default and outside the `bar-top -> mean` model the
harness assumes).

Conversely, strata the synthetic ladder tests that the real corpus does **not contain at all**:
heatmaps and colourbars (0 of 222 figures), top-centre and bottom-right label placement (real papers
use bottom-*left*), 14 of the 18 classified chart types, and near-absence of true non-guillotine
layouts (1 verified instance vs 15% of the synthetic ladder). Those results must be labelled
synthetic-only rather than presented as validated capability.

## 11. Evaluation-integrity practices worth reporting

- **Leak-free tasks**: prompts carry the rubric and the allowed label sets but never the answers.
- **Anonymized images** (shuffled `img_XXXX` map) so chart type cannot be inferred from a filename.
  This caught a real defect: two prediction rows were transposed at serialization; the checksum
  cross-check localized it to write-time (not perception) and it was corrected. **A filename-keyed
  eval would have silently mis-scored it.**
- **Label space imported live from the tool's own vocabulary** (`CHAR_VOCAB`), so a passing prediction
  is by construction a valid tool input and the eval cannot drift from the product.
- Corpora are **seeded and regenerable**; generated artifacts are gitignored, code and labels committed.
- **Confidence-vs-visibility as a leak detector.** Reader confidence tracked a pixel-audit visibility
  annotation the readers never saw (0.958 visible / 0.868 occluded / 0.600 hidden), and the single
  lowest-confidence mark in the base corpus was the one mark the audit independently flagged as fully
  hidden. Agreement between self-reported confidence and an unseen difficulty annotation is evidence
  the reader is measuring the image rather than exploiting the task format.

## 12. Open questions / what would change the conclusions

- Does a *trained* detector actually beat a general agent-with-CV on real figures' dispersion channel?
  (The one experiment that would justify building the model. Not yet run.)
- What is acc(synthetic) - acc(real) for classification on the hard pairs?
- Does series parsing degrade on dense/occluded charts enough to warrant a detector head? (§10, next)
- Scale: the real-figure pilot is 6 panels; committee-grade is ~120 rows plus a second human reader
  for an accuracy envelope, and the full 3-level `rma.mv(~1|article/row)`.
