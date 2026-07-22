#!/usr/bin/env Rscript
# generate.R -- R GROUND-TRUTH generator for the figure-extraction benchmark.
# ---------------------------------------------------------------------------
# R simulates raw data -> computes the FULL meta-analytic descriptives -> renders a
# journal-realistic chart FROM that exact data -> exports {data, descriptives, GT
# landmark pixels (device coords, top-left origin), calibration refs, metadata} as
# JSON + PNG. The GT bundle is the benchmark key: extraction tools are scored on how
# close they get to R's descriptives, with the DISPERSION (error-bar) channel as the
# first-class, separately-reported metric.
#
#   Run:  Rscript benchmark/r/generate.R            # default corpus -> benchmark/corpus/
#         Rscript benchmark/r/generate.R --n 24     # (n is advisory; corpus is a fixed spec)
# ---------------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
HERE <- tryCatch(dirname(normalizePath(sub("--file=", "",
          grep("--file=", commandArgs(FALSE), value = TRUE)[1]))), error = function(e) ".")
if (is.na(HERE) || HERE == ".") HERE <- file.path(getwd(), "benchmark", "r")
source(file.path(HERE, "rgt.R"))
CORPUS <- normalizePath(file.path(HERE, "..", "corpus"), mustWork = FALSE)
dir.create(CORPUS, showWarnings = FALSE, recursive = TRUE)

THEMES <- list(classic = theme_classic, bw = theme_bw, minimal = theme_minimal, gray = theme_gray)
mk_theme <- function(name, base_size, grid = TRUE, legend = "right") {
  th <- THEMES[[name]](base_size = base_size) + theme(legend.position = legend)
  if (!grid) th <- th + theme(panel.grid = element_blank())
  th
}

# render a ggplot to png at (W,H,DPI); return build + per-panel mappers (device closed)
render_map <- function(p, path, W, H, DPI) {
  png(path, width = W, height = H, res = DPI, type = "cairo")
  b <- ggplot_build(p)
  g <- ggplot_gtable(b)
  grid.newpage(); grid.draw(g); grid.force()
  nps <- length(b$layout$panel_params)
  mappers <- lapply(seq_len(nps), function(i) make_panel_mapper(b, i, H, DPI))
  dev.off()
  list(build = b, mappers = mappers)
}

layer_data <- function(b, i) b$data[[i]]

# round-trip: pixel-detect the drawn bar/point colour and compare to GT pixel (audit)
# (kept lightweight; full validation lives in the harness) -----------------------

# ============================ BUILDERS ========================================

build_bar <- function(id, seed, dispersionType = "SD", groups = c("Control", "Run"),
                      series = NULL, dots = FALSE, logY = FALSE, theme = "classic",
                      base_size = 13, grid = FALSE, W = 620, H = 460, DPI = 110,
                      flags = character(0)) {
  set.seed(seed)
  ng <- length(groups)
  make_raw <- function(mu, sig, n) round(rnorm(n, mu, sig), 2)
  rows <- list(); desc <- list(); raw <- list()
  if (is.null(series)) {
    for (gi in seq_len(ng)) {
      mu <- runif(1, if (logY) 30 else 150, if (logY) 400 else 320)
      sig <- mu * runif(1, 0.15, 0.30); n <- sample(6:16, 1)
      x <- make_raw(mu, sig, n)
      d <- desc_group(x); raw[[groups[gi]]] <- x; desc[[groups[gi]]] <- d
      rows[[length(rows) + 1]] <- data.frame(grp = groups[gi], series = "s1",
        mean = d$mean, half = disp_half(d, dispersionType), stringsAsFactors = FALSE)
    }
  } else {
    for (gi in seq_len(ng)) for (se in series) {
      mu <- runif(1, 150, 320); sig <- mu * runif(1, 0.15, 0.30); n <- sample(6:16, 1)
      x <- make_raw(mu, sig, n); key <- paste(groups[gi], se, sep = "/")
      d <- desc_group(x); raw[[key]] <- x; desc[[key]] <- d
      rows[[length(rows) + 1]] <- data.frame(grp = groups[gi], series = se,
        mean = d$mean, half = disp_half(d, dispersionType), stringsAsFactors = FALSE)
    }
  }
  D <- do.call(rbind, rows)
  D$grp <- factor(D$grp, levels = groups)
  dodge <- if (!is.null(series)) position_dodge(width = 0.8) else "identity"
  p <- ggplot(D, aes(x = grp, y = mean, fill = if (is.null(series)) grp else series))
  if (logY) {
    # bars-from-zero are undefined on a log axis (log10(0) = -Inf); journals use point
    # markers + error bars. Central mark = the point at the mean (landmark role 'top').
    p <- p + geom_point(aes(colour = if (is.null(series)) grp else series), size = 3.4,
                        show.legend = !is.null(series)) +
      geom_errorbar(aes(ymin = mean, ymax = mean + half), width = 0.15, position = dodge) +
      scale_colour_brewer(palette = "Set1")
  } else {
    p <- p + geom_col(width = if (is.null(series)) 0.6 else 0.7,
                      position = dodge, colour = "grey20", show.legend = !is.null(series)) +
      geom_errorbar(aes(ymin = mean, ymax = mean + half), width = 0.15, position = dodge)
  }
  if (dots && is.null(series)) {
    dd <- do.call(rbind, lapply(seq_len(ng), function(gi)
      data.frame(grp = factor(groups[gi], levels = groups), y = raw[[groups[gi]]])))
    p <- p + geom_jitter(data = dd, aes(x = grp, y = y), width = 0.12, height = 0,
                         inherit.aes = FALSE, size = 1.5, alpha = 0.8, colour = "black")
  }
  ymax <- max(D$mean + D$half) * if (dots) 1.25 else 1.15
  if (logY) {
    p <- p + scale_y_log10(limits = c(10, ymax * 1.4))
  } else {
    p <- p + scale_y_continuous(limits = c(0, ymax), expand = expansion(mult = c(0, 0.02)))
  }
  p <- p + labs(y = if (logY) "mRNA (log scale)" else "BDNF (pg/mg)", x = NULL) +
    mk_theme(theme, base_size, grid, if (is.null(series)) "none" else "right") +
    scale_fill_brewer(palette = "Set2")
  path_png <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map(p, path_png, W, H, DPI); b <- rm$build; M <- rm$mappers[[1]]
  # drawn geometry: geom_col layer = 1, errorbar = 2
  cold <- layer_data(b, 1); ebd <- layer_data(b, 2)
  lms <- list()
  for (k in seq_len(nrow(D))) {
    xn <- cold$x[k]; topn <- cold$y[k]
    capn <- ebd$ymax[k]
    top_px <- M$to_px(xn, topn, native = TRUE)
    cap_px <- M$to_px(xn, capn, native = TRUE)
    gi <- as.integer(D$grp[k]) - 1
    lms[[length(lms) + 1]] <- lm_rec("top", gi, top_px, value_x = xn,
                                     value_y = M$data_y(topn), series = as.character(D$series[k]))
    lms[[length(lms) + 1]] <- lm_rec("cap", gi, cap_px, value_x = xn,
                                     value_y = M$data_y(capn), series = as.character(D$series[k]))
  }
  yr2 <- pick_refs(M$y_ticks)
  cal <- build_calibration(M, yr2[1], yr2[2], logY = logY)
  bundle <- list(
    id = id, engine = "ggplot2", chartType = "bar",
    tier = if (length(flags)) "hard" else "clean", flags = as.list(flags),
    dispersionType = dispersionType,
    render = list(width = W, height = H, dpi = DPI, theme = theme, base_size = base_size, seed = seed),
    groups = as.list(groups), series = if (is.null(series)) NULL else as.list(series),
    data = raw, descriptives = desc,
    landmarks = lms, calibration = cal,
    panelPx = M$rect, image = paste0(id, ".png"))
  write_bundle(CORPUS, bundle); cat(sprintf("  %-26s bar   %s %s\n", id, dispersionType, paste(flags, collapse = ",")))
  invisible(bundle)
}

build_box <- function(id, seed, groups = c("Sham", "Lesion", "Treated"),
                      theme = "bw", base_size = 12, grid = TRUE,
                      W = 640, H = 460, DPI = 110, flags = character(0)) {
  set.seed(seed)
  raw <- list(); desc <- list(); rows <- list()
  for (gi in seq_along(groups)) {
    mu <- runif(1, 200, 320); sig <- runif(1, 25, 55); n <- sample(12:26, 1)
    x <- round(rnorm(n, mu, sig), 2)
    raw[[groups[gi]]] <- x; desc[[groups[gi]]] <- desc_group(x)
    rows[[length(rows) + 1]] <- data.frame(grp = groups[gi], y = x, stringsAsFactors = FALSE)
  }
  D <- do.call(rbind, rows); D$grp <- factor(D$grp, levels = groups)
  p <- ggplot(D, aes(x = grp, y = y, fill = grp)) +
    geom_boxplot(width = 0.55, outlier.size = 1.2, show.legend = FALSE) +
    labs(y = "Escape latency (s)", x = NULL) +
    mk_theme(theme, base_size, grid, "none") + scale_fill_brewer(palette = "Pastel1")
  path_png <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map(p, path_png, W, H, DPI); b <- rm$build; M <- rm$mappers[[1]]
  bx <- layer_data(b, 1)   # x, ymin(whislo), lower(q1), middle, upper(q3), ymax(whishi)
  lms <- list()
  for (k in seq_len(nrow(bx))) {
    gi <- k - 1; xn <- bx$x[k]
    for (rc in list(c("q1", "lower"), c("med", "middle"), c("q3", "upper"),
                    c("whislo", "ymin"), c("whishi", "ymax"))) {
      val <- bx[[rc[2]]][k]; pxy <- M$to_px(xn, val, native = TRUE)
      lms[[length(lms) + 1]] <- lm_rec(rc[1], gi, pxy, value_x = xn, value_y = M$data_y(val))
    }
  }
  yr2 <- pick_refs(M$y_ticks)
  cal <- build_calibration(M, yr2[1], yr2[2])
  bundle <- list(id = id, engine = "ggplot2", chartType = "box",
    tier = if (length(flags)) "hard" else "clean", flags = as.list(flags),
    render = list(width = W, height = H, dpi = DPI, theme = theme, base_size = base_size, seed = seed),
    groups = as.list(groups), data = raw, descriptives = desc,
    landmarks = lms, calibration = cal, panelPx = M$rect, image = paste0(id, ".png"))
  write_bundle(CORPUS, bundle); cat(sprintf("  %-26s box   %s\n", id, paste(flags, collapse = ",")))
  invisible(bundle)
}

build_scatter <- function(id, seed, n = 26, theme = "minimal", base_size = 12, grid = TRUE,
                          W = 620, H = 460, DPI = 110, flags = character(0)) {
  set.seed(seed)
  x <- round(runif(n, 0, 10), 3)
  slope <- runif(1, 0.8, 2.2); intercept <- runif(1, 8, 16)
  y <- round(intercept + slope * x + rnorm(n, 0, 2.4), 3)
  fit <- lm(y ~ x); co <- coef(fit)
  desc <- list(n = n, r = cor(x, y), r2 = summary(fit)$r.squared,
               slope = unname(co[2]), intercept = unname(co[1]),
               slope_se = summary(fit)$coefficients[2, 2],
               x = list(mean = mean(x), sd = sd(x)), y = list(mean = mean(y), sd = sd(y)))
  D <- data.frame(x = x, y = y)
  p <- ggplot(D, aes(x, y)) +
    geom_smooth(method = "lm", se = TRUE, colour = "#d1495b", fill = "#f3c6ce") +
    geom_point(size = 1.9, colour = "#2e2e2e") +
    labs(x = "Wheel running (km/day)", y = "BDNF (AU)") +
    mk_theme(theme, base_size, grid, "none")
  path_png <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map(p, path_png, W, H, DPI); b <- rm$build; M <- rm$mappers[[1]]
  # geom_smooth = layer 1, geom_point = layer 2
  pd <- layer_data(b, 2)
  lms <- list()
  for (k in seq_len(nrow(pd))) {
    pxy <- M$to_px(pd$x[k], pd$y[k], native = TRUE)
    lms[[length(lms) + 1]] <- lm_rec("pt", 0, pxy, value_x = pd$x[k], value_y = pd$y[k])
  }
  xref <- pick_refs(M$x_ticks, fallback = c(0, 10)); yref <- pick_refs(M$y_ticks)
  cal <- build_calibration(M, yref[1], yref[2], x1native = xref[1], x2native = xref[2],
                           x1val = as.character(xref[1]), x2val = as.character(xref[2]))
  bundle <- list(id = id, engine = "ggplot2", chartType = "scatter",
    tier = if (length(flags)) "hard" else "clean", flags = as.list(flags),
    render = list(width = W, height = H, dpi = DPI, theme = theme, base_size = base_size, seed = seed),
    data = list(x = as.list(x), y = as.list(y)), descriptives = desc,
    landmarks = lms, calibration = cal, panelPx = M$rect, image = paste0(id, ".png"))
  write_bundle(CORPUS, bundle); cat(sprintf("  %-26s scat  %s\n", id, paste(flags, collapse = ",")))
  invisible(bundle)
}

build_line <- function(id, seed, doses = c(0, 5, 10, 20, 40), series = c("WT", "KO"),
                       theme = "classic", base_size = 12, grid = FALSE,
                       W = 680, H = 460, DPI = 110, flags = character(0)) {
  set.seed(seed)
  raw <- list(); desc <- list(); rows <- list()
  for (se in series) {
    base <- runif(1, 20, 40); emax <- runif(1, 60, 120); ed50 <- runif(1, 8, 20)
    for (d in doses) {
      mu <- base + emax * d / (ed50 + d); sig <- mu * 0.18; n <- 8
      x <- round(rnorm(n, mu, sig), 2); key <- paste(se, d, sep = "@")
      dd <- desc_group(x); raw[[key]] <- x; desc[[key]] <- dd
      rows[[length(rows) + 1]] <- data.frame(series = se, dose = d, mean = dd$mean,
        half = dd$sem, stringsAsFactors = FALSE)
    }
  }
  D <- do.call(rbind, rows)
  p <- ggplot(D, aes(x = dose, y = mean, colour = series, group = series)) +
    geom_line(linewidth = 0.8) + geom_point(size = 2) +
    geom_errorbar(aes(ymin = mean - half, ymax = mean + half), width = 1.1) +
    labs(x = "Dose (mg/kg)", y = "Response (AU)", colour = NULL) +
    mk_theme(theme, base_size, grid, "top") + scale_colour_brewer(palette = "Dark2")
  path_png <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map(p, path_png, W, H, DPI); b <- rm$build; M <- rm$mappers[[1]]
  # layers: line=1, point=2, errorbar=3
  ptd <- layer_data(b, 2); ebd <- layer_data(b, 3)
  lms <- list(); si <- 0
  for (se in series) {
    rowsel <- which(D$series == se); si <- si + 1
    for (j in seq_along(rowsel)) {
      k <- rowsel[j]
      xk <- ptd$x[k]
      top <- M$to_px(xk, ptd$y[k], native = TRUE)
      cap <- M$to_px(xk, ebd$ymax[k], native = TRUE)
      lms[[length(lms) + 1]] <- lm_rec("top", j - 1, top, value_x = xk,
                                       value_y = ptd$y[k], series = se)
      lms[[length(lms) + 1]] <- lm_rec("cap", j - 1, cap, value_x = xk,
                                       value_y = ebd$ymax[k], series = se)
    }
  }
  xref <- pick_refs(M$x_ticks, fallback = c(min(doses), max(doses))); yref <- pick_refs(M$y_ticks)
  cal <- build_calibration(M, yref[1], yref[2], x1native = xref[1], x2native = xref[2],
                           x1val = as.character(xref[1]), x2val = as.character(xref[2]))
  bundle <- list(id = id, engine = "ggplot2", chartType = "line",
    tier = if (length(flags)) "hard" else "clean", flags = as.list(c(flags, "multi-series")),
    dispersionType = "SEM",
    render = list(width = W, height = H, dpi = DPI, theme = theme, base_size = base_size, seed = seed),
    series = as.list(series), doses = as.list(doses),
    data = raw, descriptives = desc, landmarks = lms, calibration = cal,
    panelPx = M$rect, image = paste0(id, ".png"))
  write_bundle(CORPUS, bundle); cat(sprintf("  %-26s line  SEM %s\n", id, paste(flags, collapse = ",")))
  invisible(bundle)
}

# Multi-panel: one PNG, faceted; emit ONE bundle PER PANEL (each carries panelBounds
# in pixels + flags 'multi-panel'), so the reader must decompose the figure.
build_multipanel <- function(id, seed, panels = c("A", "B", "C"), dispersionType = "SEM",
                             theme = "bw", base_size = 12, W = 1000, H = 380, DPI = 110) {
  set.seed(seed)
  groups <- c("Ctl", "Run")
  raw <- list(); desc <- list(); rows <- list()
  for (pl in panels) for (gi in seq_along(groups)) {
    mu <- runif(1, 150, 300); sig <- mu * runif(1, 0.15, 0.28); n <- sample(6:14, 1)
    x <- round(rnorm(n, mu, sig), 2); key <- paste(pl, groups[gi], sep = "/")
    d <- desc_group(x); raw[[key]] <- x; desc[[key]] <- d
    rows[[length(rows) + 1]] <- data.frame(panel = pl, grp = groups[gi], mean = d$mean,
      half = disp_half(d, dispersionType), stringsAsFactors = FALSE)
  }
  D <- do.call(rbind, rows); D$panel <- factor(D$panel, levels = panels)
  D$grp <- factor(D$grp, levels = groups)
  p <- ggplot(D, aes(grp, mean, fill = grp)) +
    geom_col(width = 0.6, colour = "grey20", show.legend = FALSE) +
    geom_errorbar(aes(ymin = mean, ymax = mean + half), width = 0.15) +
    facet_wrap(~panel, scales = "free_y") +
    labs(x = NULL, y = "Signal (AU)") + mk_theme(theme, base_size, TRUE, "none") +
    scale_fill_brewer(palette = "Set2")
  path_png <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map(p, path_png, W, H, DPI); b <- rm$build
  cold <- layer_data(b, 1); ebd <- layer_data(b, 2)
  lay <- b$layout$layout
  out <- list()
  for (pi in seq_along(panels)) {
    pl <- panels[pi]; M <- rm$mappers[[pi]]
    idx <- which(cold$PANEL == pi)
    lms <- list()
    for (k in idx) {
      xn <- cold$x[k]; topn <- cold$y[k]; capn <- ebd$ymax[k]
      gi <- (which(idx == k)) - 1
      lms[[length(lms) + 1]] <- lm_rec("top", gi, M$to_px(xn, topn, native = TRUE),
                                       value_x = xn, value_y = M$data_y(topn))
      lms[[length(lms) + 1]] <- lm_rec("cap", gi, M$to_px(xn, capn, native = TRUE),
                                       value_x = xn, value_y = M$data_y(capn))
    }
    yref <- pick_refs(M$y_ticks)
    cal <- build_calibration(M, yref[1], yref[2])
    pdesc <- desc[paste(pl, groups, sep = "/")]; names(pdesc) <- groups
    praw <- raw[paste(pl, groups, sep = "/")]; names(praw) <- groups
    sub_id <- paste0(id, "_p", pl)
    bundle <- list(id = sub_id, engine = "ggplot2", chartType = "bar",
      tier = "hard", flags = list("multi-panel"), dispersionType = dispersionType,
      render = list(width = W, height = H, dpi = DPI, theme = theme, base_size = base_size, seed = seed),
      groups = as.list(groups), panelLabel = pl, panelIndex = pi,
      panelBounds = M$rect, targetPanel = pl,
      data = praw, descriptives = pdesc, landmarks = lms, calibration = cal,
      panelPx = M$rect, image = paste0(id, ".png"))
    write_bundle(CORPUS, bundle); out[[pl]] <- bundle
  }
  cat(sprintf("  %-26s multi %d panels -> %d bundles\n", id, length(panels), length(out)))
  invisible(out)
}

# ============================ CORPUS SPEC =====================================
cat("Generating R ground-truth corpus -> benchmark/corpus/\n")
# --- clean tier (where WPD-class tools already win) ---
build_bar("bar_sd_clean_01", 101, "SD",   theme = "classic", grid = FALSE)
build_bar("bar_sem_clean_02", 102, "SEM", theme = "bw",      grid = TRUE, base_size = 12)
build_bar("bar_ci_clean_03",  103, "CI95", theme = "minimal", grid = TRUE)
build_box("box_clean_04", 104, theme = "bw",      grid = TRUE)
build_box("box_clean_05", 105, theme = "classic", grid = FALSE, groups = c("Veh", "Low", "High"))
build_scatter("scatter_clean_06", 106, theme = "minimal", grid = TRUE)
build_scatter("scatter_clean_07", 107, theme = "gray",    grid = TRUE, n = 32)
build_line("line_clean_08", 108, theme = "classic", grid = FALSE)
# --- hard tier (dispersion-stress + realism knobs) ---
build_bar("bar_log_hard_09",  109, "SD",  logY = TRUE,  theme = "bw",     grid = TRUE, flags = "log-axis")
build_bar("bar_dots_hard_10", 110, "SEM", dots = TRUE,  theme = "classic", grid = FALSE, flags = "raw-points-present")
build_bar("bar_dodge_hard_11", 111, "SD", series = c("Pre", "Post"), theme = "bw",
          grid = TRUE, flags = "overlapping-series")
build_bar("bar_sem_smallcap_12", 112, "SEM", theme = "minimal", grid = TRUE, flags = "small-caps")
build_line("line_hard_13", 113, doses = c(0, 2, 5, 10, 25, 50), theme = "bw", grid = TRUE)
build_multipanel("panel_ABC_14", 114, panels = c("A", "B", "C"))
build_multipanel("panel_AB_15", 115, panels = c("A", "B"), dispersionType = "SD", W = 760)

# manifest
files <- list.files(CORPUS, pattern = "\\.gt\\.json$", full.names = TRUE)
ids <- sub("\\.gt\\.json$", "", basename(files))
writeLines(toJSON(list(count = length(ids), ids = as.list(ids)), auto_unbox = TRUE, pretty = TRUE),
           file.path(CORPUS, "manifest.json"))
cat(sprintf("\nDONE: %d GT bundles + PNGs in %s\n", length(ids), CORPUS))
