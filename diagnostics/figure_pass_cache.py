"""Run the model passes ONCE and pickle everything the two figure scripts need.

Two passes, not one, and they are different bases -- this is the whole reason the
cache exists in this shape:

  weighted   compute_food_savings()                     pi(t) applied. Feeds the
                                                        dashboard's panels B and
                                                        C, the food-group
                                                        breakdown, and the whole
                                                        rebound figure.
  unweighted compute_food_savings(survival_weighted=False)
                                                        pi == 1 by construction,
                                                        so this IS the t = 0
                                                        basis. Feeds dashboard
                                                        panel A only.

Panel A sits on the unweighted basis because that is the basis the manuscript's
headline annual figures are quoted on -- `scripts/build_supplement_table.py`
takes `survival_weighted=False` for exactly that reason. A panel illustrating
those numbers has to share their basis.

`sim_slim` is the six columns of the simulation that
`build_supplement_table.compute_scenario_metrics` needs, cached so gate B6 can
call that function directly rather than reimplementing it.

This is a cache of the passes, not a comparison against a prior version of the
code: nothing here runs pre-change code and no baseline is produced.

Usage:
    PYTHONUTF8=1 python -m diagnostics.figure_pass_cache
"""

from __future__ import annotations

import pickle
import time
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "figure_pass_cache.pkl"

SIM_COLUMNS = [
    "ISO", "scenario", "weighting", "eer", "treatment_eer",
    "adheres_to_treatment",
]


def build() -> dict:
    import pyreadr

    from data_visualization.pipeline import (
        ROOT,
        SIMULATION_RDS,
        compute_food_savings,
        load_mortality_emissions,
    )
    from data_visualization.drug_footprint import build_drug_emissions

    t0 = time.time()
    print("[1/5] compute_food_savings()  -- survival-weighted pass ...")
    food_savings, result_df = compute_food_savings()
    print(f"      done in {time.time() - t0:.1f}s")

    t0 = time.time()
    print("[2/5] compute_food_savings(survival_weighted=False)  -- t=0 pass ...")
    food_u, result_u = compute_food_savings(survival_weighted=False)
    print(f"      done in {time.time() - t0:.1f}s")

    print("[3/5] load_mortality_emissions() ...")
    mort = load_mortality_emissions()

    print("[4/5] build_drug_emissions() ...")
    drug = build_drug_emissions()

    print("[5/5] slimming the simulation frame for gate B6 ...")
    sim = list(pyreadr.read_r(str(SIMULATION_RDS)).values())[0]
    sim_slim = sim[SIM_COLUMNS].copy()

    return {
        "food_savings": food_savings,
        "result_df": result_df,
        # .attrs does not survive a pickle round-trip reliably, so the survivor
        # food factor (which carries pop_treated) is lifted out explicitly.
        "survivor_food_factor": result_df.attrs.get("survivor_food_factor"),
        "unsolved": result_df.attrs.get("unsolved"),
        "food_savings_unweighted": food_u,
        "result_df_unweighted": result_u,
        "mort": mort,
        "drug": drug,
        "sim_slim": sim_slim,
    }


def main() -> None:
    payload = build()
    with CACHE.open("wb") as fh:
        pickle.dump(payload, fh, protocol=5)
    print(f"\nCached: {CACHE}")
    for k, v in payload.items():
        shape = getattr(v, "shape", None)
        print(f"  {k:26s} {shape if shape is not None else v}")


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
