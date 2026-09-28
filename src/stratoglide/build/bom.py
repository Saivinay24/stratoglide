"""Bill of materials: masses from the P3 weight build-up / components catalog, INR unit prices from
config/bom_prices.yaml (all ESTIMATE, not fetched). Writes outputs/BOM.csv and outputs/BOM.md."""
from __future__ import annotations

import csv

from ..common import Numbers, OUTPUTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json


def main():
    pr = load_cfg("bom_prices")
    s = read_json(latest_phase_file("p3", "sizing.json"))
    p6 = read_json(latest_phase_file("p6", "prop.json"))
    comp = load_cfg("components")
    w = {r["group"]: float(r["mass_kg"]) for r in csv.DictReader(open(latest_phase_file("p3", "weights.csv")))}
    fixed = comp["fixed"]
    rows = []
    for k, it in pr["items"].items():
        qty = s["n_cells"] if it.get("qty_from") == "n_cells" else it["qty"]
        if k in w:
            mass = w[k]
        elif k in fixed:
            mass = fixed[k]["mass_kg"]
        elif k == "battery_cell":
            mass = comp["battery_cell"]["mass_kg"] * qty
        else:
            mass = None
        spec = it["spec"] + (f": {p6['motor']['name']}" if k == "motor" else "")
        rows.append({"item": k, "spec": spec, "qty": qty, "mass_kg": None if mass is None else round(mass, 4),
                     "vendor_class": it["vendor_class"], "unit_inr": it["inr"], "total_inr": it["inr"] * qty,
                     "url": "", "retrieved": "", "price_source": "ESTIMATE"})
    total = sum(r["total_inr"] for r in rows)
    sourced = sum(r["total_inr"] for r in rows if r["price_source"] != "ESTIMATE")
    OUTPUTS.mkdir(exist_ok=True)
    with open(OUTPUTS / "BOM.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
        wr.writerow({"item": "TOTAL (airframe, payload excluded)", "total_inr": total, "price_source": f"sourced {sourced} / estimated {total - sourced}"})
    md = ["# StratoGlide bill of materials", "",
          "All prices are ESTIMATE: class unit prices from Indian hobby and composite retail, not fetched from vendor "
          "pages, so no URL or retrieval date is claimed. Masses come from the P3 weight build-up.", "",
          "| Item | Spec | Qty | Mass (kg) | Vendor class | Unit (INR) | Total (INR) | Price |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['item']} | {r['spec']} | {r['qty']} | {'' if r['mass_kg'] is None else r['mass_kg']} | {r['vendor_class']} | "
                  f"{r['unit_inr']} | {r['total_inr']} | {r['price_source']} |")
    md += ["", f"**Total (airframe, payload excluded): INR {total}** (sourced INR {sourced}, estimated INR {total - sourced}, "
           f"sourced share {100 * sourced / total:.0f}%)", "", f"Method: {pr['method']}."]
    (OUTPUTS / "BOM.md").write_text("\n".join(md) + "\n")
    write_json(phase_dir("p8") / "bom.json", {"rows": rows, "total_inr": total, "sourced_inr": sourced})
    n = Numbers("p8", "src/stratoglide/build/bom.py")
    n.add("bom_total_inr", total, "INR"); n.add("bom_sourced_pct", 100 * sourced / total, "%")
    n.add("bom_n_items", len(rows))
    n.save()
    print("BOM total INR", total, "sourced", sourced)


if __name__ == "__main__":
    main()
