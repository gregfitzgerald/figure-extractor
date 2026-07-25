# Evaluating and improving vision models for scientific-figure reading

A methodology for the figure-perception tier of the Metascience Observatory extraction stack. Companion to `AUTOMATED-MA-VISION.md` §19 (synthetic-GT chart model) and §19a (the vision-perceives / agent-understands split). Produced by a design pass grounded in this repo's `eval/` harness, the real `CHAR_VOCAB` taxonomy and `window.figureExtractor` tool contract, and the current chart-understanding literature.

**Design invariant (carried throughout).** The vision model does **perception** (classification + pixel landmarks). Deterministic code does the **arithmetic** (`computeCalibration`'s affine; `EXTRACT.*`). **R** does the **statistics** (escalc/Morris/metafor). A meaning-aware **agent**, reading the caption/methods, decides *what* to extract and maps it to the schema. The vision model is never asked to do math a matrix inverse does better, and never asked to make an extract/skip judgment that needs the article text it cannot see.

---

## 1. What already exists, and its limits (grounded audit)

The `eval/` harness is a good skeleton whose four pieces test different things; naming the seams matters because two are commonly confused and one was stale.

| File | What it actually tests | Honest limit |
|---|---|---|
| `make_chart_dataset.py` | Generates 20 matplotlib charts + GT (`charType`, `extractDecision`, `dispersionType`, `flags`, caption, `articleContext`), incl. 5 hard cases | 20 images, one engine (matplotlib), one MA scenario, one seed; no landmark-pixel GT. A benchmark in miniature — too small for F1/ECE/confusion |
| `make_tasks.py` | Emits leak-free prompts in **with-context** and **image-only** conditions (its best idea) | Its inlined flag list is a **subset of `CHAR_VOCAB.flags`** — label space can silently drift from the tool |
| `score.py` | Grades type/decision/dispersion/flag-recall/provenance as raw % | No per-type **F1/confusion**, no **calibration/ECE** on the `confidence` field already collected, no **abstention** analysis |
| `extraction_accuracy.py` | Feeds **exact** matplotlib pixels through `calibrate` + `EXTRACT.*` | A **unit test of the affine math**, not a model eval — no vision in the loop. (Now updated to score landmark recovery.) |
| `vision_extract_score.py` | The only end-to-end **model-in-the-loop** numeric eval (agent estimates pixels → tool → compare) | Only 3 hardcoded charts; **was stale after the landmarks-only refactor** (scored removed `sd`/`se`). **Now fixed** to score the landmark channels (errorHalf, quartiles, CI) — the load-bearing quantity anyway |

**First-day, low-effort fixes (independent of any modeling):** (a) make the eval import its label space from the tool (`window.figureExtractor.charVocab()`) so it can never drift from `make_tasks.py`; (b) [done] rewrite `vision_extract_score.py` to score landmark channels; (c) keep `extraction_accuracy.py` explicitly labeled a *math unit test*, not a model benchmark.

---

## 2. Where this sits in the literature (reuse vs. contribution)

The chart-understanding field is mature enough that most scaffolding is off-the-shelf. Be candid about what to reuse and what is genuinely novel here.

**Reuse (do not reinvent):**
- Chart-type classification and chart→table are largely solved: ChartQA, PlotQA, DVQA/FigureQA established the task; DePlot/MatCha turned it into plot→table; ChartX & ChartVLM, UniChart, ChartLlama, ChartGemma, ChartMoE are specialist VLMs to benchmark against or fine-tune from.
- Chart-element detection (bars/axes/legend/points as object detection) is a named subfield with datasets: the ICPR CHART-Infographics / CHART-Info 2024 competition and "Context-Aware Chart Element Detection" — both provide a synthetic + PubMedCentral-real split, a direct precedent for this design.
- Synthetic-GT generation + code-driven self-improvement: OneChart's reliability token, EvoChart self-training, Chart-CoCa code-driven synthesis, and the recipe result that synthetic data helps most **in pretraining**, not just LoRA.
- Older automated bar extractors give a realistic accuracy prior (~88% of bar values within 5%; axis labels ~80–89%). WebPlotDigitizer / metaDigitise are the human-in-the-loop baselines this tool competes with.

**Genuine contributions of this project (what a committee/employer should credit):**
1. **The perception/meaning split as an *evaluated* contract.** Nearly every benchmark conflates "read the chart" with "answer the question." Here the vision model is scored on perception only (types, landmarks, dispersion **presence**), and a separate agent is scored on extract/skip + schema-mapping *with* the caption. The `make_tasks.py` with-context vs image-only contrast is the seed; no cited benchmark isolates the two this way.
2. **The dispersion / error-bar channel as the load-bearing evaluated quantity.** DePlot/ChartVLM/OneChart extract the central value and largely ignore error bars — but in MA the SD/SEM/CI reweights every study (~√n). Making the error-cap channel a first-class, separately-reported metric is not standard and is where the risk lives.
3. **Measuring synthetic→real transfer against a real coded gold standard** — the dissertation's 155 rodent + 323 human hand-coded rows (§10). Almost no paper validates against an independently-coded real MA. This is the honest number.
4. **Uncertainty that propagates into a statistical model**, not a text answer: landmark pixel-spread → data-unit CI → `dispersion-type-uncertain` → R's variance treatment → abstention → the B4 human gate.

The framing to keep honest: the ML *techniques* are reused; the *evaluation object* (perception-only, dispersion-first, transfer-to-a-real-MA) and the *interface contract* are the contribution.

---

## 3. Evaluation design

### 3.1 Two corpora, three roles

**A. Synthetic-GT corpus (train + stress-test; GT exact by construction).** Extend `make_chart_dataset.py` from a 20-image demo into a parameterized generator:
- **Two+ rendering engines**, not one: keep matplotlib, add **R/ggplot2** (ideally plotly). A model that has only seen matplotlib overfits its tick styles, fonts, cap widths, palettes. Cross-engine is the cheapest slice of the synthetic→real gap.
- **Semi-randomize every nuisance:** theme/palette, font, DPI/resolution, aspect ratio, gridlines, legend position, marker style, cap width, jitter, #groups/series/points, axis ranges, and — critically — **whether values are printed on the chart** (ChartQA's known too-easy leak).
- **Emit exact GT for all three tasks at once** (the current generator does not): (i) `charType` + `dataProvenance` + `scale` per panel; (ii) **landmark pixels** for every bar top, error cap (upper *and* lower — GT `error-bars-one-sided` when clipped), box quartiles/whiskers, forest estimate/CI, scatter point, axis tick (via the engine's data→display transform, as `extraction_accuracy.py` already does); (iii) the **values, dispersion type, dispersion magnitude, and n** that generated the chart.
- **Hard cases as controllable knobs**, each tagged with the exact `CHAR_VOCAB.flags`: `multi-panel`, `log-axis`/`log2`, `broken-axis`, `dual-y-axis`, `overlapping-series`, `occluded`, per-animal **dot overlays on bars** (the rodent-paper idiom), `low-resolution`, `no-legend`, `categorical-x`. §4 slices every metric by these.
- Target scale: 10³–10⁴ for detector/LoRA training, with a held-out synthetic **test** split (§3.4). A build — comes *after* step-1 baseline proves it's needed (§14/§19).

**B. Real held-out journal set (the true test; GT by hand).** Crop real figures (the `eval/charts_real/` dir exists for this), prioritizing the **dissertation's own corpus** so the golden diff (§10) and the figure eval share studies. Label each with the same schema (`CHAR_VOCAB` + landmark pixels + dispersion type). Budget ~100–300 panels, oversampling hard flags. **Test-only, never trained on** — these are the numbers you report.

### 3.2 Label taxonomy — tie directly to `CHAR_VOCAB`

Import the label space at runtime from `window.figureExtractor.charVocab()`, never re-type it: `charType` (22 values incl. `unknown`/`other` as abstention classes), `scale`, `dispersion`, `dataProvenance` (the forest/funnel "summarizes *other* studies" distinction that gates priority), `flags` (all 14), `nonDataElement` (ignore-list), `method` (routing). Grading against the exact strings the validator enforces means a passing prediction is, by construction, a valid tool input.

### 3.3 Metrics

**(a) Classification.** Per-type accuracy and **macro/weighted F1** (rare types — violin, bland-altman, dose-response — are where value and error concentrate); **confusion matrix read structurally** (box↔violin cheap; **forest→bar catastrophic** because it flips extraction priority); **calibration/ECE** on the `confidence ∈ [0,1]` the tasks already collect (a model that says 0.9 and is right 0.6 poisons the agent's gating); **abstention precision/recall** (reward calibrated "I don't know" over confident wrongness — the metascience-specific value).

**(b) Landmark detection.** **Localization error in pixels** per landmark kind (bar-top, upper/lower cap, q1/median/q3, whisker, forest-est, CI-end, point, tick) — the model-intrinsic quantity; **localization error in data units** after the real `calibrate` — what actually reaches R; **detection precision/recall/mAP** for "did it find all the marks" — the right metric for multipanel/occlusion where the failure is a *missing* mark.

**(c) Extraction — dispersion channel as its own headline.** Central-value recovery (bar mean, box median, forest estimate) — the easy channel. **Dispersion recovery, reported separately and prominently** (`errorHalf`, IQR width, CI half-width): a b% error in `errorHalf` → ~2b% error in variance → reweights a study ~√n, so at n≈8 a 15% cap-read error is a ~30% variance error is a materially mis-weighted study. Stratify by dispersion type (SEM caps are shorter → higher relative pixel error). **End-to-end golden-diff agreement** (§10): ICC/exact-match of the final schema row (`Control_Group_Mean`, SD, n, dispersion type, `Direction`) against the dissertation CSVs — the number a committee asks for.

### 3.4 Splits, leakage, and measuring transfer

- **Split synthetic by generative family, not by image** — hold out whole style/theme/engine/seed families so the test set is stylistically unseen.
- **Leakage control on real figures:** dedup by DOI; a study's figures live entirely in train or entirely in test; a figure used to tune prompts / fine-tune never reappears in the real test set. Make the MA **scenario** a variable (several criteria), or the extract/skip task degenerates to "learn one scenario."
- **The transfer gap is the flagship measurement.** For each metric M report **Δ = M(synthetic-test) − M(real-held-out)**, per task and per hard-flag. A small classification gap but a large dispersion-channel gap (the likely outcome) tells you exactly where synthetic pretraining pays off and where real fine-tuning is mandatory. §19's honesty hinges on this number.

---

## 4. Error-analysis methodology

**Stratified failure mining is the core loop.** Compute every §3 metric globally *and sliced by `CHAR_VOCAB.flags`*; the deliverable is a slice table (metric × hard-flag) whose worst cells are the roadmap. Priors:
- **Multipanel** is a *decomposition* failure before a reading one (`runExtraction` already hard-refuses un-split multipanel). Evaluate as two stages: panel segmentation (`addSubfigure` territory) then per-panel reading — a model that reads well but can't segment needs a segmenter, not a better reader.
- **Log/broken/dual axes** are *calibration* failures (`verifyCalibration` already flags them). Evaluate (a) detection of the log/broken axis → correct `flags`, and (b) reading it correctly given correct ticks. Broken-axis is the classic trap: bar *heights* lie, absolute values don't.
- **Occlusion/overlap** is a *detection-recall* failure → mAP, not localization error.
- **Rare types + non-data ink** are *classification/attention* failures → track whether significance stars, trend lines, gridlines get read as data (`ignoredElements` recall is the metric).

**Turning failures into the next training set (the flywheel):** synthetic — the worst slice becomes an over-sampling instruction (curriculum / hard-negative mining; the free lunch of synthetic GT); real — the golden diff + B4 human adjudication *produces* labels, so adjudicated mispredictions are the highest-value additions to the real fine-tune set (EvoChart self-training with a human backstop).

---

## 5. Improvement approaches, ranked effort → payoff

| # | Approach | Needs | Expected gain | Effort |
|---|---|---|---|---|
| 1 | **Prompt / in-context** — "calibrate axis first, then read"; hard-case few-shot; `charVocab` in prompt; CoT for panel counting; "state confidence + why" | the harness | Modest classification + flag-recall; cheap ECE gain | **weekend** |
| 2 | **Tool-augmentation** — model emits *pixels only*; `calibrate`/`EXTRACT` do arithmetic | built | Large numeric gain vs. VLM doing pixel→data math; removes an error class | **done — protect it** |
| 3 | **Self-consistency / ensembling** — K landmark reads, per-landmark median pixel, spread = uncertainty | K× inference | Free calibrated uncertainty; smoother dispersion channel | **weekend** |
| 4 | **Verifier / critic loop** — `verifyCalibration` round-trip; re-render extracted table and diff vs image (DePlot-style); disagreement → abstain | renderer + 2nd pass | Catches gross reads; silent errors → abstentions | **1–2 weeks** |
| 5 | **Specialist object-detector** (DETR/YOLO/Faster-RCNN) for bars/caps/axes/quartiles/points → pixels into existing calibration | synthetic landmark GT (free), 1 GPU | **Highest ML payoff** — built for the dispersion channel + occlusion/multipanel recall; output *is* the tool's input | **1–2 wk, research-grade** |
| 6 | **LoRA fine-tune a VLM** for classification + landmark-JSON | ~10⁴ synthetic + small real, 1 GPU-hours | Meaningful ("68k synthetic + 4h LoRA" is documented); LoRA alone doesn't fix synthetic↔real *alignment* | **2–4 weeks** |
| 7 | **Synthetic pretrain → real fine-tune** + transfer-gap ablation | full synthetic + real gold, compute | **Flagship result** — the ablation *is* the paper | **research project** |

Two judgment calls: **the specialist detector (5) is the sweet spot** — it targets the load-bearing channel (caps, quartiles), its GT is free from the generator, occlusion/multipanel become detection-recall problems it's built for, its output is already the tool's pixel input, it's a legitimate ML artifact, cheaper than a VLM fine-tune, and it doesn't hallucinate round numbers. **Keep the VLM for what it's uniquely good at** — classification, flag detection, panel segmentation, reading printed text/axis labels (OCR-adjacent) — and route *position* perception to the detector. The hybrid (VLM classifies+segments; detector localizes; affine calibrates; R computes) beats any single model and mirrors the CHART-Info task decomposition.

---

## 6. The vision-model ↔ agent interface (the contract)

The load-bearing design deliverable. The vision model produces a **characterization + landmark bundle**; the agent consumes it *with the caption/methods* and produces the **schema row**. Both have API homes: `setCharacterization`, `runExtraction`, `calibrate`, `authoritativeRows`.

### 6.1 What the vision model hands the agent (perception only)

A structured object that validates against `CHAR_VOCAB` (so `validateCharacterization` accepts it) plus landmarks-with-uncertainty:

```
{
  panels: [{
    panelLabel, panelBounds,                 // multipanel -> addSubfigure
    charType,        charTypeConfidence,      // in CHAR_VOCAB.charType + [0,1]
    dataProvenance,  provenanceConfidence,    // primary vs derived (gates priority)
    axes: { x: {scale, scaleConfidence, calTicks:[{px,py,value}]}, y:{...}, y2?:{...} }, // TICK PIXELS
    landmarks: {                              // PIXELS + per-point sigma
      bars:  [{group, top:{px,py,s}, capUpper:{px,py,s}, capLower:{px,py,s}}],
      boxes: [{group, q1:{px,py,s}, median:{...}, q3:{...}, whiskers:{...}}],
      forest:[{label, est:{px,py,s}, ciLo:{...}, ciHi:{...}}],
      points:[{series, px, py, s}]
    },
    dispersion: { present: true|false, typeVisualGuess?: null },  // TYPE is usually NOT visual
    flags: [ ...CHAR_VOCAB.flags... ],
    ignoredElements: [ ...nonDataElement... ],
    abstain: false | "reason"
  }],
  producedBy: "detector@v1 | vlm@v1 | ensemble", producedAt
}
```

Contract rules, each grounded in the tool:
- **Emit tick and landmark *pixels*, never data values** — the affine (`computeCalibration`) does pixels→data. Numeric accuracy is a math problem, not a hallucination problem.
- **Uncertainty is per-landmark (`s`, e.g. ensemble spread)** and flows through `calibrate` to a data-unit CI on every value — the honest error bar on the error bar.
- **The model must *not* assert dispersion *type* from pixels.** SD vs SEM vs CI95 is visually identical; it lives in the caption. Report only `dispersion.present`. **This is the single most important boundary in the system** — a wrong dispersion type silently reweights the study. The validator already refuses a characterization with dispersion present but type unknown unless the `dispersion-type-uncertain` flag is set.
- **Flags are mandatory, not optional** — `dispersion-type-uncertain`, `log-axis`, `broken-axis`, `multi-panel` are how uncertainty becomes visible.

### 6.2 What the agent does with it (meaning)

Reads the bundle **+ caption + methods + MA criteria** and: (1) **segments** multipanel (`panelBounds` → `addSubfigure`, since `runExtraction` refuses un-split multipanel); (2) **resolves dispersion type from text** ("mean ± SEM, n=24") or keeps `dispersion-type-uncertain`; (3) **decides extract vs skip** against the MA criteria — the judgment that *needs* the article (why the image-only condition exists); (4) **fills what isn't in the figure** — `n` (methods table), `direction` (+1/−1; latency/errors lower-is-better — a field, never a mutated landmark), `timepoint`, `role`; (5) **maps to schema** via `runExtraction` → the `authoritativeRows` product (landmark values + dispersion **type** + provenance + `figure_derived=TRUE`, **no yi/vi**); (6) **routes uncertainty to the human gate** — low confidence / `abstain` / `log-axis-needs-human-review` / `dispersion-type-uncertain` → the B4 gate.

### 6.3 How uncertainty and abstention propagate (end to end)

`ensemble pixel spread (s)` → `calibrate` → **data-unit CI per landmark** → if type unresolved, `dispersion-type-uncertain` → R widens/flags variance → if any gate-triggering flag or low confidence, **B4 human gate** → human confirms, or the row is dropped ("no extractable data," counted in PRISMA). Nothing uncertain becomes a confident number without deterministic verification (`verifyCalibration` round-trip) or a human — the property the whole pipeline sells.

---

## 7. Staged plan

**Stage 0 — cheapest signal (days).** Fix the harness (§1: import `charVocab()`; [done] rewrite `vision_extract_score.py`; label `extraction_accuracy.py` a math unit test). Run the existing classification eval + the vision-extraction eval against 2–3 current VLMs (a frontier general VLM + a chart specialist like ChartGemma/ChartVLM), both with-context and image-only, and add the missing metrics (confusion, macro-F1, ECE, abstention). **Deliverable: a baseline table + first confusion structure + first ECE curve** — tells you whether prompting alone suffices before building anything.

**Stage 1 — prove the concept (2–4 weeks).** Scale the synthetic generator (add ggplot, semi-randomize, emit landmark GT); label ~150 real panels; report the **synthetic→real transfer gap** per task and per flag. Train the **specialist landmark detector** on free synthetic GT and show it **beats the VLM on the dispersion channel** and on occlusion/multipanel recall, feeding the same `EXTRACT` math. **Deliverable: "the detector closes X% of the dispersion-channel error a general VLM leaves open, validated on real figures."**

**Stage 2 — flagship ML result (research project).** Synthetic-pretrain → real-fine-tune (hybrid: VLM classify/segment/OCR + detector localize), with the **transfer-gap ablation** as the contribution, validated end-to-end against the 155+323 coded rows via the golden diff. **Deliverable: a paper-grade result** — "a perception-only, dispersion-first chart reader whose uncertainty propagates into a real three-level meta-analysis" — the pipeline's missing piece and a defensible ML contribution, because no cited benchmark evaluates that object.

Honest sequencing (§14/§19): **don't build Stage 1's model before Stage 0's baseline shows a gap a prompt can't close.** Measure that it's needed, then build it.

---

## Sources

- ChartQA — arxiv 2203.10244 · DePlot/MatCha — arxiv 2212.10505 · ChartX & ChartVLM — arxiv 2402.12185 · ChartMoE — arxiv 2409.03277 · OneChart — arxiv 2404.09987 · EvoChart — arxiv 2409.01577 · Chart-CoCa — arxiv 2508.11975 · Pretraining recipe (synthetic helps in pretraining) — arxiv 2407.14506 · Context-Aware Chart Element Detection — arxiv 2305.04151 · CHART-Info 2024 (synthetic + PMC real) — cvit.iiit.ac.in/images/ConferencePapers/2024/chart_info.pdf · Automated bar-chart extraction accuracy prior — arxiv 2011.04137 · metaDigitise (R, human-in-the-loop) — biorxiv 10.1101/247775 · Uncertainty in MA extraction — escholarship.org/uc/item/1qg250sq
