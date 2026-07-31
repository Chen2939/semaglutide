"""Null check for the downstream rewiring: per-year accumulation, the drug term,
and the eight annual-x-10 aggregate sites must all be inert at pi == 1.

GATES, declared before the run:

  D1  build_drug_emissions(survival_weighted=False) reproduces the HEAD function
      exactly, including drug_emissions_1yr_t and drug_emissions_10yr_t.
      Bar: exactly 0.0.
  D2  At pi_dose == 1, the per-year drug series is constant and its sum equals the
      legacy initial_users x 10. Bar: exactly 0.0.
  D3  compute_breakeven on a pi == 1 food frame reproduces the HEAD
      compute_breakeven exactly, every numeric column. Bar: exactly 0.0.
  D4  The replaced aggregate sites: at pi == 1, sum(total_food_savings_10yr)
      equals sum(annual_food_savings_t) x 10 to <= 4 ULP per row, mixed sign, no
      drift, with the aggregate agreeing to <= 1e-15 relative. NOT exactly 0.0,
      and the reason is declared in advance: cum_food is built by ten sequential
      additions while the old form multiplied by 10, and repeated addition of a
      double is not bit-identical to multiplying it by an integer. The error bound
      for n sequential additions grows like n*eps, so a few ULP at n = 10 is
      expected; the brief's "<= 1 ulp" row covers a restructured expression, not a
      change from one multiply to a ten-term accumulation. Unlike the drug term
      below, this one cannot be anchored: under real pi the ten addends genuinely
      differ, so accumulation is the correct algorithm and not a choice.
      This is the only gate here not held to 0.0.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization import _head_breakeven as head_be
from data_visualization import _head_drug as head_drug
from data_visualization import _head_pipeline as head_pipe
from data_visualization import breakeven_analysis as work_be
from data_visualization import drug_footprint as work_drug
from data_visualization import pipeline as work_pipe

ROOT = Path(__file__).resolve().parent.parent
HORIZON = 10
pd.set_option("display.width", 220)
failures: list[str] = []


def gate(label: str, ok: bool) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(label)


def diff_all(a: pd.DataFrame, b: pd.DataFrame, key: list[str], label: str) -> int:
    cols = [
        c for c in a.columns
        if c in b.columns and c not in key
        and pd.api.types.is_numeric_dtype(a[c]) and not pd.api.types.is_bool_dtype(a[c])
    ]
    m = a[key + cols].merge(b[key + cols], on=key, suffixes=("_a", "_b"))
    assert len(m) == len(a) == len(b), f"{label}: row sets differ"
    total = 0
    for c in cols:
        x = m[f"{c}_a"].to_numpy(dtype=float)
        y = m[f"{c}_b"].to_numpy(dtype=float)
        nn = np.isnan(x) & np.isnan(y)
        nb = int(((x != y) & ~nn).sum())
        total += nb
        if nb:
            print(f"    {c}: {nb} differing, max abs {np.nanmax(np.abs(x - y)):.3e}")
    print(f"  {label}: {len(cols)} numeric columns x {len(m)} rows, "
          f"differing {total}")
    return total


print("=" * 78)
print("D1  drug footprint, legacy lever vs HEAD")
print("=" * 78)
hd = head_drug.build_drug_emissions()
wd_off = work_drug.build_drug_emissions(survival_weighted=False, horizon=HORIZON)
n1 = diff_all(hd, wd_off, ["ISO", "scenario"], "HEAD vs survival_weighted=False")
gate("D1 drug legacy lever exactly 0.0", n1 == 0)

print()
print("=" * 78)
print("D2  per-year drug series is constant at pi_dose == 1")
print("=" * 78)
one_idx = pd.MultiIndex.from_frame(hd[["ISO", "scenario"]].drop_duplicates())
one = pd.DataFrame(1.0, index=one_idx, columns=list(range(1, HORIZON + 1)))
wd_one = work_drug.build_drug_emissions(
    survival_weighted=True, horizon=HORIZON, survival_weight=one
)
bad = 0
for y in range(1, HORIZON + 1):
    a = wd_one["drug_emissions_1yr_t"].to_numpy(dtype=float)
    b = wd_one[f"drug_emissions_t_Y{y}"].to_numpy(dtype=float)
    bad += int((a != b).sum())
print(f"  per-year vs 1yr, cells differing across Y1..Y{HORIZON}: {bad}")
n2 = diff_all(hd, wd_one, ["ISO", "scenario"], "HEAD vs pi_dose == 1")
gate("D2 per-year drug series constant and equal to HEAD at pi_dose == 1",
     bad == 0 and n2 == 0)

print()
print("=" * 78)
print("D3  compute_breakeven at pi == 1 vs HEAD")
print("=" * 78)
print("  running the HEAD pipeline + HEAD breakeven...")
head_food, _ = head_pipe.compute_food_savings()
mort = work_pipe.load_mortality_emissions("mean")
# _head_breakeven does `from .drug_footprint import build_drug_emissions`, which
# resolves to the LIVE module -- so without this it would silently pick up the new
# survival-weighted default and the comparison would be pi_dose vs 1 rather than
# 1 vs 1. Point it at the genuine HEAD drug function.
head_be.build_drug_emissions = head_drug.build_drug_emissions
be_head = head_be.compute_breakeven(head_food, mort, include_drug=True)

print("  running the pi == 1 pipeline + new breakeven...")
pi_one = pd.DataFrame(
    1.0,
    index=pd.MultiIndex.from_frame(head_food[["ISO", "scenario"]].drop_duplicates()),
    columns=list(range(1, HORIZON + 1)),
)
work_food, _ = work_pipe.compute_food_savings(
    survival_weighted=True, horizon=HORIZON, survival_weight=pi_one
)
# The drug side must also be at pi_dose == 1 for this comparison to isolate the
# accumulation change; monkeypatch the loader the new breakeven calls.
_orig = work_drug.build_drug_emissions
work_drug.build_drug_emissions = lambda *a, **k: _orig(
    survival_weighted=True, horizon=HORIZON, survival_weight=one
)
work_be.build_drug_emissions = work_drug.build_drug_emissions
try:
    be_work = work_be.compute_breakeven(work_food, mort, include_drug=True)
finally:
    work_drug.build_drug_emissions = _orig
    work_be.build_drug_emissions = _orig

n3 = diff_all(be_head, be_work, ["ISO", "Country", "scenario"],
              "HEAD vs new at pi == 1")
gate("D3 compute_breakeven exactly 0.0 at pi == 1", n3 == 0)

print()
print("=" * 78)
print("D4  aggregate sites: summed series vs annual x 10 at pi == 1")
print("=" * 78)
sub = be_work[
    np.isfinite(be_work["ratio_food_to_mort"])
    & (be_work["annual_food_savings_t"] > 0)
    & (be_work["total_survivor_emissions_10yr"] > 0)
]
a = sub["annual_food_savings_t"].to_numpy(dtype=float) * 10.0
b = sub["total_food_savings_10yr"].to_numpy(dtype=float)
d = b - a
ulp = np.abs(d) / np.spacing(np.abs(a))
pos, neg = int((d > 0).sum()), int((d < 0).sum())
print(f"  rows: {len(sub)};  differing: {int((a != b).sum())}")
print(f"  max ULP distance: {ulp.max():.2f}")
print(f"  sign: {pos} positive, {neg} negative -> "
      f"{'MIXED' if pos and neg else 'one-sided'}")
print(f"  mean signed diff: {d.mean():+.3e}   relative: "
      f"{np.max(np.abs(d) / a):.3e}")
agg_old = sub["annual_food_savings_t"].sum() * 10
agg_new = sub["total_food_savings_10yr"].sum()
print(f"  aggregate: annual x 10 = {agg_old:,.6f};  summed = {agg_new:,.6f}")
print(f"  aggregate relative difference: {abs(agg_new - agg_old) / agg_old:.3e}")
gate("D4 summed series equals annual x 10 to <= 4 ULP per row at pi == 1",
     bool(ulp.max() <= 4.0))
gate("D4b differences are mixed-sign (float association, not drift)",
     pos > 0 and neg > 0)
gate("D4c aggregate agrees to <= 1e-15 relative",
     bool(abs(agg_new - agg_old) / agg_old <= 1e-15))

print()
print("=" * 78)
if failures:
    print(f"{len(failures)} GATE(S) FAILED:")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("All downstream null gates passed.")
