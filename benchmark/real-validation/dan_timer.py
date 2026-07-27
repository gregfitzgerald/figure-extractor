#!/usr/bin/env python3
"""dan_timer.py -- per-item stopwatch for the second rater. Runs from the handoff archive.

This file ships INSIDE the handoff zip and is deliberately self-contained: standard library
only, no imports from the harness, no repository checkout, no `RV_DATA`. The version it
replaces (`prepare_dan_session.py timer`) delegated into `prepare_session.py`, which pulls
in `rvcommon`, the tool's `calibrate` module and the whole session tree -- none of which the
second rater has. The failure mode that prevents: a rater who cannot start the clock, so the
timing channel is simply missing and "did this panel take 40 s or 6 min" becomes
unanswerable after the fact.

Run it from the folder you unzipped, alongside the worksheet:

    python3 dan_timer.py A        # Stage A -- one row per figure
    python3 dan_timer.py B        # Stage B -- one row per panel

ENTER starts an item. ENTER again ends it; type a short note first if you want to record
one. `b` logs a break, `q` quits -- re-run the same command and it resumes where you
stopped. Output is `timing.jsonl` in this folder; send it back with your exports.

Timing is a bias control, not surveillance. Items read unusually fast are reported
separately, because a 40-second panel and a 6-minute panel are not the same measurement.
"""
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "timing.jsonl"
BREAK_AFTER = 10          # scheduled 15-minute break, matching the protocol's sec.6 rule

# `| 3 | `dn03_9c1a` | Figure 7 | 1700x2200 |` in A-WORKSHEET.md, and
# `| 3 | `dn03_9c1a_pB` | B | [2210, 1480] | 3.1x |` in B-WORKSHEET.md. The first two
# columns are all this needs, and they are the two columns both worksheets share.
ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_items(stage):
    """Item order, from whatever the archive actually contains.

    The worksheet is the file the rater is told to work top to bottom, so it is the
    authority; the session manifest is only a fallback for a tree that still has one. If
    the two ever disagreed, following the worksheet keeps the timing log aligned with the
    order the work was really done in."""
    ws = HERE / f"{stage}-WORKSHEET.md"
    if ws.exists():
        items = []
        for line in ws.read_text(encoding="utf-8").splitlines():
            m = ROW.match(line)
            if m:
                items.append({"position": int(m.group(1)), "item": m.group(2)})
        if items:
            return items, ws.name
    manifest = HERE / ("sessionB.json" if stage == "B" else "session.json")
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        field = "panel_item" if stage == "B" else "anon_id"
        items = [{"position": i.get("position") or n, "item": i[field]}
                 for n, i in enumerate(data.get("items") or [], 1)]
        if items:
            return items, manifest.name
    raise SystemExit(
        f"no {stage}-WORKSHEET.md (or session manifest) in\n  {HERE}\n"
        f"Run this from the folder you unzipped -- the worksheet is what gives the item "
        f"order, and timing an order other than the worksheet's is worse than not timing.")


def done_items():
    """Items already logged, so `q` then re-run resumes instead of double-counting."""
    if not LOG.exists():
        return set()
    out = set()
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue                       # a half-written line from a hard kill; ignore it
        if rec.get("item") and rec["item"] != "__break__":
            out.add(rec["item"])
    return out


def append(rec):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def log_break():
    append({"item": "__break__", "at": now_iso()})
    input("  break logged -- ENTER when you are back> ")


def main():
    stage = (sys.argv[1].upper() if len(sys.argv) > 1 else "")
    if stage not in ("A", "B"):
        raise SystemExit("usage: python3 dan_timer.py A   (or B)")

    items, source = load_items(stage)
    done = done_items()
    todo = [i for i in items if i["item"] not in done]
    total = len(items)
    print(f"Stage {stage}: {len(todo)} of {total} left  (order from {source})")
    print("ENTER starts an item, ENTER again ends it. Type a note before that second ENTER")
    print("if you want one recorded. 'b' logs a break, 'q' quits -- re-run to resume.\n")

    for n, it in enumerate(todo):
        name, pos = it["item"], it["position"]
        prompt = f"[{pos}/{total}] {name}  START> "
        cmd = input(prompt).strip().lower()
        if cmd == "b":
            log_break()
            cmd = input(prompt).strip().lower()
        if cmd == "q":
            break
        t0 = datetime.now(timezone.utc)
        note = input("  DONE> ").strip()
        t1 = datetime.now(timezone.utc)
        # A note of 'q' is still a note: quitting is the second ENTER, not the first, so the
        # item that was in progress is recorded rather than thrown away.
        quitting = note.lower() == "q"
        if quitting:
            note = ""
        seconds = round((t1 - t0).total_seconds(), 1)
        append({"item": name, "stage": stage, "position": pos,
                "startedAt": t0.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "endedAt": t1.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "seconds": seconds, "note": note})
        print(f"  {seconds:.0f}s logged\n")
        if quitting:
            break
        if pos % BREAK_AFTER == 0 and n != len(todo) - 1:
            print("  --- scheduled 15 minute break: stop clicking now, get up. ---\n")
            log_break()

    print(f"[written] {LOG}")
    print("Send timing.jsonl back with your exports.")


if __name__ == "__main__":
    main()
