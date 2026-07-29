"""
Sensitivity suite: food:survivor ratios under the carbon-intensity and
combined-conservative specifications, for both uptake levels.

Produces the numbers behind the manuscript's sensitivity table. For each
specification and each uptake level it reports:

  * cumulative 10-year food:survivor ratio (complete-data global)
  * year-10 annual food:survivor ratio -- the annual counterpart to the
    cumulative figure, which is not recoverable from it
  * the minimum-country ratio and which country
  * the count of tipping countries (ratio_food_to_mort < 1)

Specifications:
  P10                   uniform diet, carbon_intensity_p10.csv
  P90                   uniform diet, carbon_intensity_p90.csv
  combined_conservative cereals/sweets diet shift, carbon_intensity_p10.csv

Each specification is scored against the survivor-emissions file built from
its own carbon intensities, so both sides of every ratio share a basis.

``diet_sensitivity.sensitivity_overview`` covers the same specifications for
max uptake only and reports no year-10 annual ratio, so the two scripts
overlap without either subsuming the other. See the README.

Outputs:
  data_result/sensitivity_suite.csv

Usage:
    python -m diet_sensitivity.sensitivity_suite
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import (
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)

from .combined_analysis import assert_combined_conservative

SCENARIOS = ["max_uptake", "mod_uptake"]


def _valid(be: pd.DataFrame, sc: str) -> pd.DataFrame:
    """Complete-data subset: real food savings and real survivor emissions."""
    return be[
        (be["scenario"] == sc)
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be["ratio_food_to_mort"])
    ]


def ratios_for_scenario(be_df: pd.DataFrame, scenario: str) -> dict:
    """All-country cumulative and year-10 annual food:survivor ratios, over the
    complete-data subset (positive food savings, positive survivor emissions)."""
    valid = _valid(be_df, scenario).copy()
    years = np.arange(1, 11)
    cum_food = np.array([valid[f"cum_food_Y{y}"].sum() for y in years], float)
    cum_mort = np.array([valid[f"cum_mort_Y{y}"].sum() for y in years], float)
    annual_food = np.diff(cum_food, prepend=0.0)
    annual_mort = np.diff(cum_mort, prepend=0.0)
    return {
        "n_countries": int(len(valid)),
        "cum_ratio_10yr": cum_food[-1] / cum_mort[-1] if cum_mort[-1] > 0 else np.nan,
        "annual_ratio_y10": (
            annual_food[-1] / annual_mort[-1] if annual_mort[-1] > 0 else np.nan
        ),
    }


def min_and_tipping(be: pd.DataFrame, sc: str):
    """Lowest-margin country and the count of countries below parity."""
    v = _valid(be, sc)
    r = v.loc[v["ratio_food_to_mort"].idxmin()]
    n_tip = int((v["ratio_food_to_mort"] < 1).sum())
    return float(r["ratio_food_to_mort"]), r["ISO"], r["Country"], n_tip, len(v)


def run(diet: str, ci: str | Path, label: str, mort: pd.DataFrame) -> dict:
    """Run one specification and summarise both uptake levels.

    ``mort`` must be the survivor-emissions frame built from the same carbon
    intensities as ``ci``.
    """
    print(f"[{label}] diet={diet}, ci={Path(ci).name}")
    fs, _ = compute_food_savings(diet_scenario=diet, ci_file=str(ci))
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


def build_results(mort: pd.DataFrame | None = None) -> pd.DataFrame:
    """Run every specification and return the tidy suite table.

    Every specification here is a carbon-intensity variant, so each is scored
    against the survivor-emissions file built from its own intensities.
    ``mort`` is ignored and kept only so existing callers do not break.
    """
    configs = [
        ("baseline_uniform", "carbon_intensity_p10.csv", "P10", "p10"),
        ("baseline_uniform", "carbon_intensity_p90.csv", "P90", "p90"),
        (
            "cereal_sweets_up",
            "carbon_intensity_p10.csv",
            "combined_conservative",
            "p10",
        ),
    ]
    assert_combined_conservative(
        configs[2][0], configs[2][1], "sensitivity_suite.py"
    )

    mort_cache: Dict[str, pd.DataFrame] = {}
    res = []
    for diet, ci, label, ci_scenario in configs:
        if ci_scenario not in mort_cache:
            mort_cache[ci_scenario] = load_mortality_emissions(ci_scenario)
        r = run(diet, ci, label, mort_cache[ci_scenario])
        r["ci_scenario"] = ci_scenario
        res.append(r)

    rows = []
    for r in res:
        for sc in SCENARIOS:
            d = r[sc]
            rows.append({
                "scenario_spec": r["label"], "ci_scenario": r["ci_scenario"],
                "uptake": sc,
                "cum_ratio_10yr": d["cum10"], "annual_ratio_y10": d["y10"],
                "min_country_ratio": d["min_ratio"], "min_country_iso": d["min_iso"],
                "min_country_name": d["min_country"],
                "n_tipping_countries": d["n_tip"], "n_complete_countries": d["n_valid"],
            })
    return pd.DataFrame(rows)


def print_table(results: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("SENSITIVITY SUITE")
    print("=" * 100)
    print(f"{'scenario':<22}{'uptake':<10}{'cum 10-yr':>11}{'yr-10 ann':>11}"
          f"{'min ratio':>11}{'min country':>26}{'tipping':>9}{'n':>5}")
    print("-" * 100)
    for _, r in results.iterrows():
        who = f"{r['min_country_iso']} {r['min_country_name']}"[:25]
        print(f"{r['scenario_spec']:<22}{r['uptake']:<10}"
              f"{r['cum_ratio_10yr']:>10.3f}x{r['annual_ratio_y10']:>10.3f}x"
              f"{r['min_country_ratio']:>10.3f}x{who:>26}"
              f"{r['n_tipping_countries']:>9}{r['n_complete_countries']:>5}")


def main(ci_scenario: str = "mean") -> None:
    mort = load_mortality_emissions(ci_scenario)
    results = build_results(mort)
    print_table(results)
    out = output_path("sensitivity_suite.csv")
    results.to_csv(out, index=False)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
