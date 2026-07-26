# Academic Figure Extractor

A browser-based tool for extracting, annotating, and digitizing figures from academic papers --
plus a measurement suite for the question that matters if you feed those numbers into a
meta-analysis: **how accurate is figure extraction, and where exactly does it break?**


## What's here

| | |
|---|---|
| **`figure-extractor.html`** | The tool. A single self-contained file -- no server, no build, no dependencies. Annotates figures/subfigures, captures captions, digitizes charts, and exposes a `window.figureExtractor` API so an AI agent can drive it. |
| **`benchmark/`** | An extraction-accuracy benchmark where **R is the ground-truth engine**, plus a real-figure validation, a chart-type classification corpus, and a series/group-parsing tier. This is where the findings below come from. |
| **`meta-analysis/`** | The evidence-synthesis pipeline the tool feeds: staged, with mandatory human gates and an append-only decision log. |

The tool's job is deliberately narrow: it is a **visual-only fallback** for when the number you need
exists only as ink in a chart. It emits calibrated landmarks plus provenance; **all effect-size math
is R's** (`escalc`/`metafor`), never the browser's.

## Headline findings

Full detail in [`benchmark/RESULTS.md`](benchmark/RESULTS.md) and the
[technical log](benchmark/WHITE-PAPER-LOG.md).

**1. The arithmetic is exact; all error is point-picking.** Given exactly correct pixels, recovery
error is 0.00% on every chart -- clean and hard, including log axes and multi-panel. So a digitizer
should never be judged on its math (all of them are exact), only on how the points get picked.

**2. Central tendency is nearly free; dispersion is where everything breaks.**

| reader | central median | dispersion median | dispersion worst |
|---|---|---|---|
| exact pixels (geometry floor) | 0.00% | 0.00% | 0.00% |
| human click, 0.5 px jitter | 0.22% | 2.09% | 18.7% |
| human click, 1.0 px jitter | 0.44% | **4.15%** | **37.3%** |
| human click, 2.0 px jitter | 0.89% | 8.23% | 74.4% |
| CV auto-reader | 0.45% | 8.89% | 21.5% |
| vision agent | 1.17% | 8.20% | -- |

Error-bar caps are only a few pixels tall, so a 1-pixel slip is a large fraction of the *spread*
while barely touching the *mean*. A `b%` cap error becomes roughly a `2b%` variance error, which
mis-weights the study by about `sqrt(n)` in the pooled model.

**3. This is invisible to the standard validation.** WebPlotDigitizer's validation base measures
human-vs-human agreement and assumes good clicks; it never isolates the dispersion channel. The
sweep above suggests human click imprecision is an *irreducible* error source on short marks.

**4. It transfers to real journal figures, and the conclusion reproduces.** On panels from a
completed meta-analysis with hand-coded values: central 0.47% / dispersion 3.67% median. End-to-end
through `escalc`/`rma`, pooled Hedges g came out **+0.475 extracted vs +0.487 hand-coded**, CIs
coincident, 0/8 sign flips.

**5. Knowing *what* a chart is, is solved.** 18 chart types across 12 R graphing libraries, plain and
deliberately cluttered: 100% classification accuracy, no degradation on the cluttered tier. The
bottleneck is localization and structure, not recognition.

**Honest scope:** except where noted, these are synthetic charts. They *bound* accuracy and *locate*
risk; they do not prove a trained model beats a capable agent on messy real figures. That experiment
is specified in [`benchmark/README.md`](benchmark/README.md) and not yet run.

## Quick start

Open `figure-extractor.html` in any modern browser.

> Some features (the folder picker, the File System Access API) require a real origin. If the
> `file://` page misbehaves, serve the directory: `python3 -m http.server 8001` then open
> <http://localhost:8001/figure-extractor.html>.

**Load a paper** -- single-click a PDF in the browser pane, or drag a PDF onto the article pane.
Pages render client-side via PDF.js at the PDF's **native resolution** by default (never upscaled --
higher DPI costs an AI agent tokens with no fidelity gain). Change it in Settings if you need to.

For pre-converted page images: `python3 scripts/pdf-to-pages.py paper.pdf output_dir/`, then pick
the parent project folder.

### Annotate

- **Draw figures**: click and drag on any page to box a figure.
- **Draw subfigures**: in the Figures pane, draw on the cropped figure to define panels.
- **Move / resize**: select a box, then drag it or its 8 handles.
- **Label**: edit the label on each card ("Figure 1", "Figure 2a", ...). Deleting a figure frees its
  number.
- **Locate**: click a box (or card) to jump to the other view.
- **Delete**: the card's delete button, or select a box and press Delete.
- **Undo/Redo**: Ctrl+Z / Ctrl+Y. **Escape** cancels an in-progress draw.
- **Dark mode**: toggle in the top bar (persisted).

Annotations persist per-article in localStorage, so work survives a reload.

### Captions

Captions carry what you need to interpret a figure, so they are extracted automatically. A PDF's text
layer is captured on load (folder projects use a `text.json` sidecar; scanned pages fall back to OCR
via `tesseract` if installed). Boxing a figure finds its `Figure N` caption and stores it with a
confidence badge. **Re-detect** re-runs detection, **Source** highlights the origin text, and
**Split -> panels** routes `(A)/(B)...` segments to the matching subfigures. All editable.

### Digitize a chart

Calibrate two points on each axis, then pick landmarks (bar tops, error caps, box quartiles, points).
The tool converts pixels to data values and exports **landmarks with provenance** -- never effect
sizes. Every value is permanently flagged `figure_derived`, so a figure-vs-text sensitivity analysis
stays possible downstream (verified is not laundered).

Guards that refuse to fail silently: an unknown dispersion type will not produce a variance, a
nonlinear axis is flagged for human review, an un-split multi-panel figure is rejected, and a series
whose legend label is missing or whose legend order contradicts plot order must be declared rather
than silently repaired.

### Export

**Export** downloads a ZIP for the current article; **Export All** bundles every annotated article.
Each ZIP contains `annotations.json` (schema v2: figures + nested subfigures, natural-pixel `bounds`
plus normalized `boundsNorm`, captions), `figures.csv`, `figure-derived-landmarks.csv` (the
authoritative digitized output -- feed this to R), and PNG crops of every figure and subfigure.

## AI integration

`window.figureExtractor` exposes the full surface for programmatic control: state, annotation,
base64 crops, characterization, calibration, digitization, extraction, validation, and the
human-gate preview. See [`AI-SKILL.md`](AI-SKILL.md) for the API reference and
[`skills/figure-meta-extract/SKILL.md`](skills/figure-meta-extract/SKILL.md) for the
characterization protocol.

The design boundary is deliberate: **the model reads glyphs, the agent assigns meaning.** The model
may report that error bars are present -- it may never assert whether they are SD, SEM, or CI, since
that is written in the caption and getting it wrong mis-weights the study.

## Repository layout

```
figure-extractor.html         Main application (single file)
AI-SKILL.md                   Agent API reference
skills/figure-meta-extract/   Characterization protocol for meta-analytic extraction

benchmark/                    R-ground-truth extraction benchmark
  r/                          GT engine: R simulates data -> computes descriptives ->
                              renders the chart -> exports exact device pixels
  harness/                    Tool-comparison scorers (dispersion is a first-class channel)
  real/                       Real-figure golden diff vs hand-coded values
  classify/                   Chart-type classification corpus (18 types, 12 R libraries)
  series/                     Series/group parsing tier (which mark belongs to which arm)
  WHITE-PAPER-LOG.md          Running technical log of findings and caveats

meta-analysis/                Evidence-synthesis pipeline (staged, human-gated, audited)
scripts/                      Converters, scoring harness, tests, CLI helper
eval/ bench/                  Earlier evaluation harnesses (superseded by benchmark/)
```

## Testing

```bash
python3 scripts/test_score.py         # scoring-harness unit tests (stdlib only)
python3 scripts/test_browser.py       # end-to-end: synthetic PDF, drives the tool headless
python3 scripts/test_meta_layer.py    # provenance flags, dispersion guard, landmark-only export
python3 scripts/test_series_layer.py  # series/arm structure, validation, human-gate preview
python3 scripts/test_series_e2e.py    # end-to-end on real benchmark ground truth (6 arms)
python3 scripts/test_ocr.py           # scanned-PDF OCR sidecar (skips without tesseract)
```

Browser tests need PyMuPDF + Playwright and a server on `:8001`:

```bash
pip install pymupdf playwright && python3 -m playwright install chromium
python3 -m http.server 8001 &
```

They skip cleanly if dependencies are missing. To regenerate the benchmark corpora (seeded, so they
reproduce exactly): `Rscript benchmark/r/generate.R` then `python3 benchmark/harness/report_all.py`.

## License

MIT -- see [LICENSE](LICENSE).

The real-figure validation reads hand-coded data from the companion meta-analysis repository,
[GSF-dissertation-meta-analysis](https://github.com/gregfitzgerald/GSF-dissertation-meta-analysis)
(clone it as a sibling directory, or set `RODENT_CSV` / `HUMAN_CSV`). Article PDFs and figure crops
are **not** redistributed here.
