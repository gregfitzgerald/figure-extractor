# Real-figure validation: measurement and analysis plan (PRE-REGISTRATION)

**Status: pre-specified. Frozen before any real-figure ground truth exists.**
Every threshold, stratum, sample size, split assignment and decision rule below was written
before a single real annotation was collected. The point of writing it now is that it cannot
be adjusted after the numbers are seen. Any change after the LOCK set is scored must be
recorded in section 12 as an amendment with a date and a reason, and the affected result must
be relabelled *post hoc / exploratory*.

- Written: 2026-07-27
- Scorer: `score_real_validation.py` (this directory)
- Frozen synthetic comparators: `synthetic_reference.json` (this directory)
- End-to-end model: `golden_diff_rv.R` (this directory)
- Sampling frame and worklist: owned by the sampling protocol (not this file). This plan
  states the *requirements* the sample must satisfy; it does not choose the figures.

---

## 0. TL;DR

Three questions, three annotation tiers, one pre-committed metric set.

| tier | question | unit | reference | what is claimable |
|---|---|---|---|---|
| **D** detection | does Docling's figure bbox + caption association hold beyond N=1? | figure | human-drawn box, human-confirmed caption | **accuracy** (the human is a valid reference for "which box, which caption") |
| **P** panels | what is the synthetic->real transfer gap in panel decomposition? | panel | human-drawn panel boxes + letters | **accuracy** (the human is a valid reference for boxes, counts, letters) |
| **E** extraction | how do classification, series->arm parsing, central tendency and **dispersion** behave? | landmark / comparison | mixed -- see section 3 | **accuracy** for discrete targets (type, arm identity, n); **agreement + a three-reading variance decomposition** for dispersion values; real-figure accuracy only if the oracle stratum survives verification |

The headline output is not any single accuracy. It is
**Delta = metric(synthetic) - metric(real)**, computed metric-by-metric and
stratum-by-stratum, plus an honest statement of which Deltas the sample can actually resolve.

---

## 1. The measurement problem, and how this design resolves it

### 1.1 The problem

Greg's clicks carry ~1 px jitter. Measured on synthetic data where R's exact descriptives are
known, that jitter produces **4.15% median / 37.3% worst** error on the dispersion channel
against **0.44% median** on central tendency. The asymmetry is structural, not a skill issue:
a bar top is a long pixel distance from the axis, an SEM cap is a short one, so the same
1 px converts into ~10x the relative error.

Consequence: for dispersion **values** on real figures, a "machine vs human" number measures
the disagreement of two imprecise readers. Reporting it as machine accuracy would attribute
the human's own jitter to the machine. On a synthetic figure R tells you the truth; on a real
journal figure nobody does.

For everything else the human *is* a valid reference. Whether a box is panel B, whether the
caption belongs to figure 3, whether the chart is a grouped bar, whether the error bars are
SEM, whether the blue series is the enriched arm, what n is -- these are discrete facts a
careful reader reads correctly essentially always, and a 1 px click error changes none of
them. **Human-as-reference is valid for identity and invalid for magnitude.** That single
line is the whole design.

### 1.2 The resolution: three independent readings, not two

We do not have one human reading. We have two, from different occasions and different tools,
plus the machine:

| reading | symbol | what it is | when |
|---|---|---|---|
| **historical** | `D` | Greg's dissertation extraction of the same panel (WebPlotDigitizer-era; **no saved calibration or project files survive** -- only the coded numbers, so it cannot be replayed and cannot be contaminated by this study) | years ago |
| **fresh** | `G` | Greg's new blind annotation in figure-extractor, with intra-rater repeats on a subset (`G1`, `G2`) | now |
| **machine** | `M` | the pipeline / detector / agent run | now |

Coverage of the historical reading. The right source is **not** the final meta-analysis
CSV but the per-article extraction workbooks
(`.../DISSERTATION/rodent/RODENT_Processed_Extractions/*.xlsm`, sheet `Main`), which are
strictly richer. Measured by `make_coded_reference.py --stats` over 198 workbooks:

| quantity | workbooks | final MA CSV |
|---|---|---|
| figure-derived comparisons | **434** | 145 |
| articles | **171** | 43 |
| distinct (article, panel) -- the annotation unit | **355** | 98 |
| distinct (article, figure) | **248** | 60 |
| arm-value readings (2 per comparison) | **868** | 220 |
| complete mean + SD + n, both arms | **392** | 144 |
| rows naming a specific panel letter | **345** | 136 |
| multi-arm / shared-control comparisons | 194 / 110 | 37 / -- |

The universe is ~4x larger than the meta-analysis because most articles were dropped from
the MA on **content** grounds (wrong population, wrong outcome). A figure excluded for
reporting the wrong outcome is still a perfectly valid figure to read, so the
extraction-validation universe is properly the extraction corpus, not the MA corpus.

Three fields exist only in the workbooks and each one changes the design:

- **per-arm `*_Variance_Type`**, recorded rather than inferred. Distribution over the 868
  arm-values: **SEM 756+ / SD ~50 / SE, CI, Range, IQR in single digits, 10 missing** --
  i.e. **~94% SEM**. The real corpus is overwhelmingly the *short-cap* case, which is the
  hardest and highest-leverage dispersion regime and precisely where the synthetic
  benchmark located the error. Every dispersion result must be read in that light and is
  stratified by recorded variance type.
- **`Control_Group_ID` / `Experimental_Group_ID`** (e.g. `SC` / `EE+Vehicle`) -- real
  reference *names* for the arms, so series->arm binding, the silent catastrophic class,
  can be scored against something rather than assumed.
- `Direction`, `Multi_Arm_Study`, `Shared_Control_Group`, `Variance_Inflation_Factor`,
  `Between_Or_Within_Design` -- everything the end-to-end metafor stage needs, including
  the shared-control correction, applied identically to all three readings.

This turns an unidentifiable problem into an identifiable one.

### 1.3 What three readings buy: the variance decomposition

Model each reading of the same true quantity `T` on the log scale (errors on dispersion are
proportional, so `log` is the correct scale and `log(SD_M / SD_G)` is the natural difference):

```
log X_i = log T + e_i ,   i in {D, G, M}
```

With three methods and no gold standard, the **Grubbs (1948) three-instrument estimator**
identifies each method's error variance from the three pairwise difference variances alone:

```
sigma_M^2 = [ Var(M-G) + Var(M-D) - Var(G-D) ] / 2      (and cyclically for G, D)
```

equivalently `sigma_M^2 = Cov(M-G, M-D)`. No oracle is required. This is the primary
dispersion analysis.

**The confound, stated up front and signed.** `D` and `G` are the same person. Their errors
may share a component (a habitual way of reading a cap: its centre line vs its upper edge, a
consistent tick-identification bias) with covariance `c >= 0`. Then:

```
E[sigma_M^2 (Grubbs)] = sigma_M^2 + c        <- machine variance INFLATED
E[sigma_G^2 (Grubbs)] = sigma_G^2 - c        <- human variance DEFLATED
```

So shared-person error biases the comparison **against the machine**. Every machine-vs-human
statement produced this way is therefore *conservative*, and that direction must be stated
wherever the number appears. We do not get to claim the machine is better than the estimate
says; we do get to claim it is at least that good.

**Bracketing `c`.** The intra-rater repeat subset gives `sigma_G^2` directly and independently
of Grubbs: `Var(G1 - G2) = 2 * sigma_G_repeat^2`. Then

```
c_hat = sigma_G_repeat^2 - sigma_G^2 (Grubbs)
```

and we report the machine variance as an interval
`sigma_M in [ sqrt(max(0, sigma_M^2(Grubbs) - c_hat)), sqrt(sigma_M^2(Grubbs)) ]`.
`sigma_G_repeat` is a *within-tool* test-retest quantity and therefore itself understates the
across-tool human component, so `c_hat` is a lower bound on `c` and the corrected endpoint is
still an upper bound on `sigma_M`. Both endpoints are reported; neither is presented alone.

**What `D` vs `G` is and is not.** Because both are Greg, `Var(D-G)` bounds **intra-rater,
cross-tool, cross-occasion** reliability. It is **not** inter-rater reliability and will
understate the variability of "a human digitizer" as a population. Any sentence about "a
human" in the write-up must say *this human, twice*. Obtaining a genuine second rater is the
single change that would most strengthen this design and is listed in section 11 as the known
gap.

### 1.4 Why all four candidate approaches are used, and in what order

The four options are not alternatives; they answer different questions and they are layered,
cheapest claim first:

1. **Bland-Altman on `log(M/G)` and `log(M/D)`** -- the *reporting form*. Bias (systematic
   offset) and 95% limits of agreement (random spread). This is the honest description of
   "are these two readings interchangeable in a meta-analysis?", which is the question a
   reviewer actually has. It makes no accuracy claim and needs no assumptions beyond
   approximate normality of log-ratios. **Always reported.**
2. **Intra-rater noise floor from repeats** -- the *yardstick*. Machine error is reported as a
   ratio to the human's own measured repeatability, never against zero. **Always reported.**
3. **Grubbs three-reading decomposition** -- the *primary inferential claim*. The only route
   to a per-method error variance without an oracle. **Primary dispersion analysis.**
4. **Accuracy restricted to a gold standard** -- reported on two strata where a gold standard
   genuinely exists: (a) the **synthetic benchmark** (R's exact descriptives; already done,
   cited not re-run); (b) a **text-anchored real stratum** -- rows whose numeric value is also
   printed in the paper's text/table, so the published number is ground truth for the drawing.
   Measured availability: **52 of 145 figure-derived rows across 17 articles** have
   `Data_Extraction_Method` naming a text or table source. **This is the only real-figure
   accuracy claim in the study and it is confined to that stratum.**

### 1.4b The oracle stratum was tested, and it does not hold up

The layer-4 accuracy claim looked much bigger than it is. **138 of the 434 figure-derived
comparisons, across 54 articles**, carry a `Data_Extraction_Method` that *claims* a text
or table source ("Reported in text/figure" 89, "Reported in text and figure" 30,
"Reported in text and figures" 15, "Reported in figure/table" 1, "Reported in inset table
in Figure 3" 1, "Direct from text and figures" 2). If the paper prints the number and
plots the same quantity, the printed number is genuine ground truth for the figure read --
which would convert the headline from *agreement* to *accuracy*, on real figures, with no
human annotation at all.

**The field is ambiguous and the workbooks' own `Help` sheet does not define it.** It
documents `Data_Extraction_Method` only as e.g. "Reported in text", "Reported in table",
"Visual analysis of figure elements". So "Reported in text/figure" may equally mean *the
coder digitized the figure and the text corroborated it*. That difference is the whole
claim, so it was checked rather than assumed.

**The check (`verify_oracle.py`), pre-specified and mechanical.** Open the article PDF,
take the body text with the reference list stripped (a reference list is a dense field of
years, volumes and page numbers that will match almost any 2-4 digit value by chance), and
require the coded **mean and its variance to appear as printed numbers within 120
characters of each other** -- the signature of a printed `35.2 +/- 4.8`. Either number
alone is not evidence: in the first article tried, `20.13` matched a DOI and `2.7` matched
a section heading.

**Measured result, over the 34 claimed comparisons whose PDF currently resolves:**

| verdict | n | share of checkable |
|---|---|---|
| TEXT_CONFIRMED | **1** | 2.9% |
| PARTIAL | 3 | 8.8% |
| NOT_FOUND | **30** | **88.2%** |
| NO_PDF (not yet checkable) | 104 | -- |

**The oracle hypothesis is falsified at the rate observed.** "Reported in text/figure"
means *corroborated*, not *quoted*. Concretely: Aykan2024 Figure 5B is coded
20.13 +/- 2.01 (SEM, n=8) and labelled "Reported in text and figure", yet none of 20.13,
21.7, 0.53 or 0.43 appears in the paper's body text.

**Consequences, binding:**

1. The study stays **agreement-first**. The Grubbs three-reading decomposition is the
   primary dispersion analysis; the oracle stratum is a small **conditional sensitivity**
   stratum, not the headline.
2. `isOracle` is **false by construction** in the coded reference and is set *only* by
   `verify_oracle.py` on a TEXT_CONFIRMED verdict. The scorer will not admit a row to the
   accuracy analysis on the strength of the label. A selftest is unnecessary here because
   the default is refusal.
3. `verify_oracle.py` is **re-run** once the sampling protocol resolves PDFs for the full
   171-article set; 104 of 138 candidates are currently unchecked, so the confirmed count
   can only grow. If it grows past **30 confirmed comparisons across >= 10 articles**, the
   oracle stratum is promoted to a reported accuracy analysis with an explicit selection
   caveat (papers that print their numbers are plausibly better-reported papers). Below
   that it is reported as a descriptive footnote with its rule-of-three bound.
4. This negative result is itself reportable: a provenance field that a reader would
   naturally take as "the number came from the text" does not mean that, and the
   discrepancy is only visible because the check was mechanised.

**What is explicitly NOT claimable and will not be reported:** any statement of the form "the
machine's dispersion error on real figures is X%" derived from machine-vs-human disagreement
on non-oracle rows. The scorer computes that quantity, labels it
`dispersion_naive_disagreement`, and prints it under a banner saying it is a two-reader
disagreement and not an accuracy. `--selftest` asserts that a machine which is *exactly right*
still produces a large naive disagreement when the human jitters, and that Grubbs recovers
`sigma_M ~ 0` in the same data (section 9, test D3). That test exists to make the distinction
impossible to lose.

### 1.5 Two floors that are not anyone's error

- **Coded-value rounding, and why it turns out not to matter for the headline.** The
  historical reading `D` is printed to finite precision. Measured over the workbooks'
  816 usable arm-values the rounding quantum is **median 4.17% of the value, p90 16.7%,
  and exceeds 1% on 547 of 816 (67%)** -- far worse than the final CSV suggested (median
  0.118%), because the workbooks store the raw SEM (a small number at 1-2 dp) rather than
  the derived SD. At first sight that is fatal.

  It is not, **for `sigma_M`**. Quantization `Q` is independent noise entering `D` only,
  so it appears with opposite signs in the Grubbs contrast and cancels exactly:

  ```
  sigma_M^2 = [ Var(M-G) + Var(M-D) - Var(G-D) ] / 2
            = [ Var(M-G) + (sM^2 + sD^2 + Q) - (sG^2 + sD^2 + Q) ] / 2
            = sigma_M^2
  ```

  Coded print-precision inflates `sigma_D` and nothing else. **Pre-specified consequence:**
  the primary machine-variance estimate uses **all** complete `D/G/M` triplets -- no rows
  are dropped on rounding grounds, which recovers the full n and with it the power in
  section 4.4. The `<= 1%` restriction is applied **only** where `Q` does *not* cancel: the
  pairwise `M` vs `D` Bland-Altman, and the oracle accuracy stratum. `sigma_D` is reported
  twice, with the quantization variance (`h^2/3` for a uniform half-width `h`) included and
  subtracted, so it is not misread as the historical reader's skill.
  **Selftest D6 enforces the cancellation rather than asserting it.**
- **Rendering / drawing floor.** Both readers read the *same drawing*; neither can recover the
  true SD better than the plotted cap encodes it. All dispersion errors are therefore reported
  in **two units: percent, and pixels of cap length at the annotation dpi**. Cap length in
  pixels is a pre-specified stratifier (tertiles), because the synthetic work already showed
  short caps dominate the error and percent alone hides that.

---

## 2. Design overview

### 2.1 Units and nesting

```
article (43)  ->  figure  ->  panel  ->  landmark (arm-value)  ->  comparison (row)
                  ~200         ~200        220                     145
```

Metrics live at different levels; inference must respect the nesting. **All confidence
intervals are computed by article-level cluster bootstrap (B = 10000 resamples of articles
with replacement).** Design-effect arithmetic appears only in the sample-size section, for
planning; it is never used for inference.

### 2.2 The three tiers, and why they have different sample sizes

Detection GT is cheap (one box, one caption confirmation). Panel GT is moderate. Extraction GT
is expensive and is additionally *capped* by the existence of a historical coded reading. So:

| tier | annotate on | target N | cap |
|---|---|---|---|
| D | **every** figure on every page sampled from the PDFs, coded or not | >= 150 figures, >= 30 articles | none (labour only) |
| P | a stratified sample of **compound** figures from the same PDFs | >= 180 panels / >= 55 figures | none (labour only) |
| E | only panels with a historical coded reading: **355 available** (868 arm-values, 434 comparisons) | **>= 120 panels** (~290 arm-values); stretch 200 | hard: 355 |

Tier E is the only tier bounded by the dissertation, and the workbooks raise that bound from
98 panels to **355**, so it is now bounded by Greg's time rather than by data. Tier E is
therefore *sized to the precision it needs* (section 4.4) rather than to what exists: 120
panels already delivers the discrimination every gate requires, and going beyond ~200 buys
diminishing returns on every metric except the zero-event bounds.

### 2.3 DEV / LOCK split -- assigned NOW, by rule, before any figure is seen

Split at the **article** level (never the panel level: two panels of one figure share layout,
typeface, gutter and journal, so panel-level splitting leaks).

```
h      = sha256("figure-extractor-real-validation-v1|" + Article_ID).hexdigest()
bucket = int(h[:8], 16) % 3
split  = "dev" if bucket == 0 else "lock"          # ~1/3 dev, ~2/3 lock
```

The salt string `figure-extractor-real-validation-v1` is fixed by this document. Anyone can
recompute the assignment; it cannot be redrawn to suit a result. `score_real_validation.py
--split` prints the assignment and writes `split.json`.

**Permanently DEV, never LOCK, regardless of hash** -- these are already contaminated (they
produced the asterisk-occlusion finding and the pilot numbers):

```
Gobeske2009           (fig1a)
GarciaCapdevila2009   (fig1a, fig1b)
Bonaccorsi2013        (fig1b 1-day, 10-day, 20-day)
Kazlauckas2011        (fig3A -- excluded pilot panel; the exclusion reasoning is known)
```

Applied to the 171 articles of the coded reference this yields **71 DEV / 100 LOCK**
(`split.json`, regenerate with `--split`). The DEV share exceeds one third by chance; the
assignment stands as drawn, because re-drawing it after seeing the counts is exactly the
degree of freedom the rule exists to remove.

**Rules of use, binding:**

1. Every tuning decision -- thresholds, gutter minima, glyph matchers, prompt wording, abstain
   cut-offs, bug fixes that change behaviour -- is made on DEV only.
2. LOCK is scored **once per frozen detector version**. The version hash is recorded with the
   result.
3. If LOCK is scored and the detector is then changed, the next LOCK score is **post hoc** and
   must be labelled so, unless a fresh LOCK draw is made from unannotated articles.
4. The headline numbers of the study are the **LOCK** numbers. DEV numbers are reported
   alongside, always labelled DEV, and the DEV-LOCK difference is itself reported as an
   overfitting diagnostic.

---

## 3. Metrics and pre-specified thresholds

Notation: `Delta = metric(synthetic) - metric(real LOCK)`. Synthetic comparators are frozen in
`synthetic_reference.json`, sourced from `benchmark/panels/RESULTS.md`,
`benchmark/series/RESULTS.md`, `benchmark/classify/RESULTS.md`, `benchmark/RESULTS.md` and
`benchmark/real/RESULTS.md`. A threshold marked **GATE** is a decision rule input (section 8).

### 3.1 Tier D -- figure detection and caption association

| metric | definition | pre-specified threshold | synthetic comparator |
|---|---|---|---|
| figure-bbox IoU, median | IoU of Docling's Picture box vs the human's drawn figure box, page pixel coords | **>= 0.90** | none (N=1 prior) |
| figure-bbox IoU >= 0.75 | share of GT figures | **>= 90%** | none |
| figure recall | GT figures matched at IoU >= 0.5 | **>= 95%** | none |
| figure precision | predicted regions matching some GT figure at IoU >= 0.5 | **>= 90%** | none |
| spurious figures / page | unmatched predicted regions per annotated page | **<= 0.15** | none |
| **caption-association accuracy** | the caption text bound to a figure is the one GT says belongs to it (normalised text, >= 0.9 char overlap) | **>= 95%** **GATE** | none |
| caption -> letter-set accuracy | `expectedPanelsFromCaption` returns exactly the GT letter set | **>= 95%** **GATE** | none |

There is **no synthetic detection benchmark**, so no `Delta` exists for Tier D. It is reported
in absolute terms only, and the report says so rather than inventing a comparator. The
caption metrics are gates because the entire panel cascade is conditioned on the caption: the
synthetic work measured that removing the caption prior collapses exact-count from 75.8% to
9.1%. A caption-association failure is not a detection inconvenience, it is an upstream
catastrophe.

### 3.2 Tier P -- panel decomposition

Metric definitions are **imported unchanged** from `benchmark/panels/score.py` (same IoU
matching, same `IOU_HIT = 0.5`, `IOU_TIGHT = 0.9`, same reading-order fallback for unlabelled
boxes, same abstention accounting). Identical estimators on both sides is what makes `Delta`
meaningful; a redefinition would make the comparison meaningless.

| metric | synthetic (41 figs / 159 panels) | real threshold | max allowed Delta |
|---|---|---|---|
| per-panel IoU, median | 1.000 | **>= 0.90** | 0.10 |
| panels IoU >= 0.9 | 88.1% | **>= 65%** | 23 pp |
| panels IoU >= 0.5 | (>= 88.1%) | **>= 90%** | -- |
| exact panel count | 95.1% | **>= 85%** | 10 pp |
| label accuracy on localised panels | 100.0% | **>= 98%** | 2 pp |
| **silent mislabel rate** (IoU >= 0.5, wrong letter) | 0.0% | **0 observed; 95% UB <= 2.5%** **GATE** | 2.5 pp |
| answered-only exactly right | 100.0% | **>= 85%** | 15 pp |
| error rate on answered figures | 0.0% | **<= 10%** | 10 pp |
| coverage (1 - abstention) | 65.9% | **>= 50%** | 16 pp |
| abstention precision | 0.88 | **>= 0.60** | -- |
| abstention recall | 0.94 | **>= 0.50** | -- |
| **net figures saved** by abstaining | +13 | **> 0** **GATE** | -- |

Silent mislabel is the catastrophic class: right box, wrong letter, every downstream number
attributed to the wrong sub-experiment, and -- as the series tier proved -- invisible to every
geometric metric. It gets a zero-tolerance threshold and it drives the panel sample size
(section 4). `net figures saved > 0` is a gate because an abstention channel that throws away
more correct answers than it catches errors is worse than no abstention channel; the synthetic
round-2 cascade scored a perfect 0% error while netting **-1** figures, i.e. correct and
useless.

### 3.3 Tier E -- element extraction

**Classification** (vocabulary imported live from `CHAR_VOCAB.charType`, 22 classes):

| metric | synthetic | real threshold | max Delta |
|---|---|---|---|
| chart-type accuracy | 1.000 (n=80) | **>= 90%** | 10 pp |
| macro F1 | 1.000 | **>= 0.85** | -- |
| **priority-flip rate** (`extractionPriority` changes) | 0.000 | **<= 5%** **GATE** | 5 pp |
| dispersion-type agreement (SD / SEM / CI95 / IQR / none) | -- | **>= 90%** | -- |
| `dispersion-type-uncertain` flag recall on disagreements | -- | **>= 80%** **GATE** | -- |
| ECE | 0.072 | **<= 0.15** | -- |

Dispersion-type is a *text* fact, not a pixel fact, and the human is a full oracle for it. It
gets its own metric because getting SEM vs SD wrong multiplies every SD by `sqrt(n)` -- a
~3.2x error at the corpus median n of 10 -- which dwarfs every pixel effect in this study. The
flag-recall gate enforces the project's own principle: an uncertain type must be *flagged*,
not guessed.

**Series -> arm parsing** (definitions imported from `benchmark/series/score.py`; arm key
`"{groupId}|{seriesId}"`):

| metric | synthetic base / stress | real threshold | max Delta |
|---|---|---|---|
| bound series mis-assignment (per mark) | 0.000 / 0.048 | **<= 2%; 95% UB <= 5%** | 2 pp |
| bound **arm** mis-assignment (group x series) | 0.000 / 0.048 | **<= 2%** | 2 pp |
| structural mis-assignment (best-permutation) | 0.000 / 0.048 | **<= 5%** | -- |
| mean ARI | 1.000 / 0.930 | **>= 0.90** | -- |
| **legend / arm-name accuracy** | 1.000 (57/57) | **>= 99%; 0 errors preferred** **GATE** | 1 pp |
| **effect sign flips from mis-assignment** | 0/145, 0/67 | **0; 95% UB <= 5%** **GATE** | -- |

The naming metric is gated an order of magnitude tighter than the structural one because the
series tier measured the asymmetry directly: two swapped legend labels with *perfect*
clustering produced **0.000 structural error, ARI 1.000, and 30.3% effect sign flips**, while
15% structural noise produced visible degradation and only 2.9% sign flips. Naming errors are
~10x more damaging and are invisible to structural metrics. The threshold reflects the damage,
not the difficulty.

**Central tendency** (bar top / point / box median -> data units):

| metric | synthetic human_floor @1 px | real pilot (n=16) | real threshold |
|---|---|---|---|
| median abs % error vs `G` | 0.44% | 0.47% | **<= 1.0%** |
| p95 abs % error | -- | -- | **<= 5%** |
| worst | -- | 2.77% | **<= 10%** |

Central tendency is a long pixel distance and both readers resolve it well, so machine-vs-human
here is close to an accuracy statement and is reported as such with the caveat attached. It is
also the **control channel**: if central tendency degrades on real figures, the problem is
calibration or panel cropping, not the dispersion channel, and the diagnosis changes.

**Dispersion -- the headline.** Reported as four distinct quantities, never collapsed:

| quantity | how | threshold |
|---|---|---|
| (a) `dispersion_naive_disagreement` -- median abs % `M` vs `G` | direct | **reported, never interpreted as accuracy**; context only |
| (b) Bland-Altman on `log(SD_M / SD_G)`: bias and 95% LoA | mean and mean +/- 1.96 sd of log-ratios, back-transformed | **abs(bias) <= 5%; LoA within [-25%, +25%]** **GATE** |
| (c) Grubbs `sigma_M / sigma_G` (and `sigma_M / sigma_D`) | section 1.3, reported as the `c`-corrected interval | **<= 1.5** **GATE**; target <= 1.0 |
| (d) accuracy on the text-anchored oracle stratum (n ~ 52 rows / 17 articles) | vs the published number | **median <= 5%, p90 <= 15%** |

plus, stratified by **cap length in pixels (tertiles)**:

| stratum | threshold |
|---|---|
| shortest-cap tertile, median abs % error vs `G` | **<= 10%** **GATE** |
| middle and longest tertiles | **<= 5%** |

and the **noise-floor ratio**, the number the project's thesis actually turns on:

```
R_floor = median|M - G| / RC_intra ,   RC_intra = 1.96 * sqrt(2) * sigma_G_repeat
```

`R_floor <= 1` means the machine's disagreement with the human sits inside the range two of the
human's own readings differ by -- i.e. **the machine is indistinguishable from the human's own
repeatability, and no accuracy claim in either direction is supportable from real figures.**
That is a publishable finding and it is also the ML-detector no-go condition (section 8).

**End-to-end (the test that matters).** See section 6.

### 3.4 The transfer gap `Delta`

For every metric with both a synthetic and a real value, the report emits:

```
metric   synthetic   real(LOCK)   Delta   95% CI on Delta (cluster bootstrap, real side)   verdict
```

Pre-specified verdict ladder, applied per metric:

| `Delta` | verdict |
|---|---|
| <= 5 pp (or <= 0.05 for IoU-like) | **transfers** |
| 5-15 pp | **degrades but usable** -- report the stratum that carries it |
| > 15 pp | **does not transfer** for that metric |

`Delta` for a metric whose synthetic value is exactly 1.000 or 0.000 is reported with the
one-sided rule-of-three bound on the synthetic side, not as a point estimate, because a zero
count is not a zero rate.

---

## 4. Sample size: what N buys what precision

All figures below are computed in `score_real_validation.py --power` (Wilson intervals,
two-proportion power at alpha = 0.05 / 80%, order-statistic median CIs, F-based variance-ratio
CIs). Clustering is handled by cluster bootstrap at analysis time; the design effects here are
planning aids only.

### 4.1 Proportions -- Wilson 95% CI half-width (pp)

| n | p=0.80 | p=0.90 | p=0.95 | p=0.98 | p=1.00 |
|---|---|---|---|---|---|
| 50 | 10.9 | 8.5 | 6.2 | 5.1 | 3.6 |
| 98 | 7.9 | 6.1 | 4.6 | 3.3 | 1.9 |
| 150 | 6.4 | 4.8 | 3.7 | 2.5 | 1.2 |
| 200 | 5.5 | 4.2 | 3.1 | 2.1 | 0.9 |

### 4.2 Zero-event outcomes -- the rule of three

The catastrophic classes (silent mislabel, arm-name error, sign flip) are expected to be zero.
A zero count is only as strong as its denominator:

| n with 0 events | 95% upper bound |
|---|---|
| 60 | 5.0% |
| 98 | 3.1% |
| 120 | 2.5% |
| 150 | 2.0% |
| 220 | 1.4% |

**This is what sets the panel target, and it now also sets the Tier-E target.** To claim
"silent mislabels <= 2.5%" the LOCK panel count must be **>= 120**. The same arithmetic
applies to the arm-name and sign-flip gates: 0 events in the ~290 arm-values from 120
Tier-E panels bounds arm-name error at **1.0%**, and 0 flips in the ~145 LOCK comparisons
bounds the flip rate at **2.1%**. At the observed ~3.3 panels per compound figure that is ~37 LOCK
compound figures, hence a total Tier-P target of **>= 180 panels / >= 55 figures** (2/3 in
LOCK). Below 120 LOCK panels the silent-mislabel claim weakens to <= 5% and the panel gate in
section 8 must be read at that weaker level -- stated now so the trade is made knowingly.

### 4.3 Detectable transfer gaps (80% power, alpha = 0.05)

| metric | synthetic n | real n | smallest detectable drop |
|---|---|---|---|
| panel exact count (fig-level, p_syn=0.951) | 41 figs | 55 figs | **20.9 pp** |
| panel exact count | 41 figs | 100 figs | 18.6 pp |
| panels IoU >= 0.9 (p_syn=0.881) | 159 | 150 | **12.2 pp** |
| panel label accuracy (p_syn=1.000) | 159 | 150 | **4.9 pp** |
| chart-type accuracy (p_syn=1.000) | 80 | 98 | **8.8 pp** |
| series mark accuracy (p_syn=1.000) | 495 | 220 | **2.1 pp** |

Read this honestly: **the figure-level exact-count `Delta` is the weakest number in the study.**
With ~55 real compound figures we can only detect a drop of ~21 pp, so a real exact-count of
80% would *not* be distinguishable from the synthetic 95.1%. The pre-registered response is
not to pretend otherwise: the exact-count `Delta` is reported with its CI and explicitly
labelled underpowered, and the decision rule in section 8 leans on the panel-level metrics
(label accuracy, silent mislabel, IoU) which are adequately powered at n=150-200 panels.

### 4.4 Continuous outcomes

Median abs % error, distribution-free 95% CI as a share of the sample spread:

| n | CI spans |
|---|---|
| 50 | ~30% of the ordered sample |
| 98 | ~21% |
| 150 | ~18% |
| 220 | ~14% |

Grubbs variance ratio `sigma_M / sigma_G`, 95% CI multiplier on the SD scale:

| n arm-values | SD-ratio CI |
|---|---|
| 50 | [0.75, 1.33] |
| 98 | [0.82, 1.22] |
| 150 | [0.85, 1.17] |
| 220 | [0.88, 1.14] |

Because coded rounding cancels out of `sigma_M` (section 1.5), **no arm-values are lost to
the quantum filter** and the usable n is the full complement. At the **120-panel** Tier-E
target (~290 arm-values) with a plausible within-panel ICC of 0.4-0.6 (design effect
~1.5-1.7, effective n ~ 170-195), the SD-ratio CI is roughly **[0.86, 1.16]**. At the
355-panel ceiling (868 arm-values, effective ~510) it tightens to ~[0.92, 1.09]. Both are
sufficient to discriminate the section-8 gate value of 1.5 from parity, which is the
discrimination the study needs; only the ceiling would resolve a 1.2 vs 1.0 difference, and
that is the one thing worth spending extra annotation hours on if the ratio lands near 1. **Pre-specified:** no claim of the form "the machine is *more* precise
than the human on real figures" will be made unless the upper end of the corrected
`sigma_M / sigma_G` interval is below 1.0. Given the conservative bias of section 1.3, that
bar is deliberately hard.

### 4.5 End-to-end

| quantity | n needed | available |
|---|---|---|
| sign flips 0 with UB <= 5% | 60 comparisons | **434 exist; ~145 at the 120-panel target** |
| sign flips 0 with UB <= 2.5% | 120 comparisons | yes |
| 3-level `rma.mv(~1 \| article/row)` non-singular | >= 2 articles with >= 2 rows | 171 articles |
| multi-arm shared-control correction exercised | >= 20 affected rows | 194 multi-arm / 110 shared-control |

### 4.6 Labour budget, stated so the effort is spent knowingly

| tier | unit cost (est.) | N | hours |
|---|---|---|---|
| D | ~30 s / figure | 150-200 | 1.5-2 |
| P | ~3 min / figure | 55-60 | 3 |
| E | ~10 min / panel | 120 (of 355 available) | 20 |
| E repeats (20%) | ~10 min / panel | 24 | 4 |
| **total** | | | **~28-29 h** |

Staged, with a hard stop at each stage: **Stage 1** = a DEV slice (~40 panels, ~8 h) --
interface shakedown and tuning only. **Stage 2** = LOCK to >= 120 panels (~20 h) -- scored
once. **Stage 3 (optional)** = extend LOCK toward the 355-panel ceiling, and only if the
Grubbs ratio lands near 1.0 where the extra precision changes a conclusion. If Stage 2 cannot be completed, the study reports the reduced-N thresholds of section
4.2 / 4.4 rather than the full ones, and says which claims were lost.

---

## 5. Stratification

The synthetic work established that **the stratification is the deliverable** -- a global mean
hides exactly where a detector breaks. Every metric in section 3 is reported per stratum, and
no global number is reported without its strata beside it.

**Strata shared with the synthetic corpus (so `Delta` is computable per stratum).** Bucket
definitions are imported unchanged from `benchmark/panels/finalize_gt.py`; re-deriving them
would break the comparison.

| stratum | levels | source |
|---|---|---|
| gutter (measured) | `flush` (<= 2 px) / `tight` / `medium` / `wide` | `finalize_gt.bucket()` |
| layout class | `guillotine` / `non-guillotine` | annotator |
| label placement | `none` / `inside-tl` / `inside-tr` / `outside-al` / `top-centre` / `bottom-right` / `mixed` | annotator |
| panel content type | `line` / `bar` / `scatter` / `box` / `micrograph` / `heat` (+ real additions) | annotator, `CHAR_VOCAB.charType` |
| chart type | 22 `CHAR_VOCAB.charType` classes | annotator |
| dispersion type | `SD` / `SEM` / `CI95` / `IQR` / `range` / `none` / `unknown` | annotator, from text |
| cue type (series) | `color` / `shape` / `linetype` / `position` / combinations | annotator |
| occlusion | `none` / `moderate` / `severe` | annotator |
| legend style | `right` / `top` / `inside` / `direct-labels` / `none` | annotator |

**Real-only strata (reported; no `Delta` -- the synthetic corpus has no counterpart).** These
are where the *realism* gap should show up, and inventing a synthetic comparator for them
would be dishonest:

| stratum | levels | why |
|---|---|---|
| **recorded dispersion type** | SEM / SD / SE / CI-95 / Range / IQR / missing | **~94% of the corpus is SEM**, i.e. the short-cap case; recorded per arm in the workbooks, never inferred |
| **cap length in px (tertiles)** | short / mid / long | the dominant driver of dispersion error, established synthetically |
| **significance markers over the cap** | present / absent | the pilot's concrete realism finding: a naive read latches onto the asterisk and misses by 30-45 px, inflating dispersion error to 22-36% |
| control-group n | <= 8 / 9-12 / > 12 (corpus median 10) | a b% cap error becomes ~2b% variance error and ~sqrt(n) mis-weighting; short n bites hardest |
| figure origin | vector text / flattened bitmap / mixed XObjects | 43/43 corpus PDFs are born-digital but panel labels are baked into pixels; multi-XObject figures give exact free boundaries |
| render dpi | 300 / 600 | annotation-condition sensitivity |
| colour vs greyscale | 2 levels | |
| journal / publisher | as observed | style clustering, and the cluster-bootstrap sanity check |
| coded rounding quantum | <= 1% / > 1% | section 1.5; the > 1% rows leave the primary dispersion analysis |
| provenance | text-anchored oracle / figure-digitized only | section 1.4; determines which claim is available |
| DEV / LOCK | 2 levels | overfitting diagnostic |

**Minimum stratum size for a reported number: n >= 10.** Strata below that are shown with
their raw counts and no percentage, because a 2/3 in a stratum is not 67%.

---

## 6. The end-to-end test that matters

The question: **if the automated read replaces the human's figure digitization, does the
meta-analytic conclusion change?** The pilot answered it on 8 comparisons (+0.475 extracted vs
+0.487 coded, 0/8 sign flips). This scales it to 145.

### 6.1 Model, pre-specified

Exactly the dissertation's own analysis, run twice on the same rows with the same code, so the
*only* difference between the two fits is the figure reading.

```r
# effect size: bias-corrected SMD, intervention - control
esc <- escalc(measure = "SMD",
              m1i = i_mean, sd1i = i_sd, n1i = i_n,
              m2i = c_mean, sd2i = c_sd, n2i = c_n)

# multi-arm shared-control correction: the dissertation's own VIF_multiarm is applied
# identically to both fits (25 of 145 rows carry VIF != 1)
vi_adj <- esc$vi * VIF_multiarm

# PRIMARY: three-level random effects, rows nested in articles
rma.mv(yi, vi_adj, random = ~ 1 | Article_ID/Comparison_ID, method = "REML")
# FALLBACK (only if singular): rma(yi, vi_adj, method = "REML"), reported as a fallback
```

Direction is applied as the dissertation applies it (`Direction == "lower better"` flips the
sign of `yi`) **before** fitting, in both arms identically. `Direction` is a coded field and is
never inferred from the figure -- it fixes outcome polarity, not arm order, and cannot rescue a
swapped arm assignment.

### 6.2 Comparison, pre-specified

| quantity | threshold |
|---|---|
| `delta` pooled g | **abs(delta) <= 0.05 AND <= 10% of abs(g_coded)** **GATE** |
| CI overlap (intersection / union of the two 95% CIs) | **>= 0.90** |
| tau^2 ratio (extracted / coded), both levels | **within [0.80, 1.25]** |
| I^2 absolute difference | **<= 10 pp** |
| per-comparison median abs(g_ext - g_coded) | **<= 0.05** |
| per-comparison max abs(g_ext - g_coded) | **<= 0.30** |
| **sign flips** | **0 / 145; 95% UB <= 2.5%** **GATE** |
| Spearman rho of study weights (coded vs extracted) | **>= 0.95** |
| most-influential study (max Cook's distance) unchanged | **yes** |
| TOST equivalence on `delta` pooled g, margin +/- 0.10 | **p < 0.05 both one-sided tests** |

The equivalence margin of 0.10 SMD units is half the conventional "small effect" boundary of
0.20, chosen because the claim being tested is *interchangeability*, not *non-inferiority*. The
weight-rank and influence checks are included because a dispersion-channel error does not move
the pooled point estimate so much as it re-weights the evidence, and a re-weighting that leaves
`g` intact while moving `tau^2` and the influential study is still a substantive change.

The bootstrap for `delta` is a **cluster bootstrap over articles**, resampling articles and
refitting both models on each resample, because coded and extracted are paired on the same
rows and a naive interval would be far too wide.

### 6.3 The three-arm version

Where the historical `D`, fresh `G` and machine `M` readings all exist, the golden diff is run
**three times** (`D`, `G`, `M`) and the pairwise `delta`s reported as a triangle. This is the
end-to-end analogue of section 1.3: if `delta(M, G)` is no larger than `delta(D, G)` -- machine
vs human no worse than human vs the same human on another occasion -- the automated read is
meta-analytically interchangeable with the human's, which is the claim the project exists to
make and the strongest one the design supports.

---

## 7. Bias and validity threats, and the controls

| threat | mechanism | control |
|---|---|---|
| **Anchoring on the machine** | seeing a prediction pulls the click toward it | The annotation harness must run **machine-blind**: no detector output, no suggested boxes, no auto-panels, no pre-filled landmark values visible during annotation. The scorer refuses to score any GT record carrying `sawPrediction: true`. |
| **Anchoring on the coded value** | Greg knows this dataset; recalling "16.55" makes the click confirm the memory | Coded values are **never displayed** during annotation. Annotation order is **randomized** (seeded, recorded). The harness records `durationSec` per panel; the scorer flags panels read in under 60 s as `fast-read` and reports the dispersion metrics with and without them. |
| **Recognition is unavoidable** | he will recognise his own dissertation figures; full blinding is impossible | Do not pretend otherwise. Report the **provenance stratum** (`text-anchored oracle` vs `figure-digitized`) and the DEV/LOCK split separately, and state the residual risk in the limitations. The Grubbs decomposition is partially protected: recall-driven convergence of `G` toward `D` increases `c`, which *inflates* the estimated `sigma_M` -- again conservative against the machine. |
| **Fatigue** | later panels in a session are read less carefully | Record `session` and `positionInSession`. Pre-specified test: Spearman rho of `abs(log(G/D))` against `positionInSession`. If abs(rho) > 0.2 at p < 0.05, report the metrics additionally with a session-position covariate and cap sessions at the observed breakpoint. Recommended cap: 20 panels / session. |
| **Learning / drift** | early panels read differently from late ones | Repeats are drawn **uniformly across the whole annotation timeline**, not front-loaded. Pre-specified test: Spearman rho of `abs(log(G/D))` against global annotation index. |
| **Intra-rater repeat contamination** | he remembers the panel he annotated last week | Repeats scheduled **>= 14 days** after the first read, presented under a **different anonymized id**, in randomized order among fresh panels. The harness must not reveal that a panel is a repeat. |
| **Selection bias** | annotating the easy/legible panels | The worklist must be a **pre-specified stratified probability sample** with recorded inclusion probabilities, not convenience order. Every exclusion is logged **before** annotation with a code from the fixed list below, and the exclusion rate is reported per stratum. Post-annotation exclusions are forbidden except for `HARNESS_FAILURE`. |
| **Reference is human** | section 1 | The whole of section 1. Discrete targets: human as reference. Magnitudes: three-reading decomposition + BA + noise floor. Accuracy only where an oracle exists. |
| **Overfitting to a small real set** | tuning against 98 panels | DEV/LOCK split by article, fixed by hash, salt published (section 2.3). LOCK scored once per frozen version. Pilot panels permanently DEV. DEV-LOCK gap reported as a diagnostic. |
| **Metric blindness** | a corpus with no instance of a failure mode reports its absence as success -- this happened: round-3 exploits scored 100% before they were found | The scorer's `--selftest` injects each failure mode and asserts the owning metric moves (section 9). Additionally, the real GT must be checked for the presence of each stratum before the corresponding metric is reported; strata with n < 10 are reported as counts only. |
| **Shared systematic error** | machine and human both misread the same ambiguous cap the same way | Detected by the text-anchored oracle stratum, where an absolute reference exists. If the oracle stratum shows a bias that the BA analysis does not, the disagreement analyses are understating error, and that is reported. |
| **Coded-value rounding** | quantization masquerading as reader error | Quantum computed per row; primary analysis restricted to <= 1% (section 1.5). |

**Fixed exclusion reason codes** (logged before annotation; anything else requires an
amendment):

```
NO_PDF            article's PDF unavailable
PANEL_NOT_FOUND   Data_Source names a panel that does not exist in the figure
NOT_A_CHART       the named panel is a micrograph / schematic with no readable values
NO_ERROR_BARS     no dispersion is drawn, so the dispersion channel is undefined
N_MISMATCH        coded Ns correspond to no bar group in the figure (provenance ambiguity)
IMPUTED_SD        Variance_Source == "Imputed" -- not a reading of the figure
UNREADABLE        resolution/print quality makes the landmark genuinely unresolvable
HARNESS_FAILURE   tooling failure (the only permitted post-annotation exclusion)
```

---

## 8. Decision rules, pre-committed

Evaluated on **LOCK**, on a frozen detector version, in this order. The first matching rule
wins.

### 8.1 DOES NOT TRANSFER

Any one of:

- caption-association accuracy **< 85%**, or caption -> letter-set accuracy < 85%
- panel silent-mislabel rate **> 5%**
- panel exact-count **< 60%**
- arm-name binding error **> 2%**, or effect sign flips from mis-assignment **> 5%**
- abs(delta pooled g) **> 0.20**, or sign flips in the golden diff **> 5%**

**Action:** report the negative result. The synthetic benchmark measured a pipeline that does
not survive contact with real journal figures; publish the transfer gap and its localisation,
and state which architectural assumption failed (caption availability, guillotine layouts,
pixel-level label verification). Do not ship, and do not build the detector -- a detector
trained on synthetic panels inherits the same failed assumption.

### 8.2 BUILD THE ML DETECTOR (go)

Not triggered by 8.1, **and** the dispersion channel specifically fails:

```
GO  iff   ( Grubbs sigma_M / sigma_G  >  1.5                                  )
     OR   ( Bland-Altman 95% LoA on log(SD_M/SD_G) falls outside [-25%, +25%] )
     OR   ( median abs % dispersion error in the SHORTEST-CAP TERTILE > 10%   )
     OR   ( >= 5% of comparisons move abs(g_ext - g_coded) > 0.20             )
AND       ( R_floor = median|M-G| / RC_intra  >  1.0 )
AND       ( the residual localises to landmark reading -- caps, asterisk occlusion --
            and NOT to detection or panel decomposition, which have their own fixes )
```

The dispersion channel is the trigger because that is where all the leverage is: central
tendency is ~0.5% on synthetic *and* real, so no detector can improve it meaningfully, while
dispersion is 4-9% synthetic and 3.67% median / 18.1% worst on the real pilot, concentrated on
short caps and asterisk-occluded caps -- exactly what a sub-pixel specialist trained to ignore
significance glyphs would remove.

**The `R_floor > 1.0` conjunct is a hard no-go, and it is the honest part of this rule.** If
the machine's disagreement with the human is no larger than the human's disagreement with
himself, then **the residual error is not measurable against any available reference, and a
detector cannot be justified on accuracy.** Training to beat a target you cannot resolve is
not engineering. In that case the detector may still be built, but only on an explicit
**cost/throughput** argument (the series tier already established one: ~51 tool calls / ~122k
tokens for the agent's clean score on the hardest chart), and the write-up must say so in those
words rather than implying an accuracy benefit.

### 8.3 SHIP IT (agent + human gate)

All of:

- every Tier-D threshold met, caption gates >= 95%
- every Tier-P threshold met; **0 silent mislabels observed with 95% UB <= 2.5%**; net figures
  saved > 0
- classification >= 90%, priority-flip <= 5%, dispersion-type flag recall >= 80%
- arm-name accuracy >= 99% with 0 sign flips
- central tendency median <= 1.0%
- dispersion: BA bias within +/-5%, LoA within +/- 25%, Grubbs `sigma_M / sigma_G <= 1.5`
  (computed on all complete `D/G/M` triplets -- coded rounding cancels, section 1.5)
- golden diff: abs(delta g) <= 0.05 and <= 10% of abs(g), tau^2 ratio in [0.8, 1.25], 0 sign
  flips, weight rho >= 0.95, TOST passes at margin 0.10

**Action:** publish "automated figure extraction with a human dispersion-type gate reproduces
the hand-coded meta-analytic conclusion on N articles", with the transfer-gap table as the
central result and the abstention channel as the safety mechanism. Ship the tool as-is.

### 8.4 NARROW THE CLAIM (the likely outcome, and it is a real outcome)

Not 8.1, not the full 8.3, and the failures are **confined to identifiable strata**.

**Action:** ship for the strata that pass, and make the abstention channel enforce the boundary
-- the tool must abstain on the failing strata rather than answer. Publish the passing scope
explicitly ("bar and line panels with labelled letters and non-flush gutters, n = X") plus the
stratum-level failure map. This is the outcome the synthetic work already predicts: flush
mosaics and non-guillotine layouts are open, and no threshold change fixes them.

Escalation from 8.4 to 8.2 requires the 8.2 conditions to be met **within the failing
stratum**, with n >= 20 in that stratum.

### 8.5 What no result licenses

No result from this study licenses "the machine is more accurate than a human at reading error
bars from real figures". That claim needs an oracle. It is established, and will only be
cited, on the **synthetic** benchmark against R's exact descriptives. The real-figure study
establishes **transfer and interchangeability**. Keeping those two sentences apart is the
study's main methodological contribution and the report prints both, adjacent, every run.

---

## 9. The scorer and its self-test

`score_real_validation.py` consumes the normalized GT store (section 10), machine predictions,
the repeat annotations and the coded reference, and emits the stratified report plus
`out/*.csv` for the R stage. It runs, and reports "not available", when any input is missing.

`--selftest` builds a synthetic GT store, injects one failure at a time, and asserts that the
metric that owns that failure moves and the others do not. Tests, by tier:

```
P1  perfect prediction scores perfectly
P2  box shift             -> IoU falls monotonically, count unaffected
P3  LABEL SWAP            -> label accuracy falls, silent-mislabel rate rises,
                             IoU and count UNCHANGED           <- the catastrophic class
P4  dropped panel         -> count + recall fall
P5  spurious box          -> false positives + count, IoU intact
P6  abstain on everything -> coverage 0, net figures saved < 0
P7  calibrated abstention -> precision 1.0, recall 1.0, net > 0
D1  figure bbox shift     -> detection IoU falls
D2  caption swapped between two figures -> caption-association accuracy falls, bbox IoU intact
E1  chart-type flip       -> classification accuracy + priority-flip rate move
E2  SEM read as SD        -> dispersion-type agreement falls; the sqrt(n) blow-up is visible
E3  ARM SWAP              -> arm mis-assignment and SIGN FLIPS rise while central and
                             dispersion % errors stay ~0       <- structural metrics are blind
E4  dispersion scaled x1.2-> BA bias moves, LoA narrow, central unchanged
E5  dispersion + noise    -> BA LoA widen, bias ~0, Grubbs sigma_M rises
D3  HUMAN-JITTER CONTROL  -> machine EXACTLY right, human jittered:
                             naive M-vs-G disagreement is LARGE while Grubbs sigma_M ~ 0
                             and sigma_G recovers the injected jitter
                                                               <- proves the section-1 distinction
D4  Grubbs recovery       -> on simulated data with known sigma_D, sigma_G, sigma_M, the
                             estimator recovers all three within tolerance
D5  shared-person bias    -> injecting cov(e_G, e_D) = c inflates Grubbs sigma_M by ~c,
                             confirming the conservative direction claimed in section 1.3
X1  missing prediction    -> scored as a total miss, no crash
X2  missing input store   -> graceful skip, non-zero information, no crash
```

`P3` and `E3` are the tests that matter most: both are silent catastrophic classes that every
geometric or magnitude metric reports as perfect. `D3` is the test that encodes this document's
central methodological claim as an executable assertion.

---

## 10. Interface contract (what the scorer consumes)

A parallel effort owns the annotation harness and ingest. This is the contract the scorer codes
against. The scorer is **defensive**: any missing directory, file, or field degrades that
metric to "not available" and never crashes the run.

```
benchmark/real-validation/
  gt/       <figure_id>.gt.json      normalized human ground truth (one per FIGURE)
  repeat/   <figure_id>.gt.json      the >=14-day repeat, identical schema
  pred/<run>/<figure_id>.json        machine predictions, or pred/<run>.jsonl (one obj/line)
  coded/    coded_reference.json     the historical reading, built by make_coded_reference.py
  split.json                         written by --split; deterministic, recomputable
  synthetic_reference.json           frozen synthetic comparators (committed)
  out/                               report.txt, fields.csv, comparisons.csv, summary.json
```

### 10.1 GT record (`gt/<figure_id>.gt.json`)

Field names deliberately mirror `benchmark/panels/corpus/<id>.pgt.json`,
`benchmark/series/corpus/<id>.sgt.json` and the tool's own `annotations.json` v2, so the
synthetic scorers' definitions carry over unchanged.

```jsonc
{
  "schemaVersion": 1,
  "id": "Bonaccorsi2013_fig1",          // figure id; join key everywhere
  "article": "Bonaccorsi2013",          // must match rodent_data.csv Article_ID
  "doi": "10.1155/2013/196948",
  "pdf": { "path": "...", "page": 3, "dpi": 600 },
  "image": "images/Bonaccorsi2013_fig1.png",
  "figure": { "width": 2012, "height": 1402 },

  // provenance of the annotation act (bias controls, section 7)
  "annotator": "GSF", "session": 3, "positionInSession": 7, "globalIndex": 41,
  "startedAt": "2026-08-03T14:02:11Z", "durationSec": 214,
  "sawPrediction": false,               // TRUE makes the record unscorable
  "isRepeat": false,
  "excluded": null,                     // or { "code": "N_MISMATCH", "note": "..." }

  // --- TIER D -------------------------------------------------------------
  "detection": {
    "pageWidth": 5100, "pageHeight": 6600,
    "figureBbox": { "x": 610, "y": 890, "width": 2012, "height": 1402 },  // PAGE px
    "captionText": "Figure 1. Spatial memory ... (A) ... (B) ...",
    "captionBbox": { "x": 610, "y": 2300, "width": 2012, "height": 180 },
    "figuresOnPage": 2
  },

  // --- TIER P -------------------------------------------------------------
  "caption": "Figure 1. ...",
  "expectedLetters": ["A", "B"],
  "nPanels": 2,
  "layoutClass": "guillotine",          // | "non-guillotine"
  "labelPlacement": "inside-tl",
  "gutter": { "measuredPx": 8, "measuredFrac": 0.004, "bucket": "tight" },  // bucket optional
  "origin": "flattened-bitmap",         // | "vector-text" | "mixed-xobjects"
  "panels": [
    {
      "index": 0, "label": "A",
      "bbox":     { "x": 29, "y": 28, "width": 940, "height": 1340 },  // FIGURE-relative px
      "bboxCore": { "x": 29, "y": 60, "width": 940, "height": 1308 },  // optional, letter excluded
      "labelDrawn": true, "labelBbox": { "x": 31, "y": 30, "width": 26, "height": 30 },
      "contentType": "bar",

      // --- TIER E ---------------------------------------------------------
      "chartType": "grouped-bar",       // CHAR_VOCAB.charType
      "dispersionType": "SEM",          // CHAR_VOCAB.dispersion
      "dispersionTypeSource": "caption",// caption | axis | methods | convention
      "dispersionFlags": [],            // CHAR_VOCAB.flags subset
      "cueType": "color", "legendStyle": "right", "occlusion": "none",
      "sigMarkersOverCaps": true,
      "calibration": {
        "calPixels": { "x1": {"px":392,"py":920}, "x2": {"px":532,"py":920},
                       "y1": {"px":130,"py":920}, "y2": {"px":130,"py":40} },
        "calVals":   { "x1": "0", "x2": "1", "y1": "0", "y2": "25",
                       "logX": false, "logY": false }
      },
      "groups": [ { "groupId": "target", "label": "Target zone" } ],
      "series": [ { "seriesId": "sc", "label": "SC", "role": "control" },
                  { "seriesId": "ee", "label": "EE", "role": "intervention" } ],
      "landmarks": [
        {
          "landmarkId": "target|sc",    // convention: "{groupId}|{seriesId}" (the arm key)
          "groupId": "target", "seriesId": "sc", "kind": "bar",
          "centralPx":    { "px": 392, "py": 330 },   // bar top / point / median
          "dispersionPx": { "px": 392, "py": 229 },   // the cap
          "baselinePx":   { "px": 392, "py": 920 },   // optional
          "capLenPx": 101,                            // optional; derived if absent
          "n": 5,
          "central": 16.4,                            // optional; derived from pixels if absent
          "dispersion": 2.7,                          // in the SHOWN units (SEM here)
          "flags": []
        }
      ]
    }
  ]
}
```

**Rules the harness must honour.** `bbox` for panels is figure-relative; `figureBbox` is
page-relative; both in pixels at `pdf.dpi`. Values may be supplied as pixels only -- the scorer
recovers data units through the **shared affine** `benchmark/harness/calibrate.py`, which is
byte-verified against `window.figureExtractor.calibrate`, so GT and predictions pass through
identical arithmetic. Where both pixels and values are supplied, the scorer recomputes from
pixels and reports any mismatch above 0.5% as an ingest defect rather than silently choosing.

**Fallback ingest -- three accepted shapes, so the analysis is never blocked on the
harness converging on a format.** The scorer reads, in order:

1. `gt/<figure_id>.gt.json` -- the normalized schema above.
2. **Any `*.jsonl` under `gt/`** (one record per line), including the annotation
   harness's `gt/human_gt.jsonl` and `gt/<session>/panels_gt.jsonl`. Records in the
   harness's flatter per-figure shape (`task`, `figureIndex`, `figureBbox`, `panels[]`
   with `letter`) are coerced automatically.
3. Any `annotations.json` (tool schemaVersion 2) under `gt/`, normalized in place
   (`figures[]` -> figure records, `subfigures[]` -> panels, `characterization` ->
   chart/dispersion type, `digitization`/`extraction` -> landmarks).

**One coercion rule worth stating, because getting it wrong forges the study's headline
failure.** A panel's identity is its **letter**, not its display label. The harness emits
`label: "Figure 5 A"` alongside `letter: "A"`; the scorer takes `letter`, falling back to
the trailing letter of the label. Comparing `"Figure 5 A"` to a detector's `"A"` would
score every *correct* letter as a silent mislabel -- a scoring artefact indistinguishable,
in the report, from the catastrophic class the study exists to bound.

### 10.2 Prediction record

Same shape as the GT for the fields it predicts, plus the detector's own contract fields, which
match `detectPanelsCore`'s documented result object:

```jsonc
{
  "id": "Bonaccorsi2013_fig1", "run": "cascade_v4", "toolVersion": "<git sha>",
  "detection": { "figureBbox": {...}, "captionText": "...", "confidence": 0.9 },
  "confidence": 0.82, "abstain": false, "flags": ["weak-gutter"],
  "method": "gutter+labels", "lettersVerified": true, "letterSource": "anchors",
  "panels": [ { "label": "A", "bbox": {...}, "conf": 0.9,
                "chartType": "grouped-bar", "dispersionType": "SEM",
                "series": [...], "groups": [...], "landmarks": [...] } ]
}
```

Abstention: `abstain: true`, or `confidence < --abstain-at` (default 0.5, matching the panels
tier). A missing prediction file is scored as a total miss, not skipped.

### 10.3 Coded reference (`coded/coded_reference.json`)

Built by `make_coded_reference.py` from
`GSF-dissertation-meta-analysis/data/raw/rodent_data.csv`. One record per coded comparison:

```jsonc
{ "article": "Aykan2024", "comparisonId": "Aykan2024_1_1",
  "dataSource": "Figure 5B", "figureNumber": "5", "panelLetter": "B",
  "figureId": "Aykan2024_fig5", "figureDerived": true,
  "extractionMethod": "Reported in text and figure",
  "oracleClaimed": true,        // the LABEL claims a text source
  "oracleVerified": "NOT_FOUND",// verify_oracle.py verdict; the only thing that counts
  "isOracle": false,            // true ONLY on TEXT_CONFIRMED -- see sec.1.4b
  "direction": "higher better", "design": "between-groups",
  "controlArmName": "SE+Vehicle", "intervArmName": "EE+Vehicle",   // series->arm reference
  "multiArm": true, "nArms": 2, "sharedControl": false, "vifMultiarm": 1.0,
  "control": { "mean": 20.13, "n": 8, "varianceValue": 2.01, "varianceType": "SEM",
               "sd": 5.686, "roundingQuantumPct": 0.2488 },
  "interv":  { "mean": 21.7,  "n": 8, "varianceValue": 2.7,  "varianceType": "SEM",
               "sd": 7.637, "roundingQuantumPct": 1.8519 },
  "complete": true,
  "controlLandmarkId": null, "intervLandmarkId": null }   // filled by the annotator
```

`sd` is derived from the **recorded** `varianceType`, never from convention: SEM and SE are
multiplied by `sqrt(n)`, CI-95 by `sqrt(n)/1.96`, CI-99 by `sqrt(n)/2.576`, and an
unrecognised type yields `null` rather than a guess.

`controlLandmarkId` / `intervLandmarkId` are the **only** manual join the analysis needs: which
bar in the panel is which coded arm. Until they are supplied the extraction tier reports
"not available" for that row rather than guessing. Guessing here would fabricate exactly the
arm mis-assignment the study is trying to measure.

---

## 11. Known gaps in this design

Stated now so they are not discovered as objections later.

1. **One rater.** `D` and `G` are the same person, so section 1.3 bounds intra-rater
   reliability, not inter-rater. A genuine second annotator on even 30 panels would convert
   every "this human, twice" sentence into "two humans" and is the single highest-value
   addition. Not budgeted here.
2. **Grubbs assumes independent errors.** Violated in the known direction (section 1.3);
   bracketed, not eliminated.
3. **No synthetic detection benchmark**, so Tier D has no `Delta`. Building one is cheap (the R
   generator can emit page composites with known figure boxes and captions) and is the obvious
   follow-up.
4. **The figure-level exact-count `Delta` is underpowered** at ~21 pp (section 4.3). Reported
   with that label attached.
5. **Domain scope.** 43 rodent behavioural neuroscience articles from one meta-analysis.
   Generalisation to other fields, and to figures produced by other plotting toolchains, is
   unestablished. The `journal` and `origin` strata are the only evidence the study can offer
   on this and they are descriptive.
6. **The oracle stratum is currently 1 confirmed comparison, not the ~52 the labels
   suggested** (section 1.4b). Until `verify_oracle.py` is re-run over the full
   171-article PDF set there is effectively **no real-figure accuracy stratum**, and the
   study's dispersion claim is an agreement claim. If the stratum does materialise it will
   still be non-random -- papers that print their numbers are plausibly better-reported
   papers -- and carries that selection caveat.
7. **PDF coverage is the binding constraint on the oracle check**: 104 of 138 candidate
   comparisons could not be checked because the article's PDF is not yet resolved. That is
   a resolvable engineering gap, not a measurement one.
8. **~94% of the corpus is SEM.** The study will say a great deal about the short-cap
   regime and comparatively little about SD-plotted figures (~50 arm-values), which are
   the easier case. Generalising the dispersion result to SD-plotted literature is not
   supported.

---

## 12. Amendments

None. Any change after LOCK is scored goes here with a date, a reason, and a note of which
results become post hoc.

---

## 13. Files in this directory

| file | role |
|---|---|
| `ANALYSIS-PLAN.md` | this pre-registration |
| `synthetic_reference.json` | frozen synthetic comparators + every pre-specified threshold, so `Delta` is computed against a citable artifact rather than a remembered number |
| `make_coded_reference.py` | workbooks (198 `.xlsm`) -> `coded/coded_reference.json`; per-arm variance TYPE, arm names, VIF, rounding quantum. `--stats` prints the population table |
| `verify_oracle.py` | the mechanical oracle test of section 1.4b; sets `isOracle` only on TEXT_CONFIRMED |
| `score_real_validation.py` | the scorer: tiers D/P/E, stratification, transfer gap, gates, `--selftest`, `--power`, `--split` |
| `golden_diff_rv.R` | the end-to-end metafor stage: three readings, pairwise triangle, cluster bootstrap, TOST, mechanical threshold check |
| `split.json` | the DEV/LOCK assignment (generated, recomputable from the published salt) |

Reproduce:

```bash
cd benchmark/real-validation
python3 make_coded_reference.py            # coded/coded_reference.json  (+ --stats)
python3 verify_oracle.py                   # sets isOracle where the text confirms it
python3 score_real_validation.py --split   # split.json
python3 score_real_validation.py --power   # the sample-size table
python3 score_real_validation.py --selftest
python3 score_real_validation.py --run <run> --split-filter lock
Rscript golden_diff_rv.R
```
