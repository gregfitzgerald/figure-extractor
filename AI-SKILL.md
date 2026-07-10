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

## Full API Reference

| Method | Description |
|--------|-------------|
| `isReady()` | Check if project/article loaded |
| `getState()` | Full current state |
| `listArticles()` | List articles in loaded project |
| `loadArticle(name)` | Load article by name |
| `addFigure(page, bounds, label?)` | Add figure annotation |
| `addSubfigure(figId, bounds, label?)` | Add subfigure to figure |
| `updateFigureLabel(figId, label)` | Update figure label |
| `deleteFigure(figId)` | Delete a figure |
| `getPageDimensions(page)` | Get page size info |
| `getPageAsBase64(page)` | Get page as PNG base64 |
| `getFigureAsBase64(figId)` | Get cropped figure as base64 |
| `getAnnotationsJSON()` | Get annotations without download |
| `export()` | Download figures + JSON |
| `clearAnnotations()` | Clear all annotations |

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
`textlayer` | `ocr` | `manual` | `''` (`ocr` when the text came from `pdf-to-pages.py`'s
scanned-page OCR fallback, and carries slightly lower confidence).

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
