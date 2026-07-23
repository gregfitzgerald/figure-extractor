# R-GT: a benchmark for figure-data-extraction tools, with R as the ground-truth engine

This is the rigorous successor to `../bench/` (a Python-only quick harness). Its thesis:
**figure-extraction error is a serious, under-measured problem, and the error lives in the
dispersion (error-bar) channel** -- the variance-determining quantity that reweights every
study in a meta-analysis. This benchmark is built to expose that error precisely, and to be
the train/eval bed for a specialist chart-reading model.

## Why R is the ground-truth engine

Most chart benchmarks eyeball or reverse-engineer the "true" values from the image. Here the
truth is not read off the chart at all:

```
R simulates raw data  ->  R computes the FULL descriptives from that data  ->  R renders the
chart FROM that exact data  ->  R exports the device pixel coordinates of every drawn element
```

So the ground truth is *what R drew*, and the descriptives are *what R computed from the data it
drew* -- means, SDs, SEMs, medians, quartiles/IQR, min/max/range, 95% CIs, n, correlations,
regression slopes. A tool is scored on how close it gets to **R's descriptives**, never on an
eyeballed re-read. This closes the loophole that makes synthetic chart benchmarks too easy or
circular.

### The load-bearing R capability (proven, not assumed)

R can render a chart *and* recover the exact device-pixel coordinates of the drawn marks. The
method (in `r/rgt.R`), for ggplot2:

1. `ggplot_build(p)` -> `panel_params` give the expanded data ranges in the panel's native
   (transformed) coordinate space; `get_breaks()` gives the actual drawn axis ticks.
2. `ggplot_gtable` + `grid.draw` + `grid.force` render and materialize the viewport tree.
3. `seekViewport(panel)` + `grid::deviceLoc` on the panel's npc corners -> the panel's device
   rectangle in inches; `* DPI` and flip Y -> the panel rectangle in **top-left pixels** (to
   match the figure-extractor tool's pixel convention).
4. An affine maps any native data coordinate to a pixel; landmark positions are read straight
   from `ggplot_build()$data`, so dodge/stat/log transforms are already baked in.

**Verification.** `harness/audit_pixels.py` independently detects the drawn ink (bar fills,
scatter markers) from each PNG and compares to R's exported GT pixels: **median 0.44px, max
1.75px** residual across bars, points, and every multi-panel facet -- i.e. R's GT pixels sit on
the actual ink (residual = anti-aliasing at mark edges). The base-R fallback path is
`grconvertX/Y(..., "device")`; it is documented but unused because ggplot2 4.0 is installed.

## The GT bundle schema (the benchmark key)

One `corpus/<id>.gt.json` per figure (multi-panel emits one bundle per panel):

```jsonc
{
  "id": "bar_sd_clean_01", "engine": "ggplot2", "chartType": "bar",
  "tier": "clean|hard", "flags": ["log-axis", ...], "dispersionType": "SD|SEM|CI95",
  "render": { "width":620, "height":460, "dpi":110, "theme":"classic", "base_size":13, "seed":101 },
  "groups": ["Control","Run"], "series": null,
  "data":  { "Control": [195.77, ...raw obs...], "Run": [...] },          // the raw data R drew from
  "descriptives": {                                                       // R's authoritative stats
    "Control": { "n":12, "mean":217.65, "sd":32.48, "sem":9.38, "median":219.01,
                 "q1":198.12, "q3":233.81, "iqr":35.69, "min":..., "max":..., "range":...,
                 "ci95_lo":..., "ci95_hi":..., "ci_half":20.63, "var":1054.69 }, ... },
  "landmarks": [                                                          // GT pixels (top-left origin)
    { "role":"top", "group":0, "series":"s1", "px":216.39, "py":161.97, "value_x":1, "value_y":217.65 },
    { "role":"cap", "group":0, "series":"s1", "px":216.39, "py":136.75, "value_x":1, "value_y":238.28 }, ... ],
  "calibration": {                                                        // feeds figure-extractor.calibrate
    "calPixels": { "x1":{px,py}, "x2":{...}, "y1":{...}, "y2":{...} },     // pixels at 4 VISIBLE ticks
    "calVals":   { "x1":"0","x2":"1","y1":"0","y2":"300", "logX":false, "logY":false } },
  "panelPx": { "x0":..., "x1":..., "ytop":..., "ybot":... },              // panel rectangle in px
  "image": "bar_sd_clean_01.png"
}
```

Landmark `role`s: `top`/`cap` (bar & line: central mark + upper error cap), `q1`/`med`/`q3`/
`whislo`/`whishi` (box), `pt` (scatter). Calibration references are the **actual drawn axis
ticks** (what a real digitizer clicks), so the vision task is realistic.

## Complexity / realism knobs (`r/generate.R`)

Each builder is parameterized so realism is a dial, not a fixed style:

| knob | values exercised |
|---|---|
| chart type | grouped bar, box, scatter+regression, line/dose-response, multi-panel facet |
| dispersion type | **SD, SEM, CI95** (the cap length -- and thus its pixel leverage -- differs) |
| theme / font | `theme_classic/bw/minimal/gray`, `base_size` (font scale) |
| DPI / size / aspect | 96-150 dpi, per-chart width/height |
| gridlines / legend | on/off, legend position |
| hard flags | `log-axis`, `raw-points-present` (per-animal dot overlay), `overlapping-series` (dodged), `small-caps`, `multi-panel` |
| n per group | randomized 6-26 (drives SEM/CI cap length) |

Adding a chart type = one builder function that returns a bundle via the `rgt.R` helpers.

## The tool-comparison harness (`harness/`)

A **common interface** makes any extraction tool commensurable. A tool is a function
`bundle -> tool_output`:

```
tool_output = { "calPixels": {x1,x2,y1,y2:{px,py}},   # 4 axis-reference pixels the tool picked
                "calVals":   {x1,x2,y1,y2,logX,logY},  # their known values (from the task)
                "landmarks": [{role, group, series, px, py}] }  # picked landmark pixels
```

Every tool's pixels flow through the **same affine** (`harness/calibrate.py`, a byte-faithful
port of the tool's `computeCalibration` -- verified `== window.figureExtractor.calibrate` to
0.000e+00 over 184 points by `harness/crosscheck_js.py`). Tools therefore differ *only in the
pixels they pick*, never in the arithmetic -- the tool's own design invariant (vision perceives,
deterministic code does the math).

Built-in tools:

| tool | what it is | role |
|---|---|---|
| `geometry_floor` | GT's own calibration + GT landmark pixels (perfect clicks) | theoretical manual ceiling; also validates the GT round-trips to R's numbers (0%) |
| `human_floor` | GT pixels + Gaussian click jitter (`--sigma`, 40 seeds) | **realistic** manual ceiling (WPD/metaDigitise with human clicking) |
| `cv_autoreader` | real PIL/NumPy landmark detection from the PNG (bars) | an automated reader, no GT pixels |
| `vision` | agent/VLM pixel estimates from `vision/<id>.json` | model-in-the-loop |
| `webplotdigitizer`, `metadigitise` | adapter hooks (`tools_external.py`) mapping each tool's native export to `tool_output` | third-party digitizers (GUI; not headless here) |

## Metrics -- dispersion-first

Every chart is scored per **channel**, reported separately:

- **central tendency** -- bar mean, box median, scatter point/slope/r. The easy channel.
- **dispersion** -- error-bar half-height (`|cap - top|`), box IQR width. **The headline.**
  Framing: a *b%* error in the cap -> ~*2b%* error in variance -> a study reweighted by ~sqrt(n).
  At n=8 a 15% cap error is a ~30% variance error is a materially mis-weighted study.

Aggregations: headline central/dispersion medians+worst; by tier (clean/hard); per chart.
`report_all.py` runs every tool (with the jitter sweep) into `RESULTS.md`.

## How to run

```bash
# 0. one-time: R packages ggplot2/grid/gridExtra/jsonlite/scales (all present here); Python: numpy, Pillow
# 1. generate the corpus (PNGs + GT bundles + manifest)
Rscript benchmark/r/generate.R
# 2. verify GT pixels sit on the drawn ink
python3 benchmark/harness/audit_pixels.py
# 3. emit leak-free vision tasks (for a VLM/agent reader)
python3 benchmark/harness/make_tasks.py
# 4. score any tool against R's descriptives
python3 benchmark/harness/score.py --tool geometry_floor            # manual ceiling (0%)
python3 benchmark/harness/score.py --tool human_floor --sigma 1.0   # realistic manual floor
python3 benchmark/harness/score.py --tool cv_autoreader             # automated reader
python3 benchmark/harness/score.py --tool vision                    # agent estimates in vision/
# 5. consolidated dispersion-first report
python3 benchmark/harness/report_all.py                             # -> benchmark/RESULTS.md
# optional: prove the harness affine == the real tool (needs :8001 + Playwright)
python3 -m http.server 8001 &      # served from repo root (serves figure-extractor.html)
python3 benchmark/harness/crosscheck_js.py
```

## Results (see `RESULTS.md`)

| tool | central median | dispersion median | dispersion worst |
|---|---|---|---|
| geometry_floor (exact pixels) | 0.00% | 0.00% | 0.00% |
| human_floor (1px click jitter) | 0.44% | **4.03%** | **29.2%** |
| cv_autoreader (bars) | 0.45% | **8.89%** | **21.5%** |
| vision (1 genuine agent read) | 1.17% | **8.20%** | -- |

Central tendency is nearly free for every tool; **dispersion is where extraction breaks**, and
it breaks worst on short SEM caps and overlapping (dot-overlay) ink. Even perfect tools leak
large dispersion error from sub-pixel click jitter, because the cap is a small pixel distance.

## Path: individual figures -> multi-panel -> real journal figures

1. **Individual figures (done).** bar/box/scatter/line, exact GT, dispersion-first scoring.
2. **Multi-panel (done, first pass).** Faceted figures emit one GT bundle per panel with
   `panelBounds` (pixel rect) + `multi-panel` flag; the reader must decompose the figure before
   reading, mirroring the tool's hard-refusal on un-split multipanel. Extend by scoring panel
   *segmentation* (mAP on `panelBounds`) as its own stage.
3. **Real journal figures (the true test -- the transfer gap).** Synthetic charts have flat
   fill colors that make CV/GT detection easy; real figures add anti-aliasing, JPEG artifacts,
   overlap, hand-drawn significance bars, and inconsistent cap styles. The flagship measurement
   is **Delta = M(synthetic-test) - M(real-held-out)** per channel and per hard-flag. Crop real
   panels from the dissertation's own coded corpus (155 rodent + 323 human rows) so the figure
   eval and the **golden diff** share studies. Label them with the same schema; test-only.

## Why this is the train/eval bed for a specialist landmark detector

The synthetic GT is **free and exact** -- every bar top, cap, quartile, point, and tick has a
sub-pixel label with no human effort. That is precisely what a landmark detector (DETR/YOLO/
Faster-RCNN-style) needs: 10^3-10^4 charts x the complexity knobs -> a training set for a model
whose *output is already the tool's pixel input*, whose *target is the load-bearing dispersion
channel*, and whose occlusion/multipanel failures become detection-recall problems it is built
for. The harness scores that detector against R exactly as it scores the floors here.

## Honest assessment -- how strong is the ML case, and the minimal experiment

- **The problem is real and localized.** These numbers confirm the dispersion channel is where
  error concentrates (central ~0.5%, dispersion 4-9% median, worst 20-58%), and that it is
  driven by small pixel distances (short SEM/CI caps) and overlapping ink -- exactly what a
  sub-pixel specialist detector improves on and a human clicking cannot.
- **But synthetic is a ceiling, not a proof.** All numbers here are on clean synthetic renders;
  they *bound* the achievable accuracy and *locate* the risk, they do not prove a trained model
  beats an agent-with-CV on real figures. The realism gap (anti-aliasing, compression, hand-
  drawn error bars, unlabeled caps) is unmeasured until real panels are labeled.
- **The minimal experiment that would justify building the model:** label ~100-150 real panels
  from the dissertation corpus (oversampling `raw-points-present`, `log-axis`, `multi-panel`),
  run `human_floor` (a careful human click), the `cv_autoreader`/an agent, and a candidate
  detector through this harness, and report the **transfer-gap Delta on the dispersion channel**
  and the **end-to-end golden diff** (does the extracted Control/Treatment mean+SD+n, when fed to
  R's `escalc`/`rma.mv`, reproduce the hand-coded pooled estimate/CI/tau-squared?). If the
  detector closes a large real-figure dispersion gap that the agent leaves open -- and only then
  -- the model is justified. Until that Delta exists, the honest call matches
  `VISION-MODEL-METHODOLOGY.md` §7: **agent-driven digitization + a human dispersion gate now;
  the specialist detector when the real-figure gap is measured, not assumed.**

## TODO checklist

- [ ] **White paper: "more precise than WebPlotDigitizer -- take the human out of the digitization
      loop."** DEFERRED -- the author has more tests to run first. Write once the additional tests +
      the real-figure scale-up land, so the argument rests on the full evidence, not the pilot.
- [ ] Scale the real-figure golden diff (`benchmark/real/`) to committee-grade N (~120 rows), add a
      second human reader per panel for an accuracy envelope, run the full 3-level `rma.mv(~1|article/row)`.
- [ ] Train the specialist sub-pixel landmark detector and score it through the SAME harness against
      the agent baseline -- the experiment that proves a detector beats the agent on the dispersion channel.
- [ ] Classification real-figure transfer: label real panels, report acc(synthetic) - acc(real),
      oversampling the hard pairs (funnel<->scatter, dose-response<->line).
- [ ] (Author's additional tests -- TBD.)

## Roadmap / white-paper threads (detail)

- **White paper: "more precise than WebPlotDigitizer -- and why the human should come out of the
  loop."** This benchmark's `human_floor` sweep is the argument's backbone: even a *correct* human
  click with 0.5-2px of jitter drives the dispersion (error-bar) channel to ~2-8% median / ~19-74%
  worst, while central tendency stays ~0.5%. WebPlotDigitizer's celebrated ICC>0.95 validation
  assumes good human clicks and never isolates the dispersion channel, so it *hides* this error on
  exactly the quantity meta-analysis depends on. The white paper should: (1) formalize the
  cap-error -> variance-error -> study-mis-weighting chain; (2) show, with these numbers, that human
  click imprecision is an irreducible error source on short caps; (3) argue that a sub-pixel,
  deterministic reader (calibration math is exact; only point-picking is noisy) can be *more precise
  than a human*, making "take the human out of the digitization loop" a defensible claim -- with the
  human's role moving to confirming the dispersion *type* (SD/SEM/CI, which is textual, not visual)
  rather than clicking pixels. The claim is only earned once the real-figure transfer gap (above) is
  measured; frame it as the hypothesis the real-panel experiment tests.

- **Classification prerequisite (blocks the extraction agent).** Before an agent can extract the
  *scientific content* of a figure it must reliably classify what the figure IS -- chart type,
  provenance (the study's own data vs. a summary of others), axis scale, dispersion presence, and
  the non-data ink to ignore. Produce a labeled corpus spanning the most common scientific chart
  types (bar/grouped/stacked, box, violin, scatter, line/dose-response, histogram, KM, forest,
  funnel, ROC, Bland-Altman, heatmap) and measure classification accuracy/macro-F1/confusion/
  calibration on it (the costly confusions are the priority: forest->bar flips extraction priority;
  box<->violin is cheap). This is the perception tier of the vision-model/agent split
  (`VISION-MODEL-METHODOLOGY.md` §19a): the vision model classifies + locates; the agent, reading
  the caption/methods, decides what the numbers *mean*. Classification is the gate that must pass
  before extraction is even attempted -- extend this benchmark's R generator to emit the type-label
  corpus and add a classification scorer.
