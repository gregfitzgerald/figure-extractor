#!/usr/bin/env Rscript
# gen_series.R -- SERIES / GROUP PARSING corpus generator (the missing perception layer).
# ---------------------------------------------------------------------------
# Classification asks "what kind of chart is this" (measured: at ceiling).
# Localization asks "where are the marks" (measured: the dispersion problem).
# PARSING asks the question in between: *which marks belong to which series/group,
# and what does the legend call each one?* Until that structure is recovered a
# correctly-read mean+SD has no home, and a mis-assignment is a SILENT CATASTROPHIC
# error -- a correct number attached to the wrong arm computes the effect backwards.
#
# R already draws grouped/dodged/stacked bars and multi-series scatter/line FROM
# LABELED data, so it already knows every mark's series/group and the legend mapping.
# This generator EXPORTS that answer key:
#   * per mark: device pixel + groupId (x-axis cluster) + seriesId (legend entity)
#   * per series: legend swatch pixel, legend label pixel, the legend label STRING,
#     legend order vs plotting order, and the aesthetic cue that distinguishes it
#   * an objective occlusion index, so "dense" is measured, not asserted
#   * R's descriptives per ARM, so a mis-assignment can be scored end-to-end as a
#     wrong effect rather than merely a wrong label.
#
#   Run:  Rscript benchmark/series/gen_series.R            -> corpus/        (base tier)
#         Rscript benchmark/series/gen_series.R --stress   -> corpus_stress/ (stress tier)
#
# The STRESS tier exists because the base tier did not break a careful reader. It pushes
# every cue past the base corpus: 8 series whose colours REPEAT (filled vs open markers
# are the only separator), a 6-series sequential ramp with co-located clouds and real
# ink collisions, a 5-step grey bar ramp, and small monochrome glyphs. It lives in its
# own corpus/task directories so the base tier's anonymised task ids -- and therefore
# the first-pass predictions scored against them -- stay valid.
# ---------------------------------------------------------------------------
suppressWarnings(suppressMessages({library(ggplot2); library(grid); library(jsonlite)}))

HERE <- tryCatch(dirname(normalizePath(sub("--file=", "",
          grep("--file=", commandArgs(FALSE), value = TRUE)[1]))), error = function(e) ".")
if (is.na(HERE) || HERE == ".") HERE <- file.path(getwd(), "benchmark", "series")
source(file.path(HERE, "..", "r", "rgt.R"))
source(file.path(HERE, "sgt.R"))
CLI  <- commandArgs(trailingOnly = TRUE)
TIER <- if ("--stress" %in% CLI) "stress" else "base"
CORPUS <- normalizePath(file.path(HERE, if (TIER == "stress") "corpus_stress" else "corpus"),
                        mustWork = FALSE)
dir.create(CORPUS, showWarnings = FALSE, recursive = TRUE)

THEMES <- list(classic = theme_classic, bw = theme_bw, minimal = theme_minimal, gray = theme_gray)
mk_theme <- function(name, base_size, grid = TRUE, legend = "right", inside = NULL) {
  th <- THEMES[[name]](base_size = base_size)
  if (identical(legend, "inside"))
    th <- th + theme(legend.position = "inside", legend.position.inside = inside,
                     legend.background = element_rect(fill = "white", colour = "grey70"))
  else th <- th + theme(legend.position = legend)
  if (!grid) th <- th + theme(panel.grid = element_blank())
  th
}

# ---- palettes ----------------------------------------------------------------
PAL_DISTINCT <- c("#1B9E77", "#D95F02", "#7570B3", "#E7298A", "#66A61E", "#E6AB02")
PAL_SIMHUE   <- c("#3B6BA5", "#4E7CB4", "#6189C0", "#7596CB")   # near-identical blues
PAL_SIMHUE_W <- c("#B0492E", "#BB5B3D", "#C56D4D", "#CF7F5D")   # near-identical warms
MONO         <- "#2E2E2E"

# ---- small utilities ---------------------------------------------------------
`%||%` <- function(a, b) if (is.null(a)) b else a

# render metadata, including what an independent pixel audit needs to reconstruct the
# COMPOSITED colour actually written to the PNG (marker alpha over the panel background)
render_meta <- function(W, H, DPI, theme, base_size, seed, alpha = 1)
  list(width = W, height = H, dpi = DPI, theme = theme, base_size = base_size,
       seed = seed, alpha = alpha,
       panelBg = if (identical(theme, "gray")) "#EBEBEB" else "#FFFFFF")

# nearest row of `df` by x (dodged x positions are unique per arm) -- verified exact
match_x <- function(df, xv, tol = 1e-6) {
  j <- which.min(abs(df$x - xv))
  if (abs(df$x[j] - xv) > tol) stop(sprintf("no errorbar row at x=%.6f", xv))
  j
}
match_xc <- function(df, xv, col, tol = 1e-6) {   # match on x AND colour (multi-series line)
  cand <- which(abs(df$x - xv) < tol & as.character(df$colour) == col)
  if (length(cand) != 1) stop(sprintf("ambiguous errorbar match at x=%.6f colour=%s", xv, col))
  cand
}

mk_series <- function(labels, colors, shapes = NULL, linetypes = NULL) {
  lapply(seq_along(labels), function(i) list(
    seriesId = sprintf("s%d", i - 1L), index = i - 1L, label = labels[i],
    colorHex = toupper(colors[((i - 1) %% length(colors)) + 1]),
    shape = if (is.null(shapes)) NULL else shapes[i],
    linetype = if (is.null(linetypes)) NULL else linetypes[i]))
}

mk_groups <- function(labels, M) {
  lapply(seq_along(labels), function(i) {
    c0 <- M$to_px(i, M$yr[1], native = TRUE)
    list(groupId = sprintf("g%d", i - 1L), index = i - 1L, label = as.character(labels[i]),
         centerPx = list(px = c0$px, py = c0$py))
  })
}

# attach legend geometry to the series defs by matching the DRAWN label string
attach_legend <- function(series_defs, legend, required = TRUE) {
  for (i in seq_along(series_defs)) {
    lab <- series_defs[[i]]$label
    hit <- NULL
    for (e in legend) if (!is.na(e$labelText) && identical(e$labelText, lab)) hit <- e
    if (is.null(hit)) {
      if (required) stop("legend entry not found for series label: ", lab)
      series_defs[[i]]$legendIndex <- NULL
      next
    }
    series_defs[[i]]$legendIndex <- hit$legendIndex
    series_defs[[i]]$legendKeyPx <- hit$keyPx
    series_defs[[i]]$legendLabelPx <- hit$labelPx
    series_defs[[i]]$legendLabelText <- hit$labelText
  }
  series_defs
}

# plotOrderIndex: rank of each series in the chart's natural reading order
set_plot_order <- function(series_defs, key) {   # key: numeric vector, one per series
  r <- rank(key, ties.method = "first") - 1L
  for (i in seq_along(series_defs)) series_defs[[i]]$plotOrderIndex <- as.integer(r[i])
  series_defs
}

legend_matches_plot <- function(series_defs) {
  li <- sapply(series_defs, function(s) s$legendIndex %||% NA_integer_)
  pi <- sapply(series_defs, function(s) s$plotOrderIndex %||% NA_integer_)
  if (any(is.na(li)) || any(is.na(pi))) return(NULL)
  identical(order(li), order(pi))
}

finish_bundle <- function(bundle, marks, seed) {
  bundle$marks <- shuffle_marks(marks, seed)
  bundle$nMarks <- length(bundle$marks)
  write_sgt(CORPUS, bundle)
  cat(sprintf("  %-30s %-13s %-6s series=%d groups=%d marks=%3d cue=%-13s legend=%-7s occl=%s\n",
      bundle$id, bundle$chartType, bundle$difficulty, length(bundle$series),
      length(bundle$groups), bundle$nMarks, bundle$cueType, bundle$legendStyle,
      bundle$occlusion$bucket))
  invisible(bundle)
}

# =============================================================================
#  BUILDER: GROUPED (DODGED) BAR  -- marks: bar top + upper error cap per arm
# =============================================================================
build_gbar <- function(id, seed, groupLabels, seriesLabels, colors = PAL_DISTINCT,
                       dispersionType = "SD", legendPos = "right", inside = NULL,
                       reverseLegend = FALSE, difficulty = "easy", theme = "bw",
                       base_size = 12, grid = TRUE, W = 660, H = 470, DPI = 110,
                       ylab = "BDNF (pg/mg)", headroom = 1.16, traits = character(0)) {
  set.seed(seed)
  G <- length(groupLabels); S <- length(seriesLabels)
  rows <- list(); desc <- list()
  for (gi in seq_len(G)) for (si in seq_len(S)) {
    mu <- runif(1, 140, 320); sig <- mu * runif(1, 0.14, 0.28); n <- sample(6:16, 1)
    x <- round(rnorm(n, mu, sig), 2)
    d <- desc_group(x)
    key <- sprintf("g%d|s%d", gi - 1L, si - 1L)
    desc[[key]] <- d
    rows[[length(rows) + 1]] <- data.frame(grp = groupLabels[gi], ser = seriesLabels[si],
      mean = d$mean, half = disp_half(d, dispersionType), stringsAsFactors = FALSE)
  }
  D <- do.call(rbind, rows)
  D$grp <- factor(D$grp, levels = groupLabels); D$ser <- factor(D$ser, levels = seriesLabels)
  pal <- colors[seq_len(S)]
  dodge <- position_dodge(width = 0.8)
  p <- ggplot(D, aes(grp, mean, fill = ser)) +
    geom_col(position = dodge, width = 0.72, colour = "grey25") +
    geom_errorbar(aes(ymin = mean, ymax = mean + half), position = dodge, width = 0.18) +
    scale_fill_manual(values = setNames(pal, seriesLabels)) +
    scale_y_continuous(limits = c(0, max(D$mean + D$half) * headroom),
                       expand = expansion(mult = c(0, 0.02))) +
    labs(x = NULL, y = ylab, fill = NULL) +
    mk_theme(theme, base_size, grid, legendPos, inside)
  if (reverseLegend) p <- p + guides(fill = guide_legend(reverse = TRUE))

  png_path <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map_legend(p, png_path, W, H, DPI)
  b <- rm$build; M <- rm$mappers[[1]]
  cold <- b$data[[1]]; ebd <- b$data[[2]]
  sdefs <- mk_series(seriesLabels, pal)
  look <- series_lookup(sdefs, "fill")
  marks <- list(); seen <- character(0); xs_by_arm <- list()
  for (k in seq_len(nrow(cold))) {
    si <- look[[toupper(as.character(cold$fill[k]))]]
    gi <- as.integer(round(cold$x[k])) - 1L
    arm <- sprintf("g%d|s%d", gi, si)
    if (arm %in% seen) stop("duplicate arm binding in ", id)
    seen <- c(seen, arm); xs_by_arm[[arm]] <- cold$x[k]
    j <- match_x(ebd, cold$x[k])
    tp <- M$to_px(cold$x[k], cold$y[k], native = TRUE)
    cp <- M$to_px(cold$x[k], ebd$ymax[j], native = TRUE)
    for (rc in list(list("top", tp, cold$y[k]), list("cap", cp, ebd$ymax[j])))
      marks[[length(marks) + 1]] <- list(role = rc[[1]], groupId = sprintf("g%d", gi),
        group = gi, seriesId = sprintf("s%d", si), series = seriesLabels[si + 1],
        px = rc[[2]]$px, py = rc[[2]]$py, value_x = cold$x[k], value_y = M$data_y(rc[[3]]))
  }
  if (length(seen) != G * S) stop("arm coverage mismatch in ", id)
  sdefs <- attach_legend(sdefs, rm$legend)
  # plot order = left-to-right dodged x inside the first cluster
  sdefs <- set_plot_order(sdefs, sapply(seq_len(S), function(si) xs_by_arm[[sprintf("g0|s%d", si - 1L)]]))
  gdefs <- mk_groups(groupLabels, M)
  yr2 <- pick_refs(M$y_ticks); cal <- build_calibration(M, yr2[1], yr2[2])
  occ <- occlusion_index(sapply(marks, `[[`, "px"), sapply(marks, `[[`, "py"),
                         sapply(marks, `[[`, "seriesId"), radius_px = 4)
  bundle <- list(id = id, engine = "ggplot2", chartType = "grouped-bar",
    difficulty = difficulty, cueType = "color+position",
    legendStyle = if (identical(legendPos, "inside")) "inside" else legendPos,
    legendOrderMatchesPlotOrder = NULL, dispersionType = dispersionType,
    flags = as.list(c("categorical-x", "overlapping-series")), traits = as.list(traits),
    render = render_meta(W, H, DPI, theme, base_size, seed),
    groups = gdefs, series = sdefs, occlusion = occ,
    descriptives = desc, calibration = cal, panelPx = M$rect,
    image = paste0(id, ".png"))
  bundle$legendOrderMatchesPlotOrder <- legend_matches_plot(sdefs)
  finish_bundle(bundle, marks, seed)
}

# =============================================================================
#  BUILDER: STACKED BAR -- marks: one per segment, at the segment's visual CENTRE
#  (px2/py2 carry the segment's top/bottom boundary so the value is recoverable)
# =============================================================================
build_sbar <- function(id, seed, groupLabels, seriesLabels, colors = PAL_DISTINCT,
                       legendPos = "right", inside = NULL, reverseLegend = FALSE,
                       difficulty = "medium",
                       theme = "classic", base_size = 12, grid = FALSE,
                       W = 660, H = 470, DPI = 110, ylab = "Cells (%)",
                       traits = character(0)) {
  set.seed(seed)
  G <- length(groupLabels); S <- length(seriesLabels)
  rows <- list(); desc <- list()
  for (gi in seq_len(G)) {
    v <- round(runif(S, 12, 40), 1); v <- round(100 * v / sum(v), 1)
    for (si in seq_len(S)) {
      desc[[sprintf("g%d|s%d", gi - 1L, si - 1L)]] <- list(value = v[si])
      rows[[length(rows) + 1]] <- data.frame(grp = groupLabels[gi], ser = seriesLabels[si],
        value = v[si], stringsAsFactors = FALSE)
    }
  }
  D <- do.call(rbind, rows)
  D$grp <- factor(D$grp, levels = groupLabels); D$ser <- factor(D$ser, levels = seriesLabels)
  pal <- colors[seq_len(S)]
  p <- ggplot(D, aes(grp, value, fill = ser)) +
    geom_col(position = "stack", width = 0.66, colour = "white", linewidth = 0.5) +
    scale_fill_manual(values = setNames(pal, seriesLabels)) +
    labs(x = NULL, y = ylab, fill = NULL) +
    mk_theme(theme, base_size, grid, legendPos, inside)
  if (reverseLegend) p <- p + guides(fill = guide_legend(reverse = TRUE))
  png_path <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map_legend(p, png_path, W, H, DPI)
  b <- rm$build; M <- rm$mappers[[1]]
  cold <- b$data[[1]]
  sdefs <- mk_series(seriesLabels, pal)
  look <- series_lookup(sdefs, "fill")
  marks <- list(); ymin_by_s <- numeric(S)
  for (k in seq_len(nrow(cold))) {
    si <- look[[toupper(as.character(cold$fill[k]))]]
    gi <- as.integer(round(cold$x[k])) - 1L
    ctr <- M$to_px(cold$x[k], (cold$ymin[k] + cold$ymax[k]) / 2, native = TRUE)
    tpx <- M$to_px(cold$x[k], cold$ymax[k], native = TRUE)
    bpx <- M$to_px(cold$x[k], cold$ymin[k], native = TRUE)
    if (gi == 0) ymin_by_s[si + 1L] <- cold$ymin[k]
    marks[[length(marks) + 1]] <- list(role = "seg", groupId = sprintf("g%d", gi), group = gi,
      seriesId = sprintf("s%d", si), series = seriesLabels[si + 1],
      px = ctr$px, py = ctr$py, value_x = cold$x[k],
      value_y = M$data_y(cold$ymax[k] - cold$ymin[k]),
      segTopPy = tpx$py, segBotPy = bpx$py,
      segTopValue = M$data_y(cold$ymax[k]), segBotValue = M$data_y(cold$ymin[k]))
  }
  if (length(marks) != G * S) stop("segment coverage mismatch in ", id)
  sdefs <- attach_legend(sdefs, rm$legend)
  sdefs <- set_plot_order(sdefs, -ymin_by_s)   # 0 = TOP of the stack (reading order)
  gdefs <- mk_groups(groupLabels, M)
  yr2 <- pick_refs(M$y_ticks); cal <- build_calibration(M, yr2[1], yr2[2])
  occ <- occlusion_index(sapply(marks, `[[`, "px"), sapply(marks, `[[`, "py"),
                         sapply(marks, `[[`, "seriesId"), radius_px = 4)
  bundle <- list(id = id, engine = "ggplot2", chartType = "stacked-bar",
    difficulty = difficulty, cueType = "color+position",
    legendStyle = if (identical(legendPos, "inside")) "inside" else legendPos,
    legendOrderMatchesPlotOrder = NULL,
    flags = as.list(c("categorical-x", "overlapping-series")), traits = as.list(traits),
    render = render_meta(W, H, DPI, theme, base_size, seed),
    groups = gdefs, series = sdefs, occlusion = occ,
    descriptives = desc, calibration = cal, panelPx = M$rect, image = paste0(id, ".png"))
  bundle$legendOrderMatchesPlotOrder <- legend_matches_plot(sdefs)
  finish_bundle(bundle, marks, seed)
}

# =============================================================================
#  BUILDER: MULTI-SERIES LINE -- marks: the point markers (+ error caps if drawn)
#  cue: "color" | "shape" (monochrome) | "color+shape"
# =============================================================================
build_mline <- function(id, seed, xs, seriesLabels, colors = PAL_DISTINCT, cue = "color",
                        shapes = c(16, 17, 15, 18, 8, 4), linetypes = NULL, errorbars = FALSE,
                        directLabels = FALSE, legendPos = "right", inside = NULL,
                        difficulty = "easy", theme = "classic", base_size = 12,
                        grid = FALSE, W = 700, H = 470, DPI = 110,
                        xlab = "Week", ylab = "Response (AU)", crossing = FALSE,
                        forceReverseVertical = FALSE, traits = character(0)) {
  set.seed(seed)
  S <- length(seriesLabels); G <- length(xs)
  # generate S trajectories FIRST, label them SECOND -- so the label->trajectory
  # assignment can be permuted to force a legend-order / plot-order mismatch.
  traj <- lapply(seq_len(S), function(si) {
    base <- runif(1, 22, 45)
    slope <- if (crossing) runif(1, -3.2, 3.2) else runif(1, 0.4, 3.0) * (si / S + 0.4)
    lapply(seq_len(G), function(gi) {
      mu <- max(base + slope * xs[gi] + if (crossing) runif(1, -3, 3) else 0, 4)
      round(rnorm(8, mu, mu * 0.16), 2)
    })
  })
  if (forceReverseVertical)   # legend entry 1 ends LOWEST -> plot order fully reversed
    traj <- traj[order(sapply(traj, function(t) mean(t[[G]])))]
  rows <- list(); desc <- list()
  for (si in seq_len(S)) for (gi in seq_len(G)) {
    d <- desc_group(traj[[si]][[gi]])
    desc[[sprintf("g%d|s%d", gi - 1L, si - 1L)]] <- d
    rows[[length(rows) + 1]] <- data.frame(ser = seriesLabels[si], x = xs[gi],
      mean = d$mean, half = d$sem, stringsAsFactors = FALSE)
  }
  D <- do.call(rbind, rows); D$ser <- factor(D$ser, levels = seriesLabels)
  pal <- if (cue == "shape") rep(MONO, S) else colors[seq_len(S)]
  shp <- shapes[seq_len(S)]
  aesmap <- if (cue == "shape") aes(x, mean, shape = ser, group = ser)
            else if (cue == "color+shape") aes(x, mean, colour = ser, shape = ser, group = ser)
            else aes(x, mean, colour = ser, group = ser)
  mono <- if (cue == "shape") list(colour = MONO) else NULL
  p <- ggplot(D, aesmap) +
    do.call(geom_line, c(list(linewidth = 0.85), mono)) +
    do.call(geom_point, c(list(size = 2.6), mono))
  if (errorbars)
    p <- p + geom_errorbar(aes(ymin = mean, ymax = mean + half), width = diff(range(xs)) / 28)
  if (cue != "shape") p <- p + scale_colour_manual(values = setNames(pal, seriesLabels))
  if (cue %in% c("shape", "color+shape")) p <- p + scale_shape_manual(values = setNames(shp, seriesLabels))
  if (!is.null(linetypes))
    p <- p + aes(linetype = ser) +
      scale_linetype_manual(values = setNames(linetypes[seq_len(S)], seriesLabels))
  if (directLabels) {
    lastx <- max(xs)
    dl <- D[D$x == lastx, ]
    p <- p + geom_text(data = dl, aes(x = x, y = mean, label = ser), hjust = -0.15,
                       size = 3.4, show.legend = FALSE, inherit.aes = FALSE,
                       colour = if (cue == "shape") MONO else pal[as.integer(dl$ser)]) +
      scale_x_continuous(limits = c(min(xs), max(xs) + diff(range(xs)) * 0.26))
  }
  # all three scales must share a NULL title, or ggplot splits them into separate
  # guide boxes (which overflows the device and clips the first key)
  p <- p + labs(x = xlab, y = ylab, colour = NULL, shape = NULL, linetype = NULL) +
    mk_theme(theme, base_size, grid, if (directLabels) "none" else legendPos, inside)

  png_path <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map_legend(p, png_path, W, H, DPI)
  b <- rm$build; M <- rm$mappers[[1]]
  ptd <- b$data[[2]]
  ebd <- if (errorbars) b$data[[3]] else NULL
  sdefs <- mk_series(seriesLabels, pal, shapes = if (cue == "color") NULL else shp,
                     linetypes = linetypes)
  lookcue <- if (cue == "shape") "shape" else if (cue == "color+shape") "colour+shape" else "colour"
  look <- series_lookup(sdefs, lookcue)
  xlev <- sort(unique(round(ptd$x, 8)))
  marks <- list(); lasty <- numeric(S)
  for (k in seq_len(nrow(ptd))) {
    sig <- if (cue == "shape") as.character(ptd$shape[k])
           else if (cue == "color+shape") paste(toupper(as.character(ptd$colour[k])),
                                                as.character(ptd$shape[k]), sep = "|")
           else toupper(as.character(ptd$colour[k]))
    si <- look[[sig]]
    gi <- match(round(ptd$x[k], 8), xlev) - 1L
    tp <- M$to_px(ptd$x[k], ptd$y[k], native = TRUE)
    marks[[length(marks) + 1]] <- list(role = "top", groupId = sprintf("g%d", gi), group = gi,
      seriesId = sprintf("s%d", si), series = seriesLabels[si + 1],
      px = tp$px, py = tp$py, value_x = M$data_x(ptd$x[k]), value_y = M$data_y(ptd$y[k]))
    if (gi == G - 1L) lasty[si + 1L] <- ptd$y[k]
    if (errorbars) {
      j <- match_xc(ebd, ptd$x[k], as.character(ptd$colour[k]))
      cp <- M$to_px(ptd$x[k], ebd$ymax[j], native = TRUE)
      marks[[length(marks) + 1]] <- list(role = "cap", groupId = sprintf("g%d", gi), group = gi,
        seriesId = sprintf("s%d", si), series = seriesLabels[si + 1],
        px = cp$px, py = cp$py, value_x = M$data_x(ptd$x[k]), value_y = M$data_y(ebd$ymax[j]))
    }
  }
  if (directLabels) {
    txd <- b$data[[length(b$data)]]
    for (i in seq_len(S)) {
      hit <- which(as.character(txd$label) == seriesLabels[i])
      if (length(hit) == 1) {
        lp <- M$to_px(txd$x[hit], txd$y[hit], native = TRUE)
        sdefs[[i]]$directLabelPx <- list(px = lp$px, py = lp$py)
        sdefs[[i]]$directLabelText <- seriesLabels[i]
      }
    }
  } else {
    sdefs <- attach_legend(sdefs, rm$legend)
  }
  sdefs <- set_plot_order(sdefs, -lasty)   # 0 = topmost line at the right edge
  gdefs <- lapply(seq_len(G), function(i) {
    c0 <- M$to_px(xlev[i], M$yr[1], native = TRUE)
    list(groupId = sprintf("g%d", i - 1L), index = i - 1L,
         label = format(M$data_x(xlev[i]), trim = TRUE),
         centerPx = list(px = c0$px, py = c0$py))
  })
  xref <- pick_refs(M$x_ticks, fallback = range(xs)); yr2 <- pick_refs(M$y_ticks)
  cal <- build_calibration(M, yr2[1], yr2[2], x1native = xref[1], x2native = xref[2],
                           x1val = as.character(xref[1]), x2val = as.character(xref[2]))
  occ <- occlusion_index(sapply(marks, `[[`, "px"), sapply(marks, `[[`, "py"),
                         sapply(marks, `[[`, "seriesId"), radius_px = marker_radius_px(2.6, DPI))
  bundle <- list(id = id, engine = "ggplot2", chartType = "line",
    difficulty = difficulty,
    cueType = if (cue == "shape") "shape" else if (cue == "color+shape") "color+shape" else "color",
    legendStyle = if (directLabels) "direct-labels"
                  else if (identical(legendPos, "inside")) "inside" else legendPos,
    legendOrderMatchesPlotOrder = NULL, dispersionType = if (errorbars) "SEM" else NULL,
    flags = as.list(c("overlapping-series",
                      if (directLabels) "no-legend" else character(0),
                      if (occ$bucket == "severe") "occluded" else character(0))),
    traits = as.list(traits),
    render = render_meta(W, H, DPI, theme, base_size, seed),
    groups = gdefs, series = sdefs, occlusion = occ,
    descriptives = desc, calibration = cal, panelPx = M$rect, image = paste0(id, ".png"))
  bundle$legendOrderMatchesPlotOrder <- if (directLabels) NULL else legend_matches_plot(sdefs)
  finish_bundle(bundle, marks, seed)
}

# =============================================================================
#  BUILDER: MULTI-SERIES SCATTER -- marks: the points. One group ("all").
# =============================================================================
build_mscatter <- function(id, seed, seriesLabels, nper, colors = PAL_DISTINCT,
                           cue = "color", shapes = c(16, 17, 15, 18), overlap = 0.0,
                           alpha = 1, ptsize = 2.3, legendPos = "right", inside = NULL,
                           difficulty = "easy", theme = "bw", base_size = 12,
                           grid = TRUE, W = 660, H = 470, DPI = 110,
                           xlab = "Wheel running (km/day)", ylab = "BDNF (AU)",
                           traits = character(0)) {
  set.seed(seed)
  S <- length(seriesLabels)
  rows <- list(); desc <- list()
  for (si in seq_len(S)) {
    n <- nper[((si - 1) %% length(nper)) + 1]
    # overlap in [0,1]: 0 = well-separated cloud centres AND loose spread;
    # 1 = co-located centres AND tight spread -> markers physically collide (real ink occlusion)
    tighten <- 1 - 0.62 * overlap
    cx <- 5 + (si - (S + 1) / 2) * 2.6 * (1 - overlap)
    cy <- 30 + (si - (S + 1) / 2) * 9 * (1 - overlap)
    x <- round(rnorm(n, cx, 1.5 * tighten), 3)
    y <- round(cy + 2.1 * (x - cx) + rnorm(n, 0, 4.2 * tighten), 3)
    fit <- stats::lm(y ~ x); co <- stats::coef(fit)
    desc[[sprintf("g0|s%d", si - 1L)]] <- list(n = n, x_mean = mean(x), x_sd = stats::sd(x),
      y_mean = mean(y), y_sd = stats::sd(y), r = stats::cor(x, y),
      slope = unname(co[2]), intercept = unname(co[1]))
    rows[[length(rows) + 1]] <- data.frame(ser = seriesLabels[si], x = x, y = y,
                                           stringsAsFactors = FALSE)
  }
  D <- do.call(rbind, rows); D$ser <- factor(D$ser, levels = seriesLabels)
  pal <- if (cue == "shape") rep(MONO, S) else colors[seq_len(S)]
  shp <- shapes[seq_len(S)]
  aesmap <- if (cue == "shape") aes(x, y, shape = ser)
            else if (cue == "color+shape") aes(x, y, colour = ser, shape = ser)
            else aes(x, y, colour = ser)
  ptargs <- c(list(size = ptsize, alpha = alpha), if (cue == "shape") list(colour = MONO))
  p <- ggplot(D, aesmap) + do.call(geom_point, ptargs)
  if (cue != "shape") p <- p + scale_colour_manual(values = setNames(pal, seriesLabels))
  if (cue %in% c("shape", "color+shape")) p <- p + scale_shape_manual(values = setNames(shp, seriesLabels))
  # all three scales must share a NULL title, or ggplot splits them into separate
  # guide boxes (which overflows the device and clips the first key)
  p <- p + labs(x = xlab, y = ylab, colour = NULL, shape = NULL, linetype = NULL) +
    mk_theme(theme, base_size, grid, legendPos, inside)

  png_path <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map_legend(p, png_path, W, H, DPI)
  b <- rm$build; M <- rm$mappers[[1]]
  pd <- b$data[[1]]
  sdefs <- mk_series(seriesLabels, pal, shapes = if (cue == "color") NULL else shp)
  lookcue <- if (cue == "shape") "shape" else if (cue == "color+shape") "colour+shape" else "colour"
  look <- series_lookup(sdefs, lookcue)
  marks <- list(); cxs <- numeric(S)
  for (k in seq_len(nrow(pd))) {
    sig <- if (cue == "shape") as.character(pd$shape[k])
           else if (cue == "color+shape") paste(toupper(as.character(pd$colour[k])),
                                                as.character(pd$shape[k]), sep = "|")
           else toupper(as.character(pd$colour[k]))
    si <- look[[sig]]
    pxy <- M$to_px(pd$x[k], pd$y[k], native = TRUE)
    marks[[length(marks) + 1]] <- list(role = "pt", groupId = "g0", group = 0L,
      seriesId = sprintf("s%d", si), series = seriesLabels[si + 1],
      px = pxy$px, py = pxy$py, value_x = M$data_x(pd$x[k]), value_y = M$data_y(pd$y[k]))
  }
  for (si in seq_len(S)) cxs[si] <- mean(sapply(Filter(function(m)
    m$seriesId == sprintf("s%d", si - 1L), marks), `[[`, "px"))
  sdefs <- attach_legend(sdefs, rm$legend)
  sdefs <- set_plot_order(sdefs, cxs)   # 0 = leftmost cloud
  gdefs <- list(list(groupId = "g0", index = 0L, label = "all",
                     centerPx = list(px = (M$rect$x0 + M$rect$x1) / 2, py = M$rect$ybot)))
  xref <- pick_refs(M$x_ticks); yr2 <- pick_refs(M$y_ticks)
  cal <- build_calibration(M, yr2[1], yr2[2], x1native = xref[1], x2native = xref[2],
                           x1val = as.character(xref[1]), x2val = as.character(xref[2]))
  occ <- occlusion_index(sapply(marks, `[[`, "px"), sapply(marks, `[[`, "py"),
                         sapply(marks, `[[`, "seriesId"),
                         radius_px = marker_radius_px(ptsize, DPI))
  bundle <- list(id = id, engine = "ggplot2", chartType = "scatter",
    difficulty = difficulty,
    cueType = if (cue == "shape") "shape" else if (cue == "color+shape") "color+shape" else "color",
    legendStyle = if (identical(legendPos, "inside")) "inside" else legendPos,
    legendOrderMatchesPlotOrder = NULL,
    flags = as.list(c("overlapping-series",
                      if (occ$bucket %in% c("moderate", "severe")) "occluded" else character(0))),
    traits = as.list(traits),
    render = render_meta(W, H, DPI, theme, base_size, seed),
    groups = gdefs, series = sdefs, occlusion = occ,
    descriptives = desc, calibration = cal, panelPx = M$rect, image = paste0(id, ".png"))
  bundle$render$alpha <- alpha
  bundle$legendOrderMatchesPlotOrder <- legend_matches_plot(sdefs)
  finish_bundle(bundle, marks, seed)
}

# =============================================================================
#  BUILDER: DODGED BOX -- marks: q1 / med / q3 per arm (a very common journal form)
# =============================================================================
build_dbox <- function(id, seed, groupLabels, seriesLabels, colors = PAL_DISTINCT,
                       legendPos = "top", inside = NULL, difficulty = "medium",
                       theme = "bw", base_size = 12, grid = TRUE, W = 680, H = 470,
                       DPI = 110, ylab = "Escape latency (s)", traits = character(0)) {
  set.seed(seed)
  G <- length(groupLabels); S <- length(seriesLabels)
  rows <- list(); desc <- list()
  for (gi in seq_len(G)) for (si in seq_len(S)) {
    mu <- runif(1, 180, 300); sig <- runif(1, 22, 48); n <- sample(14:24, 1)
    v <- round(rnorm(n, mu, sig), 2)
    desc[[sprintf("g%d|s%d", gi - 1L, si - 1L)]] <- desc_group(v)
    rows[[length(rows) + 1]] <- data.frame(grp = groupLabels[gi], ser = seriesLabels[si],
                                           y = v, stringsAsFactors = FALSE)
  }
  D <- do.call(rbind, rows)
  D$grp <- factor(D$grp, levels = groupLabels); D$ser <- factor(D$ser, levels = seriesLabels)
  pal <- colors[seq_len(S)]
  p <- ggplot(D, aes(grp, y, fill = ser)) +
    geom_boxplot(position = position_dodge(width = 0.8), width = 0.62, outlier.size = 1.1) +
    scale_fill_manual(values = setNames(pal, seriesLabels)) +
    labs(x = NULL, y = ylab, fill = NULL) + mk_theme(theme, base_size, grid, legendPos, inside)
  png_path <- file.path(CORPUS, paste0(id, ".png"))
  rm <- render_map_legend(p, png_path, W, H, DPI)
  b <- rm$build; M <- rm$mappers[[1]]
  bx <- b$data[[1]]
  sdefs <- mk_series(seriesLabels, pal)
  look <- series_lookup(sdefs, "fill")
  marks <- list(); xs_by_arm <- list()
  for (k in seq_len(nrow(bx))) {
    si <- look[[toupper(as.character(bx$fill[k]))]]
    gi <- as.integer(round(bx$x[k])) - 1L
    xs_by_arm[[sprintf("g%d|s%d", gi, si)]] <- bx$x[k]
    for (rc in list(c("q1", "lower"), c("med", "middle"), c("q3", "upper"))) {
      val <- bx[[rc[2]]][k]; pxy <- M$to_px(bx$x[k], val, native = TRUE)
      marks[[length(marks) + 1]] <- list(role = rc[1], groupId = sprintf("g%d", gi), group = gi,
        seriesId = sprintf("s%d", si), series = seriesLabels[si + 1],
        px = pxy$px, py = pxy$py, value_x = bx$x[k], value_y = M$data_y(val))
    }
  }
  if (length(marks) != G * S * 3) stop("box arm coverage mismatch in ", id)
  sdefs <- attach_legend(sdefs, rm$legend)
  sdefs <- set_plot_order(sdefs, sapply(seq_len(S), function(si) xs_by_arm[[sprintf("g0|s%d", si - 1L)]]))
  gdefs <- mk_groups(groupLabels, M)
  yr2 <- pick_refs(M$y_ticks); cal <- build_calibration(M, yr2[1], yr2[2])
  occ <- occlusion_index(sapply(marks, `[[`, "px"), sapply(marks, `[[`, "py"),
                         sapply(marks, `[[`, "seriesId"), radius_px = 4)
  bundle <- list(id = id, engine = "ggplot2", chartType = "box",
    difficulty = difficulty, cueType = "color+position",
    legendStyle = if (identical(legendPos, "inside")) "inside" else legendPos,
    legendOrderMatchesPlotOrder = NULL,
    flags = as.list(c("categorical-x", "overlapping-series")), traits = as.list(traits),
    render = render_meta(W, H, DPI, theme, base_size, seed),
    groups = gdefs, series = sdefs, occlusion = occ,
    descriptives = desc, calibration = cal, panelPx = M$rect, image = paste0(id, ".png"))
  bundle$legendOrderMatchesPlotOrder <- legend_matches_plot(sdefs)
  finish_bundle(bundle, marks, seed)
}

# ============================ CORPUS SPEC =====================================
cat(sprintf("Generating SERIES/GROUP parsing corpus (%s tier) -> %s\n", TIER, CORPUS))
if (TIER == "base") {

## -- grouped bars: the canonical "Control vs Run nested inside 2/4/8 weeks" ----
build_gbar("gbar_2x3_easy_01", 201, c("2 wk", "4 wk", "8 wk"), c("Control", "Run"),
           difficulty = "easy", legendPos = "right", theme = "bw")
build_gbar("gbar_3x4_med_02", 202, c("D1", "D7", "D14", "D28"),
           c("Vehicle", "Low dose", "High dose"), difficulty = "medium",
           legendPos = "top", theme = "classic", grid = FALSE, dispersionType = "SEM")
build_gbar("gbar_3x4_simhue_hard_03", 203, c("Ctx", "Hip", "Str", "Cbl"),
           c("Sham", "Lesion", "Lesion+Rx"), colors = PAL_SIMHUE, difficulty = "hard",
           legendPos = "right", theme = "minimal", dispersionType = "CI95",
           traits = "low-contrast-series")
build_gbar("gbar_2x4_revlegend_hard_04", 204, c("Q1", "Q2", "Q3", "Q4"), c("Placebo", "Active"),
           reverseLegend = TRUE, difficulty = "hard", legendPos = "right", theme = "bw",
           traits = "legend-order-mismatch")
build_gbar("gbar_3x3_inside_med_05", 205, c("WT", "Het", "KO"), c("Saline", "LPS", "LPS+Mino"),
           legendPos = "inside", inside = c(0.16, 0.90), difficulty = "medium",
           theme = "classic", grid = FALSE, dispersionType = "SEM", headroom = 1.52)

## -- stacked bars: stacking order is the REVERSE of the legend order (the trap) --
build_sbar("sbar_3x4_med_06", 206, c("Ctrl", "Low", "Mid", "High"),
           c("G0/G1", "S", "G2/M"), difficulty = "medium", legendPos = "right")
build_sbar("sbar_4x3_simhue_hard_07", 207, c("Cortex", "Striatum", "Hippo"),
           c("Neuron", "Astro", "Micro", "Oligo"), colors = PAL_SIMHUE_W,
           reverseLegend = TRUE, difficulty = "hard", legendPos = "top", theme = "bw",
           grid = TRUE, traits = c("low-contrast-series", "legend-order-mismatch"))

## -- multi-series lines --------------------------------------------------------
build_mline("line_3s_easy_08", 208, c(0, 2, 4, 6, 8), c("Placebo", "Low", "High"),
            errorbars = TRUE, difficulty = "easy", legendPos = "right", theme = "classic")
build_mline("line_6s_cross_hard_09", 209, c(0, 1, 2, 4, 8, 12),
            c("A1", "A2", "B1", "B2", "C1", "C2"), crossing = TRUE, difficulty = "hard",
            legendPos = "right", theme = "bw", grid = TRUE, traits = "many-series")
build_mline("line_4s_direct_med_10", 210, c(0, 3, 6, 9, 12, 15),
            c("WT", "KO", "WT+Rx", "KO+Rx"), directLabels = TRUE, difficulty = "medium",
            theme = "classic", W = 740)
build_mline("line_3s_shape_med_11", 211, c(0, 5, 10, 15, 20, 25), c("Sham", "MCAO", "MCAO+Rx"),
            cue = "shape", difficulty = "medium", legendPos = "right", theme = "bw",
            traits = "monochrome")
build_mline("line_3s_revlegend_hard_12", 212, c(0, 4, 8, 12, 16), c("Alpha", "Beta", "Gamma"),
            crossing = TRUE, forceReverseVertical = TRUE, difficulty = "hard",
            legendPos = "right", theme = "classic", traits = "legend-order-mismatch")

## -- multi-series scatter ------------------------------------------------------
build_mscatter("scat_2s_color_easy_13", 213, c("Male", "Female"), nper = c(13, 13),
               difficulty = "easy", legendPos = "right", overlap = 0.05)
build_mscatter("scat_2s_shape_med_14", 214, c("Control", "Trained"), nper = c(13, 13),
               cue = "shape", difficulty = "medium", legendPos = "right", overlap = 0.25,
               traits = "monochrome")
build_mscatter("scat_3s_colorshape_med_15", 215, c("Young", "Adult", "Aged"), nper = c(12, 12, 12),
               cue = "color+shape", difficulty = "medium", legendPos = "top", overlap = 0.35)
build_mscatter("scat_3s_simhue_hard_16", 216, c("Site A", "Site B", "Site C"), nper = c(16, 16, 16),
               colors = PAL_SIMHUE, difficulty = "hard", legendPos = "right", overlap = 0.80,
               alpha = 0.9, traits = "low-contrast-series")
build_mscatter("scat_4s_dense_hard_17", 217, c("Q1", "Q2", "Q3", "Q4"), nper = c(18, 18, 18, 18),
               difficulty = "hard", legendPos = "right", overlap = 0.95, alpha = 0.85,
               W = 560, H = 430, traits = "dense-overlap")
build_mscatter("scat_2s_inside_med_18", 218, c("Pre", "Post"), nper = c(14, 14),
               legendPos = "inside", inside = c(0.85, 0.18), difficulty = "medium",
               overlap = 0.45, theme = "classic", grid = FALSE)

## -- dodged box ----------------------------------------------------------------
build_dbox("dbox_2x3_med_19", 219, c("Day 1", "Day 5", "Day 10"), c("Sham", "Injury"),
           difficulty = "medium", legendPos = "top")

} else {

# ======================= STRESS TIER: past the base corpus ====================
PAL_RAMP6 <- c("#2F5F92", "#3A6C9D", "#4579A8", "#5086B3", "#5B93BE", "#66A0C9")  # ~18 apart
PAL_GREY5 <- c("#B4B4B4", "#A2A2A2", "#909090", "#7E7E7E", "#6C6C6C")             # ~18 apart

## 8 series, only FOUR colours: filled vs open markers (and solid vs dashed lines) are
## the sole separator -- colour alone is ambiguous by construction.
build_mline("stress_line_8s_dup_hue_21", 301,
            c(0, 2, 4, 7, 10, 14), c("A-ctl", "A-trt", "B-ctl", "B-trt",
                                     "C-ctl", "C-trt", "D-ctl", "D-trt"),
            colors = rep(PAL_DISTINCT[1:4], each = 2), cue = "color+shape",
            shapes = rep(c(16, 1), 4), linetypes = rep(c("solid", "22"), 4),
            crossing = TRUE, difficulty = "hard", legendPos = "right", theme = "bw",
            grid = TRUE, W = 780, H = 560, traits = c("many-series", "repeated-hues"))

## 6 series on a sequential ramp, clouds co-located, small alpha-blended markers
build_mscatter("stress_scat_6s_ramp_22", 302,
               c("P1", "P2", "P3", "P4", "P5", "P6"), nper = rep(16, 6),
               colors = PAL_RAMP6, overlap = 0.97, alpha = 0.8, ptsize = 1.7,
               difficulty = "hard", legendPos = "right", W = 540, H = 420,
               traits = c("low-contrast-series", "dense-overlap", "many-series"))

## 5 arms on a 5-step grey ramp -- the greyscale-journal case
build_gbar("stress_gbar_5s_grey_23", 303, c("W1", "W2", "W3", "W4"),
           c("Veh", "D1", "D3", "D10", "D30"), colors = PAL_GREY5,
           dispersionType = "SEM", difficulty = "hard", legendPos = "right",
           theme = "classic", grid = FALSE, W = 720, traits = "low-contrast-series")

## monochrome, three SMALL glyphs, heavy overlap
build_mscatter("stress_scat_3s_smallshape_24", 304, c("Sham", "MCAO", "MCAO+Rx"),
               nper = rep(15, 3), cue = "shape", shapes = c(16, 17, 15), ptsize = 1.5,
               overlap = 0.9, difficulty = "hard", legendPos = "right", W = 540, H = 420,
               traits = c("monochrome", "dense-overlap"))
}

# ---- manifest ----------------------------------------------------------------
files <- sort(list.files(CORPUS, pattern = "\\.sgt\\.json$", full.names = TRUE))
ids <- sub("\\.sgt\\.json$", "", basename(files))
tot <- sum(sapply(files, function(f) length(fromJSON(f, simplifyVector = FALSE)$marks)))
writeLines(toJSON(list(count = length(ids), marks = tot, ids = as.list(ids)),
                  auto_unbox = TRUE, pretty = TRUE), file.path(CORPUS, "manifest.json"))
cat(sprintf("\nDONE: %d charts, %d marks -> %s\n", length(ids), tot, CORPUS))
