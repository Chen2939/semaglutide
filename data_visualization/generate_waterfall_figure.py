"""
Global emissions waterfall / bridge plot.

Decomposes the 10-year maximum-uptake climate result for complete-data
countries into a continuous bridge:

    naïve food-emission reductions
  − rebound offset
  − survivorship emissions
  − manufacturing (drug) emissions
  = net climate savings

Output:
  figures/global_emissions_waterfall.png
  data_result/global_emissions_waterfall.csv

Usage:
    python -m data_visualization.generate_waterfall_figure
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .breakeven_analysis import _complete_data_subset, compute_breakeven
from .pipeline import compute_food_savings, load_mortality_emissions, output_path


SCENARIO = "max_uptake"
HORIZON_YEARS = 10

# Muted publication palette
COLOR_START = "#4C72B0"
COLOR_DECREASE = "#C44E52"
COLOR_NET = "#55A868"


def compute_waterfall_components() -> pd.DataFrame:
    """Compute the waterfall components in Mt CO2e over 10 years."""
    food_savings, detail = compute_food_savings()
    mort = load_mortality_emissions()
    be = compute_breakeven(food_savings, mort, include_drug=True)
    valid = _complete_data_subset(be, scenario=SCENARIO)
    complete_isos = set(valid["ISO"])

    detail_max = detail[
        (detail["scenario"] == SCENARIO) & (detail["ISO"].isin(complete_isos))
    ].copy()

    detail_max["naive_carbon_savings_t"] = (
        detail_max["expected_demand_reduction"].abs()
        * detail_max["carbon_intensity_t"]
    )
    detail_max["actual_carbon_savings_t"] = detail_max["carbon_savings_t"].abs()

    naive_annual = detail_max["naive_carbon_savings_t"].sum()
    actual_annual = detail_max["actual_carbon_savings_t"].sum()
    rebound_annual = naive_annual - actual_annual

    actual_annual_be = valid["annual_food_savings_gross_t"].sum()
    if not np.isclose(actual_annual, actual_annual_be, rtol=1e-3, atol=1.0):
        print(
            "Warning: food-group actual savings differ from break-even gross "
            f"food savings ({actual_annual:,.0f} vs {actual_annual_be:,.0f} t)."
        )

    survivor_10yr = valid["total_survivor_emissions_10yr"].sum()
    drug_10yr = valid["total_drug_emissions_10yr"].sum()

    naive_10yr = naive_annual * HORIZON_YEARS
    rebound_10yr = rebound_annual * HORIZON_YEARS
    actual_10yr = actual_annual * HORIZON_YEARS
    net_10yr = actual_10yr - survivor_10yr - drug_10yr

    # Keep the intermediate actual-food step in the table for transparency,
    # but the plotted bridge is continuous without a mid-chart subtotal bar.
    rows = [
        {
            "step": "naive_reductions",
            "label": "Naive\nreductions",
            "kind": "increase",
            "plot": True,
            "value_Mt": naive_10yr / 1e6,
        },
        {
            "step": "rebound_effect",
            "label": "Rebound\neffect",
            "kind": "decrease",
            "plot": True,
            "value_Mt": rebound_10yr / 1e6,
        },
        {
            "step": "actual_food_savings",
            "label": "Actual food savings (after rebound)",
            "kind": "total",
            "plot": False,
            "value_Mt": actual_10yr / 1e6,
        },
        {
            "step": "survivorship",
            "label": "Survivorship\nemissions",
            "kind": "decrease",
            "plot": True,
            "value_Mt": survivor_10yr / 1e6,
        },
        {
            "step": "manufacturing",
            "label": "Manufacturing\nemissions",
            "kind": "decrease",
            "plot": True,
            "value_Mt": drug_10yr / 1e6,
        },
        {
            "step": "net_savings",
            "label": "Net climate\nsavings",
            "kind": "total",
            "plot": True,
            "value_Mt": net_10yr / 1e6,
        },
    ]
    out = pd.DataFrame(rows)
    out["n_countries"] = len(complete_isos)
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
            "axes.spines.top": False,
            "axes.spines.right": False,
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
        if step == "manufacturing":
            ax.annotate(
                f"-{value:,.1f} Mt",
                xy=(i, levels[i][1]),
                xytext=(i - 0.15, levels[i][1] + max(values) * 0.12),
                fontsize=8,
                color=COLOR_DECREASE,
                arrowprops=dict(
                    arrowstyle="->",
                    color=COLOR_DECREASE,
                    lw=0.8,
                    shrinkA=0,
                    shrinkB=2,
                ),
                ha="center",
                va="bottom",
            )
            continue

        y_text = levels[i][1]
        sign = "-" if kind == "decrease" else ""
        ax.text(
            i,
            y_text + max(values) * 0.015,
            f"{sign}{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#222222",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Mt CO$_2$eq over 10 years", fontsize=10)
    ax.set_title(
        "Decomposition of global climate impact under maximum uptake",
        fontsize=12,
        pad=10,
    )
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(0, max(hi for _, hi in levels) * 1.16)
    ax.tick_params(axis="both", labelsize=9)
    ax.grid(axis="y", color="#d0d0d0", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    out = output_path("global_emissions_waterfall.png")
    fig.savefig(str(out), dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(out)


def main() -> None:
    print("Building global emissions waterfall...")
    components = compute_waterfall_components()
    csv_path = output_path("global_emissions_waterfall.csv")
    components.to_csv(csv_path, index=False)
    fig_path = plot_waterfall(components)

    print(f"Saved table: {csv_path}")
    print(f"Saved figure: {fig_path}")
    print("\n10-year decomposition (Mt CO2e):")
    for _, row in components.iterrows():
        prefix = "-" if row["kind"] == "decrease" else " "
        label = str(row["label"]).replace("\n", " ")
        plotted = "" if row["plot"] else " (table only)"
        print(f"  {prefix}{label:<40} {row['value_Mt']:8.1f}{plotted}")


if __name__ == "__main__":
    main()
