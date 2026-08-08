# Test cases (acceptance spec for approval)

Concrete scenarios the pipeline must handle correctly. Each states the INPUT (what the article
looks like) and the EXPECTED structured output. Approve these and they become the automated test
suite for the META layer (numbers verified with the already-built `convert`/`extract` helpers).

## TC1 — Single experiment, bar chart, mean ± SEM  (the common case)
**Input:** Article reports BDNF in Fig 2A, one running vs sedentary bar pair, mean ± SEM,
n=10/group in Methods (running 32.4±3.1, sedentary 24.1±2.8 pg/mg, SEM).
**Expected:** 1 screening record (included); **1 study**. Arms carry `dispersionType:"SEM"`,
`sd = SEM·√n` (running 9.80, sedentary 8.85). `effect.measure="SMD"`, g ≈ 0.851 (0.8886 is Cohen's d before the Hedges J correction), var ≈ 0.21.
`provenance.source="figure"`, `reviewStatus:"needs-review"`. clusterId = articleId.

## TC2 — Multiple studies per article, SHARED control  (the article≠study case)
**Input:** One paper: a single sedentary group compared to 2-, 4-, and 8-week running groups
(Fig 3, three bar pairs, shared sedentary bar).
**Expected:** 1 article, **3 studies** (`…-2wk`, `…-4wk`, `…-8wk`), each with a `durationWeeks`
moderator. All three list the sedentary group in `sharesControlWith` (each other). Synthesis
must NOT treat them as independent: cluster by articleId (RVE) AND apply the shared-control
correction. Test asserts 3 rows, same clusterId, non-empty `sharesControlWith`.

## TC3 — Subregion split → moderator + dependency
**Input:** Dorsal and ventral hippocampus BDNF reported separately (Fig 4A/B), same animals.
**Expected:** **2 studies** with `subregion` = dorsal / ventral, same clusterId, flagged as
correlated outcomes (same animals). Decision recorded per protocol: keep both + multilevel model,
OR pre-select dorsal (primary) as a sensitivity choice. Test asserts the moderator + dependency
link is present so synthesis can honor it.

## TC4 — Excluded article (kept for PRISMA)
**Input:** Article measures BDNF *mRNA* only (qPCR), no protein.
**Expected:** 1 screening record `status:"excluded"`, `reasonExcluded:"outcome: mRNA not protein"`,
`studies: []`. Contributes to the PRISMA exclusion count; contributes NOTHING to synthesis.
Test asserts zero studies + a coded reason.

## TC5 — Figure reports SD, not SEM  (dispersion-type routing)
**Input:** Bar chart, legend says "mean ± SD", n=8/group.
**Expected:** `dispersionType:"SD"`, `sd = dispersion` (no √n multiply). Confirms the SD/SEM
branch is chosen from the caption, not guessed. (Getting this wrong changes variance by n.)

## TC6 — Box plot (median/IQR) → mean/SD
**Input:** BDNF shown as box plots (median, Q1, Q3), n=12/group.
**Expected:** `extract.boxes` → mean = (Q1+median+Q3)/3, sd = (Q3−Q1)/1.35 (Wan 2014); arm
`dispersionType:"IQR"` with the derived `sd`; then g. Test asserts the median→mean/SD conversion.

## TC7 — Missing / ambiguous fields → human review (no silent guessing)
**Input:** Caption says "error bars represent variability" (SD vs SEM unstated); n given as "8–10".
**Expected:** `dispersionType:"unknown"`, `reviewStatus:"needs-review"`,
`reviewFlags:["dispersion-type-uncertain","n-range"]`, effect withheld (or computed under a stated
assumption + flagged). Test asserts the study is quarantined from the primary synthesis until a
human confirms. (This is where the vision-accuracy finding says review must focus.)

## TC8 — Two articles, same cohort (duplicate-data guard)
**Input:** A conference paper and its journal version report the same animals.
**Expected:** De-duplicated to one contributing record; the duplicate is `excluded`
(`reason:"duplicate cohort"`) with a link to the retained one. Prevents double-counting.

---
### What "approved" unlocks
Approving these + the protocol lets the META layer be built and tested against them directly: the
numeric expectations (g, variance, SD conversions) are checkable today with the existing
`figureExtractor.convert`/`extract` functions; the structural expectations (study count, clustering,
screening, PRISMA) become the schema's unit tests.
