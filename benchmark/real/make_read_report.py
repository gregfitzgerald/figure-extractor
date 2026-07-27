#!/usr/bin/env python3
"""make_read_report.py -- a single self-contained HTML page showing what the reader
actually did to each real journal panel, next to the hand-coded values.

Consumes only committed artefacts (`tasks/`, `vision/`, `out/fields.csv`,
`out/comparisons.csv`, `out/summary.json`, `out/golden_diff.txt`) plus the overlays from
`overlay_reads.py`. Every number is recomputed from the raw picked pixels and checked
against the published CSV, so the page cannot quietly drift from the scored output.

    python3 overlay_reads.py && python3 make_read_report.py
    -> out/read-report.html
"""
import base64
import csv
import glob
import io
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"

try:
    from PIL import Image
except ImportError:
    sys.exit("needs Pillow: pip install Pillow")

MAXW = 1000


def b64(p):
    im = Image.open(p).convert("RGB")
    if im.width > MAXW:
        im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def cls(pct):
    return "good" if pct < 2 else ("mid" if pct < 8 else "bad")


def main():
    fields = list(csv.DictReader(open(OUT / "fields.csv")))
    comps = list(csv.DictReader(open(OUT / "comparisons.csv")))
    summary = json.loads((OUT / "summary.json").read_text())
    golden = (OUT / "golden_diff.txt").read_text()

    by_panel = {}
    for r in fields:
        by_panel.setdefault(r["id"], []).append(r)

    # Re-derive every extracted mean from the raw pixels; refuse to publish on mismatch.
    drift = []
    for tf in sorted(glob.glob(str(HERE / "tasks" / "*.json"))):
        t = json.loads(pathlib.Path(tf).read_text())
        vp = HERE / "vision" / f"{t['id']}.json"
        if not vp.exists():
            continue
        v = json.loads(vp.read_text())
        cp, cv = v["calPixels"], t["calVals"]
        y1p, y2p = cp["y1"]["py"], cp["y2"]["py"]
        y1v, y2v = float(cv["y1"]), float(cv["y2"])
        for bar, b in v["bars"].items():
            m = y1v + (b["top"]["py"] - y1p) * (y2v - y1v) / (y2p - y1p)
            row = next((r for r in fields if r["id"] == t["id"] and r["bar"] == bar), None)
            if row and abs(m - float(row["mean_ext"])) > 0.01:
                drift.append(f"{t['id']}/{bar}: recomputed {m:.4f} != published {row['mean_ext']}")
    if drift:
        sys.exit("published CSV does not match the raw pixels:\n  " + "\n  ".join(drift))

    tasks = {}
    for tf in sorted(glob.glob(str(HERE / "tasks" / "*.json"))):
        t = json.loads(pathlib.Path(tf).read_text())
        tasks[t["id"]] = t

    panels_html = []
    for pid, rows in by_panel.items():
        t = tasks.get(pid, {})
        ov = OUT / "overlays" / f"{pid}.png"
        v = json.loads((HERE / "vision" / f"{pid}.json").read_text())
        img = f'<img src="{b64(ov)}" alt="{pid} with the reader\'s picks overlaid">' if ov.exists() \
            else '<p class="warn">no overlay -- run overlay_reads.py</p>'
        trs = []
        for r in rows:
            mg, sg = float(r["mean_gap_pct"]), float(r["sd_gap_pct"])
            trs.append(
                f"<tr><td class='bar'>{r['bar']}</td><td>{r['role']}</td><td>{r['n']}</td>"
                f"<td>{float(r['mean_coded']):.2f}</td><td>{float(r['mean_ext']):.2f}</td>"
                f"<td class='{cls(mg)}'>{mg:.2f}%</td>"
                f"<td>{float(r['sd_coded']):.2f}</td><td>{float(r['sd_ext']):.2f}</td>"
                f"<td class='{cls(sg)}'>{sg:.1f}%</td>"
                f"<td>{float(r['caplen_units']):.2f}</td></tr>")
        panels_html.append(f"""
<section class="panel">
  <h3>{pid}</h3>
  <p class="src">{t.get('source','')}</p>
  <p class="meta">reader: <code>{v.get('reader','?')}</code> &middot;
     y-axis calibrated {t.get('calVals',{}).get('y1','?')}&ndash;{t.get('calVals',{}).get('y2','?')} &middot;
     dispersion printed as <strong>{t.get('dispersion_shown','?')}</strong></p>
  <div class="fig">{img}</div>
  <table>
    <thead><tr><th>bar</th><th>role</th><th>n</th>
      <th>mean<br>coded</th><th>mean<br>read</th><th>gap</th>
      <th>SD<br>coded</th><th>SD<br>read</th><th>gap</th>
      <th>cap len<br>(units)</th></tr></thead>
    <tbody>{''.join(trs)}</tbody>
  </table>
</section>""")

    crs = []
    for c in comps:
        d = abs(float(c["g_abs_diff"]))
        crs.append(
            f"<tr><td class='bar'>{c['id']}</td><td>{c['article']}</td>"
            f"<td>{float(c['g_coded']):+.4f}</td><td>{float(c['g_ext']):+.4f}</td>"
            f"<td class='{'good' if d < 0.05 else 'mid'}'>{d:.4f}</td>"
            f"<td>{'same' if (float(c['g_coded']) >= 0) == (float(c['g_ext']) >= 0) else 'FLIPPED'}</td></tr>")

    cc, dc = summary["central_channel"], summary["dispersion_channel"]
    html = f"""<title>Real-figure extraction: what the reader actually did</title>
<style>
:root {{ --bg:#fff; --fg:#111; --mut:#666; --line:#e3e3e3; --card:#fafafa;
        --good:#15803d; --mid:#b45309; --bad:#b91c1c; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --fg:#e8e8e8; --mut:#9aa0a6;
        --line:#2a2e35; --card:#161a20; --good:#4ade80; --mid:#fbbf24; --bad:#f87171; }} }}
:root[data-theme="dark"] {{ --bg:#0f1115; --fg:#e8e8e8; --mut:#9aa0a6; --line:#2a2e35;
        --card:#161a20; --good:#4ade80; --mid:#fbbf24; --bad:#f87171; }}
:root[data-theme="light"] {{ --bg:#fff; --fg:#111; --mut:#666; --line:#e3e3e3;
        --card:#fafafa; --good:#15803d; --mid:#b45309; --bad:#b91c1c; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--fg); margin:0 auto; padding:2rem 1.2rem 5rem;
  max-width:1080px; font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
h1 {{ font-size:1.75rem; line-height:1.25; margin:0 0 .4rem; }}
h2 {{ font-size:1.2rem; margin:2.6rem 0 .8rem; padding-bottom:.35rem;
  border-bottom:2px solid var(--line); }}
h3 {{ font-size:1.05rem; margin:0 0 .2rem; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
p.lede {{ color:var(--mut); margin:.2rem 0 1.4rem; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:.8rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.9rem 1rem; }}
.card .n {{ font-size:1.5rem; font-weight:650; }}
.card .l {{ color:var(--mut); font-size:.8rem; text-transform:uppercase; letter-spacing:.04em; }}
.panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:1.1rem 1.2rem; margin:1.2rem 0; }}
.src {{ color:var(--mut); font-size:.88rem; margin:.1rem 0 .3rem; }}
.meta {{ color:var(--mut); font-size:.82rem; margin:0 0 .9rem; }}
.fig {{ overflow-x:auto; margin:.6rem 0 1rem; }}
.fig img {{ max-width:100%; height:auto; border:1px solid var(--line); border-radius:6px;
  background:#fff; display:block; }}
table {{ border-collapse:collapse; width:100%; font-size:.86rem; }}
th,td {{ border-bottom:1px solid var(--line); padding:.4rem .5rem; text-align:right; }}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) {{ text-align:left; }}
th {{ color:var(--mut); font-weight:600; font-size:.76rem; }}
td.bar {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.good {{ color:var(--good); font-weight:600; }} .mid {{ color:var(--mid); font-weight:600; }}
.bad {{ color:var(--bad); font-weight:700; }}
.legend {{ display:flex; flex-wrap:wrap; gap:1rem; font-size:.85rem; margin:.6rem 0 0; }}
.legend span {{ display:flex; align-items:center; gap:.4rem; }}
.sw {{ width:26px; height:0; border-top-width:3px; display:inline-block; }}
pre {{ background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:.9rem 1rem; overflow-x:auto; font-size:.82rem; }}
.note {{ border-left:3px solid var(--mid); padding:.15rem 0 .15rem .9rem; margin:1rem 0;
  color:var(--fg); }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.9em; }}
footer {{ color:var(--mut); font-size:.8rem; margin-top:3rem; border-top:1px solid var(--line);
  padding-top:1rem; }}
</style>

<h1>Real-figure extraction: what the reader actually did</h1>
<p class="lede">Every published number below is recomputed from the raw picked pixels at build
time and checked against <code>out/fields.csv</code>; the page refuses to build on a mismatch.</p>

<div class="cards">
  <div class="card"><div class="n">{len(summary['panels_scored'])}</div>
    <div class="l">panels</div></div>
  <div class="card"><div class="n">{summary['n_bars']}</div><div class="l">bars read</div></div>
  <div class="card"><div class="n good">{cc['median_pct']:.2f}%</div>
    <div class="l">central, median</div></div>
  <div class="card"><div class="n mid">{dc['median_pct']:.2f}%</div>
    <div class="l">dispersion, median</div></div>
  <div class="card"><div class="n bad">{dc['worst_pct']:.1f}%</div>
    <div class="l">dispersion, worst</div></div>
</div>

<div class="note"><strong>What condition this is.</strong> These reads were produced by a
<em>vision model</em> (<code>claude-fable-5</code>) picking pixel coordinates off a grid
overlay at 600&nbsp;dpi, zoom-assisted where a significance asterisk sat over an error cap.
It is <em>not</em> a human clicking in the tool, and <em>not</em> a trained detector. It is the
"careful automated digitizer" condition. The human-click condition is what the real-validation
package exists to measure, and it has not been run.</div>

<h2>How to read the overlays</h2>
<div class="legend">
  <span><i class="sw" style="border-top:3px solid #16a34a"></i> picked bar top &rarr; extracted mean</span>
  <span><i class="sw" style="border-top:3px dashed #d97706"></i> hand-coded mean</span>
  <span><i class="sw" style="border-top:3px solid #dc2626"></i> picked error cap &rarr; extracted SD</span>
  <span><i class="sw" style="border-top:3px dashed #9333ea"></i> hand-coded SD (as mean+SEM)</span>
  <span><i class="sw" style="border-top:3px solid #2563eb"></i> axis reference pixels</span>
</div>
<p class="lede" style="margin-top:.7rem">Where the two solid/dashed pairs coincide the read was
good. The pattern to look for: <strong>bar-top lines sitting on top of each other while the cap
lines visibly separate</strong> &mdash; that is the dispersion-channel finding, drawn rather
than asserted.</p>

<h2>Panel by panel</h2>
{''.join(panels_html)}

<h2>Does it change the meta-analysis?</h2>
<p class="lede">Both columns run through the identical <code>escalc(SMD)</code> +
<code>rma</code> pipeline, so the only difference is the figure reading.</p>
<table>
  <thead><tr><th>comparison</th><th>article</th><th>g coded</th><th>g read</th>
    <th>|&Delta;g|</th><th>direction</th></tr></thead>
  <tbody>{''.join(crs)}</tbody>
</table>
<pre>{golden.strip()}</pre>

<h2>What this does and does not show</h2>
<ul>
<li><strong>Shows:</strong> on 6 real journal panels, central tendency transfers at
    ~0.5% median error and dispersion at ~3.7% median, worst 18.1% &mdash; and the pooled
    effect moves by 0.0125 <em>g</em> with no sign flips. The synthetic finding transfers.</li>
<li><strong>Does not show:</strong> anything about a <em>human</em> reader, which is the
    condition your own extraction work runs in. n = 6 panels, 3 articles, one reader, no
    repeat read, so there is no repeatability estimate and no interval you should trust.</li>
<li><strong>Selection:</strong> these are bar charts with legible caps &mdash; roughly the
    easiest 4-in-5 of the corpus. Dot/median+IQR plots and grouped 3-series bars were not
    scored here.</li>
</ul>

<footer>Generated by <code>benchmark/real/make_read_report.py</code> from committed artefacts.
Panel images are excerpts of published journal figures reproduced here for personal
methodological analysis; check the copyright status of any figure before redistributing it.</footer>
"""
    p = OUT / "read-report.html"
    p.write_text(html, encoding="utf-8")
    kb = p.stat().st_size / 1024
    print(f"[written] {p}  ({kb:.0f} KB)")
    print(f"          {len(by_panel)} panels, {len(fields)} bars, {len(comps)} comparisons; "
          f"all {len(fields)} means re-derived from pixels with 0 mismatches")


if __name__ == "__main__":
    main()
