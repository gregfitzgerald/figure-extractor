# Series / group parsing -- the missing perception layer

**What this measures.** Perception of a scientific figure decomposes into three jobs.
Two were already measured in this benchmark: **classify** (what kind of chart is this --
at ceiling, `WHITE-PAPER-LOG.md` §8) and **localize** (where are the marks -- the
dispersion problem, §2-3). The third was not measured at all:

> **Parse** -- *which marks belong to which series/group, and what does the legend call
> each one?*

A grouped bar chart is not one series: it is "Control vs Run" nested inside "2/4/8
weeks". A scatter may carry two IVs as two colours or two shapes. Until that structure
is recovered, a correctly-read mean+SD **has no home**. And a mis-assignment is the
third *silent catastrophic* error class (§9): a correct number attached to the wrong arm
computes the effect backwards or mixes conditions, and nothing downstream catches it.
That is why the headline here is a **mis-assignment rate**, not an accuracy.

---

## The answer key already existed -- this exports it

`benchmark/r/generate.R` already draws dodged, stacked and multi-series charts *from
labelled data*, so R already knows every mark's series and group. `gen_series.R` exports
that answer key, plus the piece that was genuinely new: **legend geometry**.

After ggplot2 renders and `grid.force()` materialises the viewport tree, every legend key
lives in a viewport named `key-<r>-<c>-bg` and every legend label in `label-<r>-<c>`.
Seeking those and calling `grid::deviceLoc` yields the swatch and label pixels in the same
top-left convention `rgt.R` uses for marks, and the label **string is read off the drawn
text grob** rather than assumed. Verified against right / top / inside / reversed /
shape-only legends (`sgt.R:legend_geometry`).

Two deliberate design choices keep the key trustworthy:

- **Mark -> series binding is recovered from the DRAWN AESTHETICS** (the dodged x, and the
  `fill`/`colour`/`shape` in `ggplot_build()$data`), never from row order -- so the key
  cannot silently drift if ggplot reorders layer data. Every builder asserts full arm
  coverage and dies rather than emit a partial key.
- **Occlusion is measured, not asserted**: `occlusion_index` reports the fraction of marks
  with a *different-series* mark inside two marker radii, and the bucket
  (none/moderate/severe) is derived from it.

`benchmark/r/rgt.R`, `generate.R` and `harness/` are **untouched**; the base extraction
corpus still generates byte-identically (checked), and `harness/score.py --tool
geometry_floor` still returns 0.00%.

### The GT bundle -- `corpus/<id>.sgt.json`

```jsonc
{
  "id": "gbar_3x4_med_02", "engine": "ggplot2", "chartType": "grouped-bar",
  "difficulty": "medium",                    // a-priori label
  "cueType": "color+position",               // color | shape | color+shape | color+position
  "legendStyle": "top",                      // right | top | inside | direct-labels
  "legendOrderMatchesPlotOrder": true,       // false = the classic trap; null = no legend
  "occlusion": { "index": 0, "medianNearestOther": 56.47, "bucket": "none" },
  "flags":  ["categorical-x", "overlapping-series"],   // CHAR_VOCAB.flags ONLY
  "traits": [],                                        // new stratifiers, kept OUT of flags
  "render": { "width":660, "height":470, "dpi":110, "alpha":1, "panelBg":"#FFFFFF", "seed":202 },

  "groups": [ { "groupId":"g0", "index":0, "label":"D1",
                "centerPx": {"px":146.91,"py":439.65} }, ... ],     // the x-axis clusters
  "series": [ { "seriesId":"s0", "index":0, "label":"Vehicle",
                "colorHex":"#1B9E77", "shape":null, "linetype":null,
                "legendIndex":0,                                    // order in the legend
                "plotOrderIndex":0,                                 // order in the plot
                "legendKeyPx":  {"px":221.16,"py":31.46},           // the swatch
                "legendLabelPx":{"px":261.93,"py":31.46},           // the text
                "legendLabelText":"Vehicle" }, ... ],               // read off the grob

  "marks": [ { "markId":"m017", "role":"top",                       // top|cap|pt|seg|q1|med|q3
               "groupId":"g0", "group":0,
               "seriesId":"s0", "series":"Vehicle",
               "px":109.58, "py":309.08, "value_x":0.733, "value_y":154.8 }, ... ],

  "descriptives": { "g0|s0": { "n":13, "mean":154.8, "sd":37.74, "sem":10.47,
                               "median":157.62, "q1":133.56, "q3":175.14, "ci_half":22.81, ... } },
  "calibration": { "calPixels": {...}, "calVals": {...} },          // feeds the tool's affine
  "panelPx": {...}, "image": "gbar_3x4_med_02.png"
}
```

`markId`s are assigned in a **seeded-shuffled order at generation time**, so the order in
which marks are listed leaks nothing about grouping. Stacked-bar marks additionally carry
`segTopPy`/`segBotPy`/`segTopValue`/`segBotValue` so a segment's value survives the parse.
Direct-labelled series carry `directLabelPx`/`directLabelText` in place of legend fields.

This slots into the `VISION-MODEL-METHODOLOGY.md` §19a contract directly: **the model
outputs structure** (`marks[].groupId/seriesId` + the swatch pixel), **the agent binds
meaning** (`legendLabelText` -> which arm is Control). `chartType` and `flags` are
validated live against the tool's own `CHAR_VOCAB` at task-build time, so a passing
prediction is by construction a valid tool input.

### GT verified against the pixels (`audit_series.py`)

The key is checked from the PNG alone, with no help from R:

| check | base tier | stress tier |
|---|---|---|
| marks with ink at the GT pixel | **495/495 = 1.000** | **229/229 = 1.000** |
| colour-cued marks whose ink IS the claimed series, at the exact pixel | 379/389 = 0.974 | 114/116 = 0.983 |
| ... claimed colour present but overdrawn (real occlusion) | 9 (2.3%) | 2 (1.7%) |
| ... **hidden** entirely under another series | 1 | 0 |
| legend swatches carrying their series' own colour | **53/53 = 1.000** | **22/22 = 1.000** |

The audit also writes `corpus/visibility.json` (per mark: `visible` / `occluded` /
`hidden`), so the scorer can report the mis-assignment rate with and without marks that
are *physically unreadable*. Building this check caught two real bugs in my own audit --
alpha-blended marker colours land nearer a **neighbouring** hue than their own, and
ggplot2 draws guide keys through the layer alpha too. Both were fixed by compositing
against the recorded `render.alpha` / `render.panelBg`.

---

## The corpus (19 charts, 495 marks, base tier)

| chart | type | S x G | marks | cue | legend | occlusion | legend order == plot order | traits |
|---|---|---|---|---|---|---|---|---|
| `gbar_2x3_easy_01` | grouped-bar | 2 x 3 | 12 | color+position | right | none (0.00) | yes | - |
| `gbar_3x4_med_02` | grouped-bar | 3 x 4 | 24 | color+position | top | none (0.00) | yes | - |
| `gbar_3x4_simhue_hard_03` | grouped-bar | 3 x 4 | 24 | color+position | right | none (0.00) | yes | low-contrast |
| `gbar_2x4_revlegend_hard_04` | grouped-bar | 2 x 4 | 16 | color+position | right | none (0.00) | **NO** | legend-order-mismatch |
| `gbar_3x3_inside_med_05` | grouped-bar | 3 x 3 | 18 | color+position | inside | none (0.00) | yes | - |
| `sbar_3x4_med_06` | stacked-bar | 3 x 4 | 12 | color+position | right | none (0.00) | yes | - |
| `sbar_4x3_simhue_hard_07` | stacked-bar | 4 x 3 | 12 | color+position | top | none (0.00) | **NO** | low-contrast, legend-order-mismatch |
| `line_3s_easy_08` | line | 3 x 5 | 30 | color | right | **severe (0.50)** | **NO** | - |
| `line_6s_cross_hard_09` | line | 6 x 6 | 36 | color | right | moderate (0.33) | **NO** | many-series |
| `line_4s_direct_med_10` | line | 4 x 6 | 24 | color | **direct labels** | moderate (0.25) | n/a | no legend |
| `line_3s_shape_med_11` | line | 3 x 6 | 18 | **shape** | right | moderate (0.22) | **NO** | monochrome |
| `line_3s_revlegend_hard_12` | line | 3 x 5 | 15 | color | right | **severe (0.40)** | **NO** | legend-order-mismatch |
| `scat_2s_color_easy_13` | scatter | 2 x 1 | 26 | color | right | none (0.00) | yes | - |
| `scat_2s_shape_med_14` | scatter | 2 x 1 | 26 | **shape** | right | none (0.08) | yes | monochrome |
| `scat_3s_colorshape_med_15` | scatter | 3 x 1 | 36 | color+shape | top | none (0.00) | yes | - |
| `scat_3s_simhue_hard_16` | scatter | 3 x 1 | 48 | color | right | none (0.04) | yes | low-contrast |
| `scat_4s_dense_hard_17` | scatter | 4 x 1 | 72 | color | right | moderate (0.35) | **NO** | dense-overlap |
| `scat_2s_inside_med_18` | scatter | 2 x 1 | 28 | color | inside | none (0.00) | yes | - |
| `dbox_2x3_med_19` | box | 2 x 3 | 18 | color+position | top | none (0.00) | yes | - |

Coverage: grouped bars 2-3 series x 3-4 clusters, stacked bars, multi-series line, scatter
separated by **colour** and separately by **shape**, a hard colour-only case with
near-identical hues, dense/occluded variants, legend outside vs inside, a direct-labelled
figure with **no legend**, and three charts where the **legend order does not match the
plotting order** (the classic trap).

---

## Metrics -- and why the headline splits in two

The scorer maps a reader's own series ids onto the GT's in **two different ways**, because
`WHITE-PAPER-LOG.md` §10 predicts the two halves of parsing have different owners:

- **STRUCTURE** (the candidate ML win): the permutation of reader-ids onto GT-ids that
  *maximises* agreement, plus the **ARI** of the partition. Label-free -- it asks only
  "did it carve the marks into the right clusters?"
- **NAMING** (agent work): having clustered correctly, did it read the legend and give each
  cluster the right *text*? Plus swatch localisation.
- **BOUND MIS-ASSIGNMENT** (**the headline**): the composition of the two -- the fraction of
  marks that end up attached to the **wrong named arm**. This is the quantity a
  meta-analysis actually suffers from.
- **END-TO-END**: each mark's GT pixel is pushed through the *same affine the tool uses*
  (`harness/calibrate.py`) and re-aggregated per arm **under the reader's assignment**.
  Localization is held perfect on purpose, so any error is pure parsing. Reported as
  per-arm mean/dispersion % error vs R's descriptives -- and as the **effect sign-flip
  rate**: did Control-vs-Treated come out backwards?

Stratified by chart type, a-priori difficulty, cue type, measured occlusion, legend style,
trait, and legend-order-mismatch.

### The scorer is validated before it is trusted (`score.py --selftest`)

Three synthetic readers prove each metric fires *independently*:

| synthetic reader | bound mis-assign | structural mis-assign | ARI | naming | **effect sign flips** | ill-formed arms |
|---|---|---|---|---|---|---|
| **oracle** (the GT itself) | 0.0000 | 0.0000 | 1.000 | 57/57 | **0/145** | 0 |
| **swapped** (perfect clusters, two legend labels exchanged) | **0.3798** | 0.0000 | 1.000 | 37/57 | **44/145 = 0.303** | 0 |
| **noisy** (perfect labels, 15% of marks scattered) | 0.1677 | 0.1677 | 0.559 | 57/57 | 3/103 = 0.029 | **41** |

The oracle row is also a validation of the whole chain: GT pixels -> the tool's affine ->
R's descriptives round-trips at **1.8e-09 %** central / **4.7e-08 %** dispersion error.

**This table is itself a finding.** A pure *naming* error is far more dangerous than a
structural one. The swapped reader looks perfect on every structural metric (ARI 1.00) and
produces **10x the sign flips** of the noisy reader, because its arms are clean, plausible
and backwards. The noisy reader's damage mostly shows up as 41 **ill-formed arms** -- an
inconsistency a pipeline can detect and refuse. Silent-and-wrong beats loud-and-wrong.

---

## First pass -- a genuine vision read (base tier, 19 charts / 495 marks)

Five independent vision readers were dispatched on the **leak-free, anonymised** tasks
(`tasks/img/fig_XXXX.png`; `anon_map.json` is scorer-only), each given the image and the
mark coordinates, and *forbidden* from opening the corpus or programmatically sampling
pixel colours. All 19 charts / 495 marks were returned, all `method:"visual"`.

### Headline

| metric | value |
|---|---|
| **series mis-assignment rate (bound)** | **0.0000 -- 0 of 495 marks** |
| group mis-assignment rate | 0.0000 |
| arm (group x series) mis-assignment rate | 0.0000 |
| structural mis-assignment / mean ARI | 0.0000 / **1.000** |
| legend label read correctly | **57/57 = 1.000** |
| swatch localisation | median **1.3 px**; 57/57 within 20 px |
| nSeries exactly right | **19/19** |
| nGroups exactly right | **19/19** |
| **effect sign flips** | **0 / 145 comparisons** |
| per-arm central / dispersion error (end-to-end) | 0.00% / 0.00% |
| arms lost / ill-formed | 0 / 0 |
| abstention rate | 0.000 |
| calibration | mean conf 0.956 vs accuracy 1.000 (**under-confident 0.044**), ECE 0.044 |

Every stratum is 0.000: all five chart types, all three difficulty levels, every cue type
(colour, shape, colour+shape, colour+position), every occlusion bucket **including
`severe`**, every legend style **including inside-panel and direct-labelled**, and all
three legend-order-mismatch traps.

**State the bound honestly.** 0/495 is not "zero error", it is *no error observed*. By the
rule of three the 95% upper bounds are **0.61% per mark**, **5.3% per legend label**,
**2.1% per effect comparison**, and **15.8% per chart**. The base corpus therefore does not
locate the ceiling; it only establishes that the ceiling is above it.

### The readers' uncertainty tracks an annotation they never saw

The strongest evidence that this is genuine perception rather than leakage: reader
confidence lines up with `visibility.json`, which is computed by an independent pixel audit
the readers had no access to.

| audited visibility | n | mean per-mark confidence |
|---|---|---|
| visible | 485 | 0.958 |
| occluded (overdrawn) | 9 | 0.868 |
| **hidden** (fully covered) | 1 | **0.600** |

The single lowest-confidence mark in the entire corpus is exactly the one mark the audit
independently flagged as physically hidden (`line_3s_revlegend_hard_12/m003`) -- and the
reader still got it right, by inferring the point's series from the *line* passing through
it, which a marker-only detector could not do. The readers' free-text notes corroborate:
they flagged the 1.75 px occluded pair in `scat_4s_dense_hard_17`, the 0.4 px Beta/Gamma
overlap in `line_3s_revlegend_hard_12`, the purple error-bar stem that defeats naive
nearest-top cap pairing in `line_3s_easy_08`, and the reversed legend in
`gbar_2x4_revlegend_hard_04`. Every one is a real property of the GT.

### What the readers actually did (this matters for the interpretation)

They did **not** glance at a picture. They cropped and upscaled 8-20x, built contact sheets
of per-mark patches, and in one case built *seam montages* -- butting a point's 3x3 core
patch directly against a legend swatch patch so that a matching shade makes the seam
disappear. That loop cost 30-90 tool calls and ~70-90k tokens per batch of ~100 marks.

So the honest claim is not "VLMs parse series perfectly". It is: **an agent that is allowed
to inspect the image adaptively parses this corpus perfectly, at a cost of tens of
thousands of tokens per figure.** That distinction is exactly where the ML argument lives.

---

## Baseline: a deterministic colour-clustering parser (`cv_parser.py`)

To ask "would a series-aware detector head earn its place?", the natural comparison is a
hand-built stand-in for that head: sample the ink colour at each mark (role-aware probe),
mode-seed cluster the colours, inherit each error cap from its nearest central mark, and
recover x-groups by gap structure. It reads no text, so **it cannot name a series** -- and
that is the point, not a bug.

| reader (base tier) | bound mis-assign | structural mis-assign | ARI | naming | nSeries exact |
|---|---|---|---|---|---|
| vision agent (first pass) | **0.000** | **0.000** | **1.000** | **1.000** | **19/19** |
| `cv_cluster` (colour only, no text) | 1.000 *(names nothing)* | **0.143** | 0.748 | 0.000 | 13/19 |

Where the colour parser breaks, by stratum:

| stratum | structural mis-assign |
|---|---|
| cue = **shape** (monochrome) | **0.568** |
| trait = **low-contrast-series** | **0.321** |
| occlusion = **severe** | 0.244 |
| cue = colour | 0.125 |
| cue = colour+shape | **0.000** |
| cue = colour+position (bars/box) | 0.081 |

Read this carefully. The naive detector head fails **exactly where the agent does not**:
monochrome/shape-cued figures (it has no colour signal at all), near-identical hues, and
crossing lines where a cap must be bound to the right series. And its `bound` column is
1.000 not because its structure is bad but because **no amount of clustering produces a
number you can put in a data schema** -- the arm has no name.

---

## Stress tier -- pushing past the base corpus

Because the base corpus did not break the reader, a second tier was built to locate the
ceiling rather than merely bound it. Every cue is pushed past the base corpus, and the
tier lives in its own `corpus_stress/` + `tasks_stress/` so the base tier's task ids (and
therefore the first-pass predictions already scored) stay valid.

| chart | type | S x G | marks | cue | occlusion | legend order == plot order | traits |
|---|---|---|---|---|---|---|---|
| `stress_line_8s_dup_hue_21` | line | 8 x 6 | 48 | color+shape | **severe (0.42)** | **NO** | many-series, **repeated hues** |
| `stress_scat_6s_ramp_22` | scatter | 6 x 1 | 96 | color | moderate (0.29) | **NO** | low-contrast, dense-overlap, many-series |
| `stress_gbar_5s_grey_23` | grouped-bar | 5 x 4 | 40 | color+position | none (0.00) | yes | low-contrast (5-step grey ramp) |
| `stress_scat_3s_smallshape_24` | scatter | 3 x 1 | 45 | **shape** | none (0.04) | **NO** | monochrome, dense-overlap, 1.5 pt glyphs |

The first chart is the sharpest test: **only four hues for eight series**, so colour alone
is ambiguous by construction and the reader must jointly use filled-vs-open markers and
solid-vs-dashed lines. The second co-locates six clouds drawn from a sequential ramp with
~18 RGB units between neighbours, at alpha 0.8.

### The deterministic colour head collapses here

| reader (stress tier, 229 marks) | bound mis-assign | structural mis-assign | ARI | naming | nSeries exact |
|---|---|---|---|---|---|
| `cv_cluster` (colour only, no text) | 1.000 *(names nothing)* | **0.459** | **0.430** | 0/22 | **1/4** |

It saw 3 of 6 ramp series, 5 of 8 line series, and **1 of 3** shape-cued series -- against
14.3% structural mis-assignment on the base tier, it is at **45.9%** here. This is the
clearest statement of the ceiling on a colour-clustering "series head".

### The vision agent breaks -- and only in one place

| metric | stress tier |
|---|---|
| **series mis-assignment rate (bound)** | **0.0480 -- 11 of 229 marks** |
| abstention rate | 0.0437 (10 marks) |
| structural mis-assignment / mean ARI | 0.0480 / 0.930 |
| legend label read correctly | **22/22 = 1.000** |
| swatch localisation | median **0.7 px**; 22/22 within 20 px |
| nSeries / nGroups exactly right | **4/4** / **4/4** |
| effect sign flips | **0 / 67** |
| per-arm central / dispersion error, worst | 13.95% / 39.56% |

Per chart -- the failure is *entirely* concentrated:

| chart | bound mis-assign | ARI | labels | note |
|---|---|---|---|---|
| `stress_line_8s_dup_hue_21` (8 series, 4 hues, filled/open + solid/dashed) | **0.000** | 1.00 | 8/8 | severe occlusion, 48 marks |
| `stress_gbar_5s_grey_23` (5-step grey ramp) | **0.000** | 1.00 | 5/5 | |
| `stress_scat_3s_smallshape_24` (monochrome, 1.5 pt glyphs) | **0.000** | 1.00 | 3/3 | 15/15/15 split recovered |
| `stress_scat_6s_ramp_22` (6-level sequential blue, ~6 px markers) | **0.115** | 0.72 | 6/6 | + all 10 abstentions |

**Every one of the 11 errors and all 10 abstentions are on the sequential-ramp scatter.**
Repeated hues did not break it (the reader used filled-vs-open markers and solid-vs-dashed
lines to separate 8 series through severe crossings); a 5-step grey ramp did not break it;
1.5 pt monochrome glyphs did not break it. What broke it is **six levels of one hue at
marker size, drawn on top of each other** -- i.e. a colour discrimination near the
just-noticeable difference, contaminated by alpha blending at overlaps.

### The reader's own confidence perfectly isolates its failures

| the reader's per-mark confidence | n | correct | accuracy |
|---|---|---|---|
| conf > 0.5 | 133 | 133 | **1.000** |
| conf <= 0.5 | 86 | 75 | 0.872 |
| abstained (`"unknown"`) | 10 | -- | -- |

All 11 errors carried confidence **0.18-0.30**; not one mark above 0.5 was wrong. The
reader also abstained on exactly the marks where the visible pixel is an alpha blend of
two series rather than either one, and set a whole-chart confidence of **0.05** on the
ramp. This is textbook selective prediction: **a downstream gate that drops
`conf <= 0.5` recovers 100% precision at the cost of 39% coverage on that chart, and
costs nothing on the other three.** That, not a better classifier, is the practical fix.

Aggregate calibration looks poor (ECE 0.241, mean conf 0.669 vs accuracy 0.908) -- but the
error is *under*-confidence, in the direction that costs coverage rather than correctness.

### Head-to-head on the same four charts

| reader | structural mis-assign | ARI | nSeries exact |
|---|---|---|---|
| vision agent | **0.048** | **0.930** | **4/4** |
| `cv_cluster` (colour only) | 0.459 | 0.430 | 1/4 |

Per chart the colour head is at 0.667 (small shapes -- no colour signal at all), 0.531
(the ramp), 0.500 (repeated hues), 0.000 (grey bars). Even on the one chart where the
agent fails, the agent is **4.6x better** (0.115 vs 0.531) -- and it flags its failures,
which the colour head does not.

---

## Honest read: where the agent is enough, and where a detector head would earn its place

**Where a general agent already parses structure correctly.** On flat-colour synthetic
renders, given exact mark coordinates and permission to inspect the image adaptively, the
agent got **every** structural question right on the base corpus: counts, per-mark
assignment, the legend-order traps, inside-panel legends, direct labels, shape-only
monochrome cues, and severe line crossings. The stress tier extended that to 8 series
sharing 4 hues (separated only by filled/open markers and solid/dashed lines) through
severe crossings, a 5-step grey ramp, and 1.5 pt monochrome glyphs -- all still 0.000.
This mirrors and extends the classification result (§8): *perception of chart structure is
not the bottleneck on clean figures*. It further narrows the ML case.

**Where it actually breaks -- one failure mode, and it is a perceptual limit, not a
reasoning failure.** Six levels of a single sequential hue at ~6 px marker size, drawn
overlapping: **11.5% mis-assignment plus 10 abstentions on that chart alone**, and 0.000
everywhere else. This is a colour discrimination at the just-noticeable difference,
corrupted further by alpha blending where markers overlap -- for 10 marks the visible
pixel is genuinely a *blend of two series*, so no reader, model or human, can recover them
from that pixel. The failure is therefore partly **irreducible from the image**, which
matters: a detector head would not fix it either.

**Where the naming half sits, definitively.** Legend text -> label was 57/57, and the
deterministic parser scored 0/57 because it cannot read. §10's prediction holds without
qualification: **naming is agent work, and no bespoke model is needed for it.** More
importantly, the `swapped` self-test shows naming is also the *most dangerous* half --
a mis-read legend on a perfectly-clustered chart produced a 30% effect sign-flip rate while
every structural metric read perfect. If any gate is mandatory, it is a human/agent
confirmation of **swatch -> arm-name binding**, not of the clustering.

**Where a series-aware detector head would earn its place -- four specific claims:**

1. **Not on accuracy.** The agent is at 0.000 on 19 base charts and on 3 of 4 stress
   charts; the naive colour head is at 14.3% (base) and 45.9% (stress) structural
   mis-assignment. A head would have to beat *zero* on almost everything, and on the one
   chart where the agent does fail it is still **4.6x better** than the head (0.115 vs
   0.531). The head is strictly dominated on this evidence.
2. **Not on the residual failure either -- abstention already covers it.** Where the agent
   errs, it *knows*: every mark it scored above 0.5 confidence was correct (133/133), all
   11 errors sat at 0.18-0.30, and it abstained on exactly the marks whose visible pixel is
   an alpha blend of two series. A confidence gate converts the failure into flagged
   coverage loss rather than silent corruption -- which is the whole point of the
   silent-catastrophic-error framing. Cheap, and available today.
3. **Plausibly on COST.** The agent's score was bought with an adaptive inspection loop --
   dozens of tool calls and 70-120k tokens per batch of ~100 marks; the 96-mark ramp chart
   alone took 51 tool calls and ~122k tokens. A head that emits `groupId`/`seriesId`
   alongside each detected landmark makes that loop unnecessary for the marks the cue
   already resolves, leaving the agent to adjudicate a flagged minority. **The measurable
   claim is tokens-per-figure at equal accuracy, and this harness can measure it.** That is
   a weaker but far more defensible argument than "the model is more accurate".
4. **Unknown, and the real question: on real journal figures.** Everything here is
   synthetic. The failure modes that would actually break an agent -- JPEG ringing that
   destroys hue identity, sub-100-dpi rasters where a 1.5 pt glyph is 3 pixels, legends
   rendered into a flattened bitmap, series distinguished by hatching -- are all absent.
   The transfer gap Delta = misassign(real) - misassign(synthetic) is **unmeasured**, and it
   is the only number that could still justify the head on accuracy grounds.

**What would change the conclusion.** Label ~50 real multi-series panels from the
dissertation corpus with this same schema and re-run. If the agent's bound mis-assignment
stays near 0 there too, the series head is dead on accuracy and survives only as a cost
optimisation. If it degrades on real ink, the head is justified -- and this harness will
already report it, stratified, with the effect sign-flip rate attached. The second, cheaper
experiment is the cost one: measure tokens-per-figure at matched accuracy, with and without
a structural pre-parse.

### Findings that belong in `WHITE-PAPER-LOG.md`

1. **§10 is now measured, and the answer is mostly negative for the ML case.** Agent bound
   mis-assignment **0/495 marks (95% UB 0.61%)** on the base corpus and **11/229 = 4.8%**
   on a deliberately adversarial stress tier, with legend naming 57/57 and 22/22 and
   **0/212 effect sign flips overall**. Structural parsing is *not* the bottleneck; §10's
   "genuine ML win" should be restated as a **cost** argument plus an **unmeasured
   real-figure transfer** argument, not an accuracy argument.
1b. **The single failure mode is worth naming precisely**: ~6 levels of one *sequential*
   hue at marker size, overlapping. Repeated hues disambiguated by glyph, grey ramps,
   1.5 pt monochrome glyphs and severe line crossings all parsed perfectly. The practical
   guidance that follows is about *figure design* as much as models -- a sequential palette
   for a categorical variable is the one pattern that defeats automated parsing.
2. **A new asymmetry worth its own paragraph in §9.** Naming errors and structural errors
   are not equally dangerous. Perfect clustering with two legend labels swapped produced
   **0.303** effect sign-flips with every structural metric reading perfect; 15% random
   structural noise produced **0.029** sign-flips and 41 detectably ill-formed arms.
   *The mandatory human gate belongs on swatch -> arm-name binding, not on clustering.*
3. **The naive detector head is worse than the agent, and fails in the complementary
   place**: 14.3% structural mis-assignment on the base tier (56.8% on shape-cued
   monochrome, 32.1% on low-contrast hues) and **45.9% on the stress tier** -- precisely
   the figures where the agent was flawless. A head must therefore be *shape- and
   glyph-aware*, not colour-clustering, or it will be strictly dominated.
3b. **Selective prediction is the cheap win, and it is already working.** On the stress
   tier every mark the agent scored above 0.5 confidence was correct (133/133), all 11
   errors sat at 0.18-0.30, and it abstained on exactly the alpha-blended marks. A
   confidence gate turns the residual parsing failure from silent corruption into flagged
   coverage loss -- the §9 remedy, available with no new model.
4. **Eval-integrity note (worth adding to §11).** Reader confidence correlated with a pixel-
   audit visibility annotation the readers never saw (0.958 visible / 0.868 occluded / 0.600
   hidden), which is a cheap, general **leak detector**: if a reader had the answer key its
   uncertainty would not track physical occlusion. Recommend adopting it as standard practice
   whenever a run comes back perfect.
5. **Method note.** R's grid viewport tree exposes legend swatch + label pixels *and the
   drawn label string* (`key-r-c-bg` / `label-r-c` + `deviceLoc`). Legend GT is therefore
   free and exact, like landmark GT -- this removes the last part of the parsing task that
   looked like it would need hand labelling.

---

## Files & how to run

```
benchmark/series/
  sgt.R             # legend geometry, aesthetic->series binding, occlusion index, mark shuffling
  gen_series.R      # corpus generator (base + --stress tier); sources ../r/rgt.R untouched
  audit_series.py   # verify the GT against the PNG; writes corpus*/visibility.json
  make_tasks.py     # leak-free ANONYMISED tasks; validates labels against the tool's CHAR_VOCAB
  cv_parser.py      # deterministic colour-clustering baseline (structure only, names nothing)
  score.py          # the scorer + --selftest
  corpus/  corpus_stress/     # <id>.png, <id>.sgt.json, visibility.json, manifest.json
  tasks/   tasks_stress/      # fig_XXXX.json + img/fig_XXXX.png, anon_map.json (scorer-only)
  predictions/                # firstpass.jsonl, cv_cluster.jsonl, summary_*.json
  RESULTS.md
```

```bash
Rscript benchmark/series/gen_series.R                       # 1. base corpus  (19 charts, 495 marks)
Rscript benchmark/series/gen_series.R --stress              #    stress tier  (4 charts, 229 marks)
python3 benchmark/series/audit_series.py                    # 2. verify GT vs pixels (+ visibility.json)
python3 benchmark/series/audit_series.py stress
python3 benchmark/series/make_tasks.py                      # 3. leak-free anonymised tasks
python3 benchmark/series/make_tasks.py --tier stress
python3 benchmark/series/score.py --selftest                # 4. validate the scorer itself
python3 benchmark/series/cv_parser.py                       # 5. deterministic baseline
python3 benchmark/series/score.py --run cv_cluster
# 6. a vision agent Reads tasks/img/fig_XXXX.png + tasks/fig_XXXX.json and appends one
#    JSON line per chart to predictions/<run>.jsonl (schema in the task's output_schema)
python3 benchmark/series/score.py --run firstpass           # 7. score the genuine read
python3 benchmark/series/score.py --tier stress --run firstpass_stress
python3 benchmark/series/score.py --tier stress --run cv_cluster_stress
```

Corpora are seeded and regenerate **byte-identically** (checked); anonymised task ids are
seeded too, so re-running `make_tasks.py` does not invalidate predictions already scored.
Each tier owns its own corpus/task directories precisely so that adding a tier cannot
renumber another tier's task ids.
