"""How much of the headline rests on Israel's life table standing in for the Gulf?

Reads the committed break-even output; runs no model. Two questions:

  1. Which break-even-set countries carry a mortality schedule identical to
     Israel's, i.e. were imputed from a UN region whose only HLD member is ISR?
  2. What are the cumulative 10-year ratio, the year-10 annual ratio and the
     minimum-country ratio with and without them?
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "data_result" / "net_emissions_with_drug.csv"
DROP = ["ARE", "SAU"]
pd.set_option("display.width", 220)


def valid(be: pd.DataFrame, sc: str) -> pd.DataFrame:
    return be[
        (be["scenario"] == sc)
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be["ratio_food_to_mort"])
    ].copy()


def ratios(v: pd.DataFrame) -> dict:
    cf = np.array([v[f"cum_food_Y{y}"].sum() for y in range(1, 11)], dtype=float)
    cm = np.array([v[f"cum_mort_Y{y}"].sum() for y in range(1, 11)], dtype=float)
    af, am = np.diff(cf, prepend=0.0), np.diff(cm, prepend=0.0)
    i = v["ratio_food_to_mort"].idxmin()
    return {
        "N": len(v),
        "cum_ratio_10yr": cf[-1] / cm[-1],
        "annual_ratio_y10": af[-1] / am[-1],
        "min_ratio": float(v.loc[i, "ratio_food_to_mort"]),
        "min_iso": v.loc[i, "ISO"],
        "food_10yr_Mt": cf[-1] / 1e6,
        "surv_10yr_Mt": cm[-1] / 1e6,
    }


# ── 1. Who shares Israel's schedule? ──────────────────────────────────────
sim = pd.read_pickle(ROOT / "final_df_imputed.pkl")
lut = (
    sim[["ISO", "age", "Sex", "mortality_rate"]]
    .drop_duplicates(["ISO", "age", "Sex"])
    .set_index(["ISO", "age", "Sex"])["mortality_rate"]
)
isr = lut.xs("ISR", level="ISO")
identical = []
for iso in sorted(sim["ISO"].unique()):
    if iso == "ISR":
        continue
    other = lut.xs(iso, level="ISO")
    common = isr.index.intersection(other.index)
    if len(common) == len(isr) and (isr.loc[common] == other.loc[common]).all():
        identical.append(iso)
print("=" * 90)
print("1. Countries whose mortality schedule is bit-identical to Israel's")
print("=" * 90)
print(f"  all such countries ({len(identical)}): {identical}")

be = pd.read_csv(BE, float_precision="round_trip")
in_set = set(valid(be, "max_uptake")["ISO"])
in_set_identical = sorted(set(identical) & in_set)
print(f"  of those, inside the break-even set ({len(in_set_identical)}): "
      f"{in_set_identical}")
print(f"  the rest are outside it (no OECD factor), so they cannot move a ratio.")
print(f"  dropping for this test: {DROP}"
      f"   (Cyprus retained as defensible)")

# ── 2. Ratios with and without ──────────────────────────────────────────
print()
print("=" * 90)
print("2. Headline with and without ARE + SAU")
print("=" * 90)
rows = []
for sc in ("max_uptake", "mod_uptake"):
    v = valid(be, sc)
    keep = v[~v["ISO"].isin(DROP)]
    a, b = ratios(v), ratios(keep)
    for label, r in (("with", a), ("without", b)):
        rows.append({"scenario": sc, "set": label, **r})
    rows.append({
        "scenario": sc, "set": "change",
        "N": b["N"] - a["N"],
        "cum_ratio_10yr": b["cum_ratio_10yr"] - a["cum_ratio_10yr"],
        "annual_ratio_y10": b["annual_ratio_y10"] - a["annual_ratio_y10"],
        "min_ratio": b["min_ratio"] - a["min_ratio"],
        "min_iso": f"{a['min_iso']}->{b['min_iso']}",
        "food_10yr_Mt": b["food_10yr_Mt"] - a["food_10yr_Mt"],
        "surv_10yr_Mt": b["surv_10yr_Mt"] - a["surv_10yr_Mt"],
    })
out = pd.DataFrame(rows)
print(out.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

print()
print("  Relative movement in the headline ratios:")
for sc in ("max_uptake", "mod_uptake"):
    a = out[(out["scenario"] == sc) & (out["set"] == "with")].iloc[0]
    b = out[(out["scenario"] == sc) & (out["set"] == "without")].iloc[0]
    print(f"    {sc}: cum10 {a['cum_ratio_10yr']:.4f} -> {b['cum_ratio_10yr']:.4f} "
          f"({(b['cum_ratio_10yr']/a['cum_ratio_10yr']-1)*100:+.2f}%);  "
          f"y10 annual {a['annual_ratio_y10']:.4f} -> {b['annual_ratio_y10']:.4f} "
          f"({(b['annual_ratio_y10']/a['annual_ratio_y10']-1)*100:+.2f}%)")

print()
print("  What ARE and SAU each contribute (max_uptake):")
v = valid(be, "max_uptake").set_index("ISO")
tot_f = v["cum_food_Y10"].sum()
tot_m = v["cum_mort_Y10"].sum()
for iso in DROP:
    if iso in v.index:
        r = v.loc[iso]
        print(f"    {iso}: 10-yr food {r['cum_food_Y10']/1e6:8.3f} Mt "
              f"({r['cum_food_Y10']/tot_f*100:5.2f}% of total), "
              f"survivor {r['cum_mort_Y10']/1e6:8.3f} Mt "
              f"({r['cum_mort_Y10']/tot_m*100:5.2f}%), "
              f"own ratio {r['ratio_food_to_mort']:.4f}")
