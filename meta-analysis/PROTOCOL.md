# Meta-analysis protocol (v1.0 — APPROVED 2026-07-09)

A pre-registration-style protocol. Locked before extraction (the human analog: you register the
protocol on PROSPERO *before* touching the data, so choices can't be reverse-engineered).

**Approved decisions (locked):** topic = voluntary wheel-running → hippocampal BDNF protein in
healthy adult rodents · effect size = **Hedges' g (SMD)** · scope = **broad, with pre-specified
moderators/subgroups** · dependency = **random-effects + robust variance estimation clustered by
article** (+ shared-control correction).

## 1. Topic (narrow, on purpose)
**Does voluntary wheel-running exercise raise hippocampal BDNF protein in healthy adult rodents,
versus sedentary housing?**

Why this topic is a good fit for the tool:
- **Continuous outcome** (BDNF concentration / densitometry) → clean standardized effect size.
- **Figure-locked data.** BDNF is very often reported *only* as a bar chart (ELISA or
  western-blot densitometry) with error bars and per-animal dots — exactly what figure-extractor
  digitizes. Tables are the exception, not the rule.
- **Multiple studies per article.** A single paper routinely reports several independent
  contrasts (e.g. 2- vs 4- vs 8-week running; dorsal vs ventral hippocampus; male vs female;
  different strains). Each is a separate meta-analytic unit → forces the article→studies model.
- Narrow, real, and tractable (dozens, not thousands, of papers).

*(Swappable — see the approval questions. The machinery is topic-agnostic.)*

## 2. Question (PICO for animal studies)
| | Definition |
|---|---|
| **Population** | Healthy adult rodents (mouse or rat). Exclude disease/lesion/transgenic-pathology models (AD, stroke, depression models, aged >18 mo) — those are a *separate* review or a pre-planned subgroup. |
| **Intervention** | Chronic **voluntary** wheel running (≥ 7 days). Exclude forced treadmill (different stressor profile) — pre-planned moderator if included later. |
| **Comparator** | Sedentary controls (no wheel or locked wheel), same cohort. |
| **Outcome** | **Hippocampal BDNF protein** (ELISA pg/mg or mg⁻¹; or western-blot densitometry, fold/AU). Exclude mRNA-only, serum/plasma BDNF, and non-hippocampal regions. |
| **Study design** | Controlled experiment with an exercise arm and a concurrent sedentary arm, ≥ 3 animals/arm. |

## 3. Effect size
**Primary: Hedges' g (standardized mean difference)** — BDNF is measured in incomparable units
across labs (pg/mg vs AU vs fold), so we standardize. Positive g = exercise increases BDNF.
Variance by the standard SMD formula (small-sample corrected). *(Already implemented:
`figureExtractor.convert.hedgesG`.)*

Alternative on the table: **log response ratio (lnRR)** — popular in preclinical/ecology MA,
handles ratio-scale outcomes and fold-change data gracefully. (Approval question.)

## 4. Search strategy
- **Databases:** PubMed, Embase, Web of Science, Scopus. Plus backward/forward citation chasing
  and preprint servers (bioRxiv).
- **PubMed string (draft):**
  `(hippocamp*) AND ("BDNF" OR "brain-derived neurotrophic factor") AND (running OR "wheel" OR
  "voluntary exercise" OR "physical activity" OR "physical exercise") AND (mouse OR mice OR rat
  OR rats OR rodent* OR murine)`
- **Filters:** English; any year; animal studies. No disease-model MeSH in the primary set.
- **De-duplicate** across databases (DOI + title fuzzy match).
- **PRISMA flow** recorded (identified → screened → full-text → included, with exclusion counts).

## 5. Screening (two-pass, agent + human adjudication)
1. **Title/abstract** against inclusion/exclusion → include / exclude / unsure.
2. **Full text** for survivors → final include/exclude with a **coded reason** (wrong outcome,
   wrong population, no sedentary control, mRNA only, no extractable data, duplicate cohort).
Every screened article gets a **structured screening record** (kept even for exclusions — the
PRISMA denominator and auditability depend on it).

## 6. Data extraction
For each **included article**, extract one record per **study** (comparison) — see
`data-model.md`. Sources, in priority order: a reported numeric table → text → **a figure
(figure-extractor: characterize → extract bar-endpoints/box-landmarks → mean, SD via the caption's
dispersion type, n from methods)**. Standardize to g. Dual extraction on a 20% sample to estimate
extractor error; all figure-derived values flagged for human confirmation of dispersion type + n
(the two fields most error-prone — see the accuracy benchmark).

## 7. Risk of bias
**SYRCLE's RoB tool** for animal studies (sequence generation, baseline characteristics,
allocation concealment, random housing, blinding, random outcome assessment, incomplete data,
selective reporting, other). One assessment per article; surfaced per study.

## 8. Synthesis
- **Random-effects** model (REML), because true effects vary across labs/strains.
- **Dependency:** multiple studies share an article (and sometimes a control group). Model the
  **article as a cluster** and use **robust variance estimation (RVE)** / a multilevel
  (article → study) model, *not* naive independence. Shared-control comparisons get the
  shared-control variance correction. (Approval question.)
- **Heterogeneity:** τ², I², prediction interval.
- **Moderators / subgroups** (pre-specified): species, sex, running duration, assay
  (ELISA vs WB), subregion (dorsal/ventral), age.
- **Publication bias:** funnel plot + Egger's test + trim-and-fill (interpreted cautiously with
  clustering).
- **Sensitivity:** leave-one-out; figure-derived-only vs table-derived; exclude high-RoB.
- **Output:** forest plot (by study, grouped by article), the studies table, and a PRISMA diagram.

## 9. What's already built vs. what this adds
- **Built (figure-extractor):** figure characterization, digitization, `bars/boxes/forest`
  extraction, `convert.hedgesG` etc., and a per-figure `meta-analysis.csv`.
- **This layer adds:** the protocol, the corpus + screening records, the **study-grained** record
  with moderators + article clustering + risk of bias, effect-size synthesis, and PRISMA/forest
  outputs. The per-figure `meta-analysis.csv` is a *precursor* (effect-grained); this re-grains it
  to *studies* and attaches provenance back to the exact figure + digitization.
