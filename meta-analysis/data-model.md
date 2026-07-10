# Data model — the structured record

Two representations, one source of truth:
1. **Nested JSON** (`corpus.json`) — articles → studies → arms, with full provenance. This is
   where humans/agents extract into and where auditability lives.
2. **Flat studies table** (`studies.csv`) — one row per study, derived from the JSON. This is the
   analysis-ready input for `metafor`/`meta`/Python (one row = one meta-analytic unit).

**The unit of meta-analysis is the STUDY, not the article.** One article → many studies. The
schema makes that structural, and carries the article id on every study so dependency
(clustering) is never lost.

## Nested schema (per article)
```json
{
  "articleId": "vivar2021",
  "citation": { "authors": "Vivar et al.", "year": 2021, "journal": "J Neurosci",
                "doi": "10.1523/...", "title": "…", "zoteroKey": "ABC123" },
  "screening": { "status": "included", "stage": "full-text",
                 "reasonsExcluded": [], "reviewer": "agent+human", "decidedAt": "…" },
  "riskOfBias": { "tool": "SYRCLE", "randomization": "unclear", "blindingOutcome": "low",
                  "baseline": "low", "selectiveReporting": "low", "overall": "some concerns" },
  "studies": [
    {
      "studyId": "vivar2021-exp2-dorsal-M",
      "label": "4-wk running, dorsal HC, male",
      "outcome": { "construct": "hippocampal BDNF protein", "assay": "ELISA", "unit": "pg/mg",
                   "timepoint": "post-4wk" },
      "moderators": { "species": "mouse", "strain": "C57BL/6J", "sex": "male",
                      "ageWeeks": 10, "interventionType": "voluntary wheel",
                      "durationWeeks": 4, "subregion": "dorsal hippocampus" },
      "arms": {
        "intervention": { "label": "running", "n": 10, "mean": 32.4,
                          "dispersion": 3.1, "dispersionType": "SEM", "sd": 9.80 },
        "control":      { "label": "sedentary", "n": 10, "mean": 24.1,
                          "dispersion": 2.8, "dispersionType": "SEM", "sd": 8.85 }
      },
      "effect": { "measure": "SMD", "value": 0.88, "variance": 0.213, "se": 0.462,
                  "ci95": [-0.03, 1.79], "direction": "higher = exercise increases BDNF" },
      "provenance": {
        "source": "figure",                       // figure | table | text
        "articlePage": 6, "figureRef": "Fig 3B",
        "figureExtractor": { "article": "vivar2021", "figureId": "fig3", "subId": "fig3_s2",
                             "characterization": "…ref…", "digitization": "…ref…" },
        "extractedBy": "agent", "confidence": 0.68, "reviewStatus": "needs-review",
        "reviewFlags": ["dispersion-type-from-caption", "n-from-methods"],
        "notes": "bars mean±SEM per legend; n=10/group from Methods." },
      "dependency": { "clusterId": "vivar2021",
                      "sharesControlWith": ["vivar2021-exp2-ventral-M"] }
    }
  ]
}
```

### Field rules that matter for correctness
- **`dispersionType`** on each arm is load-bearing (SD vs SEM vs CI changes variance by ~n).
  Stored raw (`dispersion`) *and* converted (`sd`) so a re-read is cheap without re-digitizing.
  From figure-extractor: `convert.seToSd`, `convert.ci95ToSd`, `convert.medianIqrToMeanSd`.
- **`n`** must be per-arm; if a range ("n=8–10") is given, record the conservative value + a flag.
- **`effect`** is computed by `convert.hedgesG(mean_i, sd_i, n_i, mean_c, sd_c, n_c)` — already
  built and unit-tested (g, variance, se).
- **`dependency.sharesControlWith`** lists studies drawing on the SAME control animals (e.g. one
  sedentary group compared to three running durations). Those aren't independent → shared-control
  variance correction + RVE clustering by `clusterId` (= articleId).
- **`reviewStatus`**: `auto` | `needs-review` | `confirmed`. Everything figure-derived starts
  `needs-review`; synthesis can be run on `confirmed`-only or all, as a sensitivity analysis.

## Flat studies table (`studies.csv`) — analysis-ready
One row per study. Columns:
```
articleId, studyId, label, species, strain, sex, ageWeeks, interventionType, durationWeeks,
assay, subregion, n_int, mean_int, sd_int, n_ctrl, mean_ctrl, sd_ctrl,
yi (effect), vi (variance), sei, measure, source, extractedBy, confidence, reviewStatus,
rob_overall, clusterId
```
`clusterId` (= articleId) is what `metafor`'s `robust()` / `rma.mv(random = ~1 | articleId/studyId)`
clusters on. `yi`/`vi` are the columns `metafor` consumes directly.

## How figure-extractor plugs in (the "in concert" seam)
```
Zotero corpus ──▶ screening records (include/exclude + reason)
     │ (included)
     ▼
figure-extractor:  render(native DPI) ▶ box figure/panels ▶ characterize
     ▼                                   (type, axes, dispersionType, provenance, priority)
     runExtraction ─▶ per-figure extraction {groups:[{mean,sd,n}], effects, …}
     ▼
META layer:  map extraction → STUDY arms  +  attach moderators (from methods text)
     ▼        compute effect (hedgesG)  +  provenance link back to figureId/digitization
     corpus.json  ─▶  studies.csv  ─▶  synthesis (RVE random-effects) ─▶ forest + PRISMA
```
figure-extractor is the **results-digitizer** component; the META layer owns the protocol,
screening, study-grain, moderators, dependency, and synthesis. The existing per-figure
`getMetaAnalysisRows()` is the hand-off point — the META layer consumes it and re-grains to studies.
