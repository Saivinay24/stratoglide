"""Blade element momentum theory for propellers (Ning-style single-residual solve in inflow angle phi).

Prandtl tip and hub loss. Axial induction a: a/(1+a) = sigma' cn / (4 F sin^2 phi); tangential a': a'/(1-a') =
sigma' ct / (4 F sin phi cos phi), sigma' = B c / (2 pi r). Residual sin(phi)/(1+a) - (V/(Omega r)) cos(phi)/(1-a').
Bracketed root search on (1e-4, pi/2); if no sign change (static or windmilling) the element is solved by
minimising |residual| on a grid (flagged).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from ..atmos import isa


def load_geom(path):
    d = np.loadtxt(path, skiprows=1)
    return {"rR": d[:, 0], "cR": d[:, 1], "beta": d[:, 2]}


def _F(B, r, R, rh, phi):
    s = max(np.sin(phi), 1e-6)
    ft = B / 2 * (R - r) / (r * s)
    fh = B / 2 * (r - rh) / (rh * s)
    return (2 / np.pi) * np.arccos(np.exp(-ft)) * (2 / np.pi) * np.arccos(np.exp(-fh))


def element(sec, B, r, R, rh, c, beta_rad, V, Om, rho, mu, a_snd):
    sig = B * c / (2 * np.pi * r)

    def state(phi):
        W0 = np.hypot(V, Om * r)
        alpha = np.degrees(beta_rad - phi)
        cl, cd = sec(alpha, rho * W0 * c / mu, W0 / a_snd)
        cl, cd = float(np.ravel(cl)[0]), float(np.ravel(cd)[0])
        cn = cl * np.cos(phi) - cd * np.sin(phi)
        ct = cl * np.sin(phi) + cd * np.cos(phi)
        F = max(_F(B, r, R, rh, phi), 1e-4)
        k = sig * cn / (4 * F * np.sin(phi) ** 2)
        kp = sig * ct / (4 * F * np.sin(phi) * np.cos(phi))
        a = k / (1 - k) if k < 0.7 else 0.7 / 0.3 + (k - 0.7) * 10  # cap runaway induction
        ap = kp / (1 + kp)
        res = np.sin(phi) / (1 + a) - V / (Om * r) * np.cos(phi) / (1 - ap)
        return res, a, ap, cl, cd, cn, ct

    lo, hi = 1e-4, np.pi / 2 - 1e-4
    flag = False
    try:
        phi = brentq(lambda p: state(p)[0], lo, hi, xtol=1e-10)
    except ValueError:
        g = np.linspace(lo, hi, 400)
        phi = g[np.argmin([abs(state(p)[0]) for p in g])]
        flag = True
    res, a, ap, cl, cd, cn, ct = state(phi)
    W = V * (1 + a) / np.sin(phi) if V > 0 else Om * r * (1 - ap) / np.cos(phi)
    q = 0.5 * rho * W ** 2
    return {"dT": B * q * c * cn, "dQ": B * q * c * ct * r, "phi": phi, "alpha": np.degrees(beta_rad - phi),
            "re": rho * W * c / mu, "mach": W / a_snd, "cl": cl, "cd": cd, "flag": flag}


def solve(sec, geom, D, B, rpm, V, z=0.0, dbeta=0.0, atm=None, n_el=None):
    st = atm or isa(z)
    rho, mu, a_snd = float(st["rho"]), float(st["mu"]), float(st["a"])
    R = D / 2
    rR = geom["rR"]
    rh = rR[0] * R * 0.9
    rr = rR * R
    cc = geom["cR"] * R
    bb = np.radians(geom["beta"] + dbeta)
    Om = rpm * 2 * np.pi / 60
    els = [element(sec, B, r, R, rh, c, b, V, Om, rho, mu, a_snd) for r, c, b in zip(rr, cc, bb)]
    dT = np.array([e["dT"] for e in els])
    dQ = np.array([e["dQ"] for e in els])
    T = float(np.trapezoid(dT, rr))
    Q = float(np.trapezoid(dQ, rr))
    n = rpm / 60
    P = Q * Om
    CT = T / (rho * n ** 2 * D ** 4)
    CP = P / (rho * n ** 3 * D ** 5)
    J = V / (n * D)
    eta = J * CT / CP if CP > 0 and CT > 0 else 0.0
    i75 = int(np.argmin(abs(rR - 0.75)))
    return {"T": T, "Q": Q, "P": P, "CT": CT, "CP": CP, "J": J, "eta": eta, "re75": els[i75]["re"],
            "mach_tip": float(np.hypot(V, Om * R) / a_snd), "mach75": float(np.hypot(V, Om * 0.75 * R) / a_snd), "flags": int(sum(e["flag"] for e in els)), "rho": rho}


def eta_ideal(CT, J):
    """Momentum-theory (actuator disk) ideal efficiency at the same thrust coefficient and advance ratio."""
    if J <= 0:
        return 0.0
    tc = 8 * CT / (np.pi * J ** 2)
    return 2 / (1 + np.sqrt(1 + tc))
