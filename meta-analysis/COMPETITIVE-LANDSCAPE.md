# Competitive landscape and differentiation — automated meta-analysis (mid-2026)

Companion to `AUTOMATED-MA-VISION.md` (condensed positioning lives in §23). Merges two research passes: the general SR/MA + LLM landscape and the preclinical/animal-specific landscape. Sources cited inline as URLs. Caveat up front: most frontier systems are single-team 2026 preprints with self-reported numbers and no external replication — weight accordingly and re-verify any single figure before citing it in a protocol.

**Bottom line.** As of mid-2026 the headline "end-to-end, question → pooled `metafor` estimate → forest plot" has **stopped being a differentiator** — it is a crowded research theme (meta-pipe, LUMEN, AutoForest, Manalyzer) plus shipped products (otto-SR, Nested Knowledge). The pooling math is universally delegated to R `metafor`/`meta`, so "R does the inference" is **table stakes, not novelty**. What no one has assembled is the **combination**: figure-derived extraction routed into a study/arm-level multilevel model (`rma.mv`) with per-value provenance, a feasibility-proven preregistration gate, an append-only decision log, and preclinical/cross-species reach — in one pipeline. Each piece exists somewhere; together, nowhere. Position as "executed more reliably, transparently, and on harder data than the 2026 preprint cohort," not "first to do X."

---

## 1. The frontier: end-to-end agentic MA systems (2025–2026) — the direct analogs

- **meta-pipe** — the nearest conceptual competitor, and **Claude-Code-native like this project** (Opus reasoning + Haiku classification) across ~10 stages (PICO/protocol → search/dedup → screening → extraction → R stats → Quarto manuscript → GRADE → PRISMA/QA). Pooling via external R `meta`/`metafor`/`gemtc`/`netmeta` (incl. network MA). Has **5 mandatory human gates** and **reads effect estimates back from R files** to prevent manuscript hallucination (two ideas to steal). But: **cannot read figures/supplements/complex tables**, **article-level only**, **no preregistration/feasibility gate**, decision "log" is a CSV, **no preclinical**, and **zero validation** ("a system description, not a validation study"). License contradictory. https://arxiv.org/abs/2606.28363 · https://github.com/htlin222/meta-pipe
- **LUMEN** — the most validated open pipeline. 11 cost-routed agents; **REML + Knapp-Hartung via `metafor`**; novelty is **cost transparency** (~$22.65/review, full per-call JSON logs) and the finding that **multi-pass extraction is essential** (5.7× more poolable analyses). 100% directional agreement on 13 outcomes. But **plain random-effects (no `rma.mv`)**, no figures, no prereg, no preclinical, oversight **optional** (a disagreement queue). MIT. https://arxiv.org/html/2606.28362v1
- **otto-SR** — strongest *deployed* system; deliberately stops before pooling. **Beat dual-human baselines** (screening 96.7%/97.9%; extraction 93.1% vs 79.7% human) and **reproduced/updated 12 Cochrane reviews in ~2 days** (~12 work-years), finding ~54 missed studies and flipping significance in 3 — but only with dual human verification; humans pool. Commercial. https://www.ottosr.com/ · https://www.medrxiv.org/content/10.1101/2025.06.13.25329541v1
- **AutoForest** (IBM/UCL) — "first end-to-end system that generates publication-ready forest plots from papers." Docling parsing → Claude extraction → **arm-level** → pooled via R `meta` → forest + RoB. 32 forest plots / 18 Cochrane reviews (extraction ~82–83%; RoB ~63%). Arm-level, but figure handling is table parsing + human validation, **not chart digitization**. https://arxiv.org/abs/2606.02403
- **Manalyzer** — multimodal end-to-end MA that **does ingest figures/images and tables** (vision models / MinerU), with human checkpoints + decision logging — so "figures in the pipeline" is not unheard-of. But non-clinical domains, stops at extraction/analysis (no confirmed random-effects pool), no prereg, no license, calculated fields ~3%. https://arxiv.org/abs/2505.20310 · https://github.com/black-yt/Manalyzer
- **AutoMETA** (auditable-protocol DL pooling; OpenReview, no code: https://openreview.net/forum?id=81XyW0druM) and **MetaMind** (end-to-end Bayesian **network** MA; no code: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12904386/) — both signal the "auditable protocol" idea is in the air.

**Reality-check benchmarks (use to puncture hype, position on rigor):**
- **MetaSyn** — 442 Nature-portfolio MAs: even at 90.9% retrieval recall, **no end-to-end system includes >52.7% of eligible studies**. Screening, not retrieval, is the bottleneck. https://arxiv.org/html/2606.17041
- **MedMeta** — models **fail to reject factually incorrect evidence**, synthesizing coherent-but-false conclusions. https://arxiv.org/html/2605.09661v1

Takeaway: the race is real, fast, and uniformly immature (single-team preprints; one meaningfully validated; none trustworthy autonomously). The gates + decision-log + feasibility discipline are validated *by* these systems' failures.

---

## 2. Commercial / SaaS (three camps that rarely overlap)

**(A) AI literature assistants — discovery/extraction, none pool.** **Elicit** (closest to a real SR tool: ~138M papers, T/A + full-text screening, PRISMA flow with auditable exclusions, ~96% self-reported extraction; but **article-level, computes no statistics**, independent study found supporting-quote accuracy ~46%; free/$49/$169+, figures gated to Scale — https://elicit.com/solutions/systematic-review, independent https://www.cambridge.org/core/journals/research-synthesis-methods/article/C97DAEC70C3173A260F0B12E729E7250). **Consensus** (scoping/QA, no ES — https://consensus.app). **Scite.ai** (citation classification only). **LitLLM/LitSuggest** (related-work aids; LitLLM Apache-2.0 — https://arxiv.org/abs/2402.01788).

**(B) Screening/extraction SaaS — carry to extraction, hand off to R/RevMan/CMA.** **Covidence** (best-in-class dual screening + Cochrane RCT classifier; **no synthesis**; $339–907/yr). **DistillerSR** (the doc's "DistillSR": active learning ~96.6% recall, **Hierarchical Data Extraction** article→outcome→arm→timepoint, GenAI "Smart Evidence Extraction" for tables+text not figures, strong **audit trail / "100% traceable evidence"**; **no in-platform pooling**; its free Forest Plot Generator only plots supplied numbers — https://www.distillersr.com/products/distillersrai). **Rayyan** (screening + newer AI extract; article-level; freemium). **Silvi.ai** (markets "search → meta-analysis" but Analysis stage = data table + overview plots; in-tool pooling undocumented; provenance-linked extraction is a genuine strength; €0–59+). **Laser AI** (screening→extraction with "Full Traceability"; synthesis in sibling GRADEpro).

**(C) Platforms that DO pool.** **Nested Knowledge** (AutoLit + Synthesis) — **the one genuine full-pipeline commercial competitor**: search → screen → **arm-level** extraction → **native pooled effects + network MA + forest plots** (via `shukra`, a JS transcription of `meta`/`metafor`), audit trails + versioning. Gaps to beat: **no figure digitizer** (points to WebPlotDigitizer), **no SYRCLE/preclinical**, MA extraction still manual, **no multilevel `rma.mv` depth**, no prereg lock. Flagship validation paper **retracted June 2026**. $295–695/user/mo — https://about.nested-knowledge.com/docs/meta-analytical-methods/. **EPPI-Reviewer** (deepest ML + native MA, but forest plot "only displays the overall outcome effect… not the different treatment arms"). **Cochrane RevMan Web** (end-to-end for RCT reviews, protocol auto-uploads to **PROSPERO**, native FE/RE + forest/funnel; **no meta-regression/NMA/multilevel**). **JBI SUMARI** (true single-product end-to-end, native FE/RE, ~no ML, no multilevel). **Stats-only engines**: **CMA** (no multilevel), **JASP/metafor module** (free, **multilevel + cluster-robust RVE**), **Meta-Essentials**, **MetaInsight** — these *own* the synthesis math this pipeline delegates to R.

---

## 3. Open-source / academic — fractured along the pipeline seams

The canonical illustration of the fragmentation: the same lab built **Abstrackr** (screening) and **OpenMeta-Analyst/OpenMEE** (metafor synthesis) and they **never connect** — both now abandoned. https://github.com/bwallace/OpenMeta-analyst-

- **Screening:** **ASReview** (Utrecht, Apache-2.0) — maintained gold standard, active learning, ~95% workload reduction, Nature Machine Intelligence validation, decisions logged w/ user+timestamp; T/A only, article-level, no synthesis (https://github.com/asreview/asreview). Others: Colandr, CADIMA, FASTREAD, revtools (stale).
- **Extraction/classification NLP (Marshall/Wallace):** **RobotReviewer** (GPL-3; full-text RCT → PICO + Cochrane RoB with supporting sentences; no pooling), **Trialstreamer** (living RCT DB; **excludes animals**), **robotsearch**, the **EBM-NLP** PICO-span lineage, **ExaCT** (21 trial features; not open).
- **Closest open thing to this project's DNA:** **`hyesunyun/llm-meta-analysis`** (Wallace group, Apache-2.0) — LLMs extract **arm-level ICO numerics** then hand to external metafor/statsmodels (reproduced a remdesivir MA). Good on 2×2, poor on continuous. Related: **Tomo-for-lab/automating-DE** (GPT-4o, SE→SD/CI→SD conversions), **OpenExtract** (LUMC; numeric + figure processing + extraction-decision tracking). https://github.com/hyesunyun/llm-meta-analysis · https://arxiv.org/html/2405.01686v2
- **The R synthesis ecosystem this pipeline builds on:** `metafor` (`escalc` + `rma.mv` multilevel/multivariate/network — docs literally describe nesting estimates from "the same paper, lab, research group, or species"), `meta`, `clubSandwich` (CR2 RVE), `robumeta`, `metaSEM`, `dmetar`, `orchaRd` (multilevel-MA viz/marginal means), `netmeta`, `PRISMA2020`. **The multilevel statistics are a solved, commodity problem here.** https://wviechtb.github.io/metafor/reference/rma.mv.html
- **Figure digitizers (standalone only):** **metaDigitise** (R, GPL-3) — closest MA-purpose competitor, reproducible interactive extraction, auto-writes calibration to a `caldat` folder, computes mean/SD; **metagear** (R) — digitization + screening + PRISMA in one; **juicr** (embeds reproducible HTML records); **WebPlotDigitizer** (incumbent; cloud "AI Assist" closed); **Engauge**; **PlotExtract** (2025; Claude 3.5 vision → plot-code → verify, >90%). Narrow adjacent: **KM/IPD reconstruction** (IPDfromKM, SurvdigitizeR, KM-GPT). **None wired into a pooling pipeline.** https://github.com/daniel1noble/metaDigitise · https://arxiv.org/abs/2503.12326
- **metaBUS** — the study-level exemplar to study: ~1.1M correlations from ~15,000 I-O psychology articles, in-browser **three-level random-effects MA** (effects nested by sample then article, REML) with **per-value provenance** (N, reliability, country). Proves one-article→many-effects + provenance + instant pooling works — but closed, scope-locked, no figures, no prereg, no audit log. https://journals.sagepub.com/doi/full/10.1177/2515245919882693

---

## 4. Preclinical / animal-specific (this pipeline's home turf)

- **SyRF** (Systematic Review Facility; CAMARADES/Edinburgh, Macleod/Sena; NC3Rs-funded; RRID:SCR_018907) — the dominant preclinical SR platform. Reference import + **blinded dual screening + majority-vote reconciliation**; on-request ML screening; custom annotation at Study→Cohort→Experiment→Outcome (so **arm/experiment-level**); outcome-data extraction; **figure digitization via Graph2Data** ("faster, higher inter-rater reliability than manual"); a per-reviewer **audit trail**. **Stops at extraction** — hands a table to a *separate* R/Shiny **Meta-Analysis App** (last release 2019) or bespoke `metafor`. Bahor et al. 2021, BMJ Open Science, https://pmc.ncbi.nlm.nih.gov/articles/PMC8647599/ · user guide https://camaradesuk.github.io/syrf_userguide/. As of June 2020: 1,251 researchers, 588 projects, ~2M citations.
- **CAMARADES toolchain:** **ASySD** (automated search dedup; R + Shiny), **Meta-Analysis App** (ES + stratified MA + meta-regression + trim-and-fill + Egger), **Graph2Data** (figure digitizer). Method (Vesterinen et al. 2014, J Neurosci Methods, https://pubmed.ncbi.nlm.nih.gov/24099992/): R + random-effects DL, NMD/SMD/MD, **multiple comparisons handled by nesting outcomes**, **shared control handled by the control-splitting rule** n′c = nc ÷ (#treatment groups) — **manual analyst conventions, not automated**. Full nesting via `rma.mv`.
- **SYRCLE RoB tool** (Hooijmans et al. 2014, BMC MRM 14:43 — https://pmc.ncbi.nlm.nih.gov/articles/PMC4230647/) — 10-item low/high/unclear checklist adding animal-specific items (baseline characteristics, random housing, random outcome assessment). A checklist, **not software**.
- **SYRCLE automation — partial, item-limited, corpus-level, no full 10-item verdict:** **pre-rob** (Wang et al. 2022; 5 items; welfare F1 91.5% but **exclusions only 46.6%**; corpus-level, not per-paper — https://onlinelibrary.wiley.com/doi/full/10.1002/jrsm.1533), **Auto-STEED** (dict+regex species/model/randomization/blinding), **SciScore** (commercial, journal-facing rigor score; blinding/power weakest), **RobotReviewer** (RCT-only, no SYRCLE).
- **Preclinical screening ML:** Bannach-Brown et al. 2019 (Syst Rev 8:23) — the algorithm SyRF exposes; found a share of apparent machine "errors" were actually **human** errors. https://pmc.ncbi.nlm.nih.gov/articles/PMC6334440/
- **Preclinical preregistration:** **PROSPERO4animals** (SR protocols for animal studies; Bannach-Brown/Wever et al. 2024 — https://pubmed.ncbi.nlm.nih.gov/38267888/), **preclinicaltrials.eu** (primary experiments), **SyRF Protocol Registry** — all **static, separate registrations, not linked to the extraction tool** with a live decision log.

Preclinical whitespace: end-to-end synthesis at arm level + *automated* shared-control handling + integrated preregistration + an append-only, protocol-linked decision log — unclaimed; and numeric extraction from text/figures is the acknowledged manual bottleneck.

---

## 5. Research threads (evidence for the design choices)

- **Screening** is mature: pooled sensitivity ~0.80–0.92 (Kim 2025) but high-recall/low-precision with a false-negative tail, and apparent accuracy **collapses after chance/imbalance correction** (Khraisha 2024, https://onlinelibrary.wiley.com/doi/10.1002/jrsm.1715). No one claims autonomy.
- **Numeric extraction — the crux, and the strongest evidence for gates/provenance.** Categorical ~96% (Gartlehner/Claude-2), but forest-plot numbers are far worse: GPT-4 exact-match **65.5% binary / 48.7% continuous** (Yun/Wallace, https://arxiv.org/abs/2405.01686); full 6-field meta-analytic tuples **collapse to F1 ≈ 0** as arity grows (Tan & D'Souza 2026, https://arxiv.org/abs/2602.10881). Human gold standards themselves err up to 63%.
- **Risk of bias** under-solved: signaling-question level ~83%, overall verdicts weak (κ ~0.2–0.5). **Design lesson: elicit signaling answers, then apply the RoB algorithm deterministically** — don't ask the LLM for the verdict (https://www.jmir.org/2025/1/e70450).
- **Living systematic reviews** are operational but human-driven; only Trialstreamer runs autonomously, abstract-level only.
- **Automated / feasibility-proven preregistration — near-total whitespace.** Only **Virtuous Machines** (2025) demonstrates auto-preregistration + a-priori power, and only for *primary* psychology studies (https://arxiv.org/abs/2508.13421). **RegCheck** is post-hoc deviation detection. MA power sims exist only as manual R tooling (POMADE, metapower, dmetar). **No system couples an auto-drafted MA protocol to a simulated feasibility/power go/no-go gate before locking.**

---

## 6. Scorecard: who covers each differentiator

| Differentiator | State of the art | Verdict |
|---|---|---|
| End-to-end → `metafor` pooling | meta-pipe, LUMEN, AutoForest, otto-SR, Nested Knowledge, EPPI-R, RevMan, SUMARI | **Occupied.** Table stakes. |
| R does inference; tools don't compute ES | LUMEN, meta-pipe, AutoForest, llm-meta-analysis | **Standard.** Everyone delegates to R. |
| Staged human-in-the-loop gates | meta-pipe (5 mandatory), otto-SR (dual human), LUMEN (optional queue) | **Partly occupied.** Mandatory gates bound to specific risks are stronger than queues. |
| Append-only decision-log auditability | Real audit logs live in tools that *don't* pool (Elicit, DistillerSR, SyRF); poolers have partial CSV/JSON | **Thin where it counts.** Append-only ledger *paired with pooling* is ~unclaimed. |
| Study/arm-level multilevel (`rma.mv`) with provenance | Stats solved; end-to-end only metaBUS (closed) & SyRF (external pooling); AutoForest arm-level but plain pooling | **Genuine whitespace + hard.** No open LLM pipeline outputs `rma.mv` with arm/study provenance. |
| Figure-extraction-as-flagged-fallback | Digitizers standalone; Manalyzer ingests figures but doesn't flag/pool cleanly | **Largely open.** Figure-derived *permanently flagged → sensitivity analysis* is unclaimed. |
| Feasibility-proven preregistration | Nobody for MA; Virtuous Machines (primary studies) adjacent; RegCheck post-hoc | **Cleanest whitespace.** Genuinely novel for MA. |
| Preclinical / cross-species MA | SyRF (non-LLM, external pooling) + SYRCLE; every LLM pooler is clinical-RCT-only | **Whitespace for automation.** |

---

## 7. Best ideas worth adapting

1. **Read effect estimates back from R output files into the report/manuscript** (meta-pipe) — an anti-hallucination guarantee that fits "R is authoritative."
2. **Elicit signaling-question answers, then apply the RoB/SYRCLE algorithm deterministically** (Claude 3.5 RoB2 study) — don't ask the model for a domain verdict.
3. **Multi-pass / dual-model extraction with an arbiter + per-phase cost logging** (LUMEN) — single-pass yielded ~6 poolable analyses vs ~34 for multi-pass; show a budget before committing at 10k–30k records.
4. **Reproducible calibration artifacts for figure extraction** (metaDigitise `caldat`; juicr HTML records) — persist axis calibration + clicked points so a human can re-verify a figure-derived value. Operationalizes "verified, not laundered."
5. **Disagreement-ranked review queue** (LUMEN) + **dual-human-verify-before-pooling** (otto-SR) — prioritize human attention by model disagreement so gates scale.
6. **Prior-MA seed set as a recall/accuracy oracle** (matches §17b) — the metaBUS-style validation target the preprint cohort lacks.
7. **Publish honest cost + accuracy numbers** (LUMEN's whole contribution) — the field is starved for validated, transparent metrics; providing them is itself a differentiator.

---

## 8. Differentiation and positioning

**Do NOT lead with (already occupied):** "automated end-to-end MA to a `metafor` estimate" (meta-pipe, LUMEN, AutoForest, otto-SR, Nested Knowledge — and meta-pipe is *also* Claude-Code-powered, so this invites "how are you different from meta-pipe?"); "R does the inference" (universal); bare "human-in-the-loop" (everyone says it); bare "decision log / auditability" (Elicit, DistillerSR, Silvi, ASReview all advertise it).

**Genuinely novel and defensible:**
- **Feasibility-proven preregistration** — no MA system makes you run real searches, recover positive controls, prove the schema on real extractions, and simulate power on the *actual moderator models* before it will let you lock. **The single strongest, cleanest wedge.**
- **The full combination** — figure-derived (permanently flagged) + study/arm-level `rma.mv` + per-value provenance + append-only ledger + preclinical/cross-species + feasibility-proven prereg, in one pipeline ending in a real multilevel RVE model. Every capability exists somewhere; no tool combines them.
- **Study-level modeling that actually reaches `rma.mv` with provenance** — the stats are commodity, but no LLM pipeline populates a three-level model with arm/study provenance, precisely because multi-row numeric extraction is the documented failure point (F1→0). If the golden diff shows you do it reliably, that's a moat.
- **Figure-derived-as-flagged-fallback carried through to a sensitivity analysis** — Manalyzer reads figures, but nobody flags figure-derived values persistently and runs the figure-vs-text sensitivity analysis.

**Uncomfortable truths:** meta-pipe is the closest analog and shares the stack — you must name the delta in one sentence (feasibility-proven prereg + study-level provenance + figures + preclinical, all validated). Nested Knowledge already ships the full commercial pipeline with arm-level extraction + native pooling — differentiate specifically on the four things it lacks (figures, preclinical/SYRCLE, multilevel depth, prereg). And the field's own benchmarks (MetaSyn ≤52.7% inclusion; numeric F1→0; MedMeta false-evidence) mean *nobody* has trustworthy autonomous MA — position on **rigor and honesty**, which the preprint cohort conspicuously lacks.

**Concrete positioning recommendations:**
1. **Lead with "feasibility-proven preregistration for meta-analysis," not "automated MA."** The one thing no competitor does; reframes the pitch from "faster review" to "un-gameable, pre-committed rigor"; the natural Metascience Observatory headline. Ship the lock-gate as the flagship demo.
2. **Own "study-level, figure-aware, provenance-first extraction" — and prove it with the golden diff.** Contrast explicitly: "meta-pipe/LUMEN extract article-level values into plain random-effects and can't read figures; we extract arm/study-level (incl. figure-derived, flagged) into three-level `rma.mv` + CR2 RVE with provenance on every cell," backed by a measured residual per-field error rate against the 155/323 coded rows.
3. **Position against named competitors on a capability grid, not vibes** — a one-slide matrix (meta-pipe / LUMEN / otto-SR / Nested Knowledge / Elicit vs. you) across the eight axes; cite meta-pipe's zero validation and Nested Knowledge's retracted paper — compete on validated rigor.
4. **Make the append-only decision log + provenance a first-class exportable artifact, paired with pooling** — frame as "team-grade inter-rater reliability + audit for a solo reviewer" (the §22b angle): the agent is a *measured* second rater (golden-diff κ), every decision immutable, provenance carried into the final model.
5. **Claim the two hardest niches deliberately: preclinical/cross-species and figure-derived data** — where the entire LLM-pooler field is empty (clinical-RCT-only) and where the dissertation is the proof of concept.
