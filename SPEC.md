# Academic Figure Extractor - Specification

## Overview

A lightweight web tool for extracting and annotating figures from academic papers. Two-pane interface for viewing article pages and managing extracted figures.

## Design Aesthetic

- **Minimalist white** - Clean, academic feel
- Light grays for borders/dividers
- Subtle shadows for depth
- No unnecessary chrome

## Interface Structure

### Two Main Tabs

#### Tab 1: "Article"
- Vertical scroll of all PDF pages (converted to PNG)
- Pages displayed in reading order
- Interactive: user draws **rectangles** around figures
- Drawn rectangles appear as colored boxes with labels (Figure 1, Figure 2, etc.)
- After subfigures are defined in Tab 2, those boxes also appear nested within figure boxes
- Clicking a figure box jumps to that figure in Tab 2

#### Tab 2: "Annotated Images"  
- Shows clipped figure images (cropped from the article based on rectangles)
- Each figure card shows:
  - The cropped figure image
  - Figure label (editable: "Figure 1", "Figure 2a", etc.)
  - Button to "Add Subfigure" - allows drawing boxes within this figure
- Subfigures appear nested under their parent figure
- Hierarchy visualization: Figure 1 → Figure 1a, 1b, 1c

## User Workflow

1. **Load PDF** - Select a PDF file
2. **Convert** - Tool converts PDF pages to PNGs (happens automatically)
3. **Draw figure boxes** - In Article tab, draw rectangles around each figure
4. **Label figures** - Assign labels (auto-increment or manual)
5. **Define subfigures** - In Annotated Images tab, draw boxes within figures to define panels
6. **Export** - Save annotations and images

## Export Function

When "Save" is pressed, export:

1. **Annotation JSON** - `annotations.json`
   ```json
   {
     "source": "chen2011.pdf",
     "dpi": 150,
     "figures": [
       {
         "id": "fig1",
         "label": "Figure 1",
         "page": 2,
         "bounds": {"x": 100, "y": 200, "width": 400, "height": 300},
         "subfigures": [
           {
             "id": "fig1a",
             "label": "Figure 1a",
             "bounds": {"x": 0, "y": 0, "width": 200, "height": 150}
           }
         ]
       }
     ]
   }
   ```

2. **Figure images** - Saved to output directory:
   ```
   output/
     Figure_1.png
     Figure_1a.png
     Figure_1b.png
     Figure_2.png
     ...
   ```

## Technical Notes

### PDF to PNG Conversion
- Use PDF.js for client-side rendering (no server needed)
- DPI setting: **ASK GREG** - default to 150 for now, make configurable
- Store rendered pages in memory for performance

### Drawing Interface
- Click and drag to draw rectangles
- Rectangles are resizable/movable after creation
- Delete with right-click or delete key
- Color coding: main figures = blue outline, subfigures = orange outline

### State Management
- All state in a single JavaScript object
- Annotations survive tab switches
- Auto-save to localStorage for crash recovery

## Files to Create

1. `figure-extractor.html` - Main application (single HTML file)
2. `README.md` - Usage instructions
3. Example with Chen et al. 2011 paper

## Questions for Greg

- [ ] What DPI for PNG conversion? (150 is readable, 300 is publication quality but larger)
- [ ] Should subfigure labels auto-generate (1a, 1b) or be fully manual?
- [ ] Output format preference: flat folder or nested (Figure_1/a.png)?
