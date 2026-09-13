"""Blade-section polar for BEMT: NeuralFoil (xlarge) table over (alpha, Re), cached, plus compressibility.

Section: NACA 4412 for both the APC validation props and the design blade (APC 'thin electric' sections are
proprietary; 4412 is the standard stand-in, logged as an assumption). Compressibility: Prandtl-Glauert on CL
(M capped at 0.7 inside the factor) and Korn-equation wave drag cd_w = 20 (M - M_crit)^4 above M_crit with
M_dd = 0.87 - t/c - cl/10 (conventional-section kappa), M_crit = M_dd - (0.1/80)^(1/3).
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from ..common import CACHE

FOIL = "naca4412"
TC = 0.12
ALPHA = np.arange(-20.0, 25.01, 0.5)
LOGRE = np.linspace(np.log10(5e3), np.log10(1.5e6), 24)


def _table(foil=FOIL):
    f = CACHE / f"bemt_polar_{foil}.npz"
    if f.exists():
        d = np.load(f)
        return d["cl"], d["cd"]
    import aerosandbox as asb
    import neuralfoil as nf
    af = asb.Airfoil(foil)
    cl = np.zeros((len(ALPHA), len(LOGRE)))
    cd = np.zeros_like(cl)
    for j, lr in enumerate(LOGRE):
        o = nf.get_aero_from_airfoil(airfoil=af, alpha=ALPHA, Re=10 ** lr, model_size="xlarge")
        cl[:, j] = o["CL"]
        cd[:, j] = o["CD"]
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez(f, cl=cl, cd=cd)
    return cl, cd


class Section:
    def __init__(self, foil=FOIL, tc=None):
        self.foil = foil
        self.tc = tc if tc is not None else TC
        cl, cd = _table(foil)
        self._cl = RegularGridInterpolator((ALPHA, LOGRE), cl, bounds_error=False, fill_value=None)
        self._cd = RegularGridInterpolator((ALPHA, LOGRE), cd, bounds_error=False, fill_value=None)

    def __call__(self, alpha_deg, re_, mach=0.0):
        a = np.clip(alpha_deg, ALPHA[0], ALPHA[-1])
        lr = np.clip(np.log10(np.maximum(re_, 1.0)), LOGRE[0], LOGRE[-1])
        pts = np.stack(np.broadcast_arrays(a, lr), axis=-1)
        cl = self._cl(pts)
        cd = np.maximum(self._cd(pts), 1e-4)
        m = np.minimum(np.asarray(mach, float), 0.7)
        cl = cl / np.sqrt(1 - m ** 2)
        mdd = 0.87 - self.tc - np.abs(cl) / 10
        mcrit = mdd - (0.1 / 80) ** (1 / 3)
        mm = np.asarray(mach, float)
        cd = cd + np.where(mm > mcrit, 20 * (mm - mcrit) ** 4, 0.0)
        return cl, cd
