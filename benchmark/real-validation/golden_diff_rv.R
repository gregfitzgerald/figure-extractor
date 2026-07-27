#!/usr/bin/env Rscript
# golden_diff_rv.R -- the END-TO-END test that matters, at scale.
#
# Question: if the automated read replaces the human's figure digitization, does the
# meta-analytic CONCLUSION change? Answered the way the dissertation does its own stats,
# run on the SAME rows with the SAME code, so the only thing differing between fits is
# the figure reading.
#
# Three readings are fitted, not two (ANALYSIS-PLAN sec.1.2 / 6.3):
#   D  the historical dissertation extraction (years ago, different tool)
#   G  Greg's fresh blind annotation
#   M  the machine
# and the pairwise deltas are reported as a TRIANGLE. The claim the project exists to
# make is delta(M,G) <= delta(D,G): the machine differs from the human no more than the
# same human differs from himself on another occasion. That is a statement the data can
# support; "the machine is more accurate" is not (no oracle exists on a real figure).
#
# Input : out/comparisons.csv, written by score_real_validation.py.
# Model : escalc(measure="SMD") -> Hedges g, then the dissertation's own multi-arm
#         variance inflation, then rma.mv(~1 | article/comparison). Falls back to rma()
#         only when the multilevel model is singular, and says so.
#
# Pre-specified thresholds (ANALYSIS-PLAN sec.6.2) are checked mechanically at the end
# so the decision cannot be re-argued after seeing the numbers.

suppressMessages(library(metafor))

here <- dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)))
if (length(here) == 0) here <- "."
csv <- file.path(here, "out", "comparisons.csv")
if (!file.exists(csv)) {
  cat("no", csv, "-- run score_real_validation.py first\n"); quit(status = 0)
}
d <- read.csv(csv, stringsAsFactors = FALSE)

# ---- pre-specified thresholds ------------------------------------------------
TH <- list(absDeltaG = 0.05, relDeltaG = 0.10, ciOverlap = 0.90,
           tau2Lo = 0.80, tau2Hi = 1.25, i2AbsPP = 10,
           medianAbsDg = 0.05, maxAbsDg = 0.30, weightRho = 0.95,
           tostMargin = 0.10)

have <- function(tag) {
  cols <- paste0(c("c_mean_", "c_sd_", "i_mean_", "i_sd_"), tag)
  all(cols %in% names(d)) && all(c("c_n", "i_n") %in% names(d)) &&
    sum(stats::complete.cases(d[, c(cols, "c_n", "i_n")])) >= 3
}
arms <- Filter(have, c("D", "G", "M"))
if (length(arms) < 2) {
  cat("need at least two complete readings among D/G/M; have:",
      paste(arms, collapse = ", "), "\n"); quit(status = 0)
}
keep <- Reduce(`&`, lapply(arms, function(t)
  stats::complete.cases(d[, paste0(c("c_mean_", "c_sd_", "i_mean_", "i_sd_"), t)])))
keep <- keep & stats::complete.cases(d[, c("c_n", "i_n")])
d <- d[keep, , drop = FALSE]
if (!"vifMultiarm" %in% names(d)) d$vifMultiarm <- 1
d$vifMultiarm[is.na(d$vifMultiarm)] <- 1
if (!"article" %in% names(d)) d$article <- "unknown"
if (!"comparisonId" %in% names(d)) d$comparisonId <- seq_len(nrow(d))
lower <- grepl("^lower", tolower(ifelse(is.na(d$direction), "", d$direction)))

cat(sprintf("Real-figure golden diff: %d comparisons, %d articles, readings: %s\n\n",
            nrow(d), length(unique(d$article)), paste(arms, collapse = " / ")))

es <- function(tag) {
  # SMD = intervention - control, bias-corrected (Hedges g). Direction is a CODED field
  # and is applied identically to every arm; it fixes outcome polarity, never arm order,
  # and cannot rescue a swapped assignment.
  x <- escalc(measure = "SMD",
              m1i = d[[paste0("i_mean_", tag)]], sd1i = d[[paste0("i_sd_", tag)]], n1i = d$i_n,
              m2i = d[[paste0("c_mean_", tag)]], sd2i = d[[paste0("c_sd_", tag)]], n2i = d$c_n)
  yi <- as.numeric(x$yi); yi[lower] <- -yi[lower]
  # the dissertation's own shared-control correction, applied identically to every arm
  list(yi = yi, vi = as.numeric(x$vi) * d$vifMultiarm)
}

fit <- function(e) {
  dat <- data.frame(yi = e$yi, vi = e$vi, art = d$article, inner = d$comparisonId)
  m <- tryCatch(rma.mv(yi, vi, random = ~ 1 | art/inner, data = dat, method = "REML"),
                error = function(x) NULL, warning = function(x) NULL)
  if (is.null(m)) {
    m <- rma(e$yi, e$vi, method = "REML"); attr(m, "fallback") <- TRUE
  }
  m
}

E <- lapply(arms, es); names(E) <- arms
F <- lapply(E, fit)
tau2 <- function(m) if (!is.null(m$tau2)) sum(m$tau2) else NA_real_
# a ratio of two zero heterogeneities is 1 (unchanged), not NaN -- both fits agree that
# there is none, which is exactly what the threshold is asking about
tau2ratio <- function(a, b) {
  ta <- tau2(a); tb <- tau2(b)
  if (is.na(ta) || is.na(tb)) return(NA_real_)
  if (ta < 1e-10 && tb < 1e-10) return(1)
  if (ta < 1e-10) return(Inf)
  tb / ta
}
i2   <- function(m) if (!is.null(m$I2)) m$I2 else NA_real_

L <- c("=== Pooled effect, one fit per reading (identical escalc + model) ===")
for (t in arms) {
  m <- F[[t]]
  L <- c(L, sprintf("%-10s g=%+.3f  SE=%.3f  95%% CI [%+.3f, %+.3f]  p=%.4f  tau^2=%.4f%s",
                    t, as.numeric(m$b)[1], m$se[1], m$ci.lb[1], m$ci.ub[1], m$pval[1],
                    tau2(m), if (isTRUE(attr(m, "fallback"))) "  [rma fallback: mv singular]" else ""))
}

ovl <- function(a, b) {
  lo <- max(a$ci.lb[1], b$ci.lb[1]); hi <- min(a$ci.ub[1], b$ci.ub[1])
  u_lo <- min(a$ci.lb[1], b$ci.lb[1]); u_hi <- max(a$ci.ub[1], b$ci.ub[1])
  max(0, hi - lo) / (u_hi - u_lo)
}

L <- c(L, "", "=== Pairwise triangle: does swapping the reading move the conclusion? ===")
pairs <- list()
for (i in seq_along(arms)) for (j in seq_along(arms)) if (i < j) {
  a <- arms[i]; b <- arms[j]
  dg <- abs(E[[a]]$yi - E[[b]]$yi)
  flips <- sum(sign(E[[a]]$yi) != sign(E[[b]]$yi))
  wa <- 1 / E[[a]]$vi; wb <- 1 / E[[b]]$vi
  rho <- suppressWarnings(cor(wa, wb, method = "spearman"))
  delta <- as.numeric(F[[b]]$b)[1] - as.numeric(F[[a]]$b)[1]
  pairs[[paste0(b, "-", a)]] <- list(delta = delta, dg = dg, flips = flips, rho = rho,
                                     ovl = ovl(F[[a]], F[[b]]),
                                     t2 = tau2ratio(F[[a]], F[[b]]),
                                     i2 = i2(F[[b]]) - i2(F[[a]]))
  L <- c(L, sprintf(
    "%-6s delta(pooled g)=%+.4f  CI overlap=%.2f  tau^2 ratio=%.2f  dI^2=%+.1fpp  |dg| med=%.3f max=%.3f  sign flips=%d/%d  weight rho=%.3f",
    paste0(b, "-", a), delta, ovl(F[[a]], F[[b]]), tau2ratio(F[[a]], F[[b]]),
    i2(F[[b]]) - i2(F[[a]]), median(dg), max(dg), flips, length(dg), rho))
}

# ---- cluster bootstrap on the M-vs-G delta (paired rows; articles are the cluster) ----
if (all(c("M", "G") %in% arms)) {
  arts <- unique(d$article); B <- 2000; set.seed(17); bs <- numeric(0)
  for (b in seq_len(B)) {
    idx <- unlist(lapply(sample(arts, length(arts), replace = TRUE),
                         function(a) which(d$article == a)))
    fm <- tryCatch(rma(E[["M"]]$yi[idx], E[["M"]]$vi[idx], method = "REML"),
                   error = function(x) NULL)
    fg <- tryCatch(rma(E[["G"]]$yi[idx], E[["G"]]$vi[idx], method = "REML"),
                   error = function(x) NULL)
    if (!is.null(fm) && !is.null(fg))
      bs <- c(bs, as.numeric(fm$b)[1] - as.numeric(fg$b)[1])
  }
  if (length(bs) > 50) {
    ci <- quantile(bs, c(.025, .975))
    tost <- (ci[1] > -TH$tostMargin) && (ci[2] < TH$tostMargin)
    L <- c(L, "", sprintf(
      "cluster bootstrap (articles, B=%d) on delta(M-G): %+.4f  95%% CI [%+.4f, %+.4f]",
      length(bs), mean(bs), ci[1], ci[2]),
      sprintf("TOST equivalence at margin +/-%.2f: %s", TH$tostMargin,
              if (tost) "PASS -- the two readings are interchangeable" else "FAIL"))
  }
}

# ---- pre-specified gate check -------------------------------------------------
L <- c(L, "", "=== Pre-specified thresholds (ANALYSIS-PLAN sec.6.2) ===")
key <- if (all(c("M", "G") %in% arms)) "M-G" else names(pairs)[1]
if (!is.null(pairs[[key]])) {
  q <- pairs[[key]]
  gref <- abs(as.numeric(F[[sub("^.*-", "", key)]]$b)[1])
  chk <- function(name, ok, val) sprintf("  [%s] %-34s %s", if (ok) "PASS" else "FAIL", name, val)
  L <- c(L,
    sprintf("  (evaluated on %s -- machine vs the fresh human reading)", key),
    chk("|delta pooled g|", abs(q$delta) <= TH$absDeltaG, sprintf("%.4f <= %.2f", abs(q$delta), TH$absDeltaG)),
    chk("|delta| as share of |g|", is.finite(gref) && gref > 0 && abs(q$delta)/gref <= TH$relDeltaG,
        sprintf("%.1f%% <= %.0f%%", 100*abs(q$delta)/max(gref, 1e-9), 100*TH$relDeltaG)),
    chk("CI overlap", q$ovl >= TH$ciOverlap, sprintf("%.2f >= %.2f", q$ovl, TH$ciOverlap)),
    chk("tau^2 ratio", is.finite(q$t2) && q$t2 >= TH$tau2Lo && q$t2 <= TH$tau2Hi,
        sprintf("%.2f in [%.2f, %.2f]", q$t2, TH$tau2Lo, TH$tau2Hi)),
    chk("median |dg|", median(q$dg) <= TH$medianAbsDg, sprintf("%.3f <= %.2f", median(q$dg), TH$medianAbsDg)),
    chk("max |dg|", max(q$dg) <= TH$maxAbsDg, sprintf("%.3f <= %.2f", max(q$dg), TH$maxAbsDg)),
    chk("SIGN FLIPS", q$flips == 0, sprintf("%d / %d  (0 required; 95%% UB with 0 events = %.1f%%)",
                                            q$flips, length(q$dg), 100*3/length(q$dg))),
    chk("study-weight rank rho", is.finite(q$rho) && q$rho >= TH$weightRho,
        sprintf("%.3f >= %.2f", q$rho, TH$weightRho)))
}
L <- c(L, "",
  "Reading the triangle: delta(M-G) <= delta(D-G) means the machine differs from the",
  "human no more than the same human differs from himself years earlier with another",
  "tool -- i.e. the automated read is meta-analytically INTERCHANGEABLE with the human's.",
  "That is an agreement claim. Accuracy on the dispersion channel is established on the",
  "SYNTHETIC benchmark against R's exact descriptives, and (where verified) on the",
  "text-anchored oracle rows -- never from machine-vs-human disagreement.")

cat(paste(L, collapse = "\n"), "\n")
dir.create(file.path(here, "out"), showWarnings = FALSE)
writeLines(L, file.path(here, "out", "golden_diff.txt"))
per <- data.frame(article = d$article, comparisonId = d$comparisonId)
for (t in arms) { per[[paste0("g_", t)]] <- E[[t]]$yi; per[[paste0("vi_", t)]] <- E[[t]]$vi }
write.csv(per, file.path(here, "out", "golden_diff_per_comparison.csv"), row.names = FALSE)
cat(sprintf("\n[written] %s\n[written] %s\n",
            file.path(here, "out", "golden_diff.txt"),
            file.path(here, "out", "golden_diff_per_comparison.csv")))
