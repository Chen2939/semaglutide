"""Old vs new 10-year survivor emissions, both read off CSVs (no model run).

The 'old' side is the HEAD blob of the survivor file, so the comparison holds the
OECD factors and the P&N add-back fixed and moves only the person-years.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NAME = "mortality model total emissions_oecd.csv"

blob = subprocess.run(
    ["git", "-C", str(ROOT), "show", f"HEAD:{NAME}"],
    capture_output=True, text=True, check=True,
).stdout
old = pd.read_csv(io.StringIO(blob))
new = pd.read_csv(ROOT / NAME)
print(f"  HEAD blob rows {old.shape}, working copy rows {new.shape}")

for scen in ("max_uptake", "mod_uptake"):
    o = old[old["scenario"] == scen]
    n = new[new["scenario"] == scen]
    ot = o["total_emissions"].sum()
    nt = n["total_emissions"].sum()
    print(f"  {scen}: 10-year survivor emissions "
          f"{ot / 1e6:>8.3f} -> {nt / 1e6:>8.3f} Mt CO2e   "
          f"(x{nt / ot:.4f}); ISO with a non-null total: "
          f"{int(o['total_emissions'].notna().sum())} -> {int(n['total_emissions'].notna().sum())}")

print()
print("  Per-country movement, max_uptake, countries with a factor in both:")
o = old[old["scenario"] == "max_uptake"].set_index("ISO")["total_emissions"]
n = new[new["scenario"] == "max_uptake"].set_index("ISO")["total_emissions"]
cmp = pd.DataFrame({"old_t": o, "new_t": n}).dropna(subset=["new_t"])
cmp["ratio"] = cmp["new_t"] / cmp["old_t"]
moved = cmp[(cmp["old_t"].isna()) | (cmp["old_t"] != cmp["new_t"])]
unchanged = cmp[cmp["old_t"] == cmp["new_t"]]
print(f"    unchanged bit-for-bit: {len(unchanged)}")
print(f"    moved or newly present: {len(moved)}")
print(moved.to_string(float_format=lambda v: f"{v:,.4f}"))
