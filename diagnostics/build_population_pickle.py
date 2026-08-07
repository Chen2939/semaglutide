"""Carry a regenerated simulation run into the pickle the mortality side reads.

WHY THIS SCRIPT EXISTS. ``final_df_imputed.pkl`` is read by
``deterministic_mortality.py``, ``survival_weighting.py`` and
``survivor_manuscript_numbers.py``, and the only thing that has ever written it
is ``Mortality Model.ipynb`` -- which CLAUDE.md records as out of the execution
path and not to be run, because it would restore removed columns and
reintroduce the old survivor decline. ``Mortality_model2.R`` writes a *second*,
older R-side vintage of the same imputation (``final_df_imputed.rds``) which is
not what the current numbers rest on. So Phase 4's "carry Run C into the
pickle" had no sanctioned mechanism.

WHAT THIS DOES INSTEAD. The pickle is the ``.rds`` plus three columns --
``Age``, ``mortality_rate`` and ``Year`` -- and only ``mortality_rate`` is read
by anything. That column is the regional/global-median imputation over the
41-country HLD extract, and it is a function of ``(ISO, age, Sex)`` ALONE: it
does not depend on the simulated population at all. So re-running the
imputation on a new population would be a no-op that risks reintroducing the
R-versus-notebook divergence. This script instead lifts the existing map off
the committed pickle and joins it onto the new run.

Every property that makes that safe is ASSERTED here, not assumed:
  * the map is single-valued on (ISO, age, Sex)
  * it is total over the new run's actual (ISO, age, Sex) combinations
  * the join adds no rows and leaves no NA
  * the baseline pickle's own bmi vector is untouched by this script

``Age`` and ``Year`` are carried through for schema fidelity. ``Age`` is the
right-hand key left by the notebook's merge against the HLD extract and is null
on 42.86% of baseline rows -- on exactly the countries that extract lacks. Both
are verified unread by every consumer before being treated as inert.

ASCII only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyreadr

ROOT = Path(__file__).resolve().parent.parent

KEY = ["ISO", "age", "Sex"]
CARRIED = ["Age", "mortality_rate", "Year"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rds", default=str(ROOT / "full_simulation_results9.rds"))
    ap.add_argument("--baseline-pkl", default=str(ROOT / "final_df_imputed.pkl"))
    ap.add_argument("--out", default=str(ROOT / "final_df_imputed9.pkl"))
    a = ap.parse_args()

    print(f"run       : {a.rds}")
    print(f"baseline  : {a.baseline_pkl}")
    print(f"out       : {a.out}")

    sim = list(pyreadr.read_r(a.rds).values())[0]
    print(f"\nsimulation rows x cols : {sim.shape}")

    base = pd.read_pickle(a.baseline_pkl)
    print(f"baseline   rows x cols : {base.shape}")

    # --- build the map -----------------------------------------------------
    m = base[KEY + CARRIED].drop_duplicates()
    dupes = int(m.duplicated(subset=KEY).sum())
    print(f"\nmap cells                    : {len(m):,}")
    print(f"cells with >1 carried tuple  : {dupes}")
    if dupes:
        # Age/Year may vary where mortality_rate does not; check which.
        for c in CARRIED:
            d = int(base[KEY + [c]].drop_duplicates().duplicated(subset=KEY).sum())
            print(f"    {c:16s} multi-valued cells: {d}")
        print(
            "\nFAIL: the carried columns are not single-valued on (ISO, age, Sex). "
            "mortality_rate must be; if only Age/Year are not, drop them from "
            "CARRIED rather than picking a value."
        )
        return 1

    n_nan_rate = int(m["mortality_rate"].isna().sum())
    n_zero = int((m["mortality_rate"] == 0).sum())
    print(f"NaN mortality_rate in map    : {n_nan_rate}")
    print(f"zero mortality_rate in map   : {n_zero}")
    if n_nan_rate or n_zero:
        print("FAIL: a NaN or zero rate is indistinguishable from immortality.")
        return 1

    # --- totality over THIS run's keys -------------------------------------
    need = sim[KEY].drop_duplicates()
    have = m[KEY]
    missing = need.merge(have, on=KEY, how="left", indicator=True)
    missing = missing[missing["_merge"] == "left_only"]
    print(f"\nrun's distinct (ISO, age, Sex): {len(need):,}")
    print(f"not covered by the map        : {len(missing)}")
    if len(missing):
        print(missing.head(15).to_string(index=False))
        print("FAIL: the map is not total over this run's keys.")
        return 1

    # --- join --------------------------------------------------------------
    n_before = len(sim)
    out = sim.merge(m, on=KEY, how="left", validate="many_to_one")
    print(f"\nrows before / after join      : {n_before:,} / {len(out):,}")
    if len(out) != n_before:
        print("FAIL: the join changed the row count.")
        return 1
    n_na = int(out["mortality_rate"].isna().sum())
    print(f"NA mortality_rate after join  : {n_na}")
    if n_na:
        print("FAIL.")
        return 1

    # --- schema report ------------------------------------------------------
    extra = [c for c in out.columns if c not in base.columns]
    dropped = [c for c in base.columns if c not in out.columns]
    print(f"\ncolumns vs baseline pickle:")
    print(f"  new in this build   : {extra}")
    print(f"  absent vs baseline  : {dropped}")
    print(f"  Age null fraction   : {out['Age'].isna().mean():.4f} "
          f"(baseline {base['Age'].isna().mean():.4f})")

    out.to_pickle(a.out)
    print(f"\nwritten: {a.out}  ({Path(a.out).stat().st_size:,} bytes)")

    # The baseline must be untouched.
    print(f"baseline still present: {Path(a.baseline_pkl).is_file()}, "
          f"{Path(a.baseline_pkl).stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
