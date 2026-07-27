#!/usr/bin/env Rscript
# gen_panels.R -- generate the PANEL-DETECTION corpus (renders + partial ground truth).
# ---------------------------------------------------------------------------
# The corpus is a DIFFICULTY LADDER over the four knobs that actually break panel
# detectors (see benchmark/panels/RESULTS.md):
#
#   L1 easy         generous gutters, plain grids, labels inside top-left
#   L2 medium       6-panel grids, shared axes, other label placements, ABSENT labels
#   L3 tight        gutters at ~1.2% of figure width, legends sitting IN a gutter,
#                   unequal row/column spans
#   L4 flush        gutter EXACTLY 0 -- abutting panels sharing a border (image mosaics
#                   and shared-axis chart mosaics)
#   L5 non-guillotine  pinwheel / windmill arrangements: no sequence of full-width or
#                   full-height cuts can separate the panels, so recursive XY-cut cannot
#                   express the answer at all
#   L6 stray letters   glyphs whose IDENTITY is an expected panel letter but which are NOT
#                   panel labels: a compact-letter display, crossed parenthesised axis
#                   units, legend keys, an inset's own letter. L1-L5 contained none, which
#                   is why a detector could score 100% on assignment while treating "each
#                   box owns one expected letter" as proof that the labels had been READ.
#   L7 many panels     9 and 12 panels, so the letter run reaches 'I' -- a bare stem that no
#                   shape test can name and that the label-size gates reject outright.
#   L8 typeface        panel letters set in bold serif italic rather than upright sans.
#
# Plus two single-panel controls (a detector must not split one panel into many).
#
#   Run:  Rscript benchmark/panels/gen_panels.R          # -> benchmark/panels/corpus/
#         python3 benchmark/panels/finalize_gt.py        # measures the ink boxes -> GT
# ---------------------------------------------------------------------------
HERE <- tryCatch(dirname(normalizePath(sub("--file=", "",
          grep("--file=", commandArgs(FALSE), value = TRUE)[1]))), error = function(e) ".")
if (is.na(HERE) || HERE == ".") HERE <- file.path(getwd(), "benchmark", "panels")
source(file.path(HERE, "pgt.R"))
CORPUS <- file.path(HERE, "corpus")
ISO <- file.path(CORPUS, "_iso")
dir.create(ISO, showWarnings = FALSE, recursive = TRUE)
for (f in list.files(CORPUS, "\\.(png|json)$", full.names = TRUE)) unlink(f)
for (f in list.files(ISO, "\\.png$", full.names = TRUE)) unlink(f)

# ---- tile helpers -------------------------------------------------------------
grid_tiles <- function(nrow, ncol, contents, letters_ = LETTERS, tints = NULL) {
  out <- list(); k <- 0
  for (r in seq_len(nrow)) for (cc in seq_len(ncol)) {
    k <- k + 1
    t <- list(label = letters_[k], content = contents[[((k - 1) %% length(contents)) + 1]],
              x0 = (cc - 1) / ncol, x1 = cc / ncol, y0 = (r - 1) / nrow, y1 = r / nrow)
    if (!is.null(tints)) { t$tint <- tints[[((k - 1) %% length(tints)) + 1]]; t$scalebar <- TRUE }
    out[[k]] <- t
  }
  out
}
tl <- function(label, content, x0, x1, y0, y1, tint = NULL, scalebar = FALSE, annots = NULL)
  list(label = label, content = content, x0 = x0, x1 = x1, y0 = y0, y1 = y1,
       tint = tint, scalebar = scalebar, annots = annots)
# Attach in-panel annotation letters (see `annot` in pgt.R) to tiles by 1-based index.
with_annots <- function(tiles, spec) {
  for (k in names(spec)) tiles[[as.integer(k)]]$annots <- spec[[k]]
  tiles
}

# PINWHEEL -- the canonical non-guillotine layout. Four panels rotate around the centre;
# no full-width or full-height cut separates any of them. Lettered CLOCKWISE from the top
# (how journals letter these), so reading-order labelling is provably wrong here and the
# detector has to read the drawn letter.
pinwheel4 <- function(contents, a = 1/3) list(
  tl("A", contents[[1]], 0,     1 - a, 0,     a),
  tl("B", contents[[2]], 1 - a, 1,     0,     1 - a),
  tl("C", contents[[3]], a,     1,     1 - a, 1),
  tl("D", contents[[4]], 0,     a,     a,     1))
pinwheel5 <- function(contents, a = 1/3) c(pinwheel4(contents, a),
  list(tl("E", contents[[5]], a, 1 - a, a, 1 - a)))
# same interlock, mirrored (counter-clockwise): a second non-guillotine shape
windmill4 <- function(contents, a = 1/3) list(
  tl("A", contents[[1]], a, 1,     0,     a),
  tl("B", contents[[2]], 1 - a, 1, a,     1),
  tl("C", contents[[3]], 0,     1 - a, 1 - a, 1),
  tl("D", contents[[4]], 0,     a,     0,     1 - a))

# ---- spec builder --------------------------------------------------------------
GUT <- list(wide = 0.050, medium = 0.028, tight = 0.012, vtight = 0.006, zero = 0)

make_spec <- function(id, level, seed, W, H, tiles, layoutName, layoutClass,
                      gutter = "medium", labelPlacement = "inside-tl", labelFormat = "A",
                      labelsDrawn = TRUE, sharedAxes = FALSE, panelGrid = TRUE,
                      baseSize = 8, dpi = 110, panelMarginPt = 2,
                      margin = c(10, 10, 10, 10), distractors = list(),
                      captionLetters = TRUE, figno = 1, notes = character(0),
                      labelFace = "bold", labelFamily = "") {
  gpx <- round(GUT[[gutter]] * W)
  for (i in seq_along(tiles)) {
    tiles[[i]]$labelDrawn <- labelsDrawn
    tiles[[i]]$index <- i - 1
  }
  spec <- list(id = id, level = level, seed = seed, W = W, H = H, dpi = dpi,
               baseSize = baseSize, panelGrid = panelGrid, panelMarginPt = panelMarginPt,
               tiles = tiles, layoutName = layoutName, layoutClass = layoutClass,
               gutterBucketNominal = gutter, gutterPx = gpx,
               labelPlacement = if (labelsDrawn) labelPlacement else "none",
               labelFormat = labelFormat, labelFace = labelFace, labelFamily = labelFamily,
               sharedAxes = sharedAxes,
               contentArea = list(x = margin[4], y = margin[1],
                                  w = W - margin[2] - margin[4], h = H - margin[1] - margin[3]),
               notes = as.list(notes))
  # distractor rects are given as fractions of the FULL figure
  spec$distractors <- lapply(distractors, function(d) {
    d$rectPx <- list(x = d$frac[1] * W, y = d$frac[2] * H, w = d$frac[3] * W, h = d$frac[4] * H)
    d$frac <- NULL
    d
  })
  spec$caption <- make_caption(spec, figno, with_letters = captionLetters)
  spec$expectedLetters <- if (captionLetters)
    as.list(sapply(tiles, function(t) t$label)) else list()
  spec
}

legend_d <- function(frac, labels = c("Control", "Treated"), colours = c("grey70", "#4a7fa5"),
                     size = 8, face = "plain")
  list(kind = "legend", frac = frac, labels = labels, colours = colours,
       size = size, face = face)
cbar_d <- function(frac, title = "z-score") list(kind = "colourbar", frac = frac, title = title)
axtitle_d <- function(frac, text, rot = 0) list(kind = "axis-title", frac = frac, text = text, rot = rot)

# ---- render one spec ------------------------------------------------------------
emit <- function(spec) {
  png_path <- file.path(CORPUS, paste0(spec$id, ".png"))
  comp <- render_figure(spec, png_path, want = "ALL", capture_plotrects = TRUE)
  iso <- list()
  for (i in seq_along(spec$tiles)) {
    cp <- file.path(ISO, sprintf("%s__p%02d_content.png", spec$id, i))
    render_figure(spec, cp, want = sprintf("p%d.content", i))
    lp <- NULL
    if (isTRUE(spec$tiles[[i]]$labelDrawn)) {
      lp <- file.path(ISO, sprintf("%s__p%02d_label.png", spec$id, i))
      render_figure(spec, lp, want = sprintf("p%d.label", i), label_black = TRUE)
    }
    iso[[i]] <- list(content = basename(cp), label = if (is.null(lp)) NULL else basename(lp))
  }
  diso <- list()
  for (j in seq_along(spec$distractors)) {
    dp <- file.path(ISO, sprintf("%s__d%02d.png", spec$id, j))
    render_figure(spec, dp, want = sprintf("d%d", j))
    diso[[j]] <- basename(dp)
  }
  bundle <- list(
    id = spec$id, image = basename(png_path), level = spec$level,
    figure = list(width = spec$W, height = spec$H, dpi = spec$dpi, seed = spec$seed),
    layoutName = spec$layoutName, layoutClass = spec$layoutClass,
    gutterNominalPx = spec$gutterPx, gutterBucketNominal = spec$gutterBucketNominal,
    labelPlacement = spec$labelPlacement, labelFormat = spec$labelFormat,
    sharedAxes = spec$sharedAxes, caption = spec$caption,
    expectedLetters = spec$expectedLetters, notes = spec$notes,
    panels = lapply(seq_along(spec$tiles), function(i) {
      t <- spec$tiles[[i]]; r <- comp$tiles[[i]]
      list(index = i - 1, label = t$label, contentType = t$content,
           labelDrawn = isTRUE(t$labelDrawn),
           tile = list(x = r$x, y = r$y, width = r$w, height = r$h),
           plotRect = if (is.null(comp$plotRects)) NULL else comp$plotRects[[i]],
           iso = iso[[i]])
    }),
    distractors = lapply(seq_along(spec$distractors), function(j) {
      d <- spec$distractors[[j]]
      list(kind = d$kind, rect = list(x = d$rectPx$x, y = d$rectPx$y,
                                      width = d$rectPx$w, height = d$rectPx$h),
           iso = diso[[j]])
    }))
  write_part(CORPUS, bundle)
  cat(sprintf("  %-34s %-14s %-16s gut=%3dpx  %d panels\n", spec$id, spec$level,
              spec$layoutName, spec$gutterPx, length(spec$tiles)))
  invisible(bundle)
}

# ============================ THE LADDER ======================================
cat("Generating PANEL-DETECTION corpus -> benchmark/panels/corpus/\n")
CH <- c("bar", "scatter", "line", "box", "heat")

# ---------------- L1: easy -- generous gutters, plain grids --------------------
emit(make_spec("L1_grid1x2_wide_01", "L1_easy", 1101, 860, 420,
  grid_tiles(1, 2, list("bar", "scatter")), "grid1x2", "guillotine",
  gutter = "wide", figno = 1))
emit(make_spec("L1_grid2x2_wide_02", "L1_easy", 1102, 900, 700,
  grid_tiles(2, 2, list("bar", "scatter", "line", "box")), "grid2x2", "guillotine",
  gutter = "wide", figno = 2))
emit(make_spec("L1_grid1x3_wide_03", "L1_easy", 1103, 1050, 380,
  grid_tiles(1, 3, list("bar", "line", "box")), "grid1x3", "guillotine",
  gutter = "wide", labelPlacement = "outside-al", labelFormat = "(A)", figno = 3))
emit(make_spec("L1_grid2x1_wide_04", "L1_easy", 1104, 520, 760,
  grid_tiles(2, 1, list("scatter", "bar")), "grid2x1", "guillotine",
  gutter = "wide", labelPlacement = "top-centre", figno = 4))
emit(make_spec("L1_grid2x2_wide_micro_05", "L1_easy", 1105, 840, 700,
  grid_tiles(2, 2, list("micrograph"), tints = list("grey", "green", "magenta", "blue")),
  "grid2x2", "guillotine", gutter = "wide", figno = 5))

# ---------------- L2: medium gutters, more panels, label variety ---------------
emit(make_spec("L2_grid2x3_med_06", "L2_medium", 1206, 1080, 640,
  grid_tiles(2, 3, list("bar", "scatter", "line", "box", "bar", "scatter")),
  "grid2x3", "guillotine", gutter = "medium", figno = 6))
emit(make_spec("L2_grid1x4_med_07", "L2_medium", 1207, 1160, 340,
  grid_tiles(1, 4, list("bar", "line", "box", "scatter")), "grid1x4", "guillotine",
  gutter = "medium", labelPlacement = "outside-al", figno = 7))
emit(make_spec("L2_grid2x2_shared_08", "L2_medium", 1208, 880, 680,
  grid_tiles(2, 2, list("scatter")), "grid2x2", "guillotine", gutter = "medium",
  sharedAxes = TRUE, margin = c(10, 10, 34, 34), figno = 8,
  distractors = list(axtitle_d(c(0.10, 0.94, 0.85, 0.055), "Distance from bregma (mm)"),
                     axtitle_d(c(0.004, 0.08, 0.032, 0.84), "Cell density", rot = 90)),
  notes = "figure-level shared axis titles are ink that belongs to no panel"))
emit(make_spec("L2_grid3x1_med_botlabel_09", "L2_medium", 1209, 480, 840,
  grid_tiles(3, 1, list("bar", "box", "line")), "grid3x1", "guillotine",
  gutter = "medium", labelPlacement = "bottom-right", figno = 9))
emit(make_spec("L2_grid2x2_nolabel_10", "L2_medium", 1210, 880, 680,
  grid_tiles(2, 2, list("bar", "line", "box", "heat")), "grid2x2", "guillotine",
  gutter = "medium", labelsDrawn = FALSE, captionLetters = TRUE, figno = 10,
  notes = "no letters drawn, but the caption still names (A)-(D)"))
emit(make_spec("L2_grid1x3_nocap_11", "L2_medium", 1211, 1000, 360,
  grid_tiles(1, 3, list("bar", "scatter", "box")), "grid1x3", "guillotine",
  gutter = "medium", labelsDrawn = FALSE, captionLetters = FALSE, figno = 11,
  notes = "neither drawn letters nor caption letters: the count constraint is unavailable"))
emit(make_spec("L2_grid1x3_heat_cbar_12", "L2_medium", 1212, 1000, 400,
  grid_tiles(1, 3, list("heat")), "grid1x3", "guillotine", gutter = "medium",
  margin = c(10, 74, 10, 10), figno = 12,
  distractors = list(cbar_d(c(0.935, 0.25, 0.06, 0.5))),
  notes = "colourbar in the right margin belongs to no panel"))

# ---------------- L3: tight gutters, legends in gutters, unequal spans ----------
# panelMarginPt = 0 so the INK gap equals the tile gap: with the default 2pt plot margin a
# nominally tight gutter measures ~6px wider and lands in the medium bucket.
emit(make_spec("L3_grid2x2_tight_13", "L3_tight", 1313, 900, 700,
  grid_tiles(2, 2, list("bar", "scatter", "line", "box")), "grid2x2", "guillotine",
  gutter = "tight", panelMarginPt = 0, figno = 13))
emit(make_spec("L3_grid1x3_tight_14", "L3_tight", 1314, 1050, 380,
  grid_tiles(1, 3, list("bar", "line", "box")), "grid1x3", "guillotine",
  gutter = "tight", panelMarginPt = 0, labelPlacement = "outside-al", figno = 14))
emit(make_spec("L3_grid2x2_vtight_15", "L3_tight", 1315, 900, 700,
  grid_tiles(2, 2, list("scatter", "bar", "box", "line")), "grid2x2", "guillotine",
  gutter = "vtight", panelMarginPt = 0, figno = 15,
  notes = "gutter is 0.6% of figure width -- below any fixed minimum-gutter threshold"))
# legend sitting IN the gutter: the column gap is opened up in the layout itself so the
# legend has somewhere to sit, exactly as journals do
emit(make_spec("L3_legend_in_gutter_16", "L3_tight", 1316, 960, 620, list(
    tl("A", "bar",     0,    0.42, 0,   0.5), tl("B", "line", 0.58, 1, 0,   0.5),
    tl("C", "scatter", 0,    0.42, 0.5, 1),   tl("D", "box",  0.58, 1, 0.5, 1)),
  "grid2x2-open-centre", "guillotine", gutter = "vtight", panelMarginPt = 0, figno = 16,
  distractors = list(legend_d(c(0.435, 0.36, 0.13, 0.20),
                              c("Control", "Treated", "Rescue"),
                              c("grey70", "#4a7fa5", "#d97706"))),
  notes = "legend sits in the wide central gutter while the row gutter is tight"))
emit(make_spec("L3_span_top_17", "L3_tight", 1317, 900, 660, list(
    tl("A", "line", 0, 1, 0, 0.5), tl("B", "bar", 0, 0.5, 0.5, 1),
    tl("C", "box", 0.5, 1, 0.5, 1)),
  "span-top-full", "guillotine", gutter = "tight", panelMarginPt = 0, figno = 17,
  notes = "unequal row spans: A spans both columns"))
emit(make_spec("L3_span_left_18", "L3_tight", 1318, 900, 640, list(
    tl("A", "heat", 0, 0.5, 0, 1), tl("B", "bar", 0.5, 1, 0, 0.5),
    tl("C", "scatter", 0.5, 1, 0.5, 1)),
  "span-left-tall", "guillotine", gutter = "tight", panelMarginPt = 0, figno = 18,
  notes = "one tall panel beside two stacked (still guillotine: cut x then y)"))
emit(make_spec("L3_mixed_tight_19", "L3_tight", 1319, 960, 400, list(
    tl("A", "micrograph", 0, 0.34, 0, 1, tint = "green", scalebar = TRUE),
    tl("B", "micrograph", 0.34, 0.68, 0, 1, tint = "magenta", scalebar = TRUE),
    tl("C", "bar", 0.68, 1, 0, 1)),
  "grid1x3-mixed", "guillotine", gutter = "tight", figno = 19,
  notes = "raster panels abut a chart panel"))

# ---------------- L4: FLUSH -- gutter exactly zero ------------------------------
emit(make_spec("L4_mosaic2x2_flush_20", "L4_flush", 1420, 720, 720,
  grid_tiles(2, 2, list("micrograph"), tints = list("grey", "green", "magenta", "blue")),
  "mosaic2x2", "guillotine", gutter = "zero", figno = 20,
  notes = "image mosaic with zero gutter: neighbouring panels share an edge"))
emit(make_spec("L4_mosaic1x4_flush_nolabel_21", "L4_flush", 1421, 1080, 300,
  grid_tiles(1, 4, list("micrograph"), tints = list("grey", "green", "magenta", "blue")),
  "mosaic1x4", "guillotine", gutter = "zero", labelsDrawn = FALSE, figno = 21))
emit(make_spec("L4_charts1x3_flush_22", "L4_flush", 1422, 1020, 360,
  grid_tiles(1, 3, list("scatter")), "charts1x3-flush", "guillotine", gutter = "zero",
  sharedAxes = TRUE, panelMarginPt = 0, labelPlacement = "top-centre",
  margin = c(10, 10, 34, 40), figno = 22,
  distractors = list(axtitle_d(c(0.10, 0.93, 0.85, 0.06), "Distance (mm)"),
                     axtitle_d(c(0.004, 0.08, 0.034, 0.80), "Cell density", rot = 90)),
  notes = "shared-axis chart mosaic: inner axes stripped, panels share a border line"))
emit(make_spec("L4_charts2x2_flush_23", "L4_flush", 1423, 860, 660,
  grid_tiles(2, 2, list("heat")), "charts2x2-flush", "guillotine", gutter = "zero",
  sharedAxes = TRUE, panelMarginPt = 0, margin = c(10, 10, 30, 36), figno = 23,
  distractors = list(axtitle_d(c(0.10, 0.94, 0.85, 0.05), "Gene"),
                     axtitle_d(c(0.004, 0.10, 0.034, 0.78), "Sample", rot = 90))))
emit(make_spec("L4_mixed_flush_24", "L4_flush", 1424, 840, 640, list(
    tl("A", "micrograph", 0, 0.5, 0, 0.5, tint = "green", scalebar = TRUE),
    tl("B", "micrograph", 0.5, 1, 0, 0.5, tint = "magenta", scalebar = TRUE),
    tl("C", "bar", 0, 0.5, 0.5, 1), tl("D", "box", 0.5, 1, 0.5, 1)),
  "mixed2x2-flush", "guillotine", gutter = "zero", panelMarginPt = 0, figno = 24,
  notes = "raster row flush against a chart row"))
emit(make_spec("L4_mosaic3x2_flush_cbar_25", "L4_flush", 1425, 900, 620,
  grid_tiles(2, 3, list("micrograph"),
             tints = list("grey", "green", "magenta", "blue", "grey", "green")),
  "mosaic2x3", "guillotine", gutter = "zero", labelPlacement = "bottom-right",
  margin = c(10, 70, 10, 10), figno = 25,
  distractors = list(cbar_d(c(0.94, 0.22, 0.055, 0.56), "intensity"))))

# ---------------- L5: NON-GUILLOTINE -------------------------------------------
emit(make_spec("L5_pinwheel4_med_26", "L5_nonguillotine", 1526, 880, 720,
  pinwheel4(list("bar", "line", "box", "scatter")), "pinwheel4", "non-guillotine",
  gutter = "medium", figno = 26,
  notes = "no full-width or full-height cut separates these panels"))
emit(make_spec("L5_pinwheel4_tight_27", "L5_nonguillotine", 1527, 880, 720,
  pinwheel4(list("scatter", "bar", "line", "box")), "pinwheel4", "non-guillotine",
  gutter = "tight", panelMarginPt = 0, figno = 27))
emit(make_spec("L5_pinwheel5_med_28", "L5_nonguillotine", 1528, 920, 780,
  pinwheel5(list("bar", "line", "box", "scatter", "heat")), "pinwheel5", "non-guillotine",
  gutter = "medium", labelPlacement = "outside-al", figno = 28))
emit(make_spec("L5_pinwheel5_tight_cbar_29", "L5_nonguillotine", 1529, 980, 780,
  pinwheel5(list("heat", "bar", "line", "box", "heat")), "pinwheel5", "non-guillotine",
  gutter = "tight", panelMarginPt = 0, margin = c(10, 72, 10, 10), figno = 29,
  distractors = list(cbar_d(c(0.945, 0.28, 0.05, 0.44)))))
emit(make_spec("L5_windmill4_tight_30", "L5_nonguillotine", 1530, 900, 720,
  windmill4(list("micrograph", "bar", "micrograph", "line")), "windmill4", "non-guillotine",
  gutter = "tight", figno = 30, notes = "mirrored pinwheel, mixed raster/chart content"))
emit(make_spec("L5_pinwheel4_flush_31", "L5_nonguillotine", 1531, 840, 700,
  pinwheel4(list("micrograph", "micrograph", "micrograph", "micrograph")),
  "pinwheel4", "non-guillotine", gutter = "zero", figno = 31,
  notes = "non-guillotine AND flush: the hardest cell of the ladder"))

# ---------------- L6: STRAY EXPECTED-LETTER DISTRACTORS -------------------------
# The blind spot of the ladder above: not one figure in it contained a letter-shaped glyph
# whose IDENTITY is an expected panel letter but which is NOT a panel label. Every figure
# either had readable labels in reading-order-consistent places or had none, so "each box
# owns exactly one expected letter" was, on this corpus, equivalent to "the labels were
# read" -- and a detector that treated the first as proof of the second scored 100% on the
# assignment metric while being trivially invertible. Adversarial probing found three live
# exploits (a swapped compact-letter display, crossed parenthesised axis units, and a
# legend key that dragged a panel boundary). These six figures put that class in the corpus.
CLD <- LABEL_PT   # strays at LABEL size: the hard case, not the polite one

emit(make_spec("L6_cld_labels_34", "L6_strayletters", 1634, 900, 700,
  with_annots(grid_tiles(2, 2, list("bar")), list(
    "3" = list(annot("a", 0.34, 0.62, CLD), annot("b", 0.66, 0.74, CLD)),
    "4" = list(annot("a", 0.34, 0.70, CLD), annot("b", 0.66, 0.58, CLD)))),
  "grid2x2", "guillotine", gutter = "medium", figno = 34,
  notes = paste("panels C and D carry a compact-letter display ('a', 'b' over the bars) at",
                "LABEL size: expected-letter glyphs that are not labels, competing with the",
                "real A and B. Getting A-D right here needs the placement evidence, not just",
                "the letter identity")))

emit(make_spec("L6_cld_nolabel_35", "L6_strayletters", 1635, 900, 700,
  with_annots(grid_tiles(2, 2, list("bar")), list(
    "1" = list(annot("d", 0.5, 0.55, CLD)), "2" = list(annot("c", 0.5, 0.55, CLD)),
    "3" = list(annot("b", 0.5, 0.55, CLD)), "4" = list(annot("a", 0.5, 0.55, CLD)))),
  "grid2x2", "guillotine", gutter = "medium", labelsDrawn = FALSE, figno = 35,
  notes = paste("NO panel labels are drawn, and the only expected-letter glyphs in the",
                "figure are a compact-letter display in REVERSE order, one per panel, in the",
                "middle of each plot. A detector that treats letter identity as label",
                "evidence names every panel wrongly with full 'verification'. The only",
                "correct behaviours are reading-order letters or abstention")))

emit(make_spec("L6_units_crossed_36", "L6_strayletters", 1636, 900, 560,
  with_annots(grid_tiles(2, 1, list("line", "scatter")), list(
    "1" = list(annot("(B)", 0.055, 0.5, CLD)),
    "2" = list(annot("(A)", 0.055, 0.5, CLD)))),
  "grid2x1", "guillotine", gutter = "medium", labelsDrawn = FALSE, figno = 36,
  notes = paste("crossed parenthesised axis units: the TOP panel is annotated '(B)' and the",
                "BOTTOM one '(A)', at mid-height against the y axis. The detector's glyph",
                "templates deliberately include the '(X)' label form, so these read as",
                "perfect swapped labels. Placement -- mid-panel, not in a label band -- is",
                "the only thing that distinguishes them")))

emit(make_spec("L6_legend_keys_37", "L6_strayletters", 1637, 1020, 460,
  grid_tiles(1, 3, list("bar", "line", "box")), "grid1x3", "guillotine",
  gutter = "medium", margin = c(10, 96, 10, 10), figno = 37,
  distractors = list(legend_d(c(0.905, 0.28, 0.085, 0.30), c("A", "B", "C"),
                              c("grey70", "#4a7fa5", "#d97706"), size = 10, face = "bold")),
  notes = paste("the shared legend's keys ARE the letters A, B and C, at label weight, in a",
                "figure whose panels are also A, B and C -- three perfect decoys sitting in",
                "the right margin, belonging to no panel")))

emit(make_spec("L6_inset_letter_38", "L6_strayletters", 1638, 900, 520, list(
    tl("A", "scatter", 0, 0.5, 0, 1, annots = list(
       annot("b", 0.60, 0.86, CLD, just = c("left", "top"),
             box = c(0.56, 0.42, 0.40, 0.50), seed = 38))),
    tl("B", "line", 0.5, 1, 0, 1)),
  "grid1x2", "guillotine", gutter = "medium", labelPlacement = "outside-al", figno = 38,
  notes = paste("panel A contains an INSET whose own letter is 'b', drawn at label size at",
                "the inset's top-left -- a label-shaped glyph in a label-shaped position,",
                "competing with the real B one panel to the right")))

# ---------------- L7: panel counts that reach 'I' -------------------------------
# 'I' is a bare vertical stem: no shape test can tell it from a lowercase 'l', and the
# label-size gates reject a solid stem outright. So every figure whose caption reaches (I)
# used to lose exactly one anchor and abstain -- a systematic hole over 9- and 12-panel
# figures that no figure in the ladder above could show.
emit(make_spec("L7_grid3x3_ai_39", "L7_manypanels", 1739, 1080, 900,
  grid_tiles(3, 3, list("bar", "scatter", "line", "box", "bar", "line", "scatter", "box", "bar")),
  "grid3x3", "guillotine", gutter = "medium", labelPlacement = "outside-al", figno = 39,
  notes = paste("nine panels, so the caption and the drawn labels both reach (I). The label",
                "strip is reserved above each plot so nothing here is confounded with the",
                "label-welded-to-a-tick-number case -- L7_grid4x3_al_40 is the version that",
                "does collide")))
emit(make_spec("L7_grid4x3_al_40", "L7_manypanels", 1740, 1000, 1120,
  grid_tiles(4, 3, list("bar", "scatter", "line", "box")), "grid4x3", "guillotine",
  gutter = "medium", figno = 40,
  notes = "twelve panels A-L: 'I' and 'l' are both expected, so a stem is ambiguous twice over"))

# ---------------- L8: label TYPEFACE --------------------------------------------
emit(make_spec("L8_serif_italic_41", "L8_typeface", 1841, 900, 700,
  grid_tiles(2, 2, list("bar", "scatter", "line", "box")), "grid2x2", "guillotine",
  gutter = "medium", labelFace = "bold.italic", labelFamily = "serif", figno = 41,
  notes = "panel letters set in bold serif ITALIC, as many journals do"))

# ---------------- controls: a single panel must NOT be split --------------------
emit(make_spec("C_single_chart_32", "C_control", 1632, 620, 460,
  list(tl("A", "line", 0, 1, 0, 1)), "single", "guillotine", gutter = "wide",
  labelsDrawn = FALSE, captionLetters = FALSE, figno = 32,
  distractors = list(legend_d(c(0.62, 0.14, 0.20, 0.14), c("WT", "KO"),
                              c("grey70", "#4a7fa5"))),
  notes = "ONE panel with an inset legend: over-splitting here is a false positive"))
emit(make_spec("C_single_micro_33", "C_control", 1633, 520, 520,
  list(tl("A", "micrograph", 0, 1, 0, 1, tint = "green", scalebar = TRUE)),
  "single", "guillotine", gutter = "wide", labelsDrawn = FALSE, captionLetters = FALSE,
  figno = 33, notes = "ONE raster panel"))

parts <- list.files(CORPUS, pattern = "\\.part\\.json$")
cat(sprintf("\nDONE: %d figures rendered (composite + solo renders in %s)\n",
            length(parts), ISO))
cat("Next: python3 benchmark/panels/finalize_gt.py\n")
