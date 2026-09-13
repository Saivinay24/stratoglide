"""Own vectorised rigid-body 6-DOF (N runs at once): NED flat earth, quaternion attitude, RK4, ISA, steady
altitude-dependent horizontal wind. Aero from aero_tables.coeffs. Motor off throughout (glide release).

State per run: pos NED (3), body velocity wrt ground (3), quaternion body->NED (4), body rates (3).
Aero uses air-relative velocity v_air = v - R^T w_ned(z).
"""
from __future__ import annotations

import numpy as np

from ..atmos import isa
from . import autopilot
from .aero_tables import coeffs

G = 9.80665


def q2R(q):
    w, x, y, z = q.T
    R = np.empty((len(q), 3, 3))
    R[:, 0, 0] = 1 - 2 * (y * y + z * z); R[:, 0, 1] = 2 * (x * y - w * z); R[:, 0, 2] = 2 * (x * z + w * y)
    R[:, 1, 0] = 2 * (x * y + w * z); R[:, 1, 1] = 1 - 2 * (x * x + z * z); R[:, 1, 2] = 2 * (y * z - w * x)
    R[:, 2, 0] = 2 * (x * z - w * y); R[:, 2, 1] = 2 * (y * z + w * x); R[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return R


def euler2q(phi, th, psi):
    cr, sr = np.cos(phi / 2), np.sin(phi / 2)
    cp, sp = np.cos(th / 2), np.sin(th / 2)
    cy, sy = np.cos(psi / 2), np.sin(psi / 2)
    return np.stack([cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                     cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy], axis=1)


def q2euler(q):
    w, x, y, z = q.T
    phi = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    th = np.arcsin(np.clip(2 * (w * y - z * x), -1, 1))
    psi = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return phi, th, psi


class Wind:
    """w_ned(z) = speed(z) * [cos(dir), sin(dir), 0]; speed from the IGRA percentile profile."""

    def __init__(self, zs, speeds, direction):
        self.zs, self.sp, self.dir = np.asarray(zs), np.asarray(speeds), np.asarray(direction)

    def __call__(self, z):
        s = np.array([np.interp(zz, self.zs, row) for zz, row in zip(z, self.sp)]) if self.sp.ndim == 2 else np.interp(z, self.zs, self.sp)
        return np.stack([s * np.cos(self.dir), s * np.sin(self.dir), 0 * s], axis=1)


def aero_state(X, wind):
    pos, v, q, w = X[:, :3], X[:, 3:6], X[:, 6:10], X[:, 10:13]
    R = q2R(q)
    z = -pos[:, 2]
    wn = wind(z)
    va = v - np.einsum("nji,nj->ni", R, wn)
    V = np.linalg.norm(va, axis=1) + 1e-9
    alpha = np.arctan2(va[:, 2], va[:, 0])
    beta = np.arcsin(np.clip(va[:, 1] / V, -1, 1))
    at = isa(z)
    return R, z, va, V, alpha, beta, at, wn


def deriv(X, p, ctl, wind):
    R, z, va, V, alpha, beta, at, _ = aero_state(X, wind)
    v, q, w = X[:, 3:6], X[:, 6:10], X[:, 10:13]
    qd = 0.5 * at["rho"] * V ** 2
    b, c, S = p["b"], p["c"], p["S"]
    ph, qh, rh = w[:, 0] * b / (2 * V), w[:, 1] * c / (2 * V), w[:, 2] * b / (2 * V)
    de, da, dr = ctl
    CX, CY, CZ, Cl, Cm, Cn, *_ = coeffs(p, alpha, beta, ph, qh, rh, de, da, dr, V / at["a"])
    m = p["mass"]
    F = (qd * S)[:, None] * np.stack([CX, CY, CZ], 1)
    g_b = np.einsum("nji,j->ni", R, np.array([0, 0, G]))
    vdot = F / np.broadcast_to(np.asarray(m, float), (len(X),))[:, None] + g_b - np.cross(w, v)
    Mom = (qd * S)[:, None] * np.stack([b * Cl, c * Cm, b * Cn], 1)
    I = np.stack([np.broadcast_to(np.asarray(p[k], float), (len(X),)) for k in ("Ixx", "Iyy", "Izz")], 1)
    wdot = (Mom - np.cross(w, I * w)) / I
    pw, qw, rw = w.T
    Om = np.zeros((len(X), 4, 4))
    Om[:, 0, 1:] = -w; Om[:, 1:, 0] = w
    Om[:, 1, 2], Om[:, 1, 3], Om[:, 2, 1], Om[:, 2, 3], Om[:, 3, 1], Om[:, 3, 2] = rw, -qw, -rw, pw, qw, -pw
    qdot = 0.5 * np.einsum("nij,nj->ni", Om, q)
    pdot = np.einsum("nij,nj->ni", R, v)
    return np.concatenate([pdot, vdot, qdot, wdot], 1), {"F": F, "qd": qd, "V": V, "alpha": alpha, "mach": V / at["a"]}


def run(p, X0, wind, t_end=120.0, dt=0.01, mode="autopilot", record_every=10):
    N = len(X0)
    X = X0.copy()
    ap = autopilot.PullOut(p, N, mode)
    hist = []
    stats = {k: np.full(N, -np.inf) for k in ("mach", "nz", "qd", "eas")}
    stats["nz_min"] = np.full(N, np.inf)
    rec = autopilot.Recovery(p, N)
    e_viol = np.full(N, -np.inf)
    steps = int(round(t_end / dt))
    for k in range(steps):
        t = k * dt
        R, z, va, V, alpha, beta, at, wn = aero_state(X, wind)
        phi, th, psi = q2euler(X[:, 6:10])
        v_ned = np.einsum("nij,nj->ni", R, X[:, 3:6])
        va_ned = v_ned - wn
        gamma = -np.arcsin(np.clip(va_ned[:, 2] / V, -1, 1))
        eas = V * np.sqrt(at["rho"] / 1.225)
        ctl = ap.step(t, eas, gamma, X[:, 10:13], phi, alpha, V, th)
        k1, info = deriv(X, p, ctl, wind)
        k2, _ = deriv(X + 0.5 * dt * k1, p, ctl, wind)
        k3, _ = deriv(X + 0.5 * dt * k2, p, ctl, wind)
        k4, _ = deriv(X + dt * k3, p, ctl, wind)
        Xn = X + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        Xn[:, 6:10] /= np.linalg.norm(Xn[:, 6:10], axis=1, keepdims=True)
        # energy sanity (air frame + wind-shear work): e = V_air^2/2 + g h
        _, zn, van, Vn, *_rest = aero_state(Xn, wind)
        wn_n = _rest[-1]
        de_air = 0.5 * (Vn ** 2 - V ** 2) + G * (zn - z)
        Rn = q2R(Xn[:, 6:10])
        va_ned_n = np.einsum("nij,nj->ni", Rn, Xn[:, 3:6]) - wn_n
        shear = np.einsum("ni,ni->n", 0.5 * (va_ned + va_ned_n), wn_n - wn)
        e_viol = np.maximum(e_viol, (de_air + shear) / dt)
        nz = -info["F"][:, 2] / (np.asarray(p["mass"]) * G)
        stats["mach"] = np.maximum(stats["mach"], info["mach"])
        stats["nz"] = np.maximum(stats["nz"], nz)
        stats["nz_min"] = np.minimum(stats["nz_min"], nz)
        stats["qd"] = np.maximum(stats["qd"], info["qd"])
        stats["eas"] = np.maximum(stats["eas"], eas)
        rec.update(t, dt, gamma, X[:, 10:13], alpha, z)
        if k % record_every == 0:
            hist.append(np.stack([np.full(N, t), z, V, info["mach"], nz, eas, gamma, alpha, th, phi, -X[:, 0] * 0 + X[:, 0], X[:, 1]], 1))
        X = Xn
    return {"stats": stats, "recovered": rec.recovered, "t_rec": rec.t_rec, "z_rec": rec.z_rec,
            "e_viol_max": e_viol, "hist": np.stack(hist, 1), "X": X}
