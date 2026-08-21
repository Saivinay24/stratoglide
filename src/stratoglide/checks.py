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


def _stub(n):
    def f():
        raise Skip(f"check {n} not implemented yet (phase pending)")
    return f


for _n in range(4, 21):
    globals().setdefault(f"check{_n}", _stub(_n))
