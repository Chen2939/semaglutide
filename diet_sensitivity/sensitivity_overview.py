"""
All-sensitivity overview against the OECD-updated baseline.

This script summarizes the sensitivity analyses currently implemented:

1. Uniform baseline with mean carbon intensity.
2. Diet-composition sensitivities with mean carbon intensity.
3. Full food carbon-intensity P10/P90 sensitivities.
4. Combined conservative case: cereals/sweets diet shift + Meat P10 CI.

Pharmaceutical emissions are folded into baseline net food savings through
``compute_breakeven(..., include_drug=True)``.

Outputs:
  data_result/all_sensitivity_overview_results.csv
  data_result/all_sensitivity_overview_country_ratios.csv
  figures/all_sensitivity_overview.png

Usage:
    python -m diet_sensitivity.sensitivity_overview
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import (
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)

from .combined_analysis import build_meat_p10_ci_file


OVERVIEW_SCENARIOS = [
    {
        "overview_scenario": "baseline_mean_ci",
        "label": "Baseline",
        "group": "Baseline",
        "diet_scenario": "baseline_uniform",
        "ci_file": "carbon_intensity.csv",
        "color": "#4c78a8",
    },
    {
        "overview_scenario": "fatty_food_down_mean_ci",
        "label": "Fatty foods down",
        "group": "Diet composition",
        "diet_scenario": "fatty_food_down",
        "ci_file": "carbon_intensity.csv",
        "color": "#2ca02c",
    },
    {
        "overview_scenario": "cereal_sweets_up_mean_ci",
        "label": "Cereals/sweets shift",
        "group": "Diet composition",
        "diet_scenario": "cereal_sweets_up",
        "ci_file": "carbon_intensity.csv",
        "color": "#d62728",
    },
    {
        "overview_scenario": "baseline_p10_ci",
        "label": "All foods P10 CI",
        "group": "Carbon intensity",
        "diet_scenario": "baseline_uniform",
        "ci_file": "carbon_intensity_p10.csv",
        "color": "#8ecae6",
    },
    {
        "overview_scenario": "baseline_p90_ci",
        "label": "All foods P90 CI",
        "group": "Carbon intensity",
        "diet_scenario": "baseline_uniform",
        "ci_file": "carbon_intensity_p90.csv",
        "color": "#023047",
    },
    {
        "overview_scenario": "cereal_sweets_up_meat_p10_ci",
        "label": "Cereals/sweets + low-meat CI",
        "group": "Combined conservative",
        "diet_scenario": "cereal_sweets_up",
        "ci_file": None,
        "color": "#7f3c8d",
    },
]


def run_overview_scenarios(mort: pd.DataFrame) -> pd.DataFrame:
    """Run all overview scenarios and return country-level ratios."""
    meat_p10_file = build_meat_p10_ci_file()
    all_results = []

    for config in OVERVIEW_SCENARIOS:
        ci_file = config["ci_file"] or meat_p10_file
        print(f"\n  -> {config['label']}")
        print(f"     diet={config['diet_scenario']}, ci={ci_file}")

        food_savings, _ = compute_food_savings(
            diet_scenario=config["diet_scenario"],
            ci_file=str(ci_file),
        )
        be = compute_breakeven(food_savings, mort)
        be["overview_scenario"] = config["overview_scenario"]
        be["overview_label"] = config["label"]
        be["sensitivity_group"] = config["group"]
        be["diet_scenario"] = config["diet_scenario"]
        be["ci_file"] = str(ci_file)
        be["net_10yr_emissions_t"] = (
            be["total_food_savings_10yr"]
            - be["total_survivor_emissions_10yr"]
        )
        be["net_positive_emissions"] = (
            (be["annual_food_savings_t"] > 0)
            & np.isfinite(be["ratio_food_to_mort"])
            & (be["ratio_food_to_mort"] < 1.0)
        )
        all_results.append(be)

    return pd.concat(all_results, ignore_index=True)


def summarize_max_uptake(results: pd.DataFrame) -> pd.DataFrame:
    """Create global and minimum-country summary for max uptake."""
    rows = []
    for config in OVERVIEW_SCENARIOS:
        sub = results[
            (results["scenario"] == "max_uptake")
            & (results["overview_scenario"] == config["overview_scenario"])
        ]
        valid = sub[
            np.isfinite(sub["ratio_food_to_mort"])
            & (sub["annual_food_savings_t"] > 0)
            & (sub["total_survivor_emissions_10yr"] > 0)
        ]
        total_food = valid["annual_food_savings_t"].sum()
        total_mort = valid["total_survivor_emissions_10yr"].sum()
        min_row = valid.loc[valid["ratio_food_to_mort"].idxmin()]
        rows.append(
            {
                "overview_scenario": config["overview_scenario"],
                "overview_label": config["label"],
                "sensitivity_group": config["group"],
                "annual_food_savings_Mt": total_food / 1e6,
                "survivor_emissions_10yr_Mt": total_mort / 1e6,
                "ratio_food_to_mort": total_food * 10 / total_mort,
                "min_country": min_row["Country"],
                "min_country_ratio": min_row["ratio_food_to_mort"],
                "n_complete_countries": valid["ISO"].nunique(),
                "n_tipped_countries": int((valid["ratio_food_to_mort"] < 1).sum()),
            }
        )
    return pd.DataFrame(rows)


def save_outputs(results: pd.DataFrame, summary: pd.DataFrame) -> tuple[Path, Path]:
    """Save summary and country-level wide ratio tables."""
    out_summary = output_path("all_sensitivity_overview_results.csv")
    summary.to_csv(out_summary, index=False)

    wide = (
        results[results["scenario"] == "max_uptake"]
        .pivot_table(
            index=["ISO", "Country"],
            columns="overview_scenario",
            values="ratio_food_to_mort",
        )
        .reset_index()
    )
    wide.columns.name = None
    out_wide = output_path("all_sensitivity_overview_country_ratios.csv")
    wide.to_csv(out_wide, index=False)
    return out_summary, out_wide


def plot_overview(summary: pd.DataFrame) -> Path:
    """Plot global ratios and lowest-country margins for all sensitivities."""
    summary = summary.copy()
    order = [s["overview_scenario"] for s in OVERVIEW_SCENARIOS]
    summary["overview_scenario"] = pd.Categorical(
        summary["overview_scenario"],
        categories=order,
        ordered=True,
    )
    summary = summary.sort_values("overview_scenario")
    colors = [s["color"] for s in OVERVIEW_SCENARIOS]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8))
    y = np.arange(len(summary))

    ratio_bars = axes[0].barh(
        y,
        summary["ratio_food_to_mort"],
        color=colors,
        edgecolor="white",
        linewidth=0.7,
    )
    axes[0].axvline(1, color="black", linestyle="--", linewidth=0.8, alpha=0.65)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(summary["overview_label"], fontsize=9)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Global 10-year food savings / survivor emissions")
    axes[0].set_title("A. Global Ratio", loc="left", fontweight="bold")
    axes[0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}x"))
    axes[0].grid(axis="x", alpha=0.2, linewidth=0.5)
    axes[0].set_axisbelow(True)

    for bar, val in zip(ratio_bars, summary["ratio_food_to_mort"]):
        axes[0].text(
            bar.get_width() + 0.08,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}x",
            va="center",
            fontsize=8,
            fontweight="bold",
        )

    min_bars = axes[1].barh(
        y,
        summary["min_country_ratio"],
        color=colors,
        edgecolor="white",
        linewidth=0.7,
    )
    axes[1].axvline(1, color="black", linestyle="--", linewidth=0.8, alpha=0.65)
    axes[1].set_yticks(y)
    axes[1].set_yticklabels([""] * len(summary))
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Lowest country ratio")
    axes[1].set_title("B. Closest Country to Tipping", loc="left", fontweight="bold")
    axes[1].xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}x"))
    axes[1].grid(axis="x", alpha=0.2, linewidth=0.5)
    axes[1].set_axisbelow(True)

    for bar, val, country in zip(
        min_bars,
        summary["min_country_ratio"],
        summary["min_country"],
    ):
        axes[1].text(
            bar.get_width() + 0.08,
            bar.get_y() + bar.get_height() / 2,
            f"{country}: {val:.1f}x",
            va="center",
            fontsize=8,
            fontweight="bold",
        )

    fig.suptitle(
        "Sensitivity Analyses vs. OECD-Updated Baseline (Max Uptake)",
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()
    out = output_path("all_sensitivity_overview.png")
    plt.savefig(out, dpi=220, bbox_inches="tight")
    plt.close()
    return out


def print_summary(summary: pd.DataFrame) -> None:
    """Print compact overview summary."""
    print("\n" + "=" * 96)
    print("ALL SENSITIVITY OVERVIEW (max uptake)")
    print("=" * 96)
    print(
        f"\n  {'Scenario':<34}  {'Group':<22}  {'Global':>8}  "
        f"{'Closest country':>24}  {'Tipped':>6}"
    )
    print("  " + "-" * 96)
    for _, row in summary.iterrows():
        print(
            f"  {row['overview_label']:<34}  {row['sensitivity_group']:<22}  "
            f"{row['ratio_food_to_mort']:>7.2f}x  "
            f"{row['min_country']:>16s} ({row['min_country_ratio']:.2f}x)  "
            f"{int(row['n_tipped_countries']):>6d}"
        )


def main() -> None:
    print("=" * 96)
    print("ALL SENSITIVITY OVERVIEW")
    print("Current sensitivities compared against OECD-updated baseline")
    print("=" * 96)

    mort = load_mortality_emissions()
    results = run_overview_scenarios(mort)
    summary = summarize_max_uptake(results)
    print_summary(summary)
    out_summary, out_wide = save_outputs(results, summary)
    out_fig = plot_overview(summary)

    print(f"\nSummary table -> {out_summary}")
    print(f"Country ratio table -> {out_wide}")
    print(f"Overview figure -> {out_fig}")


if __name__ == "__main__":
    main()
