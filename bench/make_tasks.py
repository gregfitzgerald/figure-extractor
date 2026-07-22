#!/usr/bin/env python3
"""Emit LEAK-FREE vision tasks: for each chart, what pixels a reader must locate (calibration
references at known axis values + the landmark points), with NO true values and NO GT pixels.
A vision model reads the image and writes its pixel estimates to bench/vision/<id>.json.
Run: python3 bench/make_tasks.py"""
import json, pathlib
B = pathlib.Path(__file__).resolve().parent
(B / "tasks").mkdir(exist_ok=True); (B / "vision").mkdir(exist_ok=True)
TRUTH = json.loads((B / "truth.json").read_text())

def landmark_keys(it):
    ct = it["chartType"]
    if ct == "bar":
        return [("top_0", "top-center of the LEFT bar (its column height, ignore any error bar)"),
                ("cap_0", "top tip of the UPPER error-bar whisker/cap on the LEFT bar"),
                ("top_1", "top-center of the RIGHT bar"),
                ("cap_1", "top tip of the UPPER error-bar cap on the RIGHT bar")]
    if ct == "box":
        return [("q1_0", "bottom edge of the LEFT box (Q1)"), ("med_0", "median line inside the LEFT box"),
                ("q3_0", "top edge of the LEFT box (Q3)"),
                ("q1_1", "bottom edge of the RIGHT box (Q1)"), ("med_1", "median line inside the RIGHT box"),
                ("q3_1", "top edge of the RIGHT box (Q3)")]
    if ct == "scatter":
        n = len(it["landmarks"])
        return [(f"pt_{i}", f"scatter data point #{i+1}") for i in range(n)]
    return []

for it in TRUTH:
    cv = it["calVals"]
    panel = f" IMPORTANT: read ONLY panel {it['targetPanel']}." if it.get("targetPanel") else ""
    logn = " NOTE: the y-axis is LOGARITHMIC." if cv.get("logY") else ""
    task = {
        "id": it["id"], "chartType": it["chartType"],
        "image": str(B / "charts" / f"{it['id']}.png"),
        "output": str(B / "vision" / f"{it['id']}.json"),
        "instruction": (
            "Estimate PIXEL coordinates in this chart image. Pixel origin (0,0) is the TOP-LEFT of "
            "the image; x increases right, y increases DOWN." + panel + logn + " "
            "First locate 4 axis-calibration references (give each as {px,py}); then locate each landmark below."),
        "calibration_refs": {
            "x1": f"the x-position where x = {cv['x1']} (center of the left group)",
            "x2": f"the x-position where x = {cv['x2']} (center of the right group)",
            "y1": f"the y-axis gridline/tick at value {cv['y1']}",
            "y2": f"the y-axis gridline/tick at value {cv['y2']}"},
        "landmarks": [{"key": k, "desc": d} for k, d in landmark_keys(it)],
        "output_schema": {
            "calPixels": {"x1": {"px": 0, "py": 0}, "x2": {"px": 0, "py": 0},
                          "y1": {"px": 0, "py": 0}, "y2": {"px": 0, "py": 0}},
            "landmarks": {"<key>": {"px": 0, "py": 0}}},
    }
    (B / "tasks" / f"{it['id']}.json").write_text(json.dumps(task, indent=1))
print(f"wrote {len(TRUTH)} tasks -> bench/tasks/  (estimates go to bench/vision/)")
