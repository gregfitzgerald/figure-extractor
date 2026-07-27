# pgt.R -- PANEL ground-truth engine (the decomposition tier).
# ---------------------------------------------------------------------------
# Additive layer beside ../r/rgt.R and ../series/sgt.R (both left untouched).
#
# Panel detection is a LAYOUT problem, so the ground truth this tier needs is not a
# landmark pixel but a RECTANGLE per panel. We get exact rectangles by inverting the
# usual approach: instead of drawing a figure and then trying to find its panels, we
# COMPOSE the figure out of grid viewports whose device rectangles we choose, then
# render each element a SECOND time on its own, alone on a white page, with byte-identical
# geometry. The ink bounding box of that solo render is, by construction, exactly the ink
# the element contributes to the composite -- so the GT box is measured, not asserted, and
# `audit_panels.py` can re-derive it from the composite alone.
#
# Three geometric facts are exported per panel:
#   tile      -- the rectangle the compositor ALLOCATED (layout math, exact by construction)
#   plotRect  -- the inner axes rectangle (grid::deviceLoc, the rgt.R method)
#   bbox      -- the tight ink box (computed in finalize_gt.py from the solo render)
# `bbox` is the scoring target: it is what a human cropping "panel B" would draw, and it
# is what an ink-trimming detector can in principle reach.
#
# Everything the detector must not be able to shortcut (panel count, letters) is also
# stated in the CAPTION, exactly as journals do -- captions are a legitimate constraint,
# not a leak.
# ---------------------------------------------------------------------------
suppressMessages({library(ggplot2); library(grid); library(jsonlite)})

`%||%` <- function(a, b) if (is.null(a)) b else a

# ============================ panel content ==================================
# Every content builder is seeded from (figure seed, panel index) so a solo render
# and the composite draw pixel-identical ink.

# the plot margin every panel theme uses; render_figure sets it per figure (0 = flush)
.pgt <- new.env(parent = emptyenv())
.pgt$margin_pt <- 2

pnl_theme <- function(base_size, grid_on, bg = "white", margin_pt = .pgt$margin_pt) {
  th <- theme_bw(base_size = base_size) +
    theme(legend.position = "none",
          panel.background = element_rect(fill = bg, colour = NA),
          plot.background = element_rect(fill = "white", colour = NA),
          plot.margin = margin(margin_pt, margin_pt, margin_pt, margin_pt, "pt"),
          axis.title = element_text(size = base_size * 0.95),
          axis.text = element_text(size = base_size * 0.85, colour = "grey20"))
  if (!grid_on) th <- th + theme(panel.grid = element_blank())
  th
}

# Strip a panel's own axis annotation -- what a SHARED-AXES figure does to inner panels:
# the axis TITLES move to the figure level (drawn once, as a distractor grob) and the tick
# labels survive only on the outer edge of the block.
strip_axes <- function(p, drop_x, drop_y) {
  p <- p + theme(axis.title = element_blank())
  if (drop_x) p <- p + theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
  if (drop_y) p <- p + theme(axis.text.y = element_blank(), axis.ticks.y = element_blank())
  p
}

content_bar <- function(seed, base_size, grid_on, bg) {
  set.seed(seed)
  g <- c("Ctl", "Low", "High")[1:sample(2:3, 1)]
  m <- runif(length(g), 40, 100); s <- m * runif(length(g), 0.08, 0.2)
  D <- data.frame(g = factor(g, levels = g), m = m, s = s)
  ggplot(D, aes(g, m)) +
    geom_col(width = 0.6, fill = "grey55", colour = "grey15", linewidth = 0.3) +
    geom_errorbar(aes(ymin = m, ymax = m + s), width = 0.15, linewidth = 0.3) +
    scale_y_continuous(expand = expansion(mult = c(0, 0.08))) +
    labs(x = NULL, y = "Signal (AU)") + pnl_theme(base_size, grid_on, bg)
}

content_scatter <- function(seed, base_size, grid_on, bg) {
  set.seed(seed)
  n <- sample(20:40, 1); x <- runif(n, 0, 10)
  y <- 5 + runif(1, 0.6, 2) * x + rnorm(n, 0, 2)
  ggplot(data.frame(x = x, y = y), aes(x, y)) +
    geom_point(size = 0.9, colour = "grey20") +
    geom_smooth(method = "lm", formula = y ~ x, se = FALSE, linewidth = 0.5, colour = "grey35") +
    labs(x = "Distance (mm)", y = "Density") + pnl_theme(base_size, grid_on, bg)
}

content_line <- function(seed, base_size, grid_on, bg) {
  set.seed(seed)
  d <- c(0, 2, 5, 10, 20, 40)
  D <- do.call(rbind, lapply(c("WT", "KO"), function(s) {
    e <- runif(1, 40, 90); k <- runif(1, 5, 16)
    data.frame(s = s, d = d, y = 20 + e * d / (k + d) + rnorm(length(d), 0, 2))
  }))
  ggplot(D, aes(d, y, group = s, linetype = s)) +
    geom_line(linewidth = 0.45) + geom_point(size = 0.9) +
    labs(x = "Dose (mg/kg)", y = "Response") + pnl_theme(base_size, grid_on, bg)
}

content_box <- function(seed, base_size, grid_on, bg) {
  set.seed(seed)
  g <- c("Sham", "Lesion", "Treat")
  D <- do.call(rbind, lapply(g, function(k)
    data.frame(g = k, y = rnorm(sample(10:20, 1), runif(1, 30, 70), runif(1, 5, 12)))))
  D$g <- factor(D$g, levels = g)
  ggplot(D, aes(g, y)) +
    geom_boxplot(width = 0.55, linewidth = 0.3, outlier.size = 0.6, fill = "grey85") +
    labs(x = NULL, y = "Latency (s)") + pnl_theme(base_size, grid_on, bg)
}

content_heat <- function(seed, base_size, grid_on, bg) {
  set.seed(seed)
  nx <- 8; ny <- 6
  D <- expand.grid(x = 1:nx, y = 1:ny)
  D$z <- as.vector(outer(1:ny, 1:nx, function(i, j) sin(i / 2) + cos(j / 3))) + rnorm(nx * ny, 0, 0.3)
  ggplot(D, aes(x, y, fill = z)) + geom_raster() +
    scale_fill_gradientn(colours = c("#22223b", "#4a7fa5", "#f2e8cf", "#d97706")) +
    scale_x_continuous(expand = c(0, 0)) + scale_y_continuous(expand = c(0, 0)) +
    labs(x = "Gene", y = "Sample") + pnl_theme(base_size, FALSE, bg)
}

CONTENT_FN <- list(bar = content_bar, scatter = content_scatter, line = content_line,
                   box = content_box, heat = content_heat)

# ---- micrograph / image panel (a raster that fills its tile edge to edge) -----
micro_grob <- function(seed, tint = "grey", scalebar = TRUE) {
  set.seed(seed)
  n <- 76; m <- 76
  z <- matrix(runif(n * m, 0.10, 0.26), n, m)
  X <- col(z); Y <- row(z)
  for (k in seq_len(sample(14:26, 1))) {
    cx <- runif(1, 1, m); cy <- runif(1, 1, n); r <- runif(1, 1.8, 5.5); a <- runif(1, 0.45, 0.95)
    z <- z + a * exp(-(((X - cx)^2 + (Y - cy)^2) / (2 * r^2)))
  }
  z <- pmin(1, z)
  col <- switch(tint,
    grey    = grDevices::rgb(z, z, z),
    green   = grDevices::rgb(z * 0.25, z, z * 0.35),
    magenta = grDevices::rgb(z, z * 0.22, z * 0.75),
    blue    = grDevices::rgb(z * 0.25, z * 0.4, z))
  gl <- gList(rasterGrob(matrix(col, n, m), interpolate = TRUE,
                         width = unit(1, "npc"), height = unit(1, "npc")))
  if (scalebar) gl <- gList(gl, rectGrob(x = unit(1, "npc") - unit(6, "pt"), y = unit(6, "pt"),
      width = unit(0.22, "npc"), height = unit(3, "pt"), just = c("right", "bottom"),
      gp = gpar(fill = "white", col = NA)))
  gTree(children = gl)
}

# ============================ layout engine ===================================
# Tiles are given in FRACTIONS of the content area; the gutter knob then insets every
# tile by gutter/2 on all sides, so the gap between two neighbours is exactly `gutterPx`
# and gutterPx = 0 produces genuinely FLUSH panels that share a border.
tile_rects <- function(spec) {
  CA <- spec$contentArea; g <- spec$gutterPx / 2
  lapply(spec$tiles, function(t) {
    x0 <- CA$x + t$x0 * CA$w; x1 <- CA$x + t$x1 * CA$w
    y0 <- CA$y + t$y0 * CA$h; y1 <- CA$y + t$y1 * CA$h
    list(x = x0 + g, y = y0 + g, w = (x1 - x0) - 2 * g, h = (y1 - y0) - 2 * g)
  })
}

# Rank a tile's row/column among its peers (used only to decide which inner axes a
# SHARED-AXES figure strips). Guillotine grids only.
grid_rc <- function(spec) {
  x0 <- sapply(spec$tiles, function(t) t$x0); y0 <- sapply(spec$tiles, function(t) t$y0)
  ux <- sort(unique(round(x0, 3))); uy <- sort(unique(round(y0, 3)))
  list(col = match(round(x0, 3), ux), row = match(round(y0, 3), uy),
       ncol = length(ux), nrow = length(uy))
}

LABEL_PT <- 11

# ---- in-panel ANNOTATION ink (letters that are NOT panel labels) ----------------
# A compact-letter display over the bars, a crossed axis unit "(A)", an inset's own letter:
# all of these put an expected-letter glyph inside a panel at label size. They belong to the
# PANEL (they are drawn in its viewport and so appear in its solo render), which is exactly
# what makes them dangerous -- geometry is unaffected and only the NAMING can go wrong.
# `x`/`y` are npc within the panel's plot viewport (y measured upward, as grid does).
annot <- function(text, x, y, size = LABEL_PT, face = "bold", just = c("centre", "centre"),
                  box = NULL, seed = 1)
  list(text = text, x = x, y = y, size = size, face = face, just = just,
       box = box, seed = seed)

draw_annots <- function(t) {
  for (an in t$annots %||% list()) {
    if (!is.null(an$box)) {
      grid.rect(x = unit(an$box[1], "npc"), y = unit(an$box[2], "npc"),
                width = unit(an$box[3], "npc"), height = unit(an$box[4], "npc"),
                just = c("left", "bottom"),
                gp = gpar(fill = "white", col = "grey25", lwd = 0.8))
      set.seed(an$seed)
      np <- 30
      grid.points(x = unit(an$box[1] + runif(np, 0.08, 0.94) * an$box[3], "npc"),
                  y = unit(an$box[2] + runif(np, 0.10, 0.92) * an$box[4], "npc"),
                  pch = 16, size = unit(2, "pt"), gp = gpar(col = "grey30"))
    }
    grid.text(an$text, x = unit(an$x, "npc"), y = unit(an$y, "npc"), just = an$just,
              gp = gpar(fontsize = an$size, fontface = an$face))
  }
}

# Height (px) of the strip reserved ABOVE the plot when the label sits outside it.
label_strip_px <- function(spec) if (spec$labelPlacement %in% c("outside-al", "top-centre"))
  round(LABEL_PT / 72 * spec$dpi * 1.55) else 0

label_text <- function(letter, fmt) switch(fmt,
  "A" = letter, "(A)" = paste0("(", letter, ")"), "A." = paste0(letter, "."),
  "a" = tolower(letter), "(a)" = paste0("(", tolower(letter), ")"), letter)

# Draw one panel's LETTER inside its tile, at the requested placement.
# On a raster/heat map the letter is drawn white with a thin black outline (the usual
# journal treatment), so it stays legible over both bright and dark image content.
# A letter drawn white-on-dark leaves no ink on a white page, so its SOLO render forces
# every stroke black: same glyphs, same offsets, same box.
draw_label <- function(tile, spec, letter, dark_bg) {
  txt <- label_text(letter, spec$labelFormat)
  col <- if (isTRUE(.pgt$label_black)) "black" else if (dark_bg) "white" else "black"
  pushViewport(viewport(x = unit(tile$x / spec$W, "npc"), y = unit(1 - tile$y / spec$H, "npc"),
                        width = unit(tile$w / spec$W, "npc"), height = unit(tile$h / spec$H, "npc"),
                        just = c("left", "top")))
  pad <- 4
  pos <- switch(spec$labelPlacement,
    "inside-tl"    = list(x = unit(pad, "pt"), y = unit(1, "npc") - unit(pad, "pt"),
                          just = c("left", "top")),
    "outside-al"   = list(x = unit(1, "pt"), y = unit(1, "npc") - unit(2, "pt"),
                          just = c("left", "top")),
    "top-centre"   = list(x = unit(0.5, "npc"), y = unit(1, "npc") - unit(2, "pt"),
                          just = c("centre", "top")),
    "bottom-right" = list(x = unit(1, "npc") - unit(pad, "pt"), y = unit(pad, "pt"),
                          just = c("right", "bottom")),
    NULL)
  # The panel letter is set in the FIGURE's typeface, not always in upright bold sans: a
  # serif-italic label is a normal journal choice and a real coverage case for a detector
  # whose glyph templates are upright.
  face <- spec$labelFace %||% "bold"
  fam <- spec$labelFamily %||% ""
  if (!is.null(pos)) {
    if (dark_bg) for (dx in c(-0.7, 0.7)) for (dy in c(-0.7, 0.7))
      grid.text(txt, x = pos$x + unit(dx, "pt"), y = pos$y + unit(dy, "pt"), just = pos$just,
                gp = gpar(fontface = face, fontfamily = fam, fontsize = LABEL_PT, col = "black"))
    grid.text(txt, x = pos$x, y = pos$y, just = pos$just,
              gp = gpar(fontface = face, fontfamily = fam, fontsize = LABEL_PT, col = col))
  }
  upViewport(1)
}

# ---- figure-level distractor ink (belongs to NO panel; the trap for a naive cutter) ----
draw_legend <- function(r, spec, labels, cols, size = 8, face = "plain") {
  pushViewport(viewport(x = unit(r$x / spec$W, "npc"), y = unit(1 - r$y / spec$H, "npc"),
                        width = unit(r$w / spec$W, "npc"), height = unit(r$h / spec$H, "npc"),
                        just = c("left", "top")))
  n <- length(labels)
  grid.rect(gp = gpar(fill = "white", col = "grey45", lwd = 0.7))
  for (i in seq_len(n)) {
    yy <- unit(1, "npc") - unit(8, "pt") - unit((i - 1) * 15, "pt")
    grid.rect(x = unit(7, "pt"), y = yy, width = unit(9, "pt"), height = unit(9, "pt"),
              just = c("left", "top"), gp = gpar(fill = cols[i], col = "grey25", lwd = 0.5))
    grid.text(labels[i], x = unit(20, "pt"), y = yy - unit(4.5, "pt"),
              just = c("left", "centre"), gp = gpar(fontsize = size, fontface = face))
  }
  upViewport(1)
}

draw_colourbar <- function(r, spec, title = "z-score") {
  pushViewport(viewport(x = unit(r$x / spec$W, "npc"), y = unit(1 - r$y / spec$H, "npc"),
                        width = unit(r$w / spec$W, "npc"), height = unit(r$h / spec$H, "npc"),
                        just = c("left", "top")))
  ramp <- grDevices::colorRampPalette(c("#22223b", "#4a7fa5", "#f2e8cf", "#d97706"))(64)
  grid.raster(matrix(rev(ramp), ncol = 1), x = unit(0.34, "npc"), y = unit(0.5, "npc"),
              width = unit(9, "pt"), height = unit(0.72, "npc"), interpolate = TRUE)
  grid.text(c("2", "0", "-2"), x = unit(0.34, "npc") + unit(8, "pt"),
            y = unit(0.5, "npc") + unit(c(0.36, 0, -0.36), "npc"),
            just = c("left", "centre"), gp = gpar(fontsize = 7))
  grid.text(title, x = unit(0.34, "npc"), y = unit(0.5, "npc") + unit(0.40, "npc"),
            just = c("centre", "bottom"), gp = gpar(fontsize = 7.5))
  upViewport(1)
}

draw_axis_title <- function(r, spec, txt, rot) {
  pushViewport(viewport(x = unit(r$x / spec$W, "npc"), y = unit(1 - r$y / spec$H, "npc"),
                        width = unit(r$w / spec$W, "npc"), height = unit(r$h / spec$H, "npc"),
                        just = c("left", "top")))
  grid.text(txt, rot = rot, gp = gpar(fontsize = 9))
  upViewport(1)
}

# ============================ the renderer ====================================
# `want` selects which elements are drawn; geometry is computed identically in every
# mode, so a solo render lands the element on exactly the pixels it occupies in the
# composite. want = "ALL" for the composite.
wants <- function(want, key) identical(want, "ALL") || key %in% want

render_figure <- function(spec, path, want = "ALL", capture_plotrects = FALSE,
                          label_black = FALSE) {
  tiles <- tile_rects(spec)
  strip <- label_strip_px(spec)
  .pgt$margin_pt <- spec$panelMarginPt %||% 2
  .pgt$label_black <- label_black
  rc <- if (isTRUE(spec$sharedAxes)) grid_rc(spec) else NULL
  png(path, width = spec$W, height = spec$H, res = spec$dpi, type = "cairo")
  grid.newpage(); grid.rect(gp = gpar(fill = "white", col = NA))
  drawn <- list()
  for (i in seq_along(spec$tiles)) {
    t <- spec$tiles[[i]]; tl <- tiles[[i]]
    # the plot region = tile minus the reserved label strip
    pr <- list(x = tl$x, y = tl$y + strip, w = tl$w, h = tl$h - strip)
    ckey <- sprintf("p%d.content", i)
    if (wants(want, ckey)) {
      vpname <- sprintf("tile%02d", i)
      pushViewport(viewport(x = unit(pr$x / spec$W, "npc"), y = unit(1 - pr$y / spec$H, "npc"),
                            width = unit(pr$w / spec$W, "npc"), height = unit(pr$h / spec$H, "npc"),
                            just = c("left", "top"), name = vpname))
      if (t$content == "micrograph") {
        grid.draw(micro_grob(spec$seed * 100 + i, tint = t$tint %||% "grey",
                             scalebar = isTRUE(t$scalebar)))
      } else {
        p <- CONTENT_FN[[t$content]](spec$seed * 100 + i, spec$baseSize,
                                     isTRUE(spec$panelGrid), spec$panelBg %||% "white")
        if (!is.null(rc)) p <- strip_axes(p, drop_x = rc$row[i] < rc$nrow, drop_y = rc$col[i] > 1)
        grid.draw(ggplotGrob(p))
      }
      draw_annots(t)
      upViewport(1)
      drawn[[vpname]] <- i
    }
    if (t$labelDrawn && wants(want, sprintf("p%d.label", i)))
      draw_label(tl, spec, t$label, dark_bg = (t$content %in% c("micrograph", "heat") &&
                 spec$labelPlacement %in% c("inside-tl", "bottom-right")))
  }
  for (j in seq_along(spec$distractors)) {
    d <- spec$distractors[[j]]
    if (!wants(want, sprintf("d%d", j))) next
    r <- d$rectPx
    if (d$kind == "legend") draw_legend(r, spec, d$labels, d$colours,
                                        size = d$size %||% 8, face = d$face %||% "plain")
    else if (d$kind == "colourbar") draw_colourbar(r, spec, d$title %||% "z-score")
    else if (d$kind == "axis-title") draw_axis_title(r, spec, d$text, d$rot %||% 0)
  }
  plotrects <- NULL
  if (capture_plotrects) {
    grid.force()
    L <- grid.ls(viewports = TRUE, grobs = FALSE, print = FALSE)
    plotrects <- vector("list", length(spec$tiles))
    for (vpname in names(drawn)) {
      i <- drawn[[vpname]]
      if (spec$tiles[[i]]$content == "micrograph") next
      sel <- which(grepl(paste0("::", vpname, "(::|$)"), L$vpPath) & grepl("^panel", L$name))
      if (!length(sel)) next
      ok <- tryCatch({ seekViewport(vpname); downViewport(L$name[sel[1]]); TRUE },
                     error = function(e) FALSE)
      if (!ok) next
      bl <- deviceLoc(unit(0, "npc"), unit(0, "npc"), valueOnly = TRUE)
      tr <- deviceLoc(unit(1, "npc"), unit(1, "npc"), valueOnly = TRUE)
      plotrects[[i]] <- list(x = bl$x * spec$dpi, y = spec$H - tr$y * spec$dpi,
                             width = (tr$x - bl$x) * spec$dpi,
                             height = (tr$y - bl$y) * spec$dpi)
      upViewport(0)
    }
  }
  dev.off()
  list(tiles = tiles, plotRects = plotrects, strip = strip)
}

`%||%` <- function(a, b) if (is.null(a)) b else a

# ============================ caption =========================================
CAP_PHRASE <- list(
  bar = c("quantification of %s across groups", "%s levels by treatment group"),
  scatter = c("correlation between %s and cell density", "%s plotted against distance"),
  line = c("dose-response curves for %s", "time course of %s"),
  box = c("distribution of %s by condition", "%s across the three cohorts"),
  heat = c("heat map of %s across samples", "clustered %s expression matrix"),
  micrograph = c("representative micrographs of %s", "confocal images of %s"))
CAP_SUBJ <- c("BDNF", "GFAP immunoreactivity", "dendritic spines", "synaptophysin",
              "microglial density", "c-Fos", "mitochondrial area", "hippocampal CA1")

make_caption <- function(spec, figno, with_letters = TRUE) {
  set.seed(spec$seed + 991)
  head <- sprintf("Figure %d. %s in the %s model.", figno,
                  sample(c("Exercise increases plasticity markers",
                           "Lesion alters regional signalling",
                           "Dose-dependent recovery of function",
                           "Treatment normalises cellular morphology"), 1),
                  sample(c("rodent", "murine", "rat", "transgenic"), 1))
  parts <- character(0)
  for (i in seq_along(spec$tiles)) {
    t <- spec$tiles[[i]]
    ph <- sprintf(sample(CAP_PHRASE[[t$content]], 1), sample(CAP_SUBJ, 1))
    ph <- paste0(toupper(substring(ph, 1, 1)), substring(ph, 2), ".")
    parts <- c(parts, if (with_letters) paste0("(", t$label, ") ", ph) else ph)
  }
  tail <- if (any(sapply(spec$tiles, function(t) t$content == "micrograph")))
    " Scale bars, 50 um. Data are mean +/- s.e.m." else " Data are mean +/- s.e.m."
  paste0(head, " ", paste(parts, collapse = " "), tail)
}

# ============================ GT writer =======================================
# Writes the PARTIAL bundle: everything R knows exactly. finalize_gt.py adds the ink
# boxes measured from the solo renders.
write_part <- function(dir, bundle) {
  writeLines(toJSON(bundle, auto_unbox = TRUE, digits = 6, null = "null", pretty = TRUE),
             file.path(dir, paste0(bundle$id, ".part.json")))
}
