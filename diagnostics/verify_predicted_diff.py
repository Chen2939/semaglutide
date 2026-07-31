"""Confirm each moved file changed only in the predicted rows.

The file-level set matched the prediction exactly. This checks the row level: every
differing cell must belong to GUY, NRU or TWN, and must be a value becoming NaN (or
a row disappearing from a wide pivot). A differing cell on any other country is a
fourth cause and gets reported.
"""

from __future__ import annotations

import io
import subprocess

import numpy as np
import pandas as pd

from data_visualization.pipeline import ROOT
from diagnostics.report import Report

EXPECTED = {"GUY", "NRU", "TWN"}
rep = Report(
    "verify_predicted_diff",
    "Row-level check that the regeneration moved only GUY/NRU/TWN, as predicted.",
)
problems: list[str] = []


def head_blob(rel: str) -> pd.DataFrame:
    """Read a file as of HEAD, smudging it if it is an LFS pointer.

    Most data_result CSVs are LFS-tracked, so `git show HEAD:path` returns a
    ~130-byte pointer, which read_csv happily parses into a one-column frame. That
    is worse than an error: a comparison against it looks like "every column
    changed" rather than like a broken read. Detect and smudge.
    """
    raw = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"HEAD:{rel}"],
        capture_output=True, check=True,
    ).stdout
    if raw.startswith(b"version https://git-lfs"):
        raw = subprocess.run(
            ["git", "-C", str(ROOT), "lfs", "smudge"],
            input=raw, capture_output=True, check=True,
        ).stdout
    df = pd.read_csv(io.BytesIO(raw), float_precision="round_trip")
    if len(df.columns) < 2:
        raise RuntimeError(
            f"{rel} read as {len(df.columns)} column(s) from HEAD -- almost "
            "certainly still an unsmudged LFS pointer. Refusing to compare."
        )
    return df


ROW_DUMPS = [
    ("data_result/net_emissions_with_drug.csv", ["ISO", "scenario"]),
    ("data_result/diet_sensitivity_results.csv", ["diet_scenario", "ISO", "scenario"]),
    ("data_result/combined_sensitivity_results.csv",
     ["combined_scenario", "ISO", "scenario"]),
]

rep.h2("Per-country row dumps: which rows and columns moved")
for rel, key in ROW_DUMPS:
    old = head_blob(rel)
    new = pd.read_csv(ROOT / rel, float_precision="round_trip")
    rep.h3(rel)
    if list(old.columns) != list(new.columns):
        problems.append(f"{rel}: column set changed")
        rep.text("**Column set changed** -- unexpected.")
        continue
    if len(old) != len(new):
        problems.append(f"{rel}: row count changed {len(old)} -> {len(new)}")
    m = old.merge(new, on=key, suffixes=("_old", "_new"), how="outer", indicator=True)
    num = [c for c in old.columns if c not in key
           and pd.api.types.is_numeric_dtype(old[c])
           and not pd.api.types.is_bool_dtype(old[c])]
    moved_rows, moved_cells, cols_moved = set(), 0, set()
    for c in num:
        a = m[f"{c}_old"].to_numpy(dtype=float)
        b = m[f"{c}_new"].to_numpy(dtype=float)
        nn = np.isnan(a) & np.isnan(b)
        d = (a != b) & ~nn
        if d.any():
            cols_moved.add(c)
            moved_cells += int(d.sum())
            moved_rows |= set(m.loc[d, "ISO"])
    off = sorted(moved_rows - EXPECTED)
    rep.kv({
        "rows": len(m),
        "cells differing": moved_cells,
        "countries with any differing cell": ", ".join(sorted(moved_rows)) or "none",
        "columns affected": len(cols_moved),
        "countries outside GUY/NRU/TWN": ", ".join(off) or "none",
    })
    rep.text("Columns affected: " + ", ".join(sorted(cols_moved)))
    if off:
        problems.append(f"{rel}: unexpected countries {off}")
    # direction: old finite -> new NaN
    bad_dir = 0
    for c in sorted(cols_moved):
        a = m[f"{c}_old"].to_numpy(dtype=float)
        b = m[f"{c}_new"].to_numpy(dtype=float)
        nn = np.isnan(a) & np.isnan(b)
        d = (a != b) & ~nn
        bad_dir += int((d & ~np.isnan(b)).sum())
    rep.kv({"differing cells whose NEW value is not NaN": bad_dir})
    if bad_dir:
        problems.append(f"{rel}: {bad_dir} cells moved to a non-NaN value")

rep.h2("Wide pivots: which index rows disappeared")
for rel in [
    "data_result/all_sensitivity_overview_country_ratios.csv",
    "data_result/diet_sensitivity_ratio_comparison.csv",
    "data_result/combined_sensitivity_ratio_comparison.csv",
]:
    old = head_blob(rel)
    new = pd.read_csv(ROOT / rel, float_precision="round_trip")
    gone = sorted(set(old["ISO"]) - set(new["ISO"]))
    added = sorted(set(new["ISO"]) - set(old["ISO"]))
    rep.h3(rel)
    rep.kv({
        "rows before": len(old), "rows after": len(new),
        "ISO removed": ", ".join(gone) or "none",
        "ISO added": ", ".join(added) or "none",
    })
    if set(gone) - EXPECTED or added:
        problems.append(f"{rel}: removed {gone}, added {added}")
    # every retained row must be bit-identical
    common = sorted(set(old["ISO"]) & set(new["ISO"]))
    o = old[old["ISO"].isin(common)].sort_values("ISO").reset_index(drop=True)
    n = new[new["ISO"].isin(common)].sort_values("ISO").reset_index(drop=True)
    shared = [c for c in o.columns if c in n.columns
              and pd.api.types.is_numeric_dtype(o[c])]
    bad = 0
    for c in shared:
        a, b = o[c].to_numpy(dtype=float), n[c].to_numpy(dtype=float)
        nn = np.isnan(a) & np.isnan(b)
        bad += int(((a != b) & ~nn).sum())
    rep.kv({"retained rows": len(common),
            "cells differing among retained rows": bad})
    if bad:
        problems.append(f"{rel}: {bad} cells moved on retained rows")

rep.h2("Headline invariants")
be = pd.read_csv(ROOT / "data_result" / "net_emissions_with_drug.csv",
                 float_precision="round_trip")
rows = []
for sc in ("max_uptake", "mod_uptake"):
    v = be[(be["scenario"] == sc) & (be["annual_food_savings_t"] > 0)
           & (be["total_survivor_emissions_10yr"] > 0)
           & np.isfinite(be["ratio_food_to_mort"])]
    rows.append({
        "scenario": sc, "N complete": len(v),
        "cum ratio 10yr": v["total_food_savings_10yr"].sum()
                          / v["total_survivor_emissions_10yr"].sum(),
        "min ratio": v["ratio_food_to_mort"].min(),
        "min ISO": v.loc[v["ratio_food_to_mort"].idxmin(), "ISO"],
    })
tab = pd.DataFrame(rows)
rep.table(tab)
if int(tab.loc[tab.scenario == "max_uptake", "N complete"].iloc[0]) != 40:
    problems.append("break-even set is no longer 40")

gdp = pd.read_csv(ROOT / "data_result" / "gdp_share_of_global_economy.csv")
cov = gdp.loc[gdp["in_complete_subset"], "share_of_world_pct"].sum()
rep.kv({
    "complete-data GDP coverage (%)": cov,
    "rows in the GDP table": len(gdp),
    "is 58.96% to 2 dp": bool(round(cov, 2) == 58.96),
})
if round(cov, 2) != 58.96:
    problems.append(f"GDP coverage moved to {cov:.4f}%")

rep.h2("Result")
if problems:
    rep.text("**UNEXPECTED MOVEMENT:**")
    for p in problems:
        rep.bullet(p)
else:
    rep.text(
        "Every differing cell belongs to GUY, NRU or TWN; every one moved to NaN; "
        "every retained pivot row is bit-identical; the break-even set is 40 and "
        "coverage is 58.96%. Matches the prediction with nothing left over."
    )
rep.save()
if problems:
    raise SystemExit(1)
