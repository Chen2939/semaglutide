"""
Rebound decomposition figure — analog of Hegwood et al. (2023) Figure 3.

One row per food group, three columns:
  Columns: (A) Expected demand reduction, (B) Actual reduction after
           rebound, (C) Carbon emissions saved

**Every food group is shown.** The figure used to carry a hardcoded
``["Meat", "Dairy", "Cereals"]``, and no rule reproduced that set: Meat and
Dairy are 1st and 2nd by year-1 carbon savings, but Cereals is 5th, behind Fish
and Other, and ranking by tonnage instead gives a different three again. Rather
than caption an editorial choice, the choice is removed. Rows are ordered by
descending year-1 max-uptake carbon savings, which is a rule and is stated.

Top countries shown per food group, ranked by max-uptake actual reduction.
The gap between columns A and B is the rebound effect.

Columns A and B share one x-limit within each row, so that gap is a visible
length rather than a number the reader has to subtract. The limit is per row --
the food groups span more than an order of magnitude -- and column C, in kt
CO2eq rather than Mt of food, keeps its own scale.

Built at final print dimensions (183 mm double-column) with real point sizes.
See ``figure_style`` for why, and for why this does not save with
``bbox_inches="tight"``.

Output: figures/rebound_decomposition.png

Usage:
    python -m data_visualization.generate_rebound_figure
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from .pipeline import compute_food_savings, output_path
from .figure_style import (
    DOUBLE_COLUMN_IN,
    DPI,
    PT,
    display_countries,
    display_food_group,
    food_group_shades,
    mm,
)

# Countries per row: 6, down from 12.
#
# Nine rows at twelve countries is 108 bars per column, which needs about
# 320 mm of height at a legible row pitch -- two pages. Six holds the whole
# figure at 219 mm, inside the 230 mm a page with a caption allows, at a row
# pitch of 2.9 mm with 6 pt labels.
#
# Six costs less than the arithmetic suggests: because the same large countries
# lead most groups, N=6 names 12 distinct countries across the nine rows and
# N=8 names only 13. The tail that N=12 would add is mostly repetition of
# countries already visible in another row.
N_COUNTRIES = 6

# Column colours are derived from each group's base colour (light / mid / dark)
# rather than hand-picked per group, so the nine rows are consistent and the
# three original rows keep the look they had.
# Columns: A (expected) = lighter, B (actual) = mid, C (carbon) = darkest

# ── Print geometry ────────────────────────────────────────────────────
# Everything is fixed here so the saved PNG is exactly the designed size and
# the point sizes above are the point sizes on the page.
FIG_W_IN = DOUBLE_COLUMN_IN          # 183 mm
ROW_AXES_IN = 0.678                  # per-row axes height
ROW_GAP_IN = 0.200                   # vertical gap: x tick labels plus air
COL_GAP_IN = 0.200                   # horizontal gap between panels
TOP_IN = 0.450                       # suptitle plus column titles
BOTTOM_IN = 0.450                    # tick labels, x label, footnote
LEFT_IN = 1.045                      # country labels plus the rotated row label
# The last x tick sits on the right spine and its label is centred there, so
# half of it hangs outside the axes. At 0.036 in of pad, column C's "2,000" came
# out as "2,00".
RIGHT_PAD_IN = 0.170
ROW_LABEL_OFFSET_IN = 0.80           # rotated group label, left of panel A


def _tick_decimals(ticks):
    """Fewest decimals that render every tick faithfully.

    Columns A and B are Mt/year and peak below 4, so the locator picks
    fractional ticks; a fixed 0-decimal format collapsed them to 0/1. Too few
    decimals is not only ambiguous but wrong -- 0.25 would print as "0.2".
    """
    for d in range(7):
        if all(abs(float(f"{t:.{d}f}") - t) < 1e-9 for t in ticks):
            return d
    return 6


def food_group_order(max_up: pd.DataFrame) -> list[str]:
    """Every food group present, ordered by descending year-1 carbon savings.

    This is the selection rule, and it is a rule rather than a list: whatever
    groups the pipeline emits is what the figure shows, in an order derived from
    the data it is plotting. The count is reported on every run.
    """
    return (
        max_up.groupby("final_food_group")["carbon_savings_t"]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .index.tolist()
    )


def main():
    print("Building rebound decomposition figure...")
    _, result_df = compute_food_savings()

    max_up = result_df[result_df["scenario"] == "max_uptake"].copy()
    food_groups = food_group_order(max_up)
    n_rows = len(food_groups)
    print(f"  Food groups: {n_rows} (all present), ordered by year-1 carbon savings")
    print(f"  Countries per row: {N_COUNTRIES}")

    fig_h_in = (
        n_rows * ROW_AXES_IN + (n_rows - 1) * ROW_GAP_IN + TOP_IN + BOTTOM_IN
    )
    axes_w_in = (
        FIG_W_IN - LEFT_IN - RIGHT_PAD_IN - 2 * COL_GAP_IN
    ) / 3

    fig, axes = plt.subplots(
        n_rows, 3,
        figsize=(FIG_W_IN, fig_h_in),
        gridspec_kw={
            "left": LEFT_IN / FIG_W_IN,
            "right": 1 - RIGHT_PAD_IN / FIG_W_IN,
            "top": 1 - TOP_IN / fig_h_in,
            "bottom": BOTTOM_IN / fig_h_in,
            "wspace": COL_GAP_IN / axes_w_in,
            "hspace": ROW_GAP_IN / ROW_AXES_IN,
        },
    )

    # Each column title has to fit its own 47 mm axes at 7.5 pt bold, or it
    # spills into the neighbouring column's title. "Actual Reduction (after
    # rebound)" did; the footnote carries the rebound explanation anyway.
    col_titles = [
        "A.  Expected Demand Reduction",
        "B.  Actual (after rebound)",
        "C.  Carbon Emissions Saved",
    ]
    col_units = [
        "Mt / year",
        "Mt / year",
        "kt CO₂eq / year",
    ]
    col_fields = [
        "expected_demand_reduction",
        "actual_reduction",
        "carbon_savings_t",
    ]

    for row_idx, food_group in enumerate(food_groups):
        fg_data = max_up[max_up["final_food_group"] == food_group].copy()

        fg_data["expected_demand_reduction"] = fg_data[
            "expected_demand_reduction"
        ].abs()
        fg_data["actual_reduction"] = fg_data["actual_reduction"].abs()
        fg_data["carbon_savings_t"] = fg_data["carbon_savings_t"].abs()

        # ORDERING RULE, one per row, applied to all three panels in that row:
        # countries are selected and ranked by DESCENDING panel B value (actual
        # reduction after rebound), then reversed so the largest sits at the top
        # of the horizontal bars. `agg` is reindexed onto that single order and
        # `y` is shared, so A, B and C cannot disagree.
        #
        # Panel B, not panel A. A row is therefore not monotonic in column A --
        # in Meat, Saudi Arabia sits below Romania on the A value. That is the
        # rule working, not a defect: ranking by the post-rebound quantity is
        # what makes the A-to-B gap comparable down the column.
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

        # Shared x-limit for panels A and B within this row, taken from the row's
        # panel A maximum. Independent per-panel limits were the substantive
        # defect: US meat draws 1.02 in A and 0.53 in B as bars of near-identical
        # length, so the figure's whole claim -- that the A-to-B gap IS the
        # rebound -- was invisible. Panel C keeps its own scale; it is kt CO2eq,
        # not Mt of food.
        #
        # Per row, not globally. The nine groups span more than an order of
        # magnitude and one scale across all of them would flatten most rows.
        #
        # Panel A dominates panel B elementwise (the rebound recovers
        # consumption, so |actual| < |expected|), so the A-derived limit cannot
        # clip a B bar.
        row_a_max = float(np.nanmax(agg[col_fields[0]].values)) / 1e3

        shades = food_group_shades(food_group)

        for col_idx in range(3):
            ax = axes[row_idx, col_idx]
            field = col_fields[col_idx]
            vals = agg[field].values / 1e3
            color = shades[col_idx]

            ax.barh(
                y, vals, height=0.62,
                color=color, edgecolor="white", linewidth=0.3,
            )

            vmax = max(vals)
            # Columns A and B are drawn on the row's shared basis; column C on
            # its own. Everything downstream that scales with the axis -- the
            # label offset, the headroom, the tick range fed to _tick_decimals --
            # keys off `basis`, so the three stay consistent.
            basis = row_a_max if col_idx < 2 else vmax
            offset = basis * 0.03 if basis > 0 else 0.1
            for i, v in enumerate(vals):
                if v >= 100:
                    label = f"{v:,.0f}"
                elif v >= 1:
                    label = f"{v:,.1f}"
                else:
                    label = f"{v:,.2f}"
                ax.text(
                    v + offset, y[i], label,
                    va="center", fontsize=PT["value_small"], color="#333333",
                )

            # Headroom past the longest bar so its value label clears the right
            # spine. Without this the top label is drawn across the frame.
            if basis > 0:
                ax.set_xlim(0, basis * 1.24)

            ax.set_yticks(y)
            if col_idx == 0:
                ax.set_yticklabels(
                    display_countries(top_countries), fontsize=PT["country"]
                )
            else:
                ax.set_yticklabels([""] * len(top_countries))
            ax.tick_params(axis="both", labelsize=PT["tick"], pad=1.5,
                           length=2, width=0.4)

            # One x label per column, on the bottom row only. The units are a
            # property of the column, not of the row, and nine repetitions of
            # "Mt / year" cost about 20 mm of page height.
            if row_idx == n_rows - 1:
                ax.set_xlabel(col_units[col_idx], fontsize=PT["axis_label"],
                              labelpad=2)

            if row_idx == 0:
                ax.set_title(col_titles[col_idx], fontsize=PT["panel_title"],
                             fontweight="bold", pad=4)

            ax.grid(axis="x", alpha=0.2, linewidth=0.4)
            ax.set_axisbelow(True)
            for spine in ax.spines.values():
                spine.set_linewidth(0.5)
            # steps= keeps ticks on decimal-friendly values (0.2 / 0.5 / 5000,
            # never 0.15 / 0.25), then the decimals come from the ticks this
            # axis actually got rather than a single format for all panels.
            # nbins is 4 at print width: the six ticks that suited a 483 mm
            # build collide at 183 mm.
            locator = mticker.MaxNLocator(nbins=4, steps=[1, 2, 5, 10])
            ax.xaxis.set_major_locator(locator)
            # `basis`, not `vmax`: the decimals have to be derived from the ticks
            # the axis ACTUALLY gets, and under the shared limit panel B's axis
            # runs to the row's A max, not to its own.
            hi = basis * 1.24 if basis > 0 else 1.0
            decimals = _tick_decimals(
                [t for t in locator.tick_values(0.0, hi) if 0.0 <= t <= hi]
            )
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _, d=decimals: f"{x:,.{d}f}")
            )

        axes[row_idx, 0].annotate(
            display_food_group(food_group),
            xy=(0, 0.5),
            xytext=(-ROW_LABEL_OFFSET_IN / axes_w_in, 0.5),
            xycoords="axes fraction", textcoords="axes fraction",
            fontsize=PT["row_label"], fontweight="bold", color=shades[2],
            ha="center", va="center", rotation=90,
            annotation_clip=False,
        )

    # Add rebound annotation between columns A and B
    fig.text(
        0.5, 0.006,
        "Gap between A and B = rebound effect (price-induced consumption recovery)",
        ha="center", fontsize=PT["note"], style="italic", color="#555555",
    )

    fig.suptitle(
        "Rebound Decomposition by Food Group and Country (Max Uptake 95%)",
        fontsize=PT["suptitle"], fontweight="bold",
        y=1 - 0.10 / fig_h_in, va="top",
    )

    out = output_path("rebound_decomposition.png")
    # No bbox_inches="tight": it recomputes the bounding box at save time, which
    # would make the saved PNG a different size from the one the point sizes
    # were chosen for. Margins are set explicitly on the GridSpec instead.
    plt.savefig(str(out), dpi=DPI)
    plt.close()
    print(f"Saved: {out}")
    print(f"  Figure: {mm(FIG_W_IN):.1f} x {mm(fig_h_in):.1f} mm at {DPI} dpi")

    # Print rebound summary
    print("\nRebound summary (max uptake, all countries):")
    print(f"{'Food Group':50s}  {'Expected (kt)':>14s}  {'Actual (kt)':>12s}  "
          f"{'Rebound %':>10s}")
    print("-" * 92)
    for food_group in food_groups:
        fg = max_up[max_up["final_food_group"] == food_group]
        expected = fg["expected_demand_reduction"].abs().sum() / 1e3
        actual = fg["actual_reduction"].abs().sum() / 1e3
        rebound_pct = (1 - actual / expected) * 100 if expected > 0 else 0
        print(f"{food_group:50s}  {expected:14,.1f}  {actual:12,.1f}  "
              f"{rebound_pct:9.1f}%")


if __name__ == "__main__":
    main()
