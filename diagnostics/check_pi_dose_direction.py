"""Is pi_dose <= pi elementwise, and which way does substituting pi move the drug?

The direction claim in the docs rests on the sign of (pi - pi_dose). It was
originally checked only on the min/max of each year's range, which does not
establish an elementwise ordering. Checked properly here, then the consequence is
worked through arithmetically rather than asserted.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization.drug_footprint import ANNUAL_DRUG_KG_CO2E_PER_USER
from data_visualization.survival_weighting import load_food_shock_survival_weight

ROOT = Path(__file__).resolve().parent.parent
HORIZON = 10

pi = load_food_shock_survival_weight(horizon=HORIZON, column="pi")
dose = load_food_shock_survival_weight(horizon=HORIZON, column="pi_dose")
assert pi.index.equals(dose.index)

d = (pi - dose).to_numpy(dtype=float)
print("=" * 78)
print("1. Sign of (pi - pi_dose), all (ISO, scenario, year) cells")
print("=" * 78)
print(f"  cells               : {d.size}")
print(f"  pi >  pi_dose       : {int((d > 0).sum())}")
print(f"  pi == pi_dose       : {int((d == 0).sum())}")
print(f"  pi <  pi_dose       : {int((d < 0).sum())}")
print(f"  max (pi - pi_dose)  : {d.max():+.6e}")
print(f"  min (pi - pi_dose)  : {d.min():+.6e}")
strict = bool((d >= 0).all())
print(f"  pi >= pi_dose on every cell: {strict}")
if not strict:
    bad = np.argwhere(d < 0)
    print(f"  counterexamples ({len(bad)}), first 10:")
    for r, c in bad[:10]:
        print(f"    {pi.index[r]} year {pi.columns[c]}: "
              f"pi={pi.to_numpy()[r, c]:.9f} pi_dose={dose.to_numpy()[r, c]:.9f}")

print()
print("=" * 78)
print("2. Consequence for the drug charge (national totals, break-even set)")
print("=" * 78)
# treated_user_years = initial_users * sum_y weight(y); the drug charge is
# proportional to that, so the ratio of sums IS the ratio of charges.
sum_pi = pi.sum(axis=1)
sum_dose = dose.sum(axis=1)

from data_visualization.drug_footprint import load_treated_users

users = load_treated_users().set_index(["ISO", "scenario"])["treated_users_initial"]
be = pd.read_csv(ROOT / "data_result" / "net_emissions_with_drug.csv",
                 float_precision="round_trip")
kg = ANNUAL_DRUG_KG_CO2E_PER_USER
for sc in ("max_uptake", "mod_uptake"):
    keep = be.loc[
        (be["scenario"] == sc)
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be["ratio_food_to_mort"]),
        "ISO",
    ]
    idx = pd.MultiIndex.from_product([sorted(keep), [sc]], names=["ISO", "scenario"])
    idx = idx.intersection(users.index)
    u = users.reindex(idx)
    correct = float((u * sum_dose.reindex(idx)).sum() * kg / 1000)
    wrong = float((u * sum_pi.reindex(idx)).sum() * kg / 1000)
    legacy = float((u * 10.0).sum() * kg / 1000)
    print(f"  {sc} (N={len(idx)}):")
    print(f"    10-yr drug charge with pi_dose (correct): {correct / 1e6:10.6f} Mt")
    print(f"    10-yr drug charge with pi     (wrong)  : {wrong / 1e6:10.6f} Mt"
          f"   -> {(wrong / correct - 1) * 100:+.3f}%")
    print(f"    10-yr drug charge legacy (x10)         : {legacy / 1e6:10.6f} Mt"
          f"   -> {(legacy / correct - 1) * 100:+.3f}%")
    verdict = "OVERSTATES" if wrong > correct else "UNDERSTATES"
    print(f"    => substituting pi {verdict} the drug charge.")
    print(f"       A larger drug charge is a larger subtraction from food savings,")
    print(f"       so it LOWERS net food savings and the food:survivor ratio.")
