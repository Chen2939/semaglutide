"""
Global emissions waterfall / bridge plot.

Decomposes the 10-year maximum-uptake climate result for complete-data
countries into a continuous bridge:

    naïve food-emission reductions
  − rebound offset
  − survivorship emissions
  − manufacturing (drug) emissions
  = net climate savings

Reconciliation with ``breakeven_stock_all_countries``
-----------------------------------------------------
These two figures describe the same 40-country, 10-year result and their
Year-10 endpoints match exactly; they only differ in where the drug
(manufacturing) term is placed:

  * The break-even stock figure folds drug emissions INTO its food-savings
    line, so its blue "food savings" curve is net of pharmaceuticals
    (Year-10 = 1,086.6 Mt) and its red curve is survivor emissions
    (Year-10 = 200.6 Mt).
  * This waterfall pulls drug back OUT as its own downward step (12.1 Mt),
    so ``actual_food_savings`` here is the GROSS figure before drug removal
    (1,098.6 Mt), i.e. actual_food_savings − manufacturing = the stock
    figure's blue-line endpoint.

Both land on the identical net (886.0 Mt) and 5.42× year-10 ratio; the net
bar equals the vertical gap between the stock figure's two curves at Year 10.

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

# ── Mortality-channel state, recorded into the output CSV ─────────────
#
# Panel B is the fully-weighted case: all three channels on. Recorded next to
# the numbers because horizon alone does not distinguish this artefact from
# Panel A -- the panels differ by weighting state as well as by horizon, and
# that is the distinction a reader is most likely to get wrong.
FOOD_SURVIVAL_WEIGHTED = True

# The pharmaceutical channel arrives already pi_dose-weighted: drug emissions
# come from compute_breakeven's total_drug_emissions_10yr, not from
# drug_footprint's unweighted drug_emissions_1yr_t (which is what Panel A uses,
# correctly, having all channels off).
DRUG_SURVIVAL_WEIGHTED = True

# Muted publication palette
COLOR_START = "#4C72B0"
COLOR_DECREASE = "#C44E52"
COLOR_NET = "#55A868"


def compute_waterfall_components() -> pd.DataFrame:
    """Compute the waterfall components in Mt CO2e over 10 years."""
    # Passed explicitly rather than left to the default so the value recorded in
    # the CSV cannot drift from the value actually used.
    food_savings, detail = compute_food_savings(
        survival_weighted=FOOD_SURVIVAL_WEIGHTED
    )
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

    # Sum the per-year series. This used to be `annual * HORIZON_YEARS`, which is
    # only right while the annual saving is constant; under survival weighting it
    # falls every year as treated patients die, so multiplying the year-1 value by
    # ten overstates all three legs. The naive leg needs its own per-year series
    # because it is a pre-rebound quantity, not derivable from carbon_savings.
    year_cols = [
        (f"expected_demand_reduction_Y{y}", f"carbon_savings_t_Y{y}")
        for y in range(1, HORIZON_YEARS + 1)
    ]
    if all(a in detail_max.columns and b in detail_max.columns for a, b in year_cols):
        naive_10yr = sum(
            (detail_max[a].abs() * detail_max["carbon_intensity_t"]).sum()
            for a, _ in year_cols
        )
        actual_10yr = sum(detail_max[b].abs().sum() for _, b in year_cols)
        rebound_10yr = naive_10yr - actual_10yr
    else:
        # Unweighted run: the series is constant, so this reduces to the old form.
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
    out["food_survival_weighted"] = FOOD_SURVIVAL_WEIGHTED
    out["drug_survival_weighted"] = DRUG_SURVIVAL_WEIGHTED
    # Derived, not asserted: the panel has a survivorship channel iff it draws
    # a survivorship step.
    out["survivor_emissions_included"] = "survivorship" in set(out["step"])
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
    ax.set_ylabel("Mt CO$_2$eq over 10 years", fontsize=10)
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
