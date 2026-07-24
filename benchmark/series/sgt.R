# sgt.R -- SERIES / GROUP ground-truth helpers (the parsing tier).
# ---------------------------------------------------------------------------
# Additive layer on top of ../r/rgt.R (which is left untouched). rgt.R already
# recovers exact device pixels for drawn marks; what PARSING needs on top of that is:
#
#   1. LEGEND GEOMETRY -- the device pixel of every legend swatch (key) and of its
#      text label, plus the label STRING read straight off the drawn grob. Recovered
#      from the forced grid viewport tree: ggplot2 gives every key its own viewport
#      named `key-<r>-<c>-bg` and every label one named `label-<r>-<c>`, so
#      seekViewport + grid::deviceLoc yields the same top-left pixel convention rgt.R
#      uses for marks. Verified against right/top/inside/reversed/shape legends.
#   2. MARK -> (groupId, seriesId) BINDING -- recovered from the DRAWN AESTHETICS
#      (fill/colour/shape/linetype + the dodged x), never from row order, so the
#      binding cannot drift if ggplot reorders layer data.
#   3. An objective OCCLUSION INDEX so "dense/occluded" is a measured stratum rather
#      than an asserted one.
#   4. Seeded mark-id shuffling, so a task file's mark ORDER leaks no structure.
# ---------------------------------------------------------------------------
suppressMessages({library(ggplot2); library(grid); library(jsonlite)})

# ---- legend geometry ---------------------------------------------------------
# Must be called AFTER grid.draw(gtable) + grid.force() and BEFORE dev.off().
# Returns entries ordered by reading order (row, then column) = the LEGEND ORDER.
legend_geometry <- function(H, DPI) {
  L <- grid.ls(viewports = TRUE, grobs = TRUE, print = FALSE)
  vps <- unique(L$name[L$type == "vpListing"])
  keyv <- grep("^key-[0-9]+-[0-9]+-bg", vps, value = TRUE)
  labv <- grep("^label-[0-9]+-[0-9]+", vps, value = TRUE)
  if (!length(keyv)) return(list())
  rc <- function(nm) as.integer(regmatches(nm, regexec("^(?:key|label)-([0-9]+)-([0-9]+)", nm))[[1]][2:3])
  ctr <- function(nm) {
    seekViewport(nm)
    d  <- deviceLoc(unit(0.5, "npc"), unit(0.5, "npc"), valueOnly = TRUE)
    bl <- deviceLoc(unit(0, "npc"), unit(0, "npc"), valueOnly = TRUE)
    tr <- deviceLoc(unit(1, "npc"), unit(1, "npc"), valueOnly = TRUE)
    upViewport(0)
    list(px = d$x * DPI, py = H - d$y * DPI,
         w = abs(tr$x - bl$x) * DPI, h = abs(tr$y - bl$y) * DPI)
  }
  # the label STRING, read off the drawn text grob inside the label viewport
  labtext <- function(nm) {
    L2 <- grid.ls(viewports = TRUE, grobs = TRUE, print = FALSE)
    sel <- which(grepl(paste0("::", nm, "$"), L2$vpPath) &
                 L2$type %in% c("gTreeListing", "grobListing"))
    for (i in sel) {
      pat <- paste0("^", gsub("([][(){}.*+?^$|\\\\])", "\\\\\\1", L2$name[i]), "$")
      g <- tryCatch(grid.get(pat, grep = TRUE), error = function(e) NULL)
      lb <- tryCatch(g$label, error = function(e) NULL)
      if (!is.null(lb) && length(lb)) return(as.character(lb)[1])
      ch <- tryCatch(g$children, error = function(e) NULL)
      if (!is.null(ch)) for (k in seq_along(ch)) {
        lb <- tryCatch(ch[[k]]$label, error = function(e) NULL)
        if (!is.null(lb) && length(lb)) return(as.character(lb)[1])
      }
    }
    NA_character_
  }
  keys <- lapply(keyv, function(k) c(list(rc = rc(k)), ctr(k)))
  labs <- lapply(labv, function(k) c(list(rc = rc(k), text = labtext(k)), ctr(k)))
  # pair key(r,c) with label(r,c+1); order by (row, col) = reading order
  ord <- order(sapply(keys, function(k) k$rc[1]), sapply(keys, function(k) k$rc[2]))
  out <- list()
  for (i in ord) {
    k <- keys[[i]]
    lb <- NULL
    for (l in labs) if (l$rc[1] == k$rc[1] && l$rc[2] == k$rc[2] + 1) lb <- l
    out[[length(out) + 1]] <- list(
      legendIndex = length(out),
      keyPx = list(px = k$px, py = k$py), keyW = k$w, keyH = k$h,
      labelPx = if (is.null(lb)) NULL else list(px = lb$px, py = lb$py),
      labelText = if (is.null(lb)) NA_character_ else lb$text)
  }
  out
}

# render a ggplot AND capture build + per-panel mappers + legend geometry
render_map_legend <- function(p, path, W, H, DPI) {
  png(path, width = W, height = H, res = DPI, type = "cairo")
  b <- ggplot_build(p)
  g <- ggplot_gtable(b)
  grid.newpage(); grid.draw(g); grid.force()
  nps <- length(b$layout$panel_params)
  mappers <- lapply(seq_len(nps), function(i) make_panel_mapper(b, i, H, DPI))
  lg <- legend_geometry(H, DPI)
  dev.off()
  list(build = b, mappers = mappers, legend = lg)
}

# ---- mark -> series binding from the DRAWN aesthetics -------------------------
# key = the aesthetic signature that distinguishes series in this chart:
#   'fill' | 'colour' | 'shape' | 'colour+shape' | 'colour+linetype'
aes_signature <- function(df, cue) {
  parts <- strsplit(cue, "\\+")[[1]]
  do.call(paste, c(lapply(parts, function(a) as.character(df[[a]])), sep = "|"))
}

# Build a lookup from the aesthetic signature to seriesIndex (0-based).
series_lookup <- function(series_defs, cue) {
  parts <- strsplit(cue, "\\+")[[1]]
  sig <- sapply(series_defs, function(s) {
    paste(sapply(parts, function(a) as.character(s[[
      if (a %in% c("fill", "colour")) "colorHex" else a]])), collapse = "|")
  })
  if (anyDuplicated(sig)) stop("series aesthetic signatures are not unique: ", paste(sig, collapse = ", "))
  setNames(seq_along(series_defs) - 1L, sig)
}

# drawn marker radius in device pixels for a ggplot2 `size` (mm-ish -> points -> px)
marker_radius_px <- function(size, DPI, stroke = 0.5)
  (size * 2.845276 + stroke * 96 / 25.4 / 2) / 72.27 * DPI / 2

# ---- occlusion index ---------------------------------------------------------
# fraction of marks that have >=1 mark of a DIFFERENT series within 2*marker radius
# (i.e. ink that a reader must disentangle), plus the median nearest-other distance.
occlusion_index <- function(px, py, sidx, radius_px) {
  n <- length(px)
  if (n < 2) return(list(index = 0, medianNearestOther = NA_real_, bucket = "none"))
  touch <- 0; nearest <- numeric(n)
  for (i in seq_len(n)) {
    d <- sqrt((px - px[i])^2 + (py - py[i])^2)
    d[i] <- Inf
    other <- which(sidx != sidx[i])
    nearest[i] <- if (length(other)) min(d[other]) else Inf
    if (is.finite(nearest[i]) && nearest[i] <= 2 * radius_px) touch <- touch + 1
  }
  idx <- touch / n
  list(index = idx, medianNearestOther = stats::median(nearest[is.finite(nearest)]),
       bucket = if (idx < 0.10) "none" else if (idx < 0.40) "moderate" else "severe")
}

# ---- seeded mark-id shuffling ------------------------------------------------
# Assigns m001..mNNN in a SHUFFLED order so the task file's mark ordering carries
# no information about series or group membership.
shuffle_marks <- function(marks, seed) {
  set.seed(seed + 77777)
  ord <- sample(seq_along(marks))
  out <- vector("list", length(marks))
  for (j in seq_along(ord)) {
    m <- marks[[ord[j]]]
    m$markId <- sprintf("m%03d", j)
    out[[j]] <- m
  }
  out
}

# ---- bundle writer -----------------------------------------------------------
write_sgt <- function(dir, bundle) {
  path <- file.path(dir, paste0(bundle$id, ".sgt.json"))
  writeLines(toJSON(bundle, auto_unbox = TRUE, digits = 8, null = "null", pretty = TRUE), path)
  path
}
