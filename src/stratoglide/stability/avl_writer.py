"""Write AVL geometry (.avl) and mass (.mass) files from geometry.json + wb item table.

Controls in declaration order: d1 aileron (wing), d2 elevator (htail), d3 rudder (fin).
Wing profile drag via CDCL from the knocked-down section polar at the loiter Re. The pod is not modelled as
an AVL BODY (limitation logged): its destabilising pitch/yaw contribution is not in the AVL numbers.
"""
from __future__ import annotations

import numpy as np

from ..airfoil.uiuc_loader import normalized_dat
from ..common import OUTPUTS
from ..sizing.aero_model import section_cd

CTRL = {"aileron": 1, "elevator": 2, "rudder": 3}


def _sec(x, y, z, c, inc=0.0):
    return f"SECTION\n{x:.5f} {y:.5f} {z:.5f} {c:.5f} {inc:.3f}\n"


def write_avl(g, sizing, path, xref, zref, cdp=0.0, flying_wing=False, res=1.0):
    R = lambda n: max(2, int(round(n * res)))
    cr, ct, b = g["c_root"], g["c_tip"], g["b"]
    s0, s1 = g["wing_sections"]
    foil_dat = normalized_dat(g["airfoil"]).name
    tail_dat = normalized_dat(g["htail"]["airfoil"]).name
    coef = sizing["polar_fit_coef"]
    re_ = sizing["re_loiter"]
    cls = [0.0, 0.5, 1.0]
    cds = [float(section_cd(c, re_, coef)) for c in cls]
    L = [f"StratoGlide{' flying-wing trade' if flying_wing else ''}", "0.0", "0 0 0.0",
         f"{g['S']:.5f} {g['mac']:.5f} {b:.5f}", f"{xref:.5f} 0.0 {zref:.5f}", f"{cdp:.5f}", "",
         "SURFACE", "Wing", f"{R(12)} 1.0 {R(24)} -2.0", "YDUPLICATE", "0.0", "ANGLE", "0.0", ""]

    def wing_sec(f, ctrl):
        x = s0["x_le"] + f * (s1["x_le"] - s0["x_le"])
        z = f * s1["z"]
        c = cr + f * (ct - cr)
        tw = f * s1["twist_deg"]
        out = _sec(x, f * b / 2, z, c, tw) + f"AFILE\n{foil_dat}\n"
        out += f"CDCL\n{cls[0]} {cds[0]:.5f} {cls[1]} {cds[1]:.5f} {cls[2]} {cds[2]:.5f}\n"
        if ctrl:
            out += "CONTROL\naileron 1.0 0.75 0. 0. 0. -1.0\n"
            if flying_wing:
                out += "CONTROL\nelevator 1.0 0.75 0. 0. 0. 1.0\n"
        return out

    a0, a1 = g["aileron"]["y_frac"]
    for f, ctrl in ((0.0, False), (a0, True), (a1, True), (1.0, False)):
        L.append(wing_sec(f, ctrl))
    if not flying_wing:
        h = g["htail"]
        xh = h["x_le"]
        L += ["SURFACE", "Horizontal tail", f"{R(8)} 1.0 {R(10)} -2.0", "YDUPLICATE", "0.0", "ANGLE", "0.0", ""]
        for y in (0.0, h["b"] / 2):
            L.append(_sec(xh, y, h["z"], h["chord"]) + f"AFILE\n{tail_dat}\n"
                     + f"CONTROL\nelevator 1.0 {1 - h['elevator_chord_frac']:.3f} 0. 1. 0. 1.0\n")
        v = g["vtail"]
        L += ["SURFACE", "Fin", f"{R(8)} 1.0 {R(8)} -2.0", ""]
        for zz in (v["z0"], v["z0"] + v["h"]):
            L.append(_sec(v["x_le"], 0.0, zz, v["chord"]) + f"AFILE\n{tail_dat}\n"
                     + f"CONTROL\nrudder 1.0 {1 - v['rudder_chord_frac']:.3f} 0. 0. 1. 1.0\n")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    # airfoil files next to the .avl
    for d in {foil_dat, tail_dat}:
        src = normalized_dat(d[:-4]).read_text().splitlines()
        # Fortran list-directed read parses a label like "E387" as a number (overflow): use a non-numeric label
        src[0] = f"AIRFOIL_{src[0].strip()}"
        (path.parent / d).write_text("\n".join(src) + "\n")


def write_mass(items, path, rho=1.225, g0=9.80665):
    L = ["# StratoGlide mass file (from wb.csv)", "Lunit = 1.0 m", "Munit = 1.0 kg", "Tunit = 1.0 s",
         f"g   = {g0}", f"rho = {rho}", "#  mass  x  y  z  Ixx Iyy Izz Ixy Ixz Iyz"]
    for r in items:
        L.append(f"{r['mass_kg']:.6f} {r['x']:.5f} {r['y']:.5f} {r['z']:.5f} 0 0 0 0 0 0  ! {r['item']}")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
