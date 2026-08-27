"""
Deterministic expected-value mortality model.

This replaces the headline Monte Carlo survival calculation with its
deterministic expectation. Each simulated individual carries baseline and
semaglutide survival probabilities over a 10-year horizon. Human Life-Table
``Mx`` rates are converted to one-year death probabilities using:

    q = 1 - exp(-Mx)

Mortality source
----------------
The rates come from ``final_df_imputed.pkl``'s own ``mortality_rate`` column,
which covers all 63 modelled countries. They are **not** read from
``mortality2.rds``.

``mortality2.rds`` is the raw 41-country Human Life-Table extract — an *input*
to the imputation, not its output. This module used to look rates up from it
while taking the population from the pickle, which reached past the imputation
step to its own source: the 22 countries absent from the HLD extract fell through
the ``.fillna(0)`` below to a zero hazard, i.e. immortality, and were written out
with ``diff_Y*`` identically zero. The pickle's column is the imputed version the
manuscript methods describe (regional median by age and sex, then global median
for that age-sex cohort, then a 0.00001 floor), produced by cell 5 of
``Mortality Model.ipynb``.

Outputs are **person-years only**:

  mortality model total emissions.csv
  data_result/deterministic_mortality_comparison.csv

Emissions are computed downstream. ``data_visualization.consumption_ghg`` reads
the ``diff_Y*`` columns from this file, attaches OECD demand-based
final-consumption factors, and writes
``mortality model total emissions_oecd.csv`` — which is what every analysis
script reads. This file no longer carries emissions columns of its own; the ones
it used to hold were duplicates of that OECD output.

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

import math

import numpy as np
import pandas as pd

from .pipeline import POPULATION_PKL, ROOT, output_path


# Named once, in pipeline.py, beside the .rds it is derived from. See the
# comment there for why the two artefacts of a run live in one place.
SIMULATION_FILE = POPULATION_PKL
OUTPUT_FILE = ROOT / "mortality model total emissions.csv"
PREVIOUS_OUTPUT_FILE = ROOT / "mortality model total emissions_pre_deterministic_backup.csv"
COMPARISON_FILE = output_path("deterministic_mortality_comparison.csv")


# --- Continuous hazard within the top band ----------------------------------
#
# THE DEFECT THIS FIXES. The ladder assigned a flat 2.76 to all BMI >= 40 with
# no upper bound, so a bounded published estimate (top category 40.0-59.9) was
# applied to an unbounded bin, and -- because the bin had no FLOOR -- weight
# loss inside it produced a hazard ratio of exactly 1.0 between baseline and
# treatment. About 36% of top-band adherers stay above 40 and were credited
# with zero modelled survival benefit, in the range where the real gradient is
# steepest.
#
# The converse error is the larger one and is the reason for the change: a flat
# bin gives everyone who CROSSES out of it the whole band's mean hazard as
# their baseline, and crossers come disproportionately from 40-45, whose true
# hazard is well below the band mean. Their modelled benefit was systematically
# overstated.
#
# The 2.76 anchor is Di Angelantonio et al. 2016, Lancet 388:776-786 (the
# Global BMI Mortality Collaboration), obesity grade 3, BMI 40.0 to <60.0.
# The whole ladder below 40 is from the same source. Two bin definitions
# differ from it and both are inert, measured: our 20-25 reference merges
# GBMC's 20-22.5 and 22.5-25 (both 1.00), and our bottom bin is unbounded
# below where GBMC's is 15-18.5. Nobody below BMI 27 is eligible -- the
# lowest BMI of any adherer is 27.0002 -- so for all 965,012 sub-27 rows
# the treated and baseline hazard ratios are the same value and the ratio,
# which is the only thing this module consumes, is exactly 1.
#
# That the anchor is an average over 40.0-60.0 is the SOURCE'S OWN
# interval, not an assumption this normalisation makes. K therefore
# averages hr_top over exactly the range 2.76 was estimated on.
#
# Kitahara et al. 2014, PLOS Medicine, Table 4: HR 1.40 per 5 kg/m^2 within BMI
# 40.0-59.9. K is the composition-weighted mean of 1.4^((b-40)/5) over the top
# band, using the same class III participant composition the BMI construction
# imposes in Data_Cleaning9.8.R. Normalising by K PRESERVES the 2.76 anchor, so
# the population mean baseline hazard in the top band is unchanged and total
# baseline deaths barely move; what changes is the treatment contrast.
#
# Only the RATIO semaglutide_bmi_hr / baseline_bmi_hr enters this module's
# output. The level never does and there is no calibration constant anywhere in
# the conversion, so the aggregate treated-versus-baseline figure is an output,
# not a target. HR_TOP_ANCHOR cancels entirely for anyone whose baseline and
# treated BMI both sit above 40 -- their ratio is just 1.4^(-0.118*bmi/5). What
# K buys is the size of the step at the 40 boundary, and therefore the benefit
# credited to crossers.
#
# CLASS3_N is necessarily duplicated across this file, Mortality_model2.R and
# Data_Cleaning9.8.R (three files, two runtimes). The assertion below is what
# stops them drifting: edit any copy and K moves and this fails at import.
CLASS3_N = np.array([6803.0, 1978.0, 627.0, 156.0])  # participants, not deaths
CLASS3_SHARE = CLASS3_N / CLASS3_N.sum()
HR_TOP_BASE = 2.76
HR_PER_5 = 1.40
# Under a piecewise-linear CDF each sub-band is uniform, so the mean of
# 1.4^((b-40)/5) over a five-unit segment starting at 40 + 5j is
# 1.4^j * (1.4 - 1) / ln(1.4).
HR_TOP_K = float(
    (CLASS3_SHARE
     * ((HR_PER_5 - 1.0) / math.log(HR_PER_5))
     * HR_PER_5 ** np.arange(4)).sum()
)
HR_TOP_ANCHOR = HR_TOP_BASE / HR_TOP_K  # 1.977378
assert abs(HR_TOP_K - 1.395788) < 1e-6, HR_TOP_K
assert abs(HR_TOP_ANCHOR - 1.977378) < 1e-6, HR_TOP_ANCHOR


def hr_top(bmi) -> np.ndarray:
    """Continuous hazard ratio within BMI 40-60, anchored to preserve 2.76.

    The clip at 60 is the terminal knot of the BMI construction. It never binds
    on ``bmi`` -- the knot vector guarantees that -- but it DOES bind on
    ``new_bmi`` for a handful of rows, because negative draws of
    ``individual_effect`` push them above 60. Do not assert that never happens;
    the rate is seed-dependent.
    """
    b = np.asarray(bmi, dtype=float)
    return HR_TOP_ANCHOR * HR_PER_5 ** ((np.minimum(b, 60.0) - 40.0) / 5.0)


def get_raw_bmi_hazard_ratio(bmi: pd.Series) -> np.ndarray:
    """Map BMI to published all-cause mortality hazard-ratio categories.

    Bins below 40 are unchanged step values. Above 40 the ladder is continuous;
    see the block comment above. Must stay in step with ``bmi_hazard_ratio()``
    in ``legacy/R_scripts/Mortality_model2.R``; ``diagnostics/ladder_diff.py``
    checks that they do.
    """
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
                                np.where(bmi >= 40.0, hr_top(bmi), np.nan),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def load_inputs() -> pd.DataFrame:
    """Load the simulated population, which carries its own mortality rates."""
    return pd.read_pickle(SIMULATION_FILE)


# Ages the modelled population spans, and therefore the range the rate lookup
# must cover with no holes. Adherers top out at 74, so a horizon beyond 15 years
# would walk them past 89 and off the end of this table.
LOOKUP_AGE_MIN = 18
LOOKUP_AGE_MAX = 89


def build_mortality_map(df_input: pd.DataFrame) -> pd.Series:
    """``(ISO, age, Sex) -> mortality_rate``, built from the simulation frame.

    The join key is lowercase ``age``. The frame also carries a capital ``Age``,
    which is null on 42.86% of rows: it is the right-hand key left behind by the
    notebook's merge against the 41-country HLD extract, so it is null on exactly
    the countries that extract lacks. Keying on it would silently drop them.

    Coverage is asserted rather than assumed -- a hole here becomes a zero rate
    downstream, which is indistinguishable from immortality.
    """
    lookup = df_input[["ISO", "age", "Sex", "mortality_rate"]].drop_duplicates()
    key = ["ISO", "age", "Sex"]
    dupes = lookup.duplicated(subset=key).sum()
    if dupes:
        raise ValueError(
            f"mortality_rate is not single-valued: {dupes} (ISO, age, Sex) keys "
            "carry more than one rate."
        )

    isos = df_input["ISO"].unique()
    sexes = df_input["Sex"].unique()
    ages = range(LOOKUP_AGE_MIN, LOOKUP_AGE_MAX + 1)
    expected = len(isos) * len(sexes) * len(ages)
    have = set(map(tuple, lookup[key].to_numpy()))
    missing = [
        (i, float(a), s) for i in isos for a in ages for s in sexes
        if (i, float(a), s) not in have
    ]
    if missing:
        raise ValueError(
            f"mortality_rate lookup has {len(missing)} holes over "
            f"{len(isos)} ISO x ages {LOOKUP_AGE_MIN}-{LOOKUP_AGE_MAX} x "
            f"{len(sexes)} sexes ({expected} cells). First few: {missing[:5]}"
        )
    return lookup.set_index(key)["mortality_rate"]


def run_deterministic_mortality(
    df_input: pd.DataFrame,
    *,
    benefit_reduction: float = 0.5,
    population_weighted: bool = True,
) -> pd.DataFrame:
    """Compute expected additional survivor person-years by country/scenario."""
    individual = compute_individual_survival_diffs(
        df_input,
        benefit_reduction=benefit_reduction,
        population_weighted=population_weighted,
    )
    diff_columns = [f"diff_Y{year}" for year in range(0, 11)]
    summary = individual.groupby(["ISO", "scenario"], as_index=False)[diff_columns].sum()
    summary["total_person_years_saved"] = summary[diff_columns].sum(axis=1)

    # Person-years only. Emissions are computed downstream by
    # consumption_ghg.py, which attaches OECD factors and writes
    # 'mortality model total emissions_oecd.csv'. This file previously carried
    # placeholder emissions columns to preserve a legacy schema; they were
    # duplicates of the OECD output that nothing read, and are no longer written.
    ordered_cols = ["ISO", "scenario", *diff_columns, "total_person_years_saved"]
    return summary[ordered_cols]


def compute_individual_survival_diffs(
    df_input: pd.DataFrame,
    *,
    benefit_reduction: float = 0.5,
    population_weighted: bool = True,
    horizon: int = 10,
    survival_columns: bool = False,
    missing_columns: bool = False,
    extra_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Compute deterministic survival differences for each simulated row.

    The mortality lookup is built from ``df_input`` itself. It used to be a second
    positional parameter, which is why everything after it is keyword-only now: a
    stale ``f(sim, mortality)`` call would otherwise bind the old lookup frame to
    ``benefit_reduction`` and run silently. It raises ``TypeError`` instead.

    ``horizon``, ``survival_columns`` and ``extra_columns`` exist so the
    survival-weighting of the food-side demand shock can reuse this loop rather
    than keep a second copy of it. All three default to the original behaviour:
    ``horizon=10`` produces exactly the ``diff_Y0``-``diff_Y10`` the headline
    person-years output is built from.

    ``survival_columns`` additionally returns the raw (unweighted) treatment- and
    baseline-world survival probabilities as ``p_sg_Y{t}`` / ``p_bl_Y{t}``.
    ``extra_columns`` carries further ``df_input`` columns through untouched.

    The per-year count of rows whose (ISO, age+t, Sex) mortality lookup missed is
    recorded on ``.attrs["missing_lookups"]``, and ``missing_columns`` returns the
    per-row boolean masks as ``mx_missing_Y{t}`` columns. A miss is filled with a
    zero rate below, which is indistinguishable from immortality, so the count is
    the coverage check on any horizon extension -- it must be read, not assumed.

    The masks are columns rather than another ``.attrs`` entry on purpose. pandas
    compares ``attrs`` with ``==`` when it finalises a ``concat``, so an
    array-valued attr raises "truth value of an array is ambiguous" for any caller
    that concatenates a frame derived from this one. ``missing_lookups`` is a dict
    of ints and compares cleanly; arrays must not go in beside it.
    """
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
            *extra_columns,
        ]
    ].copy()
    base["baseline_bmi_hr"] = get_raw_bmi_hazard_ratio(base["bmi"])
    base["semaglutide_bmi_hr"] = get_raw_bmi_hazard_ratio(base["new_bmi"])
    base["hr_conversion_factor"] = (
        base["semaglutide_bmi_hr"] / base["baseline_bmi_hr"] - 1
    )

    mortality_map = build_mortality_map(df_input)
    treated = base["adheres_to_treatment"].to_numpy(dtype=bool)
    p_bl = np.ones(len(base), dtype=float)
    p_sg = np.ones(len(base), dtype=float)

    diff_cols = {"diff_Y0": np.zeros(len(base), dtype=float)}
    missing_lookups: dict[int, int] = {}
    for year in range(1, horizon + 1):
        current_age = base["age"] + year
        lookup_frame = base[["ISO", "Sex"]].assign(current_age=current_age)
        raw_mx = pd.merge(
            lookup_frame,
            mortality_map,
            left_on=["ISO", "current_age", "Sex"],
            right_index=True,
            how="left",
        )["mortality_rate"]
        missing = raw_mx.isna().to_numpy()
        missing_lookups[year] = int(missing.sum())
        if missing_columns:
            diff_cols[f"mx_missing_Y{year}"] = missing

        # fillna(0) is retained: non-adherent rows are walked past age 89 at
        # longer horizons and a zero rate there is harmless, because their
        # hazard ratio is unchanged so p_sg == p_bl and the difference is zero
        # either way. On a TREATED row it is not harmless -- a zero rate makes
        # that row immortal in both worlds and silently contributes nothing,
        # which is exactly how 27 countries came to be written out with
        # diff_Y* identically zero. So the fill is guarded where it can do
        # damage rather than trusted everywhere.
        damaging = missing & treated
        if damaging.any():
            offenders = (
                base.loc[damaging, ["ISO", "age", "Sex"]]
                .assign(lookup_age=lambda d: d["age"] + year)
                .drop_duplicates(["ISO", "lookup_age", "Sex"])
            )
            raise KeyError(
                f"Year {year}: {int(damaging.sum())} treated rows have no "
                f"mortality rate for their (ISO, age+{year}, Sex). Filling zero "
                "would make them immortal. Missing keys "
                f"({len(offenders)} distinct): "
                f"{offenders.head(10).to_dict('records')}"
            )
        mx = raw_mx.fillna(0).to_numpy(dtype=float)

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
        if survival_columns:
            diff_cols[f"p_sg_Y{year}"] = p_sg.copy()
            diff_cols[f"p_bl_Y{year}"] = p_bl.copy()

    diffs = pd.DataFrame(diff_cols)
    out = pd.concat([base.reset_index(drop=True), diffs], axis=1)
    out.attrs["missing_lookups"] = missing_lookups
    return out


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

    sim = load_inputs()
    deterministic = run_deterministic_mortality(sim)
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
