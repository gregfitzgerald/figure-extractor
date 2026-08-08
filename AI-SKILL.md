---
name: figure-extractor
description: Extract and annotate figures from academic papers. Use when asked to extract figures, annotate paper images, identify subfigures/panels, or work with the figure extraction tool. Can operate via browser automation or CLI.
---

# Figure Extractor Skill

Extract figures and subfigures from academic paper page images.

## Project Structure

```
figure-extraction-projects/           # Root projects folder
  chen2011/                           # Article folder
    0001.png, 0002.png, ...           # Page images (numbered)
    metadata.json                     # Optional metadata
  another-paper/
    ...
```

**Default projects location:** `~/figure-extraction-projects/` (override with the `FIGURE_PROJECTS_DIR` environment variable when using the CLI helper)

## PDF to Pages Conversion

Before using the extractor, convert PDFs to numbered PNGs:

```bash
python3 scripts/pdf-to-pages.py <input.pdf> [output_dir] [--dpi 150]
```

## Browser Tool Location

`figure-extractor.html` in the repository root. Open it directly in any modern browser (no server required).

## AI Operation via Browser Automation

The tool exposes `window.figureExtractor` API for programmatic control.

### 1. Open the Tool

```
browser action=open targetUrl="file:///path/to/figure-extractor/figure-extractor.html"
```

### 2. Check Status

```
browser action=act request={"kind":"evaluate","fn":"JSON.stringify(figureExtractor.isReady())"}
```

### 3. After User Loads Project (via UI)

The user must select the project folder via the UI (browser security prevents direct file access).
Once loaded, AI can:

```javascript
// List available articles
figureExtractor.listArticles()

// Load an article
await figureExtractor.loadArticle('chen2011')

// Get page dimensions (needed for coordinate calculation)
figureExtractor.getPageDimensions(1)  // page 1
```

### 4. Add Annotations

```javascript
// Add a figure (bounds in NATURAL page pixels — page pixels at the render DPI)
figureExtractor.addFigure(2, {x: 100, y: 150, width: 400, height: 300}, 'Figure 1')

// Add subfigure (bounds in NATURAL pixels, relative to the figure's top-left)
figureExtractor.addSubfigure('fig1', {x: 10, y: 10, width: 180, height: 140}, 'Figure 1a')
```

### 5. Get Page for Vision Analysis

```javascript
// Get page as base64 for sending to vision model
const base64 = figureExtractor.getPageAsBase64(2)
```

### 6. Export

```javascript
// Get annotations without downloading
figureExtractor.getAnnotationsJSON()

// Trigger download of all figures + JSON
await figureExtractor.export()
```

<!-- BEGIN GENERATED: figureExtractor API reference (scripts/gen_api_docs.py -- do not edit by hand) -->
## Full API Reference

36 methods on `window.figureExtractor`, in source order. Descriptions come
from the source comments in `figure-extractor.html`; regenerate this block
with `python3 scripts/gen_api_docs.py --write` after the source changes
(`scripts/test_api_docs.py` fails when it drifts from the runtime surface).

- `getState()` -- Get current state. Returns `{projectName, currentArticle, articles, figures, pageCount}`.
- `listArticles()` -- List available articles (after project is loaded).
- `loadArticle(articleName)` (async) -- Load an article by name (project must be loaded first via UI or loadProjectFromPath). Returns `{success, pages, article}`.
- `addFigure(pageNum, bounds, label=null)` -- Add a figure annotation -- bounds: {x, y, width, height} in NATURAL image pixels (page pixels at render DPI). Returns `{success, figureId, label}`.
- `addSubfigure(figureId, bounds, label=null)` -- Add a subfigure to an existing figure -- bounds: {x, y, width, height} in NATURAL pixels, relative to the figure's top-left. Returns `{success, subfigureId, label}`.
- `updateFigureLabel(figureId, newLabel)` -- Update figure label. Returns `{success}`.
- `deleteFigure(figureId)` -- Delete a figure. Returns `{success}`.
- `detectPanels(figureId, opts={})` -- Detect subfigure panels for a figure. Returns a RESULT OBJECT, never a bare array. Returns `{ok, panels, count, method, confidence, flags, applied, error}`.
- `suggestSubfiguresLegacy(figureId, expectedCount=0)` -- Legacy XY-cut detector, kept for A/B comparison only. Returns bare boxes (no flags). Returns `{ok, panels, count, method, confidence, flags, applied, error}`.
- `getPageAsBase64(pageNum)` -- Get a page as base64 PNG (for vision model analysis).
- `getFigureAsBase64(figureId)` -- Get figure crop as base64 PNG.
- `getSubfigureAsBase64(figureId, subId)` -- Get a subfigure crop as a base64 PNG (the unit a vision model characterizes).
- `setCharacterization(figureId, subId, characterization)` -- Attach a characterization to a figure (subId=null) or subfigure. Validated against the controlled vocabulary; returns {success, errors?}. Returns `{success, errors} | {success}`.
- `getCharacterization(figureId, subId)` -- Read back the stored characterization for a figure (subId=null) or subfigure; null if none.
- `setExtraction(figureId, subId, extraction)` -- Store an interpreted extraction object on a figure/subfigure; figure-derived provenance is stamped last so a caller cannot overwrite it. Returns `{success}`.
- `getExtraction(figureId, subId)` -- Read back the stored extraction for a figure/subfigure; null if none.
- `calibrate(cal, vals, points)` -- Pure pixel->data via the affine calibration (no storage). points/[refs] carry {px,py}.
- `setDigitization(figureId, subId, dig)` -- Store an agent-supplied digitization (calibration + pixel points), returning the data values. Returns `{success, error} | {success, dataPoints, calibrationFlags}`.
- `runExtraction(figureId, subId, landmarks={})` -- Interpret landmarks into a stored `extraction` object, routed by the characterization's method. `landmarks` are in DATA units (convert pixels first with `calibrate`). Returns `{success, error} | {success, extraction}`.
- `suggestExtractionMethod(figureId, subId)` -- Per-panel extraction method(s) implied by the stored characterization (routing table).
- `extractionPriority(charType, dataProvenance)` -- Extraction priority per panel ('high'|'medium'|'low'|'none') -- prioritises the study's own primary data (bar/line/histogram/scatter/box) over derived summaries (forest/funnel).
- `suggestExtractionPriority(figureId, subId)` -- Per-panel extraction priority from the stored characterization (see extractionPriority).
- `charVocab()` -- Expose the vocab + conversion + extraction helpers so an agent/skill can validate, convert, and interpret calibrated landmarks locally.
- `extract` -- The EXTRACT namespace -- interprets calibrated DATA-unit landmarks per method; the landmarks are authoritative, R derives variances.
  - `extract.bars(groups, dispersionType)` -- bar-endpoints: groups=[{name, mean, errorHalf, n}] where errorHalf = |cap - mean| in DATA units. dispersionType decides SD vs SE vs half-CI. If the dispersion type is not a known variance-bearing type, we REFUSE to emit sd/se (a wrong SD/SEM/CI reweights the study by ~sqrt(n)) and force a `dispersion-type-uncertain` flag into the result. Returns `{method, groups, flags}`.
  - `extract.boxes(groups)` -- box-landmarks: groups=[{name, median, q1, q3, min, max, n}]. q1/q3/min/max are retained as AUTHORITATIVE landmarks; mean/SD (Wan/Hozo) are the NON-AUTHORITATIVE preview. Returns `{method, groups}`.
  - `extract.forest(rows, scale='linear')` -- forest-rows: rows=[{label, estimate, ciLo, ciHi}]; scale 'linear' (MD/SMD) or 'ratio' (OR/RR/HR). Returns `{method, rows, scale}`.
- `verifyCalibration(cal, vals)` -- Verify a calibration before trusting numbers: round-trip residual (hard: 'calibration-roundtrip-error') + nonlinear-axis check (flags 'log-axis-needs-human-review' for review).
- `setTraceExclusions(rects)` -- Auto-trace must not read the legend (a swatch of the traced colour injects phantom points and drags the column average). Set the regions to skip, in CROP pixels: [{x0,y0,x1,y1}, ...]. Returns `{success, count}`.
- `getTraceDiagnostics()` -- Diagnostics from the last auto-trace run, plus the count of active exclusion regions. Returns `{...digAutoTraceLast, exclusions}`.
- `validateSeries(figureId, subId)` -- Deterministic series-structure checks -- four of the review triggers are pure arithmetic, so they run without a model. Returns { ok, flags[], problems[] } for the B4 human gate. Returns `{ok, flags, problems}`.
- `previewAssignment(figureId, subId)` -- B4 HUMAN-GATE ARTIFACT. The benchmark measured a danger asymmetry: swapping two legend labels leaves every STRUCTURAL metric perfect (mis-assignment 0.000, ARI 1.000, zero ill-formed arms). Returns `{ok, error} | {ok, affirmations, bindings, reviewFlags, problems, structure, rows}`.
- `getFigureDerivedRows()` -- The tool's quantitative output: DATA-unit landmarks + dispersion TYPE + provenance (figure_derived/Data_Source/Data_Extraction_Method) + direction/timepoint/nSource -- NO yi/vi.
- `getFigureDerivedCsv()` -- getFigureDerivedRows() serialized as the landmarks CSV handed to R.
- `getPageDimensions(pageNum)` -- Get page dimensions (for calculating annotation coordinates). Returns `{displayWidth, displayHeight, naturalWidth, naturalHeight, scale}`.
- `export()` (async) -- Export all figures and annotations (triggers downloads). Returns `{success, figureCount}`.
- `getAnnotationsJSON()` -- Get annotations as JSON (without triggering download).
- `clearAnnotations()` -- Clear all annotations for current article. Returns `{success}`.
- `isReady()` -- Check if ready (project and article loaded). Returns `{projectLoaded, articleLoaded, loading, projectName, articleName, pageCount, figureCount}`.
<!-- END GENERATED: figureExtractor API reference -->

## Coordinate System

Bounds are in **natural pixels** (the page's pixel dimensions at the render DPI, i.e.
`getPageDimensions().naturalWidth/naturalHeight`). Figure bounds are relative to the page
top-left; subfigure bounds are relative to the parent figure's top-left. The exported
`annotations.json` also includes `boundsNorm` (fractions of the page/figure in `[0,1]`) for
resolution-independent comparison and scoring.

To convert a box measured on the displayed image to natural pixels:
```javascript
const dims = figureExtractor.getPageDimensions(pageNum);
// dims.displayWidth, dims.displayHeight = rendered size
// dims.naturalWidth, dims.naturalHeight = actual image pixels
// dims.scale = naturalWidth / displayWidth
// naturalX = displayX * dims.scale, etc.
```

## Output schema (getAnnotationsJSON / exported annotations.json)

Schema v2:
```json
{
  "schemaVersion": 2,
  "project": "...", "article": "...", "exportedAt": "...",
  "pages": [ { "pageNum": 5, "width": 1256, "height": 1631 } ],
  "figures": [
    {
      "id": "fig1", "label": "Figure 2", "pageNum": 5,
      "bounds": { "x": 150, "y": 210, "width": 960, "height": 1180 },
      "boundsNorm": { "x": 0.119, "y": 0.129, "width": 0.764, "height": 0.723 },
      "caption": "Figure 2. ...", "captionSource": "textlayer",
      "captionBounds": { "x": 150, "y": 1400, "width": 950, "height": 120 },
      "captionConfidence": 0.8,
      "subfigures": [
        { "id": "fig1_s1", "label": "Figure 2a",
          "bounds": { "x": 20, "y": 20, "width": 300, "height": 300 },
          "boundsNorm": { "x": 0.02, "y": 0.017, "width": 0.31, "height": 0.25 },
          "caption": "...", "captionSource": "manual" }
      ]
    }
  ]
}
```
`bounds` are natural px (subfigure bounds are relative to the parent figure). `boundsNorm` are
fractions of the page (figures) or figure (subfigures) for resolution-independent scoring.
Captions are auto-detected from the PDF text layer on `addFigure`; `captionSource` is
`textlayer` | `ocr` | `manual` | `panel-split` | `''` (`ocr` when the text came from
`pdf-to-pages.py`'s scanned-page OCR fallback, and carries slightly lower confidence;
`panel-split` when a verified `detectPanels` split routed the matching per-panel caption
segment onto the subfigure it created).

## Workflow for AI Figure Extraction

1. **Human** opens tool and selects project folder
2. **Human** tells AI which article to process
3. **AI** loads article: `figureExtractor.loadArticle('chen2011')`
4. **AI** gets each page as base64, sends to vision model to identify figures
5. **AI** adds figure annotations based on vision model output (captions auto-attach)
6. **AI** exports or returns annotations

## CLI Helper (Optional)

For quick operations without browser:

```bash
# Convert PDF and place in projects folder
./scripts/figure-extractor.sh convert paper.pdf chen2011

# List articles in project
./scripts/figure-extractor.sh list

# Open tool in browser
./scripts/figure-extractor.sh open

# Score extraction against hand-corrected ground truth
./scripts/figure-extractor.sh promote chen2011   # annotations.json -> ground-truth.json
./scripts/figure-extractor.sh score chen2011
./scripts/figure-extractor.sh gate               # regression gate over the whole corpus
```

## Tips

- Annotations are saved per-article in localStorage
- Subfigure bounds are relative to the parent figure, in natural pixels
- Use vision models (GPT-4V, Claude) to identify figure locations
- The tool works offline after project is loaded (captions need a PDF text layer or `text.json`)
