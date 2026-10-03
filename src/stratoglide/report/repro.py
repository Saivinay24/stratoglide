"""Clean-clone reproducibility: clone HEAD into backups/clean_clone (gitignored), run `make pipeline` there
(tools rebuilt, no cache, every phase), then compare its results/numbers.json values hash with this repo's.
Writes results/repro.json with the per-key differences (if any)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from ..common import RESULTS, ROOT, write_json


def main():
    dst = ROOT / "backups" / "clean_clone"
    if dst.exists():
        shutil.move(str(dst), str(ROOT / "backups" / f"clean_clone_{int(time.time())}"))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(dst)], check=True)
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    t0 = time.time()
    log = open(ROOT / "backups" / "clean_clone.log", "w")
    rc = subprocess.run(["make", "pipeline"], cwd=dst, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    dt = time.time() - t0
    out = {"head": head, "make_rc": rc, "seconds": dt}
    cf = dst / "results" / "numbers.json"
    if rc == 0 and cf.exists():
        a = json.loads(cf.read_text())
        b = json.loads((RESULTS / "numbers.json").read_text())
        diff = [k for k in set(a["numbers"]) | set(b["numbers"])
                if a["numbers"].get(k, {}).get("value") != b["numbers"].get(k, {}).get("value")]
        out.update({"clean_hash": a["values_sha256"], "repo_hash": b["values_sha256"],
                    "match": a["values_sha256"] == b["values_sha256"], "n_diff": len(diff),
                    "diff": {k: [b["numbers"].get(k, {}).get("value"), a["numbers"].get(k, {}).get("value")] for k in sorted(diff)[:200]}})
    else:
        out["match"] = False
    write_json(RESULTS / "repro.json", out)
    print({k: out[k] for k in out if k != "diff"})


if __name__ == "__main__":
    main()
