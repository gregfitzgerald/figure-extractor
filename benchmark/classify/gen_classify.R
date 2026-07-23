#!/usr/bin/env Rscript
# gen_classify.R -- CHART-TYPE CLASSIFICATION corpus generator.
# ---------------------------------------------------------------------------
# This is the PERCEPTION-GATE corpus: before an extraction agent can read a
# figure's scientific content it must reliably classify WHAT the figure is.
# Unlike ../r/generate.R (which exports landmark-pixel GT for the extraction
# eval), this generator needs NO pixel GT -- just the rendered image plus its
# labels in the figure-extractor CHAR_VOCAB taxonomy:
#     charType, dataProvenance, axis scale (x & y), dispersionPresent (bool),
#     and the nonDataElement ink actually drawn.
#
# Two explicit design requirements are met here:
#   (1) MANY different R graphing libraries, for visual-grammar variety --
#       base graphics, ggplot2, lattice, and the specialist packages
#       (vioplot, plotrix, pheatmap, corrplot, pROC, metafor, forestplot,
#       forestploter, survival, VennDiagram). base R vs ggplot vs lattice
#       look very different; that diversity is the point.
#   (2) A distinct DENSE tier -- every image is rendered in a `plain` and a
#       `dense` variant; dense figures are loaded with axis titles, rich
#       legends, significance stars/brackets, per-group n annotations, panel
#       labels, data-value labels, gridlines, secondary axes -- visually busy,
#       to stress-test whether the model still classifies correctly.
#
#   Run:  Rscript benchmark/classify/gen_classify.R
#         -> benchmark/classify/corpus/<id>.png + <id>.label.json + manifest.json
# ---------------------------------------------------------------------------
suppressWarnings(suppressMessages({
  library(ggplot2); library(grid); library(jsonlite)
}))
have <- function(p) suppressWarnings(requireNamespace(p, quietly = TRUE))

HERE <- tryCatch(dirname(normalizePath(sub("--file=", "",
          grep("--file=", commandArgs(FALSE), value = TRUE)[1]))), error = function(e) ".")
if (is.na(HERE) || HERE == ".") HERE <- file.path(getwd(), "benchmark", "classify")
CORPUS <- normalizePath(file.path(HERE, "corpus"), mustWork = FALSE)
dir.create(CORPUS, showWarnings = FALSE, recursive = TRUE)

# ---- label registry ----------------------------------------------------------
REG <- new.env(); REG$rows <- list(); REG$fail <- character(0)
add_row <- function(id, charType, library, grammar, tier, provenance,
                    scaleX, scaleY, dispersion, nonData) {
  REG$rows[[length(REG$rows) + 1]] <- list(
    id = id, charType = charType, library = library, grammar = grammar,
    tier = tier, dataProvenance = provenance, scaleX = scaleX, scaleY = scaleY,
    dispersionPresent = dispersion, nonDataElements = I(sort(unique(nonData))),
    image = paste0(id, ".png"))
}
open_png <- function(id, W = 720, H = 520, DPI = 100)
  png(file.path(CORPUS, paste0(id, ".png")), width = W, height = H, res = DPI, type = "cairo")

# guarded build: any single figure failing is recorded, not fatal
emit <- function(id, fn) {
  tryCatch({ fn(); TRUE },
    error = function(e) {
      REG$fail <- c(REG$fail, sprintf("%s: %s", id, conditionMessage(e)))
      try(while (dev.cur() > 1) dev.off(), silent = TRUE)
      message(sprintf("  [FAIL] %s -- %s", id, conditionMessage(e))); FALSE })
}

# ---- shared palettes ---------------------------------------------------------
PAL <- if (have("RColorBrewer")) RColorBrewer::brewer.pal(8, "Set2") else palette()
VIR <- if (have("viridisLite")) viridisLite::viridis(8) else heat.colors(8)

# ---- base-graphics dense decorators -----------------------------------------
panel_label_base <- function(lab = "A")
  mtext(lab, side = 3, line = 1.2, adj = 0, cex = 1.4, font = 2)
sig_bracket_base <- function(x1, x2, y, label = "*", drop = NULL) {
  if (is.null(drop)) drop <- (y - graphics::par("usr")[3]) * 0.03
  segments(x1, y, x1, y - drop); segments(x2, y, x2, y - drop); segments(x1, y, x2, y)
  text((x1 + x2) / 2, y, label, pos = 3, cex = 1.2, font = 2, offset = 0.2)
}

# =============================================================================
#  BUILDERS  (each emits a `plain` and a `dense` variant)
# =============================================================================

## ---- BAR (single group, with error bars) -----------------------------------
build_bar_base <- function(idbase, seed = 1) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    grps <- c("Sham", "Model", "Drug"); mu <- c(42, 78, 55); se <- c(5, 8, 6)
    nD <- c("axis-ticks")
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      bp <- barplot(mu, names.arg = grps, col = PAL[1:3], ylim = c(0, 100),
                    ylab = "Grip strength (N)",
                    main = if (tier == "dense") "Forelimb grip strength by group" else NULL,
                    border = "grey20")
      arrows(bp, mu - se, bp, mu + se, angle = 90, code = 3, length = 0.05, lwd = 1.6)
      if (tier == "dense") {
        grid(nx = NA, ny = NULL, col = "grey85"); box()
        title(xlab = "Experimental group")
        sig_bracket_base(bp[1], bp[2], 92, "**")
        sig_bracket_base(bp[2], bp[3], 82, "*")
        text(bp, 4, paste0("n=", c(10, 12, 11)), cex = 0.8)
        text(bp, mu + se + 4, sprintf("%.0f", mu), cex = 0.85, font = 2)
        panel_label_base("A")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "significance-markers", "annotation", "panel-label") else nD
    add_row(id, "bar", "base", "base", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

build_bar_ggplot <- function(idbase, seed = 2) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(grp = factor(c("WT", "KO", "Rescue"), levels = c("WT", "KO", "Rescue")),
                     mu = c(1.9, 3.4, 2.4), se = c(0.25, 0.4, 0.3), n = c(9, 8, 8))
    nD <- c("axis-ticks")
    emit(id, function() {
      p <- ggplot(df, aes(grp, mu, fill = grp)) +
        geom_col(width = 0.65, colour = "grey20") +
        geom_errorbar(aes(ymin = mu - se, ymax = mu + se), width = 0.2, linewidth = 0.7) +
        scale_fill_brewer(palette = "Dark2") +
        labs(y = "Relative mRNA (a.u.)", x = NULL) + theme_classic(base_size = 13) +
        theme(legend.position = "none")
      if (tier == "dense") {
        p <- p + labs(title = "Target gene expression", x = "Genotype",
                      subtitle = "qPCR, mean +/- SEM") +
          theme_bw(base_size = 13) + theme(legend.position = "none") +
          annotate("text", x = 1.5, y = 4.1, label = "**", size = 6) +
          annotate("segment", x = 1, xend = 2, y = 4.0, yend = 4.0) +
          annotate("text", x = df$grp, y = 0.15, label = paste0("n=", df$n), size = 3) +
          annotate("text", x = df$grp, y = df$mu + df$se + 0.18,
                   label = sprintf("%.1f", df$mu), fontface = 2, size = 3.3)
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "significance-markers", "annotation") else nD
    add_row(id, "bar", "ggplot2", "ggplot2", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

## ---- GROUPED BAR ------------------------------------------------------------
build_gbar_base <- function(idbase, seed = 3) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    m <- matrix(c(20, 35, 28, 44, 22, 30), nrow = 2,
                dimnames = list(c("Vehicle", "Treated"), c("D1", "D7", "D14")))
    se <- matrix(c(3, 4, 3, 5, 3, 4), nrow = 2)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, if (tier == "dense") 6 else 2), xpd = tier == "dense")
      bp <- barplot(m, beside = TRUE, col = PAL[c(2, 4)], ylim = c(0, 55),
                    ylab = "Lesion volume (mm3)", xlab = if (tier == "dense") "Day post-injury" else NULL,
                    main = if (tier == "dense") "Lesion volume over time" else NULL, border = "grey20")
      arrows(bp, m - se, bp, m + se, angle = 90, code = 3, length = 0.04, lwd = 1.4)
      legend(if (tier == "dense") "topright" else "topleft", rownames(m), fill = PAL[c(2, 4)],
             bty = "n", inset = if (tier == "dense") c(-0.14, 0) else 0)
      if (tier == "dense") {
        grid(nx = NA, ny = NULL, col = "grey85"); box()
        sig_bracket_base(bp[1, 2], bp[2, 2], 52, "*")
        text(as.vector(bp), 2, paste0("n=", 8), cex = 0.7)
        panel_label_base("B")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "significance-markers", "annotation", "panel-label") else c("axis-ticks", "legend")
    add_row(id, "grouped-bar", "base", "base", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

build_gbar_ggplot <- function(idbase, seed = 4) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- expand.grid(dose = c("0", "1", "10", "100"), arm = c("Placebo", "Active"))
    df$mu <- c(10, 14, 22, 33, 11, 18, 30, 46); df$se <- runif(8, 1.5, 3)
    emit(id, function() {
      p <- ggplot(df, aes(dose, mu, fill = arm)) +
        geom_col(position = position_dodge(0.8), width = 0.7, colour = "grey25") +
        geom_errorbar(aes(ymin = mu - se, ymax = mu + se), position = position_dodge(0.8),
                      width = 0.25) +
        scale_fill_manual(values = PAL[c(6, 3)]) +
        labs(x = "Dose (mg)", y = "Response (%)", fill = "Arm") + theme_minimal(base_size = 13)
      if (tier == "dense") {
        p <- p + labs(title = "Dose x arm response", subtitle = "mean +/- SEM, two-way ANOVA") +
          geom_text(aes(label = sprintf("%.0f", mu), y = mu + se + 1.5),
                    position = position_dodge(0.8), size = 2.6) +
          annotate("text", x = 4, y = 52, label = "*** interaction", fontface = 3, size = 3.2) +
          theme(legend.position = "top", panel.grid.minor = element_line(colour = "grey90"))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "significance-markers", "annotation") else c("axis-ticks", "legend", "gridlines")
    add_row(id, "grouped-bar", "ggplot2", "ggplot2", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

build_gbar_lattice <- function(idbase, seed = 5) {
  if (!have("lattice")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- expand.grid(tp = c("Pre", "Post"), grp = c("Ctrl", "Exp", "Exp2"))
    df$val <- c(30, 25, 32, 41, 29, 38)
    emit(id, function() {
      p <- lattice::barchart(val ~ tp, groups = df$grp, data = df, ylim = c(0, 50),
        ylab = "Firing rate (Hz)", xlab = if (tier == "dense") "Timepoint" else "",
        main = if (tier == "dense") "Firing rate by group" else NULL,
        auto.key = list(space = if (tier == "dense") "right" else "top", columns = if (tier == "dense") 1 else 3),
        par.settings = lattice::simpleTheme(col = PAL[1:3]),
        scales = list(x = list(rot = 0)),
        panel = function(...) { if (tier == "dense") lattice::panel.grid(h = -1, v = 0, col = "grey85"); lattice::panel.barchart(...) })
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title") else c("axis-ticks", "legend")
    add_row(id, "grouped-bar", "lattice", "lattice", tier, "primary", "categorical", "linear", FALSE, nD)
  }
}

## ---- STACKED BAR ------------------------------------------------------------
build_sbar_base <- function(idbase, seed = 6) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    m <- matrix(c(30, 45, 25, 20, 50, 30, 40, 35, 25), nrow = 3,
                dimnames = list(c("G0/G1", "S", "G2/M"), c("Ctrl", "Low", "High")))
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, if (tier == "dense") 6 else 2), xpd = tier == "dense")
      barplot(m, col = VIR[c(1, 4, 7)], ylab = "Cells (%)",
              xlab = if (tier == "dense") "Condition" else NULL,
              main = if (tier == "dense") "Cell-cycle distribution" else NULL, border = "white")
      legend(if (tier == "dense") "topright" else "top", rownames(m), fill = VIR[c(1, 4, 7)],
             bty = "n", inset = if (tier == "dense") c(-0.16, 0) else 0, horiz = tier != "dense")
      if (tier == "dense") { panel_label_base("C"); text(0.7, 50, "n=3 wells", cex = 0.75, pos = 4) }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "title", "annotation", "panel-label") else c("axis-ticks", "legend")
    add_row(id, "stacked-bar", "base", "base", tier, "primary", "categorical", "percent", FALSE, nD)
  }
}

build_sbar_ggplot <- function(idbase, seed = 7) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- expand.grid(site = c("Cortex", "Striatum", "Hippo"),
                      cell = c("Neuron", "Astro", "Micro", "Oligo"))
    df$frac <- c(50, 40, 55, 20, 25, 22, 18, 20, 13, 12, 15, 10)
    emit(id, function() {
      p <- ggplot(df, aes(site, frac, fill = cell)) +
        geom_col(position = "fill", colour = "white") +
        scale_fill_brewer(palette = "Set1") + scale_y_continuous(labels = scales::percent) +
        labs(x = NULL, y = "Proportion", fill = "Cell type") + theme_classic(base_size = 13)
      if (tier == "dense") {
        p <- p + labs(title = "Cellular composition by region", x = "Brain region",
                      subtitle = "snRNA-seq, fraction of nuclei") +
          geom_text(aes(label = paste0(frac, "%")), position = position_fill(vjust = 0.5), size = 2.7) +
          theme(legend.position = "right", panel.grid.major.y = element_line(colour = "grey88"))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "annotation") else c("axis-ticks", "legend")
    add_row(id, "stacked-bar", "ggplot2", "ggplot2", tier, "primary", "categorical", "percent", FALSE, nD)
  }
}

## ---- HISTOGRAM --------------------------------------------------------------
build_hist_base <- function(idbase, seed = 8) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    x <- c(rnorm(320, 65, 12))
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      h <- hist(x, breaks = 22, col = PAL[5], border = "grey30",
                xlab = "Latency (ms)", ylab = "Count",
                main = if (tier == "dense") "Response-latency distribution" else "")
      if (tier == "dense") {
        abline(v = mean(x), col = "red", lwd = 2, lty = 2)
        abline(v = median(x), col = "blue", lwd = 2, lty = 3)
        legend("topright", c("mean", "median"), col = c("red", "blue"), lty = c(2, 3), lwd = 2, bty = "n")
        grid(nx = NA, ny = NULL, col = "grey85")
        text(mean(x), max(h$counts) * 0.95, sprintf("mu=%.1f", mean(x)), pos = 4, cex = 0.8)
        panel_label_base("A")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "reference-line", "annotation", "panel-label") else c("axis-ticks")
    add_row(id, "histogram", "base", "base", tier, "primary", "linear", "linear", FALSE, nD)
  }
}

build_hist_ggplot <- function(idbase, seed = 9) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(v = c(rnorm(260, 20, 4), rnorm(120, 32, 5)))
    emit(id, function() {
      p <- ggplot(df, aes(v)) +
        geom_histogram(bins = 30, fill = PAL[3], colour = "grey30") +
        labs(x = "Soma diameter (um)", y = "Count") + theme_minimal(base_size = 13)
      if (tier == "dense") {
        p <- p + geom_density(aes(y = after_stat(count) * 1.5), colour = "darkred", linewidth = 0.9) +
          geom_vline(xintercept = mean(df$v), linetype = 2, colour = "black") +
          labs(title = "Soma-diameter distribution", subtitle = "n=380 cells, bimodal") +
          annotate("text", x = mean(df$v), y = 30, label = "overall mean", angle = 90, vjust = -0.4, size = 3)
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "reference-line", "trend-line", "annotation") else c("axis-ticks", "gridlines")
    add_row(id, "histogram", "ggplot2", "ggplot2", tier, "primary", "linear", "linear", FALSE, nD)
  }
}

## ---- BOX --------------------------------------------------------------------
build_box_base <- function(idbase, seed = 10) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    dat <- list(Ctrl = rnorm(30, 20, 4), Dose1 = rnorm(30, 26, 5), Dose2 = rnorm(30, 31, 6))
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      boxplot(dat, col = PAL[1:3], ylab = "Path length (m)",
              main = if (tier == "dense") "Morris water-maze path length" else "",
              ylim = c(5, 50))
      if (tier == "dense") {
        stripchart(dat, vertical = TRUE, method = "jitter", pch = 21, bg = "grey40", add = TRUE, cex = 0.7)
        sig_bracket_base(1, 3, 47, "**"); sig_bracket_base(1, 2, 43, "*")
        grid(nx = NA, ny = NULL, col = "grey88")
        text(1:3, 7, paste0("n=", 30), cex = 0.75)
        title(xlab = "Group"); panel_label_base("D")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "significance-markers", "annotation", "raw-points", "panel-label") else c("axis-ticks")
    add_row(id, "box", "base", "base", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

build_box_ggplot <- function(idbase, seed = 11) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(g = rep(c("Young", "Aged", "Aged+Rx"), each = 25),
                     y = c(rnorm(25, 70, 8), rnorm(25, 50, 10), rnorm(25, 62, 9)))
    df$g <- factor(df$g, levels = c("Young", "Aged", "Aged+Rx"))
    emit(id, function() {
      p <- ggplot(df, aes(g, y, fill = g)) + geom_boxplot(width = 0.6, outlier.shape = 21) +
        scale_fill_brewer(palette = "Pastel1") +
        labs(x = NULL, y = "Novel-object preference (%)") + theme_classic(base_size = 13) +
        theme(legend.position = "none")
      if (tier == "dense") {
        p <- p + geom_jitter(width = 0.12, size = 1.2, alpha = 0.6) +
          labs(title = "Recognition memory across age", x = "Cohort", subtitle = "boxes = IQR, Tukey whiskers") +
          annotate("text", x = 2, y = 92, label = "***", size = 6) +
          annotate("segment", x = 1, xend = 2, y = 90, yend = 90) +
          annotate("text", x = 1:3, y = 20, label = paste0("n=", 25), size = 3) +
          theme(panel.grid.major.y = element_line(colour = "grey88"))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "significance-markers", "annotation", "raw-points") else c("axis-ticks")
    add_row(id, "box", "ggplot2", "ggplot2", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

build_box_lattice <- function(idbase, seed = 12) {
  if (!have("lattice")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(g = rep(c("A", "B", "C", "D"), each = 20),
                     y = c(rnorm(20, 5), rnorm(20, 7), rnorm(20, 6), rnorm(20, 9)))
    emit(id, function() {
      p <- lattice::bwplot(y ~ g, data = df, ylab = "Amplitude (mV)",
        xlab = if (tier == "dense") "Genotype" else "",
        main = if (tier == "dense") "EPSP amplitude by genotype" else NULL,
        par.settings = lattice::simpleTheme(col = "grey30"),
        panel = function(...) { if (tier == "dense") lattice::panel.grid(h = -1, v = 0, col = "grey85"); lattice::panel.bwplot(...) })
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title") else c("axis-ticks")
    add_row(id, "box", "lattice", "lattice", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

## ---- VIOLIN -----------------------------------------------------------------
build_violin_vioplot <- function(idbase, seed = 13) {
  if (!have("vioplot")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    a <- rnorm(80, 10, 2); b <- rnorm(80, 13, 3); c3 <- rnorm(80, 11, 2.5)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      vioplot::vioplot(a, b, c3, names = c("WT", "Het", "KO"), col = PAL[c(4, 5, 6)],
                       ylab = "Firing rate (Hz)",
                       main = if (tier == "dense") "Firing-rate distribution" else "")
      if (tier == "dense") {
        sig_bracket_base(1, 2, 20, "*")
        text(1:3, 3, paste0("n=", 80), cex = 0.75); title(xlab = "Genotype"); panel_label_base("B")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "significance-markers", "annotation", "panel-label") else c("axis-ticks")
    add_row(id, "violin", "vioplot", "base", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

build_violin_ggplot <- function(idbase, seed = 14) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(g = rep(c("Saline", "LPS", "LPS+Mino"), each = 60),
                     y = c(rnorm(60, 2, 0.5), rnorm(60, 4.5, 1.2), rnorm(60, 3, 0.9)))
    df$g <- factor(df$g, levels = c("Saline", "LPS", "LPS+Mino"))
    emit(id, function() {
      p <- ggplot(df, aes(g, y, fill = g)) +
        geom_violin(trim = FALSE, colour = "grey30") +
        geom_boxplot(width = 0.12, fill = "white", outlier.shape = NA) +
        scale_fill_brewer(palette = "Accent") +
        labs(x = NULL, y = "IL-6 (pg/mL)") + theme_classic(base_size = 13) +
        theme(legend.position = "none")
      if (tier == "dense") {
        p <- p + labs(title = "Microglial cytokine release", x = "Treatment",
                      subtitle = "violin = density, inner box = IQR") +
          annotate("text", x = 2, y = 8, label = "****", size = 5) +
          annotate("segment", x = 1, xend = 2, y = 7.6, yend = 7.6) +
          annotate("text", x = 1:3, y = -0.3, label = paste0("n=", 60), size = 3) +
          theme(panel.grid.major.y = element_line(colour = "grey88"))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "significance-markers", "annotation") else c("axis-ticks")
    add_row(id, "violin", "ggplot2", "ggplot2", tier, "primary", "categorical", "linear", TRUE, nD)
  }
}

## ---- SCATTER ----------------------------------------------------------------
build_scatter_base <- function(idbase, seed = 15) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    x <- runif(60, 0, 10); y <- 2 + 1.4 * x + rnorm(60, 0, 2.2)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      plot(x, y, pch = 19, col = rgb(0.2, 0.4, 0.7, 0.7), xlab = "Dose (mg/kg)",
           ylab = "Clearance (mL/min)", main = if (tier == "dense") "Dose vs clearance" else "")
      if (tier == "dense") {
        fit <- lm(y ~ x); abline(fit, col = "red", lwd = 2)
        grid(col = "grey88")
        legend("topleft", bty = "n", legend = sprintf("r = %.2f, p < 0.001", cor(x, y)))
        text(2, max(y), "y = 1.4x + 2", pos = 4, cex = 0.85, col = "red"); panel_label_base("A")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "trend-line", "annotation", "panel-label") else c("axis-ticks")
    add_row(id, "scatter", "base", "base", tier, "primary", "linear", "linear", FALSE, nD)
  }
}

build_scatter_ggplot <- function(idbase, seed = 16) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(x = runif(90, 20, 80)); df$grp <- sample(c("M", "F"), 90, TRUE)
    df$y <- 5 + 0.6 * df$x + ifelse(df$grp == "F", 6, 0) + rnorm(90, 0, 8)
    emit(id, function() {
      p <- ggplot(df, aes(x, y, colour = grp)) + geom_point(size = 2, alpha = 0.8) +
        scale_colour_brewer(palette = "Set1") +
        labs(x = "Age (yr)", y = "Biomarker (ng/mL)", colour = "Sex") + theme_bw(base_size = 13)
      if (tier == "dense") {
        p <- p + geom_smooth(method = "lm", se = TRUE, linewidth = 0.8) +
          labs(title = "Biomarker vs age by sex", subtitle = "linear fit +/- 95% CI band") +
          annotate("text", x = 30, y = 70, label = "R2 = 0.42", size = 3.4) +
          theme(legend.position = "top")
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "trend-line", "annotation") else c("axis-ticks", "legend", "gridlines")
    add_row(id, "scatter", "ggplot2", "ggplot2", tier, "primary", "linear", "linear", tier == "dense", nD)
  }
}

build_scatter_lattice <- function(idbase, seed = 17) {
  if (!have("lattice")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(x = rnorm(70, 5, 1.5)); df$y <- 3 * df$x + rnorm(70, 0, 3)
    df$grp <- factor(sample(c("Ctrl", "Trt"), 70, TRUE))
    emit(id, function() {
      p <- lattice::xyplot(y ~ x, groups = df$grp, data = df,
        xlab = "Concentration (uM)", ylab = "Signal (RFU)",
        main = if (tier == "dense") "Signal vs concentration" else NULL,
        auto.key = if (tier == "dense") list(space = "right") else FALSE,
        type = if (tier == "dense") c("p", "r", "g") else "p",
        par.settings = lattice::simpleTheme(pch = 19, col = PAL[c(2, 4)]))
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "trend-line") else c("axis-ticks")
    add_row(id, "scatter", "lattice", "lattice", tier, "primary", "linear", "linear", FALSE, nD)
  }
}

## ---- LINE (time course) -----------------------------------------------------
build_line_base <- function(idbase, seed = 18) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    t <- 0:10; y1 <- 100 * exp(-0.15 * t); y2 <- 100 * exp(-0.30 * t)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, if (tier == "dense") 5 else 2))
      matplot(t, cbind(y1, y2), type = "b", pch = c(19, 17), lty = 1, lwd = 2,
              col = PAL[c(1, 3)], xlab = "Time (h)", ylab = "Plasma conc. (ng/mL)",
              main = if (tier == "dense") "Pharmacokinetic time course" else "")
      legend(if (tier == "dense") "topright" else "topright", c("Formulation A", "Formulation B"),
             col = PAL[c(1, 3)], pch = c(19, 17), lty = 1, bty = "n")
      if (tier == "dense") {
        arrows(t, y1 - 5, t, y1 + 5, angle = 90, code = 3, length = 0.03, col = PAL[1])
        grid(col = "grey88"); text(t[4], y1[4] + 12, "Cmax", cex = 0.8); panel_label_base("A")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "annotation", "panel-label") else c("axis-ticks", "legend")
    add_row(id, "line", "base", "base", tier, "primary", "linear", "linear", tier == "dense", nD)
  }
}

build_line_ggplot <- function(idbase, seed = 19) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- expand.grid(week = 0:8, arm = c("Placebo", "Low", "High"))
    df$score <- with(df, 50 - ifelse(arm == "High", 3.2, ifelse(arm == "Low", 1.8, 0.6)) * week + rnorm(nrow(df), 0, 1))
    df$se <- 1.5
    emit(id, function() {
      p <- ggplot(df, aes(week, score, colour = arm)) +
        geom_line(linewidth = 0.9) + geom_point(size = 2) +
        scale_colour_brewer(palette = "Dark2") +
        labs(x = "Week", y = "Symptom score", colour = "Arm") + theme_classic(base_size = 13)
      if (tier == "dense") {
        p <- p + geom_errorbar(aes(ymin = score - se, ymax = score + se), width = 0.2) +
          labs(title = "Symptom trajectory over 8 weeks", subtitle = "mean +/- SEM, mixed model") +
          annotate("text", x = 6, y = 48, label = "* group x time", size = 3, fontface = 3) +
          theme(legend.position = "top", panel.grid.major = element_line(colour = "grey90"))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "significance-markers", "annotation") else c("axis-ticks", "legend")
    add_row(id, "line", "ggplot2", "ggplot2", tier, "primary", "linear", "linear", tier == "dense", nD)
  }
}

## ---- DOSE-RESPONSE (log-x sigmoid) -----------------------------------------
build_dr_ggplot <- function(idbase, seed = 20) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    logc <- seq(-9, -4, length.out = 8); conc <- 10^logc
    resp <- 100 / (1 + 10^((-6.5 - logc) * -1)); resp <- resp + rnorm(8, 0, 3)
    df <- data.frame(conc = conc, resp = pmin(pmax(resp, 0), 100), se = 4)
    emit(id, function() {
      p <- ggplot(df, aes(conc, resp)) +
        geom_line(colour = PAL[2], linewidth = 0.9) + geom_point(size = 2.5, colour = PAL[2]) +
        scale_x_log10(labels = scales::label_log()) +
        labs(x = "[Agonist] (M)", y = "Response (% max)") + theme_bw(base_size = 13)
      if (tier == "dense") {
        p <- p + geom_errorbar(aes(ymin = resp - se, ymax = resp + se), width = 0.08) +
          geom_hline(yintercept = 50, linetype = 3, colour = "grey40") +
          geom_vline(xintercept = 10^-6.5, linetype = 2, colour = "red") +
          labs(title = "Concentration-response curve", subtitle = "4-parameter logistic fit") +
          annotate("text", x = 10^-6.5, y = 10, label = "EC50", colour = "red", size = 3.2, hjust = -0.1) +
          annotate("text", x = 1e-8, y = 90, label = "Emax = 100%", size = 3)
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "reference-line", "annotation") else c("axis-ticks", "gridlines")
    add_row(id, "dose-response", "ggplot2", "ggplot2", tier, "primary", "log", "percent", tier == "dense", nD)
  }
}

build_dr_base <- function(idbase, seed = 21) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    logc <- seq(-10, -4, length.out = 9); conc <- 10^logc
    resp <- 100 / (1 + 10^((-7 - logc) * -1.2)) + rnorm(9, 0, 2.5)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      plot(conc, pmin(pmax(resp, 0), 100), log = "x", type = "b", pch = 19, lwd = 2, col = PAL[6],
           xlab = "[Drug] (M)", ylab = "% inhibition", ylim = c(0, 100),
           main = if (tier == "dense") "Inhibition dose-response" else "")
      if (tier == "dense") {
        abline(h = 50, lty = 3); abline(v = 1e-7, lty = 2, col = "red")
        text(1e-7, 5, "IC50", col = "red", cex = 0.8); grid(col = "grey88"); panel_label_base("B")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "reference-line", "annotation", "panel-label") else c("axis-ticks")
    add_row(id, "dose-response", "base", "base", tier, "primary", "log", "percent", FALSE, nD)
  }
}

## ---- KAPLAN-MEIER -----------------------------------------------------------
build_km_survival <- function(idbase, seed = 22) {
  if (!have("survival")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    n <- 120; grp <- rep(c("Control", "Treated"), each = n / 2)
    time <- c(rexp(n / 2, 1 / 20), rexp(n / 2, 1 / 34))
    status <- rbinom(n, 1, 0.75)
    df <- data.frame(time, status, grp)
    emit(id, function() {
      fit <- survival::survfit(survival::Surv(time, status) ~ grp, data = df)
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      plot(fit, col = PAL[c(1, 3)], lwd = 2, xlab = "Time (days)", ylab = "Survival probability",
           mark.time = TRUE, conf.int = tier == "dense",
           main = if (tier == "dense") "Overall survival" else "")
      legend("bottomleft", c("Control", "Treated"), col = PAL[c(1, 3)], lwd = 2, bty = "n")
      if (tier == "dense") {
        text(50, 0.9, "HR = 0.62\n(95% CI 0.41-0.94)\nlog-rank p = 0.02", cex = 0.8, pos = 4)
        grid(col = "grey88"); panel_label_base("A")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "annotation", "panel-label") else c("axis-ticks", "legend")
    add_row(id, "kaplan-meier", "survival", "base", tier, "primary", "time", "probability", tier == "dense", nD)
  }
}

build_km_ggplot <- function(idbase, seed = 23) {
  if (!have("survival")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    n <- 100; grp <- rep(c("A", "B"), each = n / 2)
    time <- c(rexp(n / 2, 1 / 15), rexp(n / 2, 1 / 25)); status <- rbinom(n, 1, 0.8)
    fit <- survival::survfit(survival::Surv(time, status) ~ grp, data = data.frame(time, status, grp))
    sd <- data.frame(time = fit$time, surv = fit$surv,
                     grp = rep(c("A", "B"), fit$strata))
    emit(id, function() {
      p <- ggplot(sd, aes(time, surv, colour = grp)) +
        geom_step(linewidth = 0.9) + scale_colour_brewer(palette = "Set1") +
        scale_y_continuous(limits = c(0, 1)) +
        labs(x = "Follow-up (mo)", y = "Progression-free survival", colour = "Cohort") +
        theme_classic(base_size = 13)
      if (tier == "dense") {
        p <- p + labs(title = "Progression-free survival", subtitle = "Kaplan-Meier, censored ticks") +
          annotate("text", x = 40, y = 0.8, label = "log-rank p = 0.03", size = 3.4) +
          theme(legend.position = "top", panel.grid.major = element_line(colour = "grey90"))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "annotation") else c("axis-ticks", "legend")
    add_row(id, "kaplan-meier", "ggplot2", "ggplot2", tier, "primary", "time", "probability", FALSE, nD)
  }
}

## ---- FOREST (derived: summarizes OTHER studies) -----------------------------
build_forest_forestplot <- function(idbase, seed = 24) {
  if (!have("forestplot")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    studies <- c("Adams 2011", "Baker 2014", "Chen 2016", "Diaz 2019", "Evans 2021")
    est <- c(0.72, 0.85, 0.61, 0.90, 0.78); lo <- est - c(.2, .15, .25, .18, .12); hi <- est + c(.2, .15, .25, .18, .12)
    emit(id, function() {
      lab <- if (tier == "dense")
        cbind(c("Study", studies, "Pooled"),
              c("OR (95% CI)", sprintf("%.2f (%.2f-%.2f)", est, lo, hi), "0.77 (0.68-0.87)"),
              c("Weight", paste0(c(18, 25, 12, 28, 17), "%"), "100%"))
      else cbind(c("Study", studies, "Pooled"))
      m <- c(NA, est, 0.77); l <- c(NA, lo, 0.68); u <- c(NA, hi, 0.87)
      fp <- forestplot::forestplot(lab, mean = m, lower = l, upper = u,
        is.summary = c(TRUE, rep(FALSE, 5), TRUE), zero = 1, xlog = TRUE,
        col = forestplot::fpColors(box = PAL[1], line = "grey30", summary = PAL[3]),
        title = if (tier == "dense") "Random-effects meta-analysis: mortality" else NULL,
        xlab = if (tier == "dense") "Odds ratio (log scale)" else NULL)
      open_png(id, W = 760, H = 480); print(fp); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "annotation", "reference-line") else c("axis-ticks", "reference-line")
    add_row(id, "forest", "forestplot", "forestplot", tier, "derived", "log", "categorical", TRUE, nD)
  }
}

build_forest_metafor <- function(idbase, seed = 25) {
  if (!have("metafor")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    yi <- c(0.30, 0.55, 0.12, 0.44, 0.68, 0.22); vi <- c(.04, .03, .06, .02, .05, .04)
    slab <- paste(c("Fischer", "Gupta", "Ito", "Kumar", "Lopez", "Mori"), 2010:2015)
    emit(id, function() {
      res <- metafor::rma(yi, vi, slab = slab)
      open_png(id, W = 760, H = 480)
      op <- par(mar = c(5, 4, if (tier == "dense") 3 else 1, 2))
      metafor::forest(res, header = tier == "dense",
        xlab = if (tier == "dense") "Standardized mean difference" else "SMD",
        mlab = if (tier == "dense") "RE Model (Q=8.1, p=0.15, I2=38%)" else "")
      if (tier == "dense") title(main = "Effect of intervention on outcome")
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "annotation", "reference-line") else c("axis-ticks", "reference-line")
    add_row(id, "forest", "metafor", "metafor", tier, "derived", "linear", "categorical", TRUE, nD)
  }
}

build_forest_forestploter <- function(idbase, seed = 26) {
  if (!have("forestploter")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    est <- c(1.2, 0.9, 1.5, 1.1, 0.8); lo <- est - c(.3, .2, .4, .25, .2); hi <- est + c(.3, .2, .4, .25, .2)
    dt <- data.frame(Study = c("Trial-1", "Trial-2", "Trial-3", "Trial-4", "Trial-5"),
                     ` ` = paste(rep(" ", 20), collapse = " "),
                     `HR (95% CI)` = sprintf("%.2f (%.2f-%.2f)", est, lo, hi),
                     check.names = FALSE)
    if (tier == "dense") dt$`N` <- c(220, 180, 310, 150, 260)
    emit(id, function() {
      p <- forestploter::forest(dt, est = est, lower = lo, upper = hi,
        ci_column = 2, ref_line = 1, xlim = c(0, 2),
        title = if (tier == "dense") "Hazard ratios across trials" else NULL)
      open_png(id, W = 760, H = 430); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "annotation", "reference-line") else c("axis-ticks", "reference-line")
    add_row(id, "forest", "forestploter", "forestploter", tier, "derived", "linear", "categorical", TRUE, nD)
  }
}

## ---- FUNNEL (derived) -------------------------------------------------------
build_funnel_metafor <- function(idbase, seed = 27) {
  if (!have("metafor")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    k <- 30; yi <- rnorm(k, 0.4, 0.18); vi <- runif(k, 0.01, 0.12)
    emit(id, function() {
      res <- metafor::rma(yi, vi)
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      metafor::funnel(res, xlab = "Effect size (SMD)",
        main = if (tier == "dense") "Funnel plot for publication bias" else "",
        level = if (tier == "dense") c(90, 95, 99) else 95,
        shade = if (tier == "dense") c("white", "grey90", "grey80") else "white",
        legend = tier == "dense")
      if (tier == "dense") { text(0.4, 0.02, "Egger p = 0.21", cex = 0.8); panel_label_base("C") }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "title", "annotation", "reference-line", "panel-label") else c("axis-ticks", "reference-line")
    add_row(id, "funnel", "metafor", "metafor", tier, "derived", "linear", "linear", TRUE, nD)
  }
}

build_funnel_base <- function(idbase, seed = 28) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    k <- 26; se <- runif(k, 0.02, 0.25); eff <- rnorm(k, 0.35, se)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      plot(eff, se, ylim = rev(range(se)), pch = 19, col = rgb(0.2, 0.3, 0.6, 0.8),
           xlab = "Log odds ratio", ylab = "Standard error",
           main = if (tier == "dense") "Funnel plot" else "")
      abline(v = 0.35, lty = 2, col = "grey40")
      if (tier == "dense") {
        segments(0.35, 0, 0.35 - 1.96 * 0.25, 0.25, lty = 3); segments(0.35, 0, 0.35 + 1.96 * 0.25, 0.25, lty = 3)
        text(0.35, 0.02, "pooled", cex = 0.8, pos = 4); grid(col = "grey88"); panel_label_base("D")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "annotation", "reference-line", "panel-label") else c("axis-ticks", "reference-line")
    add_row(id, "funnel", "base", "base", tier, "derived", "linear", "linear", TRUE, nD)
  }
}

## ---- ROC --------------------------------------------------------------------
build_roc_pROC <- function(idbase, seed = 29) {
  if (!have("pROC")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    n <- 200; d <- rbinom(n, 1, 0.4); m <- rnorm(n, ifelse(d == 1, 1.2, 0), 1)
    emit(id, function() {
      r <- pROC::roc(d, m, quiet = TRUE)
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      plot(r, col = PAL[2], lwd = 2.5, legacy.axes = TRUE,
           main = if (tier == "dense") "ROC: biomarker for disease" else "")
      if (tier == "dense") {
        r2 <- pROC::roc(d, m + rnorm(n, 0, 0.6), quiet = TRUE)
        plot(r2, col = PAL[4], lwd = 2, add = TRUE)
        legend("bottomright", c(sprintf("Marker A (AUC=%.2f)", as.numeric(pROC::auc(r))),
                                 sprintf("Marker B (AUC=%.2f)", as.numeric(pROC::auc(r2)))),
               col = PAL[c(2, 4)], lwd = 2, bty = "n")
        grid(col = "grey88"); panel_label_base("A")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "gridlines", "title", "annotation", "reference-line", "panel-label") else c("axis-ticks", "reference-line")
    add_row(id, "roc", "pROC", "base", tier, "primary", "probability", "probability", FALSE, nD)
  }
}

build_roc_ggplot <- function(idbase, seed = 30) {
  if (!have("pROC")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    n <- 220; d <- rbinom(n, 1, 0.45); m <- rnorm(n, ifelse(d == 1, 1, 0), 1)
    r <- pROC::roc(d, m, quiet = TRUE)
    rd <- data.frame(fpr = 1 - r$specificities, tpr = r$sensitivities)
    rd <- rd[order(rd$fpr), ]
    emit(id, function() {
      p <- ggplot(rd, aes(fpr, tpr)) + geom_line(colour = PAL[3], linewidth = 1) +
        geom_abline(linetype = 2, colour = "grey50") +
        coord_equal() + labs(x = "1 - Specificity", y = "Sensitivity") + theme_bw(base_size = 13)
      if (tier == "dense") {
        p <- p + labs(title = "Classifier ROC curve", subtitle = "10-fold CV") +
          annotate("text", x = 0.6, y = 0.3, label = sprintf("AUC = %.2f", as.numeric(pROC::auc(r))), size = 4) +
          annotate("text", x = 0.7, y = 0.68, label = "chance", angle = 32, colour = "grey50", size = 3)
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "annotation", "reference-line") else c("axis-ticks", "gridlines", "reference-line")
    add_row(id, "roc", "ggplot2", "ggplot2", tier, "primary", "probability", "probability", FALSE, nD)
  }
}

## ---- BLAND-ALTMAN -----------------------------------------------------------
build_ba_base <- function(idbase, seed = 31) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    m1 <- rnorm(80, 100, 15); m2 <- m1 + rnorm(80, 2, 6)
    avg <- (m1 + m2) / 2; dif <- m1 - m2; md <- mean(dif); sdd <- sd(dif)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(5, 5, if (tier == "dense") 4 else 2, 2))
      plot(avg, dif, pch = 19, col = rgb(0.2, 0.4, 0.6, 0.7), xlab = "Mean of two methods",
           ylab = "Difference (A - B)", main = if (tier == "dense") "Method agreement" else "")
      abline(h = md, col = "blue", lwd = 2)
      abline(h = md + 1.96 * sdd, col = "red", lty = 2, lwd = 2)
      abline(h = md - 1.96 * sdd, col = "red", lty = 2, lwd = 2)
      if (tier == "dense") {
        text(max(avg), md, sprintf("bias %.1f", md), pos = 2, col = "blue", cex = 0.8)
        text(max(avg), md + 1.96 * sdd, "+1.96 SD", pos = 2, col = "red", cex = 0.75)
        text(max(avg), md - 1.96 * sdd, "-1.96 SD", pos = 2, col = "red", cex = 0.75)
        grid(col = "grey88"); panel_label_base("B")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "gridlines", "title", "annotation", "reference-line", "panel-label") else c("axis-ticks", "reference-line")
    add_row(id, "bland-altman", "base", "base", tier, "primary", "linear", "linear", TRUE, nD)
  }
}

build_ba_ggplot <- function(idbase, seed = 32) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    a <- rnorm(90, 50, 10); b <- a * 1.02 + rnorm(90, -1, 4)
    df <- data.frame(avg = (a + b) / 2, dif = a - b); md <- mean(df$dif); sdd <- sd(df$dif)
    emit(id, function() {
      p <- ggplot(df, aes(avg, dif)) + geom_point(colour = PAL[5], size = 2, alpha = 0.8) +
        geom_hline(yintercept = md, colour = "blue") +
        geom_hline(yintercept = md + 1.96 * sdd, colour = "red", linetype = 2) +
        geom_hline(yintercept = md - 1.96 * sdd, colour = "red", linetype = 2) +
        labs(x = "Average of methods (mmHg)", y = "Difference") + theme_classic(base_size = 13)
      if (tier == "dense") {
        p <- p + labs(title = "Bland-Altman: BP devices", subtitle = "bias +/- 1.96 SD limits of agreement") +
          annotate("text", x = max(df$avg), y = md + 1.96 * sdd + 1, label = "Upper LoA", size = 3, hjust = 1) +
          annotate("text", x = max(df$avg), y = md - 1.96 * sdd - 1, label = "Lower LoA", size = 3, hjust = 1) +
          annotate("text", x = min(df$avg), y = md + 1, label = sprintf("bias=%.1f", md), size = 3, hjust = 0)
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "annotation", "reference-line") else c("axis-ticks", "reference-line")
    add_row(id, "bland-altman", "ggplot2", "ggplot2", tier, "primary", "linear", "linear", TRUE, nD)
  }
}

## ---- PIE --------------------------------------------------------------------
build_pie_base <- function(idbase, seed = 33) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    v <- c(38, 27, 20, 15); lab <- c("Motor", "Sensory", "Cognitive", "Other")
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(2, 2, if (tier == "dense") 4 else 2, 2))
      pie(v, labels = if (tier == "dense") paste0(lab, "\n", v, "%") else lab,
          col = PAL[1:4], main = if (tier == "dense") "Symptom-domain breakdown" else "")
      if (tier == "dense") { legend("topleft", lab, fill = PAL[1:4], bty = "n", cex = 0.8); panel_label_base("A") }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("legend", "title", "annotation", "panel-label") else character(0)
    add_row(id, "pie", "base", "base", tier, "primary", "categorical", "categorical", FALSE, nD)
  }
}

build_pie_plotrix <- function(idbase, seed = 34) {
  if (!have("plotrix")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    v <- c(45, 30, 25); lab <- c("Responders", "Partial", "Non-resp")
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(2, 2, if (tier == "dense") 4 else 2, 2))
      plotrix::pie3D(v, labels = if (tier == "dense") paste0(lab, " (", v, "%)") else lab,
        col = PAL[c(3, 5, 7)], explode = 0.1, labelcex = 0.9,
        main = if (tier == "dense") "Treatment response (3D)" else "")
      if (tier == "dense") panel_label_base("B")
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("title", "annotation", "panel-label") else character(0)
    add_row(id, "pie", "plotrix", "plotrix", tier, "primary", "categorical", "categorical", FALSE, nD)
  }
}

build_pie_ggplot <- function(idbase, seed = 35) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    df <- data.frame(cat = c("WT", "Het", "Hom", "NA"), n = c(120, 90, 40, 10))
    df$frac <- df$n / sum(df$n)
    emit(id, function() {
      p <- ggplot(df, aes("", frac, fill = cat)) +
        geom_col(width = 1, colour = "white") + coord_polar("y") +
        scale_fill_brewer(palette = "Set3") + theme_void(base_size = 13) +
        labs(fill = "Genotype")
      if (tier == "dense") {
        p <- p + geom_text(aes(label = paste0(round(frac * 100), "%")),
                           position = position_stack(vjust = 0.5), size = 3.5) +
          labs(title = "Genotype distribution") + theme(plot.title = element_text(hjust = 0.5))
      }
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("legend", "title", "annotation") else c("legend")
    add_row(id, "pie", "ggplot2", "ggplot2", tier, "primary", "categorical", "categorical", FALSE, nD)
  }
}

## ---- HEATMAP ----------------------------------------------------------------
build_heatmap_pheatmap <- function(idbase, seed = 36) {
  if (!have("pheatmap")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    m <- matrix(rnorm(120), 12, 10)
    rownames(m) <- paste0("Gene", 1:12); colnames(m) <- paste0("S", 1:10)
    emit(id, function() {
      pheatmap::pheatmap(m, color = viridisLite::viridis(50),
        cluster_rows = tier == "dense", cluster_cols = tier == "dense",
        show_rownames = tier == "dense", show_colnames = TRUE,
        main = if (tier == "dense") "Differential expression (z-score)" else "",
        legend = TRUE, fontsize = 9,
        annotation_col = if (tier == "dense")
          data.frame(Group = rep(c("Ctrl", "Trt"), each = 5), row.names = colnames(m)) else NA,
        filename = file.path(CORPUS, paste0(id, ".png")), width = 7.2, height = 5.2)
    })
    nD <- if (tier == "dense") c("axis-ticks", "legend", "title", "colorbar", "annotation") else c("axis-ticks", "colorbar")
    add_row(id, "heatmap", "pheatmap", "pheatmap", tier, "primary", "categorical", "categorical", FALSE, nD)
  }
}

build_heatmap_corrplot <- function(idbase, seed = 37) {
  if (!have("corrplot")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    X <- matrix(rnorm(200), 20, 10); C <- cor(X); colnames(C) <- rownames(C) <- paste0("V", 1:10)
    emit(id, function() {
      open_png(id, W = 620, H = 600)
      corrplot::corrplot(C, method = if (tier == "dense") "color" else "circle",
        type = if (tier == "dense") "upper" else "full",
        addCoef.col = if (tier == "dense") "grey20" else NULL, number.cex = 0.6,
        tl.col = "black", tl.cex = 0.8, col = corrplot::COL2("RdBu", 200),
        title = if (tier == "dense") "Inter-region correlation matrix" else "",
        mar = c(0, 0, if (tier == "dense") 2 else 0, 0))
      dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "colorbar", "annotation") else c("axis-ticks", "colorbar")
    add_row(id, "heatmap", "corrplot", "corrplot", tier, "primary", "categorical", "categorical", FALSE, nD)
  }
}

build_heatmap_lattice <- function(idbase, seed = 38) {
  if (!have("lattice")) return(invisible())
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    g <- expand.grid(x = 1:12, y = 1:12); g$z <- with(g, sin(x / 2) * cos(y / 2) + rnorm(144, 0, 0.2))
    emit(id, function() {
      p <- lattice::levelplot(z ~ x * y, data = g, col.regions = viridisLite::viridis(100),
        xlab = if (tier == "dense") "Column electrode" else "x",
        ylab = if (tier == "dense") "Row electrode" else "y",
        main = if (tier == "dense") "Spatial activation map" else NULL,
        colorkey = TRUE)
      open_png(id); print(p); dev.off()
    })
    nD <- if (tier == "dense") c("axis-ticks", "title", "colorbar") else c("axis-ticks", "colorbar")
    add_row(id, "heatmap", "lattice", "lattice", tier, "primary", "categorical", "categorical", FALSE, nD)
  }
}

## ---- NON-EXTRACTABLE: schematic & flow-diagram ------------------------------
build_schematic_base <- function(idbase, seed = 39) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    emit(id, function() {
      open_png(id)
      op <- par(mar = c(1, 1, if (tier == "dense") 3 else 1, 1))
      plot.new(); plot.window(c(0, 10), c(0, 10))
      box_at <- function(x, y, w, h, lab, col) {
        rect(x - w / 2, y - h / 2, x + w / 2, y + h / 2, col = col, border = "grey20")
        text(x, y, lab, cex = 0.85)
      }
      box_at(2, 8, 3, 1.4, "Ligand", PAL[1]); box_at(2, 5, 3, 1.4, "Receptor", PAL[2])
      box_at(2, 2, 3, 1.4, "Gene ON", PAL[3]); box_at(7, 5, 3, 1.4, "Kinase", PAL[4])
      arrows(2, 7.3, 2, 5.7, length = 0.12, lwd = 2); arrows(2, 4.3, 2, 2.7, length = 0.12, lwd = 2)
      arrows(3.5, 5, 5.5, 5, length = 0.12, lwd = 2)
      if (tier == "dense") {
        title(main = "Proposed signalling mechanism")
        text(1.3, 6.5, "P", cex = 0.9, col = "red"); text(5, 5.4, "phosphorylation", cex = 0.7)
        text(4.5, 2, "transcription", cex = 0.7); panel_label_base("E")
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("schematic", "title", "annotation", "panel-label") else c("schematic")
    add_row(id, "schematic", "base", "base", tier, "unknown", "unknown", "unknown", FALSE, nD)
  }
}

build_flow_base <- function(idbase, seed = 40) {
  for (tier in c("plain", "dense")) {
    id <- paste0(idbase, "_", tier); set.seed(seed)
    emit(id, function() {
      open_png(id, W = 620, H = 640)
      op <- par(mar = c(1, 1, if (tier == "dense") 3 else 1, 1))
      plot.new(); plot.window(c(0, 10), c(0, 12))
      fb <- function(y, lab) { rect(2, y - 0.7, 8, y + 0.7, border = "grey20"); text(5, y, lab, cex = 0.8) }
      fb(11, "Assessed for eligibility (n=240)")
      fb(8.5, "Randomised (n=180)")
      fb(6, "Allocated to intervention (n=90)")
      fb(3.5, "Analysed (n=84)")
      arrows(5, 10.3, 5, 9.2, length = 0.1); arrows(5, 7.8, 5, 6.7, length = 0.1)
      arrows(5, 5.3, 5, 4.2, length = 0.1)
      if (tier == "dense") {
        rect(8.2, 9.3, 12, 10.5, border = "grey50"); text(10, 9.9, "Excluded (n=60):\n- criteria (40)\n- declined (20)", cex = 0.6)
        title(main = "CONSORT participant flow"); panel_label_base("F")
        text(8.2, 5, "Lost to F/U (n=6)", cex = 0.6, pos = 4)
      }
      par(op); dev.off()
    })
    nD <- if (tier == "dense") c("schematic", "title", "annotation", "panel-label") else c("schematic")
    add_row(id, "flow-diagram", "base", "base", tier, "unknown", "unknown", "unknown", FALSE, nD)
  }
}

# =============================================================================
#  DRIVER
# =============================================================================
BUILDERS <- list(
  function() build_bar_base("bar_base", 101),
  function() build_bar_ggplot("bar_ggplot", 102),
  function() build_gbar_base("gbar_base", 103),
  function() build_gbar_ggplot("gbar_ggplot", 104),
  function() build_gbar_lattice("gbar_lattice", 105),
  function() build_sbar_base("sbar_base", 106),
  function() build_sbar_ggplot("sbar_ggplot", 107),
  function() build_hist_base("hist_base", 108),
  function() build_hist_ggplot("hist_ggplot", 109),
  function() build_box_base("box_base", 110),
  function() build_box_ggplot("box_ggplot", 111),
  function() build_box_lattice("box_lattice", 112),
  function() build_violin_vioplot("violin_vioplot", 113),
  function() build_violin_ggplot("violin_ggplot", 114),
  function() build_scatter_base("scatter_base", 115),
  function() build_scatter_ggplot("scatter_ggplot", 116),
  function() build_scatter_lattice("scatter_lattice", 117),
  function() build_line_base("line_base", 118),
  function() build_line_ggplot("line_ggplot", 119),
  function() build_dr_ggplot("dr_ggplot", 120),
  function() build_dr_base("dr_base", 121),
  function() build_km_survival("km_survival", 122),
  function() build_km_ggplot("km_ggplot", 123),
  function() build_forest_forestplot("forest_forestplot", 124),
  function() build_forest_metafor("forest_metafor", 125),
  function() build_forest_forestploter("forest_forestploter", 126),
  function() build_funnel_metafor("funnel_metafor", 127),
  function() build_funnel_base("funnel_base", 128),
  function() build_roc_pROC("roc_pROC", 129),
  function() build_roc_ggplot("roc_ggplot", 130),
  function() build_ba_base("ba_base", 131),
  function() build_ba_ggplot("ba_ggplot", 132),
  function() build_pie_base("pie_base", 133),
  function() build_pie_plotrix("pie_plotrix", 134),
  function() build_pie_ggplot("pie_ggplot", 135),
  function() build_heatmap_pheatmap("heatmap_pheatmap", 136),
  function() build_heatmap_corrplot("heatmap_corrplot", 137),
  function() build_heatmap_lattice("heatmap_lattice", 138),
  function() build_schematic_base("schematic_base", 139),
  function() build_flow_base("flow_base", 140)
)

cat(sprintf("Generating classification corpus -> %s\n", CORPUS))
for (b in BUILDERS) b()

# ---- write labels + manifest -------------------------------------------------
rows <- REG$rows
for (r in rows) {
  writeLines(toJSON(r, auto_unbox = TRUE, pretty = TRUE),
             file.path(CORPUS, paste0(r$id, ".label.json")))
}
types <- table(vapply(rows, function(r) r$charType, ""))
libs  <- table(vapply(rows, function(r) r$library, ""))
tiers <- table(vapply(rows, function(r) r$tier, ""))
manifest <- list(
  count = length(rows),
  ids = vapply(rows, function(r) r$id, ""),
  byCharType = as.list(types), byLibrary = as.list(libs), byTier = as.list(tiers),
  failures = REG$fail)
writeLines(toJSON(manifest, auto_unbox = TRUE, pretty = TRUE),
           file.path(CORPUS, "manifest.json"))

cat(sprintf("\nDONE: %d images across %d chart types, %d libraries.\n",
            length(rows), length(types), length(libs)))
cat("charType counts:\n"); print(types)
cat("library counts:\n"); print(libs)
if (length(REG$fail)) { cat("\nFAILURES:\n"); cat(paste(" -", REG$fail), sep = "\n") }
