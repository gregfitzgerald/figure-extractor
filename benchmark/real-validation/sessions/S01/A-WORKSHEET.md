# S01 -- Stage A worksheet (structure pass)

Built 2026-07-27T23:54:05.402Z. 6 items, page renders at 200 dpi.

Full instructions: `benchmark/real-validation/PROTOCOL.md`. Short version:

**0. FIRST, BEFORE ANYTHING ELSE.** Open **Settings** and tick
   **Annotation mode**. It is OFF by default and it persists per browser, so
   check it every session. The ingest hard-requires the `annotationMode: true`
   stamp (amendment A1) and **rejects the whole session without it** -- you would
   lose the entire sitting, not one item. With it on, the `Auto-panels` button is
   hidden and every detector entry point refuses, so blinding stops being
   something you have to remember and becomes something the tool enforces.

1. Start the stopwatch:  `python3 prepare_session.py timer S01 A`
2. In figure-extractor.html (opened as a **file://** page), press
   **Select Project Folder** and choose `projectA`.
3. Work the items **in the order below**. For each one: draw the figure box,
   then draw one subfigure box per panel and rename each to its caption letter.
4. Draw a panel for **every visual tile you can see**, not only the ones you think
   carry data -- undercounting panels is the failure mode this pass exists to catch.
5. Stop after item 6 whatever happens -- do not run on into the next session, the rest between sittings is part of the measurement.
6. Press **Export All Articles** (not Export This Article), unzip into
   `exports/passA/`, then run `python3 prepare_session.py build-b S01`.

| # | item | annotate | page px |
|---|---|---|---|
| 1 | `it01_420d` | Figure 7 | 1701x2197 |
| 2 | `it02_5c87` | Figure 2 | 1701x2197 |
| 3 | `it03_90f8` | Figure 1 | 1654x2205 |
| 4 | `it04_2adb` | Figure 1 | 1654x2205 |
| 5 | `it05_83b9` | Figure 3 | 1700x2200 |
| 6 | `it06_bb24` | Figure 3 | 1654x2166 |

Tick each item off here as you finish it; the timer log is the record that counts.
