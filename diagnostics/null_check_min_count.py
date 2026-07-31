"""Null check for min_count=1 and the narrowed except.

GATES, declared before the run:

  M1  The narrowed except and the NaN-input early return change no live value.
      Bar: result_df's numeric columns exactly 0.0 against the pre-change
      pipeline, all cells.
  M2  Every FILTERED aggregate is bit-identical. Bar: exactly 0.0.
      These are the reported numbers -- every consumer applies `> 0` first.
  M3  No aggregate becomes NaN. Bar: zero NaN aggregates.
  M4  The only rows that move are the ones that should: countries with no
      computable saving go 0.0 -> NaN, and nothing else changes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_visualization import _head_pipeline as head
from data_visualization import pipeline as work
from data_visualization.breakeven_analysis import compute_breakeven
from diagnostics.report import Report

rep = Report(
    "null_check_min_count",
    "min_count=1 plus the narrowed except must move nothing that is reported.",
)
failures: list[str] = []


def gate(label: str, ok: bool) -> None:
    rep.verdict(label, ok)
    if not ok:
        failures.append(label)


head_food, head_rdf = head.compute_food_savings()
work_food, work_rdf = work.compute_food_savings()

# ── M1 result_df ─────────────────────────────────────────────────────────
rep.h2("M1 result_df is untouched")
shared = [
    c for c in head_rdf.columns
    if c in work_rdf.columns
    and pd.api.types.is_numeric_dtype(head_rdf[c])
    and not pd.api.types.is_bool_dtype(head_rdf[c])
]
assert len(head_rdf) == len(work_rdf)
bad = 0
for c in shared:
    a = head_rdf[c].to_numpy(dtype=float)
    b = work_rdf[c].to_numpy(dtype=float)
    nn = np.isnan(a) & np.isnan(b)
    bad += int(((a != b) & ~nn).sum())
rep.kv({"shared numeric columns": len(shared), "rows": len(work_rdf),
        "cells differing": bad})
gate("M1 result_df exactly 0.0 across the narrowed except", bad == 0)

# ── M4 which food_savings rows move ──────────────────────────────────────
rep.h2("M4 only the unsolvable countries move")
key = ["ISO", "Country", "scenario"]
m = head_food[key + ["annual_food_savings_t"]].merge(
    work_food[key + ["annual_food_savings_t"]], on=key, suffixes=("_head", "_work")
)
a = m["annual_food_savings_t_head"].to_numpy(dtype=float)
b = m["annual_food_savings_t_work"].to_numpy(dtype=float)
both_nan = np.isnan(a) & np.isnan(b)
moved = m[(a != b) & ~both_nan]
rep.table(moved)
became_nan = m[np.isnan(b) & ~np.isnan(a)]
rep.kv({
    "rows": len(m),
    "rows that moved": len(moved),
    "rows 0.0 -> NaN": len(became_nan),
    "all movers were exactly 0.0 before": bool(
        len(moved) and (moved["annual_food_savings_t_head"] == 0).all()),
    "all movers are NaN now": bool(
        len(moved) and moved["annual_food_savings_t_work"].isna().all()),
    "unsolved reported on attrs": str(work_rdf.attrs.get("unsolved")),
})
gate("M4 every moved row went exactly 0.0 -> NaN",
     len(moved) == len(became_nan)
     and bool((moved["annual_food_savings_t_head"] == 0).all()))

# ── M2 / M3 the reported aggregates ──────────────────────────────────────
rep.h2("M2/M3 reported aggregates, filtered as every consumer filters")
mort = work.load_mortality_emissions("mean")
be_head = compute_breakeven(head_food, mort, include_drug=True)
be_work = compute_breakeven(work_food, mort, include_drug=True)

rows = []
nan_found = []
for sc in ("max_uptake", "mod_uptake"):
    for label, fs, be in (("head", head_food, be_head), ("work", work_food, be_work)):
        f = fs[(fs["scenario"] == sc) & (fs["annual_food_savings_t"] > 0)]
        v = be[
            (be["scenario"] == sc)
            & (be["annual_food_savings_t"] > 0)
            & (be["total_survivor_emissions_10yr"] > 0)
            & np.isfinite(be["ratio_food_to_mort"])
        ]
        agg = {
            "scenario": sc, "variant": label,
            "n food>0": len(f),
            "annual food sum (t)": f["annual_food_savings_t"].sum(),
            "N complete": len(v),
            "food 10yr (t)": v["total_food_savings_10yr"].sum(),
            "survivor 10yr (t)": v["total_survivor_emissions_10yr"].sum(),
            "cum ratio": v["total_food_savings_10yr"].sum()
                         / v["total_survivor_emissions_10yr"].sum(),
            "min ratio": v["ratio_food_to_mort"].min(),
        }
        for k, val in agg.items():
            if isinstance(val, float) and np.isnan(val):
                nan_found.append(f"{sc}/{label}/{k}")
        rows.append(agg)
tab = pd.DataFrame(rows)
rep.table(tab)

diffs = {}
for sc in ("max_uptake", "mod_uptake"):
    h = tab[(tab.scenario == sc) & (tab.variant == "head")].iloc[0]
    w = tab[(tab.scenario == sc) & (tab.variant == "work")].iloc[0]
    for col in ("n food>0", "annual food sum (t)", "N complete", "food 10yr (t)",
                "survivor 10yr (t)", "cum ratio", "min ratio"):
        diffs[f"{sc} {col}"] = float(w[col]) - float(h[col])
rep.h3("head minus work, every reported aggregate")
rep.kv(diffs, header=("aggregate", "difference"))
gate("M2 every filtered aggregate exactly 0.0",
     all(d == 0.0 for d in diffs.values()))
rep.kv({"aggregates that are NaN": len(nan_found),
        "which": str(nan_found) if nan_found else "none"})
gate("M3 no aggregate became NaN", len(nan_found) == 0)

# ── the two known, accepted movements ─────────────────────────────────────
rep.h2("Known movements, accepted and named")
for sc in ("max_uptake",):
    hb = be_head[be_head["scenario"] == sc]
    wb = be_work[be_work["scenario"] == sc]
    rep.kv({
        "unfiltered breakeven annual sum, head (t)": hb["annual_food_savings_t"].sum(),
        "unfiltered breakeven annual sum, work (t)": wb["annual_food_savings_t"].sum(),
        "difference (the dropped negatives)":
            wb["annual_food_savings_t"].sum() - hb["annual_food_savings_t"].sum(),
    })
rep.text(
    "That difference is the console VALIDATION pivot in "
    "`diet_sensitivity/analysis.py:289`, which sums the break-even frame with no "
    "`> 0` filter. It is printed, never written to a CSV."
)
rep.text(
    "The other movement is `generate_emissions_figure.py`, now filtered to "
    "`> 0`: the chart drops three zero/NaN bars and its country ordering shifts "
    "by those three positions."
)

rep.h2("Result")
if failures:
    rep.text("**FAILED:** " + "; ".join(failures))
else:
    rep.text("All gates passed.")
rep.save()
if failures:
    raise SystemExit(1)
