# Real-figure ground truth: sampling frame and annotation worklist

What to annotate, in what order, why that order, and what it costs in hours. Everything here was
measured from the PDFs and the extraction workbooks, not assumed. The machine-readable twin is
`worklist.json` (schemaVersion 1, consumed by `prepare_session.py`).

Companion documents in this directory: `PROTOCOL.md` (how to annotate), `ANALYSIS-PLAN.md` (what to
compute from the result). This file owns only the frame and the worklist.

---

## 0. What changed when I looked

Three premises the project was operating on turned out to be wrong or incomplete. Each was checked
mechanically, and each changes the worklist.

**(a) The universe is 373 panels across 172 articles, not 98 across 43.**
`benchmark/real/population.json` covers only the 43 articles that survived into the final
meta-analysis. The extraction workbooks at
`/mnt/c/Users/gregs/My Drive/thesis/meta-analysis/DISSERTATION/rodent/RODENT_Processed_Extractions`
(200 `.xlsm` files) hold **528 comparisons across 198 articles**, of which **464 comparisons /
373 distinct (article, panel) pairs / 172 articles** are figure-derived. Articles excluded from the
MA for *content* reasons still have perfectly good figures. **165 of the 172 (96%) resolve to a local
Zotero PDF**; the seven that do not are `Acklin2015, Alaei2007, Falkenberg1992, Huber1997,
Kikuchi2022, More2023, Van-Gool1985`.

**(b) "The value is printed in the text" is real but ~5x rarer than the field labels suggest.**
The instruction was to prioritise the ~127 comparisons whose `Data_Extraction_Method` is "Reported in
text/figure" or "Reported in text and figure", on the theory that a text-printed value is a *true*
ground truth for the figure read. I tested that mechanically instead of trusting the field: for all
448 figure-derived comparisons with a resolvable PDF, search the whole PDF text for the coded mean
and variance as an adjacent `mean ± variance` pair.

| filter | comparisons | panels | articles |
|---|---|---|---|
| both arms found as a `mean ± var` pair | 41 | 34 | 18 |
| ... and both tokens reproduce the coded value to within 6% (1-dp rounding) | 21 | **17** | **15** |
| ... to within 0.5% (verbatim) | 10 | **8** | 7 |

And the field does **not** predict it. Of the 92 `Reported in text/figure` comparisons, **3** carry a
text-printed pair. Of the 45 `Reported in text`, **18** do. So "text/figure" most likely means "read
from the figure, located via the text", not "the number is printed". **The mechanical check is the
selector; the field is not.** Greg should still confirm the field's intended semantics, but the
worklist does not depend on that answer.

This is still the single most valuable thing in the corpus. `benchmark/real/RESULTS.md` limitation #1
is *"Reference = human coding, not ground truth ... this experiment measures agreement, not
accuracy."* Those 17 panels dissolve that limitation for 17 panels. They lead Tier 1.

**(c) 20% of the figures are vector, and their panel labels are extractable text.**
Commit `b50fb05` concluded from Chandler Fig 2 that "the figures are flattened bitmaps; panel
localization is genuinely a CV problem". True for **178 of 222** surveyed figures. **44 figures in 13
articles are vector-drawn**, and in those the panel labels are PDF text spans with font and size:

- `Lee2024` Fig 2: `A`,`B`,`C` at Roboto-Bold 9.2pt plus `(a)`,`(b)` at RotisSansSerif 9.0pt.
- `Baraldi2013` Fig 1: the panel letter `D` at Helvetica-**Bold** 12.0pt versus the compact-letter
  significance markers `a`,`c` at Helvetica-**BoldOblique** 7.7pt. Font and size separate the label
  from the exploit **for free** -- the exact discrimination the pixel-level detector was documented as
  unable to make.
- `SampedroPiquero2018` `(b)` Arial-Bold 11pt; `Jaimes2020` `(D)` Helvetica-Bold 12pt;
  `Bonaccorsi2013` `(a)` MinionPro 8pt.

So there is a **third fast path** beside the XObject path, it is worth about a fifth of the corpus,
and it has never been scored. Stratum `S11_vector_text` exists to score it, and the protocol should
record the PDF span alongside the pixel box for those items.

---

## 1. The three annotation units

The worklist samples **figures**, because the three validation targets nest in labour terms.

| unit | what is produced | serves | cost |
|---|---|---|---|
| **U1 page** | figure-region bbox + caption span + association | Target 1 (detection) | 1.5 min, verifying a Docling pre-fill |
| **U2 figure** | per-panel bbox + letter + content type + difficulty tags | Target 2 (panel decomposition) | 5-18 min |
| **U3 panel** | 4 axis-reference pixels + per-series `{top, cap}` pixels | Target 3 (dispersion) **and** training data for the sub-pixel landmark detector | 6 min, 9 min when a significance marker sits over the cap |

U3 requires the U2 crop anyway, and U2 costs a page open that U1 needs. Annotating a figure once and
harvesting all three is roughly half the cost of three separate passes.

**Time model** (`worklist.json:time_model_minutes`):
`U2 minutes = 4.5 + 0.7 x chart panels + 1.0 x raster tiles + 0.8 x schematics`.
The fixed 4.5 covers opening the page, cropping at 300-600 dpi, transcribing the caption's expected
letters, and tagging the difficulty axes. The per-tile costs are higher for rasters because a flush
mosaic's tile edges have to be judged rather than read off whitespace.

---

## 2. Sampling frame

### 2.1 The principle

Not "the first N", and not "proportional to the corpus". The sample is stratified on **the axes the
synthetic benchmark taught us matter**, and deliberately **oversampled where the detector is measured
weakest or where synthetic-to-real transfer is most doubtful**. The oversampling weights were set
when the mid-development cascade scored 0.107 median IoU / 0 of 6 figures exact on non-guillotine
layouts and 0.000 median IoU on flush mosaics; the finished cascade (`benchmark/panels/RESULTS.md`
section 7) measures 0.925 medIoU / 67% exact on non-guillotine -- still its weakest stratum -- and
86% exact on flush and on tight, so the weights keep pointing at the right strata and the draw
stands. Tight and flush are *reported* solved only on clean synthetic renders -- which is precisely
a claim that only real anti-aliased, JPEG-blocked scans can test.

Strata are **non-exclusive tags**. A single figure can discharge four of them, which is why 14
figures cover 19 strata in Tier 1+. The target n is the minimum number of *distinct figures* carrying
the tag.

### 2.2 The strata

| id | definition | target n | oversampled | synthetic analogue |
|---|---|---|---|---|
| `S0_textGT` | the paper prints the plotted `mean ± variance` in its text | 5 | yes | none needed -- the real corpus's unique asset |
| `S1_anchor` | easy/medium guillotine chart grid, labels drawn | 6 | no | L1_easy / L2_medium |
| `S2_tight` | measured inter-panel gutter < ~1.5% of the figure dimension | 4 | no | L3_tight |
| `S3_flush` | panels abutting at 0-0.5% gutter | 6 | **yes** | L4_flush -- cascade 0.997 medIoU / 86% exact |
| `S4_nonguillotine` | no full-width/full-height cut sequence separates the panels | 2 | **yes** | L5 -- the cascade's weakest stratum: 0.925 medIoU, 4/6 exact (0.107, 0/6 at sample draw) |
| `S5_labels_absent` | caption names letters (or none); the figure draws none | 4 | **yes** | L2_grid2x2_nolabel / L2_grid1x3_nocap |
| `S6_stray_letters` | expected-letter glyphs inside panels that are not labels | 1 | **yes** | L6 -- the conf 0.8-0.92 exploit |
| `S7_manypanels` | >= 8 panels; letter run reaches I or beyond | 5 | **yes** | L7 |
| `S8_label_system` | label alphabet is not `[A-Z]`: primes, `A-(a)`, `a.i`, case mixing, `Panel A`, `A)`, `A,` | 6 | **yes** | **none** |
| `S9_letter_tile_mismatch` | one caption letter covers several visual tiles | 8 | **yes** | **none** |
| `S10_single_panel_control` | one panel; any split is a false positive | 2 | no | C_control |
| `S11_vector_text` | vector figure whose labels are PDF text spans | 4 | **yes** | **none** |
| `S12_xobject` | multi-XObject figure; do XObject boxes coincide with panels? | 4 | **yes** | **none** |
| `S13_label_bottom_left` | labels outside bottom-left | 3 | no | partial (synthetic has bottom-*right*) |
| `S14_serif_italic` | panel letters in serif italic | 1 | no | L8 |
| `S15_figure_detection` | two figures on one page; body text abutting; legends on a separate page | 5 | **yes** | **none** -- Target 1 |
| `S16_nonbar_channel` | central tendency is not a bar top (point cloud + mean line, stacked-bar segment, median+IQR) | 6 | **yes** | partial |
| `S17_table_panel` | a rendered table is one of the panels | 2 | no | **none** |
| `S18_SD_rare` | dispersion is SD, not SEM | 5 | **yes** | none (synthetic varies cap length, not declared type) |

All 19 targets are met by the worklist; `worklist.json:strata` reports the per-stratum counts and the
Tier-1 subset.

### 2.3 Two deliberate anti-biases

**Include easy cases on purpose.** `S1_anchor` has a target of 6 and `Hullinger2015` Fig 2 is in the
list explicitly as the easiest figure in the corpus. A sample made only of hard cases produces a
transfer number that is pessimistic and *not comparable* to the synthetic headline, which was
computed over a ladder with 5 easy figures in it. The anchor cell is what makes the delta mean
something.

**Do not balance SD against SEM.** Arm-level variance types in the frame are **SEM 826 / SD 70 /
other 20** -- 91% SEM. That is a property of the field, not a sampling defect, and the whole
short-cap dispersion argument depends on it. Report it as the skew it is. But SD panels are rare
enough to be *lost* by proportional sampling, so `S18_SD_rare` deliberately pulls in the five that
exist (`Zhang2017`, `Nawaz2018` x2, `Bouet2011`, `Mansk2023`).

### 2.4 High-yield articles versus stratification -- where they conflict

Five articles carry 32 of the 98 panels in the old frame (`Miu2006` 8, `Clemenson2015` 7,
`Morgan2018` 6, `Zhang2017` 6, `Hullinger2015` 5), and opening one PDF for six panels is much cheaper
in human attention than opening six PDFs for one each.

**Where they agree, take the convenience.** `Zhang2017` Fig 3 is both the highest-yield single figure
(6 coded panels, 2 text-verified) and a distinct stratum (`S18_SD_rare`). It is item #1.
`Morgan2018` gives `S5_labels_absent` *and* a same-paper labelled twin *and* 6 coded panels.
`Clemenson2015` gives the only verified non-guillotine figure *and* 7 coded panels.

**Where they conflict, stratification wins.** `Miu2006` has the most panels of any article, but its
figures are ordinary 2x2 bar grids at medium gutters -- an already-crowded cell -- three of its eight
panels have **imputed** variance, and its dispersion type is stated nowhere in the paper. It sits in
Tier 2, below `Baraldi2013` Fig 1, which yields one coded panel but is the corpus's only natural
instance of the stray-letter exploit. One figure that discharges a dead stratum is worth more than
four that thicken a live one.

**Session planning consequence:** Tier 1 opens 13 PDFs for 14 figures, which is close to worst case
for context-switching. Tier 2 is much kinder -- 29 figures over 18 PDFs, with `Gobeske2009` alone
supplying 5 and `Clemenson2015`, `Hullinger2015`, `Chandler2020`, `Bonaccorsi2013` supplying 2-3 each.

### 2.5 Exclusions, recorded not hidden

- **Imputed variance (5 rows in the MA population):** `Keeley2014 Fig 3`, `Miu2006 Fig 3D/5A/6A`,
  `Yamada2018 Fig 10B`. Their reference dispersion was never read off a figure, so they cannot serve
  as a dispersion comparator. `worklist.json` marks each with
  `coded_panels[].usable_for_dispersion: false`. **Their panel geometry is still valid GT** -- do not
  drop the figures, only the dispersion comparison.
- **Non-mean/SD dispersion channels:** `Liu2009` (median ± quartile), `Kazlauckas2011` Fig 4 (median,
  IQR), `Bockmann2023` Fig 4 (IQR). Panel GT yes, dispersion channel no.
- **`Kazlauckas2011` Fig 3A** stays excluded on the pre-existing provenance grounds (coded Ns 23/28
  match no bar group in the figure).
- **`Bhat2023`'s only coded row is `Table 4`** -- not a figure-reading task.

---

## 3. Tier 1 -- the minimum viable set

**14 figures, 95 panels, 11 landmark panels, 3.9 hours.** That is at the stated ceiling with no
slack, so: **item #14 (`Ederer2022` Fig 2) is a stretch item -- cut it first.** Without it Tier 1 is
13 figures / 3.6 h, and every stratum target above is still met except that `S0_textGT` drops from 5
figures to 4. Cut nothing else; each of the remaining 13 is the *only* real instance of at least one
thing.

Columns: `letters/tiles` = caption letter count / visual tile count (a mismatch is itself the test);
`coded(text)` = coded panels in the figure, of which text-verified; `min` = U2 only.

| # | article | figure | page | licence | letters/tiles | strata | coded(text) | min |
|---|---|---|---|---|---|---|---|---|
| 1 | Zhang2017 | Fig 3 | 4 | **CC-BY-NC** | 7/7 | S0, S1, S7, S18 | 6 (2) | 11 |
| 2 | Lee2024 | Fig 2 | 6 | **CC-BY-NC** | 3/5 | S0, S8, S9, S11 | 2 (1) | 8 |
| 3 | Smith2018 | Fig 3 | 7 | **CC-BY** | 4/4 | S0, S16, S1 | 1 (1) | 7 |
| 4 | Gattas2022 | Fig 4 | 6 | **CC-BY** | 3/5 | S0, S8, S9 | 1 (0) | 9 |
| 5 | Gobeske2009 | Fig 2 | 4 | **CC-BY** | 13/13 | S3, S7 | 0 | 18 |
| 6 | Bonaccorsi2013 | Fig 2 | 5 | **CC-BY** | 2/14 | S3, S9, S12 | 0 | 16 |
| 7 | Clemenson2015 | Fig 3 | 13 | paywalled | 5/12 | **S4**, S3, S9, S2 | 2 (0) | 12 |
| 8 | Lyst2012 | Fig 7 | 6 | **CC-BY** | 0/4 | S5, S1 | 1 (0) | 7 |
| 9 | Morgan2018 | Fig 7 | 14 | paywalled | 3/3 | S5 | 3 (0) | 7 |
| 10 | Chrusch2023 | Fig 2 | 7 | **CC-BY** | 4/7 | S3, S8, S9, S2 | 0 | 11 |
| 11 | Baraldi2013 | Fig 1 | 3 | paywalled | 4/4 | **S6**, S11 | 1 (0) | 9 |
| 12 | Harburger2007b | Fig 3 | 6 | paywalled | 8/8 | S2, S7 | 2 (0) | 11 |
| 13 | Nawaz2018 | Fig 1 | 3 | paywalled | 0/1 | S10, S11 | 1 (0) | 5 |
| 14 | Ederer2022 | Fig 2 | 9 | **CC-BY** | 8/8 | S0, S7 | 2 (1) | 10 |

Pages are 1-based PDF page indices, not printed page numbers. Paths, DOIs, full captions,
per-panel comparison IDs and the adversarial-feature notes are in `worklist.json`.

**Nine of fourteen are open access.** Five are paywalled and are marked
`redistribution: "metadata_only"` -- publish the boxes, letters, tags and pixel coordinates, never
the cropped image. Each paywalled item is there because it is the only real instance of something:
`Clemenson2015` Fig 3 is the only verified non-guillotine figure in 222; `Baraldi2013` Fig 1 is the
only natural stray-letter collision; `Morgan2018` Fig 7 is the only labels-absent figure with three
coded panels *and* a labelled twin; `Harburger2007b` Fig 3 is the only 8-panel tight grid whose
caption hides its letters inside prose; `Nawaz2018` Fig 1 is a single-panel control that carries a
coded value.

### Tier 1 landmark panels (U3)

| article | panel | min | text-verified | dispersion |
|---|---|---|---|---|
| Zhang2017 | Fig 3b, 3c, 3d, 3g | 6 each | no | SD (Methods only) |
| Zhang2017 | **Fig 3e, 3f** | 6 each | **yes** | SD (Methods only) |
| Lee2024 | **Fig 2-B** | 6 | **yes** | SEM |
| Lee2024 | Fig 2-C | 6 | no | SEM |
| Smith2018 | **Fig 3A** | 9 | **yes** | SEM |
| Gattas2022 | Fig 4b | 9 | no | SEM |
| Ederer2022 | **Fig 2A** | 6 | **yes** | SEM |

### Tier 1 budget

| | minutes |
|---|---|
| U1 -- verify figure region + caption on 13 pages | 21 |
| U2 -- 14 figures, 95 panels | 142 |
| U3 -- 11 landmark panels (5 text-verified) | 71 |
| **total** | **234 min = 3.9 h** |
| **total without the stretch item #14** | **216 min = 3.6 h** |

### What Tier 1 buys, stated honestly

- **Panel decomposition:** 14 figures / 95 panels. Enough for a median per-panel IoU with a usable
  interval and for a per-stratum *direction*; **not** enough for a per-stratum rate with a tight CI
  (an exact-count rate over 14 figures carries roughly +/-13pp). It is enough to answer the actual
  open question -- *does the synthetic 95.1% survive contact with real figures, and do the flush and
  non-guillotine strata behave as badly in the wild as they do on the ladder* -- because those two
  strata are represented by 6 and 1 figures respectively rather than by nothing.
- **Dispersion:** 11 panels, of which **5 carry a text-printed reference**. That converts the pilot's
  6-panel *agreement* number into a small *accuracy* number for the first time.
- **Detection:** 13 pages of verified figure region + caption association, against the current N=1.

---

## 4. Tier 2 -- committee grade

**29 figures, 170 panels, 32 landmark panels, 9.1 h (cumulative 13.0 h).** Full list in
`worklist.json` (`tier: 2`). What it adds:

- **Statistical power.** 43 figures / 265 panels total takes the exact-count rate to about +/-7pp and
  gives every oversampled stratum 3+ figures instead of 1-2.
- **Replication inside strata.** Flush goes from 2 figures to 6 (`Gobeske2009` Fig 6/7/8,
  `Bonaccorsi2013` Fig 3, `Chandler2020` Fig 4, `Lee2024` Fig 5). Non-guillotine gets its second
  candidate (`Clemenson2015` Fig 2 -- **confirm the verdict at annotation time; it may resolve to
  span-left, which is still guillotine, and that negative result is worth recording**).
- **The controlled contrast.** `Morgan2018` Fig 7 (Tier 1, no letters) versus Fig 8 (Tier 2, letters
  drawn): same paper, same journal, same 3-panel layout, everything held constant except the drawn
  labels. This is the cleanest available estimate of how much the detector's accuracy depends on
  glyph anchoring rather than geometry.
- **The XObject fast path, scored.** `Chandler2020` Fig 3 has 4 raster XObjects whose bounding boxes
  *are* panels A-D exactly, while panel E is vector -- so the fast path returns 4 of 5 and silently
  drops the fifth. `Bonaccorsi2013` Fig 2 (Tier 1) is the opposite failure: 2 XObjects for 12 tiles.
  One figure per direction.
- **Two near-miss text references.** `Frick2003` Fig 1A and `Laurence2015` Fig 5E both produce a
  `mean ± variance` text match, but only under a looser tolerance than the 6% bar used above (the
  text rounds to 1 dp where the coding kept 2). They are worth annotating and re-checking by eye --
  if the text value is genuinely the plotted one, each adds an accuracy reference; `worklist.json`
  records `text_value_verified: false` for both so nothing silently upgrades.
- **Dispersion at scale.** 32 more landmark panels takes the dispersion channel to 43 panels, which
  is enough for the full three-level golden diff (`rma.mv(~1 | article/row)`) that
  `benchmark/real/RESULTS.md` section 5 asks for.

---

## 5. Tier 3 -- nice to have

**28 figures, 102 panels, 49 landmark panels, 9.0 h (cumulative 21.9 h).** The long tail: remaining
`Gobeske2009` and `Chrusch2023` figures, the within-paper replicates (`Leger2012a` Fig 4,
`Chrusch2023` Fig 1/3/5), the odd content types (`Gobeske2009` Fig 3's table panel, `Bouet2011`
Fig 3's table panel, `Madronal2010` Fig 4's equation box, `Aykan2024` Fig 2's stacked bars), and the
awkward-to-crop items (`Jaimes2020`, `Esselun2021`, `Meshi2006`, `SampedroPiquero2018`) which are
themselves Target-1 evidence.

**Two things that belong in Tier 3 but are not (article, figure) items:**

1. **Second-reader replication on a 20% subsample.** `benchmark/real/RESULTS.md` section 5.2 asks for
   two independent readers per panel to turn "transfer gap" into an inter-reader accuracy envelope.
   Budget: 20% of the Tier 1+2 landmark set (9 panels) at 6-9 min = ~1.2 h.
2. **The full 165-PDF Target-1 sweep.** Run Docling over all 165 resolvable PDFs (machine time), then
   have the human verify a random 30-page audit sample at 1.5 min each = 45 min. This gives a figure
   detection + caption association number over ~800 figures at the cost of 30 verifications, which is
   a far better return than verifying every page.

---

## 6. Where the real corpus CANNOT cover a synthetic stratum

Stated plainly, because a benchmark that quietly drops a stratum reports its absence as success.

**Un-coverable -- the real corpus has zero instances.**

1. **Heatmaps and colourbars.** The synthetic ladder has 12 heat panels and 3 colourbar distractors,
   including `L2_grid1x3_heat_cbar` and `L5_pinwheel5_tight_cbar` which specifically test a colourbar
   sitting between panels. Across 222 surveyed figures in 43 articles -- and the extraction workbooks'
   panel names across all 172 -- **there is not one heatmap and not one colourbar**. Rodent
   behavioural neuroscience plots bars, lines, and micrographs. The colourbar-in-gutter result stays a
   synthetic-only claim and must be labelled as one.
2. **Top-centre panel labels.** Synthetic has 2. Real: none found. Journals centre *titles*, not
   letters.
3. **Bottom-right labels.** Synthetic has 2. Real: none. The real corpus uses bottom-**left**
   (`Miu2006`, `Frick2003`), which is a different cell -- covered as `S13`, not as the synthetic one.
4. **Chart-type breadth.** `benchmark/classify` scores 18 chart types across 12 R libraries at 100%.
   The real corpus is bar, line, box, and dot plot -- four. The classifier's *breadth* cannot be
   validated here at all, only its accuracy on the four types that occur. No forest plot, no funnel
   plot, no dose-response curve of the synthetic kind.

**Barely coverable -- and that is itself the finding.**

5. **True non-guillotine.** Synthetic devotes 6 of 41 figures (15%) to pinwheel/windmill layouts.
   Across 222 real figures I found **one** verified instance (`Clemenson2015` Fig 3) and one candidate
   (`Clemenson2015` Fig 2). Journals typeset figures in grids. So the cascade's *worst* stratum is
   also its *rarest*, at roughly 0.5-1% of real figures against 15% of the synthetic ladder. Both
   directions matter: the synthetic corpus over-weights a failure that barely happens, **and** a real
   sample large enough to estimate performance in that cell does not exist in this corpus.
   Recommendation: keep the synthetic L5 tier for regression testing, stop treating its score as a
   headline, and report the real non-guillotine result as n=1-2 with no interval.

**Real strata with NO synthetic counterpart -- the more actionable direction.**

These are all common, all absent from the ladder, and several attack load-bearing design decisions.
They should become an `L9` tier in `benchmark/panels/gen_panels.R`.

6. **One caption letter over several visual tiles** (`S9`) -- found in **8 of the 14 Tier-1 figures**
   and pervasive beyond. `Bonaccorsi2013` Fig 2 names 2 letters over 14 tiles; `Leger2012a` Fig 3
   names 3 over 5; `Yamada2018` Fig 10 names 3 over 11. The cascade uses the caption count as a
   **hard constraint** (removing it drops exact-count from 95.1% to 9.1%), and on these figures that
   constraint is *systematically wrong*. Not one synthetic figure tests it. This is the highest-value
   addition to the synthetic ladder.
7. **Label systems outside `[A-Z]`** (`S8`): primes (`A`,`A'`,`C`,`C'`,`C"` -- `Chrusch2023`),
   hierarchical (`A-(a)` -- `Lee2024`), roman-numeral nesting (`a.i`, `a.ii`, `c.i` -- `Gattas2022`),
   case mixing (`Hullinger2015` Fig 4 draws `c` lowercase among uppercase), and lowercase
   Nature-style (`Meshi2006`, `Mansk2023`).
8. **Caption letter *formats* the extractor must parse**: `A)` mid-sentence (`Morgan2018`), `A,`
   (`Yamada2018`, whose PDF text layer has no spaces at all), `A.` (`Leger2012a`), `Panel A`
   (`Doulames2014`), and letters buried in prose -- `Harburger2007b`'s "young (A and E), middle-aged
   (B and F) ... the bars in D and H".
9. **Positional-only captions** (`Lyst2012` Fig 8: "top left panel", "bottom right"), and captions
   naming no letters at all (`Lyst2012` Fig 7). There is nothing to anchor to, so any answer is a pure
   reading-order claim -- exactly the condition that manufactures silent mislabels.
10. **Content types with no synthetic analogue:** Western-blot strips (`Gobeske2009` Fig 1C),
    rendered tables as panels (`Gobeske2009` Fig 3E, `Bouet2011` Fig 3A), equation boxes
    (`Madronal2010` Fig 4B), experimental-timeline schematics (everywhere), photographs of apparatus
    (`Clemenson2015` Fig 1).
11. **Section-heading text bands inside the figure** (`Chandler2020` Fig 2: bold "5 Minute Open Field"
    / "Elevated Plus Maze" between rows) -- ink owned by no panel, in a position where a gutter
    should be.
12. **Figure-region hazards** (`S15`, Target 1, entirely unexercised synthetically): two figures side
    by side on one page (`Lambert2005`), body text flowing against the figure edge (`Melani2017`),
    figure legends on a different page from the figures (`SampedroPiquero2018`, `Morgan2018` --
    accepted-manuscript PDFs), and figures on pages 32-36 of a preprint-style layout (`Jaimes2020`).
13. **Vector figures with a readable text layer** (`S11`, section 0c above).
14. **Central-tendency landmarks that are not bar tops** (`S16`): a mean line over a point cloud
    (`Smith2018`, `Chandler2020`, `Chrusch2023`, `Mansk2023` -- increasingly the modern default), a
    stacked-bar segment boundary (`Aykan2024`), median with IQR whiskers (`Kazlauckas2011`,
    `Liu2009`). The whole `bar-top -> mean` landmark model in `harness/calibrate.py` assumes a bar.

**One more, about the reference rather than the images.** The dispersion *type* is stated in the
caption for most items, in Methods only for some (`Zhang2017` SD, `Hullinger2015` SEM,
`Morgan2018` SEM -- in a *table* legend), and **nowhere at all** for `Lyst2012` and `Miu2006`. Since
`SD = SEM x sqrt(n)`, a wrong guess is a sqrt(n) error in the escalc input -- far larger than the
3.67% dispersion read error the pilot measured. Every worklist item carries a `dispersion_type` field
with its provenance, and the two "UNSTATED" articles are flagged as human-gate items rather than
silently defaulted.

---

## 7. Files

| file | role |
|---|---|
| `SAMPLING-AND-WORKLIST.md` | this document: frame, strata, tiers, budget, coverage gaps |
| `worklist.json` | machine-readable: 71 figure items + 92 landmark tasks, `schemaVersion: 1` |
| `PROTOCOL.md` | how to annotate (owned elsewhere) |
| `ANALYSIS-PLAN.md` | what to compute (owned elsewhere) |

`worklist.json` conforms to the schema `prepare_session.py:load_worklist` consumes (`item_id`,
`article`, `doi`, `pdf`, `page`, `figure`, `row_ids`, `difficulty`, `stratum`, `caption`) and carries
the additional fields above alongside. `row_ids` are `population.json` row ids where the article
survived into the meta-analysis; `comparison_ids` are the workbook `Comparison_ID`s and cover the
full 172-article frame.

### Reproducing the frame

```bash
# 1. parse the 200 extraction workbooks -> 528 comparisons / 464 figure-derived
#    (openpyxl, sheet 'Main', column C+ = Comparison_1..N)
# 2. resolve DOIs to local Zotero PDFs (165/172 ok)
ZOTERO_HOME=/mnt/c/Users/gregs/Zotero python3 benchmark/real/resolve_pdfs.py
# 3. survey figures with PyMuPDF: captions, expected letters, image XObjects vs vector ops,
#    label-like text spans inside the figure region, gutter profiles on the rendered crop
# 4. text-value verification: search each PDF for the coded 'mean +/- variance' pair
```

The survey scripts used to build this document are working files, not deliverables; the measurements
they produced are frozen in `worklist.json:frame` and in the per-item `difficulty_axes`.
Re-measure at annotation time and **overwrite any tag that disagrees** -- the tags are a survey, and
the annotation pass is the authority.
