# Real-figure golden diff -- feasibility map + pilot

The synthetic R-GT benchmark (`../RESULTS.md`) proved, on charts R rendered from known data,
that **figure-extraction error concentrates in the dispersion (error-bar) channel** (central
tendency ~0.5% median for every tool; dispersion 4-9% median, worst 20-58%), and that it is
driven by short SEM/CI caps whose few-pixel length gives the worst pixel-to-value leverage.
That is a *ceiling* argument: it bounds and locates the error but is measured on clean
synthetic renders. **This experiment tests whether that structure transfers to real journal
figures** -- the "minimal justifying experiment" the benchmark README specifies -- using the
dissertation meta-analysis's own hand-coded corpus so the figure eval and the end-to-end
**golden diff** share studies.

Everything here is under `benchmark/real/`; `benchmark/r/` and `benchmark/harness/` are
untouched (the scorer imports the shared `harness/calibrate.py` affine).

---

## 1. Feasibility -- the figure-derived population (honest numbers)

Provenance rule (dissertation codebook): a coded row is **figure-derived** iff its
`Data_Source` begins with "figure" **or** its `Data_Extraction_Method` names a figure-reading
act ("estimated/extracted/direct from figure", "figure analysis", "reported in figure",
"re-extracted"). Built by `inventory.py` -> `population.json`, `articles.json`.

| dataset | total rows | **figure-derived** | complete C/I m,sd,n | named panel | articles |
|---|---|---|---|---|---|
| rodent | 161 | **145 (90%)** | 144 | 143 | 43 |
| human | 323 | 8 (2%) | 8 | 8 | 3 |

The **rodent corpus is the population**: rodent behavioural neuroscience reports its numbers
in bar/line charts, while the human cognitive-training RCTs report in tables (only 8 figure
rows). Characterisation of the 145 figure-derived rodent rows:

- **Direction**: 109 higher-better, 36 lower-better (latency/errors -- a field, never a
  mutated landmark).
- **Dispersion**: 140 "Reported", 5 "Imputed" (the imputed rows are *not* figure reads and
  are excluded from any transfer measurement).
- **Domain**: Spatial L&M 65, Recognition 34, Fear/Associative 33, Working Memory 11, Exec 2.
- **Control N**: median **10**, range 4-24 -- i.e. the corpus is dominated by exactly the
  short-n studies where a b% cap error -> ~2b% variance error -> ~sqrt(n) mis-weighting bites
  hardest.

### Can we obtain the actual figure images? Yes -- 100% of the articles.

`resolve_pdfs.py` maps each article's DOI to a local Zotero PDF (read-only SQLite: DOI ->
parent item -> child PDF attachment -> `storage/<key>/<file>`):

- **43 / 43 figure-derived articles resolve to a local PDF** (`pdf_map.json`).
- PDFs render + crop cleanly with PyMuPDF (`render.py`); panels are located by caption
  text-search and cropped at 300-600 dpi.
- **143 / 145 rows name a specific panel** in `Data_Source` ("Figure 2B", "Figure 3c"), so the
  crop target is already specified by the coding -- no guesswork about *which* panel.

**Obtainable-panel count, stated honestly.** Availability is *not* the constraint: all 43
PDFs and all 143 named panels are in hand. The binding constraints surfaced in the pilot are
per-panel **readability** and **row-to-bar matching**:

- ~4 of every 5 sampled panels are bar/line charts with legible error bars (directly
  scorable). The remainder are dot/scatter plots with median+IQR (e.g. Kazlauckas Fig 4) or
  grouped 3-series bars -- readable but a different channel/harder match.
- Matching a coded row to a specific bar sometimes fails: **Kazlauckas2011 Fig 3A** was
  excluded because its coded Ns (23/28) do not correspond to any bar group in the figure
  (12/13/11/15) -- a genuine provenance ambiguity, not a rendering problem.

Realistic scorable yield: **~110-130 of the 145 rows** after excluding scatter/median-IQR
panels, imputed-SD rows, and unmatched-N rows. That is a committee-grade N gated only by
per-panel reading labor, not by data access.

**Do the dissertation's WebPlotDigitizer projects survive?** **No.** No `.tar`/WPD project
files, no saved axis-calibration pixels exist anywhere in the dissertation repo -- only the
coded numbers and the panel labels survive. So there is **no saved-calibration shortcut**;
each panel must be re-calibrated from its axis ticks. The granular `Data_Source` panel labels
are the substitute worklist that makes matching tractable.

---

## 2. What the harness does (method)

For each obtainable `(panel image + coded control/intervention mean,sd,n,Direction)`:

1. **`render.py`** rasterises the PDF page (300-600 dpi) and crops the panel;
   **`grid_overlay.py`** overlays a labeled pixel grid so landmark/tick pixels are read
   precisely and **auditably** (the picked coordinates are stored, not just an opaque number).
2. A **vision reader** (here a genuine model-in-the-loop read -- the same `tool_output` slot a
   trained detector or a WPD/human export would fill) records, in `vision/<id>.json`: the 4
   axis-reference pixels and, per bar, the `{top, cap}` pixels.
3. **`score_real.py`** flows those pixels through the **shared affine**
   (`harness/calibrate.py`, byte-verified `== window.figureExtractor.calibrate`) ->
   `bar-top -> mean` (central channel, a long pixel distance) and `|cap-top| -> dispersion`
   (error-bar channel, a short pixel distance). Dispersion **type** is resolved from text/
   convention (these papers plot mean +/- **SEM**), so extracted `SD = cap_units * sqrt(n)`;
   the % transfer gap on the dispersion channel is invariant to that choice (the sqrt(n)
   cancels), which only affects the absolute SD fed to `escalc`.
4. **`golden_diff.R`** runs metafor `escalc(SMD)` + `rma` on **both** the coded and the
   extracted numbers through the **identical** pipeline, so the only thing that differs
   between the two pooled fits is the figure-reading.

The reader used a **zoom-assisted** read (re-cropping the bar top + cap at 2-3x when a
significance asterisk sat over the cap). This is the realistic "careful digitizer" condition,
and the zoom step is itself a finding (below).

---

## 3. Pilot results (6 panels, 3 articles, 16 bars, 8 comparisons)

Panels: Gobeske2009 Fig 1A (Y-maze, n=8-10); GarciaCapdevila2009 Fig 1A/1B (NOR discrimination
index, n=20, one-sided SEM); Bonaccorsi2013 Fig 1B 1-/10-/20-day probes (MWM time-in-zone,
n=5). Span: n=5..20, cap length 1.2..7.3 data-units, 3 cognitive domains, both Directions.

### Headline -- dispersion-first (`out/summary.json`, `out/fields.csv`)

| channel | median % | worst % | n |
|---|---|---|---|
| central tendency (bar mean) | **0.47** | 2.77 | 16 |
| **dispersion (error-bar -> SD)** | **3.67** | **18.11** | 16 |

- **Central tendency is nearly free on real figures too** -- every bar mean recovered within
  2.8% (median 0.47%), because the bar top is a long pixel distance.
- **Dispersion is again the load-bearing channel** (3.67% median, 18% worst), and it breaks
  worst on the **shortest caps**, exactly as the synthetic benchmark predicts:
  - Gobeske day-10 cap (coded SEM 1.34u): **18.1%**
  - Bonaccorsi 20-day EE cap (coded SEM 1.37u): **14.2%**
  - GarciaCapdevila 72h SED cap: 12.5%

### The synthetic -> real transfer gap on the dispersion channel is ~0

| tool / corpus | central median | dispersion median | dispersion worst |
|---|---|---|---|
| synthetic `human_floor` (1px click jitter) | 0.44 | 3.89 | 27.7 |
| synthetic `cv_autoreader` | 0.45 | 8.89 | 21.5 |
| synthetic `vision` (agent, n=1) | 1.17 | 8.20 | -- |
| **real pilot (this, zoom-assisted vision)** | **0.47** | **3.67** | **18.1** |

**Delta = M(real) - M(synthetic human_floor@1px) = +0.03pp central, -0.48pp dispersion.**
The real-figure dispersion error sits *inside* the synthetic-predicted envelope -- the error
structure the synthetic benchmark located **transfers to real journal figures**: central
tendency ~free, dispersion the concentrated failure, worst on short caps.

### End-to-end golden diff -- the pooled estimate survives (`out/golden_diff.txt`)

`escalc(SMD)` + `rma` on coded vs extracted, identical pipeline:

```
CODED      g=+0.487  SE=0.592  95% CI [-0.672, +1.647]  p=0.410
EXTRACTED  g=+0.475  SE=0.600  95% CI [-0.702, +1.652]  p=0.429
delta(pooled g) = -0.0125   |   per-study |g_ext-g_coded|: median 0.017, max 0.078
sign flips: 0 / 8
```

Swapping the human's figure digitization for the automated read moves the pooled Hedges g by
**-0.013 (~2.5% of the estimate)**, leaves the CIs essentially co-incident, and flips **no**
effect signs. The dispersion-channel error is real and localized, but at these sample sizes it
does not overturn the meta-analytic conclusion of the pilot studies. (Wide CIs = 3 single-
domain articles; the point is the coded-vs-extracted *agreement*, not the effect itself.)

### A concrete realism-gap finding: significance markers corrupt a naive cap read

On every panel the error-bar cap sits directly under a `*`/`**` significance marker. A one-
shot read latches onto the asterisk and **over- or under-shoots the cap by 30-45px**, inflating
the dispersion error to 22-36% (e.g. Bonaccorsi SC 1-day: 36% before, 6% after). Re-cropping
the cap at 2-3x disambiguates it. This is exactly the "hand-drawn error bars / unlabeled caps"
gap the README predicts, and it is the kind of failure a **sub-pixel specialist detector**
(trained to ignore significance glyphs) is built to remove and a general VLM is not.

---

## 4. Honest limitations (what this pilot is and is not)

1. **Reference = human coding, not ground truth.** On real figures there is no independent
   pixel truth: both the automated reader and the human coder read the *same* chart. This
   experiment therefore measures **agreement / transfer**, not accuracy. The *accuracy* claim
   ("more precise than a human on the dispersion channel") is established on the **synthetic**
   benchmark against R's exact descriptives; this pilot shows that error *structure* survives
   on real figures. The two are complementary and must be reported as such.
2. **The reader is a general vision model with zoom, not yet a trained detector.** This pilot
   delivers the *agent/VLM real-figure baseline* and confirms the dispersion gap exists on real
   figures -- it does **not** yet show a detector *beats* the agent. That is Stage 1 (below),
   for which this harness is the eval bed.
3. **N is small** (8 comparisons, 3 articles) -- a pilot, not the flagship. Pooled CIs are wide.
4. **Provenance friction is real and documented**: the SD lives in different columns across
   articles (`Control_Group_SD` vs `Control_Group_Variance_Value`; "Enriched" aliases are
   study-level constants), dispersion **type** is inferred from convention + a
   `coded_SD/sqrt(n)` cross-check rather than always stated, and one sampled panel could not be
   matched by N. These are exactly the human-gate items the pipeline routes to review.

---

## 5. What it takes to scale to a committee-grade N

1. **Reading throughput.** Each panel is ~1 render + 1-2 zoom crops + ~4-8 pixel picks. The
   43 PDFs + 143 named panels are already resolved; producing `tasks/` + `vision/` for
   ~110-130 scorable rows is the labor. Two accelerators: (a) an **automated cv-reader for real
   bars** (extend `harness/tools_cv.py` with asterisk-suppression) to pre-fill `vision/` and
   have the human only confirm; (b) dispatch the vision reads as **parallel agent jobs** (one
   panel per agent) rather than serially.
2. **Two independent readers** per panel (agent + a careful human WPD click) to turn "transfer
   gap" into an inter-reader **accuracy envelope** and quantify the human's own dispersion
   jitter on real caps -- the white-paper's backbone.
3. **The full 3-level golden diff.** With ~120 rows across 43 articles, run the dissertation's
   actual `rma.mv(~1 | article/row)` on coded vs extracted and report movement in pooled g, CI,
   **tau^2 / I^2**, and per-study weight -- the pilot's `golden_diff.R` already does this and
   falls back to `rma` only when a single article makes the multilevel model singular.
4. **Then, and only then, the detector.** Train the specialist landmark detector on the free
   synthetic GT and run it through *this* harness against the same real panels. The model is
   justified iff it closes the real-figure dispersion gap (the 18% worst-case short-cap error,
   and the pre-zoom asterisk failures) that the agent leaves open. Until that delta exists, the
   honest call stands: **agent-driven digitization + a human dispersion-type gate now.**

## Reproduce

```bash
cd benchmark/real
python3 inventory.py         # population.json + articles.json (feasibility table)
python3 resolve_pdfs.py      # pdf_map.json (Zotero DOI -> local PDF; 43/43)
python3 render.py locate <Article> [--fig N]      # find the panel's page
python3 render.py render <Article> --page P --dpi 600 --crop x0,y0,x1,y1 --out p.png
python3 grid_overlay.py panels/p.png              # labeled grid for auditable pixel picks
# hand-author tasks/<id>.json (coded targets, pulled from population.json) + vision/<id>.json
python3 score_real.py        # out/fields.csv, comparisons.csv, summary.json (dispersion-first)
Rscript golden_diff.R        # out/golden_diff.txt  (escalc/rma coded vs extracted)
```
