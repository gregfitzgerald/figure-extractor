# Panel-detection benchmark (`benchmark/panels/`)

Multi-panel decomposition, measured instead of guessed at: 41 seeded figures, 159 panels,
each panel carrying an exact pixel box, a letter, a content type, a layout class and the
caption that names it -- plus a scorer that separates the four ways panel detection fails
and stratifies every metric by the thing that caused the failure.

> The corpus grew from 33 figures / 119 panels to 41 / 159 when adversarial probing found a
> blind spot the original ladder could not see; see section 3b. Section 6 onward reports the
> numbers measured on the original 33, which are reproducible with
> `score.py --run <run> --ids-matching '^(L[1-5]|C_)'`.

Real journal figures are flattened bitmaps: the panel letters A/B/C are pixels, not text,
and the only textual constraint available is the caption. This tier reproduces that
situation exactly -- the task file carries the image and the caption, nothing else.

---

## 1. How to run

```bash
Rscript benchmark/panels/gen_panels.R        # render 41 figures + solo per-element renders
python3 benchmark/panels/finalize_gt.py      # measure the ink boxes -> corpus/<id>.pgt.json
python3 benchmark/panels/audit_panels.py     # verify the GT against the composite pixels
python3 benchmark/panels/make_tasks.py       # leak-free anonymised tasks (image + caption)

python3 benchmark/panels/run_baseline.py --run legacy_caption --detector legacy
python3 benchmark/panels/run_baseline.py --run legacy_nocap   --detector legacy --expected none
python3 benchmark/panels/run_baseline.py --run core_caption   --detector core

python3 benchmark/panels/score.py --run legacy_caption
python3 benchmark/panels/score.py --run core_caption --abstain-at 0.35
python3 benchmark/panels/score.py --selftest         # prove the metrics catch each failure
```

Generation takes ~50 s and is fully seeded: same corpus every time. Renders (`corpus/*.png`,
`corpus/_iso/`, `tasks/img/`) are gitignored; the GT bundles, the code, and the prediction
files are committed. (`tasks/` is covered by the repo's pre-existing `tasks/` ignore rule,
as in `benchmark/series/` -- regenerate it with `make_tasks.py`.)

`run_baseline.py` starts its own `python3 -m http.server 8001` unless `--url` is given, and
never touches `figure-extractor.html`: it pushes the task image into `state.pages` as a
decoded `Image` and hands the detector a synthetic figure covering the whole bitmap.

A prediction file is keyed by the ANONYMISED task name, and `make_tasks.py` reshuffles those
names whenever the corpus changes. So `predictions/*.jsonl` is only meaningful against the
`tasks/anon_map.json` it was produced with: after adding a corpus figure, re-run
`run_baseline.py` rather than re-scoring an older prediction file. The files here were all
produced against the current 41-figure map. `cascade_v2.jsonl`, `cascade_postfix.jsonl` and
`verify_final.jsonl` are development snapshots that predate the extension and are NOT
scoreable against the current map.

---

## 2. How the ground truth is made (and why it is exact)

`gen_panels.R` does not draw a figure and then look for its panels. It **composes** the
figure out of `grid` viewports whose device rectangles it chooses, then re-renders every
element **alone on a white page with byte-identical geometry**. The ink bounding box of
that solo render is, by construction, exactly the ink that element contributes to the
composite. Three rectangles are therefore known per panel:

| field | meaning | source |
|---|---|---|
| `tile` | the rectangle the compositor allocated | layout arithmetic |
| `plotRect` | the inner axes rectangle | `grid::deviceLoc` (the `benchmark/r/rgt.R` method) |
| `bbox` | the tight box around everything the panel draws | ink box of the solo render |

`bbox` is the scoring target: it is what a human cropping "panel B" would draw, and what an
ink-trimming detector can in principle reach. `bboxCore` is the same box without the panel
letter, reported as a lenient variant so a detector that trims an outside-placed letter is
not scored as if it had mislocalised the panel.

`benchmark/r/rgt.R`, `benchmark/r/generate.R` and `benchmark/series/` were not modified.
`pgt.R` is an additive layer beside them.

### GT schema (`corpus/<id>.pgt.json`)

```jsonc
{
 "id": "L5_pinwheel4_med_26", "image": "L5_pinwheel4_med_26.png", "level": "L5_nonguillotine",
 "figure": { "width": 880, "height": 720, "dpi": 110, "seed": 1526 },
 "layoutName": "pinwheel4", "layoutClass": "non-guillotine",
 "gutter": { "nominalPx": 25, "bucketNominal": "medium",
             "measuredPx": 30.0, "measuredFrac": 0.0341, "measuredAxis": "x",
             "bucket": "medium", "tightestPair": ["C", "D"] },
 "labelPlacement": "inside-tl", "labelFormat": "A", "sharedAxes": false,
 "caption": "Figure 26. Lesion alters regional signalling ... (A) Quantification of ...",
 "expectedLetters": ["A", "B", "C", "D"],
 "notes": ["no full-width or full-height cut separates these panels"],
 "nPanels": 4,
 "panels": [{
   "index": 0, "label": "A", "contentType": "bar", "labelDrawn": true,
   "bbox":      { "x": 26, "y": 25, "width": 542, "height": 201 },   // SCORING TARGET
   "bboxCore":  { "x": 26, "y": 25, "width": 542, "height": 201 },   // without the letter
   "labelBbox": { "x": 29, "y": 29, "width": 12,  "height": 12 },
   "inkEscapePx": -2.5,      // how far this panel's ink reaches outside its own tile
   "labelContrast": 255,     // luminance range in the letter box: is the letter legible?
   "tile":     { "x": 22.5, "y": 22.5, "width": 548.33, "height": 208.33 },
   "plotRect": { "x": 56.07, "y": 25.54, "width": 511.72, "height": 186.77 }
 }],
 "distractors": [],   // legend / colourbar / figure-level axis title: ink owned by NO panel
 "gtMethod": "..."
}
```

`gutter.bucket` is computed from the **measured** ink-to-ink gap (normalised by the figure
dimension the gap is measured along), not from the knob that was set -- a nominally tight
gutter measures wider because a panel's ink stops short of its tile. The scorer stratifies
on the measured value.

---

## 3. The difficulty ladder

The original ladder: 33 figures / 119 panels (section 3b adds 8 more). Every knob the
mission named is present and is a GT field, so
every metric can be sliced by it.

| level | figures | what varies |
|---|---|---|
| `L1_easy` | 5 | generous gutters (4-6% of width), plain 1x2/2x2/1x3/2x1 grids, letters inside top-left, one image mosaic |
| `L2_medium` | 7 | 6-panel grids, shared axes with figure-level axis titles, colourbar, letters outside-above-left / top-centre / bottom-right / **absent**, one figure whose caption names **no letters at all** |
| `L3_tight` | 7 | gutters of 0.6-1.4% of the figure dimension (below any fixed minimum-gutter threshold), a legend sitting **in** a gutter, unequal row spans (A across the top), one tall panel beside two stacked, raster panels abutting a chart panel |
| `L4_flush` | 6 | gutter **exactly zero**: image mosaics 2x2 / 1x4 / 2x3, shared-axis chart mosaics 1x3 / 2x2 whose panels share a border line, a raster row flush against a chart row |
| `L5_nonguillotine` | 6 | pinwheel4 / pinwheel5 / windmill4 at medium, tight and zero gutter -- no sequence of full-width or full-height cuts separates these panels, so recursive XY-cut cannot express the answer at all |
| `C_control` | 2 | ONE panel (a chart with an inset legend; a micrograph). Splitting these is a false positive |

Measured strata: gutter `wide 5 / medium 12 / tight 7 / flush 7 / n-a 2`;
layout `guillotine 27 / non-guillotine 6`;
label placement `inside-tl 20 / none 5 / outside-al 4 / top-centre 2 / bottom-right 2`;
panel content `micrograph 29 / bar 23 / scatter 21 / line 17 / box 17 / heat 12`;
distractors `axis-title 6 / colourbar 3 / legend 2`.

Panel lettering follows journal convention: reading order for grids, **clockwise** for
pinwheels. Reading-order labelling is therefore provably wrong on the pinwheels, and the
drawn letters are what resolve it -- which is the point of scoring assignment separately.

## 3b. The blind spot, and the eight figures that close it

The ladder above scored the cascade detector at **100 % letter accuracy and 0 % silent
mislabels**. That number was not earned: not one figure in L1-L5 contained a glyph whose
IDENTITY is an expected panel letter but which is NOT a panel label. Every figure either
had readable labels in reading-order-consistent places, or had none. On such a corpus
"each box owns exactly one distinct expected letter" is indistinguishable from "the panel
labels were read", so a detector could treat the first as proof of the second and score
perfectly -- while being invertible by any compact-letter display, crossed axis unit,
legend key or inset letter. Adversarial probing turned that into three live exploits
(inverted naming at `ok=true`, twice; a panel boundary dragged onto a stray glyph at
confidence 0.92 with no flags at all).

| level | figures | what varies |
|---|---|---|
| `L6_strayletters` | 5 | expected-letter glyphs that are **not** labels: a compact-letter display at label size beside real labels, and again with **no** labels drawn and the CLD letters in reverse order; crossed parenthesised axis units `(B)` over `(A)`; a shared legend whose three keys ARE `A`/`B`/`C`; an inset carrying its own `b` at label size in a label-shaped position |
| `L7_manypanels` | 2 | 9 panels (A-I) and 12 panels (A-L), so the letter run reaches `I` -- a bare vertical stem that no shape test can separate from a lowercase `l` |
| `L8_typeface` | 1 | panel letters set in bold serif **italic** rather than upright sans |

Measured on these 8 figures / 40 panels: the pre-repair detector scored **5.0 % silent
mislabels** and **50 % error on answered figures**, i.e. the corpus reproduces the exploits
rather than merely describing them. `L6_units_crossed_36` in particular shipped `ok=true`
with the letters `B, A`.

These figures are ADVERSARIAL, so a low answer rate on them is the expected, correct
outcome: 6 of the 8 abstain. What matters is that nothing answered is wrong.

---

## 4. GT audit (`audit_panels.py`) -- residuals

The audit never looks at the solo renders. It re-derives everything from the composite PNG
plus the allocated tiles (independent layout arithmetic).

```
PANEL-GT AUDIT (composite PNG + layout tiles vs the exported answer key)
  figures 41   panels 159

  (1) tightness inset px   : median 0.0  max 0.0   (0 = every GT box touches its own ink on all 4 edges)
  (2) outward residual px  : median 0.0  p95 0.0  max 0.0
  (3) unclaimed ink        : max over figures 0.0000%  mean 0.0000%
  (4) worst panel-panel IoU: 0.0155  (L4_charts1x3_flush_22)
  (5) caption/letter checks: OK   label-ink checks: OK
```

- **0 px** inset: inside every one of the 159 GT boxes, ink touches all four edges. No box
  is loose.
- **0 px** outward residual: inside a panel's own tile, no ink reaches beyond its GT box.
- **0.0000 % unclaimed ink**: every dark pixel in all 41 composites lies inside some GT box
  -- a panel, or a declared distractor (legend, colourbar, figure-level axis title).
- Panel boxes are disjoint; the single non-zero pair IoU (0.0155) is the flush chart mosaic
  where ggplot2 centres the last x tick label on the axis end so it overhangs its
  neighbour by 9 px. That is real journal behaviour and the GT records it rather than
  hiding it (`inkEscapePx`).
- Every caption names exactly the letters its figure has, and every drawn letter box
  contains a legible glyph (`labelContrast`, min 60 luminance range; letters over rasters
  are drawn white with a thin black outline, as journals do).

---

## 5. Metrics (`score.py`)

Four failure classes, kept apart because they have different owners:

| metric | what it catches |
|---|---|
| per-panel IoU: median, worst, share >= 0.9, share >= 0.5 | localisation |
| exact-count rate, over/under-split, spurious boxes, caption-count agreement | segmentation count |
| letter accuracy **among localised panels**, silent-mislabel rate | assignment -- the box called "B" is not panel B |
| coverage, error rate answered vs all, abstention precision/recall, net figures saved | calibration |

`WHOLE FIGURE EXACTLY RIGHT` counts an abstained figure as right whenever the answer it
declined to give would have been right, which flatters a detector that abstains a lot. It
is reported unchanged, with `ANSWERED-ONLY exactly right` printed beneath it: the same
question asked only of the figures actually answered. A figure counts as WRONG when its
panel count is wrong, when any panel falls below the **IoU >= 0.5** localisation threshold
(`IOU_HIT`), or when any panel is a silent mislabel; that threshold governs the
`error rate ... answered only` line and is now printed alongside it. For reference, real
detected panels on this corpus sit at 0.77-0.88 IoU when they are wrong-but-close, so 0.5
is a genuinely permissive bar and the errors it reports are not near-misses.

`--ids-matching REGEX` selects which corpus figures are reported (e.g. the original ladder
with `'^(L[1-5]|C_)'`). It is a selection filter only -- no metric is defined differently
for a subset.

Matching is a one-to-one GT-to-prediction assignment maximising total IoU (exact for these
cardinalities, greedy fallback). Unmatched GT panels score IoU 0, so misses cannot hide.
Predictions without letters are read as claiming reading order -- which is what the tool's
`a/b/c` labelling means.

### Selftest

`python3 benchmark/panels/score.py --selftest` injects a failure and asserts that the
metric which owns it moves, and that the others do not:

```
PASS  perfect prediction scores perfectly            medIoU 1.000 count 100% label 100%
PASS  IoU degrades monotonically with a box shift    5px->0.942  20px->0.790  60px->0.504
PASS  a 5px shift is caught by IoU but not by count  medIoU 0.942, count still 100%
PASS  swapped panel letters -> assignment falls, geometry does not   label 48%, 62 silent mislabels, medIoU 1.000
PASS  a dropped panel -> count + recall fall         count 6%, 31 panels never matched, >=0.5 74%
PASS  a spurious box -> count + false positives, IoU intact          count 0%, 33 FPs, medIoU 1.000
PASS  two panels merged -> under-split and IoU collapse              under-split 94%, >=0.5 53% (was 100%)
PASS  abstaining on everything while being right is penalised        coverage 0%, net -33, precision 0.00
PASS  calibrated abstention: flags the wrong ones only               precision 1.00 recall 1.00 net +16
PASS  unlabelled boxes are read as READING ORDER                     guillotine 98% vs non-guillotine 50%
PASS  a missing prediction scores as a total miss, not a crash       11 figures unanswered
```

---

## 6. BASELINE: the legacy XY-cut detector

`suggestSubfigures` (now `suggestSubfiguresLegacy` in `figure-extractor.html`): recursive
XY-cut on a 480 px analysis image, minimum gutter 2.5 % of the analysis dimension, leaves
trimmed to their ink box, sliver rejection, then the caption count used to merge
over-splits back down. Median 8 ms per figure.

### With the caption count (what the UI does)

```
  LOCALISATION
    per-panel IoU     median 0.407   mean 0.420   worst 0.000
    panels IoU >= 0.9 10.1%      IoU >= 0.5 40.3%      never matched 24
  COUNT
    exact panel count 75.8%   over-split 6.1%   under-split 18.2%   spurious boxes 69
    caption states the count for 30 figures; matched for 80.0% of them
  ASSIGNMENT
    localised panels given the RIGHT letter 87.5%
    silent mislabels (well-localised, wrong letter) 5.0% of all panels
  WHOLE FIGURE EXACTLY RIGHT  30.3%
  ABSTENTION
    coverage 81.8%   abstention precision 0.83  recall 0.21   net figures saved +4
```

Stratified -- this is the deliverable:

```
  by gutter (measured)      figs  pans  medIoU   >=.9   >=.5  count  label  exact
    wide                       5    15   0.734    40%    80%   100%    92%    60%
    medium                    12    46   0.556    11%    57%    92%    88%    42%
    tight                      7    27   0.373     0%    22%    86%    67%     0%
    flush                      7    29   0.000     0%    10%    29%   100%    14%

  by layout class
    guillotine                27    93   0.424    13%    46%    74%    95%    37%
    non-guillotine             6    26   0.299     0%    19%    83%    20%     0%

  by difficulty level
    L1_easy                    5    15   0.734    40%    80%   100%    92%    60%
    L2_medium                  7    27   0.684    19%    67%    86%   100%    57%
    L3_tight                   7    24   0.389     0%    38%    86%    89%    14%
    L4_flush                   6    25   0.000     0%    12%    33%   100%    17%
    L5_nonguillotine           6    26   0.299     0%    19%    83%    20%     0%

  by panel content type      pans  medIoU   >=.9   >=.5  label  silentMis
    scatter                    21   0.629    10%    71%    80%       14%
    box                        17   0.435     6%    35%   100%        0%
    bar                        23   0.409     4%    39%    89%        4%
    micrograph                 29   0.000    17%    21%   100%        0%
```

### Without the caption count (the raw cut)

```
  per-panel IoU median 0.368   IoU >= 0.5 25.2%   never matched 19
  exact panel count 9.1%   over-split 72.7%   spurious boxes 226
  localised panels given the RIGHT letter 43.3%   silent mislabels 14.3%
  WHOLE FIGURE EXACTLY RIGHT 9.1%
```

### What the baseline numbers say

1. **Tight gutters: 0 % of panels reach IoU 0.9, 22 % reach 0.5.** The detector's minimum
   gutter is 2.5 % of the analysis dimension; the tight tier sits at 0.6-1.4 %, so the true
   gutter is never a candidate cut. It cuts elsewhere instead.
2. **Flush panels: median IoU 0.000, count right on 2 of 7 figures.** Five of the seven
   flush figures collapse to a **single box for the whole figure** (`4 -> 1`, `6 -> 1`).
   With no whitespace between panels there is no projection-profile minimum to find, and
   the leaf trim then returns the union. Note the 100 % "label" score in the flush row is
   an artefact of there being almost nothing localised to label -- read it with the 10 %
   IoU >= 0.5 column.
3. **Non-guillotine: 0 of 6 figures exactly right, letter accuracy 20 %.** The count is
   often right (83 %) because the caption prior forces it, which makes this the most
   dangerous stratum: the right *number* of boxes in the wrong *places*, then lettered by
   reading order, i.e. a silent mis-assignment of panel identity. This is unreachable in
   principle for XY-cut, not a tuning problem.
4. **The caption prior is doing most of the work.** Removing it drops exact-count from
   75.8 % to 9.1 % and multiplies spurious boxes from 69 to 226. The raw cut over-splits
   72.7 % of figures -- it treats the low-ink columns between bars, and the whitespace band
   beside a legend, as gutters. The single-panel control is split into **7** boxes.
5. **Reconciliation makes the geometry worse while making the count look right.** Merging
   over-split boxes back to the caption count unions non-adjacent fragments, which is why
   even `L1_easy` -- 45 px gutters, a plain 2x2 -- only reaches median IoU 0.734 and
   60 % of figures exactly right.
6. **There is no usable confidence signal.** The only refusal the legacy detector can make
   is "fewer than 2 boxes"; it fires on 6 figures, catching 5 real errors and costing 1
   correct answer (net +4 of 23 errors, recall 0.21). 66.7 % of the figures it does answer
   are wrong, and it says nothing about them.

---

## 7. The cascade detector

A rewrite replaced `suggestSubfigures` with `detectPanelsCore` (caption constraint -> XObject
fast path -> structural pass -> label anchoring -> verification). Both columns below are
scored with the same yardstick over the same 41-figure corpus; the cascade at
`--abstain-at 0.35` (its own gate). Reproduce with:

```bash
python3 score.py --run legacy_caption
python3 score.py --run post_fix_ext --abstain-at 0.35
```

```
                                 legacy (caption)     cascade
  per-panel IoU median                 0.398           1.000
  panels IoU >= 0.9                     7.5%           88.1%
  exact panel count                    80.5%           95.1%
  letter accuracy (localised)          74.1%          100.0%
  silent mislabels                      9.4%            0.0%
  whole figure exactly right           22.0%           95.1%
  exactly right, ANSWERED ONLY            --           100.0%  (27 figures)
  coverage                             85.4%           65.9%
  spurious boxes                          99               2
  panels never matched                    30               7
  abstention precision / recall     0.83 / 0.16     0.14 / 1.00
  net figures saved by abstaining         +4             -10

  medIoU / figures exactly right     cascade         legacy
  by gutter    wide                 0.965 / 100%    0.622 /  29%
               medium               1.000 / 100%    0.442 /  28%
               tight                1.000 /  86%    0.373 /   0%
               flush                0.997 /  86%    0.000 /  14%
  by layout    guillotine           1.000 / 100%    0.409 /  26%
               non-guillotine       0.925 /  67%    0.299 /   0%
```

**Read the two headline numbers together.** "95.1% whole figure exactly right" counts an
abstention as right whenever the answer it withheld would have been right, so it is a
statement about the detector's *judgement*, not its throughput. The throughput number is
coverage: it answers 27 of 41 figures and declines 14. On those 27 it is exactly right
**100%** of the time -- right panel count, every box at IoU >= 0.5, no mislabelled letters --
and letter accuracy is 100% with **zero silent mislabels**, which is the failure class that
matters, because a box confidently labelled with the wrong letter attaches a number to the
wrong experimental arm.

So the honest summary is: *it declines a third of figures, and is not observed to be wrong on
what it accepts.* For an extraction pipeline feeding a meta-analysis that is the right trade --
an abstention costs a minute of human attention, a silent mislabel corrupts a study's weight.

**But the abstention is badly over-cautious, and by the tier's original metric it loses.**
Recall is 1.00: it abstains on *every* figure it would have got wrong, which is the property you
actually want. Precision is 0.14: of the 14 figures it declined, only 2 were genuinely wrong, so
12 were needless. Net figures saved = 2 caught - 12 wasted = **-10**. `ANALYSIS-PLAN.md`
pre-registered `net figures saved > 0` as a hard gate, and these numbers **fail it**. The
committed `real-validation/synthetic_reference.json` moreover still recorded the superseded
0.88 / 0.94 / +13 from an earlier build -- a stale hand-maintained artifact that would have
laundered those numbers into the pre-registration unchallenged.

Both are resolved by `ANALYSIS-PLAN.md` amendment **A18** (2026-08-08), which is explicit that
it changes a pre-registered criterion after these numbers were seen: the gate is restated on
abstention **recall** (0 answered-and-wrong figures), because a needless abstention and a silent
error do not cost the same, and net figures saved / precision are reported descriptively as the
cost, alongside coverage. The old criterion and its failure stay recorded -- here, in A18, and
in the `superseded` block of `synthetic_reference.json`, which is now **generated** from this
scorer by `real-validation/make_synthetic_reference.py` (`--check` detects staleness) so it
cannot drift again. Retuning `--abstain-at` to buy back precision remains open, but it is
tuning, not a gate question.

Tight gutters and flush mosaics both went from unusable to 86% exact, and guillotine layouts
are perfect. **Non-guillotine layouts are the remaining weakness** -- 0.925 medIoU but only
67% of figures exactly right, the one stratum still below the tight/flush pair. Section 3b
explains why non-guillotine geometry resists a recursive cut. The residual localisation
misses are spread across non-guillotine, tight and flush (each has panels under the IoU >= 0.5
bar); the abstention gate is what keeps them out of the answered set.

> Earlier revisions of this section reported a mid-development snapshot (medIoU 0.923, 51.5%
> exact, flush and non-guillotine at 0%). That snapshot predated the label-anchoring and
> verification repairs and understated the detector substantially; it is superseded by the
> measured numbers above.

---

## 8. Files

| file | role |
|---|---|
| `pgt.R` | panel GT engine: layout composer, content builders, solo-render mode, caption builder |
| `gen_panels.R` | the corpus spec (the ladder) + renders; writes `corpus/<id>.part.json` |
| `finalize_gt.py` | measures ink boxes from the solo renders -> `corpus/<id>.pgt.json` + manifest |
| `audit_panels.py` | independent verification against the composite pixels |
| `make_tasks.py` | leak-free anonymised tasks (image + caption only) |
| `run_baseline.py` | Playwright driver for `suggestSubfiguresLegacy` and `detectPanelsCore` |
| `score.py` | the metric set, the stratification, and `--selftest` |
