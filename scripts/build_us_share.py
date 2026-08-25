"""US share of year-1 food-emission savings, on the Supplementary Figure 1 basis.

Answers one co-author question: what fraction of the year-1 food-emission
saving comes from the United States alone. Quoted in the main text beside
"Most emissions savings are concentrated in the United States."

BASIS -- fixed, and deliberately not parameterised.

  scenario          max_uptake (mod_uptake also emitted)
  ci_file           carbon_intensity.csv (mean)
  diet_scenario     None
  survival_weighted False
  pharmaceuticals   EXCLUDED -- the drug step is never called
  horizon           year 1 only
  sample            every country with computable food savings; must be 53

Two of those need their reasons recorded, because both look like omissions.

``survival_weighted=False``. Supp Fig 1's caption says "mortality effects
excluded", and it was written before the food-savings term was survival
weighted at all. Read at face value the caption excludes the pi weighting as
well as the survivor-emissions term, so False is the stated basis.
``--diagnostic`` measures whether that reading matters; it does not choose it.

The 53-country sample, not the 40-country one. 40 exists only because a
food:survivor ratio needs an OECD per-capita factor, which is a mortality-side
constraint. Nothing on this figure's numerator touches survivor emissions, so
imposing it here would drop 13 countries from a denominator for a reason that
does not apply to it -- and would inflate the US share.

Pharmaceuticals are out because Supp Fig 1 is a food-group breakdown and the
drug is not a food group; the figure is gross by construction.

Also emits ``baseline_food_emissions_mt`` -- the baseline (pre-treatment)
national food emissions of the same 53-country sample, so the manuscript can
quote year-1 savings as a share of baseline food-system emissions. It is the sum
over country x food group of ``initial_eql_quantity * carbon_intensity_t`` (the
pipeline's ``pn_food_footprint``, reused verbatim), on pre-shock tonnage, so it
is delta-independent and independent of all three mortality channels. Emitting
it here rather than in a separate script pairs it with ``total_mt`` by
construction: same basis, same country set, one pipeline call. See
``_baseline_food_emissions`` for the two gates it enforces.

Writes:
  data_result/us_share_year1.csv        (read by scripts/build_manuscript_numbers.R)
  data_result/us_share_diagnostic.txt   (--diagnostic only)

Usage:
    python scripts/build_us_share.py
    python scripts/build_us_share.py --diagnostic

ASCII only.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_visualization.pipeline import compute_food_savings, output_path

SCENARIOS = ("max_uptake", "mod_uptake")
EXPECTED_N_COUNTRIES = 53
TARGET_ISO = "USA"

# Same input-by-input probe pipeline._report_unsolved uses. Only consulted when
# the country-count gate fails, to say WHICH input each dropped country lacks
# rather than just that it dropped.
MISSING_INPUT_CHECKS = {
    "price": "price",
    "FAOSTAT tonnage": "initial_eql_quantity",
    "carbon intensity": "carbon_intensity_t",
    "supply elasticity": "elasticity_supply",
    "demand elasticity": "elasticity_demand",
    "demand shock": "expected_demand_reduction_percent",
}


class GateFailure(RuntimeError):
    """A declared verification gate did not hold. Reported, never worked around."""


def _missing_inputs_for(result_df: pd.DataFrame, iso: str) -> str:
    rows = result_df[result_df["ISO"] == iso]
    if rows.empty:
        return "no rows in result_df at all"
    missing = [
        label
        for label, col in MISSING_INPUT_CHECKS.items()
        if col not in rows.columns or rows[col].isna().all()
    ]
    return ", ".join(missing) if missing else "inputs present; solve produced NaN"


def _baseline_food_emissions(
    result_df: pd.DataFrame, scenario: str, total_mt_isos: set
) -> dict:
    """Baseline (pre-treatment) national food emissions for the total_mt sample.

    Baseline food emissions = sum over country x food group of
    ``initial_eql_quantity * carbon_intensity_t``, on the no-diet baseline. That
    is exactly the pipeline's ``pn_food_footprint`` (per ISO x scenario), built
    inside ``_survivor_food_factor`` and carried on
    ``result_df.attrs["survivor_food_factor"]``. It is REUSED verbatim, never
    reimplemented: this only selects the scenario, restricts to the country set
    that feeds ``total_mt``, enforces two gates, and sums.

    Pre-shock tonnage, so no equilibrium solve enters -- delta-independent and
    independent of all three mortality channels (pi, pi_dose, survivor
    emissions).

    Two of the baseline feature's declared gates are enforced here (both
    stop-on-failure). They are numbered per the task spec, NOT per
    ``compute_share``'s own internal gate 1-4:

      * Baseline gate 2 -- the ISO set actually summed must equal the ISO set
        feeding ``total_mt``. The symmetric difference is reported and any
        non-empty difference raises. Countries that carry baseline tonnage but
        have no price index (GUY/NRU/TWN as of writing) drop out of ``total_mt``
        and so must not be summed here; restricting to ``total_mt_isos`` is what
        excludes them, and ``carries_no_price`` establishes -- rather than
        assumes -- that they do carry tonnage.
      * Baseline gate 3 -- a country whose baseline footprint is NaN has no
        FAOSTAT tonnage on any food group (``pn_food_footprint`` uses
        ``min_count=1``, so it stays NaN rather than collapsing to a silent 0).
        Such a country is dropped and named, never handed to a skipna sum that
        would treat it as a zero contribution.

    Baseline gate 1 (bit-identity across scenarios) is checked in ``main()``,
    where both scenarios' values are in hand.
    """
    factor = result_df.attrs["survivor_food_factor"]
    scoped = factor[factor["scenario"] == scenario]

    on_set = scoped[scoped["ISO"].isin(total_mt_isos)]

    # ---- Baseline gate 3: exclude and name any NaN-footprint country; never zero it.
    nan_isos = sorted(on_set.loc[on_set["pn_food_footprint"].isna(), "ISO"])
    if nan_isos:
        raise GateFailure(
            f"[{scenario}] {len(nan_isos)} country(ies) in the total_mt set have "
            f"NaN baseline food footprint and would be silently zeroed: "
            + ", ".join(nan_isos[:10])
            + (f" (+{len(nan_isos) - 10} more)" if len(nan_isos) > 10 else "")
        )

    # Sorted by ISO so the summation order is identical across scenarios; the
    # per-ISO footprints are already bit-identical (pre-shock, delta-free), so
    # this makes the total bit-identical too -- what gate 1 checks in main().
    summed = on_set[on_set["pn_food_footprint"].notna()].sort_values("ISO")
    summed_isos = set(summed["ISO"])

    # ---- Baseline gate 2: the summed set must equal the total_mt set, exactly.
    sym_diff = sorted(summed_isos ^ set(total_mt_isos))
    if sym_diff:
        raise GateFailure(
            f"[{scenario}] baseline ISO set does not match the total_mt ISO set. "
            f"Symmetric difference has {len(sym_diff)} ISO(s): "
            + ", ".join(sym_diff[:10])
            + (f" (+{len(sym_diff) - 10} more)" if len(sym_diff) > 10 else "")
        )

    carries_no_price = sorted(
        set(scoped.loc[scoped["pn_food_footprint"].notna(), "ISO"])
        - set(total_mt_isos)
    )

    baseline_t = float(summed["pn_food_footprint"].sum())
    return {
        "baseline_mt": baseline_t / 1e6,
        "baseline_t": baseline_t,
        "summed_isos": summed_isos,
        "nan_isos": nan_isos,
        "sym_diff": sym_diff,
        "carries_no_price": carries_no_price,
    }


def compute_share(
    food_savings: pd.DataFrame, result_df: pd.DataFrame, scenario: str
) -> dict:
    """US share of the year-1 food-emission saving, with every gate enforced."""
    col = "annual_food_savings_t"
    scoped = food_savings[food_savings["scenario"] == scenario]

    # > 0 rather than notna(): the unpriced countries are NaN, and NaN > 0 is
    # False, so this drops them without a separate dropna. Any genuine zero
    # would also drop, which is the same treatment every downstream ratio in the
    # repo applies.
    valid = scoped[scoped[col] > 0]

    # ---- Gate 1: the sample is the full 53-country food-data set.
    if len(valid) != EXPECTED_N_COUNTRIES:
        dropped = sorted(set(scoped["ISO"]) - set(valid["ISO"]))
        detail = "\n".join(
            f"      {iso}: {_missing_inputs_for(result_df, iso)}" for iso in dropped
        )
        raise GateFailure(
            f"[{scenario}] expected {EXPECTED_N_COUNTRIES} countries with "
            f"computable food savings, got {len(valid)}.\n"
            f"    {len(dropped)} of {len(scoped)} scenario rows dropped out:\n"
            f"{detail}"
        )

    # ---- Gate 2: USA is present exactly once.
    usa_rows = valid[valid["ISO"] == TARGET_ISO]
    if len(usa_rows) != 1:
        raise GateFailure(
            f"[{scenario}] expected exactly 1 {TARGET_ISO} row in the valid set, "
            f"got {len(usa_rows)}."
        )

    usa_t = float(usa_rows[col].iloc[0])
    total_t = float(valid[col].sum())

    # ---- Gate 3: the reported total is the sum of the per-country values,
    # exactly. Reconstructed by a different route to the same set -- selecting
    # the scenario frame by the valid ISO list instead of by the > 0 mask -- so
    # this catches a filtering slip rather than restating the line above. Same
    # process and same code path, so no tolerance is warranted and none is given.
    reconstructed = float(scoped[scoped["ISO"].isin(set(valid["ISO"]))][col].sum())
    if reconstructed - total_t != 0.0:
        raise GateFailure(
            f"[{scenario}] per-country sum does not reproduce the reported total "
            f"exactly: reconstructed {reconstructed!r} vs total {total_t!r} "
            f"(difference {reconstructed - total_t!r})."
        )

    # Reported, NOT gated. fsum is exactly rounded while pandas sums pairwise, so
    # a last-bit disagreement here is a floating-point artefact and says nothing
    # about the model. Surfaced so it is visible rather than assumed to be zero.
    fsum_delta = math.fsum(sorted(valid[col].tolist())) - total_t

    share = usa_t / total_t

    # ---- Gate 4: the share is a genuine fraction.
    if not 0.0 < share < 1.0:
        raise GateFailure(
            f"[{scenario}] share {share!r} is not strictly between 0 and 1 "
            f"(usa {usa_t!r} / total {total_t!r})."
        )

    # Baseline (pre-treatment) national food emissions over exactly this
    # total_mt sample, so the two are paired by construction. Gates 2 and 3 are
    # enforced inside. The ISO set feeding total_mt is set(valid["ISO"]).
    baseline = _baseline_food_emissions(result_df, scenario, set(valid["ISO"]))

    return {
        "scenario": scenario,
        "usa_mt": usa_t / 1e6,
        "total_mt": total_t / 1e6,
        "share_pct": share * 100.0,
        "n_countries": len(valid),
        "fsum_delta_t": fsum_delta,
        "baseline_food_emissions_mt": baseline["baseline_mt"],
        "baseline_diag": baseline,
    }


def run_pipeline(survival_weighted: bool):
    return compute_food_savings(
        diet_scenario=None,
        ci_file="carbon_intensity.csv",
        survival_weighted=survival_weighted,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--diagnostic",
        action="store_true",
        help=(
            "additionally run the survival_weighted=True variant and write "
            "data_result/us_share_diagnostic.txt. Costs a second pipeline call."
        ),
    )
    args = ap.parse_args()

    print("US share of year-1 food-emission savings (Supp Fig 1 basis)")
    print("  survival_weighted=False, mean CI, no diet variant, drug excluded")
    print("Running pipeline (survival_weighted=False)...")
    fs_unweighted, rd_unweighted = run_pipeline(survival_weighted=False)

    reported = [compute_share(fs_unweighted, rd_unweighted, sc) for sc in SCENARIOS]

    # ---- Baseline gate 1: baseline food emissions is delta-independent
    # (pre-shock tonnage, no equilibrium solve), so it must be bit-identical
    # across the two uptake scenarios. Any nonzero difference is a stop -- not
    # rounded, not tolerated. One pipeline call produced both, so this compares
    # like with like.
    by_sc = {r["scenario"]: r for r in reported}
    b_max = by_sc["max_uptake"]["baseline_food_emissions_mt"]
    b_mod = by_sc["mod_uptake"]["baseline_food_emissions_mt"]
    if b_max != b_mod:
        raise GateFailure(
            "Baseline food emissions differ between scenarios (must be "
            f"delta-independent): max_uptake {b_max!r} vs mod_uptake {b_mod!r} "
            f"(difference {b_max - b_mod!r})."
        )

    out = pd.DataFrame(reported)[
        ["scenario", "usa_mt", "total_mt", "share_pct", "baseline_food_emissions_mt",
         "n_countries"]
    ]
    out["survival_weighted"] = False
    out["ci_file"] = "carbon_intensity.csv"
    out["diet_scenario"] = "none"
    out["includes_drug"] = False
    out_path = output_path("us_share_year1.csv")
    out.to_csv(out_path, index=False)
    print(f"\nSaved table: {out_path}")

    print("\nReported basis (survival_weighted=False):")
    for r in reported:
        print(
            f"  {r['scenario']:<11} USA {r['usa_mt']:8.3f} Mt  /  total "
            f"{r['total_mt']:8.3f} Mt  =  {r['share_pct']:6.2f}%  "
            f"(N={r['n_countries']})"
        )
        print(f"              fsum-vs-pandas delta: {r['fsum_delta_t']:.6e} t "
              f"(reported, not gated)")

    # Baseline food emissions -- printed at full float precision, not rounded.
    print("\nBaseline (pre-treatment) national food emissions, 53-country sample:")
    print(f"  delta-independent value (max_uptake == mod_uptake, gate 1 held):")
    print(f"    {b_max!r} MtCO2e")
    for r in reported:
        d = r["baseline_diag"]
        yr1_pct = r["total_mt"] / r["baseline_food_emissions_mt"] * 100.0
        print(
            f"  {r['scenario']:<11} baseline {r['baseline_food_emissions_mt']!r} Mt  "
            f"(summed {len(d['summed_isos'])} ISO; gate2 sym-diff {len(d['sym_diff'])}; "
            f"gate3 NaN-excluded {len(d['nan_isos'])})"
        )
        print(f"              year-1 savings = {yr1_pct:.4f}% of baseline")
    probe = by_sc["max_uptake"]["baseline_diag"]["carries_no_price"]
    print(
        f"  carry baseline tonnage but no price index -> in neither total_mt nor "
        f"baseline: {len(probe)} ISO [{', '.join(probe[:10])}]"
    )

    if not args.diagnostic:
        return

    print("\nRunning pipeline (survival_weighted=True) for the diagnostic...")
    fs_weighted, rd_weighted = run_pipeline(survival_weighted=True)
    weighted = [compute_share(fs_weighted, rd_weighted, sc) for sc in SCENARIOS]

    lines = [
        "US share of year-1 food-emission savings -- survival-weighting diagnostic",
        "",
        "QUESTION. Supp Fig 1's caption says 'mortality effects excluded'. That",
        "caption predates the survival weighting of the food-savings term, so it",
        "has two readings: exclude only the survivor-emissions term, or exclude",
        "the pi weighting as well. This measures whether the two readings give",
        "materially different US shares, so the caption can be made unambiguous.",
        "",
        "It does NOT change the reported basis. The reported figure stays on",
        "survival_weighted=False, which is the caption read at face value.",
        "",
        "Both runs: mean CI, diet_scenario=None, pharmaceuticals excluded,",
        "year-1 only, all countries with computable food savings.",
        "",
        f"{'scenario':<12} {'basis':<26} {'USA Mt':>10} {'total Mt':>10} "
        f"{'share %':>9} {'N':>4}",
    ]
    for sc in SCENARIOS:
        u = next(r for r in reported if r["scenario"] == sc)
        w = next(r for r in weighted if r["scenario"] == sc)
        for label, r in (
            ("survival_weighted=False", u),
            ("survival_weighted=True", w),
        ):
            lines.append(
                f"{sc:<12} {label:<26} {r['usa_mt']:10.4f} {r['total_mt']:10.4f} "
                f"{r['share_pct']:9.4f} {r['n_countries']:4d}"
            )
        diff_pp = w["share_pct"] - u["share_pct"]
        lines.append(
            f"{sc:<12} {'DIFFERENCE (True - False)':<26} "
            f"{w['usa_mt'] - u['usa_mt']:10.4f} "
            f"{w['total_mt'] - u['total_mt']:10.4f} {diff_pp:9.4f} "
            f"{w['n_countries'] - u['n_countries']:4d}"
        )
        lines.append("")

    diag_path = output_path("us_share_diagnostic.txt")
    diag_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved diagnostic: {diag_path}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
