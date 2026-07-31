"""
Produces a figure showing carbon emissions saved from food reduction
by country, for both moderate and maximum semaglutide uptake scenarios.

Output: figures/emissions_saved_by_country.png

Usage:
    python -m data_visualization.generate_emissions_figure
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from .pipeline import compute_food_savings, output_path


def main():
    food_savings, _ = compute_food_savings()

    # Restrict to countries with a computable saving, as every other consumer
    # does. Countries whose demand shock cannot be solved (no FAOSTAT price index)
    # carry NaN since min_count=1 landed; before that they carried exactly 0.0 and
    # were drawn as zero-length bars, which read as "this country saves nothing"
    # rather than "this country has no price data". Neither belongs in a chart of
    # emissions saved.
    country_totals = food_savings[food_savings["annual_food_savings_t"] > 0].copy()
    country_totals["carbon_savings_kt"] = country_totals["annual_food_savings_t"] / 1e3

    sort_order = (
        country_totals[country_totals["scenario"] == "max_uptake"]
        .sort_values("carbon_savings_kt", ascending=True)
        .set_index("Country")
        .index.tolist()
    )

    fig, ax = plt.subplots(figsize=(12, max(10, len(sort_order) * 0.28)))

    y = np.arange(len(sort_order))
    bar_height = 0.35

    max_vals, mod_vals = [], []
    for country in sort_order:
        max_row = country_totals[
            (country_totals["Country"] == country)
            & (country_totals["scenario"] == "max_uptake")
        ]
        mod_row = country_totals[
            (country_totals["Country"] == country)
            & (country_totals["scenario"] == "mod_uptake")
        ]
        max_vals.append(
            max_row["carbon_savings_kt"].values[0] if len(max_row) > 0 else 0
        )
        mod_vals.append(
            mod_row["carbon_savings_kt"].values[0] if len(mod_row) > 0 else 0
        )

    ax.barh(
        y + bar_height / 2, max_vals, bar_height,
        label="Maximum uptake (95%)", color="#2166ac",
        edgecolor="white", linewidth=0.5,
    )
    ax.barh(
        y - bar_height / 2, mod_vals, bar_height,
        label="Moderate uptake (50%)", color="#92c5de",
        edgecolor="white", linewidth=0.5,
    )

    ax.set_yticks(y)
    ax.set_yticklabels(sort_order, fontsize=7.5)
    ax.set_xlabel(
        "Carbon Emissions Saved in Year 1 (thousand tonnes CO₂eq)", fontsize=11
    )
    # Year 1, not a flat annual figure. The saving is survival-weighted, so it
    # declines each year as treated patients die, and year 1 is the largest year
    # of the series. Labelling it "annual" would imply a constant it is not.
    ax.set_title(
        "Carbon Emissions Saved from Reduced Food Consumption\n"
        "by Country and Uptake Scenario (year 1 of 10)",
        fontsize=13, fontweight="bold", pad=15,
    )
    ax.legend(loc="lower right", fontsize=10, framealpha=0.9)
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )
    ax.grid(axis="x", alpha=0.25, linewidth=0.5)
    ax.set_axisbelow(True)

    offset = max(max_vals) * 0.01
    for i in range(len(sort_order) - 1, max(len(sort_order) - 11, -1), -1):
        ax.text(
            max_vals[i] + offset, y[i] + bar_height / 2,
            f"{max_vals[i]:,.0f}",
            va="center", fontsize=6.5, color="#2166ac", fontweight="bold",
        )
        ax.text(
            mod_vals[i] + offset, y[i] - bar_height / 2,
            f"{mod_vals[i]:,.0f}",
            va="center", fontsize=6.5, color="#5a9ec4", fontweight="bold",
        )

    plt.tight_layout()
    out = output_path("emissions_saved_by_country.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()

    print(f"Figure saved: {out}\n")
    print("Top 10 countries by emissions saved (max uptake):")
    print(f"{'Country':30s}  {'Max (kt)':>10s}  {'Mod (kt)':>10s}")
    print("-" * 54)
    for i in range(len(sort_order) - 1, max(len(sort_order) - 11, -1), -1):
        print(f"{sort_order[i]:30s}  {max_vals[i]:10,.0f}  {mod_vals[i]:10,.0f}")

    total_max = sum(max_vals)
    total_mod = sum(mod_vals)
    print("-" * 54)
    print(f"{'TOTAL':30s}  {total_max:10,.0f}  {total_mod:10,.0f}")
    print(f"\nTotal: {total_max / 1e3:.1f} Mt (max) / {total_mod / 1e3:.1f} Mt (mod)")


if __name__ == "__main__":
    # Redirected stdout on Windows falls back to cp1252, which cannot encode the
    # non-ASCII this script prints. Set UTF-8 on the streams here rather than at
    # module level, so importing this module never mutates global stream state.
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    main()
