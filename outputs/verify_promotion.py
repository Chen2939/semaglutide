"""
Post-promotion verification (run AFTER canonical CI files were replaced with the
raw-milk-dairy rebuild).

Part 1 — DEFAULT mean path:
  compute_food_savings() with all defaults (ci_file="carbon_intensity.csv",
  exclude_aggregates=True) must reproduce the fix1+fix2+cireg headline column
  exactly (baseline 6,510.9 Mt), proving the promotion only redirected the
  default path to the already-verified regenerated file.

Part 2 — sensitivity ratios under raw-milk dairy:
  Recompute P10 / P90 / combined-conservative global max-uptake ratios using the
  NEW canonical p10/p90 (raw-milk dairy), to show the shift from the prior
  blend-based 2.36 / 10.37 (manuscript 2.34 / 10.13).

Run:  PYTHONUTF8=1 C:\\Python314\\python.exe outputs\\verify_promotion.py
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
from diet_sensitivity.pipeline import compute_food_savings_diet
from outputs.compare_fix1 import (
    baseline_food_emissions_mt,
    ratios_for_scenario,
    total_food_savings_mt,
)
from outputs.repro_sensitivity import global_max_ratio, build_meat_p10_on_mean

SCEN = ["max_uptake", "mod_uptake"]

# fix1+fix2+cireg targets (outputs/cireg/headline_numbers_cireg.csv, run=fix1_fix2_cireg)
TARGET = {
    "baseline_mt": 6510.9065615889995,
    "savings": {"max_uptake": 64.30221196661066, "mod_uptake": 32.92472966330065},
    "cum10": {"max_uptake": 2.975908731414115, "mod_uptake": 2.8705886878029645},
    "y10": {"max_uptake": 1.5953789020301703, "mod_uptake": 1.5432627536101429},
}
# prior blend-based sensitivity (handoff) and manuscript
PRIOR_BLEND = {"P10": 2.36, "P90": 10.37, "combined_conservative": 2.71}
MANUSCRIPT = {"P10": 2.34, "P90": 10.13, "combined_conservative": 2.71}


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


def main():
    mort = load_mortality_emissions()

    # ── Part 1: default mean-path headline ──────────────────────────────
    print("=" * 84)
    print("PART 1 — DEFAULT PIPELINE  compute_food_savings()  vs  fix1+fix2+cireg target")
    print("=" * 84)
    fs, rdf = compute_food_savings()  # all defaults
    be = compute_breakeven(fs, mort, include_drug=True)
    baseline = baseline_food_emissions_mt(rdf)
    savings = total_food_savings_mt(fs)
    ratios = {sc: ratios_for_scenario(be, sc) for sc in SCEN}

    checks = []
    print(f"\n  {'metric':<38}{'default':>16}{'target':>18}{'match?':>8}")
    print("  " + "-" * 78)

    def line(name, got, tgt):
        ok = approx(got, tgt)
        checks.append(ok)
        print(f"  {name:<38}{got:>16,.6f}{tgt:>18,.6f}{('YES' if ok else 'NO'):>8}")

    line("Baseline food emissions (Mt)", baseline, TARGET["baseline_mt"])
    for sc in SCEN:
        line(f"Annual savings {sc} (Mt/yr)", savings[sc], TARGET["savings"][sc])
    for sc in SCEN:
        line(f"Cumulative 10-yr ratio {sc}", ratios[sc]["cum_ratio_10yr"], TARGET["cum10"][sc])
    for sc in SCEN:
        line(f"Year-10 annual ratio {sc}", ratios[sc]["annual_ratio_y10"], TARGET["y10"][sc])

    part1_ok = all(checks)
    print(f"\n  PART 1: {'ALL MATCH — default path reproduces fix1+fix2+cireg exactly' if part1_ok else '*** MISMATCH — a stale file is being read somewhere, STOP ***'}")

    # ── Part 2: sensitivity ratios under raw-milk dairy ─────────────────
    print("\n" + "=" * 84)
    print("PART 2 — SENSITIVITY RATIOS under raw-milk dairy (new canonical p10/p90)")
    print("=" * 84)
    got = {}
    for key, diet, ci in [
        ("P10", "baseline_uniform", "carbon_intensity_p10.csv"),
        ("P90", "baseline_uniform", "carbon_intensity_p90.csv"),
    ]:
        fsd, _ = compute_food_savings_diet(diet_scenario=diet, ci_file=ci)
        r, n = global_max_ratio(fsd, mort)
        got[key] = (r, n)

    meat_file = build_meat_p10_on_mean("carbon_intensity_p10.csv")
    fsd, _ = compute_food_savings_diet(diet_scenario="cereal_sweets_up", ci_file=meat_file.name)
    r, n = global_max_ratio(fsd, mort)
    got["combined_conservative"] = (r, n)

    print(f"\n  {'scenario':<24}{'manuscript':>12}{'prior(blend)':>14}{'now(raw-milk)':>15}{'Δ vs prior':>12}")
    print("  " + "-" * 77)
    rows = []
    for key in ["P10", "P90", "combined_conservative"]:
        r, n = got[key]
        print(f"  {key:<24}{MANUSCRIPT[key]:>12.2f}{PRIOR_BLEND[key]:>14.2f}"
              f"{r:>15.2f}{r - PRIOR_BLEND[key]:>12.2f}")
        rows.append({"scenario": key, "manuscript": MANUSCRIPT[key],
                     "prior_blend": PRIOR_BLEND[key], "raw_milk": round(r, 4),
                     "delta_vs_prior": round(r - PRIOR_BLEND[key], 4), "n_countries": n})
    out = Path(__file__).resolve().parent / "cireg" / "sensitivity_raw_milk.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\n  Saved: {out}")

    print("\n" + "=" * 84)
    print(f"OVERALL: Part 1 headline match = {part1_ok}")
    print("=" * 84)


if __name__ == "__main__":
    main()
