"""Merge every phase's latest numbers.json into results/numbers.json, add frozen config inputs (mission.*, bars.*)
as input records, and compute a values-only SHA-256 (sorted key=value lines; provenance fields excluded so a
clean re-run that reproduces every value reproduces the hash)."""
from __future__ import annotations

import hashlib
import json

from .common import RESULTS, latest_phase_file, load_cfg, read_json, sha256_file, write_json, CONFIG

PHASES = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]


def flatten(d, pre):
    out = {}
    for k, v in d.items():
        kk = f"{pre}.{k}"
        if isinstance(v, dict):
            out.update(flatten(v, kk))
        else:
            out[kk] = v
    return out


def values_hash(nums):
    lines = [f"{k}={json.dumps(v['value'], sort_keys=True)}" for k, v in sorted(nums.items())]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def main():
    nums, src = {}, {}
    for ph in PHASES:
        try:
            f = latest_phase_file(ph, "numbers.json")
        except FileNotFoundError:
            continue
        d = read_json(f)
        nums.update(d)
        src[ph] = str(f)
    for name in ("mission", "bars"):
        for k, v in flatten(load_cfg(name), name).items():
            if isinstance(v, (int, float, str, bool)) or v is None or isinstance(v, list):
                nums[k] = {"value": v, "unit": "input", "script": f"config/{name}.yaml",
                           "inputs_sha": sha256_file(CONFIG / f"{name}.yaml")[:16]}
    nums["mission.release_alt_m"] = nums["mission.release.alt_m"]
    nums["bars.validation_re"] = nums.get("bars.airfoil.validation_re", nums.get("bars.validation.re", {"value": [100000, 200000], "unit": "input", "script": "config/bars.yaml"}))
    # derived headline values (computed here, so they carry this script as provenance)
    def drv(key, value, unit, note):
        nums[f"derived.{key}"] = {"value": value, "unit": unit, "script": "src/stratoglide/collect_numbers.py", "note": note}
    cands = {k: nums[k]["value"] for k in ("p2.cd_mape_E387_re100k", "p2.cd_mape_E387_re200k",
                                           "p2.cd_mape_SD7037_re100k", "p2.cd_mape_SD7037_re200k") if k in nums}
    if cands:
        worst = max(cands, key=cands.get)
        drv("cd_mape_re100k_200k_worst", cands[worst], "-", f"worst of E387/SD7037 at Re 100k and 200k: {worst}")
        best = min(cands, key=cands.get)
        drv("cd_mape_re100k_200k_best", cands[best], "-", f"best of E387/SD7037 at Re 100k and 200k: {best}")
    if "p3.mtow_grid_kg" in nums:
        g, o = nums["p3.mtow_grid_kg"]["value"], nums["p3.mtow_opti_kg"]["value"]
        drv("opti_vs_grid_pct", 100 * abs(o / g - 1), "%", "continuous optimum, Opti vs grid")
    out = {"values_sha256": values_hash(nums), "n": len(nums), "sources": src, "numbers": nums}
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_json(RESULTS / "numbers.json", out)
    print("numbers", len(nums), "values_sha256", out["values_sha256"][:16])


if __name__ == "__main__":
    main()
