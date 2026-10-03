"""Render the engineering report (HTML -> PDF via headless Chrome), README.md and the resume contract from
results/numbers.json. Every number in the text comes from a numbers.json key through the n()/pct() helpers;
lint_report.py checks the rendered text for untraceable numeric tokens and em dashes."""
from __future__ import annotations

import json
import shutil
import subprocess

from jinja2 import Environment, StrictUndefined

from ..common import OUTPUTS, RESULTS, ROOT, latest_phase_file, read_json

REPORT = OUTPUTS / "report"
CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]


class N:
    def __init__(self):
        d = read_json(RESULTS / "numbers.json")
        self.d, self.hash = d["numbers"], d["values_sha256"]

    def v(self, k):
        return self.d[k]["value"]

    def n(self, k, nd=2):
        x = self.v(k)
        if isinstance(x, bool) or isinstance(x, str):
            return str(x)
        return f"{x:,.{nd}f}" if abs(x) >= 1000 else f"{x:.{nd}f}"

    def pct(self, k, nd=1):
        return f"{100 * self.v(k):.{nd}f}"


CSS = """
:root{--ink:#14213d;--mute:#5a6478;--line:#d8dde6;--gold:#b8860b}
body{font-family:-apple-system,Helvetica,Arial,sans-serif;color:var(--ink);max-width:960px;margin:24px auto;padding:0 16px;line-height:1.45;font-size:13.5px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;border-bottom:2px solid var(--gold);padding-bottom:3px;margin-top:28px}
h3{font-size:14.5px;margin:16px 0 6px}table{border-collapse:collapse;width:100%;margin:8px 0 12px;font-size:12.5px}
th,td{border:1px solid var(--line);padding:4px 7px;text-align:left;vertical-align:top}th{background:#f2f4f8}
.fail{color:#b42318;font-weight:600}.pass{color:#067647;font-weight:600}img{max-width:100%;border:1px solid var(--line);margin:6px 0}
.sub{color:var(--mute)}code{background:#f2f4f8;padding:0 3px;border-radius:3px}
@media print{h2{page-break-after:avoid}img,table{page-break-inside:avoid}}
"""

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StratoGlide Report</title><style>{{ css }}</style></head><body>
<h1>StratoGlide</h1>
<p class="sub">Balloon-launched stratospheric ISR glider: mission requirements to a build-ready package. Design complete, build pending; no flight claims.
numbers.json values hash <code>{{ N.hash[:16] }}</code>.</p>

<h2>Executive summary</h2>
<table><tr><th>Quantity</th><th>Value</th><th>Bar / requirement</th><th>Status</th></tr>
<tr><td>MTOW</td><td>{{ N.n('p3.mtow_kg',3) }} kg</td><td>closes the mass loop (check 8)</td><td class="pass">converged</td></tr>
<tr><td>Span / wing area / AR</td><td>{{ N.n('p3.span_m',3) }} m / {{ N.n('p3.S_m2',3) }} m^2 / {{ N.n('p3.AR',1) }}</td><td>span limit {{ N.n('mission.ground.span_max_m',1) }} m (MR-7)</td><td class="pass">met</td></tr>
<tr><td>Hand-launch stall</td><td>{{ N.n('p3.vs_eas_sl',2) }} m/s EAS</td><td>{{ N.n('mission.handlaunch.stall_eas_max_mps',1) }} m/s (MR-8)</td><td class="pass">met (active)</td></tr>
<tr><td>Loiter Re (19 km)</td><td>{{ N.n('p3.re_loiter',0) }}</td><td>validated Re {{ N.n('p2.re_min_validated',0) }} (MR-9 strict)</td><td class="fail">not met; max reachable {{ N.n('p3.max_re_loiter_other_constraints',0) }}</td></tr>
<tr><td>XFOIL vs UIUC CD error, Re 100k to 200k</td><td>worst {{ N.pct('derived.cd_mape_re100k_200k_worst') }}%, best {{ N.pct('derived.cd_mape_re100k_200k_best') }}%</td><td>{{ N.pct('bars.validation.cd_mape_max',0) }}%</td><td class="fail">fail (E387); drag knockdown carried</td></tr>
<tr><td>Loiter endurance at 19 km</td><td>{{ N.n('p7.endurance_min_19km',1) }} min</td><td>{{ N.n('mission.loiter.duration_min',0) }} min (MR-4)</td><td class="pass">met</td></tr>
<tr><td>Static margin SL / 20 km</td><td>{{ N.n('p4.sm_pct_sl',2) }}% / {{ N.n('p4.sm_pct_20km',2) }}% MAC</td><td>{{ '%.0f to %.0f' % (N.v('bars.stability.sm_pct')[0], N.v('bars.stability.sm_pct')[1]) }}% MAC</td><td class="pass">met</td></tr>
<tr><td>Release MC (N = {{ N.n('p5.mc_n',0) }}) autopilot recovery</td><td>{{ N.pct('p5.recovery_rate_autopilot',1) }}%</td><td>{{ N.pct('bars.release.recovery_autopilot',0) }}%</td><td class="pass">met</td></tr>
<tr><td>Passive (controls fixed) recovery</td><td>{{ N.pct('p5.recovery_rate_passive',1) }}%</td><td>{{ N.pct('bars.release.recovery_passive_min',0) }}%</td><td class="fail">fail (phugoid)</td></tr>
<tr><td>Peak Mach P99 / max n</td><td>{{ N.n('p5.mach_p99',3) }} / {{ N.n('p5.nz_max',2) }} g</td><td>{{ N.n('bars.release.mach_p99_max',2) }} / {{ N.n('bars.release.n_max_g',1) }} g</td><td class="pass">met</td></tr>
<tr><td>Altitude lost to recovery P50 / P95</td><td>{{ N.n('p5.alt_loss_p50_m',0) }} / {{ N.n('p5.alt_loss_p95_m',0) }} m</td><td>no pre-registered bar</td><td>reported</td></tr>
<tr><td>Variable pitch gain vs fixed pitch</td><td>{{ N.n('p6.vp_gain_eta_points_max',2) }} eta points (at {{ N.n('p6.vp_gain_eta_points_max_alt_m',0) }} m)</td><td>VP never worse</td><td class="pass">met</td></tr>
<tr><td>BOM (airframe)</td><td>INR {{ N.n('p8.bom_total_inr',0) }}</td><td>all prices ESTIMATE</td><td>reported</td></tr>
</table>

<h2>1. Mission requirements</h2>
<p>Release at {{ N.n('mission.release.alt_m',0) }} m from a balloon, pitch {{ N.n('mission.release.pitch_deg.min',0) }} to {{ N.n('mission.release.pitch_deg.max',0) }} deg; loiter {{ N.n('mission.loiter.duration_min',0) }} min at {{ N.n('mission.loiter.alt_m',0) }} m with a {{ N.n('mission.payload.mass_kg',1) }} kg, {{ N.n('mission.payload.power_w',1) }} W payload kept above {{ N.n('mission.payload.min_temp_c',0) }} C; parachute at {{ N.n('mission.return.chute_deploy_agl_m',0) }} m AGL in P95 winds; span at most {{ N.n('mission.ground.span_max_m',1) }} m; hand-launch stall at most {{ N.n('mission.handlaunch.stall_eas_max_mps',1) }} m/s EAS. Requirements and bars were frozen and hashed before any result (check 0).</p>

<h2>2. Atmosphere and Reynolds map</h2>
<p>ISA-1976 at geometric altitude: rho(20 km) = {{ N.n('p1.rho_20km',5) }} kg/m^3, rho(25 km) = {{ N.n('p1.rho_25km',5) }} kg/m^3. Using geometric altitude as geopotential would give {{ N.n('p1.rho_20km_if_z_used_as_H',5) }} at 20 km. The density ratio sea level to 20 km is {{ N.n('p1.density_ratio_sl_20km',2) }} : 1 (3 to 15 km: {{ N.n('p1.density_ratio_3_15km',2) }} : 1).</p>
<img src="../p1_re_map.png" alt="Reynolds number map">

<h2>3. Airfoil validation (the centrepiece)</h2>
<p>XFOIL 6.99 polars were validated against UIUC LSAT wind-tunnel data before being trusted, with the design Ncrit chosen by a pre-registered rule (Ncrit {{ N.n('p2.design_ncrit',0) }}). CD error at matched CL:</p>
<table><tr><th>Foil</th><th>Re 60k</th><th>Re 100k</th><th>Re 200k</th><th>Re 300k</th></tr>
{% for f in ['E387','SD7037'] %}<tr><td>{{ f }}</td>{% for r in ['60k','100k','200k','300k'] %}<td>{{ N.pct('p2.cd_mape_'+f+'_re'+r) }}% (tunnel scatter {{ N.pct('p2.tunnel_scatter_cd_mape_'+f+'_re'+r) }}%)</td>{% endfor %}</tr>{% endfor %}
</table>
<p><b>Honest negative:</b> the {{ N.pct('bars.validation.cd_mape_max',0) }}% bar fails at Re 100k for both foils and at 200k for E387. Only Re {{ N.n('p2.re_min_validated',0) }} passes. The design therefore carries a measured drag knockdown k(Re) (mean {{ N.n('p2.drag_k_mean_re100k',2) }} at 100k; E387 own {{ N.n('p2.drag_k_max_re100k',2) }}) and a design Re floor of {{ N.n('p2.re_design_floor_final',0) }}.</p>
<img src="../p2_validation.png" alt="XFOIL vs UIUC validation">

<h2>4. Sizing</h2>
<p>Grid sweep and AeroSandbox Opti agree on the continuous optimum within {{ N.n('derived.opti_vs_grid_pct',2) }}%. The integer {{ N.v('p3.pack') }} pack ({{ N.n('p3.n_cells',0) }} cells) is closed by re-optimising the planform with the pack fixed. MTOW {{ N.n('p3.mtow_kg',3) }} kg, wing loading {{ N.n('p3.wing_loading_npm2',1) }} N/m^2, CL at loiter {{ N.n('p3.cl_loiter',3) }}, loiter V {{ N.n('p3.v_loiter_tas',1) }} m/s TAS ({{ N.n('p3.v_loiter_eas',2) }} m/s EAS), L/D {{ N.n('p3.ld_loiter',2) }}. Stall and the Re floor are the active constraints.</p>
<p>Battery: {{ N.n('p3.E_nameplate_wh',1) }} Wh nameplate, {{ N.n('p3.E_usable_wh',1) }} Wh usable after the cold derate. Cells stay at or above {{ N.n('p3.cell_T_min_c',1) }} C (uninsulated counterfactual {{ N.n('p3.noinsulation_cell_T_min_c',1) }} C); payload minimum {{ N.n('p3.payload_T_min_c',1) }} C.</p>
<img src="../p3_constraint.png" alt="constraint diagram"><img src="../p3_thermal.png" alt="battery thermal">

<h2>5. Stability and control: sea level vs 20 km</h2>
<p>AVL at matched CL. The pod is shifted {{ N.n('p4.pod_shift_m',4) }} m to place the CG at {{ N.n('p4.sm_pct_sl',2) }}% MAC static margin. Relative density mu rises from {{ N.n('p4.mu_rel_sl',0) }} to {{ N.n('p4.mu_rel_20km',0) }}, so damping falls with altitude:</p>
<table><tr><th>Mode</th><th>Sea level</th><th>20 km</th></tr>
<tr><td>Short period zeta / wn</td><td>{{ N.n('p4.short_period_zeta_sl',3) }} / {{ N.n('p4.short_period_wn_sl',2) }} rad/s</td><td>{{ N.n('p4.short_period_zeta_20km',3) }} / {{ N.n('p4.short_period_wn_20km',2) }} rad/s</td></tr>
<tr><td>Phugoid zeta / period</td><td>{{ N.n('p4.phugoid_zeta_sl',3) }} / {{ N.n('p4.phugoid_period_s_sl',1) }} s</td><td>{{ N.n('p4.phugoid_zeta_20km',3) }} / {{ N.n('p4.phugoid_period_s_20km',1) }} s</td></tr>
<tr><td>Dutch roll zeta</td><td>{{ N.n('p4.dutch_roll_zeta_sl',3) }}</td><td>{{ N.n('p4.dutch_roll_zeta_20km',3) }}</td></tr>
<tr><td>Roll time constant</td><td>{{ N.n('p4.roll_tau_s_sl',3) }} s</td><td>{{ N.n('p4.roll_tau_s_20km',3) }} s</td></tr></table>
<p>The fin volume was enlarged (P4 Dutch-roll trade) after the 20 km Dutch roll fell below its bar of {{ N.n('bars.stability.dr_zeta_min.alt20',2) }}. <b>Honest negatives:</b> the phugoid period ratio differs from the V_TAS ratio by more than {{ N.pct('bars.stability.phugoid_ratio_tol_frac',0) }}% (check 12); the AeroSandbox VLM cross-check does not grid-converge on this geometry (CL_alpha {{ N.n('p4.asb_CLa',3) }} vs AVL {{ N.n('p4.CLa_20km',3) }}, check 13).</p>

<h2>6. Release and pull-out</h2>
<p>{{ N.n('p5.mc_n',0) }}-run Latin hypercube Monte Carlo from {{ N.n('mission.release.alt_m',0) }} m with the own 6-DOF; JSBSim flies the same law on the nominal case (altitude lost {{ N.n('p5.nominal_alt_lost_jsb_m',1) }} vs {{ N.n('p5.nominal_alt_lost_own_m',1) }} m, peak n {{ N.n('p5.nominal_nz_jsb',3) }} vs {{ N.n('p5.nominal_nz_own',3) }} g). Autopilot recovery {{ N.pct('p5.recovery_rate_autopilot',1) }}%, P99 Mach {{ N.n('p5.mach_p99',3) }}, max n {{ N.n('p5.nz_max',2) }} g, altitude lost P95 {{ N.n('p5.alt_loss_p95_m',0) }} m, time to recover P95 {{ N.n('p5.t_rec_p95_s',1) }} s.</p>
<p>Vertical-dive counterfactual (no pull-out): Mach {{ N.n('p5.vertical_dive_max_mach_clean',3) }}. Flutter screen (2-DOF Theodorsen, screening estimate, not clearance): {{ N.n('p5.v_flutter_eas_min',1) }} m/s EAS vs MC peak {{ N.n('p5.peak_eas_max',1) }} m/s. <b>Honest negative:</b> with controls fixed, passive recovery is {{ N.pct('p5.recovery_rate_passive',1) }}% by the strict definition; the airframe pulls out (max Mach {{ N.n('p5.passive_mach_max',3) }}, max n {{ N.n('p5.passive_nz_max',2) }} g) but the high-altitude phugoid keeps flight path swinging {{ N.n('p5.passive_gamma_swing_last20s_p50_deg',1) }} deg (P50) at the end of the {{ N.n('bars.release.recovered_def.window_s',0) }} s window.</p>
<img src="../p5_release_mc.png" alt="release Monte Carlo">

<h2>7. Propulsion</h2>
<p>Own BEMT. Held-out CT error {{ N.pct('p6.bemt_ct_rel_max_heldout',1) }}% (bar {{ N.pct('bars.prop.ct_rel_max',0) }}%, <span class="fail">fail</span>), eta peak error {{ N.n('p6.bemt_eta_peak_abs_max_heldout',3) }} (bar {{ N.n('bars.prop.eta_peak_abs_max',2) }}, pass). Prop D {{ N.n('p6.prop_diameter_m',2) }} m, P/D {{ N.n('p6.prop_pitch_over_D_A',2) }}, eta {{ N.n('p6.eta_prop_loiter_19km',3) }} at 19 km, blade Re75 {{ N.n('p6.re75_20km',0) }} at 20 km, helical tip Mach {{ N.n('p6.mach_tip_19km',3) }} at 19 km. At constant EAS the required CT/J^2 is the same at every altitude, so variable pitch recovers only {{ N.n('p6.vp_gain_eta_points_max',2) }} points over the same blade at fixed pitch ({{ N.n('p6.vp_gain_vs_B_max',2) }} over a sea-level-optimised blade at {{ N.n('p6.vp_gain_vs_B_max_alt_m',0) }} m).</p>
<img src="../p6_validation.png" alt="BEMT validation"><img src="../p6_eta_vs_alt.png" alt="efficiency vs altitude">

<h2>8. Mission performance</h2>
<p>Endurance at 18 / 19 / 20 km: {{ N.n('p7.endurance_min_18km',1) }} / {{ N.n('p7.endurance_min_19km',1) }} / {{ N.n('p7.endurance_min_20km',1) }} min. Still-air glide range from release to deploy {{ N.n('p7.glide_range_still_km',1) }} km. Return reach from the end of loiter in P95 winds: {{ N.n('p7.footprint_p95_max_reach_km',1) }} km downwind; some crosswind tracks cannot be held through the jet layer.</p>
<img src="../p7_power_curves.png" alt="power curves"><img src="../p7_glide_polar.png" alt="glide polars"><img src="../p7_footprint.png" alt="return footprint">

<h2>9. Build package</h2>
<p>STEP assembly and per-part STL (mesh span and area within {{ N.pct('p8.mesh_area_rel',2) }}% of the design), BOM INR {{ N.n('p8.bom_total_inr',0) }} (all ESTIMATE), ArduPlane starter parameters (AIRSPEED_MIN {{ N.n('p8.airspeed_min_eas',1) }}, CRUISE {{ N.n('p8.airspeed_cruise_eas',1) }}, MAX {{ N.n('p8.airspeed_max_eas',1) }} m/s EAS; names checked against apm.pdef.xml). Airspeed sensor must cover {{ N.n('p8.sensor_required_range_pa',0) }} Pa with {{ N.n('p8.sensor_required_resolution_pa',2) }} Pa resolution.</p>

<h2>10. Flight-test predictions</h2>
<table><tr><th>Card</th><th>Quantity</th><th>Predicted</th><th>Band</th><th>Unit</th></tr>
{% for p in preds %}<tr><td>{{ p.card }}</td><td>{{ p.quantity }}</td><td>{{ N.n(p.numbers_key, 3) }}</td><td>{{ p.lo }} to {{ p.hi }}</td><td>{{ p.unit }}</td></tr>{% endfor %}
</table>

<h2>11. Limitations and honest negatives</h2>
<ul><li>No CFD or tunnel test of the full aircraft; AVL is linear and inviscid and omits the pod; the release post-stall aero is a blended model carried as a Monte Carlo parameter; flutter is a screen; thermal is lumped; vendor data and all BOM prices are ESTIMATE.</li>
<li>Pre-registered bars that fail are reported, not loosened: XFOIL CD error at Re 100k (check 5); MR-9 strict Re (check 9); phugoid period ratio (check 12); AeroSandbox VLM convergence (check 13); passive recovery (check 15); BEMT held-out CT (check 17); glide-range vs mid-altitude L/D (check 19).</li>
<li>Named next step: SU2 transition-RANS check of the E387 at Re 100k with grid convergence.</li></ul>

<h2>12. Reproducibility</h2>
<p><code>make all</code> rebuilds XFOIL and AVL, runs every phase into an isolated run directory, writes results/numbers.json and runs verify.py. Environment pinned by uv.lock (ENV_SNAPSHOT.md). Values hash <code>{{ N.hash }}</code>.</p>
</body></html>
"""

README = r"""# StratoGlide

Balloon-launched stratospheric ISR glider, taken from mission requirements to a build-ready package. **Design complete, build pending; no flight claims.** Every number below is read from `results/numbers.json` (values hash `{{ N.hash[:16] }}`), produced by the scripts in this repo.

## Run

```bash
make all        # tools, every phase P1-P9 into a fresh run directory, numbers.json, report, site, verify.py
make verify     # just the 20 numbered checks
```

## Results

| Quantity | Value | Key |
|---|---|---|
| MTOW | {{ N.n('p3.mtow_kg',3) }} kg | `p3.mtow_kg` |
| Span / area / AR | {{ N.n('p3.span_m',3) }} m / {{ N.n('p3.S_m2',3) }} m^2 / {{ N.n('p3.AR',1) }} | `p3.span_m` |
| XFOIL vs UIUC CD error, Re 100k-200k (worst / best) | {{ N.pct('derived.cd_mape_re100k_200k_worst') }}% / {{ N.pct('derived.cd_mape_re100k_200k_best') }}% | `derived.cd_mape_re100k_200k_worst` |
| Static margin SL / 20 km | {{ N.n('p4.sm_pct_sl',2) }}% / {{ N.n('p4.sm_pct_20km',2) }}% MAC | `p4.sm_pct_sl` |
| Release MC runs / autopilot recovery | {{ N.n('p5.mc_n',0) }} / {{ N.pct('p5.recovery_rate_autopilot',1) }}% | `p5.recovery_rate_autopilot` |
| Peak Mach P99 / altitude lost P95 | {{ N.n('p5.mach_p99',3) }} / {{ N.n('p5.alt_loss_p95_m',0) }} m | `p5.mach_p99` |
| Variable pitch gain (same blade) | {{ N.n('p6.vp_gain_eta_points_max',2) }} eta points | `p6.vp_gain_eta_points_max` |
| Loiter endurance at 19 km | {{ N.n('p7.endurance_min_19km',1) }} min | `p7.endurance_min_19km` |
| BOM (airframe, all ESTIMATE) | INR {{ N.n('p8.bom_total_inr',0) }} | `p8.bom_total_inr` |

![XFOIL vs UIUC](outputs/p2_validation.png)

## What it is not

Not flown, not built, no CFD or tunnel test of the full aircraft. Failed pre-registered bars are listed in `HONEST_LOG.md` and in the report, not loosened.

## Repo map

`config/` frozen requirements and bars, inputs; `src/stratoglide/` atmosphere, airfoil, sizing, stability, release, prop, perf, build, report; `verify.py` 20 checks; `outputs/` figures, geometry, BOM, test cards, report; `site/` static dashboard; `results/numbers.json` every number with provenance.
"""

RESUME = r"""# Resume contract (StratoGlide)

StratoGlide - XFLR5/AVL, XFOIL, JSBSim 6-DOF, BEMT, Python (AeroSandbox, NeuralFoil, CadQuery)

- Designed StratoGlide, a balloon-launched stratospheric ISR glider taken from mission requirements to a build-ready package (build pending), sizing a {{ N.n('p3.mtow_kg',2) }} kg, {{ N.n('p3.span_m',2) }} m span airframe and validating XFOIL low-Re polars against UIUC wind-tunnel data ({{ N.pct('derived.cd_mape_re100k_200k_best',0) }} to {{ N.pct('derived.cd_mape_re100k_200k_worst',0) }}% drag error at Re 100k-200k, carried as a measured knockdown).
- Built a JSBSim 6-DOF cross-checked to an own simulator ({{ N.pct('p5.jsb_vs_own_alt_lost_rel',1) }}% apart); {{ N.n('p5.mc_n',0) }} Monte Carlo releases from {{ N.n('mission.release.alt_m',0) }} m recovered {{ N.pct('p5.recovery_rate_autopilot',0) }}% to trimmed glide, P99 Mach {{ N.n('p5.mach_p99',2) }}, P95 altitude loss {{ N.n('p5.alt_loss_p95_m',0) }} m. Held {{ N.n('p4.sm_pct_sl',1) }}% static margin at sea level and 20 km; BEMT showed variable pitch recovering only {{ N.n('p6.vp_gain_eta_points_max',1) }} efficiency points.

| Number | numbers.json key |
|---|---|
| {{ N.n('p3.mtow_kg',2) }} kg | `p3.mtow_kg` |
| {{ N.n('p3.span_m',2) }} m | `p3.span_m` |
| {{ N.pct('derived.cd_mape_re100k_200k_best',0) }} to {{ N.pct('derived.cd_mape_re100k_200k_worst',0) }}% | `derived.cd_mape_re100k_200k_best`, `derived.cd_mape_re100k_200k_worst` |
| {{ N.n('p5.mc_n',0) }} runs | `p5.mc_n` |
| {{ N.pct('p5.recovery_rate_autopilot',0) }}% | `p5.recovery_rate_autopilot` |
| P99 Mach {{ N.n('p5.mach_p99',2) }} | `p5.mach_p99` |
| {{ N.n('p5.alt_loss_p95_m',0) }} m | `p5.alt_loss_p95_m` |
| {{ N.n('p4.sm_pct_sl',1) }}% | `p4.sm_pct_sl` |
| {{ N.n('p6.vp_gain_eta_points_max',1) }} points | `p6.vp_gain_eta_points_max` |
"""


def fmt_band(x):
    return f"{float(f'{x:.6g}'):.4g}"  # round from the 6-sig-fig value numbers.json stores, never from raw floats


def main():
    Nn = N()
    env = Environment(undefined=StrictUndefined, autoescape=False)
    preds = json.loads((OUTPUTS / "test_cards" / "predictions.json").read_text())
    pr = [{"card": p["card"], "quantity": p["quantity"], "numbers_key": p["numbers_key"], "unit": p["unit"],
           "lo": fmt_band(p["band_lo"]), "hi": fmt_band(p["band_hi"])} for p in preds]
    REPORT.mkdir(parents=True, exist_ok=True)
    html = env.from_string(TEMPLATE).render(N=Nn, css=CSS, preds=pr)
    (REPORT / "StratoGlide_Report.html").write_text(html)
    (ROOT / "README.md").write_text(env.from_string(README).render(N=Nn))
    (OUTPUTS / "RESUME_CONTRACT.md").write_text(env.from_string(RESUME).render(N=Nn))
    pdf = REPORT / "StratoGlide_Report.pdf"
    for c in CHROME:
        exe = shutil.which(c) or (c if c.startswith("/") else None)
        if not exe:
            continue
        try:
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", (REPORT / "StratoGlide_Report.html").as_uri()],
                           check=True, capture_output=True, timeout=180)
            break
        except Exception:
            continue
    print("report", (REPORT / "StratoGlide_Report.html").exists(), "pdf", pdf.exists(), "hash", Nn.hash[:16])


if __name__ == "__main__":
    main()
