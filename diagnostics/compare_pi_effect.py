"""Isolate the pi effect: same survivor data, survival weighting off vs on.

Step 1 (the mortality source swap) is already committed, so comparing against the
committed blobs would bundle two changes. This holds everything else fixed and
moves only pi, which is what "old vs new" has to mean for this change.

Also reports the 32 bucket-1 control countries separately: their survivor
emissions were bit-identical through step 1, so any ratio movement they show is
attributable to pi alone. EST, ISL, LUX and SVN are excluded (they moved by up to
1.4e-4 in step 1) and the 27 restored countries are not controls at all.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import compute_food_savings, load_mortality_emissions

ROOT = Path(__file__).resolve().parent.parent
pd.set_option("display.width", 240)

FLOORED = {"EST", "ISL", "LUX", "SVN"}
RESTORED = {
    "AND", "ARE", "ASM", "ATG", "BHR", "BHS", "BMU", "BRB", "BRN", "CYP", "GRL",
    "GUY", "KNA", "KWT", "MLT", "NRU", "OMN", "PAN", "PRI", "PYF", "QAT", "ROU",
    "SAU", "SGP", "SYC", "TTO", "URY",
}

mort = load_mortality_emissions("mean")

print("Running with survival weighting OFF (pi == 1, the old behaviour)...")
food_off, _ = compute_food_savings(survival_weighted=False)
be_off = compute_breakeven(food_off, mort, include_drug=True)

print("Running with survival weighting ON...")
food_on, _ = compute_food_savings(survival_weighted=True, horizon=10)
be_on = compute_breakeven(food_on, mort, include_drug=True)


def valid(be, sc):
    return be[
        (be["scenario"] == sc)
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be["ratio_food_to_mort"])
    ].copy()


print()
print("=" * 96)
print("Global aggregates, mean carbon intensity, drug folded in")
print("=" * 96)
rows = []
for sc in ("max_uptake", "mod_uptake"):
    a, b = valid(be_off, sc), valid(be_on, sc)
    assert set(a["ISO"]) == set(b["ISO"]), "country set moved -- investigate"
    rows.append({
        "scenario": sc,
        "N": len(b),
        "annual_t0_old_Mt": a["annual_food_savings_t"].sum() / 1e6,
        "annual_y1_new_Mt": b["annual_food_savings_t"].sum() / 1e6,
        "food10yr_old_Mt": a["total_food_savings_10yr"].sum() / 1e6,
        "food10yr_new_Mt": b["total_food_savings_10yr"].sum() / 1e6,
        "surv10yr_Mt": b["total_survivor_emissions_10yr"].sum() / 1e6,
        "drug10yr_old_Mt": a["total_drug_emissions_10yr"].sum() / 1e6,
        "drug10yr_new_Mt": b["total_drug_emissions_10yr"].sum() / 1e6,
    })
g = pd.DataFrame(rows)
g["ratio_old"] = g["food10yr_old_Mt"] / g["surv10yr_Mt"]
g["ratio_new"] = g["food10yr_new_Mt"] / g["surv10yr_Mt"]
g["ratio_pct_change"] = (g["ratio_new"] / g["ratio_old"] - 1) * 100
g["food10yr_pct_change"] = (g["food10yr_new_Mt"] / g["food10yr_old_Mt"] - 1) * 100
print(g.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

print()
print("=" * 96)
print("Year-10 annual (flow) ratio, and the annual food series")
print("=" * 96)
for sc in ("max_uptake", "mod_uptake"):
    a, b = valid(be_off, sc), valid(be_on, sc)
    for label, v in (("OFF", a), ("ON ", b)):
        cf = np.array([v[f"cum_food_Y{y}"].sum() for y in range(1, 11)])
        cm = np.array([v[f"cum_mort_Y{y}"].sum() for y in range(1, 11)])
        af, am = np.diff(cf, prepend=0.0), np.diff(cm, prepend=0.0)
        print(f"  {sc} {label}: annual food Y1 {af[0]/1e6:7.3f} -> Y10 "
              f"{af[-1]/1e6:7.3f} Mt;  y10 annual ratio "
              f"{af[-1]/am[-1]:6.4f};  cum10 ratio {cf[-1]/cm[-1]:6.4f}")

print()
print("=" * 96)
print("Break-even year and tipping counts")
print("=" * 96)
for sc in ("max_uptake", "mod_uptake"):
    a, b = valid(be_off, sc), valid(be_on, sc)
    for label, v in (("OFF", a), ("ON ", b)):
        tip = int((v["ratio_food_to_mort"] < 1).sum())
        allbe = bool(v["food_dominates_all_years"].all())
        mi = v.loc[v["ratio_food_to_mort"].idxmin()]
        print(f"  {sc} {label}: N={len(v)}  tipping(<1)={tip}  "
              f"all break even in Y1={allbe}  "
              f"min={mi['ratio_food_to_mort']:.4f} ({mi['ISO']} {mi['Country']})")

print()
print("=" * 96)
print("Controls: the 32 bucket-1 countries (step-1-identical survivor emissions)")
print("=" * 96)
for sc in ("max_uptake",):
    a, b = valid(be_off, sc), valid(be_on, sc)
    ctl = sorted((set(a["ISO"]) - FLOORED - RESTORED))
    print(f"  control countries present in the break-even set: {len(ctl)}")
    ai = a.set_index("ISO").loc[ctl]
    bi = b.set_index("ISO").loc[ctl]
    ratio_old = ai["total_food_savings_10yr"].sum() / ai["total_survivor_emissions_10yr"].sum()
    ratio_new = bi["total_food_savings_10yr"].sum() / bi["total_survivor_emissions_10yr"].sum()
    print(f"  survivor emissions identical across the two runs: "
          f"{bool((ai['total_survivor_emissions_10yr'] == bi['total_survivor_emissions_10yr']).all())}")
    print(f"  controls-only 10-yr ratio: {ratio_old:.4f} -> {ratio_new:.4f} "
          f"({(ratio_new/ratio_old - 1) * 100:+.2f}%)")
    per = pd.DataFrame({
        "ratio_old": ai["ratio_food_to_mort"],
        "ratio_new": bi["ratio_food_to_mort"],
    })
    per["pct"] = (per["ratio_new"] / per["ratio_old"] - 1) * 100
    print(f"  per-country ratio change: min {per['pct'].min():+.3f}%  "
          f"median {per['pct'].median():+.3f}%  max {per['pct'].max():+.3f}%")

be_on.to_csv(ROOT / "diagnostics" / "be_pi_on.csv", index=False)
be_off.to_csv(ROOT / "diagnostics" / "be_pi_off.csv", index=False)
print()
print("Wrote diagnostics/be_pi_{on,off}.csv")
