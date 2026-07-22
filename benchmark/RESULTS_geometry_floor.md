# R-GT benchmark -- geometry_floor vs R's authoritative descriptives

Engine: `py` (faithful port of the tool affine).  Charts scored: 18.

All errors are % vs the values R computed from the raw simulated data. The chart was
rendered FROM that data, so the ground truth is what R drew, not an eyeballed re-read.

## Headline channels (% error)

| channel | median | worst | n |
|---|---|---|---|
| central tendency (mean/median/point) | 0.00 | 0.00 | 18 |
| **dispersion (error-bar / IQR)** | **0.00** | **0.00** | 16 |

The dispersion row is the load-bearing one: a b% cap error -> ~2b% variance error ->
~sqrt(n) study mis-weighting in a meta-analysis.

## By tier (all channels)

| tier | median | worst | n |
|---|---|---|---|
| clean | 0.00 | 0.00 | 20 |
| hard | 0.00 | 0.00 | 18 |

## Per chart

| chart | tier | type | flags | errors (%) |
|---|---|---|---|---|
| bar_ci_clean_03 | clean | bar | - | central=0.00 dispersion=0.00 |
| bar_dodge_hard_11 | hard | bar | overlapping-series | central=0.00 dispersion=0.00 |
| bar_dots_hard_10 | hard | bar | raw-points-present | central=0.00 dispersion=0.00 |
| bar_log_hard_09 | hard | bar | log-axis | central=0.00 dispersion=0.00 |
| bar_sd_clean_01 | clean | bar | - | central=0.00 dispersion=0.00 |
| bar_sem_clean_02 | clean | bar | - | central=0.00 dispersion=0.00 |
| bar_sem_smallcap_12 | hard | bar | small-caps | central=0.00 dispersion=0.00 |
| box_clean_04 | clean | box | - | central=0.00 dispersion=0.00 |
| box_clean_05 | clean | box | - | central=0.00 dispersion=0.00 |
| line_clean_08 | clean | line | multi-series | central=0.00 dispersion=0.00 |
| line_hard_13 | clean | line | multi-series | central=0.00 dispersion=0.00 |
| panel_AB_15_pA | hard | bar | multi-panel | central=0.00 dispersion=0.00 |
| panel_AB_15_pB | hard | bar | multi-panel | central=0.00 dispersion=0.00 |
| panel_ABC_14_pA | hard | bar | multi-panel | central=0.00 dispersion=0.00 |
| panel_ABC_14_pB | hard | bar | multi-panel | central=0.00 dispersion=0.00 |
| panel_ABC_14_pC | hard | bar | multi-panel | central=0.00 dispersion=0.00 |
| scatter_clean_06 | clean | scatter | - | point=0.00 r=0.00 slope=0.00 |
| scatter_clean_07 | clean | scatter | - | point=0.00 r=0.00 slope=0.00 |