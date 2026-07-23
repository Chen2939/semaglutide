"""
CI-REGEN (repo hygiene, NOT a numbered fix).

Regenerates the three carbon-intensity files (mean/p10/p90) from CURRENT
build_carbon_intensity.py code (which computes "Oilcrops Oil, Other" as
oilcrops_avg = 5.286 instead of the stale hardcoded 4.50) to *_cireg filenames,
WITHOUT overwriting any committed baseline.

Then, isolating the CI-regen increment on top of fix1+fix2:
  C = fix1+fix2        -> exclude_aggregates=True, ci=carbon_intensity_fix2.csv
                          (oilcrops 4.50 [stale]  + dairy 3.15)
  D = fix1+fix2+cireg  -> exclude_aggregates=True, ci=carbon_intensity_cireg_fix2.csv
                          (oilcrops 5.286 [regen] + dairy 3.15)
Between C and D only the Fats-and-oils CI changes, so only that group's
emissions should move.

Outputs -> outputs/cireg/.  Commits nothing.

Run:  PYTHONUTF8=1 C:\\Python314\\python.exe outputs\\compare_cireg.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_carbon_intensity as bci
from data_visualization.pipeline import compute_food_savings, load_mortality_emissions
from data_visualization.breakeven_analysis import compute_breakeven
from outputs.compare_fix1 import (
    baseline_food_emissions_mt,
    ratios_for_scenario,
    total_food_savings_mt,
)
from outputs.compare_fix2 import group_baseline_emissions_mt

OUT = Path(__file__).resolve().parent
CIREG = OUT / "cireg"
CIREG.mkdir(parents=True, exist_ok=True)
FOOD = ROOT / "Food data"

SCENARIOS = ["max_uptake", "mod_uptake"]
CI_MULT = 1000.0
GROUP_COLS = [
    "Cereals", "Dairy", "Eggs", "Fats and oils", "Fish",
    "Fruit and vegetables", "Meat", "Other",
    "Sweets, confectionery, and sweetened beverages",
]


def regen_ci_files(dairy_raw_milk_basis=True):
    """Regenerate mean/p10/p90 to *_cireg from current code.

    ``dairy_raw_milk_basis`` is threaded through to EVERY scenario explicitly
    rather than relying on build_ci's default. Not passing the flag here is what
    originally produced blend-based p10/p90 while the mean was raw-milk; passing
    it explicitly keeps all three scenarios consistent regardless of the default.
    """
    print("Regenerating CI files from current code -> *_cireg ...")
    out = {}
    for scenario, name in [
        ("mean", "carbon_intensity_cireg.csv"),
        ("p10", "carbon_intensity_p10_cireg.csv"),
        ("p90", "carbon_intensity_p90_cireg.csv"),
    ]:
        path = FOOD / name
        bci.build_ci(scenario, dairy_raw_milk_basis=dairy_raw_milk_basis, out_path=str(path))
        out[scenario] = path
    return out


def diff_ci(committed_name, cireg_path, label):
    """Per-column max abs delta between a committed CI file and its _cireg build."""
    committed = FOOD / committed_name
    print("\n" + "=" * 92)
    print(f"CI-FILE DIFF: {label}  ({committed_name}  vs  {cireg_path.name})")
    print("=" * 92)
    if not committed.exists():
        print(f"  No committed counterpart '{committed_name}' exists — "
              f"the _cireg file is created for the FIRST time (nothing to diff).")
        return None
    a = pd.read_csv(committed)
    b = pd.read_csv(cireg_path)
    m = pd.merge(a, b, on="ISO", suffixes=("_old", "_new"))
    moved = []
    print(f"  {'column':<48}{'max |Δ| per country':>22}")
    print("  " + "-" * 70)
    for c in GROUP_COLS:
        d = (m[f"{c}_new"] - m[f"{c}_old"]).abs().max()
        if d > 1e-9:
            moved.append(c)
        print(f"  {c:<48}{d:>22.8f}")
    print(f"\n  Columns that move: {moved if moved else 'NONE'}")
    return moved


def per_country_fats(result_df):
    """Per-country Fats-and-oils tonnage, CI (kg/kg) and emissions (Mt)."""
    one = result_df[result_df["scenario"] == "max_uptake"].drop_duplicates(
        subset=["ISO", "final_food_group"]
    )
    fats = one[one["final_food_group"] == "Fats and oils"][
        ["ISO", "Country", "initial_eql_quantity", "carbon_intensity_t"]
    ].copy()
    fats["ci_kg"] = fats["carbon_intensity_t"] / CI_MULT
    fats["emis_mt"] = fats["initial_eql_quantity"] * fats["carbon_intensity_t"] / 1e6
    return fats.rename(columns={"initial_eql_quantity": "tonnage"})


def run(ci_file, label, save_dir=None):
    print(f"[{label}] compute_food_savings(ci_file={ci_file!r}, exclude_aggregates=True) ...")
    fs, rdf = compute_food_savings(ci_file=ci_file, exclude_aggregates=True)
    mort = load_mortality_emissions()
    be = compute_breakeven(fs, mort, include_drug=True)
    if save_dir is not None:
        fs.to_csv(save_dir / "food_savings.csv", index=False)
        be.to_csv(save_dir / "breakeven.csv", index=False)
    return {
        "label": label, "result_df": rdf, "food_savings": fs, "breakeven": be,
        "baseline_mt": baseline_food_emissions_mt(rdf),
        "group_emis_mt": group_baseline_emissions_mt(rdf),
        "savings_mt": total_food_savings_mt(fs),
        "ratios": {sc: ratios_for_scenario(be, sc) for sc in SCENARIOS},
    }


def main():
    print("=" * 92)
    print("CI-REGEN — reproducibility cleanup (oilcrops 4.50 -> 5.286), on top of fix1+fix2")
    print("=" * 92)

    # ── Step 2: regenerate ──────────────────────────────────────────────
    paths = regen_ci_files()

    # ── Step 3: diffs vs committed ──────────────────────────────────────
    mean_moved = diff_ci("carbon_intensity.csv", paths["mean"], "mean")
    diff_ci("carbon_intensity_p10.csv", paths["p10"], "p10")
    diff_ci("carbon_intensity_p90.csv", paths["p90"], "p90")

    if mean_moved != ["Fats and oils"]:
        print(f"\n*** STOP: mean file moved in columns {mean_moved}, "
              f"expected only ['Fats and oils']. Investigate before continuing. ***")
        return
    print("\nConfirmed: in the MEAN file, 'Fats and oils' is the only column that changes.")

    # ── Build cireg+fix2 mean CI (oilcrops 5.286 + dairy raw-milk 3.15) ──
    milk = bci.GHG_SCENARIOS["mean"]["milk"]
    cireg = pd.read_csv(paths["mean"])
    cireg_fix2 = cireg.copy()
    cireg_fix2["Dairy"] = milk
    cireg_fix2_path = FOOD / "carbon_intensity_cireg_fix2.csv"
    cireg_fix2.to_csv(cireg_fix2_path, index=False)
    # sanity: differs from carbon_intensity_fix2.csv ONLY in Fats and oils
    base_fix2 = pd.read_csv(FOOD / "carbon_intensity_fix2.csv")
    mm = pd.merge(base_fix2, cireg_fix2, on="ISO", suffixes=("_f2", "_cf2"))
    moved2 = [c for c in GROUP_COLS
              if (mm[f"{c}_cf2"] - mm[f"{c}_f2"]).abs().max() > 1e-9]
    print(f"carbon_intensity_cireg_fix2.csv vs carbon_intensity_fix2.csv moves: {moved2}")

    # ── Step 5: pipeline runs C and D ───────────────────────────────────
    print()
    C = run("carbon_intensity_fix2.csv", "fix1+fix2")
    D = run("carbon_intensity_cireg_fix2.csv", "fix1+fix2+cireg", save_dir=CIREG)

    # ── confirm only Fats group emissions moved (C -> D) ────────────────
    print("\n" + "=" * 92)
    print("PER-GROUP BASELINE EMISSIONS (Mt): fix1+fix2 -> fix1+fix2+cireg")
    print("=" * 92)
    print(f"  {'Food group':<48}{'fix1+fix2':>14}{'+cireg':>14}{'Δ':>12}")
    print("  " + "-" * 86)
    other_moved = []
    for g in GROUP_COLS:
        b = C["group_emis_mt"].get(g, 0.0)
        a = D["group_emis_mt"].get(g, 0.0)
        d = a - b
        flag = ""
        if g != "Fats and oils" and not np.isclose(d, 0.0, atol=1e-6):
            flag = "  <-- UNEXPECTED"
            other_moved.append(g)
        print(f"  {g:<48}{b:>14,.3f}{a:>14,.3f}{d:>12,.3f}{flag}")
    if other_moved:
        print(f"\n  *** Non-Fats groups changed: {other_moved} — STOP. ***")
        return
    print("\n  Confirmed: only the Fats-and-oils group's emissions changed.")

    # ── Step 4: per-country invariant  Δemis = tonnage × ΔCI ─────────────
    fc = per_country_fats(C["result_df"]).rename(
        columns={"ci_kg": "ci_before", "emis_mt": "emis_before", "tonnage": "tonnage_before"}
    )
    fd = per_country_fats(D["result_df"]).rename(
        columns={"ci_kg": "ci_after", "emis_mt": "emis_after", "tonnage": "tonnage_after"}
    )
    inv = pd.merge(
        fc[["ISO", "Country", "tonnage_before", "ci_before", "emis_before"]],
        fd[["ISO", "ci_after", "emis_after", "tonnage_after"]],
        on="ISO",
    )
    inv["observed_delta_mt"] = inv["emis_after"] - inv["emis_before"]
    inv["expected_delta_mt"] = (
        inv["tonnage_before"] * (inv["ci_after"] - inv["ci_before"]) * CI_MULT / 1e6
    )
    inv["gap"] = inv["observed_delta_mt"] - inv["expected_delta_mt"]
    inv["tonnage_unchanged"] = np.isclose(inv["tonnage_before"], inv["tonnage_after"])
    inv.to_csv(CIREG / "fats_invariant_by_country.csv", index=False)

    print("\n" + "=" * 92)
    print("INVARIANT (per country): Δ(Fats emissions) == Fats tonnage × (CI_after − CI_before)")
    print("=" * 92)
    obs = inv["observed_delta_mt"].sum()
    exp = inv["expected_delta_mt"].sum()
    print(f"  Countries checked:               {len(inv)}")
    print(f"  Fats tonnage unchanged (all):    {'YES' if inv['tonnage_unchanged'].all() else 'NO — STOP'}")
    print(f"  Observed Σ Δ Fats emissions:     {obs:>14,.4f} Mt")
    print(f"  Expected Σ tonnage × ΔCI:        {exp:>14,.4f} Mt")
    print(f"  Aggregate gap:                   {abs(obs - exp):>14,.6f} Mt")
    print(f"  Worst per-country |gap|:         {inv['gap'].abs().max():>14,.8f} Mt")
    inv_ok = (
        inv["tonnage_unchanged"].all()
        and np.isclose(obs, exp, rtol=1e-9, atol=1e-6)
        and inv["gap"].abs().max() < 1e-6
    )
    print(f"  {'INVARIANT HOLDS' if inv_ok else '*** INVARIANT VIOLATED — STOP ***'}")
    if not inv_ok:
        return

    # ── headline: fix1+fix2  vs  fix1+fix2+cireg ────────────────────────
    def row(a, b):
        return f"{a:>16,.1f}{b:>18,.1f}{b - a:>14,.2f}"

    print("\n" + "=" * 92)
    print("HEADLINE NUMBERS — fix1+fix2  vs  fix1+fix2+cireg  (CI-regen increment isolated)")
    print("=" * 92)
    print(f"  {'':<34}{'fix1+fix2':>16}{'fix1+fix2+cireg':>18}{'Δ (cireg)':>14}")
    print("  " + "-" * 80)
    print(f"  {'Baseline food emissions (Mt)':<34}"
          + row(C["baseline_mt"], D["baseline_mt"]))
    for sc in SCENARIOS:
        print(f"  {'Annual food savings ' + sc + ' (Mt/yr)':<34}"
              + row(C["savings_mt"][sc], D["savings_mt"][sc]))
    for sc in SCENARIOS:
        a = C["ratios"][sc]["cum_ratio_10yr"]; b = D["ratios"][sc]["cum_ratio_10yr"]
        print(f"  {'Cumulative 10-yr ratio ' + sc:<34}{a:>15,.2f}x{b:>17,.2f}x{b - a:>13,.3f}")
    for sc in SCENARIOS:
        a = C["ratios"][sc]["annual_ratio_y10"]; b = D["ratios"][sc]["annual_ratio_y10"]
        print(f"  {'Year-10 annual ratio ' + sc:<34}{a:>15,.2f}x{b:>17,.2f}x{b - a:>13,.3f}")

    rows = []
    for lbl, d in [("fix1_fix2", C), ("fix1_fix2_cireg", D)]:
        for sc in SCENARIOS:
            rows.append({
                "run": lbl, "scenario": sc,
                "baseline_food_emissions_mt": d["baseline_mt"],
                "total_annual_food_savings_mt": d["savings_mt"][sc],
                "cum_food_to_survivor_ratio_10yr": d["ratios"][sc]["cum_ratio_10yr"],
                "annual_food_to_survivor_ratio_y10": d["ratios"][sc]["annual_ratio_y10"],
            })
    pd.DataFrame(rows).to_csv(CIREG / "headline_numbers_cireg.csv", index=False)
    print(f"\nSaved: {CIREG / 'headline_numbers_cireg.csv'}")
    print(f"Saved: {CIREG / 'fats_invariant_by_country.csv'}")
    print(f"Saved: outputs/cireg/ (food_savings.csv, breakeven.csv)")
    print(f"CI files written to Food data/: carbon_intensity_cireg.csv, "
          f"carbon_intensity_p10_cireg.csv, carbon_intensity_p90_cireg.csv, "
          f"carbon_intensity_cireg_fix2.csv")


if __name__ == "__main__":
    main()
