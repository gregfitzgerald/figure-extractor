#!/usr/bin/env python3
"""test_prereq_gate.py -- the build gate on a MIXED trailing session (amendment A16).

Since A16 a trailing session carries held-back FRESH items alongside the re-reads, so
`_gate_prerequisites` must check the calendar gap for the re-reads ONLY. A held-back fresh
item's "original" resolves to the session currently being built, which is by definition not
sealed yet -- walking every item therefore reports it as an unsealed repeat and blocks the
session from ever being built.

test_end_to_end.py asserts this too, but its fixture (4 items, REPEAT_MIN=3) is too small to
place a fresh item in a trailing session, so there the assertion is vacuous. This constructs
the situation directly.

    python3 test_prereq_gate.py
"""
import datetime
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent

CHILD = r'''
import datetime, pathlib, sys
sys.path.insert(0, %r)
import rvcommon as rv
import prepare_session as ps

old = (datetime.datetime.now(datetime.timezone.utc)
       - datetime.timedelta(days=30)).strftime("%%Y-%%m-%%dT%%H:%%M:%%S.%%fZ")

rv.write_json(rv.KEYS / "plan.key.json", {"sessions": [
    {"session": "S01", "isRepeatSession": False, "nRepeats": 0, "items": [
        {"anon_id": "aa01", "item_id": "w1", "isRepeat": False},
        {"anon_id": "aa02", "item_id": "w2", "isRepeat": False}]},
    {"session": "S02", "isRepeatSession": True, "nRepeats": 1, "items": [
        {"anon_id": "bb01", "item_id": "w1", "isRepeat": True},
        {"anon_id": "bb02", "item_id": "w9", "isRepeat": False}]},
]})
rv.write_json(rv.DATA / "plan.json", {"nItems": 3, "sessions": [
    {"session": "S01", "nItems": 2, "items": []},
    {"session": "S02", "nItems": 2, "items": []}]})
(rv.SESSIONS / "S01").mkdir(parents=True, exist_ok=True)
rv.write_json(rv.SESSIONS / "S01" / "seal.json", {"sealedAt": old, "files": []})

problems = ps._gate_prerequisites("S02", force=True)
for p in problems:
    print("PROBLEM:", p)
''' % (str(HERE),)


def main():
    with tempfile.TemporaryDirectory(prefix="rv-prereq-") as td:
        r = subprocess.run([sys.executable, "-c", CHILD], cwd=str(HERE), text=True,
                           capture_output=True, env=dict(os.environ, RV_DATA=td))
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit("child failed")

    problems = [l[len("PROBLEM: "):] for l in r.stdout.splitlines()
                if l.startswith("PROBLEM: ")]
    failures = []

    def check(name, cond, note=""):
        print(f"  [{'ok ' if cond else 'FAIL'}] {name}{('  ' + note) if note else ''}")
        if not cond:
            failures.append(name)

    bogus = [p for p in problems if "bb02" in p or "w9" in p]
    check("a held-back fresh item is not treated as a re-read", not bogus,
          bogus[0] if bogus else f"{len(problems)} problem(s), none naming bb02")
    check("the genuine re-read is still gated", any("bb01" in p for p in problems),
          "bb01 checked against its original")

    print("\nprereq-gate OK" if not failures else f"\n{len(failures)} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
