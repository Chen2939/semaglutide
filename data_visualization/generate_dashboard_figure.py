"""
Country Dashboard — combined multi-panel figure for paper.

Inspired by Nature Food series (Hegwood et al., 2023) "sprawling visuals."
Shows top countries side-by-side across three dimensions:
  Panel A: Carbon emissions saved from reduced food consumption
  Panel B: Person-years saved from reduced mortality
  Panel C: Break-even ratio (food savings ÷ survivor emissions, 10-year)

All panels share a y-axis (country names) so readers can track each
country across outcomes.

Output: figures/country_dashboard.png

Usage:
    python -m data_visualization.generate_dashboard_figure
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec

from .pipeline import compute_food_savings, load_mortality_emissions, output_path
from .breakeven_analysis import compute_breakeven

# ── Color palette — each panel has its own color family ───────────────

CLR_A_MAX = "#0d7e83"    # teal (food-emission savings)
CLR_A_MOD = "#7bc8c9"
CLR_B_MAX = "#6a3d9a"    # purple (person-years saved)
CLR_B_MOD = "#b5a4d4"
CLR_C_MAX = "#e66101"    # amber (break-even ratio)
CLR_C_MOD = "#f5b97a"

N_COUNTRIES = 15


def build_dashboard_data():
    """Merge food savings, mortality, and break-even into one DataFrame."""
    print("[1/3] Running Price Rebound pipeline...")
    food_savings, result_df = compute_food_savings()

    print("[2/3] Loading mortality data...")
    mort = load_mortality_emissions()

    print("[3/3] Computing break-even ratios...")
    be_df = compute_breakeven(food_savings, mort)

    # Extract person-years saved from mortality CSV
    person_years = mort[
        ["ISO", "scenario", "total_person_years_saved"]
    ].copy()

    # Merge all three into one frame
    dashboard = pd.merge(
        food_savings, person_years, on=["ISO", "scenario"], how="inner"
    )
    dashboard = pd.merge(
        dashboard,
        be_df[["ISO", "scenario", "ratio_food_to_mort",
               "total_food_savings_10yr", "total_survivor_emissions_10yr"]],
        on=["ISO", "scenario"], how="left",
    )

    # Food-group breakdown for stacked bars
    food_by_group = (
        result_df.groupby(["ISO", "Country", "scenario", "final_food_group"])[
            "carbon_savings_t"
        ]
        .sum()
        .abs()
        .reset_index()
    )

    return dashboard, food_by_group


def plot_dashboard(dashboard, food_by_group):
    """Generate the 3-panel country dashboard figure."""

    max_up = dashboard[dashboard["scenario"] == "max_uptake"].copy()
    mod_up = dashboard[dashboard["scenario"] == "mod_uptake"].copy()

    # Rank by max-uptake food savings
    max_up = max_up.sort_values("annual_food_savings_t", ascending=False)
    top_isos = max_up.head(N_COUNTRIES)["ISO"].tolist()

    max_top = max_up[max_up["ISO"].isin(top_isos)].set_index("ISO").loc[top_isos]
    mod_top = mod_up[mod_up["ISO"].isin(top_isos)].set_index("ISO").reindex(top_isos)

    countries = max_top["Country"].tolist()
    n = len(countries)
    y = np.arange(n)
    bh = 0.35

    fig = plt.figure(figsize=(22, max(8, n * 0.55)))
    gs = GridSpec(1, 3, figure=fig, width_ratios=[1.2, 1, 0.8], wspace=0.35)

    # ── Panel A: Food-emission savings (kt CO2eq/yr) ──────────────────

    ax_a = fig.add_subplot(gs[0])

    food_max = max_top["annual_food_savings_t"].values / 1e3
    food_mod = mod_top["annual_food_savings_t"].values / 1e3

    ax_a.barh(y + bh / 2, food_max, bh,
              color=CLR_A_MAX, edgecolor="white", linewidth=0.5,
              label="Max uptake (95%)")
    ax_a.barh(y - bh / 2, food_mod, bh,
              color=CLR_A_MOD, edgecolor="white", linewidth=0.5,
              label="Mod uptake (50%)")

    offset_a = max(food_max) * 0.015
    for i in range(n):
        ax_a.text(food_max[i] + offset_a, y[i] + bh / 2,
                  f"{food_max[i]:,.0f}", va="center",
                  fontsize=7, color=CLR_A_MAX, fontweight="bold")
        ax_a.text(food_mod[i] + offset_a, y[i] - bh / 2,
                  f"{food_mod[i]:,.0f}", va="center",
                  fontsize=7, color="#4ea6a7", fontweight="bold")

    ax_a.set_yticks(y)
    ax_a.set_yticklabels(countries, fontsize=9)
    ax_a.set_xlabel("Emissions Saved (kt CO₂eq / year)", fontsize=10)
    ax_a.set_title("A.  Food-Emission Savings", fontsize=12, fontweight="bold",
                    loc="left", pad=10)
    ax_a.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )
    ax_a.invert_yaxis()
    ax_a.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax_a.set_axisbelow(True)
    ax_a.legend(fontsize=8, loc="lower right", framealpha=0.9)

    # ── Panel B: Person-years saved ───────────────────────────────────

    ax_b = fig.add_subplot(gs[1])

    py_max = max_top["total_person_years_saved"].values / 1e3
    py_mod = mod_top["total_person_years_saved"].values / 1e3

    ax_b.barh(y + bh / 2, py_max, bh,
              color=CLR_B_MAX, edgecolor="white", linewidth=0.5)
    ax_b.barh(y - bh / 2, py_mod, bh,
              color=CLR_B_MOD, edgecolor="white", linewidth=0.5)

    offset_b = max(py_max) * 0.015
    for i in range(n):
        ax_b.text(py_max[i] + offset_b, y[i] + bh / 2,
                  f"{py_max[i]:,.0f}", va="center",
                  fontsize=7, color=CLR_B_MAX, fontweight="bold")

    ax_b.set_yticks(y)
    ax_b.set_yticklabels([""] * n)
    ax_b.set_xlabel("Person-Years Saved (thousands, 10-yr)", fontsize=10)
    ax_b.set_title("B.  Person-Years Saved", fontsize=12, fontweight="bold",
                    loc="left", pad=10)
    ax_b.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )
    ax_b.invert_yaxis()
    ax_b.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax_b.set_axisbelow(True)

    # ── Panel C: Break-even ratio (log scale) ─────────────────────────

    ax_c = fig.add_subplot(gs[2])

    ratio_max = max_top["ratio_food_to_mort"].values
    ratio_mod = mod_top["ratio_food_to_mort"].values

    ax_c.barh(y + bh / 2, ratio_max, bh,
              color=CLR_C_MAX, edgecolor="white", linewidth=0.5,
              label="Max uptake")
    ax_c.barh(y - bh / 2, ratio_mod, bh,
              color=CLR_C_MOD, edgecolor="white", linewidth=0.5,
              label="Mod uptake")

    for i in range(n):
        if np.isfinite(ratio_max[i]) and ratio_max[i] > 0:
            ax_c.text(ratio_max[i] * 1.15, y[i] + bh / 2,
                      f"{ratio_max[i]:,.0f}×", va="center",
                      fontsize=7, color=CLR_C_MAX, fontweight="bold")

    ax_c.set_yticks(y)
    ax_c.set_yticklabels([""] * n)
    ax_c.set_xlabel("Food Savings ÷ Survivor Emissions (10-yr)", fontsize=10)
    ax_c.set_title("C.  Break-Even Ratio", fontsize=12, fontweight="bold",
                    loc="left", pad=10)
    ax_c.set_xscale("log")
    ax_c.axvline(x=1, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    ax_c.invert_yaxis()
    ax_c.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax_c.set_axisbelow(True)
    ax_c.legend(fontsize=8, loc="lower right", framealpha=0.9)

    fig.suptitle(
        "Semaglutide Impact Dashboard: Top Countries by Food-Emission Savings",
        fontsize=15, fontweight="bold", y=1.01,
    )

    out = output_path("country_dashboard.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"\nDashboard saved: {out}")
    return out


def plot_food_group_breakdown(food_by_group):
    """Stacked horizontal bars showing food-group composition of savings."""

    FOOD_COLORS = {
        "Meat": "#c1272d",
        "Dairy": "#f5a623",
        "Cereals": "#d4a74a",
        "Fish": "#4a90d9",
        "Eggs": "#7ecdc1",
        "Fats and oils": "#9b7ab8",
        "Fruit and vegetables": "#5cb85c",
        "Sweets, confectionery, and sweetened beverages": "#e07b91",
        "Other": "#8c8c8c",
    }

    max_up = food_by_group[food_by_group["scenario"] == "max_uptake"].copy()

    country_totals = (
        max_up.groupby(["ISO", "Country"])["carbon_savings_t"]
        .sum()
        .sort_values(ascending=False)
    )
    top_isos = country_totals.head(N_COUNTRIES).reset_index()["ISO"].tolist()

    pivot = (
        max_up[max_up["ISO"].isin(top_isos)]
        .pivot_table(
            index=["ISO", "Country"],
            columns="final_food_group",
            values="carbon_savings_t",
            fill_value=0,
        )
        / 1e3
    )

    country_order = (
        country_totals.head(N_COUNTRIES)
        .reset_index()
        .set_index("ISO")["Country"]
    )
    pivot = pivot.loc[
        [(iso, country_order[iso]) for iso in top_isos]
    ]

    fig, ax = plt.subplots(figsize=(14, max(6, N_COUNTRIES * 0.45)))

    y = np.arange(len(pivot))
    left = np.zeros(len(pivot))

    sorted_groups = pivot.sum().sort_values(ascending=False).index.tolist()

    for group in sorted_groups:
        if group not in pivot.columns:
            continue
        vals = pivot[group].values
        color = FOOD_COLORS.get(group, "#cccccc")
        ax.barh(y, vals, left=left, height=0.6, label=group, color=color,
                edgecolor="white", linewidth=0.3)
        left += vals

    ax.set_yticks(y)
    ax.set_yticklabels(
        [c for _, c in pivot.index.tolist()], fontsize=9
    )
    ax.set_xlabel("Carbon Emissions Saved (kt CO₂eq / year)", fontsize=10)
    ax.set_title(
        "Food-Group Breakdown of Emission Savings (Max Uptake, Top Countries)",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(
        fontsize=8, loc="lower right", framealpha=0.9,
        ncol=2, title="Food Group", title_fontsize=9,
    )

    out = output_path("food_group_breakdown.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Food-group breakdown saved: {out}")
    return out


def main():
    print("=" * 65)
    print("COUNTRY DASHBOARD — Combined Figure for Paper")
    print("=" * 65)

    dashboard, food_by_group = build_dashboard_data()

    print("\nGenerating dashboard (3-panel)...")
    plot_dashboard(dashboard, food_by_group)

    print("\nGenerating food-group breakdown...")
    plot_food_group_breakdown(food_by_group)

    # Print summary table
    max_up = dashboard[dashboard["scenario"] == "max_uptake"].copy()
    max_up = max_up.sort_values("annual_food_savings_t", ascending=False).head(
        N_COUNTRIES
    )

    print("\n" + "=" * 95)
    print(f"{'Country':30s}  {'Food Savings':>14s}  {'Person-Yrs':>12s}  "
          f"{'BE Ratio':>10s}")
    print(f"{'':30s}  {'(kt CO2/yr)':>14s}  {'(thousands)':>12s}  "
          f"{'(10-yr)':>10s}")
    print("-" * 95)
    for _, r in max_up.iterrows():
        ratio_str = (
            f"{r['ratio_food_to_mort']:10,.0f}×"
            if np.isfinite(r["ratio_food_to_mort"])
            else "       inf"
        )
        print(
            f"  {r['Country']:30s}  "
            f"{r['annual_food_savings_t']/1e3:12,.0f}  "
            f"{r['total_person_years_saved']/1e3:12,.0f}  "
            f"{ratio_str}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
