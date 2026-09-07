"""Implementations of the verify.py checks. Each returns (status, message) or raises Skip."""
from __future__ import annotations

import re

import numpy as np

from .common import CONFIG, RESULTS, ROOT, latest_phase_file, load_cfg, read_json, sha256_file


class Skip(Exception):
    pass


def _bars():
    return load_cfg("bars")


def _pf(ok: bool):
    return "PASS" if ok else "FAIL"


def _phase(phase, name):
    try:
        return latest_phase_file(phase, name)
    except FileNotFoundError:
        raise Skip(f"{phase}/{name} not produced yet")


def _num(key):
    p = RESULTS / "numbers.json"
    if not p.exists():
        raise Skip("results/numbers.json missing")
    d = read_json(p)
    if key not in d:
        raise Skip(f"{key} not in numbers.json")
    return d[key]["value"]


# ---------------------------------------------------------------- 0
def check0():
    log = (ROOT / "HONEST_LOG.md").read_text()
    out, ok = [], True
    for f in ("bars.yaml", "mission.yaml"):
        m = re.search(rf"PREREG {re.escape(f)} sha256=([0-9a-f]{{64}})", log)
        if not m:
            return "FAIL", f"no PREREG line for {f} in HONEST_LOG.md"
        cur = sha256_file(CONFIG / f)
        same = cur == m.group(1)
        ok &= same
        out.append(f"{f} {'match' if same else 'MISMATCH'} ({cur[:12]})")
    return _pf(ok), "; ".join(out)


# ---------------------------------------------------------------- 1
def _need(mod):
    import importlib
    try:
        return importlib.import_module(f"stratoglide.{mod}")
    except ModuleNotFoundError:
        raise Skip(f"stratoglide.{mod} not built yet")


def check1():
    validate = _need("atmos").validate
    tol = _bars()["atmos"]["ref_tol_frac"]
    rows = validate()
    worst = max(max(abs(r["err_T"]), abs(r["err_p"]), abs(r["err_rho"])) for r in rows)
    zs = sorted({int(r["z_m"] / 1000) for r in rows})
    need = {0, 20, 25, 30, 32}
    missing = need - set(zs)
    ok = worst <= tol and not missing
    return _pf(ok), (f"max |err| {worst:.2e} over {len(rows)} tabulated points ({zs[0]}-{zs[-1]} km, incl. "
                     f"0/20/25/30/32 km) vs bar {tol:.0e}" + (f"; missing {missing}" if missing else ""))


# ---------------------------------------------------------------- 2
def check2():
    isa = _need("atmos").isa
    b = _bars()["atmos"]
    mu = isa(20000)["mu"]
    e_mu = abs(mu / b["mu_ref_216_65"] - 1)
    jumps = []
    for zb in (11000.0, 20000.0, 32000.0):
        # geometric altitude of the geopotential layer boundary
        z = zb * 6356766.0 / (6356766.0 - zb)
        lo, hi = isa(np.nextafter(z, 0.0) - 1e-9), isa(z + 1e-9)
        jumps.append(max(abs(hi[k] / lo[k] - 1) for k in ("T", "p", "rho")))
    zz = np.arange(0, 35001, 10.0)
    mono = bool(np.all(np.diff(isa(zz)["rho"]) < 0))
    ok = e_mu <= b["mu_tol_frac"] and max(jumps) < b["continuity_tol"] and mono
    return _pf(ok), (f"mu(216.65 K) err {e_mu:.2e} (bar {b['mu_tol_frac']}); max layer-boundary jump "
                     f"{max(jumps):.1e} (bar {b['continuity_tol']:.0e}); rho monotonic to 35 km {mono}")


# ---------------------------------------------------------------- 3
def check3():
    isa = _need("atmos").isa
    try:
        s = read_json(_phase("p3", "sizing.json"))
    except Skip:
        raise
    tol = _bars()["recompute_tol_frac"]
    z = s["loiter_alt_m"]
    st = isa(z)
    ws = s["wing_loading_npm2"]
    cl = s["cl_loiter"]
    c = s["mac_m"]
    v = np.sqrt(2 * ws / (st["rho"] * cl))
    q = ws / cl
    re_ = st["rho"] * v * c / st["mu"]
    m = v / st["a"]
    errs = {"V": v / s["v_loiter_tas"] - 1, "q": q / s["q_loiter"] - 1, "Re": re_ / s["re_loiter"] - 1,
            "M": m / s["mach_loiter"] - 1}
    worst = max(abs(e) for e in errs.values())
    return _pf(worst <= tol), (f"independent recompute at {z/1000:.0f} km: V {v:.2f} m/s, q {q:.1f} Pa, "
                               f"Re {re_:.0f}, M {m:.3f}; max rel diff {worst:.1e} (bar {tol})")


# ---------------------------------------------------------------- 4
def check4():
    from .airfoil import neuralfoil_runner, xfoil_runner
    dec = _bars()["determinism_decimals"]
    cases = [("E387", 100000.0, 9.0), ("SD7037", 200000.0, 5.0), ("SD7037", 60000.0, 7.0)]
    worst = 0.0
    for f, r, nc in cases:
        for mod in (xfoil_runner, neuralfoil_runner):
            a = mod.polar(f, r, nc)
            b = mod.polar(f, r, nc, nocache=True)
            if a["alpha"] != b["alpha"]:
                return "FAIL", f"{mod.__name__} {f} {r}: alpha sets differ ({len(a['alpha'])} vs {len(b['alpha'])})"
            for k in ("cl", "cd", "cm"):
                worst = max(worst, float(np.max(np.abs(np.round(a[k], dec) - np.round(b[k], dec)))))
    return _pf(worst == 0.0), f"3 XFOIL + 3 NeuralFoil polars re-run uncached; max diff after rounding to {dec} dp = {worst:g}"


# ---------------------------------------------------------------- 5
def check5():
    v = read_json(_phase("p2", "validation.json"))
    b = _bars()["validation"]
    nc = v["design_ncrit"]
    parts, ok = [], True
    for f in b["foils"]:
        for r in b["re"]:
            x = v["results"][f"{f}|{r}|{nc}|xfoil"]
            m, p = x["metrics"], x["pass"]
            ok &= p["all"]
            parts.append(f"{f} {r//1000}k CD {100*m['cd_mape']:.1f}% CLa {100*m['cla_rel_err']:.1f}% "
                         f"CLmax {m['clmax_abs_err']:.3f}{'' if p['all'] else ' (miss)'}")
    return _pf(ok), f"design Ncrit {nc}; " + "; ".join(parts) + f"; bars <=15%, <=10%, <=0.10"


# ---------------------------------------------------------------- 6
def check6():
    v = read_json(_phase("p2", "validation.json"))
    nc = v["design_ncrit"]
    have = all(f"{f}|60000|{nc}|xfoil" in v["results"] for f in ("E387", "SD7037"))
    log = (ROOT / "HONEST_LOG.md").read_text()
    in_log = "60k" in log
    rep = ROOT / "outputs" / "report" / "StratoGlide_Report.html"
    if not rep.exists():
        raise Skip(f"report not built yet (60k in validation.json {have}, HONEST_LOG {in_log})")
    rep_ok = "60k" in rep.read_text()
    rmin = v.get("re_min_validated")
    ok = have and in_log and rmin is not None and rep_ok
    return _pf(ok), (f"60k in validation.json {have}, HONEST_LOG {in_log}, report {rep_ok}; Re_min_validated = {rmin}")


# ---------------------------------------------------------------- 7
def check7():
    from .airfoil.select import score
    s = read_json(_phase("p2", "selection.json"))
    w = load_cfg("design_space")["selection"]["weights"]
    if w != s["weights"]:
        return "FAIL", "weights in selection.json differ from config/design_space.yaml"
    nc = str(s["design_ncrit"])
    sc = score(s["per_ncrit"][nc]["metrics"], w)
    win = max(sc, key=sc.get)
    repro = win == s["winner_design_ncrit"]
    stable = s["winner_stable_across_ncrit"]
    logged = stable or ("flip" in (ROOT / "HONEST_LOG.md").read_text().lower())
    return _pf(repro and logged), (f"recomputed winner {win} == stored {s['winner_design_ncrit']}: {repro}; "
                                   f"stable across Ncrit 7-12: {stable}{'' if stable else ' (flip logged: ' + str(logged) + ')'}; "
                                   f"selected {s['selected']}; Kendall tau top-3 min {min(s['kendall_tau_top3'].values()):.2f}")


# ---------------------------------------------------------------- 8
def check8():
    s = read_json(_phase("p3", "sizing.json"))
    b = _bars()["sizing"]
    import csv
    w = list(csv.DictReader(open(_phase("p3", "weights.csv"))))
    tot = sum(float(r["mass_kg"]) for r in w)
    e_sum = abs(tot / s["mtow_kg"] - 1)
    res = s["mass_loop_residual_frac"]
    wbrows = list(csv.DictReader(open(_phase("p4", "wb.csv")) if _exists("p4", "wb.csv") else open(_phase("p3", "wb.csv"))))
    M = sum(float(r["mass_kg"]) for r in wbrows)
    xcg = sum(float(r["mass_kg"]) * float(r["x_m"]) for r in wbrows) / M
    e_wb = abs(M / s["mtow_kg"] - 1)
    mf = ROOT / "outputs" / "geometry" / "stratoglide.mass"
    if not mf.exists():
        raise Skip(f"AVL .mass not written yet (P4); mass loop residual {res:.1e}, sum(weights) err {e_sum:.1e}")
    rows = []
    for ln in mf.read_text().splitlines():
        t = ln.split("!")[0].split()
        if len(t) >= 4 and not ln.strip().startswith(("#", "L", "M", "T", "g", "r")):
            try:
                rows.append([float(x) for x in t[:4]])
            except ValueError:
                pass
    a = np.array(rows)
    x_mass = float((a[:, 0] * a[:, 1]).sum() / a[:, 0].sum())
    dcg = abs(x_mass - xcg)
    ok = res <= b["mass_loop_tol_frac"] and e_sum <= b["mass_loop_tol_frac"] and e_wb <= b["mass_loop_tol_frac"] and dcg <= b["cg_match_m"]
    return _pf(ok), (f"mass-loop residual {res:.1e}, sum(weights.csv) vs MTOW {e_sum:.1e}, sum(wb.csv) vs MTOW {e_wb:.1e} "
                     f"(bar {b['mass_loop_tol_frac']}); CG wb.csv {xcg:.4f} m vs AVL .mass {x_mass:.4f} m, diff {1000*dcg:.2f} mm (bar 1 mm)")


def _exists(phase, name):
    try:
        latest_phase_file(phase, name)
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------- 9
def check9():
    s = read_json(_phase("p3", "sizing.json"))
    m = load_cfg("mission")
    b = _bars()["sizing"]
    usable_ok = s["E_usable_wh"] >= s["E_required_noheat_wh"]
    mr4 = usable_ok
    mr7 = s["span_m"] <= m["ground"]["span_max_m"]
    mr8 = s["vs_eas_sl"] <= m["handlaunch"]["stall_eas_max_mps"] + 1e-6
    mr9 = s["mr9_strict_met"]
    g, o = s["grid"]["mtow"], s["opti"].get("mtow")
    agree = o is not None and abs(o / g - 1) <= b["opti_vs_grid_tol_frac"]
    ok = mr4 and mr7 and mr8 and mr9 and agree
    return _pf(ok), (f"MR-4 usable {s['E_usable_wh']:.1f} Wh >= need {s['E_required_noheat_wh']:.1f} Wh: {mr4}; MR-7 span "
                     f"{s['span_m']:.3f} m: {mr7}; MR-8 Vs {s['vs_eas_sl']:.2f} m/s EAS: {mr8}; MR-9 Re {s['re_loiter']:.0f} >= "
                     f"Re_min_validated {s['re_min_validated_strict']:.0f}: {mr9} (max reachable {s['grid']['max_re_other_constraints']:.0f}); "
                     f"Opti {o:.3f} vs grid {g:.3f} kg ({100*abs(o/g-1):.2f}%, bar 2%)")


# ---------------------------------------------------------------- 10
def check10():
    s = read_json(_phase("p3", "sizing.json"))
    m = load_cfg("mission")
    derate = s["E_usable_wh"] < s["E_nameplate_wh"]
    heat = s["E_heater_wh"] > 0
    tmin = s["cell_T_min_c"] >= m["thermal"]["cell_min_c"]
    return _pf(derate and heat and tmin), (f"usable {s['E_usable_wh']:.1f} < nameplate {s['E_nameplate_wh']:.1f} Wh: {derate}; "
                                           f"heater energy {s['E_heater_wh']:.3f} Wh > 0: {heat}; cell T min {s['cell_T_min_c']:.1f} C "
                                           f">= {m['thermal']['cell_min_c']} C: {tmin} (no-insulation counterfactual "
                                           f"{s['noinsulation_cell_T_min_c']:.1f} C)")


# ---------------------------------------------------------------- 11
def check11():
    st = read_json(_phase("p4", "stability.json"))
    b = _bars()["stability"]
    lo, hi = b["sm_pct"]
    msgs, ok = [], True
    for k in ("sl", "alt20"):
        c = st["cases"][k]
        d = c["derivs"]
        good = lo <= c["sm_pct"] <= hi and d["Cma"] < 0 and d["Cnb"] > 0 and d["Clb"] < 0
        ok &= good
        msgs.append(f"{k}: SM {c['sm_pct']:.2f}% [{lo}-{hi}], Cma {d['Cma']:.3f}, Cnb {d['Cnb']:.4f}, Clb {d['Clb']:.4f}")
    return _pf(ok), "; ".join(msgs)


# ---------------------------------------------------------------- 12
def check12():
    st = read_json(_phase("p4", "stability.json"))
    b = _bars()["stability"]
    sl, hi = st["cases"]["sl"]["modes"], st["cases"]["alt20"]["modes"]
    res = []

    def add(name, cond, txt):
        res.append((name, bool(cond), txt))
    for tag, md in (("sl", sl), ("alt20", hi)):
        sp = md["short_period"]["avl"]
        add(f"SP zeta {tag}", sp["zeta"] >= b["sp_zeta_min"][tag], f"{sp['zeta']:.3f}>={b['sp_zeta_min'][tag]}")
        dr = md["dutch_roll"]["avl"]
        add(f"DR zeta {tag}", dr["zeta"] >= b["dr_zeta_min"][tag], f"{dr['zeta']:.3f}>={b['dr_zeta_min'][tag]}")
        ph = md["phugoid"]["avl"]
        stable = ph["re"] < 0
        if b["phugoid"][tag] == "stable":
            add(f"phugoid {tag}", stable, f"re {ph['re']:+.4f}")
        else:
            add(f"phugoid {tag}", stable or (ph["t_double_s"] or 0) >= b["phugoid_t2_min_s"],
                f"re {ph['re']:+.4f}" + (f", T2 {ph['t_double_s']:.0f}s" if ph["t_double_s"] else ""))
        spl = md["spiral"]["avl"]
        add(f"spiral {tag}", spl["re"] < 0 or spl["t_double_s"] >= b["spiral_t2_min_s"],
            "stable" if spl["re"] < 0 else f"T2 {spl['t_double_s']:.1f}s")
    rl = sl["roll"]["avl"]["tau_s"]
    add("roll tau sl", rl <= b["roll_tau_max_s"]["sl"], f"{rl:.3f}s<={b['roll_tau_max_s']['sl']}")
    add("SP zeta drops with altitude", hi["short_period"]["avl"]["zeta"] < sl["short_period"]["avl"]["zeta"],
        f"{hi['short_period']['avl']['zeta']:.3f}<{sl['short_period']['avl']['zeta']:.3f}")
    tr = hi["phugoid"]["avl"]["period_s"] / sl["phugoid"]["avl"]["period_s"]
    vr = st["cases"]["alt20"]["V_tas"] / st["cases"]["sl"]["V_tas"]
    add("phugoid T ratio vs V ratio", abs(tr / vr - 1) <= b["phugoid_ratio_tol_frac"], f"{tr:.3f} vs {vr:.3f} ({100*abs(tr/vr-1):.1f}%)")
    ok = all(c for _, c, _ in res)
    return _pf(ok), "; ".join(f"{n} {t}{'' if c else ' FAIL'}" for n, c, t in res)


# ---------------------------------------------------------------- 13
def check13():
    st = read_json(_phase("p4", "stability.json"))
    b = _bars()["stability"]["avl_vs_asb"]
    a = st["asb"]
    if "cla_rel" not in a:
        return "FAIL", f"AeroSandbox cross-check did not run: {a}"
    cv = st["vlm_convergence"]
    ok = a["cla_rel"] <= b["cla_rel"] and a["xnp_frac_mac"] <= b["xnp_frac_mac"]
    return _pf(ok), (f"converged grids: CLa AVL {a['avl_CLa']:.3f} vs ASB {a['CLa']:.3f} ({100*a['cla_rel']:.2f}%, bar "
                     f"{100*b['cla_rel']:.0f}%); Xnp AVL {a['avl_Xnp']:.4f} vs ASB {a['Xnp']:.4f} m "
                     f"({100*a['xnp_frac_mac']:.2f}% MAC, bar {100*b['xnp_frac_mac']:.0f}%); last-step change AVL "
                     f"{100*cv['avl_last_step_xnp_frac_mac']:.2f}% MAC, ASB {100*cv['asb_last_step_xnp_frac_mac']:.2f}% MAC")


def _stub(n):
    def f():
        raise Skip(f"check {n} not implemented yet (phase pending)")
    return f


for _n in range(4, 21):
    globals().setdefault(f"check{_n}", _stub(_n))
