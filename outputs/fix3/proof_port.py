"""Faithful-port proof: diet pipeline (uniform diet, mean CI) must reproduce the
main post-fix-#3 pipeline bit-for-bit before any sensitivity run."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_visualization.pipeline import compute_food_savings
from diet_sensitivity.pipeline import compute_food_savings_diet
from outputs.compare_fix1 import baseline_food_emissions_mt, total_food_savings_mt

TARGET = {"baseline": 6510.906562, "max": 54.197555, "mod": 27.766417}

fs_m, rdf_m = compute_food_savings(exclude_aggregates=True, all_ages_denominator=True)
fs_d, rdf_d = compute_food_savings_diet(diet_scenario="baseline_uniform",
                                        ci_file="carbon_intensity.csv")

bm = baseline_food_emissions_mt(rdf_m); bd = baseline_food_emissions_mt(rdf_d)
sm = total_food_savings_mt(fs_m); sd = total_food_savings_mt(fs_d)

print("=" * 78)
print("FAITHFUL-PORT PROOF  (diet uniform/mean-CI  vs  main post-fix-#3)")
print("=" * 78)
print(f"{'metric':<34}{'target':>16}{'main':>16}{'diet':>16}")
print("-" * 82)
print(f"{'baseline food emissions (Mt)':<34}{TARGET['baseline']:>16.6f}{bm:>16.6f}{bd:>16.6f}")
print(f"{'annual food savings max (Mt/yr)':<34}{TARGET['max']:>16.6f}{sm['max_uptake']:>16.6f}{sd['max_uptake']:>16.6f}")
print(f"{'annual food savings mod (Mt/yr)':<34}{TARGET['mod']:>16.6f}{sm['mod_uptake']:>16.6f}{sd['mod_uptake']:>16.6f}")

# bit-for-bit per-country savings comparison
m = fs_m.merge(fs_d, on=["ISO", "scenario"], suffixes=("_m", "_d"))
dmax = (m["annual_food_savings_t_m"] - m["annual_food_savings_t_d"]).abs().max()

print("\nchecks:")
tol = 1e-6
ok_target = (abs(bd - TARGET["baseline"]) < tol and abs(sd["max_uptake"] - TARGET["max"]) < tol
             and abs(sd["mod_uptake"] - TARGET["mod"]) < tol)
print(f"  diet == committed targets (<{tol}):        {ok_target}")
print(f"  diet == main baseline emissions:           {np.isclose(bd, bm, atol=1e-9, rtol=0)}")
print(f"  diet == main savings (max/mod):            "
      f"{np.isclose(sd['max_uptake'], sm['max_uptake'], atol=1e-9) and np.isclose(sd['mod_uptake'], sm['mod_uptake'], atol=1e-9)}")
print(f"  max |per-country savings diff| main vs diet: {dmax:.6e} t")
print(f"  countries compared: {len(m)}")
print("\nRESULT:", "PASS -- port faithful, safe to run sensitivity"
      if (ok_target and np.isclose(bd, bm, atol=1e-9) and dmax < 1e-3)
      else "FAIL -- STOP, paths diverge")
