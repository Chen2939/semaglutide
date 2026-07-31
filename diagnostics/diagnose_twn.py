"""Why does TWN have exactly 0.0 food savings despite being in the FAOSTAT
mapping? Locates which input is missing. Read-only."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_visualization.pipeline import ROOT, compute_food_savings

pd.set_option("display.width", 240)

_, result_df = compute_food_savings(survival_weighted=False)
twn = result_df[(result_df["ISO"] == "TWN") & (result_df["scenario"] == "max_uptake")]
print(f"result_df rows for TWN, max_uptake: {len(twn)}")
cols = [
    "final_food_group", "initial_eql_quantity", "price", "elasticity_supply",
    "elasticity_demand", "expected_demand_reduction_percent", "Q_eql_new",
    "actual_reduction", "carbon_intensity_t", "carbon_savings_t",
]
print(twn[[c for c in cols if c in twn.columns]].to_string(index=False))
print()
print("Null counts across those columns:")
print(twn[[c for c in cols if c in twn.columns]].isna().sum().to_string())

print()
print("Raw FAOSTAT presence for the mapped area name:")
norm = pd.read_csv(
    ROOT / "Food data" / "FoodBalanceSheets_E_All_Data_(Normalized)"
    / "FoodBalanceSheets_E_All_Data_(Normalized).csv"
)
area = "China, Taiwan Province of"
sub = norm[(norm["Area"] == area) & (norm["Year"] == 2022)]
print(f"  FBS rows for {area!r} in 2022: {len(sub)}")
print(f"  of which Element == 'Food': "
      f"{len(sub[sub['Element'] == 'Food'])}")
print(f"  any year at all for that area: {len(norm[norm['Area'] == area]):,} rows; "
      f"years {sorted(norm.loc[norm['Area'] == area, 'Year'].unique())[:5]}..."
      f"{sorted(norm.loc[norm['Area'] == area, 'Year'].unique())[-3:]}"
      if len(norm[norm["Area"] == area]) else "  area absent from FBS entirely")

print()
print("Price index presence:")
cpi = pd.read_csv(
    ROOT / "Food data" / "ConsumerPriceIndices_E_All_Data_(Normalized)"
    / "ConsumerPriceIndices_E_All_Data_(Normalized).csv"
)
print(f"  CPI rows for {area!r}: {len(cpi[cpi['Area'] == area]):,}")

print()
print("Carbon-intensity file presence:")
ci = pd.read_csv(ROOT / "Food data" / "carbon_intensity.csv")
print(f"  TWN in carbon_intensity.csv: {'TWN' in set(ci['ISO'])}")
