"""
Reproduce the manuscript sensitivity ratios using the regenerated _cireg
p10/p90 CI files, via the SAME code path the manuscript used
(diet_sensitivity.compute_food_savings_diet — no fix1/fix2 applied there).

Manuscript targets (global max-uptake ratio_food_to_mort):
    P10 = 2.34 , P90 = 10.13 , combined-conservative = 2.71

Global ratio = Σ annual_food_savings_t × 10 / Σ total_survivor_emissions_10yr
over max-uptake countries with positive food savings and positive survivor
emissions (matches diet_sensitivity.sensitivity_overview.summarize_max_uptake).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import load_mortality_emissions
from diet_sensitivity.pipeline import compute_food_savings_diet

FOOD = ROOT / "Food data"
OUT = Path(__file__).resolve().parent / "cireg"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = {"P10": 2.34, "P90": 10.13, "combined_conservative": 2.71}


def global_max_ratio(food_savings, mort):
    be = compute_breakeven(food_savings, mort)  # include_drug=True (manuscript default)
    sub = be[be["scenario"] == "max_uptake"]
    valid = sub[
        np.isfinite(sub["ratio_food_to_mort"])
        & (sub["annual_food_savings_t"] > 0)
        & (sub["total_survivor_emissions_10yr"] > 0)
    ]
    total_food = valid["annual_food_savings_t"].sum()
    total_mort = valid["total_survivor_emissions_10yr"].sum()
    return total_food * 10 / total_mort, len(valid)


def build_meat_p10_on_mean(p10_cireg_name: str) -> Path:
    """Manuscript 'combined conservative' CI: mean CI with Meat swapped to P10."""
    mean_ci = pd.read_csv(FOOD / "carbon_intensity.csv")
    p10 = pd.read_csv(FOOD / p10_cireg_name)
    derived = mean_ci.set_index("ISO").copy()
    derived["Meat"] = p10.set_index("ISO")["Meat"]
    if derived["Meat"].isna().any():
        raise ValueError("Meat P10 missing after alignment")
    out = FOOD / "carbon_intensity_meat_p10_cireg.csv"
    derived.reset_index().to_csv(out, index=False)
    return out


def main():
    mort = load_mortality_emissions()

    print("=" * 78)
    print("REPRODUCTION: manuscript sensitivity ratios with _cireg p10/p90")
    print("=" * 78)

    configs = [
        ("P10", "baseline_uniform", "carbon_intensity_p10_cireg.csv"),
        ("P90", "baseline_uniform", "carbon_intensity_p90_cireg.csv"),
    ]
    results = {}
    for key, diet, ci in configs:
        print(f"\n[{key}] diet={diet}, ci={ci}")
        fs, _ = compute_food_savings_diet(diet_scenario=diet, ci_file=ci)
        ratio, n = global_max_ratio(fs, mort)
        results[key] = (ratio, n)

    # combined conservative: cereal_sweets_up diet + meat-P10-on-mean CI
    meat_file = build_meat_p10_on_mean("carbon_intensity_p10_cireg.csv")
    print(f"\n[combined_conservative] diet=cereal_sweets_up, ci={meat_file.name}")
    fs, _ = compute_food_savings_diet(
        diet_scenario="cereal_sweets_up", ci_file=meat_file.name
    )
    ratio, n = global_max_ratio(fs, mort)
    results["combined_conservative"] = (ratio, n)

    print("\n" + "=" * 78)
    print(f"  {'scenario':<24}{'manuscript':>12}{'reproduced':>12}{'Δ':>10}{'match?':>10}")
    print("  " + "-" * 66)
    rows = []
    for key in ["P10", "P90", "combined_conservative"]:
        got, n = results[key]
        tgt = TARGETS[key]
        d = got - tgt
        match = "YES" if abs(d) <= 0.05 else ("close" if abs(d) <= 0.15 else "NO")
        print(f"  {key:<24}{tgt:>12.2f}{got:>12.2f}{d:>10.2f}{match:>10}")
        rows.append({"scenario": key, "manuscript": tgt, "reproduced": round(got, 4),
                     "delta": round(d, 4), "n_countries": n, "match": match})
    pd.DataFrame(rows).to_csv(OUT / "sensitivity_reproduction.csv", index=False)
    print(f"\nSaved: {OUT / 'sensitivity_reproduction.csv'}")


if __name__ == "__main__":
    main()
