# Series / group parsing: pipeline integration design

How the third perception sub-task (**parse**: which marks belong to which series/group, and what the
legend calls them) lands in the existing system -- the `figure-extractor.html` tool, the vision-model
<-> agent interface contract, the meta-analysis data schema, and the B4 human gate.

Companions: `WHITE-PAPER-LOG.md` §9-§10 (the three silent-catastrophic-error classes; where ML helps),
`../meta-analysis/VISION-MODEL-METHODOLOGY.md` §6 (the interface contract this extends) and §19a,
`../meta-analysis/AUTOMATED-MA-VISION.md` §5/§6a (gates + the two typed schemas),
`README.md` (the R-GT benchmark whose GT bundle already carries `group`/`series` per landmark).

**Status: design only.** Nothing here is applied. No shared code is modified; `benchmark/series/`,
`benchmark/r/`, and `benchmark/harness/` are untouched (a parallel agent owns the benchmark). Code
blocks marked PROPOSAL are illustrative sketches of the patch, not the patch.

**The invariant carried throughout** (from VISION-MODEL-METHODOLOGY §5 and WHITE-PAPER-LOG §10):
the model outputs **structure**, the agent binds **meaning**, deterministic code does the arithmetic,
R does the statistics, and a human confirms the quantities that are catastrophic when silently wrong.
Series assignment is now the third such quantity, alongside dispersion type and `Direction`.

---

## 0. Where the capability is missing today (grounded audit)

Series is not absent from the tool -- it is present in five places, each stopping short of the one
that matters. The gaps are precise:

| # | Where | What exists | What is missing |
|---|---|---|---|
| 1 | `CHAR_VOCAB.role` (line 4507) | `['control','intervention','comparison','reference','subgroup','pooled','unknown']` | **Never validated and never read.** `validateCharacterization` (4543-4570) does not check `role`; nothing downstream consumes it. |
| 2 | `panel.series[]` | Documented in the `figure-meta-extract` SKILL as `{name, role, colorHex, n, nSource}`; read once at `runExtraction` line 4812 (`panel.series[0].nSource`) | **Not validated, not keyed, not linked to any landmark.** Only `series[0]`'s `nSource` is ever used. |
| 3 | `EXTRACT.bars` (4591-4600) | `groups=[{name, mean, errorHalf, n}]` | `name` is **free text** with no group/series decomposition. A 3-timepoint x 2-arm chart is 6 unrelated strings. |
| 4 | `LANDMARK_HEADER` / `authoritativeRows` (4118-4138) | one `group` column | No `seriesId`/`seriesLabel`/`role`. Worse: the scatter branch (line 4134) emits `{landmarkKind:'point', x, y}` and **drops `p.s`** -- the digitizer's own series index, which `runExtraction` line 4820 carefully preserved. A two-colour scatter exports as one undifferentiated cloud. |
| 5 | Digitizer `dig.series` (3473-3478, 3530, 4782) | real, working series with colour + per-point `s` index; persisted by `setDigitization` (4774-4786) and `persistDig` (3691) | Series carry `{name, color}` only -- no id, no role, no legend swatch; the manual path and the agent path do not share a structure. |

Two more consequences worth naming because they are live defects, not just absences:

- **`digAutoTrace` (3506-3525) scans every column of the whole crop**, legend included. A legend swatch
  of the traced colour contributes phantom points to the series. Series-awareness supplies a legend
  bounding box, which makes this a deterministic exclusion (guard G8, §5).
- **Extraction flags never reach the CSV.** `runExtraction` stores `flags` on the extraction (4828) and
  `setDigitization` stores calibration flags (4783), but `LANDMARK_HEADER` (4118) has no flags column,
  so `dispersion-type-uncertain` -- the flag whose entire purpose is "this uncertainty must never be
  silent" -- is invisible in the artifact handed to R. Series flags must not repeat that mistake.

And in the real-figure golden diff, series assignment is currently done **out of band by a human**:
`benchmark/real/tasks/*.json` pre-declares `"control_bar": "sc_target", "interv_bar": "ee_target"`.
That is the layer this design internalizes. Honest corollary for the white paper: **the real-figure
result in WHITE-PAPER-LOG §5 does not measure series parsing at all** -- the reader was handed it.
The same fields are the ready-made answer key for scoring it.

---

## 1. Data-model changes

### 1.1 The modeling decision: two structuring dimensions, not one

A mark in a grouped chart sits at the intersection of two independent dimensions:

- **group** -- position on the categorical axis (`2 weeks` / `4 weeks` / `8 weeks`; `Vehicle` / `Low` / `High`).
  Usually a *moderator or timepoint* in the MA schema.
- **series** -- the legend entry (`Control` / `Run`). Usually an *arm*.

The tool currently collapses both into one free-text `name`. That collapse is exactly the
silent-catastrophic surface: `"Control 2wk"` is unparseable downstream, a 2x3 design cannot be checked
for missing cells, and the arm/moderator distinction -- which decides whether a value becomes an arm
mean or a moderator level -- is left to string matching.

So: **every landmark declares `(groupId, seriesId)`.** A plain bar chart is the degenerate case: each
bar is its own group with a single implicit series `s1` (the same default `setDigitization` already
synthesizes at line 4782 and `digitizationToCsv` at 3714).

This matches the benchmark GT bundle, which already emits `{"role":"top","group":0,"series":"s1",...}`
per landmark (`README.md`, GT schema). Terminology note for the scorer: in the GT bundle's simple-bar
case the top-level `"groups": ["Control","Run"]` array names what this design calls **series**; the
per-landmark `group` integer is the categorical-axis index. The design keeps the per-landmark meaning
(axis position = group, legend entry = series) and the mapping is mechanical.

### 1.2 `CHAR_VOCAB` additions (additive; schemaVersion stays 2)

```js
// PROPOSAL -- additions to CHAR_VOCAB (line 4504)
seriesEncoding: ['color', 'fill-pattern', 'marker-shape', 'line-style', 'position-only',
                 'panel', 'mixed', 'none', 'unknown'],
seriesLayout:   ['single', 'grouped', 'stacked', 'overlaid', 'paired', 'unknown'],
labelSource:    ['legend', 'axis-tick', 'direct-label', 'caption', 'inferred', 'none'],
flags: [ ...existing 14...,
  'series-assignment-uncertain',  // the mandatory-flag mechanism, mirroring dispersion-type-uncertain
  'series-count-mismatch',        // legend entries != detected series, or cells != groups x series
  'legend-order-mismatch',        // legend order != plot order
  'legend-unbound',               // legend text read but not bindable to a role from caption/methods
  'similar-hue-series',           // two swatches below a deltaE threshold
  'series-shared-control',        // one series serves as control for >1 intervention series
],
```

`role` (4507) is unchanged in content but becomes **enforced** -- `validateCharacterization` gains a
`role` check with the same shape as the existing `dataProvenance` check at line 4565. `overlapping-series`,
`occluded`, and `no-legend` already exist and are directly load-bearing here; reuse them, do not duplicate.

`seriesEncoding` is not cosmetic: it decides which guards apply. `color` invites the similar-hue guard;
`position-only` (dodged bars distinguished purely by x-offset) invites the order guard; `marker-shape`
under `low-resolution` is where assignment confidence should collapse.

### 1.3 The validated panel schema

```jsonc
// PROPOSAL -- panel additions. All keys optional; validated only when present.
{
  "charType": "grouped-bar",
  "seriesLayout": "grouped",
  "seriesEncoding": "color",

  // The categorical-axis dimension. Order is PLOT order, left to right / top to bottom.
  "groups": [
    { "id": "g0", "label": "2 weeks", "labelSource": "axis-tick", "order": 0 },
    { "id": "g1", "label": "4 weeks", "labelSource": "axis-tick", "order": 1 }
  ],

  // The legend dimension. `id` is the STABLE key every landmark references.
  "series": [
    { "id": "s1", "label": "SC", "labelSource": "legend",
      "swatch": { "px": 512, "py": 44, "colorHex": "#4472c4", "shape": "square" },
      "encoding": "color", "plotOrder": 0, "legendOrder": 0,
      "assignmentConfidence": 0.94,          // MODEL: confidence that marks tagged s1 really are s1
      "role": "control",                     // AGENT: meaning, bound from caption/methods
      "roleEvidence": "caption: 'SC = standard cage'",
      "roleConfidence": 0.97,
      "n": 5, "nSource": "caption",
      "markCount": 2 },                      // cross-check against groups.length
    { "id": "s2", "label": "EE", "labelSource": "legend",
      "swatch": { "px": 512, "py": 62, "colorHex": "#ed7d31", "shape": "square" },
      "encoding": "color", "plotOrder": 1, "legendOrder": 1,
      "assignmentConfidence": 0.91,
      "role": "intervention", "roleEvidence": "caption: 'EE = enriched environment'",
      "roleConfidence": 0.97, "n": 5, "nSource": "caption", "markCount": 2 }
  ],

  // The legend as a READ object -- never a digitized one. `legend` stays in ignoredElements.
  "legend": {
    "present": true, "bbox": { "x": 500, "y": 32, "width": 96, "height": 44 },
    "orientation": "vertical", "entryCount": 2, "readConfidence": 0.93
  },

  "ignoredElements": ["legend", "significance-markers", "gridlines"]
}
```

Design rules baked into the shape:

- **`id` is the join key, `label` is the printed text, `role` is the meaning.** Three separate fields
  because three different producers own them: the tool/agent mints ids, the model reads labels
  (OCR-adjacent perception -- permitted), the agent assigns roles from the caption (meaning -- required).
- **`assignmentConfidence` (structure) is separate from `roleConfidence` (meaning).** They fail
  independently: a model can be certain which marks are blue and have no idea what blue means; an agent
  can be certain "EE = enriched" and be fed a bad grouping.
- **`swatch.px/py` are pixels**, per the contract rule that the model emits pixels, never data values
  (VISION-MODEL-METHODOLOGY §6.1). The swatch position is what makes the gate's preview renderable and
  what makes the legend-exclusion guard computable.
- **`plotOrder` vs `legendOrder`** are recorded separately precisely so their mismatch is detectable.
  This is the highest-yield cheap check: ggplot's stacking order is reversed relative to legend order by
  default, and an off-by-one series labeling propagates across an entire figure.

### 1.4 The extraction record

`EXTRACT.bars` (4591-4600) currently returns `groups:[{name, n, mean, errorHalf, dispersionType}]`. The
proposal keeps that array shape and adds the decomposition, so existing consumers reading `name` keep working:

```js
// PROPOSAL -- EXTRACT.bars output element
{ name: "2 weeks / EE",        // legacy composite (back-compat display string)
  groupId: "g0", groupLabel: "2 weeks",
  seriesId: "s2", seriesLabel: "EE", seriesRole: "intervention",
  assignmentConfidence: 0.91,
  n: 5, mean: 18.36, errorHalf: 2.25, dispersionType: "SEM" }
```

`EXTRACT.boxes` takes the same three id fields. `EXTRACT.forest` rows gain `seriesRole` only, whose real
job there is `'pooled'` -- flagging the summary diamond so it is not extracted as if it were a study
(the forest analogue of a mis-assignment).

`stacked-bar` stays **explicitly unimplemented**: `CHART_METHOD['stacked-bar'] = 'segment-boundary'`
(4536) routes to a method `EXTRACT` does not define, so `runExtraction` already returns
`'no extraction method for stacked-bar'` at line 4822. That refusal is correct and should be preserved,
not "fixed" by routing stacked bars to `bars` -- stacked segment tops are cumulative, so reading them as
values is a silent 2x-scale error on every series but the first.

### 1.5 `LANDMARK_HEADER` and `authoritativeRows`

```js
// PROPOSAL -- LANDMARK_HEADER (line 4118), series block inserted after `group`,
// `seriesFlags` appended before the provenance trio.
const LANDMARK_HEADER = ['article','target','chartType','landmarkKind',
  'group','groupId','groupLabel','seriesId','seriesLabel','seriesRole','assignmentConfidence',
  'mean','errorHalf','dispersionType','median','q1','q3','min','max',
  'estimate','ciLo','ciHi','x','y','n','nSource','direction','timepoint',
  'seriesFlags','figure_derived','Data_Source','Data_Extraction_Method'];
```

Three notes:

1. `group` is retained verbatim as the composite display string, so nothing that reads it breaks.
2. `landmarksCsv` (4139) and the `push()` default-fill in `authoritativeRows` (4130) are name-keyed, so
   insertion is safe inside the tool; the only external risk is a positional consumer. In-repo consumers
   are name-keyed (`benchmark/real/score_real.py`, R's `read.csv`).
3. `seriesFlags` (semicolon-joined) is the fix for the §0 defect that extraction flags never reach the
   CSV. It should carry the series flags **and** `dispersion-type-uncertain`, so R and the human both see
   the uncertainty in the artifact rather than only inside `annotations.json`.

The scatter branch fix is one line and is the cheapest win in this document:

```js
// PROPOSAL -- authoritativeRows line 4134: stop discarding the series index.
else if (Array.isArray(e.points)) e.points.forEach(p => push({
    landmarkKind: 'point', x: p.x, y: p.y,
    seriesId: seriesIdFor(e, p.s), seriesLabel: seriesLabelFor(e, p.s), seriesRole: seriesRoleFor(e, p.s)
}));
```

### 1.6 Backward compatibility

`SCHEMA_VERSION` stays **2** and the change stays additive, per the standing comment at line 4503. The
rules that make that true:

- Every new field is optional. `validateCharacterization` validates each only when present -- the same
  pattern as `dataProvenance` (4565) and `ignoredElements` (4566).
- A characterization with no `series[]` is legal: the tool synthesizes a single implicit series
  `{id:'s1', label:null, role:'unknown'}` at read time, matching the defaults already used at 4782 and 3714.
- Old extractions emit `''` in the new CSV columns; `authoritativeRows`' zero-fill `push()` (4130) needs
  only the new keys added to its default object.
- `figuresToJSON`/`figuresFromJSON` (4166 / 4197) copy `characterization`, `digitization`, and `extraction`
  opaquely, so old annotations round-trip untouched with no loader change.
- **Reverse compatibility caveat, worth stating in the release note:** `validateCharacterization` line 4568
  rejects any flag not in `CHAR_VOCAB.flags`. A new flag string emitted by an updated agent prompt against
  an older tool build fails validation. So the flag additions and the prompt change must ship together, and
  the eval must keep importing the label space live from `charVocab()` (WHITE-PAPER-LOG §11).

---

## 2. The vision <-> agent contract extension

This extends VISION-MODEL-METHODOLOGY §6 without changing its shape. §6.1's bundle gains structure;
§6.2's agent gains one binding step; §6.3's uncertainty chain gains one more strand.

### 2.1 What the vision model hands the agent (structure only)

```jsonc
// PROPOSAL -- additions to the §6.1 perception bundle
{
  "panels": [{
    "seriesStructure": {
      "seriesCount": 2, "groupCount": 3,
      "encoding": "color", "layout": "grouped",
      "legend": { "present": true, "bbox": {...}, "orientation": "vertical",
                  "entries": [ { "text": "SC", "swatch": {"px":512,"py":44,"colorHex":"#4472c4"}, "order": 0 },
                               { "text": "EE", "swatch": {"px":512,"py":62,"colorHex":"#ed7d31"}, "order": 1 } ] },
      "plotOrder":   ["s1","s2"],       // order the series appear in the plot (left-to-right within a group)
      "legendOrder": ["s1","s2"],       // order they appear in the legend
      "structureConfidence": 0.92,
      "abstain": false
    },
    "landmarks": {
      "bars": [
        { "groupId": "g0", "seriesId": "s1", "assignConf": 0.96,
          "top": {"px":161,"py":288,"s":0.7}, "capUpper": {"px":161,"py":270,"s":1.1} },
        { "groupId": "g0", "seriesId": "s2", "assignConf": 0.93, "top": {...}, "capUpper": {...} }
      ],
      "points": [ { "seriesId": "s1", "px": 402, "py": 155, "s": 0.8, "assignConf": 0.71 } ]
    }
  }]
}
```

Contract rules, stated as sharply as the dispersion rule they mirror:

- **The model may read the legend's glyphs; it must not assert what they mean.** `entries[].text` is OCR
  (perception, permitted). `role` is never a model output. This is the series analogue of "the model must
  not assert dispersion type from pixels" -- and it holds for the same reason: `EE`, `Group 2`, and a bare
  colour swatch are visually complete and semantically empty. The meaning is in the caption.
- **Every mark carries an assignment, or it carries `null` plus a flag.** A mark with `seriesId: null` in a
  panel declaring >1 series must come with `series-assignment-uncertain`. Silence is not an option, exactly
  as the validator already refuses silent dispersion uncertainty (4559-4562).
- **`plotOrder` and `legendOrder` are reported separately, always** -- even when identical. Reporting only
  one makes the mismatch undetectable.
- **Per-assignment confidence is per-mark (`assignConf`), not per-panel.** Occlusion is local: the two
  overlapping points in the middle of a dense scatter are the uncertain ones, and a panel-level number
  averages that signal away.
- **Structural abstention is allowed and is a success, not a failure.** `abstain: "3 series declared in the
  legend, only 2 separable hues"` is the desired output; a confident 2-series read is the catastrophic one.

### 2.2 What the agent binds (meaning), and how series become arms

The agent reads the bundle **plus caption plus methods plus the MA criteria** and performs a binding it
records explicitly in the reasoning log (AUTOMATED-MA-VISION §6a):

| Step | Input | Output | Failure mode if skipped |
|---|---|---|---|
| B1 swatch -> label | `legend.entries[].text`, swatch pixels | `series[].label` | -- (model supplies) |
| B2 label -> role | caption/methods ("SC = standard cage") | `series[].role` + `roleEvidence` | **arm swap: effect computes backwards** |
| B3 group label -> schema dimension | axis-tick labels + caption | `timepoint` / moderator / `Test_ID` | timepoints mixed into one arm |
| B4 series -> arm ids | `role` + the codebook | `Control_Group_ID_Standardized`, `Intervention_Group_ID_Standardized` | rows that cannot be joined |
| B5 pairing | roles within a panel | one comparison per (control, intervention) pair per group | multi-arm variance wrong (§2.3) |

Mapping onto the dissertation codebook (`GSF-dissertation-meta-analysis/data/codebook.md`):

- `series[].role == 'control'` -> `Control_Group_Mean`, `Control_Group_Variance_Value`, `Control_N`,
  `Control_Group_ID_Standardized`.
- `series[].role == 'intervention'` -> `Intervention_Group_Mean`, `Intervention_Group_Variance_Value`,
  `Intervention_N`, `Intervention_Group_ID_Standardized`, `Arm_Number`.
- `groups[].label` -> **not an arm.** It becomes `timepoint`, a moderator column, or a distinct
  `Test_ID`/`Outcome_ID`, depending on the caption. Deciding which is an agent judgment that needs the
  article, which is why it cannot live in the model.
- One emitted comparison per (control series, intervention series, group) triple -> one `Comparison_ID`,
  and the nesting `Study_Arm_ID / Test_ID / Outcome_ID` the three-level `rma.mv` needs.

The tool itself never writes arm columns. It emits `seriesRole` on the landmark row and stops; the agent
maps role -> codebook column. That boundary keeps the tool population-agnostic (rodent and human schemas
diverge, per AUTOMATED-MA-VISION §2) while still making the assignment auditable in the tool's own artifact.

### 2.3 Multi-arm and shared control -- why this is a variance correctness issue

A panel with one control series and k>1 intervention series is a **shared-control multi-arm study**. If
the agent emits k comparisons without recording that they share a control, each comparison's variance is
computed as if independent, the pooled variance is too small, and the study is over-weighted. The codebook
already carries the machinery -- `Multi_Arm_Study`, `Number_of_Arms`, `Shared_Control_Group`,
`VIF_multiarm`, `vi_adjusted_multiarm` -- and R applies it (AUTOMATED-MA-VISION §7).

The consequence to state plainly: **recovering series structure is what makes the multi-arm correction
possible at all.** Without it there is no way to know two rows share a control group, so this capability
is not only about getting the right number in the right arm -- it is a precondition for the variance model.
Hence guard G7 (§5): the agent must set `series-shared-control` and `Shared_Control_Group = TRUE`, or refuse.

### 2.4 Uncertainty and abstention propagation

Extending the §6.3 chain with the series strand:

```
per-mark assignConf  ->  min over marks in a series  ->  series[].assignmentConfidence
                                                          |
legend read confidence + plotOrder/legendOrder diff ------+--> series flags
similar-hue deltaE (deterministic, tool-side) ------------+
cell-count invariant (deterministic, tool-side) ----------+
                                                          v
                    any flag or confidence < tau  ->  B4 human gate
                                                          v
                    confirmed -> row emitted with seriesFlags recorded (never cleared)
                    unresolved -> arms not emitted; counted as "no extractable data" in PRISMA
```

Same discipline as `figure_derived`: confirmation does not erase the flag. Verified is not laundered
(AUTOMATED-MA-VISION §6c) -- a human-confirmed assignment stays visible in `seriesFlags` so a
series-uncertain sensitivity analysis remains possible.

---

## 3. API surface (`window.figureExtractor`)

All sketches are PROPOSALS. Function names and line references point at the code they would sit beside.

### 3.1 `setSeries` -- a targeted updater for the binding step

Role binding happens in a different step, from different inputs, than perception. Forcing the agent to
re-POST the entire characterization to add a role invites clobbering a good landmark read with a stale copy.

```js
// PROPOSAL -- new API beside setCharacterization (line 4744)
setSeries: (figureId, subId, panelIndex, spec) => {
    const t = findTarget(figureId, subId);
    if (!t) throw new Error('target not found');
    const c = t.characterization;
    if (!c || !c.panels || !c.panels[panelIndex]) return { success: false, errors: ['no characterization panel'] };
    const errs = validateSeries(spec, c.panels[panelIndex]);
    if (errs.length) return { success: false, errors: errs };
    commit(() => {
        const p = c.panels[panelIndex];
        if (spec.series) p.series = spec.series;
        if (spec.groups) p.groups = spec.groups;
        if (spec.legend) p.legend = spec.legend;
        p.seriesUpdatedAt = nowISO();
    });
    return { success: true, flags: seriesFlags(c.panels[panelIndex]) };
},
```

### 3.2 `validateSeries` + `seriesFlags` -- the deterministic half

`validateSeries` returns hard errors (structure unusable); `seriesFlags` returns soft flags (structure fine,
review needed). Exposed the way `verifyCalibration` is exposed at line 4855, so an agent can pre-flight.

```js
// PROPOSAL -- beside validateCharacterization (line 4543)
function validateSeries(spec, panel) {
    const errs = [], ids = new Set();
    for (const s of (spec.series || [])) {
        if (!s.id) errs.push('series: missing id');
        else if (ids.has(s.id)) errs.push(`series: duplicate id "${s.id}"`);
        ids.add(s.id);
        if (s.role && !CHAR_VOCAB.role.includes(s.role)) errs.push(`series ${s.id}: unknown role "${s.role}"`);
        if (s.labelSource && !CHAR_VOCAB.labelSource.includes(s.labelSource)) errs.push(`series ${s.id}: unknown labelSource`);
        if (s.encoding && !CHAR_VOCAB.seriesEncoding.includes(s.encoding)) errs.push(`series ${s.id}: unknown encoding`);
    }
    return errs;
}

// Deterministic review triggers -- computable from the stored panel alone, no model involved.
function seriesFlags(panel) {
    const f = [], S = panel.series || [], G = panel.groups || [];
    const legendN = panel.legend && panel.legend.entryCount;
    if (legendN != null && S.length && legendN !== S.length) f.push('series-count-mismatch');
    if (S.length && G.length) {
        const expect = S.length * G.length;
        const got = S.reduce((a, s) => a + (s.markCount || 0), 0);
        if (got && got !== expect && !(panel.flags || []).includes('sparse-design')) f.push('series-count-mismatch');
    }
    const po = S.map(s => s.plotOrder), lo = S.map(s => s.legendOrder);
    if (po.every(v => v != null) && lo.every(v => v != null) && po.join() !== lo.join()) f.push('legend-order-mismatch');
    for (let i = 0; i < S.length; i++) for (let j = i + 1; j < S.length; j++) {
        if (hueDistance(S[i].swatch, S[j].swatch) < HUE_MIN) { f.push('similar-hue-series'); break; }
    }
    if (S.length > 1 && S.some(s => !s.role || s.role === 'unknown')) f.push('legend-unbound');
    if (S.filter(s => s.role === 'intervention').length > 1 && S.filter(s => s.role === 'control').length === 1)
        f.push('series-shared-control');
    if (S.some(s => (s.assignmentConfidence != null) && s.assignmentConfidence < ASSIGN_TAU))
        f.push('series-assignment-uncertain');
    return [...new Set(f)];
}
```

Note what is deterministic here: hue distance, count invariants, order comparison, role completeness. Four
of the six review triggers need no model at all -- they are arithmetic over the stored structure. That is
the cheap, buildable-now half of this capability (§6).

### 3.3 `runExtraction` accepts series-tagged landmarks

`runExtraction` (4794-4832) keeps its signature. Landmarks gain a **cell** form; the multi-panel hard-fail
at 4801-4803 gains a series sibling.

```js
// PROPOSAL -- landmark payload for a grouped bar chart
figureExtractor.runExtraction('fig1', 'fig1_s2', {
  cells: [
    { groupId: 'g0', seriesId: 's1', mean: 18.58, errorHalf: 2.25, n: 5 },
    { groupId: 'g0', seriesId: 's2', mean: 18.36, errorHalf: 2.25, n: 5 },
    { groupId: 'g1', seriesId: 's1', mean: 21.10, errorHalf: 1.90, n: 5 },
    { groupId: 'g1', seriesId: 's2', mean: 26.44, errorHalf: 2.05, n: 5 }
  ],
  direction: +1, timepoint: 'probe', nSource: 'caption'
});

// PROPOSAL -- guard inside runExtraction, immediately after the multi-panel refusal (line 4803)
const declared = new Set((panel.series || []).map(s => s.id));
const cells = landmarks.cells || landmarks.groups || [];
if (declared.size > 1) {
    const undeclared = cells.filter(c => c.seriesId && !declared.has(c.seriesId));
    if (undeclared.length) return { success: false,
        error: `landmarks reference undeclared seriesId(s): ${[...new Set(undeclared.map(c=>c.seriesId))].join(', ')}` };
    if (cells.some(c => !c.seriesId)) return { success: false,
        error: 'panel declares multiple series but some landmarks carry no seriesId -- assign or abstain' };
}
```

`landmarks.groups` (the current free-text form) stays accepted for single-series panels, so every existing
call site and the entire `eval/` harness keep working unchanged.

### 3.4 `EXTRACT.bars` grouped by series

The change mirrors the dispersion refusal at 4596-4599 exactly -- same structure, same "uncertainty is never
silent" contract:

```js
// PROPOSAL -- EXTRACT.bars (line 4591)
bars(cells, dispersionType, panel = {}) {
    const knownDisp = DISPERSION_WITH_VARIANCE.has(dispersionType);
    const byId = Object.fromEntries((panel.series || []).map(s => [s.id, s]));
    const gById = Object.fromEntries((panel.groups || []).map(g => [g.id, g]));
    const out = cells.map(c => {
        const s = byId[c.seriesId] || {}, g = gById[c.groupId] || {};
        return {
            name: c.name || [g.label, s.label].filter(Boolean).join(' / ') || String(c.groupId ?? ''),
            groupId: c.groupId ?? '', groupLabel: g.label ?? '',
            seriesId: c.seriesId ?? '', seriesLabel: s.label ?? '', seriesRole: s.role ?? '',
            assignmentConfidence: c.assignConf ?? s.assignmentConfidence ?? null,
            n: c.n ?? s.n ?? null, mean: c.mean, errorHalf: c.errorHalf, dispersionType
        };
    });
    const flags = knownDisp ? [] : ['dispersion-type-uncertain'];
    // Series discipline: multiple series with any untagged cell is a mis-assignment risk, never silent.
    if ((panel.series || []).length > 1 && out.some(o => !o.seriesId)) flags.push('series-assignment-uncertain');
    return { method: 'bar-endpoints', groups: out, flags };
}
```

### 3.5 The gate preview

```js
// PROPOSAL -- renders the assignment for human confirmation (uses cropImage, line 3035,
// and the marker-drawing pattern of digRender, line 3648).
previewAssignment: (figureId, subId) => ({
    image: /* data URL: panel crop with each mark overprinted in its series colour + "g0/s2",
              each legend swatch outlined and connected to its series id */,
    bindings: [{ seriesId, label, colorHex, role, roleEvidence, assignmentConfidence, markCount }],
    rows: authoritativeRowsFor(figureId, subId),   // exactly what would reach R
    flags: seriesFlags(panel)
}),
```

### 3.6 Converging the manual digitizer onto the same structure

`dig.series` (3476) is `{name, color}` and points carry `s` as an **array index** (3521, 3530) -- which
breaks if a series is deleted or reordered. Proposal: add optional `{id, label, role}` to each series
object and an optional `seriesId` on points, with `s` retained as the index fallback so every stored
digitization keeps loading (`openDigitizer` at 3742 already tolerates a missing `series`). Then:

- `persistDig` (3691) and `setDigitization` (4774) store the same series objects the agent produces.
- `renderDigPoints` (3667) and `digCsv` (3699) already render a `series` column when `dig.series.length > 1`;
  they gain a `role` column for free.
- The `+ Series` button (markup 1169; handler 1470-1475) is where a human fixes a bad machine assignment -- the manual path
  becomes the repair path for the automated one, rather than a parallel universe.

---

## 4. The human gate (B4)

AUTOMATED-MA-VISION §4/§5 puts B4 at "confirm figure-derived + dispersion + Direction". Series assignment
joins that list as the third silent-catastrophic quantity (WHITE-PAPER-LOG §9). The gate cannot be cleared
until three independent affirmations are written to the reasoning log: `confirmed_dispersion`,
`confirmed_direction`, `confirmed_series`, each with who and when.

### 4.1 What the checkpoint shows

1. **The assignment preview image** (§3.5). The panel crop with every mark overprinted in its assigned
   series colour and labelled `groupLabel / seriesLabel`, and each legend swatch outlined and tied to its
   series id. One glance answers the only question that matters: *is the bar the pipeline called Control
   actually the one the legend calls Control?* This is the artifact; a table of ids is not a substitute,
   because the error is spatial.
2. **The binding table** -- one row per series: swatch | printed label | role | evidence (the caption
   sentence, quoted) | assignment confidence | mark count. Role is a two-state control the human can flip;
   flipping it writes an amendment line to the reasoning log rather than silently editing the value.
3. **The emitted rows** -- the actual `authoritativeRows` cells that would go to R, including the composite
   `group` string and `seriesFlags`. The human confirms the object that leaves the system, not a paraphrase.
4. **The comparison preview** -- which (control, intervention) pairs will become `Comparison_ID`s, and
   whether `Shared_Control_Group` is set. This is where a multi-arm mis-coding is visible.

### 4.2 What a mis-assignment looks like

Naming the failure shapes, because the gate's job is to make them recognizable in seconds:

| Failure | What the human sees | Why nothing downstream catches it |
|---|---|---|
| **Role swap** (control <-> intervention) | Preview: the darker bar is labelled Control when the legend says otherwise | The effect size is numerically valid with the opposite sign. A negative `g` is legitimate, so no range check, no residual check, and **not `Direction`** -- `Direction` fixes outcome polarity, not arm order -- will flag it. The pooled estimate shifts and nothing complains. |
| **Series/group transposition** (read down instead of across) | Means paired with the wrong timepoint; group labels look shuffled | Every value is a real value from the chart; only the pairing is wrong. Totals and ranges are unchanged. |
| **Legend/plot order mismatch** | Every series label shifted by one across the whole figure | Systematic, so it looks internally consistent. Two-series charts turn it into a full swap. |
| **Dropped series under occlusion** | Fewer marks than groups x series | A missing row is invisible in a CSV of present rows. Only the cell-count invariant sees it. |
| **Legend swatch digitized as data** | A phantom point at the legend's y-value | Plausible magnitude; joins the cloud and biases the fit. |

### 4.3 Auto-flags that force review

Any of these routes the panel to B4 regardless of overall confidence:

- `series-assignment-uncertain` -- any mark below tau (tau set from the benchmark's measured
  mis-assignment-rate-vs-confidence curve, not guessed; see §6).
- `series-count-mismatch` -- legend entries != series, or emitted cells != groups x series without a
  declared sparse design.
- `legend-order-mismatch` -- plot order != legend order.
- `similar-hue-series` -- two swatches below the deltaE threshold.
- `legend-unbound` -- role could not be bound from the caption/methods.
- `no-legend` (existing flag) with >1 series -- labels can only come from the caption, so binding is textual
  and unverifiable against the image.
- `overlapping-series` / `occluded` (existing flags) -- assignment recall, not localization, is at risk.
- `series-shared-control` -- forces confirmation of the multi-arm coding (§2.3).

Plus a sampling rule: gate a random fraction of *unflagged* panels too, so the residual post-gate error rate
(AUTOMATED-MA-VISION §10) is measurable rather than assumed.

---

## 5. Failure modes and guards

The existing precedents set the pattern: a **hard fail** when the structure is unusable (the multi-panel
refusal, 4801-4803), a **forced flag** when the structure is fine but the meaning is uncertain (the
dispersion-type refusal, 4596-4599 and 4559-4562). Series guards split the same way.

| # | Guard | Trigger | Response | Precedent |
|---|---|---|---|---|
| G1 | Undeclared series id | landmark `seriesId` not in `panel.series[]` | **hard fail**, nothing stored | multi-panel guard 4801 |
| G2 | Ambiguous series count | legend entries != detected series, and neither is confidently zero | **refuse to emit arms**; store landmarks with `seriesId:null` + `series-assignment-uncertain` | dispersion refusal 4596 |
| G3 | Role unbound | >1 series, any `role` missing/`unknown` | emit rows with empty `seriesRole` + `legend-unbound`; the agent must not write `Control_*`/`Intervention_*` columns | -- |
| G4 | Similar hues | swatch deltaE below threshold | mandatory human confirmation (`similar-hue-series`) | dispersion type: "cannot be read from pixels" |
| G5 | Cell-count invariant | cells != groups x series, no `sparse-design` | `series-count-mismatch` -> gate | -- |
| G6 | Stacked bars | `charType == 'stacked-bar'` | keep the existing refusal (`segment-boundary` unimplemented, 4822); never route to `bars` | current behaviour, preserved deliberately |
| G7 | Shared control | 1 control series, k>1 intervention series | require `Shared_Control_Group = TRUE` + `Multi_Arm_Study` before k comparisons are emitted | codebook `VIF_multiarm` |
| G8 | Legend ink as data | any landmark/digitized point inside `legend.bbox` | drop with a warning; re-run `digAutoTrace` with the legend rect excluded | `ignoredElements` contract (4517), made enforceable |
| G9 | Series-count vs n-source | `series[].n` present for only some series | `n-unknown` (existing flag) per series, not per panel | existing flag, finer granularity |

G1, G4, G5, G8 are pure arithmetic/geometry over stored fields -- no model, no benchmark evidence needed.
G2, G3, G7 are contract enforcement at the agent boundary. G6 is a refusal to preserve.

One anti-guard worth stating: **do not auto-repair a suspected order mismatch by swapping labels.** The
correct response to `legend-order-mismatch` is a gate, not a fix -- a heuristic swap converts a detectable
error into an undetectable one, which is the exact failure class this whole design exists to prevent.

---

## 6. Sequencing

The project's discipline is measure-before-building (AUTOMATED-MA-VISION §19, VISION-MODEL-METHODOLOGY §7).
That splits this capability cleanly, because most of the *integration* is contract and arithmetic, while
only the *perception* half needs the benchmark's evidence.

### Buildable now (no model, no benchmark dependency)

1. **Activate what already exists.** Validate `panel.series[]` and the `role` vocab (both present since the
   characterization layer was written, neither enforced). Cost: one validator function, one vocab check.
2. **Stop discarding series in the CSV.** The scatter branch fix at 4134 (`p.s` is already computed at 4820)
   plus the `seriesId`/`seriesLabel`/`seriesRole` columns in `LANDMARK_HEADER`. This is the highest
   value-per-line change in the document: a two-colour scatter currently exports as one cloud.
3. **`seriesFlags` column**, which also fixes the standing defect that `dispersion-type-uncertain` never
   reaches the artifact R and the human actually read.
4. **The deterministic guards G1, G4, G5, G8.** Hue distance, count invariants, order comparison, legend-rect
   exclusion. All computable from stored fields; all catch real, named failures.
5. **The B4 gate artifact** -- the assignment preview image plus the binding table. The gate is where this
   capability pays off, and it needs no model to be useful: it makes a *human's* assignment auditable too.
6. **Extend the `figure-meta-extract` skill** to require the binding table with a quoted caption evidence
   line per series, and to forbid asserting a role without one.

### Waits on the benchmark's evidence

1. **The confidence threshold tau.** Setting it now would be a guess. The benchmark's headline metric is a
   **mis-assignment rate** (WHITE-PAPER-LOG §10); tau should be read off the mis-assignment-rate-versus-
   confidence curve at the tolerable rate, sliced by density/occlusion.
2. **Whether `legend-order-mismatch` should hard-fail rather than flag.** Depends on measured frequency and
   on whether models systematically report legend order when asked for plot order.
3. **Whether structural grouping needs a detector head.** Per WHITE-PAPER-LOG §10 the split is: legend text
   -> label is agent work (language, and classification is already at ceiling per §8); mark -> series
   assignment on dense/occluded charts is the candidate ML win, implemented as a **series-aware head on the
   landmark detector**, not a separate model. Build it only if the benchmark shows assignment accuracy
   degrading with density in a way prompting cannot close -- the same bar the detector itself has to clear.
4. **The real-figure transfer gap for assignment.** Note the honest caveat from §0: the current real-figure
   result was handed its series assignment by `benchmark/real/tasks/*.json` (`control_bar`/`interv_bar`),
   so it measures reading, not parsing. Those same fields are the answer key for measuring it -- the
   cheapest real-figure series experiment available, and it should be reported as its own number rather than
   folded into the existing dispersion result.

### The one-line summary of the split

Everything that makes a mis-assignment **visible** (schema fields, deterministic guards, the CSV columns,
the gate preview) is cheap and should exist before the next real-figure run. Everything that makes
assignment **more accurate** (a detector head, a tuned threshold) waits for the benchmark to say how
inaccurate it currently is, and on which charts.
