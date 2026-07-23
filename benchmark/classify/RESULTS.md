# Chart-type classification — the perception gate (first pass)

**What this measures.** Before an extraction agent can read a figure's *scientific
content*, it must reliably classify what the figure **is**: chart type, provenance
(the study's own data vs. a summary of *other* studies), axis scale, whether
dispersion is drawn, and which ink is non-data. Classification is the gate that must
pass before extraction is even attempted (`VISION-MODEL-METHODOLOGY.md` §19a: the
vision model *classifies + locates*; the agent, reading the caption/methods, decides
what the numbers *mean*). This corpus + scorer is the eval bed for that gate.

Labels are the **exact `CHAR_VOCAB` taxonomy** parsed at build time from
`figure-extractor.html` (22 `charType`, 8 `scale`, 3 `dataProvenance`, 12
`nonDataElement`), so a passing prediction is, by construction, a valid tool input.

## The corpus

80 images, generated seeded by `gen_classify.R`, **no landmark-pixel GT needed** —
each image carries a `<id>.label.json` with `charType`, `library`, `grammar`, `tier`,
`dataProvenance`, `scaleX/scaleY`, `dispersionPresent` (bool), and the
`nonDataElements` actually drawn.

| dimension | coverage |
|---|---|
| **chart types (18)** | bar (4), grouped-bar (6), stacked-bar (4), histogram (4), box (6), violin (4), scatter (6), line (4), dose-response (4), kaplan-meier (4), forest (6), funnel (4), roc (4), bland-altman (4), pie (6), heatmap (6), schematic (2), flow-diagram (2) |
| **tiers** | 40 **plain** / 40 **dense** (every figure rendered both ways) |
| **libraries (12)** | base (26), ggplot2 (26), lattice (8), metafor (4), forestplot (2), forestploter (2), pheatmap (2), corrplot (2), plotrix (2), pROC (2), survival (2), vioplot (2) |
| render failures | **0 / 80** |

The **dense tier** is loaded with axis titles, rich legends, significance
stars/brackets, per-group n annotations, panel labels (A–F), data-value labels,
gridlines, and reference lines — visually busy, to stress-test robustness. Provenance
is honest to the plot semantics: forest/funnel are `derived` (they summarize *other*
studies); schematic/flow-diagram are `unknown`; everything else is `primary`.

## R-library inventory (what rendered, what failed)

Confirmed present + used: **base graphics, ggplot2, lattice, metafor** (forest +
funnel), **forestplot, forestploter, pheatmap, corrplot, plotrix** (3D pie), **pROC**
(ROC), **survival** (`plot.survfit` KM), **vioplot, cowplot/patchwork,
RColorBrewer/viridisLite/scales**. Installed on top of the base image this session:
`plotrix, pROC, pheatmap, corrplot, vioplot, beeswarm, ggbeeswarm`. **Failed to
install:** `ggpubr` (needs `car`/`lme4` compilation, which failed) — not required;
significance stars/brackets are drawn directly in ggplot2/base instead. This spans
three genuinely different visual grammars (base vs ggplot vs lattice look nothing
alike) plus eight specialist packages — the visual variety is the point.

## First-pass classifier

A genuine vision read: the classifier is handed **leak-free, anonymised** tasks
(`make_tasks.py` copies each `<id>.png` to `tasks/img/img_XXXX.png` under a shuffled
name, so the chart type cannot be read off the filename; `anon_map.json` is
scorer-only) and returns `charType` + `confidence` + the aux labels, blind. All 80
images were classified.

### Headline metrics (`score.py --run firstpass`)

| metric | value |
|---|---|
| charType accuracy | **1.000 (80/80)** |
| macro-F1 / weighted-F1 | **1.000 / 1.000** |
| priority-flip rate (forest→bar-style routing errors) | **0 / 80** |
| calibration: mean-confidence vs accuracy | 0.928 vs 1.000 (**under-confident by 0.07**) |
| ECE | 0.072 |
| abstention (unknown/other) used | 0 / 80 |
| dataProvenance accuracy | 1.000 |
| scaleY / scaleX accuracy | 1.000 / 1.000 |
| dispersionPresent (bool) F1 | 1.00 (TP37 FP0 FN0 TN43) |
| nonDataElements micro-F1 (ignore-list) | 0.99 |

**Confusion matrix: empty.** No chart type was confused for another. In particular
the two *costly* confusions the methodology flags — **forest→bar** (flips extraction
priority from derived/low to primary/high) and **funnel→scatter** — did **not** occur:
the derived-vs-primary grammar (forest study rows + summary diamond; funnel's inverted
standard-error axis) was perceptible in every case, so `dataProvenance` was 100%.

### Stratification — does the dense tier degrade accuracy?

| stratum | accuracy |
|---|---|
| **plain** tier | 1.000 (40/40) |
| **dense** tier | 1.000 (40/40) |
| base grammar | 1.000 (32/32) |
| ggplot2 grammar | 1.000 (26/26) |
| lattice grammar | 1.000 (8/8) |
| every specialist library | 1.000 |

**Visual busyness did not degrade chart-type classification.** Significance
stars, dual annotations, panel labels, and rich legends did not cause any type flip —
they were correctly bucketed into `nonDataElements` (micro-F1 0.99; the only misses
were an off-canvas significance bracket in one dense `vioplot` whose y-limit clipped it).

### The fragility frontier (where a *weaker* model would break)

The four lowest-confidence genuine calls — all correct, but the calls closest to a
flip — locate exactly where a smaller VLM will fail:

```
conf=0.85  funnel_base_plain        true=funnel        pred=funnel     (a bare funnel resembles a scatter)
conf=0.85  heatmap_corrplot_plain   true=heatmap       pred=heatmap    (a circle-glyph correlation matrix — heatmap vs "other")
conf=0.88  dr_base_plain            true=dose-response pred=dose-response (log-x sigmoid resembles a line/curve)
conf=0.88  dr_ggplot_plain          true=dose-response pred=dose-response
```

These are the honest hard cases: **funnel↔scatter**, **dose-response↔line**, and
**correlation-matrix-as-heatmap**. They are trivially separable in clean synthetic
form but are precisely the calls that real-figure noise (§ "honest limits") will erode.

## Harness self-test (the confusion machinery *does* fire)

Because the genuine run is clean, the scorer's structural machinery was validated on
an **injected-error** set (a forest→bar priority flip + a box→violin cheap confusion):

```
== confusions (2 errors) ==
     forest -> bar     x1   <-- PRIORITY FLIP
        box -> violin  x1   (same priority)
priority-flip rate: 1/6 = 0.167
calibration: mean conf 0.908 vs acc 0.667  ->  ECE 0.242   (over-confident + wrong)
```

The confusion matrix, the **priority-flip** flag (which reads the confusion *through
the tool's own `extractionPriority`* — box↔violin is cheap, forest→bar is
catastrophic), and the ECE penalty for confident-wrongness all behave correctly.

## Honest read — where classification is reliable vs where it breaks

- **Reliable now (bounded, not assumed):** on *clean, flat-color synthetic* renders,
  chart-type classification by a strong VLM is **at ceiling** across 18 types, 12 R
  libraries, three grammars, and a deliberately busy dense tier. The costly
  provenance-flipping confusions do not occur. This is the outcome
  `VISION-MODEL-METHODOLOGY.md` §3.4 predicted ("a small classification gap … the
  likely outcome"): the value and the error live **downstream**, in the dispersion
  channel and in real-figure transfer — not in perception of the chart *type*.

- **Calibration is mildly under-confident** (0.93 stated vs 1.00 actual). Harmless
  here, but the fix is to nudge confidences up on canonical grammars while *keeping*
  the 0.85 humility on funnel/correlation-matrix cases — those are the right places to
  be unsure.

- **Where it will break (unmeasured here):** this corpus *bounds* the ceiling; it does
  **not** prove reliability on real journal figures. The transfer gap — anti-aliasing,
  JPEG artifacts, hand-drawn/unlabeled error bars, overlapping ink, unlabeled or log
  axes, multi-panel composites that must be *segmented* before typing — is untested.
  The fragility frontier above (funnel↔scatter, dose-response↔line, box↔violin,
  forest↔grouped-bar) names the confusions to watch when real panels are added; the
  next step is to label real panels from the dissertation corpus and report
  **Δ = accuracy(synthetic) − accuracy(real)**, oversampling those hard pairs.

- **Eval-integrity note.** The anonymise-then-checksum design earned its keep on the
  first run: two rows were transposed at write time (`box_base_dense` ↔
  `line_base_plain`); the checksum cross-check proved the images were faithful copies,
  localising the slip to serialization rather than perception, and it was corrected.
  A naive filename-keyed eval would have silently mis-scored or hidden it.

## Files & how to run

```
benchmark/classify/
  gen_classify.R      # generate 80 PNGs + <id>.label.json + manifest.json   (R 4.1.2)
  make_tasks.py       # emit leak-free ANONYMISED tasks (imports CHAR_VOCAB from the tool)
  score.py            # score: accuracy, macro/weighted-F1, confusion+priority-flip, ECE, abstention, aux, strata
  corpus/             # <id>.png, <id>.label.json, manifest.json
  tasks/  img/        # img_XXXX.json + img_XXXX.png (blind), anon_map.json (scorer-only), tasks.jsonl
  predictions/        # firstpass.jsonl (vision reads), summary_firstpass.json
  RESULTS.md
```

```bash
Rscript benchmark/classify/gen_classify.R              # 1. build corpus (0 failures)
python3 benchmark/classify/make_tasks.py               # 2. emit leak-free anonymised tasks
# 3. a vision agent Reads tasks/img/img_XXXX.png and appends one JSON line per image to
#    predictions/<run>.jsonl:  {"task","charType","confidence","dataProvenance",
#                               "scaleX","scaleY","dispersionPresent","nonDataElements"}
python3 benchmark/classify/score.py --run firstpass    # 4. score (all metrics + strata)
```
