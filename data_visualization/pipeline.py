"""
Shared data-loading and equilibrium-solving pipeline.

All file paths are resolved relative to the project root
(one level above this package).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr
from scipy.optimize import root_scalar

ROOT = Path(__file__).resolve().parent.parent


# ── Equilibrium solver ────────────────────────────────────────────────


def _equilibrium_gap(P, Cs, Cd, Es, Ed, demand_shock_pct):
    Qs = Cs * (P ** Es)
    Qd = Cd * (P ** Ed) * (1 + demand_shock_pct)
    return Qs - Qd


def _compute_equilibrium(row):
    try:
        result = root_scalar(
            _equilibrium_gap,
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


# ── Full pipeline ─────────────────────────────────────────────────────


def compute_food_savings(ci_file: str = "carbon_intensity.csv"):
    """Run the Price Rebound equilibrium model and return per-country
    annual food-emission savings plus a detailed result DataFrame.

    Parameters
    ----------
    ci_file : str
        Carbon-intensity CSV inside ``Food data/``.  Use
        ``carbon_intensity_p10.csv`` or ``carbon_intensity_p90.csv``
        for sensitivity scenarios.

    Returns
    -------
    food_savings : DataFrame
        Columns: ISO, Country, scenario, annual_food_savings_t
    result_df : DataFrame
        Row-level detail (country × food-group × scenario) with
        carbon_savings_t and all intermediate columns.
    """
    sim_result = list(
        pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values()
    )[0]
    sim_result["weighted_eer"] = sim_result["weighting"] * sim_result["eer"]
    sim_result["weighted_treatment_eer"] = (
        sim_result["weighting"] * sim_result["treatment_eer"]
    )

    norm = pd.read_csv(
        ROOT / "Food data" / "FoodBalanceSheets_E_All_Data_(Normalized)"
        / "FoodBalanceSheets_E_All_Data_(Normalized).csv"
    )
    mapping = pd.read_csv(ROOT / "Food data" / "FBS_Group_Mapping.csv")
    iso_mapping = pd.read_csv(ROOT / "Food data" / "faostat_country_mapping.csv")
    price_index = pd.read_csv(
        ROOT / "Food data" / "ConsumerPriceIndices_E_All_Data_(Normalized)"
        / "ConsumerPriceIndices_E_All_Data_(Normalized).csv"
    )
    elasticity_supply_raw = pd.read_csv(ROOT / "Food data" / "elasticity_supply.csv")
    elasticity_demand = pd.read_csv(ROOT / "Food data" / "elasticity_demand.csv")
    carbon_intensity_raw = pd.read_csv(ROOT / "Food data" / ci_file)

    countries_in_scope = sim_result["ISO"].unique()

    # FAOSTAT food quantities
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

    # Price index
    price_clean = pd.merge(price_index, iso_mapping, on="Area", how="left")
    price_clean = price_clean.loc[
        (price_clean["Months"] == "December")
        & (price_clean["Year"] == 2022)
        & (price_clean["Item"] == "Consumer Prices, Food Indices (2015 = 100)")
    ]
    price_clean = (
        price_clean[price_clean["ISO"].isin(countries_in_scope)][
            ["Area", "ISO", "Value"]
        ]
        .rename(columns={"Area": "Country", "Value": "price"})
        .reset_index(drop=True)
    )

    # Elasticities
    elasticity_supply = elasticity_supply_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="elasticity_supply",
    )

    # Carbon intensity
    carbon_intensity = carbon_intensity_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="carbon_intensity_t",
    )
    carbon_intensity["carbon_intensity_t"] *= 1000

    # Merge everything
    merged = pd.merge(
        food_grouped, price_clean[["ISO", "price"]], on="ISO", how="outer"
    )
    merged = pd.merge(
        merged, elasticity_demand.set_index("food_groups"),
        left_on="final_food_group", right_index=True, how="left",
    )
    merged = pd.merge(
        merged,
        elasticity_supply[["ISO", "final_food_group", "elasticity_supply"]],
        on=["ISO", "final_food_group"], how="left",
    )

    merged["Cs"] = merged["initial_eql_quantity"] / (
        merged["price"] ** merged["elasticity_supply"]
    )
    merged["Cd"] = merged["initial_eql_quantity"] / (
        merged["price"] ** merged["elasticity_demand"]
    )

    sim_result_perc = sim_result.groupby(["ISO", "scenario"]).sum(numeric_only=True)
    sim_result_perc = sim_result_perc[
        ["weighted_eer", "weighted_treatment_eer"]
    ].copy()
    sim_result_perc["expected_demand_reduction_percent"] = (
        sim_result_perc["weighted_treatment_eer"]
        / sim_result_perc["weighted_eer"]
    ) - 1

    merged = pd.merge(
        merged,
        sim_result_perc[["expected_demand_reduction_percent"]].reset_index(),
        on="ISO", how="left",
    )

    # Solve new equilibrium
    result_df = merged.copy()
    result_df["expected_demand_reduction"] = (
        result_df["initial_eql_quantity"]
        * result_df["expected_demand_reduction_percent"]
    )
    result_df[["P_eq_new", "Q_eql_new"]] = result_df.apply(
        _compute_equilibrium, axis=1
    )
    result_df["actual_reduction"] = (
        result_df["Q_eql_new"] - result_df["initial_eql_quantity"]
    )
    result_df["rebound_effect"] = (
        result_df["actual_reduction"] - result_df["expected_demand_reduction"]
    )
    result_df["rebound_effect_percent"] = (
        -1 * result_df["rebound_effect"] / result_df["expected_demand_reduction"]
    )

    result_df = pd.merge(
        result_df,
        carbon_intensity[["ISO", "final_food_group", "carbon_intensity_t"]],
        how="left", on=["ISO", "final_food_group"],
    )
    result_df["carbon_savings_t"] = (
        result_df["actual_reduction"] * result_df["carbon_intensity_t"]
    )

    food_savings = (
        result_df.groupby(["ISO", "Country", "scenario"])["carbon_savings_t"]
        .sum()
        .abs()
        .reset_index()
        .rename(columns={"carbon_savings_t": "annual_food_savings_t"})
    )

    return food_savings, result_df


def load_mortality_emissions():
    """Load year-by-year survivor emissions from the Mortality Model CSV.

    Expects ``mortality model total emissions.csv`` generated with
    ``population_weighted=True``.
    """
    return pd.read_csv(ROOT / "mortality model total emissions.csv")


def output_path(filename: str) -> Path:
    """Return the standard output path for generated results.

    Figures are written to ``figures/``. Tabular/data outputs are written to
    ``data_result/``. This keeps the legacy ``test/`` directory from collecting
    new analysis artifacts.
    """
    suffix = Path(filename).suffix.lower()
    figure_suffixes = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
    p = ROOT / ("figures" if suffix in figure_suffixes else "data_result")
    p.mkdir(exist_ok=True)
    return p / filename
