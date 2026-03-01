# Figure Extractor Bug Report - Post Night Shift QA

## Critical Bugs

### BUG-1: Literal `\n` characters in source (5 occurrences)
**Lines:** 570, 833, 1011, 1148, 2019
The night shift injected literal `\n` text instead of actual newlines at code section boundaries. This causes:
- Visible `\n` text rendered on the page (below browser pane)
- **CSS selector corruption**: `.pdf-modal` rule on line 571 becomes `n .pdf-modal` -- a descendant selector that never matches, so the modal's `display: none` never applies

### BUG-2: PDF modal visible on page load
**Cause:** BUG-1. The CSS rule `n .pdf-modal { display: none }` doesn't match `.pdf-modal`, so the modal is always visible. Cancel button removes class `visible` but that doesn't help since the modal was never hidden by CSS in the first place.

### BUG-3: Duplicate JSZip `<script>` tag inside main script block
**Line:** 2681
A `<script src="jszip">` tag is nested inside the main `<script>` block, just before `</script>`. This is invalid HTML -- a script tag inside a script tag terminates the outer script early, potentially breaking everything after it.

### BUG-4: Keyboard shortcuts not implemented (only undo/redo)
The task-5 deliverable (Delete, arrows, Tab, Escape, ?, help overlay, selection system) is almost entirely missing. Only Ctrl+Z/Y bindings exist. No `selectedFigureId` in state, no `selectFigure()`/`deselectFigure()` functions, no help overlay HTML/CSS, no arrow key nudge, no Tab cycling.

### BUG-5: Resize handles dead code -- `createResizeHandles()` never called
**Line:** 1309
The function is defined with all 8 handles but is never invoked in `renderAnnotations()`. Resize handles never appear on annotation boxes. The `startResize`/`handleResize`/`endResize` functions and CSS exist but are unreachable.

## Medium Bugs

### BUG-6: Undo/redo indicator missing from topbar
The progress notes mention "visual indicator in topbar" but I see no HTML element for it. The undo/redo system itself (pushHistory/undo/redo) needs verification -- check if pushHistory is called before mutations.

### BUG-7: `resetPdfModal` and `resetExportModal` may not exist
Line 1019 and 1026 call these functions but they need verification.
