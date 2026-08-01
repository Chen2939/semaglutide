"""
Combined two-panel emissions waterfall figure.

Stacks the two waterfall variants into a single image:

  Panel A (top)    — no-mortality counterfactual: an annual rate with all three
                     mortality channels off (food-side pi, pharmaceutical-side
                     pi_dose, survivor emissions), full 53-country food-data
                     sample (from ``generate_waterfall_1yr_figure``).
  Panel B (bottom) — 10-year cumulative, includes survivorship, 35-country OECD
                     complete-data subset (from ``generate_waterfall_figure``).

Each panel keeps its own y-axis scale. The two panels are not the same quantity
over different horizons, so the y-axis labels carry the distinction: Panel A is
a per-year rate with mortality excluded, Panel B a 10-year cumulative total with
survivorship included, visible as its extra downward step. Panel A's label must
not imply elapsed time -- it is a rate under a counterfactual, not a year of the
modelled series.

Styling matches the standalone figures: red reduction labels, no callout
arrows, full panel border, no per-panel title (only the A/B labels).

Output:
  figures/global_emissions_waterfall_combined.png

Usage:
    python -m data_visualization.generate_waterfall_combined_figure
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .generate_waterfall_figure import compute_waterfall_components as compute_10yr
from .generate_waterfall_1yr_figure import compute_waterfall_components as compute_1yr
from .pipeline import output_path


# Muted publication palette (shared with both standalone figures)
COLOR_START = "#4C72B0"
COLOR_DECREASE = "#C44E52"
COLOR_NET = "#55A868"


def draw_waterfall(ax, components: pd.DataFrame, ylabel: str, panel_label: str) -> None:
    """Draw a single continuous bridge chart onto ``ax``."""
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
    colors = [
        COLOR_START if k == "increase" else COLOR_DECREASE if k == "decrease" else COLOR_NET
        for k in kinds
    ]

    x = np.arange(len(labels))
    ax.bar(
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
        y = levels[i][0] if kinds[i] == "decrease" else levels[i][1]
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
    ax.set_ylabel(ylabel, fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(0, max(hi for _, hi in levels) * 1.16)
    ax.tick_params(axis="both", labelsize=9)
    ax.grid(axis="y", color="#d0d0d0", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    ax.text(
        -0.08,
        1.05,
        panel_label,
        transform=ax.transAxes,
        fontsize=15,
        fontweight="bold",
        va="top",
        ha="left",
    )


def plot_combined() -> str:
    comp_a = compute_1yr()
    comp_b = compute_10yr()

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": True,
            "axes.spines.right": True,
            "axes.linewidth": 0.8,
        }
    )

    fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(9.5, 11.2))
    draw_waterfall(ax_a, comp_a, "Mt CO$_2$eq per year, mortality effects excluded", "A")
    draw_waterfall(ax_b, comp_b, "Mt CO$_2$eq over 10 years", "B")

    fig.tight_layout(h_pad=3.0)
    out = output_path("global_emissions_waterfall_combined.png")
    fig.savefig(str(out), dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(out)


def main() -> None:
    print("Building combined two-panel emissions waterfall (A: 1-year/53; B: 10-year/35)...")
    fig_path = plot_combined()
    print(f"Saved figure: {fig_path}")


if __name__ == "__main__":
    main()
