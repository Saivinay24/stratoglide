"""Dutch-roll design trade (P4): fin volume VV x wing dihedral at SL and 20 km, AVL eigenvalues.

Screening run at fixed mass properties (fin mass change neglected; the chosen point is then re-sized in P3).
Writes p4/dr_trade.json. Selection rule: smallest VV meeting the 20 km Dutch-roll bar with spiral stable.
"""
import copy
import csv

import numpy as np

from ..common import latest_phase_file, load_cfg, phase_dir, read_json, write_json
from ..sizing import geometry, wb
from . import modes
from . import run_stability as rs


def main():
    s = read_json(latest_phase_file("p3", "sizing.json"))
    g0 = read_json(latest_phase_file("p4", "geometry_final.json"))
    items = [{"item": r["item"], "mass_kg": float(r["mass_kg"]), "x": float(r["x_m"]), "y": float(r["y_m"]),
              "z": float(r["z_m"])} for r in csv.DictReader(open(latest_phase_file("p4", "wb.csv")))]
    I = wb.inertia(items)
    bar = load_cfg("bars")["stability"]["dr_zeta_min"]["alt20"]
    orig = geometry.load_cfg
    rows = []
    try:
        for vv in (0.035, 0.05, 0.065, 0.08):
            for dih in (5.0, 3.0, 1.0):
                def patched(name, _vv=vv, _d=dih):
                    c = copy.deepcopy(orig(name))
                    if name == "design_space":
                        c["sizing"]["tail_VV"] = _vv
                        c["sizing"]["wing_dihedral_deg"] = _d
                    return c
                geometry.load_cfg = patched
                g = geometry.build(g0["S"], g0["AR"], g0["airfoil"], g0["htail"]["airfoil"], g0["tc"])
                for k in ("pod", "prop", "boom", "cg", "mass", "aileron"):
                    if k in g0:
                        g[k] = g0[k]
                row = {"VV": vv, "dihedral_deg": dih}
                for tag, z in (("sl", 0.0), ("alt20", 20000.0)):
                    r = rs.run_at(g, s, items, z, s["cl_loiter"], tag="_sweep")
                    st = r["st"]
                    rho = r["atm"]["rho"]
                    V = float(np.sqrt(2 * s["mtow_kg"] * 9.80665 / (rho * g["S"] * s["cl_loiter"])))
                    A1, A2 = modes.state_space(st, s["mtow_kg"], I, g["S"], g["mac"], g["b"], rho, V, st["e"], g["AR"])
                    nm = modes.classify(r["eig"], A1, A2)
                    row[tag] = {"dr_zeta": nm["dutch_roll"]["avl"]["zeta"], "spiral_re": nm["spiral"]["avl"]["re"],
                                "roll_tau_s": nm["roll"]["avl"]["tau_s"], "sm_pct": 100 * (st["Xnp"] - r["cg"]["x"]) / g["mac"]}
                rows.append(row)
                print(f"VV {vv} dih {dih}: DR zeta SL {row['sl']['dr_zeta']:.3f} 20km {row['alt20']['dr_zeta']:.3f} "
                      f"spiral re 20km {row['alt20']['spiral_re']:+.4f}")
    finally:
        geometry.load_cfg = orig
    ok = [r for r in rows if r["alt20"]["dr_zeta"] >= bar and r["alt20"]["spiral_re"] < 0]
    pick = min(ok, key=lambda r: (r["VV"], -r["dihedral_deg"])) if ok else None
    write_json(phase_dir("p4") / "dr_trade.json", {"bar_dr_zeta_alt20": bar, "rows": rows, "selected": pick,
                                                  "rule": "smallest VV meeting the 20 km DR bar with a stable spiral"})
    print("selected", pick and (pick["VV"], pick["dihedral_deg"]))


if __name__ == "__main__":
    main()
