"""Measure before choosing: exact per-year re-solve vs scaling the result by pi.

Route 1 (exact)       -- re-solve the equilibrium each year with delta*pi(t).
                         _compute_equilibrium runs 15x (or 10x) more often.
Route 2 (approximate) -- solve once, scale annual_food_savings_t by pi(t).
                         Near-linear in delta, so the error should be small.

Reports the row count into the apply, the wall clock of one compute_food_savings,
the isolated cost of the apply itself, and the relative error of route 2 against
route 1 -- for one named country and food group at pi = 0.86 as specified, and
then across every row so the single case is not mistaken for the worst case.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization.pipeline import (
    _compute_equilibrium,
    compute_food_savings,
)

ROOT = Path(__file__).resolve().parent.parent
PI = 0.86
pd.set_option("display.width", 220)

print("=" * 78)
print("Cost")
print("=" * 78)
t0 = time.perf_counter()
food_savings, result_df = compute_food_savings()
whole = time.perf_counter() - t0
print(f"  compute_food_savings() whole call        : {whole:6.1f} s")
print(f"  rows into result_df.apply(_compute_equilibrium, axis=1): {len(result_df):,}")

solvable = result_df[result_df["Cs"].notna() & result_df["Cd"].notna()]
t0 = time.perf_counter()
result_df.apply(_compute_equilibrium, axis=1)
apply_only = time.perf_counter() - t0
print(f"  the apply alone, once                    : {apply_only:6.1f} s")
print(f"  rows that actually solve (Cs, Cd present): {len(solvable):,}")
print(f"  implied cost of a 10-year exact route    : {apply_only * 10:6.1f} s "
      f"extra  ({apply_only * 10 / whole * 100:.0f}% of one current call)")
print(f"  implied cost of a 15-year exact route    : {apply_only * 15:6.1f} s extra")

print()
print("=" * 78)
print(f"Accuracy of route 2, one named row, pi = {PI}")
print("=" * 78)


def solve_one(row, shock):
    r = row.copy()
    r["expected_demand_reduction_percent"] = shock
    out = _compute_equilibrium(r)
    return float(out["Q_eql_new"])


# A real, large, non-degenerate row: the biggest Meat reduction in the set.
cand = solvable[
    (solvable["final_food_group"] == "Meat")
    & (solvable["scenario"] == "max_uptake")
    & solvable["expected_demand_reduction_percent"].notna()
].copy()
cand["mag"] = (cand["initial_eql_quantity"] * cand["expected_demand_reduction_percent"]).abs()
row = cand.loc[cand["mag"].idxmax()]
print(f"  {row['Country']} ({row['ISO']}), {row['final_food_group']}, {row['scenario']}")
print(f"    initial quantity  {row['initial_eql_quantity']:,.1f} t")
print(f"    delta             {row['expected_demand_reduction_percent']:+.9f}")
print(f"    Es {row['elasticity_supply']:.3f}   Ed {row['elasticity_demand']:.3f}"
      f"   price {row['price']:.3f}")

q0 = float(row["initial_eql_quantity"])
delta = float(row["expected_demand_reduction_percent"])
q_base = solve_one(row, delta)
q_exact = solve_one(row, delta * PI)
red_base = q_base - q0
red_exact = q_exact - q0
red_approx = PI * red_base
err = abs(red_approx - red_exact) / abs(red_exact)
print()
print(f"    actual_reduction at delta          : {red_base:,.4f} t")
print(f"    route 1  solve(pi*delta) - q0      : {red_exact:,.4f} t")
print(f"    route 2  pi * (solve(delta) - q0)  : {red_approx:,.4f} t")
print(f"    relative error of route 2          : {err:.6e}  ({err * 100:.4f}%)")

print()
print("=" * 78)
print(f"Accuracy across every solvable row at pi = {PI}")
print("=" * 78)
sub = solvable[solvable["expected_demand_reduction_percent"].notna()].copy()
errs = []
for _, r in sub.iterrows():
    q0 = float(r["initial_eql_quantity"])
    d = float(r["expected_demand_reduction_percent"])
    if not np.isfinite(q0) or d == 0:
        continue
    rb = solve_one(r, d) - q0
    re_ = solve_one(r, d * PI) - q0
    if not np.isfinite(rb) or not np.isfinite(re_) or re_ == 0:
        continue
    errs.append(abs(PI * rb - re_) / abs(re_))
errs = np.array(errs)
print(f"  rows compared: {len(errs):,}")
for q in (50, 90, 99, 100):
    print(f"    p{q:<3} relative error = {np.percentile(errs, q):.6e}"
          f"  ({np.percentile(errs, q) * 100:.4f}%)")
print(f"    mean               = {errs.mean():.6e}")

print()
print("  Aggregate effect: what route 2 would do to the global annual saving")
print("  if it were used at pi = 0.86 uniformly.")
ci = sub["carbon_intensity_t"].to_numpy(dtype=float)
q0a = sub["initial_eql_quantity"].to_numpy(dtype=float)
da = sub["expected_demand_reduction_percent"].to_numpy(dtype=float)
ex, ap = [], []
for i, (_, r) in enumerate(sub.iterrows()):
    if not np.isfinite(ci[i]):
        continue
    rb = solve_one(r, da[i]) - q0a[i]
    re_ = solve_one(r, da[i] * PI) - q0a[i]
    if not (np.isfinite(rb) and np.isfinite(re_)):
        continue
    ex.append(abs(re_ * ci[i]))
    ap.append(abs(PI * rb * ci[i]))
ex_t, ap_t = float(np.sum(ex)), float(np.sum(ap))
print(f"    route 1 total: {ex_t / 1e6:,.6f} Mt")
print(f"    route 2 total: {ap_t / 1e6:,.6f} Mt")
print(f"    relative difference on the aggregate: "
      f"{abs(ap_t - ex_t) / ex_t:.6e}  ({abs(ap_t - ex_t) / ex_t * 100:.4f}%)")
