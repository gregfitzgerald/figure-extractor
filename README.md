# Academic Figure Extractor

A browser-based tool for extracting, annotating, and organizing figures from academic papers. Supports subfigure hierarchy and AI-assisted annotation, as part of an automated meta-analysis / evidence-synthesis pipeline.

![Figure Extractor: a multi-panel figure boxed on the page (blue) with its six panels marked as nested subfigures (orange), and the extracted figure card with per-panel crops in the right pane](screenshot.png)

## Quick Start

Open `figure-extractor.html` in any modern browser. No server, no dependencies, no installation.

### Load a Paper

**Option A: Load PDF directly**
Click "Load PDF" in the browser pane. Select a PDF file. Choose DPI (150 for speed, 300 for quality). Pages render client-side via PDF.js.

**Option B: Load pre-converted page images**
1. Convert a PDF to numbered PNGs: `python3 scripts/pdf-to-pages.py paper.pdf output_dir/`
2. Click "Select Project Folder" and choose the parent directory containing article folders
3. Select an article from the browser pane

### Annotate

- **Draw figures**: Click and drag on any page to draw a rectangle around a figure
- **Draw subfigures**: In the Figures pane, draw on the cropped figure image to define panels
- **Move / resize**: Click a figure box to select it, then drag it or its 8 resize handles to adjust
- **Label**: Edit the label field on each figure card ("Figure 1", "Figure 2a", ...)
- **Locate**: Click a figure box (or card) to jump to the other view
- **Delete**: Delete button on a card, or select a box and press Delete
- **Undo/Redo**: Ctrl+Z / Ctrl+Y; **Escape** cancels an in-progress draw
- **Dark mode**: toggle in the top bar (persisted)

Annotations persist per-article in localStorage, so work survives a page reload.

### Captions

Captions carry information needed to interpret a figure, so they are extracted automatically:

- When a PDF is loaded, its text layer is captured; folder-based projects get the same from a
  `text.json` sidecar written by `pdf-to-pages.py`. Born-digital PDFs need nothing extra; for
  **scanned/image-only pages** the converter falls back to OCR (via a `tesseract` binary, if
  installed) so their captions are recovered too.
- The moment you box a figure, its caption is found from the nearby `Figure N` text, transcribed,
  and stored — with a confidence badge (Auto / OCR / Low confidence / Edited).
- Review it in the caption box on each figure card. **Re-detect** re-runs detection, **Source**
  highlights where the text came from on the page, and **Split → panels** routes `(A)/(B)…`
  segments to the matching subfigures. Every caption is fully editable.

### Export

- **Export** downloads a ZIP for the current article; **Export All** bundles every annotated
  article in the project into one ZIP (per-article subfolders).
- Each ZIP contains `annotations.json` (schema v2: figures + nested subfigures, natural-pixel
  `bounds` plus normalized `boundsNorm`, and `caption` / `captionSource` / `captionConfidence`),
  a `figures.csv` flat table (one row per figure/subfigure with label, page, and caption — ready
  for a spreadsheet or stats tool), and individual PNG crops of every figure and subfigure.

### Evaluation / optimizing extraction

To measure and improve extraction quality against your own hand-scored ground truth:

1. Hand-correct an article in the tool, Export, and drop `annotations.json` into its project dir.
2. `scripts/figure-extractor.sh promote <article>` copies it to `ground-truth.json`.
3. `scripts/figure-extractor.sh score <article>` (or `score-all`) reports figure detection
   precision/recall/F1 (IoU-matched), localization IoU, subfigure-count accuracy, caption-text
   similarity, and an error taxonomy that points at the failing stage.
4. `gate` logs each run to `scores.jsonl` and exits nonzero if macro-F1 regresses below your best
   recorded run — so a heuristic change is only adopted after it beats the ground-truth set.

## File Structure

```
figure-extractor.html    # Main application (single file, runs in browser)
scripts/
  pdf-to-pages.py        # PDF -> numbered PNGs + text.json caption sidecar (OCR fallback)
  score.py               # Ground-truth scoring harness (stdlib only)
  test_score.py          # Unit tests for the scoring harness (stdlib)
  test_browser.py        # Self-contained end-to-end browser test (synthetic PDF)
  test_ocr.py            # OCR-sidecar test (scanned PDF; skips without tesseract)
  figure-extractor.sh    # CLI helper (convert, promote, score, gate, ...)
SPEC.md                  # Original design specification (aspirational; not all features built)
SCOPE-AND-RECOMMENDATIONS.md  # Project scope and technical recommendations
AI-SKILL.md              # Instructions for AI agents to operate the tool programmatically
```

## Testing

```bash
python3 scripts/test_score.py     # scoring-harness unit tests (stdlib only)
python3 scripts/test_browser.py   # end-to-end: generates a synthetic PDF, drives the tool
                                  # headless, checks caption/schema/undo/resize/split/CSV
python3 scripts/test_ocr.py       # scanned-PDF OCR sidecar (skips without tesseract)
```

`test_browser.py` needs PyMuPDF and Playwright (`pip install pymupdf playwright && python -m
playwright install chromium`); it skips cleanly if they aren't installed.

## AI Integration

The tool exposes `window.figureExtractor` API for programmatic control. See `AI-SKILL.md` for the full API reference.
