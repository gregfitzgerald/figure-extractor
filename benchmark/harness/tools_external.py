#!/usr/bin/env python3
"""tools_external.py -- ADAPTER HOOKS for third-party digitizers so they score against
R's descriptives through the SAME harness (score.py's common tool interface). These
tools are interactive/GUI (they need a display) and are NOT run headless in this env,
so the functions below define the mapping from each tool's native export to the harness
tool_output = {calPixels, calVals, landmarks[{role,group,series,px,py}]}. Drop a real
export into benchmark/external/<tool>/<id>.<ext> and these adapters make it scorable.

Why an adapter and not a rerun: WebPlotDigitizer and metaDigitise both externalize a
reproducible record of (a) the axis calibration pixels + values and (b) the clicked
data pixels. That is exactly the harness's tool_output -- so scoring them is a pure
format map, and every tool is judged on the pixels it picked, never on its arithmetic.
"""
import json, pathlib

EXT = pathlib.Path(__file__).resolve().parent.parent / "external"


# ---- WebPlotDigitizer ---------------------------------------------------------
# WPD exports JSON (Tar project or the "Export as JSON") with axesColl (calibration
# points: {px,py}+value) and datasetColl (clicked points, in pixels). Map WPD's two
# calibration points per axis -> the harness's x1,x2,y1,y2 refs; map each dataset to a
# landmark role by dataset NAME convention (name datasets "top_0","cap_0",... in WPD).
def adapt_webplotdigitizer(bundle, export_path):
    """export_path: a WPD JSON export. Returns harness tool_output, or None if absent."""
    p = pathlib.Path(export_path)
    if not p.exists():
        return None
    wpd = json.loads(p.read_text())
    axes = wpd["axesColl"][0]["calibrationPoints"]  # 4 pts: 2 on x-axis, 2 on y-axis
    # WPD calibration points carry .px/.py + .dx/.dy (data). Sort into x/y refs by which
    # data coordinate varies. (Convention: first two vary in x, last two vary in y.)
    xr = [c for c in axes if c.get("dx") is not None][:2]
    yr = [c for c in axes if c.get("dy") is not None][:2]
    calPixels = {"x1": {"px": xr[0]["px"], "py": xr[0]["py"]},
                 "x2": {"px": xr[1]["px"], "py": xr[1]["py"]},
                 "y1": {"px": yr[0]["px"], "py": yr[0]["py"]},
                 "y2": {"px": yr[1]["px"], "py": yr[1]["py"]}}
    calVals = bundle["calibration"]["calVals"]  # values are known from the task
    landmarks = []
    for ds in wpd["datasetColl"]:
        role, _, grp = ds["name"].partition("_")   # dataset named "<role>_<group>[_<series>]"
        grp, _, series = grp.partition("_")
        for pt in ds["data"]:
            landmarks.append({"role": role, "group": int(grp), "series": series or None,
                              "px": pt["value"][0] if "value" in pt else pt["px"],
                              "py": pt["value"][1] if "value" in pt else pt["py"]})
    return {"calPixels": calPixels, "calVals": calVals, "landmarks": landmarks}


# ---- metaDigitise (R) ---------------------------------------------------------
# metaDigitise stores a reproducible `caldat` record per figure (calibration + clicked
# points) and can export raw clicks. Point it at the exported CSV/RDS-derived JSON with
# columns {role,group,series,px,py} plus the 4 calibration pixels.
def adapt_metadigitise(bundle, export_path):
    p = pathlib.Path(export_path)
    if not p.exists():
        return None
    md = json.loads(p.read_text())  # {calPixels:{...}, points:[{role,group,series,px,py}]}
    return {"calPixels": md["calPixels"], "calVals": bundle["calibration"]["calVals"],
            "landmarks": md["points"]}


ADAPTERS = {"webplotdigitizer": adapt_webplotdigitizer, "metadigitise": adapt_metadigitise}


def make_external_tool(name):
    """Return a harness tool(bundle) that reads benchmark/external/<name>/<id>.json."""
    adapt = ADAPTERS[name]

    def tool(bundle):
        return adapt(bundle, EXT / name / f"{bundle['id']}.json")
    return tool
