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


def _stub(n):
    def f():
        raise Skip(f"check {n} not implemented yet (phase pending)")
    return f


for _n in range(4, 21):
    globals().setdefault(f"check{_n}", _stub(_n))
