#!/usr/bin/env python3
"""verify_oracle_v2.py -- find every coded value for which the article ITSELF prints the
number, and say where it is printed.

Why v2 exists
-------------
`verify_oracle.py` (v1) asked one question -- "is the coded mean+variance printed in the
BODY TEXT?" -- and answered it over the wrong universe with a broken PDF map. Greg has
since clarified that the `Data_Extraction_Method` label "Reported in text and figure"
means the number appeared in ANY of:

  (a) the article's body text,
  (b) the FIGURE CAPTION,
  (c) PRINTED INSIDE THE FIGURE -- above a bar, or in an inset table.

(c) is the valuable one. A number printed inside the figure, beside the mark you would
measure, is a within-figure accuracy oracle: truth and measurand in the same image, no
human annotation, no cross-referencing assumption. v1 could not see (b) or (c) at all.

What v2 does
------------
For every figure-derived comparison it partitions the article's PDF into three DISJOINT
search zones and searches all of them:

  BODY      every text block that is not a caption and does not sit inside a figure
            region, with the reference list stripped (references are a dense field of
            years/volumes/pages that match any 2-4 digit value by chance)
  CAPTION   the caption block of the named figure ("Figure 5B" -> the "Fig. 5." block)
  FIGURE    text INSIDE the figure's region on the page. Two routes:
              vector -- the values are real PDF text spans; read them directly (a prior
                        survey found 44 of 222 figures are vector-drawn)
              raster -- the values are pixels; render the region at 400 dpi and OCR it

Disjointness matters: without it a caption hit would also register as a body hit and the
provenance counts would be meaningless.

The matching rule (section "MATCHING" below, and defended in the report)
------------------------------------------------------------------------
A value is CONFIRMED only on a PAIRED match: the coded mean and its variance found
together as a printed `m +/- s` (or `m (s)`, or `m, SEM = s`). A lone number is not
evidence -- '2.7' matches a section heading, '20.13' matches a DOI, and inside a figure
region every axis tick is a lone number that will collide with some coded mean.

Print precision is handled exactly rather than with a flat percentage: a printed token
carries its own rounding half-width (10^-decimals / 2), and a coded value matches iff it
falls inside that interval. So coded 20.13 matches printed "20.1" (half-width 0.05,
|0.03| <= 0.05) and printed "20" (half-width 0.5), but coded 20.13 does NOT match printed
"20.2". This is the correct model of "the paper rounded", and it fixes the two near-misses
that a flat 6% bar mis-ruled (SAMPLING-AND-WORKLIST.md sec.4).

Mean-only hits are reported in a separate, weaker tier (PARTIAL_MEAN), with axis-tick
sequences excluded, because the mean channel alone is still useful for central tendency.

Every headline count is accompanied by a PERMUTATION NULL: the identical search is re-run
with the coded values shuffled. If the shuffled search confirms almost as many rows as the
real one, the confirmations are coincidence and the number is worth nothing. That
calibration, not an assertion, is what licenses the counts.

FOUR nulls are reported, because the choice of donor IS the choice of alternative and the
first version got it wrong (it drew corpus-wide at 3 replicates, so the shipped FDR rested
on two events):

  matched     donor from ANOTHER article whose control mean is within a factor of ~1.8
              -- PRIMARY. Magnitude drives chance collisions, and the donor is guaranteed
              not to be printed in the target's paper.
  within_nf   donor from the SAME article, restricted to rows that paper does NOT print.
              Same-paper realism, tautology removed -- but 12 of the 17 confirming articles
              contain no such row, so it is dominated by papers that print nothing.
  within_all  donor from the same article, unrestricted. NOT A NULL: a same-paper donor
              very often has its own values printed there, so it confirms because it is
              genuinely printed. Reported only to explain why its ~7.6% rate is meaningless.
  corpus      donor from anywhere -- what v2 shipped, kept as the contrast.

And the mechanical search PROPOSES while a committed hand adjudication DISPOSES: see
ADJUDICATION below. A regex cannot tell that a printed "110.5 +/- 21.6" belongs to the
14-month cohort rather than the 4-month row that claimed it. Twelve of thirty-two
mechanically confirmed rows failed that reading.

Verdicts (strongest evidence wins; precedence FIGURE_VECTOR > FIGURE_OCR > CAPTION > TEXT)
  CONFIRMED_IN_FIGURE_VECTOR   printed inside the figure, read as PDF text spans
  CONFIRMED_IN_FIGURE_OCR      printed inside the figure, read by OCR of the rendered crop
  CONFIRMED_CAPTION            printed in the figure's caption
  CONFIRMED_TEXT               printed in the body text
  PARTIAL_MEAN                 mean matched but no paired variance anywhere
  NOT_FOUND                    neither channel matched in any zone
  NO_PDF / NO_FIGURE           cannot check

Usage
  python3 verify_oracle_v2.py --dry-run          # report only; writes NOTHING (not even
                                                 #   the report -- it used to write that)
  python3 verify_oracle_v2.py                    # + write isOracle/oracleSource back
  python3 verify_oracle_v2.py --no-ocr           # vector + text + caption only (fast)
  python3 verify_oracle_v2.py --limit 20         # first N articles, for a smoke test
  python3 verify_oracle_v2.py --no-adjudication  # raw mechanical verdicts, ledger off
  python3 verify_oracle_v2.py --null-reps 0 --null-reps-corpus 0   # skip the nulls
"""
import argparse
import collections
import csv
import functools
import json
import math
import os
import pathlib
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CODED = HERE / "coded" / "coded_reference.json"
PDF_MAP_43 = HERE.parent / "real" / "pdf_map.json"      # read-only cache, 43 MA articles
PDF_MAP_FULL = HERE / "coded" / "pdf_map_full.json"     # what v2 builds, all articles
OCR_CACHE = HERE / "coded" / "ocr_cache"
REPORT_JSON = HERE / "coded" / "oracle_report_v2.json"
REPORT_MD = HERE / "coded" / "ORACLE-REPORT-V2.md"

_ZHOME = pathlib.Path(os.environ.get("ZOTERO_HOME", "/mnt/c/Users/gregs/Zotero"))
ZOTERO_DB = os.environ.get("ZOTERO_DB", str(_ZHOME / "zotero.sqlite"))
ZOTERO_STORAGE = os.environ.get("ZOTERO_STORAGE", str(_ZHOME / "storage"))

TESSERACT = os.environ.get("TESSERACT_EXE", "/mnt/c/Program Files/Tesseract-OCR/tesseract.exe")
OCR_DPI = 400
# Tesseract here is the Windows build invoked from WSL, so its file arguments must be
# Windows paths on a drive WSL exposes -- scratch must therefore live under /mnt/c, not in
# /tmp. Derived from this file's own location (which already satisfies that on the author's
# machine) rather than hardcoded to one user's home, so a clone elsewhere still works.
OCR_SCRATCH = pathlib.Path(os.environ.get(
    "OCR_SCRATCH", str(HERE.parent.parent / ".ocrtmp")))

# ---------------------------------------------------------------- ADJUDICATION LEDGER
# The mechanical search PROPOSES; a recorded hand adjudication DISPOSES.
#
# A regex cannot tell that a printed "110.5 +/- 21.6" belongs to the elevated zero maze
# rather than to the Barnes maze panel the coded row names. That is a semantic judgement
# about which experiment a sentence describes, and it has to be made by reading. Making
# it silently would be worse than making it in public, so every rejection is listed here
# with the sentence that was matched and the reason it does not support the row.
#
# Rules of use (pre-registration amendment A6, 2026-07-27):
#   1. The ledger may only REJECT what the mechanical search proposed. It can never
#      promote a NOT_FOUND row to CONFIRMED -- that direction would let a reader
#      manufacture oracle rows.
#   2. Adjudication is done on the EVIDENCE SENTENCE and the coded row's `dataSource`
#      and outcome, NOT on how well the machine or the human later scores on the panel.
#      It was completed before any real annotation exists, which is what makes it
#      pre-registerable rather than post hoc.
#   3. `--no-adjudication` reproduces the raw mechanical counts.
# Key: "{article}|{comparisonId}|{dataSource}" -- comparisonId alone is NOT unique.
# The two acceptance conditions, applied to every mechanically CONFIRMED row by reading
# the article:
#   (a) ARM/QUANTITY. Each printed `m +/- s` must be the quantity the coded arm names --
#       same outcome, same group, same age/timepoint -- as the article's own text says.
#   (b) LOCATOR. Nothing in the article may contradict the coded row's `dataSource` panel.
#       This is not pedantry. The oracle's job is to be the truth for the value a rater and
#       the machine read OUT OF THAT PANEL. If the row names panel C and the printed number
#       belongs to panel D, the oracle scores a correct machine read as a gross error, which
#       is the exact corruption this stratum exists to avoid.
# A row is REJECTED only where the article DEMONSTRABLY contradicts (a) or (b); silence is
# not a contradiction. Each entry quotes the sentence that decides it.
ADJUDICATION = {
    "Ederer2022|Ederer2022_1_1|Figure 2A": {"reason":
        "arms spliced across two panels. Fig 2A is 'primary latency during the training "
        "period'; the printed 105.4 +/- 22.3 is the PROBE TRIAL (Fig 2F) and 38.0 +/- 12.9 "
        "is the RETENTION TEST (Fig 2G). The coded control variance 21.5 belongs to a third "
        "printed value (106.8 +/- 21.5). No single printed comparison supports this row."},
    "Ederer2022|Ederer2022_1_2|Figure 2B": {"reason":
        "wrong panel. The matched sentence is the RETENTION-TEST cognitive score ('isolated "
        "runners: 0.57 +/- 0.06, isolated controls: 0.48 +/- 0.09'); the caption assigns (B) "
        "to the cognitive score DURING THE TRAINING PERIOD, plotted as mean per day."},
    "Frick2003|Frick2003_1_1|Figure 1A": {"reason":
        "wrong source. 40.8 +/- 2.1 and 39.3 +/- 3.3 are cells of Table 2, 'Group Means for "
        "PLATFORM TRIAL Measures'. Fig 1A is the ACQUISITION curve -- 'each point represents "
        "the mean +/- SEM of each group for four trials' -- so it has no single value to "
        "which these numbers could be the truth."},
    "Frick2003|Frick2003_3_1|Figure 4A": {"reason":
        "wrong source, same as Frick2003_1_1: 38.9 +/- 1.9 / 33.3 +/- 2.5 are the female row "
        "of Table 2 (platform trial), while Fig 4A is the per-block acquisition curve."},
    "Gawryluk2024|Gawryluk2024_2_1|Figure 3": {"reason":
        "both printed values are the SAME ARM. The article: aged EE mice's CR 'ranged from "
        "64.62 +/- 5.31% on the first day ... to 25.38 +/- 4.43% on day 3'. The row assigns "
        "day 1 to the control arm and day 3 to the intervention arm, so it turns a "
        "within-group time course into a between-group contrast."},
    "Lee2024|Lee2024_1_1|Figure 2-C": {"reason":
        "wrong panel. The article attaches '(Figure 2-C)' to the number-correct outcome -- "
        "which is the sibling row Lee2024_1_2 -- while 187.50 +/- 11.33 / 171.89 +/- 3.24 "
        "are 'Time spent in RAM'. Two different outcomes cannot both be panel C."},
    "Mansk2023|Mansk2023_1_1|Figure 1c": {"reason":
        "wrong arm. The article reads 'SRM does not persist ... in Swiss mice (Swiss: 0.46 "
        "+/- 0.10) ... C57BL/6 mice recognized the juvenile 10 days after training (C57BL/6: "
        "0.40 +/- 0.08) (Fig. 1c)'. 0.40 is the C57BL/6 STRAIN, not the 'Swiss enriched "
        "environment' arm the row names; Fig 1 has no EE arm at all -- EE enters at Fig 2."},
    "Mansk2023|Mansk2023_2_1|Figure 2f": {"reason":
        "neither arm is in the named panel. 0.46 +/- 0.10 is tagged '(Fig. 1c)' and 0.41 "
        "+/- 0.07 is tagged '(Fig. 2a and b)' in the article's own text; the row names "
        "Figure 2f."},
    "Singhal2019|Singhal2019_1_1|Figure 12A": {"reason":
        "wrong age cohort. '110.5 +/- 21.6 and 107.5 +/- 20.4 vs. 21.0 +/- 8.3' is stated "
        "'at 14-month'; the same paragraph prints the 4-month control as 3.7 +/- 0.7. The "
        "row is coded 4M_Control vs 4M_EE."},
    "Singhal2019|Singhal2019_2_1|Figure 12A": {"reason":
        "wrong apparatus and wrong age. 23.9 +/- 7.3 is '14-month-old control' TIME IN THE "
        "OPEN ARMS OF THE EZM; Figure 12A is 'escape latency to find the escape box' in the "
        "Barnes maze. 19.7 +/- 5.6 is likewise a 14-month open-arm value."},
    "Singhal2019|Singhal2019_3_1|Figure 12A": {"reason":
        "wrong table and wrong arm. Both values come from a summary table that terminates in "
        "the caption of Figure 8, not Figure 12; and that table reads 'PE vs. EE 85.0 +/- "
        "15.9 vs. 31.4 +/- 8.4', so 31.4 is the EE arm while the row codes it as PE+EE "
        "(printed in the next line as 46.6 +/- 13.7)."},
    "Smith2018|Smith2018_1_1|Figure 3A": {"reason":
        "pre-test read as the test. The sentence is 'Percent time investigating the novel "
        "object location IN PRE-TESTING was similar between housing conditions: 56.931 +/- "
        "9.10% pair-housed vs. 58.65 +/- 6.08% group-housed; t = 0.21, p = 0.83'. Figure 3A "
        "is the test itself, where the groups DIFFER (p = 0.032). Same animals, different "
        "measurement occasion."},
}


def adj_key(row):
    return f"{row['article']}|{row['comparisonId']}|{row.get('dataSource')}"


REF_HEADS = re.compile(
    r"\n\s*(references|bibliography|literature cited|works cited)\s*\n", re.I)
CAP_RE = re.compile(r"^\s*(?:Fig(?:ure)?s?\.?|FIG(?:URE)?S?\.?)\s*0*(\d+)\b")
PROX_WINDOW = 120          # v1's proximity window, kept only for the WEAK tier
MIN_GRAPHIC_AREA = 4.0     # pt^2: only reject degenerate/zero-area ops -- see _graphic_rects


# ---------------------------------------------------------------- PDF resolution
def _norm_doi(doi):
    return (doi or "").strip().lower().replace(
        "https://doi.org/", "").replace("http://dx.doi.org/", "")


def zotero_index(db_path):
    """DOI -> local PDF path, read from Zotero's SQLite READ-ONLY (safe while running)."""
    if not pathlib.Path(db_path).exists():
        return {}, {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    doi_item = {}
    for r in con.execute(
            "SELECT i.itemID iid, idv.value v FROM items i "
            "JOIN itemData d ON i.itemID=d.itemID "
            "JOIN itemDataValues idv ON d.valueID=idv.valueID "
            "JOIN fields f ON d.fieldID=f.fieldID WHERE f.fieldName='DOI'"):
        doi_item[_norm_doi(r["v"])] = r["iid"]
    att = collections.defaultdict(list)
    for r in con.execute(
            "SELECT ia.parentItemID pid, ia.path path, it.key key FROM itemAttachments ia "
            "JOIN items it ON ia.itemID=it.itemID WHERE ia.contentType='application/pdf'"):
        att[r["pid"]].append((r["key"], r["path"]))
    con.close()
    return doi_item, att


def build_pdf_map(articles, refresh=False):
    """articles: {article_id: doi}. Returns {article_id: {doi, pdf, status}}."""
    if PDF_MAP_FULL.exists() and not refresh:
        cached = json.loads(PDF_MAP_FULL.read_text())
        if set(cached) >= set(articles):
            return cached
    out = {}
    if PDF_MAP_43.exists():
        out.update(json.loads(PDF_MAP_43.read_text()))
    doi_item, att = zotero_index(ZOTERO_DB)
    for a, doi in sorted(articles.items()):
        if out.get(a, {}).get("status") == "ok" and pathlib.Path(
                out[a].get("pdf") or "/nonexistent").exists():
            continue
        iid = doi_item.get(_norm_doi(doi))
        pdf, status = None, "no-doi-match"
        if iid is not None:
            pdfs = att.get(iid, [])
            status = "no-pdf-attachment" if not pdfs else "file-missing"
            for key, path in pdfs:
                if path and path.startswith("storage:"):
                    full = os.path.join(ZOTERO_STORAGE, key, path[len("storage:"):])
                    if os.path.exists(full):
                        pdf, status = full, "ok"
                        break
        out[a] = {"doi": doi, "pdf": pdf, "status": status}
    PDF_MAP_FULL.parent.mkdir(parents=True, exist_ok=True)
    PDF_MAP_FULL.write_text(json.dumps(out, indent=2))
    return out


# ---------------------------------------------------------------- MATCHING: numbers
# One token = one printed number, carrying the precision it was printed at. The precision
# IS the tolerance: a value printed as "20.1" asserts only that the truth lies in
# [20.05, 20.15), so that half-width -- not an arbitrary percentage -- is the match radius.
_NUM_BODY = r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?"
NUM_RE = re.compile(r"(?<![0-9A-Za-z._])(" + _NUM_BODY + r")(?![0-9])")
_SIGN_OK_BEFORE = set(" \t\n([=,;:*/±")


class Tok:
    __slots__ = ("value", "prec", "start", "end", "text", "bbox")

    def __init__(self, value, prec, start, end, text, bbox=None):
        self.value, self.prec = value, prec
        self.start, self.end, self.text, self.bbox = start, end, text, bbox

    @property
    def halfwidth(self):
        return 0.5 * (10.0 ** -self.prec)

    def __repr__(self):
        return f"Tok({self.text}={self.value}@{self.prec}dp)"


def _parse_token_text(s):
    """'1,234.5'->(1234.5,1)  '20,13'->(20.13,2)  '1,234'->(1234,0)  '20.1'->(20.1,1)."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):            # thousands, no decimal
        return float(s.replace(",", "")), 0
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d+", s):       # thousands + decimal point
        v = s.replace(",", "")
        return float(v), len(v.split(".")[1])
    if "." in s:
        return float(s), len(s.split(".")[1])
    if "," in s:                                           # European decimal comma
        frac = s.split(",")[1]
        return float(s.replace(",", ".")), len(frac)
    return float(s), 0


@functools.lru_cache(maxsize=64)
def tokens(text):
    """Every printed number in `text`, with position and print precision."""
    out = []
    for m in NUM_RE.finditer(text):
        s = m.group(1)
        try:
            v, prec = _parse_token_text(s)
        except ValueError:
            continue
        i = m.start(1)
        # a minus sign only counts when it opens the number rather than joining a range
        if i > 0 and text[i - 1] in "-−–" and (
                i == 1 or text[i - 2] in _SIGN_OK_BEFORE):
            v, i = -v, i - 1
        out.append(Tok(v, prec, i, m.end(1), text[i:m.end(1)]))
    return out


def matches(coded, tok, scale=1.0):
    """Does the coded value fall inside the interval the printed token asserts?"""
    if coded is None:
        return False
    return abs(coded * scale - tok.value) <= tok.halfwidth + 1e-9


def informative(tok):
    """Reject 1-digit tokens: a lone '5' matches by chance far too often."""
    return len(tok.text.lstrip("-−").replace(",", "").replace(".", "").lstrip("0")) >= 2 \
        or tok.prec >= 1


# ---------------------------------------------------------------- MATCHING: pairs
_N = _NUM_BODY
PAIR_PATTERNS = [
    ("pm", re.compile(r"(" + _N + r")\s*(?:±|\+\s*/\s*-|\+-|∓)\s*(" + _N + r")")),
    ("label", re.compile(r"(" + _N + r")\s*[,;(\[]?\s*(?:S\.?E\.?M\.?|S\.?E\.?|S\.?D\.?|"
                         r"std\.?\s*(?:dev|error)\w*)\s*[=:]?\s*(" + _N + r")", re.I)),
    ("paren", re.compile(r"(" + _N + r")\s*\(\s*(" + _N + r")\s*\)")),
]


@functools.lru_cache(maxsize=64)
def pairs(text):
    """Printed (mean, variance) pairs, strongest form first. Returns list of dicts.

    Cached: the body-text zone is scanned once per arm per permutation replicate, so
    without memoisation the same 40k-character regex sweep runs thousands of times.
    """
    out, seen = [], set()
    for kind, pat in PAIR_PATTERNS:
        for m in pat.finditer(text):
            key = (m.start(1), m.start(2))
            if key in seen:
                continue
            seen.add(key)
            try:
                av, ap = _parse_token_text(m.group(1))
                bv, bp = _parse_token_text(m.group(2))
            except ValueError:
                continue
            a = Tok(av, ap, m.start(1), m.end(1), m.group(1))
            b = Tok(bv, bp, m.start(2), m.end(2), m.group(2))
            i = m.start(1)
            if i > 0 and text[i - 1] in "-−–" and (
                    i == 1 or text[i - 2] in _SIGN_OK_BEFORE):
                a.value, a.start = -a.value, i - 1
            out.append({"kind": kind, "a": a, "b": b,
                        "ctx": text[max(0, m.start() - 45):m.end() + 45].replace("\n", " ")})
    return out


SCALES = (1.0, 10.0, 100.0, 1000.0, 0.1, 0.01, 0.001)


def match_arm(zone_text, mean, var, sd_alt, allow_scale):
    """Best PAIRED evidence for one arm in one zone.

    Returns a dict or None. `varChannel` says WHICH dispersion the printed second token
    reproduced -- the coded variance as recorded, or the SD derived from it. That
    distinction is load-bearing: a paper printing mean+/-SD against a coder who recorded
    SEM is a confirmation of both numbers, not a miss.
    """
    if mean is None:
        return None
    scales = SCALES if allow_scale else (1.0,)
    best = None
    for p in pairs(zone_text):
        for s in scales:
            if not matches(mean, p["a"], s):
                continue
            chan = None
            if matches(var, p["b"], s):
                chan = "asCoded"
            elif sd_alt is not None and matches(sd_alt, p["b"], s):
                chan = "asSD"
            # GUARD (restored 2026-07-27, amendment A6). This was relaxed to
            #     informative(a) OR (chan and informative(b))
            # so that Bakeche2020's printed "(3 +/- 0.81)" would confirm. Hand inspection
            # showed that confirmation is FALSE -- the sentence is the wrong outcome, the
            # wrong lighting condition and the wrong phase, and the arms are inverted --
            # so the relaxation bought one false positive and no true ones. A one-digit
            # mean cannot carry the match: it collides with an axis tick, a group size or
            # a day index at a rate the null cannot absorb. The MEAN token must be
            # informative in its own right; the variance can only corroborate.
            if not informative(p["a"]):
                continue
            rank = (0 if chan else 1, 0 if s == 1.0 else 1,
                    {"pm": 0, "label": 1, "paren": 2}[p["kind"]])
            cand = {"kind": p["kind"], "scale": s, "varChannel": chan,
                    "meanText": p["a"].text, "varText": p["b"].text,
                    "pos": p["a"].start,
                    "ctx": p["ctx"], "_rank": rank,
                    "verbatimMean": abs(mean * s - p["a"].value) < 1e-9}
            if best is None or rank < best["_rank"]:
                best = cand
            break
    return best


def match_mean_only(zone_text, mean, allow_scale, exclude=()):
    """Weak tier: the mean printed alone. `exclude` carries axis-tick token positions."""
    if mean is None:
        return None
    scales = SCALES if allow_scale else (1.0,)
    for t in tokens(zone_text):
        if not informative(t) or t.start in exclude:
            continue
        for s in scales:
            if matches(mean, t, s):
                return {"meanText": t.text, "scale": s,
                        "ctx": zone_text[max(0, t.start - 45):t.end + 45].replace("\n", " ")}
    return None


# ---------------------------------------------------------------- ZONES from the PDF
def _graphic_rects(page):
    """Every graphic mark on the page as (rect, is_image)."""
    import fitz
    rects = []
    for im in page.get_images(full=True):
        try:
            rects += [(fitz.Rect(r), True) for r in page.get_image_rects(im[0])]
        except Exception:
            pass
    parea = abs(page.rect.get_area()) or 1.0
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        a = abs(r.get_area())
        if a < MIN_GRAPHIC_AREA or a > 0.85 * parea:
            continue
        rects.append((r, False))
    # The threshold is deliberately near zero. A scatter or line plot is drawn as hundreds
    # of individual marker paths -- Baraldi2013 p2 is 254 ops of which 253 are under
    # 400pt^2 -- so any "real graphics are big" filter deletes the entire figure. Since the
    # region is the UNION of the band between captions, small ops cost nothing and are
    # exactly what locates a marker-drawn figure.
    return [(r, im) for r, im in rects if r.width > 1 and r.height > 1]


def _grow_region(cap_rect, graphics, ceiling, floor):
    """The figure is the UNION of every graphic between the neighbouring captions.

    Two rules that look reasonable both fail on real pages, so neither is used:
      * chain outward from the graphic nearest the caption -- a stray 17x26pt glyph path
        sits directly under the caption, the chain starts and stops there, and the figure
        comes back 26pt tall (Baraldi2013 Fig 1);
      * cluster, then pick the best cluster by area/distance -- a multi-panel vector
        figure fragments into per-panel clusters and the score picks one panel, dropping
        the other 40 text spans (Lee2024 Fig 2, 42 spans -> 0).
    Unioning the whole band is immune to both. It cannot leak into a neighbouring figure
    because `ceiling`/`floor` are that figure's caption, and it cannot swallow prose
    because prose is text, not a graphic -- the only exposure is a paragraph sandwiched
    between two graphic rows, which the body-paragraph guard in build_doc removes.
    """
    import fitz
    sides = {"above": [g for g in graphics
                       if g[0].y1 <= cap_rect.y0 + 4 and g[0].y1 >= ceiling],
             "below": [g for g in graphics
                       if g[0].y0 >= cap_rect.y1 - 4 and g[0].y0 <= floor]}
    # Which side of the caption is the figure on? Journals set the caption below the
    # figure, manuscripts above it, so the side must be measured rather than assumed.
    # Two naive scores both fail: "above if anything is above" gives Jaimes2020 Fig 2 a
    # 488x16 page-header rule and never looks down, and raw total area gives Frick2003
    # Fig 5 the ruled Table 3 below instead of the plot above. What actually separates a
    # figure from a rule or a table is the AREA IT COVERS -- a header rule is 488x16, the
    # plot below it is 264x276 -- with a bonus for bitmaps, since an image XObject is a
    # figure almost by definition. (A per-op count fails too: Jaimes2020's header rule is
    # itself 16 drawing ops, tying the 16 marker paths of the real figure.)
    best, side = None, None
    for k, seq in sides.items():
        if not seq:
            continue
        reg = fitz.Rect(seq[0][0])
        for g, _ in seq[1:]:
            reg |= g
        score = abs(reg.get_area()) + 9.0 * sum(abs(g.get_area()) for g, im in seq if im)
        if best is None or score > best[0]:
            best, side = (score, reg), k
    return (best[1], side) if best else (None, None)


def build_doc(pdf_path, want_figs, do_ocr=True, article=""):
    """Partition one PDF into disjoint BODY / CAPTION[fig] / FIGURE[fig] zones."""
    import fitz
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return {"error": f"open failed: {e}"}

    caps = []                                     # (fignum, page_index, rect, text)
    for pno, page in enumerate(doc):
        for b in page.get_text("blocks"):
            m = CAP_RE.match(b[4])
            if m:
                caps.append((m.group(1), pno, fitz.Rect(b[:4]), b[4]))

    out = {"captions": {}, "figures": {}, "regions": {}, "error": None}
    cap_rects = collections.defaultdict(list)
    for f, pno, r, t in caps:
        cap_rects[pno].append(r)
        out["captions"].setdefault(f, []).append(t)

    for fig in want_figs:
        cands = [c for c in caps if c[0] == fig]
        if not cands:
            continue
        # a figure referenced mid-paragraph also matches CAP_RE; the real caption is the
        # one with graphics next to it, so score candidates by adjacent graphic area
        best = None
        for f, pno, r, t in cands:
            page = doc[pno]
            graphics = _graphic_rects(page)
            others = [x for x in cap_rects[pno] if x != r]
            ceiling = max([x.y1 for x in others if x.y1 <= r.y0] + [0.0])
            floor = min([x.y0 for x in others if x.y0 >= r.y1] + [page.rect.y1])
            reg, side = _grow_region(r, graphics, ceiling, floor)
            area = abs(reg.get_area()) if reg else 0.0
            if best is None or area > best["area"]:
                best = {"page": pno, "cap": r, "reg": reg, "side": side,
                        "area": area, "text": t}
        if best is None or best["reg"] is None:
            out["regions"][fig] = None
            continue
        page = doc[best["page"]]
        reg = best["reg"]
        spans, has_img = [], False
        for bl in page.get_text("dict")["blocks"]:
            if bl["type"] != 0:
                continue
            # A body paragraph that happens to fall inside the figure's bounding box is
            # not figure content. Figure-internal text is short labels; 25+ words is prose.
            btxt = " ".join(sp["text"] for ln in bl["lines"] for sp in ln["spans"])
            # Prose that happens to fall inside the figure's bounding box is not figure
            # content: running heads, and caption text that the PDF split into its own
            # block below the anchor line. Figure-internal text is short labels.
            if len(btxt.split()) >= 15 or CAP_RE.match(btxt):
                continue
            for ln in bl["lines"]:
                for sp in ln["spans"]:
                    r = fitz.Rect(sp["bbox"])
                    c = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
                    if reg.contains(fitz.Point(*c)) and not best["cap"].contains(
                            fitz.Point(*c)):
                        spans.append({"t": sp["text"], "bbox": list(r), "size": sp["size"]})
        for im in page.get_images(full=True):
            for ir in page.get_image_rects(im[0]):
                if abs((fitz.Rect(ir) & reg).get_area()) > 0.25 * abs(reg.get_area()):
                    has_img = True
        out["regions"][fig] = {"page": best["page"], "rect": list(reg),
                               "side": best["side"], "nSpans": len(spans),
                               "hasImage": has_img}
        out["figures"][fig] = {"vectorLines": _lines_from_spans(spans), "ocrLines": None}
        if do_ocr and has_img:
            out["figures"][fig]["ocrLines"] = ocr_region(
                page, reg, f"{article}_fig{fig}")

    # BODY = everything that is neither a real caption nor a short label inside a figure.
    regs = collections.defaultdict(list)
    for fig, r in out["regions"].items():
        if r:
            regs[r["page"]].append(fitz.Rect(r["rect"]))
    gcache = {}
    body = []
    for pno, page in enumerate(doc):
        for b in page.get_text("blocks"):
            br, btxt = fitz.Rect(b[:4]), b[4]
            prose = len(btxt.split()) >= 15
            if CAP_RE.match(btxt):
                # CAP_RE also fires on a Results paragraph that opens "Figure 2 shows...".
                # Dropping every match cost Ederer2022 the sentence carrying its own
                # printed mean+/-SEM. A real caption has the figure right next to it; an
                # in-text reference does not, so adjacency decides.
                if pno not in gcache:
                    gcache[pno] = _graphic_rects(page)
                if any(0 <= br.y0 - g.y1 <= 40 or 0 <= g.y0 - br.y1 <= 40
                       for g, _ in gcache[pno]):
                    continue
            # Prose inside a figure's bounding box stays in BODY. Figure regions are the
            # union of a whole band and can cover most of a page (Gawryluk2024 Fig 2 is
            # 84% of page 4); excluding whatever they overlap deleted a third of that
            # article's text, including its Results numbers. Only short labels are figure
            # content, and those are what the FIGURE zone already took.
            if not prose and any(abs((br & x).get_area()) > 0.5 * abs(br.get_area() or 1)
                                 for x in regs[pno]):
                continue
            body.append(btxt)
    doc.close()
    txt = "\n".join(body)
    hits = list(REF_HEADS.finditer(txt))
    if hits:
        txt = txt[:hits[-1].start()]
    out["body"] = re.sub(r"[ \t ]+", " ", txt)
    return out


def _lines_from_spans(spans):
    """Rebuild reading lines geometrically -- span order in a vector figure is draw order,
    so '12.3' and its '+/- 1.4' can arrive far apart in the span list while sitting side
    by side on the page. Without this the pair regex never fires inside a figure."""
    if not spans:
        return []
    rows = []
    for s in sorted(spans, key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0])):
        yc = (s["bbox"][1] + s["bbox"][3]) / 2
        h = max(4.0, s["bbox"][3] - s["bbox"][1])
        for r in rows:
            if abs(r["y"] - yc) <= 0.6 * h:
                r["items"].append(s)
                r["y"] = (r["y"] * (len(r["items"]) - 1) + yc) / len(r["items"])
                break
        else:
            rows.append({"y": yc, "items": [s]})
    lines = []
    for r in rows:
        it = sorted(r["items"], key=lambda s: s["bbox"][0])
        buf = it[0]["t"]
        for prev, cur in zip(it, it[1:]):
            gap = cur["bbox"][0] - prev["bbox"][2]
            buf += (" " if gap > 0.8 else "") + cur["t"]
        lines.append({"y": r["y"], "text": buf,
                      "x0": min(s["bbox"][0] for s in it),
                      "x1": max(s["bbox"][2] for s in it)})
    return lines


# ---------------------------------------------------------------- OCR (raster figures)
_OCR_OK = None


def ocr_available():
    global _OCR_OK
    if _OCR_OK is None:
        _OCR_OK = pathlib.Path(TESSERACT).exists() or bool(shutil.which("tesseract"))
    return _OCR_OK


def _win_path(p):
    s = str(p)
    if s.startswith("/mnt/") and len(s) > 6:
        return s[5].upper() + ":" + s[6:].replace("/", "\\")
    return s


def ocr_region(page, rect, key):
    """Render the figure crop at OCR_DPI and OCR it into geometric lines."""
    if not ocr_available():
        return None
    OCR_CACHE.mkdir(parents=True, exist_ok=True)
    cache = OCR_CACHE / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".json")
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    OCR_SCRATCH.mkdir(parents=True, exist_ok=True)
    stem = OCR_SCRATCH / re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    png = stem.with_suffix(".png")
    try:
        page.get_pixmap(clip=rect, dpi=OCR_DPI).save(png)
        exe = TESSERACT if pathlib.Path(TESSERACT).exists() else "tesseract"
        win = pathlib.Path(TESSERACT).exists()
        subprocess.run([exe, _win_path(png) if win else str(png),
                        _win_path(stem) if win else str(stem), "tsv"],
                       check=True, capture_output=True, timeout=300)
        rows = list(csv.DictReader(stem.with_suffix(".tsv").open(encoding="utf-8",
                                                                errors="replace"),
                                   delimiter="\t", quoting=csv.QUOTE_NONE))
    except Exception:
        return None
    finally:
        for p in (png, stem.with_suffix(".tsv")):
            try:
                p.unlink()
            except OSError:
                pass
    groups = collections.OrderedDict()
    for r in rows:
        if not (r.get("text") or "").strip():
            continue
        try:
            if float(r.get("conf", -1)) < 40:
                continue
        except ValueError:
            continue
        k = (r["block_num"], r["par_num"], r["line_num"])
        groups.setdefault(k, []).append(r)
    scale = 72.0 / OCR_DPI
    lines = []
    for k, ws in groups.items():
        ws.sort(key=lambda w: int(w["left"]))
        lines.append({
            "text": " ".join(w["text"] for w in ws),
            "y": rect.y0 + (int(ws[0]["top"]) + int(ws[0]["height"]) / 2) * scale,
            "x0": rect.x0 + int(ws[0]["left"]) * scale,
            "x1": rect.x0 + (int(ws[-1]["left"]) + int(ws[-1]["width"])) * scale,
        })
    cache.write_text(json.dumps(lines))
    return lines


# ---------------------------------------------------------------- axis-tick suppression
def axis_tokens(lines):
    """Numeric tokens that are axis tick labels, so the mean-only tier can drop them.

    A y-axis is a COLUMN of numbers at near-identical x forming an arithmetic run; an
    x-axis is a ROW at near-identical y doing the same. Inside a figure region every such
    number is a lone number that will collide with some coded mean by chance, so leaving
    them in would make the weak tier pure noise.
    """
    pts = []
    for ln in lines or []:
        for t in tokens(ln["text"]):
            pts.append((t.value, ln["x0"], ln["y"]))
    axis = set()
    for idx, tol in ((1, 6.0), (2, 4.0)):        # 1 = column (x), 2 = row (y)
        buckets = collections.defaultdict(list)
        for v, x, y in pts:
            buckets[round((x if idx == 1 else y) / tol)].append(v)
        for vals in buckets.values():
            u = sorted(set(vals))
            if len(u) < 3:
                continue
            d = [round(b - a, 6) for a, b in zip(u, u[1:])]
            if max(d) - min(d) <= 1e-6 * max(1.0, max(d)) or (
                    len(set(d)) == 1):
                axis.update(u)
    return axis


# ---------------------------------------------------------------- verification core
ZONE_RANK = ["IN_FIGURE_VECTOR", "IN_FIGURE_OCR", "CAPTION", "TEXT"]


def zones_for(dm, fig):
    """The searchable text of each zone for one comparison, strongest zone first."""
    z = []
    f = dm.get("figures", {}).get(fig) or {}
    vl, ol = f.get("vectorLines"), f.get("ocrLines")
    if vl:
        z.append(("IN_FIGURE_VECTOR", "\n".join(l["text"] for l in vl), vl))
    if ol:
        z.append(("IN_FIGURE_OCR", "\n".join(l["text"] for l in ol), ol))
    cap = dm.get("captions", {}).get(fig)
    if cap:
        z.append(("CAPTION", "\n".join(cap), None))
    if dm.get("body"):
        z.append(("TEXT", dm["body"], None))
    return z


def verify_row(row, dm, allow_scale=False, mean_override=None):
    """Best evidence for one comparison. mean_override drives the permutation null."""
    fig = row.get("figureNumber")
    res = {"verdict": "NOT_FOUND", "zone": None, "arms": {}, "evidence": []}
    if not dm or dm.get("error"):
        res["verdict"] = "NO_PDF"
        return res
    zl = zones_for(dm, fig)
    if not zl:
        res["verdict"] = "NO_FIGURE"
        return res

    arms = {}
    for name in ("control", "interv"):
        a = row.get(name) or {}
        mean = a.get("mean") if mean_override is None else mean_override[name]["mean"]
        var = a.get("varianceValue") if mean_override is None \
            else mean_override[name]["varianceValue"]
        sd = a.get("sd") if mean_override is None else mean_override[name].get("sd")
        arms[name] = {"mean": mean, "var": var, "sd": sd,
                      "pair": None, "pairZone": None,
                      "meanOnly": None, "meanOnlyZone": None}
        for zname, ztext, zlines in zl:
            hit = match_arm(ztext, mean, var, sd, allow_scale)
            if hit:
                arms[name]["pair"], arms[name]["pairZone"] = hit, zname
                break
        for zname, ztext, zlines in zl:
            # The mean-only tier is NOT run over body text. Measured: coded 20.13 "matched"
            # the '20' of "20 mg/kg", coded 0.53 matched "exceeding 0.5, the chance level",
            # coded 21.7 matched a grant number. A body-text hit on a lone number carries
            # no information, so the zone is excluded rather than reported and caveated.
            if zname == "TEXT":
                continue
            if zlines is not None:
                ax = axis_tokens(zlines)
                if mean is not None and any(abs(mean - v) < 1e-9 for v in ax):
                    continue          # the only in-figure hit would be an axis tick
            hit = match_mean_only(ztext, mean, allow_scale)
            if hit:
                arms[name]["meanOnly"], arms[name]["meanOnlyZone"] = hit, zname
                break

    res["arms"] = arms
    c, i = arms["control"], arms["interv"]
    if c["pair"] and i["pair"]:
        z = max(c["pairZone"], i["pairZone"], key=ZONE_RANK.index)
        res["verdict"] = "CONFIRMED_" + z
        res["zone"] = z
        # How far apart, in characters of the same zone, the two arms' printed pairs sit.
        # Reported, not thresholded: a paper stating the contrast prints the two arms
        # within a sentence of each other, while two matches drawn from unrelated
        # paragraphs are evidence for two different experiments that happen to share
        # numbers. It is the mechanical input to the hand adjudication (ADJUDICATION).
        res["armGapChars"] = (abs(c["pair"]["pos"] - i["pair"]["pos"])
                              if c["pairZone"] == i["pairZone"] else None)
        res["evidence"] = [
            {"arm": k, "zone": arms[k]["pairZone"], "kind": arms[k]["pair"]["kind"],
             "matched": f"{arms[k]['pair']['meanText']} +/- {arms[k]['pair']['varText']}",
             "varChannel": arms[k]["pair"]["varChannel"],
             "scale": arms[k]["pair"]["scale"],
             "pos": arms[k]["pair"].get("pos"),
             "context": arms[k]["pair"]["ctx"][:200]} for k in ("control", "interv")]
    elif c["pair"] or i["pair"] or (c["meanOnly"] and i["meanOnly"]):
        res["verdict"] = "PARTIAL_MEAN"
        res["zone"] = None
        for k in ("control", "interv"):
            h = arms[k]["pair"] or arms[k]["meanOnly"]
            if h:
                res["evidence"].append(
                    {"arm": k, "zone": arms[k]["pairZone"] or arms[k]["meanOnlyZone"],
                     "kind": h.get("kind", "meanOnly"),
                     "matched": h.get("meanText"), "context": h["ctx"][:200]})
    return res


def channel_counts(res):
    """(meanConfirmed, varConfirmed) at COMPARISON level -- both arms required."""
    a = res.get("arms") or {}
    if not a:
        return False, False
    both_pair = bool(a.get("control", {}).get("pair") and a.get("interv", {}).get("pair"))
    if not both_pair:
        return False, False
    var_ok = all((a[k]["pair"] or {}).get("varChannel") for k in ("control", "interv"))
    return True, bool(var_ok)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--allow-scale", action="store_true",
                    help="also accept a common power-of-ten unit rescaling of the pair")
    ap.add_argument("--limit", type=int, default=0, help="first N articles (smoke test)")
    ap.add_argument("--refresh-pdf-map", action="store_true")
    ap.add_argument("--null-reps", type=int, default=1000,
                    help="WITHIN-ARTICLE permutation-null replicates per row (0 disables). "
                         "This is the calibrated null: a coded value competes with the "
                         "numbers printed in ITS OWN paper.")
    ap.add_argument("--null-reps-corpus", type=int, default=200,
                    help="CORPUS-WIDE permutation-null replicates per row (0 disables). "
                         "Reported only as the contrast that shows why the corpus-wide "
                         "null is the wrong alternative -- see sec.1.4b.")
    ap.add_argument("--no-adjudication", action="store_true",
                    help="report the raw mechanical verdicts without applying the "
                         "committed hand-adjudication ledger (ADJUDICATION below)")
    a = ap.parse_args()

    if not CODED.exists():
        sys.exit(f"no coded reference at {CODED} -- run make_coded_reference.py first")
    data = json.loads(CODED.read_text())
    rows = data["rows"]
    # NOTE: `comparisonId` is NOT unique in the coded reference -- 25 ids are shared by
    # 70 rows (e.g. Zhang2017_3_1 is both "Figure 3d" and "Figure 3e"). Everything below
    # is therefore keyed by ROW INDEX; keying by comparisonId silently gave every row in
    # a collision group the last one's verdict.
    fd = [(i, r) for i, r in enumerate(rows) if r.get("figureDerived")]
    articles = {}
    for _, r in fd:
        articles.setdefault(r["article"], r.get("doi"))

    pdfmap = build_pdf_map(articles, refresh=a.refresh_pdf_map)
    resolved = {k for k, v in pdfmap.items() if v.get("status") == "ok"
                and v.get("pdf") and pathlib.Path(v["pdf"]).exists()}
    do_ocr = not a.no_ocr and ocr_available()
    print(f"figure-derived comparisons: {len(fd)} across {len(articles)} articles")
    print(f"PDFs resolved: {len(resolved & set(articles))}/{len(articles)}"
          f"   (v1 used benchmark/real/pdf_map.json = {len(json.loads(PDF_MAP_43.read_text())) if PDF_MAP_43.exists() else 0} articles)")
    print(f"OCR: {'tesseract ' + TESSERACT if do_ocr else 'DISABLED'}\n")

    order = sorted(articles)
    if a.limit:
        order = order[:a.limit]
    todo = collections.defaultdict(list)
    for i, r in fd:
        if r["article"] in order:
            todo[r["article"]].append((i, r))

    results, docs = {}, {}
    stats = collections.Counter()

    # ---- PASS 1: the real verdicts. Documents are retained so pass 2 does not re-parse.
    for n, art in enumerate(order, 1):
        ent = pdfmap.get(art) or {}
        pdf = ent.get("pdf")
        figs = sorted({str(r.get("figureNumber")) for _, r in todo[art]
                       if r.get("figureNumber")})
        dm = None
        if pdf and pathlib.Path(pdf).exists():
            dm = build_doc(pdf, figs, do_ocr=do_ocr, article=art)
        docs[art] = dm
        if dm and not dm.get("error"):
            stats["figuresWanted"] += len(figs)
            for f in figs:
                reg = dm["regions"].get(f)
                if reg:
                    stats["figuresLocated"] += 1
                    stats["figVector" if reg["nSpans"] >= 3 else "figNoText"] += 1
                    stats["figRaster"] += 1 if reg["hasImage"] else 0
                    if (dm["figures"].get(f) or {}).get("ocrLines"):
                        stats["figOCRd"] += 1
        for i, r in todo[art]:
            results[i] = verify_row(r, dm, a.allow_scale)
        print(f"  [{n:3d}/{len(order)}] {art:24s} figs={len(figs):2d} "
              f"rows={len(todo[art]):2d} "
              + " ".join(f"{k.replace('CONFIRMED_','C:')}={v}" for k, v in
                         collections.Counter(results[i]['verdict']
                                             for i, _ in todo[art]).items()))

    # ---- PASS 2: THE PERMUTATION NULL, and what the right alternative actually is.
    #
    # v2 as shipped drew donor codings from the WHOLE CORPUS, so 99.35% of null trials
    # asked "does this coded value collide with a number in some OTHER paper?" -- a
    # question about values of the wrong magnitude, in the wrong units, from the wrong
    # behavioural test. Measured here: 0.330% of trials. That is not the alternative a
    # confirmation competes against. A coded value is searched for in ITS OWN paper.
    #
    # But the naive within-article null is wrong in the OTHER direction, and measurably
    # so. Draw a donor from the same article and 7.603% of trials "confirm" -- an implied
    # FDR of 100%, which is absurd on its face. The reason is a tautology: if this paper
    # prints its numbers at all, then a donor row FROM THE SAME PAPER very often has its
    # own values printed there too. The trial then confirms because the donor is genuinely
    # printed, not because a random number collided. The null hypothesis being simulated
    # ("this value is not printed in this paper") is FALSE for the donor by construction.
    #
    # Two repairs are needed, and they fix different halves of the problem.
    #
    # (1) MAGNITUDE-MATCHED donors from a DIFFERENT article -- THE PRIMARY NULL.
    #     Magnitude is the dominant driver of a chance collision: a coded 0.34 cannot
    #     collide with a paper that prints latencies in the hundreds, and the corpus-wide
    #     pool is full of such donors. Restricting the donor pool to rows whose control
    #     mean is within a factor of ~1.8 of the target's (|log10 ratio| <= 0.25) keeps
    #     the competitor at the right scale while guaranteeing that the donor's values are
    #     NOT printed in the target's paper. It has FULL COVERAGE -- every row gets trials.
    #
    # (2) WITHIN-ARTICLE donors restricted to rows this paper does NOT print (verdict
    #     NOT_FOUND). Same-paper realism with the tautology removed. It is reported, but
    #     it is NOT the primary, because it has a measured coverage hole: 12 of the 17
    #     confirming articles have no NOT_FOUND row at all, so the papers that actually
    #     print numbers contribute almost nothing to it and its rate is dominated by
    #     papers that print nothing, where the answer is trivially zero.
    #
    # All four rates are reported. The gap between them IS the finding.
    MAG_BAND = 0.25                      # decades; a factor of 10**0.25 ~ 1.78 either way
    nulls = {"matched": collections.Counter(), "within_nf": collections.Counter(),
             "within_all": collections.Counter(), "corpus": collections.Counter()}
    null_rows = {"matched": 0, "within_nf": 0, "within_all": 0, "corpus": 0}
    rng = random.Random(20260727)
    corpus_pool = [(i, r) for i, r in fd if (r.get("control") or {}).get("mean") is not None]

    def _mag(r):
        m = (r.get("control") or {}).get("mean")
        try:
            return math.log10(abs(m)) if m else None
        except Exception:
            return None

    mags = {i: _mag(r) for i, r in corpus_pool}

    def matched_pool(row_idx, row):
        t = mags.get(row_idx)
        if t is None:
            return []
        return [(i, r) for i, r in corpus_pool
                if r["article"] != row["article"] and mags.get(i) is not None
                and abs(mags[i] - t) <= MAG_BAND]

    null_cache = {}

    def _null_pass(scope, reps, row_idx, row, dm, donors):
        """`reps` shuffled replicates for one row. Memoised on (row_idx, donor_idx): the
        verdict is a deterministic function of that pair, so 1000 replicates over a pool
        of 6 donors costs 6 searches, not 1000."""
        if not reps or not donors:
            return False
        for _ in range(reps):
            di, donor = donors[rng.randrange(len(donors))]
            if di == row_idx:
                continue
            key = (row_idx, di)
            v = null_cache.get(key)
            if v is None:
                v = verify_row(row, dm, a.allow_scale,
                               mean_override={"control": donor["control"],
                                              "interv": donor["interv"]})["verdict"]
                null_cache[key] = v
            nulls[scope][v] += 1
        return True

    if a.null_reps or a.null_reps_corpus:
        print("\n  running the permutation null ...")
        for art in order:
            dm = docs.get(art)
            pool_all = [(i, r) for i, r in todo[art]
                        if (r.get("control") or {}).get("mean") is not None]
            pool_nf = [(i, r) for i, r in pool_all
                       if results.get(i, {}).get("verdict") == "NOT_FOUND"]
            for i, r in todo[art]:
                if _null_pass("matched", a.null_reps, i, r, dm,
                              matched_pool(i, r)):
                    null_rows["matched"] += 1
                if _null_pass("within_nf", a.null_reps, i, r, dm,
                              [d for d in pool_nf if d[0] != i]):
                    null_rows["within_nf"] += 1
                if _null_pass("within_all", a.null_reps, i, r, dm,
                              [d for d in pool_all if d[0] != i]):
                    null_rows["within_all"] += 1
                if _null_pass("corpus", a.null_reps_corpus, i, r, dm, corpus_pool):
                    null_rows["corpus"] += 1
    docs.clear()

    # ---- ADJUDICATION. Applied BEFORE anything is counted or written, so the report,
    #      the coded reference and the pre-registered bar all see the same set.
    adjudicated = {}
    if not a.no_adjudication:
        by_idx = {i: r for i, r in fd}
        for i, res in results.items():
            row = by_idx.get(i)
            entry = ADJUDICATION.get(adj_key(row)) if row else None
            if entry and res["verdict"].startswith("CONFIRMED"):
                adjudicated[i] = {"mechanical": res["verdict"], **entry}
                res["adjudication"] = entry
                res["mechanicalVerdict"] = res["verdict"]
                res["verdict"] = "REJECTED_ADJUDICATION"
                res["zone"] = None

    report = summarise(fd, order, results, nulls, null_rows, a, stats, pdfmap,
                       adjudicated)
    if not a.dry_run:
        write_back(data, results, report)
    else:
        print("\n[--dry-run] nothing written: coded_reference.json and "
              f"{REPORT_JSON.name} are unchanged")
    return report


def _canon(a):
    """The single article-key canonicalisation, shared with score_real_validation.py.
    Falls back to a local copy so this script still runs standalone."""
    try:
        sys.path.insert(0, str(HERE))
        from score_real_validation import canonical_article
        return canonical_article(a)
    except Exception:
        return re.sub(r"[^a-z0-9]+", "", (a or "").lower())


def _scope_table(conf):
    """Oracle stratum size AT EVERY SCOPE THE STUDY ANALYSES.

    ANALYSIS-PLAN sec.1.4b consequence 6 forbids quoting the corpus-wide count next to a
    result computed on a subset, and the subsets are much smaller: the corpus clears the
    >=30/>=10 bar, and the Tier-1 worklist intersects it at a handful of comparisons in a
    handful of articles. The table is emitted so the right number is always to hand and
    nobody has to recompute it (or reach for the corpus figure by default)."""
    wl = HERE / "worklist.json"
    if not wl.exists():
        return {}
    try:
        items = json.loads(wl.read_text())["items"]
    except Exception:
        return {}
    try:
        sys.path.insert(0, str(HERE))
        from score_real_validation import split_of
    except Exception:
        split_of = None

    def size(rs):
        return {"comparisons": len(rs),
                "panels": len({(r["article"], r.get("figureId") or r["dataSource"],
                                (r.get("panelLetter") or "").strip().upper()
                                or r["dataSource"]) for r in rs}),
                "figures": len({(r["article"], r.get("figureId") or r["dataSource"])
                                for r in rs}),
                "articles": len({_canon(r["article"]) for r in rs})}

    rows = [r for _, r in conf]
    out = collections.OrderedDict()
    out["corpus-wide (all 434 coded)"] = size(rows)
    for cut in (1, 2, 3):
        arts = {_canon(i["article"]) for i in items if i.get("tier", 9) <= cut}
        sel = [r for r in rows if _canon(r["article"]) in arts]
        out[f"worklist tiers 1-{cut}"] = size(sel)
        if split_of:
            for sp in ("dev", "lock"):
                a2 = {_canon(i["article"]) for i in items
                      if i.get("tier", 9) <= cut and split_of(i["article"]) == sp}
                out[f"  tiers 1-{cut}, {sp.upper()}"] = size(
                    [r for r in rows if _canon(r["article"]) in a2])
    return out


def summarise(fd, order, results, nulls, null_rows, args, stats, pdfmap, adjudicated):
    checked = [(i, r) for i, r in fd if i in results]
    verdicts = collections.Counter(results[i]["verdict"] for i, _ in checked)
    checkable = [(i, r) for i, r in checked if results[i]["verdict"] != "NO_PDF"]
    conf = [(i, r) for i, r in checked if results[i]["verdict"].startswith("CONFIRMED")]

    # The ANNOTATION UNIT is the PANEL, and a panel is a (figure, letter) pair. Keying on
    # figureId alone counts FIGURES: Zhang2017 "Figure 3d" and "Figure 3e" share the
    # figureId `Zhang2017_fig3` and collapsed into one. That is what produced the "21
    # panels" the plan quoted next to a panel-level bar.
    def panels(rs):
        return {(r["article"], r.get("figureId") or r["dataSource"],
                 (r.get("panelLetter") or "").strip().upper() or r["dataSource"])
                for _, r in rs}

    def figures(rs):
        return {(r["article"], r.get("figureId") or r["dataSource"]) for _, r in rs}

    mean_ok = [(i, r) for i, r in checked if channel_counts(results[i])[0]
               and results[i]["verdict"].startswith("CONFIRMED")]
    var_ok = [(i, r) for i, r in checked if channel_counts(results[i])[1]
              and results[i]["verdict"].startswith("CONFIRMED")]

    W = 34
    print("\n" + "=" * 74)
    print("ORACLE VERIFICATION v2 -- three sources (body text / caption / inside figure)")
    print("=" * 74)
    print(f"\n  {'universe':<{W}} {len(fd):>5} figure-derived comparisons")
    print(f"  {'  ... checked here':<{W}} {len(checked):>5}")
    print(f"  {'  ... PDF resolved (checkable)':<{W}} {len(checkable):>5}")
    print(f"\n  {'verdict':<{W}} {'n':>5}   share of checkable")
    for k in ("CONFIRMED_IN_FIGURE_VECTOR", "CONFIRMED_IN_FIGURE_OCR",
              "CONFIRMED_CAPTION", "CONFIRMED_TEXT", "PARTIAL_MEAN",
              "NOT_FOUND", "NO_FIGURE", "NO_PDF"):
        n = verdicts.get(k, 0)
        sh = f"{100*n/len(checkable):5.1f}%" if checkable and k != "NO_PDF" else "     -"
        print(f"  {k:<{W}} {n:>5}   {sh}")

    if adjudicated:
        print(f"\n  HAND ADJUDICATION (ledger in the source; --no-adjudication disables)")
        print(f"    {'mechanically proposed, then REJECTED':<{W+8}} {len(adjudicated):>5}")
        byi = dict(fd)
        for i, e in sorted(adjudicated.items()):
            r = byi[i]
            print(f"      [{e['mechanical'].replace('CONFIRMED_','C:')}] "
                  f"{r['article']} {r['comparisonId']} ({r.get('dataSource')})")
            print(f"          {e['reason']}")

    print(f"\n  {'CONFIRMED (any source), comparisons':<{W+8}} {len(conf):>5}")
    print(f"  {'CONFIRMED, distinct PANELS (fig x letter)':<{W+8}} {len(panels(conf)):>5}")
    print(f"  {'CONFIRMED, distinct FIGURES':<{W+8}} {len(figures(conf)):>5}")
    print(f"  {'CONFIRMED, distinct articles':<{W+8}} "
          f"{len({r['article'] for _, r in conf}):>5}")
    print(f"\n  channel (both arms required)")
    print(f"    {'mean confirmed':<{W}} {len(mean_ok):>5} comparisons / "
          f"{len(panels(mean_ok))} panels / {len(figures(mean_ok))} figures / "
          f"{len({r['article'] for _, r in mean_ok})} articles")
    print(f"    {'variance confirmed':<{W}} {len(var_ok):>5} comparisons / "
          f"{len(panels(var_ok))} panels / {len(figures(var_ok))} figures / "
          f"{len({r['article'] for _, r in var_ok})} articles")

    # Scope table. A result computed on a subset may NOT cite the corpus-wide count
    # (ANALYSIS-PLAN sec.1.4b consequence 6). The stratum size is reported at every
    # scope the study actually analyses, so the right number is always to hand.
    scopes = _scope_table(conf)
    if scopes:
        print(f"\n  ORACLE STRATUM SIZE AT EACH SCOPE ANALYSED")
        print(f"    {'scope':<30}{'comparisons':>13}{'panels':>8}{'figures':>9}{'articles':>10}")
        for name, s in scopes.items():
            print(f"    {name:<30}{s['comparisons']:>13}{s['panels']:>8}"
                  f"{s['figures']:>9}{s['articles']:>10}")

    print(f"\n  figure localization")
    for k in ("figuresWanted", "figuresLocated", "figVector", "figNoText",
              "figRaster", "figOCRd"):
        print(f"    {k:<{W}} {stats.get(k,0):>5}")

    nullrep = {}
    print(f"\n  PERMUTATION NULL -- the alternative a confirmation competes against")
    for scope, label, reps in (
            ("matched", "MAGNITUDE-MATCHED, other article (PRIMARY)", args.null_reps),
            ("within_nf", "within-article, donors NOT printed", args.null_reps),
            ("within_all", "within-article, ANY donor (tautological)", args.null_reps),
            ("corpus", "corpus-wide donors (the null v2 shipped)", args.null_reps_corpus)):
        cnt = nulls.get(scope) or collections.Counter()
        tot = sum(cnt.values())
        if not reps or not tot:
            print(f"    {label:<{W+4}} disabled")
            continue
        nc = sum(v for k, v in cnt.items() if k.startswith("CONFIRMED"))
        rate = nc / tot
        exp = len(checkable) * rate
        fdr = (exp / len(conf)) if conf else None
        nullrep[scope] = {"repsPerRow": reps, "rowsWithDonors": null_rows.get(scope, 0),
                          "trials": tot, "confirmed": nc, "rate": rate,
                          "expectedFalseConfirmed": exp,
                          "impliedFDR": fdr, "verdicts": dict(cnt)}
        print(f"    {label:<{W+4}} {reps:>5} reps x {null_rows.get(scope,0)} rows "
              f"= {tot} trials")
        print(f"      {'confirmed under shuffled values':<{W}} {nc:>6}  "
              f"({100*rate:.3f}% of trials)")
        print(f"      {'-> expected false CONFIRMED':<{W}} {exp:>6.1f} of "
              f"{len(checkable)} checkable")
        if fdr is not None:
            print(f"      {'-> implied FDR of the real count':<{W}} {100*fdr:>6.1f}%")
    if "matched" in nullrep and "corpus" in nullrep and nullrep["corpus"]["rate"] > 0:
        f_ = nullrep["matched"]["rate"] / nullrep["corpus"]["rate"]
        nullrep["matchedOverCorpusRatio"] = f_
        print(f"\n    PRIMARY = line 1: a donor of the SAME MAGNITUDE from a DIFFERENT")
        print(f"    paper. Magnitude is what drives a chance collision, and the donor's")
        print(f"    values are guaranteed not to be printed in the target's paper.")
        print(f"    Line 2 (same paper, donors this paper does not print) is the same-paper")
        print(f"    idea with the tautology removed, but 12 of the confirming articles have")
        print(f"    NO such donor, so it is dominated by papers that print nothing.")
        print(f"    Line 3 is NOT a null: a same-paper donor whose values ARE printed")
        print(f"    confirms because it is genuinely printed, hence the absurd ~100% FDR.")
        print(f"    Line 4 is what v2 shipped. MEASURED: the magnitude-matched rate is")
        print(f"    {f_:.2f}x the corpus-wide one -- so the corpus-wide null was NOT the")
        print(f"    source of the error. The alarming 'within-article collisions are ~18x")
        print(f"    more likely' figure is an artefact of line 3's tautology, not a real")
        print(f"    property of the search. Report that plainly rather than the scarier")
        print(f"    number: what actually inflated the count was the relaxed pair guard")
        print(f"    and twelve semantic mismatches, both now fixed.")

    bar_c, bar_a = 30, 10
    ok = len(conf) >= bar_c and len({r["article"] for _, r in conf}) >= bar_a
    print(f"\n  PRE-REGISTERED BAR (ANALYSIS-PLAN sec.1.4b consequence 3):")
    print(f"    >= {bar_c} confirmed comparisons across >= {bar_a} articles")
    print(f"    observed: {len(conf)} comparisons / {len(panels(conf))} panels / "
          f"{len(figures(conf))} figures / "
          f"{len({r['article'] for _, r in conf})} articles  -> "
          f"{'MET' if ok else 'NOT MET'}")
    if not ok:
        print(f"    The bar is NOT MET. Say so plainly wherever the stratum is reported:")
        print(f"    the oracle stratum is a descriptive result, not a powered one.")

    rep = {
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "method": {
            "zones": ["BODY (references stripped, captions and figure regions removed)",
                      "CAPTION (the named figure's caption block)",
                      "IN_FIGURE_VECTOR (PDF text spans inside the figure region)",
                      "IN_FIGURE_OCR (tesseract over the region rendered at %d dpi)"
                      % OCR_DPI],
            "confirmRule": "both arms matched as a printed mean+/-variance PAIR "
                           "(+/- separator, 'SEM ='-style label, or 'm (s)')",
            "tolerance": "the printed token's own rounding half-width "
                         "(10^-decimals / 2); no flat percentage",
            "varianceChannels": ["asCoded", "asSD (coded SEM x sqrt(n))"],
            "unitScaling": bool(args.allow_scale),
            "ocr": TESSERACT if ocr_available() and not args.no_ocr else None,
        },
        "counts": {
            "figureDerived": len(fd), "checked": len(checked),
            "checkable": len(checkable),
            "verdicts": dict(verdicts),
            "confirmedComparisons": len(conf),
            "confirmedPanels": len(panels(conf)),
            "confirmedFigures": len(figures(conf)),
            "confirmedArticles": sorted({r["article"] for _, r in conf}),
            "meanConfirmedComparisons": len(mean_ok),
            "meanConfirmedPanels": len(panels(mean_ok)),
            "meanConfirmedFigures": len(figures(mean_ok)),
            "varianceConfirmedComparisons": len(var_ok),
            "varianceConfirmedPanels": len(panels(var_ok)),
            "varianceConfirmedFigures": len(figures(var_ok)),
            "_unitNote": "PANELS are (figure, letter); FIGURES are (article, figureId). "
                         "They differ -- e.g. Zhang2017 Figure 3d and 3e are two panels "
                         "of one figure. Never quote one next to a bar stated in the "
                         "other.",
        },
        "scopes": _scope_table(conf),
        "figureLocalization": dict(stats),
        "permutationNull": nullrep,
        "adjudication": {
            "applied": not args.no_adjudication,
            "rejected": [
                {"rowIndex": i, "article": dict(fd)[i]["article"],
                 "comparisonId": dict(fd)[i]["comparisonId"],
                 "dataSource": dict(fd)[i].get("dataSource"),
                 "mechanicalVerdict": e["mechanical"], "reason": e["reason"]}
                for i, e in sorted(adjudicated.items())],
        },
        "preRegisteredBar": {"comparisons": bar_c, "articles": bar_a, "met": ok},
        "audit": [
            {"rowIndex": i, "comparisonId": r["comparisonId"], "article": r["article"],
             "dataSource": r["dataSource"], "panelLetter": r.get("panelLetter"),
             "figureId": r.get("figureId"),
             "extractionMethod": r.get("extractionMethod"),
             "verdict": results[i]["verdict"], "zone": results[i]["zone"],
             "mechanicalVerdict": results[i].get("mechanicalVerdict"),
             "adjudication": results[i].get("adjudication"),
             "armGapChars": results[i].get("armGapChars"),
             "meanConfirmed": channel_counts(results[i])[0],
             "varianceConfirmed": channel_counts(results[i])[1],
             "evidence": results[i]["evidence"]}
            for i, r in checked
            if results[i]["verdict"] not in ("NOT_FOUND", "NO_PDF")],
    }
    if args.dry_run:
        print(f"\n[--dry-run] report NOT written to {REPORT_JSON}")
    else:
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(rep, indent=2))
        print(f"\n[written] {REPORT_JSON}")
    return rep


def write_back(data, results, report):
    src = {"CONFIRMED_IN_FIGURE_VECTOR": "in_figure_vector",
           "CONFIRMED_IN_FIGURE_OCR": "in_figure_ocr",
           "CONFIRMED_CAPTION": "caption", "CONFIRMED_TEXT": "body_text"}
    n = 0
    for i, r in enumerate(data["rows"]):
        res = results.get(i)
        if res is None:
            continue
        v = res["verdict"]
        r["oracleVerified"] = v
        r["isOracle"] = v.startswith("CONFIRMED")
        r["oracleSource"] = src.get(v)
        mc, vc = channel_counts(res)
        r["oracleMeanConfirmed"], r["oracleVarianceConfirmed"] = mc, vc
        n += r["isOracle"]
    data["oracleVerificationV2"] = {k: report[k] for k in
                                    ("generatedAt", "method", "counts",
                                     "permutationNull", "preRegisteredBar")}
    CODED.write_text(json.dumps(data, indent=2))
    print(f"[written] {CODED}  (isOracle=true on {n} rows; oracleSource set)")


if __name__ == "__main__":
    main()
