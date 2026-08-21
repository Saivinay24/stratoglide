"""Whole-aircraft drag polar used by sizing (P3), performance (P7) and the release sim (P5).

Wing section drag: smooth fit of XFOIL polars of the selected airfoil at the design Ncrit over the sweep Re
grid (60k-300k), multiplied by the measured knockdown k(Re) (downgrade D2). The fit form is casadi-safe:
  ln cd = c0 + c1 cl + c2 cl^2 + c3 L + c4 cl L + c5 L^2 ,  L = ln(Re / 1e5)
Parasite drag: pod, boom and tails by component build-up (turbulent flat-plate Cf, Raymer form factors) at
the actual Re, plus the excrescence factor. Induced: CL^2 / (pi e AR).
"""
from __future__ import annotations

import numpy as _np

from ..common import latest_phase_file, load_cfg, read_json
from ..airfoil import xfoil_runner
from ..airfoil.validate import _monotonic_branch, drag_k

FIT_RES = [60000, 80000, 100000, 150000, 200000, 300000]


def fit_section_polar(foil: str, ncrit: float, cl_lo=0.15, cl_hi=None, which_k="mean"):
    vjson = read_json(latest_phase_file("p2", "validation.json"))
    X, Y = [], []
    clmax = {}
    for r in FIT_RES:
        p = xfoil_runner.polar(foil, float(r), float(ncrit))
        a, cl, cd = _monotonic_branch(p["alpha"], p["cl"], p["cd"])
        clmax[r] = float(_np.max(p["cl"]))
        hi = cl_hi if cl_hi else 0.92 * clmax[r]
        m = (cl >= cl_lo) & (cl <= hi)
        k = drag_k(r, which_k, vjson)
        L = _np.log(r / 1e5)
        for c, d in zip(cl[m], cd[m]):
            X.append([1, c, c * c, L, c * L, L * L])
            Y.append(_np.log(d * k))
    X, Y = _np.array(X), _np.array(Y)
    coef, *_ = _np.linalg.lstsq(X, Y, rcond=None)
    res = Y - X @ coef
    return {"coef": coef.tolist(), "rms_log": float(_np.sqrt(_np.mean(res ** 2))), "n": len(Y),
            "max_rel_err": float(_np.max(_np.abs(_np.exp(res) - 1))), "clmax_by_re": clmax, "k": which_k}


def section_cd(cl, re_, coef, np=_np):
    L = np.log(re_ / 1e5)
    c0, c1, c2, c3, c4, c5 = coef
    return np.exp(c0 + c1 * cl + c2 * cl ** 2 + c3 * L + c4 * cl * L + c5 * L ** 2)


def cf_turb(re_, np=_np):
    return 0.455 / (np.log10(re_)) ** 2.58


def parasite_cds(v, rho, mu, geo: dict, tail_cd: float, np=_np):
    """Parasite drag area D/q [m^2] of pod, boom and tails (excrescence factor applied by caller)."""
    pod_l, pod_d = geo["pod_l"], geo["pod_d"]
    f = pod_l / pod_d
    re_pod = rho * v * pod_l / mu
    swet_pod = 0.85 * _np.pi * pod_d * pod_l
    ff_pod = 1 + 60 / f ** 3 + f / 400
    d_pod = cf_turb(re_pod, np) * ff_pod * swet_pod
    re_boom = rho * v * geo["boom_l"] / mu
    d_boom = cf_turb(re_boom, np) * 1.1 * _np.pi * geo["boom_d"] * geo["boom_l"]
    d_tail = tail_cd * (geo["S_h"] + geo["S_v"])
    return d_pod + d_boom + d_tail


class AircraftPolar:
    """Callable CD(CL, V, rho, mu) for a given geometry, numpy or casadi."""

    def __init__(self, foil, ncrit, which_k="mean"):
        self.fit = fit_section_polar(foil, ncrit, which_k=which_k)
        sel = read_json(latest_phase_file("p2", "selection.json"))
        tail = sel["tail_selected"]
        # tail section is an XFOIL polar too: D2 knockdown applies (Re 30-50k clamps to the 60k factor)
        self.tail_cd = float(sel["tail_screen"][tail]["mean_cd_abs_alpha_le4"]) * drag_k(40000, which_k)
        cfg = load_cfg("sizing")
        self.exc = cfg["aero"]["excrescence_factor"]

    def cd(self, CL, V, rho, mu, S, AR, e, mac, geo, np=_np):
        re_w = rho * V * mac / mu
        cdw = section_cd(CL, re_w, self.fit["coef"], np)
        cdi = CL ** 2 / (_np.pi * e * AR)
        cdp = self.exc * parasite_cds(V, rho, mu, geo, self.tail_cd, np) / S
        return cdw + cdi + cdp, {"cd_wing_profile": cdw, "cd_induced": cdi, "cd_parasite": cdp, "re_wing": re_w}
