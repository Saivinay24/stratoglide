"""BEMT validation vs UIUC Propeller Data Site (Brandt & Selig) APC thin-electric props.

Calibration/validation split (declared before running): the blade-section stand-in is chosen on APC 10x7
(all RPMs) by the bars' CT metric; APC 9x6 and 10x5 are held out and are what check 17 judges.
Also checks eta_BEMT <= momentum ideal eta at every evaluated point.
"""
from __future__ import annotations

import re

import numpy as np

from ..common import DATA, Numbers, OUTPUTS, load_cfg, phase_dir, write_json
from . import bemt
from .section import Section

PROPS = DATA / "validation" / "props"
CANDIDATES = [("naca4412", 0.12), ("clarky", 0.117), ("naca6412", 0.12), ("e63", 0.043), ("sd7037", 0.092)]
CALIB = "apce_10x7"
HELD_OUT = ["apce_9x6", "apce_10x5"]


def runs_for(prop):
    out = []
    for f in sorted(PROPS.glob(f"{prop}_*_*.txt")):
        if f.name.endswith("_geom.txt"):
            continue
        rpm = int(re.search(r"_(\d+)\.txt$", f.name).group(1))
        out.append((rpm, np.loadtxt(f, skiprows=1, ndmin=2), f.name))
    return out


def evaluate(sec, prop, bars):
    g = bemt.load_geom(PROPS / f"{prop}_geom.txt")
    D = float(re.match(r"apce_(\d+)x", prop).group(1)) * 0.0254
    j0, j1 = bars["j_range"]
    rows, per_rpm = [], {}
    for rpm, d, name in runs_for(prop):
        pr = []
        for J, ct, cp, eta in d:
            r = bemt.solve(sec, g, D, 2, rpm, J * rpm / 60 * D)
            ei = bemt.eta_ideal(r["CT"], r["J"])
            pr.append({"J": J, "CT_exp": ct, "CP_exp": cp, "eta_exp": eta, "CT": r["CT"], "CP": r["CP"],
                       "eta": r["eta"], "eta_ideal": ei, "re75": r["re75"]})
        sel = [p for p in pr if j0 <= p["J"] <= j1 and p["CT_exp"] > 0]
        ct_rel = np.mean([abs(p["CT"] - p["CT_exp"]) for p in sel]) / np.mean([p["CT_exp"] for p in sel])
        eta_pk = abs(max(p["eta"] for p in sel) - max(p["eta_exp"] for p in sel))
        per_rpm[str(rpm)] = {"ct_rel": float(ct_rel), "eta_peak_abs": float(eta_pk), "re75_mean": float(np.mean([p["re75"] for p in pr])),
                             "points": pr, "file": name}
        rows += pr
    bound = all(p["eta"] <= p["eta_ideal"] + 1e-9 for p in rows)
    return {"per_rpm": per_rpm, "ct_rel_max": max(v["ct_rel"] for v in per_rpm.values()),
            "eta_peak_abs_max": max(v["eta_peak_abs"] for v in per_rpm.values()), "momentum_bound_ok": bound}


def main():
    bars = load_cfg("bars")["prop"]
    calib = {}
    for foil, tc in CANDIDATES:
        try:
            ev = evaluate(Section(foil, tc), CALIB, bars)
            calib[foil] = {"tc": tc, "ct_rel_max": ev["ct_rel_max"], "eta_peak_abs_max": ev["eta_peak_abs_max"]}
            print("calib", foil, round(ev["ct_rel_max"], 4), round(ev["eta_peak_abs_max"], 4), flush=True)
        except Exception as e:
            calib[foil] = {"error": f"{type(e).__name__}: {e}"}
    ok = {k: v for k, v in calib.items() if "ct_rel_max" in v}
    pick = min(ok, key=lambda k: ok[k]["ct_rel_max"])
    sec = Section(pick, ok[pick]["tc"])
    held = {p: evaluate(sec, p, bars) for p in HELD_OUT}
    calib_full = evaluate(sec, CALIB, bars)
    out = {"calibration_prop": CALIB, "candidates": calib, "section": pick, "section_tc": ok[pick]["tc"],
           "held_out": held, "calibration": calib_full,
           "ct_rel_max_heldout": max(h["ct_rel_max"] for h in held.values()),
           "eta_peak_abs_max_heldout": max(h["eta_peak_abs_max"] for h in held.values()),
           "momentum_bound_ok": all(h["momentum_bound_ok"] for h in held.values()) and calib_full["momentum_bound_ok"]}
    d = phase_dir("p6")
    write_json(d / "prop_validation.json", out)
    _plot(out)
    n = Numbers("p6", "src/stratoglide/prop/validate_prop.py")
    n.add("bemt_section_calib_ct_rel", ok[pick]["ct_rel_max"], "-", note=f"section stand-in {pick} chosen on {CALIB}")
    n.add("bemt_ct_rel_max_heldout", out["ct_rel_max_heldout"])
    n.add("bemt_eta_peak_abs_max_heldout", out["eta_peak_abs_max_heldout"])
    for p, h in held.items():
        for rpm, v in h["per_rpm"].items():
            n.add(f"bemt_ct_rel_{p}_{rpm}", v["ct_rel"])
            n.add(f"bemt_eta_peak_abs_{p}_{rpm}", v["eta_peak_abs"])
            n.add(f"bemt_re75_{p}_{rpm}", v["re75_mean"])
    n.add("bemt_ct_rel_max_calib", calib_full["ct_rel_max"])
    n.save()
    print("section", pick, "held-out CT", round(out["ct_rel_max_heldout"], 4), "eta_pk", round(out["eta_peak_abs_max_heldout"], 4),
          "bound", out["momentum_bound_ok"])


def _plot(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    for i, (p, h) in enumerate(list(out["held_out"].items()) + [(out["calibration_prop"] + " (calibration)", out["calibration"])]):
        for rpm, v in h["per_rpm"].items():
            J = [q["J"] for q in v["points"]]
            l, = ax[i].plot(J, [q["CT_exp"] for q in v["points"]], "o", ms=3, label=f"UIUC {rpm} rpm")
            ax[i].plot(J, [q["CT"] for q in v["points"]], "-", color=l.get_color(), label=f"BEMT {rpm}")
            ax[i].plot(J, [q["eta_exp"] / 5 for q in v["points"]], "s", ms=2, color=l.get_color(), alpha=0.4)
            ax[i].plot(J, [q["eta"] / 5 for q in v["points"]], ":", color=l.get_color(), alpha=0.6)
        ax[i].set_title(f"{p}: CT (solid/dots), eta/5 (dotted/squares)")
        ax[i].set_xlabel("J")
        ax[i].grid(alpha=0.3)
        ax[i].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUTPUTS / "p6_validation.png", dpi=130)


if __name__ == "__main__":
    main()
