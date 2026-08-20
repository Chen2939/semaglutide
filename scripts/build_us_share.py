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

    return {
        "scenario": scenario,
        "usa_mt": usa_t / 1e6,
        "total_mt": total_t / 1e6,
        "share_pct": share * 100.0,
        "n_countries": len(valid),
        "fsum_delta_t": fsum_delta,
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

    out = pd.DataFrame(reported)[
        ["scenario", "usa_mt", "total_mt", "share_pct", "n_countries"]
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
