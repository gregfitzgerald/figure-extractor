---
name: figure-meta-extract
description: >
  Characterize a figure/subfigure from an academic paper for META-ANALYTIC
  extraction, then decide whether/how to extract its numbers. ALWAYS reads the
  figure together with its article context (caption + surrounding text) and the
  meta-analysis criteria. Trigger on "characterize this figure", "what kind of
  chart is this", "extract figure data for meta-analysis", "pull effect sizes
  from the figures", "digitize this figure".
---

# figure-meta-extract

Turn a figure crop into a structured **characterization** that (a) names what the
chart is, (b) records the semantics needed to convert its marks into an effect size
+ variance, and (c) decides — against the meta-analysis criteria — whether and how to
extract it. Pairs with the `figure-extractor` tool (`window.figureExtractor`).

## The one rule: never characterize an image in isolation

The chart **type** is visual, but almost everything that makes a figure *usable* for
meta-analysis is not in the pixels:

- what the error bars mean (SD vs SEM vs 95% CI) — usually only the caption says;
- the units, the group **n**, the timepoint that is the outcome;
- whether the figure even reports the outcome the meta-analysis is about, for the
  comparison it cares about (Drug vs placebo, etc.).

So the input is always **image + article context (caption + relevant body text) +
meta-analysis criteria**. If the caption/context is missing, say so and lower
`confidence`; do not guess dispersion type, n, or the extract decision from the image.

## Inputs
- The figure/subfigure crop (`figureExtractor.getSubfigureAsBase64(figId, subId)` or
  `getFigureAsBase64(figId)`), rendered at the page's native resolution — never upscaled
  (higher DPI costs tokens with no fidelity gain).
- The caption and any surrounding article text that describes the figure.
- The meta-analysis criteria: the outcome(s), comparison(s), and eligible effect types.

## Procedure
1. **Read the crop.** Identify the number of panels; if multi-panel, characterize each
   panel separately (or recommend splitting into subfigures first).
2. **Classify the chart type** per the vocabulary below (visual).
3. **Read the axes** — label, unit, scale (linear/log/categorical), range, ticks.
4. **Read the series/groups** — names, roles (control/intervention), legend colors.
5. **Pull the statistics semantics from the CAPTION**: central tendency (mean/median/
   proportion/effect size), dispersion **type** (SD/SEM/CI95/IQR…), n per group,
   p-values. Mark any field you inferred rather than read, and flag
   `dispersion-type-uncertain` when the caption doesn't state it.
6. **Decide extract vs skip against the MA criteria** — does this figure report the
   target outcome for the target comparison, in an extractable form? Give a one-line
   reason grounded in the criteria + caption.
7. **Choose the extraction method** from the routing table.
8. Emit the characterization JSON; store it with
   `figureExtractor.setCharacterization(figId, subId, obj)` (validated against the vocab).

## Prioritise figures with the study's OWN original data
The point of extraction is the study's primary measurements. Rank targets accordingly:
- **HIGH — original data (extract first):** `bar`, `grouped-bar`, `histogram`, `line`,
  `scatter`, `box`, `violin`, `dose-response`, `kaplan-meier` — the study's own means,
  distributions, trajectories, points.
- **LOW — derived summaries:** `forest`, `funnel` plots **usually re-summarize OTHER
  studies' effects, not original data** — deprioritize them (extract only if the article
  ITSELF is that meta-analysis). Set `dataProvenance:"derived"`.
- **NONE:** `schematic`, `micrograph`, `flow-diagram` — no numeric data.

Tag every panel with `dataProvenance`: `primary` (the study measured it) vs `derived`
(a summary of other sources) vs `unknown`. Use `figureExtractor.extractionPriority(charType,
dataProvenance)` to get high/medium/low/none.

## Identify and IGNORE non-data elements
A chart is mostly non-data ink. Only DATA marks (bars, points, lines, error-bar caps) feed
`series` and extraction. Explicitly recognize and EXCLUDE — never treat as a data series or
digitize — these, and list them in `ignoredElements`:
`legend` (swatches name series, they are not extra data points) · `significance-markers`
(stars, brackets, p-value annotations) · `gridlines` · `axis-ticks`/labels · `title` ·
`panel-label` (A/B/C…) · `schematic`/`image-inset`/`micrograph` sub-parts · `colorbar`
(unless the chart is a heatmap) · `trend-line`/`reference-line` (a fitted/identity line is not
raw data) · free-text `annotation`. When auto-tracing a curve, pick the DATA color and avoid
axis/gridline black/grey and legend swatches.

## Chart-type vocabulary
`bar · grouped-bar · stacked-bar · histogram · line · scatter · box · violin · forest ·
kaplan-meier · pie · heatmap · roc · bland-altman · funnel · dose-response ·
flow-diagram · table · micrograph · schematic · other · unknown`

## Extraction routing (chart type -> method -> what you get)
| type | method | yields |
|---|---|---|
| scatter | digitize_points | (x,y) points -> r, slope, n |
| line / kaplan-meier / roc | auto_trace | per-series curve -> trajectory / survival / sens-spec |
| bar / grouped-bar / histogram | bar-endpoints | bar top (mean) + error-cap -> mean, SD/SE |
| stacked-bar | segment-boundary | segment values -> proportions/counts |
| box / violin | box-landmarks | median, Q1, Q3, whiskers -> mean/SD (Wan 2014) |
| forest | forest-rows | per-row effect size + CI -> variance directly |
| pie | angle-digitizer | slice proportions |
| heatmap | colorbar-calibration | cell values (e.g. correlations) |
| table | read_table | printed numbers directly |
| flow-diagram / schematic / micrograph | not_extractable | no numeric yield |

## Statistics -> meta-analytic form (R's job, not the tool's)
Effect-size math (SE<->SD, CI->SD, median/IQR->mean/SD, Hedges g, Fisher z, ratio-CI
variances) was deliberately REMOVED from the tool -- there is no `figureExtractor.convert`
namespace, and calling it throws. The tool's authoritative output is calibrated DATA-unit
landmarks + dispersion TYPE + provenance: collect it with `getFigureDerivedRows()` /
`getFigureDerivedCsv()` and hand it to R (escalc / metafor), which computes every effect
size and variance. **Getting SD/SEM/CI wrong changes the variance by up to a factor of n**
-- so confirm dispersion type from the caption and flag `dispersion-type-uncertain` when
unknown; the tool refuses to treat an unknown dispersion type as variance-bearing.

## Output (characterization JSON — the tool's schema)
A concrete, validator-accepted example (every enum value below is from
`figureExtractor.charVocab()`; `scripts/test_api_docs.py` feeds this exact block through
the live validator, so it cannot drift):
```json
{
  "schemaVersion": 1, "confidence": 0.9, "source": "vision+caption", "panelCount": 1,
  "panels": [{
    "charType": "grouped-bar", "charTypeConfidence": 0.95,
    "dataProvenance": "primary",
    "extractionPriority": "high",
    "ignoredElements": ["legend", "significance-markers", "gridlines"],
    "axes": {
      "x": { "label": "Timepoint", "unit": "weeks", "scale": "categorical", "range": null, "ticks": ["0", "6", "12"] },
      "y": { "label": "HAM-D score", "unit": "points", "scale": "linear", "range": [0, 30], "ticks": [0, 10, 20, 30] },
      "y2": null
    },
    "series": [
      { "id": "s1", "label": "Placebo", "role": "control", "color": "#1a73e8",
        "encoding": "color", "labelSource": "legend", "n": 24, "nSource": "caption" },
      { "id": "s2", "label": "Psilocybin 25 mg", "role": "intervention", "color": "#dc2626",
        "encoding": "color", "labelSource": "legend", "n": 25, "nSource": "caption" }
    ],
    "statistics": {
      "encodes": ["mean", "dispersion"],
      "centralTendency": "mean",
      "dispersion": { "present": true, "type": "SEM", "typeConfidence": 0.9 },
      "sampleSizePerGroup": { "s1": 24, "s2": 25 }, "pValuesShown": []
    },
    "extractionPlan": { "method": "bar-endpoints", "requiresCalibration": true }
  }],
  "extractDecision": "extract",
  "extractReason": "Reports the target outcome (HAM-D) for the target comparison (drug vs placebo) as mean + SEM bars.",
  "flags": []
}
```
Series fields are a deliberate three-way split -- never collapse them into one name:
`id` is the join key that landmarks/marks bind to (REQUIRED, unique per panel); `label`
is the printed legend text as read from the image; `role` is the arm MEANING
(control/intervention/...), assigned by the agent from the caption and validated against
the vocab. `color` is a hex string (there is no `colorHex` field), `encoding` says how
series are visually distinguished, and `labelSource` says where the label text came from.
Dispersion present with `"type": "unknown"` requires the `dispersion-type-uncertain`
flag; more than one series with any of them unlabeled requires `series-unlabeled` --
the validator rejects the characterization otherwise.

## Notes
- Type from the image; dispersion type / n / units / decision from the caption + criteria.
- When the caption is absent, classify the type but set `dispersion.type:"unknown"`,
  `nSource:"unknown"`, `extractDecision:"skip"` (insufficient context), and say why.
- Multi-panel: one characterization per panel.
- Store with `setCharacterization`; interpreted numbers go in a sibling `extraction` object
  via `setExtraction`.
