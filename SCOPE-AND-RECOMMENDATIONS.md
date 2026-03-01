# Academic Figure Extractor: Project Scope and Recommendations

*Compiled by Moltie, February 28, 2026*

---

## 1. What This Project Is

The Academic Figure Extractor is a browser-based tool for extracting, annotating, and organizing figures from academic papers. It exists because the available alternatives -- Docling, PyMuPDF, pdfimages, and their ilk -- fail at a task that seems like it should be trivially solved by now: getting the actual figures out of a PDF in a way that preserves their structure and meaning.

The tool currently lives as a single HTML file (`figure-extractor.html`, ~1470 lines) with a three-pane interface: a file browser, an article viewer where you draw rectangles around figures, and an annotated images pane showing the cropped results with subfigure support. It works entirely client-side. No server, no dependencies, no installation. You open it in a browser, point it at a folder of page images, and start annotating.

This document lays out where the project stands, what it should become, and the technical decisions that need to be made to get there.

---

## 2. The Problem Being Solved

Academic papers contain figures. Those figures contain subfigures (panels). Researchers need to extract both -- cleanly, with metadata, and with the parent-child relationships intact. This sounds simple. It is not.

### What Docling Does (and Why It's Not Enough)

We ran Docling against Pandey et al. 2023, a 27-page biology paper with western blots, bar charts, and multi-panel figures. Docling found 46 "figures." Of those, 8 were actual figures or tables. The remaining 38 were journal logos, decorative elements, individual western blot bands, and other noise. That's an 83% false positive rate.

But the real problem isn't the noise -- you can filter noise. The real problem is that Docling has no concept of subfigures. A five-panel figure (panels A through E) gets shredded into five disconnected images with no relationship to each other and no relationship to the parent figure. For the kind of work Greg does -- neuroscience papers with complex multi-panel figures -- this makes Docling's output essentially useless without extensive manual curation afterward.

The figure extractor solves this by flipping the paradigm. Instead of trying to automatically detect figures (and failing), it gives the human a fast, precise interface for drawing boxes around what they see, then uses hierarchy (figure → subfigure) to preserve the structure that automated tools destroy.

### Where Automated Detection Still Has a Role

That said, throwing out automation entirely would be a mistake. A vision model (Claude, GPT-4V) looking at a page image can identify figure regions with reasonable accuracy. The key insight is that automated detection should be a *starting point* that the human corrects, not a *final answer* that the human has to reverse-engineer when it's wrong. This is the hybrid approach: AI proposes, human disposes.

---

## 3. Current State of the Codebase

### What Works

- **Three-pane layout**: Browser (file navigation), Article (page viewer with drawing), Figures (annotated crops with subfigure support). Clean, minimal, academic aesthetic.
- **Rectangle drawing**: Click-and-drag on page images to define figure regions. Boxes are resizable conceptually (delete and redraw). Color-coded: blue for figures, orange for subfigures.
- **Subfigure hierarchy**: Draw sub-regions within cropped figures. Labels auto-generate (Figure 1 → Figure 1a, 1b, 1c). Parent-child relationship is preserved in the data model.
- **Export**: Generates `annotations.json` with full metadata (page number, bounds in natural image coordinates, subfigure hierarchy) plus individual PNG crops of every figure and subfigure.
- **Docling import**: If an `annotations.json` file exists in the article folder (from a Docling run or previous session), the tool loads it as a starting point. A "Reset" button lets you revert to the Docling annotations after manual edits.
- **localStorage persistence**: Annotations survive tab closes and browser restarts. Manual edits override imported annotations.
- **AI API** (`window.figureExtractor`): Full programmatic interface for headless/automated operation. Methods for adding figures, getting page images as base64, exporting annotations, etc.
- **Coordinate system**: All bounds stored in natural image pixels (not display pixels), so annotations are resolution-independent.

### What Doesn't Work Yet (or Is Missing)

- **No PDF-to-pages integration in the UI**: The tool expects pre-converted PNG page images. The conversion step (`pdf-to-pages.py` or Docling) is a separate manual step. This is the single biggest friction point in the workflow.
- **No undo/redo**: Delete is permanent. Drawing a bad rectangle means starting over.
- **No box resizing**: You can delete and redraw, but you can't grab a handle and adjust. For precise annotation, this matters.
- **No zoom**: Pages render at whatever the browser decides. For dense figures with small panels, you can't zoom in to draw precise subfigure boundaries.
- **No keyboard shortcuts**: Everything is mouse-driven. Power users (which Greg is) expect shortcuts for common operations.
- **No batch export to a server-side directory**: Export triggers individual browser downloads. For a 30-figure paper, that's 30+ download dialogs. There's no "save all to this folder" option.
- **No vision model integration**: The AI API exists but there's no built-in "auto-detect figures" button that sends pages to a vision model and pre-populates annotations.
- **No cross-page figures**: Some figures span page breaks. The tool has no way to represent a figure that starts on page 5 and continues on page 6.
- **Subfigure coordinates are in display pixels**: While main figure bounds are stored in natural image coordinates, subfigure bounds are stored relative to the rendered crop size. This means subfigure positions break if the figure card renders at a different size (which it will on different screens or window widths). This is a bug.
- **No DPI configuration**: The tool doesn't know or care about DPI. The SPEC asks for configurable DPI, but the tool just uses whatever resolution the page images happen to be.

---

## 4. Architecture Decisions

### Single HTML File vs. Component Architecture

The current single-file approach has real advantages: zero build step, zero dependencies, runs anywhere, trivial to distribute. Greg can email it to a collaborator and it just works. For a tool of this complexity (~1470 lines), a single file is still manageable. I'd keep it as a single file until it crosses roughly 3000 lines, at which point the cognitive overhead of scrolling becomes a real cost.

But we're going to need to add significant functionality (vision model integration, PDF conversion, zoom, undo/redo). That will push past 3000 lines easily. My recommendation: **stay single-file for now, but start organizing the JavaScript into clearly separated sections with comment headers**. If it hits 3000 lines, extract into modules with a minimal bundler (esbuild, single command).

### Client-Side vs. Server-Side PDF Conversion

The SPEC mentions PDF.js for client-side rendering. This is the right call for portability, but it has limitations: PDF.js renders pages as canvas elements, and complex PDFs (especially those with embedded fonts or unusual colorspaces) sometimes render with artifacts. The alternative is server-side conversion with `pdftoppm` or Ghostscript, which handles edge cases better but requires a local server.

**Recommendation: Implement PDF.js first for the zero-dependency experience. Add a "Use local converter" option that calls a lightweight local HTTP endpoint for papers where PDF.js chokes.** The local converter already exists (`pdf-to-pages.py`), so this is just a thin API wrapper.

### Coordinate System Fix

The subfigure coordinate bug needs to be fixed before anything else. Subfigure bounds should be stored as fractions of the parent figure's dimensions (0.0 to 1.0), not as pixel values relative to the display. This makes them resolution-independent and screen-size-independent, the same way the main figure bounds work via natural image coordinates.

### Storage Strategy

localStorage is fine for crash recovery but terrible for long-term storage. It's per-origin, per-browser, and invisible to file management tools. The real annotations should live in `annotations.json` files alongside the page images, with localStorage as a write-ahead log that gets flushed on explicit save.

**Recommendation: Add an auto-save to `annotations.json` (via the File System Access API where available, with a manual download fallback). Keep localStorage for crash recovery only.**

---

## 5. Feature Roadmap (Prioritized)

### Tier 1: Fix What's Broken (Night Shift Targets)

These are bugs or missing fundamentals that compromise the tool's core value.

1. **Fix subfigure coordinate system** -- Convert to fractional coordinates relative to parent figure bounds. Migrate any existing annotations on load.

2. **Add undo/redo** -- Maintain a history stack of state snapshots. Ctrl+Z / Ctrl+Y. Cap at 50 states to avoid memory bloat.

3. **Add box resizing** -- Drag handles on annotation corners and edges. This is essential for precision work. Without it, getting a tight crop around a figure requires multiple delete-and-redraw cycles.

4. **Add zoom** -- At minimum, Ctrl+scroll to zoom the article pane. Ideally, a zoom slider or fit-to-width toggle. Drawing should work at any zoom level with correct coordinate mapping.

5. **Keyboard shortcuts** -- Delete key to remove selected annotation. Arrow keys to nudge selected box by 1px (Shift+arrow for 10px). Tab to cycle through annotations. Escape to deselect.

### Tier 2: Workflow Improvements

These make the tool significantly faster to use but aren't blocking.

6. **Integrated PDF loading** -- Drop a PDF onto the tool (or use a file picker). PDF.js converts to page images client-side. No more separate conversion step. Show a progress bar during conversion.

7. **Batch export to folder** -- Use the File System Access API (Chrome/Edge) to write all crops and the annotation JSON directly to a chosen directory. Falls back to a ZIP download on Firefox/Safari.

8. **Vision model pre-annotation** -- A "Detect Figures" button that sends each page as base64 to a configurable API endpoint (Claude, GPT-4V, or a local model). Returns bounding boxes that get drawn as proposed annotations (dashed outline, different color). User accepts, rejects, or adjusts each one.

9. **Annotation categories** -- Not all boxed regions are "figures." Some are tables, some are equations, some are supplementary panels. Add a type selector (Figure, Table, Equation, Supplementary) that affects the label prefix and export organization.

10. **Cross-page figure support** -- Allow linking annotations across pages. "This box on page 5 and this box on page 6 are parts of the same figure." The export stitches them together.

### Tier 3: Power Features

These are nice-to-have for advanced workflows.

11. **Comparison mode** -- Side-by-side view of Docling's automated extraction vs. manual annotations. Useful for evaluating automated tools and for Greg's research on figure extraction quality.

12. **Batch processing** -- Process multiple articles in sequence. Queue papers, run vision model detection on all, then review and correct.

13. **Annotation templates** -- For journals with consistent layouts (e.g., every Nature paper has figures in the same general positions), save and apply templates.

14. **Integration with Zotero** -- Pull papers directly from Greg's Zotero library. Export annotated figures back as Zotero attachments with proper metadata.

15. **Collaborative annotation** -- Share annotation state between multiple users. Probably overkill for Greg's use case, but relevant if this becomes a tool for a lab.

---

## 6. Technical Recommendations

### DPI Question (from SPEC)

**Recommendation: 150 DPI default, 300 DPI option.**

150 DPI is sufficient for screen viewing, figure identification, and most annotation work. It keeps file sizes manageable (a 27-page paper is ~30MB at 150 DPI vs ~120MB at 300 DPI). 300 DPI should be available as an option for when publication-quality crops are needed (e.g., re-using a figure in a presentation or thesis).

The DPI setting should be configurable per-project, not globally, since different use cases have different needs. Store it in a `project.json` or in the `annotations.json` metadata.

### Subfigure Labels (from SPEC)

**Recommendation: Auto-generate with manual override.**

Default behavior: when you draw a subfigure inside Figure 3, it becomes "Figure 3a", then "Figure 3b", then "Figure 3c". The label is editable -- click to change "Figure 3a" to "Fig. 3A" or "Panel A" or whatever the paper actually calls it. This gives you speed (no typing for the common case) with flexibility (override when the paper uses non-standard labeling).

The auto-labeling should use lowercase letters by default (a, b, c) since that's the most common convention in biology papers. But some papers use uppercase, Roman numerals, or numbers. The override handles all of these without needing a configuration UI.

### Output Format (from SPEC)

**Recommendation: Flat folder with prefixed filenames.**

```
output/
  Figure_1.png
  Figure_1a.png
  Figure_1b.png
  Figure_1c.png
  Figure_2.png
  Table_1.png
  annotations.json
```

Not nested (`Figure_1/a.png`). Flat is easier to browse in a file manager, easier to glob in scripts, and plays better with Zotero attachment imports. The label prefix (`Figure_1a`) makes the hierarchy obvious without needing folder structure.

The `annotations.json` file should contain everything needed to reconstruct the extraction: source PDF name, DPI used, page dimensions, all bounds, all labels, all subfigure relationships, and a timestamp. Think of it as the "recipe" -- given the original PDF and this JSON, you should be able to reproduce every crop exactly.

### The Docling Integration Question

Docling is useful as a *source of initial annotations* despite its high false-positive rate. The workflow should be:

1. Run Docling on the PDF (or use a cached run)
2. Load Docling's output as proposed annotations
3. Human reviews: deletes the 83% noise, adjusts bounds on the 17% real figures, adds subfigures

The tool already supports this partially (it loads `annotations.json` from Docling). What's missing is a clear visual distinction between "Docling proposed this" and "human confirmed this." Proposed annotations should look different (dashed border, muted color) until explicitly accepted.

On the new PC with the RTX 2060, Docling with CUDA should finish a 27-page paper in under a minute instead of 8+. That changes the calculus -- if Docling is fast, it's worth running on every paper as a starting point even if 83% of its output is garbage, because deleting garbage is faster than drawing from scratch.

### Vision Model Integration Architecture

For the "Detect Figures" feature, the cleanest architecture is:

1. The tool sends page images to a configurable endpoint
2. The endpoint returns bounding boxes with confidence scores
3. The tool draws proposed annotations (filtered by a confidence threshold)
4. Human reviews and confirms

The endpoint could be:
- **Claude API directly** (requires API key in the tool -- security concern for shared tools)
- **A thin local proxy** that holds the API key and forwards requests
- **Moltie** -- the tool sends pages to a local WebSocket endpoint that Moltie monitors, Moltie runs the vision analysis, and sends back coordinates

Option C is the most interesting because it keeps the API key out of the browser, leverages the existing Moltie infrastructure, and allows Moltie to use whatever model is most appropriate (Claude for complex papers, a faster/cheaper model for simple ones).

---

## 7. What the Night Shift Should Build

Given the current state, the highest-impact work the night shift can do is fix the foundation and add the features that transform this from a working prototype into a tool Greg would actually reach for every time he reads a paper.

### Night Shift Task List

**Task 1: Fix subfigure coordinate system**
Convert subfigure bounds from display pixels to fractional coordinates (0.0-1.0) relative to parent figure dimensions. Add a migration path for any existing annotations that use the old format. Test with the chen2011 project.

**Task 2: Add undo/redo**
Implement a state history stack. Capture state on every mutation (add figure, delete figure, add subfigure, label change). Ctrl+Z to undo, Ctrl+Y/Ctrl+Shift+Z to redo. Visual indicator showing undo depth ("3 changes ago"). Cap at 50 entries.

**Task 3: Add annotation box resizing**
Add drag handles to annotation boxes (8 handles: 4 corners + 4 edges). Dragging a handle resizes the box. Minimum size constraint (20x20px) to prevent accidental collapse. Update stored bounds on resize end. Works for both figures and subfigures.

**Task 4: Add zoom controls**
Ctrl+scroll to zoom the article pane (0.25x to 4x range). Zoom slider in the article pane header. "Fit width" button. Drawing coordinates must remain correct at all zoom levels. Zoom level persists per-article in localStorage.

**Task 5: Add keyboard shortcuts**
Delete/Backspace to delete selected annotation. Arrow keys to nudge (1px, Shift+10px). Tab/Shift+Tab to cycle selection. Escape to deselect. Ctrl+E to export. Ctrl+Z/Y for undo/redo. Show a "?" help overlay listing all shortcuts.

**Task 6: Integrate PDF.js for client-side PDF loading**
Add a "Load PDF" button that accepts a PDF file. Use PDF.js (loaded from CDN) to render pages to canvas, then convert to PNG data URLs. Show progress during conversion. DPI selector (150/300) in the load dialog. Store converted pages the same way folder-loaded pages are stored.

**Task 7: Improve export with ZIP download**
Instead of triggering individual file downloads, bundle everything into a ZIP (using JSZip from CDN). Single download: `{article-name}_figures.zip` containing all crops + `annotations.json`. Add an "Export to Folder" option using File System Access API where available.

---

## 8. What I'm Not Recommending (Yet)

A few things that might seem obvious but would be premature:

- **Making this a web app with a backend**: The zero-dependency, single-file nature is a feature, not a limitation. Adding a server adds deployment complexity, authentication questions, and hosting costs. Keep it local until there's a compelling reason not to.

- **Building a full Docling replacement**: Docling's layout detection, despite its flaws, is the product of serious ML research. Trying to replicate that with a custom model would be a multi-month effort with uncertain returns. Better to use Docling as one input among many and focus on the human-in-the-loop correction experience.

- **Mobile support**: Academic figure annotation is a desktop activity. Responsive design for mobile would add complexity for zero practical value.

- **Electron/Tauri packaging**: A packaged desktop app would solve the File System Access API limitations, but it's a significant maintenance burden. The browser version is good enough. Revisit only if file system access becomes a persistent pain point.

---

## 9. Success Criteria

The figure extractor is successful when:

1. Greg can go from "I have a PDF" to "I have all figures and subfigures cropped and labeled" in under 10 minutes for a typical 10-page paper
2. The subfigure hierarchy is preserved in a machine-readable format (for downstream tools like Anki card generation or thesis figure management)
3. The tool is fast enough that using it is less annoying than manually screenshotting figures from a PDF viewer
4. Annotations are durable -- they survive browser restarts, machine changes, and are backed up alongside the paper files

Right now, criteria 1 and 3 are partially met (the tool works but friction from missing features slows it down). Criteria 2 is met (the JSON format captures hierarchy). Criteria 4 is weakly met (localStorage is fragile, but the export function produces durable files).

The night shift work targets criteria 1 and 3 directly by removing the friction points (no zoom, no undo, no resize, no keyboard shortcuts, separate PDF conversion step).

---

## 10. Timeline and Effort Estimates

- **Subfigure coordinate fix** -- Low complexity, ~50 lines changed, low risk
- **Undo/redo** -- Medium complexity, ~120 new lines, low risk (well-understood pattern)
- **Box resizing** -- High complexity, ~200 new lines, medium risk (coordinate math with zoom)
- **Zoom controls** -- Medium complexity, ~150 new lines, medium risk (must not break drawing)
- **Keyboard shortcuts** -- Low complexity, ~80 new lines, low risk
- **PDF.js integration** -- High complexity, ~250 new lines, medium risk (PDF.js edge cases)
- **ZIP export** -- Low complexity, ~80 new lines, low risk (JSZip is straightforward)

Total estimated addition: ~800-1000 lines, bringing the file to ~2300-2500 lines. Still within single-file territory.

The night shift should be able to complete tasks 1-5 comfortably (the foundational fixes) and make good progress on tasks 6-7 (the workflow improvements). The vision model integration (Tier 2, task 8 from the roadmap) is better left for a follow-up session where Greg can test the interaction model and give feedback.

---

*This document will be updated as the night shift progresses and decisions are made.*
