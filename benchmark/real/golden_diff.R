#!/usr/bin/env Rscript
# golden_diff.R -- the END-TO-END real-figure golden diff.
#
# Question: if we replace the human's figure-digitized Control/Treatment mean+SD+n with an
# AUTOMATED reader's numbers, does the meta-analytic result move? We answer it the way the
# dissertation does its stats (metafor: escalc -> rma), run TWICE -- once on the hand-coded
# numbers, once on the extracted numbers -- and diff the pooled effect, its CI, and tau^2/I^2.
#
# Input : out/comparisons.csv (from score_real.py) -- per comparison, the coded and extracted
#         control/intervention mean, SD, n.
# escalc: measure="SMD" (bias-corrected Hedges g), computed by metafor for BOTH datasets, so
#         the ONLY thing that differs between the two pooled fits is the figure-reading.
# model : random-effects rma (pilot n is small; a 3-level rma.mv(~1|article/row) is used when
#         there are >=2 articles with >=2 rows, else falls back to rma()).
#
# Output: out/golden_diff.txt (printed) + out/golden_diff.csv (per-study coded vs extracted g).

suppressMessages(library(metafor))
here <- dirname(sub("--file=", "", grep("--file=", commandArgs(FALSE), value = TRUE)))
if (length(here) == 0) here <- "."
csv <- file.path(here, "out", "comparisons.csv")
d <- read.csv(csv, stringsAsFactors = FALSE)
cat(sprintf("Real-figure golden diff: %d comparisons from %d articles\n\n",
            nrow(d), length(unique(d$article))))

esc <- function(m1, sd1, n1, m2, sd2, n2) {
  # SMD = standardized mean difference, intervention(2) - control(1), Hedges g.
  escalc(measure = "SMD", m1i = m2, sd1i = sd2, n1i = n2,
         m2i = m1, sd2i = sd1, n2i = n1)
}
cod <- esc(d$c_mean_coded, d$c_sd_coded, d$c_n, d$i_mean_coded, d$i_sd_coded, d$i_n)
ext <- esc(d$c_mean_ext,   d$c_sd_ext,   d$c_n, d$i_mean_ext,   d$i_sd_ext,   d$i_n)

d$g_coded <- cod$yi; d$vi_coded <- cod$vi
d$g_ext   <- ext$yi; d$vi_ext   <- ext$vi
d$g_abs_diff <- abs(d$g_ext - d$g_coded)

fit <- function(yi, vi, art) {
  ok <- length(unique(art)) >= 2 && all(table(art) >= 1)
  m <- tryCatch(
    rma.mv(yi, vi, random = ~ 1 | art/inner, data = data.frame(yi, vi, art, inner = seq_along(yi))),
    error = function(e) NULL)
  if (is.null(m)) m <- rma(yi, vi, method = "REML")
  m
}
mc <- fit(cod$yi, cod$vi, d$article)
me <- fit(ext$yi, ext$vi, d$article)

row1 <- function(tag, m) {
  ci <- c(m$ci.lb, m$ci.ub)
  tau2 <- if (!is.null(m$tau2)) sum(m$tau2) else NA
  sprintf("%-10s g=%+.3f  SE=%.3f  95%% CI [%+.3f, %+.3f]  p=%.4f  tau^2=%.3f",
          tag, as.numeric(m$b)[1], m$se[1], ci[1], ci[2], m$pval[1], tau2)
}
out <- c(
  "=== Pooled effect: hand-coded vs automated-extracted (same escalc + model) ===",
  row1("CODED", mc),
  row1("EXTRACTED", me),
  sprintf("delta(pooled g)      = %+.4f", as.numeric(me$b)[1] - as.numeric(mc$b)[1]),
  sprintf("delta(CI width)      = %+.4f", (me$ci.ub - me$ci.lb) - (mc$ci.ub - mc$ci.lb)),
  "",
  sprintf("per-study |g_ext - g_coded|: median=%.3f  mean=%.3f  max=%.3f",
          median(d$g_abs_diff), mean(d$g_abs_diff), max(d$g_abs_diff)),
  sprintf("sign flips (effect direction changed): %d / %d",
          sum(sign(d$g_ext) != sign(d$g_coded)), nrow(d)),
  "",
  "Interpretation: a small delta(pooled g) with overlapping CIs means the automated read",
  "reproduces the hand-coded meta-analytic conclusion; per-study |dg| localizes where",
  "figure-reading (dispersion-channel) error would perturb individual study weights."
)
cat(paste(out, collapse = "\n"), "\n")
writeLines(out, file.path(here, "out", "golden_diff.txt"))
write.csv(d[, c("id","row_id","article","g_coded","vi_coded","g_ext","vi_ext","g_abs_diff")],
          file.path(here, "out", "golden_diff.csv"), row.names = FALSE)
cat(sprintf("\n[written] %s\n[written] %s\n",
            file.path(here, "out", "golden_diff.txt"), file.path(here, "out", "golden_diff.csv")))
