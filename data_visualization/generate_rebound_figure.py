"""
Rebound decomposition figure — analog of Hegwood et al. (2023) Figure 3.

3-row × 3-column grid:
  Rows:    Meat, Dairy, Cereals (top food groups by carbon impact)
  Columns: (A) Expected demand reduction, (B) Actual reduction after
           rebound, (C) Carbon emissions saved

Top countries shown per food group, ranked by max-uptake actual reduction.
The gap between columns A and B is the rebound effect.

Output: test/rebound_decomposition.png

Usage:
    python -m data_visualization.generate_rebound_figure
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from .pipeline import compute_food_savings, output_path

N_COUNTRIES = 12
FOOD_GROUPS = ["Meat", "Dairy", "Cereals"]

COL_COLORS = {
    "Meat":    ["#e06666", "#c1272d", "#8b1a1a"],
    "Dairy":   ["#f7c87b", "#f5a623", "#c07d14"],
    "Cereals": ["#e8cc7a", "#d4a74a", "#a67c2e"],
}
# Columns: A (expected) = lighter, B (actual) = mid, C (carbon) = darkest


def main():
    print("Building rebound decomposition figure...")
    _, result_df = compute_food_savings()

    max_up = result_df[result_df["scenario"] == "max_uptake"].copy()

    fig, axes = plt.subplots(
        len(FOOD_GROUPS), 3,
        figsize=(18, len(FOOD_GROUPS) * 4.5),
        gridspec_kw={"wspace": 0.35, "hspace": 0.45},
    )

    col_titles = [
        "A.  Expected Demand Reduction",
        "B.  Actual Reduction (after rebound)",
        "C.  Carbon Emissions Saved",
    ]
    col_units = [
        "Mt / year",
        "Mt / year",
        "kt CO\u2082eq / year",
    ]
    col_fields = [
        "expected_demand_reduction",
        "actual_reduction",
        "carbon_savings_t",
    ]

    for row_idx, food_group in enumerate(FOOD_GROUPS):
        fg_data = max_up[max_up["final_food_group"] == food_group].copy()

        fg_data["expected_demand_reduction"] = fg_data[
            "expected_demand_reduction"
        ].abs()
        fg_data["actual_reduction"] = fg_data["actual_reduction"].abs()
        fg_data["carbon_savings_t"] = fg_data["carbon_savings_t"].abs()

        country_rank = (
            fg_data.groupby("Country")["actual_reduction"]
            .sum()
            .sort_values(ascending=False)
        )
        top_countries = country_rank.head(N_COUNTRIES).index.tolist()
        top_countries.reverse()

        fg_top = fg_data[fg_data["Country"].isin(top_countries)].copy()
        agg = (
            fg_top.groupby("Country")[col_fields]
            .sum()
            .reindex(top_countries)
        )

        y = np.arange(len(top_countries))

        for col_idx in range(3):
            ax = axes[row_idx, col_idx]
            field = col_fields[col_idx]
            vals = agg[field].values / 1e3
            color = COL_COLORS.get(food_group, ["#aaa", "#888", "#555"])[col_idx]

            bars = ax.barh(
                y, vals, height=0.6,
                color=color, edgecolor="white", linewidth=0.4,
            )

            offset = max(vals) * 0.03 if max(vals) > 0 else 0.1
            for i, v in enumerate(vals):
                if v >= 100:
                    label = f"{v:,.0f}"
                elif v >= 1:
                    label = f"{v:,.1f}"
                else:
                    label = f"{v:,.2f}"
                ax.text(
                    v + offset, y[i], label,
                    va="center", fontsize=7, color="#333333",
                )

            ax.set_yticks(y)
            if col_idx == 0:
                ax.set_yticklabels(top_countries, fontsize=8)
            else:
                ax.set_yticklabels([""] * len(top_countries))

            ax.set_xlabel(col_units[col_idx], fontsize=9)

            if row_idx == 0:
                ax.set_title(col_titles[col_idx], fontsize=11,
                             fontweight="bold", pad=10)

            ax.grid(axis="x", alpha=0.2, linewidth=0.5)
            ax.set_axisbelow(True)
            ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
            )

        label_color = COL_COLORS.get(food_group, ["#aaa", "#888", "#555"])[1]
        axes[row_idx, 0].annotate(
            food_group,
            xy=(0, 0.5), xytext=(-0.35, 0.5),
            xycoords="axes fraction", textcoords="axes fraction",
            fontsize=13, fontweight="bold", color=label_color,
            ha="center", va="center", rotation=90,
        )

    # Add rebound annotation between columns A and B
    fig.text(
        0.38, 0.01,
        "Gap between A and B = rebound effect (price-induced consumption recovery)",
        ha="center", fontsize=10, style="italic", color="#555555",
    )

    fig.suptitle(
        "Rebound Decomposition by Food Group and Country (Max Uptake 95%)",
        fontsize=15, fontweight="bold", y=0.98,
    )

    out = output_path("rebound_decomposition.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")

    # Print rebound summary
    print("\nRebound summary (max uptake, top countries):")
    print(f"{'Food Group':15s}  {'Expected (kt)':>14s}  {'Actual (kt)':>12s}  "
          f"{'Rebound %':>10s}")
    print("-" * 55)
    for food_group in FOOD_GROUPS:
        fg = max_up[max_up["final_food_group"] == food_group]
        expected = fg["expected_demand_reduction"].abs().sum() / 1e3
        actual = fg["actual_reduction"].abs().sum() / 1e3
        rebound_pct = (1 - actual / expected) * 100 if expected > 0 else 0
        print(f"{food_group:15s}  {expected:14,.0f}  {actual:12,.0f}  "
              f"{rebound_pct:9.1f}%")

    # Copy to figures/
    import shutil
    fig_dest = output_path("rebound_decomposition.png").parent.parent / "figures"
    if fig_dest.exists():
        shutil.copy(str(out), str(fig_dest / "rebound_decomposition.png"))
        print(f"Copied to: {fig_dest / 'rebound_decomposition.png'}")


if __name__ == "__main__":
    main()
