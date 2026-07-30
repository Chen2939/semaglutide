"""Why do 230,520 non-adherent rows have new_bmi != bmi yet hr_conversion_factor
== 0 on every one of them?  Read-only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_visualization import deterministic_mortality as work

sim = work.load_inputs()
non_adh = ~sim["adheres_to_treatment"].to_numpy(dtype=bool)
d = (sim["new_bmi"] - sim["bmi"]).to_numpy()
moved = non_adh & (d != 0)

print(f"non-adherent rows                : {int(non_adh.sum()):,}")
print(f"  of those with new_bmi != bmi   : {int(moved.sum()):,}")
print(f"  of those also qualifies_for_treatment: "
      f"{int((moved & sim['qualifies_for_treatment'].to_numpy(dtype=bool)).sum()):,}")
print()
print("Magnitude of new_bmi - bmi on those rows:")
dm = np.abs(d[moved])
for q in (0, 50, 90, 99, 100):
    print(f"  p{q:<3} = {np.percentile(dm, q):.6e}")
print(f"  max as a fraction of bmi: "
      f"{np.max(dm / sim['bmi'].to_numpy()[moved]):.6e}")
print()
print("Is it a float artifact of recomputing bmi from treatment_weight?")
print(f"  individual_effect on those rows: min={sim['individual_effect'].to_numpy()[moved].min():.3e} "
      f"max={sim['individual_effect'].to_numpy()[moved].max():.3e}")
print(f"  weight_diff on those rows:      min={sim['weight_diff'].to_numpy()[moved].min():.3e} "
      f"max={sim['weight_diff'].to_numpy()[moved].max():.3e}")
print(f"  ULP-scale? count with |d| < 1e-12 * bmi: "
      f"{int((dm < 1e-12 * sim['bmi'].to_numpy()[moved]).sum()):,} of {int(moved.sum()):,}")
print()
hr_base = work.get_raw_bmi_hazard_ratio(sim["bmi"])
hr_sg = work.get_raw_bmi_hazard_ratio(sim["new_bmi"])
print("Hazard-ratio categories on those rows:")
print(f"  rows where hr_sg != hr_base : {int((hr_sg[moved] != hr_base[moved]).sum()):,}")
print(f"  rows where either HR is NaN : "
      f"{int((np.isnan(hr_sg[moved]) | np.isnan(hr_base[moved])).sum()):,}")
print(f"  hr_conversion_factor != 0   : "
      f"{int((((hr_sg / hr_base) - 1)[moved] != 0).sum()):,}")
print()
print("Same question for ADHERENT rows, for contrast:")
adh = ~non_adh
print(f"  adherent rows: {int(adh.sum()):,}")
print(f"  hr_conversion_factor != 0: {int((((hr_sg / hr_base) - 1)[adh] != 0).sum()):,}")
print(f"  |new_bmi - bmi| median on adherent rows: {np.median(np.abs(d[adh])):.4f}")
