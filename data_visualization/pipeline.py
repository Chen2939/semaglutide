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
    """Solve for the post-shock price and quantity, or fail loudly.

    The price LEVEL cancels out of the quantity answer. With ``Cs = Q0/P0^Es`` and
    ``Cd = Q0/P0^Ed``, market clearing reduces to ``(P/P0)^(Es-Ed) = 1+delta``, so

        Q_new / Q0 = (1 + delta) ** (Es / (Es - Ed))

    -- a function of the shock and the two elasticities alone. That matters because
    the FAOSTAT food CPI is an index on each country's own base year: if the level
    entered, every result would depend on an arbitrary normalisation. It does not.
    ``P_eq_new`` is the one price-dependent output and nothing reads it.

    This used to be wrapped in a bare ``except Exception: pass`` returning NaN,
    which a groupby then turned into a silent 0.0 -- that is how three countries
    came to sit in the outputs with zero food savings and no warning. The two
    failure modes are now separated:

      * inputs already NaN -- no solve is possible and NaN is the honest answer.
        The caller names these rows; see the guard in ``compute_food_savings``.
      * a genuine solver failure on real inputs -- raises. Nothing in the current
        data takes this path (measured: 0 of 10,080 calls), so making it loud costs
        nothing today and stops the next occurrence being absorbed.

    The bracket is worth keeping in view. It is in price-LEVEL units even though
    the answer is scale-free, so a country whose CPI sits outside [1e-3, 1e3] fails
    to bracket. Seven countries in the FAOSTAT file are at or above 1e3 (Venezuela
    at 9.1e11, then ZWE, LBN, SDN, SSD, ARG, SUR). None is in the modelled set,
    whose 53 priced countries span 103.247-190.779 -- a factor of five inside the
    bracket -- so this is inert today. It is the reason it is inert, not a reason it
    always will be: a country set reaching high-inflation economies would now raise
    here rather than quietly drop them.
    """
    args = (
        row["Cs"], row["Cd"],
        row["elasticity_supply"], row["elasticity_demand"],
        row["expected_demand_reduction_percent"],
    )
    if any(pd.isna(a) for a in args):
        return pd.Series({"P_eq_new": np.nan, "Q_eql_new": np.nan})

    where = (
        f"{row.get('ISO')} / {row.get('final_food_group')} / {row.get('scenario')}"
    )
    try:
        result = root_scalar(
            _equilibrium_gap, args=args, method="brentq", bracket=[1e-3, 1e3]
        )
    except Exception as exc:
        raise RuntimeError(
            f"Equilibrium solve failed for {where}: {type(exc).__name__}: {exc}. "
            f"Inputs Cs={args[0]!r} Cd={args[1]!r} Es={args[2]!r} Ed={args[3]!r} "
            f"delta={args[4]!r}. If this is a bracketing failure, check the price "
            "index against bracket=[1e-3, 1e3] -- see this function's docstring."
        ) from exc
    if not result.converged:
        raise RuntimeError(
            f"Equilibrium solve did not converge for {where} with finite inputs: "
            f"{result.flag!r}. Inputs Cs={args[0]!r} Cd={args[1]!r} "
            f"Es={args[2]!r} Ed={args[3]!r} delta={args[4]!r}."
        )
    P_new = result.root
    Q_new = row["Cs"] * (P_new ** row["elasticity_supply"])
    return pd.Series({"P_eq_new": P_new, "Q_eql_new": Q_new})


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

    Parent-level aggregates are excluded, as in the tonnage step, so the
    shares are not distorted in favour of the groups that have a parent item.
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
    # Drop parent-level aggregate items before grouping, for the same reason the
    # tonnage step does: the Food Balance Sheets carry both parents and their
    # components, so summing both double-counts every group that has a parent.
    # Dairy and Eggs have no parent item and would be counted once while the
    # other seven groups were counted twice, understating their calorie shares
    # and leaving the calibrated multipliers no longer averaging to 1.
    kcal = kcal[~kcal["Item"].isin(AGGREGATE_ITEMS)]
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


# ── Survivor food factor (Poore & Nemecek basis) ──────────────────────
#
# Survivor emissions are charged an OECD demand-based per-capita factor whose
# food component is priced at national inventory rates, while the food-savings
# side of the same analysis prices food with Poore & Nemecek -- roughly double
# per kilo. This builds the P&N-basis food footprint of one treated survivor so
# the OECD food bundle can be swapped out for it downstream.
#
# Three things are easy to get wrong here and each produces a plausible number:
#
#  1. The energy denominator and numerator both use BASELINE ``eer``, never
#     ``treatment_eer``. The demand shock already carries the reduction; a
#     treated eer here would apply it a second time.
#  2. The energy pool is DAILY kcal and the footprint is ANNUAL tonnes, so the
#     quotient is already tonnes/year per kcal/day. There is no 365 anywhere.
#  3. The footprint is rebuilt from whichever carbon-intensity file the caller
#     passed, so it moves with the P10/P90 sensitivity scenarios instead of
#     being pinned to the mean.


def _survivor_food_factor(
    result_df: pd.DataFrame,
    sim_result: pd.DataFrame,
    sim_result_perc: pd.DataFrame,
) -> pd.DataFrame:
    """Per ISO × scenario P&N food footprint of one treated survivor.

    Parameters
    ----------
    result_df : DataFrame
        The row-level (country × food group × scenario) frame, already joined
        to ``carbon_intensity_t``.
    sim_result : DataFrame
        The raw simulation rows, carrying ``weighted_eer`` (= weighting × eer).
    sim_result_perc : DataFrame
        Indexed by (ISO, scenario), carrying ``weighted_eer`` and
        ``child_pool_daily``.

    Returns
    -------
    DataFrame with columns: ISO, scenario, pn_food_footprint,
        energy_pool_daily, mean_eer_treated, food_factor, survivor_food_t,
        pop_treated, pop_adult.
    """
    # National P&N food footprint: the same carbon intensities the savings side
    # uses, applied to BASELINE tonnage rather than the reduction.  min_count=1
    # keeps a country with no FAOSTAT tonnage as NaN instead of a silent zero.
    pn_food_footprint = (
        (result_df["initial_eql_quantity"] * result_df["carbon_intensity_t"])
        .groupby([result_df["ISO"], result_df["scenario"]])
        .sum(min_count=1)
        .rename("pn_food_footprint")
    )

    # All-ages daily energy pool -- the same adults + children denominator the
    # demand shock is normalised on, reused rather than rebuilt.
    energy_pool_daily = (
        sim_result_perc["weighted_eer"] + sim_result_perc["child_pool_daily"]
    ).rename("energy_pool_daily")

    treated = sim_result.loc[sim_result["adheres_to_treatment"]]
    treated_grouped = treated.groupby(["ISO", "scenario"])
    pop_treated = treated_grouped["weighting"].sum().rename("pop_treated")
    mean_eer_treated = (
        treated_grouped["weighted_eer"].sum() / pop_treated
    ).rename("mean_eer_treated")
    pop_adult = (
        sim_result.groupby(["ISO", "scenario"])["weighting"]
        .sum()
        .rename("pop_adult")
    )

    factor = pd.concat(
        [energy_pool_daily, mean_eer_treated, pop_treated, pop_adult], axis=1
    ).join(pn_food_footprint, how="left")

    # tonnes/year ÷ kcal/day → tonnes/year per kcal/day.  Not per-day; do not
    # rescale by 365.
    factor["food_factor"] = (
        factor["pn_food_footprint"] / factor["energy_pool_daily"]
    )
    factor["survivor_food_t"] = (
        factor["food_factor"] * factor["mean_eer_treated"]
    )

    return factor.reset_index()[
        [
            "ISO",
            "scenario",
            "pn_food_footprint",
            "energy_pool_daily",
            "mean_eer_treated",
            "food_factor",
            "survivor_food_t",
            "pop_treated",
            "pop_adult",
        ]
    ]


def _report_unsolved(food_savings: pd.DataFrame, result_df: pd.DataFrame) -> None:
    """Name every country whose food savings could not be computed, and why.

    This is the load-bearing half of ``min_count=1``. Turning a silent 0.0 into a
    silent NaN gains little on its own: the downstream ``> 0`` filters drop both,
    so the country vanishes from the counts either way. What was missing was
    anybody saying so. Three countries had been sitting in the outputs at exactly
    zero food savings for the life of the model without a line of output.

    Prints rather than raises. These are genuine, permanent input gaps -- a country
    with no FAOSTAT price index cannot be solved and never will be -- so raising
    would break every run over a known condition. The list is also attached to
    ``result_df.attrs["unsolved"]`` so a caller can act on it.
    """
    unsolved = food_savings[food_savings["annual_food_savings_t"].isna()]
    result_df.attrs["unsolved"] = sorted(unsolved["ISO"].unique())
    if unsolved.empty:
        return

    # Which input is missing, per country. Reported rather than guessed at: the
    # three current cases are all a missing price, but that is a fact about today's
    # data, not a property of the code.
    checks = {
        "price": "price",
        "FAOSTAT tonnage": "initial_eql_quantity",
        "carbon intensity": "carbon_intensity_t",
        "supply elasticity": "elasticity_supply",
        "demand elasticity": "elasticity_demand",
        "demand shock": "expected_demand_reduction_percent",
    }
    print(
        f"    NOTE: {unsolved['ISO'].nunique()} country(ies) have no computable "
        "food savings and are NaN, not zero:"
    )
    for iso in sorted(unsolved["ISO"].unique()):
        rows = result_df[result_df["ISO"] == iso]
        missing = [
            label for label, col in checks.items()
            if col in rows.columns and rows[col].isna().all()
        ]
        country = rows["Country"].dropna().iloc[0] if rows["Country"].notna().any() else "?"
        print(
            f"      {iso} ({country}): missing "
            f"{', '.join(missing) if missing else 'no single input on every row'}"
        )
    print(
        "    They are excluded from every ratio by the downstream '> 0' filters, "
        "which is correct -- but it is now stated rather than implied by a zero."
    )


# ── Full pipeline ─────────────────────────────────────────────────────


def compute_food_savings(
    *,
    diet_scenario: Optional[str] = None,
    ci_file: str = "carbon_intensity.csv",
    child_energy_file: str = "child_energy_by_country.xlsx",
    survival_weighted: bool = True,
    horizon: int = 10,
    survival_weight: Optional[pd.DataFrame] = None,
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
    survival_weighted : bool
        Scale the demand shock by ``pi(t)``, the difference-weighted mean
        treatment-world survival, so patients who die stop contributing a food
        saving. See ``data_visualization.survival_weighting``. ``False``
        reproduces the legacy single-solve behaviour, where every treated patient
        eats less forever.

        **``False`` IS A PRODUCTION DEPENDENCY. DO NOT DELETE IT AS DEAD TEST
        CODE.** It began as a test lever and is no longer one:
        ``generate_waterfall_1yr_figure`` passes ``survival_weighted=False`` to
        build Panel A of the emissions waterfall, a published figure, as its
        no-mortality counterfactual -- all three mortality channels off
        (food-side ``pi``, pharmaceutical-side ``pi_dose``, survivor emissions).
        Removing this argument does not break a test; it silently changes a
        figure in the manuscript from the unweighted basis to the weighted one,
        and the output stays plausible either way. That is exactly how the
        mismatch Panel A was rebuilt to remove went unnoticed in the first
        place. ``null_check_pi.py`` gate N2 pins the behaviour.
    horizon : int
        Years of the per-year series to solve, when ``survival_weighted``.
    survival_weight : DataFrame, optional
        Pre-built ``pi`` table, wide by year, indexed by (ISO, scenario), used
        instead of reading the committed artefact. The injection point for
        sensitivity runs and for the ``pi == 1`` null check.

    Returns
    -------
    food_savings : DataFrame
        Columns: ISO, Country, scenario, annual_food_savings_t, and
        annual_food_savings_t_Y1..Y{horizon} when ``survival_weighted``
        (plus diet_scenario when ``diet_scenario`` was given).

        ``annual_food_savings_t`` is the **year-1** saving. Under survival
        weighting the annual saving is no longer constant, so a single number has
        to mean a particular year; year 1 keeps every existing single-value
        consumer correct for the quantity it already reports, and moves it only
        by ``pi(1)``, which is about 0.5%. Anything cumulative must sum the
        series -- ``annual * 10`` is wrong once the series varies.
    result_df : DataFrame
        Row-level detail (country × food-group × scenario) with
        carbon_savings_t and all intermediate columns, on the **year-1** solve,
        plus ``actual_reduction_Y{t}`` and ``carbon_savings_t_Y{t}`` per year.
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

    # ── Survival weighting of the shock ───────────────────────────────
    #
    # The shock as built above carries no survival probability, i.e. it assumes
    # every treated patient is alive in every year. Patients who die despite the
    # drug are dead in both worlds and eat nothing in either, so their food saving
    # must stop being counted. pi(t) is the difference-weighted mean
    # treatment-world survival and the corrected shock is delta * pi(t).
    #
    # Only the NUMERATOR is weighted. The denominator of delta stays on the 2022
    # baseline energy pool, because that is the basis of the observed FAOSTAT
    # tonnage the shock is applied to.
    #
    # This does NOT touch _survivor_food_factor. That handles a different group of
    # people -- the additional survivors, who are alive only because of the drug
    # and eat a full diet nobody would otherwise have eaten. Both are real and
    # they do not overlap.
    result_df = merged.copy()
    base_shock = result_df["expected_demand_reduction_percent"].copy()

    years = list(range(1, horizon + 1)) if survival_weighted else [1]
    if survival_weighted:
        if survival_weight is None:
            from .survival_weighting import load_food_shock_survival_weight

            survival_weight = load_food_shock_survival_weight(horizon=horizon)
        # Same shape of guard as the child-energy pool above: a country that
        # receives a shock but has no pi would silently keep the unweighted shock,
        # which is invisible in aggregate output.
        shocked = set(
            result_df.loc[result_df["initial_eql_quantity"].notna(), "ISO"].unique()
        )
        have = set(survival_weight.index.get_level_values("ISO"))
        offenders = sorted(shocked - have)
        if offenders:
            raise ValueError(
                f"Survival weighting: no pi for shocked country(ies) {offenders}. "
                "Refusing to proceed -- these would fall back to an unweighted "
                "shock in which nobody ever dies. Rebuild with: "
                "python -m data_visualization.survival_weighting"
            )
        idx = pd.MultiIndex.from_arrays(
            [result_df["ISO"], result_df["scenario"]], names=["ISO", "scenario"]
        )
        pi_by_year = {
            y: survival_weight[y].reindex(idx).to_numpy(dtype=float) for y in years
        }
    else:
        pi_by_year = {1: np.ones(len(result_df), dtype=float)}

    result_df = pd.merge(
        result_df,
        carbon_intensity[["ISO", "final_food_group", "carbon_intensity_t"]],
        how="left", on=["ISO", "final_food_group"],
    )

    # The equilibrium is re-solved per year rather than the year-1 answer being
    # scaled by pi(t). The solve is near-linear in delta, so scaling is close --
    # measured at 0.06% on the global aggregate and up to 0.14% on a single row at
    # pi = 0.86 -- but that is the same order as the smallest real correction this
    # model has recorded, and the exact route costs about 0.4 s per extra year
    # against a 33 s call. Accuracy is the cheaper option here.
    per_year = {}
    for year in years:
        result_df["expected_demand_reduction_percent"] = base_shock * pi_by_year[year]
        result_df["expected_demand_reduction"] = (
            result_df["initial_eql_quantity"]
            * result_df["expected_demand_reduction_percent"]
        )
        solved = result_df.apply(_compute_equilibrium, axis=1)
        actual = solved["Q_eql_new"] - result_df["initial_eql_quantity"]
        per_year[year] = {
            "P_eq_new": solved["P_eq_new"],
            "Q_eql_new": solved["Q_eql_new"],
            "actual_reduction": actual,
            "expected_demand_reduction": result_df["expected_demand_reduction"].copy(),
            "expected_demand_reduction_percent": result_df[
                "expected_demand_reduction_percent"
            ].copy(),
            "carbon_savings_t": actual * result_df["carbon_intensity_t"],
        }

    # The unsuffixed columns are year 1, so every consumer that wants a single
    # year keeps working and keeps meaning something.
    first = per_year[1]
    for col, values in first.items():
        result_df[col] = values
    result_df["rebound_effect"] = (
        result_df["actual_reduction"] - result_df["expected_demand_reduction"]
    )
    result_df["rebound_effect_percent"] = (
        -1 * result_df["rebound_effect"] / result_df["expected_demand_reduction"]
    )
    if survival_weighted:
        for year in years:
            result_df[f"actual_reduction_Y{year}"] = per_year[year]["actual_reduction"]
            result_df[f"carbon_savings_t_Y{year}"] = per_year[year]["carbon_savings_t"]
            # The pre-rebound ("naive") reduction is needed per year too: the
            # 10-year waterfall decomposes naive into rebound plus actual, and all
            # three legs have to be summed over the same declining series.
            result_df[f"expected_demand_reduction_Y{year}"] = per_year[year][
                "expected_demand_reduction"
            ]

    if diet_scenario is not None:
        result_df["diet_scenario"] = diet_scenario

    # min_count=1 so a country whose every food group is NaN reports NaN rather
    # than 0.0. A bare .sum() returns 0.0 for an all-NaN group, which is
    # indistinguishable from "this country genuinely saves nothing" and is how
    # three countries sat in the outputs at zero with nothing warning. The guard
    # below is the half that makes it visible -- a silent NaN is barely better than
    # a silent zero, since the downstream `> 0` filters drop either one.
    food_savings = (
        result_df.groupby(["ISO", "Country", "scenario"])["carbon_savings_t"]
        .sum(min_count=1)
        .abs()
        .reset_index()
        .rename(columns={"carbon_savings_t": "annual_food_savings_t"})
    )
    _report_unsolved(food_savings, result_df)
    if survival_weighted:
        for year in years:
            series = (
                result_df.groupby(["ISO", "Country", "scenario"])[
                    f"carbon_savings_t_Y{year}"
                ]
                .sum(min_count=1)
                .abs()
                .reset_index()
                .rename(
                    columns={
                        f"carbon_savings_t_Y{year}": f"annual_food_savings_t_Y{year}"
                    }
                )
            )
            food_savings = pd.merge(
                food_savings, series, on=["ISO", "Country", "scenario"], how="left"
            )
    if diet_scenario is not None:
        food_savings["diet_scenario"] = diet_scenario

    # Carried on .attrs rather than returned: every caller unpacks exactly two
    # values, so a third return would break all of them for a quantity almost
    # none of them want.
    result_df.attrs["survivor_food_factor"] = _survivor_food_factor(
        result_df, sim_result, sim_result_perc
    )

    return food_savings, result_df


# Carbon-intensity sensitivity scenarios the survivor food factor is built for.
# The factor must be rebuilt inside each one -- pinning it to the mean would
# leave the P10/P90 runs pricing survivor food at central intensities while
# pricing the food savings at the sensitivity intensities.
SURVIVOR_CI_SCENARIOS: Dict[str, str] = {
    "mean": "carbon_intensity.csv",
    "p10": "carbon_intensity_p10.csv",
    "p90": "carbon_intensity_p90.csv",
}


def build_survivor_food_factor(
    ci_scenarios: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Build and write the per ISO × scenario × ci_scenario survivor food factor.

    Writes ``data_result/survivor_food_factor.csv``.  Reads nothing the
    price-rebound pipeline does not already read, and writes no other output.
    """
    if ci_scenarios is None:
        ci_scenarios = SURVIVOR_CI_SCENARIOS

    frames = []
    for label, ci in ci_scenarios.items():
        print(f"  survivor food factor: ci_scenario={label} ({ci})")
        _, result_df = compute_food_savings(ci_file=ci)
        frame = result_df.attrs["survivor_food_factor"].copy()
        frame.insert(2, "ci_scenario", label)
        frames.append(frame)

    out = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["ISO", "scenario", "ci_scenario"])
        .reset_index(drop=True)
    )
    path = output_path("survivor_food_factor.csv")
    out.to_csv(path, index=False)
    print(f"Survivor food factor: {path}  ({len(out)} rows)")
    return out


# Survivor emissions are written once per carbon-intensity scenario, because the
# per-capita factor now carries a P&N food add-back that is built from that
# scenario's carbon intensities.  The mean file keeps the original unsuffixed
# name, so every reader that does not ask for a scenario is unaffected.
SURVIVOR_EMISSIONS_FILES: Dict[str, str] = {
    "mean": "mortality model total emissions_oecd.csv",
    "p10": "mortality model total emissions_oecd_p10.csv",
    "p90": "mortality model total emissions_oecd_p90.csv",
}


def survivor_emissions_path(ci_scenario: str = "mean") -> Path:
    """Path to the survivor-emissions CSV for one carbon-intensity scenario."""
    if ci_scenario not in SURVIVOR_EMISSIONS_FILES:
        raise ValueError(
            f"Unknown ci_scenario {ci_scenario!r}. "
            f"Choose from: {sorted(SURVIVOR_EMISSIONS_FILES)}"
        )
    return ROOT / SURVIVOR_EMISSIONS_FILES[ci_scenario]


def load_mortality_emissions(ci_scenario: str = "mean"):
    """Load year-by-year survivor emissions with OECD consumption-GHG factors.

    Reads the survivor-emissions CSV for ``ci_scenario``, written by
    ``data_visualization.consumption_ghg``. That script takes the mortality
    model's person-years from ``mortality model total emissions.csv`` (which must
    be generated with ``population_weighted=True``) and attaches OECD
    demand-based final-consumption emissions factors.

    ``ci_scenario`` must match the carbon-intensity file the food-savings side of
    the same comparison is run with. The survivor factor's P&N food add-back is
    priced with those intensities, so pairing (say) P90 food savings with the
    mean survivor file compares two different bases -- the exact defect this
    parameter exists to prevent.

    The two files are deliberately distinct: consumption_ghg used to write back
    over its own input, which made the run order load-bearing and silent. Run
    ``python -m data_visualization.consumption_ghg`` before any analysis script
    if the person-years have changed. See the README for the run order.
    """
    path = survivor_emissions_path(ci_scenario)
    if not path.is_file():
        raise FileNotFoundError(
            f"Survivor emissions file not found:\n  {path}\n"
            "Build it with: python -m data_visualization.consumption_ghg"
        )
    return pd.read_csv(path)


def adjust_survivor_decline(mort: pd.DataFrame, decline_rate: float) -> pd.DataFrame:
    """Apply an annual decline to the NON-FOOD part of the survivor factor.

    The decline used to apply to the whole per-capita factor, which post-basis-
    change is ``oecd_nonfood_ghg_t_per_capita + food_add_back_t_per_capita``, so
    it declined food too. Food emissions are difficult-to-abate and plateau while
    other sectors decarbonise (Smith, Vaughan & Forster), and the food-savings
    side of the same comparison holds carbon intensity constant across all ten
    years -- so declining the survivor's food put the same food on two different
    trajectories. Food is now held flat and only non-food declines.

    ``emissions_factor_Y0`` is unchanged: it remains the undeclined sum, and year
    0 is not declined either way.
    """
    required = ["oecd_nonfood_ghg_t_per_capita", "food_add_back_t_per_capita"]
    missing = [c for c in required if c not in mort.columns]
    if missing:
        raise KeyError(
            f"Survivor frame is missing {missing}. The decline applies to the "
            "non-food component only, so the food/non-food split is required. "
            "Rebuild with: python -m data_visualization.consumption_ghg"
        )

    adjusted = mort.copy()
    adjusted["total_emissions"] = 0.0
    for year in range(1, 11):
        factor_col = f"emissions_factor_Y{year}"
        emissions_col = f"emissions_Y{year}"
        # DO NOT "simplify" this to nonfood * (1 - decline_rate) ** year + food.
        # The two are algebraically identical -- nf*q + fd == (nf + fd) - nf*(1-q)
        # -- but this form anchors years 1-10 to the committed
        # emissions_factor_Y0 instead of re-deriving the sum from the two
        # separately-parsed components, and that difference is measurable.
        #
        # pandas read_csv defaults to float_precision=None (the fast xstrtod
        # converter), which parses 26 cells of these three columns to a double
        # one ULP off what an exact strtod gives. The file text itself is exactly
        # round-trippable -- Python's float() reproduces the identity -- so the
        # components sum to the factor in memory but not always after a read.
        # Re-deriving therefore moved 20 rows by 1-2 ULP at decline_rate=0.0,
        # where the decline must be an exact no-op. Here (1 - (1-0.0)**year) is
        # exactly 0.0, so the factor is emissions_factor_Y0 untouched, bit for
        # bit, whatever the parser did.
        #
        # Food is held flat implicitly: it is whatever Y0 - nonfood leaves. The
        # food column is required by the guard above but never read here, so do
        # not go looking for the term that holds it constant -- there isn't one.
        adjusted[factor_col] = adjusted["emissions_factor_Y0"] - (
            adjusted["oecd_nonfood_ghg_t_per_capita"]
            * (1 - (1 - decline_rate) ** year)
        )
        adjusted[emissions_col] = adjusted[f"diff_Y{year}"] * adjusted[factor_col]
        adjusted["total_emissions"] = adjusted["total_emissions"] + adjusted[emissions_col]
    return adjusted


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


if __name__ == "__main__":
    # Redirected stdout on Windows falls back to cp1252, which cannot encode the
    # non-ASCII this script prints. Set UTF-8 on the streams here rather than at
    # module level, so importing this module never mutates global stream state.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    build_survivor_food_factor()
