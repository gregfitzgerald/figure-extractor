# Automating meta-analysis — design (v3), applied to the EE→Cognition dissertation MA

How the staged, human-gated pipeline would be applied to your own work (`GSF-dissertation-meta-analysis`). Your completed dissertation MA is the *worked example and the acceptance test*: the pipeline is "done" only when it could have produced that MA — cross-species (rodent + human), 115-/134-column raw schemas, three-level `rma.mv` + RVE (CR2) in metafor, VCV at an assumed within-cluster r, Morris pre-post effect sizes, the RLS dose construct, and the lnCVR variability strand — with a human in the loop at the load-bearing steps and every decision on record.

**This is v2, revised after an adversarial review.** The review's core finding: v1 located its hard parts in the wrong place — it treated as solved (a single schema "spine," a Python effect-size core, "RVE clustered by article," a power sim "at predicted k") exactly the things your dissertation shows are hard, plural, and assumption-laden. v2 moves those corrections to the center. Section 0 summarizes what changed; Section 15 traces every original requirement *and* every review point to where it now lives.

**v3 adds your reading-pass feedback (§16–§22)** and situates this pipeline as the **meta-analysis module of the broader Metascience Observatory project**. New sections: §16 hypothesis specification + variable taxonomy (descriptive/primary/exploratory); §17 the prior-work (meta-meta-analysis) table + prior-MA-author outreach; §18 effect-size metric selection + commensurability; §19 a synthetic-ground-truth chart-understanding model; §20 primary-author outreach to resolve extraction ambiguities; §21 outputs & dissemination (RMarkdown notebooks, interactive charts, publicity); §22 preregistration publishing + collaboration/inter-rater reliability.

---

## 0. What changed after review (read this first)

| Review finding (v1 was over-optimistic about…) | Correction in v2 |
|---|---|
| One schema "spine" | **Two typed schemas** (rodent/human) with different load-bearing machinery; §2, §6a |
| `metalib.py` presented as the math core | **Retired from inference entirely.** R (`escalc`/Morris/`rma.mv`) does all effect sizes; §7 |
| Effect sign assumed positive = better | **`Direction` is a first-class field**; sign-flip is mandatory and logged; §6a, §7 |
| Human half ignored | **Morris `dppc2` pre-post SMD** is a required effect-size family; §7 |
| Dependency = "RVE clustered by article" | **Three-level nesting** (`Study_Arm_ID / Test_ID / Outcome_ID`) + multi-arm VIF + VCV; §6a, §7 |
| r = 0.7 treated as data | **r is an assumption, swept {0.5,0.7,0.9}** in every model and the sim; §7, §8 |
| RVE unspecified | **Pinned: clubSandwich CR2 + Satterthwaite**; cluster-count floor named; §7 |
| Power sim "at predicted k" | **Simulates the actual moderator/interaction models**, not the intercept; §8 |
| RLS extraction assumed tractable | Named as **the highest-risk extraction**; validated by golden diff before trusted; §6b, §10 |
| Feasibility-proven prereg == un-gameable | **Named tension**; walled-off pilot rule; OTS proves time-not-blindness; §12 |
| Control-recall = "found the field" | Reframed as a **floor**, paired with a miss estimate; §4 A3 |
| Scale/retrieval ignored | **New section** on throughput, cost, paywalls, author-contact; §11 |
| No accuracy measurement | **Golden diff against your coded CSVs is now step 1**, not optional; §10, §14 |
| Missing analyses | **lnRR/lnCVR (H4), pub-bias via article-level aggregation, sensitivity family** added; §7, §9 |

---

## 1. Your MA, read back to you (the target we must be able to reproduce)

| Piece | What's there | Design consequence |
|---|---|---|
| Design | Cross-species rodent + human, combined for a **species×dose interaction** | The hardest estimand; drives the power-sim rewrite (§8) |
| Unit hierarchy | `Article_ID → Study_ID → Comparison_ID → Test_ID → Outcome_ID → Arm_Number` (+ `Study_Arm_ID`) | A **three-level** random structure, not article→study→arm; the schema must carry all levels |
| Dose construct | **RLS 0–11**, enrichment decomposed into 11 components + quantities → `RLS_Differential` | Object-level, invented-by-you, lives in methods prose; highest extraction risk (§6b) |
| Direction | Per-outcome `Direction` (+1 better / −1 worse) | Latency/errors are lower-is-better; **sign flips are mandatory**, else effects cancel |
| Raw | `rodent_data.csv` (115), `human_data.csv` (134) — differ on load-bearing parts | **Two schemas**, not one; human needs pre/post, adherence, RoB2 |
| Effect sizes | `Hedges_g_corrected` (rodent between-group; human **Morris dppc2** change-score), `vi_adjusted_multiarm`, `VIF_multiarm` | Two effect-size families + a multi-arm variance correction |
| Processed | `rodent_main.rds`, `human_main.rds`, `VCV_*.rds` (impute_covariance_matrix, r=0.7) | metafor-ready; r is a swept assumption |
| Analysis | `CONSOLIDATED_ANALYSIS.Rmd`: three-level `rma.mv` + `robust`/`coef_test(CR2)`; I²/τ²; H1 dose, H2 components, H3 domains, **H4 lnCVR**; pub-bias after `agg_study` article-level aggregation | The execution template; R is non-negotiable |
| Provenance | `Data_Source` (text/table/figure/supplement), `Data_Extraction_Method`, `Morris_Method_Required`, `sensitivity_*` family | Where figure-extractor slots in (and stays flagged); the sensitivity set must be pre-enumerated |

The toy BDNF pipeline in this repo is a thin Phase-B skeleton that validates the *easy* path (a mean off a bar chart). It proves nothing about the parts that would actually sink the vision (RLS, Morris, nesting, Direction). v2 fixes the priority order accordingly (§14).

---

## 2. Design principle (the three pillars, corrected)

> Agent power in MA rests on **(a)** rich extension rules/criteria as *worked* skills — for screening *and* extraction; **(b)** well-specified data structure(s) as the spine — the agent's target and the human's verification surface at once; **(c)** figure-extraction as the *visual-only* fallback, permanently flagged.

Two corrections from review: pillar (b) is **schemas, plural** — one per population, because the human and rodent structures diverge on the effect-size machinery, not just labels. And pillar (a)'s extraction skill must encode object-level study reading (RLS scoring, SYRCLE, Direction), which is where accuracy is genuinely unknown and must be *measured* (§10), not assumed.

---

## 3. The reframe: preregistration-first, feasibility-proven — and its honest limit

A human MA fails quietly two ways: **preregistered on wishful thinking** (an analysis the eventual data can't support) and **silently amended** after results arrive. The pipeline splits into two phases with a wall between:

- **Phase A — Preregistration & feasibility.** You lock the prereg not by *describing* a plan but by *demonstrating* it: multiple searches actually run and deduplicated, positive controls recovered, the data schema(s) proven by extracting several real included articles end-to-end, power simulated in R against a predicted k **and** the actual moderator models. The system refuses to lock until these artifacts exist.
- **Phase B — Execution** against the locked prereg, ending in a deviation report reconciling realized k / effects / heterogeneity against the predictions.

**The honest limit (review point 6).** "Feasibility-proven" and "blind pre-commitment" are in genuine tension: to prove feasibility you must handle real study data before locking, which is the opposite of "choices can't be reverse-engineered." OpenTimestamps proves *not-written-after-T*, never *written-before-you-saw-data*. The design does not pretend these compose for free. The rule:

1. Pilot on a **walled-off subset** (e.g. one database, or a random 15%) that is then either excluded from the main run or explicitly carried as a pre-declared pilot.
2. **Freeze the inclusion criteria and the analysis plan before pilot *extraction*** — pilot extraction may reshape the *schema* (a data-structure fix) but may not reshape *hypotheses or models* (an analysis choice). The prereg records which is which.
3. Everything after lock is a numbered, timestamped **amendment** with rationale; B6 reports them.

---

## 4. Stage map (applied to EE→Cognition)

### Phase A — Preregistration & feasibility

| # | Stage | On your MA | Gate |
|---|---|---|:--:|
| A0 | **Landscape** | Prior EE→cognition MAs/SRs/narrative reviews; field consensus; **required written justification of why yours is better** (wider species scope + RLS dose model + three-level RVE). Infeasible-topic tripwire. | |
| A1 | **Question + epistemics** | Lock PICO; **brief the user in writing on the unknown-k problem** — k, effect, and heterogeneity are unknown until screening ends, so the plan is a bet hedged by simulation. | |
| A2 | **Draft search** | Your real term sets (PubMed/Scopus/PsycNET, rodent + human); **gray-lit toggle** (preprints, dissertations); **positive controls** from prior reviews + your known-included set. | |
| A3 | **Search bake-off** | Run multiple versions; dedup (DOI + fuzzy title); score each on **control recall (a floor, not proof) + a miss estimate** (e.g. capture-recapture across databases). | ● pick strategy |
| A4 | **Pilot screening** | Title/abstract **and a substantial full-text subset**; full-text pass flags extraction problems per paper (effect size where? text/table/figure-only? Morris needed? Direction?). | ● |
| A5 | **Schema proof** | Specify **both** raw schemas + **both** processed schemas; **prove** by extracting several real included articles end-to-end (raw → reasoning log → processed row → a metafor call that runs). Accept up front this is two schemas with pre-post machinery on the human side. | ● schema lock |
| A6 | **Simulation / power** | In R, simulate the **actual models** (dose slope, species×dose interaction), sweeping true effect, τ² at each level, moderator distribution, and r; report where the **cluster-count floor** (not raw power) is the binding constraint. | ● power sign-off |
| A7 | **Methods literacy** | Required sections (§9): FE vs RE, Cohen vs MCID, two heterogeneities, **and cross-species SMD combination**. | |
| A8 | **LOCK** | Assemble prereg; hash + OpenTimestamp; record k prediction + power basis + the sensitivity set. Amendments only after. | ● final approval |

### Phase B — Execution (against the locked prereg)

| # | Stage | On your MA | Gate |
|---|---|---|:--:|
| B1 | **Full search + dedup** | Winning A3 strategy at full scale; PRISMA identification. | |
| B2 | **Screening** | t/a → full-text, agent + human, coded reasons; PRISMA flow. | ● adjudicate |
| B3 | **Extraction** | One row per study/comparison/**test/outcome/arm** into the correct raw schema; **per-study reasoning log** for every derived value; **figure-extractor only when the effect-size/CI info is visual-only**, permanently flagged. | |
| B4 | **Raw → processed (R)** | `escalc`/Morris `dppc2`; **Direction sign-flip**; multi-arm VIF → `vi_adjusted`; `impute_covariance_matrix` (r swept); emit `*_main.rds` validated against the A5 schema. | ● confirm figure-derived + dispersion + Direction |
| B5 | **Synthesis (R)** | Three-level `rma.mv` + `coef_test(CR2)`; I²/τ²; H1–H4 incl. **lnCVR**; pub-bias **after `agg_study` article-level aggregation**; the pre-enumerated sensitivity set. | |
| B6 | **Deviation report** | Realized k / effects / heterogeneity vs A8 predictions; every departure listed as an amendment. | ● approve |

---

## 5. Human gates, and why each is a gate

A gate halts the pipeline and writes an editable checkpoint; nothing advances until a human resolves it and the decision is logged.

1. **A3 search strategy** — control recall is a human judgment about coverage; automations over-trust their own queries.
2. **A4 pilot screening** — inclusion defines the sample; first contact with extraction feasibility.
3. **A5 schema lock** — the single highest-leverage decision (your own experience); locked only after *proven* on real articles.
4. **A6 power sign-off** — the user must consciously accept the k-vs-power (and interaction-power) bet.
5. **A8 prereg lock** — the wall; timestamped, hashed.
6. **B2 adjudicate**, **B4 confirm figure-derived / dispersion / Direction**, **B6 approve** — the error-prone, bias-prone, and final-call moments. B4 now explicitly gates on **Direction** because a silent sign error is the review's clearest "quietly wrong" failure.

---

## 6. The three pillars, concretely on your MA

### 6a. Two typed schemas + the reasoning log (the spine, corrected)

Your codebook is the template — treated as a *typed, validated contract*, one per population:

- **Raw** (one row per Outcome×Arm; your 115/134-col shape): means/SDs, `Variance_Source` (reported/calculated/imputed), **`Direction`**, SYRCLE, RLS components (rodent), pre/post + adherence + RoB2 (human), sensitivity flags. "Raw but not really" — some cells are derived, so each points to…
- **Reasoning log** (one linked file per study): every ambiguous or calculated decision ("SD = SEM×√n; n from methods table; **Direction = −1 for escape latency, sign flipped so +g = better**; Morris dppc2 with pre/post r assumed 0.5"). The human-verification surface and the audit trail.
- **Processed** (your `*_main.rds` shape): `yi`/`vi` (`Hedges_g_corrected`, `vi_adjusted_multiarm`), the **three nesting IDs** (`Study_Arm_ID/Test_ID/Outcome_ID`), cluster ID, VCV inputs. Schema-locked in A5 so B4 can only emit something that fits.

The schema must express the full nesting (multiple tests per study, multiple outcomes per test) — without it you cannot reach the 155 rodent / 323 human effect sizes or feed the three-level model.

### 6b. Extension rules as worked skills — screening AND extraction

Two Claude Code skills, each carrying **adjudicated real exemplars** from your MA (rules get their power from worked cases, not one-line rubrics):

- **`ma-screen`** — inclusion/exclusion with 3–5 real borderline abstracts + correct call + reasoning ("adolescent rats — age violates healthy-adult window → exclude `population`").
- **`ma-extract`** — worked extractions for several real included papers: the exact map from what the paper reports to the raw-schema row, including the hard cases — multi-arm shared control → `Study_Arm_ID` + VIF; median/IQR → mean/SD (with the Wan sample-size correction); figure-only → figure-extractor; Morris pre-post; **Direction**. **The RLS scoring rubric lives here and is the highest-risk piece**: it is your invented construct, sits in dense methods prose (figure-extraction is irrelevant to it), has no literature exemplars, and if scoring drifts the entire dose-response is wrong with no downstream numeric gate to catch it. Therefore RLS accuracy is *measured* by the golden diff (§10) before it is trusted, and RLS scoring stays human-confirmed longest. SYRCLE is similar, with the wrinkle that most rodent papers report nothing on allocation/blinding, so an agent outputs "Unclear" and is right for the wrong reasons — cheap to automate, low value, human-backstopped.

### 6c. Figure-extractor as the visual-only fallback (permanently flagged)

Invoked **only when text/tables lack the effect-size/CI info** and it must be read off a chart (`Data_Source = figure`). Output is double-flagged (`Data_Source = figure`, `Data_Extraction_Method = figure-extractor`) plus a `figure_derived = TRUE` marker that **persists even after human verification** — so the figure- vs text-derived sensitivity analysis your MA already contemplates stays honest. Verified is not laundered.

---

## 7. Inference in R (metalib retired), with the estimators pinned

**Split.** Python orchestrates (agents, screening, figure-extractor, the state machine, the schema validator). **R does every effect size and every inference** — there is no substitute for metafor/clubSandwich. `pipeline.py` shells to `Rscript`. R is installed here (`/usr/bin/Rscript`), so this is runnable now.

**`metalib.py` is retired from inference.** The review found it cannot reproduce your MA and introduces bias:
- no `Direction` → wrong-signed effects that cancel the pool;
- no Morris `dppc2` → structurally cannot produce the human (pre-post) half;
- CI→SD divides by 1.96, but rodent n≈8 needs t₍.975,7₎ ≈ 2.365 → SD underestimated ~20%, small studies overweighted;
- `box_to_mean_sd` hardcodes `/1.35`, dropping the Wan-2014 sample-size correction Q(n).

These are precisely the "wrong dispersion silently reweights studies" failure our own gate exists to catch — so the tool must not commit it. metalib may survive only as a non-authoritative sanity check; the authoritative path is R. (STATUS.md's "math core… done" claim is corrected accordingly.)

**The pinned R spec (must match `CONSOLIDATED_ANALYSIS.Rmd`):**
- Effect sizes: `escalc(measure="SMD")` for between-group; **Morris `dppc2`** for pre-post; **lnRR** (PROTOCOL alt) and **lnCVR** (H4) where prespecified. Apply `Direction` sign-flip at this step.
- Multi-arm: shared-control variance inflation → `VIF_multiarm` → `vi_adjusted_multiarm`.
- Dependency: `impute_covariance_matrix(vi, cluster=Article_ID, r=…)` **swept over r ∈ {0.5,0.7,0.9}**; three-level `rma.mv(yi, V, random = ~1 | Study_Arm_ID/Test_ID/Outcome_ID)`.
- Inference: **`robust()` / `coef_test(vcov="CR2")` (clubSandwich, Satterthwaite dfs)**, not the plain sandwich. Where article clusters < ~40, use **cluster-wild bootstrap** and say so — small-cluster RVE is anticonservative.
- Heterogeneity: I² (Higgins&Thompson, multilevel decomposition), τ² per level, prediction interval.
- Publication bias: **aggregate to article level (`agg_study`) first** (Egger/trim-fill/PET-PEESE assume independence), then test.

---

## 8. Simulation and power (A6) — the right estimand

v1 promised power "at k≈N you can detect g≈X" — that is power for a *pooled intercept*, the quantity you care about least. Your headline tests are a **dose slope** (`RLS_Differential`) and a **species×dose interaction** (`h1_cs`). Meta-regression interaction power depends on the moderator's range and joint distribution, effects-per-cluster, τ² at multiple levels, and r — not on k alone. And the moderator distribution is unknowable until after extraction, so interaction power at prereg time is a bet (dose distribution) on a bet (k) on a bet (τ²).

So A6, concretely, must:
1. simulate the **actual moderator models** (slope, interaction), not the intercept model;
2. **sweep r** ∈ {0.5,0.7,0.9} and τ² at each level;
3. draw the moderator from a plausible declared distribution and show sensitivity to it;
4. run the *identical* `rma.mv |> coef_test(CR2)` the analysis will use;
5. **report the cluster-count floor**: below ~40 article clusters, RVE inference is the binding constraint, not raw power — widen scope or switch to cluster-wild bootstrap.

Done honestly, A6 makes the FE/RE and k-vs-power tradeoffs *visible*, doubles as a validated, professionally formatted proof that the output machinery works before a single real paper is extracted (a genuine morale/marketing artifact), and — critically — states plainly which powers it *cannot* honestly estimate pre-data.

---

## 9. Required methods-literacy sections (A7) — cannot be skipped

Short, prescriptive; the lock is blocked until each is acknowledged.

- **FE vs RE.** FE assumes one true effect and is *anticonservative* under real between-study variance; RE admits a distribution. There is usually **no clean digestible test** for which is "true." **Default: field convention (RE for a heterogeneous behavioral literature); when there's a genuine choice, err conservative.** Your MA already does this (three-level RE + RVE).
- **Cohen vs practical.** Required for biomedical work: distinguish Cohen's arbitrary small/medium/large from **MCID / practical significance** — what change in the cognitive outcome matters. The prereg must state the practical threshold.
- **Two heterogeneities.** τ²/I² is the **mathematical** dispersion; **conceptual** heterogeneity is whether the studies measure the same thing (Morris vs fear conditioning vs Y-maze; mouse vs human). High I² is benign or fatal depending on the conceptual story — the section forces that story.
- **Cross-species combination (new).** Your `h1_cs` z-standardizes rodent `RLS_Differential` and human `Total_Hours` onto a shared `Dose_Z` and fits `Species*Dose_Z`. This apples-to-oranges standardization is the most novel and most contestable move in the dissertation; combining SMDs across species with different dose operationalizations must be a **required written justification**, not a silent `scale()`.

---

## 10. Validation first: the golden diff (the experiment the vision rests on)

Gates only catch errors if the human re-does the work; the design must instead *measure* how often the agent is wrong. You are sitting on the ideal gold standard — **155 fully-coded rodent + 323 human rows**. Before building scaffolding:

- Have `ma-extract` re-extract ~8 already-coded articles (mix rodent + human, incl. multi-arm and figure-only cases) from the PDFs.
- Score **field-level agreement** against `rodent_data.csv` / `human_data.csv`: exact-match / ICC on `Control_Group_Mean`, SDs, `n`, `Hedges_g_corrected`; κ on screening decisions and SYRCLE; and especially the high-risk fields — **RLS components, dispersion type, `Direction`**.
- Report a **residual per-field error rate after gating** — the number a committee will demand and the number that tells you whether this vision is viable at all.

This was v1's optional "decision #2." It is not optional; it is step 1 (§14).

---

## 11. Scale, retrieval, and cost (the seams where real pipelines stall)

The toy fetched 120 records; your real `rodent_pubmed_query.txt` is an OR-heavy string returning thousands to tens of thousands. The design must address:
- **Screening throughput/cost/reliability at 10k–30k records** — batching, cheaper first-pass models, agreement sampling, and a budget the user sees before committing.
- **Retrieval** — A4 full-text and B3 figure-extraction both presuppose you *have* the PDFs and supplements. Paywalls, missing supplements, and dead links are top PRISMA drop reasons. Wire the existing `fetch-pdf-from-doi` and `author-contact` skills into B1/B3; record "full text unobtainable" and "no extractable data" as coded, counted exclusions.

---

## 12. Preregistration integrity (OTS + the blind limit)

Assemble the prereg to one document, hash it (SHA-256), and anchor the hash so it can't be back-dated or silently edited:
- **OpenTimestamps** — anchors the hash into Bitcoin via a `.ots` proof, free, no account. The honest version of "blockchain?": you don't need a bespoke chain, you need a *trustless timestamp*. It proves *not-after-T* — **not** *written-before-you-saw-data* (§3's limit). Conventional analogs (OSF/PROSPERO registration, a signed git tag) pair with it.
- After lock, `pipeline.py` treats the prereg as immutable; changes are numbered, timestamped **amendments** with rationale, surfaced in B6.

---

## 13. Honest constraints

- **Unknown k is irreducible.** Simulation manages the bet; it cannot remove it. B6 is the reckoning.
- **Object-level quality scoring (RLS, SYRCLE) is the hardest thing to automate well** and stays human-supervised longest; the golden diff (§10) is how you learn *how* unreliable it is before trusting it.
- **Feasibility-proving weakens pre-commitment** (§3). Named, not hidden.
- **Control recall is a floor, not proof of coverage** (§4 A3).
- **Blockchain buys a trustless timestamp, nothing more** (§12). It does not make the prereg good — A3–A6 do.

---

## 14. Reprioritized build order

1. **Golden diff first (§10).** Agent re-extracts ~8 already-coded articles; score field-level agreement vs your CSVs. Cheap, uses assets you have, tells you if the vision is viable *before* building around it. Highest information per dollar.
2. **R inference harness, specified (§7).** `escalc` + Morris `dppc2` + `impute_covariance_matrix` swept over r + three-level `rma.mv` + `coef_test(CR2)`. Retire metalib's role. **Acceptance test: regenerate a slice of `rodent_main.rds` from raw and diff against yours** — runnable today.
3. **The two typed schemas + `Direction` + full nesting (§6a),** proven on real articles (A5).
4. **Extension-rule skills (§6b)** with worked exemplars, RLS scoring measured not assumed.
5. **Prereg front-end (A0–A3), power sim (§8), OTS lock (§12), methods-literacy gate (§9).** Valuable, but scaffolding around a core that must be validated first.

The distance between an impressive-looking pipeline and one that would have produced your dissertation is almost entirely items 1–3.

---

## 15. Requirements traceability (original asks + review points)

| Requirement / review point | Where handled |
|---|---|
| Work in **R** (metafor; Python has no substitute) | §7; metalib retired from inference |
| Explain **method limitations** to users | §9 methods-literacy gate |
| **Simulations** for k-vs-power | §8 (actual moderator models, r-swept) |
| Apprise user of **prior MAs/SRs/reviews** + consensus | §4 A0 |
| Justify **why yours is better** | §4 A0 (required) |
| **Unknown k** epistemics | §4 A1; §13 |
| Understand **nature of primary research** → quality scoring | §6b object-level; §10 measures it; §13 |
| **Timestamped (blockchain?) prereg** | §12 OpenTimestamps |
| Prevent **infeasible MAs** | §3; §4 A0 tripwire + A3 recall + A6 power |
| Prevent **post-hoc changes** | §3 wall; §12 immutable lock + amendments; B6 |
| Prereg **predicts final k** | §4 A6/A8; B6 checks realized vs predicted |
| **Simulate different effect sizes** | §8 |
| **FE vs RE** convention/conservative | §9 |
| **Cohen vs MCID** | §9 |
| **Mathematical vs conceptual heterogeneity** | §9 |
| Forbid finishing prereg without **real searches + dedup + optimize** | §4 A3 |
| **Substantial full-text subset** in pilot | §4 A4 |
| **Positive controls** | §4 A2/A3 (as a floor, §13) |
| Full-text screening **finds extraction issues** | §4 A4 |
| Figure-extractor **visual-only**, flagged post-verification | §6c permanent flag |
| **Hardest part:** one framework for all study data; variables + types | §6a **two** typed schemas; §4 A5 proof |
| Specify structure in prereg; **prove by extracting articles** | §4 A5; §10 |
| **Raw** (needs calculation) + **per-study reasoning log** | §6a |
| **Processed** `.rds` for metafor; needed for sim | §6a; §8 |
| Justify vs **predecessors** | §4 A0 |
| Agent power = rich **rules/criteria** (screen + extract skills) | §2, §6b |
| Well-specified **data structure** (also for verification) | §6a duality |
| **Figure-extractor as backup** | §6c |
| *(review)* One-spine wrong → **two schemas** | §2, §6a |
| *(review)* metalib bias (**Direction, Morris, CI/1.96, Wan**) | §7 |
| *(review)* Three-level nesting + VIF + r-sweep + CR2 | §6a, §7 |
| *(review)* Power sim wrong estimand | §8 |
| *(review)* RLS highest-risk extraction | §6b, §10 |
| *(review)* Feasibility vs blind prereg tension | §3, §12 |
| *(review)* Control recall oversold | §4 A3, §13 |
| *(review)* Scale/retrieval absent | §11 |
| *(review)* No accuracy measurement → **golden diff** | §10, §14 |
| *(review)* Missing lnCVR/H4, pub-bias aggregation, sensitivity family, cross-species justification | §7, §9 |
| *(v3)* Synthetic-GT chart model (classification / detection / extraction) | §19 |
| *(v3)* Author outreach to resolve extraction ambiguities (schema field) | §20; §6a |
| *(v3)* Variable taxonomy: descriptive / primary (corrected) / exploratory (uncorrected) | §16 |
| *(v3)* Null + research hypotheses stated mathematically + verbally, each justified | §16 |
| *(v3)* Hypothesis families / hierarchical testing to conserve power | §16 |
| *(v3)* Prior-MA summary table (meta-meta-analysis) + seed set + author feedback | §17; §4 A0 |
| *(v3)* RMarkdown notebooks for all R (chunked, sanity-checkable) | §21 |
| *(v3)* Interactive / animated charts (browser, not Shiny) | §21 |
| *(v3)* Infographic / tweet thread for dissemination | §21 |
| *(v3)* Best effect-size metric for the question + commensurability (escalc) | §18; §9 |
| *(v3)* Prereg publishing (OSF / PROSPERO caveat / Cochrane best practices) | §22; §12 |
| *(v3)* DistillSR positioning + collaboration / inter-rater reliability | §22 |
| *(v3)* Metascience Observatory branding | title; §21 |
| *(v3)* Competitive landscape — adapt others' ideas, differentiate | §23; `COMPETITIVE-LANDSCAPE.md` |
| *(v3)* Vision-model eval/improve methodology | §19a; `VISION-MODEL-METHODOLOGY.md` |

---

## 16. Hypothesis specification and the variable taxonomy (prereg)

A prereg is not just a search + analysis plan; it is a *statistical argument stated in advance*. This section makes the user write it like a research-methods final, and it gates the prereg lock (slots into A1/A5/A7).

### 16a. Null and research hypotheses, stated rigorously

- For each hypothesis, state **H0 and H1 in both mathematical and rigorous verbal form** — e.g. H0: β_dose = 0 vs H1: β_dose > 0, verbally "the pooled dose–response slope of the cognition effect (Hedges g) on RLS differential is zero" vs "…is positive" — naming the estimand, the direction, and the test.
- **Justify the inclusion of each hypothesis**: why it is worth testing, what prior work or theory motivates it, and what a null result would mean. A hypothesis with no justification is cut.

### 16b. Variable taxonomy: descriptive / primary / exploratory

Every variable in the schema carries a declared analytic role (a required schema attribute, §6a) that governs multiplicity:

| Role | Definition | Multiplicity |
|---|---|---|
| **Descriptive** | Characterizes the corpus (country, publication year, species, assay). Not tested against a hypothesis. | none |
| **Primary** | Directly associated with a pre-specified hypothesis. | **must correct for multiple comparisons** |
| **Exploratory** | Not part of any primary hypothesis but more than descriptive; hypothesis-generating. | generally uncorrected, **but conclusions must be explicitly tentative** — the prereg forbids anything but tentative claims from exploratory tests |

The taxonomy is locked in the prereg; moving a variable from exploratory to primary after seeing data is a tracked amendment (§12), never a silent upgrade.

### 16c. Hypothesis families and hierarchical (gatekeeping) testing

- Where possible, **structure hypotheses into families with sub-hypotheses**: an omnibus/overall effect of a factor, with its moderators/subgroups nested beneath. (Sometimes impossible; when it can be done, it ought to be.)
- This **conserves power and controls multiplicity**: a hierarchical/gatekeeping procedure tests the omnibus effect first and descends to sub-hypotheses only if the family's gate passes, rather than paying a flat correction across every test. On your MA: H1 (dose) as an omnibus family, with sex×dose, subregion×dose, and species×dose as nested sub-hypotheses.
- The prereg records the **family structure and the testing order** (which corrections apply within vs across families) — that order is a prime target for silent post-hoc change.

---

## 17. Prior-work synthesis: the meta-meta-analysis table and author outreach

Expands A0 (Landscape). "Find all previous SRs/MAs" means produce an artifact, not a reading list.

### 17a. The extant-MA summary table

- A **table of every prior systematic review and meta-analysis** on the (or a similar) question, with their **quantitative conclusions** where cross-comparable: pooled effect, CI, k, heterogeneity, and the effect-size metric used.
- The **planned MA is a row in that same table**, positioned to show how it **differs and improves** — wider species scope, newer/larger corpus, the RLS dose model, three-level RVE vs naive independence. (This is the §4 A0 "why yours is better" justification, now in tabular form.)
- Cross-comparability is itself a finding: if prior MAs used incommensurable metrics (§18), the table records that.

### 17b. Prior MAs as a resource (meta-meta-analysis)

- Their included-study lists yield a **seed set of certain-includes** — papers that *must* survive your search + screening. That seed set validates **search-term recall, screening accuracy, and extraction accuracy** (the positive controls of §4 A3 and the golden-diff targets of §10). Mining prior MAs for it is the meta-meta-analytic move.

### 17c. Email the prior-MA authors

- **Contact the authors of the prior MAs/SRs** with a draft of the planned protocol and ask for feedback — they know the literature's traps and often have unpublished tips. The person who just did the adjacent MA is the cheapest expert review you can get. (Logged as a decision: who was contacted, what they said, what changed.)

---

## 18. Effect-size metric selection and commensurability

Expands §7/§9: choosing the metric is a first-class prereg decision, not a default.

- **Pick the metric the question and the data demand**, not a habit: SMD/Hedges g (incomparable units, as in your MA), lnRR/ROM (ratio-scale, fold-change), lnCVR (variability, your H4), OR/RR/RD (binary outcomes), correlation/Fisher z (associations), hazard ratio (time-to-event). The choice depends on the hypothesis, how the to-be-synthesized studies actually measure the outcome, and what keeps studies commensurable. **Consult prior MAs (§17)** — the metric a good prior MA on the same topic used is strong evidence.
- **Commensurability is load-bearing.** `escalc` (metafor) computes and, under assumptions, inter-converts many measures (d↔r, OR↔d), but **some are genuinely incommensurable**: a hazard ratio is not a risk ratio is not an odds ratio, and converting across them without the underlying survival / base-rate information is a silent error. OR and RR diverge as the base rate rises; HR carries time information the others lack. The prereg must state the chosen metric, what it may be converted from, and what it must **not** be pooled with.
- **Risk / hazard / odds literacy is a required note** (they are widely conflated) — a methods-literacy item (§9) as well as a metric-selection step.
- Reference (from your **Metascience Observatory** Zotero collection): **Röseler, L., Kaiser, L., Doetsch, C., Klett, N., Seida, C., Schütz, A., et al. (2024). The Replication Database: Documenting the Replicability of Psychological Science. *Journal of Open Psychology Data*, 12(1). DOI: 10.5334/jopd.101.** A replication database must harmonize effect sizes across original + replication studies, so it documents the `escalc`-style conversions used and — the load-bearing part for us — which metrics are genuinely incommensurable. It anchors this section's rule that the prereg declare the chosen metric and its (in)convertibility.

---

## 19. A chart-understanding model trained on synthetic ground truth

A capability upgrade for pillar (c). Rather than rely only on a general vision model reading pixels, train a specialized model on synthetic charts whose ground truth is known by construction.

- **Generate a large, semi-randomized synthetic chart corpus** in R (ggplot) and Python (matplotlib/plotly), spanning all chart types and **deliberately hard cases: complex multi-panel figures, log/broken/dual axes, overlapping series, per-animal dot overlays**. Because the charts are fully synthetic, the **ground truth (types, landmarks, values, panel structure) is exact and effectively unlimited** — no human labeling.
- Train and evaluate three tasks against it: **classification** (chart type + provenance), **feature/landmark detection** (bars, error caps, box quartiles, axes, non-data ink), and **extraction** (calibrated values). This is the ML backbone that could let figure-extractor *detect* rather than merely *convert* — today it only does the affine math on human/agent-supplied pixels (its honest niche).
- **Relationship to the golden diff (§10):** synthetic GT is exact but may not transfer to real journal figures; the golden diff against your coded CSVs measures *transfer*. So synthetic corpus **trains and stress-tests**; real gold **validates**. **Honest sequencing:** this is a large build — it comes *after* the golden diff shows an accuracy gap a general vision model can't close (§14). Don't train the model before measuring that it's needed.

### 19a. The two-tier architecture: vision model perceives, agent understands

The division of labor is deliberate — perception and meaning are different jobs, and separating them is what makes the extraction auditable:

- **Vision model = perception.** It does the **classification** (chart type, provenance, non-data ink) and the **quantitative reading** — detect landmarks (bar tops, error caps, box quartiles, axes, points) and produce **calibrated values with uncertainty**. It is *blind to what the figure means*; it just reports what is drawn. This is the specialized model §19 trains.
- **AI agent = meaning.** A separate agent that **understands the figure in the context of the study** (caption, methods, hypotheses) **uses the tools** to drive extraction: it decides *which* landmarks matter, interprets them (which group is control? what is the dispersion type? which timepoint? what is `Direction`?), maps them onto the data schema (§6a), and flags ambiguity for human review or author outreach (§20). It does *not* re-read pixels — it consumes the vision model's structured output.
- **The interface (contract).** The vision model hands the agent a structured object: `{ types + confidences, landmarks with per-landmark uncertainty, detected axes/scales, flags (multipanel, log-axis, occlusion, error-bars-one-sided) }`. The agent combines that with the caption/methods to produce the final schema row, and **uncertainty/abstention propagates**: low-confidence perception → the agent flags rather than fabricates. This mirrors the tool's current honest niche (it converts, it does not invent) — the vision model raises the floor on perception; the agent supplies the judgment.
- **How to evaluate + improve the perception tier** — benchmark construction, synthetic→real transfer measurement, error analysis, the ranked improvement ladder (prompting → tool-augmentation → ensembling → verifier loop → **specialist landmark detector** → LoRA → synthetic-pretrain+real-fine-tune), and the full vision↔agent interface contract — is written up in the companion **`VISION-MODEL-METHODOLOGY.md`**. Headline: the specialist landmark detector (free synthetic GT, feeds the existing calibration math, targets the load-bearing dispersion channel) is the sweet spot; validate everything against the dissertation's 155+323 coded rows (the golden diff, §10). Don't build the model before a Stage-0 baseline shows prompting can't close the gap.

---

## 20. Author outreach to resolve extraction ambiguities

Distinct from §17c (which contacts *prior-MA* authors for design feedback); this contacts **primary-study authors** to resolve missing or ambiguous data — often the single biggest real-world extraction blocker: the number simply isn't in the paper.

- The **raw schema carries an outreach field** alongside the provenance/metadata: for each ambiguous, unreported, or figure-derived-and-uncertain cell, record a **structured query** — `query_status` (none / needed / sent / answered / no-response), `query_text`, `query_response`, `resolved_value`. "We asked the authors for the SD and n" becomes an auditable part of the record, not a lost email.
- **Batched, semi-automated outreach**: the pipeline drafts author emails from the query fields (wiring the existing `author-contact` skill), tracks responses, and updates the value + provenance when an answer arrives — an author-supplied value outranks a figure-derived one, and the `figure_derived` flag is updated accordingly (§6c).
- Ties to §11 (retrieval) and the PRISMA accounting: a study can end up excluded as "author non-response, data unobtainable," coded and counted.

---

## 21. Outputs and dissemination

How results leave the pipeline — three layers: reproducible notebooks, interactive figures, and publicity.

### 21a. RMarkdown notebooks for all R

- **Every R step ships as an RMarkdown (.Rmd) notebook**, chunked so a human can run each chunk and **sanity-check its output** — the discipline that caught real coding errors in your own MA (small chunks are eyeball-able). The canonical deliverable is the **.Rmd knit to a self-contained HTML report** (reproducible, viewable with no runtime).
- **On Jupyter (your question):** Jupyter runs `.ipynb`, not `.Rmd`, natively. To execute R in Jupyter you need the **IRkernel** — with it, plots and tables *do* render inline after a chunk, as in RStudio. To use the `.Rmd` in Jupyter, pair it to an `.ipynb` with **jupytext** (round-trips `.Rmd ↔ .ipynb`). Recommendation: ship the `.Rmd` (+ knit HTML) as canonical for RStudio users and a jupytext-paired `.ipynb` (IRkernel) for Jupyter users — inline graphs/tables work in both. (RStudio is still the smoothest `.Rmd` experience; the pipeline shouldn't assume it.)

### 21b. Interactive and animated charts (browser, not Shiny)

- For **browser-consumable, no-server** figures, the pragmatic choice is **Plotly** — it works from *both* R and Python and emits a self-contained interactive HTML widget (hover-to-read forest plots, zoomable funnels, filterable moderator views). R alternatives: `ggiraph` (interactive SVG); and — correcting "not sure R even has animation" — **`gganimate`** *does* produce GIF/MP4 animations (via gifski/av). Python: Plotly / Altair / Bokeh for interactivity, `matplotlib.animation` / `celluloid` for animation (likely the Python animation library you remember).
- **Shiny only when you need a real app** (live re-computation, user-uploaded data). For a shareable results artifact a self-contained Plotly HTML beats a Shiny app that needs hosting — matching your "out of Shiny, in the browser" lean. (`shinylive` can run Shiny fully client-side if app-like interactivity is genuinely required.)

### 21c. Publicity: infographic and tweet thread

- End-stage deliverables are not only the traditional report but a **one-page infographic** and a **tweet/thread** — the headline effect, its practical (MCID, §9) meaning, and the PRISMA/forest at a glance — to publicize the result **and the Metascience Observatory** project. Generated from the same locked numbers as the report (no separate, un-sourced claims).

---

## 22. Preregistration publishing and collaboration / inter-rater reliability

### 22a. Publish the prereg where it counts

- The prereg (§12) should be **registered in a real venue**, with in-pipeline guidance for doing so: **OSF Registries** (general, reliable, timestamped) is the default; some **journals** offer Registered Reports. **Caveat for your topic:** PROSPERO's scope is human health-related reviews and it has **not reliably accepted purely preclinical / animal reviews** — so for the rodent arm, follow **SYRCLE's preregistration guidance** and register on OSF rather than assuming PROSPERO. Follow **Cochrane / PRISMA-P** protocol best-practices for structure and completeness. (OpenTimestamps from §12 is the cryptographic belt-and-suspenders on top of public registration.)

### 22b. Collaboration and inter-rater reliability (and why DistillSR)

- The pipeline runs **solo or as a team**. Some steps — notably **inter-rater reliability** on screening and extraction — *functionally require ≥2 raters* (you cannot compute κ / agreement from one). The design supports two IRR modes: **agent-vs-human** (the agent is the second rater, measured by the golden diff, §10) and **human-vs-human** when a team is present.
- **Why others value DistillSR (you didn't, solo):** its pull is largely **collaboration, reviewer reconciliation, and team audit trails** — the multi-person machinery a solo reviewer doesn't need. The opportunity: **beat it** by making the agent a rigorous, *measured* second rater with full decision-logging (already the pipeline's spine, §5/§12), so a solo user gets team-grade IRR + auditability and a team gets that plus human–human reconciliation. A positioning note, not yet a build; revisit once the core (golden diff → R harness → schemas) is proven (§14).

---

## 23. Competitive positioning (mid-2026)

Full landscape + sources in the companion **`COMPETITIVE-LANDSCAPE.md`**. The strategic summary:

**The ground shifted in 2025–2026.** "End-to-end, question → pooled `metafor` estimate → forest plot" is **no longer a differentiator** — it is a crowded research theme (meta-pipe, LUMEN, AutoForest, Manalyzer) plus shipped products (otto-SR, Nested Knowledge). "R does the inference" is universal — **table stakes, not novelty.** Notably, **meta-pipe** is the closest analog *and is also Claude-Code-native*, so leading with "automated MA" invites "how is this different from meta-pipe?"

**What no one has assembled is the combination.** Each capability exists somewhere; together, nowhere:

| This pipeline's claim | Where it stands vs. the field |
|---|---|
| End-to-end → `metafor` | **Occupied** (meta-pipe, LUMEN, otto-SR, Nested Knowledge). Don't lead with it. |
| R does inference | **Universal.** Not a distinction. |
| Mandatory human gates | **Partly occupied** (meta-pipe has 5). Ours bound to specific epistemic risks is stronger than queue-style. |
| Append-only log **paired with pooling** | **Thin** — real audit logs live in tools that *don't* pool (Elicit, DistillerSR, SyRF). ~Unclaimed together. |
| Study/arm-level `rma.mv` **with provenance** | **Whitespace + hard** — only metaBUS (closed) & SyRF (external pooling) reach it; no LLM pipeline does. The documented accuracy cliff (F1→0 on multi-field numerics). |
| Figure-derived, **permanently flagged → sensitivity analysis** | **Largely open** — Manalyzer reads figures but doesn't flag/pool cleanly; digitizers (metaDigitise, WebPlotDigitizer) are standalone. |
| **Feasibility-proven preregistration** | **Cleanest whitespace** — nobody does it for MA (Virtuous Machines is primary-studies-only; RegCheck is post-hoc). |
| Preclinical / cross-species | **Whitespace for automation** — every LLM pooler is clinical-RCT-only; SyRF is non-LLM + external pooling. |

**Positioning (five moves):** (1) **Lead with "feasibility-proven preregistration for meta-analysis," not "automated MA"** — the one thing no competitor does; reframes the pitch from "faster" to "un-gameable, pre-committed rigor"; the natural Metascience Observatory headline. (2) **Own "study-level, figure-aware, provenance-first extraction" and prove it with the golden diff** — a measured residual per-field error rate against the 155/323 coded rows, the validation the preprint cohort lacks. (3) **Compete on a capability grid, not vibes** — cite meta-pipe's *zero validation* and Nested Knowledge's *retracted* flagship paper; win on validated rigor. (4) **Make the append-only log + provenance a first-class exportable artifact paired with pooling** (the §22b "team-grade IRR for a solo reviewer" angle). (5) **Claim the two hardest niches deliberately: preclinical/cross-species and figure-derived data** — where the LLM-pooler field is empty and the dissertation is the proof of concept.

**Ideas worth adopting from competitors** (detail in the companion): read effect estimates back from R files into the report to bar manuscript hallucination (meta-pipe); elicit RoB/SYRCLE *signaling answers* then apply the algorithm deterministically, never ask the model for the verdict (Claude 3.5 RoB2 study); multi-pass extraction with an arbiter + per-phase cost logging (LUMEN); persist reproducible figure-calibration artifacts so a human can re-verify (metaDigitise `caldat`); publish honest cost + accuracy numbers (the field is starved for them).

**Reality check to internalize:** the field's own benchmarks say nobody is close to trustworthy autonomy — no end-to-end system includes >52.7% of eligible studies (MetaSyn), multi-field numeric extraction collapses to F1≈0, and models fail to reject false evidence (MedMeta). The gates + validation-first discipline are the right response; **position on rigor and honesty**, which the 2026 preprint cohort conspicuously lacks.
