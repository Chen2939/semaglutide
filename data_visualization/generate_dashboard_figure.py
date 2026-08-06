"""
Country Dashboard — combined multi-panel figure for paper.

Inspired by Nature Food series (Hegwood et al., 2023) "sprawling visuals."

  Panel A: t = 0 food-emission savings PER PATIENT, net of the pharmaceutical
           manufacturing charge. Intensive.
  Panel B: Person-years saved from reduced mortality, absolute. Extensive.
  Panel C: Break-even ratio (food savings / survivor emissions, 10-year) for
           every complete-data country, with a carbon-intensity range.

**Panel A is on the unweighted t = 0 basis; panels B and C are not.** Panel A
illustrates the manuscript's headline annual figures, and those are quoted on
the instantaneous basis that `scripts/build_supplement_table.py` produces with
`survival_weighted=False` -- 54.2 / 27.8 Mt after rebound. A panel illustrating
them has to share their basis, so panel A takes a second pipeline call with
weighting off. pi(0) == 1 by construction, so no survival weight enters panel A
on either the food side or the drug side. Panels B and C are cumulative 10-year
quantities and stay survival-weighted, which is correct for them.

**Panels A and B do not cover the same countries as panel C, and the caption
must say so.** A and B show the fifteen leading countries by absolute year-1
savings; C shows the full complete-data set (positive food savings, positive
survivor emissions, finite ratio), derived at runtime.

A and B share a y-axis and a country order, so a reader can track a country
between them. Panel A is deliberately per-patient: as an absolute it was a
population ranking that duplicated panel B.

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
from .breakeven_analysis import compute_breakeven, _complete_data_subset
from .drug_footprint import build_drug_emissions
from .figure_style import (
    DOUBLE_COLUMN_IN,
    DPI,
    FOOD_GROUP_COLORS,
    PT,
    display_countries,
    mm,
)

# ── Print geometry ────────────────────────────────────────────────────
# Fixed so the saved PNG is exactly the designed size and the point sizes in
# figure_style are the point sizes on the page. See figure_style for why this
# module does not save with bbox_inches="tight".
FIG_W_IN = DOUBLE_COLUMN_IN          # 183 mm
FIG_H_IN = 6.60                      # 168 mm -- set by panel C's 40 rows
LEFT_IN = 0.610                      # A/B country labels
# Half of the last x tick label hangs outside the axes, so the pad has to cover
# it or panel C's "6" is sliced down the middle.
RIGHT_PAD_IN = 0.120
TOP_IN = 0.560                       # suptitle, panel title, annotation header
BOTTOM_IN = 0.300                    # tick labels and x label
ROW_GAP_IN = 0.600                   # A's x label, A's legend, B's title
COL_GAP_IN = 0.980                   # A's annotation column + C's country labels
ANNOTATION_COL_IN = 0.300            # of COL_GAP_IN, reserved for the totals

# ── Color palette — each panel has its own color family ───────────────

CLR_A_MAX = "#0d7e83"    # teal (food-emission savings)
CLR_A_MOD = "#7bc8c9"
CLR_B_MAX = "#6a3d9a"    # purple (person-years saved)
CLR_B_MOD = "#b5a4d4"
CLR_C_MAX = "#e66101"    # amber (break-even ratio)
CLR_C_MOD = "#f5b97a"

N_COUNTRIES = 15

# Panel C's whisker endpoints. Read, never recomputed: these are the all-food
# P10 and P90 carbon-intensity specifications from the sensitivity overview, and
# re-deriving them here would put a second producer of a published number in the
# tree.
SENSITIVITY_RATIOS = "all_sensitivity_overview_country_ratios.csv"

# Deliberately NOT in the whisker: the combined-conservative case and the
# diet-shift scenarios. Those are stress tests, not draws from a distribution --
# combined-conservative in particular is a joint tail with no symmetric
# counterpart -- so plotting them as range endpoints would tell the reader they
# are plausible outcomes. They belong in the text and the supplement table. A
# stacked optimistic specification, if one is ever added, goes to the same table
# and not to this whisker.


def build_dashboard_data():
    """Merge food savings, mortality, break-even, drug and sensitivity data.

    Returns ``(dashboard, food_by_group, complete_isos, panel_a_isos)``.

    Two country sets, deliberately different, and the caption must say so:

    * ``complete_isos`` -- panel C. Derived from ``_complete_data_subset``, the
      same filter every headline aggregate in this repository uses: positive
      food savings, positive survivor emissions, finite ratio. Currently 40.
    * ``panel_a_isos`` -- panels A and B. The leading 15 of the food-data
      universe, which is positive food savings and nothing else, with no
      survivor-data requirement. The universe is currently 53.

    Neither number is hardcoded; both are reported on every run.
    """
    print("[1/6] Running Price Rebound pipeline (survival-weighted)...")
    food_savings, result_df = compute_food_savings()

    # Second call, different basis. Panel A only. Not a duplicate of the call
    # above: pi is forced to 1, so this is the instantaneous t = 0 shock rather
    # than year 1 of a declining series, and it is the basis the manuscript's
    # annual figures are quoted on.
    print("[2/6] Running Price Rebound pipeline (unweighted, t=0)...")
    food_t0, _ = compute_food_savings(survival_weighted=False)

    print("[3/6] Loading mortality data...")
    mort = load_mortality_emissions()

    print("[4/6] Computing break-even ratios...")
    be_df = compute_breakeven(food_savings, mort)

    print("[5/6] Loading treated-user headcounts...")
    # THE denominator for panel A. ``treated_users_initial`` is the
    # population-weighted headcount of ADHERERS -- sim[adheres_to_treatment]
    # grouped and summed on ``weighting`` -- which is the identical expression
    # pipeline.py uses for ``pop_treated``. So the adherer/treated-user
    # distinction that would make a mixed denominator a defect does not arise in
    # this model: the drug charge is already levied per adherer, and the food
    # term and the drug term are divided by the same headcount by construction.
    #
    # ``drug_emissions_1yr_t`` is taken alongside it, NOT
    # ``drug_emissions_t_Y1``. The 1yr column is `initial_users x 5.38 kg` with
    # no survival applied, and generate_waterfall_1yr_figure documents it as
    # correct exactly where the food side is also unweighted. Panel A is now
    # that case. Pairing the pi_dose-weighted column against an unweighted food
    # side would be the mismatch that column comment exists to prevent.
    treated = build_drug_emissions()[
        ["ISO", "scenario", "treated_users_initial", "drug_emissions_1yr_t"]
    ]

    print("[6/6] Loading carbon-intensity sensitivity ratios...")
    sens = pd.read_csv(output_path(SENSITIVITY_RATIOS))[
        ["ISO", "baseline_mean_ci", "baseline_p10_ci", "baseline_p90_ci"]
    ]

    # Extract person-years saved from mortality CSV
    person_years = mort[
        ["ISO", "scenario", "total_person_years_saved"]
    ].copy()

    # Merge all three into one frame
    dashboard = pd.merge(
        food_savings, person_years, on=["ISO", "scenario"], how="inner"
    )
    # ``annual_food_savings_t`` already exists on food_savings as the year-1
    # GROSS saving, and break-even publishes a same-named column that is net of
    # the drug charge. Renaming on the way in keeps the two apart; a plain merge
    # would suffix them _x/_y and leave which is which to the reader.
    dashboard = pd.merge(
        dashboard,
        be_df[["ISO", "scenario", "ratio_food_to_mort",
               "total_food_savings_10yr", "total_survivor_emissions_10yr",
               "annual_food_savings_gross_t", "annual_drug_emissions_t",
               "annual_food_savings_t"]].rename(
            columns={"annual_food_savings_t": "annual_food_savings_net_t"}
        ),
        on=["ISO", "scenario"], how="left",
    )
    dashboard = pd.merge(dashboard, treated, on=["ISO", "scenario"], how="left")
    # Merged on ISO alone: the sensitivity overview is a max-uptake table, and
    # panel C's whisker is a max-uptake quantity. The columns are attached to
    # both scenario rows but only ever read off the max-uptake ones.
    dashboard = pd.merge(dashboard, sens, on="ISO", how="left")
    # Panel A's numerator, on the t = 0 basis. Renamed on the way in so it can
    # never be confused with the survival-weighted column of the same name that
    # panels B and C's ranking and filters use.
    dashboard = pd.merge(
        dashboard,
        food_t0[["ISO", "scenario", "annual_food_savings_t"]].rename(
            columns={"annual_food_savings_t": "food_savings_t0_t"}
        ),
        on=["ISO", "scenario"], how="left",
    )

    complete_isos = _complete_data_subset(be_df, scenario="max_uptake")["ISO"].tolist()

    # Panels A and B: the food-data universe, which is the positive-food-savings
    # filter with NO survivor-data requirement, then its leading 15 by absolute
    # t = 0 saving. Derived, not listed.
    universe = food_t0[
        (food_t0["scenario"] == "max_uptake")
        & (food_t0["annual_food_savings_t"] > 0)
    ].sort_values("annual_food_savings_t", ascending=False)
    panel_a_isos = universe.head(N_COUNTRIES)["ISO"].tolist()
    print(f"      food-data universe N = {len(universe)}; "
          f"complete-data set N = {len(complete_isos)}")

    # Food-group breakdown for stacked bars
    food_by_group = (
        result_df.groupby(["ISO", "Country", "scenario", "final_food_group"])[
            "carbon_savings_t"
        ]
        .sum()
        .abs()
        .reset_index()
    )

    return dashboard, food_by_group, complete_isos, panel_a_isos


def plot_dashboard(dashboard, food_by_group, complete_isos, panel_a_isos):
    """Generate the 3-panel country dashboard figure.

    Layout: A and B stacked in the left column, C given its own full-height
    column on the right. Panel C carries 40 rows against A and B's 15, so C sets
    the figure height; spanning C across the full width beneath them instead
    would make each of its forty bars a hairline running the width of the page.
    """

    max_up = dashboard[dashboard["scenario"] == "max_uptake"].copy()
    mod_up = dashboard[dashboard["scenario"] == "mod_uptake"].copy()

    # Panels A and B: the leading countries by ABSOLUTE t = 0 savings, derived
    # in build_dashboard_data. Panel A is ordered by the absolute quantity, not
    # by its own per-patient values, so it reads as an explanation of the
    # absolute ranking rather than an unrelated second one.
    top_isos = panel_a_isos

    max_top = max_up[max_up["ISO"].isin(top_isos)].set_index("ISO").loc[top_isos]
    mod_top = mod_up[mod_up["ISO"].isin(top_isos)].set_index("ISO").reindex(top_isos)

    countries = max_top["Country"].tolist()
    n = len(countries)
    y = np.arange(n)
    bh = 0.35

    # Panel C: every complete-data country, sorted ascending by baseline
    # max-uptake ratio so the binding cases (Hungary, Lithuania) sit at the top
    # of the panel where the eye lands first.
    c_df = (
        max_up[max_up["ISO"].isin(complete_isos)]
        .sort_values("ratio_food_to_mort", ascending=True)
        .reset_index(drop=True)
    )
    nc = len(c_df)
    yc = np.arange(nc)

    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN))
    # Margins in inches, converted, so the saved PNG is exactly 183 mm wide.
    # COL_GAP_IN has to clear two things at once: panel A's annotation column,
    # which hangs off A's right spine, and panel C's country labels, which hang
    # off C's left. ROW_GAP_IN has to clear panel A's x label and its legend
    # above panel B's title.
    _axes_w = (FIG_W_IN - LEFT_IN - RIGHT_PAD_IN - COL_GAP_IN) / 2
    _axes_h = (FIG_H_IN - TOP_IN - BOTTOM_IN - ROW_GAP_IN) / 2
    gs = GridSpec(
        2, 2, figure=fig,
        width_ratios=[1.45, 1], height_ratios=[1, 1],
        left=LEFT_IN / FIG_W_IN, right=1 - RIGHT_PAD_IN / FIG_W_IN,
        top=1 - TOP_IN / FIG_H_IN, bottom=BOTTOM_IN / FIG_H_IN,
        wspace=COL_GAP_IN / _axes_w, hspace=ROW_GAP_IN / _axes_h,
    )

    # ── Panel A: per-patient t = 0 savings, net of the drug charge ─────
    #
    # Quantity: instantaneous post-rebound food-emission savings minus the
    # pharmaceutical manufacturing charge, divided by treated-patient headcount.
    # Every term is t = 0 and there is NO survivor term -- additional survivors
    # at that horizon are negligible in magnitude, which is a fact about the
    # size of the number and not a boundary convention. The caption must say it
    # that way.
    #
    # pi(0) == 1 by construction, so neither pi nor pi_dose enters this panel on
    # either side: the food term comes from the unweighted pipeline call and the
    # drug term from the unweighted drug column.
    #
    # Max uptake only. Per patient the two uptake series very nearly coincide
    # (moderate is 0.966x-1.013x of maximum across these fifteen, a median 0.8%
    # of the panel's x-range apart, and moderate exceeds maximum on three of
    # them), so a paired bar would read as a rendering fault and would visibly
    # invert on Australia, France and Spain. The uptake contrast lives in panel
    # B, where it is a real 2x.

    ax_a = fig.add_subplot(gs[0, 0])

    denom_a = max_top["treated_users_initial"].values
    gross_a = max_top["food_savings_t0_t"].values
    drug_a = max_top["drug_emissions_1yr_t"].values
    # tonnes -> kg per patient.
    pp_gross = gross_a * 1e3 / denom_a
    pp_net = (gross_a - drug_a) * 1e3 / denom_a

    bh_a = 0.60
    # The drug charge drawn rather than netted invisibly: the pale bar is the
    # gross saving, the solid bar over it is what survives the manufacturing
    # charge, and the exposed tail between them is the charge itself.
    #
    # On this basis the charge is EXACTLY 5.38 kg per patient in every country,
    # because drug_emissions_1yr_t is treated_users_initial x 5.38 kg and the
    # denominator is that same headcount. So the pale tail is a constant width
    # on every bar and carries no cross-country information -- it shows the size
    # of the pharmaceutical term against the food saving, which is its purpose,
    # and nothing else. It is a legend entry, not a comparison.
    ax_a.barh(y, pp_gross, bh_a,
              color=CLR_A_MOD, edgecolor="white", linewidth=0.3,
              label="Pharmaceutical mfg, 5.38 kg/patient-yr")
    ax_a.barh(y, pp_net, bh_a,
              color=CLR_A_MAX, edgecolor="white", linewidth=0.3,
              label="Net food savings (max uptake, 95%)")

    x_hi_a = pp_gross.max() * 1.16
    offset_a = pp_gross.max() * 0.018
    for i in range(n):
        # The bar's OWN value at the bar end. The absolute national total is a
        # different quantity and goes in the annotation column, outside the
        # frame: a number printed at a bar end reads as that bar's value, and a
        # per-patient bar carrying a national total would be misleading.
        ax_a.text(pp_gross[i] + offset_a, y[i],
                  f"{pp_net[i]:,.0f}", va="center",
                  fontsize=PT["value"], color=CLR_A_MAX, fontweight="bold")

    ax_a.set_xlim(0, x_hi_a)
    ax_a.set_yticks(y)
    ax_a.set_yticklabels(display_countries(countries), fontsize=PT["country"])
    ax_a.set_xlabel(
        "Savings per treated patient at t = 0, net of drug (kg CO₂eq)",
        fontsize=PT["axis_label"], labelpad=2,
    )
    # Kept short: at 183 mm a longer title runs under the annotation column's
    # header, which sits just off panel A's right spine at the same height.
    ax_a.set_title(
        "A.  Food-Emission Savings per Patient (t = 0)",
        fontsize=PT["panel_title"], fontweight="bold", loc="left", pad=4,
    )
    ax_a.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )
    ax_a.invert_yaxis()
    ax_a.grid(axis="x", alpha=0.2, linewidth=0.4)
    ax_a.set_axisbelow(True)
    ax_a.tick_params(axis="both", labelsize=PT["tick"], pad=1.5,
                     length=2, width=0.4)
    for spine in ax_a.spines.values():
        spine.set_linewidth(0.5)
    # Below the axes, not inside it: the Netherlands bar reaches 211 of a 317
    # x-range, so a lower-right legend sat on top of the bottom row.
    ax_a.legend(fontsize=PT["legend"], loc="upper left",
                bbox_to_anchor=(0.0, -0.130), ncol=2, frameon=False,
                handlelength=1.1, handletextpad=0.4, borderpad=0.0,
                columnspacing=1.0)

    # Annotation column: the absolute national total, so the panel still conveys
    # scale after going intensive. Outside the plot area, with its own header
    # naming the units. Max uptake only. It costs ANNOTATION_COL_IN of the
    # inter-column gap and does not come out of panel A's axes width.
    ann_x = 1.02
    ax_a.text(
        ann_x, 1.015, "t = 0 national\ntotal (kt CO₂eq)",
        transform=ax_a.transAxes, fontsize=PT["annotation"], fontweight="bold",
        ha="left", va="bottom", color="#444444", clip_on=False,
    )
    for i in range(n):
        ax_a.text(
            ann_x, y[i], f"{gross_a[i] / 1e3:,.0f}",
            transform=ax_a.get_yaxis_transform(), fontsize=PT["annotation"],
            ha="left", va="center", color="#444444", clip_on=False,
        )

    # ── Panel B: Person-years saved (absolute; unchanged) ─────────────
    #
    # Left extensive on purpose: this is the panel that carries scale in the
    # figure, against panel A's intensive per-patient quantity.

    ax_b = fig.add_subplot(gs[1, 0])

    py_max = max_top["total_person_years_saved"].values / 1e3
    py_mod = mod_top["total_person_years_saved"].values / 1e3

    # Max uptake is the UPPER bar of the pair. The y-axis is inverted, so the
    # upper bar is the one at y - bh/2, not y + bh/2; drawing max at y + bh/2
    # put the lighter moderate bar on top while the legend listed max first.
    # Max is registered first, so the legend order matches the draw order.
    ax_b.barh(y - bh / 2, py_max, bh,
              color=CLR_B_MAX, edgecolor="white", linewidth=0.3,
              label="Max uptake (95%)")
    ax_b.barh(y + bh / 2, py_mod, bh,
              color=CLR_B_MOD, edgecolor="white", linewidth=0.3,
              label="Mod uptake (50%)")

    offset_b = max(py_max) * 0.018
    for i in range(n):
        ax_b.text(py_max[i] + offset_b, y[i] - bh / 2,
                  f"{py_max[i]:,.0f}", va="center",
                  fontsize=PT["value"], color=CLR_B_MAX, fontweight="bold")

    ax_b.set_xlim(0, max(py_max) * 1.16)
    ax_b.set_yticks(y)
    ax_b.set_yticklabels(display_countries(countries), fontsize=PT["country"])
    ax_b.set_xlabel("Person-Years Saved (thousands, 10-yr)",
                    fontsize=PT["axis_label"], labelpad=2)
    ax_b.set_title("B.  Person-Years Saved", fontsize=PT["panel_title"],
                    fontweight="bold", loc="left", pad=4)
    ax_b.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )
    ax_b.invert_yaxis()
    ax_b.grid(axis="x", alpha=0.2, linewidth=0.4)
    ax_b.set_axisbelow(True)
    ax_b.tick_params(axis="both", labelsize=PT["tick"], pad=1.5,
                     length=2, width=0.4)
    for spine in ax_b.spines.values():
        spine.set_linewidth(0.5)
    ax_b.legend(fontsize=PT["legend"], loc="lower right", framealpha=0.9,
                handlelength=1.4, handletextpad=0.5, borderpad=0.35,
                labelspacing=0.25)

    # ── Panel C: baseline ratio with carbon-intensity range ───────────
    #
    # Linear scale, not log. Over a range of roughly 1.2 to 4 the log scale
    # bought nothing and compressed the distance from the break-even line, which
    # is the one distance in this panel a reader is trying to read.

    ax_c = fig.add_subplot(gs[:, 1])

    ratio_max = c_df["ratio_food_to_mort"].values
    p10 = c_df["baseline_p10_ci"].values
    p90 = c_df["baseline_p90_ci"].values

    # Underscore-prefixed labels: matplotlib keeps them out of the legend, and
    # they let the diagnostic harness identify each artist by name instead of
    # guessing from offset counts, now that several collections in this panel
    # carry 40 points each.
    has_whisker = np.isfinite(p10) & np.isfinite(p90)
    ax_c.hlines(
        yc[has_whisker], p10[has_whisker], p90[has_whisker],
        color=CLR_C_MAX, linewidth=0.7, alpha=0.55, zorder=2,
        label="_whiskers",
    )
    for name, arr in (("_p10_caps", p10), ("_p90_caps", p90)):
        ax_c.scatter(
            arr[has_whisker], yc[has_whisker], marker="|", s=8,
            linewidths=0.6, color=CLR_C_MAX, alpha=0.75, zorder=3,
            label=name,
        )
    # Moderate uptake is NOT drawn here. The two uptake series sit a median
    # 0.79% of the x-range apart, which at 6 pt over 40 rows put an unfilled
    # marker on top of a filled one and read as a smudge rather than a second
    # series. Panel C is max uptake only; panel B carries the uptake contrast,
    # where it is a real 2x. Panel A is max-only for the same reason, so the
    # figure now mixes conventions across panels and the caption must say so.
    ax_c.scatter(
        ratio_max, yc, marker="o", s=7, color=CLR_C_MAX, zorder=5,
        label="_max_points",
    )
    # The only legend entry. The max-uptake marker needs none -- it is the sole
    # series and the panel title names it -- and the break-even line carries its
    # own inline italic label. Wrapped over two lines because the panel has
    # vertical room in the upper right and no horizontal room anywhere.
    ax_c.plot(
        [], [], color=CLR_C_MAX, linewidth=0.7, alpha=0.55,
        label="Food carbon intensity,\nP10–P90",
    )

    x_hi_c = float(np.nanmax([np.nanmax(p90), np.nanmax(ratio_max)])) * 1.22
    for i in range(nc):
        # One decimal place. At integer precision a country at 1.4 and one at
        # 2.4 printed the same value, and Poland rendered as "1x" -- which reads
        # as sitting exactly on break-even when it is not.
        anchor = p90[i] if np.isfinite(p90[i]) else ratio_max[i]
        ax_c.text(anchor + x_hi_c * 0.014, yc[i], f"{ratio_max[i]:,.1f}x",
                  va="center", fontsize=PT["value_small"], color=CLR_C_MAX,
                  fontweight="bold")

    ax_c.set_xlim(0, x_hi_c)
    # Ordinary padding, the same order as panels A and B get from matplotlib's
    # default bar margins. Pass 2 opened this to -5.4 to park a three-entry
    # legend above the first country, which cost about five row-heights of blank
    # page. With one entry the legend fits inside the data limits: the panel is
    # sorted ascending, so the top rows are the short ones and the upper right
    # is genuinely empty.
    ax_c.set_ylim(-0.8, nc - 0.2)
    ax_c.set_yticks(yc)
    ax_c.set_yticklabels(
        display_countries(c_df["Country"].tolist()), fontsize=PT["country"]
    )
    ax_c.set_xlabel("Food Savings ÷ Survivor Emissions (10-yr)",
                    fontsize=PT["axis_label"], labelpad=2)
    # Short for the same reason as panel A's: panel C's axes is only about
    # 55 mm wide, and a left-aligned 7.5 pt bold title longer than this runs off
    # the page edge. That panels A/B and C cover different country sets is a
    # caption statement, not a title one.
    # "max uptake" has to be in the title now that the legend has no series
    # entry to carry it. Panel C's title has 2.363 in of room before the page
    # edge, and the full "Break-Even Ratio, max uptake (N = 40)" measures
    # 2.505 in -- it renders clipped. "Ratio" is the word dropped rather than
    # the country count: the x label directly beneath already says the quantity
    # is a ratio and the break-even line is labelled inline, whereas the 40-vs-15
    # country contrast with panels A and B has nothing else on the figure to
    # carry it. Measured, not estimated -- gate G5 rechecks it on every run.
    ax_c.set_title(
        f"C.  Break-Even, max uptake (N = {nc})",
        fontsize=PT["panel_title"], fontweight="bold", loc="left", pad=4,
    )
    ax_c.axvline(x=1, color="black", linestyle="--", linewidth=0.7, alpha=0.7)
    ax_c.text(
        1, nc - 0.45, " break-even", fontsize=PT["note"], color="#333333",
        ha="left", va="center", style="italic",
    )
    ax_c.invert_yaxis()
    ax_c.grid(axis="x", alpha=0.2, linewidth=0.4)
    ax_c.set_axisbelow(True)
    ax_c.tick_params(axis="both", labelsize=PT["tick"], pad=1.5,
                     length=2, width=0.4)
    for spine in ax_c.spines.values():
        spine.set_linewidth(0.5)
    # Upper right, inside the data limits. The panel is sorted ascending, so the
    # top rows are the low-ratio ones and the space to their right is empty.
    ax_c.legend(fontsize=PT["legend"], loc="upper right", framealpha=0.9,
                handlelength=1.2, handletextpad=0.5, borderpad=0.3,
                labelspacing=0.2)

    fig.suptitle(
        "Semaglutide Impact Dashboard: Leading Countries (A, B) and the "
        "Complete-Data Set (C)",
        fontsize=PT["suptitle"], fontweight="bold",
        y=1 - 0.09 / FIG_H_IN, va="top",
    )

    out = output_path("country_dashboard.png")
    # No bbox_inches="tight": see figure_style. The saved PNG must be exactly
    # the designed 183 mm wide or the point sizes stop being point sizes.
    plt.savefig(str(out), dpi=DPI)
    plt.close()
    print(f"\nDashboard saved: {out}")
    print(f"  Figure: {mm(FIG_W_IN):.1f} x {mm(FIG_H_IN):.1f} mm at {DPI} dpi")
    return out


def plot_food_group_breakdown(food_by_group):
    """Stacked horizontal bars showing food-group composition of savings."""

    # Single source, shared with the rebound figure, which derives its
    # light/mid/dark triples from the same base colours. The values are
    # unchanged from the dict that used to live here, so this figure is
    # byte-identical across the move.
    FOOD_COLORS = FOOD_GROUP_COLORS

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
    ax.set_xlabel("Carbon Emissions Saved in Year 1 (kt CO₂eq)", fontsize=10)
    ax.set_title(
        "Food-Group Breakdown of Emission Savings\n"
        "(Max Uptake, Top Countries, year 1 of 10)",
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

    dashboard, food_by_group, complete_isos, panel_a_isos = build_dashboard_data()

    print("\nGenerating dashboard (3-panel)...")
    plot_dashboard(dashboard, food_by_group, complete_isos, panel_a_isos)

    print("\nGenerating food-group breakdown...")
    plot_food_group_breakdown(food_by_group)

    # Print summary table
    max_up = dashboard[dashboard["scenario"] == "max_uptake"].copy()
    top = max_up.set_index("ISO").loc[panel_a_isos]

    print(f"\n  Panel A/B country set: leading {len(panel_a_isos)} of the "
          f"food-data universe (derived)")
    print(f"  Panel C country set (derived, not hardcoded): N = "
          f"{len(complete_isos)}")

    # Population-weighted global mean per patient, over the whole food-data
    # universe rather than the fifteen shown. Reported, not tuned to anything.
    uni = max_up[max_up["food_savings_t0_t"] > 0]
    g_gross = uni["food_savings_t0_t"].sum()
    g_drug = uni["drug_emissions_1yr_t"].sum()
    g_pat = uni["treated_users_initial"].sum()
    print(f"\n  GLOBAL population-weighted mean, max uptake, N = {len(uni)}:")
    print(f"    gross {g_gross * 1e3 / g_pat:8.4f} kg CO2eq per patient at t = 0")
    print(f"    drug  {g_drug * 1e3 / g_pat:8.4f} kg")
    print(f"    NET   {(g_gross - g_drug) * 1e3 / g_pat:8.4f} kg")

    print("\n" + "=" * 108)
    print(f"{'Country':30s}  {'t=0 total':>14s}  {'Per patient':>12s}  "
          f"{'Person-Yrs':>12s}  {'BE Ratio':>10s}")
    print(f"{'':30s}  {'(kt CO2, t=0)':>14s}  {'(kg, net)':>12s}  "
          f"{'(thousands)':>12s}  {'(10-yr)':>10s}")
    print("-" * 108)
    for _, r in top.iterrows():
        ratio_str = (
            f"{r['ratio_food_to_mort']:10,.1f}x"
            if np.isfinite(r["ratio_food_to_mort"])
            else "       inf"
        )
        per_patient = (
            (r["food_savings_t0_t"] - r["drug_emissions_1yr_t"])
            * 1e3 / r["treated_users_initial"]
        )
        print(
            f"  {r['Country']:30s}  "
            f"{r['food_savings_t0_t']/1e3:12,.0f}  "
            f"{per_patient:12,.1f}  "
            f"{r['total_person_years_saved']/1e3:12,.0f}  "
            f"{ratio_str}"
        )

    print("\nDone.")


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
