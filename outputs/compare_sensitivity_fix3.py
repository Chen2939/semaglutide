"""
Stage 1 sensitivity suite on the POST-FIX-#3 pipeline (fix1+fix2+fix3), numbers
only, no figures.

Runs via the now-ported diet pipeline (compute_food_savings_diet, which mirrors
the main pipeline's fix #1 + fix #3 and reads fix #2 via the canonical CI files):
  P10                   : baseline_uniform diet, carbon_intensity_p10.csv
  P90                   : baseline_uniform diet, carbon_intensity_p90.csv
  combined_conservative : cereal_sweets_up diet, mean CI with Meat swapped to P10

Reports per scenario (max_uptake, mod_uptake): cumulative 10-yr and year-10
annual food:survivor ratios (complete-data global), minimum-country ratio and
which country, and tipping-country count (ratio_food_to_mort < 1, matching
diet_sensitivity.sensitivity_overview).

Outputs -> outputs/fix3/ only. Commits nothing. Regenerates no figures.
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
from outputs.compare_fix1 import ratios_for_scenario

FOOD = ROOT / "Food data"
OUT = ROOT / "outputs" / "fix3"
OUT.mkdir(parents=True, exist_ok=True)
SCENARIOS = ["max_uptake", "mod_uptake"]


def _valid(be, sc):
    return be[
        (be["scenario"] == sc)
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be["ratio_food_to_mort"])
    ]


def min_and_tipping(be, sc):
    v = _valid(be, sc)
    i = v["ratio_food_to_mort"].idxmin()
    r = v.loc[i]
    n_tip = int((v["ratio_food_to_mort"] < 1).sum())
    return float(r["ratio_food_to_mort"]), r["ISO"], r["Country"], n_tip, len(v)


def build_meat_p10_on_mean() -> Path:
    """Combined-conservative CI: canonical mean CI with Meat column set to P10."""
    mean_ci = pd.read_csv(FOOD / "carbon_intensity.csv").set_index("ISO")
    p10 = pd.read_csv(FOOD / "carbon_intensity_p10.csv").set_index("ISO")
    mean_ci["Meat"] = p10["Meat"]
    if mean_ci["Meat"].isna().any():
        raise ValueError("Meat P10 missing after alignment")
    out = OUT / "carbon_intensity_meat_p10_fix3.csv"
    mean_ci.reset_index().to_csv(out, index=False)
    return out


def run(diet, ci, label, mort):
    print(f"[{label}] diet={diet}, ci={Path(ci).name}")
    fs, _ = compute_food_savings_diet(diet_scenario=diet, ci_file=ci)
    be = compute_breakeven(fs, mort, include_drug=True)
    out = {"label": label}
    for sc in SCENARIOS:
        rat = ratios_for_scenario(be, sc)
        mr, mi, mc, ntip, nval = min_and_tipping(be, sc)
        out[sc] = {
            "cum10": rat["cum_ratio_10yr"], "y10": rat["annual_ratio_y10"],
            "min_ratio": mr, "min_iso": mi, "min_country": mc,
            "n_tip": ntip, "n_valid": nval,
        }
    return out


def main():
    mort = load_mortality_emissions()
    meat_p10 = build_meat_p10_on_mean()
    configs = [
        ("baseline_uniform", "carbon_intensity_p10.csv", "P10"),
        ("baseline_uniform", "carbon_intensity_p90.csv", "P90"),
        ("cereal_sweets_up", str(meat_p10), "combined_conservative"),
    ]
    res = [run(d, c, l, mort) for d, c, l in configs]

    print("\n" + "=" * 100)
    print("SENSITIVITY SUITE — POST FIX-#3 (fix1+fix2+fix3), baseline only, no figures")
    print("=" * 100)
    hdr = (f"{'scenario':<22}{'uptake':<10}{'cum 10-yr':>11}{'yr-10 ann':>11}"
           f"{'min ratio':>11}{'min country':>26}{'tipping':>9}{'n':>5}")
    print(hdr); print("-" * 100)
    rows = []
    for r in res:
        for sc in SCENARIOS:
            d = r[sc]
            print(f"{r['label']:<22}{sc:<10}{d['cum10']:>10.3f}x{d['y10']:>10.3f}x"
                  f"{d['min_ratio']:>10.3f}x{(d['min_iso']+' '+str(d['min_country']))[:25]:>26}"
                  f"{d['n_tip']:>9}{d['n_valid']:>5}")
            rows.append({
                "scenario_spec": r["label"], "uptake": sc,
                "cum_ratio_10yr": d["cum10"], "annual_ratio_y10": d["y10"],
                "min_country_ratio": d["min_ratio"], "min_country_iso": d["min_iso"],
                "min_country_name": d["min_country"],
                "n_tipping_countries": d["n_tip"], "n_complete_countries": d["n_valid"],
            })
        print()
    pd.DataFrame(rows).to_csv(OUT / "sensitivity_suite_fix3.csv", index=False)
    print(f"Saved: {OUT / 'sensitivity_suite_fix3.csv'}")
    print(f"Derived CI (scratch): {meat_p10}")


if __name__ == "__main__":
    main()
