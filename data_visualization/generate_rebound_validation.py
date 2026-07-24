"""
Rebound validation figure — analog of Hegwood et al. (2023) Figure 4a.

Grouped horizontal bar chart showing computed rebound effect (%)
by food type and World Bank income group, validating that our
semaglutide demand-shock model produces rebound percentages
consistent with Hegwood's FLW framework.

Output: figures/rebound_by_income.png

Usage:
    python -m data_visualization.generate_rebound_validation
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .pipeline import compute_food_savings, output_path, ROOT

FOOD_ORDER = [
    "Cereals",
    "Fruit and vegetables",
    "Meat",
    "Dairy",
    "Fish",
    "Eggs",
    "Fats and oils",
    "Other",
    "Sweets, confectionery, and sweetened beverages",
]

FOOD_LABELS = {
    "Cereals": "Cereals",
    "Fruit and vegetables": "Fruits and\nvegetables",
    "Meat": "Meat",
    "Dairy": "Milk / Dairy",
    "Fish": "Fish",
    "Eggs": "Eggs",
    "Fats and oils": "Fats and oils",
    "Other": "Other",
    "Sweets, confectionery, and sweetened beverages": "Sweets /\nconfectionery",
}

FOOD_COLORS = {
    "Cereals": "#d4a74a",
    "Fruit and vegetables": "#5cb85c",
    "Meat": "#c1272d",
    "Dairy": "#f5a623",
    "Fish": "#4a90d9",
    "Eggs": "#7ecdc1",
    "Fats and oils": "#9b7ab8",
    "Other": "#8c8c8c",
    "Sweets, confectionery, and sweetened beverages": "#e07b91",
}

INCOME_LABELS = {
    "H": "High income",
    "UM": "Upper-middle income",
    "LM": "Lower-middle income",
    "L": "Low income",
}
INCOME_ORDER = ["H", "UM", "LM", "L"]
INCOME_COLORS = {
    "H": "#4393c3",
    "UM": "#92c5de",
    "LM": "#f4a582",
    "L": "#d6604d",
}


def load_income_groups():
    """Load World Bank income classification (2022 column)."""
    wb = pd.read_excel(ROOT / "legacy" / "data" / "Worldbank_incomes_cleaned.xlsx")
    income = wb[["ISO", 2022]].copy()
    income.columns = ["ISO", "income_group"]
    income = income.dropna(subset=["income_group"])
    income = income[income["income_group"].isin(INCOME_ORDER)]
    return income


def main():
    print("Building rebound validation figure...")

    _, result_df = compute_food_savings()

    max_up = result_df[result_df["scenario"] == "max_uptake"].copy()

    income = load_income_groups()
    max_up = pd.merge(max_up, income, on="ISO", how="left")
    max_up = max_up.dropna(subset=["income_group", "rebound_effect_percent"])

    # Filter to valid rebound values (between 0 and 1)
    valid = max_up[
        (max_up["rebound_effect_percent"] >= 0)
        & (max_up["rebound_effect_percent"] <= 1)
    ].copy()

    # Compute mean rebound % per food group × income group
    rebound_summary = (
        valid.groupby(["final_food_group", "income_group"])["rebound_effect_percent"]
        .mean()
        .unstack(fill_value=np.nan)
        * 100
    )

    # Filter to food groups with enough data
    food_groups_present = [
        fg for fg in FOOD_ORDER
        if fg in rebound_summary.index and rebound_summary.loc[fg].notna().any()
    ]

    income_groups_present = [
        ig for ig in INCOME_ORDER if ig in rebound_summary.columns
    ]

    n_food = len(food_groups_present)
    n_income = len(income_groups_present)

    fig, ax = plt.subplots(figsize=(10, max(5, n_food * 0.9)))

    y = np.arange(n_food)
    total_height = 0.7
    bar_height = total_height / n_income

    if n_income == 1:
        # All countries are same income group — color by food group instead
        ig = income_groups_present[0]
        vals = []
        bar_colors = []
        for fg in food_groups_present:
            v = rebound_summary.loc[fg, ig] if ig in rebound_summary.columns else np.nan
            vals.append(v if not np.isnan(v) else 0)
            bar_colors.append(FOOD_COLORS.get(fg, "#999999"))

        bars = ax.barh(
            y, vals, 0.6,
            color=bar_colors, edgecolor="white", linewidth=0.5,
        )

        for i, v in enumerate(vals):
            if v > 0:
                ax.text(
                    v + 0.8, y[i], f"{v:.0f}%",
                    va="center", fontsize=9, color="#333333",
                    fontweight="bold",
                )
    else:
        for j, ig in enumerate(income_groups_present):
            vals = []
            for fg in food_groups_present:
                v = rebound_summary.loc[fg, ig] if ig in rebound_summary.columns else np.nan
                vals.append(v if not np.isnan(v) else 0)

            y_pos = y + (j - n_income / 2 + 0.5) * bar_height

            bars = ax.barh(
                y_pos, vals, bar_height * 0.9,
                color=INCOME_COLORS[ig], edgecolor="white", linewidth=0.5,
                label=INCOME_LABELS[ig],
            )

            for i, v in enumerate(vals):
                if v > 0:
                    ax.text(
                        v + 0.8, y_pos[i], f"{v:.0f}%",
                        va="center", fontsize=8, color="#333333",
                    )

    ax.set_yticks(y)
    ax.set_yticklabels(
        [FOOD_LABELS.get(fg, fg) for fg in food_groups_present],
        fontsize=10,
    )
    ax.set_xlabel("Rebound (%)", fontsize=11)
    ax.set_xlim(0, 85)
    ax.set_title(
        "Rebound Effect by Food Type and Income Group (Max Uptake 95%)\n"
        "Validation against Hegwood et al. (2023) Figure 4a",
        fontsize=12, fontweight="bold", pad=12,
    )
    ax.axvline(x=50, color="gray", linestyle=":", linewidth=0.8, alpha=0.5)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax.set_axisbelow(True)
    if n_income > 1:
        ax.legend(fontsize=9, loc="lower right", framealpha=0.9)

    plt.tight_layout()
    fig.subplots_adjust(bottom=0.14)

    # Place annotations below the plot, outside the axes
    fig.text(
        0.98, 0.025,
        f"All {n_food} food groups: {INCOME_LABELS[income_groups_present[0]]}   |   "
        f"Hegwood et al. (2023) high-income range: 53\u201371%",
        ha="right", va="bottom", fontsize=9, style="italic", color="#666666",
    )
    out = output_path("rebound_by_income.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")

    # Print summary table
    print("\nRebound % by food type and income group:")
    print(f"{'Food Group':30s}", end="")
    for ig in income_groups_present:
        print(f"  {INCOME_LABELS[ig]:>20s}", end="")
    print()
    print("-" * (30 + 22 * n_income))
    for fg in food_groups_present:
        print(f"{fg:30s}", end="")
        for ig in income_groups_present:
            v = rebound_summary.loc[fg, ig] if ig in rebound_summary.columns else np.nan
            if np.isnan(v):
                print(f"  {'n/a':>20s}", end="")
            else:
                print(f"  {v:19.1f}%", end="")
        print()

    # Copy to figures/
    import shutil
    fig_dest = ROOT / "figures"
    dest = fig_dest / "rebound_by_income.png"
    if fig_dest.exists() and out.resolve() != dest.resolve():
        shutil.copy(str(out), str(dest))
        print(f"\nCopied to: {dest}")


if __name__ == "__main__":
    main()
