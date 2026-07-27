"""
Shared data-loading and equilibrium-solving pipeline.

A single ``compute_food_savings()`` runs the Price Rebound equilibrium model.
The optional ``diet_scenario`` argument redistributes the country-level demand
shock across food groups (calorie-preserving); with no diet scenario the shock
is uniform across groups, which is the baseline specification.

All file paths are resolved relative to the project root
(one level above this package).
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import pyreadr
from scipy.optimize import root_scalar

ROOT = Path(__file__).resolve().parent.parent

# Single source of truth for the FAOSTAT parent-level aggregate items that
# double-count their sub-items. build_carbon_intensity.py excludes these from
# its carbon-intensity weighting; the food-quantity step below applies the
# identical exclusion.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from build_carbon_intensity import AGGREGATE_ITEMS

from diet_sensitivity.scenarios import SCENARIOS


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


# ── Diet-scenario calibration ─────────────────────────────────────────
#
# Only used when a ``diet_scenario`` is requested. The country-level demand
# shock is redistributed across food groups by scenario multipliers, rescaled
# so the calorie-weighted average multiplier is exactly 1 — i.e. the total
# calorie reduction is preserved for every country x scenario, and only its
# composition changes.


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


# ── Full pipeline ─────────────────────────────────────────────────────


def compute_food_savings(
    *,
    diet_scenario: Optional[str] = None,
    ci_file: str = "carbon_intensity.csv",
    child_energy_file: str = "child_energy_by_country.xlsx",
):
    """Run the Price Rebound equilibrium model and return per-country
    annual food-emission savings plus a detailed result DataFrame.

    All arguments are keyword-only by design. This function consolidates two
    former pipelines whose first positional parameters differed (``ci_file``
    vs. ``diet_scenario``), so a positional call could bind a carbon-intensity
    filename to the diet scenario and quietly compute the wrong scenario.
    Keyword-only makes any such call a ``TypeError`` at the call site.

    Parameters
    ----------
    diet_scenario : str, optional
        Key from ``diet_sensitivity.scenarios.SCENARIOS``. When None (default)
        or ``"baseline_uniform"``, the country-level demand shock is applied
        uniformly across all food groups — the baseline specification. Any
        other scenario redistributes the same total calorie reduction across
        food groups using that scenario's multipliers.

        When None, ``food_savings``/``result_df`` carry no ``diet_scenario``
        column; when a scenario is named explicitly (including
        ``"baseline_uniform"``) the column is added for downstream labelling.
    ci_file : str
        Carbon-intensity CSV inside ``Food data/``. Use
        ``carbon_intensity_p10.csv`` or ``carbon_intensity_p90.csv``
        for sensitivity scenarios. An absolute path is used as-is, which lets
        callers pass a derived CI file generated outside ``Food data/``.
    child_energy_file : str
        Excel file inside ``Food data/`` with the per-country child (0-17)
        energy pool (columns ``ISO3``, ``total_annual_child_kcal``), used to put
        the demand-reduction fraction on an all-ages basis.

    Returns
    -------
    food_savings : DataFrame
        Columns: ISO, Country, scenario, annual_food_savings_t
        (plus diet_scenario when ``diet_scenario`` was given).
    result_df : DataFrame
        Row-level detail (country × food-group × scenario) with
        carbon_savings_t and all intermediate columns.
    """
    if diet_scenario is not None and diet_scenario not in SCENARIOS:
        raise ValueError(
            f"Unknown diet_scenario {diet_scenario!r}.  "
            f"Choose from: {list(SCENARIOS)}"
        )
    multipliers = SCENARIOS[diet_scenario] if diet_scenario is not None else {}

    # ── Simulation results (from R) ────────────────────────────────────
    sim_result = list(
        pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values()
    )[0]
    sim_result["weighted_eer"] = sim_result["weighting"] * sim_result["eer"]
    sim_result["weighted_treatment_eer"] = (
        sim_result["weighting"] * sim_result["treatment_eer"]
    )
    countries_in_scope = sim_result["ISO"].unique()

    # ── Inputs ────────────────────────────────────────────────────────
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

    # ── FAOSTAT food quantities ───────────────────────────────────────
    food_norm = pd.merge(norm, iso_mapping, on="Area", how="left")
    food_norm = food_norm.loc[
        (food_norm["Year"] == 2022)
        & (food_norm["Element"] == "Food")
        & (food_norm["ISO"].isin(countries_in_scope))
    ]
    # Drop parent-level aggregate items before grouping so their tonnage is not
    # summed on top of their own components. The FAOSTAT Food Balance Sheets
    # carry both parents (e.g. "Meat", "Cereals - Excluding Beer") and their
    # component items; summing both double-counts every aggregated group.
    # build_carbon_intensity.py applies the identical exclusion when weighting
    # carbon intensities, so AGGREGATE_ITEMS is shared between the two steps.
    food_norm = food_norm[~food_norm["Item"].isin(AGGREGATE_ITEMS)]
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

    # ── Price index ───────────────────────────────────────────────────
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

    # ── Elasticities ──────────────────────────────────────────────────
    elasticity_supply = elasticity_supply_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="elasticity_supply",
    )

    # ── Carbon intensity ──────────────────────────────────────────────
    carbon_intensity = carbon_intensity_raw.melt(
        id_vars=["ISO", "Country", "Region"],
        var_name="final_food_group", value_name="carbon_intensity_t",
    )
    carbon_intensity["carbon_intensity_t"] *= 1000

    # ── Country-level demand shock (uniform, from EER) ─────────────────
    sim_result_perc = sim_result.groupby(["ISO", "scenario"]).sum(numeric_only=True)
    sim_result_perc = sim_result_perc[
        ["weighted_eer", "weighted_treatment_eer"]
    ].copy()

    # All-ages denominator. The summed weighted_(treatment_)eer are the national
    # 18+ DAILY energy pools (eer = Mifflin BMR/day x PAL; weighting expands the
    # sim to national 18+ headcounts). Children (0-17) are untreated but still
    # consume food, so their energy requirement belongs UNCHANGED in both the
    # baseline and treatment pools, putting the reduction fraction on the
    # all-ages basis that matches the all-ages FAOSTAT supply the shock is
    # applied to. Normalising on adults alone would implicitly assume adults are
    # 100% of national food consumption and overstate the reduction. The child
    # file carries a national ANNUAL kcal total, so /365 puts it on the adult
    # daily basis.
    #
    # child_energy_file is built by compute_child_energy.R from UN WPP 2024
    # single-age populations x FAO/WHO/UNU (2004) moderate-activity energy
    # requirements for ages 0-17. See the README for the input/output map.
    #
    # NOTE: the FAO/WHO/UNU tables already have activity level embedded in the
    # kcal/day figure, so NO PAL multiplier is applied to the child pool -- the
    # R script uses pop x kcal_day x 365 directly. This differs from the adult
    # side above, which is Mifflin BMR x PAL. Do not apply PAL to children a
    # second time.
    child = pd.read_excel(ROOT / "Food data" / child_energy_file)
    child_pool_daily = (
        child.set_index("ISO3")["total_annual_child_kcal"] / 365.0
    ).dropna()
    cpd = sim_result_perc.index.get_level_values("ISO").map(child_pool_daily)
    sim_result_perc["child_pool_daily"] = np.asarray(cpd, dtype=float)
    sim_result_perc["expected_demand_reduction_percent"] = (
        (sim_result_perc["weighted_treatment_eer"]
         + sim_result_perc["child_pool_daily"])
        / (sim_result_perc["weighted_eer"]
           + sim_result_perc["child_pool_daily"])
    ) - 1

    # ── Merge into one DataFrame (food groups × scenarios per country) ─
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

    # Hard guard: every country that carries a FAOSTAT food quantity (i.e.
    # actually receives a demand shock) must have supplied a child pool. A
    # silently missing child pool would leave that country on an adults-only
    # fraction -- invisible in aggregate output -- so raise rather than let it
    # through (never fill zero).
    shock = merged[merged["initial_eql_quantity"].notna()]
    no_child = sorted(set(shock["ISO"].unique()) - set(child_pool_daily.index))
    nan_delta = sorted(
        shock.loc[
            shock["expected_demand_reduction_percent"].isna(), "ISO"
        ].unique()
    )
    offenders = sorted(set(no_child) | set(nan_delta))
    if offenders:
        raise ValueError(
            "All-ages denominator: no child energy pool for shocked "
            f"country(ies) {offenders}. Refusing to proceed -- these would "
            "fall back to an inflated adults-only demand shock. Add rows to "
            f"'Food data/{child_energy_file}'."
        )

    # ── Apply diet-scenario calibrated shocks ─────────────────────────
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

    # ── Solve new equilibrium ─────────────────────────────────────────
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
    if diet_scenario is not None:
        result_df["diet_scenario"] = diet_scenario

    food_savings = (
        result_df.groupby(["ISO", "Country", "scenario"])["carbon_savings_t"]
        .sum()
        .abs()
        .reset_index()
        .rename(columns={"carbon_savings_t": "annual_food_savings_t"})
    )
    if diet_scenario is not None:
        food_savings["diet_scenario"] = diet_scenario

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
