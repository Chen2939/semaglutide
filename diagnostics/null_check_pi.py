"""HARD STOP 2 null check: with pi forced to 1.0, the survival-weighted pipeline
must reproduce the pre-pi pipeline's annual_food_savings_t bit-for-bit.

GATES, all declared before the run:

  N1  pi == 1.0 in every year, survival_weighted=True (so the new code path runs
      in full, 10 solves) vs the HEAD pipeline's single solve.
      Bar: exactly 0.0 on annual_food_savings_t, all rows.
      Rationale for exactly-0.0: at pi == 1.0 the shock is `base * 1.0`, which is
      the identical double, so the solver sees identical arguments and the code
      path is arithmetically the same. This is a value read and compared, not
      re-derived from separately-parsed components.

  N2  survival_weighted=False vs the HEAD pipeline. Bar: exactly 0.0.
      This began as the legacy lever. It is now a PRODUCTION PATH: Panel A of
      the emissions waterfall (generate_waterfall_1yr_figure) is built with
      survival_weighted=False as its no-mortality counterfactual, so this gate
      no longer guards a reproducibility toggle -- it guards a published figure.
      A regression here changes the manuscript, not just a test, and it changes
      it to a number that still looks reasonable. Must remain a strict no-op.

  N3  result_df's unsuffixed columns at pi == 1.0 vs HEAD, for every shared
      numeric column. Bar: exactly 0.0. Catches a year-1 wiring mistake that
      food_savings alone could hide.

  N4  Does any committed blob still carry an annual_food_savings_t that HEAD
      reproduces? Reported, not gated -- if none does, the food-side blobs are
      stale relative to HEAD and N1-N3 are the only clean references. Anchored to
      a committed column, read with float_precision='round_trip'.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization import _head_pipeline as head
from data_visualization import pipeline as work

ROOT = Path(__file__).resolve().parent.parent
KEY = ["ISO", "Country", "scenario"]
HORIZON = 10
pd.set_option("display.width", 220)

failures: list[str] = []


def gate(label: str, ok: bool) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(label)


def compare(a: pd.DataFrame, b: pd.DataFrame, col: str, label: str) -> int:
    m = a[KEY + [col]].merge(b[KEY + [col]], on=KEY, suffixes=("_a", "_b"), how="outer",
                             indicator=True)
    assert (m["_merge"] == "both").all(), f"{label}: row sets differ"
    x = m[f"{col}_a"].to_numpy(dtype=float)
    y = m[f"{col}_b"].to_numpy(dtype=float)
    both_nan = np.isnan(x) & np.isnan(y)
    ndiff = int(((x != y) & ~both_nan).sum())
    d = np.abs(x - y)
    print(f"    {label}: {len(m)} rows, differing {ndiff}, max abs "
          f"{np.nanmax(d) if len(d) else 0:.3e}")
    return ndiff


print("Running the HEAD (pre-pi) pipeline...")
head_food, head_result = head.compute_food_savings()

print("Running the survival-weighted pipeline with pi forced to 1.0...")
one = pd.DataFrame(
    1.0,
    index=pd.MultiIndex.from_frame(
        head_food[["ISO", "scenario"]].drop_duplicates()
    ),
    columns=list(range(1, HORIZON + 1)),
)
pi1_food, pi1_result = work.compute_food_savings(
    survival_weighted=True, horizon=HORIZON, survival_weight=one
)

print("Running the survival-weighted pipeline with survival_weighted=False...")
off_food, off_result = work.compute_food_savings(survival_weighted=False)

print()
print("=" * 78)
print("N1  pi == 1.0, full new code path, vs HEAD")
print("=" * 78)
n1 = compare(head_food, pi1_food, "annual_food_savings_t", "annual_food_savings_t")
gate("N1 annual_food_savings_t exactly 0.0 at pi == 1.0", n1 == 0)

print("  and the per-year series must all equal year 1 at pi == 1.0:")
series_bad = 0
for y in range(1, HORIZON + 1):
    a = pi1_food["annual_food_savings_t"].to_numpy(dtype=float)
    b = pi1_food[f"annual_food_savings_t_Y{y}"].to_numpy(dtype=float)
    nb = int((a != b).sum())
    series_bad += nb
    if nb:
        print(f"    Y{y}: {nb} rows differ")
print(f"    total differing cells across Y1..Y{HORIZON}: {series_bad}")
gate("N1b every year equals year 1 at pi == 1.0", series_bad == 0)

print()
print("=" * 78)
print("N2  survival_weighted=False vs HEAD")
print("=" * 78)
n2 = compare(head_food, off_food, "annual_food_savings_t", "annual_food_savings_t")
gate("N2 legacy lever is a strict no-op", n2 == 0)

print()
print("=" * 78)
print("N3  result_df unsuffixed columns at pi == 1.0 vs HEAD")
print("=" * 78)
shared = [
    c for c in head_result.columns
    if c in pi1_result.columns
    and pd.api.types.is_numeric_dtype(head_result[c])
    and not pd.api.types.is_bool_dtype(head_result[c])
]
print(f"  shared numeric columns: {len(shared)}")
assert len(head_result) == len(pi1_result), "result_df row count changed"
total_bad = 0
for c in shared:
    x = head_result[c].to_numpy(dtype=float)
    y = pi1_result[c].to_numpy(dtype=float)
    both_nan = np.isnan(x) & np.isnan(y)
    nb = int(((x != y) & ~both_nan).sum())
    total_bad += nb
    if nb:
        print(f"    {c}: {nb} differing, max abs "
              f"{np.nanmax(np.abs(x - y)):.3e}")
print(f"  total differing cells: {total_bad} of {len(shared) * len(head_result):,}")
gate("N3 result_df year-1 columns exactly 0.0 at pi == 1.0", total_bad == 0)

print()
print("=" * 78)
print("N4  Is any committed blob a valid anchor for annual_food_savings_t?")
print("=" * 78)
hf = head_food.set_index(["ISO", "scenario"])["annual_food_savings_t"]
candidates = [
    ("data_result/net_emissions_with_drug.csv", "annual_food_savings_gross_t", None),
    ("data_result/net_emissions_with_drug.csv", "annual_food_savings_gross_from_be_t", None),
    ("data_result/diet_sensitivity_results.csv", "annual_food_savings_t",
     ("diet_scenario", "baseline_uniform")),
]
for rel, col, filt in candidates:
    path = ROOT / rel
    if not path.is_file():
        print(f"  {rel}: absent")
        continue
    df = pd.read_csv(path, float_precision="round_trip")
    if col not in df.columns:
        print(f"  {rel} [{col}]: column absent")
        continue
    if filt:
        df = df[df[filt[0]] == filt[1]]
    s = df.set_index(["ISO", "scenario"])[col]
    common = hf.index.intersection(s.index)
    a = hf.loc[common].to_numpy(dtype=float)
    b = s.loc[common].to_numpy(dtype=float)
    nd = int((a != b).sum())
    rel_err = np.max(np.abs(b - a) / np.where(a != 0, np.abs(a), np.nan)) if len(a) else np.nan
    print(f"  {rel} [{col}]: {len(common)} common rows, differing {nd}, "
          f"max rel {rel_err:.3e}")

print()
print("=" * 78)
if failures:
    print(f"{len(failures)} GATE(S) FAILED:")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("All null gates passed.")
