# Tool dossier: validation evidence, runnability, and a benchmark plan

Companion to `COMPETITIVE-LANDSCAPE.md` and `HISTORY-OF-AUTOMATING-MA.md`. For each tool: published validation, how to run it, and a "benchmarkable in this env?" verdict (Linux/WSL, R 4.1, Python 3.10+uv, Node 24; NO GPU, NO .NET, NO Windows).

Verdict legend: `YES` runs here · `NEEDS-GPU` · `NEEDS-API-KEY` · `WINDOWS-ONLY` · `COMMERCIAL-NO-CODE` · `HEAVY-MODELS` (large download / legacy stack).

## Part 1 — Figure/chart digitizers (the build-vs-buy decision)

| Tool | Validation (best evidence) | Verdict | Repo |
|---|---|---|---|
| **WebPlotDigitizer** | Most-validated. Drevon 2017 (3,596 pts/168 series, high ICR & validity, DOI 10.1177/0145445516673998); Burda 2017 (ICC>0.95, % err 0.23–30%, 10.1002/jrsm.1232); Kadić 2016 (faster + higher IRR than manual, 10.1016/j.jclinepi.2016.08.002) | **YES** (offline web/Electron; manual GUI) | automeris-io/WebPlotDigitizer |
| **Graph2Data** | No standalone study; only SyRF trial Bahor 2021 (~5:52 faster, **29% more accurate than manual**, 10.1136/bmjos-2020-100103). Architecturally a .NET wrapper around pdf.js + WebPlotDigitizer → accuracy ≈ WPD | **WINDOWS-ONLY** (.NET; not runnable here) | EPPI-Centre/Graph2Data |
| **metaDigitise** | Pick 2019 (software/reproducibility paper, 10.1111/2041-210X.13118); auto mean/SD/n; reproducible `caldat` record | **YES** (R; interactive, needs display) | daniel1noble/metaDigitise |
| **metagear** | Lajeunesse 2016 (10.1111/2041-210X.12472); screening + figure extraction + ES prep | **YES** (R + Tcl/Tk + Bioconductor EBImage) | cran/metagear |
| **juicr** | metagear successor; embeds HTML record of every clicked point (reproducibility) | **YES** (R + EBImage + Tcl/Tk) | mjlajeunesse/juicr |
| **Engauge** | Long-standing baseline; no formal accuracy paper | **YES** (Qt GUI, needs display) | markummitchell/engauge-digitizer |
| **PlotExtract** | Polak & Morgan 2025 (arXiv 2503.12326): >90% precision, ~90% recall, ~5% pos error **on extractable plots** (multimodal LLM, zero-shot). The ready-made "LLM chart reader" comparator | **NEEDS-API-KEY** | none (figshare data) |
| **ChartOCR / DeepRule** | Luo 2021 WACV (10.1109/WACV48630.2021.00196); strong on clean synthetic, weak on real multi-panel (the transfer gap) | **NEEDS-GPU** + HEAVY-MODELS | soap117/DeepRule |
| **IPDfromKM** | Guyot 2012 (no material systematic error, 10.1186/1471-2288-12-9); Liu 2021 R pkg (10.1186/s12874-021-01308-8) | **YES** (R, CRAN) | CRAN |

**Build-vs-buy takeaway:** the digitizer accuracy ceiling for *clean* charts is already high and validated (WPD ICC>0.95), and metaDigitise/juicr already give the reproducible-calibration provenance you want. **A bespoke ML reader is justified only where those tools require manual clicking on *hard* real panels** (multi-panel, log/broken axes, dot overlays). PlotExtract (>90% on extractable plots) is the exact comparator to test that gap. Graph2Data is a dead end to run and adds no accuracy over WPD.

## Part 2 — End-to-end agentic pipelines

| Tool | Validation | Verdict | Repo |
|---|---|---|---|
| **meta-pipe** | None (arXiv 2606.28363, system description). Steal: 5 mandatory gates; read estimates back from R | **NEEDS-API-KEY** (uv Py3.12 + R 4.2 + Quarto) | htlin222/meta-pipe |
| **LUMEN** | Most-validated open (arXiv 2606.28362): 100% directional agreement/13 outcomes; $22.65/review; multi-pass = 5.7× more poolable; metafor REML+HK | **NEEDS-API-KEY** (worth running as reference) | YHHuan/LUMEN |
| **AutoForest** | arXiv 2606.02403; 32 forest plots/18 Cochrane; ~82–83% extraction, ~63% RoB; arm-level; pools via R meta; table-parsing not chart digitizing | **NEEDS-API-KEY / no public repo** | none |
| **Manalyzer** | arXiv 2505.20310; multimodal (parses figures+tables); non-clinical; calculated fields ~3% | **NEEDS-API-KEY** | black-yt/Manalyzer |
| **otto-SR** | Best deployed: screening 96.7%/97.9%, extraction 93.1% vs 79.7% human; 12 Cochrane reviews in ~2 days (10.1101/2025.06.13.25329541) | **COMMERCIAL-NO-CODE** | none |
| **AutoMETA** | Auditable-protocol DL pooling; OpenReview 81XyW0druM; no code | **COMMERCIAL-NO-CODE** | none |
| **MetaMind** | Multi-agent Bayesian NMA; 100% on limited PICO set (10.1371/journal.pone.0342895) | **NEEDS-API-KEY / no repo** | none |

## Part 3 — Screening / extraction

| Tool | Validation | Verdict | Repo |
|---|---|---|---|
| **ASReview** | van de Schoot 2021, Nat Mach Intell (~95% workload reduction; 10.1038/s42256-020-00287-7) | **YES** (pip, CPU) | asreview/asreview |
| **Auto-STEED** | Wang/Ineichen 2024 (sens>85%, spec>80%, F>0.9; 10.1371/journal.pone.0311358); pure R dict+regex | **YES** (R, light) | Ineichen-Group/Auto-STEED |
| **ASySD** | Hair 2023 BMC Biology (10.1186/s12915-023-01686-z); dedup | **YES** (R + Shiny) | camaradesuk/ASySD |
| **pre-rob** | Wang 2022 (welfare F1 91.5%, exclusions 46.6%; 10.1002/jrsm.1533); BERT | **HEAVY-MODELS** (GPU rec.) | qianyingw/pre-rob |
| **RobotReviewer** | Marshall 2016 JAMIA (10.1093/jamia/ocv044); RoB1 + PICO | **HEAVY-MODELS** (Py3.6+TF1.12+Grobid+SciBERT; Docker) | ijmarshall/robotreviewer |
| **Trialstreamer** | Marshall 2020 JAMIA (10.1093/jamia/ocaa163); excludes animals | **HEAVY-MODELS** (server/DB) | ijmarshall/trialstreamer |
| **llm-meta-analysis** | Yun 2024 MLHC (arXiv 2405.01686); binary ~65.5%, continuous ~48.7% | **NEEDS-API-KEY** | hyesunyun/llm-meta-analysis |
| **OpenMeta-Analyst** | Wallace 2012 JSS (10.18637/jss.v049.i05); R-backed GUI | legacy (Py2.7+GUI) → **skip**; use metafor | bwallace/OpenMeta-analyst- |

## Part 4 — Synthesis (reference implementations = the ground truth)

| Tool | Reference | Verdict |
|---|---|---|
| **metafor** | Viechtbauer 2010 JSS (10.18637/jss.v036.i03); escalc + rma.mv | **YES** (R) |
| **meta** | Balduzzi/Schwarzer 2019 (10.1136/ebmental-2019-300117); engine behind LUMEN/AutoForest | **YES** (R) |
| **clubSandwich** | Pustejovsky & Tipton 2018 (10.1080/07350015.2016.1247004); CR2 RVE | **YES** (R) |

## Benchmark plan — three runnable clusters

**Cluster 1 — Figure digitizers (the build/buy call).** Shared task: ~30–50 synthetic bar/box/scatter/line charts with known GT + the panels from the 8 golden-diff articles; feed the *same* images to each. Metric: per-point % error + ICC vs true mean/SD; time-per-figure. Runnable: WPD, metaDigitise, metagear/juicr, Engauge, IPDfromKM(+KM), and a PlotExtract-style LLM reader (NEEDS-API-KEY) as the **comparator that answers "should I build an ML reader?"** ChartOCR/Graph2Data: cite published numbers only. *Decision: if an LLM-vision reader can't beat WPD's ICC>0.95 on clean charts but wins on the hard real panels where WPD needs manual clicks, that's the build case.*

**Cluster 2 — Screening/dedup/extraction.** Shared task: a labeled screening corpus (your dissertation's include/exclude set, or a public SYNERGY/CAMARADES set). Metric: WSS@95%, recall, κ. Runnable: ASReview (primary), Auto-STEED (preclinical params), ASySD (dedup). pre-rob/RobotReviewer only with a GPU/Docker box.

**Cluster 3 — Synthesis correctness.** Shared task: regenerate a slice of `rodent_main.rds` / a known Cochrane forest. Metric: agreement of pooled estimate/CI/τ²/I². Runnable: metafor+clubSandwich (ground truth), meta (cross-check).

**Compare-on-paper-only:** meta-pipe, LUMEN, AutoForest, Manalyzer, MetaMind, llm-meta-analysis (NEEDS-API-KEY); otto-SR, AutoMETA (COMMERCIAL); ChartOCR (GPU). **LUMEN is the one end-to-end pipeline worth an actual reference run** if API keys are supplied.
