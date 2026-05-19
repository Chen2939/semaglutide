"""
breakeven_analysis.py

Break-even analysis: when do cumulative food-emission savings from
semaglutide equal cumulative emissions from additional survivors?

Food side:  Annual CO2eq savings from reduced food consumption
            (Price Rebound Model — static equilibrium, 2022 baseline)
Mortality:  Year-by-year emissions from additional survivors
            (Mortality Model — 10-year Monte Carlo simulation)

Outputs:
    test/breakeven_by_country.png   — break-even years by country
    test/breakeven_curves.png       — cumulative curves for top countries
"""

import numpy as np
import pandas as pd
import pyreadr
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy.optimize import root_scalar


# =====================================================================
# PART 1: Compute annual food-emission savings (Price Rebound Model)
# =====================================================================

def compute_food_savings():
    """Re-run equilibrium model and return annual food savings by (ISO, scenario)."""

    sim_result = list(pyreadr.read_r("full_simulation_results8.rds").values())[0]
    sim_result["weighted_eer"] = sim_result["weighting"] * sim_result["eer"]
    sim_result["weighted_treatment_eer"] = sim_result["weighting"] * sim_result["treatment_eer"]

    norm = pd.read_csv(
        "Food data/FoodBalanceSheets_E_All_Data_(Normalized)/"
        "FoodBalanceSheets_E_All_Data_(Normalized).csv"
    )
    mapping = pd.read_csv("Food data/FBS_Group_Mapping.csv")
    iso_mapping = pd.read_csv("Food data/faostat_country_mapping.csv")
    price_index = pd.read_csv(
        "Food data/ConsumerPriceIndices_E_All_Data_(Normalized)/"
        "ConsumerPriceIndices_E_All_Data_(Normalized).csv"
    )
    elasticity_supply_raw = pd.read_csv("Food data/elasticity_supply.csv")
    elasticity_demand = pd.read_csv("Food data/elasticity_demand.csv")
    carbon_intensity_raw = pd.read_csv("Food data/carbon_intensity.csv")

    countries_in_scope = sim_result["ISO"].unique()

    food_norm = pd.merge(norm, iso_mapping, on="Area", how="left")
    food_norm = food_norm.loc[
        (food_norm["Year"] == 2022)
        & (food_norm["Element"] == "Food")
        & (food_norm["ISO"].isin(countries_in_scope))
    ]
    food_norm = pd.merge(
        food_norm,
        mapping.set_index("fbs_group")[["first_level_aggregation", "final_food_group"]],
        left_on="Item", right_index=True, how="left",
    )
    food_grouped = (
        food_norm.groupby(["Area", "ISO", "final_food_group"])
        .sum(numeric_only=True)[["Value"]]
        .reset_index()
    )
    food_grouped = (
        food_grouped[food_grouped["ISO"].isin(countries_in_scope)]
        .rename(columns={"Area": "Country", "Value": "initial_eql_quantity"})
        .reset_index(drop=True)
    )

    price_clean = pd.merge(price_index, iso_mapping, on="Area", how="left")
    price_clean = price_clean.loc[
        (price_clean["Months"] == "December")
        & (price_clean["Year"] == 2022)
        & (price_clean["Item"] == "Consumer Prices, Food Indices (2015 = 100)")
    ]
    price_clean = (
        price_clean[price_clean["ISO"].isin(countries_in_scope)][["Area", "ISO", "Value"]]
        .rename(columns={"Area": "Country", "Value": "price"})
        .reset_index(drop=True)
    )

    elasticity_supply = elasticity_supply_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="elasticity_supply",
    )

    carbon_intensity = carbon_intensity_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="carbon_intensity_t",
    )
    carbon_intensity["carbon_intensity_t"] *= 1000

    merged = pd.merge(food_grouped, price_clean[["ISO", "price"]], on="ISO", how="outer")
    merged = pd.merge(
        merged, elasticity_demand.set_index("food_groups"),
        left_on="final_food_group", right_index=True, how="left",
    )
    merged = pd.merge(
        merged,
        elasticity_supply[["ISO", "final_food_group", "elasticity_supply"]],
        on=["ISO", "final_food_group"], how="left",
    )

    merged["Cs"] = merged["initial_eql_quantity"] / (merged["price"] ** merged["elasticity_supply"])
    merged["Cd"] = merged["initial_eql_quantity"] / (merged["price"] ** merged["elasticity_demand"])

    sim_result_perc = sim_result.groupby(["ISO", "scenario"]).sum(numeric_only=True)
    sim_result_perc = sim_result_perc[["weighted_eer", "weighted_treatment_eer"]].copy()
    sim_result_perc["expected_demand_reduction_percent"] = (
        sim_result_perc["weighted_treatment_eer"] / sim_result_perc["weighted_eer"]
    ) - 1

    merged = pd.merge(
        merged,
        sim_result_perc[["expected_demand_reduction_percent"]].reset_index(),
        on="ISO", how="left",
    )

    def equilibrium_gap(P, Cs, Cd, Es, Ed, demand_shock_pct):
        Qs = Cs * (P ** Es)
        Qd = Cd * (P ** Ed) * (1 + demand_shock_pct)
        return Qs - Qd

    def compute_equilibrium(row):
        try:
            result = root_scalar(
                equilibrium_gap,
                args=(
                    row["Cs"], row["Cd"],
                    row["elasticity_supply"], row["elasticity_demand"],
                    row["expected_demand_reduction_percent"],
                ),
                method="brentq",
                bracket=[1e-3, 1e3],
            )
            if result.converged:
                P_new = result.root
                Q_new = row["Cs"] * (P_new ** row["elasticity_supply"])
                return pd.Series({"P_eq_new": P_new, "Q_eql_new": Q_new})
        except Exception:
            pass
        return pd.Series({"P_eq_new": np.nan, "Q_eql_new": np.nan})

    result_df = merged.copy()
    result_df["expected_demand_reduction"] = (
        result_df["initial_eql_quantity"] * result_df["expected_demand_reduction_percent"]
    )
    result_df[["P_eq_new", "Q_eql_new"]] = result_df.apply(compute_equilibrium, axis=1)
    result_df["actual_reduction"] = result_df["Q_eql_new"] - result_df["initial_eql_quantity"]

    result_df = pd.merge(
        result_df,
        carbon_intensity[["ISO", "final_food_group", "carbon_intensity_t"]],
        how="left", on=["ISO", "final_food_group"],
    )
    result_df["carbon_savings_t"] = result_df["actual_reduction"] * result_df["carbon_intensity_t"]

    # Annual food savings per (ISO, Country, scenario) — positive = savings
    food_savings = (
        result_df.groupby(["ISO", "Country", "scenario"])["carbon_savings_t"]
        .sum()
        .abs()
        .reset_index()
        .rename(columns={"carbon_savings_t": "annual_food_savings_t"})
    )

    return food_savings


# =====================================================================
# PART 2: Load mortality-side emissions
# =====================================================================

def load_mortality_emissions():
    """Load year-by-year survivor emissions from Mortality Model output.

    The CSV is generated by the Mortality Model notebook's final cell.
    When run_multi_simulation() uses population_weighted=True (the
    default since the weighting fix), diff_Y{k} values are already at
    population level and so are the derived emissions_Y{k} columns.
    No post-hoc scaling is needed.

    If the CSV was generated with population_weighted=False (original
    sample-level output), the break-even ratios will be off by the
    average weighting factor — re-run the mortality model with
    population_weighted=True to fix.
    """
    mort = pd.read_csv("mortality model total emissions.csv")
    return mort


# =====================================================================
# PART 3: Compute break-even
# =====================================================================

def compute_breakeven(food_savings, mort):
    """For each (ISO, scenario), find the year where cumulative food savings
    exceed cumulative survivor emissions."""

    merged = pd.merge(food_savings, mort, on=["ISO", "scenario"], how="inner")

    records = []
    for _, row in merged.iterrows():
        annual_food = row["annual_food_savings_t"]

        cum_food = 0.0
        cum_mort = 0.0
        breakeven_year = None

        yearly_food = []
        yearly_mort = []

        for y in range(1, 11):
            cum_food += annual_food
            cum_mort += row[f"emissions_Y{y}"]
            yearly_food.append(cum_food)
            yearly_mort.append(cum_mort)

            if breakeven_year is None and cum_food < cum_mort:
                # Food savings behind — check if they catch up later
                pass

        # Determine break-even: first year where cum_food >= cum_mort
        # Since food savings grow linearly and survivor emissions grow
        # sub-linearly (or linearly), check year by year
        breakeven_year = None
        for y in range(10):
            if yearly_food[y] >= yearly_mort[y]:
                if y == 0:
                    breakeven_year = 1.0
                else:
                    if yearly_food[y - 1] < yearly_mort[y - 1]:
                        # Crossover between year y and y+1; interpolate
                        gap_prev = yearly_mort[y - 1] - yearly_food[y - 1]
                        gap_curr = yearly_food[y] - yearly_mort[y]
                        frac = gap_prev / (gap_prev + gap_curr)
                        breakeven_year = y + frac
                    else:
                        breakeven_year = 1.0
                break

        if breakeven_year is None:
            breakeven_year = float("inf")

        # Food savings always dominate from year 1?
        food_dominates_all = all(
            yearly_food[y] >= yearly_mort[y] for y in range(10)
        )

        records.append({
            "ISO": row["ISO"],
            "Country": row["Country"],
            "scenario": row["scenario"],
            "annual_food_savings_t": annual_food,
            "total_survivor_emissions_10yr": cum_mort,
            "total_food_savings_10yr": cum_food,
            "ratio_food_to_mort": cum_food / cum_mort if cum_mort > 0 else float("inf"),
            "breakeven_year": breakeven_year,
            "food_dominates_all_years": food_dominates_all,
            **{f"cum_food_Y{y+1}": yearly_food[y] for y in range(10)},
            **{f"cum_mort_Y{y+1}": yearly_mort[y] for y in range(10)},
        })

    return pd.DataFrame(records)


# =====================================================================
# PART 4: Figures
# =====================================================================

def plot_breakeven_bars(be_df):
    """Figure A: Break-even year by country for both scenarios."""

    max_up = be_df[be_df["scenario"] == "max_uptake"].copy()
    mod_up = be_df[be_df["scenario"] == "mod_uptake"].copy()

    # All countries break even in year 1 — show ratio instead
    max_up = max_up.sort_values("ratio_food_to_mort", ascending=True)
    country_order = max_up["Country"].tolist()

    fig, ax = plt.subplots(figsize=(12, max(8, len(country_order) * 0.28)))

    y = np.arange(len(country_order))
    bar_height = 0.35

    max_ratios = []
    mod_ratios = []
    for country in country_order:
        mr = max_up[max_up["Country"] == country]["ratio_food_to_mort"].values
        max_ratios.append(mr[0] if len(mr) > 0 else 0)
        mr2 = mod_up[mod_up["Country"] == country]["ratio_food_to_mort"].values
        mod_ratios.append(mr2[0] if len(mr2) > 0 else 0)

    ax.barh(
        y + bar_height / 2, max_ratios, bar_height,
        label="Maximum uptake (95%)", color="#2166ac", edgecolor="white", linewidth=0.5,
    )
    ax.barh(
        y - bar_height / 2, mod_ratios, bar_height,
        label="Moderate uptake (50%)", color="#92c5de", edgecolor="white", linewidth=0.5,
    )

    ax.set_yticks(y)
    ax.set_yticklabels(country_order, fontsize=7)
    ax.set_xlabel("Ratio: Cumulative Food Savings / Cumulative Survivor Emissions (10-year)", fontsize=10)
    ax.set_title(
        "Break-Even Analysis: Food Emission Savings vs. Survivor Emissions\n"
        "All countries break even in Year 1 — bars show 10-year savings-to-emissions ratio",
        fontsize=12, fontweight="bold", pad=15,
    )
    ax.axvline(x=1, color="red", linestyle="--", linewidth=1, label="Break-even line (ratio = 1)")
    ax.set_xscale("log")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)

    # Annotate top 5
    for i in range(len(country_order) - 1, max(len(country_order) - 6, -1), -1):
        ax.text(
            max_ratios[i] * 1.1, y[i] + bar_height / 2,
            f"{max_ratios[i]:,.0f}x", va="center", fontsize=6, color="#2166ac", fontweight="bold",
        )

    plt.tight_layout()
    out = "test/breakeven_by_country.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


def plot_breakeven_curves(be_df):
    """Figure B: Cumulative food savings vs survivor emissions over 10 years
    for the top countries by food savings (max uptake)."""

    max_up = be_df[be_df["scenario"] == "max_uptake"].copy()
    top = max_up.nlargest(8, "annual_food_savings_t")

    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    axes = axes.flatten()
    years = np.arange(1, 11)

    for idx, (_, row) in enumerate(top.iterrows()):
        ax = axes[idx]

        cum_food = [row[f"cum_food_Y{y}"] for y in range(1, 11)]
        cum_mort = [row[f"cum_mort_Y{y}"] for y in range(1, 11)]

        # Scale to kt for readability
        cum_food_kt = [v / 1e3 for v in cum_food]
        cum_mort_kt = [v / 1e3 for v in cum_mort]

        ax.plot(years, cum_food_kt, "b-o", markersize=4, linewidth=2,
                label="Food savings (cumulative)")
        ax.plot(years, cum_mort_kt, "r-s", markersize=4, linewidth=2,
                label="Survivor emissions (cumulative)")

        ax.fill_between(years, cum_mort_kt, cum_food_kt, alpha=0.15, color="blue")

        ax.set_title(f"{row['Country']}", fontsize=10, fontweight="bold")
        ax.set_xlabel("Year", fontsize=8)
        ax.set_ylabel("kt CO₂eq", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        ratio = row["ratio_food_to_mort"]
        ax.text(
            0.97, 0.05,
            f"Ratio: {ratio:,.0f}x",
            transform=ax.transAxes, fontsize=8, ha="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", edgecolor="gray"),
        )

        if idx == 0:
            ax.legend(fontsize=7, loc="upper left")

    fig.suptitle(
        "Cumulative Food-Emission Savings vs. Survivor Emissions (Max Uptake)\n"
        "Blue shading = net emission reduction from semaglutide",
        fontsize=13, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    out = "test/breakeven_curves.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out}")


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("=" * 65)
    print("BREAK-EVEN ANALYSIS")
    print("Food-emission savings vs. survivor emissions from semaglutide")
    print("=" * 65)

    print("\n[1/4] Computing annual food-emission savings...")
    food_savings = compute_food_savings()

    print("[2/4] Loading mortality-model emissions...")
    mort = load_mortality_emissions()

    print("[3/4] Computing break-even...")
    be_df = compute_breakeven(food_savings, mort)

    # Summary
    print("\n" + "=" * 65)
    print("RESULTS")
    print("=" * 65)

    for scenario in ["max_uptake", "mod_uptake"]:
        sub = be_df[be_df["scenario"] == scenario].copy()
        label = "Maximum uptake (95%)" if scenario == "max_uptake" else "Moderate uptake (50%)"
        print(f"\n--- {label} ---\n")

        all_break_y1 = sub["food_dominates_all_years"].all()
        print(f"  All countries break even in Year 1: {'YES' if all_break_y1 else 'NO'}")

        if not all_break_y1:
            late = sub[~sub["food_dominates_all_years"]].sort_values("breakeven_year")
            print(f"  Countries NOT breaking even in Year 1:")
            for _, r in late.iterrows():
                be = r["breakeven_year"]
                be_str = f"Year {be:.1f}" if be <= 10 else ">10 years"
                print(f"    {r['Country']:40s}  break-even: {be_str}")

        sub_sorted = sub.sort_values("ratio_food_to_mort", ascending=False)
        print(f"\n  {'Country':40s}  {'Food (kt/yr)':>12s}  {'Mort 10yr (kt)':>14s}  {'Ratio':>10s}")
        print("  " + "-" * 80)
        for _, r in sub_sorted.iterrows():
            ratio_str = f"{r['ratio_food_to_mort']:10,.1f}x" if np.isfinite(r['ratio_food_to_mort']) else "       inf"
            print(
                f"  {r['Country']:40s}  "
                f"{r['annual_food_savings_t']/1e3:12,.0f}  "
                f"{r['total_survivor_emissions_10yr']/1e3:14,.1f}  "
                f"{ratio_str}"
            )

        total_food = sub["annual_food_savings_t"].sum()
        total_mort = sub["total_survivor_emissions_10yr"].sum()
        print("  " + "-" * 80)
        print(
            f"  {'TOTAL':40s}  "
            f"{total_food/1e3:12,.0f}  "
            f"{total_mort/1e3:14,.1f}  "
            f"{total_food * 10 / total_mort:10,.1f}x"
        )

    print(f"\n[4/4] Generating figures...")
    plot_breakeven_bars(be_df)
    plot_breakeven_curves(be_df)

    # Key finding
    print("\n" + "=" * 65)
    print("KEY FINDING")
    print("=" * 65)
    max_sub = be_df[be_df["scenario"] == "max_uptake"]
    # Exclude countries with no food data (0 savings)
    valid = max_sub[
        (max_sub["annual_food_savings_t"] > 0)
        & (max_sub["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(max_sub["ratio_food_to_mort"])
    ]
    min_ratio = valid["ratio_food_to_mort"].min()
    min_country = valid.loc[valid["ratio_food_to_mort"].idxmin(), "Country"]
    global_food = valid["annual_food_savings_t"].sum()
    global_mort = valid["total_survivor_emissions_10yr"].sum()
    n_no_data = len(max_sub) - len(valid)
    mort_units = f"{global_mort/1e6:.1f} Mt" if global_mort >= 1e6 else f"{global_mort/1e3:.1f} kt"

    print(f"\n  ({n_no_data} countries excluded due to missing food/mortality data)")
    print(f"\n  Global (max uptake, {len(valid)} countries):")
    print(f"    Annual food savings:          {global_food/1e6:.1f} Mt CO2eq/year")
    print(f"    10-year food savings:         {global_food*10/1e6:.1f} Mt CO2eq")
    print(f"    10-year survivor emissions:   {mort_units} CO2eq")
    print(f"    10-year ratio:                {global_food*10/global_mort:,.1f}x")
    print(f"\n  Smallest margin: {min_country} ({min_ratio:,.1f}x over 10 years)")

    all_y1 = valid["food_dominates_all_years"].all()
    if all_y1:
        print("\n  All countries with data break even in Year 1.")
    else:
        n_late = (~valid["food_dominates_all_years"]).sum()
        print(f"\n  {len(valid) - n_late}/{len(valid)} countries break even in Year 1.")

    print("""
  NOTE: This analysis assumes mortality model total emissions.csv was
  generated with population_weighted=True in run_multi_simulation().
  If using the original sample-level output, re-run the mortality model
  with population_weighted=True for correct cross-model comparison.
""")


if __name__ == "__main__":
    main()
