"""
build_carbon_intensity.py

Generates country-specific carbon intensity (kg CO2eq/kg) per food group
by mapping Poore & Nemecek (2018) GHG values onto FAOSTAT country-level
food consumption weights.

Supports three scenarios via --scenario flag:
  mean  (default) — central estimate
  p10   — 10th percentile (low-emission bound)
  p90   — 90th percentile (high-emission bound)

Sources:
  - Poore & Nemecek (2018) Science 360, 987-992: GHG per kg at retail
    via recategorize/aaq0216_datas2.xls "Results - Retail Weight"
  - FAOSTAT Food Balance Sheets (2022): country-level consumption
  - Food data/FBS_Group_Mapping.csv: 115 FAOSTAT items -> 9 food groups
"""

import argparse
import pandas as pd
import numpy as np

# ============================================================
# P&N GHG values (kg CO2eq per kg retail weight, IPCC 2013)
# From aaq0216_datas2.xls "Results - Retail Weight" sheet
#
# Each product has three values: (p10, mean, p90)
# Composite bovine/dairy/sugar values use the same production
# weights from "Results - Global Totals" across all scenarios.
# ============================================================

_PROD_BEEF_HERD = 40571
_PROD_DAIRY_HERD = 31425
_PROD_MILK = 470267
_PROD_CHEESE = 21191
_PROD_CANE = 141702
_PROD_BEET = 34038

def _composite(prod_a, val_a, prod_b, val_b):
    return (prod_a * val_a + prod_b * val_b) / (prod_a + prod_b)

GHG_SCENARIOS = {
    "mean": {
        "bovine":    _composite(_PROD_BEEF_HERD, 99.48, _PROD_DAIRY_HERD, 33.30),
        "dairy":     _composite(_PROD_MILK, 3.15, _PROD_CHEESE, 23.88),
        "sugar_raw": _composite(_PROD_CANE, 3.20, _PROD_BEET, 1.81),
        "beef_herd": 99.48, "dairy_herd": 33.30,
        "lamb": 39.72, "pig": 12.31, "poultry": 9.87,
        "eggs": 4.67, "milk": 3.15, "cheese": 23.88,
        "fish": 13.63, "shrimp": 26.87,
        "wheat": 1.57, "maize": 1.70, "barley": 1.18,
        "oat": 2.48, "rice": 4.45,
        "potato": 0.46, "cassava": 1.32, "root_veg": 0.43,
        "tomato": 2.09, "onion": 0.50, "other_veg": 0.53,
        "citrus": 0.39, "banana": 0.86, "apple": 0.43,
        "berry_grape": 1.53, "other_fruit": 1.05,
        "groundnut": 3.23, "nut": 0.43, "tofu": 3.16,
        "soybean_oil": 6.32, "palm_oil": 7.32,
        "sunflower_oil": 3.60, "rapeseed_oil": 3.77, "olive_oil": 5.42,
        "coffee": 28.53, "chocolate": 46.65,
        "wine": 1.79, "other_pulse": 1.79, "pea": 0.98,
        "cane_sugar": 3.20, "beet_sugar": 1.81,
        "soymilk": 0.98,
    },
    "p10": {
        "bovine":    _composite(_PROD_BEEF_HERD, 40.37, _PROD_DAIRY_HERD, 17.94),
        "dairy":     _composite(_PROD_MILK, 1.70, _PROD_CHEESE, 10.92),
        "sugar_raw": _composite(_PROD_CANE, 0.92, _PROD_BEET, 1.21),
        "beef_herd": 40.37, "dairy_herd": 17.94,
        "lamb": 24.52, "pig": 7.41, "poultry": 4.18,
        "eggs": 2.93, "milk": 1.70, "cheese": 10.92,
        "fish": 5.65, "shrimp": 8.04,
        "wheat": 0.79, "maize": 0.73, "barley": 0.70,
        "oat": 0.85, "rice": 1.46,
        "potato": 0.16, "cassava": 0.35, "root_veg": 0.24,
        "tomato": 0.39, "onion": 0.30, "other_veg": 0.23,
        "citrus": 0.08, "banana": 0.61, "apple": 0.29,
        "berry_grape": 0.77, "other_fruit": 0.35,
        "groundnut": 1.63, "nut": -3.65, "tofu": 1.60,
        "soybean_oil": 2.43, "palm_oil": 3.61,
        "sunflower_oil": 2.46, "rapeseed_oil": 2.50, "olive_oil": 2.86,
        "coffee": 5.20, "chocolate": -0.10,
        "wine": 0.91, "other_pulse": 0.98, "pea": 0.56,
        "cane_sugar": 0.92, "beet_sugar": 1.21,
        "soymilk": 0.58,
    },
    "p90": {
        "bovine":    _composite(_PROD_BEEF_HERD, 209.85, _PROD_DAIRY_HERD, 50.90),
        "dairy":     _composite(_PROD_MILK, 4.83, _PROD_CHEESE, 39.32),
        "sugar_raw": _composite(_PROD_CANE, 5.10, _PROD_BEET, 2.42),
        "beef_herd": 209.85, "dairy_herd": 50.90,
        "lamb": 54.44, "pig": 22.26, "poultry": 20.12,
        "eggs": 8.39, "milk": 4.83, "cheese": 39.32,
        "fish": 26.51, "shrimp": 52.12,
        "wheat": 2.31, "maize": 2.31, "barley": 1.64,
        "oat": 4.08, "rice": 8.77,
        "potato": 0.63, "cassava": 2.11, "root_veg": 0.56,
        "tomato": 5.95, "onion": 0.79, "other_veg": 0.97,
        "citrus": 0.56, "banana": 1.18, "apple": 0.57,
        "berry_grape": 2.67, "other_fruit": 2.93,
        "groundnut": 5.81, "nut": 3.84, "tofu": 5.55,
        "soybean_oil": 13.44, "palm_oil": 12.04,
        "sunflower_oil": 4.58, "rapeseed_oil": 4.64, "olive_oil": 7.63,
        "coffee": 84.85, "chocolate": 134.70,
        "wine": 2.65, "other_pulse": 3.75, "pea": 1.67,
        "cane_sugar": 5.10, "beet_sugar": 2.42,
        "soymilk": 1.47,
    },
}

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

def build_faostat_ghg_map(scenario="mean", dairy_raw_milk_basis=True):
    """Build FAOSTAT item -> GHG mapping for the given scenario.

    ``dairy_raw_milk_basis`` defaults to True (fix #2, now canonical): the
    Dairy-group item ``Milk - Excluding Butter`` — whose FAOSTAT mass is in
    whole-milk equivalent — is assigned the raw-milk CI (``g["milk"]`` ≈ 3.15)
    instead of the per-product milk+cheese blend (``g["dairy"]`` ≈ 4.04), which
    would otherwise double-count cheese intensity against milk-equivalent mass.
    This corrects a units mismatch, not a scenario assumption, so it applies to
    mean/p10/p90 alike. Set False only to reproduce the legacy blend.
    Butter/Cream (Fats-and-oils group) are left unchanged.
    """
    g = GHG_SCENARIOS[scenario]
    milk_basis = g["milk"] if dairy_raw_milk_basis else g["dairy"]

    # Proxy values that don't have a direct P&N product
    tea = 1.50 if scenario == "mean" else (0.75 if scenario == "p10" else 2.50)
    honey = 1.00 if scenario == "mean" else (0.50 if scenario == "p10" else 2.00)
    infant = 3.00 if scenario == "mean" else (1.50 if scenario == "p10" else 5.00)
    oilcrops_avg = (g["soybean_oil"] + g["palm_oil"] + g["sunflower_oil"]
                    + g["rapeseed_oil"] + g["olive_oil"]) / 5

    return {
        # --- Cereals ---
        "Wheat and products":       g["wheat"],
        "Rice and products":        g["rice"],
        "Barley and products":      g["barley"],
        "Maize and products":       g["maize"],
        "Rye and products":         g["wheat"],
        "Oats":                     g["oat"],
        "Sorghum and products":     g["maize"],
        "Cereals, other":           g["maize"],
        "Millet and products":      g["maize"],
        "Cassava and products":     g["cassava"],
        "Potatoes and products":    g["potato"],
        "Sweet potatoes":           g["cassava"],
        "Roots, Other":             g["root_veg"],
        "Yams":                     g["cassava"],

        # --- Dairy ---
        "Milk - Excluding Butter":  milk_basis,

        # --- Eggs ---
        "Eggs":                     g["eggs"],

        # --- Fats and oils ---
        "Soyabeans":                g["tofu"],
        "Groundnuts":               g["groundnut"],
        "Sunflower seed":           g["sunflower_oil"],
        "Coconuts - Incl Copra":    g["olive_oil"],
        "Rape and Mustardseed":     g["rapeseed_oil"],
        "Sesame seed":              g["sunflower_oil"],
        "Oilcrops, Other":          g["sunflower_oil"],
        "Olives (including preserved)": g["olive_oil"],
        "Cottonseed":               g["sunflower_oil"],
        "Palm kernels":             g["palm_oil"],
        "Soyabean Oil":             g["soybean_oil"],
        "Groundnut Oil":            g["groundnut"],
        "Rape and Mustard Oil":     g["rapeseed_oil"],
        "Palm Oil":                 g["palm_oil"],
        "Coconut Oil":              g["olive_oil"],
        "Sunflowerseed Oil":        g["sunflower_oil"],
        "Sesameseed Oil":           g["sunflower_oil"],
        "Olive Oil":                g["olive_oil"],
        "Oilcrops Oil, Other":      oilcrops_avg,
        "Cottonseed Oil":           g["sunflower_oil"],
        "Maize Germ Oil":           g["maize"],
        "Palmkernel Oil":           g["palm_oil"],
        "Ricebran Oil":             g["rice"],
        "Butter, Ghee":             g["dairy"],
        "Cream":                    g["dairy"],
        "Fats, Animals, Raw":       g["pig"],
        "Fish, Body Oil":           g["fish"],
        "Fish, Liver Oil":          g["fish"],

        # --- Fish ---
        "Freshwater Fish":          g["fish"],
        "Demersal Fish":            g["fish"],
        "Pelagic Fish":             g["fish"],
        "Marine Fish, Other":       g["fish"],
        "Crustaceans":              g["shrimp"],
        "Cephalopods":              g["fish"],
        "Molluscs, Other":          g["fish"],
        "Aquatic Animals, Others":  g["fish"],
        "Aquatic Plants":           g["other_veg"],

        # --- Fruit and vegetables ---
        "Oranges, Mandarines":      g["citrus"],
        "Lemons, Limes and products": g["citrus"],
        "Citrus, Other":            g["citrus"],
        "Bananas":                  g["banana"],
        "Plantains":                g["banana"],
        "Apples and products":      g["apple"],
        "Pineapples and products":  g["other_fruit"],
        "Grapefruit and products":  g["citrus"],
        "Grapes and products (excl wine)": g["berry_grape"],
        "Fruits, other":            g["other_fruit"],
        "Dates":                    g["other_fruit"],
        "Tomatoes and products":    g["tomato"],
        "Vegetables, other":        g["other_veg"],
        "Onions":                   g["onion"],

        # --- Meat ---
        "Bovine Meat":              g["bovine"],
        "Mutton & Goat Meat":       g["lamb"],
        "Pigmeat":                  g["pig"],
        "Poultry Meat":             g["poultry"],
        "Meat, Other":              g["poultry"],
        "Offals, Edible":           g["poultry"],

        # --- Other ---
        "Wine":                     g["wine"],
        "Beer":                     g["barley"],
        "Beverages, Fermented":     g["barley"],
        "Beverages, Alcoholic":     g["barley"],
        "Alcohol, Non-Food":        g["barley"],
        "Coffee and products":      g["coffee"],
        "Cocoa Beans and products": g["chocolate"],
        "Tea (including mate)":     tea,
        "Beans":                    g["other_pulse"],
        "Peas":                     g["pea"],
        "Pulses, Other and products": g["other_pulse"],
        "Pepper":                   tea,
        "Pimento":                  tea,
        "Spices, Other":            tea,
        "Cloves":                   tea,
        "Nuts and products":        g["nut"],
        "Infant food":              infant,

        # --- Sweets ---
        "Sugar (Raw Equivalent)":   g["sugar_raw"],
        "Sweeteners, Other":        g["sugar_raw"],
        "Honey":                    honey,
        "Sugar non-centrifugal":    g["cane_sugar"],
        "Sugar cane":               g["cane_sugar"],
        "Sugar beet":               g["beet_sugar"],
    }

# ============================================================
# Global fallback: production-weighted group averages from P&N
# Used when a country has no leaf-item data for a food group
# ============================================================

def compute_global_group_averages(scenario="mean", dairy_raw_milk_basis=True):
    """Compute production-weighted P&N average per food group for a scenario.

    ``dairy_raw_milk_basis`` defaults to True (fix #2, canonical): the Dairy
    fallback uses raw milk only (whole-milk-equivalent basis) rather than a
    milk+cheese production blend. Set False to reproduce the legacy blend.
    """
    g = GHG_SCENARIOS[scenario]
    dairy_products = (
        [(_PROD_MILK, g["milk"])]
        if dairy_raw_milk_basis
        else [(470267, g["milk"]), (21191, g["cheese"])]
    )
    group_products = {
        "Cereals": [
            (482152, g["wheat"]), (194554, g["maize"]),
            (206523, g["barley"]), (397780, g["rice"]),
            (4463, g["oat"]), (173814, g["cassava"]),
            (332343, g["potato"]),
        ],
        "Dairy": dairy_products,
        "Eggs": [(63489, g["eggs"])],
        "Fats and oils": [
            (11827, g["groundnut"]), (15296, g["nut"]),
            (11853, g["tofu"]), (24148, g["soybean_oil"]),
            (16691, g["palm_oil"]), (9554, g["sunflower_oil"]),
            (10311, g["rapeseed_oil"]), (2997, g["olive_oil"]),
        ],
        "Fish": [(45223, g["fish"]), (10633, g["shrimp"])],
        "Fruit and vegetables": [
            (148957, g["tomato"]), (77045, 0.51 if scenario == "mean" else (0.23 if scenario == "p10" else 0.97)),
            (77927, g["onion"]), (35154, g["root_veg"]),
            (654375, g["other_veg"]), (127923, g["citrus"]),
            (128971, g["banana"]), (75781, g["apple"]),
            (67079, g["berry_grape"]), (210650, g["other_fruit"]),
        ],
        "Meat": [
            (_PROD_BEEF_HERD, g["beef_herd"]), (_PROD_DAIRY_HERD, g["dairy_herd"]),
            (14195, g["lamb"]), (112892, g["pig"]),
            (96439, g["poultry"]),
        ],
        "Other": [
            (7778, g["coffee"]), (4416, g["chocolate"]),
            (26013, g["wine"]), (42765, g["other_pulse"]),
            (6026, g["pea"]),
        ],
        "Sweets, confectionery, and sweetened beverages": [
            (_PROD_CANE, g["cane_sugar"]), (_PROD_BEET, g["beet_sugar"]),
            (4416, g["chocolate"]),
        ],
    }
    averages = {}
    for group, products in group_products.items():
        total_prod = sum(p[0] for p in products)
        weighted = sum(p[0] * p[1] for p in products)
        averages[group] = weighted / total_prod if total_prod > 0 else 1.0
    return averages


# ============================================================
# git-LFS guard
# ============================================================

def _assert_not_lfs_pointer(path):
    """Raise a clear error if ``path`` is an unresolved git-LFS pointer stub.

    The tracked carbon-intensity CSVs are stored via git LFS. On a fresh clone
    where LFS was never initialized they materialize as ~130-byte pointer files
    beginning ``version https://git-lfs.github.com/spec/v1`` instead of CSV
    data — which pandas would otherwise parse into a garbage one-column frame
    and fail later with an obscure KeyError on ['ISO','Country','Region'].
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return  # missing file: let the normal reader raise its own error
    if first.startswith("version https://git-lfs.github.com/spec/v1"):
        raise RuntimeError(
            f"{path!r} is an unresolved git-LFS pointer, not CSV data. "
            f"The carbon-intensity files are tracked via git LFS — run "
            f"`git lfs pull` (or `git lfs install` then re-checkout the branch) "
            f"to download their real contents."
        )


# ============================================================
# MAIN: Build country-specific carbon intensity
# ============================================================

def build_ci(scenario="mean", dairy_raw_milk_basis=True, out_path=None):
    """Build country-specific carbon intensity for a given scenario.

    Returns the result DataFrame and also writes to CSV. ``dairy_raw_milk_basis``
    defaults to True (fix #2, now canonical): the Dairy group uses the raw-milk
    CI. A default run therefore writes the canonical files
    (``carbon_intensity.csv`` / ``_p10`` / ``_p90``) and reproduces them
    bit-for-bit. Set it False only to reproduce the legacy milk+cheese blend.
    ``out_path`` overrides the output filename entirely (e.g. to write
    ``*_cireg`` comparison files without clobbering the canonical baselines).
    """
    faostat_ghg = build_faostat_ghg_map(scenario, dairy_raw_milk_basis)

    mapping = pd.read_csv("Food data/FBS_Group_Mapping.csv")
    norm = pd.read_csv(
        "Food data/FoodBalanceSheets_E_All_Data_(Normalized)/"
        "FoodBalanceSheets_E_All_Data_(Normalized).csv"
    )
    iso_map = pd.read_csv("Food data/faostat_country_mapping.csv")
    _assert_not_lfs_pointer("Food data/carbon_intensity.csv")
    old_ci = pd.read_csv("Food data/carbon_intensity.csv")

    global_avg = compute_global_group_averages(scenario, dairy_raw_milk_basis)
    food_groups = [
        "Cereals", "Dairy", "Eggs", "Fats and oils", "Fish",
        "Fruit and vegetables", "Meat", "Other",
        "Sweets, confectionery, and sweetened beverages",
    ]

    food = norm[(norm["Year"] == 2022) & (norm["Element"] == "Food")].copy()
    food = pd.merge(food, iso_map, on="Area", how="left")
    food = pd.merge(
        food,
        mapping.set_index("fbs_group")[["final_food_group"]],
        left_on="Item", right_index=True, how="left",
    )

    food["ghg_per_kg"] = food["Item"].map(faostat_ghg)
    food["is_aggregate"] = food["Item"].isin(AGGREGATE_ITEMS)

    leaves = food[(~food["is_aggregate"]) & (food["Value"] > 0)].copy()
    leaves["weighted_ghg"] = leaves["Value"] * leaves["ghg_per_kg"]

    grouped = leaves.groupby(["ISO", "final_food_group"]).agg(
        total_consumption=("Value", "sum"),
        total_weighted_ghg=("weighted_ghg", "sum"),
    ).reset_index()
    grouped["ci"] = grouped["total_weighted_ghg"] / grouped["total_consumption"]

    ci_wide = grouped.pivot(
        index="ISO", columns="final_food_group", values="ci"
    ).reindex(columns=food_groups)

    scope = old_ci[["ISO", "Country", "Region"]].copy()
    result = pd.merge(scope, ci_wide, on="ISO", how="left")

    for fg in food_groups:
        result[fg] = result[fg].fillna(global_avg.get(fg, 1.0))

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

    for fg in food_groups:
        result[fg] = result[fg].round(6)

    # Determine output filename. Raw-milk dairy basis (fix #2) is canonical, so
    # a default run writes the canonical filenames; pass out_path explicitly to
    # write comparison variants without clobbering them.
    if out_path is None:
        if scenario == "mean":
            out_path = "Food data/carbon_intensity.csv"
        else:
            out_path = f"Food data/carbon_intensity_{scenario}.csv"

    result.to_csv(out_path, index=False)

    # Print summary
    label = {"mean": "Mean (central)", "p10": "10th Percentile (low)", "p90": "90th Percentile (high)"}
    print(f"\n=== {label[scenario]} Carbon Intensity ===\n")
    print(f"Output: {out_path}")
    print(f"Countries: {len(result)}")
    print(f"Countries with FAOSTAT data: {len(has_data & set(scope['ISO']))}\n")

    for fg in food_groups:
        vals = result[fg]
        print(f"  {fg:50s} min={vals.min():7.2f}  mean={vals.mean():7.2f}  max={vals.max():7.2f}")

    print("\n  Spot checks (USA):")
    row = result[result["ISO"] == "USA"]
    if len(row) > 0:
        row = row.iloc[0]
        print(f"    Cereals={row['Cereals']:.2f}  Dairy={row['Dairy']:.2f}  "
              f"Meat={row['Meat']:.2f}  Fish={row['Fish']:.2f}")

    unmapped = leaves[leaves["ghg_per_kg"].isna()]["Item"].unique()
    if len(unmapped) > 0:
        print(f"\n  WARNING: {len(unmapped)} items without GHG values")

    return result


def main():
    parser = argparse.ArgumentParser(description="Build carbon intensity CSVs")
    parser.add_argument(
        "--scenario", choices=["mean", "p10", "p90", "all"],
        default="all",
        help="Which GHG scenario to build (default: all)"
    )
    args = parser.parse_args()

    if args.scenario == "all":
        for s in ["mean", "p10", "p90"]:
            build_ci(s)
        print("\n" + "=" * 60)
        print("All three scenario files written to Food data/")
        print("  carbon_intensity.csv      (mean — central estimate)")
        print("  carbon_intensity_p10.csv  (10th percentile — low bound)")
        print("  carbon_intensity_p90.csv  (90th percentile — high bound)")
    else:
        build_ci(args.scenario)


if __name__ == "__main__":
    main()
