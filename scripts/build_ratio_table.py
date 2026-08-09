"""
Build the before/after-drug ratio table across all sensitivity specifications.

This is the manuscript's "Before (gross) / After (food - drug)" table. Nothing
in the tree produced it as a unit: ``drug_footprint_summary.csv`` has both
columns and both uptakes but only the baseline spec, and
``all_sensitivity_overview_results.csv`` has all six specs but only max uptake
and only the after-drug ratio. This closes the gap.

Definitions match ``drug_effect/analysis.py``: the gross ratio comes from a
second ``compute_breakeven(..., include_drug=False)`` pass, not from adding the
drug term back onto the netted one.

    before (gross)    = sum(gross 10yr food) / sum(survivor 10yr)
    after (food-drug) = sum(net   10yr food) / sum(survivor 10yr)

Writes:
  data_result/ratio_table_before_after_drug.csv

Usage:
    python -m scripts.build_ratio_table
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data_visualization.breakeven_analysis import compute_breakeven  # noqa: E402
from data_visualization.pipeline import (  # noqa: E402
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)
from diet_sensitivity.sensitivity_overview import OVERVIEW_SCENARIOS  # noqa: E402

UPTAKES = ["max_uptake", "mod_uptake"]

# Committed values this must reproduce exactly. Sources:
#   before -> data_result/drug_footprint_summary.csv        (ratio_without_drug)
#   after  -> data_result/all_sensitivity_overview_results.csv (ratio_food_to_mort)
# Pinned baseline max-uptake ratios, gross and net of the drug charge. Refreshed
# with the reference snapshots after the population regeneration (447e688), which
# is what moved them; the previous pin was 1.8933028079285414 / 1.8473655359514574
# and predated that commit, so this guard was failing on every run. Moderate
# uptake moved the same way, 1.832 -> 2.0007 gross and 1.787 -> 1.9519 net.
BAR = {"before": 1.9912545286046903, "after": 1.9427609867232756}


def build() -> pd.DataFrame:
    rows, mort_cache = [], {}
    for cfg in OVERVIEW_SCENARIOS:
        print(f"  -> {cfg['label']}")
        food, _ = compute_food_savings(
            diet_scenario=cfg["diet_scenario"], ci_file=cfg["ci_file"]
        )
        ci = cfg["ci_scenario"]
        if ci not in mort_cache:
            mort_cache[ci] = load_mortality_emissions(ci)
        net = compute_breakeven(food, mort_cache[ci], include_drug=True)
        gross = compute_breakeven(food, mort_cache[ci], include_drug=False)[
            ["ISO", "scenario", "total_food_savings_10yr"]
        ].rename(columns={"total_food_savings_10yr": "gross_10yr"})
        be = net.merge(gross, on=["ISO", "scenario"], how="left")

        for uptake in UPTAKES:
            v = be[(be["scenario"] == uptake)
                   & np.isfinite(be["ratio_food_to_mort"])
                   & (be["annual_food_savings_t"] > 0)
                   & (be["total_survivor_emissions_10yr"] > 0)]
            surv = v["total_survivor_emissions_10yr"].sum()
            rows.append({
                "spec": cfg["overview_scenario"],
                "label": cfg["label"],
                "group": cfg["group"],
                "uptake": uptake,
                "before_gross_ratio": v["gross_10yr"].sum() / surv,
                "after_net_ratio": v["total_food_savings_10yr"].sum() / surv,
                "n_tipped": int((v["ratio_food_to_mort"] < 1).sum()),
                "n_countries": v["ISO"].nunique(),
                "food_gross_10yr_Mt": v["gross_10yr"].sum() / 1e6,
                "food_net_10yr_Mt": v["total_food_savings_10yr"].sum() / 1e6,
                "survivor_10yr_Mt": surv / 1e6,
                "drug_10yr_Mt": v["total_drug_emissions_10yr"].sum() / 1e6,
            })
    return pd.DataFrame(rows)


def main() -> int:
    print("Building before/after-drug ratio table...")
    df = build()

    base = df[(df["spec"] == "baseline_mean_ci") & (df["uptake"] == "max_uptake")]
    got = {"before": float(base["before_gross_ratio"].iloc[0]),
           "after": float(base["after_net_ratio"].iloc[0])}
    bad = [k for k, want in BAR.items() if got[k] != want]
    for k, want in BAR.items():
        print(f"  [{'PASS' if k not in bad else 'FAIL'}] baseline max {k:6s} "
              f"want {want!r} got {got[k]!r}")

    out = output_path("ratio_table_before_after_drug.csv")
    df.to_csv(out, index=False)

    for uptake in UPTAKES:
        print(f"\n{uptake}")
        print(f"  {'Metric':<34}{'Before':>10}{'After':>10}{'Tipped':>8}")
        for _, r in df[df["uptake"] == uptake].iterrows():
            print(f"  {r['label']:<34}{r['before_gross_ratio']:>9.2f}x"
                  f"{r['after_net_ratio']:>9.2f}x{r['n_tipped']:>8}")
        print(f"  N = {df[df['uptake'] == uptake]['n_countries'].iloc[0]} countries")

    print(f"\nTable -> {out}")
    if bad:
        print(f"BAR FAILED on: {', '.join(bad)} -- do not use these numbers.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
