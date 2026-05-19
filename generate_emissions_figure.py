"""
generate_emissions_figure.py

Produces a figure showing carbon emissions saved from food reduction
by country, for both moderate and maximum semaglutide uptake scenarios.

Runs the full Price Rebound Model pipeline (data loading, equilibrium
solving, carbon savings calculation) and outputs:
  test/emissions_saved_by_country.png

Usage:
    python generate_emissions_figure.py
"""

import numpy as np
import pandas as pd
import pyreadr
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy.optimize import root_scalar


# ── 1. Load data ──────────────────────────────────────────────────────────

sim_result = list(pyreadr.read_r("full_simulation_results8.rds").values())[0]
sim_result["weighted_eer"] = sim_result["weighting"] * sim_result["eer"]
sim_result["weighted_treatment_eer"] = sim_result["weighting"] * sim_result["treatment_eer"]

norm = pd.read_csv(
    "Food data/FoodBalanceSheets_E_All_Data_(Normalized)/"
    "FoodBalanceSheets_E_All_Data_(Normalized).csv"
)
raw = pd.read_csv("Food data/FoodBalanceSheets_E_All_Data/FoodBalanceSheets_E_All_Data.csv")
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

# ── 2. Prepare FAOSTAT food quantities ────────────────────────────────────

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

# ── 3. Prepare price and elasticity data ──────────────────────────────────

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
carbon_intensity["carbon_intensity_t"] = carbon_intensity["carbon_intensity_t"] * 1000

# ── 4. Build merged model DataFrame ──────────────────────────────────────

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
sim_result_perc["diff"] = (
    sim_result_perc["weighted_treatment_eer"] - sim_result_perc["weighted_eer"]
)
sim_result_perc["expected_demand_reduction_percent"] = (
    sim_result_perc["weighted_treatment_eer"] / sim_result_perc["weighted_eer"]
) - 1

merged = pd.merge(
    merged,
    sim_result_perc[["expected_demand_reduction_percent"]].reset_index(),
    on="ISO", how="left",
)

# ── 5. Solve equilibrium ─────────────────────────────────────────────────


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
            Q_eql_new = row["Cs"] * (P_new ** row["elasticity_supply"])
            return pd.Series({"P_eq_new": P_new, "Q_eql_new": Q_eql_new})
    except Exception:
        pass
    return pd.Series({"P_eq_new": np.nan, "Q_eql_new": np.nan})


result_df = merged.copy()
result_df["expected_demand_reduction"] = (
    result_df["initial_eql_quantity"] * result_df["expected_demand_reduction_percent"]
)
result_df[["P_eq_new", "Q_eql_new"]] = result_df.apply(compute_equilibrium, axis=1)
result_df["actual_reduction"] = result_df["Q_eql_new"] - result_df["initial_eql_quantity"]
result_df["rebound_effect"] = result_df["actual_reduction"] - result_df["expected_demand_reduction"]
result_df["rebound_effect_percent"] = (
    -1 * result_df["rebound_effect"] / result_df["expected_demand_reduction"]
)

result_df = pd.merge(
    result_df,
    carbon_intensity[["ISO", "final_food_group", "carbon_intensity_t"]],
    how="left", on=["ISO", "final_food_group"],
)
result_df["carbon_savings_t"] = result_df["actual_reduction"] * result_df["carbon_intensity_t"]

# ── 6. Generate figure ───────────────────────────────────────────────────

country_totals = (
    result_df.groupby(["Country", "ISO", "scenario"])["carbon_savings_t"]
    .sum()
    .abs()
    .reset_index()
)
country_totals["carbon_savings_kt"] = country_totals["carbon_savings_t"] / 1e3

# Sort by max_uptake savings
sort_order = (
    country_totals[country_totals["scenario"] == "max_uptake"]
    .sort_values("carbon_savings_kt", ascending=True)
    .set_index("Country")
    .index.tolist()
)

fig, ax = plt.subplots(figsize=(12, max(10, len(sort_order) * 0.28)))

y = np.arange(len(sort_order))
bar_height = 0.35

max_vals = []
mod_vals = []
for country in sort_order:
    max_row = country_totals[
        (country_totals["Country"] == country) & (country_totals["scenario"] == "max_uptake")
    ]
    mod_row = country_totals[
        (country_totals["Country"] == country) & (country_totals["scenario"] == "mod_uptake")
    ]
    max_vals.append(max_row["carbon_savings_kt"].values[0] if len(max_row) > 0 else 0)
    mod_vals.append(mod_row["carbon_savings_kt"].values[0] if len(mod_row) > 0 else 0)

bars_max = ax.barh(
    y + bar_height / 2, max_vals, bar_height,
    label="Maximum uptake (95%)", color="#2166ac", edgecolor="white", linewidth=0.5,
)
bars_mod = ax.barh(
    y - bar_height / 2, mod_vals, bar_height,
    label="Moderate uptake (50%)", color="#92c5de", edgecolor="white", linewidth=0.5,
)

ax.set_yticks(y)
ax.set_yticklabels(sort_order, fontsize=7.5)
ax.set_xlabel("Carbon Emissions Saved (thousand tonnes CO₂eq)", fontsize=11)
ax.set_title(
    "Carbon Emissions Saved from Reduced Food Consumption\nby Country and Uptake Scenario",
    fontsize=13, fontweight="bold", pad=15,
)
ax.legend(loc="lower right", fontsize=10, framealpha=0.9)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
ax.grid(axis="x", alpha=0.25, linewidth=0.5)
ax.set_axisbelow(True)

# Annotate top 10 with numbers for both scenarios
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
out_path = "test/emissions_saved_by_country.png"
plt.savefig(out_path, dpi=200, bbox_inches="tight")
plt.close()

# ── 7. Print summary ─────────────────────────────────────────────────────

print(f"Figure saved: {out_path}\n")
print("Top 10 countries by emissions saved (max uptake):")
print(f"{'Country':30s}  {'Max (kt)':>10s}  {'Mod (kt)':>10s}")
print("-" * 54)
for i in range(len(sort_order) - 1, max(len(sort_order) - 11, -1), -1):
    print(f"{sort_order[i]:30s}  {max_vals[i]:10,.0f}  {mod_vals[i]:10,.0f}")

total_max = sum(max_vals)
total_mod = sum(mod_vals)
print("-" * 54)
print(f"{'TOTAL':30s}  {total_max:10,.0f}  {total_mod:10,.0f}")
print(f"\nTotal: {total_max/1e3:.1f} Mt (max) / {total_mod/1e3:.1f} Mt (mod)")
