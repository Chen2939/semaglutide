"""Baseline food emissions must be delta-independent, so pi must not move them.

If they moved, pi has leaked into the baseline tonnage or the carbon intensities
and every derived number is suspect. Bar: exactly 0.0 between survival weighting
off and on.

Separately reports the gap against the old reference value 6510.9065615889995,
which predates commits 6e826a4 and be44eb4 -- the two food-side fixes the README
records as having made the reference snapshots stale.
"""

from __future__ import annotations

import pandas as pd

from data_visualization.pipeline import compute_food_savings
from reference.metrics import baseline_food_emissions_mt

OLD_REFERENCE = 6510.9065615889995

_, rdf_off = compute_food_savings(survival_weighted=False)
_, rdf_on = compute_food_savings(survival_weighted=True, horizon=10)

off = baseline_food_emissions_mt(rdf_off)
on = baseline_food_emissions_mt(rdf_on)

print(f"  rows: off {len(rdf_off):,}   on {len(rdf_on):,}")
print(f"  baseline food emissions, weighting OFF: {off!r}")
print(f"  baseline food emissions, weighting ON : {on!r}")
print(f"  identical: {off == on}")
print()
for col in ("initial_eql_quantity", "carbon_intensity_t"):
    a = rdf_off[col].to_numpy(dtype=float)
    b = rdf_on[col].to_numpy(dtype=float)
    import numpy as np
    nn = np.isnan(a) & np.isnan(b)
    print(f"  {col}: cells differing {int(((a != b) & ~nn).sum())} of {len(a)}")
print()
print(f"  old reference value: {OLD_REFERENCE!r}")
print(f"  current            : {on!r}")
print(f"  relative gap       : {abs(on - OLD_REFERENCE) / OLD_REFERENCE:.3e} "
      f"({(on / OLD_REFERENCE - 1) * 100:+.4f}%)")
print()
if off != on:
    raise SystemExit("FAILED: pi moved the baseline -- it must be delta-independent")
print("PASSED: baseline is delta-independent; pi does not touch it.")
