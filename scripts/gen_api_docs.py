#!/usr/bin/env python3
"""Generate the `window.figureExtractor` API reference from figure-extractor.html.

The block between the BEGIN/END GENERATED markers in AI-SKILL.md is emitted by
this script. Hand-written API tables drift (the pre-generator table documented
14 of 36 methods); this one is parsed from the object literal itself and
cross-checked against the live runtime by scripts/test_api_docs.py. To change a
description, edit the source comment in figure-extractor.html, then re-run with
--write.

Usage:
  python3 scripts/gen_api_docs.py            # print the generated block
  python3 scripts/gen_api_docs.py --names    # print parsed method names, one per line
  python3 scripts/gen_api_docs.py --write    # rewrite the block in AI-SKILL.md
  python3 scripts/gen_api_docs.py --check    # exit 1 if AI-SKILL.md is stale

Parsing strategy: comments and string interiors are masked out first, so brace/
paren matching and property splitting only ever see structural code. The object
boundary is found by brace matching from `window.figureExtractor = {`, never by
indentation or a closing-brace regex.
"""

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML = REPO / "figure-extractor.html"
DOC = REPO / "AI-SKILL.md"
MARK_BEGIN = "<!-- BEGIN GENERATED: figureExtractor API reference (scripts/gen_api_docs.py -- do not edit by hand) -->"
MARK_END = "<!-- END GENERATED: figureExtractor API reference -->"

# Descriptions for the few members whose source comment attaches to a sibling
# (comment blocks bind to the property immediately below them). Only used when
# the member has no comment of its own; names that vanish from the source just
# leave dead dict entries and cannot resurrect a removed method.
FALLBACK_DESC = {
    "getCharacterization": "Read back the stored characterization for a figure (subId=null) or subfigure; null if none.",
    "setExtraction": "Store an interpreted extraction object on a figure/subfigure; figure-derived provenance is stamped last so a caller cannot overwrite it.",
    "getExtraction": "Read back the stored extraction for a figure/subfigure; null if none.",
    "suggestExtractionPriority": "Per-panel extraction priority from the stored characterization (see extractionPriority).",
    "extract": "The EXTRACT namespace -- interprets calibrated DATA-unit landmarks per method; the landmarks are authoritative, R derives variances.",
    "getTraceDiagnostics": "Diagnostics from the last auto-trace run, plus the count of active exclusion regions.",
    "getFigureDerivedCsv": "getFigureDerivedRows() serialized as the landmarks CSV handed to R.",
}

BANNER = re.compile(r"^-{3,}.*-{3,}$")


def mask_code(src):
    """Blank comments and string/template interiors; keep length identical.

    Returns (masked, comments) where `comments` is a list of (start, end, text)
    spans for // line comments (text excludes the slashes).
    """
    n = len(src)
    out = list(src)
    comments = []
    mode = "code"
    interp = []  # brace depths of open template-literal ${ } interpolations
    cstart = 0
    i = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if mode == "code":
            if c == "/" and nxt == "/":
                cstart = i
                out[i] = out[i + 1] = " "
                i += 2
                mode = "line"
            elif c == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                i += 2
                mode = "block"
            elif c == "'":
                mode = "sq"
                i += 1
            elif c == '"':
                mode = "dq"
                i += 1
            elif c == "`":
                out[i] = " "
                mode = "tpl"
                i += 1
            else:
                if interp:
                    if c == "{":
                        interp[-1] += 1
                    elif c == "}":
                        if interp[-1] == 0:
                            interp.pop()
                            out[i] = " "
                            mode = "tpl"
                            i += 1
                            continue
                        interp[-1] -= 1
                i += 1
        elif mode == "line":
            if c == "\n":
                comments.append((cstart, i, src[cstart + 2:i]))
                mode = "code"
            else:
                out[i] = " "
            i += 1
        elif mode == "block":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                mode = "code"
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
        elif mode in ("sq", "dq"):
            q = "'" if mode == "sq" else '"'
            if c == "\\" and i + 1 < n:
                out[i] = " "
                if src[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
            elif c == q or c == "\n":
                mode = "code"
                i += 1
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
        elif mode == "tpl":
            if c == "\\" and i + 1 < n:
                out[i] = " "
                if src[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
            elif c == "`":
                out[i] = " "
                mode = "code"
                i += 1
            elif c == "$" and nxt == "{":
                out[i] = out[i + 1] = " "
                interp.append(0)
                mode = "code"
                i += 2
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
    return "".join(out), comments


def match_brace(masked, open_idx):
    depth = 0
    for j in range(open_idx, len(masked)):
        c = masked[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("unbalanced braces from index %d" % open_idx)


def parse_object(masked, comments, open_idx):
    """Split an object literal into top-level properties.

    Returns (close_idx, props); each prop is a dict with name, vstart (index
    where the value/params begin), end (exclusive), comments (list of comment
    texts between the previous property and this one), shorthand (True for
    `name(args) { ... }` method syntax).
    """
    close = match_brace(masked, open_idx)
    props = []
    depth = 0
    expecting = True
    prev_end = open_idx + 1
    j = open_idx + 1
    while j < close:
        c = masked[j]
        if c in "{[(":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == ",":
            expecting = True
            if props:
                props[-1]["end"] = j
            prev_end = j + 1
        elif depth == 0 and expecting and (c.isalpha() or c in "_$"):
            m = re.match(r"([A-Za-z_$][\w$]*)\s*(:|\()", masked[j:])
            if m:
                name, kind = m.group(1), m.group(2)
                cmts = [t for (s, e, t) in comments if prev_end <= s < j]
                vstart = j + (m.end() if kind == ":" else len(name))
                props.append({"name": name, "vstart": vstart, "end": close,
                              "comments": cmts, "shorthand": kind == "("})
                expecting = False
                j += len(name)
                continue
            expecting = False
        j += 1
    return close, props


def parse_params(masked, src, prop):
    """Return the parameter list (with defaults, from the original source), or
    None when the value is not a function."""
    v0, v1 = prop["vstart"], prop["end"]
    m = re.match(r"\s*(async\s+)?\(", masked[v0:v1])
    if not m:
        return None, False
    is_async = bool(m.group(1))
    po = v0 + m.end() - 1
    depth = 0
    pc = None
    for j in range(po, v1):
        c = masked[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                pc = j
                break
    if pc is None:
        return None, False
    if not prop["shorthand"]:
        if not masked[pc + 1:v1].lstrip().startswith("=>"):
            return None, False
    params = []
    depth = 0
    start = po + 1
    for j in range(po + 1, pc + 1):
        c = masked[j]
        if c in "([{":
            depth += 1
        elif c in ")]}" and j != pc:
            depth -= 1
        if (c == "," and depth == 0) or j == pc:
            p = re.sub(r"\s+", " ", src[start:j].strip())
            if p:
                params.append(re.sub(r"\s*=\s*", "=", p))
            start = j + 1
    return params, is_async


def literal_keys(masked, src, open_idx):
    """Top-level keys of an object literal (shorthand and spread included)."""
    close = match_brace(masked, open_idx)
    keys = []
    depth = 0
    expecting = True
    j = open_idx + 1
    while j < close:
        c = masked[j]
        if c in "{[(":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == ",":
            expecting = True
        elif depth == 0 and expecting and not c.isspace():
            m = re.match(r"\.\.\.[\w$.]*", src[j:])
            if m:
                keys.append(m.group(0))
                expecting = False
                j += len(m.group(0))
                continue
            m = re.match(r"[A-Za-z_$][\w$]*", masked[j:])
            if m:
                keys.append(m.group(0))
                expecting = False
                j += len(m.group(0))
                continue
            expecting = False
        j += 1
    return keys


def return_shapes(masked, src, prop):
    """Shapes of object literals the function returns, where determinable."""
    v0, v1 = prop["vstart"], prop["end"]
    seg = masked[v0:v1]
    starts = []
    m = re.match(r"\s*(?:async\s+)?\([^)]*\)\s*=>\s*\(\s*\{", seg)
    if m:
        starts.append(v0 + m.end() - 1)
    for mm in re.finditer(r"\breturn\s*\{", seg):
        starts.append(v0 + mm.end() - 1)
    shapes = []
    for s in starts:
        keys = literal_keys(masked, src, s)
        if keys:
            sig = "{" + ", ".join(keys) + "}"
            if sig not in shapes:
                shapes.append(sig)
    return shapes


def build_desc(comment_lines):
    """One-line description from a comment block: the first sentence(s), joined
    across wrapped lines, stopping at a sentence terminator or ~300 chars."""
    lines = [t.strip() for t in comment_lines]
    lines = [l for l in lines if l and not BANNER.match(l)]
    if not lines:
        return ""
    desc = lines[0]
    i = 1
    while i < len(lines) and len(desc) < 300 and not re.search(r"[.:;)]$", desc):
        nxt = lines[i]
        if desc.endswith("-"):
            desc += nxt
        elif re.match(r"^[a-z_$][\w$]*\s*:", nxt):
            desc += " -- " + nxt  # a `param: meaning` note starting its own line
        else:
            desc += " " + nxt
        i += 1
    desc = desc.rstrip(":").rstrip()
    desc = desc.replace("—", "--").replace("–", "--")
    desc = re.sub(r"\s+", " ", desc)
    if not re.search(r"[.!?]$", desc):
        desc += "."
    return desc


def parse_api(html_text):
    """Parse window.figureExtractor and the EXTRACT namespace it re-exports."""
    masked, comments = mask_code(html_text)
    m = re.search(r"window\.figureExtractor\s*=\s*\{", masked)
    if not m:
        raise ValueError("window.figureExtractor = { ... } not found")
    _, props = parse_object(masked, comments, m.end() - 1)
    me = re.search(r"const EXTRACT\s*=\s*\{", masked)
    extract_props = []
    if me:
        _, extract_props = parse_object(masked, comments, me.end() - 1)
    return masked, html_text, props, extract_props


def generate(html_text):
    """Return (markdown_block, method_names)."""
    masked, src, props, extract_props = parse_api(html_text)
    out = []
    out.append("## Full API Reference")
    out.append("")
    out.append("%d methods on `window.figureExtractor`, in source order. Descriptions come"
               % len(props))
    out.append("from the source comments in `figure-extractor.html`; regenerate this block")
    out.append("with `python3 scripts/gen_api_docs.py --write` after the source changes")
    out.append("(`scripts/test_api_docs.py` fails when it drifts from the runtime surface).")
    out.append("")
    for p in props:
        name = p["name"]
        params, is_async = parse_params(masked, src, p)
        desc = build_desc(p["comments"]) or FALLBACK_DESC.get(name, "(no source comment)")
        value = src[p["vstart"]:p["end"]].strip().rstrip(",").strip()
        if params is None and value == "EXTRACT":
            out.append("- `%s` -- %s" % (name, desc))
            for ep in extract_props:
                eparams, _ = parse_params(masked, src, ep)
                edesc = build_desc(ep["comments"]) or "(no source comment)"
                eshapes = return_shapes(masked, src, ep)
                entry = "  - `extract.%s(%s)` -- %s" % (ep["name"], ", ".join(eparams or []), edesc)
                if eshapes:
                    entry += " Returns `%s`." % " | ".join(eshapes)
                out.append(entry)
            continue
        if params is None:
            sig = "`%s`" % name
        else:
            sig = "`%s(%s)`" % (name, ", ".join(params))
        if is_async:
            sig += " (async)"
        entry = "- %s -- %s" % (sig, desc)
        shapes = return_shapes(masked, src, p)
        if shapes:
            entry += " Returns `%s`." % " | ".join(shapes)
        out.append(entry)
    return "\n".join(out) + "\n", [p["name"] for p in props]


def current_block(doc_text):
    b = doc_text.find(MARK_BEGIN)
    e = doc_text.find(MARK_END)
    if b == -1 or e == -1 or e < b:
        return None
    return doc_text[b + len(MARK_BEGIN):e].strip("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--names", action="store_true", help="print parsed method names")
    ap.add_argument("--write", action="store_true", help="rewrite the block in AI-SKILL.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if AI-SKILL.md is stale")
    args = ap.parse_args()

    block, names = generate(HTML.read_text(encoding="utf-8"))

    if args.names:
        print("\n".join(names))
        return 0

    if args.write or args.check:
        doc = DOC.read_text(encoding="utf-8")
        cur = current_block(doc)
        if cur is None:
            print("gen_api_docs: BEGIN/END markers not found in %s" % DOC, file=sys.stderr)
            return 1
        if args.check:
            if cur.strip() != block.strip():
                print("gen_api_docs: %s is STALE -- run scripts/gen_api_docs.py --write" % DOC.name,
                      file=sys.stderr)
                return 1
            print("gen_api_docs: %s is up to date (%d methods)" % (DOC.name, len(names)))
            return 0
        b = doc.find(MARK_BEGIN)
        e = doc.find(MARK_END)
        new = doc[:b + len(MARK_BEGIN)] + "\n" + block + MARK_END + doc[e + len(MARK_END):]
        DOC.write_text(new, encoding="utf-8")
        print("gen_api_docs: wrote %d methods into %s" % (len(names), DOC.name))
        return 0

    print(block, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
