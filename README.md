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
- **Label**: Edit the label field on each figure card ("Figure 1", "Figure 2a", ...)
- **Locate**: Click a figure card's image to scroll to its source page
- **Delete**: Delete button on each figure card
- **Undo/Redo**: Ctrl+Z / Ctrl+Y

Annotations persist per-article in localStorage, so work survives a page reload.

### Export

Click Export to download a ZIP containing:
- `annotations.json` with full metadata and subfigure hierarchy
- Individual PNG crops of every figure and subfigure

## File Structure

```
figure-extractor.html    # Main application (single file, runs in browser)
scripts/
  pdf-to-pages.py        # PDF to PNG conversion utility
  figure-extractor.sh    # CLI helper for common operations
SPEC.md                  # Original design specification (aspirational; not all features built)
SCOPE-AND-RECOMMENDATIONS.md  # Project scope and technical recommendations
AI-SKILL.md              # Instructions for AI agents to operate the tool programmatically
```

## AI Integration

The tool exposes `window.figureExtractor` API for programmatic control. See `AI-SKILL.md` for the full API reference.
