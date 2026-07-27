#!/usr/bin/env python3
"""rvcommon.py -- shared plumbing for the human real-figure validation tier.

Everything in here exists so the HUMAN annotation pass and the MACHINE pass are
literally the same measurement:

  * the controlled vocabularies are parsed LIVE out of figure-extractor.html
    (`CHAR_VOCAB`), so a human coding form that validates is by construction a
    valid tool input and cannot drift from the product;
  * pixel -> data goes through `benchmark/harness/calibrate.py::py_calibrate`,
    the byte-verified port of the tool's `computeCalibration`, so the human's
    clicks and the agent's picks pass through the SAME affine;
  * the landmark CSV is emitted with the tool's own `LANDMARK_HEADER` (also
    parsed live) and the tool's quoting/CRLF conventions, so a human export and
    a machine export are diffable line for line.

Nothing here imports or modifies figure-extractor.html; it only reads it.
"""
import hashlib
import json
import os
import pathlib
import random
import re
import sys
import unicodedata
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent
HTML = REPO / "figure-extractor.html"
HARNESS = BENCH / "harness"
REAL = BENCH / "real"

# All *data* (sessions, keys, GT) lives under DATA, which defaults to this directory but
# can be redirected with RV_DATA so the end-to-end test runs in a sandbox. Code and the
# tool itself are always read from the repo.
DATA = pathlib.Path(os.environ.get("RV_DATA") or HERE).resolve()
SESSIONS = DATA / "sessions"
KEYS = DATA / "keys"
GT = DATA / "gt"

sys.path.insert(0, str(HARNESS))
from calibrate import py_calibrate  # noqa: E402  (the tool's affine, not a reimplementation)

SCHEMA_VERSION = 2          # must match figure-extractor.html's SCHEMA_VERSION
RV_SCHEMA_VERSION = 1       # this tier's own record schema

# ---------------------------------------------------------------- vocabulary

_VOCAB_KEYS = ["charType", "scale", "role", "dispersion", "encodes", "method",
               "flags", "seriesEncoding", "labelSource", "dataProvenance",
               "nonDataElement"]


def load_vocab():
    """Parse CHAR_VOCAB out of figure-extractor.html.

    Same regex approach as benchmark/classify/make_tasks.py -- the label space is
    imported from the tool rather than hardcoded, so the coding form can never
    accept a value `validateCharacterization` would reject.
    """
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const CHAR_VOCAB\s*=\s*\{(.*?)\n\};", txt, re.S)
    if not m:
        raise SystemExit("could not locate CHAR_VOCAB in figure-extractor.html")
    body = m.group(1)
    vocab = {}
    for key in _VOCAB_KEYS:
        km = re.search(key + r"\s*:\s*\[(.*?)\]", body, re.S)
        if km:
            vocab[key] = re.findall(r"'([^']+)'", km.group(1))
    missing = [k for k in _VOCAB_KEYS if k not in vocab]
    if missing:
        raise SystemExit(f"CHAR_VOCAB parse incomplete, missing: {missing}")
    return vocab


def load_landmark_header():
    """Parse LANDMARK_HEADER out of figure-extractor.html (29 columns, exact order)."""
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const LANDMARK_HEADER\s*=\s*\[(.*?)\];", txt, re.S)
    if not m:
        raise SystemExit("could not locate LANDMARK_HEADER in figure-extractor.html")
    return re.findall(r"'([^']+)'", m.group(1))


def load_dispersion_with_variance():
    """Parse DISPERSION_WITH_VARIANCE -- the types R can turn into a variance."""
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const DISPERSION_WITH_VARIANCE\s*=\s*new Set\(\[(.*?)\]\)", txt, re.S)
    if not m:
        raise SystemExit("could not locate DISPERSION_WITH_VARIANCE in figure-extractor.html")
    return set(re.findall(r"'([^']+)'", m.group(1)))


def load_js_set(name):
    """Parse `const <name> = new Set([...])` out of figure-extractor.html."""
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const " + name + r"\s*=\s*new Set\(\[(.*?)\]\)", txt, re.S)
    if not m:
        raise SystemExit(f"could not locate {name} in figure-extractor.html")
    return set(re.findall(r"'([^']+)'", m.group(1)))


def extraction_priority(char_type, provenance):
    """Port of figure-extractor.html::extractionPriority, with the type sets read live."""
    if char_type in load_js_set("NON_DATA_TYPES"):
        return "none"
    if char_type in load_js_set("DERIVED_TYPES"):
        return "medium" if provenance == "primary" else "low"
    if provenance == "derived":
        return "low"
    if char_type in load_js_set("ORIGINAL_DATA_TYPES"):
        return "high"
    return "medium"


def load_chart_method():
    """Parse CHART_METHOD -- chartType -> default extraction method routing table."""
    txt = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const CHART_METHOD\s*=\s*\{(.*?)\n\};", txt, re.S)
    if not m:
        raise SystemExit("could not locate CHART_METHOD in figure-extractor.html")
    out = {}
    for k, v in re.findall(r"'?([A-Za-z-]+)'?\s*:\s*'([a-z_-]+)'", m.group(1)):
        out[k] = v
    return out


# ------------------------------------------------------ landmark CSV (tool-identical)

def csv_cell(v):
    """figure-extractor.html::csvCell -- every DATA cell quoted, quotes doubled."""
    s = "" if v is None else str(v)
    return '"' + s.replace('"', '""') + '"'


def landmarks_csv(rows, header=None):
    """figure-extractor.html::landmarksCsv -- BARE header row, quoted data cells, CRLF,
    no trailing newline. Byte-compatible with the tool's figure-derived-landmarks.csv."""
    header = header or load_landmark_header()
    out = [",".join(header)]
    for r in rows:
        out.append(",".join(csv_cell(r.get(h, "")) for h in header))
    return "\r\n".join(out)


def blank_landmark_row(header=None):
    """The tool's `push()` default object: every column present and empty."""
    header = header or load_landmark_header()
    return {h: "" for h in header}


# ------------------------------------------------------------------ small utils

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def read_json(p, default=None):
    p = pathlib.Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p, obj, indent=2):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=indent, ensure_ascii=False), encoding="utf-8")
    print(f"[written] {p}")
    return p


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def anon_id(rng, index, used):
    """`it07_3f9c` -- position-carrying but content-free. Reissued fresh for every
    session, which is what keeps an intra-rater REPEAT unrecognisable as a repeat."""
    while True:
        cand = f"it{index:02d}_{rng.randrange(16**4):04x}"
        if cand not in used:
            used.add(cand)
            return cand


def windows_path(p):
    """Greg opens files from Windows Explorer; WSL paths do not work there."""
    s = str(pathlib.Path(p).resolve())
    if s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        s = s[5].upper() + ":" + s[6:]
    return s.replace("/", "\\")


# --------------------------------------------------- pixel -> data (the tool's affine)

def to_data(cal, vals, points):
    """cal/vals exactly as stored in annotations.json `digitization`."""
    return py_calibrate(cal, vals, points)


def pct(est, ref):
    return 100.0 * abs(est - ref) / abs(ref) if ref else float("nan")


# -------------------------------------------------------------------- seal / blinding

# Fingerprints that PROVE the machine panel detector ran on an export. `panelDetection`
# is written only by applyPanelResult (the "Auto-panels" button / detectPanels API), and
# `captionSource:'panel-split'` is stamped only on auto-created subfigures. A blind human
# pass must carry neither.
ANNOTATION_MODE_MESSAGE = (
    "annotationMode is not true in the export -- the Settings checkbox was off, so the "
    "tool cannot assert that Auto-panels was unavailable. This export is not usable.")


def annotation_mode_violations(annotations):
    """The POSITIVE half of the doubled blinding, and it is the half that matters.

    `blinding_violations` below is negative evidence: it detects that the detector ran and
    throws the figure away afterwards. `annotationMode: true` is the tool asserting that
    the detector COULD NOT have run -- the Settings toggle hides the Auto-panels button,
    makes `detectPanels` refuse (it returns `flags:['annotation-mode']` and no boxes), and
    stamps the marker into both export sites.

    BOTH RATERS ARE HELD TO THE SAME BAR. `prepare_dan_session.check_exports` has always
    hard-rejected a Dan export without the stamp; Greg's ingest did not check for it at
    all, so the two readings being compared were blinded by different mechanisms -- one
    mechanical, one by good intentions. That asymmetry is itself a threat to the
    comparison, because a difference between the two readers could then be a difference in
    how they were blinded. Same check, same severity, same wording, both sides
    (amendment A1).
    """
    return [] if annotations.get("annotationMode") is True else [ANNOTATION_MODE_MESSAGE]


def blinding_violations(annotations):
    bad = []
    for f in annotations.get("figures", []):
        fid = f.get("id") or f.get("label") or "?"
        if f.get("panelDetection") is not None:
            pd = f["panelDetection"]
            bad.append(f"figure {fid}: panelDetection present "
                       f"(method={pd.get('method')}, conf={pd.get('confidence')}) "
                       f"-- the Auto-panels detector was run on this figure")
        for s in f.get("subfigures", []):
            if s.get("captionSource") == "panel-split":
                bad.append(f"subfigure {s.get('id')}: captionSource='panel-split' "
                           f"-- this panel box was created by the detector, not by hand")
    return bad


def seal(paths, extra=None):
    """A tamper-evident record of exactly what the human produced and WHEN.

    The machine pass must run strictly after `sealedAt`; the analysis plan asserts
    that ordering, which is what makes "the human did not see the detector" checkable
    after the fact rather than merely asserted.
    """
    files = []
    for p in sorted(pathlib.Path(x) for x in paths):
        files.append({"path": str(p.relative_to(DATA)) if DATA in p.parents else str(p),
                      "sha256": sha256_file(p), "bytes": p.stat().st_size})
    rec = {"schemaVersion": RV_SCHEMA_VERSION, "sealedAt": now_iso(), "files": files}
    if extra:
        rec.update(extra)
    return rec


def verify_seal(rec, base=None):
    """Return a list of problems (empty = the sealed artifacts are unchanged)."""
    base = base or DATA
    bad = []
    for f in rec.get("files", []):
        p = pathlib.Path(f["path"])
        if not p.is_absolute():
            p = base / p
        if not p.exists():
            bad.append(f"MISSING {p}")
        elif sha256_file(p) != f["sha256"]:
            bad.append(f"CHANGED {p}")
    return bad


# ------------------------------------------------------------------ ordering / strata

def interleave_by_stratum(items, key, seed):
    """Round-robin across strata after shuffling within each.

    Randomising the whole list would let a run of hard figures land at the end of a
    session by chance, confounding fatigue with difficulty. Round-robin guarantees the
    strata are spread evenly over serial position; the within-stratum shuffle keeps the
    order unpredictable. `ingest_annotations.py audit` reports the realised
    difficulty-vs-position correlation so the balance is verified, not assumed.
    """
    rng = random.Random(seed)
    buckets = {}
    for it in items:
        buckets.setdefault(key(it), []).append(it)
    for b in buckets.values():
        rng.shuffle(b)
    order = sorted(buckets.keys(), key=str)
    rng.shuffle(order)
    out, i = [], 0
    while any(buckets[k] for k in order):
        k = order[i % len(order)]
        if buckets[k]:
            out.append(buckets[k].pop())
        i += 1
    return out
