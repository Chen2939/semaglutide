"""Why does the production pi differ from the hard-stop-1 CSV by 1 ULP?

Two candidate causes, separated:

  A  The reference is a CSV round-trip. pandas read_csv defaults to
     float_precision=None (fast xstrtod), which can land one ULP off an exact
     strtod. Re-read with float_precision='round_trip' and see if it closes.

  B  Summation association. Hard stop 1 summed over the 350,424 rows with a
     non-zero treatment effect; the production builder sums over all 1,890,000.
     The extra terms are exact zeros, but numpy's pairwise summation blocks by
     index, so inserting zeros moves the block boundaries and changes which
     partial sums are formed.

Read-only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_visualization.deterministic_mortality import (
    compute_individual_survival_diffs,
    load_inputs,
)
from data_visualization.survival_weighting import (
    PI_HORIZON,
    build_food_shock_survival_weight,
)

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "diagnostics" / "pi_by_country_pkl.csv"
COLS = [f"pi_Y{t}" for t in range(1, PI_HORIZON + 1)]

pi = build_food_shock_survival_weight()
wide = pi.pivot(index=["ISO", "scenario"], columns="year", values="pi")
wide.columns = COLS


def report(label: str, a: np.ndarray, b: np.ndarray) -> None:
    d = a - b
    ad = np.abs(d)
    nz = a != 0
    rel = np.zeros_like(ad)
    rel[nz] = ad[nz] / np.abs(a[nz])
    ulp = np.zeros_like(ad)
    ulp[nz] = ad[nz] / np.spacing(np.abs(a[nz]))
    print(f"  {label}")
    print(f"    cells differing : {int((a != b).sum()):>5} / {a.size}")
    print(f"    max abs         : {ad.max():.3e}")
    print(f"    max rel         : {rel.max():.3e}")
    print(f"    max ULP distance: {ulp.max():.2f}")
    pos = int((d > 0).sum())
    neg = int((d < 0).sum())
    print(f"    sign of (ref - new): {pos} positive, {neg} negative "
          f"-> {'MIXED' if pos and neg else 'ONE-SIDED (drift)'}")
    print(f"    mean signed diff: {d.mean():+.3e}  (drift would show here)")


print("=" * 78)
print("A. Reference re-read with each parser")
print("=" * 78)
new = wide[COLS].to_numpy(dtype=float)
for fp in (None, "round_trip"):
    ref = pd.read_csv(REF, float_precision=fp).set_index(["ISO", "scenario"])
    a = ref.loc[wide.index, COLS].to_numpy(dtype=float)
    report(f"float_precision={fp!r}", a, new)

print()
print("=" * 78)
print("B. Subset vs full frame, both in memory, no CSV anywhere")
print("=" * 78)
sim = load_inputs()

full = compute_individual_survival_diffs(
    sim, horizon=PI_HORIZON, survival_columns=True,
    extra_columns=("eer_diff",), population_weighted=False,
)
full["w_diff"] = full["weighting"] * full["eer_diff"]

sub = full[full["eer_diff"] != 0].copy()
print(f"  full rows {len(full):,}   subset rows {len(sub):,}")


def pi_from(frame: pd.DataFrame) -> np.ndarray:
    key = ["ISO", "scenario"]
    den = frame.groupby(key, observed=True)["w_diff"].sum()
    out = {}
    for t in range(1, PI_HORIZON + 1):
        frame = frame.assign(_n=frame["w_diff"] * frame[f"p_sg_Y{t}"])
        out[f"pi_Y{t}"] = frame.groupby(key, observed=True)["_n"].sum() / den
    return pd.DataFrame(out).sort_index()


pi_full = pi_from(full)
pi_sub = pi_from(sub)
report("full-frame vs subset (in memory)", pi_sub.to_numpy(float), pi_full.to_numpy(float))

print()
print("  Is the production builder identical to the in-memory full-frame sum?")
prod = wide[COLS].sort_index().to_numpy(float)
print(f"    cells differing: {int((prod != pi_full.sort_index().to_numpy(float)).sum())}"
      f" / {prod.size}")

print()
print("=" * 78)
print("C. Conclusion")
print("=" * 78)
print("  If A closes to 0 under round_trip, the CSV parse is the whole story and")
print("  the hard-stop-1 values were never actually different -- only their text")
print("  form was. If B is non-zero, summation association contributes too, and")
print("  the correct bar is <=1 ULP with mixed sign and no drift, not exactly 0.")
