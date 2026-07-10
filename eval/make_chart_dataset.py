#!/usr/bin/env python3
"""
Build a labeled chart dataset for evaluating figure characterization.

Each entry is a chart PNG + a ground-truth JSON that includes not only the visual
label (chart type, axes, series) but the ARTICLE CONTEXT (caption + study snippet),
a meta-analysis scenario, and the correct extract/skip decision. That pairing is the
point: chart TYPE is visual, but what the error bars mean, the units, n, and above all
whether/how a figure should be extracted, are only knowable from the article + the MA
criteria — not the image alone.

Run:  python3 eval/make_chart_dataset.py
Out:  eval/charts/<id>.png  + eval/charts/<id>.json  + eval/charts/manifest.json
"""
import json, pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = pathlib.Path(__file__).resolve().parent / "charts"
OUT.mkdir(parents=True, exist_ok=True)
RNG = np.random.default_rng(7)

# One meta-analysis scenario governs every extract/skip decision in the set.
MA_CRITERIA = (
    "Meta-analysis of Drug X vs placebo on CONTINUOUS stress-biomarker outcomes "
    "(e.g. plasma cortisol). For each eligible figure extract post-treatment group "
    "means, SDs (or dispersion convertible to SD) and n per arm; also accept a reported "
    "standardized effect size with its CI. SKIP figures that do not report a between-group "
    "CONTINUOUS outcome comparison for Drug X vs placebo (correlations, agreement/ROC, "
    "survival, categorical response, single-group distributions, participant-flow diagrams)."
)

entries = []


def _save(fig, id, gt):
    fig.tight_layout()
    fig.savefig(OUT / f"{id}.png", dpi=120)
    plt.close(fig)
    gt["id"] = id
    gt["metaAnalysisCriteria"] = MA_CRITERIA
    gt.setdefault("flags", [])
    gt.setdefault("panelCount", 1)
    (OUT / f"{id}.json").write_text(json.dumps(gt, indent=2))
    entries.append({k: gt[k] for k in ("id", "charType", "extractDecision")})


def add(id, build, gt):
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    build(ax)
    _save(fig, id, gt)


def add_fig(id, build, gt):  # builder gets the whole figure (multi-panel / twin axes)
    fig = plt.figure(figsize=(6.4, 4.6))
    build(fig)
    _save(fig, id, gt)


# ---- 1. simple bar (error bars are SEM — caption-only) ----
def bar(ax):
    g = ["Placebo", "Drug X"]; m = [312, 241]; se = [21, 19]
    ax.bar(g, m, yerr=se, capsize=6, color=["#4477aa", "#ee6677"])
    ax.set_xlabel("Group"); ax.set_ylabel("Plasma cortisol (nmol/L)"); ax.set_title("Post-treatment cortisol")
add("01_bar", bar, {
    "charType": "bar",
    "axes": {"x": {"label": "Group", "scale": "categorical"}, "y": {"label": "Plasma cortisol", "unit": "nmol/L", "scale": "linear"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "dispersionType": "SEM", "dispersionVisibleInImage": False, "nPerGroup": {"Placebo": 24, "Drug X": 26},
    "encodes": ["mean", "dispersion"], "extractionMethod": "bar-endpoints",
    "caption": "Figure 2. Post-treatment plasma cortisol (mean ± SEM). n=24 placebo, 26 Drug X. *p<0.01.",
    "articleContext": "RCT of Drug X vs placebo for chronic stress; primary outcome plasma cortisol at 8 weeks.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome (cortisol) for Drug X vs placebo; SEM+n -> SD."})


# ---- 2. grouped bar (SD error bars) ----
def gbar(ax):
    t = np.arange(3); w = 0.35
    ax.bar(t - w/2, [300, 305, 310], w, yerr=[25, 24, 26], capsize=4, label="Placebo", color="#4477aa")
    ax.bar(t + w/2, [298, 270, 232], w, yerr=[24, 23, 22], capsize=4, label="Drug X", color="#ee6677")
    ax.set_xticks(t); ax.set_xticklabels(["Baseline", "Week 4", "Week 8"])
    ax.set_xlabel("Timepoint"); ax.set_ylabel("Cortisol (nmol/L)"); ax.legend()
add("02_grouped_bar", gbar, {
    "charType": "grouped-bar",
    "axes": {"x": {"label": "Timepoint", "scale": "categorical", "categories": ["Baseline", "Week 4", "Week 8"]},
             "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "dispersionType": "SD", "dispersionVisibleInImage": False, "nPerGroup": {"Placebo": 24, "Drug X": 26},
    "encodes": ["mean", "dispersion"], "extractionMethod": "bar-endpoints",
    "caption": "Figure 3. Cortisol over time (mean ± SD) for placebo vs Drug X.",
    "articleContext": "Same RCT; secondary time-course analysis of the primary biomarker.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome over time; use Week 8 means/SD/n."})


# ---- 3. stacked bar (categorical proportions) ----
def sbar(ax):
    g = ["Placebo", "Drug X"]; resp = np.array([[.4, .5], [.35, .3], [.25, .2]])
    b = np.zeros(2)
    for i, lab in enumerate(["None", "Partial", "Full"]):
        ax.bar(g, resp[i], bottom=b, label=lab); b += resp[i]
    ax.set_ylabel("Proportion of patients"); ax.set_xlabel("Group"); ax.legend(title="Response")
add("03_stacked_bar", sbar, {
    "charType": "stacked-bar",
    "axes": {"x": {"label": "Group", "scale": "categorical"}, "y": {"label": "Proportion", "scale": "linear"}},
    "series": [{"name": "None"}, {"name": "Partial"}, {"name": "Full"}],
    "encodes": ["proportion"], "extractionMethod": "segment-boundary",
    "caption": "Figure 4. Distribution of clinical response category by group.",
    "articleContext": "Same RCT; categorical responder analysis.",
    "extractDecision": "skip",
    "extractReason": "Categorical response, not the continuous cortisol outcome the MA targets."})


# ---- 4. histogram (single group) ----
def hist(ax):
    ax.hist(RNG.normal(46, 11, 220), bins=18, color="#66aa77", edgecolor="white")
    ax.set_xlabel("Age (years)"); ax.set_ylabel("Count")
add("04_histogram", hist, {
    "charType": "histogram",
    "axes": {"x": {"label": "Age", "unit": "years", "scale": "linear"}, "y": {"label": "Count", "scale": "linear"}},
    "encodes": ["count"], "extractionMethod": "bar-endpoints",
    "caption": "Figure 1. Age distribution of the enrolled cohort (N=220).",
    "articleContext": "Baseline characteristics of the trial cohort.",
    "extractDecision": "skip",
    "extractReason": "Single-group baseline demographic, not a between-group outcome."})


# ---- 5. line (time course, two arms) ----
def line(ax):
    x = np.arange(0, 9);
    ax.errorbar(x, 300 - 2*x, yerr=8, marker="o", label="Placebo", color="#4477aa")
    ax.errorbar(x, 300 - 9*x, yerr=8, marker="s", label="Drug X", color="#ee6677")
    ax.set_xlabel("Week"); ax.set_ylabel("Cortisol (nmol/L)"); ax.legend()
add("05_line", line, {
    "charType": "line",
    "axes": {"x": {"label": "Week", "scale": "linear"}, "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "dispersionType": "SEM", "dispersionVisibleInImage": False,
    "encodes": ["mean", "dispersion"], "extractionMethod": "auto_trace",
    "caption": "Figure 3. Mean (± SEM) cortisol trajectory by arm over 8 weeks (n=24/26).",
    "articleContext": "Same RCT; longitudinal primary-outcome trajectory.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome trajectory; read Week 8 endpoint."})


# ---- 6. scatter (correlation) ----
def scat(ax):
    x = RNG.normal(50, 10, 60); y = 0.8*x + RNG.normal(0, 12, 60) + 40
    ax.scatter(x, y, s=18, color="#8844aa"); ax.set_xlabel("Age (years)"); ax.set_ylabel("Baseline cortisol (nmol/L)")
add("06_scatter", scat, {
    "charType": "scatter",
    "axes": {"x": {"label": "Age", "unit": "years", "scale": "linear"}, "y": {"label": "Baseline cortisol", "unit": "nmol/L", "scale": "linear"}},
    "encodes": ["raw-points", "correlation"], "extractionMethod": "digitize_points",
    "caption": "Figure 5. Correlation between age and baseline cortisol (r=0.62).",
    "articleContext": "Exploratory baseline correlation.",
    "extractDecision": "skip",
    "extractReason": "Correlation, not a Drug-X-vs-placebo continuous outcome comparison."})


# ---- 7. box plot ----
def box(ax):
    data = [RNG.normal(300, 40, 40), RNG.normal(240, 38, 40)]
    ax.boxplot(data, tick_labels=["Placebo", "Drug X"]); ax.set_ylabel("Cortisol (nmol/L)"); ax.set_xlabel("Group")
add("07_box", box, {
    "charType": "box",
    "axes": {"x": {"label": "Group", "scale": "categorical"}, "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "encodes": ["median", "dispersion"], "dispersionType": "IQR", "extractionMethod": "box-landmarks",
    "caption": "Figure 2. Cortisol by group shown as median, IQR and range (n=24/26).",
    "articleContext": "Same RCT; robust summary of the primary outcome.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome; median/IQR/n -> mean/SD (Wan 2014)."})


# ---- 8. violin ----
def violin(ax):
    data = [RNG.normal(300, 40, 80), RNG.normal(245, 36, 80)]
    ax.violinplot(data, showmedians=True); ax.set_xticks([1, 2]); ax.set_xticklabels(["Placebo", "Drug X"])
    ax.set_ylabel("Cortisol (nmol/L)"); ax.set_xlabel("Group")
add("08_violin", violin, {
    "charType": "violin",
    "axes": {"x": {"label": "Group", "scale": "categorical"}, "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "encodes": ["median", "density"], "extractionMethod": "box-landmarks",
    "caption": "Figure 2. Cortisol distribution by arm (violin with median line; n=24/26).",
    "articleContext": "Same RCT; distributional view of the primary outcome.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome; median + spread extractable."})


# ---- 9. forest plot ----
def forest(ax):
    studies = ["Ahn 2019", "Bell 2020", "Cruz 2021", "Diaz 2022", "Pooled"]
    est = [-0.6, -0.3, -0.8, -0.45, -0.52]; lo = [-1.0, -0.7, -1.2, -0.8, -0.7]; hi = [-0.2, 0.1, -0.4, -0.1, -0.34]
    y = np.arange(len(studies))[::-1]
    for yi, e, l, h in zip(y, est, lo, hi):
        ax.plot([l, h], [yi, yi], "k-"); ax.plot(e, yi, "s", color="#333", ms=8 if yi > 0 else 11)
    ax.axvline(0, ls="--", color="#999"); ax.set_yticks(y); ax.set_yticklabels(studies)
    ax.set_xlabel("Standardized mean difference (95% CI)")
add("09_forest", forest, {
    "charType": "forest",
    "axes": {"x": {"label": "Standardized mean difference", "scale": "linear"}, "y": {"label": "Study", "scale": "categorical"}},
    "encodes": ["effect-size", "dispersion"], "dispersionType": "CI95", "extractionMethod": "forest-rows",
    "caption": "Figure 6. Forest plot of SMD (Drug X vs placebo) on cortisol across trials; pooled SMD -0.52 (95% CI -0.70, -0.34).",
    "articleContext": "A prior meta-analysis of Drug X on cortisol.",
    "extractDecision": "extract",
    "extractReason": "Per-study standardized effect sizes with CIs — directly meta-analyzable."})


# ---- 10. kaplan-meier ----
def km(ax):
    t = np.linspace(0, 24, 25)
    ax.step(t, np.clip(1 - t/40, 0, 1), where="post", label="Placebo", color="#4477aa")
    ax.step(t, np.clip(1 - t/70, 0, 1), where="post", label="Drug X", color="#ee6677")
    ax.set_xlabel("Months"); ax.set_ylabel("Survival probability"); ax.set_ylim(0, 1); ax.legend()
add("10_kaplan_meier", km, {
    "charType": "kaplan-meier",
    "axes": {"x": {"label": "Months", "scale": "time"}, "y": {"label": "Survival probability", "scale": "probability"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "encodes": ["survival"], "extractionMethod": "auto_trace",
    "caption": "Figure 7. Kaplan-Meier overall survival by arm (HR 0.71).",
    "articleContext": "Same trial; survival is a secondary endpoint.",
    "extractDecision": "skip",
    "extractReason": "Time-to-event outcome, not the continuous cortisol outcome the MA targets."})


# ---- 11. pie ----
def pie(ax):
    ax.pie([45, 30, 15, 10], labels=["None", "Mild", "Moderate", "Severe"], autopct="%1.0f%%")
    ax.set_title("Adverse events")
add("11_pie", pie, {
    "charType": "pie",
    "axes": {}, "encodes": ["proportion"], "extractionMethod": "angle-digitizer",
    "caption": "Figure 8. Distribution of adverse-event severity in the Drug X arm.",
    "articleContext": "Safety analysis.",
    "extractDecision": "skip",
    "extractReason": "Categorical safety proportions, not the continuous efficacy outcome."})


# ---- 12. heatmap ----
def heat(ax):
    m = RNG.uniform(-1, 1, (6, 6)); m = (m + m.T) / 2; np.fill_diagonal(m, 1)
    im = ax.imshow(m, cmap="coolwarm", vmin=-1, vmax=1); ax.figure.colorbar(im, ax=ax)
    ax.set_title("Biomarker correlation matrix")
add("12_heatmap", heat, {
    "charType": "heatmap",
    "axes": {"x": {"label": "Biomarker", "scale": "categorical"}, "y": {"label": "Biomarker", "scale": "categorical"}},
    "encodes": ["correlation"], "extractionMethod": "colorbar-calibration",
    "caption": "Figure 9. Pairwise correlations among baseline biomarkers.",
    "articleContext": "Exploratory baseline biomarker structure.",
    "extractDecision": "skip",
    "extractReason": "Correlation matrix, not a between-group outcome comparison."})


# ---- 13. ROC ----
def roc(ax):
    fpr = np.linspace(0, 1, 50); tpr = fpr ** 0.35
    ax.plot(fpr, tpr, color="#cc5500"); ax.plot([0, 1], [0, 1], "k--")
    ax.set_xlabel("1 - Specificity"); ax.set_ylabel("Sensitivity"); ax.set_title("ROC (AUC 0.81)")
add("13_roc", roc, {
    "charType": "roc",
    "axes": {"x": {"label": "1 - Specificity", "scale": "probability"}, "y": {"label": "Sensitivity", "scale": "probability"}},
    "encodes": ["raw-points"], "extractionMethod": "auto_trace",
    "caption": "Figure 10. ROC curve for cortisol as a diagnostic marker (AUC 0.81).",
    "articleContext": "Diagnostic accuracy sub-analysis.",
    "extractDecision": "skip",
    "extractReason": "Diagnostic accuracy, not a Drug-X-vs-placebo outcome effect."})


# ---- 14. bland-altman ----
def ba(ax):
    mean = RNG.normal(300, 30, 60); diff = RNG.normal(2, 12, 60)
    ax.scatter(mean, diff, s=16, color="#227766")
    ax.axhline(diff.mean(), color="#333"); ax.axhline(diff.mean() + 1.96*diff.std(), ls="--", color="#999")
    ax.axhline(diff.mean() - 1.96*diff.std(), ls="--", color="#999")
    ax.set_xlabel("Mean of methods (nmol/L)"); ax.set_ylabel("Difference (nmol/L)")
add("14_bland_altman", ba, {
    "charType": "bland-altman",
    "axes": {"x": {"label": "Mean of methods", "unit": "nmol/L", "scale": "linear"}, "y": {"label": "Difference", "unit": "nmol/L", "scale": "linear"}},
    "encodes": ["raw-points"], "extractionMethod": "digitize_points",
    "caption": "Figure 11. Bland-Altman agreement between two cortisol assays.",
    "articleContext": "Assay validation sub-study.",
    "extractDecision": "skip",
    "extractReason": "Method-agreement, not a treatment-effect outcome."})


# ---- 15. flow diagram (CONSORT) ----
def flow(ax):
    ax.axis("off")
    boxes = [("Assessed n=310", .5, .9), ("Randomized n=260", .5, .65),
             ("Placebo n=130", .28, .4), ("Drug X n=130", .72, .4),
             ("Analyzed n=124", .28, .12), ("Analyzed n=126", .72, .12)]
    for t, x, y in boxes:
        ax.add_patch(plt.Rectangle((x-.16, y-.05), .32, .1, fill=False))
        ax.text(x, y, t, ha="center", va="center", fontsize=9)
    for (x0, y0, x1, y1) in [(.5, .85, .5, .70), (.5, .60, .28, .45), (.5, .60, .72, .45), (.28, .35, .28, .17), (.72, .35, .72, .17)]:
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="->"))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
add("15_flow_diagram", flow, {
    "charType": "flow-diagram",
    "axes": {}, "encodes": [], "extractionMethod": "not_extractable",
    "caption": "Figure 1. CONSORT participant flow diagram.",
    "articleContext": "Trial profile / enrollment.",
    "extractDecision": "skip",
    "extractReason": "Participant-flow schematic; no numeric outcome to extract."})


# ===== Hard cases (stress the flags) =====

# ---- 16. log-scale line ----
def logline(ax):
    x = np.arange(1, 9)
    ax.semilogy(x, 1000 * np.exp(-0.5 * x), "o-", label="Placebo", color="#4477aa")
    ax.semilogy(x, 1000 * np.exp(-0.9 * x), "s-", label="Drug X", color="#ee6677")
    ax.set_xlabel("Week"); ax.set_ylabel("Viral load (copies/mL, log)"); ax.legend()
add("16_log_line", logline, {
    "charType": "line",
    "axes": {"x": {"label": "Week", "scale": "linear"}, "y": {"label": "Viral load", "unit": "copies/mL", "scale": "log"}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "encodes": ["mean"], "extractionMethod": "auto_trace", "flags": ["log-axis"],
    "caption": "Figure 4. Mean viral load (log10 scale) by arm over 8 weeks (n=30/30).",
    "articleContext": "Same RCT; a log-scaled continuous outcome.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome; must digitize on a LOG y-axis."})


# ---- 17. broken-axis bar ----
def brokenbar(ax):
    g = ["Placebo", "Drug X"]; ax.bar(g, [318, 244], yerr=[22, 20], capsize=6, color=["#4477aa", "#ee6677"])
    ax.set_ylim(200, 360)  # axis does NOT start at 0 -> misleading bar heights
    ax.plot([-.4, .1], [206, 210], "k-", lw=1, clip_on=False); ax.plot([-.4, .1], [204, 208], "k-", lw=1, clip_on=False)
    ax.set_xlabel("Group"); ax.set_ylabel("Cortisol (nmol/L)"); ax.set_title("Note: y-axis begins at 200")
add("17_broken_axis_bar", brokenbar, {
    "charType": "bar",
    "axes": {"x": {"label": "Group", "scale": "categorical"}, "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear", "brokenAxis": True}},
    "series": [{"name": "Placebo", "role": "control"}, {"name": "Drug X", "role": "intervention"}],
    "dispersionType": "SD", "encodes": ["mean", "dispersion"], "extractionMethod": "bar-endpoints",
    "flags": ["broken-axis"],
    "caption": "Figure 2. Post-treatment cortisol (mean ± SD); note truncated y-axis (starts at 200).",
    "articleContext": "Same RCT; a truncated-axis presentation of the primary outcome.",
    "extractDecision": "extract",
    "extractReason": "Between-group continuous outcome; extract but flag the truncated y-axis (read absolute values, not bar heights)."})


# ---- 18. dual y-axis ----
def dualy(ax):
    x = np.arange(0, 9)
    ax.plot(x, 300 - 8 * x, "o-", color="#4477aa"); ax.set_ylabel("Cortisol (nmol/L)", color="#4477aa")
    ax2 = ax.twinx(); ax2.plot(x, 20 + 3 * x, "s--", color="#cc6600"); ax2.set_ylabel("Symptom score", color="#cc6600")
    ax.set_xlabel("Week")
add("18_dual_y", dualy, {
    "charType": "line",
    "axes": {"x": {"label": "Week", "scale": "linear"}, "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear"},
             "y2": {"label": "Symptom score", "scale": "linear"}},
    "series": [{"name": "Cortisol"}, {"name": "Symptom score"}],
    "encodes": ["mean"], "extractionMethod": "auto_trace", "flags": ["dual-y-axis"],
    "caption": "Figure 5. Drug X arm: cortisol (left axis) and symptom score (right axis) over time.",
    "articleContext": "Same RCT; two outcomes on twin axes for the Drug X arm.",
    "extractDecision": "skip",
    "extractReason": "Single-arm (Drug X only) dual-axis plot; no placebo comparison for the outcome."})


# ---- 19. many overlapping series ----
def manyseries(ax):
    x = np.arange(0, 9)
    for i, c in enumerate(["#4477aa", "#ee6677", "#66aa55", "#cc8800", "#8844aa"]):
        ax.plot(x, 300 - (3 + i) * x + RNG.normal(0, 3, 9), "-", color=c, label=f"Dose {i+1}")
    ax.set_xlabel("Week"); ax.set_ylabel("Cortisol (nmol/L)"); ax.legend(fontsize=7, ncol=2)
add("19_many_series_line", manyseries, {
    "charType": "line",
    "axes": {"x": {"label": "Week", "scale": "linear"}, "y": {"label": "Cortisol", "unit": "nmol/L", "scale": "linear"}},
    "series": [{"name": f"Dose {i+1}"} for i in range(5)],
    "encodes": ["mean"], "extractionMethod": "auto_trace", "flags": ["overlapping-series"],
    "caption": "Figure 6. Cortisol trajectories across five Drug X doses (no placebo arm).",
    "articleContext": "Dose-ranging sub-study of Drug X.",
    "extractDecision": "skip",
    "extractReason": "Dose-ranging within Drug X only; no Drug-X-vs-placebo comparison."})


# ---- 20. multi-panel 2x2 (mixed types) ----
def multipanel(fig):
    axs = fig.subplots(2, 2)
    axs[0, 0].bar(["P", "D"], [300, 240], yerr=[20, 18], capsize=4, color=["#4477aa", "#ee6677"]); axs[0, 0].set_title("A", loc="left")
    xx = np.arange(9); axs[0, 1].plot(xx, 300 - 8 * xx, "o-"); axs[0, 1].set_title("B", loc="left")
    axs[1, 0].scatter(RNG.normal(50, 10, 40), RNG.normal(250, 30, 40), s=10); axs[1, 0].set_title("C", loc="left")
    axs[1, 1].boxplot([RNG.normal(300, 40, 30), RNG.normal(240, 36, 30)], tick_labels=["P", "D"]); axs[1, 1].set_title("D", loc="left")
add_fig("20_multi_panel", multipanel, {
    "charType": "other", "panelCount": 4,
    "panels": [{"panelLabel": "A", "charType": "bar"}, {"panelLabel": "B", "charType": "line"},
               {"panelLabel": "C", "charType": "scatter"}, {"panelLabel": "D", "charType": "box"}],
    "encodes": ["mean", "median"], "extractionMethod": "not_extractable", "flags": ["multi-panel"],
    "caption": "Figure 3. (A) cortisol by arm, (B) trajectory, (C) age vs cortisol, (D) cortisol distribution.",
    "articleContext": "Same RCT; composite results figure.",
    "extractDecision": "extract",
    "extractReason": "Multi-panel: split into panels first; panels A/B/D carry the between-group outcome."})


(OUT / "manifest.json").write_text(json.dumps({
    "metaAnalysisCriteria": MA_CRITERIA, "count": len(entries), "entries": entries
}, indent=2))
print(f"Wrote {len(entries)} charts to {OUT}")
for e in entries:
    print(f"  {e['id']:22s} {e['charType']:15s} -> {e['extractDecision']}")
