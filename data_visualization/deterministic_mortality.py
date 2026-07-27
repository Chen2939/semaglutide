"""
Deterministic expected-value mortality model.

This replaces the headline Monte Carlo survival calculation with its
deterministic expectation. Each simulated individual carries baseline and
semaglutide survival probabilities over a 10-year horizon. Human Life-Table
``Mx`` rates are converted to one-year death probabilities using:

    q = 1 - exp(-Mx)

Outputs preserve the schema consumed by ``data_visualization.consumption_ghg``:

  mortality model total emissions.csv
  data_result/deterministic_mortality_comparison.csv

``population_weighted``
-----------------------
Only the ``True`` (population-scaled) path is valid for anything feeding the
food:survivor ratio. Survivor emissions are divided into *national* FAOSTAT food
supply, so the numerator must be on the same national scale: ``True`` multiplies
each simulated individual's survival difference by its ``weighting`` before
aggregating, expanding the sample to national headcounts. ``False`` sums raw
per-individual differences and is sample-scale — roughly 240x smaller, since
``weighting`` has a median of ~241 — which would inflate every food:survivor
ratio by about that factor. It is retained only because the two settings are
different output *units*, not a correct-versus-incorrect pair.

Usage:
    python -m data_visualization.deterministic_mortality
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyreadr

from .pipeline import ROOT, output_path


SIMULATION_FILE = ROOT / "final_df_imputed.pkl"
MORTALITY_FILE = ROOT / "mortality2.rds"
OUTPUT_FILE = ROOT / "mortality model total emissions.csv"
PREVIOUS_OUTPUT_FILE = ROOT / "mortality model total emissions_pre_deterministic_backup.csv"
COMPARISON_FILE = output_path("deterministic_mortality_comparison.csv")


def get_raw_bmi_hazard_ratio(bmi: pd.Series) -> np.ndarray:
    """Map BMI to published all-cause mortality hazard-ratio categories."""
    return np.where(
        bmi < 18.5,
        1.51,
        np.where(
            (bmi >= 18.5) & (bmi < 20.0),
            1.13,
            np.where(
                (bmi >= 20.0) & (bmi < 25.0),
                1.00,
                np.where(
                    (bmi >= 25.0) & (bmi < 27.5),
                    1.07,
                    np.where(
                        (bmi >= 27.5) & (bmi < 30.0),
                        1.20,
                        np.where(
                            (bmi >= 30.0) & (bmi < 35.0),
                            1.45,
                            np.where(
                                (bmi >= 35.0) & (bmi < 40.0),
                                1.94,
                                np.where(bmi >= 40.0, 2.76, np.nan),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load simulated population and mortality lookup data."""
    sim = pd.read_pickle(SIMULATION_FILE)
    mortality = list(pyreadr.read_r(str(MORTALITY_FILE)).values())[0]
    return sim, mortality


def run_deterministic_mortality(
    df_input: pd.DataFrame,
    mortality_lookup: pd.DataFrame,
    benefit_reduction: float = 0.5,
    population_weighted: bool = True,
) -> pd.DataFrame:
    """Compute expected additional survivor person-years by country/scenario."""
    individual = compute_individual_survival_diffs(
        df_input,
        mortality_lookup,
        benefit_reduction=benefit_reduction,
        population_weighted=population_weighted,
    )
    diff_columns = [f"diff_Y{year}" for year in range(0, 11)]
    summary = individual.groupby(["ISO", "scenario"], as_index=False)[diff_columns].sum()
    summary["total_person_years_saved"] = summary[diff_columns].sum(axis=1)

    # Placeholder emissions columns keep the legacy schema intact until
    # consumption_ghg.py rebuilds authoritative OECD emissions.
    summary["emissions_factor_Y0"] = np.nan
    summary["total_emissions"] = 0.0
    for year in range(1, 11):
        summary[f"emissions_factor_Y{year}"] = np.nan
        summary[f"emissions_Y{year}"] = np.nan

    ordered_cols = [
        "ISO",
        "scenario",
        *diff_columns,
        "total_person_years_saved",
        "emissions_factor_Y0",
        "total_emissions",
        *[
            col
            for year in range(1, 11)
            for col in (f"emissions_factor_Y{year}", f"emissions_Y{year}")
        ],
    ]
    return summary[ordered_cols]


def compute_individual_survival_diffs(
    df_input: pd.DataFrame,
    mortality_lookup: pd.DataFrame,
    benefit_reduction: float = 0.5,
    population_weighted: bool = True,
) -> pd.DataFrame:
    """Compute deterministic survival differences for each simulated row."""
    base = df_input[
        [
            "age",
            "Sex",
            "ISO",
            "scenario",
            "weighting",
            "bmi",
            "new_bmi",
            "adheres_to_treatment",
        ]
    ].copy()
    base["baseline_bmi_hr"] = get_raw_bmi_hazard_ratio(base["bmi"])
    base["semaglutide_bmi_hr"] = get_raw_bmi_hazard_ratio(base["new_bmi"])
    base["hr_conversion_factor"] = (
        base["semaglutide_bmi_hr"] / base["baseline_bmi_hr"] - 1
    )

    mortality_map = mortality_lookup.set_index(["ISO", "Age", "Sex"])["mortality_rate"]
    p_bl = np.ones(len(base), dtype=float)
    p_sg = np.ones(len(base), dtype=float)

    diff_cols = {"diff_Y0": np.zeros(len(base), dtype=float)}
    for year in range(1, 11):
        current_age = base["age"] + year
        lookup_frame = base[["ISO", "Sex"]].assign(current_age=current_age)
        mx = pd.merge(
            lookup_frame,
            mortality_map,
            left_on=["ISO", "current_age", "Sex"],
            right_index=True,
            how="left",
        )["mortality_rate"].fillna(0).to_numpy(dtype=float)

        benefit_mask = current_age.to_numpy() < 75
        sg_mx = np.where(
            benefit_mask,
            mx * (1 + base["hr_conversion_factor"].to_numpy()),
            mx * (1 + base["hr_conversion_factor"].to_numpy() * benefit_reduction),
        )
        sg_mx = np.clip(sg_mx, 0, None)

        p_bl *= np.exp(-mx)
        p_sg *= np.exp(-sg_mx)

        diff = p_sg - p_bl
        if population_weighted:
            diff = diff * base["weighting"].to_numpy()
        diff_cols[f"diff_Y{year}"] = diff

    diffs = pd.DataFrame(diff_cols)
    return pd.concat([base.reset_index(drop=True), diffs], axis=1)


def save_comparison(new_output: pd.DataFrame) -> None:
    """Compare deterministic person-years with the previous saved output."""
    if not PREVIOUS_OUTPUT_FILE.exists():
        return
    previous = pd.read_csv(PREVIOUS_OUTPUT_FILE)
    comparison = previous[
        ["ISO", "scenario", "total_person_years_saved"]
    ].merge(
        new_output[["ISO", "scenario", "total_person_years_saved"]],
        on=["ISO", "scenario"],
        suffixes=("_previous", "_deterministic"),
    )
    comparison["person_years_change_pct"] = (
        comparison["total_person_years_saved_deterministic"]
        / comparison["total_person_years_saved_previous"]
        - 1
    ) * 100
    comparison.to_csv(COMPARISON_FILE, index=False)


def main() -> None:
    print("Running deterministic mortality model...")
    if OUTPUT_FILE.exists() and not PREVIOUS_OUTPUT_FILE.exists():
        pd.read_csv(OUTPUT_FILE).to_csv(PREVIOUS_OUTPUT_FILE, index=False)
        print(f"Saved previous mortality output backup: {PREVIOUS_OUTPUT_FILE}")

    sim, mortality = load_inputs()
    deterministic = run_deterministic_mortality(sim, mortality)
    deterministic.to_csv(OUTPUT_FILE, index=False)
    save_comparison(deterministic)

    print(f"Updated mortality output: {OUTPUT_FILE}")
    print(f"Comparison output: {COMPARISON_FILE}")
    print(
        "Global person-years saved (max uptake): "
        f"{deterministic[deterministic['scenario'] == 'max_uptake']['total_person_years_saved'].sum():,.0f}"
    )
    print(
        "Global person-years saved (moderate uptake): "
        f"{deterministic[deterministic['scenario'] == 'mod_uptake']['total_person_years_saved'].sum():,.0f}"
    )


if __name__ == "__main__":
    main()
