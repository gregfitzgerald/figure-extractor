# Human annotation protocol -- real-figure validation

**Read this once, end to end, before you annotate anything.** After that, §14 is the
card you keep open while working.

---

## 0. What you are producing, and what it is for

You are producing a **human reference** for reading data out of published figures. A
machine pipeline (a panel detector plus a vision agent) will read the same figures, and
the two will be compared.

You annotate **inside `figure-extractor.html`** -- the same tool the machine drives. That
is not a convenience. It means your clicks pass through the *same* `computeCalibration`
affine the machine's picks do, and your export has the *same* schema. Any difference
between you and the machine is therefore a difference in **perception**, never in
arithmetic. If you annotated in some other tool, that guarantee would be gone and the
comparison would be uninterpretable.

**Where you are the oracle, and where you are not.** This matters and it changes how you
should treat different parts of the job.

| what you record | your status | why |
|---|---|---|
| figure bounding box | **ground truth** | a 1 px hand slip on a 400 px box is 0.25% |
| panel boxes, panel count, panel letters | **ground truth** | same -- the tolerance is enormous relative to your precision |
| chart type | **ground truth** | semantic; you read it, you are right |
| which series is control vs intervention, and the legend text | **ground truth** | semantic, read from legend + caption; a machine that gets this wrong fails silently |
| dispersion type (SD / SEM / CI95) and *n* | **ground truth** | these live in the caption and methods text, not in the pixels; they cannot be read off a figure at all |
| **central value** (bar top, box median) | **second reader** | ~0.4% error from hand jitter alone |
| **dispersion value** (error-bar cap length, IQR) | **second reader, and the weakest channel** | ~4% median and up to ~37% worst error from *one pixel* of hand jitter |

The last row is the reason this protocol is as fussy as it is. An error-bar cap sits only
a few pixels above the bar top, so a one-pixel slip is a large fraction of the thing being
measured. Where you are a second reader rather than an oracle, your numbers get an error
bar of their own -- which is why §3 makes you re-read part of the corpus (§3.3).

**Nothing here is a test of you.** Recording "I could not tell, and here is why" is a
*result*, and a useful one. Guessing to avoid a blank is the only thing that damages the
dataset.

---

## 1. One-time setup

1. **Open the tool from the file system, not from the local server.**

   Paste this into Windows Explorer's address bar or the Run dialog (Win+R):

   ```
   C:\Users\gregs\figure-extractor\figure-extractor.html
   ```

   It must open as a `file://` page. *Do not* use `start-figure-extractor.bat` for this
   work: when the tool is served over `localhost` it hides the **Select Project Folder**
   button, which is the only way to load these sessions.

2. **Stay online.** The tool pulls JSZip from a CDN; without it the Export buttons do
   nothing.

3. **Settings** (gear icon). Two settings, and the first is not optional.

   - **`Annotation mode` -> ON. REQUIRED.** It hides the `✨ Auto-panels` button, makes
     `detectPanels` and `suggestSubfiguresLegacy` refuse to return anything, and stamps
     `"annotationMode": true` into every file you export. **The ingest hard-rejects any
     export without that stamp**, with the same severity as a detector fingerprint: the
     session is not usable and has to be redone. The second rater is held to exactly the
     same check, so a difference between the two of you can never be a difference in how
     you were blinded.
   - *Auto-detect caption when drawing a figure* -> **ON**. The caption is *input* -- you
     are supposed to read it, and so is the machine.
   - The DPI setting is irrelevant here (pages are pre-rendered).

   **Verify it before you annotate anything**, once per browser profile. Draw a throwaway
   figure box on any page, press **Export This Article**, open the JSON in a text editor
   and confirm the top level contains:

   ```json
   "annotationMode": true
   ```

   If it says `false`, the checkbox is off. Turn it on, delete the throwaway figure, and
   check again. Doing this once costs a minute; discovering it after a 20-item block costs
   the block. The same check runs mechanically at ingest:

   ```bash
   python3 ingest_annotations.py ingest S01     # refuses on any export lacking the stamp
   ```

4. **Use the same browser profile, the same monitor, and the same display scaling for
   every session.** The tool keeps your work in that profile's `localStorage`. Changing
   monitors mid-corpus changes your click precision, which is one of the things being
   measured.

5. **Do not clear browsing data** between opening a session and exporting it. Your work
   lives in `localStorage` until you export.

6. Open a WSL terminal at `/mnt/c/Users/gregs/figure-extractor/benchmark/real-validation`.
   Every command below is run from there.

---

## 2. The shape of the job

Each figure is annotated in **two stages**, and the order is deliberate.

**Stage A -- structure.** You see the whole journal page at 200 dpi. You draw the figure
box and one box per panel, and you name the panels. Precision demands here are mild.

**Stage B -- meaning, then measurement.** The harness takes the panel boxes *you* drew and
re-renders each panel from the original PDF at a much higher resolution (long edge ~2200
px, typically 2-4x). For each panel you then (1) fill in a semantic coding form, and only
*after that* (2) click the landmarks.

Two reasons for the split:

- **Zoom.** Reading real figures at page scale was measured to be **22-36% off on the
  dispersion channel** until the panels were re-cropped at 2-3x. The re-crop is not
  optional polish; it is the difference between a usable and an unusable number. Doing it
  as a build step means the magnification is *fixed and recorded* rather than depending on
  how much you happened to zoom.
- **Anchoring.** Deciding what a bar *means* after you have already measured it is
  contaminated. Semantics first, pixels second.

---

## 3. Session discipline

### 3.1 Order

The harness fixes the order and you follow it. Do not skip ahead, do not do "the easy ones
first". The order is randomised *within* difficulty strata and then round-robined *across*
them, so hard figures are spread evenly over the session. If you reorder, fatigue becomes
confounded with difficulty and the whole session's timing data is worthless.

### 3.2 Length and breaks

- **Maximum 20 items per Stage A block** and **20 panels per Stage B block**.
- **Mandatory 15-minute break after item 10.** Get up. The timer will remind you.
- **Maximum two blocks per day**, with at least an hour between them.
- **At least 12 hours between sessions.** The harness enforces this and will refuse to
  build the next session early.
- If you notice yourself clicking without really looking, **stop and log a break**. That
  is not slacking; a rushed cap pick is worse than no cap pick.

### 3.3 The re-read subset (this is what makes your numbers interpretable)

About **18%** of items are scheduled to be annotated a **second time**, in a later
session, at least **3 days** after the first read. This measures *your own* repeatability,
which is the only way to know whether a machine-vs-human disagreement is a machine error
or your own hand jitter. Without it, an "agreement" figure means nothing.

You will not know which items are repeats. They come back under **new random item ids**,
in a different position, mixed in with fresh items. **Do not try to work out which ones
they are, and never look at your earlier exports.** If you do recognise one, do not go
back to check what you said last time -- just annotate it as it looks today and note
`"suspected repeat"` in the panel's `notes` field so the pair can be down-weighted.

### 3.4 Timing

Start the stopwatch before you touch the tool and leave it running:

```bash
python3 prepare_session.py timer S01 A     # Stage A
python3 prepare_session.py timer S01 B     # Stage B
```

It prompts you per item: ENTER to start, ENTER again when done (you can type a short note
before that second ENTER). `b` logs a break, `q` quits and resumes later.

---

## 4. Blinding: the three things you must not do

The comparison is destroyed if you see the machine's answer first. Three rules:

1. **Never press the `✨ Auto-panels` button.** With `Annotation mode` ON (§1.3) the
   button is not even shown, and the detector API refuses to return boxes, so this is
   enforced rather than trusted. Every panel box must be one you drew.

   Blinding is now checked **twice, in opposite directions**:

   | check | what it proves | what fails it |
   |---|---|---|
   | `annotationMode: true` in the export | the detector **could not have run** | the Settings checkbox was off |
   | no `panelDetection`, no `captionSource: 'panel-split'` | the detector **did not run** | Auto-panels was pressed |

   The first is the one that matters: detecting a violation after the fact is strictly
   worse than preventing it, and "we found no fingerprint" is a weaker claim than "the
   export asserts it could not have happened". Both are hard rejections at ingest. There
   is no way to un-press Auto-panels -- you would have to redo the figure.
2. **Never open anything under `keys/`, `gt/`, or `benchmark/real/vision/`.** `keys/` maps
   the anonymous item ids back to articles and marks which items are repeats. `gt/` and
   `benchmark/real/vision/` hold previously read values.
3. **Do not run the machine pipeline on a session before you have annotated and ingested
   it.** Ingest writes a sealed, timestamped, hashed record; the analysis relies on being
   able to show the human pass finished first.

What you *are* free -- and expected -- to read: the figure, its caption, the legend, and
the methods section of the paper. The machine gets the caption too. That is shared input,
not a leak.

---

## 4b. Calibration round -- do this FIRST, before any scored session

**This is your half of a two-rater round.** The second rater's protocol
(`SECOND-RATER-PROTOCOL.md` §4) instructs him to do exactly the same three figures, on the
same day, from an identical pair of zips. Both halves have to happen or neither is worth
anything, so this section exists to make sure you do not skip yours.

**Why.** Inter-rater studies fail far more often from **two people silently using different
definitions** than from anybody being careless. Does the panel box include the axis labels?
Is "the top of the bar" the top edge of the outline or the middle of it? Is the cap its
centre line or its upper edge? Two raters who answer those differently produce a large,
perfectly *reproducible* disagreement that looks like unreliability and is really a missing
convention. It is bias, not noise, and bias does not average out. Settling it costs 40
minutes; not settling it costs the study.

**The three figures, and which stage each convention belongs to.** They come from papers
already used for pilot work, are permanently DEV, and are built into `dan/calibration/` --
a separate data tree the analysis cannot reach.

| # | what it is | settles in **Stage A** | settles in **Stage B** |
|---|---|---|---|
| C1 | 2 tiles, grouped bar, SEM named in the caption -- the plain case | does the panel box include the y-axis and its tick labels | where exactly is the bar top; where exactly is the cap -- centre line or upper edge |
| C2 | 6 tiles sharing an axis, SEM, significance glyphs genuinely over the caps (the figure that produced this project's asterisk-occlusion finding) | who owns a shared axis (§8.1) | asterisk vs cap (§8.5); what counts as occluded |
| C3 | 5 visible tiles, caption names only 4 letters | what is a panel; do you split; how do you name an unlabelled tile (§8.6, §8.8) | -- nothing to digitise |

**Read which column is which.** Panel boxes are Stage A and they are the cheap half -- a
1 px slip on a 400 px box is 0.25%. **Every convention that moves a number is Stage B.** A
round that stopped after Stage A would reconcile the boxes and none of the measurements,
which is why both stages run before anybody compares anything.

**Build both zips (you build them; the second rater only receives them):**

```bash
python3 prepare_dan_session.py calibrate             # -> DAN-C01-stageA.zip
#   both raters do Stage A independently and return their projectA exports;
#   unzip them into dan/calibration/sessions/C01/exports/passA/, one folder per item
python3 prepare_dan_session.py calibrate --stage-b   # -> DAN-C01-stageB.zip
```

Stage B literally cannot be built before Stage A comes back: each rater's Stage B crops are
re-rendered from **their own** panel boxes.

**How to run your half:**

1. **Stage A on all three figures**, exactly as §5 describes, with `Annotation mode` ON
   (§1.3). Export, return the export. **Compare nothing yet.**
2. **Stage B on the chart panels**, exactly as §6 and §7 describe -- coding form first,
   landmarks second, zoom discipline as in §7.1-7.2. Export.
3. **Only now**, each of you writes, separately, **one sentence per convention** in a plain
   text file -- literally "I put the box edge at ..." / "I clicked the cap at ...". Six to
   ten sentences, covering both columns of the table above.
4. **Compare in a 20-minute call. Go through the sentences, not the numbers.** Where you
   differ, pick one convention and record it in `SECOND-RATER-PROTOCOL.md` §13 with a date
   and both sets of initials. That table overrides the corresponding rule in *both*
   protocols for *both* raters from then on.
5. **Do NOT compare your measured values on the calibration panels.** Reconcile
   *definitions*, never *readings*. Agreeing "we should both have got about 21.4" trains you
   toward each other on magnitudes, which is precisely the independence the second rater
   exists to supply. Definitions are arbitrary choices that must be shared; magnitudes are
   the measurement and must not be.
6. Re-do any figure whose convention changed, so you both finish applying the agreed rules.
   Then start the scored set -- **not on the same day**.

**Nothing you do on these three figures is analysed.** Their only job is to surface a
disagreement while it is still free to fix. The residual cost is real and is recorded as a
caveat: calibrating conventions makes the two of you slightly more correlated, which
slightly reduces the independence the analysis wants. It is the right trade, because an
uncalibrated convention difference is bias and bias does not average out.

---

## 5. Stage A -- structure

Build the session (once):

```bash
python3 prepare_session.py build S01
```

It prints a Windows path to `projectA` and writes `sessions/S01/A-WORKSHEET.md`, which
lists the item order and the target figure for each item.

Then, per item, in the listed order:

1. In the tool, press **Select Project Folder** and choose the `projectA` folder. (Once
   per session, not once per item.) Approve the browser's "upload files" prompt -- nothing
   is uploaded; that is just how folder access is worded.
2. Click the item's id in the **Articles** list. The page renders.
3. Read `TARGET.txt` in that item's folder if you are unsure which figure is the target;
   the worksheet says the same thing (e.g. "Figure 1").
4. **Draw the figure box.** Drag a rectangle around the whole figure: all panels, the
   shared legend if there is one, the axis labels, the colourbar -- but **not** the
   caption text. Tight but complete.
5. **Check the caption.** The tool auto-fills it. If it grabbed the wrong caption or only
   part of it, fix it by hand (the caption textarea in the Figures pane).
6. **Draw one subfigure box per panel.** Click into the figure to open the subfigure
   overlay, then drag a box per panel. Same rule: the panel's plot area plus its own axes
   and axis labels; exclude anything shared between panels (see §8).
7. **Rename each subfigure to its caption letter.** The text box next to each subfigure
   thumbnail. Use the letter *as the caption writes it*, upper-cased: `A`, `B`, `C`. Not
   `Figure 1a`, not `panel A`. Just `A`.
8. If the panel count or letters are ambiguous, apply §8 -- and record it.
9. Press ENTER on the timer.

When the block is done:

10. Press **Export All Articles**. You get `projectA_all_figures.zip`.
11. Unzip its **contents** into `sessions/S01/exports/passA/` so you end up with
    `exports/passA/<item_id>/annotations.json`.
12. Build Stage B:

    ```bash
    python3 prepare_session.py build-b S01
    ```

    This reads your panel boxes, re-renders each panel at working magnification, and
    writes one blank coding form per panel. It refuses if any export carries the
    detector's fingerprints.

---

## 6. Stage B, part 1 -- the coding form (semantics BEFORE pixels)

One file per panel: `sessions/S01/coding/<panel_item>.form.json`. Open it in a text
editor. Every field starting with `_` is documentation -- `_allowed` lists the exact legal
values, pulled live out of the tool's own vocabulary, so anything else will be rejected.

Fill it in **before** you open the digitizer for that panel.

| field | what to put |
|---|---|
| `charType` | one of `_allowed.charType`. What the panel *is*: `bar`, `grouped-bar`, `box`, `line`, `scatter`, `forest`, `micrograph`, … |
| `extractable` | `true` if this panel carries group means/medians you could digitise; `false` for micrographs, schematics, flow diagrams. If `false`, fill `charType` and stop -- no other fields, no digitising. |
| `dataProvenance` | `primary` if these are the study's own measurements; `derived` if the panel summarises *other* studies (a forest plot of prior work). |
| `axes.x.scale`, `axes.y.scale` | `linear`, `log`, `categorical`, `time`, `percent`, … Bar-chart x-axes are `categorical`. **A log axis must be declared** -- digitising a log axis as linear is silently wrong. |
| `axes.y.unit` | free text, e.g. `s`, `% freezing`, `entries/min`. |
| `dispersion.present` | `true` if error bars / boxes are drawn. |
| `dispersion.type` | `SD`, `SEM`, `CI95`, `IQR`, `range`, `none`, `unknown`. **Read this from the caption or methods, never from the picture** -- SD and SEM look identical. |
| `dispersion.evidence` | **Quote the sentence you got it from**, with its source. `"caption: 'Data are mean ± SEM'"` or `"methods p.4: 'values are mean ± SD'"`. The ingest rejects an asserted type with no quoted evidence. If nothing in the paper says, set `type` to `unknown`, add the flag `dispersion-type-uncertain`, and record an ambiguity. |
| `series[]` | one entry per **legend entity** (usually one per arm). `id` is a short join key (`s1`, `s2`); `label` is the **printed legend text, verbatim**; `role` is the meaning: `control`, `intervention`, `comparison`, `reference`, `subgroup`, `pooled`. `encoding` is how it is distinguished (`fill`, `color`, `shape`, `linetype`, `position`, `direct-label`). `labelSource` is where the text came from (`legend`, `direct-label`, `axis`, `caption`). |
| `series[].n` | the group size. |
| `series[].nSource` + `series[].evidence` | where *n* came from, and the quote. `"caption"` / `"n = 8 per group"`. |
| `marks[]` | **the roster.** One entry per mark you are going to click, in strict **left-to-right** order across the panel (top-to-bottom for forest plots). `group` is the categorical-axis position (`"probe"`, `"week 4"`, `""` if there is only one); `seriesId` points at the arm. **This ordering is load-bearing** -- §7 decodes your clicks against it, and a mismatch is a hard error, not a guess. |
| `direction` | `1` if a higher value is a better outcome, `-1` if lower is better (latency to escape, error counts). Get this from the outcome's meaning, not the figure. |
| `timepoint` | free text if the panel is one timepoint of several (`"day 10"`). |
| `nonDataElements` | ink present but not data: `legend`, `significance-markers`, `gridlines`, `axis-ticks`, `title`, `panel-label`, `colorbar`, `image-inset`, `trend-line`, `reference-line`. |
| `flags` | from `_allowed.flags` only. Common ones: `dispersion-type-uncertain`, `log-axis`, `error-bars-one-sided`, `n-unknown`, `overlapping-series`, `series-unlabeled`, `low-resolution`, `broken-axis`, `dual-y-axis`. |
| `ambiguities[]` | see §8. `{"field": "...", "why": "...", "resolution": "abstain"｜"guess", "confidence": 0.0-1.0}` |
| `notes` | anything else. |

**Two things the ingest will refuse outright:**

- a series with no `role` (an unassigned arm is the single most damaging error in this
  whole pipeline -- it computes the effect backwards and *nothing downstream detects it*);
- a `dispersion.type` asserted with an empty `evidence`.

Both can be satisfied by abstaining honestly: set the value to `unknown` / `null` and add
an `ambiguities` entry. Refusing to answer is always allowed. Answering without evidence
is not.

---

## 7. Stage B, part 2 -- the landmark picks

In the tool, press **Select Project Folder** and choose `projectB`. Then per panel, in
worksheet order:

1. Click the panel's id in the Articles list. A figure box is already drawn for you around
   the panel content. Click the **📈** button on it to open the digitizer.

2. **Zoom to 1:1 before you click anything.** See §7.1.

3. **Set the axes.** Press **1. Set axes** and click four points in the order the hint
   line tells you: X₁, X₂, Y₁, Y₂. Then type the four data values into the boxes.

   - Click **tick marks**, not axis ends, and pick the two *furthest apart* ticks you can
     read confidently. A short baseline multiplies every later error.
   - **Categorical x-axis** (all bar charts): click the centre of the first category as
     X₁ with value `0`, and the centre of the *second* category as X₂ with value `1`.
     The tool needs a non-degenerate x-axis even when x carries no meaning.
   - **Log axis**: tick the `log` box for that axis *and* set `axes.<n>.scale` to `log` in
     the coding form. Both.

4. **Name the series to match the landmark slots.** The series chips are at the right.
   Double-click a chip to rename it; **+ Series** adds one. The name *is* the slot, spelled
   exactly:

   | chart type | series to create, in this order |
   |---|---|
   | `bar`, `grouped-bar`, `histogram` | `top`, then `cap` |
   | `box`, `violin` | `median`, `q1`, `q3`, then `min` and `max` if whiskers are drawn |
   | `forest` | `estimate`, `ciLo`, `ciHi` |
   | `line`, `scatter` | leave the single default series; click freely |

   Omit `cap` entirely if `dispersion.present` is `false`. Omit `min`/`max` if there are no
   whiskers.

5. **Pick the landmarks.** Press **2. Add points**. Click a series chip to make it active,
   then click *all* of that slot's marks **left to right**, then switch to the next chip.

   - `top` = the **top edge of the bar**, at the bar's horizontal centre.
   - `cap` = the **centre of the error-bar cap** on the *same* bar, same horizontal
     position. Only the upper cap; if the bar has caps both ways, still click the upper
     one and note it.
   - The number of clicks in each slot must equal the number of entries in `marks[]`.

6. **Check the points table.** It shows every point's recovered data value live. Sanity-check
   it against the axis: a bar you eyeballed at "about 18" should read about 18. If it does
   not, your calibration is wrong -- press **1. Set axes** and redo it. Delete a bad point
   with the `×` in its row.

7. Press **Done**, then ENTER on the timer.

When the block is finished: **Export All Articles**, and unzip the contents into
`sessions/S01/exports/passB/`.

### 7.1 Zoom discipline -- the 1:1 rule

Your hand jitter is roughly one **screen** pixel, always. So the only thing that reduces
your error is making the mark **bigger on screen**. This is why the panels are pre-enlarged
and why you must still zoom in.

Every Stage B panel has a **striped patch** burned into the strip along its bottom edge:
alternating 1-pixel black and white vertical lines, next to the label
`1:1 check - must show separate lines`.

> **Before you click any landmark, scroll-zoom (mouse wheel over the image) until that
> patch resolves into visibly separate black and white lines rather than a flat grey
> smear. Shift-drag to pan back to the mark you are picking.**

That is a genuine optical criterion, not a rule of thumb: below 1:1 the grating aliases
into grey; at or above 1:1 it resolves. Passing it guarantees one screen pixel is at most
one image pixel, which is what lets the audit report a *conservative* estimate of your
jitter instead of an optimistic one.

**Zoom in further than 1:1 whenever the cap is short.** The rule of thumb that matters:
the vertical distance from bar top to cap should span **at least ~100 screen pixels**
before you click. At that separation, one pixel of jitter is a 1% dispersion error; at 25
pixels it is 4%.

### 7.2 Screen pixels, image pixels, and which one the audit uses

These are two different units and the protocol needs both, so here is the exact relation.

Let `k` be the digitizer's **magnification**: screen pixels per image pixel. It is printed
live in the digitizer header (`1.85x`, next to the panel name), and it is recorded in your
export -- once per panel as `digitization.k`, and again on every individual point as the
`k` in force when you clicked it.

```
screen span = k x image span
```

- **The rule you follow is in SCREEN pixels**, because your hand jitter is ~1 screen pixel
  no matter how far you have zoomed. `>= 100 screen px` from bar top to cap.
- **The audit's floor is in IMAGE pixels** (`ZOOM_FLOOR_PX = 100` in
  `ingest_annotations.py`), because image pixels are what the stored geometry is in.

The 1:1 grating (§7.1) guarantees `k >= 1`, so an image span of >= 100 px is *always* also
a screen span of >= 100 px. The image-pixel floor is therefore **conservative**: it can
flag a landmark you actually picked at adequate screen magnification, but it can never
miss one you picked too small. That is the direction you want an audit to err in.

The audit reports both:

```bash
python3 ingest_annotations.py audit --session S01
```

It prints the implied 1-pixel jitter per channel, and **names every landmark whose
cap-to-top span fell below 100 IMAGE px**, with the recorded `k` and the implied screen
span beside it. Re-pick anything whose **screen** span is under 100. A landmark below the
image-pixel floor but comfortably above 100 screen px is fine and the audit says so --
that is what recording `k` bought. Do not argue with the screen-span column; that number
is the measurement telling you it is not good enough yet.

---

## 8. Ambiguity rules

**The general rule: never guess to fill a blank.** Record the ambiguity and abstain. An
abstention is data -- it tells us the figure is genuinely under-determined, which is a
finding about published figures, not a gap in your work.

Every judgement call below gets an entry in the relevant `ambiguities[]` list:

```json
{"field": "dispersion.type", "why": "caption says 'error bars' with no type; methods silent",
 "resolution": "abstain", "confidence": 0.0}
```

`resolution` is `"abstain"` (you left it `null`/`unknown`) or `"guess"` (you filled
something you are not sure of -- then set `confidence` honestly, 0.0-1.0).

### 8.1 Panels sharing an axis

A row of panels sharing one y-axis on the left.

> **Rule.** The shared axis belongs to the **leftmost (or bottom-most) panel only.**
> Every other panel's box starts at its own plot area. Add flag `axis-partially-visible`
> to every panel that does not own the axis, and record an ambiguity on `panels`.
> Do not duplicate the shared axis into several boxes and do not stretch one box to
> swallow the neighbours.

Calibration still works for the axis-less panels: in Stage B their crop excludes the
axis, so use the **gridlines or the panel frame** as your Y references if the values are
printed, and if they are not, mark the panel `extractable: false` with an ambiguity
saying the axis is not inside the panel.

### 8.2 A legend that serves two or more panels

> **Rule.** The legend is **not** part of any panel box. Include it in the *figure* box
> only. List `legend` in `nonDataElements` for every panel it applies to, and put the
> legend text into each panel's `series[].label` -- the label is a property of the series,
> not of the box.

### 8.3 A colourbar

> **Rule.** Same as a legend: inside the figure box, outside every panel box, listed as
> `colorbar` in `nonDataElements`. A heatmap panel whose only quantitative scale is the
> colourbar is `extractable: false` unless you can read values off it directly -- say so
> in an ambiguity.

### 8.4 An inset

A small axes drawn *inside* a larger panel.

> **Rule.** The inset is **not** a separate panel unless the caption gives it its own
> letter. If the caption does not name it: leave it inside the parent panel's box, add
> `image-inset` to `nonDataElements`, and do not digitise it. If the caption *does* name
> it (e.g. "(C) inset"), draw it as its own subfigure box with that letter, overlapping the
> parent -- overlapping boxes are fine and are what the caption asserts.

### 8.5 Significance asterisks over an error cap

This is a **known, measured failure mode**: a one-shot read confuses the asterisk with the
cap and misses by 30-45 px, a 22-36% dispersion error.

> **Rule.** The cap is the **short horizontal rule** that terminates the vertical whisker.
> The asterisk is a glyph *floating above it*, not touching the whisker, and usually
> larger. Zoom past 1:1 until you can see the whisker's end. Click the whisker's
> termination, not the glyph.
> If the asterisk genuinely overlaps and hides the cap, **do not guess the cap**: omit
> that mark's cap, add flag `occluded`, and record an ambiguity on `marks[i].cap`.
> Add `significance-markers` to `nonDataElements` whenever asterisks are present.

### 8.6 A panel with no visible label

> **Rule.** If the caption enumerates panels, assign letters by **reading order** --
> left-to-right, then top-to-bottom -- and label them accordingly, then record an
> ambiguity on `panels` with `resolution: "guess"` and a confidence. If the caption does
> *not* enumerate panels either, label them `A`, `B`, `C` in reading order, add flag
> `no-legend` if applicable, and record the ambiguity. Never leave a box unnamed.

### 8.7 Drawn letters that disagree with the caption

The figure shows A-D; the caption talks about (a), (b), (c), (e).

> **Rule.** **The drawn letters win** for naming the boxes -- they are what a reader of
> the figure sees. Record an ambiguity on `panels` quoting both, e.g.
> `"figure draws A-D; caption enumerates (a),(b),(c),(e) -- no (d)"`. Do not silently
> reconcile them, and do not renumber to make them match. The disagreement is the finding.

### 8.8 Panel count disagrees with the caption

> **Rule.** Same principle: draw the boxes **you can see**, record an ambiguity on
> `panels` stating the count you drew and the count the caption implies. Do not add a
> phantom box to reach the caption's number and do not merge two visible panels to reduce
> to it.

### 8.9 A shared x-axis label or a title sitting in the gutter between panels

> **Rule.** Shared furniture goes in **neither** panel box. Panels stop at their own plot
> content. Add `title` or `axis-ticks` to `nonDataElements` as appropriate.

### 8.10 Which arm is control?

> **Rule.** Assign `role` from the **caption, legend, and methods** -- never from bar
> order and never from which bar is taller. If the paper genuinely does not identify a
> control (e.g. two active treatments), use `comparison` for both, or `unknown` plus an
> ambiguity. A guessed `control`/`intervention` assignment is the worst possible error
> here: it computes the effect backwards and produces a perfectly plausible negative
> result that no downstream check will catch.

### 8.11 Error bars drawn in one direction only

> **Rule.** Click the cap that is drawn. Add flag `error-bars-one-sided`. (The integrity
> check expects caps above the bar top; if a bar points *downward* the flag is what stops
> the ingest treating it as a mis-click.)

### 8.12 A broken / truncated axis

> **Rule.** Add flag `broken-axis`. If both your Y reference ticks lie on the *same*
> continuous segment, the calibration is valid -- proceed. If the marks you need lie
> across the break, the panel is `extractable: false`; record the ambiguity.

### 8.13 A bar whose top is hidden behind another bar or a data-point cloud

> **Rule.** If you cannot see the top edge, do not infer it. Omit the mark, add flag
> `occluded`, record the ambiguity. A missing mark costs coverage; an invented one
> corrupts the reference.

### 8.14 A panel that is a micrograph, schematic, or flow diagram

> **Rule.** `charType` = `micrograph` / `schematic` / `flow-diagram`,
> `extractable: false`. You still draw its box and give it its letter -- panel structure
> is scored on *all* panels, not just the readable ones.

---

## 9. When you are stuck

In order:

1. **Re-read the caption and the relevant methods paragraph.** Most ambiguity here is
   textual, not visual.
2. **Zoom further.** Half of what looks ambiguous at 1:1 is obvious at 4:1.
3. **Still ambiguous? Abstain and record it.** That is the correct answer, not a failure.
   Move on -- do not spend more than about 3 minutes on any single judgement call.
4. **The tool misbehaves** (a box will not draw, the digitizer will not open): note the
   item id, skip it, and keep going. Do not fight it mid-session. It will show up in the
   ingest as a missing export and can be redone.
5. **You realise you made a mistake several items back.** Go back and fix it *within the
   same session* -- your work is live in the browser until you export. Do not fix anything
   after you have exported and ingested; the export is sealed, and a later edit breaks the
   hash check. Report it instead and the item can be re-run.

---

## 10. Saving, exporting, ingesting

The tool saves to browser storage on every change; there is no Save button. But **nothing
leaves the browser until you export**, so:

- Export at the **end of every block**, not at the end of the day.
- **Export All Articles** (not "Export This Article") -- it bundles every item you opened
  in that project folder. Items you never opened are silently omitted, so check the item
  count in the zip against the worksheet.
- Unzip **contents** into `exports/passA/` or `exports/passB/`. You want
  `exports/passB/<panel_item>/annotations.json`, not
  `exports/passB/projectB_all_figures/<panel_item>/annotations.json`.

Then:

```bash
python3 ingest_annotations.py ingest S01
```

This validates everything, converts your pixels to data through the tool's own affine,
writes the normalized ground-truth store, and **seals** the session with hashes and a UTC
timestamp. It will refuse and tell you exactly what is wrong -- a form value outside the
vocabulary, a click count that disagrees with your roster, a cap that is nowhere near its
bar top, a missing `annotationMode` stamp, a detector fingerprint. Fix and re-run. Nothing
is written until it all passes. (`--allow-problems` ingests the valid panels and warns about
the rest; use it only when a panel genuinely cannot be fixed.)

**Re-ingesting a session you have already ingested is destructive, and the ingest now says
so.** It replaces every record for that session, which is what you want when you are redoing
the session in full -- and is data loss when the second run produces *fewer* panels than the
first, which is exactly what `--allow-problems` after a clean run does. The ingest compares
the two sets, **names every panel that would disappear, and refuses**:

```
! RE-INGEST WOULD DESTROY 1 PANEL RECORD(S) already in human_gt.jsonl:
!     - it04_9c1a_pB
! prior: 4 records for S01; this run produced 3.
refusing to write. Nothing has been changed in human_gt.jsonl.
```

A panel that ingested cleanly before and does not now is a **regression**, not a correction:
find the missing export first. Only if the loss is genuinely intended -- the panel was
withdrawn -- add `--reingest`, which writes anyway and prints what it discarded.

Then:

```bash
python3 ingest_annotations.py audit --session S01
```

Read the audit. Act on the zoom-floor list before moving on.

Once several sessions including repeats are in:

```bash
python3 ingest_annotations.py intra
```

That is the report that gives your reference its error bar.

`python3 prepare_session.py status` shows where every session stands.

---

## 11. Worked example

**Item `it04_9c1a`, Figure 1 of a rodent enrichment study.** Two panels side by side, each
a two-bar chart with error bars; the caption reads:

> *Figure 1. Effect of environmental enrichment on spatial memory. (A) Time in target zone
> during the 1-day probe. (B) Time in target zone during the 10-day probe. Open bars,
> standard cage (SC); filled bars, enriched environment (EE). Data are mean ± SEM;
> n = 5 per group. \*p < 0.05.*

### Stage A

Draw the figure box around both panels plus the shared y-axis label, excluding the caption
text. The tool auto-fills the caption -- it caught the whole thing, so leave it. Draw two
subfigure boxes; each includes its own y-axis and x tick labels. Rename them `A` and `B`.
There is no legend graphic (arms are described in prose), so nothing to exclude. ~90
seconds.

Export, unzip to `exports/passA/`, run `build-b`. The harness produces `it04_9c1a_pA` and
`it04_9c1a_pB`, each ~2200 px on the long edge at 720 dpi, and two blank forms.

### Stage B, form for panel A

```json
{
  "panel_item": "it04_9c1a_pA",
  "panelLetter": "A",
  "charType": "bar",
  "extractable": true,
  "dataProvenance": "primary",
  "axes": {"x": {"scale": "categorical", "unit": ""},
           "y": {"scale": "linear", "unit": "s"}},
  "dispersion": {"present": true, "type": "SEM",
                 "evidence": "caption: 'Data are mean ± SEM'"},
  "series": [
    {"id": "s1", "label": "SC", "role": "control", "encoding": "fill",
     "labelSource": "caption", "n": 5, "nSource": "caption",
     "evidence": "caption: 'Open bars, standard cage (SC)' ; 'n = 5 per group'"},
    {"id": "s2", "label": "EE", "role": "intervention", "encoding": "fill",
     "labelSource": "caption", "n": 5, "nSource": "caption",
     "evidence": "caption: 'filled bars, enriched environment (EE)' ; 'n = 5 per group'"}
  ],
  "marks": [{"group": "target", "seriesId": "s1"},
            {"group": "target", "seriesId": "s2"}],
  "direction": 1,
  "timepoint": "1-day probe",
  "nonDataElements": ["axis-ticks", "significance-markers"],
  "flags": [],
  "ambiguities": [],
  "notes": "Arms identified in prose, not a legend graphic -- labelSource is 'caption'."
}
```

Note `direction: 1`: more time in the target zone is better memory. Note
`labelSource: "caption"` rather than `"legend"` -- there is no legend box. Note
`significance-markers`, because an asterisk sits over panel A.

### Stage B, picks for panel A

Open the digitizer. Wheel-zoom until the striped patch at the bottom shows separate lines
-- roughly six wheel clicks from the default fit, since each click is 1.15x -- then
shift-drag to pan back to the y-axis.

**Axes.** `1. Set axes`, then click: the SC bar's centre on the x baseline (X₁, value `0`),
the EE bar's centre (X₂, value `1`), the `0` tick on the y-axis (Y₁, value `0`), and the
`25` tick (Y₂, value `25`) -- the furthest apart pair that is unambiguously labelled.

**Series.** Rename the default chip to `top`. Press **+ Series**, rename it to `cap`.

**Picks.** Click the `top` chip. Click the SC bar top, then the EE bar top -- left to
right, matching `marks[]`. Click the `cap` chip. Zoom further: the SC cap sits only ~70
screen px above its bar top at 1:1, below the 100 px floor. Three more wheel clicks
(1.15³ ≈ 1.5x) takes it past 105. Now click the SC cap centre, then the EE cap centre.

The asterisk sits about 40 px above the SC cap. Zoomed in it is obviously a glyph floating
free of the whisker -- click the short horizontal rule where the whisker *ends*, not the
asterisk.

**Check the table.** It reads:

| # | series | x | y |
|---|---|---|---|
| 1 | top | 0.00 | 18.58 |
| 2 | top | 1.00 | 18.36 |
| 3 | cap | 0.00 | 21.03 |
| 4 | cap | 1.00 | 20.61 |

Bars around 18-19 s on a 0-25 axis: consistent with what you see. Caps ~2.3 s above the
tops, so SEM ≈ 2.3, SD ≈ 2.3 × √5 ≈ 5.1. Plausible. Press **Done**.

### After

Export, unzip to `exports/passB/`, `ingest S01`, `audit --session S01`. The audit reports
a median implied jitter of ~0.3% central and ~1.4% dispersion, and no landmark below the
zoom floor. Panel A took 4 minutes 10 seconds.

Three days later the same figure comes back as `it11_4b7e`. You annotate it fresh. The
intra-rater report later pairs the two reads and reports how far apart they were -- which
is exactly the tolerance inside which no machine can be called wrong.

---

## 12. Tool support for this protocol -- what is implemented, and where

All three of the changes this section used to *propose* are now in
`figure-extractor.html`. This section is the record of what they do and where to check
them, not a wish list. `schemaVersion` stays **2**: every change is additive, and
`figuresFromJSON` passes `digitization` through opaquely, so older exports still load.

### 12.1 `annotationMode` -- blind mode (REQUIRED, §1.3)

A Settings toggle. When on:

| what it does | where |
|---|---|
| the setting exists and persists per browser profile | `figure-extractor.html:1300` (`settings`), `:1398` (checkbox state), `:1546` (`onchange`) |
| the `✨ Auto-panels` button is not rendered | `:2894` -- `if (!locked && !settings.annotationMode)` in the Subfigures pane |
| `detectPanels` refuses and returns `flags:['annotation-mode']` with no boxes | `:6745` |
| `suggestSubfiguresLegacy` refuses identically | `:6763` -- it was the hole: it returns bare boxes, writes no `panelDetection` and stamps no `captionSource:'panel-split'`, so boxes taken from it left **no fingerprint at all** |
| `"annotationMode": true` is stamped into the export | **both** export sites: `:5941` (the inline duplicate) and `:6184` (`buildAnnotations()`) |

Enforcement is symmetric across the two raters: `rvcommon.annotation_mode_violations()`
is the single implementation, called by `ingest_annotations.py` for Greg and by
`prepare_dan_session.check_exports` for the second rater, with the same severity and the
same message. An export without the stamp is rejected, not warned about.

### 12.2 Exported magnification -- the zoom floor in the unit the rule is written in

`persistDig()` (`figure-extractor.html:~5592`) now stores, alongside
`cal / vals / points / series / notes`:

```jsonc
"view":  { "zoom": 1.75, "panX": -412, "panY": -88 },
"scale": 1.06,                 // the crop-to-canvas fit factor
"k":     1.855                 // = scale * view.zoom, screen px per image px
```

and every point records the `k` in force **when it was clicked**
(`dig.points.push({px, py, s, k})`).

*Why it mattered:* §7.1's rule is stated in **screen** pixels and the audit could only
measure **image** pixels, so it had to assume `k >= 1` from the grating and report a lower
bound. With `k` in the artifact the audit computes `screen = k x image` and names the
landmarks that genuinely fail the rule instead of the ones that merely look small. See
§7.2 for the arithmetic and `ingest_annotations.py::jitter_report`.

### 12.3 Live magnification readout

The digitizer header prints `k` continuously (`1.85x`, next to the panel name;
`figure-extractor.html::digRender`). The 1:1 grating was always a workaround for a missing
number. Use the number: it lets you hit a magnification target directly rather than judging
whether a grating has aliased.

### 12.4 Stale-work guard on session rebuilds

`localStorage` is keyed by article name, so a rebuilt session used to silently serve the
*previous* run's boxes over the freshly written `annotations.json`. The harness now writes
`"forceCleanLoad": true` into every session's `annotations.json`, and the tool discards the
cached copy and tells you it did (`figure-extractor.html::loadArticleAnnotations`). If you
ever see a toast saying your item is being served from **browser storage** rather than the
session file, stop: that item was rebuilt and you are looking at stale work.

---

## 13. If you only remember five things

1. **`Annotation mode` ON**, always. An export without the stamp is rejected, not warned
   about -- and with it on, **Auto-panels** is not even shown.
2. Fill the coding form **before** you pick landmarks.
3. Zoom until the striped patch shows **separate lines**, and further still for short caps.
4. Click each landmark slot **left to right**, matching the `marks[]` roster exactly.
5. **Abstain and say why** rather than guess. Especially for dispersion type and arm role.

---

## 14. Command card

```bash
cd /mnt/c/Users/gregs/figure-extractor/benchmark/real-validation

python3 prepare_dan_session.py calibrate         # ONCE, first: the two-rater calibration
python3 prepare_dan_session.py calibrate --stage-b   #   ... after both Stage A exports return

python3 prepare_session.py plan                 # once, for the whole corpus
python3 prepare_session.py status               # where everything stands

python3 prepare_session.py build S01            # Stage A materials
python3 prepare_session.py timer S01 A          # stopwatch, Stage A
#   -> annotate in the tool -> Export All Articles
#   -> unzip contents into sessions/S01/exports/passA/
python3 prepare_session.py build-b S01          # Stage B crops + coding forms
python3 prepare_session.py timer S01 B          # stopwatch, Stage B
#   -> fill sessions/S01/coding/*.form.json
#   -> digitize in the tool -> Export All Articles
#   -> unzip contents into sessions/S01/exports/passB/
python3 ingest_annotations.py ingest S01        # validate, normalize, seal
python3 ingest_annotations.py audit --session S01

python3 ingest_annotations.py intra             # after the repeat sessions land
python3 ingest_annotations.py verify-seal       # nothing has been edited since
```

Tool: `C:\Users\gregs\figure-extractor\figure-extractor.html` (open as a **file://** page).

Session folders: `C:\Users\gregs\figure-extractor\benchmark\real-validation\sessions`
