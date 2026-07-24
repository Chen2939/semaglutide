"""Fix #3 delta verification (no equilibrium; pure pool arithmetic).

Prints per country the dilution factor (adult+child)/adult and the ratio of
new delta to old delta. Identity: new/old = adult/(adult+child) = 1/dilution
(the treatment term cancels), so it is scenario-independent.
Expected new/old ~ 0.85. Flags anything near 0.79 (pop-share proxy) or
0.64 (FAOSTAT over-correction).
"""
from pathlib import Path
import numpy as np
import pandas as pd
import pyreadr

ROOT = Path(r"C:\Users\sethw\repos")

sim = list(pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values())[0]
sim["w_eer"] = sim["weighting"] * sim["eer"]
sim["w_teer"] = sim["weighting"] * sim["treatment_eer"]
pools = (sim.groupby(["ISO", "scenario"])
         .agg(w=("w_eer", "sum"), wt=("w_teer", "sum")).reset_index())

child = pd.read_excel(ROOT / "Food data" / "child_energy_by_country.xlsx")
child_daily = (child.set_index("ISO3")["total_annual_child_kcal"] / 365.0)

pools["child"] = pools["ISO"].map(child_daily)
pools = pools.dropna(subset=["child"])          # keep the 56 in-scope
pools["old_delta"] = pools["wt"] / pools["w"] - 1
pools["new_delta"] = (pools["wt"] + pools["child"]) / (pools["w"] + pools["child"]) - 1
pools["dilution"] = (pools["w"] + pools["child"]) / pools["w"]
pools["new_over_old"] = pools["new_delta"] / pools["old_delta"]

mx = pools[pools["scenario"] == "max_uptake"].copy().sort_values("new_over_old")

def flag(r):
    if abs(r - 0.64) < 0.02: return "  <-- ~0.64 FAOSTAT?!"
    if abs(r - 0.79) < 0.015: return "  <-- ~0.79 pop-share?!"
    return ""

print(f"\n{'ISO':<5}{'adult_daily_kcal':>20}{'child_daily_kcal':>20}"
      f"{'dilution':>11}{'new/old':>10}{'old_delta':>12}{'new_delta':>12}")
print("-" * 92)
for _, r in mx.iterrows():
    print(f"{r.ISO:<5}{r.w:>20,.0f}{r.child:>20,.0f}{r.dilution:>11.4f}"
          f"{r.new_over_old:>10.4f}{r.old_delta:>12.5f}{r.new_delta:>12.5f}"
          f"{flag(r.new_over_old)}")

print("-" * 92)
print(f"n countries: {len(mx)}")
print(f"new/old   : median {mx.new_over_old.median():.4f}  mean {mx.new_over_old.mean():.4f}"
      f"  min {mx.new_over_old.min():.4f} ({mx.iloc[0].ISO})"
      f"  max {mx.new_over_old.max():.4f} ({mx.iloc[-1].ISO})")
print(f"dilution  : median {mx.dilution.median():.4f}  min {mx.dilution.min():.4f}"
      f"  max {mx.dilution.max():.4f}")
near79 = mx[(mx.new_over_old - 0.79).abs() < 0.015]
near64 = mx[(mx.new_over_old - 0.64).abs() < 0.02]
print(f"countries near 0.79 (pop-share): {len(near79)}   near 0.64 (FAOSTAT): {len(near64)}")
# confirm scenario-independence of the ratio
md = pools[pools.scenario == "mod_uptake"][["ISO", "new_over_old"]].rename(
    columns={"new_over_old": "ratio_mod"})
chk = mx[["ISO", "new_over_old"]].merge(md, on="ISO")
print(f"max identical to mod ratio (scenario-independent): "
      f"{np.allclose(chk.new_over_old, chk.ratio_mod)}")
mx.to_csv(ROOT / "outputs" / "fix3" / "delta_verification.csv", index=False)
print("wrote outputs/fix3/delta_verification.csv")
