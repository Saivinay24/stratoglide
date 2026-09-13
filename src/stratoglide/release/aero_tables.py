"""Full-envelope aero model for release / pull-out (alpha -180..180 deg, beta -90..90 deg).

Attached range: AVL stability derivatives (P4, 20 km case; nondimensional, same at all altitudes), Prandtl-Glauert
on lift slope. Drag: parabolic polar through the P3 loiter point (CD0 + CL^2/(pi e AR)).
Post-stall: logistic blend in |alpha| (centre alpha_stall, width w) to a flat plate: CN = CD90 sin(alpha),
CL_fp = CN cos(alpha), CD_fp = CN sin(alpha) + CD0. Pitch: Cm = Cm0 + Cma_eff * g(alpha) with g = alpha attached,
sin(alpha) post-stall (bounded; alpha = 180 tail-first is an unstable equilibrium). Controls lose half their
effectiveness post-stall. Drag-rise placeholder above M 0.6 (flagged; design must never get there).
Tail effectiveness factor k_tail scales only the tail share of Cma, Cmq, Cnb, Cnr, CYb (AVL total minus the
flying-wing AVL case). All angles in radians internally; control derivatives from AVL are per degree.
"""
from __future__ import annotations

import numpy as np

from ..common import latest_phase_file, read_json

D2R = np.pi / 180


def nominal():
    st = read_json(latest_phase_file("p4", "stability.json"))
    s = read_json(latest_phase_file("p3", "sizing.json"))
    g = read_json(latest_phase_file("p4", "geometry_final.json"))
    c = st["cases"]["alt20"]
    d = c["derivs"]
    a_t = c["trim_alpha_deg"] * D2R
    de_t = c["trim_elevator_deg"]
    fw = st.get("flying_wing_trade", {})
    e = s["oswald_e"]
    AR = s["AR"]
    cd0 = s["cd_loiter"] - s["cl_loiter"] ** 2 / (np.pi * e * AR)
    clmax = s["clmax_3d"]
    CL0 = d["CLtot"] - d["CLa"] * a_t - d["CLd02"] * de_t
    p = {"S": s["S_m2"], "b": s["span_m"], "c": s["mac_m"], "mass": s["mtow_kg"],
         "Ixx": g["mass"]["Ixx"], "Iyy": g["mass"]["Iyy"], "Izz": g["mass"]["Izz"],
         "CL0": CL0, "CLa": d["CLa"], "CLq": d["CLq"], "CLde": d["CLd02"], "CD0": cd0, "k_ind": 1 / (np.pi * e * AR),
         "Cm0": -d["Cma"] * a_t - d["Cmd02"] * de_t, "Cma": d["Cma"], "Cmq": d["Cmq"], "Cmde": d["Cmd02"],
         "Cma_wb": fw.get("Cma", d["Cma"]), "Cnb_wb": fw.get("Cnb", d["Cnb"]), "Cnr_wb": fw.get("Cnr", d["Cnr"]),
         "CYb": d["CYb"], "CYp": d["CYp"], "CYr": d["CYr"], "CYdr": d["CYd03"],
         "Clb": d["Clb"], "Clp": d["Clp"], "Clr": d["Clr"], "Clda": d["Cld01"], "Cldr": d["Cld03"],
         "Cnb": d["Cnb"], "Cnp": d["Cnp"], "Cnr": d["Cnr"], "Cnda": d["Cnd01"], "Cndr": d["Cnd03"],
         "alpha_stall": (clmax - CL0) / d["CLa"], "CD90": 1.2, "blend_w": 2.0 * D2R, "k_tail": 1.0, "k_elev": 1.0,
         "dcg_mac": 0.0, "trim_alpha": a_t, "trim_de_deg": de_t, "cl_loiter": s["cl_loiter"], "ld_loiter": s["ld_loiter"],
         "vs_eas": s["vs_eas_sl"], "clmax": clmax}
    return p


def coeffs(p, alpha, beta, ph, qh, rh, de, da, dr, mach):
    """Vectorised. p values may be arrays (per MC run). ph, qh, rh are nondimensional rates (p b/2V, q c/2V, r b/2V).
    Returns CX, CY, CZ (body axes), Cl, Cm, Cn."""
    kt = p["k_tail"]
    m = np.minimum(mach, 0.9)
    pg = 1 / np.sqrt(1 - m ** 2)
    sig = 1 / (1 + np.exp(-(np.abs(alpha) - p["alpha_stall"]) / p["blend_w"]))
    CL_att = p["CL0"] + p["CLa"] * pg * alpha + p["CLq"] * qh + p["CLde"] * p["k_elev"] * de
    CD_att = p["CD0"] + p["k_ind"] * CL_att ** 2
    CN = p["CD90"] * np.sin(alpha)
    CL_fp = CN * np.cos(alpha)
    CD_fp = CN * np.sin(alpha) + p["CD0"]
    CL = (1 - sig) * CL_att + sig * CL_fp
    CD = (1 - sig) * CD_att + sig * CD_fp + np.where(mach > 0.6, 20 * (mach - 0.6) ** 4, 0.0)
    ctl = 1 - 0.5 * sig
    Cma = p["Cma_wb"] + kt * (p["Cma"] - p["Cma_wb"])
    g_a = (1 - sig) * alpha + sig * np.sin(alpha)
    Cm = (p["Cm0"] * (1 - sig) + Cma * g_a + kt * p["Cmq"] * qh + p["Cmde"] * p["k_elev"] * kt * ctl * de
          + CL * p["dcg_mac"])
    sb = np.sin(beta)
    Cnb = p["Cnb_wb"] + kt * (p["Cnb"] - p["Cnb_wb"])
    Cnr = p["Cnr_wb"] + kt * (p["Cnr"] - p["Cnr_wb"])
    CY = kt * p["CYb"] * sb + p["CYp"] * ph + p["CYr"] * rh + p["CYdr"] * ctl * dr
    Cl = p["Clb"] * sb + p["Clp"] * ph + p["Clr"] * rh + p["Clda"] * ctl * da + p["Cldr"] * ctl * dr
    Cn = Cnb * sb + p["Cnp"] * ph + Cnr * rh + p["Cnda"] * ctl * da + p["Cndr"] * kt * ctl * dr
    ca, sa = np.cos(alpha), np.sin(alpha)
    CX = -CD * ca + CL * sa
    CZ = -CD * sa - CL * ca
    return CX, CY, CZ, Cl, Cm, Cn, CL, CD, sig
