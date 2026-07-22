#!/usr/bin/env python3
"""make_tasks.py -- emit LEAK-FREE vision tasks. For each chart, what pixels a reader
must locate (axis-calibration references at known values + the landmark points), with
NO true values and NO GT pixels. A vision model / agent reads the image and writes its
pixel estimates to benchmark/vision/<id>.json; score.py --tool vision then runs those
estimates through the same affine and scores them vs R's descriptives.

Estimate schema written by the reader (keys match score.tool_vision exactly):
  { "calPixels": {"x1":{px,py},"x2":{...},"y1":{...},"y2":{...}},
    "landmarks": { "<role>_<group>[_<series>]": {px,py}, ... } }

Run: python3 benchmark/harness/make_tasks.py
"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus"
TASKS = HERE.parent / "tasks"; TASKS.mkdir(exist_ok=True)
(HERE.parent / "vision").mkdir(exist_ok=True)
sys.path.insert(0, str(HERE))


def lm_key(l):
    k = f"{l['role']}_{l['group']}"
    if l.get("series") and l["series"] not in (None, "s1", "NA"):
        k += f"_{l['series']}"
    return k


ROLE_DESC = {
    "top": "top-centre of the bar's column (its height; ignore the error bar)",
    "cap": "top tip of the UPPER error-bar cap (the whisker end above the column)",
    "q1": "bottom edge of the box (Q1 / lower hinge)",
    "med": "median line inside the box",
    "q3": "top edge of the box (Q3 / upper hinge)",
    "whislo": "lower whisker end", "whishi": "upper whisker end",
    "pt": "a scatter data point",
}


def main():
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    n = 0
    for cid in manifest["ids"]:
        b = json.loads((CORPUS / f"{cid}.gt.json").read_text())
        cv = b["calibration"]["calVals"]
        panel = f" IMPORTANT: read ONLY panel {b['targetPanel']} (its bounds are approx pixels {b['panelBounds']})." if b.get("targetPanel") else ""
        logn = " NOTE: the y-axis is LOGARITHMIC (values grow by decades)." if cv.get("logY") else ""
        lms = [{"key": lm_key(l), "desc": ROLE_DESC.get(l["role"], l["role"])} for l in b["landmarks"]]
        task = {
            "id": cid, "chartType": b["chartType"], "image": b["image"],
            "output": f"benchmark/vision/{cid}.json",
            "instruction": (
                "Estimate PIXEL coordinates in this chart image. Origin (0,0) is the TOP-LEFT; "
                "x increases right, y increases DOWN." + panel + logn + " First locate 4 axis-"
                "calibration references, then each landmark below. Give every point as {px,py}."),
            "calibration_refs": {
                "x1": f"x-position where x = {cv['x1']}", "x2": f"x-position where x = {cv['x2']}",
                "y1": f"y-axis tick/gridline at value {cv['y1']}", "y2": f"y-axis tick/gridline at value {cv['y2']}"},
            "landmarks": lms,
            "output_schema": {"calPixels": {"x1": {"px": 0, "py": 0}, "x2": {"px": 0, "py": 0},
                                            "y1": {"px": 0, "py": 0}, "y2": {"px": 0, "py": 0}},
                              "landmarks": {"<key>": {"px": 0, "py": 0}}},
        }
        (TASKS / f"{cid}.json").write_text(json.dumps(task, indent=1))
        n += 1
    print(f"wrote {n} leak-free tasks -> benchmark/tasks/  (estimates go to benchmark/vision/)")


if __name__ == "__main__":
    main()
