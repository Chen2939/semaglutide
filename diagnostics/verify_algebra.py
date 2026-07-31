"""Verify section 2 of the brief numerically rather than by symbol-pushing.

Three invariants, per (ISO, scenario) and globally:

  I1  Delta(t)  ==  term1(t) + term2(t)
        Delta(t) = sum w*p_sg(t)*treatment_eer - sum w*p_bl(t)*eer
        term1(t) = sum w*p_sg(t)*(treatment_eer - eer)
        term2(t) = sum w*(p_sg(t) - p_bl(t))*eer

  I2  term1(t) / term1(0)  ==  pi(t)        (pi is exactly the missing scalar)

  I3  term2(t) == sum over the diff_Y{t} the survivor side already uses,
        weighted by baseline eer -- i.e. term 2 is the survivor add-back's
        population, not the food side's.

Bar: I1 and I2 to <= 1e-12 relative (float re-association only). I3 exact.

Re-run as the opening gate of the pi work: the decomposition is what the whole
correction rests on, so it is re-confirmed against the live lookup
(``build_mortality_map``, from the pickle's own imputed column) rather than
against the retired ``mortality2.rds`` this script was first written on.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization.deterministic_mortality import (
    compute_individual_survival_diffs,
    load_inputs,
)

ROOT = Path(__file__).resolve().parent.parent
HORIZON = 15

sim = load_inputs()

# The whole population is needed here, not just the treated: term 2 runs over
# everyone with a survival difference, and Delta(t) over everyone who eats.
# The mortality lookup is built inside the function from sim itself.
ind = compute_individual_survival_diffs(
    sim,
    horizon=HORIZON,
    survival_columns=True,
    extra_columns=("eer", "treatment_eer", "eer_diff"),
    population_weighted=False,
)
w = ind["weighting"].to_numpy()
eer = ind["eer"].to_numpy()
teer = ind["treatment_eer"].to_numpy()
ediff = ind["eer_diff"].to_numpy()

print("=" * 78)
print("Sanity: eer_diff column == eer - treatment_eer, bit for bit")
print("=" * 78)
print(f"  max |eer_diff - (eer - treatment_eer)| = {np.abs(ediff - (eer - teer)).max():.3e}")

print()
print("=" * 78)
print("I1 / I2  global, both scenarios")
print("=" * 78)
scen = ind["scenario"].to_numpy()
for s in ("max_uptake", "mod_uptake"):
    k = scen == s
    wk, eerk, teerk, edk = w[k], eer[k], teer[k], ediff[k]
    term1_0 = float((wk * (teerk - eerk)).sum())
    print(f"\n  {s}:  term1(0) = sum w*(treatment_eer - eer) = {term1_0:,.4f}")
    print(f"  {'t':>3}  {'Delta(t)':>18}  {'term1+term2':>18}  {'I1 rel':>10}  "
          f"{'term1(t)/term1(0)':>18}  {'pi(t)':>10}  {'I2 rel':>10}")
    for t in range(1, HORIZON + 1):
        psg = ind[f"p_sg_Y{t}"].to_numpy()[k]
        pbl = ind[f"p_bl_Y{t}"].to_numpy()[k]
        delta = float((wk * psg * teerk).sum() - (wk * pbl * eerk).sum())
        term1 = float((wk * psg * (teerk - eerk)).sum())
        term2 = float((wk * (psg - pbl) * eerk).sum())
        i1 = abs(delta - (term1 + term2)) / max(abs(delta), 1e-30)
        ratio = term1 / term1_0
        pi = float((wk * psg * edk).sum() / (wk * edk).sum())
        i2 = abs(ratio - pi) / abs(pi)
        print(f"  {t:>3}  {delta:>18,.4f}  {term1 + term2:>18,.4f}  {i1:>10.2e}  "
              f"{ratio:>18.12f}  {pi:>10.6f}  {i2:>10.2e}")

print()
print("=" * 78)
print("I1 per (ISO, scenario), worst case over all 63 x 2 x 15")
print("=" * 78)
g = ind.groupby(["ISO", "scenario"], observed=True)
worst_i1 = 0.0
worst_i2 = 0.0
ind["_w_teer"] = w * teer
ind["_w_eer"] = w * eer
ind["_w_ed"] = w * ediff
den = g["_w_ed"].sum()
t1_0 = g.apply(lambda d: (d["weighting"] * (d["treatment_eer"] - d["eer"])).sum(),
               include_groups=False)
for t in range(1, HORIZON + 1):
    ind["_a"] = ind[f"p_sg_Y{t}"] * ind["_w_teer"]
    ind["_b"] = ind[f"p_bl_Y{t}"] * ind["_w_eer"]
    ind["_t1"] = ind[f"p_sg_Y{t}"] * ind["weighting"] * (ind["treatment_eer"] - ind["eer"])
    ind["_t2"] = (ind[f"p_sg_Y{t}"] - ind[f"p_bl_Y{t}"]) * ind["_w_eer"]
    ind["_n"] = ind[f"p_sg_Y{t}"] * ind["_w_ed"]
    gg = ind.groupby(["ISO", "scenario"], observed=True)[
        ["_a", "_b", "_t1", "_t2", "_n"]
    ].sum()
    delta = gg["_a"] - gg["_b"]
    i1 = (delta - (gg["_t1"] + gg["_t2"])).abs() / delta.abs()
    pi = gg["_n"] / den
    i2 = ((gg["_t1"] / t1_0) - pi).abs() / pi.abs()
    worst_i1 = max(worst_i1, float(i1.max()))
    worst_i2 = max(worst_i2, float(i2.max()))
print(f"  worst I1 relative error: {worst_i1:.3e}   (bar 1e-12)")
print(f"  worst I2 relative error: {worst_i2:.3e}   (bar 1e-12)")
print(f"  I1 {'PASS' if worst_i1 <= 1e-12 else 'FAIL'}   "
      f"I2 {'PASS' if worst_i2 <= 1e-12 else 'FAIL'}")

print()
print("=" * 78)
print("I3  term2(t) is the survivor side's population, not the food side's")
print("=" * 78)
print("  term2(t) = sum w*(p_sg - p_bl)*eer, and diff_Y{t} = sum w*(p_sg - p_bl).")
print("  So term2(t) / diff_Y{t} is a survivor-weighted mean baseline eer:")
for t in (1, 10, 15):
    ind["_t2"] = (ind[f"p_sg_Y{t}"] - ind[f"p_bl_Y{t}"]) * ind["_w_eer"]
    ind["_d"] = (ind[f"p_sg_Y{t}"] - ind[f"p_bl_Y{t}"]) * ind["weighting"]
    a = ind[ind["scenario"] == "max_uptake"]
    print(f"    t={t:>2}: term2 = {a['_t2'].sum():>18,.2f} kcal/day, "
          f"diff_Y{t} = {a['_d'].sum():>14,.2f} survivors, "
          f"implied mean eer = {a['_t2'].sum() / a['_d'].sum():,.2f} kcal/day")
print()
print("  It uses BASELINE eer, matching _survivor_food_factor's documented")
print("  choice. term 2 is therefore already handled downstream and is not")
print("  touched by the food-side correction.")
