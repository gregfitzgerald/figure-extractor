#!/usr/bin/env python3
"""Emit per-chart task files (rubric + article context, NO answers) for the eval agents,
in two conditions: with-context and image-only. Ground truth is never included."""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
CH = ROOT / "charts"
(ROOT / "tasks").mkdir(exist_ok=True)
(ROOT / "tasks_imgonly").mkdir(exist_ok=True)

VOCAB = ("bar, grouped-bar, stacked-bar, histogram, line, scatter, box, violin, forest, "
         "kaplan-meier, pie, heatmap, roc, bland-altman, funnel, dose-response, "
         "flow-diagram, table, micrograph, schematic, other, unknown")

RUBRIC = f"""You are applying the `figure-meta-extract` skill to ONE chart image.

Chart-type vocabulary (choose exactly one): {VOCAB}

Rules:
- The chart TYPE is read from the image.
- The dispersion TYPE (SD / SEM / CI95 / IQR / none / unknown), the group n, and the
  extract-vs-skip decision are read from the CAPTION + article context + meta-analysis
  criteria, NOT guessed from pixels. If no caption/context is given, set dispersionType
  and extractDecision to "unknown" and "skip" respectively, and say why.
- extractDecision is "extract" only if the figure reports the meta-analysis's target
  outcome for its target comparison in an extractable form; else "skip".
- Report visual difficulty flags you see: a LOG axis, a truncated/BROKEN axis, DUAL y-axes,
  many OVERLAPPING series, or a MULTI-PANEL composite (several sub-charts in one image).
- Prioritise ORIGINAL data: bar/line/histogram/scatter/box carry the study's own measurements
  (high priority). A forest/funnel plot usually re-summarizes OTHER studies (dataProvenance
  "derived", low priority) unless the article itself is that meta-analysis.
- Identify NON-DATA elements (legend, significance stars/brackets, gridlines, titles, panel
  letters, schematics, trend/reference lines) and list them in ignoredElements — they are NOT
  data and must not be counted as series or digitized."""

OUT_KEYS = """Write ONLY a JSON object (no prose) to the given output path with keys:
  charType         (one value from the vocabulary; for a multi-panel figure use "other")
  panelCount       (integer number of distinct sub-charts/panels in the image)
  dataProvenance   (primary = the study's own data | derived = a summary of OTHER studies,
                    e.g. a forest/funnel plot | na for schematics/non-data)
  extractionPriority (high|medium|low|none — original data high; derived summaries low)
  ignoredElements  (array of non-data elements present that must NOT be treated as data:
                    legend, significance-markers, gridlines, axis-ticks, title, panel-label,
                    schematic, image-inset, colorbar, trend-line, reference-line, annotation)
  dispersionType   (SD|SEM|CI95|IQR|range|none|unknown)
  extractDecision  (extract|skip)
  extractReason    (one sentence)
  flags            (array from: multi-panel, log-axis, broken-axis, dual-y-axis,
                    overlapping-series, no-legend, dispersion-type-uncertain, n-unknown;
                    include every one that applies, [] if none)
  confidence       (0..1)"""

for gt_path in sorted(CH.glob("*.json")):
    if gt_path.name == "manifest.json":
        continue
    gt = json.loads(gt_path.read_text())
    id = gt["id"]
    # WITH CONTEXT
    (ROOT / "tasks" / f"{id}.md").write_text(
        f"{RUBRIC}\n\n## Article context\nCaption: {gt['caption']}\n"
        f"Study context: {gt['articleContext']}\n\n## Meta-analysis criteria\n{gt['metaAnalysisCriteria']}\n\n{OUT_KEYS}\n")
    # IMAGE ONLY (no caption / context / criteria)
    (ROOT / "tasks_imgonly" / f"{id}.md").write_text(
        f"{RUBRIC}\n\n## Article context\n(NONE PROVIDED — you only have the image.)\n\n{OUT_KEYS}\n")

print("Wrote task files for", len(list(CH.glob('*.json'))) - 1, "charts (with-context + image-only).")
