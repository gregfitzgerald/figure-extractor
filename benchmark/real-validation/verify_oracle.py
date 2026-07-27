#!/usr/bin/env python3
"""verify_oracle.py -- decide, MECHANICALLY, whether a coded value is a real oracle.

Why this exists
---------------
A coded row whose `Data_Extraction_Method` reads "Reported in text/figure" or "Reported
in text and figure" LOOKS like a gold standard: if the paper prints the number in its
Results text and plots the same quantity, the printed number is true ground truth for
the figure read, and the study gets a genuine ACCURACY claim on real figures with no
human annotation at all.

But the field is ambiguous. It can equally mean "the coder digitized the figure and the
text corroborated it qualitatively". The workbooks' own 'Help' sheet does NOT define the
value -- it documents `Data_Extraction_Method` only as e.g. "Reported in text",
"Reported in table", "Visual analysis of figure elements". So the label cannot be
trusted, and the difference is the difference between an accuracy claim and an agreement
claim. It has to be checked, not assumed.

The check
---------
Open the article PDF, take the body text (references stripped -- a reference list is
dense with numbers and manufactures false positives), and require that BOTH the coded
mean AND the coded variance appear as printed numbers CLOSE TOGETHER (default within 120
characters, which is what "35.2 +/- 4.8" or "(M = 35.2, SEM = 4.8)" looks like). Either
number alone is not evidence: '2.7' matches a section heading, '20.13' matches a DOI.

Verdicts:
  TEXT_CONFIRMED   both arms' mean+variance found co-located -> a genuine oracle row
  PARTIAL          one arm confirmed, or mean found without its variance
  NOT_FOUND        the numbers are not in the text -> NOT an oracle; the coder read the
                   figure and the label means "corroborated", not "quoted"
  NO_PDF           cannot check

Only TEXT_CONFIRMED rows are admitted to the accuracy analysis. Everything else stays in
the agreement analysis, where the human is a second reader rather than an oracle.

  python3 verify_oracle.py                 # verify + write back into coded_reference.json
  python3 verify_oracle.py --dry-run       # report only
"""
import argparse
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
CODED = HERE / "coded" / "coded_reference.json"
PDF_MAP = HERE.parent / "real" / "pdf_map.json"
WINDOW = 120                      # chars between a mean and its variance to count as paired
REF_HEADS = re.compile(
    r"\n\s*(references|bibliography|literature cited|works cited)\s*\n", re.I)


def body_text(path):
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    txt = "\n".join(p.get_text() for p in doc)
    doc.close()
    # strip the reference list: it is a dense field of numbers (years, volumes, pages,
    # DOIs) that will match almost any 2-4 digit value by chance
    hits = list(REF_HEADS.finditer(txt))
    if hits:
        txt = txt[:hits[-1].start()]
    return re.sub(r"[ \t ]+", " ", txt)


def number_variants(v):
    """A coded 20.13 may be printed as '20.13', '20,13' or (rounded) '20.1'."""
    if v is None:
        return []
    s = f"{float(v):g}"
    out = {s, s.replace(".", ",")}
    if "." in s:
        d = len(s.split(".")[1])
        for k in range(1, d):
            out.add(f"{float(v):.{k}f}")
    else:
        out.add(f"{float(v):.1f}")
    return [x for x in out if len(x.replace(",", "").replace(".", "")) >= 2]


def find_all(txt, variants):
    pos = []
    for v in variants:
        pat = re.compile(r"(?<![0-9.,])" + re.escape(v) + r"(?![0-9])")
        pos += [m.start() for m in pat.finditer(txt)]
    return sorted(pos)


def arm_confirmed(txt, mean, var):
    """Both numbers present AND co-located -- the signature of a printed 'm +/- s'."""
    mp = find_all(txt, number_variants(mean))
    vp = find_all(txt, number_variants(var))
    if not mp or not vp:
        return False, len(mp), len(vp)
    for a in mp:
        for b in vp:
            if abs(a - b) <= WINDOW:
                return True, len(mp), len(vp)
    return False, len(mp), len(vp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--window", type=int, default=WINDOW)
    a = ap.parse_args()
    if not CODED.exists():
        sys.exit(f"no coded reference at {CODED} -- run make_coded_reference.py first")
    data = json.loads(CODED.read_text())
    rows = data["rows"]
    pdfmap = json.loads(PDF_MAP.read_text()) if PDF_MAP.exists() else {}

    cache, verdicts = {}, collections.Counter()
    cand = [r for r in rows if r.get("oracleClaimed")]
    print(f"verifying {len(cand)} oracle-CLAIMED comparisons "
          f"across {len({r['article'] for r in cand})} articles "
          f"({len(pdfmap)} PDFs resolvable)\n")
    detail = []
    for r in cand:
        art = r["article"]
        if art not in cache:
            ent = pdfmap.get(art) or {}
            p = ent.get("pdf")
            cache[art] = body_text(p) if p and pathlib.Path(p).exists() else None
        txt = cache[art]
        if not txt:
            r["oracleVerified"] = "NO_PDF"
            verdicts["NO_PDF"] += 1
            continue
        ok_c, mc, vc = arm_confirmed(txt, r["control"].get("mean"),
                                     r["control"].get("varianceValue"))
        ok_i, mi, vi = arm_confirmed(txt, r["interv"].get("mean"),
                                     r["interv"].get("varianceValue"))
        v = "TEXT_CONFIRMED" if (ok_c and ok_i) else ("PARTIAL" if (ok_c or ok_i)
                                                      else "NOT_FOUND")
        r["oracleVerified"] = v
        r["isOracle"] = (v == "TEXT_CONFIRMED")
        verdicts[v] += 1
        detail.append((art, r["dataSource"], r["extractionMethod"], v))

    print(f"  {'verdict':<16}{'n':>5}   share of checkable")
    checkable = sum(v for k, v in verdicts.items() if k != "NO_PDF")
    for k in ("TEXT_CONFIRMED", "PARTIAL", "NOT_FOUND", "NO_PDF"):
        n = verdicts[k]
        share = f"{100*n/checkable:5.1f}%" if checkable and k != "NO_PDF" else "     -"
        print(f"  {k:<16}{n:>5}   {share}")
    print()
    conf_arts = {a for a, _, _, v in detail if v == "TEXT_CONFIRMED"}
    print(f"  articles with >=1 confirmed oracle row: {len(conf_arts)}")
    if conf_arts:
        print(f"    {', '.join(sorted(conf_arts)[:12])}"
              + (" ..." if len(conf_arts) > 12 else ""))
    by_method = collections.defaultdict(collections.Counter)
    for _, _, m, v in detail:
        by_method[str(m)][v] += 1
    print("\n  by Data_Extraction_Method (does the label predict the verdict?)")
    for m, c in sorted(by_method.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(c.values())
        print(f"    {m:<34} n={tot:<4} "
              + "  ".join(f"{k}={c[k]}" for k in
                          ("TEXT_CONFIRMED", "PARTIAL", "NOT_FOUND", "NO_PDF") if c[k]))
    print("\n  INTERPRETATION")
    tc = verdicts["TEXT_CONFIRMED"]
    if checkable and tc / checkable >= 0.5:
        print("    The label is largely trustworthy. The confirmed rows form a genuine")
        print("    real-figure ACCURACY stratum: primary accuracy analysis (plan sec.1.4b).")
    elif tc == 0:
        print("    NOT A SINGLE claimed row has its numbers printed in the text.")
        print("    'Reported in text/figure' means CORROBORATED, not QUOTED. There is no")
        print("    oracle stratum; the whole dispersion analysis stays an AGREEMENT")
        print("    analysis (three-reading Grubbs decomposition). Do not weaken this to")
        print("    'accuracy' anywhere in the write-up.")
    else:
        print(f"    Mixed: {tc}/{checkable} confirmed. Use ONLY the confirmed rows as the")
        print("    accuracy stratum, report its size and its selection caveat, and keep")
        print("    everything else in the agreement analysis.")

    if not a.dry_run:
        data["oracleVerification"] = {
            "window": a.window, "verdicts": dict(verdicts),
            "confirmedArticles": sorted(conf_arts),
        }
        CODED.write_text(json.dumps(data, indent=2))
        print(f"\n[written] {CODED} (isOracle set only where TEXT_CONFIRMED)")


if __name__ == "__main__":
    main()
