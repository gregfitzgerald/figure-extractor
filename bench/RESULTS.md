# Benchmark Cluster 1 -- automated chart reader vs. the manual ceiling

Charts scored: 12 / 12

Manual ceiling (geometry floor, exact clicks): ~0.00% on every chart, clean and hard (bench/floor.json).
The numbers below are the VISION READER's recovery error -- i.e. how much accuracy is lost to the
model picking points from the image rather than a human clicking them.

## By tier (all channels, % error)

| Tier | median | worst | n |
|---|---|---|---|
| clean | 0.42 | 2.85 | 10 |
| hard | 0.82 | 8.32 | 12 |

## Dispersion channel (the load-bearing, variance-determining quantity)

error-bar (SD) recovery: median 1.64%  worst 8.32%  (n=8)

## Per chart

| chart | tier | type | flags | errors (%) |
|---|---|---|---|---|
| clean_bar_00 | clean | bar | - | mean=0.43 dispersion=1.27 |
| clean_bar_01 | clean | bar | - | mean=0.26 dispersion=2.85 |
| clean_box_02 | clean | box | - | quartiles=0.08 |
| clean_box_03 | clean | box | - | quartiles=0.11 |
| clean_scatter_04 | clean | scatter | - | point=0.39 r=0.41 |
| clean_scatter_05 | clean | scatter | - | point=0.51 r=0.63 |
| hard_logbar_06 | hard | bar | log-axis | mean=0.44 dispersion=8.32 |
| hard_logbar_07 | hard | bar | log-axis | mean=0.27 dispersion=2.00 |
| hard_dotbar_08 | hard | bar | raw-points-present | mean=0.25 dispersion=2.50 |
| hard_dotbar_09 | hard | bar | raw-points-present | mean=0.40 dispersion=0.98 |
| hard_panel_10 | hard | bar | multi-panel | mean=2.61 dispersion=0.30 |
| hard_panel_11 | hard | bar | multi-panel | mean=1.14 dispersion=0.65 |

## What the reader actually was

The "vision reader" here is a **capable agent with CV tools**: each subagent solved its charts by writing
PIL/NumPy pixel-detection code (color-based landmark finding, axis-tick detection, least-squares log-axis
fits) rather than eyeballing. That is the realistic reader for this pipeline (the agent writes code), and it
is a **best case** -- the charts are clean synthetic renders whose flat fill colors make CV detection easy.

## Findings

1. **Central tendency is nearly free.** Bar means and box medians recover to ~0.1-0.6% on the clean tier
   and mostly <1% on the hard tier -- essentially the manual ceiling, with no human clicking. Even the
   worst mean error (multi-panel, 2.6%) is small.
2. **The dispersion channel is the weak point, exactly as predicted.** Error-bar (SD) recovery: median
   1.64%, worst **8.32%** (the log-axis chart). Because a b% error in the error-cap maps to ~2b% in
   variance (~sqrt(n) mis-weighting), an 8% cap error is a ~16% variance error -- material. This
   empirically confirms the design choice to **human-confirm dispersion at the B4 gate**.
3. **The hard tier degrades only modestly** (median 0.82% vs 0.42% clean). The agent-with-tools reader
   handled log axes, dot overlays, and multi-panel without catastrophe -- the failure modes that wreck a
   naive VLM (median 1.6% but max 43% in the earlier eyeballing eval) were largely neutralized by writing
   detection code. The residual cost concentrates in log-axis dispersion and multi-panel calibration.

## Verdict (build vs. buy)

- **Near-term: buy/reuse + agent, not a bespoke model yet.** An agent that drives CV extraction already
  gets within a few percent of the manual ceiling on synthetic charts *without a human clicking every
  point* -- so the immediate path is agent-driven digitization + human confirmation of the dispersion
  type/magnitude (the B4 gate), not an urgent trained detector. This matches the honest sequencing in
  VISION-MODEL-METHODOLOGY.md: don't build the model until a gap is proven.
- **The build case is specific and measurable, not general.** A specialized landmark detector earns its
  place in two places these numbers flag: (a) the **dispersion channel on hard axes** (log worst at 8.3%),
  and (b) **robustness on REAL journal figures**, where flat-color CV detection breaks (anti-aliasing,
  overlap, compression). These synthetic numbers are a ceiling; the **golden diff on real coded figures**
  is the experiment that converts "good on synthetic" into "justified" -- run that before training anything.
- **Bottom line for positioning:** figure-derived extraction is viable now via an agent, with dispersion as
  the human-gated risk -- consistent with the pipeline's whole design. The ML reader is a *later*,
  transfer-gap-driven investment, and its clearest target is the error-bar channel on real, messy figures.