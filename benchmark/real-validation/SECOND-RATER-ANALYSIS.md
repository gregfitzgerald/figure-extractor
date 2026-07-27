# Addendum H2 -- a second rater. Diff against ANALYSIS-PLAN.md

**Status: pre-specified, written before any `H2` annotation exists.**
Written: 2026-07-27.

This is an **addendum**, not a revision. `ANALYSIS-PLAN.md` is unchanged and stays the
pre-registration of record. This file states, in diff form, exactly what a second rater adds,
what it changes, and what it does *not* license. If and when H2 data is collected, a one-line
pointer to this file goes in `ANALYSIS-PLAN.md` §12 (Amendments) with a date. Until then
nothing in the main plan is altered and no result in it is relabelled.

It closes **known gap #1** (`ANALYSIS-PLAN.md` §11.1): *"One rater. `D` and `G` are the same
person, so §1.3 bounds intra-rater reliability, not inter-rater. A genuine second annotator on
even 30 panels would convert every 'this human, twice' sentence into 'two humans' and is the
single highest-value addition."*

---

## A0. The whole change, in one table

| | before | after |
|---|---|---|
| readings | `D`, `G`, `M` | `D`, `G`, `M`, **`H2`** |
| does H2 replace D? | -- | **No. It joins as a fourth instrument.** See A5. |
| primary dispersion estimator (full corpus) | Grubbs `{D,G,M}` | **unchanged** -- it keeps the n |
| primary dispersion estimator (H2 overlap) | -- | **Grubbs `{G,H2,M}`** -- three instruments, no two sharing a person |
| shared-person covariance `c` | argued to be `>= 0`, bracketed by `sigma_G_repeat` | **measured**: `c_hat = sigma_G^2{D,G,M} - sigma_G^2{G,H2,M}` |
| the yardstick for "is M as good as a human" | `RC_intra = 2.77 * s_w` from G's own repeats | `RC_intra` **and** `RC_inter` from G vs H2, reported side by side |
| the sentence in the write-up | "this human, twice" | "two trained annotators, independently" |
| what is still not claimable | "the machine is more accurate than a human on real figures" | **unchanged.** Accuracy needs an oracle; H2 buys interchangeability, not accuracy. |

---

## A1. The subset, and the rule that chose it

**23 scored panels across 7 figures, 7 articles, 11 strata, all drawn from Tier 1.**
Stage A additionally covers all **35** panels of those 7 figures (structure is annotated
whole-figure; see C0). Machine-readable in `prepare_dan_session.py:DAN_SUBSET`; regenerate
with `python3 prepare_dan_session.py plan`.

| # | figure | tiles | scored | disp. type | strata | 4-instrument cells |
|---|---|---|---|---|---|---|
| 1 | `Zhang2017_F3` | 7 | 4 | SD (methods) | S0, S1, S7, **S18** | 4 (incl. 3e, 3f text-verified) |
| 2 | `Lee2024_F2` | 5 | 4 | SEM (caption) | S0, S8, S9, S11 | 2 (incl. 2B text-verified) |
| 3 | `Ederer2022_F2` | 8 | 4 | SEM (caption) | S0, S7 | 1 (2A text-verified) |
| 4 | `Lyst2012_F7` | 4 | 4 | **UNSTATED** | S5, S1 | 0 |
| 5 | `Morgan2018_F7` | 3 | 3 | SEM (table legend) | S5 | 0 |
| 6 | `Chrusch2023_F2` | 7 | 3 | SEM (caption) | **S3**, S2, S8, S9 | 0 |
| 7 | `Nawaz2018_F1` | 1 | 1 | SD (caption) | **S10**, S11 | 0 |
| | **7 figures** | **35** | **23** | | **11 strata** | **7 (4 text-verified)** |

Stretch add-backs, in restore order (`--stretch`): `Gattas2022_F4` (+3 panels, +1
four-instrument cell, roman-numeral labels), `Harburger2007b_F3` (+4 SEM panels at a 0.92%
gutter). Together they take the set to 30 panels / 9 articles / ~5.2 h.

### The rule

**C0 -- Stage A is whole-figure; only Stage B is subselected.** Handing a rater a list of
panels to annotate *inside* a figure tells him how many panels the figure has and what they
are called. Panel count and letters are the Tier-P measurement. So Dan draws every tile of
every figure he opens, and the per-figure scored cap is applied by the harness **after** his
Stage A is exported and sealed, where it can leak nothing.

**C1 -- Overlap is mandatory.** Candidates are Tier-1 figures **only**. Dan reads nothing Greg
does not read. An unpaired panel contributes exactly zero to any inter-rater statistic, so a
"broader" subset that is not paired is not broader, it is smaller. This is the one clause with
no trade-off in it.

**C2 -- Four-instrument core.** Take every Tier-1 figure carrying a `landmark_task` with
`usable_for_dispersion: true`, prioritising `text_value_verified` tasks. These are the only
cells where `D`, `G`, `M` and `H2` coexist, and they are what makes `c` **measurable** rather
than merely bracketed (A5). Yields `Zhang2017_F3`, `Lee2024_F2`, `Ederer2022_F2`.

**C3 -- Dispersion-mix correction.** *This is the clause that stops the subset being the
convenient one.* Tier 1's 11 coded landmark panels are **6/11 from a single article, 6/11 SD,
and 5/5 from `S0_textGT`** -- i.e. the four-instrument core is concentrated in the *long-cap
easy case* and in papers that print their own numbers, while the corpus is ~91% SEM and the
whole dispersion argument is about short caps. A subset restricted to those 11 would be the
least representative slice available for the channel the claim rests on. So: add SEM-bearing
figures until SEM is the majority of scored panels and no article supplies more than ~20% of
them. Yields `Morgan2018_F7`, `Chrusch2023_F2`.

The freedom to do this comes from a structural fact worth stating plainly: **`H2` vs `G` needs
no historical reading.** The 355-panel ceiling on Tier E exists because Grubbs `{D,G,M}` needs
`D`. The `{G,H2,M}` triple does not, so the inter-rater sample is bounded by Dan's hours, not
by what Greg happened to code years ago.

**C4 -- Convention stress.** Add unconditionally the figures that instantiate the failure modes
the protocol already names, because a convention difference that only appears on hard panels is
precisely what an inter-rater study exists to find:
- `Lyst2012_F7` -- the paper states **no dispersion type at all**. The correct answer is
  *abstain*, `dispersion-type-uncertain` flag recall >= 80% is a pre-committed **GATE** (§3.3),
  and abstention is the behaviour most likely to differ between two people.
- `Nawaz2018_F1` -- single-panel control, where any split is a false positive. 1 tile, ~11 min:
  the cheapest stratum in the corpus.

**C5 -- Budget stop** at Tier 1's own ~4 h ceiling, via the per-figure `cap_b`.

### Resulting mix

- **Dispersion type:** SEM 14/23 (61%), SD 5/23 (22%), unstated 4/23 (17%). Deliberately *not*
  proportional to the corpus's 91% SEM: SD (`S18_SD_rare`) and unstated are both oversampled
  strata in the parent design, and the deviation is recorded rather than corrected.
- **Articles:** 7, maximum single-article share 4/23 = 17%.
- **Strata:** 11 of 19, including flush (`S3`), tight (`S2`), single-panel (`S10`),
  labels-absent (`S5`), non-`[A-Z]` alphabet (`S8`) and letter/tile mismatch (`S9`).
  Not covered: `S4` non-guillotine, `S6` stray letters, `S12`-`S17`. `S4` and `S6` are each a
  single 4-12-tile figure that yields no bar panels, so they cost Stage-A time and buy no
  dispersion; they are the first candidates if the structure channel is later prioritised.

---

## A2. What precision this buys -- and what it does not

All figures below come from `score_real_validation.py --power` (the pre-registered estimators:
Wilson, rule of three, Wilson-Hilferty F for variance ratios) evaluated at the `n` this subset
delivers. **They are not encouraging, and that is the point of computing them in advance.**

Expected paired arm-values: 23 panels x 2.28 marks/panel (the `mbar` in `--power`'s clustering
block) ~= **53 dispersion pairs** and ~53 central pairs. The four-instrument subset is 7 panels
~= **16** pairs.

| quantity | n | 95% interval / bound | verdict |
|---|---|---|---|
| Grubbs `sigma_M / sigma_G` on `{G,H2,M}` | 53 | **[0.68, 1.47]** at a true ratio of 1.0 | **direction check, not an estimate.** It barely excludes the §8.2 gate value of 1.5 and cannot separate 1.0 from 1.3. |
| the same, on the four-instrument cells (for `c_hat`) | 16 | **[0.48, 2.10]** | **sign check only.** `c_hat` gets a direction, never a magnitude. |
| Bland-Altman bias on `log(SD_H2/SD_G)` | 53 | +/- 0.269 x `sd_diff` (= **+/- 2.7 pp** at `sd_log` = 0.10) | **usable.** Discriminates a real systematic offset from zero. |
| Bland-Altman **limits of agreement** | 53 | +/- 0.466 x `sd_diff` per limit (= **+/- 4.7 pp** at `sd_log` = 0.10) | **usable, and the headline.** At `sd_log` = 0.10 the LoA are ~[-18%, +22%] +/- 4.7 pp, which genuinely tests the pre-registered +/-25% gate. |
| `ICC(A,1)`, dispersion | 53 | true 0.95 -> **[0.894, 0.977]** | usable, **with the caveat in A6.2** |
| categorical channels (chart type, dispersion type, roles) | 23 panels | 0 disagreements -> UB **13.0%**; at 90% observed, +/- 12.2 pp | **weak.** Detects a convention difference; cannot certify a rate. |
| structure channels (panel count, letters, box IoU) | 35 panels / 7 figures | 0 disagreements -> UB **8.6%** | **weak.** Cannot independently establish the <= 5% silent-mislabel gate. |

**Stated plainly, so it is not over-read later:**

- What 23 panels buys is a **convention check plus a first inter-rater limit of agreement**.
  That is exactly what upgrades the *phrasing* of the central claim (A7).
- What it does **not** buy is a precise `sigma_M / sigma_G`. The §4.4 rule -- *no claim that the
  machine is more precise than the human unless the upper end of the interval is below 1.0* --
  **cannot be cleared at n = 53** unless the point estimate lands at or below ~0.68.
  Pre-specified: if the point estimate lands in [0.68, 0.85] (suggestive but not resolvable),
  that triggers **Stage 2**, not a weakened claim.
- **Stage 2 trigger, pre-committed.** Extend H2 into Tier 2 (`worklist.json` has 32 further
  landmark panels at tier 2) to ~120 dispersion pairs, where the interval tightens to
  **[0.77, 1.29]** and a point estimate of 0.77 would clear the bar. ~52 panels, ~9 h of a
  second rater's time. Do this **only** on that trigger; running it unconditionally spends a
  colleague's day on a number that is already resolved.

**Clustering.** With 7 articles the article-level cluster bootstrap prescribed in §2.1 is not
usable (7 clusters cannot support a 10 000-resample percentile interval). Pre-specified
substitute: intervals on H2 quantities are computed by **panel-level** bootstrap and are
labelled **"not cluster-adjusted"** wherever they appear, with the article-level ICC of the
log-ratios reported descriptively beside them. This is a real weakness of a 7-article subset and
it is not repaired by pretending otherwise.

---

## A3. Doubled blinding -- Dan blind to the machine *and* to Greg

Both halves are mechanical and both fail closed.

### A3.1 Blind to the machine -- asserted, not inferred

`ANALYSIS-PLAN.md` §7 currently controls this *after the fact*: the ingest detects that the
detector ran (`panelDetection != null`, `captionSource == 'panel-split'`) and throws the figure
away. Detecting a violation is strictly worse than preventing one.

The tool now ships the `annotationMode` setting proposed in `PROTOCOL.md` §12: it hides
`Auto-panels`, makes `detectPanels` refuse with `flags: ['annotation-mode']`, and stamps
`annotationMode: true` into every export (`figure-extractor.html:5920`, `:6163`).

**Added for H2:** `prepare_dan_session.py check` -- and `build-b`, and `pack` -- **refuse any
export whose top-level `annotationMode` is not `true`**, on top of the existing fingerprint
test. That converts blinding from *"we found no evidence it happened"* to *"the export asserts
it could not have"*. A Dan session done with the checkbox off is not suspect, it is unusable.

This is scoped to Dan only. `rvcommon.blinding_violations` is deliberately **not** modified, so
Greg's path is byte-identical and the main pre-registration's controls are unchanged.

### A3.2 Blind to Greg -- physical separation, plus a leak scan

| mechanism | what it prevents |
|---|---|
| **Separate data root.** `prepare_dan_session.py` sets `RV_DATA` to `benchmark/real-validation/dan/` before importing `rvcommon`, which relocates `sessions/`, `keys/` and `gt/` together. Dan's tree and Greg's tree share no path. | Dan's ingest cannot reach Greg's `human_gt.jsonl`; Greg's cannot reach Dan's. Both matter: the session-scoped replace at `ingest_annotations.py:553` would otherwise let a same-named session **delete** the other rater's rows. |
| **`dn` id prefix + a different RNG stream** (`SEED_DAN = 20260728`, over a different item list). | No id Dan sees is derivable from, or collides with, one of Greg's. There is no arithmetic mapping `dn03_9c1a` onto an `it..` id. |
| **`pack` walks the archive before writing it** and aborts on any member named `plan.key.json`, `human_gt.jsonl`, `coded_reference.json`, `*seal.json*`, `split.json`, `intra_rater*`, or sitting under `keys/ gt/ repeat/ pred/ coded/ out/ exports/`. | Dan receives page images, blank coding forms, a worksheet and the protocol. Nothing else can get into the zip, including by accident. |
| **`build-b` is gated on Greg being sealed first.** Building Dan's Stage B means opening Dan's panel boxes, so whoever runs it sees them. If G is not yet finished on those figures, that is a contamination path running **Dan -> Greg**. The command reads only the `item_id` list out of Greg's key and the existence of his `gt/<session>/seal.json`, and refuses until every overlapping item is sealed. | The wrong-direction leak, which is the one nobody thinks about. |

Every one of these is asserted by `test_second_rater.py`.

---

## A4. Calibration round (and its statistical cost, stated)

Specified in full in `SECOND-RATER-PROTOCOL.md` §4. Summary and rationale:

- **3 figures, both raters, independently, no discussion.** `GarciaCapdevila2009_F1` (2 tiles,
  grouped bar, SEM -- the plain case: where exactly is the bar top / the cap, and does the panel
  box include the y-axis and its tick labels), `Bonaccorsi2013_F1` (6 tiles sharing an axis,
  SEM, and the figure that produced this project's own asterisk-occlusion finding -- who owns a
  shared axis, asterisk vs cap, what counts as occluded), `Gobeske2009_F4` (5 tiles, caption
  names 4 letters -- what is a panel, how do you name an unlabelled tile).
- **All three are from the articles §2.3 marks permanently DEV**, so they are already
  contaminated, already excluded from LOCK, and cost nothing to spend on a warm-up. None is in
  Dan's scored set. `prepare_dan_session.py calibrate` builds them into a **separate data root**
  (`dan/calibration/`), and `plan --calibration` **refuses to run outside it**, so a calibration
  read cannot reach `dan/gt/human_gt.jsonl` and cannot be analysed by accident.
- The round runs through the identical Stage A -> export -> Stage B mechanics, so it also
  functions as a dry run of the tool and the handoff.
- Each rater writes one sentence per convention. Then a 20-minute call reconciles the
  **sentences**, and the agreed wording is recorded in `SECOND-RATER-PROTOCOL.md` §13 with a
  date and initials. Any panel whose convention changed is redone. The scored set starts on a
  different day.
- **Definitions are reconciled; values are never compared.** Agreeing "we should both have got
  about 21.4" would train the raters toward each other *on magnitudes*, which is the exact
  independence the design is buying.

**The cost, and why it is worth paying.** Calibration induces a shared error component `c'`
between `G` and `H2`. That is not free, and the direction must be stated: in Grubbs `{G,H2,M}`,

```
sigma_M^2(est) = [Var(M-G) + Var(M-H2) - Var(G-H2)] / 2
               = sigma_M^2 + c'                            (c' = cov(e_G, e_H2) >= 0)
```

so a shared convention **inflates** the machine's estimated variance -- **conservative against
the machine**, the same direction §1.3 establishes for `c` between `D` and `G`. The
conservatism argument therefore survives the calibration round intact, and
`inter_rater.py --selftest` asserts this numerically rather than in prose.

The alternative -- two uncalibrated raters using different definitions -- produces an inflated
`Var(G - H2)` that is **bias, not unreliability**, and bias does not average out. Reconciling
arbitrary definitional choices while never reconciling measurements is the standard resolution
and is the right one here.

---

## A5. Where `H2` enters the estimator

### A5.1 It joins as a fourth instrument. It does not replace `D`.

Three estimates are computed and reported side by side, each labelled with what it is good for:

| # | triple | scope | n | property |
|---|---|---|---|---|
| 1 | `{D, G, M}` | all complete Tier-E triplets | large | **precise, confounded.** `D` and `G` share a person; `E[sigma_M^2] = sigma_M^2 + c`, conservative against M. **Remains the primary for the corpus.** |
| 2 | `{G, H2, M}` | Dan's 23-panel overlap | ~53 | **unconfounded, imprecise.** No two instruments share a person. `c'` from calibration only (A4), same conservative direction. **New primary on the overlap.** |
| 3 | difference of 1 and 2 | the 7 four-instrument cells | ~16 | `c_hat = sigma_G^2{D,G,M} - sigma_G^2{G,H2,M}` -- the first *measurement* of the quantity §1.3 could only bracket. |

**Why not replace `D`.** `D` costs nothing, covers 355 panels, and its quantization cancels out
of `sigma_M` (§1.5). Dropping it would trade a large-n estimate for a 53-pair one and lose the
only thing that makes `c_hat` computable.

**Why not pool into one four-instrument least-squares fit** over the six pairwise difference
variances: it is more efficient, but its efficiency comes precisely from assuming all four error
terms are independent, which `D` is known to violate. Pre-specified: the four-instrument
over-identified fit is reported as a **sensitivity analysis only**, never as the primary, and
its over-identification residual is reported as a diagnostic of the independence assumption.

### A5.2 Pre-committed reading of `c_hat`

`ANALYSIS-PLAN.md` §1.3 asserts a direction: shared-person error biases the comparison
**against** the machine, so every machine-vs-human statement produced by `{D,G,M}` is
conservative. That assertion is currently untested. With H2 it becomes falsifiable:

- **`c_hat > 0`** (equivalently `sigma_M{D,G,M} > sigma_M{G,H2,M}`) -> §1.3 is **confirmed**.
  The corpus-wide `sigma_M` stays as reported and keeps its "at least this good" framing.
- **`c_hat <= 0` with the intervals separated** -> §1.3's conservatism claim is **refuted** and
  must be withdrawn from the write-up, not softened. The `{D,G,M}` estimate would then be
  anti-conservative and every statement resting on it is relabelled.
- **intervals overlapping** (the likely outcome at n = 16) -> reported as *unresolved at this
  n*, with the §1.3 argument retained as an argument and explicitly not as a measurement.

### A5.3 New yardstick alongside `R_floor`

`ANALYSIS-PLAN.md` §3.3 defines `R_floor = median|M - G| / RC_intra` with
`RC_intra = 1.96 * sqrt(2) * sigma_G_repeat`, and §8.2 makes `R_floor > 1.0` a hard no-go
conjunct for building the ML detector. Add, computed identically but from the inter-rater pairs:

```
RC_inter  = 2.77 * s_w(G, H2)      # s_w from the relative-difference form `intra` already uses
R_inter   = median|M - G| / RC_inter
```

`RC_inter >= RC_intra` is expected (two people disagree more than one person with himself). Both
ratios are reported, always adjacent, and **`R_inter` is the one the write-up leads with**,
because "the machine sits inside the range two humans differ by" is the claim a reader actually
cares about, while `R_floor` answers the narrower within-person question.

**Change to §8.2, pre-committed.** The no-go conjunct becomes
`R_floor > 1.0 AND R_inter > 1.0`. If the machine's disagreement is inside the *inter*-rater
band but outside the intra-rater one, the residual is not measurable against the human reference
population and a detector still cannot be justified on accuracy. This makes the existing gate
strictly harder to trigger, which is the correct direction: the honest reading of "the machine
is within human-to-human variation" is that there is nothing left to train against.

---

## A6. Inter-rater statistics to report, per channel

Produced by `inter_rater.py`, written to `dan/inter-rater.md` + `.json`.

### A6.1 Panel and mark matching

Panels are paired on `(item_id, panelLetter)` first, then -- for panels whose letters disagree --
by **maximum panel-box IoU >= 0.5** within the same figure. The two routes are counted
separately. **A letter disagreement between two humans is the Tier-P silent-mislabel class
occurring between people**, so it is reported as a number, never absorbed as a join failure. It
is also the number that says how much of any machine-vs-human letter disagreement is convention
rather than error.

Marks within a panel are matched **by index, not by label**. `ingest_annotations.cmd_intra`
matches groups on `"<group> <seriesLabel>"`, which is fine when one person typed both and
useless across two people. The ingest already enforces left-to-right click order against the
coding form's `marks[]` roster, so the i-th group is the i-th bar from the left in both
readings: index is the convention-free join.

### A6.2 Continuous channels -- central, dispersion

**Primary: Bland-Altman on `log(H2 / G)`,** reported as bias and 95% limits of agreement,
back-transformed to percent, with a 95% CI on the bias and on each limit. Log scale because
dispersion error is proportional (§1.3), which makes the LoA directly comparable to the
pre-registered `[-25%, +25%]` gate on `log(SD_M / SD_G)`.

**Secondary: `ICC(A,1)`** -- two-way random effects, absolute agreement, single measurement
(Shrout & Fleiss ICC(2,1) / McGraw & Wong ICC(A,1)). The form is chosen, not defaulted:

- *two-way **random***, because the claim is about "a competent human annotator", not about these
  two men specifically; a mixed-effects form would restrict inference to Greg and Dan;
- ***absolute* agreement, not consistency**, because a constant offset between raters (one clicks
  the cap's centre line, the other its upper edge) is a **real** error here -- the number enters
  `escalc` as it stands and is never mean-centred;
- *single measurement*, because the study uses **one** rater's reading, not the mean of two.

**And the caveat that must travel with it.** ICC is a ratio of rater variance to *between-panel*
variance. Panel values here span orders of magnitude across figures (seconds, percent freezing,
entries/min), so an ICC computed over the pooled set will be ~0.99 and will say nothing about
measurement quality -- it will be reporting that the panels differ from each other.
**Pre-specified:** ICC is reported (a) only within a common unit/outcome family, (b) never as the
headline, and (c) always beside the Bland-Altman LoA and `RC_inter`, which are scale-free and
interpretable. If ICC and LoA disagree in their impression, the LoA is correct.

**Also reported, matching the `intra` report exactly** so inter and intra are the same quantity:
median and worst relative % difference, `s_w`, and `RC = 2.77 * s_w`.

### A6.3 Categorical channels -- chart type, dispersion type, series roles, extractability

Percent agreement **and Cohen's kappa**, both. `cmd_intra` reports raw agreement only, which is
uninterpretable on a degenerate channel -- and ~91% of this corpus is SEM, so dispersion-type
agreement is exactly that case. `inter_rater.py --selftest` asserts that a channel scoring **90%
raw agreement** on an 18/20 SEM split returns **kappa < 0.1**.

### A6.4 Structure channels -- panel count, letter set, per-letter box IoU

Reported per figure and per panel: panel-count agreement, letter-set agreement, median and worst
per-letter IoU, and the count of letters assigned differently. These bound how much of the
Tier-P machine-vs-human gap is human convention.

---

## A7. How the claim must be phrased once inter-rater data exists

**Unchanged and still binding (§8.5).** No result from this study licenses *"the machine is more
accurate than a human at reading error bars from real figures."* That claim needs an oracle. It
is established, and will only be cited, on the **synthetic** benchmark against R's exact
descriptives. A second rater does not create an oracle -- two people who both misread the same
ambiguous cap the same way agree perfectly and are both wrong.

**What changes is the interchangeability sentence**, and it changes from a weak form to a strong
one:

> **Before (permitted now):** "The automated read's disagreement with the human annotator was no
> larger than the range within which that annotator's own two readings of the same panels
> differed (`R_floor` = ...)." -- i.e. *this human, twice*.

> **After (permitted only once H2 exists, and only if the numbers support it):** "On N real
> journal panels read independently and blind by two trained annotators, the automated read's
> disagreement with either human reading was no larger than the two humans' disagreement with
> each other (`RC_inter` = a%, median |M-G| = b%, `R_inter` = r, 95% CI [.., ..], not
> cluster-adjusted; n = 23 panels / ~53 arm-values from 7 articles)."

**Three riders that must appear wherever that sentence appears**, pre-committed:

1. **the n and the article count**, because 23 panels from 7 articles is a small, deliberately
   stratified sample and the reader must be able to see that;
2. **"interchangeable, not accurate"** -- the sentence is about agreement, and the study's main
   methodological contribution is keeping those two apart;
3. **the direction of every known bias**: shared-person `c` (§1.3), calibration-induced `c'` (A4)
   and any G/H2 shared misreading all inflate the estimated `sigma_M`, so the machine statement
   is conservative. *"We do not get to claim the machine is better than the estimate says; we do
   get to claim it is at least that good."*

**And one thing the phrasing must not do**: it must not describe Dan as a random draw from "human
annotators". He is a colleague trained by `SECOND-RATER-PROTOCOL.md` and calibrated against Greg
on three panels. The correct noun phrase is **"two trained annotators following a common written
protocol"**, which is what a meta-analysis team actually is, and it is a narrower and more honest
claim than "two humans".

---

## A8. Additions to §7 (bias and validity threats)

| threat | mechanism | control | direction of residual bias |
|---|---|---|---|
| **Dan -> Greg contamination** | building Dan's Stage B requires opening Dan's panel boxes | `prepare_dan_session.py build-b` refuses until every overlapping item of Greg's is ingested **and sealed** | eliminated if the gate is respected; `--force` use is visible in the session record |
| **Calibration-induced correlation** | reconciling conventions makes `e_G` and `e_H2` share a component `c' >= 0` | conventions reconciled, values never; the round runs on non-scored panels | **inflates** `sigma_M{G,H2,M}` -- conservative against the machine (A4) |
| **Dan is not a random annotator** | one colleague, trained by this protocol, calibrated against Greg | claim narrowed to "two trained annotators following a common written protocol" (A7) | unquantified; a generalisation limit, not a bias |
| **7 articles is too few to cluster** | §2.1 prescribes an article-level cluster bootstrap at B = 10 000 | panel-level bootstrap substituted; every H2 interval labelled **"not cluster-adjusted"**; article ICC of log-ratios reported descriptively | intervals are **too narrow** by the design effect (~1.5 at ICC 0.4), stated wherever they appear |
| **The overlap is a hard, stratified sample** | Dan reads Tier 1, which deliberately oversamples flush, tight, labels-absent and unstated-dispersion figures | reported per stratum, as everywhere else | `RC_inter` from this sample is **pessimistic** relative to a proportional sample -- so the "machine inside human variation" claim is *harder* to make, not easier |
| **A mislabelled ingest reported as inter-rater** | `cmd_intra` pairs on `(item_id, panelLetter)` with **no rater filter**, so a Greg/Dan pair would be reported as *intra*-rater repeatability | `inter_rater.py` **refuses** any store whose `reader` is `GF-human`/absent; the two trees are physically disjoint so the stores cannot merge | eliminated; asserted by `test_second_rater.py` |

---

## A9. Section-by-section diff against `ANALYSIS-PLAN.md`

| section | change |
|---|---|
| **§1.2** (three readings) | add a fourth row: `H2` -- second rater, figure-extractor, blind to both `M` and `G`, 23 panels of Tier 1. |
| **§1.3** (variance decomposition) | the `c` bracketing argument gains a **measurement** (`c_hat`, A5.2) and a falsification condition. `sigma_G_repeat` remains the bracketing device for the corpus-wide `{D,G,M}` estimate. |
| **§3.3** (dispersion, the headline) | quantity (c) gains a second row: Grubbs on `{G,H2,M}` with its own CI. `R_floor` gains `R_inter` beside it. |
| **§4.4** (continuous outcomes) | the "no *more precise* claim unless the upper interval end is below 1.0" rule gains an explicit n-feasibility note: **unachievable at 53 pairs**; Stage-2 trigger in A2. |
| **§4.6** (labour budget) | add a row: `H2` -- 23 scored panels + 35 Stage-A panels + calibration, **~4.5 h of a second person**. Optional Stage 2: +~9 h. |
| **§5** (stratification) | H2 quantities are reported per stratum like everything else, subject to the n >= 10 minimum -- which **only the SEM stratum meets** (14 panels). SD (5) and unstated (4) are reported as raw counts, no percentages. |
| **§7** (threats) | six rows added, A8. |
| **§8.2** (BUILD THE DETECTOR) | the `R_floor > 1.0` conjunct becomes `R_floor > 1.0 AND R_inter > 1.0`. Strictly harder to trigger. |
| **§8.5** (what no result licenses) | unchanged in substance; the permitted interchangeability sentence is upgraded per A7 and the three riders become mandatory. |
| **§10** (interface contract) | H2 records use the same `human_gt.jsonl` schema in a **separate data root**, distinguished by `reader: "DK-human"`. The scorer's hard-coded `GT_DIR = HERE/"gt"` is **not** changed; `inter_rater.py` takes both roots as arguments. |
| **§11** (known gaps) | gap #1 **closed at Tier 1 scope**, with the honest qualifier that 23 panels resolves the *phrasing* of the claim and not the *precision* of `sigma_M`. Gap #2 (Grubbs independence) is downgraded from "violated, bracketed" to "violated in `{D,G,M}`, absent in `{G,H2,M}`, measured by `c_hat`". |
| **§12** (amendments) | when H2 data is collected, add: *"YYYY-MM-DD -- second rater added per `SECOND-RATER-ANALYSIS.md`. No pre-existing threshold changed; §8.2's no-go conjunct tightened."* |
| **§13** (files) | four files added, A10. |

---

## A10. Files added, and how to run them

| file | role |
|---|---|
| `SECOND-RATER-PROTOCOL.md` | standalone instructions for the second rater; assumes zero project context |
| `prepare_dan_session.py` | Dan's blinded session builder: `plan` / `build` / `check` / `build-b` / `pack` / `timer` / `ingest` / `status` / `--selftest`. Sets `RV_DATA` to `dan/` and delegates rendering, cropping and ingest to the unmodified `prepare_session.py` / `ingest_annotations.py`. |
| `inter_rater.py` | the `G` vs `H2` report: index-matched marks, kappa, `ICC(A,1)`, Bland-Altman on log-ratios, `RC_inter`, Grubbs `{G,H2,M}`, `c_hat` stub. `--selftest`. |
| `test_second_rater.py` | end-to-end on real PDFs in a temp tree: blinding refusals, the pack leak scan, the Greg-sealed gate, the Stage-B cap, ingest attribution, and the inter-rater report. |

**Nothing in the existing pipeline is modified.** `prepare_session.py`, `rvcommon.py`,
`ingest_annotations.py`, `score_real_validation.py`, `ANALYSIS-PLAN.md`, `PROTOCOL.md`,
`SAMPLING-AND-WORKLIST.md` and `worklist.json` are untouched; `test_end_to_end.py` and all four
existing `--selftest` suites pass unchanged.

```bash
cd benchmark/real-validation

python3 prepare_dan_session.py --selftest
python3 prepare_dan_session.py calibrate         # the shared warm-up, in dan/calibration/
#   ... BOTH raters do it, then reconcile conventions (A4) and record them
python3 prepare_dan_session.py plan              # 7 figures / 35 panels / 23 scored
python3 prepare_dan_session.py build S01
python3 prepare_dan_session.py pack  S01 A       # -> DAN-S01-stageA.zip, leak-scanned
#   ... Dan annotates, returns his export; unzip into dan/sessions/S01/exports/passA/
python3 prepare_dan_session.py check S01 passA   # annotationMode + fingerprints
python3 prepare_dan_session.py build-b S01       # gated on G being sealed; applies the cap
python3 prepare_dan_session.py pack  S01 B
#   ... Dan fills forms + digitizes; unzip into dan/sessions/S01/exports/passB/
python3 prepare_dan_session.py ingest S01        # --reader DK-human, into dan/gt/

python3 inter_rater.py                           # -> dan/inter-rater.md + .json
python3 inter_rater.py --run <machine-run>       # + Grubbs on {G, H2, M}
python3 test_second_rater.py
```
