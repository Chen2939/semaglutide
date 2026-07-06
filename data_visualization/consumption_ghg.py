"""
OECD demand-based final-consumption GHG survivor-emissions pipeline.

This module replaces the old World Bank territorial emissions factor used for
additional survivors with OECD Greenhouse Gas Footprints (GHGFP) demand-based
final-consumption GHG.  It preserves the existing
``mortality model total emissions.csv`` schema so downstream break-even,
dashboard, and diet-sensitivity scripts can be rerun without major changes.

Method scope:
    FINAL_DEMAND_CATEGORY == CONS  (Final consumption)
    ACTIVITY == _T                 (Total - All activities)
    TIME_PERIOD == 2022
    UNIT_MEASURE == T_CO2E         (Tonnes of CO2-equivalent)
    UNIT_MULT == 6                 (Millions, i.e. Mt CO2e)

Usage:
    python -m data_visualization.consumption_ghg
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import warnings

from .pipeline import ROOT, output_path


OECD_FILE = ROOT / "oecd" / "consumption_ghg_2025.csv"
MORTALITY_EMISSIONS_FILE = ROOT / "mortality model total emissions.csv"
BACKUP_FILE = ROOT / "mortality model total emissions_worldbank_backup.csv"
NEW_FILE = ROOT / "mortality model total emissions.csv"
COMPARISON_FILE = ROOT / "data_result" / "oecd_vs_worldbank_survivor_emissions.csv"
PER_CAPITA_FILE = ROOT / "data_result" / "oecd_consumption_ghg_per_capita.csv"


def load_oecd_final_consumption_ghg(path: Path = OECD_FILE) -> pd.DataFrame:
    """Load OECD final-consumption GHG totals in Mt CO2e."""
    df = pd.read_csv(path)
    filtered = df[
        (df["FINAL_DEMAND_CATEGORY"] == "CONS")
        & (df["ACTIVITY"] == "_T")
        & (df["TIME_PERIOD"] == 2022)
        & (df["UNIT_MEASURE"] == "T_CO2E")
        & (df["UNIT_MULT"] == 6)
    ].copy()

    filtered["OBS_VALUE"] = pd.to_numeric(filtered["OBS_VALUE"], errors="coerce")
    filtered = filtered.dropna(subset=["OBS_VALUE"])
    filtered = filtered.rename(
        columns={
            "FINAL_DEMAND_AREA": "ISO",
            "Final demand area": "Country",
            "OBS_VALUE": "oecd_consumption_ghg_Mt",
        }
    )
    return filtered[["ISO", "Country", "TIME_PERIOD", "oecd_consumption_ghg_Mt"]]


def load_un_population_2022() -> pd.DataFrame:
    """Load 2022 total national population from UN WPP (all ages, both sexes)."""
    path = ROOT / "UN" / "WPP2024_POP_F01_1_POPULATION_SINGLE_AGE_BOTH_SEXES.xlsx"
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


def build_oecd_per_capita_table() -> pd.DataFrame:
    """Build OECD final-consumption GHG per-capita emissions in t/person."""
    ghg = load_oecd_final_consumption_ghg()
    pop = load_un_population_2022()
    per_capita = pd.merge(ghg, pop, on="ISO", how="inner")
    per_capita["oecd_consumption_ghg_t_per_capita"] = (
        per_capita["oecd_consumption_ghg_Mt"] * 1e6
        / per_capita["population_2022"]
    )
    return per_capita.sort_values("ISO").reset_index(drop=True)


def validate_oecd_inputs(per_capita: pd.DataFrame) -> None:
    """Validate professor's USA check and print coverage."""
    usa = per_capita[per_capita["ISO"] == "USA"]
    if usa.empty:
        raise ValueError("USA is missing from OECD per-capita table")

    usa_total = float(usa["oecd_consumption_ghg_Mt"].iloc[0])
    usa_pc = float(usa["oecd_consumption_ghg_t_per_capita"].iloc[0])
    if not np.isclose(usa_total, 5892.9, atol=0.05):
        raise ValueError(
            f"USA OECD validation failed: expected 5892.9 Mt, got {usa_total}"
        )

    print("OECD validation")
    print(f"  USA 2022 final-consumption GHG: {usa_total:,.1f} Mt CO2e")
    print(f"  USA per-capita factor:          {usa_pc:,.2f} t/person")
    print(f"  Countries with OECD + population match: {len(per_capita)}")


def rebuild_mortality_emissions(
    decline_rate: float = 0.0,
    old_file: Path = MORTALITY_EMISSIONS_FILE,
    comparison_file: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild survivor emissions using OECD per-capita GHG factors.

    Parameters
    ----------
    decline_rate:
        Annual multiplicative decline applied after year 0.  The corrected
        central analysis uses 0.0 (constant 2022 OECD factors).
    old_file:
        Existing survivor-emissions CSV, used as the source of mortality
        person-year diffs.
    comparison_file:
        Optional older survivor-emissions CSV, used only to recover the previous
        per-capita emissions factor for comparison.  The comparison is computed
        with the current person-year diffs so deterministic mortality updates
        are not mixed with old Monte Carlo person-years.
    """
    per_capita = build_oecd_per_capita_table()
    validate_oecd_inputs(per_capita)

    old = pd.read_csv(old_file)
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
        per_capita[["ISO", "oecd_consumption_ghg_t_per_capita"]],
        on="ISO",
        how="left",
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
    merged["total_emissions"] = 0.0
    for year in range(1, 11):
        factor_col = f"emissions_factor_Y{year}"
        emissions_col = f"emissions_Y{year}"
        merged[factor_col] = merged["emissions_factor_Y0"] * ((1 - decline_rate) ** year)
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
    ]
    rebuilt = merged[ordered_cols]

    comparison_source = old
    if comparison_file is not None and comparison_file.exists():
        comparison_source = pd.read_csv(comparison_file)

    old_factor = comparison_source[["ISO", "scenario", "emissions_factor_Y0"]].rename(
        columns={"emissions_factor_Y0": "emissions_factor_Y0_worldbank"}
    )
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


def main() -> None:
    print("Rebuilding mortality survivor emissions with OECD consumption GHG...")
    rebuilt, comparison = rebuild_mortality_emissions(
        decline_rate=0.0,
        old_file=MORTALITY_EMISSIONS_FILE,
        comparison_file=BACKUP_FILE if BACKUP_FILE.exists() else None,
    )

    if not BACKUP_FILE.exists():
        pd.read_csv(MORTALITY_EMISSIONS_FILE).to_csv(BACKUP_FILE, index=False)
        print(f"Saved World Bank backup: {BACKUP_FILE}")

    rebuilt.to_csv(NEW_FILE, index=False)
    COMPARISON_FILE.parent.mkdir(exist_ok=True)
    comparison.to_csv(COMPARISON_FILE, index=False)
    build_oecd_per_capita_table().to_csv(PER_CAPITA_FILE, index=False)

    print(f"Updated survivor-emissions CSV: {NEW_FILE}")
    print(f"Comparison table: {COMPARISON_FILE}")
    print(f"OECD per-capita table: {PER_CAPITA_FILE}")

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
