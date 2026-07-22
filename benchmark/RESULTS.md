# R-GT figure-extraction benchmark -- results

R is the authoritative ground-truth engine: it simulates the raw data, computes the
full descriptives, and renders each chart FROM that data. Every tool is scored on how
close it gets to **R's descriptives**, with the **dispersion (error-bar) channel** as a
first-class, separately-reported headline. Corpus: 18 GT bundles (bar/box/scatter/line +
multi-panel), ggplot2 engine, verified GT pixels (detected ink vs R-GT: median 0.44px).

## Tool comparison -- % error vs R (central tendency | dispersion)

| tool | central median | central worst | **dispersion median** | **dispersion worst** |
|---|---|---|---|---|
| geometry_floor (exact pixels) | 0.00 | 0.00 | **0.00** | **0.00** |
| human_floor (0.5px click jitter) | 0.22 | 1.32 | **2.09** | **18.70** |
| human_floor (1.0px click jitter) | 0.44 | 2.67 | **4.15** | **37.34** |
| human_floor (2.0px click jitter) | 0.89 | 5.46 | **8.23** | **74.42** |
| cv_autoreader (bars, n=10) | 0.45 | 1.05 | **8.89** | **21.45** |
| vision (agent read, n=1) | 1.17 | 1.17 | **8.20** | **8.20** |

## Reading the table

- **Central tendency is nearly free** for every tool (<=1% median) -- bar means and box
  medians recover trivially once the axes are calibrated.
- **Dispersion is the load-bearing failure.** Even the *exact-pixel* ceiling is 0% only
  because pixels are perfect; add realistic 1px click jitter and the dispersion channel
  jumps to ~4% median / ~27% worst, while central tendency stays ~0.5%. A real CV reader
  leaves ~9% median dispersion error, worst on short SEM caps and dot-overlay bars.
- The framing: a b% cap error -> ~2b% variance error -> ~sqrt(n) study mis-weighting.
  The dispersion column is therefore the number a meta-analyst must care about, and the
  channel a specialist detector should target.

- The `vision` row is a genuine model-in-the-loop read (bar_sd_clean_01); it lands at the same
  place -- central ~1%, dispersion ~8% -- confirming the pattern with a real reader.

## Per-tool detail

See `RESULTS_geometry_floor.md`, `RESULTS_cv_autoreader.md` for per-chart tables
(regenerate with `python3 benchmark/harness/score.py --tool <name>`).