"""
Reconcile the three annual food-savings totals that disagree.

  51.856697  data_result/all_sensitivity_overview_results.csv (baseline row)
  53.942134  data_result/global_emissions_waterfall_1yr.csv  (actual_food_savings)
  52.609522  data_result/global_emissions_waterfall_1yr.csv  (net_savings)

Question: is the 51.9 an error, or a different basis? Reads committed CSVs only
-- no model run.
"""

import io
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE = r"C:\Users\sethw\repos\data_result"


def mt(s):
    return s.sum() / 1e6


def main():
    d = pd.read_csv(f"{BASE}\\net_emissions_with_drug.csv")
    m = d[d.scenario == "max_uptake"].copy()

    wf = pd.read_csv(f"{BASE}\\global_emissions_waterfall_1yr.csv")
    wf_gross = float(wf.loc[wf.step == "actual_food_savings", "value_Mt"].iloc[0])
    wf_manu = float(wf.loc[wf.step == "manufacturing", "value_Mt"].iloc[0])
    wf_net = float(wf.loc[wf.step == "net_savings", "value_Mt"].iloc[0])

    # comment="#" drops the trailing N-countries note appended by
    # sensitivity_overview.append_country_count_note.
    ov = pd.read_csv(f"{BASE}\\all_sensitivity_overview_results.csv", comment="#")
    ov_food = float(ov.loc[ov.overview_scenario == "baseline_mean_ci",
                           "annual_food_savings_Mt"].iloc[0])
    ov_surv = float(ov.loc[ov.overview_scenario == "baseline_mean_ci",
                           "survivor_emissions_10yr_Mt"].iloc[0])
    ov_n = int(ov.loc[ov.overview_scenario == "baseline_mean_ci",
                      "n_complete_countries"].iloc[0])

    print("=" * 78)
    print("1. WHICH ROWS EACH TOTAL IS SUMMING")
    print("=" * 78)
    print(f"rows in net_emissions_with_drug (max_uptake): {len(m)}")
    finite_food = m.annual_food_savings_t.notna()
    print(f"  with finite annual_food_savings_t:          {finite_food.sum()}")
    print(f"  with NaN annual_food_savings_t:             {(~finite_food).sum()}"
          f"  -> {sorted(m.loc[~finite_food, 'ISO'])}")

    # The overview's own filter, from sensitivity_overview.py:161-165
    valid = m[m.ratio_food_to_mort.notna()
              & (m.annual_food_savings_t > 0)
              & (m.total_survivor_emissions_10yr > 0)]
    print(f"  passing the overview 'valid' filter:        {valid.ISO.nunique()}"
          f"   (CSV says n_complete_countries={ov_n})")

    surv_pos = m[m.total_survivor_emissions_10yr > 0]
    dropped = sorted(set(surv_pos.ISO) - set(valid.ISO))
    print(f"  survivor>0 but failing the filter:          {dropped}")
    for iso in dropped:
        r = m[m.ISO == iso].iloc[0]
        print(f"      {iso}: survivor_10yr={r.total_survivor_emissions_10yr/1e6:.6f} Mt, "
              f"annual_food={r.annual_food_savings_t}, ratio={r.ratio_food_to_mort}")

    print()
    print("=" * 78)
    print("2. DOES EACH PUBLISHED NUMBER REPRODUCE?")
    print("=" * 78)
    checks = [
        ("overview annual_food_savings_Mt", ov_food,
         mt(valid.annual_food_savings_t), "sum(annual_food_savings_t) over valid"),
        ("overview survivor_emissions_10yr_Mt", ov_surv,
         mt(valid.total_survivor_emissions_10yr),
         "sum(total_survivor_emissions_10yr) over valid"),
        ("waterfall actual_food_savings", wf_gross,
         mt(m.annual_food_savings_gross_t),
         "sum(annual_food_savings_gross_t) over ALL rows"),
        ("waterfall manufacturing", wf_manu,
         mt(m.loc[finite_food, "annual_drug_emissions_t"]),
         "sum(annual_drug_emissions_t) over finite-food rows"),
        ("waterfall net_savings", wf_net,
         mt(m.annual_food_savings_t), "sum(annual_food_savings_t) over ALL rows"),
    ]
    for name, published, recomputed, how in checks:
        delta = published - recomputed
        ok = "MATCH" if abs(delta) < 5e-7 else f"DIFFERS by {delta:+.6f}"
        print(f"  {name:38s} {published:12.6f}  vs {recomputed:12.6f}  {ok}")
        print(f"      {how}")

    print()
    print("=" * 78)
    print("3. THE 53.94 -> 51.86 GAP, ITEMISED")
    print("=" * 78)
    gross_all = mt(m.annual_food_savings_gross_t)
    drug_finite = mt(m.loc[finite_food, "annual_drug_emissions_t"])
    net_all = mt(m.annual_food_savings_t)
    net_valid = mt(valid.annual_food_savings_t)
    excluded = m[finite_food & ~m.ISO.isin(valid.ISO)]

    print(f"  gross annual, all countries          {gross_all:12.6f}")
    print(f"  less drug manufacturing              {-drug_finite:12.6f}")
    print(f"  = net annual, all countries          {net_all:12.6f}   "
          f"(waterfall net_savings)")
    print(f"  less countries lacking survivor data {-mt(excluded.annual_food_savings_t):12.6f}   "
          f"({excluded.ISO.nunique()} countries)")
    print(f"  = net annual, complete set           {net_valid:12.6f}   "
          f"(overview baseline)")
    print(f"  residual vs published overview       "
          f"{ov_food - net_valid:12.9f}")
    print()
    print(f"  the {excluded.ISO.nunique()} excluded countries, largest first:")
    e = excluded[["ISO", "Country", "annual_food_savings_t"]].copy()
    e = e.sort_values("annual_food_savings_t", ascending=False)
    for _, r in e.iterrows():
        print(f"      {r.ISO}  {r.Country[:42]:42s} {r.annual_food_savings_t/1e6:9.6f} Mt")

    print()
    print("=" * 78)
    print("4. DRUG EMISSIONS OF THE UNSOLVED COUNTRIES")
    print("=" * 78)
    unsolved = m[~finite_food]
    print(f"  sum(annual_drug_emissions_t) all rows      {mt(m.annual_drug_emissions_t):.6f}")
    print(f"  sum over finite-food rows only             {drug_finite:.6f}")
    print(f"  difference (unsolved countries' drug)      "
          f"{mt(m.annual_drug_emissions_t) - drug_finite:.6f}")
    for _, r in unsolved.iterrows():
        print(f"      {r.ISO}  drug={r.annual_drug_emissions_t/1e6:.6f} Mt, "
              f"gross_food={r.annual_food_savings_gross_t}")


if __name__ == "__main__":
    main()
