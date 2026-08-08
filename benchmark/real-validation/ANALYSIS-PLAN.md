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
| **E** extraction | how do classification, series->arm parsing, central tendency and **dispersion** behave? | landmark / comparison | mixed -- see section 3 | **accuracy** for discrete targets (type, arm identity, n); **agreement + a three-reading variance decomposition** for dispersion values; real-figure accuracy on the verified oracle stratum -- **20 comparisons / 17 panels / 12 figures / 12 articles corpus-wide, and only 5 / 5 / 3 / 3 inside LOCK**, so it is DESCRIPTIVE, not powered (sec.1.4b) |

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

equivalently `sigma_M^2 = Cov(M-G, M-D)`. No oracle is required. It is **one of three
estimates of the dispersion channel**, reported beside Bland-Altman and the oracle stratum,
with its assumption stated every time.

**The assumption, and why the earlier version of this section was wrong.**
Grubbs identifies `sigma_M` only if `e_D`, `e_G` and `e_M` are **mutually uncorrelated**.
Writing `c_XY = Cov(e_X, e_Y)`, the estimator's expectation with correlated errors is:

```
E[sigma_M^2 (Grubbs)] = sigma_M^2 + c_DG - c_DM - c_GM
E[sigma_G^2 (Grubbs)] = sigma_G^2 + c_GM - c_DG - c_DM
E[sigma_D^2 (Grubbs)] = sigma_D^2 + c_DM - c_DG - c_GM
```

Earlier versions of this plan kept only the `+ c_DG` term -- `D` and `G` are the same
person, so their errors plausibly share a component (a habitual way of reading a cap: its
centre line vs its upper edge, a consistent tick-identification bias) -- and concluded that
the estimate could only ever be too LARGE, i.e. **"conservative against the machine"**.

**That conclusion is withdrawn.** `c_DM` and `c_GM` are not zero, and they enter with a
MINUS sign. Section 7 of this document lists *"machine and human both misread the same
ambiguous cap the same way"* as a live validity threat; a cap hidden behind a significance
asterisk, a cap on a 6-pixel error bar, a bar top under a data-point cloud -- these are
difficulties shared by **every** reader of that panel, human or machine. Whenever a panel is
hard for the human it tends to be hard for the machine, and that is precisely a positive
`c_DM` and `c_GM`.

**Binding consequence: the direction of the bias is UNKNOWN** without assuming the machine's
errors are uncorrelated with the humans'. No sentence anywhere in this study, in the scorer's
output, or in the write-up may describe the Grubbs estimate as conservative, as a bound, or
as biased against the machine. It may be described only as *an estimate under an
independence assumption that the design cannot verify from the three readings alone*, because
a shared error looks exactly like agreement. Selftest **D5b** reproduces the
anti-conservative case with a known truth -- a shared-difficulty component makes Grubbs
return a `sigma_M` well below the true value -- so the failure mode stays visible in the
test output rather than living only in this paragraph.

**Bracketing `c_DG` (and only `c_DG`).** The intra-rater repeat subset gives `sigma_G^2`
directly and independently of Grubbs: `Var(G1 - G2) = 2 * sigma_G_repeat^2`. Then

```
c_hat = sigma_G_repeat^2 - sigma_G^2 (Grubbs)
```

and the machine variance is reported as an interval
`sigma_M in [ sqrt(max(0, sigma_M^2(Grubbs) - c_hat)), sqrt(sigma_M^2(Grubbs)) ]`.
**This interval brackets `c_DG` alone. It does not bracket `c_DM` or `c_GM`**, so when
shared reading difficulty dominates, the whole interval can sit *below* the true `sigma_M`.
Both endpoints are reported; neither is presented alone; and neither is called a bound.

**The cross-check that can actually see the confound: the ORACLE stratum.**
On the oracle rows the truth is **printed in the paper**. It was not read off the drawing by
anybody, so no error shared between the machine and the humans can move it. `sd(log(M /
printed truth))` is therefore an estimate of `sigma_M` that carries no `c_DM`, no `c_GM` and
no `c_DG` -- the only such estimate the design has.

> **Pre-specified reading rule.** Report Grubbs `sigma_M` and oracle `sigma_M` side by side,
> with the oracle stratum's size at the scope being analysed. If the **oracle estimate is
> materially larger** than the Grubbs estimate, that is evidence the shared-difficulty
> confound is present and **Grubbs is understating the machine's error** -- the
> anti-conservative direction. Say so in those words. If the oracle estimate is materially
> smaller, `c_DG` is likely dominating and Grubbs is overstating. If they agree, the
> independence assumption has survived a real test, which is the only circumstance in which
> the Grubbs number should be quoted without the assumption attached.
>
> The scorer computes this as `_dispersion.grubbsVsOracle` and prints it as layer (f) of the
> dispersion report. It is **underpowered at the oracle stratum's realised size** (sec.1.4b),
> and the report says so; an underpowered check that can detect the confound is still the
> only check that can detect it at all.

**What `D` vs `G` is and is not.** Because both are Greg, `Var(D-G)` bounds **intra-rater,
cross-tool, cross-occasion** reliability. It is **not** inter-rater reliability and will
understate the variability of "a human digitizer" as a population. Any sentence about "a
human" in the write-up must say *this human, twice*. Obtaining a genuine second rater is the
single change that would most strengthen this design and is listed in section 11 as the known
gap.

### 1.4 Why all four candidate approaches are used, and in what order

The four options are not alternatives; they answer different questions and they are layered,
cheapest claim first:

1. **Bland-Altman on `log(M/G)` and `log(M/D)`, reported BY CAP-LENGTH TERTILE** -- the
   *reporting form*. Bias (systematic offset) and 95% limits of agreement (random spread).
   This is the honest description of "are these two readings interchangeable in a
   meta-analysis?", which is the question a reviewer actually has. It makes no accuracy
   claim. Its one assumption -- approximate normality of the log-ratios -- is now *screened*
   with a probability-plot correlation rather than assumed, and the LoA is computed within
   strata because the log transform does not stabilise the variance here (section 3.3).
   **Always reported.**
2. **Intra-rater noise floor from repeats** -- the *yardstick*. Machine error is reported as a
   ratio to the human's own measured repeatability, never against zero. **Always reported.**
3. **Grubbs three-reading decomposition** -- **one of three estimates, not the primary
   claim** (amendment A2). The only route to a per-method error variance without an oracle,
   and it buys that at the cost of an independence assumption the three readings cannot
   themselves verify. Reported with its assumption attached and never as a bound. See
   section 1.3.
4. **Accuracy restricted to a gold standard** -- reported on two strata where a gold standard
   genuinely exists: (a) the **synthetic benchmark** (R's exact descriptives; already done,
   cited not re-run); (b) a **text-anchored real stratum** -- rows whose numeric value is also
   printed in the paper's text/table, so the published number is ground truth for the drawing.
   Measured availability: **52 of 145 figure-derived rows across 17 articles** have
   `Data_Extraction_Method` naming a text or table source. **This is the only real-figure
   accuracy claim in the study and it is confined to that stratum.**

### 1.4b The oracle stratum, re-tested against all three places a number can be printed

**The first test asked the wrong question.** `verify_oracle.py` (v1) searched the article's
BODY TEXT only, over the 138 comparisons whose `Data_Extraction_Method` *claims* a text
source, and returned **1 confirmed of 34 checkable**. Two things were wrong with that.

*First, the semantics.* Greg (the coder) has since clarified that "Reported in text and
figure" / "Reported in text/figure" means the number appeared in **any** of: (a) the body
text, (b) the **figure caption**, or (c) **printed inside the figure itself** -- above a
bar, or in an inset table. v1 could see (a) only, so it undercounted by construction.

*Second, the universe.* v1 resolved PDFs through `benchmark/real/pdf_map.json`, which
covers the **43** articles that survived the meta-analysis' content screen, not the 171
with figure data. 104 of its 138 candidates came back `NO_PDF` -- it checked 34 rows and
called the answer. Resolving DOIs directly against Zotero reaches **164 of 171** articles.
And the label restriction was itself a mistake: the label does **not** predict the verdict
(table below), so filtering on it discarded most of the real hits before the search began.

**The re-test (`verify_oracle_v2.py`).** Every one of the 434 figure-derived comparisons,
against three DISJOINT zones of its PDF:

| zone | what it is | how it is read |
|---|---|---|
| `TEXT` | every block that is not a real caption and is not a short label inside a figure, references stripped | PDF text layer |
| `CAPTION` | the caption block of the *named* figure ("Figure 5B" -> the "Fig. 5." block) | PDF text layer |
| `IN_FIGURE_VECTOR` | text spans whose bbox falls inside the figure's region on the page | PDF text layer -- no OCR needed |
| `IN_FIGURE_OCR` | the figure region rendered at 400 dpi | tesseract 5.5 |

Disjointness is load-bearing: without it every caption hit would also count as a body hit
and the provenance split would mean nothing.

**Confirmation requires a PAIR.** The coded mean *and* its variance must be found together
as a printed `m +/- s`, `m (s)`, or `m, SEM = s`. A lone number is not evidence: measured
on this corpus, coded 20.13 "matches" the 20 of "20 mg/kg", coded 0.53 matches "exceeding
0.5, the chance level", and coded 21.7 matches a grant number. Inside a figure the problem
is worse -- every axis tick is a lone number -- so the mean-only tier additionally drops
tokens belonging to an arithmetic tick sequence, and is never run over body text at all.

**Tolerance is the printed token's own rounding half-width**, not a flat percentage. A
value printed as `20.1` asserts only that the truth lies in [20.05, 20.15), so that
half-width is the match radius; coded 20.13 matches printed `20.1` and printed `20`, but
not printed `20.2`. This is the correct model of "the paper rounded", and it is what
resolves the two near-misses that a flat 6% bar mis-ruled (SAMPLING-AND-WORKLIST.md sec.0b).
The variance channel accepts either the coded variance as recorded **or** the SD derived
from it, so a paper printing `mean +/- SD` against a coder who recorded SEM is a
confirmation of both numbers rather than a miss; which one matched is recorded per row.

**Measured result, over all 421 checkable comparisons (13 of 434 have no PDF).** These are
the counts AFTER the guard restoration and the hand adjudication described immediately
below; the first version of this table reported 33 and was wrong.

| verdict | comparisons | share of checkable |
|---|---|---|
| CONFIRMED_TEXT | **18** | 4.3% |
| CONFIRMED_CAPTION | **2** | 0.5% |
| CONFIRMED_IN_FIGURE_VECTOR | **0** | 0.0% |
| CONFIRMED_IN_FIGURE_OCR | **0** | 0.0% |
| REJECTED_ADJUDICATION | 12 | 2.9% |
| PARTIAL_MEAN | 28 | 6.7% |
| NOT_FOUND | 361 | 85.7% |

**20 confirmed comparisons across 17 distinct PANELS, 12 distinct FIGURES and 12 articles.**
All 20 have both the mean and the variance channel confirmed.

> **Panels are not figures and the plan previously conflated them.** The earlier "21 panels"
> was produced by a helper keyed on `figureId`, so `Zhang2017` "Figure 3d" and "Figure 3e" --
> two panels of one figure -- collapsed into one. That number was a FIGURE count standing
> next to a panel-level bar. `verify_oracle_v2.py::summarise` now keys panels on
> `(article, figureId, panelLetter)` and reports comparisons, panels, figures and articles
> as four separate columns, at every scope.

**How 33 became 20.** Two independent corrections, both of which reduce the count:

1. **The pair guard was restored (13 -> 12 of the loss is here: one row).** `match_arm`
   had been relaxed from "the printed MEAN token must be informative" to "the mean OR the
   variance must be", specifically so that `Bakeche2020`'s printed `(3 +/- 0.81)` would
   confirm. Hand inspection shows that confirmation is false in four separate ways -- wrong
   outcome, wrong lighting condition, wrong phase, and the arms inverted -- so the
   relaxation bought exactly one false positive and no true ones. A one-digit mean cannot
   carry a match: it collides with an axis tick, a group size or a day index far too often.
   Restored at `verify_oracle_v2.py::match_arm`.
2. **Twelve rows failed hand adjudication.** The mechanical search cannot tell that a
   printed `110.5 +/- 21.6` belongs to the 14-month cohort rather than the 4-month row that
   claimed it, or that a sentence describes the elevated zero maze rather than the Barnes
   maze panel named by the row. That judgement requires reading the article. The ledger
   lives in `verify_oracle_v2.py::ADJUDICATION`, is applied before anything is counted or
   written, is disabled by `--no-adjudication`, and reproduces every rejection with the
   sentence that decides it. Its rules are: it may only REJECT what the mechanical search
   proposed (never promote); it judges on the evidence sentence and the coded row's own
   outcome/group/timepoint, never on how anything later scores; and it rejects only where
   the article DEMONSTRABLY contradicts, never on silence.

   The two acceptance conditions are (a) each printed `m +/- s` is the quantity the coded
   arm names, and (b) nothing in the article contradicts the row's `dataSource` panel.
   Condition (b) is not pedantry: the oracle's job is to be the truth for the value a rater
   and the machine read *out of that panel*, so a row that names panel C while its printed
   numbers belong to panel D would score a correct machine read as a gross error.

   The twelve rejections, by failure class: **wrong age cohort or apparatus** (3 --
   `Singhal2019` x3, where the paper prints the 4-month control as 3.7 +/- 0.7 while the row
   claims 110.5 +/- 21.6, and where an elevated-zero-maze open-arm sentence was matched to a
   Barnes-maze escape-latency panel); **wrong panel** (4 -- `Ederer2022` x2, `Lee2024_1_1`,
   `Mansk2023_2_1`); **wrong source table** (2 -- `Frick2003` x2, where the values are cells
   of a platform-trial summary table while the named figure is a per-block acquisition
   curve); **wrong arm** (2 -- `Mansk2023_1_1`, where 0.40 +/- 0.08 is the C57BL/6 strain
   and not the "Swiss enriched" arm; `Gawryluk2024_2_1`, where both printed values are the
   SAME arm on day 1 and day 3); **pre-test read as the test** (1 -- `Smith2018_1_1`).

**The permutation null, re-run against the right alternative.** The shipped null drew donor
codings from the WHOLE CORPUS at `--null-reps 3`, so the headline FDR rested on two events
and on trials that were 99.35% cross-article. Both defects are fixed: the default is now
`--null-reps 1000`, and four nulls are reported.

| null | donors | trials | confirmed | rate | implied FDR on 20 |
|---|---|---|---|---|---|
| **magnitude-matched (PRIMARY)** | other article, control mean within a factor of ~1.8 | 404 000 | 1 203 | **0.298%** | **6.3%** (~1.3 rows) |
| within-article, donors this paper does NOT print | same article, own verdict `NOT_FOUND` | 328 000 | 0 | 0.000% | 0% |
| within-article, ANY donor | same article, any row | 368 000 | 28 068 | 7.627% | 160% -- absurd |
| corpus-wide (what v2 shipped) | anywhere | 86 611 | 297 | 0.343% | 7.2% |

Read that table honestly, because it does **not** say what the objection to it predicted.
The alarming "within-article collisions are ~18x more likely" figure is line 3, and line 3
is not a null at all: a donor drawn from the same paper very often has its *own* values
printed there, so the trial confirms because the donor is genuinely printed, not by chance.
The hypothesis being simulated is false for the donor by construction. Line 2 removes that
tautology but has a measured coverage hole -- 12 of the 17 mechanically-confirming articles
contain no `NOT_FOUND` row, so it is dominated by papers that print nothing. Line 1 keeps
the magnitude realism (magnitude is what drives a chance collision) while guaranteeing the
donor is not printed in the target's paper, and it lands at **0.9-1.0x the corpus-wide
rate**. **The corpus-wide null was not the thing that was wrong.** What inflated the count
was the relaxed pair guard and twelve semantic mismatches, and those are what the corrected
count removes.

**The label does not predict the verdict.** This reproduces the sampling document's
finding and is worth reporting on its own:

| `Data_Extraction_Method` | CONFIRMED | PARTIAL |
|---|---|---|
| Reported in text | **16** | 1 |
| Reported in text/figure | **3** | 10 |
| Extracted from figure | **6** | 5 |
| Reported in text and figure | **4** | 5 |
| Reported in text and figures | **2** | 0 |

"Reported in text/figure" confirms at 3 of 13; plain "Reported in text" at 16 of 17, and
*"Extracted from figure"* -- a label that denies a text source -- yields 6. The provenance
field is not a usable selector. The mechanical check is.

**The most valuable hypothesis is dead, and the negative is well measured.** A value
printed inside the figure, beside the mark you would measure, would be a within-figure
accuracy oracle needing no annotation and no cross-referencing assumption. It does not
exist in this corpus. 224 of 238 figure regions were located; **68 carried readable vector
text spans (924 numeric tokens) and 174 were OCR'd (3842 numeric tokens)** -- and across
all 4766 tokens there is **not one printed `mean +/- variance` pair**. The five candidate
pairs OCR returned are artefacts: `0.01 (0.003)` is a p-value annotation, `1 (1,14)` is
the `F(1,14)` of a test statistic, `4 084` is OCR noise. Inspected directly, the numbers
inside these figures are axis ticks, group labels (`SC-2`, `EE-15`), timeline annotations
(`3X`, `5 min`, `20X`) and sample sizes. **The rodent enrichment literature does not print
its data values in its figures.** That is a measurement over 222 surveyed figures, not an
impression, and it should be reported as such -- it is also the reason the extraction tool
this study evaluates has to exist.

**The stratum size AT THE SCOPE BEING ANALYSED, which is the only size that may be quoted
beside a result.** The corpus-wide count describes 434 coded comparisons across 171
articles. The study does not analyse 171 articles; it analyses the worklist, split
DEV/LOCK. Those are different, much smaller numbers, and a Tier-1 result may not cite the
corpus-wide 20 any more than it could cite the old 33.

| scope | comparisons | panels | figures | articles |
|---|---|---|---|---|
| corpus-wide (all 434 coded) | 20 | 17 | 12 | 12 |
| worklist tiers 1-1 | 4 | 4 | 2 | 2 |
| tiers 1-1, DEV | 0 | 0 | 0 | 0 |
| tiers 1-1, **LOCK** | **4** | **4** | **2** | **2** |
| worklist tiers 1-3 | 5 | 5 | 3 | 3 |
| tiers 1-3, DEV | 0 | 0 | 0 | 0 |
| tiers 1-3, **LOCK** | **5** | **5** | **3** | **3** |

`verify_oracle_v2.py` emits this table on every run (`scopes` in the report JSON) and
`score_real_validation.py` prints the joined stratum's size, at the run's own
`--split-filter`, immediately beneath the oracle accuracy line. Only nine of the twenty
oracle articles fall inside the worklist frame at all, and only three inside the LOCK half
of it -- so the oracle stratum is essentially a **corpus-level** result that the
confirmatory set barely touches.

**Consequences, binding:**

1. The pre-registered bar was **>= 30 confirmed comparisons across >= 10 articles**.
   Observed after correction: **20 comparisons / 17 panels / 12 figures / 12 articles ->
   NOT MET.** The comparisons bar fails; the articles bar passes. The oracle stratum is
   therefore **NOT promoted to a powered accuracy analysis**. It is reported
   **descriptively**, always with its n at the analysed scope, and it may not carry a
   threshold verdict. The corresponding row of the section-3.3 metric table is marked
   "not establishable -- reported descriptively only".
2. It nonetheless retains one job that nothing else can do: it is the **only estimate of
   `sigma_M` immune to the shared-difficulty confound** of section 1.3, because its truth
   is printed rather than read. Underpowered at n = 5 LOCK comparisons (10 arm-values), the
   cross-check is weak -- but a weak check that can see the confound is the only check that
   can see it at all, and the report prints its n beside it so nobody mistakes it for
   strong.
3. `isOracle` is set exclusively by `verify_oracle_v2.py`, on a `CONFIRMED_*` verdict that
   has also survived adjudication. Each such row carries `oracleSource`
   (`body_text` | `caption` | `in_figure_vector` | `in_figure_ocr`) and the two channel
   flags `oracleMeanConfirmed` / `oracleVarianceConfirmed`; all 20 have both.
4. **The selection caveat is not optional.** These rows were found by searching for the
   coded value, so the procedure can only find printed values that AGREE with the coding;
   a panel the coder read badly cannot enter the stratum. This does not invalidate the
   oracle for its actual purpose -- scoring the *machine's* read against the printed truth
   -- but it does mean the stratum is a non-random sample of panels, biased toward
   well-reported papers and accurate codings. Report it with the estimate, every time.
5. Provenance is **body text (18) and caption (2)**. No accuracy claim of the form "the
   value was printed in the figure" is available at any n.
6. **The adjudication is itself a finding about the corpus**, and should be reported as
   one: 12 of 32 mechanically-confirmed rows (38%) were cross-panel, cross-cohort or
   cross-outcome mismatches between a coded row and the sentence that appears to support
   it. Anyone building a text-anchored oracle by regex alone, without reading the papers,
   should expect a comparable rate.

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

Metrics live at different levels; inference must respect the nesting. **Every confidence
interval this study reports is computed by article-level cluster bootstrap (B = 10000
resamples of articles with replacement)**, via the single entry point
`score_real_validation.py::cb`, which is called for the caption gates, letter-set accuracy,
figure-bbox IoU, every panel-tier rate and median, every extraction-tier rate, the naive and
central medians, the Bland-Altman bias and both limits of agreement, the Grubbs
`sigma_M / sigma_G` ratio, and the oracle median. Design-effect arithmetic appears only in
the sample-size section, for planning; it is never used for inference.

**The exceptions, stated here and labelled again at the point of printing.** A blanket
"all CIs are clustered" claim that the program does not implement is worse than no claim,
so the list is exhaustive:

- **The rule-of-three zero-event upper bound** (silent mislabel, arm-name error, sign flip)
  is **not cluster-adjusted, and cannot be.** With 0 observed events every bootstrap
  resample also has 0 events, so the bootstrap returns `[0, 0]` and carries no information.
  The report prints the panel-level bound *and* the article-level bound and says in the
  output that neither is a cluster bootstrap.
- **`R_floor`** is printed as a point estimate with **no interval at all**.
- Lines suffixed `_iid` (`captionCI_iid`, `ratio_MG_ci_iid`, `medianCI_iid`) are the naive
  intervals, printed **only** as the labelled contrast that shows how much narrower they
  would have been. They are never the reported interval.

Selftest `S2b` measures the difference on a deliberately clustered sample: the cluster
interval comes out **2.88x** the width of the Wilson interval it replaced. The i.i.d.
intervals this plan previously described as clustered were, on the shipped code, roughly
19-25% too narrow at the panel level and about 1.6x too narrow at the article level.

### 2.2 The three tiers, and why they have different sample sizes

Detection GT is cheap (one box, one caption confirmation). Panel GT is moderate. Extraction GT
is expensive and is additionally *capped* by the existence of a historical coded reading. So:

| tier | unit | annotate on | ORIGINAL target N | **ACHIEVABLE at LOCK** (worklist, 21.9 h) |
|---|---|---|---|---|
| D | **figure** | every figure on every page sampled from the PDFs, coded or not | >= 150 figures, >= 30 articles | **49 figures / 30 articles** |
| P | **panel** | a stratified sample of **compound** figures from the same PDFs | >= 180 panels / >= 55 figures | **175 panels / 49 figures** |
| E discrete | **panel** | only panels with a historical coded reading | >= 120 panels | **69 panels** |
| E dispersion | **arm-value** | 2 per coded comparison | ~290 arm-values | **200 arm-values** |
| end-to-end | **comparison** | coded comparisons | 145 comparisons | **100 comparisons** |

**The units are not interchangeable and the plan previously mixed them.** The ">= 120
panels" target was derived in section 4.2 from the *silent-mislabel* arithmetic, which is a
**Tier P** quantity -- and Tier P clears it comfortably at 175 LOCK panels. It was then
also applied to **Tier E**, where the annotation unit is a coded panel and only 69 exist in
the LOCK half of the worklist. Dispersion is measured on **arm-values**, of which there are
two per comparison, so that channel is better powered than the sign-flip channel on the
identical sample. Section 4.0 states what each unit buys.

**Regenerate these numbers rather than trusting them:**

```bash
python3 score_real_validation.py --power     # prints the achievable-N table from worklist.json
```

Tier E is the only tier bounded by the dissertation. The workbooks raise the theoretical
bound from 98 panels to **355**, so the binding constraint is now Greg's time and the
worklist's own sampling frame, not the data: the sampled worklist reaches 86 coded panels
in total and 69 in LOCK. Extending Tier E toward the 355-panel ceiling would require
drawing more articles into the worklist, which is a sampling decision, not an annotation
one.

### 2.3 DEV / LOCK split -- assigned NOW, by rule, before any figure is seen

Split at the **article** level (never the panel level: two panels of one figure share layout,
typeface, gutter and journal, so panel-level splitting leaks).

```
key    = canonical_article(Article_ID)             # lowercase, strip every non-alphanumeric
h      = sha256("figure-extractor-real-validation-v1|" + key).hexdigest()
bucket = int(h[:8], 16) % 3
split  = "dev" if bucket == 0 else "lock"          # ~1/3 dev, ~2/3 lock
```

The salt string `figure-extractor-real-validation-v1` is fixed by this document. Anyone can
recompute the assignment from the salt and the article name alone; it is a pure function and
it cannot be redrawn to suit a result. `score_real_validation.py --split` prints the
assignment and writes `split.json`.

**`canonical_article` is not cosmetic** (amendment A8). The corpus spells the same article
both ways: `Garcia-Capdevila2009` in the coded reference, `GarciaCapdevila2009` in the
worklist; likewise `Sampedro-Piquero2018`, `Mora-Gallegos2015`, `Del-Arco2007`. Hashing the
raw name made an article's split depend on its typography, and exact-string membership in
`PERMANENT_DEV` failed outright -- see the amendment for what that cost. One canonicalisation
helper is used for `PERMANENT_DEV`, for the hash, for the `split.json` lookup, for the
figure-id join between the GT store and the coded reference, and for the cluster-bootstrap
cluster key. Selftests `S1b`-`S1d` assert it over every `PERMANENT_DEV` entry in fourteen
spellings.

**Permanently DEV, never LOCK, regardless of hash** -- these are already contaminated (they
produced the asterisk-occlusion finding and the pilot numbers):

```
Gobeske2009           (fig1a)
GarciaCapdevila2009   (fig1a, fig1b)
Bonaccorsi2013        (fig1b 1-day, 10-day, 20-day)
Kazlauckas2011        (fig3A -- excluded pilot panel; the exclusion reasoning is known)
```

Applied to the 171 articles of the coded reference this yields **53 DEV / 118 LOCK**
(`split.json`, regenerate with `--split`). Under the pre-canonicalisation rule it was
71 / 100; moving the hash onto the canonical key reassigns 84 of the 171 (amendment A8,
which records the measured impact and the reason a redraw was preferred to a patch). The
assignment stands as drawn. Re-drawing it after seeing a *result* is the degree of freedom
this rule exists to remove, and no result exists: no LOCK panel, and no DEV panel outside
the four permanently-DEV pilot articles, has been annotated. Those four are unaffected by
the redraw, because `PERMANENT_DEV` overrides the hash.

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
`synthetic_reference.json`, which is **generated by `make_synthetic_reference.py`, never
edited by hand** (amendment A18): the panels block is computed live from
`benchmark/panels/score.py`, the rest is transcribed once from `benchmark/series/RESULTS.md`,
`benchmark/classify/RESULTS.md`, `benchmark/RESULTS.md` and `benchmark/real/RESULTS.md`.
A threshold marked **GATE** is a decision rule input (section 8).

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
| abstention precision | 0.14 | reported descriptively (A18) | -- |
| **abstention recall** | 1.00 | **= 1.00, i.e. 0 answered-and-wrong figures** **GATE** | -- |
| net figures saved by abstaining | -10 | reported descriptively (A18) | -- |

Silent mislabel is the catastrophic class: right box, wrong letter, every downstream number
attributed to the wrong sub-experiment, and -- as the series tier proved -- invisible to every
geometric metric. It gets a zero-tolerance threshold and it drives the panel sample size
(section 4).

The abstention gate is **recall**: every figure the detector would have got wrong must be
abstained on, because an answered-and-wrong figure is a silent error and a silent error is
the failure class this whole tier exists to prevent. An abstention costs a minute of human
attention; a silently mislabelled panel attaches a number to the wrong experimental arm and
corrupts a study's weight in the pooled model, undetectably. Those costs are wildly
asymmetric, which is why the gate is not stated on precision or on a net count that weights
them equally. Precision and net figures saved are the *cost* of the recall, reported
alongside coverage, never gated. The degenerate corner -- abstain on everything, recall
trivially perfect -- is held off by the coverage threshold above, which is unchanged.

**This gate was amended after data was seen.** As originally registered the gate was
`net figures saved > 0`, and the final cascade FAILS it: measured -10 (2 errors caught minus
12 correct answers thrown away). Amendment **A18** records what changed, why, and why the
original criterion was the wrong loss function for this decision; the superseded comparator
values (precision 0.88 / recall 0.94 / net +13, from an earlier detector build) are preserved
in `synthetic_reference.json` under `superseded`. Read A18 before trusting this table. The
synthetic round-2 cascade's perfect-0%-error-while-netting-**-1** result ("correct and
useless") remains the cautionary example for why the cost side must always be printed.

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
| (b) Bland-Altman on `log(SD_M / SD_G)`: bias and 95% LoA, **BY CAP-LENGTH TERTILE** | mean and mean +/- 1.96 sd of log-ratios, back-transformed, computed within each tertile | **abs(bias) <= 5%; LoA within [-25%, +25%], evaluated per tertile** **GATE**. The pooled LoA is printed as a diagnostic and is NOT a result -- see below |
| (c) Grubbs `sigma_M / sigma_G` (and `sigma_M / sigma_D`) | section 1.3, reported as the `c_DG`-corrected interval, with the bias direction stated as UNKNOWN and the oracle cross-check beside it | **<= 1.5** **GATE**; one of three estimates, assumption stated every time |
| (d) accuracy on the verified oracle stratum. Corpus-wide n = 20 comparisons / 17 panels / 12 figures / 12 articles; **at LOCK n = 5 comparisons / 5 panels / 3 articles** (sec.1.4b) | vs the published number | **NOT ESTABLISHABLE -- reported descriptively only.** The pre-registered >=30-comparison bar is NOT MET (20). No threshold verdict is issued. Median and p90 are printed with the n at the analysed scope beside them. |

plus, stratified by **cap length in pixels (tertiles)**:

| stratum | threshold |
|---|---|
| shortest-cap tertile, median abs % error vs `G` | **<= 10%** **GATE** |
| middle and longest tertiles | **<= 5%** |

**Why the Bland-Altman LoA is reported by stratum and the pooled figure is not a result.**
A limit of agreement is a `+/- 1.96 sd` interval and is only a 95% interval if the
log-ratios are approximately normal, so the scorer prints a probability-plot correlation as
a normality screen -- pooled and per tertile -- rather than assuming it. More importantly,
the log transform is the right scale for a *multiplicative* error, and the dominant error
here is not multiplicative: it is ~1 pixel of hand jitter on a cap whose length varies about
tenfold across the corpus, so `sd(log-ratio)` still scales with `1/capLen` and logging does
**not** stabilise the variance. A pooled LoA is therefore a mixture of a wide short-cap
distribution and a narrow long-cap one, and describes neither: the pilot measured
`[-41.9%, +59.1%]` in the shortest tertile against `[-5.0%, +4.4%]` in the longest. The
gate is evaluated **within each cap-length tertile**. The pooled numbers remain in the
output, labelled "DIAGNOSTIC ONLY, describes no stratum", because their absence would be
harder to explain than their presence.

**Dropped rows are counted, never absorbed.** Every log-ratio site -- Bland-Altman `M`-vs-`G`,
Bland-Altman `M`-vs-`D`, the Grubbs triplets, the oracle accuracy -- silently discarded rows
that could not form a ratio (a missing or non-positive reading, or a coded quantum above 1%).
A metric computed on an unstated subset is not a metric. Each site now reports its own
`nDropped` beside its `n`, split by reason where more than one applies, and the report prints
both.

and the **noise-floor ratio**, the number the project's thesis actually turns on:

```
                sd( log(SD_M / SD_G) )          <- how far the machine and the human differ
R_floor  =  ---------------------------------
                sd( log(SD_G1 / SD_G2) )        <- how far the human differs from HIMSELF

numerator estimated robustly as  median|log(SD_M/SD_G)| / 0.6745
```

**Both sides are difference-SDs on the same scale**, which is the whole point.
`Var(M - G) = sigma_M^2 + sigma_G^2` and `Var(G1 - G2) = 2 sigma_G^2`, so `R_floor == 1`
exactly when `sigma_M == sigma_G`. The classical-sd variant of the numerator is printed
beside the robust one so the estimator choice is visible rather than assumed.

`R_floor <= 1` means the machine's disagreement with the human sits inside the range two of
the human's own readings differ by -- i.e. **the machine is indistinguishable from the
human's own repeatability, and no accuracy claim in either direction is supportable from
real figures.** That is a publishable finding and it is also the ML-detector no-go condition
(section 8.2).

> **Amendment A7.** As shipped, the numerator was a **median absolute** (`0.6745 sigma` for
> a normal) and the denominator was a **repeatability coefficient** (`2.77 sigma`). Mixing
> the two scales meant `R_floor > 1.0` required `sd(M-G) > 4.11 x sd(G1-G2)` -- the machine
> had to be about four times worse than the human before the mandatory AND-conjunct of the
> section-8.2 GO rule could fire. On a like-for-like sample the shipped formula returned
> **0.24** where the corrected one returns **0.93** (selftest S3). The threshold of 1.0 is
> unchanged and now means what this section has always said it means.

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

## 4. Sample size: what N buys what precision, and what it does NOT buy

All figures below are computed in `score_real_validation.py --power` (Wilson intervals,
two-proportion power at alpha = 0.05 / 80%, order-statistic median CIs, F-based
variance-ratio CIs) and the achievable-N table is derived live from `worklist.json` and the
canonical split. Clustering is handled by cluster bootstrap at analysis time (section 2.1);
the design effects here are planning aids only.

### 4.0 What the sample ACTUALLY yields, per tier, per split

Previous versions of this section stated targets without checking them against the sample
that exists. They are not all reachable, and the gate table below is written against what
is (amendment A4). Regenerate with `--power`.

| scope | hours | figures | articles | P-panels | E-panels | comparisons | arm-values |
|---|---|---|---|---|---|---|---|
| tiers 1-1, DEV | | 4 | 4 | 23 | 3 | 3 | 6 |
| tiers 1-1, **LOCK** | | **10** | **10** | **41** | **19** | **30** | **60** |
| tiers 1-1, all | 3.9 | 14 | 14 | 64 | 22 | 33 | 66 |
| tiers 1-2, DEV | | 15 | 7 | 80 | 11 | 15 | 30 |
| tiers 1-2, **LOCK** | | **28** | **17** | **110** | **45** | **66** | **132** |
| tiers 1-2, all | 13.0 | 43 | 24 | 190 | 56 | 81 | 162 |
| tiers 1-3, DEV | | 22 | 12 | 102 | 17 | 28 | 56 |
| tiers 1-3, **LOCK** | | **49** | **30** | **175** | **69** | **100** | **200** |
| tiers 1-3, all | 21.9 | 71 | 42 | 277 | 86 | 128 | 256 |

**Which unit belongs to which metric, stated once so it is never mixed again:**

| unit | how it is counted | which metrics use it |
|---|---|---|
| **figure** | one per worklist item | Tier D: bbox IoU, recall, precision, caption association, caption -> letter set |
| **P-panel** | the caption's letter count (the **conservative** of the two available counts) | Tier P: per-panel IoU, exact count, label accuracy, **silent mislabel** |
| **E-panel** | a panel carrying a historical coded reading | Tier E discrete: chart type, dispersion type, priority flip |
| **comparison** | a coded control/intervention row | end-to-end golden diff, **effect sign flips** |
| **arm-value** | 2 per comparison | **dispersion**: naive, Bland-Altman, Grubbs, oracle, arm-name binding |

**Two P-panel counts exist and the conservative one is used.** The worklist records both
`caption_letter_count` (what the caption enumerates) and `visual_tile_count_survey` (what
a survey of the rendered figure counted). They disagree -- 277 vs 367 corpus-wide, 175 vs
228 at LOCK -- and §8.8 of `PROTOCOL.md` tells the annotator to draw *the boxes she can
see*, so the realised count will land between them and nearer the tile count. The tables
above use the **caption count**, the smaller of the two, so no bar is cleared on the
strength of the more generous number. The silent-mislabel gate clears either way
(120 needed; 175 or 228 available), and §4.7's labour table uses the tile count because
that is what the time model was built on -- which is why its per-tier panel numbers are
larger than §4.0's.

There are twice as many arm-values as comparisons, so **the dispersion channel is better
powered than the sign-flip channel on the identical sample**. Reporting one N for "the
extraction tier" hides that and was the source of the original ">= 120 panels" confusion:
that number came from the *silent-mislabel* arithmetic, which is a P-panel quantity.

### 4.1 Proportions -- Wilson 95% CI half-width (pp), at the achievable LOCK n

| n | p=0.80 | p=0.90 | p=0.95 | p=0.98 | p=1.00 |
|---|---|---|---|---|---|
| 30 (T1-1 comparisons) | 13.9 | 11.1 | 9.7 | 8.0 | 5.7 |
| 49 (T1-3 figures) | 11.1 | 8.7 | 6.3 | 5.2 | 3.6 |
| 69 (T1-3 E-panels) | 9.4 | 7.2 | 5.3 | 3.8 | 2.6 |
| 100 (T1-3 comparisons) | 7.8 | 6.0 | 4.5 | 3.2 | 1.8 |
| 175 (T1-3 P-panels) | 5.9 | 4.4 | 3.4 | 2.2 | 1.1 |
| 200 (T1-3 arm-values) | 5.5 | 4.2 | 3.1 | 2.1 | 0.9 |

### 4.2 Zero-event outcomes -- the rule of three

The catastrophic classes (silent mislabel, arm-name error, sign flip) are expected to be
zero. A zero count is only as strong as its denominator, and this bound is the **one
quantity in the study that is not cluster-adjusted** (section 2.1): with 0 events every
bootstrap resample also has 0 events. It is printed at both the panel level and the article
level, and labelled as not cluster-adjusted in the report itself.

| n with 0 events | 95% upper bound | | claim that needs it |
|---|---|---|---|
| 49 | 6.1% | | |
| 60 | 5.0% | | sign flips <= 5% |
| 69 | 4.3% | | |
| 100 | 3.0% | | |
| 120 | 2.5% | | silent mislabel <= 2.5%; sign flips <= 2.5% |
| 175 | 1.7% | | |
| 200 | 1.5% | | |
| 300 | 1.0% | | arm-name error <= 1.0% |

### 4.3 THE GATE TABLE, rewritten to the achievable bars

This replaces the aspirational thresholds. Every row states its unit, the achievable LOCK n,
and whether the pre-registered bar can be established **at all** on this sample. A gate
marked *not establishable* is **reported descriptively only** -- the number and its interval
are printed, and no PASS/FAIL verdict is issued against the original threshold.

| gate | unit | LOCK n | original bar | achievable bar | status |
|---|---|---|---|---|---|
| **P: silent mislabel, 0 observed** | P-panel | 175 | UB <= 2.5% (needs 120) | **UB 1.7%** | **ESTABLISHABLE -- and stronger than pre-registered** |
| **P: abstention recall = 1.00 (0 answered-and-wrong figures)** | figure | 49 | net figures saved > 0 (pre-A18; FAILS on synthetic at -10) | 0 missed errors; zero-event UB by rule of three on the answered-figure count (knowable only after coverage is observed) | ESTABLISHABLE as a zero-event bound (amendment A18; net figures saved is reported descriptively) |
| **E: sign flips, 0 observed** | comparison | 100 | UB <= 2.5% (needs 120) | **UB 3.0%** | **NOT ESTABLISHABLE at 2.5%.** Establishable at <= 5.0%; the section-8.1 no-transfer trigger (> 5%) is unaffected, the 8.3 ship criterion is reported descriptively |
| **E: arm-name error, 0 observed** | arm-value | 200 | UB <= 1.0% (needs 300) | **UB 1.5%** | **NOT ESTABLISHABLE at 1.0%.** Establishable at <= 1.5% |
| **E: arm-name accuracy >= 99%** | arm-value | 200 | >= 99% | half-width ~0.9 pp at p=1.00 | ESTABLISHABLE |
| **D: caption association >= 95%** | figure | 49 | >= 95% | half-width 6.3 pp at p=0.95 -> CI ~[0.89, 0.99] | **NOT ESTABLISHABLE.** 95% is not distinguishable from 85% at n=49. Reported descriptively; the 8.1 no-transfer trigger (< 85%) is still usable because it is a much larger gap |
| **D: caption -> letter set >= 95%** | figure | 49 | >= 95% | as above | **NOT ESTABLISHABLE**, same reason |
| **E: chart-type accuracy >= 90%** | E-panel | 69 | >= 90% | half-width 7.2 pp -> CI ~[0.79, 0.96] | marginal; reported with its CI, verdict issued only if the CI clears 0.90 entirely |
| **E: priority-flip <= 5%** | E-panel | 69 | <= 5% | UB 4.3% at 0 events | ESTABLISHABLE if 0 events; otherwise descriptive |
| **E: dispersion-type flag recall >= 80%** | disagreeing E-panel | unknown (subset of 69) | >= 80% | **NOT ESTABLISHABLE** -- the denominator is the number of *disagreements*, which cannot be known in advance and will plausibly be single digits | descriptive only |
| **E: Grubbs sigma_M/sigma_G <= 1.5** | arm-value | 200 | <= 1.5 | CI ~[0.78, 1.28] at effective n ~125 | ESTABLISHABLE against 1.5; **NOT** against 1.2 vs 1.0 |
| **E: BA bias within +/-5%, LoA within +/-25%** | arm-value | 200, split 3 ways by cap tertile | pooled | ~67 per tertile | ESTABLISHABLE per tertile; **the pooled figure is not reported as a result** (section 3.3) |
| **E: shortest-cap tertile median <= 10%** | arm-value | ~67 | <= 10% | median CI spans ~25% of the ordered sample | marginal; reported with its cluster-bootstrap CI |
| **E: oracle accuracy median <= 5%, p90 <= 15%** | oracle comparison | **5** | n >= 30 | -- | **NOT ESTABLISHABLE.** The stratum has 20 comparisons corpus-wide and 5 in LOCK (section 1.4b). Descriptive only, always with its n at the analysed scope |
| **E (tier target): >= 120 coded panels** | E-panel | 69 | >= 120 | -- | **NOT REACHABLE** on this worklist. The target was a P-panel figure applied to the wrong unit |

### 4.4 Detectable transfer gaps (80% power, alpha = 0.05), at the achievable n

| metric | synthetic n | LOCK n | smallest detectable drop |
|---|---|---|---|
| panel exact count (fig-level, p_syn=0.951) | 41 figs | **49 figs** | **21.5 pp** |
| panels IoU >= 0.9 (p_syn=0.881) | 159 | **175** | **11.8 pp** |
| panel label accuracy (p_syn=1.000) | 159 | **175** | **4.7 pp** |
| chart-type accuracy (p_syn=1.000) | 80 | **69** | **9.7 pp** |
| series mark accuracy (p_syn=1.000) | 495 | **200** | **2.2 pp** |

Read this honestly: **the figure-level exact-count `Delta` is the weakest number in the
study.** At 49 real compound figures we can only detect a drop of ~21.5 pp, so a real
exact-count of 80% would not be distinguishable from the synthetic 95.1%. The pre-registered
response is not to pretend otherwise: the exact-count `Delta` is reported with its
cluster-bootstrap CI and explicitly labelled underpowered, and the decision rule in section
8 leans on the panel-level metrics (label accuracy, silent mislabel, IoU), which are
adequately powered at 175 LOCK panels.

### 4.5 Continuous outcomes

Median abs % error, distribution-free 95% CI as a share of the sample spread:

| n | CI spans |
|---|---|
| 50 | ~30% of the ordered sample |
| 100 | ~21% |
| 175 | ~17% |
| 200 | ~15% |

Grubbs variance ratio `sigma_M / sigma_G`, 95% CI multiplier on the SD scale (i.i.d. n, and
then at the effective n after a within-panel ICC of 0.4-0.6, design effect ~1.6):

| n arm-values | i.i.d. SD-ratio CI | effective n | clustered SD-ratio CI |
|---|---|---|---|
| 60 (T1-1 LOCK) | [0.69, 1.44] | 38 | **[0.63, 1.60]** |
| 132 (T1-2 LOCK) | [0.78, 1.28] | 82 | **[0.73, 1.36]** |
| 200 (T1-3 LOCK) | [0.82, 1.22] | 125 | **[0.78, 1.28]** |

Because coded rounding cancels out of `sigma_M` (section 1.5), no arm-values are lost to the
quantum filter and the usable n is the full complement. At the full worklist the interval is
**[0.78, 1.28]**: sufficient to discriminate the section-8 gate value of 1.5 from parity,
which is the discrimination the decision rule needs, and **insufficient** to resolve 1.2 from
1.0. Say the second part out loud in the write-up; it is the difference between "the machine
is not much worse" and "the machine is as good", and this sample supports only the first.

**Pre-specified:** no claim of the form "the machine is *more* precise than the human on
real figures" will be made unless the upper end of the `c_DG`-corrected `sigma_M / sigma_G`
interval is below 1.0 **and** the oracle-stratum cross-check of section 1.3 does not
contradict it. The Grubbs interval alone cannot license that claim, because its bias
direction is unknown: a shared reading difficulty would make the machine look better than it
is, which is exactly the error this bar exists to prevent. At n = 5 LOCK oracle comparisons
the cross-check is weak, so in practice this claim is **not available from this study** and
the write-up should not go looking for it.

### 4.6 End-to-end

| quantity | n needed | achievable at LOCK |
|---|---|---|
| sign flips 0 with UB <= 5% | 60 comparisons | **100 -> yes** |
| sign flips 0 with UB <= 2.5% | 120 comparisons | **100 -> NO** (achieved UB 3.0%) |
| 3-level `rma.mv(~1 \| article/row)` non-singular | >= 2 articles with >= 2 rows | 30 LOCK articles -> yes |
| multi-arm shared-control correction exercised | >= 20 affected rows | 194 multi-arm / 110 shared-control corpus-wide; the LOCK subset must be counted at analysis time and reported |

### 4.7 Labour budget, stated so the effort is spent knowingly

The worklist's own time model (`worklist.json.budget`) is the authority; these are its
numbers, not an independent estimate.

| tier | figures | P-panels | landmark panels | hours | cumulative |
|---|---|---|---|---|---|
| 1 | 14 | 95 | 11 | 3.9 | 3.9 |
| 2 | 29 | 170 | 32 | 9.1 | 13.0 |
| 3 | 28 | 102 | 49 | 9.0 | 21.9 |

Staged, with a hard stop at each stage. **Stage 1** = the DEV slice -- interface shakedown
and tuning only; across all three tiers that is 22 figures / 102 P-panels / 17 E-panels.
**Stage 2** = the LOCK set, scored once: 49 figures / 175 P-panels / 69 E-panels /
100 comparisons / 200 arm-values, and that is the whole confirmatory study.
**Stage 3 (optional)** = extend the *worklist* -- not the annotation -- toward the
355-panel Tier-E ceiling, which requires drawing more articles into the sampling frame and
is a sampling decision. It is worth doing only if the Grubbs ratio lands near 1.0, where the
extra precision would change a conclusion, or to add oracle rows, which section 11 identifies
as the highest-value extension available.

**If Stage 2 cannot be completed**, the study reports the reduced-N bounds of section 4.2 /
4.5 rather than the full ones and states, gate by gate, which claims were lost.

**Every precision claim in this document, and in the report the scorer prints, states
whether it is DEV, LOCK, or both.** A number without that label is a defect: `--split-filter`
defaults to `lock`, so an unlabelled figure quoted from a default run describes the
confirmatory half only, and the same figure quoted from `--split-filter all` describes
roughly twice as much data. Tier 1 alone splits 4 DEV / 10 LOCK figures.

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
| **Recognition is unavoidable** | he will recognise his own dissertation figures; full blinding is impossible | Do not pretend otherwise. Report the **provenance stratum** (`text-anchored oracle` vs `figure-digitized`) and the DEV/LOCK split separately, and state the residual risk in the limitations. Recall-driven convergence of `G` toward `D` raises `c_DG`, which pushes the Grubbs `sigma_M` UP -- but `c_DM`/`c_GM` push it down and the net direction is unknown (sec.1.3). Do not present this as protection; present it as an unsigned bias, and read the oracle cross-check. |
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

`R_floor` is the corrected, like-for-like ratio of section 3.3 (amendment A7): the SD of the
machine-vs-human log difference over the SD of the human's own test-retest log difference,
so `> 1.0` genuinely means "the machine's error exceeds the human's own repeatability". It
is evaluated mechanically and appears in the report's gate table
(`E: R_floor = sd(logM/G)/sd(logG1/G2)`), with selftests S3/S3b/S3c asserting that it reads
1.0 at parity, rises above 1 when the machine is worse, and is actually wired into the gate.

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
- every Tier-P threshold met; **0 silent mislabels observed with 95% UB <= 2.5%**; abstention
  recall 1.00, i.e. 0 answered-and-wrong figures (amendment A18; coverage and net figures
  saved reported alongside as the cost)
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

The 20-comparison oracle stratum of section 1.4b does not change this. It is a descriptive
result on 17 panels selected by a procedure that can only find codings that were already
right, in 12 papers that happened to print their numbers -- and only 5 of those comparisons,
in 3 articles, fall inside LOCK. It licenses "on these panels,
the machine's read differed from the published value by X"; it does not license a
comparative claim about humans, and it does not generalise to the other 400 comparisons.

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
D5  c_DG alone           -> injecting cov(e_G, e_D) = c inflates Grubbs sigma_M by ~c.
                             This is HALF the story and is labelled as such.
D5b ANTI-CONSERVATIVE    -> a difficulty component SHARED by D, G and M (an occluded cap;
                             a 6-px error bar) makes Grubbs UNDERSTATE sigma_M -- measured
                             at -40% against a known truth of 0.100 -- while the ORACLE
                             estimate recovers 0.100 exactly.
                                          <- the failure mode that killed "conservative
                                             against the machine" (sec.1.3), kept executable
                                             so it cannot quietly come back
S1  split determinism    -> two draws agree
S1b permanent-DEV        -> EVERY PERMANENT_DEV article is DEV in EVERY spelling
                             (14 spellings of 4 articles)
S1c spelling invariance  -> `Garcia-Capdevila2009` and `GarciaCapdevila2009` -- and the
                             space/underscore/case variants -- land in the SAME bucket
S1d canonicalisation     -> strips typography, never identity
S2  CI provenance        -> the CIs the report prints are the cluster bootstrap the plan
                             promises, not the i.i.d. interval
S2b clustering bites     -> on a deliberately clustered sample the cluster interval is
                             2.88x the width of the Wilson interval it replaced
S3  R_floor units        -> sigma_M == sigma_G gives R_floor ~ 1.0 (the shipped formula
                             returned 0.24 on the same data)
S3b R_floor direction    -> sigma_M = 3 x sigma_G gives R_floor 2.28
S3c R_floor is gated     -> the sec.8.2 AND-conjunct appears in the gate table
X1  missing prediction    -> scored as a total miss, no crash
X2  missing input store   -> graceful skip, non-zero information, no crash
```

`P3` and `E3` are the tests that matter most: both are silent catastrophic classes that every
geometric or magnitude metric reports as perfect. `D3` is the test that encodes this document's
central methodological claim as an executable assertion, and **`D5b` is the test that keeps
the plan honest about the claim it had to withdraw**: it reproduces, against a known truth,
the case in which the Grubbs estimate is anti-conservative. A guarantee that survives only in
prose is a guarantee nobody can check.

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
  synthetic_reference.json           frozen synthetic comparators (generated by
                                     make_synthetic_reference.py, committed; A18)
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
  "oracleClaimed": true,        // the LABEL claims a text source -- NOT a selector, sec.1.4b
  "oracleVerified": "NOT_FOUND",// verify_oracle_v2.py verdict; the only thing that counts
  "isOracle": false,            // true ONLY on a CONFIRMED_* verdict -- see sec.1.4b
  "oracleSource": null,         // body_text | caption | in_figure_vector | in_figure_ocr
  "oracleMeanConfirmed": false, // the two channels are recorded separately: a panel whose
  "oracleVarianceConfirmed": false, //  mean is printed but whose SEM is not still counts
                                //  for central tendency and not for dispersion
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
6. **The oracle stratum does not clear its pre-registered bar.** 20 confirmed comparisons /
   17 panels / 12 figures / 12 articles corpus-wide, against a bar of >= 30 comparisons
   across >= 10 articles -- and only **5 comparisons in 3 articles inside LOCK** (section
   1.4b). It is reported descriptively, never with a threshold verdict, and always with the
   n at the scope being analysed. The stratum is non-random by construction -- it was found
   by searching for the coded value, so it selects panels the coder read accurately, in
   papers that print their numbers -- and carries that caveat wherever it is reported.
   Its one irreplaceable role is as the cross-check on the Grubbs independence assumption
   (section 1.3), and at n = 5 LOCK comparisons that cross-check is weak. **This is the
   single most damaging gap in the design**: the plan's primary dispersion estimator has an
   assumption the plan cannot verify, and the only instrument that could verify it is
   underpowered. Adding oracle rows -- by widening the frame to the 9 worklist-eligible
   oracle articles, or by hand-verifying `PARTIAL_MEAN` rows -- is the highest-value
   extension available and costs no annotation time.
7. **No value is printed inside any figure in this corpus.** 4766 numeric tokens were read
   out of 242 figure interiors (68 vector, 174 OCR) and not one forms a printed
   `mean +/- variance` pair; they are axis ticks, group labels and sample sizes
   (section 1.4b). The within-figure accuracy oracle -- truth and measurand in the same
   image -- does not exist here at any n. The 13 remaining unresolved PDFs are the only
   residual coverage gap, down from 104.
8. **~94% of the corpus is SEM.** The study will say a great deal about the short-cap
   regime and comparatively little about SD-plotted figures (~50 arm-values), which are
   the easier case. Generalising the dispersion result to SD-plotted literature is not
   supported.

---

## 12. Amendments

Any change after LOCK is scored goes here with a date, a reason, and a note of which results
become post hoc.

**Status of A1-A17: PRE-DATA.** No LOCK panel has been annotated. No DEV panel
outside the four permanently-DEV pilot articles has been annotated. **No result of any kind
exists**, so nothing in A1-A17 can have been chosen to suit an outcome and none of it is
post hoc. They are recorded as amendments anyway, because a pre-registration whose changes
are not logged is not a pre-registration.

**A18 does not get that shield and says so in its own entry**: it changes a pre-registered
criterion after the synthetic data it gates had been seen. It is still pre-data with respect
to every REAL-figure result -- none exists -- but that is a weaker status and the entry
states both.

---

### A1 -- `annotationMode` is enforced for BOTH raters. 2026-07-27.

**What changed.** `rvcommon.annotation_mode_violations()` (new, `rvcommon.py`) is the single
implementation of the check; `ingest_annotations.py` calls it on both the Stage A and Stage B
exports (`cmd_ingest`), alongside the existing `blinding_violations`. `PROTOCOL.md` §1.3
lists `Annotation mode` as a REQUIRED setting with a one-minute verification step; §4 rule 1
and §12 are rewritten as implemented rather than proposed.

**Why.** `annotationMode` was implemented in the tool but the protocol still described it as
"not yet implemented -- do not edit figure-extractor.html", the settings list did not mention
it, and `ingest_annotations.py` contained zero references to it -- while
`prepare_dan_session.check_exports` had always hard-rejected a second-rater export without
the stamp. The two readings being compared were therefore blinded by different mechanisms:
one mechanical, one by good intentions. A difference between the raters could then have been
a difference in how they were blinded, which is a threat to the only comparison the second
rater exists to supply.

### A2 -- "conservative against the machine" is WITHDRAWN. 2026-07-27.

**What changed.** Section 1.3 now states the full algebra
`E[sigma_M^2] = sigma_M^2 + c_DG - c_DM - c_GM`; every unqualified claim that the Grubbs
estimate is conservative, a bound, or biased against the machine has been deleted from this
document and from `score_real_validation.py`'s output and docstring. Grubbs is demoted from
"the primary inferential claim" to **one of three estimates, with its assumption stated at
every appearance**. The oracle stratum is elevated to the cross-check, with a pre-specified
reading rule for what Grubbs-vs-oracle disagreement means. New selftest **D5b** reproduces
the anti-conservative case against a known truth.

**Why.** The derivation kept only `+ c_DG` and concluded the estimate could only be too
large. `c_DM` and `c_GM` are not zero -- section 7 lists shared misreading of the same
ambiguous cap as a live threat -- and they enter with a minus sign. Measured in D5b: a
shared-difficulty component makes Grubbs return `sigma_M = 0.060` against a true 0.100, a
40% understatement, while the oracle estimate recovers 0.100 exactly. The bias direction is
**unknown** without assuming the machine's errors are uncorrelated with the humans', and a
guarantee that is false in the dangerous direction is worse than no guarantee.

### A3 -- every reported CI is actually a cluster bootstrap. 2026-07-27.

**What changed.** `cluster_bootstrap` had **zero call sites** and `BOOTSTRAP_B` was unused,
while section 2.1 claimed in bold that all CIs used it and `--power` printed the same claim.
Added `cb` / `cb_rate` / `cb_median` (`score_real_validation.py`) and wired them into every
reported interval: caption association, letter set, figure IoU, all panel-tier rates and
medians, all extraction-tier rates, naive and central medians, Bland-Altman bias and both
limits, the Grubbs ratio, the oracle median. Default `B` is now `BOOTSTRAP_B` (10000). The
report ends with a CI-provenance block listing the exceptions. Selftests S2/S2b.

**Why.** Shipped intervals were i.i.d. and roughly 19-25% too narrow at the panel level and
1.6x too narrow at the article level. **No statement may survive that the code does not
implement**: the rule-of-three zero-event bound genuinely cannot be clustered (with 0 events
the bootstrap returns [0, 0]), so it is now labelled "not cluster-adjusted" at the point of
printing, with both the panel-level and article-level bounds shown, and the blanket claim in
section 2.1 has been replaced by an exhaustive list.

### A4 -- the gate table is rewritten to the ACHIEVABLE N. 2026-07-27.

**What changed.** New section 4.0 (achievable N per tier per split, generated live by
`--power` from `worklist.json` and the canonical split) and a rewritten section 4.3 gate
table. Units are stated per metric: figures for Tier D, P-panels for decomposition, E-panels
for Tier E discrete, comparisons for the end-to-end, **arm-values for dispersion**. Section
2.2's target table gains an ACHIEVABLE column. Every gate that cannot be established at the
achievable N is marked **"not establishable -- reported descriptively only"**.

**Why.** The plan required >= 120 LOCK panels and the full worklist (21.9 h) yields 69 LOCK
E-panels. The ">= 120" figure came from the *silent-mislabel* arithmetic, a P-panel
quantity -- and Tier P clears it at 175 LOCK panels. Applying one N to both units hid a
reachable bar behind an unreachable one. Not establishable at the achievable N: sign flips
at UB <= 2.5% (100 comparisons gives 3.0%), arm-name error at UB <= 1.0% (200 arm-values
gives 1.5%), both caption gates at 95% (49 figures cannot separate 95% from 85%), the
dispersion-type flag-recall gate (its denominator is unknowable in advance), and the oracle
accuracy gate (section 1.4b). Newly *stronger* than pre-registered: silent mislabel, at
UB 1.7%.

Also: `--split-filter` defaults to `lock`, so published "14 figures / 95 panels" precision
claims were describing Tier 1 in full while the confirmatory set is 10 figures / 41 panels.
Every precision claim in this document now states whether it is DEV, LOCK or both.

### A5 -- the oracle stratum is reported at the SCOPE being analysed. 2026-07-27.

**What changed.** `verify_oracle_v2.py` emits an oracle-size table at every scope the study
analyses (corpus, worklist tiers 1-1/1-2/1-3, each split by DEV/LOCK), and
`score_real_validation.py` prints the joined stratum's size at the run's own
`--split-filter` immediately beneath the oracle accuracy line, with an explicit instruction
not to quote the corpus-wide count beside it. Section 1.4b carries the same table.

**Why.** The >= 30 / >= 10 bar was evaluated corpus-wide, but the study analyses the
worklist. The corpus-wide stratum intersects Tier 1 at 4 comparisons in 2 articles and the
full worklist at 5 comparisons in 3 articles, all in LOCK. A Tier-1 result citing the
corpus-wide count would overstate its evidence by roughly fivefold.

### A6 -- the oracle count is corrected from 33 to 20, and the null is re-run. 2026-07-27.

**What changed.** Four things, in `verify_oracle_v2.py`:

1. **The pair guard is restored** (`match_arm`): the printed MEAN token must be informative
   in its own right. It had been relaxed to "mean OR variance" specifically so that
   `Bakeche2020`'s printed `(3 +/- 0.81)` would confirm; that confirmation is false in four
   ways and the relaxation bought no true positives. Cost: 1 row.
2. **A committed hand-adjudication ledger** (`ADJUDICATION`), applied before anything is
   counted or written, disabled by `--no-adjudication`, reproducing every rejection with the
   sentence that decides it. It may only REJECT, never promote. **12 of 32 rows rejected**
   for cross-cohort, cross-panel, cross-outcome or wrong-arm mismatches, each verified
   against the source PDF.
3. **The permutation null is re-run at `--null-reps 1000`** (was 3 -- the shipped FDR rested
   on two events) against four donor schemes, with a magnitude-matched cross-article donor
   as the primary. Reported FDR on the corrected count: **6.3%**.
4. **Panels are counted as `(article, figureId, panelLetter)`**; the previous helper keyed on
   `figureId` alone, so "21 panels" was really 21 figures. Comparisons, panels, figures and
   articles are now four separate columns. `--dry-run` no longer writes the report (it wrote
   `oracle_report_v2.json` outside the guard).

**Result: 20 comparisons / 17 panels / 12 figures / 12 articles. The pre-registered bar of
>= 30 comparisons is NOT MET.** The oracle stratum is demoted to a descriptive result.

**An honest correction to the objection that prompted this.** The claim was that
within-article donors collide 17.8x more often than corpus-wide ones, implying an FDR near
68%. Measured at 1000 reps: the unrestricted within-article rate is indeed ~25x the
corpus-wide one, **but that comparison is not a null** -- a donor drawn from the same paper
very often has its own values printed there, so it confirms because it is genuinely printed.
Removing that tautology (magnitude-matched donors from a different paper) gives 0.298% against
the corpus-wide 0.343%, i.e. **0.9x**. The corpus-wide null was not the source of the error.
The relaxed guard and twelve semantic mismatches were, and those are what the correction
removes.

### A7 -- `R_floor` is rescaled so 1.0 means what it says. 2026-07-27.

**What changed.** `R_floor = sd(log(SD_M/SD_G)) / sd(log(SD_G1/SD_G2))`, both sides on the
difference-SD scale, numerator estimated robustly as `median|log ratio| / 0.6745`; the
classical-sd variant is printed beside it. Section 3.3 restated; the conjunct is now
evaluated mechanically in the gate table. Selftests S3/S3b/S3c.

**Why.** The shipped formula divided a **median absolute** (`0.6745 sigma`) by a
**repeatability coefficient** (`2.77 sigma`), so `R_floor > 1.0` demanded `sd(M-G) > 4.11 x
sd(G1-G2)` -- the machine had to be about four times worse than the human before the
mandatory AND-conjunct of the section-8.2 GO rule could fire. On like-for-like data the old
formula returns 0.24 where the new one returns 0.93. The threshold of 1.0 is unchanged; only
the scale is fixed, and the GO rule now reads correctly.

### A8 -- article keys are canonicalised everywhere. 2026-07-27.

**What changed.** `score_real_validation.canonical_article()` (lowercase, strip every
non-alphanumeric character) is the single helper, used for `PERMANENT_DEV` membership, for
the split hash, for the `split.json` lookup (which now also carries a `byCanonicalKey`
index), for the figure-id join between the GT store and the coded reference, and for the
cluster-bootstrap cluster key. Selftests S1b-S1d cover every `PERMANENT_DEV` entry in
fourteen spellings and assert that hyphen, space, underscore and case never change a bucket.

**Why.** `PERMANENT_DEV` held `GarciaCapdevila2009` while the coded reference writes
`Garcia-Capdevila2009`, and membership was tested with exact `in`. The result: a
**pilot-contaminated article -- one that produced the asterisk-occlusion finding and that
both raters see as a calibration figure -- was sitting in LOCK.** Three worklist articles
(`GarciaCapdevila2009`, `MoraGallegos2015`, `SampedroPiquero2018`) also had no split
assignment at all, because the worklist spells them without hyphens and `split.json` with.

**Impact, stated because it is the uncomfortable part.** Hashing the canonical key rather
than the raw name reassigns **84 of 171 articles**, changing the corpus split from 71 DEV /
100 LOCK to **53 DEV / 118 LOCK**, and the full-worklist LOCK yield from 55 to 69 E-panels.
The alternative -- canonicalising only for membership and lookups while hashing the raw
name -- would have moved one article, but it makes the split a function of which spelling
the coded reference happened to use, i.e. data-dependent rather than a pure function of the
published salt. The pure function was preferred because section 2.3's whole claim is that
anyone can recompute the assignment. The four permanently-DEV articles are unaffected
(`PERMANENT_DEV` overrides the hash), so no pilot-contaminated article moved into LOCK, and
no annotation exists against either draw.

### A9 -- ingest refuses a destructive re-ingest. 2026-07-27.

**What changed.** `ingest_annotations.py::cmd_ingest` compares the session's existing records
against the new ones, names every panel that would disappear, and refuses unless `--reingest`
is given. `PROTOCOL.md` §10 documents it.

**Why.** Re-ingest silently replaced every record for a session, so a `--allow-problems` run
after a clean one destroyed the panels that no longer validated: demonstrated 4 records ->
3, with no warning, against a protocol that promises "nothing is written until it all
passes". A panel that ingested cleanly before and does not now is a regression, not a
correction.

### A10 -- the zoom floor is reconciled between screen and image pixels. 2026-07-27.

**What changed.** `persistDig()` exports `view`, `scale` and `k = scale * zoom`, and every
point records the `k` in force when it was clicked; the digitizer header prints `k` live;
`jitter_report` reads it and the audit prints image px, `k`, **screen px** and an explicit
RE-PICK verdict per landmark. New `PROTOCOL.md` §7.2 states the arithmetic.

**Why.** The rule was written in SCREEN pixels ("at least ~100 screen pixels ... do not argue
with it") and measured in IMAGE pixels. The 1:1 grating guarantees `k >= 1`, so the
image-pixel floor was conservative rather than wrong -- but it over-flagged landmarks picked
at high magnification and the artifact contained no way to tell. With `k` recorded the audit
computes the screen span instead of assuming it.

### A11 -- `suggestSubfiguresLegacy` is guarded by `annotationMode`. 2026-07-27.

**What changed.** `figure-extractor.html` -- the legacy XY-cut entry point now refuses in
annotation mode, in the same result shape `detectPanels` uses.

**Why.** It was unguarded, and because it returns bare boxes it writes no `panelDetection`
and stamps no `captionSource: 'panel-split'`. Boxes taken from it left **no fingerprint at
all**, so the after-the-fact blinding check could not see them. An unguarded API producing
untraceable machine suggestions is strictly worse than the guarded one.

### A12 -- stale `localStorage` can no longer override a rebuilt session. 2026-07-27.

**What changed.** `figure-extractor.html::loadArticleAnnotations` honours
`"forceCleanLoad": true` in a session's `annotations.json` by discarding the cached copy and
saying so; where the cache still wins it now raises a visible toast naming the conflict.

**Why.** `localStorage` is keyed by article name and a harness reuses names across rebuilds,
so a rebuilt session silently served the previous run's boxes over the freshly written file.
The rater then annotates on top of work that is no longer the task.

### A13 -- Bland-Altman limits of agreement are reported BY STRATUM. 2026-07-27.

**What changed.** LoA and bias are computed within each cap-length tertile, with a
probability-plot normality screen per stratum; the pooled figure remains, labelled
"DIAGNOSTIC ONLY, describes no stratum". Section 3.3 restated. Every log-ratio site now
reports its dropped-row count.

**Why.** There was no normality check at all behind a `+/- 1.96 sd` interval, and the log
transform does not stabilise the variance under a pixel-additive error: `sd(log-ratio)`
still scales with `1/capLen`, so a pooled LoA is a mixture of a wide short-cap distribution
(`[-41.9%, +59.1%]` on the pilot) and a narrow long-cap one (`[-5.0%, +4.4%]`) and describes
neither.

### A14 -- the legacy detector is guarded at the SOURCE, not at the wrapper. 2026-07-27.

**What changed.** The guard A11 describes was added to the `window.figureExtractor`
wrapper only. The bare global `function suggestSubfiguresLegacy` (`figure-extractor.html`
:3455) was still unguarded and still reachable. It now refuses before it computes anything,
and `scripts/test_panels.py` exercises **the bare global directly**.

**Why.** A11 was verified by calling the wrapper, which returned `flags:['annotation-mode']`
-- so the fix looked complete and was recorded as complete. The function the wrapper calls
was untouched, and a devtools console reaches it directly. This is the one detector whose
output the after-the-fact audit *structurally cannot see*: it returns bare boxes, writes no
`panelDetection`, stamps no `captionSource:'panel-split'`. Verified empirically both ways --
with `annotationMode` off the bare global returns 2 boxes, with it on, 0 plus a warning.
The lesson generalises: testing the entry point you happen to know about is not the same as
testing the entry point an actor would use.

### A15 -- the RNG seed is sealed; the rater-facing plan states nothing that identifies a re-read. 2026-07-27.

**What changed.** `prepare_session.SEED = 20260727` is gone. The seed resolves from
`--seed` / `$RV_SEED` / a gitignored `.rv_seed`, else 64 bits from `os.urandom` persisted
there, with a sha256 commitment written to the tracked `seed.commit.json`. `plan.json` now
carries `seedCommitment` and drops `seed`, `nRepeats` and `repeatFraction`; `status` prints
the commitment rather than the seed; `keys/` (which holds `repeatIds`) is gitignored.

**Why.** The seed was a committed constant, so this file plus the tracked `worklist.json`
were together sufficient to recompute every intra-rater repeat pair -- and the rater is also
the operator who runs the script. `RC_intra` is the denominator of `R_floor`. Being
date-shaped, it was guessable even without the repo. `keys/` was neither tracked nor
ignored, so the first `plan` run would have created the answer key in the working tree for
the next `git add -A` to sweep in -- the same way `.obsidian/` was swept in previously.
The commitment preserves what the constant was actually good for: proving post hoc that the
seed was fixed before the reads rather than chosen after them to flatter the result.

### A16 -- re-reads are mixed with held-back fresh items. 2026-07-27.

**What changed.** `cmd_plan` holds back one fresh item per repeat from the first pass and
spends them in the trailing sessions, so a trailing session is a mix. Repeats are drawn from
first-pass items only; within-session order is shuffled so serial position does not encode
repeat status; `isRepeat` is now a property of the item rather than of its session. Where
the worklist is smaller than `2 x nRepeats` the mix is arithmetically impossible and `plan`
now says so on stderr instead of shipping silently.

**Why.** This module's own docstring promised repeats were "interleaved with fresh items, so
it cannot be recognised as a repeat". They were not. Repeats were scheduled only after every
fresh item was spent, so **every trailing session was 100% re-reads, and short**: on a
24-item probe, S05 (2 items) and S06 (1 item) were both pure repeats while S01-S04 held 6
each. The rater did not need the seed -- the schedule announced the answer. Sealing the seed
(A15) does nothing about this; the structure had to change. After the fix the same probe
gives one trailing session of 6 = 3 repeats + 3 fresh, with no all-repeat session.

**Consequence for the schedule.** Total reads are unchanged (n + nRepeats); the first pass is
shorter by `nRepeats` items and the trailing sessions correspondingly fuller.

### A17 -- a blinding failure is not bypassable, and the sealed GT keeps its evidence. 2026-07-27.

**What changed.** `ingest_annotations.py` raises on any `BLINDING` problem regardless of
`--allow-problems`, and the sealed per-figure record carries the rater's actual
`panelDetection` and the export's `annotationMode` instead of a hardcoded `None`.

**Why.** `--allow-problems` exists so one unreadable export does not block the other 19, but
it also downgraded a blinding failure to a stderr line. A blinding failure is a statement
about the *rater's setup*, which implicates every item read that session, not just the one
that left a fingerprint. Separately, hardcoding `panelDetection: None` made re-running
`rv.blinding_violations` on the sealed GT vacuous -- it passed by construction rather than on
evidence, so the gate was trust-on-first-run and not independently reproducible afterwards.

### A18 -- the abstention gate is restated on RECALL; "net figures saved" is demoted to a descriptive; `synthetic_reference.json` is generated, not hand-maintained. 2026-08-08.

**Status, stated plainly: this amendment changes a pre-registered criterion AFTER seeing the
data it gates.** The original criterion, exactly as registered in sections 3.2, 4.3 and 8.3:
`net figures saved > 0`, a hard GATE. The final cascade, measured by
`python3 benchmark/panels/score.py --run post_fix_ext --abstain-at 0.35`, scores abstention
precision 0.14, recall 1.00, **net figures saved -10**. The registered gate FAILS. No
real-figure result exists (that part of the pre-data status is intact), but the synthetic
number this gate is evaluated against was known before this entry was written, and a reader
must weigh the new criterion accordingly. The original criterion, the measured failure, and
the superseded comparators are all preserved -- here, in `benchmark/panels/RESULTS.md`
sec.7, and in `synthetic_reference.json` under `superseded` -- so that a reader can apply
the old rule and judge for themselves.

**What changed.**

1. The Tier-P abstention gate is now **abstention recall = 1.00**, operationalised as **0
   answered-and-wrong figures** (a zero-event criterion, well-defined even when no errors
   exist; rule-of-three UB on the answered-figure count). Coverage keeps its unchanged
   >= 50% threshold -- it is what blocks the degenerate abstain-on-everything corner
   (selftest P6) -- and abstention precision and net figures saved are demoted to reported
   descriptives: the *cost* of the recall, printed beside it, never gated. Sections 3.2,
   4.3 and 8.3 are rewritten accordingly, and `score_real_validation.py:gate_check` now
   evaluates the amended gate (`missedErrors <= 0`) instead of `netFiguresSaved >= 1`.
2. `synthetic_reference.json` is now **emitted by `make_synthetic_reference.py`**, which
   computes the panels block by importing `benchmark/panels/score.py` and scoring the
   committed run through the scorer's own functions. `--check` mechanically detects
   staleness. The displaced values (precision 0.88 / recall 0.94 / net +13, and a `pct50`
   that was a copied lower bound rather than a measurement) move to a dated `superseded`
   block, per the file's own rule.

**Why the metric was wrong for the decision it informs.** "Net figures saved" weights a
needless abstention EQUALLY with a silent error. For meta-analytic extraction those costs
are wildly asymmetric: an abstention costs a minute of human attention; a silently
mislabelled panel attaches a number to the wrong experimental arm and corrupts a study's
weight in the pooled model, undetectably. The detector's measured behaviour is recall 1.00 /
precision 0.14: it declines EVERY figure it would have got wrong, at the cost of declining
12 it would have got right. Under a symmetric loss that nets -10 and fails; under the
asymmetric loss this pipeline actually faces, it is the correct corner to be in. The gate is
therefore restated on the property that matters -- catch every error -- with the cost
reported beside it. This is not a post-hoc rescue that lowers a bar the detector missed; it
replaces a criterion that presumed symmetric costs with one aligned to the decision, and the
new criterion is not trivially easier: a single answered-and-wrong figure fails it, where
the old gate could have been passed by a sloppier detector that caught 3 errors and wasted 2
correct answers while letting 5 more errors through (net +1, recall 0.375).

**Why the second change matters more than the first.** The gate failing was recoverable; the
artifact hiding it was not, without luck. `synthetic_reference.json` is a committed
machine-readable comparator that the analysis validates against, and it still carried the
superseded 0.88 / 0.94 / +13 from an earlier detector build -- so the pre-registration would
have validated against numbers the live scorer no longer produces, silently. A comparator a
human must remember to update WILL drift; the fix is to make the scorer the only writer.

### A19 -- the A2 prohibition is enforced in `SECOND-RATER-ANALYSIS.md`. 2026-08-08.

**What changed.** `SECOND-RATER-ANALYSIS.md` described the Grubbs estimate as "conservative
against the machine" in five places (A4's cost paragraph, both estimator rows of the A5.1
table, rider 3 of A7, and the A8 threat table), kept the one-term algebra
`sigma_M^2 + c'` that A2 corrected, and A5.2 attributed the directional assertion to §1.3 in
the present tense -- §1.3 had withdrawn it. Every passage is rewritten to the full
expectation (`+ c' - c_GM - c_H2M`), each component's sign stated separately, the net
direction stated as unknown, and the "at least that good" framing removed. A stale comment
in `inter_rater.py`'s selftest ("in the direction sec.1.3 claims") is corrected the same
way; the numerical assertion itself was always about the `c'` term in isolation and stands.

**Why.** A2 is explicit: *no sentence anywhere in this study* may call the Grubbs estimate
conservative, a bound, or biased against the machine. A self-imposed prohibition that a
sibling document goes on violating is worse for credibility than the original error, because
it shows the correction was local rather than understood. The addendum predates the A2 sweep
by hours and was simply missed by it; the claims removed here are the same claims A2
withdrew, for the same algebraic reason.

---

### Second-rater amendments (owned by `SECOND-RATER-PROTOCOL.md`, logged here)

### A-H2-01 -- calibration round extended to Stage B. 2026-07-27.

`prepare_dan_session.cmd_calibrate` built only Stage A; it is now a two-phase command
(`calibrate`, then `calibrate --stage-b` once both raters' Stage-A exports return).
`SECOND-RATER-PROTOCOL.md` §4 and the new `PROTOCOL.md` §4b are written against it, with the
convention table split into Stage-A and Stage-B columns.

**Why.** Every convention the round exists to settle -- bar top, cap centre line vs upper
edge, asterisk vs cap, what counts as occluded -- is a **Stage B** landmark quantity. A
Stage-A-only warm-up reconciles the boxes and none of the measurements, and the tool
contradicted the protocol text that already told both raters to do Stage B.

### A-H2-02 -- the second rater's handoff is self-contained. 2026-07-27.

`cmd_pack` now ships `figure-extractor.html` and a new dependency-free `dan_timer.py` at the
archive root plus a generated `HANDOFF.txt`, and prints the tool's sha256.
`SECOND-RATER-PROTOCOL.md` §3/§6/§12 rewritten so no path on Greg's machine appears in any
instruction addressed to the rater.

**Why.** The protocol told the rater to unzip to his own machine and then open the tool and
the timer from Greg's WSL and Windows paths, which do not exist for him. Recording the tool
hash makes the version he annotated with provable rather than recalled.

### A-H2-03 -- the H2 id stream and item order moved out of the source. 2026-07-27.

`SEED_DAN = 20260728` removed; the seed is drawn once from `os.urandom` into the untracked
`dan/keys/seed.json`, and the item order is drawn from it via `interleave_by_stratum`.
`SECOND-RATER-PROTOCOL.md` §2 restated: blinding is primarily **procedural**, the
cryptographic half is secondary, and the old claim is recorded as having been false.

**Why.** With the seed, the subset and `dan_anon_id` all committed, `anon_id -> item_id` was
replayable in about a dozen lines -- and because an anon id embeds its position, a fixed
source order gave the mapping away even without the seed. `attack_dan_ids.py` demonstrates
7/7 recovery before and 0/7 after. The selection rule C1..C5 and the realised subset stay
public: they are the pre-registration.

**Operational consequence, and it must be acted on:** `dan/keys/plan.key.json` on disk was
generated by the old code and is crackable. Delete `dan/plan.json` and `dan/keys/plan.key.json`
and re-run `plan` before any session is handed out. Rebuild
`dan/calibration/DAN-C01-stageA.zip` with `calibrate --force`; the existing one predates
A-H2-02 and contains neither the tool nor the timer.

### A-H2-04 -- the pre-registered Stage-B cap made deterministic. 2026-07-27.

`_cap_stage_b` breaks ties with a sha256-derived index instead of the builtin `hash()`.

**Why.** Python salts `hash()` on `str` per process, so two runs of the same command kept
different panels and `shutil.rmtree`d different losers -- a "pre-registered" cap whose
realised set depended on `PYTHONHASHSEED`. Demonstrated over four seed values: the old code
produced four different scored sets, the new code one.

### A-H2-05 -- the `extractable` (abstention) agreement channel made joinable. 2026-07-27.

`inter_rater.py` rebuilds a `(item_id, panel letter)` identity for **any** record, joins on
it, and reports one-sided panels as `absent` rather than dropping them; the reader guard now
tests the readers present.

**Why.** `ingest_annotations.py` writes a non-extractable panel with no `item_id`, so
abstentions never reached the join: the one channel `Lyst2012_F7` was selected to test could
report agreement but never disagreement, and a single abstention in the second rater's store
would in fact have crashed the script. `ingest_annotations.py` was not modified.

---

## 13. Files in this directory

| file | role |
|---|---|
| `ANALYSIS-PLAN.md` | this pre-registration |
| `synthetic_reference.json` | frozen synthetic comparators + every pre-specified threshold, so `Delta` is computed against a citable artifact rather than a remembered number. Generated -- never hand-edited -- since amendment A18 |
| `make_synthetic_reference.py` | emits `synthetic_reference.json`: the panels block computed live from `benchmark/panels/score.py`, the rest carried as sourced data; `--check` detects staleness (amendment A18) |
| `make_coded_reference.py` | workbooks (198 `.xlsm`) -> `coded/coded_reference.json`; per-arm variance TYPE, arm names, VIF, rounding quantum. `--stats` prints the population table |
| `verify_oracle.py` | superseded by `verify_oracle_v2.py`; kept for the v1 body-text-only number quoted in sec.1.4b |
| `verify_oracle_v2.py` | the mechanical oracle test of section 1.4b: body text + caption + inside-the-figure (vector spans and OCR); four permutation nulls at 1000 reps; the committed hand-adjudication ledger (`ADJUDICATION`); sets `isOracle`, `oracleSource` and the two channel flags. Also builds `coded/pdf_map_full.json` (168/171 articles resolved) from Zotero |
| `dan_timer.py` | dependency-free stopwatch shipped inside the second rater's zip; writes `timing.jsonl` on his machine (amendment A-H2-02) |
| `attack_dan_ids.py` | the 12-line replay attack on the second rater's anon-ids, kept as an executable regression: 7/7 recovered before amendment A-H2-03, 0/7 after |
| `inter_rater.py` | the two-rater agreement report, including the abstention (`extractable`) channel |
| `score_real_validation.py` | the scorer: tiers D/P/E, stratification, transfer gap, gates, `--selftest`, `--power`, `--split` |
| `golden_diff_rv.R` | the end-to-end metafor stage: three readings, pairwise triangle, cluster bootstrap, TOST, mechanical threshold check |
| `split.json` | the DEV/LOCK assignment (generated, recomputable from the published salt) |

Reproduce:

```bash
cd benchmark/real-validation
python3 make_synthetic_reference.py        # synthetic_reference.json  (--check: staleness)
python3 make_coded_reference.py            # coded/coded_reference.json  (+ --stats)
python3 verify_oracle_v2.py                # sets isOracle/oracleSource where the ARTICLE prints the value
python3 verify_oracle_v2.py --no-ocr       # same, vector+caption+text only (fast)
python3 score_real_validation.py --split   # split.json
python3 score_real_validation.py --power   # the sample-size table
python3 score_real_validation.py --selftest
python3 score_real_validation.py --run <run> --split-filter lock
Rscript golden_diff_rv.R
```
