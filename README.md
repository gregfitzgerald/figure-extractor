# Academic Figure Extractor

A browser-based tool for extracting, annotating, and digitizing figures from academic papers --
plus a measurement suite for the question that matters if you feed those numbers into a
meta-analysis: **how accurate is figure extraction, and where exactly does it break?**


## What's here

| | |
|---|---|
| **`figure-extractor.html`** | The tool. A single file -- no server, no build, no install; PDF.js and JSZip load from a CDN, so loading PDFs and exporting need a network connection (a banner appears at load when the CDN is unreachable). Annotates figures/subfigures, captures captions, digitizes charts, and exposes a `window.figureExtractor` API so an AI agent can drive it. |
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
| human click, 0.5 px jitter | 0.22% | 1.94% | 13.8% |
| human click, 1.0 px jitter | 0.44% | **3.89%** | **27.7%** |
| human click, 2.0 px jitter | 0.89% | 7.81% | 55.3% |
| CV auto-reader | 0.45% | 8.89% | 21.5% |
| vision agent | 1.17% | 8.20% | -- |

Error-bar caps are only a few pixels tall, so a 1-pixel slip is a large fraction of the *spread*
while barely touching the *mean*. A `b%` cap error becomes roughly a `2b%` variance error, which
mis-weights the study by about `sqrt(n)` in the pooled model.

> The jitter rows are freshly regenerated. They previously read 2.09 / 4.15 / 8.23 median and
> 18.7 / 37.3 / 74.4 worst, seeded via Python's `hash()` on a string -- which CPython salts per
> process, so the table changed on every run and could not be reproduced by anyone, including
> its author. Seeding now uses `crc32`; re-running `benchmark/harness/report_all.py` reproduces
> the numbers above exactly. The medians barely moved and the conclusion is unchanged; the
> *worst*-case column was the part that was noise.

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

**6. Splitting a multi-panel figure works, provided it is allowed to decline.** 41 seeded figures /
159 panels, each with an exact pixel box and a letter ([`benchmark/panels/RESULTS.md`](benchmark/panels/RESULTS.md)):

| | legacy XY-cut | cascade detector |
|---|---|---|
| per-panel IoU, median | 0.398 | **1.000** |
| exact panel count | 80.5% | **95.1%** |
| letter accuracy | 74.1% | **100%** |
| **silent mislabels** | 9.4% | **0%** |
| coverage (figures answered) | 85.4% | 65.9% |
| exactly right, *answered only* | -- | **100%** (27 figures) |

Read those last two rows together: it declines a third of figures and is not observed to be wrong on
what it accepts. That is the right trade here -- an abstention costs a minute of attention, whereas a
box confidently labelled with the wrong letter attaches a number to the wrong experimental arm.
The abstention is nonetheless over-cautious: recall 1.00 (it declines *every* figure it would have
got wrong) but precision 0.14, so 12 of its 14 abstentions were needless and net figures saved is
**-10**, against a pre-registered gate of `> 0`. That gate currently fails.

**And none of this transfers yet.** Run the same detector over 71 real journal figures and it
abstains on **93%** of them (synthetic: 34%). It made zero silent errors across 259 invocations --
every answer it stood behind matched the caption's own letter count -- but it stands behind almost
nothing. The 95.1% above is a statement about synthetic captions generated by the same script that
drew the figures.

Two separate things are wrong, and it is worth keeping them apart, because fixing the first does
not fix the second:

- **Reading the caption.** The parser returned nothing for half of real captions. That is now
  measured and partly fixed (`benchmark/real/caption_corpus.py`): 49.3% -> 54.9% parse rate, and
  two *silent undercounts* removed along the way -- a caption reading `(A) ... (A') ... (B) ...
  (B')` used to report two panels for a four-tile figure.
- **Standing behind an answer.** This is the binding constraint, and it is NOT the caption.
  Reading four more captions moved abstention by exactly zero: 92.9% before, 92.9% after, 5
  figures answered both times. Of 65 abstentions, 58 carry `panel-labels-unverified`, and half
  happen *with* a caption count already in hand.

  The obvious next suspect was letter verification, which was all-or-nothing: one missing glyph
  discarded every correctly-read one. Probing 13 real figures directly, the glyph finder does
  work -- it found anchors on 12 -- but was short by one or more on 8 (Zhang2017 Fig 3: 5
  anchors for 7 panels). Allowing a *partial* reading to count when it corroborates the
  reading-order prior therefore looked like the fix. **It changed nothing: 92.9% -> 92.9%, and
  not one figure qualified.** The partial path needs each anchor to land cleanly on a distinct
  box, and the boxes themselves are wrong -- derived from a heuristic figure crop, not a human
  one. So the failure is upstream of both the caption and the labels: it is the figure region.

So the honest next step is not more caption work. It is panel-label verification on real raster
figures, measured against human-drawn panel boxes -- which is exactly what
[`benchmark/real-validation/`](benchmark/real-validation/) exists to collect.

On synthetic figures, non-guillotine layouts (67% exact) are the remaining weakness, and **the
caption is the load-bearing input**: withhold it and exact-count collapses from 80.5% to 7.3%,
with spurious boxes going 99 -> 305. Knowing how many panels to expect is worth more than any
amount of pixel cleverness -- which is why the real-caption parse rate above matters even though
improving it did not, on its own, move abstention.

**Honest scope.** Findings 1, 2, 3, 5 and 6 are measured on *synthetic* charts that R rendered from
known data, so the ground truth is exact by construction. They *bound* accuracy and *locate* risk;
they do not prove a trained model beats a capable agent on messy real figures. Finding 4 is the one
real-figure result, and it is small: 6 panels, 3 articles, one reader, no repeat read.

Two things are consequently **not** established. There is no measurement of a *human* reader in the
loop -- every number above comes from exact pixels, simulated jitter, a CV reader or a vision model.
And while panel detection has now been *run* over 71 real journal figures, its **accuracy** there is
still unmeasured: nobody has drawn a panel box on any of them, so every real-figure number above is
"the detector emitted N", never "the figure has N". The 95.1% remains a synthetic result.
Both gaps are the subject of [`benchmark/real-validation/`](benchmark/real-validation/), a
pre-registered human annotation study that is built and blinded but not yet run to completion.

## Quick start

Open `figure-extractor.html` in any modern browser.

> **Which origin you open it from changes the folder UI**, because the File System Access API is
> unavailable on `file://`:
> - **`file://`** -- you get **Select Project Folder** (the `webkitdirectory` picker). Simple, works
>   offline, loads a project folder of page images.
> - **`python3 -m http.server 8001`** then <http://localhost:8001/figure-extractor.html> -- you get
>   the richer **Open Folder** file tree plus the **Render PDFs** batch picker, and recent projects
>   are remembered. `Select Project Folder` is hidden in this mode.
>
> Both load projects; pick whichever suits the task. (Export needs a network connection -- JSZip
> loads from a CDN.)

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
Then **Confirm extraction** (step 3 in the digitizer): declare the chart type and what the error
bars show (SD / SEM / CI -- answered from the caption, never guessed; "unknown" is recorded as a
`dispersion-type-uncertain` flag), plus optionally the direction of benefit and n. Confirming is
what produces the figure-derived extraction behind `figure-derived-landmarks.csv`.
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
plus normalized `boundsNorm`, captions), `figures.csv`, PNG crops of every figure and subfigure,
and -- once at least one extraction has been confirmed (digitizer step 3, or the API) --
`figure-derived-landmarks.csv` (the authoritative digitized output -- feed this to R). The bundled
README states whether the landmarks CSV is present.

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
  real/                       Real-figure golden diff vs hand-coded values, plus
                              overlay_reads.py / make_read_report.py, which draw the
                              reader's actual picked pixels back onto each journal panel
  classify/                   Chart-type classification corpus (18 types, 12 R libraries)
  panels/                     Multi-panel decomposition tier (41 figures, 159 panels)
  series/                     Series/group parsing tier (which mark belongs to which arm)
  real-validation/            Pre-registered human annotation study: blinded session
                              builder, ingest with structural blinding gates, analysis plan
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
python3 scripts/test_panels.py        # 20 panel-detection cases + the annotationMode guards
python3 scripts/test_ocr.py           # scanned-PDF OCR sidecar (skips without tesseract)
```

The human-validation harness has its own suite (run from `benchmark/real-validation/`):

```bash
python3 prepare_session.py --selftest      # session planning, blinding, repeat scheduling
python3 prepare_dan_session.py --selftest  # second-rater packaging, id/seed independence
python3 test_prereq_gate.py                # the build gate on a mixed trailing session
python3 test_end_to_end.py                 # plan -> annotate -> ingest -> intra-rater report
python3 test_second_rater.py               # inter-rater subset, gates, mislabelled-ingest refusal
```

Four of the five run on a fresh clone. Only `test_end_to_end.py` needs real article PDFs, resolved
via `benchmark/real/pdf_map.json` -- generated locally by `resolve_pdfs.py` against a Zotero library,
and not redistributable -- so it exits with `need 4 resolvable PDFs` rather than skipping cleanly.

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
