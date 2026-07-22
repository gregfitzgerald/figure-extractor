# rgt.R -- R Ground-Truth engine (shared library)
# ---------------------------------------------------------------------------
# R is the AUTHORITATIVE ground-truth engine for the figure-extraction benchmark.
# This file provides the load-bearing capability: after ggplot2 renders a chart to
# a raster device at a known DPI, recover the EXACT device pixel coordinates
# (top-left origin, to match the figure-extractor tool) of any drawn element, plus
# the full set of meta-analytic descriptives computed from the raw simulated data.
#
# The pixel-recovery method (proven against independent PNG pixel detection to <2px):
#   1. ggplot_build(p)          -> panel_params give the EXPANDED data ranges in the
#                                  panel's native (transformed) coordinate space.
#   2. ggplot_gtable + grid.draw -> render; grid.force materializes the viewport tree.
#   3. seekViewport(panel) + grid::deviceLoc(npc corners) -> the panel's device
#      rectangle in inches; * DPI and flip Y -> panel rectangle in top-left pixels.
#   4. affine map (native data coord) -> (pixel) using the panel range + rectangle.
#   Reading drawn positions straight from ggplot_build()$data guarantees each landmark
#   pixel sits on the actual rendered mark (dodge, stat, log transform already applied).
# ---------------------------------------------------------------------------
suppressMessages({library(ggplot2); library(grid); library(jsonlite)})

# ---- descriptives: the full set a meta-analyst could need, from raw data --------
desc_group <- function(x, conf = 0.95) {
  x <- x[is.finite(x)]
  n <- length(x); m <- mean(x); s <- stats::sd(x)
  sem <- s / sqrt(n)
  tcrit <- stats::qt(1 - (1 - conf) / 2, df = n - 1)
  qs <- stats::quantile(x, c(0.25, 0.5, 0.75), type = 7, names = FALSE)
  list(
    n = n, mean = m, sd = s, sem = sem,
    median = qs[2], q1 = qs[1], q3 = qs[3], iqr = qs[3] - qs[1],
    min = min(x), max = max(x), range = max(x) - min(x),
    ci95_lo = m - tcrit * sem, ci95_hi = m + tcrit * sem, ci_half = tcrit * sem,
    var = s^2
  )
}

# the half-height that a given dispersion type draws as an error bar
disp_half <- function(d, type) switch(type,
  SD = d$sd, SEM = d$sem, CI95 = d$ci_half, SE = d$sem,
  stop(paste("unknown dispersion type", type)))

# ---- pixel mapper -------------------------------------------------------------
# Must be called AFTER grid.draw(gtable) + grid.force(). Builds one mapper per panel.
# Returns a closure to_px(x, y, native=FALSE): native=TRUE means x,y are already in the
# panel's transformed coordinate space (as ggplot_build()$data stores them).
.trans_to_native <- function(v, name) {
  if (is.null(name)) return(v)
  if (grepl("log-10", name)) return(log10(v))
  if (grepl("log2|log-2", name)) return(log2(v))
  v
}
.trans_from_native <- function(v, name) {   # native -> data units
  if (is.null(name)) return(v)
  if (grepl("log-10", name)) return(10^v)
  if (grepl("log2|log-2", name)) return(2^v)
  v
}
trans_name_of <- function(pp, axis) {
  sc <- pp[[axis]]$scale
  nm <- tryCatch(sc$trans$name, error = function(e) NULL)
  if (is.null(nm)) nm <- tryCatch(sc$transform$name, error = function(e) NULL)
  if (is.null(nm)) "identity" else nm
}

make_panel_mapper <- function(build, panel_i, H, DPI) {
  lay <- build$layout$layout
  row <- lay$ROW[panel_i]; col <- lay$COL[panel_i]
  pp  <- build$layout$panel_params[[panel_i]]
  xr <- pp$x.range; yr <- pp$y.range
  xtr <- trans_name_of(pp, "x"); ytr <- trans_name_of(pp, "y")
  paths <- grid.ls(viewports = TRUE, grobs = FALSE, print = FALSE)$name
  nm <- grep(sprintf("^panel-%d-%d(\\.|$)", col, row), paths, value = TRUE)
  if (!length(nm)) nm <- grep("^panel", paths, value = TRUE)[panel_i]
  seekViewport(nm[1])
  bl <- deviceLoc(unit(0, "npc"), unit(0, "npc"), valueOnly = TRUE)
  tr <- deviceLoc(unit(1, "npc"), unit(1, "npc"), valueOnly = TRUE)
  PBLx <- bl$x * DPI; PBLy <- H - bl$y * DPI          # bottom-left (top-left px origin)
  PTRx <- tr$x * DPI; PTRy <- H - tr$y * DPI          # top-right
  to_px <- function(x, y, native = FALSE) {
    xn <- if (native) x else .trans_to_native(x, xtr)
    yn <- if (native) y else .trans_to_native(y, ytr)
    fx <- (xn - xr[1]) / (xr[2] - xr[1])
    fy <- (yn - yr[1]) / (yr[2] - yr[1])
    list(px = PBLx + fx * (PTRx - PBLx), py = PBLy + fy * (PTRy - PBLy))
  }
  # actual DRAWN axis ticks (visible gridlines a real reader calibrates on), in DATA units
  in_range_ticks <- function(axis, rng, trname) {
    bk <- tryCatch(pp[[axis]]$get_breaks(), error = function(e) numeric(0))
    bk <- bk[is.finite(bk)]; bk <- bk[bk >= rng[1] & bk <= rng[2]]
    .trans_from_native(bk, trname)
  }
  list(to_px = to_px, xtr = xtr, ytr = ytr, xr = xr, yr = yr,
       rect = list(x0 = PBLx, x1 = PTRx, ytop = PTRy, ybot = PBLy),
       y_ticks = in_range_ticks("y", yr, ytr), x_ticks = in_range_ticks("x", xr, xtr),
       data_y = function(y_native) .trans_from_native(y_native, ytr),
       data_x = function(x_native) .trans_from_native(x_native, xtr))
}

# pick two well-separated visible ticks as calibration references
pick_refs <- function(ticks, fallback = c(0, 1)) {
  ticks <- sort(unique(ticks[is.finite(ticks)]))
  if (length(ticks) < 2) return(fallback)
  c(ticks[1], ticks[length(ticks)])
}

# ---- calibration reference bundle (feeds figure-extractor.calibrate) ----------
# Emits calPixels {x1,x2,y1,y2:{px,py}} + calVals (data value strings + log flags).
# x refs are two group centers (native x=1,2 -> data x label 0,1); y refs are two
# round in-range y DATA values. The tool takes log10 of the value strings itself.
build_calibration <- function(mapper, y1val, y2val, logY = FALSE, logX = FALSE,
                              x1native = 1, x2native = 2, x1val = "0", x2val = "1") {
  P <- mapper$to_px
  cx1 <- P(x1native, mapper$yr[1], native = TRUE)
  cx2 <- P(x2native, mapper$yr[1], native = TRUE)
  cy1 <- P(x1native, y1val)      # y refs at data values (mapper applies transform)
  cy2 <- P(x1native, y2val)
  list(
    calPixels = list(
      x1 = list(px = cx1$px, py = cx1$py), x2 = list(px = cx2$px, py = cx2$py),
      y1 = list(px = cy1$px, py = cy1$py), y2 = list(px = cy2$px, py = cy2$py)),
    calVals = list(x1 = x1val, x2 = x2val,
                   y1 = format(y1val, scientific = FALSE),
                   y2 = format(y2val, scientific = FALSE),
                   logX = logX, logY = logY)
  )
}

# ---- landmark record ----------------------------------------------------------
lm_rec <- function(role, group, px_xy, value_x = NULL, value_y = NULL, series = NULL) {
  r <- list(role = role, group = group, px = px_xy$px, py = px_xy$py)
  if (!is.null(value_x)) r$value_x <- value_x
  if (!is.null(value_y)) r$value_y <- value_y
  if (!is.null(series)) r$series <- series
  r
}

# ---- write one GT bundle ------------------------------------------------------
write_bundle <- function(dir, bundle) {
  path <- file.path(dir, paste0(bundle$id, ".gt.json"))
  writeLines(toJSON(bundle, auto_unbox = TRUE, digits = 8, null = "null", pretty = TRUE), path)
  path
}
