"""Mission-closed sizing model: geometry, weights, energy, constraints as functions of (S, AR, CL_loiter, MTOW).

Written once with an `np` argument so the identical equations run under numpy (vectorised grid sweep with a
fixed-point mass loop) and under aerosandbox.numpy / CasADi (Opti with MTOW as a variable and the mass
closure as an equality constraint). Check 9 requires the two to agree within 2% on MTOW.
"""
from __future__ import annotations

import numpy as _np

from ..atmos import RHO0, isa
from ..common import latest_phase_file, load_cfg, read_json
from ..perf.wind_profile import wind_at
from .aero_model import AircraftPolar

G = 9.80665


class SizingModel:
    def __init__(self, prop_override: dict | None = None, which_k: str | None = None):
        self.m = load_cfg("mission")
        self.c = load_cfg("components")
        self.s = load_cfg("sizing")
        self.ds = load_cfg("design_space")
        sel = read_json(latest_phase_file("p2", "selection.json"))
        val = read_json(latest_phase_file("p2", "validation.json"))
        self.foil = sel["selected"]
        self.ncrit = val["design_ncrit"]
        vsel = read_json(latest_phase_file("p2", "validation_selected.json"))
        self.re_floor = float(vsel["design_floor_final"])
        self.re_min_validated = float(val["re_min_validated"]) if val["re_min_validated"] else float("inf")
        # D4: own measured knockdown if the selected foil is a validation foil, else the two-foil mean (D2)
        if which_k is None:
            which_k = self.foil if self.foil in val["drag_k"][next(iter(val["drag_k"]))]["per_foil"] else "mean"
        self.which_k = which_k
        self.polar = AircraftPolar(self.foil, self.ncrit, which_k)
        from ..airfoil.uiuc_loader import normalized_dat, thickness
        self.tc = thickness(_np.loadtxt(normalized_dat(self.foil), skiprows=1))
        clmax_sec = self.polar.fit["clmax_by_re"][self.s["aero"]["stall_re_for_clmax"]]
        self.clmax3d = self.s["aero"]["clmax_3d_factor"] * clmax_sec
        self.atm = {k: isa(z) for k, z in (("sl", 0.0), ("loiter", self.m["loiter"]["alt_m"]),
                                            ("top", self.m["loiter"]["band_m"][1]), ("rel", self.m["release"]["alt_m"]))}
        self.w95_loiter = float(wind_at(self.m["loiter"]["alt_m"], "p95"))
        self.prop = prop_override or {}
        # descent quadrature nodes (geometric altitude) and their atmosphere
        zg = self.m["recovery_site_elev_m"] + self.m["return"]["chute_deploy_agl_m"]
        n = self.s["descent"]["quad_nodes"]
        self.z_desc = _np.linspace(zg, self.m["loiter"]["alt_m"], n)
        self.z_rel = _np.linspace(self.m["loiter"]["alt_m"], self.m["release"]["alt_m"], n // 2)
        self.atm_desc = isa(self.z_desc)
        self.atm_rel = isa(self.z_rel)
        self.T_asc_mean = float(_np.mean(isa(_np.linspace(self.m["recovery_site_elev_m"], self.m["release"]["alt_m"], 200))["T"]))
        cap = self.c["battery_cell"]["capacity_vs_temp_c"]
        ts = sorted(float(k) for k in cap)
        self.cap_hold = float(_np.interp(self.s["thermal"]["setpoint_c"], ts, [cap[int(t)] if int(t) in cap else cap[t] for t in ts]))

    # ------------------------------------------------------------------ geometry
    def geometry(self, S, AR, np=_np):
        lam = self.ds["sizing"]["taper"]
        b = np.sqrt(S * AR)
        cr = 2 * S / (b * (1 + lam))
        mac = (2 / 3) * cr * (1 + lam + lam ** 2) / (1 + lam)
        lt = self.s["layout"]["tail_arm_over_span"] * b
        Sh = self.ds["sizing"]["tail_VH"] * S * mac / lt
        Sv = self.ds["sizing"]["tail_VV"] * S * b / lt
        pod = self.c["pod"]
        ch = np.sqrt(Sh / self.s["layout"]["htail_AR"])
        cv = Sv / np.sqrt(Sv * self.s["layout"]["vtail_AR"])
        boom_l = lt + 0.25 * cr + 0.75 * np.fmax(ch, cv) - (pod["nose_x_m"] + pod["length_m"] - 0.05)
        return {"b": b, "cr": cr, "ct": lam * cr, "mac": mac, "lt": lt, "S_h": Sh, "S_v": Sv,
                "pod_l": pod["length_m"], "pod_d": pod["diameter_m"], "boom_l": boom_l,
                "boom_d": self.s["layout"]["boom_diameter_m"]}

    def flight(self, S, AR, CL, W, atm, geo, e, np=_np):
        V = np.sqrt(2 * W / (atm["rho"] * S * CL))
        cd, parts = self.polar.cd(CL, V, atm["rho"], atm["mu"], S, AR, e, geo["mac"], geo, np)
        D = 0.5 * atm["rho"] * V ** 2 * S * cd
        return {"V": V, "CD": cd, "D": D, "P": D * V, "re": parts["re_wing"], "LD": CL / cd, **parts}

    def cl_bestld(self, S, AR, V, atm, geo, e, np=_np):
        cd0 = self.polar.cd(0.5, V, atm["rho"], atm["mu"], S, AR, 1e9, geo["mac"], geo, np)[0]
        return np.sqrt(cd0 * _np.pi * e * AR)

    # ------------------------------------------------------------------ spar
    def spar_mass(self, S, AR, W, geo, np=_np):
        cu = self.c["structure"]["carbon_ud"]
        n_ult = self.m["pullout"]["n_limit_g"] * self.m["margins"]["ultimate_factor"]
        L = geo["b"] / 2
        h = 0.85 * self.tc * geo["cr"]
        M_ult = n_ult * W * geo["b"] / (3 * _np.pi)
        M_lim = M_ult / self.m["margins"]["ultimate_factor"]
        A_str = M_ult / (cu["sigma_allow_pa"] * h)
        A_def = M_lim * L / (0.2 * cu["E_pa"] * h ** 2)
        A = np.fmax(np.fmax(A_str, A_def), self.s["structure"]["spar_min_cap_area_m2"])
        return 2 * A * cu["rho_kgm3"] * L * 2 * 0.6 * 1.2, {"A_cap_m2": A, "h_m": h, "M_ult_Nm": M_ult,
                                                          "A_strength": A_str, "A_deflection": A_def}

    # ------------------------------------------------------------------ evaluate
    def evaluate(self, S, AR, CL, mtow, np=_np, n_cells_fixed=None, E_heat_override=None):
        m, c, s = self.m, self.c, self.s
        W = mtow * G
        geo = self.geometry(S, AR, np)
        e = self.prop.get("oswald_e", s["aero"]["oswald_e_initial"])
        lo = self.flight(S, AR, CL, W, self.atm["loiter"], geo, e, np)
        top = self.flight(S, AR, CL, W, self.atm["top"], geo, e, np)
        pi = self.prop
        eta_p = pi.get("eta_prop_loiter", s["propulsion_initial"]["eta_prop"])
        eta_m = pi.get("eta_motor", s["propulsion_initial"]["eta_motor"])
        eta_e = s["propulsion_initial"]["eta_esc"]
        eta_climb = pi.get("eta_prop_climb", eta_p)
        P_loiter_elec = lo["P"] / (eta_p * eta_m * eta_e)
        P_climb_shaft = top["P"] + W * m["loiter"]["climb_rate_mps"] * top["V"] / top["V"]
        P_max_shaft = 1.2 * P_climb_shaft
        # descent / transit times (quadrature over altitude, sink = V CD / CL)
        clbl = self.cl_bestld(S, AR, lo["V"], self.atm["loiter"], geo, e, np)
        cl_d = clbl / self.ds["sizing"]["descent_eas_factor"] ** 2
        t_desc, t_rel = 0.0, 0.0
        for zz, aa, store in ((self.z_desc, self.atm_desc, "d"), (self.z_rel, self.atm_rel, "r")):
            cl_use = cl_d if store == "d" else CL
            acc = 0.0
            for i in range(len(zz) - 1):
                at = {k: aa[k][i] for k in ("rho", "mu")}
                f = self.flight(S, AR, cl_use, W, at, geo, e, np)
                sink = f["V"] * f["CD"] / cl_use
                acc = acc + (zz[i + 1] - zz[i]) / sink
            if store == "d":
                t_desc = acc
            else:
                t_rel = acc
        t_asc = (m["release"]["alt_m"] - m["recovery_site_elev_m"]) / m["thermal"]["ascent_rate_mps"]
        t_loit = m["loiter"]["duration_min"] * 60
        t_flight = t_rel + t_loit + t_desc
        t_tot = t_asc + t_flight
        # battery box and heater (analytic lumped steady losses; transient model checks the final design)
        cell = c["battery_cell"]
        th = s["thermal"]
        ins = c["insulation"]
        E_noheat = (P_loiter_elec * t_loit + m["payload"]["power_w"] * t_loit
                    + m["payload"]["standby_power_w"] * (t_tot - t_loit)
                    + m["avionics"]["power_w"] * t_tot + m["avionics"]["servo_power_w"] * t_flight) / 3600.0
        # iterate cell count <-> heater energy (2 passes is enough: heater is a few % of energy)
        E_req = E_noheat
        for _ in range(3):
            n_cells = E_req / (cell["v_nom"] * cell["ah"] * self.cap_hold * cell["dod_limit"])
            vol = n_cells * th["cell_d_m"] ** 2 * th["cell_h_m"]
            side = vol ** (1 / 3) + 2 * th["box_wall_gap_m"]
            A_in = 6 * 1.15 * side ** 2
            A_out = 6 * 1.15 * (side + 2 * ins["thickness_m"]) ** 2
            A_m = np.sqrt(A_in * A_out)
            R = ins["thickness_m"] / (ins["k_w_mk"] * A_m) + 1 / (th["h_ext_wm2k"] * A_out)
            Tset = th["setpoint_c"] + 273.15
            T_mis = 216.65
            P_h_asc = np.fmax(0.0, (Tset - self.T_asc_mean) / R)
            P_h_mis = np.fmax(0.0, (Tset - T_mis) / R)
            E_heat = (P_h_asc * t_asc + P_h_mis * t_flight) / 3600.0
            E_req = E_noheat + E_heat
        if E_heat_override is not None:
            E_heat = E_heat_override
            E_req = E_noheat + E_heat
        n_cells = E_req / (cell["v_nom"] * cell["ah"] * self.cap_hold * cell["dod_limit"])
        self._last_cont_cells = n_cells
        if n_cells_fixed is not None:
            n_cells = n_cells_fixed
        m_batt = n_cells * cell["mass_kg"] * (1 + s["pack_overhead"])
        m_ins = ins["density_kgm3"] * A_m * ins["thickness_m"]
        tp = s["thermal"]["payload_insulation_m"]
        m_pay_ins = ins["density_kgm3"] * 6 * (0.12 + tp) ** 2 * tp   # 0.12 m payload box
        # masses
        st = c["structure"]
        m_wing_shell = st["wing_shell_kgm2"] * 2.04 * S
        m_spar, spar = self.spar_mass(S, AR, W, geo, np)
        m_tail = st["tail_shell_kgm2"] * 2.04 * (geo["S_h"] + geo["S_v"])
        m_boom = st["boom_kg_per_m"] * geo["boom_l"]
        m_pod = st["pod_shell_kgm2"] * 0.85 * _np.pi * geo["pod_d"] * geo["pod_l"]
        fx = c["fixed"]
        m_avion = sum(v["mass_kg"] for k, v in fx.items() if k != "payload")
        pp = s["propulsion_initial"]
        m_motor = pi.get("motor_mass_kg", pp["motor_kg_per_kw"] * P_max_shaft / 1000 + pp["motor_base_kg"])
        D = pi.get("prop_diameter_m", pp["prop_diameter_m"])
        m_prop = pi.get("prop_mass_kg", c["propeller"]["areal_mass_kg_per_m2_disk"] * _np.pi * D ** 2 / 4 + c["propeller"]["hub_kg"])
        m_wiring = c["wiring_fraction"] * (m_avion + m_motor + m_prop)
        m_struct = m_wing_shell + m_spar + m_tail + m_boom + m_pod
        m_empty = m_struct + m_avion + m_motor + m_prop + m_wiring + m_ins + m_pay_ins
        m_margin = m["margins"]["empty_weight_margin"] * m_empty
        m_sum = m_empty + m_margin + fx["payload"]["mass_kg"] + m_batt
        # constraints g <= 0
        vs_eas = np.sqrt(2 * W / (RHO0 * S * self.clmax3d))
        v_bl_tas = np.sqrt(2 * W / (self.atm["loiter"]["rho"] * S * clbl))
        vs_rel = np.sqrt(2 * W / (self.atm["rel"]["rho"] * S * self.clmax3d))
        cons = {
            "stall_eas": vs_eas - m["handlaunch"]["stall_eas_max_mps"],
            "re_floor": (self.re_floor - lo["re"]) / 1e4,
            "span": geo["b"] - m["ground"]["span_max_m"],
            "wind_penetration": self.ds["sizing"]["wind_penetration_factor"] * self.w95_loiter - v_bl_tas,
            "pullout_alt": vs_rel ** 2 / (2 * G) - self.ds["sizing"]["pullout_alt_budget_m"],
            "loiter_speed_margin": CL - self.clmax3d / s["aero"]["loiter_min_speed_margin"] ** 2,
        }
        if n_cells_fixed is not None:  # usable energy at the thermostat temperature must cover the requirement
            cons["energy"] = (E_req - n_cells * cell["v_nom"] * cell["ah"] * self.cap_hold * cell["dod_limit"]) / 10.0
        return {"m_sum": m_sum, "cons": cons, "geo": geo, "loiter": lo, "top": top,
                "masses": {"wing_shell": m_wing_shell, "wing_spar": m_spar, "tails": m_tail, "boom": m_boom,
                           "pod": m_pod, "avionics_fixed": m_avion, "motor": m_motor, "propeller": m_prop,
                           "wiring": m_wiring, "insulation": m_ins, "payload_insulation": m_pay_ins, "battery": m_batt, "margin": m_margin,
                           "payload": fx["payload"]["mass_kg"]},
                "energy": {"E_req_wh": E_req, "E_noheat_wh": E_noheat, "E_heater_est_wh": E_heat, "n_cells_cont": n_cells,
                           "P_loiter_elec_w": P_loiter_elec, "P_loiter_shaft_w": lo["P"], "P_max_shaft_w": P_max_shaft,
                           "t_ascent_s": t_asc, "t_release_glide_s": t_rel, "t_loiter_s": t_loit, "t_descent_s": t_desc,
                           "R_th_kw": R, "box_area_m2": A_out, "heater_mis_w": P_h_mis},
                "spar": spar, "vs_eas": vs_eas, "v_bestld_tas_loiter": v_bl_tas, "cl_bestld": clbl,
                "cl_descent": cl_d, "e": e}
