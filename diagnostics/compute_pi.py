"""Build pi through the production builder and regression-gate it.

GATE, declared before the run: ``build_food_shock_survival_weight()`` must
reproduce the pi values already computed and reviewed at hard stop 1
(``diagnostics/pi_by_country_pkl.csv``, from the pickle's own lookup, which the
mortality source swap has since made the live one) for **all 63 ISO x 2 scenarios
x 15 years, exactly 0.0**.

Two things changed between the two computations and neither may move a value:
the lookup is now built inside ``compute_individual_survival_diffs`` by
``build_mortality_map`` instead of being passed in, and the full 1,890,000-row
frame is passed instead of the 350,424 rows with a non-zero treatment effect.
Any divergence is a finding about the refactor, not about pi.

    PYTHONUTF8=1 C:\\Python314\\python.exe -m diagnostics.compute_pi
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization.survival_weighting import (
    PI_HORIZON,
    build_food_shock_survival_weight,
)

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "diagnostics" / "pi_by_country_pkl.csv"
pd.set_option("display.width", 250)

print("Building pi through the production builder...")
pi = build_food_shock_survival_weight()
wide = pi.pivot(index=["ISO", "scenario"], columns="year", values="pi")
wide.columns = [f"pi_Y{c}" for c in wide.columns]

print()
print("=" * 78)
print("GATE  reproduce the reviewed hard-stop-1 values, bar exactly 0.0")
print("=" * 78)
# float_precision='round_trip' is load-bearing, not decoration. The reference is
# a CSV written by the hard-stop-1 script, and pandas' default parser (the fast
# xstrtod) reads 721 of these 1,890 cells one ULP off an exact strtod -- mixed
# sign, mean signed difference 4e-19, no drift, i.e. purely the parse.
# diagnostics/diagnose_pi_gate.py separates that from any real cause and shows
# the in-memory computations agree at exactly 0.0. Reading the reference loosely
# would have meant loosening this gate to hide a parser artifact.
cols = [f"pi_Y{t}" for t in range(1, PI_HORIZON + 1)]
loose = pd.read_csv(REFERENCE).set_index(["ISO", "scenario"])
ref = pd.read_csv(REFERENCE, float_precision="round_trip").set_index(
    ["ISO", "scenario"]
)
print(f"  reference: {REFERENCE.name}  {ref.shape}")
print(f"  new      : {wide.shape}")
assert sorted(ref.index) == sorted(wide.index), "index set changed"
b = wide[cols].to_numpy(dtype=float)
n_loose = int((loose.loc[wide.index, cols].to_numpy(dtype=float) != b).sum())
a = ref.loc[wide.index, cols].to_numpy(dtype=float)
ndiff = int((a != b).sum())
print(f"  cells differing under the default parser   : {n_loose} (1 ULP, parse only)")
print(f"  cells compared: {a.size:,}   differing under round_trip: {ndiff}")
if ndiff:
    d = np.abs(a - b)
    print(f"  max abs {d.max():.3e}   max rel {np.max(d / np.abs(a)):.3e}")
    bad = wide.index[(a != b).any(axis=1)]
    print(f"  rows differing: {list(bad)[:20]}")
    print("  GATE FAILED")
    sys.exit(1)
print("  GATE PASSED (exactly 0).")

print()
print("=" * 78)
print("Global pi(t), difference-weighted, both scenarios")
print("=" * 78)
# A global pi is a re-weighted aggregate, not a mean of the per-country values,
# so it is recomputed from the weights rather than averaged off the table.
from data_visualization.deterministic_mortality import (
    compute_individual_survival_diffs,
    load_inputs,
)

sim = load_inputs()
ind = compute_individual_survival_diffs(
    sim, horizon=PI_HORIZON, survival_columns=True,
    extra_columns=("eer_diff",), population_weighted=False,
)
ind["w_diff"] = ind["weighting"] * ind["eer_diff"]
rows = []
for scen in ("max_uptake", "mod_uptake"):
    s = ind[ind["scenario"] == scen]
    den = s["w_diff"].sum()
    for t in range(1, PI_HORIZON + 1):
        rows.append({"scenario": scen, "year": t,
                     "pi_global": float((s["w_diff"] * s[f"p_sg_Y{t}"]).sum() / den)})
g = pd.DataFrame(rows).pivot(index="year", columns="scenario", values="pi_global")
print(g.to_string(float_format=lambda v: f"{v:.6f}"))

print()
print("=" * 78)
print("Coverage: pi vs the food model's country set (report only, no stop)")
print("=" * 78)
from data_visualization.pipeline import compute_food_savings

food_savings, result_df = compute_food_savings()
fs = food_savings[food_savings["scenario"] == "max_uptake"]
food_all = set(fs["ISO"])
food_pos = set(fs.loc[fs["annual_food_savings_t"] > 0, "ISO"])
pi_iso = set(pi["ISO"])
print(f"  ISO with a pi: {len(pi_iso)}")
print(f"  ISO in food_savings: {len(food_all)};  with annual_food_savings_t > 0: {len(food_pos)}")
print(f"  food savings > 0 but no pi: {sorted(food_pos - pi_iso)}")
print(f"  pi but no food savings > 0: {sorted(pi_iso - food_pos)}")

oecd = pd.read_csv(ROOT / "mortality model total emissions_oecd.csv")
oecd_mx = oecd[oecd["scenario"] == "max_uptake"].set_index("ISO")
has_factor = set(oecd_mx.index[oecd_mx[
    ["oecd_nonfood_ghg_t_per_capita", "food_add_back_t_per_capita"]
].notna().all(axis=1)])
no_factor_but_food = sorted((food_pos & pi_iso) - has_factor)
print()
print(f"  ISO carrying food savings and a pi but NO OECD factor "
      f"({len(no_factor_but_food)}): {no_factor_but_food}")
print("  pi scales the food side for these too. They never reach the break-even,")
print("  which needs a survivor factor, but they do enter every food-only")
print("  aggregate -- so pi must be applied regardless of survivor coverage.")
print()
print(f"  break-even set (food savings > 0, pi, and an OECD factor): "
      f"{len(sorted((food_pos & pi_iso) & has_factor))}")
