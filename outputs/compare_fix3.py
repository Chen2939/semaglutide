"""
Side-by-side verification of fix #3 (all-ages EER demand-shock denominator).

Runs the baseline food pipeline twice from a SINGLE process, on the committed
canonical CI (carbon_intensity.csv = fix1+fix2+CI-promotion), fix #1 aggregate
exclusion on for both:

  legacy   -> compute_food_savings(all_ages_denominator=False)
              adults-only fraction  wt/w - 1   (== current committed state)
  fix3     -> compute_food_savings(all_ages_denominator=True)
              all-ages fraction     (wt+c)/(w+c) - 1
              where c = child (0-17) daily energy pool (national),
              from Food data/child_energy_by_country.xlsx.

delta affects only the demand shock; baseline food emissions (sum quantity*CI)
are delta-independent and must be identical across the two runs.

BASELINE ONLY: no P10/P90, no combined-conservative, no diet variants.

Outputs -> outputs/fix3/ only (new files; nothing committed is overwritten).
Run: PYTHONUTF8=1 C:\\Python314\\python.exe outputs\\compare_fix3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_visualization.pipeline import compute_food_savings, load_mortality_emissions
from data_visualization.breakeven_analysis import compute_breakeven
from outputs.compare_fix1 import (
    baseline_food_emissions_mt,
    ratios_for_scenario,
    total_food_savings_mt,
)

OUT = ROOT / "outputs" / "fix3"
LEG = OUT / "legacy_adults_only"
FIX = OUT / "corrected_fix3"
for d in (OUT, LEG, FIX):
    d.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["max_uptake", "mod_uptake"]

# Current committed reference (post fix1+fix2+CI promotion), from the task.
COMMITTED = {
    "baseline_mt": 6510.906562,
    "savings": {"max_uptake": 64.302212, "mod_uptake": 32.924730},
    "cum_ratio": {"max_uptake": 2.976, "mod_uptake": 2.870},
    "y10_ratio": {"max_uptake": 1.60, "mod_uptake": 1.54},
}


def min_country_ratio(be_df, scenario):
    """Smallest per-country cumulative 10-yr food:survivor ratio over the
    complete-data subset (positive food savings + positive survivor emissions)."""
    valid = be_df[
        (be_df["scenario"] == scenario)
        & (be_df["annual_food_savings_t"] > 0)
        & (be_df["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be_df["ratio_food_to_mort"])
    ]
    i = valid["ratio_food_to_mort"].idxmin()
    r = valid.loc[i]
    return float(r["ratio_food_to_mort"]), r["ISO"], r["Country"]


def run(all_ages_denominator: bool, out_dir: Path, label: str):
    print(f"\n[{label}] compute_food_savings(exclude_aggregates=True, "
          f"all_ages_denominator={all_ages_denominator}) ...")
    fs, rdf = compute_food_savings(
        exclude_aggregates=True, all_ages_denominator=all_ages_denominator
    )
    mort = load_mortality_emissions()
    be = compute_breakeven(fs, mort, include_drug=True)
    fs.to_csv(out_dir / "food_savings.csv", index=False)
    be.to_csv(out_dir / "breakeven.csv", index=False)
    return {
        "label": label,
        "baseline_mt": baseline_food_emissions_mt(rdf),
        "savings_mt": total_food_savings_mt(fs),
        "ratios": {sc: ratios_for_scenario(be, sc) for sc in SCENARIOS},
        "min_ratio": {sc: min_country_ratio(be, sc) for sc in SCENARIOS},
    }


def main():
    L = run(False, LEG, "legacy_adults_only")
    F = run(True, FIX, "corrected_fix3")

    # ── invariant: baseline emissions are delta-independent ─────────────
    print("\n" + "=" * 92)
    print("INVARIANT: baseline food emissions are delta-independent (must match)")
    print("=" * 92)
    print(f"  legacy : {L['baseline_mt']:>16,.6f} Mt")
    print(f"  fix3   : {F['baseline_mt']:>16,.6f} Mt")
    print(f"  |Δ|    : {abs(F['baseline_mt'] - L['baseline_mt']):>16.6e} Mt "
          f"({'OK' if np.isclose(L['baseline_mt'], F['baseline_mt'], atol=1e-6) else 'STOP'})")

    # ── legacy reproduces committed state? ──────────────────────────────
    print("\n" + "=" * 92)
    print("HARNESS CHECK: legacy adults-only run vs committed reference")
    print("=" * 92)
    print(f"  baseline Mt      committed {COMMITTED['baseline_mt']:>14,.6f}   "
          f"legacy {L['baseline_mt']:>14,.6f}")
    for sc in SCENARIOS:
        print(f"  savings {sc:<10} committed {COMMITTED['savings'][sc]:>14,.6f}   "
              f"legacy {L['savings_mt'][sc]:>14,.6f}")
    for sc in SCENARIOS:
        print(f"  cum10  {sc:<10} committed {COMMITTED['cum_ratio'][sc]:>14,.3f}   "
              f"legacy {L['ratios'][sc]['cum_ratio_10yr']:>14,.3f}")
    for sc in SCENARIOS:
        print(f"  y10    {sc:<10} committed {COMMITTED['y10_ratio'][sc]:>14,.2f}   "
              f"legacy {L['ratios'][sc]['annual_ratio_y10']:>14,.2f}")

    # ── headline: committed (=legacy) vs +fix3 ──────────────────────────
    def r3(a, b):
        return f"{a:>18,.6f}{b:>18,.6f}{(b/a-1)*100:>12.2f}%"

    print("\n" + "=" * 92)
    print("HEADLINE — committed (fix1+fix2+CI promotion) vs +fix3  (baseline, mean CI)")
    print("=" * 92)
    print(f"  {'':<40}{'committed':>18}{'+fix3':>18}{'change':>13}")
    print("  " + "-" * 88)
    print(f"  {'Baseline food emissions (Mt)':<40}"
          + r3(L['baseline_mt'], F['baseline_mt']))
    for sc in SCENARIOS:
        print(f"  {'Annual food savings ' + sc + ' (Mt/yr)':<40}"
              + r3(L['savings_mt'][sc], F['savings_mt'][sc]))
    for sc in SCENARIOS:
        a = L['ratios'][sc]['cum_ratio_10yr']; b = F['ratios'][sc]['cum_ratio_10yr']
        print(f"  {'Cumulative 10-yr food:survivor ' + sc:<40}"
              f"{a:>17,.3f}x{b:>17,.3f}x{(b-a):>12,.3f}")
    for sc in SCENARIOS:
        a = L['ratios'][sc]['annual_ratio_y10']; b = F['ratios'][sc]['annual_ratio_y10']
        print(f"  {'Year-10 annual food:survivor ' + sc:<40}"
              f"{a:>17,.3f}x{b:>17,.3f}x{(b-a):>12,.3f}")

    # ── minimum country ratio ───────────────────────────────────────────
    print("\n" + "=" * 92)
    print("MINIMUM COUNTRY RATIO (cumulative 10-yr food:survivor, complete-data)")
    print("=" * 92)
    for sc in SCENARIOS:
        lr, li, lc = L['min_ratio'][sc]
        fr, fi, fc = F['min_ratio'][sc]
        print(f"  {sc:<12} committed {lr:>7,.3f}x ({li} {lc})   "
              f"+fix3 {fr:>7,.3f}x ({fi} {fc})")

    # ── persist headline ────────────────────────────────────────────────
    rows = []
    for lbl, d in [("committed_legacy", L), ("corrected_fix3", F)]:
        for sc in SCENARIOS:
            mr, mi, mc = d["min_ratio"][sc]
            rows.append({
                "run": lbl, "scenario": sc,
                "baseline_food_emissions_mt": d["baseline_mt"],
                "total_annual_food_savings_mt": d["savings_mt"][sc],
                "cum_food_to_survivor_ratio_10yr": d["ratios"][sc]["cum_ratio_10yr"],
                "annual_food_to_survivor_ratio_y10": d["ratios"][sc]["annual_ratio_y10"],
                "min_country_ratio_10yr": mr,
                "min_country_iso": mi,
                "min_country_name": mc,
                "n_complete_countries": d["ratios"][sc]["n_countries"],
            })
    pd.DataFrame(rows).to_csv(OUT / "headline_numbers_fix3.csv", index=False)
    print(f"\nSaved: {OUT / 'headline_numbers_fix3.csv'}")
    print(f"Saved: {LEG}/ and {FIX}/ (food_savings.csv, breakeven.csv)")


if __name__ == "__main__":
    main()
