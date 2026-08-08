# Second-rater protocol -- instructions for Dan

**You have not seen this project before. You do not need to have.** This document is
self-contained: read it once end to end, do the calibration round in §4, then work from the
card in §12. Everything you need is here, and everything you need to *run* is in the zip this
document came in; you should not have to ask a question to finish correctly, and the only
other files you should open are the ones §3 lists.

Budget: **~40 min calibration + ~4 h annotation**, over three sittings.

---

## 1. What the project is, in one page

Greg's dissertation was a meta-analysis of rodent behavioural studies. A large part of the
data was read *out of published figures by hand* -- put a cursor on the top of a bar, put a
cursor on the top of the error bar, convert pixels to data units. That is normal practice
in meta-analysis and nobody knows how good it is.

He has since built a tool (`figure-extractor.html`) that lets a machine do the same job, and
the question is whether the machine can be trusted with it. Two channels matter:

- the **central value** (the top of the bar). Easy. A bar top is a long pixel distance from
  the axis, so a one-pixel slip is a ~0.4% error.
- the **dispersion value** (the length of the error bar). Hard. An SEM cap sits only a few
  pixels above the bar top, so *the same one-pixel slip* is a ~4% error, and up to ~37% on
  the worst panel measured. About 91% of this corpus plots SEM, i.e. the short-cap case.

So the whole study turns on the error-bar channel, and there the human is not a gold
standard -- the human is just another imprecise instrument. Comparing machine to human
there measures the disagreement of two imprecise readers, not the machine's accuracy.

**Where you come in.** The study currently has three readings of each panel: `D` (Greg's
original dissertation extraction, years ago, different tool), `G` (Greg's fresh annotation,
now), and `M` (the machine). `D` and `G` are **the same person**. Two readings by one person
bound how much he disagrees *with himself* -- test-retest -- which systematically understates
how much two competent people would disagree. Every sentence in the write-up currently has to
say "this human, twice", and a reviewer will immediately ask the obvious question.

**You are the answer to that question.** Your reading is called `H2`. You are a genuinely
independent second rater, and `H2` vs `G` is real inter-rater reliability. On the subset you
read, three things become possible that are not possible now:

1. the error-bar reliability number stops being "one man, twice" and becomes "two people";
2. the machine's error variance can be estimated from three instruments *no two of which
   share a person* -- which removes a known bias in the current estimate;
3. the size of that bias becomes measurable rather than merely argued about.

That is the whole reason you are being asked. It is about 4 hours of work and it upgrades the
central claim of the study.

**You are not being tested.** Writing down "I could not tell, and here is why" is a *result*
and a useful one. Guessing in order to avoid a blank is the only thing that damages the data.

---

## 2. What you must and must not see

Two things must stay hidden from you, and both are enforced mechanically rather than by
your good intentions.

**(a) You must not see the machine's answer.** If you see where the detector put a box, your
box moves toward it, and the comparison is destroyed.

> **Turn on `annotationMode` in the tool's Settings (gear icon) before you do anything else,
> and never turn it off.** It hides the `✨ Auto-panels` button, makes the panel detector
> refuse to run at all, and stamps a marker into every file you export. The harness
> **rejects any export that does not carry that marker** -- so a session done with the
> setting off is not merely suspect, it is unusable and has to be redone.

**(b) You must not see Greg's answer.** That is why you are getting a zip file rather than a
repository checkout. Your zip contains page images, blank coding forms, a worksheet, the tool
and a stopwatch, and nothing else -- no boxes, no values, no key. The packer that builds it
walks the archive and refuses to write it if anything else got in.

Your items are named things like `dn03_9c1a`, with a `dn` prefix Greg never uses. Two
separate things stop those ids lining up with his, and it is worth being precise about which
one is doing the work. The one that matters is **procedural**: you do not have his session
materials, his worklist or his key, and you are asked not to go looking for them. Behind it
sits a mechanical one: your ids *and* your item order are both drawn from a seed generated
once on his machine and committed nowhere, so the mapping cannot be recomputed even by
someone holding the entire codebase.

An earlier version of this paragraph claimed the mechanical half alone made alignment
impossible -- "a different random stream over a different item list". It did not. The stream,
the item list and the seed were all in the repository, and the mapping came back in about a
dozen lines; `attack_dan_ids.py` is the script that showed it, and it now recovers nothing.
The blinding you should rely on is the first kind. Do not try.

**What you *are* free -- and expected -- to read:** the figure, its caption, the figure
legend, and the methods section of the paper. The machine gets the caption too. That is
shared input, not a leak.

If you happen to recognise a figure or a paper, that is fine and unavoidable. Just do not go
looking for anyone else's reading of it.

---

## 3. Setup (once)

**You need nothing from Greg's machine.** The zip is self-contained: the tool, the
stopwatch, the page images, the worksheet and this document are all inside it. No checkout,
no server, no install beyond a Python 3 you probably already have. Every path in this
document is relative to the folder you unzip into -- this document calls it your **work
folder**, and you choose where it lives.

1. **Unzip your handoff** somewhere convenient. You get:

   ```
   figure-extractor.html      the tool
   dan_timer.py               the stopwatch
   HANDOFF.txt                the one-screen version of what to do and what to send back
   SECOND-RATER-PROTOCOL.md   this file
   A-WORKSHEET.md             the item order              -- Stage A
   projectA\                  one folder per item          -- Stage A
   B-WORKSHEET.md             the panel order              -- Stage B
   projectB\                  one folder per panel         -- Stage B
   coding\                    one blank coding form per panel  -- Stage B
   ```

2. **Open `figure-extractor.html` from the file system, not from a local server.** It is in
   your work folder; double-click it, or paste its path into Windows Explorer's address bar
   or the Run dialog (Win+R).

   It must open as a **`file://`** page. Do *not* start it via `start-figure-extractor.bat`
   or any `http://localhost` address: when the tool is served over localhost it **hides the
   Select Project Folder button**, which is the only way to load your session. If you cannot
   see a *Select Project Folder* button, this is why.

   Use **the copy in your zip**, not one you find elsewhere. Its checksum was recorded when
   the handoff was built, so which version of the tool you annotated with is on the record
   rather than a matter of recollection.

3. **Stay online.** The tool pulls a zip library from a CDN; without it the Export buttons
   silently do nothing.

4. **Settings (gear icon):**
   - **`Annotation mode` -> ON.** Non-negotiable; see §2.
   - *Auto-detect caption when drawing a figure* -> **ON**. The caption is input, not an
     answer -- you are supposed to read it and so is the machine.
   - The DPI setting is irrelevant; your pages are pre-rendered.

5. **Use the same browser profile, the same monitor and the same display scaling for every
   sitting.** Your work lives in that profile's `localStorage` until you export, and changing
   monitors mid-way changes your click precision, which is one of the things being measured.

6. **Do not clear browsing data** between opening a session and exporting it.

---

## 4. Calibration round -- do this FIRST, and do not skip it

Inter-rater studies fail far more often from **two people silently using different
definitions** than from anybody being careless. Does the panel box include the axis labels?
Is "the top of the bar" the top edge of the outline or the middle of it? Is the cap its
centre line or its upper edge? Two raters who answer those differently produce a large,
perfectly reproducible disagreement that looks like unreliability and is actually just a
missing convention.

Settling that costs 40 minutes. Not settling it costs the study.

### The calibration panels

You get two separate zips, **`DAN-C01-stageA.zip`** and then **`DAN-C01-stageB.zip`**,
covering the same **three figures**. Greg gets the identical zips. They are **not part of
your scored set and never will be** -- they come from papers this project has already used
for pilot work, which are permanently excluded from the scored analysis, and they are built
into a separate data tree that the analysis cannot reach. They are:

| # | what it is | conventions it forces -- **Stage A** | conventions it forces -- **Stage B** |
|---|---|---|---|
| C1 | 2 tiles, grouped bar, SEM named in the caption -- the plain case | does the panel box include the y-axis and its tick labels | where exactly is the bar top -- the top edge of the outline or the middle of it; where exactly is the cap -- its centre line or its upper edge |
| C2 | 6 tiles sharing an axis, SEM, with significance glyphs genuinely sitting over the caps (this is the figure that produced this project's asterisk-occlusion finding) | who owns a shared axis | asterisk vs cap; what counts as occluded |
| C3 | 5 visible tiles, caption names only 4 letters | what is a panel; do you split; how do you name an unlabelled tile | -- (nothing here to digitise) |

**Read which column is which.** Panel boxes are Stage A, and they are the cheap half: a
1-pixel slip on a 400-pixel box is 0.25%. Every convention that moves a *number* -- the bar
top, the cap, the asterisk -- is a **Stage B** landmark pick. A calibration round that
stopped after Stage A would settle the boxes and none of the measurements, which is why the
round runs both stages before anybody compares anything.

Do them exactly as you would a scored figure: Stage A on all three, then Stage B on the chart
panels. The round doubles as a dry run of the tool, the export and the handoff, so any
mechanical problem surfaces on panels that do not matter.

**These three figures are NOT part of the scored set. Nothing you do on them is analysed.**
Their only job is to surface a disagreement while it is still free to fix.

### How to run it

1. **Stage A, both raters, independently and without discussion.** You each get
   `DAN-C01-stageA.zip`. Do all three figures as §7 describes -- figure box, one box per
   panel, letters -- press **Export All Articles**, and send the export back. Greg does the
   same, on the same day. Neither of you shows the other anything, and **nobody compares
   anything yet**.
2. **Stage B, both raters, independently.** You get `DAN-C01-stageB.zip` back, built from
   *your own* panel boxes -- it cannot exist before your Stage A does. Do it as §8 describes:
   coding form first, landmarks second, zoom discipline as in §8.3. Export and send back.
3. **Only now**, each of you writes, in a plain text file, **one sentence per convention** --
   literally "I put the box edge at ..." / "I clicked the cap at ...". Six to ten sentences,
   covering both columns of the table above.
4. **Then compare, in a 20-minute call.** Go through the sentences, not the numbers. Where
   you differ, pick one convention and write it down as an amendment at the bottom of this
   file, under §13. Both of you then use it.
5. **Deliberately do NOT compare your measured values on the calibration panels.** Reconcile
   *definitions*, never *readings*. Agreeing "we should both have got about 21.4" would train
   you toward each other on magnitudes, which is precisely the independence the study is
   buying from you. Definitions are arbitrary choices that must be shared; magnitudes are the
   measurement and must not be.
6. Re-do any of the three figures whose convention changed, so you both finish the round
   applying the agreed rules. Then start the scored set -- **not on the same day**.

Greg builds the two zips. Nothing here is yours to run:

```bash
python3 prepare_dan_session.py calibrate             # -> DAN-C01-stageA.zip
# both raters do Stage A and return their projectA exports; unzip them into
# dan/calibration/sessions/C01/exports/passA/, one folder per item, then:
python3 prepare_dan_session.py calibrate --stage-b   # -> DAN-C01-stageB.zip
```

This tension is real and worth naming: calibrating conventions makes the two of you slightly
more correlated, which slightly reduces the independence the analysis wants. It is the right
trade anyway, because an uncalibrated convention difference is *bias*, not noise, and bias
does not average out. The analysis records that the calibration happened and treats the
residual correlation as an explicit caveat.

---

## 5. The shape of the job

Each figure is annotated in **two stages**, and the order is deliberate.

**Stage A -- structure.** You see the whole journal page at 200 dpi. You draw a box around
the figure and one box per panel, and you name the panels. Precision demands are mild here:
a 1-pixel slip on a 400-pixel box is 0.25%.

**Stage B -- meaning, then measurement.** The harness takes the panel boxes *you* drew and
re-renders each panel from the original PDF at 2-4x magnification. For each panel you then
(1) fill in a semantic coding form, and only *after that* (2) click the landmarks.

Two reasons for the split:

- **Zoom.** Reading real figures at page scale was measured to be **22-36% off on the
  dispersion channel** until the panels were re-cropped bigger. The re-crop is not polish; it
  is the difference between a usable and an unusable number.
- **Anchoring.** Deciding what a bar *means* after you have already measured it is
  contaminated. Semantics first, pixels second.

Between the two stages you send your Stage A export back and get a new zip. That is normal;
Stage B literally cannot be built until your panel boxes exist.

---

## 6. Session discipline

- **Follow the worksheet order.** Do not skip ahead and do not do the easy ones first. The
  order is randomised within difficulty strata and then round-robined across them, so hard
  figures are spread evenly. Reordering confounds fatigue with difficulty.
- **Maximum ~20 items per sitting**, and take a **15-minute break after item 10**. Get up.
- **At least 12 hours between sittings.** The harness enforces this and will refuse to build
  the next session early.
- If you catch yourself clicking without really looking, **stop**. A rushed cap pick is worse
  than no cap pick.
- Start the stopwatch and leave it running. From a terminal **in your work folder** -- the
  one holding `dan_timer.py` and the worksheet:

  ```bash
  python3 dan_timer.py A     # Stage A
  python3 dan_timer.py B     # Stage B
  ```

  ENTER to start an item, ENTER again when done (type a short note first if you want).
  `b` logs a break, `q` quits -- re-run the same command and it picks up where you stopped.
  It reads the item order out of the worksheet and writes `timing.jsonl` next to it; send
  that file back with your exports. Timing is a bias control, not surveillance: panels read
  in under 60 s get flagged and reported separately.

---

## 7. Stage A -- structure

Press **Select Project Folder** and choose the `projectA` folder. (Once per sitting, not once
per item.) Approve the browser's "upload files" prompt -- nothing is uploaded; that is just
how folder access is worded.

Then, per item, **in worksheet order**:

1. Click the item's id in the **Articles** list. The page renders.
2. Read `TARGET.txt` in that item's folder if you are unsure which figure is the target; the
   worksheet says the same thing (e.g. "Figure 3").
3. **Draw the figure box.** Drag a rectangle around the whole figure: all panels, the shared
   legend if there is one, the axis labels, the colourbar -- but **not** the caption text.
   Tight but complete.
4. **Check the caption.** The tool auto-fills it. If it grabbed the wrong caption, or only
   part of it, fix it by hand in the caption textarea.
5. **Draw one subfigure box per panel.** Click into the figure to open the subfigure overlay,
   then drag a box per panel. Same rule: the panel's own plot area plus its own axes and axis
   labels; exclude anything *shared* between panels (§9.1, §9.2, §9.9).
6. **Rename each subfigure to its caption letter.** Use the letter as the caption writes it,
   upper-cased: `A`, `B`, `C`. Not `Figure 3a`, not `panel A`. Just `A`.
7. If the panel count or the letters are ambiguous, apply §9 -- and record it.
8. Press ENTER on the timer.

**Annotate every panel of every figure you are given, including the micrographs, schematics
and flow diagrams.** Panel structure is scored on *all* panels, not only the readable ones.
Nobody will tell you how many panels a figure has -- working that out is one of the things
being measured.

When the sitting is done:

9. Press **Export All Articles** (not "Export This Article"). You get
   `projectA_all_figures.zip`.
10. Check the item count in the zip against the worksheet -- items you never opened are
    silently omitted.
11. **Send the zip back.** You will get a Stage B zip in return.

---

## 8. Stage B

### 8.1 Part 1 -- the coding form (semantics BEFORE pixels)

One file per panel: `coding\<panel_item>.form.json`. Open it in a text editor. Every field
beginning with `_` is documentation; `_allowed` lists the exact legal values, pulled live out
of the tool's own vocabulary, so anything else is rejected on ingest.

**Fill the form in before you open the digitizer for that panel.**

| field | what to put |
|---|---|
| `charType` | one of `_allowed.charType`. What the panel *is*: `bar`, `grouped-bar`, `box`, `line`, `scatter`, `forest`, `micrograph`, ... |
| `extractable` | `true` if the panel carries group means/medians you could digitise; `false` for micrographs, schematics, flow diagrams. If `false`, fill `charType` and **stop** -- no other fields, no digitising. |
| `dataProvenance` | `primary` if these are the study's own measurements; `derived` if the panel summarises *other* studies (e.g. a forest plot of prior work). |
| `axes.x.scale`, `axes.y.scale` | `linear`, `log`, `categorical`, `time`, `percent`, ... Bar-chart x-axes are `categorical`. **A log axis must be declared** -- digitising a log axis as linear is silently wrong. |
| `axes.y.unit` | free text: `s`, `% freezing`, `entries/min`. |
| `dispersion.present` | `true` if error bars or boxes are drawn. |
| `dispersion.type` | `SD`, `SEM`, `CI95`, `IQR`, `range`, `none`, `unknown`. **Read this from the caption or the methods, never from the picture** -- SD and SEM look identical. |
| `dispersion.evidence` | **Quote the sentence you got it from, with its source.** `"caption: 'Data are mean ± SEM'"` or `"methods p.4: 'values are mean ± SD'"`. An asserted type with empty evidence is rejected. If nothing in the paper says: set `type` to `unknown`, add the flag `dispersion-type-uncertain`, and record an ambiguity. |
| `series[]` | one entry per **legend entity** (usually one per arm). `id` is a short join key (`s1`, `s2`); `label` is the **printed legend text, verbatim**; `role` is the meaning: `control`, `intervention`, `comparison`, `reference`, `subgroup`, `pooled`; `encoding` is how the arms are distinguished (`fill`, `color`, `shape`, `linetype`, `position`, `direct-label`); `labelSource` is where the text came from (`legend`, `direct-label`, `axis`, `caption`). |
| `series[].n` | the group size. |
| `series[].nSource` + `series[].evidence` | where *n* came from, and the quote. |
| `marks[]` | **the roster.** One entry per mark you are going to click, in strict **left-to-right** order across the panel (top-to-bottom for forest plots). `group` is the categorical-axis position (`"probe"`, `"week 4"`, `""` if there is only one); `seriesId` points at the arm. **This ordering is load-bearing** -- §8.2 decodes your clicks against it, and a mismatch is a hard error, not a guess. |
| `direction` | `1` if a higher value is a better outcome, `-1` if lower is better (escape latency, error counts). Get this from what the outcome means, not from the figure. |
| `timepoint` | free text if the panel is one timepoint of several (`"day 10"`). |
| `nonDataElements` | ink present but not data: `legend`, `significance-markers`, `gridlines`, `axis-ticks`, `title`, `panel-label`, `colorbar`, `image-inset`, `trend-line`, `reference-line`. |
| `flags` | from `_allowed.flags` only. Common: `dispersion-type-uncertain`, `log-axis`, `error-bars-one-sided`, `n-unknown`, `overlapping-series`, `series-unlabeled`, `low-resolution`, `broken-axis`, `dual-y-axis`, `occluded`. |
| `ambiguities[]` | see §9: `{"field": "...", "why": "...", "resolution": "abstain"｜"guess", "confidence": 0.0-1.0}` |
| `notes` | anything else. |

**Two things are refused outright:**

- a series with **no `role`**. An unassigned arm is the single most damaging error in this
  pipeline: it computes the treatment effect backwards and *nothing downstream detects it*.
- a `dispersion.type` asserted with **empty `evidence`**.

Both are satisfied by abstaining honestly -- set the value to `unknown`/`null` and add an
`ambiguities` entry. **Refusing to answer is always allowed. Answering without evidence is
not.**

### 8.2 Part 2 -- the landmark picks

In the tool, press **Select Project Folder** and choose `projectB`. Then per panel, in
worksheet order:

1. Click the panel's id in the Articles list. A figure box is already drawn around the panel
   content. Click the **📈** button on it to open the digitizer.

2. **Zoom first. See §8.3. Do not click anything before you have.**

3. **Set the axes.** Press **1. Set axes** and click four points in the order the hint line
   gives: X₁, X₂, Y₁, Y₂. Then type the four data values into the boxes.
   - Click **tick marks**, not axis ends, and pick the two ticks *furthest apart* that you can
     read confidently. A short baseline multiplies every later error.
   - **Categorical x-axis** (every bar chart): click the centre of the first category as X₁
     with value `0`, the centre of the *second* category as X₂ with value `1`. The tool needs
     a non-degenerate x-axis even when x carries no meaning.
   - **Log axis:** tick the `log` box for that axis *and* set `axes.<n>.scale` to `log` in the
     coding form. Both.

4. **Name the series to match the landmark slots.** The series chips are on the right;
   double-click a chip to rename it, **+ Series** adds one. **The name *is* the slot**,
   spelled exactly:

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
   - `cap` = the **centre of the error-bar cap** on the *same* bar, at the same horizontal
     position. Upper cap only; if the bar has caps both ways, still click the upper one and
     say so in `notes`.
   - The number of clicks in each slot must equal the number of entries in `marks[]`.

6. **Check the points table.** It shows every point's recovered data value live. Sanity-check
   it: a bar you eyeballed at "about 18" should read about 18. If it does not, your
   calibration is wrong -- press **1. Set axes** and redo it. Delete a bad point with the `×`
   in its row.

7. Press **Done**, then ENTER on the timer.

When the sitting is finished: **Export All Articles**, and send the zip back.

### 8.3 Zoom discipline -- the 1:1 rule

Your hand jitter is roughly one **screen** pixel, always. So the only thing that reduces your
error is making the mark **bigger on screen**. This is why the panels are pre-enlarged and why
you must still zoom in.

Every Stage B panel has a **striped patch** burned into a strip along its bottom edge:
alternating 1-pixel black and white vertical lines, next to the label
`1:1 check - must show separate lines`.

> **Before you click any landmark, scroll-zoom (mouse wheel over the image) until that patch
> resolves into visibly separate black and white lines rather than a flat grey smear.
> Shift-drag to pan back to the mark you are picking.**

That is a genuine optical criterion, not a rule of thumb: below 1:1 the grating aliases into
grey; at or above 1:1 it resolves. Passing it guarantees one screen pixel is at most one image
pixel.

**Zoom further than 1:1 whenever the cap is short.** The rule that matters: the vertical
distance from bar top to cap should span **at least ~100 screen pixels** before you click. At
that separation one pixel of jitter is a 1% dispersion error; at 25 pixels it is 4%. Each
wheel click is 1.15x, so ~3 clicks is 1.5x and ~6 is 2.3x.

After your data is ingested, an audit reports the implied 1-pixel jitter per channel and
**names every landmark whose cap-to-top span fell below 100 px**. Those get re-picked at
higher magnification. Do not argue with that list; it is the measurement telling you it is not
good enough yet.

---

## 9. Ambiguity rules

**The general rule: never guess to fill a blank.** Record the ambiguity and abstain. An
abstention is data -- it says the figure is genuinely under-determined, which is a finding
about published figures, not a gap in your work.

Every judgement call below gets an entry in the relevant `ambiguities[]` list:

```json
{"field": "dispersion.type", "why": "caption says 'error bars' with no type; methods silent",
 "resolution": "abstain", "confidence": 0.0}
```

`resolution` is `"abstain"` (you left it `null`/`unknown`) or `"guess"` (you filled something
you are not sure of -- then set `confidence` honestly, 0.0-1.0).

**9.1 Panels sharing an axis.** A row of panels with one y-axis on the left.
> The shared axis belongs to the **leftmost (or bottom-most) panel only.** Every other
> panel's box starts at its own plot area. Add flag `axis-partially-visible` to every panel
> that does not own the axis, and record an ambiguity on `panels`. Do not duplicate the shared
> axis into several boxes and do not stretch one box to swallow its neighbours.
> For the axis-less panels in Stage B, use the **gridlines or the panel frame** as Y
> references if values are printed; if they are not, mark the panel `extractable: false` with
> an ambiguity saying the axis is not inside the panel.

**9.2 A legend serving two or more panels.**
> The legend is **not** part of any panel box -- it goes in the *figure* box only. List
> `legend` in `nonDataElements` for every panel it applies to, and put the legend text into
> each panel's `series[].label`. The label is a property of the series, not of the box.

**9.3 A colourbar.**
> Same as a legend: inside the figure box, outside every panel box, listed as `colorbar` in
> `nonDataElements`. A heatmap whose only quantitative scale is the colourbar is
> `extractable: false` unless you can read values off it directly -- say so in an ambiguity.

**9.4 An inset** -- a small axes drawn inside a larger panel.
> The inset is **not** a separate panel unless the caption gives it its own letter. If the
> caption does not name it: leave it inside the parent panel's box, add `image-inset` to
> `nonDataElements`, and do not digitise it. If the caption *does* name it ("(C) inset"), draw
> it as its own subfigure box with that letter, overlapping the parent. Overlapping boxes are
> fine and are what the caption asserts.

**9.5 A significance asterisk over an error cap.** This is a **known, measured failure mode**:
a naive read confuses the asterisk with the cap and misses by 30-45 px, a 22-36% dispersion
error. You will meet it.
> The cap is the **short horizontal rule that terminates the vertical whisker**. The asterisk
> is a glyph *floating above it*, not touching the whisker, and usually larger. Zoom past 1:1
> until you can see where the whisker ends. Click the whisker's termination, not the glyph.
> If the asterisk genuinely overlaps and hides the cap, **do not guess the cap**: omit that
> mark's cap, add flag `occluded`, record an ambiguity on `marks[i].cap`.
> Add `significance-markers` to `nonDataElements` whenever asterisks are present.

**9.6 A panel with no visible label.**
> If the caption enumerates panels, assign letters by **reading order** -- left-to-right, then
> top-to-bottom -- and record an ambiguity on `panels` with `resolution: "guess"` and a
> confidence. If the caption does not enumerate panels either, label them `A`, `B`, `C` in
> reading order and record the ambiguity. **Never leave a box unnamed.**

**9.7 Drawn letters that disagree with the caption** -- the figure shows A-D, the caption says
(a), (b), (c), (e).
> **The drawn letters win** for naming the boxes: they are what a reader of the figure sees.
> Record an ambiguity on `panels` quoting both. Do not silently reconcile them and do not
> renumber to make them match. **The disagreement is the finding.**

**9.8 Panel count disagrees with the caption.**
> Draw the boxes **you can see**, and record an ambiguity on `panels` stating the count you
> drew and the count the caption implies. Do not add a phantom box to reach the caption's
> number and do not merge two visible panels to reduce to it.

**9.9 A shared x-axis label or a title in the gutter between panels.**
> Shared furniture goes in **neither** panel box. Panels stop at their own plot content. Add
> `title` or `axis-ticks` to `nonDataElements` as appropriate.

**9.10 Which arm is the control?**
> Assign `role` from the **caption, legend and methods** -- never from bar order and never
> from which bar is taller. If the paper genuinely does not identify a control (two active
> treatments), use `comparison` for both, or `unknown` plus an ambiguity. A guessed
> control/intervention assignment is the worst possible error here: it computes the effect
> backwards and produces a perfectly plausible negative result that no downstream check
> catches.

**9.11 Error bars drawn in one direction only.**
> Click the cap that is drawn. Add flag `error-bars-one-sided`. (The integrity check expects
> caps above the bar top; if a bar points *downward*, that flag is what stops the ingest
> treating your click as a slip.)

**9.12 A broken or truncated axis.**
> Add flag `broken-axis`. If both your Y reference ticks lie on the *same* continuous segment,
> the calibration is valid -- proceed. If the marks you need lie across the break, the panel is
> `extractable: false`; record the ambiguity.

**9.13 A bar top hidden behind another bar or a data-point cloud.**
> If you cannot see the top edge, do not infer it. Omit the mark, add flag `occluded`, record
> the ambiguity. A missing mark costs coverage; an invented one corrupts the reference.

**9.14 A micrograph, schematic or flow diagram.**
> `charType` = `micrograph` / `schematic` / `flow-diagram`, `extractable: false`. You still
> draw its box and give it its letter -- panel structure is scored on all panels.

---

## 10. When you are stuck

In order:

1. **Re-read the caption and the relevant methods paragraph.** Most ambiguity here is
   textual, not visual.
2. **Zoom further.** Half of what looks ambiguous at 1:1 is obvious at 4:1.
3. **Still ambiguous? Abstain and record it.** That is the correct answer. Move on -- do not
   spend more than about 3 minutes on any single judgement call.
4. **The tool misbehaves** (a box will not draw, the digitizer will not open): note the item
   id, skip it, keep going. Do not fight it mid-sitting; it will show up as a missing export
   and can be redone.
5. **You realise you made a mistake several items back.** Fix it *within the same sitting* --
   your work is live in the browser until you export. Do **not** fix anything after you have
   exported: the export is sealed with a hash and a later edit breaks the check. Report it
   instead and the item will be re-run.

---

## 11. Worked example

**Everything in this section is ILLUSTRATIVE.** The item, the figure, the caption, every
pixel value, every table entry and every timing below are invented to show the workflow at
full resolution. They are not measured outputs from any session, and no number here may be
quoted as data.

**Item `dn04_9c1a`, Figure 1 of a rodent enrichment study.** Two panels side by side, each a
two-bar chart with error bars. Caption:

> *Figure 1. Effect of environmental enrichment on spatial memory. (A) Time in target zone
> during the 1-day probe. (B) Time in target zone during the 10-day probe. Open bars, standard
> cage (SC); filled bars, enriched environment (EE). Data are mean ± SEM; n = 5 per group.
> \*p < 0.05.*

### Stage A

Draw the figure box around both panels plus the shared y-axis label, excluding the caption
text. The tool auto-fills the caption and caught the whole thing, so leave it. Draw two
subfigure boxes; each includes its own y-axis and x tick labels. Rename them `A` and `B`.
There is no legend graphic -- the arms are described in prose -- so nothing to exclude.
About 90 seconds. Export, send back.

You get `dn04_9c1a_pA` and `dn04_9c1a_pB` in return, each ~2200 px on the long edge, plus two
blank forms.

### Stage B, form for panel A

```json
{
  "panel_item": "dn04_9c1a_pA",
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

`direction: 1` because more time in the target zone is better memory.
`labelSource: "caption"` rather than `"legend"` because there is no legend box.
`significance-markers` because an asterisk sits over panel A.

### Stage B, picks for panel A

Open the digitizer. Wheel-zoom until the striped patch at the bottom shows separate lines --
roughly six clicks from the default fit -- then shift-drag back to the y-axis.

**Axes.** `1. Set axes`, then click: the SC bar's centre on the x baseline (X₁, value `0`),
the EE bar's centre (X₂, value `1`), the `0` tick on the y-axis (Y₁, value `0`), and the `25`
tick (Y₂, value `25`) -- the furthest-apart pair that is unambiguously labelled.

**Series.** Rename the default chip to `top`. Press **+ Series**, rename it to `cap`.

**Picks.** Click the `top` chip; click the SC bar top, then the EE bar top -- left to right,
matching `marks[]`. Click the `cap` chip. The SC cap sits only ~70 screen px above its bar top
at 1:1, below the 100 px floor, so zoom three more clicks (1.15³ ≈ 1.5x) to take it past 105.
Now click the SC cap centre, then the EE cap centre.

The asterisk sits about 40 px above the SC cap. Zoomed in it is obviously a glyph floating
free of the whisker -- click the short horizontal rule where the **whisker ends**, not the
asterisk (§9.5).

**Check the table:**

| # | series | x | y |
|---|---|---|---|
| 1 | top | 0.00 | 18.58 |
| 2 | top | 1.00 | 18.36 |
| 3 | cap | 0.00 | 21.03 |
| 4 | cap | 1.00 | 20.61 |

Bars around 18-19 s on a 0-25 axis: consistent with what you can see. Caps ~2.3 s above the
tops, so SEM ≈ 2.3 and SD ≈ 2.3 × √5 ≈ 5.1. Plausible. Press **Done**. Panel A took 4 min 10 s.

---

## 12. Command card

Everything on your side is: unzip, annotate, export, send back. The commands below are only
the timer and are optional-but-wanted. Everything lives in your work folder; nothing here
refers to anyone else's machine.

```
Tool:      figure-extractor.html   in your work folder (open it as a file:// page)
Settings:  Annotation mode ON. Auto-detect caption ON.
```

```bash
cd <your work folder>
python3 dan_timer.py A     # stopwatch, Stage A
python3 dan_timer.py B     # stopwatch, Stage B
```

**Send back** -- `HANDOFF.txt` in the zip says the same thing for the stage you are on:

| stage | what goes back |
|---|---|
| A | `projectA_all_figures.zip`, `timing.jsonl` |
| B | `projectB_all_figures.zip`, the whole `coding\` folder, `timing.jsonl` |

**If you only remember six things:**

1. **Annotation mode ON**, always. An export without it is unusable.
2. Do the **calibration round first**, and reconcile *definitions*, never *values*.
3. Fill the coding form **before** you pick landmarks.
4. Zoom until the striped patch shows **separate lines**, and further still for short caps.
5. Click each landmark slot **left to right**, matching the `marks[]` roster exactly.
6. **Abstain and say why** rather than guess -- especially for dispersion type and arm role.

---

## 13. Calibration amendments

*Conventions agreed in the §4 round go here, dated and initialled by both raters. Anything
written here overrides the corresponding rule above for both of you.*

| date | field | agreed convention | initials |
|---|---|---|---|
| | | | |
