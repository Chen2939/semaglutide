"""
build_carbon_intensity.py

Generates country-specific carbon intensity (kg CO2eq/kg) per food group
by mapping Poore & Nemecek (2018) GHG values onto FAOSTAT country-level
food consumption weights.

Sources:
  - Poore & Nemecek (2018) Science 360, 987-992: GHG per kg at retail
    via recategorize/aaq0216_datas2.xls "Results - Retail Weight"
  - FAOSTAT Food Balance Sheets (2022): country-level consumption
  - Food data/FBS_Group_Mapping.csv: 115 FAOSTAT items -> 9 food groups
"""

import pandas as pd
import numpy as np

# ============================================================
# P&N GHG values (kg CO2eq per kg retail weight, Mean, IPCC 2013)
# From aaq0216_datas2.xls "Results - Retail Weight" sheet
# ============================================================

# Composite values from P&N "Results - Global Totals" production volumes
_BOVINE_GHG = (40571 * 99.48 + 31425 * 33.30) / (40571 + 31425)  # ~70.6
_DAIRY_GHG = (470267 * 3.15 + 21191 * 23.88) / (470267 + 21191)  # ~4.04
_SUGAR_RAW_GHG = (141702 * 3.20 + 34038 * 1.81) / (141702 + 34038)  # ~2.93

# ============================================================
# FAOSTAT aggregate items to EXCLUDE from weighted averages
# These are parent-level totals that double-count sub-items.
# Groups with a single item (Eggs, Dairy) are NOT excluded.
# ============================================================

AGGREGATE_ITEMS = {
    "Cereals - Excluding Beer",
    "Starchy Roots",
    "Meat",
    "Offals",
    "Oilcrops",
    "Vegetable Oils",
    "Animal fats",
    "Fruits - Excluding Wine",
    "Vegetables",
    "Pulses",
    "Spices",
    "Stimulants",
    "Sugar & Sweeteners",
    "Sugar Crops",
    "Treenuts",
    "Alcoholic Beverages",
    "Fish, Seafood",
    "Aquatic Products, Other",
    "Miscellaneous",
}

# ============================================================
# Complete mapping: 115 FAOSTAT items -> GHG (kg CO2eq/kg)
#
# Three tiers:
#   Direct match:  FAOSTAT item has a clear P&N counterpart
#   Close proxy:   No exact match; assigned nearest P&N product
#   Group fallback: Aggregate items (excluded from calculation)
# ============================================================

FAOSTAT_TO_GHG = {
    # --- Cereals (includes starchy roots per FAOSTAT grouping) ---
    "Wheat and products":       1.57,   # P&N: Wheat & Rye
    "Rice and products":        4.45,   # P&N: Rice
    "Barley and products":      1.18,   # P&N: Barley
    "Maize and products":       1.70,   # P&N: Maize
    "Rye and products":         1.57,   # P&N: Wheat & Rye
    "Oats":                     2.48,   # P&N: Oatmeal
    "Sorghum and products":     1.70,   # Proxy: Maize (similar grain)
    "Cereals, other":           1.70,   # Proxy: Maize (generic cereal)
    "Millet and products":      1.70,   # Proxy: Maize (similar grain)
    "Cassava and products":     1.32,   # P&N: Cassava
    "Potatoes and products":    0.46,   # P&N: Potatoes
    "Sweet potatoes":           1.32,   # Proxy: Cassava (tropical tuber)
    "Roots, Other":             0.43,   # P&N: Root Vegetables
    "Yams":                     1.32,   # Proxy: Cassava (tropical tuber)

    # --- Dairy ---
    "Milk - Excluding Butter":  _DAIRY_GHG,  # Production-weighted Milk + Cheese

    # --- Eggs ---
    "Eggs":                     4.67,   # P&N: Eggs

    # --- Fats and oils ---
    "Soyabeans":                3.16,   # P&N: Tofu (soy product)
    "Groundnuts":               3.23,   # P&N: Groundnuts
    "Sunflower seed":           3.60,   # P&N: Sunflower Oil
    "Coconuts - Incl Copra":    5.42,   # Proxy: Olive Oil (tree crop)
    "Rape and Mustardseed":     3.77,   # P&N: Rapeseed Oil
    "Sesame seed":              3.60,   # Proxy: Sunflower Oil (seed crop)
    "Oilcrops, Other":          3.60,   # Proxy: mid-range seed crop
    "Olives (including preserved)": 5.42, # P&N: Olive Oil
    "Cottonseed":               3.60,   # Proxy: mid-range seed crop
    "Palm kernels":             7.32,   # P&N: Palm Oil
    "Soyabean Oil":             6.32,   # P&N: Soybean Oil
    "Groundnut Oil":            3.23,   # Proxy: Groundnuts
    "Rape and Mustard Oil":     3.77,   # P&N: Rapeseed Oil
    "Palm Oil":                 7.32,   # P&N: Palm Oil
    "Coconut Oil":              5.42,   # Proxy: tree-crop oil
    "Sunflowerseed Oil":        3.60,   # P&N: Sunflower Oil
    "Sesameseed Oil":           3.60,   # Proxy: Sunflower Oil
    "Olive Oil":                5.42,   # P&N: Olive Oil
    "Oilcrops Oil, Other":      4.50,   # Proxy: avg across oils
    "Cottonseed Oil":           3.60,   # Proxy: seed-based oil
    "Maize Germ Oil":           1.70,   # Proxy: Maize-derived
    "Palmkernel Oil":           7.32,   # P&N: Palm Oil
    "Ricebran Oil":             4.45,   # Proxy: Rice-derived
    "Butter, Ghee":             _DAIRY_GHG, # Dairy fat byproduct
    "Cream":                    _DAIRY_GHG, # Dairy product
    "Fats, Animals, Raw":       12.31,  # Proxy: Pig Meat (animal fat source)
    "Fish, Body Oil":           13.63,  # P&N: Fish (farmed)
    "Fish, Liver Oil":          13.63,  # P&N: Fish (farmed)

    # --- Fish ---
    "Freshwater Fish":          13.63,  # P&N: Fish (farmed)
    "Demersal Fish":            13.63,  # P&N: Fish (farmed)
    "Pelagic Fish":             13.63,  # P&N: Fish (farmed)
    "Marine Fish, Other":       13.63,  # P&N: Fish (farmed)
    "Crustaceans":              26.87,  # P&N: Prawns (farmed)
    "Cephalopods":              13.63,  # P&N: Fish (farmed)
    "Molluscs, Other":          13.63,  # P&N: Fish (farmed)
    "Aquatic Animals, Others":  13.63,  # P&N: Fish (farmed)
    "Aquatic Plants":           0.53,   # Proxy: Other Vegetables (aquatic plant)

    # --- Fruit and vegetables ---
    "Oranges, Mandarines":      0.39,   # P&N: Citrus Fruit
    "Lemons, Limes and products": 0.39, # P&N: Citrus Fruit
    "Citrus, Other":            0.39,   # P&N: Citrus Fruit
    "Bananas":                  0.86,   # P&N: Bananas
    "Plantains":                0.86,   # Proxy: Bananas
    "Apples and products":      0.43,   # P&N: Apples
    "Pineapples and products":  1.05,   # Proxy: Other Fruit
    "Grapefruit and products":  0.39,   # P&N: Citrus Fruit
    "Grapes and products (excl wine)": 1.53, # P&N: Berries & Grapes
    "Fruits, other":            1.05,   # P&N: Other Fruit
    "Dates":                    1.05,   # Proxy: Other Fruit
    "Tomatoes and products":    2.09,   # P&N: Tomatoes
    "Vegetables, other":        0.53,   # P&N: Other Vegetables
    "Onions":                   0.50,   # P&N: Onions & Leeks

    # --- Meat ---
    "Bovine Meat":              _BOVINE_GHG, # Weighted beef herd + dairy herd
    "Mutton & Goat Meat":       39.72,  # P&N: Lamb & Mutton
    "Pigmeat":                  12.31,  # P&N: Pig Meat
    "Poultry Meat":             9.87,   # P&N: Poultry Meat
    "Meat, Other":              9.87,   # Proxy: Poultry (conservative)
    "Offals, Edible":           9.87,   # Proxy: Poultry (byproduct, low-value cut)

    # --- Other ---
    "Wine":                     1.79,   # P&N: Wine
    "Beer":                     1.18,   # P&N: Barley (Beer)
    "Beverages, Fermented":     1.18,   # Proxy: Beer
    "Beverages, Alcoholic":     1.18,   # Proxy: Beer
    "Alcohol, Non-Food":        1.18,   # Proxy: Beer
    "Coffee and products":      28.53,  # P&N: Coffee
    "Cocoa Beans and products": 46.65,  # P&N: Dark Chocolate
    "Tea (including mate)":     1.50,   # Proxy: low-emission beverage crop
    "Beans":                    1.79,   # P&N: Other Pulses
    "Peas":                     0.98,   # P&N: Peas
    "Pulses, Other and products": 1.79, # P&N: Other Pulses
    "Pepper":                   1.50,   # Proxy: low-emission crop
    "Pimento":                  1.50,   # Proxy: low-emission crop
    "Spices, Other":            1.50,   # Proxy: low-emission crop
    "Cloves":                   1.50,   # Proxy: low-emission crop
    "Nuts and products":        0.43,   # P&N: Nuts
    "Infant food":              3.00,   # Proxy: processed food blend

    # --- Sweets, confectionery, and sweetened beverages ---
    "Sugar (Raw Equivalent)":   _SUGAR_RAW_GHG,  # Weighted cane + beet
    "Sweeteners, Other":        _SUGAR_RAW_GHG,  # Proxy: sugar avg
    "Honey":                    1.00,   # Low-emission natural product
    "Sugar non-centrifugal":    3.20,   # P&N: Cane Sugar
    "Sugar cane":               3.20,   # P&N: Cane Sugar
    "Sugar beet":               1.81,   # P&N: Beet Sugar
}

# ============================================================
# Global fallback: production-weighted group averages from P&N
# Used when a country has no leaf-item data for a food group
# ============================================================

def compute_global_group_averages():
    """Compute production-weighted P&N average per food group."""
    group_products = {
        "Cereals": [
            ("Wheat & Rye", 482152, 1.57), ("Maize", 194554, 1.70),
            ("Barley", 206523, 1.18), ("Rice", 397780, 4.45),
            ("Oatmeal", 4463, 2.48), ("Cassava", 173814, 1.32),
            ("Potatoes", 332343, 0.46),
        ],
        "Dairy": [("Milk", 470267, 3.15), ("Cheese", 21191, 23.88)],
        "Eggs": [("Eggs", 63489, 4.67)],
        "Fats and oils": [
            ("Groundnuts", 11827, 3.23), ("Nuts", 15296, 0.43),
            ("Tofu", 11853, 3.16), ("Soybean Oil", 24148, 6.32),
            ("Palm Oil", 16691, 7.32), ("Sunflower Oil", 9554, 3.60),
            ("Rapeseed Oil", 10311, 3.77), ("Olive Oil", 2997, 5.42),
        ],
        "Fish": [("Fish (farmed)", 45223, 13.63), ("Crustaceans (farmed)", 10633, 26.87)],
        "Fruit and vegetables": [
            ("Tomatoes", 148957, 2.09), ("Brassicas", 77045, 0.51),
            ("Onions & Leeks", 77927, 0.50), ("Root Veg", 35154, 0.43),
            ("Other Veg", 654375, 0.53), ("Citrus", 127923, 0.39),
            ("Bananas", 128971, 0.86), ("Apples", 75781, 0.43),
            ("Berries & Grapes", 67079, 1.53), ("Other Fruit", 210650, 1.05),
        ],
        "Meat": [
            ("Beef (beef)", 40571, 99.48), ("Beef (dairy)", 31425, 33.30),
            ("Lamb & Mutton", 14195, 39.72), ("Pig Meat", 112892, 12.31),
            ("Poultry", 96439, 9.87),
        ],
        "Other": [
            ("Coffee", 7778, 28.53), ("Dark Chocolate", 4416, 46.65),
            ("Wine", 26013, 1.79), ("Other Pulses", 42765, 1.79),
            ("Peas", 6026, 0.98),
        ],
        "Sweets, confectionery, and sweetened beverages": [
            ("Cane Sugar", 141702, 3.20), ("Beet Sugar", 34038, 1.81),
            ("Dark Chocolate", 4416, 46.65),
        ],
    }
    averages = {}
    for group, products in group_products.items():
        total_prod = sum(p[1] for p in products)
        weighted = sum(p[1] * p[2] for p in products)
        averages[group] = weighted / total_prod if total_prod > 0 else 1.0
    return averages


# ============================================================
# MAIN: Build country-specific carbon intensity
# ============================================================

def main():
    mapping = pd.read_csv("Food data/FBS_Group_Mapping.csv")
    norm = pd.read_csv(
        "Food data/FoodBalanceSheets_E_All_Data_(Normalized)/"
        "FoodBalanceSheets_E_All_Data_(Normalized).csv"
    )
    iso_map = pd.read_csv("Food data/faostat_country_mapping.csv")
    old_ci = pd.read_csv("Food data/carbon_intensity.csv")

    global_avg = compute_global_group_averages()
    food_groups = [
        "Cereals", "Dairy", "Eggs", "Fats and oils", "Fish",
        "Fruit and vegetables", "Meat", "Other",
        "Sweets, confectionery, and sweetened beverages",
    ]

    # Filter FAOSTAT to 2022 food supply and merge mappings
    food = norm[(norm["Year"] == 2022) & (norm["Element"] == "Food")].copy()
    food = pd.merge(food, iso_map, on="Area", how="left")
    food = pd.merge(
        food,
        mapping.set_index("fbs_group")[["final_food_group"]],
        left_on="Item", right_index=True, how="left",
    )

    # Assign GHG values and flag aggregates
    food["ghg_per_kg"] = food["Item"].map(FAOSTAT_TO_GHG)
    food["is_aggregate"] = food["Item"].isin(AGGREGATE_ITEMS)

    # Use only leaf items (non-aggregate) with positive consumption
    leaves = food[(~food["is_aggregate"]) & (food["Value"] > 0)].copy()
    leaves["weighted_ghg"] = leaves["Value"] * leaves["ghg_per_kg"]

    # Weighted average per country x food group
    grouped = leaves.groupby(["ISO", "final_food_group"]).agg(
        total_consumption=("Value", "sum"),
        total_weighted_ghg=("weighted_ghg", "sum"),
    ).reset_index()
    grouped["ci"] = grouped["total_weighted_ghg"] / grouped["total_consumption"]

    # Pivot to wide format
    ci_wide = grouped.pivot(
        index="ISO", columns="final_food_group", values="ci"
    ).reindex(columns=food_groups)

    # Countries in scope (from old carbon_intensity.csv)
    scope = old_ci[["ISO", "Country", "Region"]].copy()
    result = pd.merge(scope, ci_wide, on="ISO", how="left")

    # Fill missing food groups with global P&N average
    for fg in food_groups:
        result[fg] = result[fg].fillna(global_avg.get(fg, 1.0))

    # For 7 countries with no FAOSTAT data, use regional average
    has_data = set(grouped["ISO"].unique())
    for idx, row in result.iterrows():
        if row["ISO"] not in has_data:
            region = row["Region"]
            region_rows = result[
                (result["Region"] == region) & (result["ISO"].isin(has_data))
            ]
            if len(region_rows) > 0:
                for fg in food_groups:
                    result.at[idx, fg] = region_rows[fg].mean()

    # Round to 6 decimal places
    for fg in food_groups:
        result[fg] = result[fg].round(6)

    # Back up old file and write new one
    old_ci.to_csv("Food data/carbon_intensity_old.csv", index=False)
    result.to_csv("Food data/carbon_intensity.csv", index=False)

    # Print validation summary
    print("=== Carbon Intensity Summary (kg CO2eq/kg) ===\n")
    print(f"Countries: {len(result)}")
    print(f"Countries with FAOSTAT data: {len(has_data & set(scope['ISO']))}")
    print(f"Countries using regional avg: {len(scope) - len(has_data & set(scope['ISO']))}")
    print()

    for fg in food_groups:
        vals = result[fg]
        print(f"  {fg:50s} min={vals.min():.2f}  mean={vals.mean():.2f}  max={vals.max():.2f}")

    print("\n=== Spot Checks ===\n")
    for iso in ["JPN", "USA", "AUS", "BRA", "GBR", "SAU"]:
        row = result[result["ISO"] == iso]
        if len(row) > 0:
            row = row.iloc[0]
            print(f"  {iso} ({row['Country']}):")
            print(f"    Cereals={row['Cereals']:.2f}  Dairy={row['Dairy']:.2f}  "
                  f"Meat={row['Meat']:.2f}  Fruit&Veg={row['Fruit and vegetables']:.2f}")

    # Warn about items without GHG assignment
    unmapped = leaves[leaves["ghg_per_kg"].isna()]["Item"].unique()
    if len(unmapped) > 0:
        print(f"\nWARNING: {len(unmapped)} FAOSTAT items without GHG values:")
        for item in unmapped:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
