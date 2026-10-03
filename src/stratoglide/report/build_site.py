"""Static dashboard: site/index.html + site/assets (css, js, figures) + site/data/*.json, all exported from pipeline
outputs (no number is typed into the page; app.js renders every value from the JSON). Relative paths only, so the
folder works from any subpath with no server. A copy goes to app/static/."""
from __future__ import annotations

import csv
import json
import shutil

import numpy as np

from ..airfoil import xfoil_runner
from ..airfoil.uiuc_loader import load_series
from ..common import OUTPUTS, RESULTS, ROOT, latest_phase_file, read_json

SITE = ROOT / "site"
SRC = ROOT / "src" / "stratoglide" / "report" / "site_src"
FIGS = ["p3_constraint.png", "p3_thermal.png", "p7_footprint.png", "p2_validation.png", "p5_release_mc.png"]


def r6(x):
    if isinstance(x, dict):
        return {k: r6(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [r6(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(f"{float(x):.6g}") if np.isfinite(x) else None  # strict JSON; null = not achievable / undefined
    if isinstance(x, np.integer):
        return int(x)
    return x


def polars():
    v = read_json(latest_phase_file("p2", "validation.json"))
    nc = v["design_ncrit"]
    out = []
    for f in ("E387", "SD7037"):
        exp = load_series(f, "primary")
        for r in (60000, 100000, 200000, 300000):
            res = v["results"][f"{f}|{r}|{nc}|xfoil"]
            p = xfoil_runner.polar(f, float(res["re_actual"]), float(nc))
            d = exp[r]["drag"]
            out.append({"foil": f, "re": r, "ncrit": nc, "cd_mape": res["metrics"]["cd_mape"],
                        "held_out": r not in v["bars"]["re"],
                        "uiuc": {"cd": d[:, 2].tolist(), "cl": d[:, 1].tolist()},
                        "xfoil": {"cd": p["cd"], "cl": p["cl"]}})
    return {"design_ncrit": nc, "bar": v["bars"]["cd_mape_max"], "cases": out}


def release():
    mc = read_json(latest_phase_file("p5", "release_mc.json"))
    z = np.load(latest_phase_file("p5", "release_traj.npz"))
    cols = [str(c) for c in z["cols"]]
    A = z["auto"]
    ci = {c: cols.index(c) for c in ("t", "z", "mach", "nz")}
    pick = np.linspace(0, A.shape[0] - 1, 60).astype(int)
    tr = []
    for i in pick:
        h = A[i]
        ok = np.isfinite(h[:, ci["t"]])
        tr.append({"t": h[ok, ci["t"]].tolist(), "z": h[ok, ci["z"]].tolist()})
    peak_mach = np.nanmax(A[:, :, ci["mach"]], axis=1)
    peak_nz = np.nanmax(A[:, :, ci["nz"]], axis=1)
    return {"N": mc["N"], "seed": mc["seed"], "autopilot": mc["autopilot"], "passive": {k: mc["passive"][k] for k in
            ("recovery_rate", "mach", "nz", "gamma_swing_last20s_deg")},
            "vertical_dive_max_mach_clean": mc["vertical_dive_max_mach_clean"], "traj": tr,
            "peak_mach_recorded": peak_mach.tolist(), "peak_nz_recorded": peak_nz.tolist(),
            "note": "traces and histograms use the recorded history (every 100th step); headline percentiles use every step"}


def main():
    nums = read_json(RESULTS / "numbers.json")
    data = {
        "numbers": {"values_sha256": nums["values_sha256"],
                    "numbers": {k: {"value": v["value"], "unit": v.get("unit", ""), "script": v.get("script", "")}
                                for k, v in nums["numbers"].items()}},
        "geometry": read_json(latest_phase_file("p4", "geometry_final.json")),
        "polars": polars(),
        "stability": {k: read_json(latest_phase_file("p4", "stability.json"))[k] for k in ("cases", "vlm_convergence", "asb")},
        "release": release(),
        "prop": {k: read_json(latest_phase_file("p6", "prop.json"))[k] for k in ("design", "table", "diameter_trade", "motor")},
        "perf": read_json(latest_phase_file("p7", "perf.json")),
        "predictions": json.loads((OUTPUTS / "test_cards" / "predictions.json").read_text()),
        "bom": list(csv.DictReader(open(OUTPUTS / "BOM.csv"))),
    }
    vl = RESULTS / "verify_last.json"
    if vl.exists():
        v = read_json(vl)
        if v.get("total", 0) >= 21:
            data["verify"] = v
    (SITE / "data").mkdir(parents=True, exist_ok=True)
    (SITE / "assets" / "fig").mkdir(parents=True, exist_ok=True)
    for k, d in data.items():
        (SITE / "data" / f"{k}.json").write_text(json.dumps(r6(d), separators=(",", ":")))
    # same data as a script, so the page also works opened straight from disk (file:// blocks fetch)
    (SITE / "data" / "bundle.js").write_text("window.SG_DATA=" + json.dumps(r6(data), separators=(",", ":")) + ";\n")
    for f in FIGS:
        shutil.copy2(OUTPUTS / f, SITE / "assets" / "fig" / f)
    for f in ("index.html", "style.css", "app.js"):
        dst = SITE / f if f == "index.html" else SITE / "assets" / f
        shutil.copy2(SRC / f, dst)
    app = ROOT / "app" / "static"  # generated mirror of site/ (nothing hand-written lives here)
    shutil.copytree(SITE, app, dirs_exist_ok=True)
    print("site", sorted(p.name for p in (SITE / "data").iterdir()), "verify embedded", "verify" in data)


if __name__ == "__main__":
    main()
