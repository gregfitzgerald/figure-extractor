#!/usr/bin/env python3
"""Vision-in-the-loop extraction accuracy: write per-chart landmark-estimation tasks for
agents (no answers), plus a truth file for scoring. Agents estimate pixel coordinates from
the ACC_*.png charts; a scorer then feeds those pixels through the tool and compares the
recovered stats to truth."""
import json, pathlib

R = pathlib.Path(__file__).resolve().parent
CH = R / "charts_real"
(R / "vtasks").mkdir(exist_ok=True)
(R / "vresults").mkdir(exist_ok=True)

# calibration anchors (data values) + truth mirror the extraction_accuracy.py builders
TRUTH = {
    "ACC_bar": {"kind": "bar", "ns": [24, 26], "means": [312.0, 241.0], "sds": [95.0, 88.0],
                "calVals": {"x1": "0", "x2": "1", "y1": "0", "y2": "300"}},
    "ACC_box": {"kind": "box", "q": [{"q1": 280.0, "med": 305.0, "q3": 330.0},
                                     {"q1": 205.0, "med": 240.0, "q3": 268.0}],
                "calVals": {"x1": "0", "x2": "1", "y1": "200", "y2": "350"}},
    "ACC_forest": {"kind": "forest", "rows": [{"est": -0.60, "lo": -1.00, "hi": -0.20},
                                              {"est": -0.45, "lo": -0.80, "hi": -0.10}],
                   "calVals": {"x1": "-1.0", "x2": "0.0", "y1": "0", "y2": "1"}},
}
(R / "vtruth.json").write_text(json.dumps(TRUTH, indent=2))

TASKS = {
 "ACC_bar": """Estimate pixel coordinates (image is 720x480, origin TOP-LEFT) from this bar chart.
Use the y-axis LINEAR scale: locate the tick at value 0 and the tick at value 300.
Return ONLY this JSON (no prose) to the output path:
{ "y1":{"px":..,"py":..},  (a point on the y-axis at value 0)
  "y2":{"px":..,"py":..},  (a point on the y-axis at value 300)
  "x1":{"px":..,"py":..},  (baseline point under the LEFT bar)
  "x2":{"px":..,"py":..},  (baseline point under the RIGHT bar)
  "bars":[ {"top":{"px":..,"py":..},"cap":{"px":..,"py":..}},   (LEFT bar: top-center, upper error-bar cap)
           {"top":{"px":..,"py":..},"cap":{"px":..,"py":..}} ] }  (RIGHT bar)
Be as precise as you can reading pixel positions.""",
 "ACC_box": """Estimate pixel coordinates (image 720x480, origin TOP-LEFT) from this box plot.
Use the y-axis at value 200 and value 350 for calibration. Two boxes (left, right).
Return ONLY this JSON to the output path:
{ "y1":{"px":..,"py":..},(y-axis at 200) "y2":{"px":..,"py":..},(y-axis at 350)
  "x1":{"px":..,"py":..},(under left box) "x2":{"px":..,"py":..},(under right box)
  "boxes":[ {"q1":{"px":..,"py":..},"med":{"px":..,"py":..},"q3":{"px":..,"py":..}},  (LEFT: lower edge, median line, upper edge)
            {"q1":{"px":..,"py":..},"med":{"px":..,"py":..},"q3":{"px":..,"py":..}} ] }""",
 "ACC_forest": """Estimate pixel coordinates (image 720x480, origin TOP-LEFT) from this forest plot.
The x-axis is linear; use the tick at value -1.0 and value 0.0 for calibration. Two rows.
Return ONLY this JSON to the output path:
{ "x1":{"px":..,"py":..},(x-axis at -1.0) "x2":{"px":..,"py":..},(x-axis at 0.0)
  "y1":{"px":..,"py":..},(any point; use row spacing - pick the LOWER row marker center)
  "y2":{"px":..,"py":..},(the UPPER row marker center)
  "rows":[ {"est":{"px":..,"py":..},"lo":{"px":..,"py":..},"hi":{"px":..,"py":..}},  (UPPER row: marker, left CI end, right CI end)
           {"est":{"px":..,"py":..},"lo":{"px":..,"py":..},"hi":{"px":..,"py":..}} ] }  (LOWER row)
For y calibration use y1=lower row (value 0), y2=upper row (value 1).""",
}
for k, t in TASKS.items():
    (R / "vtasks" / f"{k}.md").write_text(t)
print("wrote vision-extraction tasks + truth for:", list(TASKS))
