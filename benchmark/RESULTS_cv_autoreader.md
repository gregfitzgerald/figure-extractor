# R-GT benchmark -- cv_autoreader vs R's authoritative descriptives

Engine: `py` (faithful port of the tool affine).  Charts scored: 10 (missing: bar_dodge_hard_11, bar_log_hard_09, box_clean_04, box_clean_05, line_clean_08, line_hard_13, scatter_clean_06, scatter_clean_07).

All errors are % vs the values R computed from the raw simulated data. The chart was
rendered FROM that data, so the ground truth is what R drew, not an eyeballed re-read.

## Headline channels (% error)

| channel | median | worst | n |
|---|---|---|---|
| central tendency (mean/median/point) | 0.45 | 1.05 | 10 |
| **dispersion (error-bar / IQR)** | **8.89** | **21.45** | 10 |

The dispersion row is the load-bearing one: a b% cap error -> ~2b% variance error ->
~sqrt(n) study mis-weighting in a meta-analysis.

## By tier (all channels)

| tier | median | worst | n |
|---|---|---|---|
| clean | 1.94 | 21.45 | 6 |
| hard | 2.99 | 16.21 | 14 |

## Per chart

| chart | tier | type | flags | errors (%) |
|---|---|---|---|---|
| bar_ci_clean_03 | clean | bar | - | central=0.60 dispersion=8.28 |
| bar_dots_hard_10 | hard | bar | raw-points-present | central=0.41 dispersion=15.05 |
| bar_sd_clean_01 | clean | bar | - | central=0.42 dispersion=3.28 |
| bar_sem_clean_02 | clean | bar | - | central=0.38 dispersion=21.45 |
| bar_sem_smallcap_12 | hard | bar | small-caps | central=0.34 dispersion=5.18 |
| panel_AB_15_pA | hard | bar | multi-panel | central=0.49 dispersion=8.12 |
| panel_AB_15_pB | hard | bar | multi-panel | central=1.05 dispersion=4.93 |
| panel_ABC_14_pA | hard | bar | multi-panel | central=0.59 dispersion=9.50 |
| panel_ABC_14_pB | hard | bar | multi-panel | central=0.51 dispersion=16.21 |
| panel_ABC_14_pC | hard | bar | multi-panel | central=0.39 dispersion=10.32 |