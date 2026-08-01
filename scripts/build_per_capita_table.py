"""
Per-patient-year companion to the two emissions waterfalls, across sensitivities.

The waterfalls report absolute Mt. This normalises them by TREATED PATIENT-YEARS,
which is the denominator that answers "what does one patient on treatment buy".

Panel A  one year, NO mortality (all three channels off), 53-country food-data
         sample. Patient-years = the initial patient count, nobody dying.
Panel B  ten-year cumulative, survivorship included, 40-country complete-data
         set. Patient-years = pi_dose-weighted across the ten years.

Each panel's patient-years are recovered from that panel's OWN manufacturing
term, so the denominator always carries the same mortality-channel state as the
numerator it divides. See ``patient_years``.

``population_2022`` is retained as a convenience denominator but NOT divided
through. Per-resident and per-patient-year are different quantities and answer
different questions; an earlier version of this table reported per-resident,
which made max and moderate uptake look far apart (43.8 vs 22.4 kg) purely
because the denominator was the whole population while the treated share
doubled. Per patient-year the two are within 2%. Anyone wanting per-resident can
divide value_Mt by population_2022.

Populations come from UN WPP 2024 (single-age, both sexes) via the already
verified ``consumption_ghg.load_un_population_2022``, so the year convention
(2022, matching the FAOSTAT base year) and the ISO mapping are shared with the
rest of the model rather than reinvented here. Requires UN_WPP_DIR.

This script recomputes the waterfall steps rather than importing them, because
the production builders are hardcoded to the baseline specification and take no
arguments. That duplication is made safe by a bar: for the baseline, EVERY step
of both panels must reproduce the committed waterfall CSVs exactly, or the
script refuses to write.

Writes:
  data_result/per_capita_emissions_savings.csv

Usage:
    UN_WPP_DIR=... python -m scripts.build_per_capita_table
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data_visualization.breakeven_analysis import (  # noqa: E402
    _complete_data_subset,
    compute_breakeven,
)
from data_visualization.consumption_ghg import load_un_population_2022  # noqa: E402
from data_visualization.drug_footprint import (  # noqa: E402
    ANNUAL_DRUG_KG_CO2E_PER_USER,
    build_drug_emissions,
)
from data_visualization.pipeline import (  # noqa: E402
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)
from diet_sensitivity.sensitivity_overview import OVERVIEW_SCENARIOS  # noqa: E402

UPTAKES = ["max_uptake", "mod_uptake"]
HORIZON = 10

# Baseline plus the three sensitivities requested. Pulled from OVERVIEW_SCENARIOS
# so the diet/CI definitions are not restated here; add a spec by naming it.
SPECS = [
    "baseline_mean_ci",
    "baseline_p10_ci",
    "baseline_p90_ci",
    "cereal_sweets_up_p10_ci",
]

# Committed baseline max-uptake waterfalls the recomputation must reproduce.
BAR_A = "data_result/global_emissions_waterfall_1yr.csv"
BAR_B = "data_result/global_emissions_waterfall.csv"


def patient_years(drug_emissions_t: float) -> float:
    """Patient-years behind a panel, recovered from that panel's own drug term.

    Manufacturing is priced at a flat ANNUAL_DRUG_KG_CO2E_PER_USER per treated
    patient-year, so dividing it back out returns the patient-years actually
    charged -- and returns them on the SAME mortality-channel basis the panel
    used, without that basis having to be restated anywhere:

      Panel A  drug_emissions_1yr_t = initial_users x kg
               -> patient-years = the initial patient count, nobody dying,
                  which is what all-channels-off means.
      Panel B  total_drug_emissions_10yr = sum_y initial x pi_dose(y) x kg
               -> patient-years = survival-weighted over the ten years.

    Deriving rather than looking up the treated-user columns means the
    denominator cannot drift from the manufacturing bar it sits next to. The
    equality against those columns is checked as a bar in main().
    """
    return drug_emissions_t / (ANNUAL_DRUG_KG_CO2E_PER_USER / 1000.0)


def panel_a(food, detail, drug, uptake):
    """One year, no mortality. Mirrors generate_waterfall_1yr_figure."""
    fs = food[(food["scenario"] == uptake) & (food["annual_food_savings_t"] > 0)]
    isos = set(fs["ISO"])
    d = detail[(detail["scenario"] == uptake) & (detail["ISO"].isin(isos))]
    naive = (d["expected_demand_reduction"].abs() * d["carbon_intensity_t"]).sum()
    actual = d["carbon_savings_t"].abs().sum()
    dr = drug[(drug["scenario"] == uptake) & (drug["ISO"].isin(isos))]
    manu = dr["drug_emissions_1yr_t"].sum()
    return isos, patient_years(manu), [
        ("naive_reductions", naive),
        ("rebound_effect", naive - actual),
        ("actual_food_savings", actual),
        ("manufacturing", manu),
        ("net_savings", actual - manu),
    ]


def panel_b(detail, be, uptake):
    """Ten-year cumulative with survivorship. Mirrors generate_waterfall_figure."""
    valid = _complete_data_subset(be, scenario=uptake)
    isos = set(valid["ISO"])
    d = detail[(detail["scenario"] == uptake) & (detail["ISO"].isin(isos))]
    naive = sum(
        (d[f"expected_demand_reduction_Y{y}"].abs() * d["carbon_intensity_t"]).sum()
        for y in range(1, HORIZON + 1)
    )
    actual = sum(d[f"carbon_savings_t_Y{y}"].abs().sum() for y in range(1, HORIZON + 1))
    surv = valid["total_survivor_emissions_10yr"].sum()
    drug = valid["total_drug_emissions_10yr"].sum()
    return isos, patient_years(drug), [
        ("naive_reductions", naive),
        ("rebound_effect", naive - actual),
        ("actual_food_savings", actual),
        ("survivorship", surv),
        ("manufacturing", drug),
        ("net_savings", actual - surv - drug),
    ]


def main() -> int:
    print("Loading UN WPP 2022 population...")
    pop = load_un_population_2022().set_index("ISO")["population_2022"]
    cfgs = {c["overview_scenario"]: c for c in OVERVIEW_SCENARIOS}
    drug = build_drug_emissions()
    mort_cache: dict = {}
    rows, py_checks = [], []

    for spec in SPECS:
        cfg = cfgs[spec]
        print(f"  -> {cfg['label']}")
        # Panel A: unweighted, single solve. Panel B: weighted, 10 solves.
        food_u, detail_u = compute_food_savings(
            diet_scenario=cfg["diet_scenario"], ci_file=cfg["ci_file"],
            survival_weighted=False,
        )
        food_w, detail_w = compute_food_savings(
            diet_scenario=cfg["diet_scenario"], ci_file=cfg["ci_file"],
        )
        ci = cfg["ci_scenario"]
        if ci not in mort_cache:
            mort_cache[ci] = load_mortality_emissions(ci)
        be = compute_breakeven(food_w, mort_cache[ci], include_drug=True)

        for uptake in UPTAKES:
            for panel, (isos, pyears, steps) in (
                ("A_1yr_no_mortality", panel_a(food_u, detail_u, drug, uptake)),
                ("B_10yr_with_survivorship", panel_b(detail_w, be, uptake)),
            ):
                missing = sorted(i for i in isos if i not in pop.index)
                if missing:
                    raise ValueError(
                        f"{spec}/{uptake}/{panel}: no UN population for {missing}. "
                        "Refusing to divide by a short denominator."
                    )
                headcount = float(pop.reindex(sorted(isos)).sum())
                # Bar: the derived patient-years must equal the committed
                # treated-user columns for this panel's basis.
                col = ("treated_users_initial" if panel.startswith("A")
                       else "treated_user_years_10yr_approx")
                direct = float(drug[(drug["scenario"] == uptake)
                                    & (drug["ISO"].isin(isos))][col].sum())
                py_checks.append((f"{spec}/{uptake}/{panel[0]}", col,
                                  pyears, direct))
                for step, value_t in steps:
                    rows.append({
                        "panel": panel,
                        "spec": spec,
                        "label": cfg["label"],
                        "uptake": uptake,
                        "step": step,
                        "value_Mt": value_t / 1e6,
                        "n_countries": len(isos),
                        # Retained as a convenience denominator only. This table
                        # reports per PATIENT-YEAR; per-resident is a different
                        # quantity and is deliberately not precomputed here.
                        "population_2022": headcount,
                        "patient_years": pyears,
                        "per_patient_year_kg": value_t * 1000.0 / pyears,
                    })

    df = pd.DataFrame(rows)

    # ---- bar: baseline must reproduce the committed waterfalls exactly ----
    print("\nBAR: baseline max_uptake vs the committed waterfall CSVs")
    fails = []
    for panel, path in (("A_1yr_no_mortality", BAR_A),
                        ("B_10yr_with_survivorship", BAR_B)):
        want = pd.read_csv(_ROOT / path, float_precision="round_trip")
        got = df[(df["panel"] == panel) & (df["spec"] == "baseline_mean_ci")
                 & (df["uptake"] == "max_uptake")]
        merged = want.merge(got, on="step", suffixes=("_want", "_got"))
        if len(merged) != len(want):
            fails.append(f"{panel}: step set differs")
            continue
        for _, r in merged.iterrows():
            ok = r["value_Mt_want"] == r["value_Mt_got"]
            if not ok:
                fails.append(f"{panel}/{r['step']}")
            print(f"  [{'PASS' if ok else 'FAIL'}] {panel:26s} {r['step']:20s} "
                  f"{r['value_Mt_got']!r}")

    worst = max(abs(p - d) / d for _, _, p, d in py_checks)
    ok_py = worst < 1e-9
    print(f"\nBAR: derived patient-years vs the committed treated-user columns "
          f"({len(py_checks)} combinations)")
    print(f"  [{'PASS' if ok_py else 'FAIL'}] worst relative deviation {worst:.3e}")
    if not ok_py:
        for name, col, p, d in py_checks:
            if abs(p - d) / d >= 1e-9:
                print(f"    {name:44s} {col:32s} {p!r} vs {d!r}")
        fails.append("patient_years")

    if fails:
        print("\nBAR FAILED: " + ", ".join(fails))
        print("Nothing written -- the recomputation diverges from production.")
        return 1

    out = output_path("per_capita_emissions_savings.csv")
    df.to_csv(out, index=False)

    print("\nNET savings per patient-year (the headline figures)")
    for panel, basis in (
        ("A_1yr_no_mortality", "patient-years = initial patients, unweighted"),
        ("B_10yr_with_survivorship", "patient-years = pi_dose-weighted over 10y"),
    ):
        print(f"\n  {panel}  ({basis})")
        n = df[(df["panel"] == panel) & (df["step"] == "net_savings")]
        print(f"    {'Specification':<34}{'uptake':<12}{'Mt':>10}"
              f"{'patient-years':>17}{'kg/patient-yr':>15}")
        for _, r in n.iterrows():
            print(f"    {r['label']:<34}{r['uptake']:<12}{r['value_Mt']:>10.2f}"
                  f"{r['patient_years']:>17,.0f}{r['per_patient_year_kg']:>15.2f}")
        print(f"    N = {n['n_countries'].iloc[0]} countries")

    print(f"\nTable -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
