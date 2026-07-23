"""
Side-by-side verification of fix #1 (FAOSTAT aggregate double-counting).

Runs the food pipeline twice from a SINGLE process:
  * current      -> compute_food_savings(exclude_aggregates=False)
                    (logic-identical to the pre-fix pipeline)
  * corrected    -> compute_food_savings(exclude_aggregates=True)
                    (fix #1: parent-level AGGREGATE_ITEMS dropped)

Nothing existing is overwritten; every artifact lands under
  outputs/current/  and  outputs/corrected_fix1/

It then:
  1. writes per-(country, food-group) food tonnage for each run,
  2. computes the tonnage of the excluded aggregate items directly from the
     raw FAOSTAT data (independent of the two pipeline runs),
  3. verifies the invariant  (before - after) == excluded-aggregate tonnage,
  4. reports headline numbers current vs corrected.

Run from repo root:  C:\\Python314\\python.exe outputs\\compare_fix1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_carbon_intensity import AGGREGATE_ITEMS
from data_visualization.pipeline import (
    compute_food_savings,
    load_mortality_emissions,
)
from data_visualization.breakeven_analysis import compute_breakeven

OUT = Path(__file__).resolve().parent
CUR = OUT / "current"
FIX = OUT / "corrected_fix1"
CUR.mkdir(parents=True, exist_ok=True)
FIX.mkdir(parents=True, exist_ok=True)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

SCENARIOS = ["max_uptake", "mod_uptake"]


# ── helpers ────────────────────────────────────────────────────────────


def food_quantity_by_group(result_df: pd.DataFrame) -> pd.DataFrame:
    """Per (ISO, Country, food-group) food tonnage that fed the savings model.

    initial_eql_quantity is identical across scenarios, so take one scenario.
    """
    one = result_df[result_df["scenario"] == "max_uptake"]
    q = (
        one[["ISO", "Country", "final_food_group", "initial_eql_quantity"]]
        .dropna(subset=["initial_eql_quantity"])
        .drop_duplicates(subset=["ISO", "final_food_group"])
        .reset_index(drop=True)
    )
    return q


def baseline_food_emissions_mt(result_df: pd.DataFrame) -> float:
    """National baseline food emissions (Mt CO2e): sum of quantity * CI over
    every (country, food-group), one scenario only (quantity/CI are the same
    across scenarios)."""
    one = result_df[result_df["scenario"] == "max_uptake"].copy()
    one = one.drop_duplicates(subset=["ISO", "final_food_group"])
    emis_t = (one["initial_eql_quantity"] * one["carbon_intensity_t"]).sum()
    return emis_t / 1e6


def excluded_aggregate_tonnage() -> pd.DataFrame:
    """Tonnage of the excluded aggregate items themselves, per (ISO, Country,
    food-group), computed straight from raw FAOSTAT data + the FBS mapping.

    Mirrors the pipeline's own filtering so the invariant is a genuine check:
    same year/element/scope, same mapping, NaN food-group keys dropped (as
    groupby would drop them).
    """
    norm = pd.read_csv(
        ROOT / "Food data" / "FoodBalanceSheets_E_All_Data_(Normalized)"
        / "FoodBalanceSheets_E_All_Data_(Normalized).csv"
    )
    mapping = pd.read_csv(ROOT / "Food data" / "FBS_Group_Mapping.csv")
    iso_mapping = pd.read_csv(ROOT / "Food data" / "faostat_country_mapping.csv")

    import pyreadr

    sim = list(pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values())[0]
    scope = sim["ISO"].unique()

    fn = pd.merge(norm, iso_mapping, on="Area", how="left")
    fn = fn.loc[
        (fn["Year"] == 2022)
        & (fn["Element"] == "Food")
        & (fn["ISO"].isin(scope))
        & (fn["Item"].isin(AGGREGATE_ITEMS))
    ]
    fn = pd.merge(
        fn,
        mapping.set_index("fbs_group")[["final_food_group"]],
        left_on="Item", right_index=True, how="left",
    )
    fn = fn.dropna(subset=["final_food_group"])
    agg = (
        fn.groupby(["Area", "ISO", "final_food_group"])["Value"]
        .sum()
        .reset_index()
        .rename(columns={"Area": "Country", "Value": "excluded_aggregate_t"})
    )
    return agg


def ratios_for_scenario(be_df: pd.DataFrame, scenario: str) -> dict:
    """All-country cumulative and year-10 annual food:survivor ratios, over the
    complete-data subset (positive food savings, positive survivor emissions)."""
    valid = be_df[
        (be_df["scenario"] == scenario)
        & (be_df["annual_food_savings_t"] > 0)
        & (be_df["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be_df["ratio_food_to_mort"])
    ].copy()
    years = np.arange(1, 11)
    cum_food = np.array([valid[f"cum_food_Y{y}"].sum() for y in years], float)
    cum_mort = np.array([valid[f"cum_mort_Y{y}"].sum() for y in years], float)
    annual_food = np.diff(cum_food, prepend=0.0)
    annual_mort = np.diff(cum_mort, prepend=0.0)
    return {
        "n_countries": int(len(valid)),
        "cum_ratio_10yr": cum_food[-1] / cum_mort[-1] if cum_mort[-1] > 0 else np.nan,
        "annual_ratio_y10": (
            annual_food[-1] / annual_mort[-1] if annual_mort[-1] > 0 else np.nan
        ),
        "cum_food_10yr_mt": cum_food[-1] / 1e6,
        "cum_mort_10yr_mt": cum_mort[-1] / 1e6,
        "annual_food_y10_mt": annual_food[-1] / 1e6,
        "annual_mort_y10_mt": annual_mort[-1] / 1e6,
    }


def total_food_savings_mt(food_savings: pd.DataFrame) -> dict:
    """Gross annual food savings (Mt/yr) summed over countries with positive
    savings, per scenario."""
    out = {}
    for sc in SCENARIOS:
        sub = food_savings[
            (food_savings["scenario"] == sc)
            & (food_savings["annual_food_savings_t"] > 0)
        ]
        out[sc] = sub["annual_food_savings_t"].sum() / 1e6
    return out


# ── run both pipelines ─────────────────────────────────────────────────


def run(exclude_aggregates: bool, out_dir: Path, label: str):
    print(f"\n[{label}] compute_food_savings(exclude_aggregates={exclude_aggregates}) ...")
    food_savings, result_df = compute_food_savings(
        exclude_aggregates=exclude_aggregates
    )
    food_savings.to_csv(out_dir / "food_savings.csv", index=False)
    q = food_quantity_by_group(result_df)
    q.to_csv(out_dir / "food_quantity_by_group.csv", index=False)

    mort = load_mortality_emissions()
    be_df = compute_breakeven(food_savings, mort, include_drug=True)
    be_df.to_csv(out_dir / "breakeven.csv", index=False)

    baseline_mt = baseline_food_emissions_mt(result_df)
    savings_mt = total_food_savings_mt(food_savings)
    ratios = {sc: ratios_for_scenario(be_df, sc) for sc in SCENARIOS}

    return {
        "label": label,
        "food_savings": food_savings,
        "result_df": result_df,
        "quantity": q,
        "breakeven": be_df,
        "baseline_mt": baseline_mt,
        "savings_mt": savings_mt,
        "ratios": ratios,
    }


def main():
    cur = run(False, CUR, "current")
    fix = run(True, FIX, "corrected_fix1")

    # ── per (country, food-group) tonnage comparison ────────────────────
    before = cur["quantity"].rename(columns={"initial_eql_quantity": "tonnage_before"})
    after = fix["quantity"].rename(columns={"initial_eql_quantity": "tonnage_after"})
    excl = excluded_aggregate_tonnage()

    comp = pd.merge(
        before, after[["ISO", "final_food_group", "tonnage_after"]],
        on=["ISO", "final_food_group"], how="outer",
    )
    comp = pd.merge(
        comp, excl[["ISO", "final_food_group", "excluded_aggregate_t"]],
        on=["ISO", "final_food_group"], how="left",
    )
    for c in ["tonnage_before", "tonnage_after", "excluded_aggregate_t"]:
        comp[c] = comp[c].fillna(0.0)
    comp["difference"] = comp["tonnage_before"] - comp["tonnage_after"]
    comp["invariant_gap"] = comp["difference"] - comp["excluded_aggregate_t"]
    comp = comp.sort_values(["Country", "final_food_group"]).reset_index(drop=True)
    comp.to_csv(OUT / "tonnage_comparison_by_country_group.csv", index=False)

    # per food group (all countries)
    by_group = (
        comp.groupby("final_food_group")[
            ["tonnage_before", "tonnage_after", "difference", "excluded_aggregate_t"]
        ]
        .sum()
        .reset_index()
    )
    by_group["invariant_gap"] = (
        by_group["difference"] - by_group["excluded_aggregate_t"]
    )
    by_group.to_csv(OUT / "tonnage_comparison_by_group.csv", index=False)

    # per country (all groups)
    by_country = (
        comp.groupby(["ISO", "Country"])[
            ["tonnage_before", "tonnage_after", "difference", "excluded_aggregate_t"]
        ]
        .sum()
        .reset_index()
    )
    by_country["invariant_gap"] = (
        by_country["difference"] - by_country["excluded_aggregate_t"]
    )
    by_country.to_csv(OUT / "tonnage_comparison_by_country.csv", index=False)

    # ── print: per food group ───────────────────────────────────────────
    print("\n" + "=" * 92)
    print("TONNAGE COMPARISON BY FOOD GROUP (all countries summed, tonnes)")
    print("=" * 92)
    hdr = f"{'Food group':<48}{'before':>14}{'after':>14}{'diff':>14}{'excl.aggr':>14}"
    print(hdr)
    print("-" * 92)
    for _, r in by_group.iterrows():
        print(
            f"{r['final_food_group']:<48}"
            f"{r['tonnage_before']:>14,.0f}"
            f"{r['tonnage_after']:>14,.0f}"
            f"{r['difference']:>14,.0f}"
            f"{r['excluded_aggregate_t']:>14,.0f}"
        )
    tb, ta = by_group["tonnage_before"].sum(), by_group["tonnage_after"].sum()
    td, te = by_group["difference"].sum(), by_group["excluded_aggregate_t"].sum()
    print("-" * 92)
    print(f"{'TOTAL':<48}{tb:>14,.0f}{ta:>14,.0f}{td:>14,.0f}{te:>14,.0f}")

    # ── print: per country (top 20 by removed tonnage) ──────────────────
    print("\n" + "=" * 92)
    print("TONNAGE COMPARISON BY COUNTRY (all groups summed, tonnes) — top 20 by removed")
    print("=" * 92)
    print(f"{'Country':<40}{'before':>14}{'after':>14}{'diff':>14}{'excl.aggr':>12}")
    print("-" * 92)
    top = by_country.sort_values("difference", ascending=False).head(20)
    for _, r in top.iterrows():
        print(
            f"{r['Country'][:38]:<40}"
            f"{r['tonnage_before']:>14,.0f}"
            f"{r['tonnage_after']:>14,.0f}"
            f"{r['difference']:>14,.0f}"
            f"{r['excluded_aggregate_t']:>12,.0f}"
        )
    print(f"(full per-country x per-group table: {OUT / 'tonnage_comparison_by_country_group.csv'})")

    # ── invariant check ─────────────────────────────────────────────────
    removed_total = comp["difference"].sum()
    excluded_total = comp["excluded_aggregate_t"].sum()
    max_abs_gap = comp["invariant_gap"].abs().max()
    rel_gap = abs(removed_total - excluded_total) / excluded_total if excluded_total else np.nan

    print("\n" + "=" * 92)
    print("INVARIANT: tonnage removed  ==  tonnage of excluded aggregate items")
    print("=" * 92)
    print(f"  Total tonnage removed (before - after):      {removed_total:>18,.1f} t")
    print(f"  Total excluded aggregate-item tonnage:       {excluded_total:>18,.1f} t")
    print(f"  Absolute difference:                         {abs(removed_total - excluded_total):>18,.1f} t")
    print(f"  Relative difference:                         {rel_gap:>18.2e}")
    print(f"  Worst per-cell |gap|:                        {max_abs_gap:>18,.4f} t")

    ok = np.isclose(removed_total, excluded_total, rtol=1e-6, atol=1.0) and (
        max_abs_gap < 1.0
    )
    if ok:
        print("\n  INVARIANT HOLDS: the exclusion removes exactly the aggregate items.")
    else:
        worst = comp.reindex(
            comp["invariant_gap"].abs().sort_values(ascending=False).index
        ).head(15)
        print("\n  *** INVARIANT VIOLATED — STOP. Worst offending cells: ***")
        print(worst[[
            "Country", "final_food_group", "tonnage_before", "tonnage_after",
            "difference", "excluded_aggregate_t", "invariant_gap",
        ]].to_string(index=False))
        print(
            "\n  The exclusion is removing something other than the intended "
            "aggregate items. Not proceeding to headline numbers."
        )
        return

    # ── headline numbers ────────────────────────────────────────────────
    print("\n" + "=" * 92)
    print("HEADLINE NUMBERS — current vs corrected (fix #1)")
    print("=" * 92)

    print(f"\n  Baseline national food emissions (Mt CO2e):")
    print(f"    current   : {cur['baseline_mt']:>12,.1f} Mt")
    print(f"    corrected : {fix['baseline_mt']:>12,.1f} Mt")
    print(f"    change    : {fix['baseline_mt'] - cur['baseline_mt']:>12,.1f} Mt "
          f"({(fix['baseline_mt']/cur['baseline_mt'] - 1)*100:+.1f}%)")

    print(f"\n  Total annual food savings (Mt CO2e/yr), gross of drug:")
    print(f"    {'scenario':<16}{'current':>12}{'corrected':>12}{'change %':>12}")
    for sc in SCENARIOS:
        c, f = cur["savings_mt"][sc], fix["savings_mt"][sc]
        print(f"    {sc:<16}{c:>12,.1f}{f:>12,.1f}{(f/c-1)*100:>11.1f}%")

    print(f"\n  Cumulative 10-yr food:survivor ratio (complete-data countries):")
    print(f"    {'scenario':<16}{'current':>14}{'corrected':>14}")
    for sc in SCENARIOS:
        c = cur["ratios"][sc]["cum_ratio_10yr"]
        f = fix["ratios"][sc]["cum_ratio_10yr"]
        print(f"    {sc:<16}{c:>13,.1f}x{f:>13,.1f}x")

    print(f"\n  Year-10 ANNUAL food:survivor ratio (complete-data countries):")
    print(f"    {'scenario':<16}{'current':>14}{'corrected':>14}")
    for sc in SCENARIOS:
        c = cur["ratios"][sc]["annual_ratio_y10"]
        f = fix["ratios"][sc]["annual_ratio_y10"]
        print(f"    {sc:<16}{c:>13,.1f}x{f:>13,.1f}x")

    # persist a compact headline table
    rows = []
    for scope_lbl, d in [("current", cur), ("corrected_fix1", fix)]:
        for sc in SCENARIOS:
            rows.append({
                "run": scope_lbl,
                "scenario": sc,
                "baseline_food_emissions_mt": d["baseline_mt"],
                "total_annual_food_savings_mt": d["savings_mt"][sc],
                "cum_food_to_survivor_ratio_10yr": d["ratios"][sc]["cum_ratio_10yr"],
                "annual_food_to_survivor_ratio_y10": d["ratios"][sc]["annual_ratio_y10"],
                "n_complete_countries": d["ratios"][sc]["n_countries"],
            })
    pd.DataFrame(rows).to_csv(OUT / "headline_numbers.csv", index=False)
    print(f"\nSaved: {OUT / 'headline_numbers.csv'}")
    print(f"Saved: outputs/current/, outputs/corrected_fix1/, and comparison CSVs in outputs/")


if __name__ == "__main__":
    main()
