"""Read survivor coverage straight off the regenerated CSVs. No model runs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DIFFS = [f"diff_Y{y}" for y in range(0, 11)]
FACTORS = ["oecd_nonfood_ghg_t_per_capita", "food_add_back_t_per_capita"]
FIVE = ["ARE", "CYP", "MLT", ROU_ := "ROU", "SAU"]
pd.set_option("display.width", 220)

new = pd.read_csv(ROOT / "mortality model total emissions_oecd.csv")
old = pd.read_csv(ROOT / "diagnostics" / "person_years_old.csv")

print("=" * 78)
print("Columns of the regenerated survivor file")
print("=" * 78)
print(f"  shape {new.shape}")
print("  factor columns present:", [c for c in FACTORS if c in new.columns])

print()
print("=" * 78)
print("Coverage, max_uptake, read off the CSV")
print("=" * 78)
for scen in ("max_uptake", "mod_uptake"):
    n = new[new["scenario"] == scen].set_index("ISO")
    o = old[old["scenario"] == scen].set_index("ISO")
    py_new = n[DIFFS].abs().sum(axis=1) > 0
    py_old = o[DIFFS].abs().sum(axis=1) > 0
    both_f = n[FACTORS].notna().all(axis=1)
    e10 = n["emissions_Y10"].notna()
    qual_new = py_new & both_f
    qual_old = py_old.reindex(n.index).fillna(False) & both_f
    print(f"\n  -- {scen} --")
    print(f"    ISO rows in file                              {len(n)}")
    print(f"    non-zero person-years            old {int(py_old.sum()):>3}   new {int(py_new.sum()):>3}")
    print(f"    both factor components non-null                {int(both_f.sum())}")
    print(f"    non-zero emissions_Y10 non-null                {int(e10.sum())}")
    print(f"    QUALIFY (non-zero person-years AND both factors):"
          f"  old {int(qual_old.sum()):>3}   new {int(qual_new.sum()):>3}")
    gained = sorted(set(n.index[qual_new]) - set(n.index[qual_old]))
    print(f"    newly qualifying ({len(gained)}): {gained}")
    if scen == "max_uptake":
        print(f"    the five named in the brief: "
              + ", ".join(
                  f"{i}={'YES' if bool(qual_new.get(i, False)) else 'no'}" for i in FIVE
              ))

print()
print("=" * 78)
print("Countries with non-zero person-years but NO factors (cannot contribute)")
print("=" * 78)
n = new[new["scenario"] == "max_uptake"].set_index("ISO")
pyn = n[DIFFS].abs().sum(axis=1) > 0
nof = ~n[FACTORS].notna().all(axis=1)
print(f"  {int((pyn & nof).sum())} ISO: {sorted(n.index[pyn & nof])}")
print("  These lack an OECD demand-based per-capita factor, which is a separate")
print("  gap from the mortality one and is unchanged by this edit.")

print()
print("=" * 78)
print("The five: person-years and 10-year survivor emissions now on the file")
print("=" * 78)
cols = ["diff_Y1", "diff_Y10", "emissions_factor_Y0", "emissions_Y10", "total_emissions"]
print(n.loc[[i for i in FIVE if i in n.index], cols].to_string(
    float_format=lambda v: f"{v:,.4f}"))

print()
print("=" * 78)
print("Global survivor emissions, max_uptake, from the CSV")
print("=" * 78)
for scen in ("max_uptake", "mod_uptake"):
    s = new[new["scenario"] == scen]
    print(f"  {scen}: total_emissions summed over {int(s['total_emissions'].notna().sum())} "
          f"ISO with a factor = {s['total_emissions'].sum() / 1e6:,.3f} Mt CO2e (10-year)")
