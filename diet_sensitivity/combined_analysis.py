"""
Combined conservative sensitivity analysis.

This stacks two conservative assumptions reviewers may ask about:

1. Diet composition shifts toward cereals/sweets while meat decreases less
   (``cereal_sweets_up``).
2. Meat carbon intensity is set to the P10 value, while all other food groups
   keep the central/mean carbon intensity.

Outputs:
  data_result/combined_sensitivity_results.csv
  data_result/combined_sensitivity_ratio_comparison.csv
  data_result/carbon_intensity_meat_p10.csv
  figures/combined_sensitivity_lowest_ratio_countries.png

Usage:
    python -m diet_sensitivity.combined_analysis
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import ROOT, load_mortality_emissions, output_path

from .pipeline import compute_food_savings_diet


COMBINED_SCENARIOS = [
    {
        "combined_scenario": "baseline_uniform_mean_ci",
        "label": "Uniform baseline",
        "diet_scenario": "baseline_uniform",
        "ci_file": "carbon_intensity.csv",
    },
    {
        "combined_scenario": "cereal_sweets_up_mean_ci",
        "label": "Cereals/sweets shift",
        "diet_scenario": "cereal_sweets_up",
        "ci_file": "carbon_intensity.csv",
    },
    {
        "combined_scenario": "cereal_sweets_up_meat_p10_ci",
        "label": "Cereals/sweets + low-meat CI",
        "diet_scenario": "cereal_sweets_up",
        "ci_file": None,  # Filled in after derived CI file is created.
    },
]

SCENARIO_COLORS = {
    "baseline_uniform_mean_ci": "#4c78a8",
    "cereal_sweets_up_mean_ci": "#d62728",
    "cereal_sweets_up_meat_p10_ci": "#7f3c8d",
}


def build_meat_p10_ci_file() -> Path:
    """Create a derived carbon-intensity file with only Meat set to P10."""
    mean_ci = pd.read_csv(ROOT / "Food data" / "carbon_intensity.csv")
    p10_ci = pd.read_csv(ROOT / "Food data" / "carbon_intensity_p10.csv")

    derived = mean_ci.copy()
    derived["Meat"] = p10_ci["Meat"]

    out = output_path("carbon_intensity_meat_p10.csv")
    derived.to_csv(out, index=False)
    return out


def run_combined_scenarios(mort: pd.DataFrame) -> pd.DataFrame:
    """Run each combined sensitivity scenario and return stacked results."""
    meat_p10_file = build_meat_p10_ci_file()
    all_results = []

    for config in COMBINED_SCENARIOS:
        ci_file = config["ci_file"] or meat_p10_file
        print(f"\n  -> {config['combined_scenario']}")
        print(f"     diet={config['diet_scenario']}, ci={ci_file}")

        food_savings, _ = compute_food_savings_diet(
            diet_scenario=config["diet_scenario"],
            ci_file=str(ci_file),
        )
        be = compute_breakeven(food_savings, mort)
        be["combined_scenario"] = config["combined_scenario"]
        be["combined_label"] = config["label"]
        be["diet_scenario"] = config["diet_scenario"]
        be["ci_assumption"] = (
            "meat_p10_other_mean"
            if config["combined_scenario"] == "cereal_sweets_up_meat_p10_ci"
            else "mean"
        )
        all_results.append(be)

    return pd.concat(all_results, ignore_index=True)


def build_results_table(be_all: pd.DataFrame, mort: pd.DataFrame) -> pd.DataFrame:
    """Add person-years, net emissions, and tipping flags."""
    person_years = mort[["ISO", "scenario", "total_person_years_saved"]]
    results = pd.merge(
        be_all,
        person_years,
        on=["ISO", "scenario"],
        how="left",
    )
    results["net_10yr_emissions_t"] = (
        results["total_food_savings_10yr"]
        - results["total_survivor_emissions_10yr"]
    )
    results["net_positive_emissions"] = (
        (results["annual_food_savings_t"] > 0)
        & np.isfinite(results["ratio_food_to_mort"])
        & (results["ratio_food_to_mort"] < 1.0)
    )
    return results


def print_summary(results: pd.DataFrame) -> None:
    """Print global and lowest-margin summaries for max uptake."""
    print("\n" + "=" * 88)
    print("COMBINED SENSITIVITY SUMMARY (max uptake)")
    print("=" * 88)
    print(
        f"\n  {'Scenario':<34}  {'Food sav (Mt/yr)':>16}  "
        f"{'Surv em 10yr (Mt)':>18}  {'10yr ratio':>10}  {'Min country':>18}"
    )
    print("  " + "-" * 104)

    for config in COMBINED_SCENARIOS:
        sub = results[
            (results["combined_scenario"] == config["combined_scenario"])
            & (results["scenario"] == "max_uptake")
        ]
        valid = sub[
            np.isfinite(sub["ratio_food_to_mort"])
            & (sub["annual_food_savings_t"] > 0)
            & (sub["total_survivor_emissions_10yr"] > 0)
        ]
        total_food = valid["annual_food_savings_t"].sum()
        total_mort = valid["total_survivor_emissions_10yr"].sum()
        ratio = total_food * 10 / total_mort
        min_row = valid.loc[valid["ratio_food_to_mort"].idxmin()]
        print(
            f"  {config['label']:<34}  {total_food / 1e6:>16.2f}  "
            f"{total_mort / 1e6:>18.2f}  {ratio:>10.2f}x  "
            f"{min_row['Country']:>18s} ({min_row['ratio_food_to_mort']:.2f}x)"
        )

    tipped = results[
        (results["scenario"] == "max_uptake")
        & (results["net_positive_emissions"])
    ]
    if tipped.empty:
        print("\nNo complete-data country tips into net positive emissions.")
    else:
        print("\nCountries tipping into net positive emissions:")
        print(
            tipped[
                [
                    "combined_label",
                    "Country",
                    "ratio_food_to_mort",
                    "net_10yr_emissions_t",
                ]
            ].to_string(index=False)
        )


def save_outputs(results: pd.DataFrame) -> tuple[Path, Path]:
    """Save full and wide result tables."""
    out_full = output_path("combined_sensitivity_results.csv")
    results.to_csv(out_full, index=False)

    wide = (
        results[results["scenario"] == "max_uptake"]
        .pivot_table(
            index=["ISO", "Country"],
            columns="combined_scenario",
            values="ratio_food_to_mort",
        )
        .reset_index()
    )
    wide.columns.name = None
    out_wide = output_path("combined_sensitivity_ratio_comparison.csv")
    wide.to_csv(out_wide, index=False)
    return out_full, out_wide


def plot_lowest_ratio_countries(results: pd.DataFrame, n_countries: int = 15) -> Path:
    """Plot countries closest to tipping across combined scenarios."""
    max_up = results[
        (results["scenario"] == "max_uptake")
        & (results["annual_food_savings_t"] > 0)
        & (results["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(results["ratio_food_to_mort"])
    ].copy()

    lowest = (
        max_up.groupby(["ISO", "Country"])["ratio_food_to_mort"]
        .min()
        .sort_values()
        .head(n_countries)
        .reset_index()
    )
    country_order = lowest["Country"].tolist()
    plotted = max_up[max_up["Country"].isin(country_order)]
    max_plot_ratio = plotted["ratio_food_to_mort"].max()

    y = np.arange(len(country_order))
    height = 0.25
    offsets = {
        "baseline_uniform_mean_ci": -height,
        "cereal_sweets_up_mean_ci": 0.0,
        "cereal_sweets_up_meat_p10_ci": height,
    }

    fig, ax = plt.subplots(figsize=(11, max(6, len(country_order) * 0.38)))
    for config in COMBINED_SCENARIOS:
        key = config["combined_scenario"]
        sub = (
            max_up[max_up["combined_scenario"] == key]
            .set_index("Country")
            .reindex(country_order)
        )
        vals = sub["ratio_food_to_mort"].values
        bars = ax.barh(
            y + offsets[key],
            vals,
            height,
            color=SCENARIO_COLORS[key],
            edgecolor="white",
            linewidth=0.6,
            label=config["label"],
        )
        for bar, val in zip(bars, vals):
            if np.isfinite(val):
                ax.text(
                    bar.get_width() + 0.08,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}x",
                    va="center",
                    ha="left",
                    fontsize=7,
                    color=SCENARIO_COLORS[key],
                    fontweight="bold",
                )

    ax.axvline(1, color="black", linestyle="--", linewidth=0.8, alpha=0.65)
    ax.text(
        1.03,
        -0.75,
        "positive-emissions threshold",
        fontsize=8,
        color="black",
        alpha=0.75,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(country_order, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("10-year food savings / survivor emissions")
    ax.set_title(
        "Combined Sensitivity: Countries Closest to Positive Emissions",
        loc="left",
        fontweight="bold",
    )
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}x"))
    ax.set_xlim(0, max_plot_ratio * 1.18)
    ax.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8, loc="upper right", framealpha=0.9)

    plt.tight_layout()
    out = output_path("combined_sensitivity_lowest_ratio_countries.png")
    plt.savefig(out, dpi=220, bbox_inches="tight")
    plt.close()
    return out


def main() -> None:
    print("=" * 88)
    print("COMBINED CONSERVATIVE SENSITIVITY")
    print("Diet shift to cereals/sweets + low meat carbon intensity")
    print("=" * 88)

    mort = load_mortality_emissions()
    be_all = run_combined_scenarios(mort)
    results = build_results_table(be_all, mort)

    print_summary(results)
    out_full, out_wide = save_outputs(results)
    fig_out = plot_lowest_ratio_countries(results)

    print(f"\nFull results -> {out_full}")
    print(f"Wide ratio comparison -> {out_wide}")
    print(f"Lowest-ratio figure -> {fig_out}")


if __name__ == "__main__":
    main()
