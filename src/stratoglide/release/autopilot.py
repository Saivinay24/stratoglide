"""Generic pull-out law (nothing mission-specific) and the 'recovered' detector.

Autopilot: controls neutral (trim elevator, zero aileron/rudder) until EAS >= q_arm fraction of stall q (i.e.
EAS >= sqrt(q_arm) * Vs_eas); then pitch-rate command q_cmd = clamp(k_g (gamma_glide - gamma), 0..q_n) where
q_n = g (n_cmd - cos gamma) / V caps the load factor at n_cmd < n_limit; elevator = trim + Kq (q - q_cmd) + Ki * integral(q - q_cmd) with
alpha protection above 0.85 alpha_stall (no nose-up rate command, integrator frozen, nose-down Ka term); wings-level roll hold and yaw damper.
Passive mode: controls held at trim for the whole run (the brown-out safety case).
Recovered (plan definition): |gamma - gamma_glide| < 3 deg, |p,q,r| < 5 deg/s, alpha in the attached range,
held for 10 s, all within 120 s of release.
"""
from __future__ import annotations

import numpy as np

D2R = np.pi / 180
G = 9.80665
# Gains at the reference EAS V_ref = 1.3 Vs; scaled by (V_ref / EAS)^2 (dynamic-pressure scheduling), floor at
# EAS = 0.5 V_ref. Set from target closed-loop time constants at q_ref (pitch rate ~0.1 s, roll ~0.15 s):
# Kq [deg elevator per rad/s] = Iyy / (tau q_ref S c |Cm_de|), Kp likewise with Ixx, b, |Cl_da|.
GAINS = {"q_arm": 0.6, "n_cmd": 3.0, "k_g": 1.0, "Kq": 6.5, "Ki": 5.0, "Kphi": 0.04, "Kp": 0.026, "Kr": 0.044,
         "Ka": 0.5, "de_lim": 20.0, "theta_roll_gate_deg": 60.0}


class PullOut:
    def __init__(self, p, N, mode="autopilot", gains=None):
        self.p, self.N, self.mode = p, N, mode
        self.gn = {**GAINS, **(gains or {})}
        self.armed = np.zeros(N, bool)
        self.integ = np.zeros(N)
        self.t_last = 0.0
        self.gamma_glide = -np.arctan(1 / p["ld_loiter"])

    def step(self, t, eas, gamma, w, phi, alpha, V, theta=None):
        p, gn = self.p, self.gn
        de0 = np.broadcast_to(np.asarray(p["trim_de_deg"], float), (self.N,)).copy()
        if self.mode == "passive":
            return de0, np.zeros(self.N), np.zeros(self.N)
        self.armed |= eas >= np.sqrt(gn["q_arm"]) * p["vs_eas"]
        q_n = G * (gn["n_cmd"] - np.cos(gamma)) / np.maximum(V, 1.0)
        q_cmd = np.clip(gn["k_g"] * (self.gamma_glide - gamma), -0.2, q_n)
        a_lim = 0.85 * np.asarray(p["alpha_stall"])
        prot = alpha > a_lim
        q_cmd = np.where(prot, np.minimum(q_cmd, 0.0), q_cmd)
        dt = max(t - self.t_last, 0.0)
        self.t_last = t
        err = w[:, 1] - q_cmd
        # integrator frozen while alpha protection is active (anti-windup), clamped otherwise
        self.integ = np.where(self.armed & ~prot, np.clip(self.integ + err * dt, -1.0, 1.0), self.integ)
        self.integ = np.where(self.armed, self.integ, 0.0)
        vref = 1.3 * np.asarray(p["vs_eas"], float)
        sch = (vref / np.maximum(eas, 0.5 * vref)) ** 2
        de = de0 + sch * (gn["Kq"] * err + gn["Ki"] * self.integ + gn["Ka"] * np.maximum(alpha - a_lim, 0.0) / D2R)
        # roll-angle hold gated off near vertical (Euler phi ill-defined); rate damping always on
        gate = np.ones(self.N) if theta is None else (np.abs(theta) < gn["theta_roll_gate_deg"] * D2R)
        da = sch * (gn["Kphi"] * gate * phi / D2R + gn["Kp"] * w[:, 0] / D2R)
        dr = -sch * gn["Kr"] * w[:, 2] / D2R  # Cn_dr > 0 in AVL: yaw damper opposes r
        lim = gn["de_lim"]
        de = np.where(self.armed, np.clip(de, -lim, lim), de0)
        da = np.where(self.armed, np.clip(da, -lim, lim), 0.0)
        dr = np.where(self.armed, np.clip(dr, -lim, lim), 0.0)
        return de, da, dr


class Recovery:
    def __init__(self, p, N, gamma_tol=3.0, rate_tol=5.0, hold=10.0, window=120.0):
        self.p = p
        self.gg = -np.arctan(1 / p["ld_loiter"])
        self.gt, self.rt, self.hold, self.win = gamma_tol * D2R, rate_tol * D2R, hold, window
        self.timer = np.zeros(N)
        self.recovered = np.zeros(N, bool)
        self.t_rec = np.full(N, np.nan)
        self.z_rec = np.full(N, np.nan)
        self.t_start = np.full(N, np.nan)
        self.z_start = np.full(N, np.nan)

    def update(self, t, dt, gamma, w, alpha, z):
        ok = ((np.abs(gamma - self.gg) < self.gt) & np.all(np.abs(w) < self.rt, axis=1)
              & (np.abs(alpha) < np.asarray(self.p["alpha_stall"])))
        newly = ok & (self.timer == 0)
        self.t_start = np.where(newly, t, self.t_start)
        self.z_start = np.where(newly, z, self.z_start)
        self.timer = np.where(ok, self.timer + dt, 0.0)
        done = (self.timer >= self.hold) & ~self.recovered & (self.t_start <= self.win)
        self.t_rec = np.where(done, self.t_start, self.t_rec)
        self.z_rec = np.where(done, self.z_start, self.z_rec)
        self.recovered |= done
