"""Pass-2 stage 1: the facts to establish before editing either figure.

Reads diagnostics/figure_pass_cache.pkl -- no model pass here.

    1. The unweighted (t = 0) country universe and its top 15.
    2. Whether the pass-1 mod > max per-patient inversion survives unweighting.
    3. The population-weighted global mean per-patient value.
    4. Gate B6 rehearsal: does the cached unweighted pass reproduce
       build_supplement_table's emissions figure exactly?
    5. Gate B7 rehearsal: how far the unweighted totals move from the weighted
       ones the committed PNG carries.
    6. The food-group set and ordering for the rebound figure.

Usage:
    PYTHONUTF8=1 python -m diagnostics.figure_fixes_predecide
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "figure_pass_cache.pkl"

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)

DRUG_KG = 5.38


def main() -> None:
    with CACHE.open("rb") as fh:
        c = pickle.load(fh)

    fu, ru = c["food_savings_unweighted"], c["result_df_unweighted"]
    fw = c["food_savings"]
    drug = c["drug"]

    print("=" * 78)
    print("1. UNWEIGHTED (t=0) COUNTRY UNIVERSE")
    print("=" * 78)
    for sc in ("max_uptake", "mod_uptake"):
        n = ((fu["scenario"] == sc) & (fu["annual_food_savings_t"] > 0)).sum()
        print(f"  {sc}: positive food savings on N = {n}")
    mxu = fu[(fu.scenario == "max_uptake") & (fu.annual_food_savings_t > 0)] \
        .sort_values("annual_food_savings_t", ascending=False)
    mxw = fw[(fw.scenario == "max_uptake") & (fw.annual_food_savings_t > 0)] \
        .sort_values("annual_food_savings_t", ascending=False)
    top_u, top_w = mxu.head(15)["ISO"].tolist(), mxw.head(15)["ISO"].tolist()
    print(f"\n  top-15 unweighted == top-15 weighted (same order)? {top_u == top_w}")
    if top_u != top_w:
        print(f"    unweighted: {top_u}")
        print(f"    weighted  : {top_w}")
    print(f"  16th/15th margin (unweighted): "
          f"{mxu.iloc[14]['ISO']} {mxu.iloc[14]['annual_food_savings_t']/1e3:,.1f} kt vs "
          f"{mxu.iloc[15]['ISO']} {mxu.iloc[15]['annual_food_savings_t']/1e3:,.1f} kt")

    print()
    print("=" * 78)
    print("2/3. PER-PATIENT ON THE UNWEIGHTED BASIS")
    print("=" * 78)
    d = fu.merge(drug[["ISO", "scenario", "treated_users_initial",
                       "drug_emissions_1yr_t"]], on=["ISO", "scenario"], how="left")
    d["net_t"] = d["annual_food_savings_t"] - d["drug_emissions_1yr_t"]
    d["pp_kg"] = d["net_t"] * 1e3 / d["treated_users_initial"]
    d["pp_gross_kg"] = d["annual_food_savings_t"] * 1e3 / d["treated_users_initial"]
    d["pp_drug_kg"] = d["drug_emissions_1yr_t"] * 1e3 / d["treated_users_initial"]

    a = d[d.scenario == "max_uptake"].set_index("ISO").reindex(top_u)
    b = d[d.scenario == "mod_uptake"].set_index("ISO").reindex(top_u)
    cmp = pd.DataFrame({
        "ISO": top_u, "Country": a["Country"].values,
        "pp_max_kg": a["pp_kg"].values, "pp_mod_kg": b["pp_kg"].values,
    })
    cmp["mod_over_max"] = cmp["pp_mod_kg"] / cmp["pp_max_kg"]
    print()
    print(cmp.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    inv = cmp[cmp.mod_over_max > 1]
    print(f"\n  mod > max on: {sorted(inv['ISO']) if len(inv) else 'none'}")
    print(f"  pass-1 (weighted) had: ['AUS', 'ESP', 'FRA']")
    print(f"  separation as frac of x-range: median "
          f"{(np.abs(cmp.pp_max_kg - cmp.pp_mod_kg) / cmp.pp_max_kg.max()).median():.4f}")
    print(f"\n  per-patient drug charge, kg: min {d['pp_drug_kg'].min():.6f}  "
          f"max {d['pp_drug_kg'].max():.6f}  (nominal {DRUG_KG})")

    # Population-weighted global mean, over the derived universe, max uptake.
    uni = d[(d.scenario == "max_uptake") & (d.annual_food_savings_t > 0)]
    g_gross = uni["annual_food_savings_t"].sum()
    g_pat = uni["treated_users_initial"].sum()
    g_drug = uni["drug_emissions_1yr_t"].sum()
    print(f"\n  GLOBAL population-weighted mean per patient (max uptake, N={len(uni)}):")
    print(f"    gross : {g_gross * 1e3 / g_pat:.4f} kg CO2eq/patient-year")
    print(f"    drug  : {g_drug * 1e3 / g_pat:.4f} kg")
    print(f"    NET   : {(g_gross - g_drug) * 1e3 / g_pat:.4f} kg")
    print(f"    (treated headcount {g_pat:,.0f}; gross total "
          f"{g_gross / 1e6:.4f} Mt)")

    print()
    print("=" * 78)
    print("4. GATE B6 REHEARSAL -- vs build_supplement_table, same code path")
    print("=" * 78)
    from scripts.build_supplement_table import compute_scenario_metrics
    sim = c["sim_slim"]
    for sc in ("max_uptake", "mod_uptake"):
        m = compute_scenario_metrics(sc, fu, ru, sim)
        mine = fu.loc[(fu.scenario == sc) & (fu.annual_food_savings_t > 0),
                      "annual_food_savings_t"].sum()
        theirs = m["emissions_after_Mt"] * 1e6
        print(f"  {sc}: N={m['N']}  supplement {theirs:,.9f} t  "
              f"mine {mine:,.9f} t  abs diff {abs(mine - theirs):.6e}  "
              f"EXACT-ZERO {abs(mine - theirs) == 0.0}")
        hc = m["treated_headcount"]
        mine_hc = fu.loc[(fu.scenario == sc) & (fu.annual_food_savings_t > 0), "ISO"] \
            .pipe(lambda s: drug[(drug.scenario == sc) & drug.ISO.isin(s)]
                  ["treated_users_initial"].sum())
        print(f"        headcount supplement {hc:,.6f} vs drug-file {mine_hc:,.6f}  "
              f"abs diff {abs(hc - mine_hc):.6e}")
        print(f"        supplement per-patient gross "
              f"{m['emissions_after_Mt'] * 1e9 / hc:.4f} kg, net "
              f"{m['emissions_after_Mt'] * 1e9 / hc - DRUG_KG:.4f} kg")

    print()
    print("=" * 78)
    print("5. GATE B7 REHEARSAL -- unweighted vs weighted year-1 totals")
    print("=" * 78)
    j = mxu.head(15)[["ISO", "Country", "annual_food_savings_t"]].merge(
        mxw[["ISO", "annual_food_savings_t"]], on="ISO", suffixes=("_unw", "_wtd"))
    j["pct_higher"] = (j.annual_food_savings_t_unw / j.annual_food_savings_t_wtd - 1) * 100
    print()
    print(j.assign(unw_kt=j.annual_food_savings_t_unw / 1e3,
                   wtd_kt=j.annual_food_savings_t_wtd / 1e3)
          [["ISO", "Country", "unw_kt", "wtd_kt", "pct_higher"]]
          .to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    print(f"\n  all 15 differ: {(j.pct_higher.abs() > 1e-9).all()}")
    print(f"  pct higher: min {j.pct_higher.min():.4f}%  max {j.pct_higher.max():.4f}%")

    print()
    print("=" * 78)
    print("6. FOOD GROUPS FOR THE REBOUND FIGURE")
    print("=" * 78)
    mu = c["result_df"][c["result_df"].scenario == "max_uptake"]
    rank = (mu.groupby("final_food_group")["carbon_savings_t"]
            .sum().abs().sort_values(ascending=False) / 1e3)
    print(f"\n  groups present: {len(rank)}")
    for i, (g, v) in enumerate(rank.items(), 1):
        print(f"    {i:2d}. {g:50s} {v:12,.1f} kt")
    # How many distinct countries would appear at N per row?
    for n in (5, 6, 8, 12):
        isos = set()
        for g in rank.index:
            sub = (mu[mu.final_food_group == g].groupby("Country")["actual_reduction"]
                   .sum().abs().sort_values(ascending=False).head(n))
            isos |= set(sub.index)
        print(f"  N={n:2d} per row -> {len(rank) * n:3d} bars/panel-column, "
              f"{len(isos)} distinct countries named")
    longest = max((len(str(x)) for x in mu["Country"].unique()))
    from data_visualization.figure_style import display_country
    longest_d = max((len(display_country(str(x))) for x in mu["Country"].unique()))
    print(f"  longest country label: {longest} chars raw, {longest_d} chars shortened")


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
