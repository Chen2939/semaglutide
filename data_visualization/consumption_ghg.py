"""
OECD demand-based final-consumption GHG survivor-emissions pipeline.

This module replaces the old World Bank territorial emissions factor used for
additional survivors with OECD Greenhouse Gas Footprints (GHGFP) demand-based
final-consumption GHG.  It preserves the existing
``mortality model total emissions.csv`` schema so downstream break-even,
dashboard, and diet-sensitivity scripts can be rerun without major changes.

Method scope:
    FINAL_DEMAND_CATEGORY == CONS  (Final consumption)
    TIME_PERIOD == 2022
    UNIT_MEASURE == T_CO2E         (Tonnes of CO2-equivalent)
    UNIT_MULT == 6                 (Millions, i.e. Mt CO2e)

The ACTIVITY dimension is read in full rather than filtered to ``_T``, because
the per-capita factor is now assembled as

    (OECD total - OECD food bundle) + food add-back

so that the food component can be re-priced.  See FOOD_BUNDLE_ACTIVITIES.

Usage:
    python -m data_visualization.consumption_ghg
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import warnings

from .pipeline import (
    ROOT,
    SURVIVOR_EMISSIONS_FILES,
    output_path,
    survivor_emissions_path,
)


OECD_FILE = ROOT / "oecd" / "consumption_ghg_2025.csv"

# Input: the mortality model's person-year output. This script consumes the
# diff_Y* columns only; it drops and recomputes every emissions column.
MORTALITY_EMISSIONS_FILE = ROOT / "mortality model total emissions.csv"

# Output: a distinct file. This script used to write back over
# MORTALITY_EMISSIONS_FILE, which made the input and the output the same path.
# That made run order load-bearing and silent: running it twice fed its own
# output back in, and running deterministic_mortality.py afterwards replaced the
# emissions columns with NaN placeholders. Separate paths make the dependency
# explicit and the sequence order-insensitive.
NEW_FILE = survivor_emissions_path("mean")

# Optional World Bank baseline, used only to produce the OECD-vs-World-Bank
# comparison. It is NOT written by this script: auto-creating it from
# MORTALITY_EMISSIONS_FILE would label already-rebuilt OECD data as the World
# Bank baseline and yield a comparison of OECD against itself.
BACKUP_FILE = ROOT / "mortality model total emissions_worldbank_backup.csv"

COMPARISON_FILE = ROOT / "data_result" / "oecd_vs_worldbank_survivor_emissions.csv"
PER_CAPITA_FILE = ROOT / "data_result" / "oecd_consumption_ghg_per_capita.csv"

# The P&N-basis food footprint of one treated survivor, per ISO × scenario ×
# ci_scenario.  Built by ``python -m data_visualization.pipeline``.
SURVIVOR_FOOD_FACTOR_FILE = ROOT / "data_result" / "survivor_food_factor.csv"

# Which carbon-intensity scenario's add-back feeds the headline survivor
# emissions file.  The food-savings side of the headline analysis runs on
# ``carbon_intensity.csv``, so the add-back must be the matching "mean" rows --
# pairing a P90 add-back with mean-priced savings would reintroduce, in the
# opposite direction, exactly the basis mismatch this change removes.
DEFAULT_CI_SCENARIO = "mean"


# ── Food bundle ───────────────────────────────────────────────────────
#
# The four ISIC activity codes whose demand-based emissions are food.  A01 and
# A03 are sub-sections of A (A02, forestry and logging, is not food and stays in
# the remainder) and C10T12 is a sub-section of C, so the non-food remainder has
# to be built by subtracting those children from their parents -- dropping the
# parent sections wholesale would discard forestry and all non-food
# manufacturing along with the food.
FOOD_BUNDLE_ACTIVITIES = ("A01", "A03", "C10T12", "I")

# The ISIC sections.  Together with HH -- direct household emissions, i.e.
# household fuel and vehicle use, which belong to no industry -- these partition
# the ``_T`` total.  Omitting HH would silently understate every country.
ISIC_SECTIONS = tuple("ABCDEFGHIJKLMNOPQRST")

# The OECD publishes these series to three decimals in Mt, so a section-wise sum
# carries rounding of order 1e-3 Mt.  A residual materially above that means the
# filter is selecting the wrong slice, not that the data are noisy.
STRUCTURAL_TOLERANCE_MT = 0.005

# The factor's two components are carried into the survivor-emissions file next
# to the sum they make up. They are built by one addition (nonfood + food) in
# build_oecd_per_capita_table, so the residual is expected to be exactly zero,
# not merely small; the tolerance is a floor against a future reassociation of
# that expression rather than a real error budget. Factors are of order 1-30
# t/person, so this is ~1e-13 relative.
COMPONENT_SUM_TOLERANCE = 1e-12


def _load_oecd_by_activity(path: Path = OECD_FILE) -> pd.DataFrame:
    """Load 2022 final-consumption GHG in Mt CO2e, one column per ACTIVITY."""
    df = pd.read_csv(path)
    filtered = df[
        (df["FINAL_DEMAND_CATEGORY"] == "CONS")
        & (df["TIME_PERIOD"] == 2022)
        & (df["UNIT_MEASURE"] == "T_CO2E")
        & (df["UNIT_MULT"] == 6)
    ].copy()

    filtered["OBS_VALUE"] = pd.to_numeric(filtered["OBS_VALUE"], errors="coerce")
    filtered = filtered.dropna(subset=["OBS_VALUE"])

    wide = filtered.pivot_table(
        index=["FINAL_DEMAND_AREA", "Final demand area"],
        columns="ACTIVITY",
        values="OBS_VALUE",
        aggfunc="sum",
    )
    wide.index.names = ["ISO", "Country"]
    return wide.reset_index()


def check_activity_partition(wide: pd.DataFrame) -> pd.Series:
    """Verify the food bundle plus the non-food remainder reconstructs ``_T``.

    This is the guard that the ACTIVITY filter is selecting the right slice.  If
    the bundle were double-counting a parent section, or the remainder were
    missing HH, the reconstruction would miss ``_T`` by far more than the
    publication rounding.  Raises rather than warns: a wrong split here silently
    rescales every survivor emissions factor.

    Returns the per-country residual in Mt.
    """
    required = {*ISIC_SECTIONS, "HH", "_T", "A02", *FOOD_BUNDLE_ACTIVITIES}
    missing = sorted(required - set(wide.columns))
    if missing:
        raise ValueError(
            f"OECD extract is missing ACTIVITY code(s) {missing}. "
            "The food bundle cannot be separated from the total."
        )
    if wide[sorted(required)].isna().any().any():
        blank = sorted(
            wide.loc[wide[sorted(required)].isna().any(axis=1), "ISO"].unique()
        )
        raise ValueError(
            f"OECD extract has blank ACTIVITY cells for {blank}. "
            "A missing section would be read as a zero contribution to _T."
        )

    # A must split cleanly into its three sub-sections, or the A01/A03 pull-out
    # is not a partition of A.
    a_residual = (
        wide[["A01", "A02", "A03"]].sum(axis=1) - wide["A"]
    ).abs()
    if (a_residual > STRUCTURAL_TOLERANCE_MT).any():
        raise ValueError(
            "A01+A02+A03 does not reconstruct section A; max residual "
            f"{a_residual.max():.6f} Mt."
        )

    other_sections = [s for s in ISIC_SECTIONS if s not in ("A", "C", "I")]
    remainder = (
        wide["A02"]
        + (wide["C"] - wide["C10T12"])
        + wide[other_sections].sum(axis=1)
        + wide["HH"]
    )
    bundle = wide[list(FOOD_BUNDLE_ACTIVITIES)].sum(axis=1)
    residual = (bundle + remainder - wide["_T"]).abs()

    over = residual[residual > STRUCTURAL_TOLERANCE_MT]
    if len(over):
        worst = over.sort_values(ascending=False).head(5)
        detail = ", ".join(
            f"{wide.loc[i, 'ISO']}={v:.6f}" for i, v in worst.items()
        )
        raise ValueError(
            f"Food bundle + non-food remainder does not reconstruct _T for "
            f"{len(over)} country(ies) (tolerance {STRUCTURAL_TOLERANCE_MT} Mt). "
            f"Worst: {detail}. The ACTIVITY filter is wrong."
        )
    return residual


def load_oecd_final_consumption_ghg(path: Path = OECD_FILE) -> pd.DataFrame:
    """Load OECD final-consumption GHG totals and the food bundle, in Mt CO2e."""
    wide = _load_oecd_by_activity(path)
    check_activity_partition(wide)

    out = wide[["ISO", "Country"]].copy()
    out["TIME_PERIOD"] = 2022
    out["oecd_consumption_ghg_Mt"] = wide["_T"]
    out["oecd_food_bundle_Mt"] = wide[list(FOOD_BUNDLE_ACTIVITIES)].sum(axis=1)
    return out.reset_index(drop=True)


def un_wpp_path(filename: str) -> Path:
    """Resolve a UN WPP 2024 workbook, read from wherever it already lives.

    The WPP workbooks are large and are not redistributed in this repository, so
    ``UN_WPP_DIR`` points at a local copy and the file is read in place. Copying
    one into the tree would create a second version that can drift from the
    source without anything noticing.

    ``code/compute_child_energy.R`` reads the same environment variable for the
    single-age male and female workbooks.
    """
    base = Path(os.environ.get("UN_WPP_DIR", ROOT / "UN"))
    path = base / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"UN WPP 2024 workbook not found:\n  {path}\n"
            f"Set UN_WPP_DIR to the directory containing '{filename}'.\n"
            "See the README (data sources) for the download."
        )
    return path


def load_un_population_2022() -> pd.DataFrame:
    """Load 2022 total national population from UN WPP (all ages, both sexes)."""
    path = un_wpp_path("WPP2024_POP_F01_1_POPULATION_SINGLE_AGE_BOTH_SEXES.xlsx")
    pop = pd.read_excel(path, sheet_name=0, skiprows=16)
    pop = pop[pop["Year"] == 2022].copy()
    pop = pop.rename(columns={"Region, subregion, country or area *": "Country"})

    age_cols = [
        col
        for col in pop.columns
        if isinstance(col, int) or str(col).isdigit() or str(col).endswith("+")
    ]
    age_data = pop[age_cols].apply(pd.to_numeric, errors="coerce")
    pop = pop[["Country", "ISO3 Alpha-code"]].copy()
    pop["population_2022"] = age_data.sum(axis=1) * 1000
    pop["ISO"] = pop["ISO3 Alpha-code"]
    pop = pop[pop["ISO"].notna()]
    return pop[["ISO", "Country", "population_2022"]].drop_duplicates("ISO")


def load_survivor_food_add_back(
    ci_scenario: str = DEFAULT_CI_SCENARIO,
    path: Path = SURVIVOR_FOOD_FACTOR_FILE,
) -> pd.DataFrame:
    """Load the P&N-basis survivor food footprint, in t CO2e/person/year.

    ``survivor_food_t`` is already an annual per-person tonnage, so it drops
    straight into the per-capita factor with no rescaling.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Survivor food factor not found:\n  {path}\n"
            "Build it with: python -m data_visualization.pipeline"
        )
    df = pd.read_csv(path)
    available = sorted(df["ci_scenario"].unique())
    if ci_scenario not in available:
        raise ValueError(
            f"Unknown ci_scenario {ci_scenario!r}. Available: {available}"
        )
    sub = df[df["ci_scenario"] == ci_scenario]
    return sub[["ISO", "scenario", "survivor_food_t"]].rename(
        columns={"survivor_food_t": "food_add_back_t_per_capita"}
    )


def build_oecd_per_capita_table(
    ci_scenario: str = DEFAULT_CI_SCENARIO,
    null_mode: bool = False,
) -> pd.DataFrame:
    """Build the survivor per-capita emissions factor in t/person.

    The factor is assembled as

        (OECD total - OECD food bundle) + food add-back

    rather than taken straight from the OECD total.  The OECD bundle prices food
    at national inventory rates while the food-savings side of the analysis
    prices the same food with Poore & Nemecek -- roughly double per kilo -- so
    charging survivors the OECD food component compared two different bases.
    The add-back puts both sides on P&N.

    The factor now varies by uptake scenario, because the treated population's
    mean energy requirement does; the returned table is one row per ISO ×
    scenario.

    Parameters
    ----------
    ci_scenario:
        Which carbon-intensity scenario's add-back to use ("mean", "p10",
        "p90").  Must match the carbon intensities the food-savings side is run
        with.
    null_mode:
        When True the add-back is the OECD food bundle that was just removed,
        making the restructure an exact no-op.  Retained as a regression check
        that the subtract-and-re-add plumbing is inert; not used in analysis.
    """
    ghg = load_oecd_final_consumption_ghg()
    pop = load_un_population_2022()
    per_capita = pd.merge(ghg, pop, on="ISO", how="inner")

    per_capita["oecd_nonfood_ghg_t_per_capita"] = (
        (per_capita["oecd_consumption_ghg_Mt"] - per_capita["oecd_food_bundle_Mt"])
        * 1e6
        / per_capita["population_2022"]
    )
    per_capita["oecd_food_bundle_t_per_capita"] = (
        per_capita["oecd_food_bundle_Mt"] * 1e6
        / per_capita["population_2022"]
    )

    add_back = load_survivor_food_add_back(ci_scenario)
    per_capita["ci_scenario"] = ci_scenario

    # Expand to one row per uptake scenario before joining, so that a country
    # with no P&N add-back keeps its scenario rows and reports a NaN factor
    # rather than silently vanishing from the table.
    scenarios = pd.DataFrame({"scenario": sorted(add_back["scenario"].unique())})
    per_capita = per_capita.merge(scenarios, how="cross")
    per_capita = per_capita.merge(add_back, on=["ISO", "scenario"], how="left")

    if null_mode:
        per_capita["food_add_back_t_per_capita"] = per_capita[
            "oecd_food_bundle_t_per_capita"
        ]

    per_capita["oecd_consumption_ghg_t_per_capita"] = (
        per_capita["oecd_nonfood_ghg_t_per_capita"]
        + per_capita["food_add_back_t_per_capita"]
    )
    return per_capita.sort_values(["ISO", "scenario"]).reset_index(drop=True)


def validate_oecd_inputs(per_capita: pd.DataFrame) -> None:
    """Validate against the published USA total and print coverage."""
    usa = per_capita[per_capita["ISO"] == "USA"]
    if usa.empty:
        raise ValueError("USA is missing from OECD per-capita table")

    usa_total = float(usa["oecd_consumption_ghg_Mt"].iloc[0])
    if not np.isclose(usa_total, 5892.9, atol=0.05):
        raise ValueError(
            f"USA OECD validation failed: expected 5892.9 Mt, got {usa_total}"
        )

    print("OECD validation")
    print(f"  USA 2022 final-consumption GHG: {usa_total:,.1f} Mt CO2e")
    print(
        "  USA food basis: OECD bundle "
        f"{float(usa['oecd_food_bundle_t_per_capita'].iloc[0]):,.2f} t/person"
        " -> P&N add-back "
        f"{float(usa['food_add_back_t_per_capita'].iloc[0]):,.2f} t/person"
    )
    for _, r in usa.iterrows():
        print(
            f"  USA per-capita factor ({r['scenario']}): "
            f"{r['oecd_consumption_ghg_t_per_capita']:,.2f} t/person"
        )
    print(
        "  Countries with OECD + population match: "
        f"{per_capita['ISO'].nunique()}"
    )
    n_no_addback = int(
        per_capita.loc[
            per_capita["food_add_back_t_per_capita"].isna(), "ISO"
        ].nunique()
    )
    if n_no_addback:
        print(
            f"  Countries with no P&N add-back (factor is NaN): {n_no_addback}"
        )


def rebuild_mortality_emissions(
    decline_rate: float = 0.0,
    old_file: Path = MORTALITY_EMISSIONS_FILE,
    comparison_file: Path | None = None,
    ci_scenario: str = DEFAULT_CI_SCENARIO,
    null_mode: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild survivor emissions using OECD per-capita GHG factors.

    Parameters
    ----------
    decline_rate:
        Annual multiplicative decline applied after year 0, to the NON-FOOD
        component only; the food add-back is held flat.  The corrected central
        analysis uses 0.0 (constant 2022 OECD factors), where the two forms
        coincide exactly.
    old_file:
        Existing survivor-emissions CSV, used as the source of mortality
        person-year diffs.
    comparison_file:
        Optional older survivor-emissions CSV, used only to recover the previous
        per-capita emissions factor for comparison.  The comparison is computed
        with the current person-year diffs so deterministic mortality updates
        are not mixed with old Monte Carlo person-years.
    ci_scenario, null_mode:
        Passed through to ``build_oecd_per_capita_table``.
    """
    per_capita = build_oecd_per_capita_table(
        ci_scenario=ci_scenario, null_mode=null_mode
    )
    validate_oecd_inputs(per_capita)

    old = pd.read_csv(old_file)
    # Joined on ISO *and* scenario: the factor now carries a P&N food add-back
    # that depends on the treated population's mean energy requirement, which
    # differs between max and moderate uptake. An ISO-only join would silently
    # fan out to two rows per country.
    merged = pd.merge(
        old.drop(
            columns=[
                "emissions_factor_Y0",
                "total_emissions",
                *[f"emissions_factor_Y{y}" for y in range(1, 11)],
                *[f"emissions_Y{y}" for y in range(1, 11)],
            ],
            errors="ignore",
        ),
        # The two components of the factor travel with it. The survivor decline
        # applies to non-food only -- food emissions are difficult-to-abate and
        # plateau while other sectors decarbonise -- so the consumer of this file
        # needs the split, not just the sum it used to get here.
        #
        # These come from build_oecd_per_capita_table above, which is called once
        # per ci_scenario. Do NOT source them from
        # data_result/oecd_consumption_ghg_per_capita.csv instead: that file is
        # written from a single default (mean) call, so joining it would give the
        # p10 and p90 mortality files mean-basis components without failing.
        per_capita[
            [
                "ISO",
                "scenario",
                "oecd_consumption_ghg_t_per_capita",
                "oecd_nonfood_ghg_t_per_capita",
                "food_add_back_t_per_capita",
            ]
        ],
        on=["ISO", "scenario"],
        how="left",
    )
    if len(merged) != len(old):
        raise ValueError(
            f"Factor join changed row count: {len(old)} -> {len(merged)}. "
            "The per-capita table is not unique on ISO x scenario."
        )

    missing = merged[merged["oecd_consumption_ghg_t_per_capita"].isna()]["ISO"].unique()
    if len(missing) > 0:
        print(
            "Warning: missing OECD per-capita factors for "
            f"{len(missing)} ISO codes: {', '.join(sorted(missing))}"
        )

    merged = merged.rename(
        columns={"oecd_consumption_ghg_t_per_capita": "emissions_factor_Y0"}
    )

    # The widened join is new surface: three columns now arrive where one did,
    # and nothing downstream would notice if the components did not belong to the
    # sum they are carried alongside. Assert the identity instead of trusting it.
    nonfood_null = merged["oecd_nonfood_ghg_t_per_capita"].isna()
    food_null = merged["food_add_back_t_per_capita"].isna()
    factor_null = merged["emissions_factor_Y0"].isna()

    # Null patterns first, because the sum check has to skip null rows and a bare
    # .notna() filter would also skip a row whose factor went NaN for some other
    # reason -- masking exactly the mismatch this is here to catch. Rows can be
    # legitimately null two ways: an ISO absent from the OECD/population join
    # (all three null), or a country with no P&N add-back (AGO is one: food and
    # therefore the factor are null, non-food is not). Both are covered by
    # requiring the factor to be null exactly when a component is.
    expected_null = nonfood_null | food_null
    if not factor_null.equals(expected_null):
        bad = merged.loc[factor_null != expected_null, ["ISO", "scenario"]]
        raise ValueError(
            "Survivor factor null pattern does not match its components for "
            f"{len(bad)} row(s): "
            + ", ".join(f"{r.ISO}/{r.scenario}" for r in bad.itertuples())
            + ". The factor must be NaN exactly when a component is."
        )

    present = ~expected_null
    residual = (
        merged.loc[present, "oecd_nonfood_ghg_t_per_capita"]
        + merged.loc[present, "food_add_back_t_per_capita"]
        - merged.loc[present, "emissions_factor_Y0"]
    ).abs()
    worst = float(residual.max()) if len(residual) else 0.0
    if worst > COMPONENT_SUM_TOLERANCE:
        raise ValueError(
            "Survivor factor components do not sum to the factor: worst "
            f"residual {worst:.3e} t/person over {int(present.sum())} rows "
            f"(tolerance {COMPONENT_SUM_TOLERANCE:.0e}). The join brought in "
            "components from a different basis than the sum."
        )
    print(
        f"  Component check: nonfood + food == factor on {int(present.sum())} "
        f"rows, worst residual {worst:.3e} t/person; "
        f"{int(expected_null.sum())} null row(s) skipped, null patterns agree"
    )

    merged["total_emissions"] = 0.0
    for year in range(1, 11):
        factor_col = f"emissions_factor_Y{year}"
        emissions_col = f"emissions_Y{year}"
        # Non-food declines, food is held flat -- the same correction as
        # pipeline.adjust_survivor_decline, which is the live implementation. This
        # path is inert (main() passes 0.0), but leaving the old whole-factor form
        # here would be a landmine for the first caller to pass a nonzero rate.
        #
        # Written in the same anchored form as the shared function, deliberately:
        # DO NOT "simplify" to nonfood * (1 - decline_rate) ** year + food. The
        # two are algebraically identical, but this one subtracts the abated part
        # of non-food from emissions_factor_Y0 rather than re-deriving the sum
        # from its components, so at decline_rate=0.0 the factor is Y0 bit for
        # bit. The components are in memory here, so the pandas float-parser
        # artifact documented in pipeline.adjust_survivor_decline cannot arise on
        # this path -- but one form in both places is worth more than a local
        # optimisation, since these two must not drift again.
        merged[factor_col] = merged["emissions_factor_Y0"] - (
            merged["oecd_nonfood_ghg_t_per_capita"]
            * (1 - (1 - decline_rate) ** year)
        )
        merged[emissions_col] = merged[f"diff_Y{year}"] * merged[factor_col]
        merged["total_emissions"] = merged["total_emissions"] + merged[emissions_col]

    # Match the original column order as closely as possible.
    ordered_cols = [
        "ISO",
        "scenario",
        *[f"diff_Y{y}" for y in range(0, 11)],
        "total_person_years_saved",
        "emissions_factor_Y0",
        "total_emissions",
        *[
            col
            for year in range(1, 11)
            for col in (f"emissions_factor_Y{year}", f"emissions_Y{year}")
        ],
        # Appended, not slotted in beside emissions_factor_Y0 where they belong
        # semantically. Grouping them with the sum would shift the position of
        # every emissions column after it; appending leaves all 36 pre-existing
        # columns at their existing index, so any reader doing positional access
        # is unaffected by the widening.
        "oecd_nonfood_ghg_t_per_capita",
        "food_add_back_t_per_capita",
    ]
    rebuilt = merged[ordered_cols]

    comparison_source = old
    if comparison_file is not None and comparison_file.exists():
        comparison_source = pd.read_csv(comparison_file)

    if "emissions_factor_Y0" in comparison_source.columns:
        old_factor = comparison_source[
            ["ISO", "scenario", "emissions_factor_Y0"]
        ].rename(columns={"emissions_factor_Y0": "emissions_factor_Y0_worldbank"})
    else:
        # The person-years input carries no emissions columns, so when no
        # genuine World Bank baseline is supplied there is nothing to compare
        # against. Leave the baseline empty; main() skips writing the table.
        old_factor = comparison_source[["ISO", "scenario"]].copy()
        old_factor["emissions_factor_Y0_worldbank"] = np.nan
    comparison = old[
        ["ISO", "scenario", "total_person_years_saved", *[f"diff_Y{y}" for y in range(1, 11)]]
    ].merge(
        old_factor,
        on=["ISO", "scenario"],
        how="left",
    )
    comparison["total_emissions_worldbank"] = 0.0
    for year in range(1, 11):
        comparison["total_emissions_worldbank"] += (
            comparison[f"diff_Y{year}"] * comparison["emissions_factor_Y0_worldbank"]
        )

    comparison = comparison[
        ["ISO", "scenario", "total_person_years_saved", "emissions_factor_Y0_worldbank", "total_emissions_worldbank"]
    ].merge(
        rebuilt[["ISO", "scenario", "emissions_factor_Y0", "total_emissions"]],
        on=["ISO", "scenario"],
    )
    comparison = comparison.rename(
        columns={
            "emissions_factor_Y0": "emissions_factor_Y0_oecd",
            "total_emissions": "total_emissions_oecd",
        }
    )
    comparison["emissions_factor_change_pct"] = (
        comparison["emissions_factor_Y0_oecd"]
        / comparison["emissions_factor_Y0_worldbank"]
        - 1
    ) * 100
    comparison["survivor_emissions_change_pct"] = (
        comparison["total_emissions_oecd"]
        / comparison["total_emissions_worldbank"]
        - 1
    ) * 100

    return rebuilt, comparison


def main(ci_scenarios: list[str] | None = None) -> None:
    print("Rebuilding mortality survivor emissions with OECD consumption GHG...")

    # One survivor-emissions file per carbon-intensity scenario. The mean file
    # goes to the original unsuffixed path, so every existing reader keeps
    # reading the same file and gets the same basis it does now.
    if ci_scenarios is None:
        ci_scenarios = list(SURVIVOR_EMISSIONS_FILES)

    comparison = None
    for ci in ci_scenarios:
        print(f"\n-- ci_scenario={ci} --")
        rebuilt, comp = rebuild_mortality_emissions(
            decline_rate=0.0,
            old_file=MORTALITY_EMISSIONS_FILE,
            comparison_file=BACKUP_FILE if BACKUP_FILE.exists() else None,
            ci_scenario=ci,
        )
        out = survivor_emissions_path(ci)
        rebuilt.to_csv(out, index=False)
        print(f"Survivor-emissions CSV (OECD, {ci}): {out}")
        if ci == DEFAULT_CI_SCENARIO:
            comparison = comp

    COMPARISON_FILE.parent.mkdir(exist_ok=True)
    build_oecd_per_capita_table().to_csv(PER_CAPITA_FILE, index=False)
    print(f"\nOECD per-capita table ({DEFAULT_CI_SCENARIO}): {PER_CAPITA_FILE}")

    if comparison is None:
        return

    # The comparison is only meaningful against a genuine World Bank baseline.
    # Without one, comparison_source falls back to the input file -- which is
    # itself OECD-derived -- so the table would report a uniform 0% change.
    # Skip it rather than overwrite a real comparison with zeros.
    if BACKUP_FILE.exists():
        comparison.to_csv(COMPARISON_FILE, index=False)
        print(f"Comparison table: {COMPARISON_FILE}")
    else:
        print(
            f"\nSkipped {COMPARISON_FILE.name}: no World Bank baseline at\n"
            f"  {BACKUP_FILE}\n"
            "  Without it the comparison would be OECD against itself (0% change).\n"
            "  The committed comparison table is left untouched."
        )

    usa = comparison[(comparison["ISO"] == "USA") & (comparison["scenario"] == "max_uptake")]
    if not usa.empty:
        row = usa.iloc[0]
        print("\nUSA max_uptake change")
        print(
            "  emissions factor: "
            f"{row['emissions_factor_Y0_worldbank']:.2f} -> "
            f"{row['emissions_factor_Y0_oecd']:.2f} t/person"
        )
        print(
            "  10-year survivor emissions: "
            f"{row['total_emissions_worldbank']/1e6:.2f} -> "
            f"{row['total_emissions_oecd']/1e6:.2f} Mt"
        )


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=pd.errors.PerformanceWarning)
        main()
