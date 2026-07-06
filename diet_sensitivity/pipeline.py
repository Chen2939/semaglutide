"""
Diet-composition-aware price-rebound pipeline.

Extends the baseline ``data_visualization.pipeline.compute_food_savings()``
logic with per-food-group demand-shock calibration derived from FAOSTAT
``Food supply (kcal/capita/day)`` data.

The key idea:
  1.  Compute a country-level calorie-share for each of the 9 final_food_groups.
  2.  Apply scenario multipliers to the uniform EER-based demand shock.
  3.  Solve for a "neutral" multiplier for unspecified groups so the
      calorie-weighted average multiplier equals 1  →  total calorie
      reduction is preserved for every country × scenario.
  4.  Feed the per-group shocks into the standard Hegwood et al. constant-
      elasticity equilibrium solver (unchanged from existing pipeline).

All data loading uses the same files as the existing pipeline; no new data
files are required.
"""

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyreadr

# Re-use the pure-math equilibrium utilities and project root from the
# existing package — these are stable, unit-tested, and should not be
# duplicated.
from data_visualization.pipeline import (
    ROOT,
    _compute_equilibrium,
)

from .scenarios import SCENARIOS


# ── FAOSTAT kcal helpers ──────────────────────────────────────────────────────

def load_kcal_shares(countries_in_scope) -> pd.DataFrame:
    """
    Load 2022 FAOSTAT kcal supply and compute calorie shares per
    country × ``final_food_group``.

    Returns
    -------
    DataFrame with columns: ISO, final_food_group, kcal_share
        Shares sum to 1.0 per ISO.  Countries with no kcal data are absent.
    """
    norm = pd.read_csv(
        ROOT / "Food data" / "FoodBalanceSheets_E_All_Data_(Normalized)"
        / "FoodBalanceSheets_E_All_Data_(Normalized).csv"
    )
    mapping = pd.read_csv(ROOT / "Food data" / "FBS_Group_Mapping.csv")
    iso_mapping = pd.read_csv(ROOT / "Food data" / "faostat_country_mapping.csv")

    kcal = pd.merge(norm, iso_mapping, on="Area", how="left")
    kcal = kcal.loc[
        (kcal["Year"] == 2022)
        & (kcal["Element"] == "Food supply (kcal/capita/day)")
        & (kcal["ISO"].isin(countries_in_scope))
    ]
    kcal = pd.merge(
        kcal,
        mapping.set_index("fbs_group")[["final_food_group"]],
        left_on="Item", right_index=True, how="left",
    )
    kcal = kcal.dropna(subset=["final_food_group"])

    kcal_grouped = (
        kcal.groupby(["ISO", "final_food_group"])
        .sum(numeric_only=True)[["Value"]]
        .reset_index()
        .rename(columns={"Value": "kcal"})
    )
    # Remove rows with zero or missing kcal (can't compute valid share)
    kcal_grouped = kcal_grouped[kcal_grouped["kcal"] > 0]

    country_total = (
        kcal_grouped.groupby("ISO")["kcal"]
        .sum()
        .reset_index()
        .rename(columns={"kcal": "total_kcal"})
    )
    shares = pd.merge(kcal_grouped, country_total, on="ISO")
    shares["kcal_share"] = shares["kcal"] / shares["total_kcal"]

    return shares[["ISO", "final_food_group", "kcal_share"]].copy()


def calibrate_group_multipliers(
    country_kcal_shares: pd.DataFrame,
    multipliers: Dict[str, float],
) -> tuple[Dict[str, float], float]:
    """Compute food-group multipliers that preserve total calorie reduction.

    Algorithm
    ---------
    For the remaining ("neutral") groups, ``m_neutral`` is solved so that the
    calorie-weighted sum of all multipliers equals 1, i.e.:

            Σ_g  w_g × m_g  =  1

    ``m_neutral`` is not clamped.  In a few high-cereal countries it can be
    negative, meaning non-targeted groups increase slightly to preserve the
    total calorie reduction while honoring the specified diet-preference shift.
    """
    shares = country_kcal_shares.set_index("final_food_group")["kcal_share"]
    all_groups: List[str] = shares.index.tolist()

    # Groups with an explicit multiplier that are also present in the kcal data
    specified = {g: multipliers[g] for g in multipliers if g in all_groups}
    neutral_groups = [g for g in all_groups if g not in specified]

    # Calorie-weighted sum of specified multipliers
    w_specified = sum(shares[g] * m for g, m in specified.items())
    w_neutral_total = sum(shares[g] for g in neutral_groups)

    if w_neutral_total > 1e-9:
        m_neutral = (1.0 - w_specified) / w_neutral_total
    else:
        # All calorie share is in specified groups — use 1.0 as fallback
        m_neutral = 1.0

    result: Dict[str, float] = {}
    for g in all_groups:
        result[g] = specified.get(g, m_neutral)

    weighted_avg = sum(shares[g] * result[g] for g in all_groups)
    if not np.isclose(weighted_avg, 1.0, atol=1e-9):
        raise ValueError(
            "Diet calibration failed to preserve calories: "
            f"weighted multiplier={weighted_avg:.12f}"
        )

    return result, m_neutral


def calibrate_group_shocks(
    base_pct: float,
    country_kcal_shares: pd.DataFrame,
    multipliers: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute per-food-group demand reduction percentages that preserve the
    total calorie reduction while applying the scenario multipliers.
    """
    group_multipliers, _ = calibrate_group_multipliers(
        country_kcal_shares,
        multipliers,
    )
    result: Dict[str, float] = {}
    for g, m in group_multipliers.items():
        result[g] = base_pct * m

    return result


def build_diet_shocks(
    sim_result_perc: pd.DataFrame,
    kcal_shares: pd.DataFrame,
    multipliers: Dict[str, float],
) -> pd.DataFrame:
    """
    Build a long-format DataFrame of per-(ISO, scenario, food_group) demand
    reduction percentages calibrated to the diet scenario.

    Parameters
    ----------
    sim_result_perc : DataFrame
        Index: (ISO, scenario).  Column: expected_demand_reduction_percent.
    kcal_shares : DataFrame
        Output of load_kcal_shares().
    multipliers : dict
        Scenario multipliers.

    Returns
    -------
    DataFrame with columns: ISO, scenario, final_food_group, diet_shock_pct
    """
    rows = []
    diagnostics = []
    for (iso, scenario), row in sim_result_perc.iterrows():
        base_pct = row["expected_demand_reduction_percent"]
        country_kcal = kcal_shares[kcal_shares["ISO"] == iso]

        if country_kcal.empty:
            # No kcal data → no rows added; fillna in the caller applies
            # the uniform shock as fallback
            continue

        group_multipliers, m_neutral = calibrate_group_multipliers(
            country_kcal,
            multipliers,
        )
        if m_neutral < 0:
            diagnostics.append({
                "ISO": iso,
                "scenario": scenario,
                "neutral_multiplier": m_neutral,
                "base_pct": base_pct,
                "implied_neutral_shock_pct": base_pct * m_neutral,
            })
        group_shocks = {fg: base_pct * m for fg, m in group_multipliers.items()}
        for fg, shock_pct in group_shocks.items():
            rows.append({
                "ISO": iso,
                "scenario": scenario,
                "final_food_group": fg,
                "diet_shock_pct": shock_pct,
            })

    if diagnostics:
        diag = pd.DataFrame(diagnostics)
        print(
            "    Diet calibration note: "
            f"{len(diag)} country-scenarios require small neutral-group increases "
            "to preserve total calories. "
            f"Max implied increase: {diag['implied_neutral_shock_pct'].max() * 100:.3f}%"
        )

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ISO", "scenario", "final_food_group", "diet_shock_pct"]
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def compute_food_savings_diet(
    diet_scenario: str = "baseline_uniform",
    ci_file: str = "carbon_intensity.csv",
):
    """
    Run the Price Rebound equilibrium model with a diet-composition scenario.

    When ``diet_scenario == "baseline_uniform"`` the output is numerically
    identical to ``data_visualization.pipeline.compute_food_savings()``.

    Parameters
    ----------
    diet_scenario : str
        Key from ``diet_sensitivity.scenarios.SCENARIOS``.
    ci_file : str
        Carbon-intensity CSV inside ``Food data/``.

    Returns
    -------
    food_savings : DataFrame
        Columns: ISO, Country, scenario, annual_food_savings_t, diet_scenario
    result_df : DataFrame
        Row-level detail (country × food-group × scenario) with carbon_savings_t
        and all intermediate columns.  Also includes diet_scenario column.
    """
    if diet_scenario not in SCENARIOS:
        raise ValueError(
            f"Unknown diet_scenario {diet_scenario!r}.  "
            f"Choose from: {list(SCENARIOS)}"
        )
    multipliers = SCENARIOS[diet_scenario]

    # ── Simulation results (from R) ───────────────────────────────────────
    sim_result = list(
        pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values()
    )[0]
    sim_result["weighted_eer"] = sim_result["weighting"] * sim_result["eer"]
    sim_result["weighted_treatment_eer"] = (
        sim_result["weighting"] * sim_result["treatment_eer"]
    )
    countries_in_scope = sim_result["ISO"].unique()

    # ── FAOSTAT food quantities (kg) ──────────────────────────────────────
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
    ci_path = Path(ci_file)
    if not ci_path.is_absolute():
        ci_path = ROOT / "Food data" / ci_file
    carbon_intensity_raw = pd.read_csv(ci_path)

    # ── FAOSTAT food quantities ────────────────────────────────────────────
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

    # ── Price index ────────────────────────────────────────────────────────
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

    # ── Elasticities ──────────────────────────────────────────────────────
    elasticity_supply = elasticity_supply_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="elasticity_supply",
    )

    # ── Carbon intensity ──────────────────────────────────────────────────
    carbon_intensity = carbon_intensity_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="carbon_intensity_t",
    )
    carbon_intensity["carbon_intensity_t"] *= 1000

    # ── Country-level demand shock (uniform, from EER) ────────────────────
    sim_result_perc = sim_result.groupby(["ISO", "scenario"]).sum(numeric_only=True)
    sim_result_perc = sim_result_perc[
        ["weighted_eer", "weighted_treatment_eer"]
    ].copy()
    sim_result_perc["expected_demand_reduction_percent"] = (
        sim_result_perc["weighted_treatment_eer"]
        / sim_result_perc["weighted_eer"]
    ) - 1

    # ── Merge into one DataFrame (food groups × scenarios per country) ────
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
    # Expand to (country × food group × scenario)
    merged = pd.merge(
        merged,
        sim_result_perc[["expected_demand_reduction_percent"]].reset_index(),
        on="ISO", how="left",
    )

    # ── Apply diet-scenario calibrated shocks ─────────────────────────────
    if multipliers:
        print(f"    Loading FAOSTAT kcal shares for calibration...")
        kcal_shares = load_kcal_shares(countries_in_scope)

        diet_shocks = build_diet_shocks(sim_result_perc, kcal_shares, multipliers)

        if not diet_shocks.empty:
            merged = pd.merge(
                merged,
                diet_shocks[["ISO", "scenario", "final_food_group", "diet_shock_pct"]],
                on=["ISO", "scenario", "final_food_group"],
                how="left",
            )
            # For countries/groups without kcal data, fall back to uniform shock
            merged["expected_demand_reduction_percent"] = (
                merged["diet_shock_pct"]
                .fillna(merged["expected_demand_reduction_percent"])
            )
            merged = merged.drop(columns=["diet_shock_pct"])

    # ── Solve new equilibrium ─────────────────────────────────────────────
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
    result_df["diet_scenario"] = diet_scenario

    food_savings = (
        result_df.groupby(["ISO", "Country", "scenario"])["carbon_savings_t"]
        .sum()
        .abs()
        .reset_index()
        .rename(columns={"carbon_savings_t": "annual_food_savings_t"})
    )
    food_savings["diet_scenario"] = diet_scenario

    return food_savings, result_df
