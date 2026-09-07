"""P4 diagnostic: is AeroSandbox VLM non-convergence caused by the tail lying near the wing wake plane?
Re-runs AVL and ASB with the tail at its design height and 0.15 m lower. Writes p4/asb_wake_diag.json."""
import copy

from ..common import latest_phase_file, phase_dir, read_json, write_json
from . import run_stability as rs


def main():
    g0 = read_json(latest_phase_file("p4", "geometry_final.json"))
    s = read_json(latest_phase_file("p3", "sizing.json"))
    items = rs.load_items()
    out = []
    for dz in (0.0, -0.15):
        g = copy.deepcopy(g0)
        g["htail"]["z"] += dz
        r = rs.run_at(g, s, items, 19000.0, s["cl_loiter"], tag="_diag")
        row = {"tail_dz_m": dz, "avl": {"CLa": r["st"]["CLa"], "Xnp": r["st"]["Xnp"]}, "asb": []}
        for sr, cr in ((12, 8), (30, 12), (50, 16)):
            x = rs.asb_crosscheck(g, g["cg"], r["st"]["Alpha"], sr=sr, cr=cr)
            row["asb"].append({"sr": sr, "cr": cr, "CLa": float(x["CLa"]), "Xnp": float(x["Xnp"])})
        out.append(row)
        print(row, flush=True)
    write_json(phase_dir("p4") / "asb_wake_diag.json", {"rows": out, "conclusion_rule":
               "if the dz=-0.15 case converges while dz=0 does not, wake-plane proximity is the cause"})


if __name__ == "__main__":
    main()
