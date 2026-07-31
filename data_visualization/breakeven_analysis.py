"""
Break-even analysis: when do cumulative food-emission savings from
semaglutide equal cumulative emissions from additional survivors?

Food side:  Annual CO2eq savings from reduced food consumption
            (Price Rebound Model — static equilibrium, 2022 baseline),
            net of pharmaceutical production emissions by default
Mortality:  Year-by-year emissions from additional survivors
            (Deterministic expected-value mortality model)

Outputs:
    figures/breakeven_by_country.png   — break-even ratios by country
    figures/breakeven_curves.png       — cumulative curves for top countries
    figures/breakeven_stock_all_countries.png
        — cumulative stock for all complete-data countries
    figures/breakeven_flow_all_countries.png
        — annual flow for all complete-data countries
    figures/breakeven_publication.png / .pdf
        — Nature Food-style panel: A (cumulative stock) + B (annual flow),
          joined, square, no titles/annotations, muted colorblind-safe palette

Usage:
    python -m data_visualization.breakeven_analysis
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from .drug_footprint import build_drug_emissions
from .pipeline import compute_food_savings, load_mortality_emissions, output_path

# Carbon-intensity file per scenario, paired with the survivor-emissions file of
# the same name. Both sides of the comparison must move together.
CI_FILES = {
    "mean": "carbon_intensity.csv",
    "p10": "carbon_intensity_p10.csv",
    "p90": "carbon_intensity_p90.csv",
}


# Countries in the break-even set whose mortality schedule is an imputation from a
# UN region containing exactly one Human Life-Table country, so their life table is
# literally another country's. Israel is the only such donor that reaches this set.
#
# Seven countries carry Israel's schedule bit-for-bit -- ARE, BHR, CYP, KWT, OMN,
# QAT, SAU -- but only ARE, CYP and SAU have an OECD per-capita factor and so
# appear in a ratio at all. Cyprus is retained as defensible; the two Gulf states
# are the exposure worth reporting.
#
# Derived, not assumed: diagnostics/imputation_sensitivity.py compares each
# country's (age, Sex) -> mortality_rate map against Israel's and prints the list.
# Re-run it if final_df_imputed.pkl is ever rebuilt.
IMPUTED_FROM_ISRAEL = ["ARE", "SAU"]


def imputation_sensitivity(be_df, exclude=IMPUTED_FROM_ISRAEL):
    """Headline ratios with and without the countries imputed from Israel.

    Reported on every run rather than kept as a one-off: if the headline depended
    on Israel's life table standing in for Saudi Arabia's, that would be a reason
    not to include those countries at all, and the only way to know is to look.
    """
    rows = []
    for scenario in ("max_uptake", "mod_uptake"):
        full = _complete_data_subset(be_df, scenario=scenario)
        kept = full[~full["ISO"].isin(exclude)]
        for label, v in (("with", full), ("without", kept)):
            years = np.arange(1, 11)
            cf = np.array([v[f"cum_food_Y{y}"].sum() for y in years], dtype=float)
            cm = np.array([v[f"cum_mort_Y{y}"].sum() for y in years], dtype=float)
            af, am = np.diff(cf, prepend=0.0), np.diff(cm, prepend=0.0)
            idx = v["ratio_food_to_mort"].idxmin()
            rows.append({
                "scenario": scenario,
                "set": label,
                "N": len(v),
                "cum_ratio_10yr": cf[-1] / cm[-1] if cm[-1] > 0 else np.nan,
                "annual_ratio_y10": af[-1] / am[-1] if am[-1] > 0 else np.nan,
                "min_ratio": float(v.loc[idx, "ratio_food_to_mort"]),
                "min_iso": v.loc[idx, "ISO"],
            })
    return pd.DataFrame(rows)


def print_imputation_sensitivity(be_df, exclude=IMPUTED_FROM_ISRAEL) -> None:
    tab = imputation_sensitivity(be_df, exclude=exclude)
    print("\n" + "=" * 65)
    print("IMPUTATION EXPOSURE")
    print("=" * 65)
    print(f"\n  Excluding {exclude}: countries whose life table is Israel's,")
    print("  imputed from a UN region whose only HLD member is Israel.")
    print(f"\n  {'scenario':<12}{'set':<9}{'N':>4}{'cum 10-yr':>12}"
          f"{'y10 annual':>12}{'min':>9}{'min ISO':>9}")
    for _, r in tab.iterrows():
        print(f"  {r['scenario']:<12}{r['set']:<9}{r['N']:>4}"
              f"{r['cum_ratio_10yr']:>12.4f}{r['annual_ratio_y10']:>12.4f}"
              f"{r['min_ratio']:>9.4f}{r['min_iso']:>9}")
    for scenario in ("max_uptake", "mod_uptake"):
        a = tab[(tab["scenario"] == scenario) & (tab["set"] == "with")].iloc[0]
        b = tab[(tab["scenario"] == scenario) & (tab["set"] == "without")].iloc[0]
        print(f"  {scenario}: cum 10-yr moves "
              f"{(b['cum_ratio_10yr'] / a['cum_ratio_10yr'] - 1) * 100:+.2f}%, "
              f"y10 annual {(b['annual_ratio_y10'] / a['annual_ratio_y10'] - 1) * 100:+.2f}%, "
              f"binding country {a['min_iso']} -> {b['min_iso']}")


def compute_breakeven(food_savings, mort, include_drug: bool = True):
    """For each (ISO, scenario), find the year where cumulative food savings
    exceed cumulative survivor emissions.

    When ``include_drug`` is True (default), annual pharmaceutical emissions are
    subtracted from annual food savings before the cumulative comparison, so the
    baseline mortality break-even already accounts for drug production.
    """

    merged = pd.merge(food_savings, mort, on=["ISO", "scenario"], how="inner")
    drug_year_cols = [f"drug_emissions_t_Y{y}" for y in range(1, 11)]
    if include_drug:
        drug = build_drug_emissions()[
            ["ISO", "scenario", "drug_emissions_1yr_t", "drug_emissions_10yr_t",
             *drug_year_cols]
        ]
        merged = pd.merge(merged, drug, on=["ISO", "scenario"], how="left")
        for c in ["drug_emissions_1yr_t", "drug_emissions_10yr_t", *drug_year_cols]:
            merged[c] = merged[c].fillna(0.0)
    else:
        for c in ["drug_emissions_1yr_t", "drug_emissions_10yr_t", *drug_year_cols]:
            merged[c] = 0.0

    # Both sides of the comparison are now per-year series. Food savings decline
    # with pi(t) as treated patients die, and dosing declines with pi_dose(t) for
    # the same reason, so neither can be represented by a single annual number
    # repeated ten times. Where a per-year food column is absent -- an unweighted
    # run -- the year-1 value is reused, which reproduces the old constant series.
    food_year_cols = [f"annual_food_savings_t_Y{y}" for y in range(1, 11)]
    have_food_series = all(c in merged.columns for c in food_year_cols)

    records = []
    for _, row in merged.iterrows():
        annual_food_gross = float(row["annual_food_savings_t"])
        # Year-1 dosing, so the reported annual figures are the same year as
        # year 1 of the cumulative series below. Identical to
        # drug_emissions_1yr_t on an unweighted run.
        annual_drug = float(row["drug_emissions_t_Y1"])
        annual_food = annual_food_gross - annual_drug

        cum_food = 0.0
        cum_mort = 0.0
        has_survivor_emissions = True

        yearly_food = []
        yearly_mort = []

        for y in range(1, 11):
            gross_y = (
                float(row[f"annual_food_savings_t_Y{y}"])
                if have_food_series
                else annual_food_gross
            )
            cum_food += gross_y - float(row[f"drug_emissions_t_Y{y}"])
            emissions_y = row[f"emissions_Y{y}"]
            if pd.isna(emissions_y):
                has_survivor_emissions = False
            else:
                cum_mort += emissions_y
            yearly_food.append(cum_food)
            yearly_mort.append(cum_mort if has_survivor_emissions else np.nan)

        breakeven_year = None
        if has_survivor_emissions:
            for y in range(10):
                if yearly_food[y] >= yearly_mort[y]:
                    if y == 0:
                        breakeven_year = 1.0
                    else:
                        if yearly_food[y - 1] < yearly_mort[y - 1]:
                            gap_prev = yearly_mort[y - 1] - yearly_food[y - 1]
                            gap_curr = yearly_food[y] - yearly_mort[y]
                            frac = gap_prev / (gap_prev + gap_curr)
                            breakeven_year = y + frac
                        else:
                            breakeven_year = 1.0
                    break

        if breakeven_year is None:
            breakeven_year = float("inf")

        food_dominates_all = (
            has_survivor_emissions
            and all(yearly_food[y] >= yearly_mort[y] for y in range(10))
        )

        records.append({
            "ISO": row["ISO"],
            "Country": row["Country"],
            "scenario": row["scenario"],
            "annual_food_savings_gross_t": annual_food_gross,
            "annual_drug_emissions_t": annual_drug,
            "annual_food_savings_t": annual_food,
            "total_survivor_emissions_10yr": cum_mort,
            "total_food_savings_10yr": cum_food,
            "total_drug_emissions_10yr": float(row["drug_emissions_10yr_t"]),
            "ratio_food_to_mort": (
                cum_food / cum_mort if has_survivor_emissions and cum_mort > 0 else np.nan
            ),
            "breakeven_year": breakeven_year,
            "food_dominates_all_years": food_dominates_all,
            "drug_included_in_food_savings": include_drug,
            **{f"cum_food_Y{y+1}": yearly_food[y] for y in range(10)},
            **{f"cum_mort_Y{y+1}": yearly_mort[y] for y in range(10)},
        })

    return pd.DataFrame(records)


def plot_breakeven_bars(be_df):
    valid = be_df[
        np.isfinite(be_df["ratio_food_to_mort"])
        & (be_df["annual_food_savings_t"] > 0)
        & (be_df["total_survivor_emissions_10yr"] > 0)
    ].copy()
    max_up = valid[valid["scenario"] == "max_uptake"].copy()
    mod_up = valid[valid["scenario"] == "mod_uptake"].copy()

    max_up = max_up.sort_values("ratio_food_to_mort", ascending=True)
    country_order = max_up["Country"].tolist()

    fig, ax = plt.subplots(figsize=(12, max(8, len(country_order) * 0.28)))

    y = np.arange(len(country_order))
    bar_height = 0.35

    max_ratios, mod_ratios = [], []
    for country in country_order:
        mr = max_up[max_up["Country"] == country]["ratio_food_to_mort"].values
        max_ratios.append(mr[0] if len(mr) > 0 else 0)
        mr2 = mod_up[mod_up["Country"] == country]["ratio_food_to_mort"].values
        mod_ratios.append(mr2[0] if len(mr2) > 0 else 0)

    ax.barh(
        y + bar_height / 2, max_ratios, bar_height,
        label="Maximum uptake (95%)", color="#2166ac",
        edgecolor="white", linewidth=0.5,
    )
    ax.barh(
        y - bar_height / 2, mod_ratios, bar_height,
        label="Moderate uptake (50%)", color="#92c5de",
        edgecolor="white", linewidth=0.5,
    )

    ax.set_yticks(y)
    ax.set_yticklabels(country_order, fontsize=7)
    ax.set_xlabel(
        "Ratio: Cumulative Food Savings / Cumulative Survivor Emissions (10-year)",
        fontsize=10,
    )
    ax.set_title(
        "Break-Even Analysis: Food Emission Savings vs. Survivor Emissions\n"
        "All countries break even in Year 1 — bars show 10-year "
        "savings-to-emissions ratio",
        fontsize=12, fontweight="bold", pad=15,
    )
    ax.axvline(
        x=1, color="red", linestyle="--", linewidth=1,
        label="Break-even line (ratio = 1)",
    )
    ax.set_xscale("log")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)

    for i in range(
        len(country_order) - 1, max(len(country_order) - 6, -1), -1
    ):
        ax.text(
            max_ratios[i] * 1.1, y[i] + bar_height / 2,
            f"{max_ratios[i]:,.0f}x",
            va="center", fontsize=6, color="#2166ac", fontweight="bold",
        )

    plt.tight_layout()
    out = output_path("breakeven_by_country.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_breakeven_curves(be_df):
    max_up = be_df[be_df["scenario"] == "max_uptake"].copy()
    top = max_up.nlargest(8, "annual_food_savings_t")

    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    axes = axes.flatten()
    years = np.arange(1, 11)

    for idx, (_, row) in enumerate(top.iterrows()):
        ax = axes[idx]

        cum_food_kt = [row[f"cum_food_Y{y}"] / 1e3 for y in range(1, 11)]
        cum_mort_kt = [row[f"cum_mort_Y{y}"] / 1e3 for y in range(1, 11)]

        ax.plot(
            years, cum_food_kt, "b-o", markersize=4, linewidth=2,
            label="Food savings (cumulative)",
        )
        ax.plot(
            years, cum_mort_kt, "r-s", markersize=4, linewidth=2,
            label="Survivor emissions (cumulative)",
        )
        ax.fill_between(years, cum_mort_kt, cum_food_kt, alpha=0.15, color="blue")

        ax.set_title(f"{row['Country']}", fontsize=10, fontweight="bold")
        ax.set_xlabel("Year", fontsize=8)
        ax.set_ylabel("kt CO₂eq", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

        ratio = row["ratio_food_to_mort"]
        ax.text(
            0.97, 0.05, f"Ratio: {ratio:,.0f}x",
            transform=ax.transAxes, fontsize=8, ha="right",
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="lightyellow", edgecolor="gray",
            ),
        )

        if idx == 0:
            ax.legend(fontsize=7, loc="upper left")

    fig.suptitle(
        "Cumulative Food-Emission Savings vs. Survivor Emissions (Max Uptake)\n"
        "Blue shading = net emission reduction from semaglutide",
        fontsize=13, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    out = output_path("breakeven_curves.png")
    plt.savefig(str(out), dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def _complete_data_subset(be_df: pd.DataFrame, scenario: str = "max_uptake") -> pd.DataFrame:
    """Return complete-data rows used for headline all-country aggregates."""
    return be_df[
        (be_df["scenario"] == scenario)
        & (be_df["annual_food_savings_t"] > 0)
        & (be_df["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be_df["ratio_food_to_mort"])
    ].copy()


def plot_stock_flow_all_countries(be_df: pd.DataFrame, scenario: str = "max_uptake") -> tuple[str, str]:
    """Save separate stock and flow figures for all complete-data countries.

    Figure A: cumulative food savings vs cumulative survivor emissions.
    Figure B: annual food savings vs annual survivor emissions.
    """
    valid = _complete_data_subset(be_df, scenario=scenario)
    years = np.arange(1, 11)

    cum_food = np.array([valid[f"cum_food_Y{y}"].sum() for y in years], dtype=float)
    cum_mort = np.array([valid[f"cum_mort_Y{y}"].sum() for y in years], dtype=float)
    annual_food = np.diff(cum_food, prepend=0.0)
    annual_mort = np.diff(cum_mort, prepend=0.0)

    # Convert tonnes to Mt for readable all-country axis labels.
    cum_food_mt = cum_food / 1e6
    cum_mort_mt = cum_mort / 1e6
    annual_food_mt = annual_food / 1e6
    annual_mort_mt = annual_mort / 1e6
    ratio_10yr = cum_food[-1] / cum_mort[-1] if cum_mort[-1] > 0 else np.nan

    uptake_label = "maximum uptake" if scenario == "max_uptake" else "moderate uptake"
    common_title = (
        "All complete-data countries: food-emission savings vs survivor emissions\n"
        f"({uptake_label}; food savings net of pharmaceutical emissions)"
    )

    # Figure A: cumulative stock
    fig_a, ax = plt.subplots(figsize=(7.2, 5.2))
    ax.plot(
        years,
        cum_food_mt,
        "b-o",
        markersize=5,
        linewidth=2.2,
        label="Food savings (cumulative)",
    )
    ax.plot(
        years,
        cum_mort_mt,
        "r-s",
        markersize=5,
        linewidth=2.2,
        label="Survivor emissions (cumulative)",
    )
    ax.fill_between(years, cum_mort_mt, cum_food_mt, alpha=0.15, color="blue")
    ax.set_title("A. Cumulative stock", fontsize=12, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Mt CO₂eq")
    ax.set_xticks(years)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.25)
    ax.annotate(
        f"Year 1:\nfood {cum_food_mt[0]:,.1f} Mt\nsurvivor {cum_mort_mt[0]:,.1f} Mt",
        xy=(1, cum_food_mt[0]),
        xytext=(2.4, cum_food_mt[0] + (cum_food_mt[-1] - cum_food_mt[0]) * 0.12),
        fontsize=8,
        arrowprops=dict(arrowstyle="->", color="gray"),
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray"),
    )
    ax.text(
        0.97,
        0.05,
        f"Year-10 ratio: {ratio_10yr:,.1f}x",
        transform=ax.transAxes,
        fontsize=9,
        ha="right",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", edgecolor="gray"),
    )
    fig_a.suptitle(common_title, fontsize=11, fontweight="bold", y=1.02)
    fig_a.tight_layout()
    out_a = output_path("breakeven_stock_all_countries.png")
    fig_a.savefig(str(out_a), dpi=200, bbox_inches="tight")
    plt.close(fig_a)

    # Figure B: annual flow
    fig_b, ax = plt.subplots(figsize=(7.2, 5.2))
    ax.plot(
        years,
        annual_food_mt,
        "b-o",
        markersize=5,
        linewidth=2.2,
        label="Food savings (annual)",
    )
    ax.plot(
        years,
        annual_mort_mt,
        "r-s",
        markersize=5,
        linewidth=2.2,
        label="Survivor emissions (annual)",
    )
    ax.fill_between(years, annual_mort_mt, annual_food_mt, alpha=0.15, color="blue")
    ax.set_title("B. Annual flow", fontsize=12, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Mt CO₂eq / year")
    ax.set_xticks(years)
    # Leave headroom so the legend sits above the flat food-savings line.
    ax.set_ylim(0, annual_food_mt.max() * 1.28)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.1f}"))
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25)
    ax.annotate(
        f"Year 1:\nfood {annual_food_mt[0]:,.1f} Mt/yr\nsurvivor {annual_mort_mt[0]:,.1f} Mt/yr",
        xy=(1, annual_mort_mt[0]),
        xytext=(2.8, annual_food_mt[0] * 0.42),
        fontsize=8,
        arrowprops=dict(arrowstyle="->", color="gray"),
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray"),
    )
    ax.annotate(
        (
            f"Year 10:\n"
            f"food {annual_food_mt[-1]:,.1f} Mt/yr\n"
            f"survivor {annual_mort_mt[-1]:,.1f} Mt/yr"
        ),
        xy=(10, annual_mort_mt[-1]),
        xytext=(6.6, annual_food_mt[-1] * 0.42),
        fontsize=8,
        arrowprops=dict(arrowstyle="->", color="gray"),
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray"),
    )
    fig_b.suptitle(common_title, fontsize=11, fontweight="bold", y=1.02)
    fig_b.tight_layout()
    out_b = output_path("breakeven_flow_all_countries.png")
    fig_b.savefig(str(out_b), dpi=200, bbox_inches="tight")
    plt.close(fig_b)

    print(
        f"  Stock/flow aggregate ({len(valid)} countries, {scenario}): "
        f"year-10 cumulative ratio {ratio_10yr:,.2f}x; "
        f"year-1 annual food {annual_food_mt[0]:,.1f} Mt vs "
        f"survivor {annual_mort_mt[0]:,.1f} Mt; "
        f"year-10 annual food {annual_food_mt[-1]:,.1f} Mt vs "
        f"survivor {annual_mort_mt[-1]:,.1f} Mt"
    )
    print(f"Saved: {out_a}")
    print(f"Saved: {out_b}")
    return str(out_a), str(out_b)


def plot_breakeven_publication(
    be_df: pd.DataFrame, scenario: str = "max_uptake"
) -> str:
    """Nature Food-ready joined panel figure (A: cumulative stock, B: annual flow).

    Same underlying data as ``plot_stock_flow_all_countries``, but combined into
    a single figure, with no panel titles/suptitle, both panels drawn as squares
    (equal box aspect) for print layout, and a single in-wedge ratio annotation
    per panel computed directly from the plotted arrays (not hardcoded). Saved
    as both a 300 dpi PNG and a vector PDF.
    """
    valid = _complete_data_subset(be_df, scenario=scenario)
    years = np.arange(1, 11)

    cum_food = np.array([valid[f"cum_food_Y{y}"].sum() for y in years], dtype=float)
    cum_mort = np.array([valid[f"cum_mort_Y{y}"].sum() for y in years], dtype=float)
    annual_food = np.diff(cum_food, prepend=0.0)
    annual_mort = np.diff(cum_mort, prepend=0.0)

    cum_food_mt = cum_food / 1e6
    cum_mort_mt = cum_mort / 1e6
    annual_food_mt = annual_food / 1e6
    annual_mort_mt = annual_mort / 1e6

    # Year-10 ratios, derived from the same arrays that are plotted so the
    # annotation text always tracks the underlying data.
    ratio_cum_y10 = cum_food_mt[-1] / cum_mort_mt[-1]
    ratio_annual_y10 = annual_food_mt[-1] / annual_mort_mt[-1]

    # Place each label inside the shaded wedge, vertically centred between the
    # two curves at that x position (interpolated so x need not be an integer
    # year).
    ann_a_x = 8.0
    ann_a_y = (
        np.interp(ann_a_x, years, cum_food_mt)
        + np.interp(ann_a_x, years, cum_mort_mt)
    ) / 2
    ann_b_x = 8.2
    ann_b_y = (
        np.interp(ann_b_x, years, annual_food_mt)
        + np.interp(ann_b_x, years, annual_mort_mt)
    ) / 2

    food_color = "#648FFF"  # bright colorblind-safe blue (IBM palette)
    survivor_color = "#FE6100"  # bright colorblind-safe orange (IBM palette)

    rc = {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.weight": "bold",
        "axes.labelweight": "bold",
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.labelsize": 11,
        "legend.fontsize": 10,
    }

    with plt.rc_context(rc):
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 5.5))

        # Panel A: cumulative stock
        ax_a.plot(
            years, cum_food_mt, "-o", color=food_color, markersize=4, linewidth=1.5,
            label="Food savings (cumulative)",
        )
        ax_a.plot(
            years, cum_mort_mt, "-s", color=survivor_color, markersize=4, linewidth=1.5,
            label="Survivor emissions (cumulative)",
        )
        ax_a.fill_between(years, cum_mort_mt, cum_food_mt, alpha=0.12, color=food_color)
        ax_a.set_xlabel("Year")
        ax_a.set_ylabel(r"Cumulative Mt CO$_2$eq")
        ax_a.set_xticks(years)
        ax_a.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax_a.legend(loc="upper left", frameon=False)
        ax_a.set_axisbelow(True)
        ax_a.set_box_aspect(1)
        ax_a.text(
            ann_a_x, ann_a_y, f"{ratio_cum_y10:.1f}× at year 10",
            ha="center", va="center", fontsize=10, color="#333333",
        )
        ax_a.text(
            -0.14, 1.06, "A", transform=ax_a.transAxes,
            fontsize=14, fontweight="bold", va="bottom", ha="left",
        )

        # Panel B: annual flow
        ax_b.plot(
            years, annual_food_mt, "-o", color=food_color, markersize=4, linewidth=1.5,
            label="Food savings (annual)",
        )
        ax_b.plot(
            years, annual_mort_mt, "-s", color=survivor_color, markersize=4, linewidth=1.5,
            label="Survivor emissions (annual)",
        )
        ax_b.fill_between(years, annual_mort_mt, annual_food_mt, alpha=0.12, color=food_color)
        ax_b.set_xlabel("Year")
        ax_b.set_ylabel(r"Annual Mt CO$_2$eq yr$^{-1}$")
        ax_b.set_xticks(years)
        ax_b.set_ylim(0, annual_food_mt.max() * 1.1)
        ax_b.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax_b.set_axisbelow(True)
        ax_b.set_box_aspect(1)
        ax_b.text(
            ann_b_x, ann_b_y, f"{ratio_annual_y10:.1f}× at year 10",
            ha="center", va="center", fontsize=10, color="#333333",
        )
        ax_b.text(
            -0.14, 1.06, "B", transform=ax_b.transAxes,
            fontsize=14, fontweight="bold", va="bottom", ha="left",
        )

        fig.tight_layout()
        out_png = output_path("breakeven_publication.png")
        out_pdf = output_path("breakeven_publication.pdf")
        fig.savefig(str(out_png), dpi=300, bbox_inches="tight")
        fig.savefig(str(out_pdf), bbox_inches="tight")
        plt.close(fig)

    print(f"Saved: {out_png}")
    print(f"Saved: {out_pdf}")
    return str(out_png)


def main(ci_scenario: str = "mean"):
    print("=" * 65)
    print("BREAK-EVEN ANALYSIS")
    print("Food-emission savings vs. survivor emissions from semaglutide")
    print("(Food savings are net of pharmaceutical production emissions)")
    print("=" * 65)

    ci_file = CI_FILES[ci_scenario]
    print("\n[1/4] Computing annual food-emission savings...")
    food_savings, _ = compute_food_savings(ci_file=ci_file)

    # The survivor file must match the carbon intensities the food side just
    # used: its P&N food add-back is priced with the same intensities.
    print(f"[2/4] Loading mortality-model emissions (ci={ci_scenario})...")
    mort = load_mortality_emissions(ci_scenario)

    print("[3/4] Computing break-even (folding in drug emissions)...")
    be_df = compute_breakeven(food_savings, mort, include_drug=True)

    print("\n" + "=" * 65)
    print("RESULTS")
    print("=" * 65)

    for scenario in ["max_uptake", "mod_uptake"]:
        sub_all = be_df[be_df["scenario"] == scenario].copy()
        sub = sub_all[
            np.isfinite(sub_all["ratio_food_to_mort"])
            & (sub_all["annual_food_savings_t"] > 0)
            & (sub_all["total_survivor_emissions_10yr"] > 0)
        ].copy()
        label = (
            "Maximum uptake (95%)" if scenario == "max_uptake"
            else "Moderate uptake (50%)"
        )
        print(f"\n--- {label} ---\n")
        print(f"  Countries with complete food + survivor data: {len(sub)}")
        print(f"  Countries excluded due to missing data: {len(sub_all) - len(sub)}")

        all_break_y1 = sub["food_dominates_all_years"].all()
        print(f"  All countries break even in Year 1: "
              f"{'YES' if all_break_y1 else 'NO'}")

        if not all_break_y1:
            late = sub[~sub["food_dominates_all_years"]].sort_values(
                "breakeven_year"
            )
            print("  Countries NOT breaking even in Year 1:")
            for _, r in late.iterrows():
                be = r["breakeven_year"]
                be_str = f"Year {be:.1f}" if be <= 10 else ">10 years"
                print(f"    {r['Country']:40s}  break-even: {be_str}")

        sub_sorted = sub.sort_values("ratio_food_to_mort", ascending=False)
        print(
            f"\n  {'Country':40s}  {'Food (kt/yr)':>12s}  "
            f"{'Mort 10yr (kt)':>14s}  {'Ratio':>10s}"
        )
        print("  " + "-" * 80)
        for _, r in sub_sorted.iterrows():
            ratio_str = (
                f"{r['ratio_food_to_mort']:10,.1f}x"
                if np.isfinite(r["ratio_food_to_mort"])
                else "       inf"
            )
            print(
                f"  {r['Country']:40s}  "
                f"{r['annual_food_savings_t']/1e3:12,.0f}  "
                f"{r['total_survivor_emissions_10yr']/1e3:14,.1f}  "
                f"{ratio_str}"
            )

        total_food = sub["annual_food_savings_t"].sum()
        total_mort = sub["total_survivor_emissions_10yr"].sum()
        # Cumulative food is the SUM of the per-year series, which
        # total_food_savings_10yr already accumulates. It is not annual x 10:
        # under survival weighting the annual saving falls every year, so
        # annual x 10 overstates it.
        total_food_10yr = sub["total_food_savings_10yr"].sum()
        print("  " + "-" * 80)
        print(
            f"  {'TOTAL':40s}  "
            f"{total_food/1e3:12,.0f}  "
            f"{total_mort/1e3:14,.1f}  "
            f"{total_food_10yr / total_mort:10,.1f}x"
        )

    print_imputation_sensitivity(be_df)

    print(f"\n[4/4] Generating figures...")
    plot_breakeven_bars(be_df)
    plot_breakeven_curves(be_df)
    plot_stock_flow_all_countries(be_df, scenario="max_uptake")
    plot_breakeven_publication(be_df, scenario="max_uptake")

    max_sub = be_df[be_df["scenario"] == "max_uptake"]
    valid = max_sub[
        (max_sub["annual_food_savings_t"] > 0)
        & (max_sub["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(max_sub["ratio_food_to_mort"])
    ]
    min_ratio = valid["ratio_food_to_mort"].min()
    min_country = valid.loc[valid["ratio_food_to_mort"].idxmin(), "Country"]
    global_food = valid["annual_food_savings_t"].sum()
    global_food_10yr = valid["total_food_savings_10yr"].sum()
    global_mort = valid["total_survivor_emissions_10yr"].sum()
    n_no_data = len(max_sub) - len(valid)
    mort_units = (
        f"{global_mort/1e6:.1f} Mt"
        if global_mort >= 1e6
        else f"{global_mort/1e3:.1f} kt"
    )

    print("\n" + "=" * 65)
    print("KEY FINDING")
    print("=" * 65)
    print(f"\n  ({n_no_data} countries excluded due to missing data)")
    print(f"\n  Global (max uptake, {len(valid)} countries):")
    print(f"    Annual food savings (year 1): {global_food/1e6:.1f} Mt CO2eq/year")
    print(f"    10-year food savings:         {global_food_10yr/1e6:.1f} Mt CO2eq")
    print(f"    10-year survivor emissions:   {mort_units} CO2eq")
    print(f"    10-year ratio:                {global_food_10yr/global_mort:,.1f}x")
    print(f"\n  Smallest margin: {min_country} ({min_ratio:,.1f}x over 10 years)")

    all_y1 = valid["food_dominates_all_years"].all()
    if all_y1:
        print("\n  All countries with data break even in Year 1.")
    else:
        n_late = (~valid["food_dominates_all_years"]).sum()
        print(
            f"\n  {len(valid) - n_late}/{len(valid)} countries "
            "break even in Year 1."
        )


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
