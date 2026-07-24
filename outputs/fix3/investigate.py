"""Fix #3 investigation (read-only, no pipeline changes).

Quantifies candidate denominators for the demand shock delta:
  current : delta = adult_reduction / adult_EER_pool          (buggy, adult-only)
  faostat : delta = adult_reduction / FAOSTAT_all_ages_kcal   (middle path)

Also reports population shares and the implied adult food-energy share so we
can see whether the FAOSTAT path is a pure population-base correction
(~1.10-1.15x, as predicted) or also mixes in a requirement-vs-supply scale shift.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyreadr

ROOT = Path(r"C:\Users\sethw\repos")
OUT = ROOT / "outputs" / "fix3"
OUT.mkdir(parents=True, exist_ok=True)

# ── simulation (adults 18-89) ────────────────────────────────────────────
sim = list(pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values())[0]
print("sim columns:", list(sim.columns))
sim["w_eer"] = sim["weighting"] * sim["eer"]
sim["w_teer"] = sim["weighting"] * sim["treatment_eer"]

g = sim.groupby(["ISO", "scenario"]).agg(
    adult_pop=("weighting", "sum"),
    adult_EER_pool=("w_eer", "sum"),          # national adult kcal/day requirement
    adult_TEER_pool=("w_teer", "sum"),
).reset_index()
g["adult_reduction"] = g["adult_EER_pool"] - g["adult_TEER_pool"]   # kcal/day, positive
g["delta_current"] = g["adult_TEER_pool"] / g["adult_EER_pool"] - 1  # negative
countries = sim["ISO"].unique()

# ── FAOSTAT FBS: all-ages kcal/capita/day and total population ───────────
iso_map = pd.read_csv(ROOT / "Food data" / "faostat_country_mapping.csv")
fbs = pd.read_csv(
    ROOT / "Food data" / "FoodBalanceSheets_E_All_Data_(Normalized)"
    / "FoodBalanceSheets_E_All_Data_(Normalized).csv"
)
fbs = pd.merge(fbs, iso_map, on="Area", how="left")
fbs = fbs[(fbs["Year"] == 2022) & (fbs["ISO"].isin(countries))]

# all-ages energy per capita per day: sum over the "Grand Total" is item 2901;
# but to be safe sum item-level rows. FAOSTAT provides a Grand Total item too.
kcal = fbs[fbs["Element"] == "Food supply (kcal/capita/day)"]
# Grand Total item code S2901; use it if present, else sum non-aggregate items.
grand = kcal[kcal["Item"] == "Grand Total"].groupby("ISO")["Value"].sum()
kcal_sum_all = kcal.groupby("ISO")["Value"].sum()  # includes aggregates -> double
print("\nGrand Total present for %d countries" % grand.notna().sum())

pop = (fbs[fbs["Element"] == "Total Population - Both sexes"]
       .groupby("ISO")["Value"].mean())  # 1000 persons

f = pd.DataFrame({"kcal_grand": grand, "total_pop_k": pop}).reset_index()
# national all-ages kcal/day = kcal/capita/day * population(persons)
f["faostat_kcal_day"] = f["kcal_grand"] * f["total_pop_k"] * 1000.0

m = pd.merge(g, f, on="ISO", how="left")
# adult pop is in same person units as weighting; total_pop_k is 1000-persons
m["total_pop"] = m["total_pop_k"] * 1000.0
m["adult_pop_share"] = m["adult_pop"] / m["total_pop"]
m["delta_faostat"] = -m["adult_reduction"] / m["faostat_kcal_day"]
m["factor_faostat"] = m["delta_faostat"] / m["delta_current"]        # shrink factor
m["adult_energy_share_faostat"] = m["adult_EER_pool"] / m["faostat_kcal_day"]
# mean per-capita numbers for scale diagnosis
m["adult_eer_percap"] = m["adult_EER_pool"] / m["adult_pop"]
m["faostat_kcal_percap"] = m["kcal_grand"]

max_u = m[m["scenario"] == m["scenario"].unique()[0]].copy()
print("\nscenarios:", list(m["scenario"].unique()))

cols = ["ISO", "scenario", "adult_pop_share", "adult_eer_percap",
        "faostat_kcal_percap", "adult_energy_share_faostat",
        "delta_current", "delta_faostat", "factor_faostat"]
summary = m[cols].dropna(subset=["factor_faostat"])
summary.to_csv(OUT / "denominator_investigation.csv", index=False)

def describe(df, label):
    print(f"\n=== {label} (n={len(df)}) ===")
    for c in ["adult_pop_share", "adult_eer_percap", "faostat_kcal_percap",
              "adult_energy_share_faostat", "factor_faostat"]:
        s = df[c]
        print(f"  {c:28s} median={s.median():.4f}  mean={s.mean():.4f}  "
              f"p10={s.quantile(.1):.4f}  p90={s.quantile(.9):.4f}")

for sc in m["scenario"].unique():
    describe(summary[summary["scenario"] == sc], sc)

print("\nSample rows (max-uptake scenario):")
print(summary[summary["scenario"] == m["scenario"].unique()[0]]
      .sort_values("adult_pop_share").head(8).to_string(index=False))
print(summary[summary["scenario"] == m["scenario"].unique()[0]]
      .sort_values("adult_pop_share").tail(8).to_string(index=False))
print("\nWrote", OUT / "denominator_investigation.csv")
