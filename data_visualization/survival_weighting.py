"""Survival weighting for the food-side demand shock.

The food model's demand shock is built from the whole treated cohort as if all of
it were alive in every year. It is not: some treated patients die anyway, and a
dead patient eats nothing in either world, so their food saving must not keep
being counted.

The exact difference in national food energy between the treated and untreated
worlds in year *t*, with ``p_sg`` and ``p_bl`` the treatment- and baseline-world
survival probabilities, splits into two terms:

    Delta(t) = sum w*p_sg(t)*(treatment_eer - eer)  +  sum w*(p_sg(t) - p_bl(t))*eer

with term 1 the diet effect among treatment-world survivors, and term 2 the
additional survivors.

**Term 2 is not this module's business.** It is the additional-survivor
population, priced downstream by ``pipeline._survivor_food_factor`` on baseline
``eer``, and it is already correct. This module concerns term 1, which is a
different group of people: patients who were treated, saved food while alive, and
then died. Do not "unify" the two.

The food side currently computes term 1 with no survival probability at all --
equivalent to ``p_sg == 1`` for everyone in every year. The missing scalar is

    pi(t) = sum w*p_sg(t)*(eer - treatment_eer)  /  sum w*(eer - treatment_eer)

a difference-weighted mean of treatment-world survival, with ``pi(0) == 1``
falling each year, and the corrected shock is ``delta(t) = delta * pi(t)``. The
denominator of ``delta`` is deliberately *not* survival-weighted: it must stay on
the 2022 baseline energy pool, which is the basis of the observed FAOSTAT tonnage
the shock is applied to.

``eer_diff`` is ``eer - treatment_eer``, a positive reduction, and is non-zero on
exactly the treated-adherer rows -- so pi averages over treated adherers only,
without needing to filter for them. Note it is not element-wise positive: about
2.5% of adherers draw a negative weight-loss effect, so pi is a ratio of sums
with a few negative weights rather than a convex average, and carries no a priori
[0, 1] bound.

Horizon: the table is built to 15 years, which is the last year with complete
mortality coverage for treated patients (adherers span ages 18-74 and the rate
lookup ends at 89). The food model itself still runs 10.

Usage:
    python -m data_visualization.survival_weighting
"""

from __future__ import annotations

import sys

import pandas as pd

from .deterministic_mortality import compute_individual_survival_diffs, load_inputs
from .pipeline import output_path

# Last year with complete mortality coverage for treated patients. See the
# age-89 ceiling note in CHANGES.md before raising this: it needs more mortality
# data, not a code change.
PI_HORIZON = 15

OUTPUT_FILE = "food_shock_survival_weight.csv"


def build_food_shock_survival_weight(horizon: int = PI_HORIZON) -> pd.DataFrame:
    """Long-format ``(ISO, scenario, year) -> pi, pi_dose`` survival weights.

    Two weights, because two different quantities are being scaled and they do
    not share a weighting:

    ``pi``      weights survival by ``w * eer_diff``. It scales the FOOD shock,
                where a patient counts in proportion to how much their intake
                fell.
    ``pi_dose`` weights survival by ``w`` alone, over treated adherers. It scales
                the PHARMACEUTICAL term, where a surviving patient is dosed once
                regardless of how much their intake fell.

    Using ``pi`` for the drug term would silently weight dosing by appetite
    reduction. The two are close but they are not the same number, and which one
    is correct depends on what is being counted.

    Returns
    -------
    DataFrame with columns ISO, scenario, year, pi, pi_dose.
    """
    sim = load_inputs()

    # The full frame is passed, not just the treated rows: the mortality lookup is
    # built from df_input and its coverage assertion spans ages 18-89, which a
    # treated-only subset (18-74) would fail. Untreated rows carry eer_diff == 0
    # and so contribute exactly 0.0 to both sums -- adding exact zeros does not
    # perturb a running total, so the result is identical either way.
    ind = compute_individual_survival_diffs(
        sim,
        horizon=horizon,
        survival_columns=True,
        extra_columns=("eer_diff",),
        population_weighted=False,
    )
    ind["w_diff"] = ind["weighting"] * ind["eer_diff"]
    # Dosing weight: headcount among treated adherers. eer_diff is non-zero on
    # exactly those rows, so the same mask defines both populations.
    ind["w_dose"] = ind["weighting"].where(ind["eer_diff"] != 0, 0.0)

    key = ["ISO", "scenario"]
    denom = ind.groupby(key, observed=True)["w_diff"].sum()
    denom_dose = ind.groupby(key, observed=True)["w_dose"].sum()
    for name, den in (("pi", denom), ("pi_dose", denom_dose)):
        if (den == 0).any():
            raise ValueError(
                f"{name} is undefined for {den.index[den == 0].tolist()}: no "
                "treated adherers, so the denominator is zero."
            )

    frames = []
    for year in range(1, horizon + 1):
        ind["_num"] = ind["w_diff"] * ind[f"p_sg_Y{year}"]
        ind["_num_dose"] = ind["w_dose"] * ind[f"p_sg_Y{year}"]
        g = ind.groupby(key, observed=True)[["_num", "_num_dose"]].sum()
        frames.append(
            pd.DataFrame({
                "pi": g["_num"] / denom,
                "pi_dose": g["_num_dose"] / denom_dose,
            }).reset_index().assign(year=year)
        )

    out = pd.concat(frames, ignore_index=True)[
        ["ISO", "scenario", "year", "pi", "pi_dose"]
    ].sort_values(["ISO", "scenario", "year"]).reset_index(drop=True)
    out.attrs.clear()
    return out


def countries_with_donor_life_table(donor: str = "ISR") -> list[str]:
    """ISO codes whose imputed mortality schedule is identical to ``donor``'s.

    The imputation in ``Mortality Model.ipynb`` fills a missing country from the
    median of its UN region. Where that region contains exactly one Human
    Life-Table country, the median *is* that country, so the recipient's life
    table is literally the donor's rather than a blend. Those are the countries
    whose results rest on a single-country proxy.

    Derived from the pickle, not listed. A hardcoded set would be a claim about
    the imputation that nothing keeps true: the equivalent list for the *region*
    went stale the moment the mortality source changed, and the whole point of
    this function is that the criterion is checkable against the data it
    describes. Re-derives itself if ``final_df_imputed.pkl`` is ever rebuilt.

    Note this is a stricter and more honest criterion than "in the donor's
    region": it catches exactly the countries carrying a copied table and no
    others, without anyone having to maintain a region mapping.
    """
    sim = load_inputs()
    key = ["ISO", "age", "Sex"]
    lut = sim[key + ["mortality_rate"]].drop_duplicates(key).set_index(key)[
        "mortality_rate"
    ]
    if donor not in set(lut.index.get_level_values("ISO")):
        raise KeyError(f"Donor {donor!r} is not in the simulation's ISO set.")
    ref = lut.xs(donor, level="ISO")
    out = []
    for iso in sorted(set(lut.index.get_level_values("ISO"))):
        if iso == donor:
            continue
        other = lut.xs(iso, level="ISO")
        common = ref.index.intersection(other.index)
        if len(common) == len(ref) and bool((ref.loc[common] == other.loc[common]).all()):
            out.append(iso)
    return out


def load_food_shock_survival_weight(
    filename: str = OUTPUT_FILE, horizon: int = 10, column: str = "pi"
) -> pd.DataFrame:
    """Read the committed weight table, wide by year: index (ISO, scenario).

    The food side reads this artefact rather than recomputing survival, so
    ``pipeline`` never has to open mortality data. ``column`` selects ``pi``
    (food shock) or ``pi_dose`` (pharmaceutical term) -- see
    ``build_food_shock_survival_weight`` for why they differ.
    """
    path = output_path(filename)
    if not path.is_file():
        raise FileNotFoundError(
            f"Survival-weight table not found:\n  {path}\n"
            "Build it with: python -m data_visualization.survival_weighting"
        )
    # float_precision='round_trip' is required, not tidiness. pandas defaults to
    # the fast xstrtod converter, which parses a small fraction of these cells one
    # ULP off an exact strtod -- measured at 721 of 1,890 on this table. pi
    # multiplies every food-savings number, so a 1-ULP wobble in the parse would
    # propagate into every downstream figure and make a bit-for-bit comparison
    # against a re-read of the same file impossible.
    pi = pd.read_csv(path, float_precision="round_trip")
    if column not in pi.columns:
        raise KeyError(f"{path.name} has no column {column!r}; has {list(pi.columns)}")
    wide = pi.pivot(index=["ISO", "scenario"], columns="year", values=column)
    missing = [y for y in range(1, horizon + 1) if y not in wide.columns]
    if missing:
        raise ValueError(
            f"{path.name} covers years {sorted(wide.columns)}; "
            f"years {missing} are needed for a {horizon}-year horizon."
        )
    return wide[list(range(1, horizon + 1))]


def main() -> None:
    out = build_food_shock_survival_weight()
    path = output_path(OUTPUT_FILE)
    out.to_csv(path, index=False)
    print(f"Survival weight pi: {path}  ({len(out)} rows)")
    for scen in sorted(out["scenario"].unique()):
        s = out[out["scenario"] == scen]
        print(f"  {scen}: {s['ISO'].nunique()} ISO")
        for col in ("pi", "pi_dose"):
            bits = []
            for y in (1, 10, PI_HORIZON):
                v = s.loc[s["year"] == y, col]
                bits.append(f"Y{y} {v.min():.6f}-{v.max():.6f}")
            print(f"    {col:8s} " + "   ".join(bits))
    gap = (out["pi"] - out["pi_dose"]).abs()
    print(f"  |pi - pi_dose|: max {gap.max():.6e}, mean {gap.mean():.6e}")


if __name__ == "__main__":
    # Redirected stdout on Windows falls back to cp1252, which cannot encode the
    # non-ASCII this script prints.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    main()
