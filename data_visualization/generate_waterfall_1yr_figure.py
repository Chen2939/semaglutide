"""
Global emissions waterfall / bridge plot — Panel A: one-year, no survivorship.

Companion to ``generate_waterfall_figure`` (the 10-year decomposition, which
includes survivorship emissions for the 35-country OECD complete-data subset).

This version (Panel A) shows a single year of the maximum-uptake climate result
and deliberately excludes survivorship emissions. Because it does not use
survivor emissions or mortality at all, it is not gated by OECD/HLD coverage and
therefore uses the FULL 53-country food-data sample (every country with real
food-emission savings under maximum uptake):

    naïve food-emission reductions (1 year)
  − rebound offset (1 year)
  − manufacturing (drug) emissions (1 year)
  = net climate savings (1 year)

Only the food side and one year of pharmaceutical manufacturing are needed, so
no imputation of survivor emissions or mortality is involved.

Output:
  figures/global_emissions_waterfall_1yr.png
  data_result/global_emissions_waterfall_1yr.csv

Usage:
    python -m data_visualization.generate_waterfall_1yr_figure
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .drug_footprint import build_drug_emissions
from .pipeline import compute_food_savings, output_path


SCENARIO = "max_uptake"
HORIZON_YEARS = 1

# Muted publication palette (matches the 10-year figure)
COLOR_START = "#4C72B0"
COLOR_DECREASE = "#C44E52"
COLOR_NET = "#55A868"


def compute_waterfall_components() -> pd.DataFrame:
    """Compute the one-year waterfall components in Mt CO2e (no survivorship).

    Uses the full 53-country food-data sample: every country with positive
    food-emission savings under the scenario. Survivor emissions and mortality
    are not used, so there is no OECD/HLD coverage gate.
    """
    food_savings, detail = compute_food_savings()

    # Full food-data sample: countries with real food savings in this scenario.
    food_scenario = food_savings[
        (food_savings["scenario"] == SCENARIO)
        & (food_savings["annual_food_savings_t"] > 0)
    ]
    sample_isos = set(food_scenario["ISO"])

    detail_max = detail[
        (detail["scenario"] == SCENARIO) & (detail["ISO"].isin(sample_isos))
    ].copy()

    detail_max["naive_carbon_savings_t"] = (
        detail_max["expected_demand_reduction"].abs()
        * detail_max["carbon_intensity_t"]
    )
    detail_max["actual_carbon_savings_t"] = detail_max["carbon_savings_t"].abs()

    naive_annual = detail_max["naive_carbon_savings_t"].sum()
    actual_annual = detail_max["actual_carbon_savings_t"].sum()
    rebound_annual = naive_annual - actual_annual

    actual_annual_agg = food_scenario["annual_food_savings_t"].sum()
    if not np.isclose(actual_annual, actual_annual_agg, rtol=1e-3, atol=1.0):
        print(
            "Warning: food-group actual savings differ from aggregated gross "
            f"food savings ({actual_annual:,.0f} vs {actual_annual_agg:,.0f} t)."
        )

    # One year of pharmaceutical manufacturing emissions for the same sample.
    drug = build_drug_emissions()
    drug_scenario = drug[
        (drug["scenario"] == SCENARIO) & (drug["ISO"].isin(sample_isos))
    ]
    drug_annual = drug_scenario["drug_emissions_1yr_t"].sum()

    # Net one-year savings: food savings after rebound, minus drug emissions.
    # Survivorship emissions are intentionally excluded from this figure.
    net_annual = actual_annual - drug_annual

    # Keep the intermediate actual-food step in the table for transparency,
    # but the plotted bridge is continuous without a mid-chart subtotal bar.
    rows = [
        {
            "step": "naive_reductions",
            "label": "Naive\nreductions",
            "kind": "increase",
            "plot": True,
            "value_Mt": naive_annual / 1e6,
        },
        {
            "step": "rebound_effect",
            "label": "Rebound\neffect",
            "kind": "decrease",
            "plot": True,
            "value_Mt": rebound_annual / 1e6,
        },
        {
            "step": "actual_food_savings",
            "label": "Actual food savings (after rebound)",
            "kind": "total",
            "plot": False,
            "value_Mt": actual_annual / 1e6,
        },
        {
            "step": "manufacturing",
            "label": "Manufacturing\nemissions",
            "kind": "decrease",
            "plot": True,
            "value_Mt": drug_annual / 1e6,
        },
        {
            "step": "net_savings",
            "label": "Net climate\nsavings",
            "kind": "total",
            "plot": True,
            "value_Mt": net_annual / 1e6,
        },
    ]
    out = pd.DataFrame(rows)
    out["n_countries"] = len(sample_isos)
    out["scenario"] = SCENARIO
    out["horizon_years"] = HORIZON_YEARS
    return out


def plot_waterfall(components: pd.DataFrame) -> str:
    """Draw a continuous publication-style bridge chart."""
    plot_df = components[components["plot"]].reset_index(drop=True)
    actual_after_rebound = float(
        components.loc[components["step"] == "actual_food_savings", "value_Mt"].iloc[0]
    )

    labels = plot_df["label"].tolist()
    values = plot_df["value_Mt"].to_numpy(dtype=float)
    kinds = plot_df["kind"].tolist()
    steps = plot_df["step"].tolist()

    levels = []
    running = 0.0
    for value, kind in zip(values, kinds):
        if kind == "increase":
            levels.append((0.0, value))
            running = value
        elif kind == "decrease":
            levels.append((running - value, running))
            running -= value
        else:
            levels.append((0.0, value))
            running = value

    bottoms = np.array([lo for lo, _ in levels])
    heights = np.array([hi - lo for lo, hi in levels])
    colors = []
    for kind in kinds:
        if kind == "increase":
            colors.append(COLOR_START)
        elif kind == "decrease":
            colors.append(COLOR_DECREASE)
        else:
            colors.append(COLOR_NET)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": True,
            "axes.spines.right": True,
            "axes.linewidth": 0.8,
        }
    )

    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    x = np.arange(len(labels))
    bars = ax.bar(
        x,
        heights,
        bottom=bottoms,
        color=colors,
        width=0.58,
        edgecolor="white",
        linewidth=0.6,
        zorder=3,
    )

    # Connect successive bridge tops for a continuous waterfall read.
    for i in range(len(levels) - 1):
        left_top = levels[i][1] if kinds[i] != "decrease" else levels[i][0]
        # After an increase/total, next decrease starts from that top;
        # after a decrease, next bar starts from the lower edge.
        if kinds[i] == "decrease":
            y = levels[i][0]
        else:
            y = levels[i][1]
        ax.plot(
            [i + 0.29, i + 1 - 0.29],
            [y, y],
            color="#7f7f7f",
            linewidth=0.9,
            linestyle="-",
            zorder=2,
        )

    # Reference line: food savings remaining after rebound.
    ax.axhline(
        actual_after_rebound,
        color="#9a9a9a",
        linewidth=0.8,
        linestyle="--",
        zorder=1,
    )
    ax.text(
        1.0,
        actual_after_rebound - max(values) * 0.045,
        f"After rebound = {actual_after_rebound:,.0f} Mt",
        ha="center",
        va="top",
        fontsize=8,
        color="#555555",
    )

    for i, (value, kind, step) in enumerate(zip(values, kinds, steps)):
        y_text = levels[i][1]
        sign = "-" if kind == "decrease" else ""
        text_color = COLOR_DECREASE if kind == "decrease" else "#222222"
        ax.text(
            i,
            y_text + max(values) * 0.015,
            f"{sign}{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color=text_color,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Mt CO$_2$eq over 1 year", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(0, max(hi for _, hi in levels) * 1.16)
    ax.tick_params(axis="both", labelsize=9)
    ax.grid(axis="y", color="#d0d0d0", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = output_path("global_emissions_waterfall_1yr.png")
    fig.savefig(str(out), dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(out)


def main() -> None:
    print("Building global emissions waterfall (Panel A: 1-year, no survivorship, 53-country sample)...")
    components = compute_waterfall_components()
    csv_path = output_path("global_emissions_waterfall_1yr.csv")
    components.to_csv(csv_path, index=False)
    fig_path = plot_waterfall(components)

    print(f"Sample size: {int(components['n_countries'].iloc[0])} countries")
    print(f"Saved table: {csv_path}")
    print(f"Saved figure: {fig_path}")
    print("\n1-year decomposition (Mt CO2e):")
    for _, row in components.iterrows():
        prefix = "-" if row["kind"] == "decrease" else " "
        label = str(row["label"]).replace("\n", " ")
        plotted = "" if row["plot"] else " (table only)"
        print(f"  {prefix}{label:<40} {row['value_Mt']:8.1f}{plotted}")


if __name__ == "__main__":
    main()
