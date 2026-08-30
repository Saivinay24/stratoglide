"""Single geometry source (geometry.json) for AVL, AeroSandbox, JSBSim, CAD and XFLR5.

Axes: x aft from the wing root leading edge, y right, z up. Wing quarter-chord line unswept, straight taper,
constant dihedral. Conventional tail on a single carbon boom; tractor motor at the pod nose; EO gimbal under
the pod.
"""
from __future__ import annotations

import numpy as np

from ..common import load_cfg


def build(S, AR, foil, tail_foil, tc):
    ds, s, c = load_cfg("design_space"), load_cfg("sizing"), load_cfg("components")
    lam = ds["sizing"]["taper"]
    b = float(np.sqrt(S * AR))
    cr = 2 * S / (b * (1 + lam))
    ct = lam * cr
    mac = (2 / 3) * cr * (1 + lam + lam ** 2) / (1 + lam)
    y_mac = b / 6 * (1 + 2 * lam) / (1 + lam)
    x_qc = 0.25 * cr
    dih = np.radians(ds["sizing"]["wing_dihedral_deg"])
    lt = s["layout"]["tail_arm_over_span"] * b
    Sh = ds["sizing"]["tail_VH"] * S * mac / lt
    Sv = ds["sizing"]["tail_VV"] * S * b / lt
    bh = float(np.sqrt(Sh * s["layout"]["htail_AR"])); ch = Sh / bh
    hv = float(np.sqrt(Sv * s["layout"]["vtail_AR"])); cv = Sv / hv
    x_tail_qc = x_qc + lt
    pod = c["pod"]
    z_boom = -0.03
    g = {
        "S": S, "AR": AR, "b": b, "taper": lam, "c_root": cr, "c_tip": ct, "mac": mac, "y_mac": y_mac,
        "x_ac_wing": x_qc, "dihedral_deg": ds["sizing"]["wing_dihedral_deg"], "airfoil": foil, "tc": tc,
        "wing_sections": [
            {"x_le": 0.0, "y": 0.0, "z": 0.0, "chord": cr, "twist_deg": 0.0},
            {"x_le": x_qc - 0.25 * ct, "y": b / 2, "z": b / 2 * float(np.tan(dih)), "chord": ct, "twist_deg": -2.0},
        ],
        "aileron": {"y_frac": [0.5, 0.95], "chord_frac": 0.25},
        "htail": {"S": Sh, "b": bh, "chord": ch, "x_le": x_tail_qc - 0.25 * ch, "z": z_boom, "airfoil": tail_foil,
                  "elevator_chord_frac": 0.35, "VH": ds["sizing"]["tail_VH"]},
        "vtail": {"S": Sv, "h": hv, "chord": cv, "x_le": x_tail_qc - 0.25 * cv, "z0": z_boom, "airfoil": tail_foil,
                  "rudder_chord_frac": 0.35, "VV": ds["sizing"]["tail_VV"]},
        "tail_arm": lt,
        "pod": {"x_nose": pod["nose_x_m"], "length": pod["length_m"], "diameter": pod["diameter_m"], "z": -0.04},
        "boom": {"x0": pod["nose_x_m"] + pod["length_m"] - 0.05, "x1": x_tail_qc + 0.75 * max(ch, cv),
                 "d": s["layout"]["boom_diameter_m"], "z": z_boom},
        "prop": {"x": pod["nose_x_m"] - 0.02, "diameter": s["propulsion_initial"]["prop_diameter_m"], "layout": "tractor"},
    }
    g["boom"]["length"] = g["boom"]["x1"] - g["boom"]["x0"]
    return g


def np_estimate(g):
    """Classical neutral point estimate (P3 only; AVL replaces it in P4)."""
    AR, ARh = g["AR"], g["htail"]["b"] ** 2 / g["htail"]["S"]
    aw = 2 * np.pi * AR / (2 + np.sqrt(AR ** 2 + 4))
    at = 2 * np.pi * ARh / (2 + np.sqrt(ARh ** 2 + 4))
    deda = 2 * aw / (np.pi * AR)
    eta = 0.9
    VH = g["htail"]["S"] * g["tail_arm"] / (g["S"] * g["mac"])
    return float(g["x_ac_wing"] + eta * VH * (at / aw) * (1 - deda) * g["mac"])
