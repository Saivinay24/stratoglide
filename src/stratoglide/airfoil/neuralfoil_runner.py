"""NeuralFoil 0.3.3 polars on the same alpha grid as XFOIL (cross-check tool, inherits XFOIL's physics)."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import neuralfoil as nf

from ..common import CACHE, sha256_file
from .uiuc_loader import normalized_dat

VERSION_TAG = "neuralfoil0.3.3-v1"


def polar(foil: str, re_: float, ncrit: float, amin=-4.0, amax=14.0, step=0.25, model="xlarge", nocache=False):
    dat = normalized_dat(foil)
    key = hashlib.sha256(json.dumps([VERSION_TAG, sha256_file(dat), re_, ncrit, amin, amax, step, model]).encode()
                         ).hexdigest()[:20]
    cdir = CACHE / "neuralfoil"
    cdir.mkdir(parents=True, exist_ok=True)
    cf = cdir / f"{foil}_{int(re_)}_{ncrit}_{model}_{key}.json"
    if cf.exists() and not nocache:
        return json.loads(cf.read_text())
    alpha = np.round(np.arange(amin, amax + step / 2, step), 4)
    r = nf.get_aero_from_dat_file(str(dat), alpha=alpha, Re=float(re_), n_crit=float(ncrit), model_size=model)
    out = {"foil": foil, "re": re_, "ncrit": ncrit, "model": model, "alpha": alpha.tolist(),
           "cl": np.asarray(r["CL"]).tolist(), "cd": np.asarray(r["CD"]).tolist(), "cm": np.asarray(r["CM"]).tolist(),
           "confidence": np.asarray(r["analysis_confidence"]).tolist(),
           "xtr_top": np.asarray(r.get("Top_Xtr", np.full_like(alpha, np.nan))).tolist()}
    if not nocache:
        cf.write_text(json.dumps(out))
    return out
