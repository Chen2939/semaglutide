"""
Diet-composition sensitivity analysis.

Runs three diet scenarios through the price-rebound model:
  1. baseline_uniform  — current model (uniform EER shock to all food groups)
  2. fatty_food_down   — Meat, Dairy, Fats and oils fall more (Blundell 2017)
  3. cereal_sweets_up  — Cereals and Sweets fall more, Meat falls less (Hironaka 2025)

For each scenario × uptake combination the script:
  • Computes annual food-emission savings (same equilibrium model as baseline)
  • Merges with the pre-computed survivor CO₂ from the Mortality Model
  • Calculates the 10-year food-savings-to-survivor-emissions ratio
  • Flags countries where that ratio < 1 (net positive emissions)

Outputs
-------
  test/diet_sensitivity_results.csv          — full results, one row per country
  test/diet_sensitivity_ratio_comparison.csv — wide table: scenario columns, country rows

Usage
-----
    python -m diet_sensitivity.analysis
"""

import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import load_mortality_emissions, output_path

from .pipeline import compute_food_savings_diet
from .scenarios import SCENARIOS


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_all_scenarios(mort: pd.DataFrame):
    """
    Run every scenario in SCENARIOS and return stacked results.

    Parameters
    ----------
    mort : DataFrame
        Output of load_mortality_emissions() — survivor emissions CSV.

    Returns
    -------
    be_all : DataFrame
        compute_breakeven() output for all scenarios stacked, with
        an extra ``diet_scenario`` column.
    """
    all_be = []

    for diet_s in SCENARIOS:
        print(f"\n  → {diet_s}")
        food_savings, _ = compute_food_savings_diet(diet_s)
        be = compute_breakeven(food_savings, mort)
        be["diet_scenario"] = diet_s
        all_be.append(be)

    return pd.concat(all_be, ignore_index=True)


def build_results_table(be_all: pd.DataFrame, mort: pd.DataFrame) -> pd.DataFrame:
    """Assemble a tidy results table with a net-emissions column."""
    person_years = mort[["ISO", "scenario", "total_person_years_saved"]].copy()

    results = pd.merge(
        be_all[[
            "diet_scenario", "scenario", "ISO", "Country",
            "annual_food_savings_t",
            "total_food_savings_10yr",
            "total_survivor_emissions_10yr",
            "ratio_food_to_mort",
            "breakeven_year",
            "food_dominates_all_years",
        ]],
        person_years,
        on=["ISO", "scenario"],
        how="left",
    )

    # Positive value = food savings exceed survivor emissions (net benefit)
    results["net_10yr_emissions_t"] = (
        results["total_food_savings_10yr"]
        - results["total_survivor_emissions_10yr"]
    )
    # Only flag as positive emissions when food data exists and ratio is
    # genuinely < 1.  A ratio of 0.0 signals missing FAOSTAT coverage, not
    # a real tipping (food savings are 0 due to absent price/supply data).
    results["net_positive_emissions"] = (
        (results["annual_food_savings_t"] > 0)
        & np.isfinite(results["ratio_food_to_mort"])
        & (results["ratio_food_to_mort"] < 1.0)
    )

    return results


# ── Reporting ──────────────────────────────────────────────────────────────────

def print_global_summary(results: pd.DataFrame):
    print("\n" + "=" * 78)
    print("GLOBAL TOTALS BY SCENARIO")
    print("=" * 78)
    print(
        f"\n  {'Diet scenario':<22}  {'Uptake':<12}  "
        f"{'Food sav (Mt/yr)':>16}  {'Surv em 10yr (Mt)':>18}  {'10yr ratio':>10}"
    )
    print("  " + "-" * 82)

    for diet_s in SCENARIOS:
        for uptake_s in ["max_uptake", "mod_uptake"]:
            sub = results[
                (results["diet_scenario"] == diet_s)
                & (results["scenario"] == uptake_s)
            ]
            valid = sub[
                np.isfinite(sub["ratio_food_to_mort"])
                & (sub["annual_food_savings_t"] > 0)
                & (sub["total_survivor_emissions_10yr"] > 0)
            ]
            if valid.empty:
                continue

            total_food = valid["annual_food_savings_t"].sum()
            total_mort = valid["total_survivor_emissions_10yr"].sum()
            ratio_10yr = total_food * 10 / total_mort

            label_u = "Max (95%)" if uptake_s == "max_uptake" else "Mod (50%)"
            print(
                f"  {diet_s:<22}  {label_u:<12}  "
                f"{total_food / 1e6:>16.2f}  {total_mort / 1e6:>18.2f}  "
                f"{ratio_10yr:>10.1f}x"
            )


def print_scenario_change_vs_baseline(results: pd.DataFrame):
    """Show how each sensitivity scenario changes the global food savings vs baseline."""
    print("\n" + "=" * 78)
    print("CHANGE VS BASELINE (max uptake only)")
    print("=" * 78)
    print(
        f"\n  {'Diet scenario':<22}  {'Δ Food sav (Mt/yr)':>20}  "
        f"{'Δ 10yr ratio':>14}  {'Direction'}"
    )
    print("  " + "-" * 70)

    baseline_vals = {}
    for uptake_s in ["max_uptake", "mod_uptake"]:
        sub = results[
            (results["diet_scenario"] == "baseline_uniform")
            & (results["scenario"] == uptake_s)
        ]
        valid = sub[np.isfinite(sub["ratio_food_to_mort"]) & (sub["annual_food_savings_t"] > 0)]
        baseline_vals[uptake_s] = {
            "food": valid["annual_food_savings_t"].sum(),
            "mort": valid["total_survivor_emissions_10yr"].sum(),
        }

    for diet_s in SCENARIOS:
        if diet_s == "baseline_uniform":
            continue
        sub = results[
            (results["diet_scenario"] == diet_s)
            & (results["scenario"] == "max_uptake")
        ]
        valid = sub[np.isfinite(sub["ratio_food_to_mort"]) & (sub["annual_food_savings_t"] > 0)]
        if valid.empty:
            continue
        new_food = valid["annual_food_savings_t"].sum()
        new_mort = valid["total_survivor_emissions_10yr"].sum()
        base = baseline_vals["max_uptake"]

        delta_food = (new_food - base["food"]) / 1e6
        delta_ratio = (new_food * 10 / new_mort) - (base["food"] * 10 / base["mort"])
        direction = "↑ more savings" if delta_food > 0 else "↓ fewer savings"

        print(
            f"  {diet_s:<22}  {delta_food:>+20.2f} Mt  "
            f"{delta_ratio:>+14.1f}x  {direction}"
        )


def print_at_risk_countries(results: pd.DataFrame, ratio_threshold: float = 10.0):
    """
    Print countries with ratio_food_to_mort below the threshold for any scenario.
    Also flags countries that tip into net positive emissions (ratio < 1).
    """
    print("\n" + "=" * 78)
    print(f"COUNTRIES WITH RATIO < {ratio_threshold:.0f}x  (lowest margin, max uptake)")
    print("=" * 78)

    for diet_s in SCENARIOS:
        sub = results[
            (results["diet_scenario"] == diet_s)
            & (results["scenario"] == "max_uptake")
        ].copy()
        valid = sub[
            np.isfinite(sub["ratio_food_to_mort"])
            & (sub["annual_food_savings_t"] > 0)
            & (sub["total_survivor_emissions_10yr"] > 0)
            & (sub["ratio_food_to_mort"] < ratio_threshold)
        ].sort_values("ratio_food_to_mort")

        print(f"\n  ── {diet_s} ──")
        if valid.empty:
            print("    (none below threshold)")
            continue

        print(
            f"  {'Country':<40}  {'Ratio':>8}  "
            f"{'Net 10yr (kt CO2)':>18}  {'Positive emiss?':>16}"
        )
        print("  " + "-" * 88)
        for _, r in valid.iterrows():
            flag = "  *** YES ***" if r["ratio_food_to_mort"] < 1.0 else ""
            print(
                f"  {r['Country']:<40}  {r['ratio_food_to_mort']:>8.1f}x  "
                f"{r['net_10yr_emissions_t'] / 1e3:>18,.0f}  "
                f"{'YES' if r['ratio_food_to_mort'] < 1.0 else 'No':>16}{flag}"
            )

    # Cross-scenario: countries that appear in at-risk list for any sensitivity
    print("\n  ── Cross-scenario: countries newly at risk vs baseline ──")
    baseline_safe = set(
        results[
            (results["diet_scenario"] == "baseline_uniform")
            & (results["scenario"] == "max_uptake")
            & (results["ratio_food_to_mort"] >= ratio_threshold)
        ]["ISO"]
    )
    for diet_s in [s for s in SCENARIOS if s != "baseline_uniform"]:
        newly_at_risk = results[
            (results["diet_scenario"] == diet_s)
            & (results["scenario"] == "max_uptake")
            & (results["ISO"].isin(baseline_safe))
            & np.isfinite(results["ratio_food_to_mort"])
            & (results["ratio_food_to_mort"] < ratio_threshold)
        ].sort_values("ratio_food_to_mort")

        if newly_at_risk.empty:
            print(f"    {diet_s}: no countries newly fall below {ratio_threshold:.0f}x threshold")
        else:
            print(f"    {diet_s}: {len(newly_at_risk)} country/ies newly below {ratio_threshold:.0f}x —")
            for _, r in newly_at_risk.iterrows():
                print(
                    f"      {r['Country']:<40}  ratio = {r['ratio_food_to_mort']:.1f}x"
                )


def validate_calorie_preservation(results: pd.DataFrame):
    """
    Quick sanity-check: for each (diet_scenario, uptake_scenario), print the
    global sum of food savings relative to baseline.  If calorie preservation
    is working correctly, this will differ across scenarios but the underlying
    mortality data should be unchanged.
    """
    print("\n" + "=" * 78)
    print("VALIDATION — food savings by scenario (should differ)")
    print("(Mortality data is unchanged across scenarios by design)")
    print("=" * 78)
    pivot = (
        results[results["scenario"] == "max_uptake"]
        .groupby("diet_scenario")["annual_food_savings_t"]
        .sum()
        .reset_index()
    )
    pivot["Mt_per_yr"] = pivot["annual_food_savings_t"] / 1e6
    print(pivot[["diet_scenario", "Mt_per_yr"]].to_string(index=False))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 78)
    print("DIET-COMPOSITION SENSITIVITY ANALYSIS")
    print("Scenarios:", list(SCENARIOS.keys()))
    print("=" * 78)

    print("\n[1/3] Loading mortality survivor emissions...")
    mort = load_mortality_emissions()

    print("\n[2/3] Running all diet scenarios through price-rebound model...")
    print("      (this runs the full equilibrium solver 3 × — may take ~2 min)")
    be_all = run_all_scenarios(mort)

    print("\n[3/3] Assembling results and generating report...")
    results = build_results_table(be_all, mort)

    # ── Print report ──────────────────────────────────────────────────────
    print_global_summary(results)
    print_scenario_change_vs_baseline(results)
    print_at_risk_countries(results, ratio_threshold=10.0)
    validate_calorie_preservation(results)

    # ── Save outputs ──────────────────────────────────────────────────────
    out_full = output_path("diet_sensitivity_results.csv")
    results.to_csv(str(out_full), index=False)
    print(f"\nFull results → {out_full}")

    # Wide comparison: countries × scenarios for ratio_food_to_mort
    wide = results[results["scenario"] == "max_uptake"].pivot_table(
        index=["ISO", "Country"],
        columns="diet_scenario",
        values="ratio_food_to_mort",
    ).reset_index()
    wide.columns.name = None
    out_wide = output_path("diet_sensitivity_ratio_comparison.csv")
    wide.to_csv(str(out_wide), index=False)
    print(f"Wide ratio comparison → {out_wide}")

    # Highlight positive-emissions countries
    tipped = results[
        results["net_positive_emissions"] == True  # noqa: E712
    ][["diet_scenario", "scenario", "ISO", "Country",
       "ratio_food_to_mort", "net_10yr_emissions_t"]].sort_values(
        ["diet_scenario", "scenario", "ratio_food_to_mort"]
    )
    if tipped.empty:
        print("\nNo countries tip into net positive emissions under any scenario.")
    else:
        out_tipped = output_path("diet_sensitivity_tipped_countries.csv")
        tipped.to_csv(str(out_tipped), index=False)
        print(f"\n*** {len(tipped)} country-scenario rows with POSITIVE net emissions ***")
        print(f"    Saved → {out_tipped}")
        print(tipped.to_string(index=False))


if __name__ == "__main__":
    main()
