#!/usr/bin/env python3
"""Drift guard for the figureExtractor API docs.

The API reference in AI-SKILL.md is GENERATED (scripts/gen_api_docs.py); this
test fails when the docs and the tool diverge again -- which is exactly how the
old hand-written table ended up documenting 14 of 36 methods, a `convert`
namespace that had been removed, and a characterization schema the validator
rejects.

Checks:
  1. AI-SKILL.md's generated block == a fresh regeneration from the source.
  2. skills/figure-meta-extract/SKILL.md no longer references the removed
     `figureExtractor.convert` namespace, and its characterization example is
     strict JSON whose series carry id/label/color (the fields the tool reads).
  3. AI-SKILL.md documents the `panel-split` captionSource the tool emits.
  4. (Playwright + Chromium, skipped when unavailable) the parsed method list
     equals Object.keys(window.figureExtractor) exactly, `convert` is really
     gone, and the SKILL.md example passes the live validator verbatim.

Run:  python3 scripts/test_api_docs.py
"""

import difflib
import importlib.util
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML = REPO / "figure-extractor.html"
DOC = REPO / "AI-SKILL.md"
SKILL = REPO / "skills" / "figure-meta-extract" / "SKILL.md"

spec = importlib.util.spec_from_file_location("gen_api_docs", REPO / "scripts" / "gen_api_docs.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

failures = []


def check(ok, label, detail=""):
    print("%s %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        failures.append(label)
        if detail:
            print(detail)


def static_checks():
    block, names = gen.generate(HTML.read_text(encoding="utf-8"))
    doc = DOC.read_text(encoding="utf-8")

    cur = gen.current_block(doc)
    check(cur is not None, "AI-SKILL.md contains the BEGIN/END generated markers")
    if cur is not None:
        same = cur.strip() == block.strip()
        diff = ""
        if not same:
            diff = "\n".join(difflib.unified_diff(
                cur.strip().splitlines(), block.strip().splitlines(),
                "AI-SKILL.md (current)", "regenerated", lineterm=""))
        check(same, "AI-SKILL.md API block matches a fresh regeneration "
                    "(run scripts/gen_api_docs.py --write)", diff)

    check(len(names) >= 30, "parser found a plausible method count (%d)" % len(names))
    missing = [n for n in names if ("`%s`" % n) not in block and ("`%s(" % n) not in block]
    check(not missing, "every parsed method appears in the generated block", str(missing))

    skill = SKILL.read_text(encoding="utf-8")
    check("figureExtractor.convert" not in skill,
          "SKILL.md does not reference the removed figureExtractor.convert namespace")

    m = re.search(r"```json\n(.*?)```", skill, re.S)
    example = None
    check(m is not None, "SKILL.md has a characterization example block")
    if m:
        try:
            example = json.loads(m.group(1))
        except ValueError as e:
            check(False, "SKILL.md characterization example is strict JSON", str(e))
        else:
            check(True, "SKILL.md characterization example is strict JSON")
            s0 = example["panels"][0]["series"][0]
            need = {"id", "label", "color"}
            check(need <= set(s0),
                  "SKILL.md series example carries the fields the tool reads (id/label/color)",
                  "series[0] keys: %s" % sorted(s0))
            check("colorHex" not in s0 and "name" not in s0,
                  "SKILL.md series example dropped the rejected {name, colorHex} fields")

    check("panel-split" in doc, "AI-SKILL.md documents the panel-split captionSource")
    return names, example


def runtime_checks(names, example):
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except Exception as e:
        print("skip runtime checks (missing dependency: %s)" % e)
        return

    import asyncio

    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            pg = await browser.new_page()
            await pg.goto(HTML.as_uri())
            keys = await pg.evaluate("() => Object.keys(window.figureExtractor)")
            conv = await pg.evaluate("() => typeof window.figureExtractor.convert")
            errs = None
            if example is not None:
                errs = await pg.evaluate("(c) => validateCharacterization(c)", example)
            await browser.close()
        detail = ("runtime-only: %s\ndoc-only: %s"
                  % ([k for k in keys if k not in names], [n for n in names if n not in keys]))
        check(keys == names, "Object.keys(window.figureExtractor) == documented methods, "
                             "exactly and in order (%d)" % len(keys), detail)
        check(conv == "undefined", "figureExtractor.convert is undefined at runtime (typeof: %s)" % conv)
        if example is not None:
            check(errs == [], "SKILL.md characterization example is accepted by the live validator",
                  "validator errors: %s" % errs)

    asyncio.run(run())


def main():
    names, example = static_checks()
    runtime_checks(names, example)
    if failures:
        print("test_api_docs: FAIL (%d)" % len(failures))
        return 1
    print("test_api_docs: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
