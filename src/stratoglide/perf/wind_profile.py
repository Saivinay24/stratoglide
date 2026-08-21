"""Wind statistics vs altitude from NOAA IGRA v2 radiosondes, Lucknow/Amausi (INM00042369, WMO 42369).

Raw: data/winds/raw/INM00042369-data.txt.zip (NCEI data-por, sha256 in MANIFEST). Years 2016-2025
(10 complete years). Geopotential height -> geometric altitude. Per 1 km bin 0-30 km: P50, P95 wind speed
(annual and per month) and the vector-mean direction. Fallback if raw is missing: documented parametric
profile tagged ASSUMED.
"""
from __future__ import annotations

import io
import zipfile

import numpy as np

from ..atmos import R0
from ..common import DATA, write_json

RAW = DATA / "winds" / "raw" / "INM00042369-data.txt.zip"
URL = "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/access/data-por/INM00042369-data.txt.zip"
DERIVED = DATA / "winds" / "lucknow_igra_2016_2025.json"
YEARS = (2016, 2025)
BINS = np.arange(0, 31000, 1000.0)


def parse(years=YEARS):
    """Per sounding: wind components interpolated onto BINS inside the sounding's own altitude range."""
    U, V, M = [], [], []
    with zipfile.ZipFile(RAW) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            keep, month, lev = False, 0, []

            def flush():
                if len(lev) >= 4:
                    a = np.array(sorted(lev))
                    z, ws, wd = a[:, 0], a[:, 1], a[:, 2]
                    u = -ws * np.sin(np.radians(wd)); v = -ws * np.cos(np.radians(wd))
                    inside = (BINS >= z[0]) & (BINS <= z[-1])
                    ui = np.where(inside, np.interp(BINS, z, u), np.nan)
                    vi = np.where(inside, np.interp(BINS, z, v), np.nan)
                    U.append(ui); V.append(vi); M.append(month)

            for raw in io.TextIOWrapper(fh, encoding="ascii", errors="replace"):
                if raw.startswith("#"):
                    if keep:
                        flush()
                    yr = int(raw[13:17]); month = int(raw[18:20])
                    keep = years[0] <= yr <= years[1]
                    lev = []
                    continue
                if not keep:
                    continue
                gph, wdir, wspd = int(raw[16:21]), int(raw[40:45]), int(raw[46:51])
                if gph <= -8888 or wspd <= -8888 or wdir <= -8888:
                    continue
                H = float(gph)
                lev.append((H * R0 / (R0 - H), wspd / 10.0, wdir))
            if keep:
                flush()
    return np.array(U), np.array(V), np.array(M)


def build():
    U, V, M = parse()
    W = np.hypot(U, V)
    out = {"source": URL, "station": "INM00042369 LUCKNOW/AMAUSI", "years": list(YEARS), "n_soundings": int(len(M)),
           "method": "per-sounding linear interpolation of u,v onto 1 km geometric grid, no extrapolation",
           "bins_m": BINS.tolist(), "p50": [], "p95": [], "n": [], "dir_mean_from_deg": [], "monthly_p95": {}}
    for j in range(len(BINS)):
        ok = ~np.isnan(W[:, j])
        out["n"].append(int(ok.sum()))
        if ok.sum() < 100:
            out["p50"].append(None); out["p95"].append(None); out["dir_mean_from_deg"].append(None)
            continue
        out["p50"].append(float(np.percentile(W[ok, j], 50)))
        out["p95"].append(float(np.percentile(W[ok, j], 95)))
        out["dir_mean_from_deg"].append(float((np.degrees(np.arctan2(-U[ok, j].mean(), -V[ok, j].mean())) + 360) % 360))
    for mo in range(1, 13):
        vals = []
        for j in range(len(BINS)):
            ok = ~np.isnan(W[:, j]) & (M == mo)
            vals.append(float(np.percentile(W[ok, j], 95)) if ok.sum() >= 20 else None)
        out["monthly_p95"][str(mo)] = vals
    write_json(DERIVED, out)
    return out


def parametric():
    """ASSUMED fallback profile (plan P7): jet core 40 m/s at 12 km, 10 m/s at 20 km, 15 m/s at 25 km."""
    zk = np.array([0, 5, 12, 16, 20, 25, 30]) * 1000.0
    p95 = np.array([10, 20, 40, 20, 10, 15, 20.0])
    return {"bins_m": BINS.tolist(), "p95": np.interp(BINS, zk, p95).tolist(),
            "p50": (0.5 * np.interp(BINS, zk, p95)).tolist(), "source": "ASSUMED parametric"}


def load():
    if DERIVED.exists():
        return __import__("json").loads(DERIVED.read_text())
    if RAW.exists():
        return build()
    return parametric()


def wind_at(z, pct="p95", prof=None):
    prof = prof or load()
    b = np.array(prof["bins_m"])
    v = np.array([np.nan if x is None else x for x in prof[pct]], float)
    ok = ~np.isnan(v)
    return np.interp(z, b[ok], v[ok])


if __name__ == "__main__":
    o = build()
    for zb, a, b, n in zip(o["bins_m"], o["p50"], o["p95"], o["n"]):
        if zb % 2000 == 0:
            print(int(zb), a, b, n)
    print("soundings", o["n_soundings"])
