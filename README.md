# Academic Figure Extractor

A browser-based tool for extracting, annotating, and organizing figures from academic papers. Supports subfigure hierarchy, keyboard-driven workflows, and AI-assisted annotation.

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
- **Resize**: Hover over any annotation to see drag handles
- **Select**: Click an annotation to select it (red highlight)
- **Nudge**: Arrow keys move selected annotation by 1px (Shift = 10px)
- **Delete**: Delete/Backspace removes selected annotation
- **Undo/Redo**: Ctrl+Z / Ctrl+Y
- **Zoom**: Ctrl+scroll or use the slider

Press **?** for full keyboard shortcut reference.

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
SPEC.md                  # Original design specification
SCOPE-AND-RECOMMENDATIONS.md  # Project scope and technical recommendations
AI-SKILL.md              # Instructions for AI agents to operate the tool programmatically
```

## AI Integration

The tool exposes `window.figureExtractor` API for programmatic control. See `AI-SKILL.md` for the full API reference.
