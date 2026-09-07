"""Own linear state-space from AVL stability-axis derivatives (independent of AVL's MODE solver).

Longitudinal [u, w, q, theta] and lateral [v, p, r, phi] small-perturbation models (Etkin/Nelson form,
Ixz and w-dot terms neglected, CD_alpha from the induced-drag slope). Used to (a) classify AVL's eigenvalues
into named modes by nearest match, (b) cross-check AVL's eigenvalues.
"""
from __future__ import annotations

import numpy as np

G = 9.80665


def state_space(st, mass, I, S, c, b, rho, V, e, AR):
    Q = 0.5 * rho * V ** 2
    CL, CD = st["CLtot"], st["CDtot"]
    CLa, Cma, Cmq = st["CLa"], st["Cma"], st["Cmq"]
    CDa = 2 * CL * CLa / (np.pi * e * AR)
    m = mass
    Xu = -2 * CD * Q * S / (m * V)
    Xw = (CL - CDa) * Q * S / (m * V)
    Zu = -2 * CL * Q * S / (m * V)
    Zw = -(CLa + CD) * Q * S / (m * V)
    Zq = -st.get("CLq", 0.0) * Q * S * c / (2 * V * m)
    Mw = Cma * Q * S * c / (I["Iyy"] * V)
    Mq = Cmq * Q * S * c ** 2 / (2 * V * I["Iyy"])
    Alon = np.array([[Xu, Xw, 0, -G], [Zu, Zw, V + Zq, 0], [0, Mw, Mq, 0], [0, 0, 1, 0]])
    Yv = st["CYb"] * Q * S / (m * V)
    Yp = st.get("CYp", 0.0) * Q * S * b / (2 * m * V)
    Yr = st.get("CYr", 0.0) * Q * S * b / (2 * m * V)
    Lv = st["Clb"] * Q * S * b / (I["Ixx"] * V)
    Lp = st["Clp"] * Q * S * b ** 2 / (2 * V * I["Ixx"])
    Lr = st["Clr"] * Q * S * b ** 2 / (2 * V * I["Ixx"])
    Nv = st["Cnb"] * Q * S * b / (I["Izz"] * V)
    Np = st["Cnp"] * Q * S * b ** 2 / (2 * V * I["Izz"])
    Nr = st["Cnr"] * Q * S * b ** 2 / (2 * V * I["Izz"])
    Alat = np.array([[Yv, Yp, Yr - V, G], [Lv, Lp, Lr, 0], [Nv, Np, Nr, 0], [0, 1, 0, 0]])
    return Alon, Alat


def describe(lam):
    lam = complex(lam)
    wn = abs(lam)
    out = {"re": lam.real, "im": abs(lam.imag), "wn": wn}
    out["zeta"] = -lam.real / wn if wn > 0 else 0.0
    out["period_s"] = 2 * np.pi / abs(lam.imag) if abs(lam.imag) > 1e-9 else None
    out["t_half_s"] = np.log(2) / -lam.real if lam.real < 0 else None
    out["t_double_s"] = np.log(2) / lam.real if lam.real > 0 else None
    out["tau_s"] = -1 / lam.real if (abs(lam.imag) < 1e-9 and lam.real != 0) else None
    return out


def classify(avl_eigs, Alon, Alat):
    """Name AVL eigenvalues by nearest match to the own longitudinal/lateral eigenvalues."""
    own_lon = np.linalg.eigvals(Alon)
    own_lat = np.linalg.eigvals(Alat)
    names = {}
    lon_c = sorted([l for l in own_lon if l.imag > 1e-9], key=lambda l: -abs(l))  # SP then phugoid
    lat_c = [l for l in own_lat if l.imag > 1e-9]
    lat_r = sorted([l for l in own_lat if abs(l.imag) <= 1e-9], key=lambda l: l.real)  # roll (most neg), spiral
    own = {}
    if len(lon_c) == 2:
        own["short_period"], own["phugoid"] = lon_c
    else:  # overdamped short period: two real roots, phugoid complex
        own["phugoid"] = lon_c[0] if lon_c else None
        own["short_period"] = min(own_lon, key=lambda l: l.real)
    if lat_c:
        own["dutch_roll"] = lat_c[0]
    if len(lat_r) >= 2:
        own["roll"], own["spiral"] = lat_r[0], lat_r[-1]
    avl = [complex(r, i) for r, i in avl_eigs]
    avl_pos = [l for l in avl if l.imag >= 0]
    used = set()
    for k, l0 in own.items():
        if l0 is None:
            continue
        j = min((i for i in range(len(avl_pos)) if i not in used), key=lambda i: abs(avl_pos[i] - l0), default=None)
        if j is not None:
            used.add(j)
            names[k] = {"avl": describe(avl_pos[j]), "own": describe(l0),
                        "rel_diff_wn": abs(abs(avl_pos[j]) - abs(l0)) / max(abs(l0), 1e-9)}
    return names
