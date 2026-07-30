"""
Manuscript survivor numbers from the authoritative deterministic mortality path.

This reports the concise X/Y-style quantities requested for manuscript text:

  - average BMI-driven hazard-ratio reduction among treated users
  - starting treated users
  - expected additional survivors alive at year 10
  - cumulative additional survivor person-years over 10 years

It shares ``deterministic_mortality``'s survival machinery and therefore its
mortality source: ``final_df_imputed.pkl``'s own imputed ``mortality_rate``
column, covering all 63 countries. The two must not diverge on that choice or
the manuscript numbers stop describing the headline output.

Usage:
    python -m data_visualization.survivor_manuscript_numbers
"""

from __future__ import annotations

import pandas as pd

from .deterministic_mortality import compute_individual_survival_diffs, load_inputs
from .pipeline import output_path


SUMMARY_FILE = output_path("survivor_manuscript_numbers.csv")
TOP_COUNTRIES_FILE = output_path("survivor_manuscript_top_countries.csv")


def build_manuscript_numbers() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute scenario summary and top-country manuscript survivor numbers."""
    sim = load_inputs()
    individual = compute_individual_survival_diffs(
        sim,
        population_weighted=True,
    )
    diff_cols = [f"diff_Y{year}" for year in range(1, 11)]

    rows = []
    top_rows = []
    for scenario, s in individual.groupby("scenario", sort=False):
        treated = s[s["adheres_to_treatment"] == True]
        weights = treated["weighting"].to_numpy()
        avg_hr_reduction = (
            1 - treated["semaglutide_bmi_hr"] / treated["baseline_bmi_hr"]
        )

        rows.append(
            {
                "scenario": scenario,
                "avg_hr_reduction_pct": (avg_hr_reduction * weights).sum()
                / weights.sum()
                * 100,
                "treated_users": weights.sum(),
                "extra_survivors_y10": s["diff_Y10"].sum(),
                "total_person_years_saved": s[diff_cols].sum(axis=1).sum(),
            }
        )

        top = (
            s.groupby("ISO", as_index=False)["diff_Y10"]
            .sum()
            .sort_values("diff_Y10", ascending=False)
            .head(5)
        )
        top["scenario"] = scenario
        top_rows.append(top[["scenario", "ISO", "diff_Y10"]])

    summary = pd.DataFrame(rows)
    top_countries = pd.concat(top_rows, ignore_index=True).rename(
        columns={"diff_Y10": "extra_survivors_y10"}
    )
    return summary, top_countries


def main() -> None:
    summary, top_countries = build_manuscript_numbers()
    summary.to_csv(SUMMARY_FILE, index=False)
    top_countries.to_csv(TOP_COUNTRIES_FILE, index=False)

    print("Manuscript survivor numbers")
    print(
        f"{'scenario':<12}{'avg HR reduction':>18}{'treated users (Y)':>22}"
        f"{'extra survivors Y10 (X)':>26}{'person-years saved':>24}"
    )
    for row in summary.itertuples(index=False):
        print(
            f"{row.scenario:<12}"
            f"{row.avg_hr_reduction_pct:>16.1f}%"
            f"{row.treated_users / 1e6:>19.1f} M"
            f"{row.extra_survivors_y10:>26,.0f}"
            f"{row.total_person_years_saved:>24,.0f}"
        )

    max_top = top_countries[top_countries["scenario"] == "max_uptake"]
    print(
        "Top-5 max-uptake countries (extra survivors Y10): "
        f"{dict(zip(max_top['ISO'], max_top['extra_survivors_y10'].round().astype(int)))}"
    )
    print(f"Summary output: {SUMMARY_FILE}")
    print(f"Top countries output: {TOP_COUNTRIES_FILE}")


if __name__ == "__main__":
    main()
