"""
Global emissions waterfall / bridge plot — Panel A: one-year, no survivorship.

Companion to ``generate_waterfall_figure`` (the 10-year decomposition, which
includes survivorship emissions for the 40-country OECD complete-data subset).

Panel A is a **no-mortality counterfactual**: the maximum-uptake climate result
with all three of the model's mortality channels switched off.

    1. food-side survival weighting pi(t)         OFF
    2. pharmaceutical-side weighting pi_dose(t)   OFF
    3. survivor emissions                         OFF (no bar in this panel)

Mechanically that is the first year's shock solved with the weighting disabled:
``compute_food_savings(survival_weighted=False)`` runs ``years=[1]`` with the
pi vector set to exact 1.0, through the same solver the weighted path uses. It
is not an evaluation at a zero timepoint -- there is no year-0 row in the
survival-weight table and none is needed.

    naïve food-emission reductions
  − rebound offset
  − manufacturing (drug) emissions
  = net emissions savings

**Do not "fix" the drug side to use a survival-weighted column.** It reads
``drug_emissions_1yr_t``, which is ``treated_users_initial x kg_per_user_year``
with no survival applied, and unweighted is *correct here*: channel 2 is off by
the same decision that switches off channel 1. The weighted column
(``drug_emissions_t_Y1``, equal to breakeven's ``annual_drug_emissions_t``) is
the right one everywhere else in the tree, and swapping it in here would restore
exactly the mismatch this panel was rebuilt to remove -- a weighted drug side
against an unweighted food side.

This panel is why the combination matters more than any single channel. It was
previously current and internally inconsistent, not stale: the food side picked
up pi(t) when weighting was introduced at source, the drug side did not, and the
output stayed entirely plausible.

Because no survivor emissions or mortality data are read, the panel is not gated
by OECD/HLD coverage and uses the FULL 53-country food-data sample (every
country with real food-emission savings under maximum uptake).

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

# ── Mortality-channel state, recorded into the output CSV ─────────────
#
# horizon_years alone does not say what the number means: Panel A and Panel B
# differ by which mortality channels are switched on, not only by horizon. The
# artefact records that state so a reader does not have to infer it from the
# module, which is what let a weighted food side sit against an unweighted drug
# side here without anyone noticing.
FOOD_SURVIVAL_WEIGHTED = False

# The choice of drug column IS the pharmaceutical channel's state, so the flag
# is looked up from the column name rather than asserted alongside it. Swap the
# column and the recorded state follows automatically -- meaning a future swap
# back to the weighted column would announce itself in the CSV as a food/drug
# mismatch instead of hiding.
DRUG_COLUMN = "drug_emissions_1yr_t"
DRUG_COLUMN_IS_WEIGHTED = {
    "drug_emissions_1yr_t": False,  # users_initial x kg, no survival applied
    "drug_emissions_t_Y1": True,    # pi_dose-weighted year 1
}

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
    # survival_weighted=False is the no-mortality counterfactual: years=[1] with
    # the pi vector set to exact 1.0, through the same solver the weighted path
    # uses (pipeline.py: years/pi_by_year). Gated at exactly 0.0 against the
    # pre-pi pipeline by null_check_pi.py gate N2.
    food_savings, detail = compute_food_savings(
        survival_weighted=FOOD_SURVIVAL_WEIGHTED
    )

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
    # Unweighted by design -- see the module docstring. drug_emissions_1yr_t is
    # users_initial x kg_per_user_year with no survival applied, which is the
    # correct column for a panel with every mortality channel off. Do not swap
    # in drug_emissions_t_Y1; that is the weighted column the rest of the tree
    # uses and it would put a weighted drug side against an unweighted food side.
    drug_annual = drug_scenario[DRUG_COLUMN].sum()

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
            "label": "Net emissions\nsavings",
            "kind": "total",
            "plot": True,
            "value_Mt": net_annual / 1e6,
        },
    ]
    out = pd.DataFrame(rows)
    out["n_countries"] = len(sample_isos)
    out["scenario"] = SCENARIO
    out["horizon_years"] = HORIZON_YEARS
    out["food_survival_weighted"] = FOOD_SURVIVAL_WEIGHTED
    out["drug_survival_weighted"] = DRUG_COLUMN_IS_WEIGHTED[DRUG_COLUMN]
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
    ax.set_ylabel("Mt CO$_2$eq per year, mortality effects excluded", fontsize=10)
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
