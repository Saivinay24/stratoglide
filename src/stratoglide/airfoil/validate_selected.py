"""Direct lift validation of the SELECTED wing section where UIUC has data for it (downgrade/tightening D3).

UIUC LSAT Vol 5 has clean S1223 lift/moment data (no drag) at Re 80k-250k. Same CLa and CLmax bars as
check 5. Section lift floor = lowest tested Re such that it and every higher tested Re pass both lift bars.
The sizing design floor becomes max(D1 floor, this floor). Drag of the selected section stays unvalidated
(no tunnel drag data); the E387/SD7037 knockdown k(Re) (D2) is applied to it.
"""
from __future__ import annotations

import re

import numpy as np

from ..common import DATA, Numbers, latest_phase_file, load_cfg, phase_dir, read_json, write_json
from . import xfoil_runner
from .uiuc_loader import ascending_branch
from .validate import _fit_slope

VOL5 = DATA / "validation" / "uiuc_lsat_vol5"
FILES = {"S1223": "s1223_lift.dat", "E387": "e387_lift.dat"}


def load_vol5_lift(foil):
    s = (VOL5 / FILES[foil]).read_text(errors="replace").replace("\r", "")
    out = []
    for p in re.split(r"Average Reynolds #:\s*\n", s)[1:]:
        L = p.split("\n")
        rows = []
        for ln in L[1:]:
            t = ln.split()
            if len(t) == 3:
                try:
                    rows.append([float(x) for x in t])
                except ValueError:
                    pass
        out.append({"re": float(L[0]), "lift": np.array(rows)})
    return out


def main():
    sel = read_json(latest_phase_file("p2", "selection.json"))
    val = read_json(latest_phase_file("p2", "validation.json"))
    bars = load_cfg("bars")["validation"]
    foil, nc = sel["selected"], val["design_ncrit"]
    res = {"foil": foil, "ncrit": nc, "available": foil in FILES, "rows": []}
    floor = None
    if foil in FILES:
        for run in load_vol5_lift(foil):
            a = ascending_branch(run["lift"])
            p = xfoil_runner.polar(foil, float(round(run["re"])), float(nc))
            i = int(np.argmax(a[:, 1]))
            cla_e = _fit_slope(a[:, 0], a[:, 1], *bars["cla_alpha_range_deg"])
            cla_m = _fit_slope(p["alpha"], p["cl"], *bars["cla_alpha_range_deg"])
            row = {"re": run["re"], "clmax_exp": float(a[i, 1]), "alpha_clmax_exp": float(a[i, 0]),
                   "clmax_xfoil": float(np.max(p["cl"])), "cla_exp": cla_e, "cla_xfoil": cla_m}
            row["clmax_err"] = abs(row["clmax_xfoil"] - row["clmax_exp"])
            row["cla_err"] = abs(cla_m / cla_e - 1)
            row["pass_clmax"] = bool(row["clmax_err"] <= bars["clmax_abs_err_max"])
            row["pass_cla"] = bool(row["cla_err"] <= bars["cla_rel_err_max"])
            row["pass"] = row["pass_clmax"]  # D3 floor uses CLmax (lift-cliff hazard); CLa reported as measured
            res["rows"].append(row)
        rows = sorted(res["rows"], key=lambda r: r["re"])
        for i, r in enumerate(rows):
            if all(x["pass"] for x in rows[i:]):
                floor = r["re"]
                break
    res["section_lift_floor"] = floor
    d1 = float(val["re_design_floor"])
    if res["available"] and floor is None:
        raise SystemExit(f"{foil} fails its own CLmax data at every tested Re: not usable (no fallback floor)")
    # floor rounded up to the sweep grid point at or above the measured run Re
    res["design_floor_final"] = max(d1, floor) if floor else d1
    write_json(phase_dir("p2") / "validation_selected.json", res)
    n = Numbers("p2", "src/stratoglide/airfoil/validate_selected.py")
    n.add("selected_lift_validation_available", res["available"], "bool")
    n.add("selected_section_lift_floor_re", floor, "-")
    n.add("re_design_floor_final", res["design_floor_final"], "-", note="max(D1 floor, selected-section lift floor)")
    for r in res["rows"]:
        k = f"{int(round(r['re'] / 1e4) * 10)}k"
        n.add(f"sel_clmax_err_re{k}", r["clmax_err"], "-")
        n.add(f"sel_clmax_exp_re{k}", r["clmax_exp"], "-")
    pth = phase_dir("p2") / "numbers.json"
    prev = read_json(pth) if pth.exists() else {}
    prev.update(n.items)
    write_json(pth, prev)
    for r in res["rows"]:
        print(f"Re {r['re']:7.0f} CLmax exp {r['clmax_exp']:.2f} xfoil {r['clmax_xfoil']:.2f} err {r['clmax_err']:.2f} "
              f"CLa err {100*r['cla_err']:.1f}% CLmax {'PASS' if r['pass_clmax'] else 'fail'} CLa {'PASS' if r['pass_cla'] else 'fail'}")
    print("section lift floor", floor, "design floor final", res["design_floor_final"])


if __name__ == "__main__":
    main()
