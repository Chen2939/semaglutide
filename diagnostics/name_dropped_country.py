"""Name the country that has both OECD factor components and non-zero survivor
person-years but no positive food savings, so the break-even set is 40 not 41.
Read-only; prints only.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_visualization.pipeline import compute_food_savings

ROOT = Path(__file__).resolve().parent.parent
DIFFS = [f"diff_Y{y}" for y in range(0, 11)]
FACTORS = ["oecd_nonfood_ghg_t_per_capita", "food_add_back_t_per_capita"]

food_savings, _ = compute_food_savings(survival_weighted=False)
oecd = pd.read_csv(ROOT / "mortality model total emissions_oecd.csv")

for scen in ("max_uptake", "mod_uptake"):
    fs = food_savings[food_savings["scenario"] == scen].set_index("ISO")
    o = oecd[oecd["scenario"] == scen].set_index("ISO")

    nonzero_py = o.index[o[DIFFS].abs().sum(axis=1) > 0]
    has_factor = o.index[o[FACTORS].notna().all(axis=1)]
    survivor_ok = set(nonzero_py) & set(has_factor)
    food_pos = set(fs.index[fs["annual_food_savings_t"] > 0])

    dropped = sorted(survivor_ok - food_pos)
    print(f"-- {scen} --")
    print(f"  survivor-side qualifying (person-years > 0 and both factors): "
          f"{len(survivor_ok)}")
    print(f"  of those with annual_food_savings_t > 0                    : "
          f"{len(survivor_ok & food_pos)}")
    print(f"  DROPPED: {dropped}")
    for iso in dropped:
        present = iso in fs.index
        val = float(fs.loc[iso, "annual_food_savings_t"]) if present else None
        print(f"    {iso}: present in food_savings = {present}; "
              f"annual_food_savings_t = {val}")

print()
print("Why: does FAOSTAT cover it?")
mapping = pd.read_csv(ROOT / "Food data" / "faostat_country_mapping.csv")
for iso in ("TWN", "USA"):
    hit = mapping[mapping["ISO"] == iso]
    print(f"  {iso}: {len(hit)} row(s) in faostat_country_mapping.csv"
          + (f" -> Area={list(hit['Area'])}" if len(hit) else ""))
