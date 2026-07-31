"""
Combined conservative sensitivity analysis.

This stacks two conservative assumptions reviewers may ask about:

1. Diet composition shifts toward cereals/sweets while meat decreases less
   (``cereal_sweets_up``).
2. Carbon intensity is set to the P10 value for ALL food groups, not just meat.
   Each cell is scored against the survivor-emissions file built from its own
   carbon intensities, so both sides of the comparison move together.

Outputs:
  data_result/combined_sensitivity_results.csv
  data_result/combined_sensitivity_ratio_comparison.csv
  (carbon intensities come from Food data/carbon_intensity_p10.csv)
  figures/combined_sensitivity_lowest_ratio_countries.png

Usage:
    python -m diet_sensitivity.combined_analysis
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import (
    ROOT,
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)



COMBINED_SCENARIOS = [
    {
        "combined_scenario": "baseline_uniform_mean_ci",
        "label": "Uniform baseline",
        "diet_scenario": "baseline_uniform",
        "ci_file": "carbon_intensity.csv",
        "ci_scenario": "mean",
    },
    {
        "combined_scenario": "cereal_sweets_up_mean_ci",
        "label": "Cereals/sweets shift",
        "diet_scenario": "cereal_sweets_up",
        "ci_file": "carbon_intensity.csv",
        "ci_scenario": "mean",
    },
    {
        "combined_scenario": "cereal_sweets_up_p10_ci",
        "label": "Cereals/sweets + all-food P10 CI",
        "diet_scenario": "cereal_sweets_up",
        "ci_file": "carbon_intensity_p10.csv",
        "ci_scenario": "p10",
    },
]

SCENARIO_COLORS = {
    "baseline_uniform_mean_ci": "#4c78a8",
    "cereal_sweets_up_mean_ci": "#d62728",
    "cereal_sweets_up_p10_ci": "#7f3c8d",
}


def build_meat_p10_ci_file() -> Path:
    """Create a derived carbon-intensity file with only Meat set to P10.

    UNCONSUMED. The combined-conservative cell moved from a meat-only P10 to an
    all-food P10 assumption, so nothing calls this any more. Kept because
    retiring it -- and deleting the derived file it writes into ``data_result/``
    -- is separate cleanup, not part of the basis change.
    """
    mean_ci = pd.read_csv(ROOT / "Food data" / "carbon_intensity.csv")
    p10_ci = pd.read_csv(ROOT / "Food data" / "carbon_intensity_p10.csv")

    derived = mean_ci.set_index("ISO").copy()
    meat_p10 = p10_ci.set_index("ISO")["Meat"]
    derived["Meat"] = meat_p10
    if derived["Meat"].isna().any():
        missing = ", ".join(derived[derived["Meat"].isna()].index.astype(str))
        raise ValueError(f"Meat P10 missing for ISO codes after alignment: {missing}")
    derived = derived.reset_index()

    out = output_path("carbon_intensity_meat_p10.csv")
    derived.to_csv(out, index=False)
    return out


# ── The combined-conservative cell ────────────────────────────────────
#
# This one specification is named in three separate modules -- here, in
# sensitivity_overview.py and in sensitivity_suite.py -- each with its own
# config literal. Three copies of a definition drift: a change to one is not a
# change to the others, and nothing complains, so two scripts silently report a
# different scenario under the same label. The definition below is canonical and
# each call site asserts against it, so drift fails loudly at run time instead of
# surfacing as an unexplained disagreement between two tables.
#
# The assertion below compares the (diet, ci_file) pair only. It does NOT check
# the scenario key or the human label, so renaming the cell without renaming its
# label is a drift it cannot catch -- keep the key, the label and this spec in
# step by hand.
COMBINED_CONSERVATIVE_DIET = "cereal_sweets_up"
COMBINED_CONSERVATIVE_CI_FILE = "carbon_intensity_p10.csv"
COMBINED_CONSERVATIVE_CI_SCENARIO = "p10"


def combined_conservative_spec() -> tuple[str, str]:
    """The canonical (diet_scenario, ci_file) pair for combined conservative."""
    return COMBINED_CONSERVATIVE_DIET, COMBINED_CONSERVATIVE_CI_FILE


def assert_combined_conservative(diet: str, ci_file: str | Path, where: str) -> None:
    """Raise if a call site's combined-conservative cell has drifted."""
    exp_diet, exp_ci = combined_conservative_spec()
    got = (diet, Path(ci_file).name)
    expected = (exp_diet, Path(exp_ci).name)
    if got != expected:
        raise ValueError(
            f"Combined-conservative definition in {where} has drifted.\n"
            f"  expected {expected}\n"
            f"  got      {got}\n"
            "All three definitions (combined_analysis.py, sensitivity_overview.py, "
            "sensitivity_suite.py) must resolve to the same (diet, ci_file) pair."
        )


def run_combined_scenarios(mort: pd.DataFrame | None = None) -> pd.DataFrame:
    """Run each combined sensitivity scenario and return stacked results.

    Each cell is scored against the survivor-emissions file built from its own
    carbon intensities. ``mort`` is ignored and kept only so existing callers
    do not break; pairing every cell with one frame is the basis mismatch this
    change removes.
    """
    all_results = []
    mort_cache: Dict[str, pd.DataFrame] = {}

    for config in COMBINED_SCENARIOS:
        ci_file = config["ci_file"]
        if config["combined_scenario"] == "cereal_sweets_up_p10_ci":
            assert_combined_conservative(
                config["diet_scenario"], ci_file, "combined_analysis.py"
            )
        ci_scenario = config["ci_scenario"]
        print(f"\n  -> {config['combined_scenario']}")
        print(f"     diet={config['diet_scenario']}, ci={ci_file}, "
              f"survivor={ci_scenario}")

        if ci_scenario not in mort_cache:
            mort_cache[ci_scenario] = load_mortality_emissions(ci_scenario)

        food_savings, _ = compute_food_savings(
            diet_scenario=config["diet_scenario"],
            ci_file=str(ci_file),
        )
        be = compute_breakeven(food_savings, mort_cache[ci_scenario])
        be["combined_scenario"] = config["combined_scenario"]
        be["combined_label"] = config["label"]
        be["diet_scenario"] = config["diet_scenario"]
        be["ci_assumption"] = ci_scenario
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
        # Sum of the per-year series, not annual x 10.
        ratio = valid["total_food_savings_10yr"].sum() / total_mort
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
        "cereal_sweets_up_p10_ci": height,
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


def main(ci_scenario: str = "mean") -> None:
    print("=" * 88)
    print("COMBINED CONSERVATIVE SENSITIVITY")
    print("Diet shift to cereals/sweets + all-food P10 carbon intensity")
    print("=" * 88)

    mort = load_mortality_emissions(ci_scenario)
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
