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
// Add a figure (coordinates relative to displayed image)
figureExtractor.addFigure(2, {x: 100, y: 150, width: 400, height: 300}, 'Figure 1')

// Add subfigure (coordinates relative to figure crop)
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

Bounds are in **display pixels** (how the image appears in the browser).

To calculate from percentages or natural pixels:
```javascript
const dims = figureExtractor.getPageDimensions(pageNum);
// dims.displayWidth, dims.displayHeight = rendered size
// dims.naturalWidth, dims.naturalHeight = actual image pixels
// dims.scale = naturalWidth / displayWidth
```

## Workflow for AI Figure Extraction

1. **Human** opens tool and selects project folder
2. **Human** tells AI which article to process
3. **AI** loads article: `figureExtractor.loadArticle('chen2011')`
4. **AI** gets each page as base64, sends to vision model to identify figures
5. **AI** adds figure annotations based on vision model output
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
```

## Tips

- Annotations are saved per-article in localStorage
- Subfigure bounds are relative to the cropped figure, not the page
- Use vision models (GPT-4V, Claude) to identify figure locations
- The tool works offline after project is loaded
