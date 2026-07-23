"""
Side-by-side verification of fix #2 (dairy raw-milk CI basis), on top of fix #1.

Three configurations, run from a SINGLE process:
  * original      -> exclude_aggregates=False, ci=carbon_intensity.csv
  * fix1          -> exclude_aggregates=True,  ci=carbon_intensity.csv
  * fix1_fix2     -> exclude_aggregates=True,  ci=carbon_intensity_fix2.csv
                     (Dairy CI = raw milk 3.15 instead of milk+cheese blend 4.04;
                      isolated: carbon_intensity_fix2.csv differs from
                      carbon_intensity.csv ONLY in the Dairy column.)

Nothing existing is overwritten; fix1_fix2 outputs land in outputs/corrected_fix2/.

Verification order (intermediates BEFORE totals):
  1. Dairy-group CI before/after.
  2. Dairy tonnage (must be unchanged by fix #2).
  3. Dairy-group emissions (Mt) before/after.
  4. Invariant: Δ(dairy emissions) == dairy tonnage × (CI_before − CI_after).
  5. Confirm NO other food group's emissions moved.
  6. Headline numbers three ways: original / fix1 / fix1+fix2.

Run from repo root:  C:\\Python314\\python.exe outputs\\compare_fix2.py
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

OUT = Path(__file__).resolve().parent
FIX2 = OUT / "corrected_fix2"
FIX2.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["max_uptake", "mod_uptake"]
CI_MULT = 1000.0  # pipeline multiplies CI (kg/kg) by 1000 -> t CO2e per FAOSTAT unit


def group_baseline_emissions_mt(result_df: pd.DataFrame) -> pd.Series:
    """Per-food-group national baseline emissions (Mt), one scenario (quantity
    and CI are scenario-invariant)."""
    one = result_df[result_df["scenario"] == "max_uptake"].drop_duplicates(
        subset=["ISO", "final_food_group"]
    ).copy()
    one["emis_t"] = one["initial_eql_quantity"] * one["carbon_intensity_t"]
    return one.groupby("final_food_group")["emis_t"].sum() / 1e6


def dairy_tonnage_and_ci(result_df: pd.DataFrame) -> tuple[float, float]:
    """Total Dairy tonnage and the CI (kg/kg) actually applied in the run."""
    one = result_df[result_df["scenario"] == "max_uptake"].drop_duplicates(
        subset=["ISO", "final_food_group"]
    )
    dairy = one[one["final_food_group"] == "Dairy"]
    tonnage = dairy["initial_eql_quantity"].sum()
    ci_kg = (dairy["carbon_intensity_t"] / CI_MULT).dropna().unique()
    ci_val = float(ci_kg[0]) if len(ci_kg) == 1 else float("nan")
    return tonnage, ci_val


def run(ci_file, exclude_aggregates, label, save_dir=None):
    print(f"[{label}] compute_food_savings(ci_file={ci_file!r}, "
          f"exclude_aggregates={exclude_aggregates}) ...")
    fs, rdf = compute_food_savings(
        ci_file=ci_file, exclude_aggregates=exclude_aggregates
    )
    mort = load_mortality_emissions()
    be = compute_breakeven(fs, mort, include_drug=True)
    if save_dir is not None:
        fs.to_csv(save_dir / "food_savings.csv", index=False)
        be.to_csv(save_dir / "breakeven.csv", index=False)
    return {
        "label": label,
        "food_savings": fs,
        "result_df": rdf,
        "breakeven": be,
        "baseline_mt": baseline_food_emissions_mt(rdf),
        "group_emis_mt": group_baseline_emissions_mt(rdf),
        "savings_mt": total_food_savings_mt(fs),
        "ratios": {sc: ratios_for_scenario(be, sc) for sc in SCENARIOS},
    }


def main():
    print("=" * 92)
    print("FIX #2 (dairy raw-milk CI) on top of FIX #1 — three-way comparison")
    print("=" * 92)
    orig = run("carbon_intensity.csv", False, "original")
    fix1 = run("carbon_intensity.csv", True, "fix1")
    fix2 = run("carbon_intensity_fix2.csv", True, "fix1_fix2", save_dir=FIX2)

    # ── intermediates ───────────────────────────────────────────────────
    ton_before, ci_before = dairy_tonnage_and_ci(fix1["result_df"])
    ton_after, ci_after = dairy_tonnage_and_ci(fix2["result_df"])

    print("\n" + "=" * 92)
    print("INTERMEDIATE QUANTITIES (fix1  ->  fix1+fix2)")
    print("=" * 92)
    print(f"  Dairy-group CI (kg CO2e/kg):     before = {ci_before:.6f}   "
          f"after = {ci_after:.6f}   Δ = {ci_before - ci_after:.6f}")
    print(f"  Dairy tonnage (FAOSTAT units):   before = {ton_before:,.3f}   "
          f"after = {ton_after:,.3f}")
    tonnage_unchanged = np.isclose(ton_before, ton_after, rtol=0, atol=1e-6)
    print(f"  Dairy tonnage unchanged by fix #2: "
          f"{'YES' if tonnage_unchanged else 'NO — STOP'}")

    dairy_emis_before = fix1["group_emis_mt"]["Dairy"]
    dairy_emis_after = fix2["group_emis_mt"]["Dairy"]
    print(f"  Dairy-group emissions (Mt):      before = {dairy_emis_before:,.3f}   "
          f"after = {dairy_emis_after:,.3f}   Δ = {dairy_emis_after - dairy_emis_before:,.3f}")

    if not tonnage_unchanged:
        print("\n  *** Dairy tonnage moved — fix #2 should not touch tonnage. STOP. ***")
        return

    # ── invariant: Δemissions == tonnage × ΔCI ──────────────────────────
    observed_delta_mt = dairy_emis_after - dairy_emis_before          # negative
    expected_delta_mt = ton_after * (ci_after - ci_before) * CI_MULT / 1e6
    print("\n" + "=" * 92)
    print("INVARIANT: Δ(dairy emissions) == dairy tonnage × (CI_after − CI_before)")
    print("=" * 92)
    print(f"  Observed Δ dairy emissions:      {observed_delta_mt:>14,.4f} Mt")
    print(f"  Expected  tonnage × ΔCI:         {expected_delta_mt:>14,.4f} Mt")
    print(f"  Absolute gap:                    {abs(observed_delta_mt - expected_delta_mt):>14,.6f} Mt")
    inv_ok = np.isclose(observed_delta_mt, expected_delta_mt, rtol=1e-9, atol=1e-6)
    print(f"  {'INVARIANT HOLDS' if inv_ok else '*** INVARIANT VIOLATED — STOP ***'}")
    if not inv_ok:
        print("  Something other than the Dairy CI swap has moved. Not proceeding.")
        return

    # ── confirm only Dairy moved ────────────────────────────────────────
    print("\n" + "=" * 92)
    print("PER-GROUP BASELINE EMISSIONS (Mt): fix1 -> fix1+fix2 (only Dairy should move)")
    print("=" * 92)
    groups = sorted(set(fix1["group_emis_mt"].index) | set(fix2["group_emis_mt"].index))
    print(f"  {'Food group':<48}{'fix1':>14}{'fix1+fix2':>14}{'Δ':>12}")
    print("  " + "-" * 86)
    other_moved = []
    for g in groups:
        b = fix1["group_emis_mt"].get(g, 0.0)
        a = fix2["group_emis_mt"].get(g, 0.0)
        d = a - b
        flag = ""
        if g != "Dairy" and not np.isclose(d, 0.0, atol=1e-6):
            flag = "  <-- UNEXPECTED"
            other_moved.append(g)
        print(f"  {g:<48}{b:>14,.3f}{a:>14,.3f}{d:>12,.3f}{flag}")
    if other_moved:
        print(f"\n  *** Non-dairy groups changed: {other_moved} — STOP. ***")
        return
    print("\n  Confirmed: only the Dairy group's emissions changed.")

    # ── headline three ways ─────────────────────────────────────────────
    def col(v):
        return f"{v:>14,.1f}"

    print("\n" + "=" * 92)
    print("HEADLINE NUMBERS — original / fix1 / fix1+fix2")
    print("=" * 92)

    print("\n  Baseline national food emissions (Mt CO2e):")
    print(f"    {'':<16}{'original':>14}{'fix1':>14}{'fix1+fix2':>14}")
    print(f"    {'':<16}{col(orig['baseline_mt'])}{col(fix1['baseline_mt'])}{col(fix2['baseline_mt'])}")

    print("\n  Total annual food savings (Mt CO2e/yr), gross of drug:")
    print(f"    {'scenario':<16}{'original':>14}{'fix1':>14}{'fix1+fix2':>14}")
    for sc in SCENARIOS:
        print(f"    {sc:<16}{col(orig['savings_mt'][sc])}"
              f"{col(fix1['savings_mt'][sc])}{col(fix2['savings_mt'][sc])}")

    print("\n  Cumulative 10-yr food:survivor ratio (complete-data countries):")
    print(f"    {'scenario':<16}{'original':>14}{'fix1':>14}{'fix1+fix2':>14}")
    for sc in SCENARIOS:
        print(f"    {sc:<16}"
              f"{orig['ratios'][sc]['cum_ratio_10yr']:>13,.1f}x"
              f"{fix1['ratios'][sc]['cum_ratio_10yr']:>13,.1f}x"
              f"{fix2['ratios'][sc]['cum_ratio_10yr']:>13,.1f}x")

    print("\n  Year-10 ANNUAL food:survivor ratio (complete-data countries):")
    print(f"    {'scenario':<16}{'original':>14}{'fix1':>14}{'fix1+fix2':>14}")
    for sc in SCENARIOS:
        print(f"    {sc:<16}"
              f"{orig['ratios'][sc]['annual_ratio_y10']:>13,.1f}x"
              f"{fix1['ratios'][sc]['annual_ratio_y10']:>13,.1f}x"
              f"{fix2['ratios'][sc]['annual_ratio_y10']:>13,.1f}x")

    # persist compact headline table
    rows = []
    for lbl, d in [("original", orig), ("fix1", fix1), ("fix1_fix2", fix2)]:
        for sc in SCENARIOS:
            rows.append({
                "run": lbl,
                "scenario": sc,
                "baseline_food_emissions_mt": d["baseline_mt"],
                "total_annual_food_savings_mt": d["savings_mt"][sc],
                "cum_food_to_survivor_ratio_10yr": d["ratios"][sc]["cum_ratio_10yr"],
                "annual_food_to_survivor_ratio_y10": d["ratios"][sc]["annual_ratio_y10"],
            })
    pd.DataFrame(rows).to_csv(OUT / "headline_numbers_fix2.csv", index=False)
    print(f"\nSaved: {OUT / 'headline_numbers_fix2.csv'}")
    print(f"Saved: outputs/corrected_fix2/  (food_savings.csv, breakeven.csv)")


if __name__ == "__main__":
    main()
