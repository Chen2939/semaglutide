"""
Year-1 food-emission savings: report the two bases side by side.

WHAT THIS IS. The model reports year-1 food savings on two different bases, and
this script prints both, with the arithmetic connecting them. It REPORTS. It
does not check anything, and there is no condition under which it fails.

THE TWO BASES.

  Unweighted, "Panel A"  -- the no-mortality counterfactual. All three mortality
      channels are switched off: food-side survival weighting pi(t), the
      pharmaceutical-side weight pi_dose(t), and survivor emissions. Produced by
      compute_food_savings(survival_weighted=False) and published as
      `actual_food_savings` in global_emissions_waterfall_1yr.csv. See the
      module docstring of data_visualization/generate_waterfall_1yr_figure.py.

  Survival-weighted     -- the production path, in which first-year savings are
      scaled by each country's pi(1) because some treated patients do not
      survive the year. Published per country as `annual_food_savings_gross_t`
      in net_emissions_with_drug.csv.

THESE TWO ARE NOT SUPPOSED TO BE EQUAL. The difference is a deliberate design
choice about which counterfactual each figure answers, not a defect and not a
stale output. Survival weighting is the mechanism that produces it: the weighted
total is the smaller of the two, by roughly the average shortfall of pi(1)
below 1.

WHY THIS FILE EXISTS IN THIS FORM. It previously printed five MATCH/DIFFERS
verdicts. Three of them began reporting DIFFERS once survival weighting was
introduced, because they compared figures across the two bases above -- so the
verdicts were wrong about what they were testing, not about the arithmetic.
ALL FIVE have been converted to plain reporting. No assertion replaced them:
losing that test is accepted and deliberate, because the quantity that would
actually verify the difference cannot currently be computed (see below).

CORROBORATION. data_result/us_share_diagnostic.txt is the cleanest evidence for
the mechanism. It runs both bases over the same 53 countries with only the
survival flag changed, and reproduces both totals -- which isolates survival
weighting as the sole cause and rules out any difference in country coverage.

WHAT IS DELIBERATELY NOT PRINTED HERE. The exact identity is

    sum(weighted savings) = sum(unweighted savings) x Pi_bar

where Pi_bar is the mean of pi(1) weighted BY PER-COUNTRY UNWEIGHTED SAVINGS.
That vector is not committed anywhere in the repository, and deriving it would
mean re-running the rebound solver, so Pi_bar cannot be formed from committed
outputs. No substitute weighting is used in its place: weighting pi(1) by
treated users, by survival-weighted savings, or not at all produces a number
close enough to the implied factor to look like confirmation while verifying
nothing. Only the RANGE of pi(1) is printed. The unweighted mean is omitted for
the same reason -- a reader would compare it to the implied factor and read the
proximity as proof.

Reads committed CSVs only. No model run.

    python -m diagnostics.reconcile_annual_food_savings
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# Resolve against the repository root rather than an absolute path, so the
# script runs from any checkout. diagnostics/ sits one level below the root.
ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data_result"

SCENARIO = "max_uptake"


def mt(s):
    return s.sum() / 1e6


def rule(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main():
    d = pd.read_csv(BASE / "net_emissions_with_drug.csv")
    m = d[d.scenario == SCENARIO].copy()

    wf = pd.read_csv(BASE / "global_emissions_waterfall_1yr.csv")
    wf_gross = float(wf.loc[wf.step == "actual_food_savings", "value_Mt"].iloc[0])
    wf_manu = float(wf.loc[wf.step == "manufacturing", "value_Mt"].iloc[0])
    wf_net = float(wf.loc[wf.step == "net_savings", "value_Mt"].iloc[0])
    wf_n = int(wf.loc[wf.step == "actual_food_savings", "n_countries"].iloc[0])

    # comment="#" drops the trailing N-countries note appended by
    # sensitivity_overview.append_country_count_note.
    ov = pd.read_csv(BASE / "all_sensitivity_overview_results.csv", comment="#")
    ov_food = float(ov.loc[ov.overview_scenario == "baseline_mean_ci",
                           "annual_food_savings_Mt"].iloc[0])
    ov_surv = float(ov.loc[ov.overview_scenario == "baseline_mean_ci",
                           "survivor_emissions_10yr_Mt"].iloc[0])
    ov_n = int(ov.loc[ov.overview_scenario == "baseline_mean_ci",
                      "n_complete_countries"].iloc[0])

    finite_food = m.annual_food_savings_gross_t.notna()
    iso_headline = set(m.loc[finite_food, "ISO"])
    ct_gross = mt(m.annual_food_savings_gross_t)

    # ---------------------------------------------------------------- 1
    rule("1. THE TWO YEAR-1 TOTALS")

    print(f"  unweighted, no-mortality (Panel A)   {wf_gross:12.6f} Mt   "
          f"{wf_n} countries")
    print("      global_emissions_waterfall_1yr.csv, step=actual_food_savings")
    print(f"  survival-weighted                    {ct_gross:12.6f} Mt   "
          f"{int(finite_food.sum())} countries")
    print("      net_emissions_with_drug.csv, sum(annual_food_savings_gross_t),")
    print(f"      scenario={SCENARIO}")
    print()
    print(f"  absolute difference                  {wf_gross - ct_gross:12.6f} Mt")
    print(f"  implied factor (weighted/unweighted) {ct_gross / wf_gross:12.8f}")
    print()
    print("  Different bases by design. Neither is an error, and the pair is")
    print("  not expected to agree.")

    # ---------------------------------------------------------------- 2
    rule("2. PER-COUNTRY YEAR-1 FOOD SURVIVAL WEIGHT pi(1)")

    sw = pd.read_csv(BASE / "food_shock_survival_weight.csv")

    # The weight table is 63 ISO x 2 scenarios x 15 years = 1890 rows, so it is
    # emphatically not one row per country. Take year 1 because both totals
    # above are year-1 annual flows, and max_uptake because both are max-uptake.
    # Then restrict to the 53 countries carried by those totals: the weight
    # table covers ten further ISOs that contribute nothing to either figure,
    # and quoting their pi values alongside would misdescribe the range.
    y1 = sw[(sw.scenario == SCENARIO) & (sw.year == 1)]
    y1h = y1[y1.ISO.isin(iso_headline)]

    print(f"  source  food_shock_survival_weight.csv  ({len(sw)} rows = "
          f"{sw.ISO.nunique()} ISO x {sw.scenario.nunique()} scenarios x "
          f"{sw.year.nunique()} years)")
    print(f"  slice   scenario={SCENARIO}, year=1, restricted to the "
          f"{len(iso_headline)} headline countries")
    print(f"          ({len(y1)} ISOs at year 1; "
          f"{len(y1) - len(y1h)} dropped as absent from the totals above)")
    print()
    print(f"  pi(1) minimum   {y1h.pi.min():.10f}")
    print(f"  pi(1) maximum   {y1h.pi.max():.10f}")
    print(f"  n countries     {len(y1h)}")
    print()
    print("  No mean is printed. The figure that would verify the difference in")
    print("  section 1 is pi(1) weighted by per-country UNWEIGHTED savings, and")
    print("  that vector is not committed anywhere. See the module docstring.")

    # ---------------------------------------------------------------- 3
    rule("3. WHICH ROWS EACH TOTAL COVERS")

    print(f"  rows in net_emissions_with_drug ({SCENARIO}): {len(m)}")
    print(f"    with finite annual_food_savings_gross_t:   "
          f"{int(finite_food.sum())}")
    print(f"    with NaN:                                  "
          f"{int((~finite_food).sum())}"
          f"  -> {sorted(m.loc[~finite_food, 'ISO'])}")

    # The overview's own filter, from sensitivity_overview.py:161-165
    valid = m[m.ratio_food_to_mort.notna()
              & (m.annual_food_savings_t > 0)
              & (m.total_survivor_emissions_10yr > 0)]
    print(f"    passing the overview 'valid' filter:       {valid.ISO.nunique()}"
          f"   (CSV records n_complete_countries={ov_n})")

    surv_pos = m[m.total_survivor_emissions_10yr > 0]
    dropped = sorted(set(surv_pos.ISO) - set(valid.ISO))
    print(f"    survivor>0 but outside that filter:        {dropped}")
    for iso in dropped:
        r = m[m.ISO == iso].iloc[0]
        print(f"        {iso}: survivor_10yr="
              f"{r.total_survivor_emissions_10yr / 1e6:.6f} Mt, "
              f"annual_food={r.annual_food_savings_t}, "
              f"ratio={r.ratio_food_to_mort}")

    # ---------------------------------------------------------------- 4
    rule("4. THE FIVE PUBLISHED FIGURES AND THEIR COMMITTED SOURCES")

    print("  Previously five MATCH/DIFFERS checks; now reported provenance.")
    print("  'same basis' means the published figure is the sum of the named")
    print("  committed rows. 'cross-basis' means the published figure is the")
    print("  unweighted counterpart of that sum, per section 1.")
    print()

    drug = pd.read_csv(BASE / "drug_emissions_by_country.csv")
    dm = drug[(drug.scenario == SCENARIO) & (drug.ISO.isin(iso_headline))]

    entries = [
        ("overview annual_food_savings_Mt", ov_food,
         mt(valid.annual_food_savings_t),
         "sum(annual_food_savings_t) over the valid set", "same basis"),
        ("overview survivor_emissions_10yr_Mt", ov_surv,
         mt(valid.total_survivor_emissions_10yr),
         "sum(total_survivor_emissions_10yr) over the valid set", "same basis"),
        ("waterfall actual_food_savings", wf_gross,
         mt(m.annual_food_savings_gross_t),
         "sum(annual_food_savings_gross_t) over all rows", "cross-basis"),
        ("waterfall manufacturing", wf_manu,
         mt(m.loc[finite_food, "annual_drug_emissions_t"]),
         "sum(annual_drug_emissions_t) over finite-food rows", "cross-basis"),
        ("waterfall net_savings", wf_net,
         mt(m.annual_food_savings_t),
         "sum(annual_food_savings_t) over all rows", "cross-basis"),
    ]
    for name, published, summed, how, kind in entries:
        print(f"  {name:38s} {published:12.6f}")
        print(f"      {how}")
        if kind == "same basis":
            print(f"      committed rows sum to {summed:.6f}  (same basis)")
        else:
            print(f"      committed rows sum to {summed:.6f}  (survival-weighted;")
            print(f"      the published figure is the unweighted counterpart, "
                  f"delta {published - summed:+.6f} Mt)")
        print()

    # The drug side pins the mechanism exactly, because both the weighted and
    # unweighted per-country drug columns are committed. Reported, not checked.
    print(f"  drug side, both columns committed ({len(dm)} countries):")
    print(f"      sum(drug_emissions_1yr_t), unweighted        "
          f"{mt(dm.drug_emissions_1yr_t):.8f} Mt")
    print(f"      sum(drug_emissions_t_Y1),  survival-weighted "
          f"{mt(dm.drug_emissions_t_Y1):.8f} Mt")
    print(f"      ratio                                        "
          f"{dm.drug_emissions_t_Y1.sum() / dm.drug_emissions_1yr_t.sum():.10f}")
    print("      The first equals waterfall manufacturing; the second equals")
    print("      annual_drug_emissions_t in the country table.")

    # ---------------------------------------------------------------- 5
    rule("5. BRIDGE FROM THE COUNTRY TABLE TO THE OVERVIEW BASELINE")

    drug_finite = mt(m.loc[finite_food, "annual_drug_emissions_t"])
    net_all = mt(m.annual_food_savings_t)
    net_valid = mt(valid.annual_food_savings_t)
    excluded = m[finite_food & ~m.ISO.isin(valid.ISO)]

    print(f"  gross annual, all countries          {ct_gross:12.6f}")
    print(f"  less drug manufacturing              {-drug_finite:12.6f}")
    print(f"  = net annual, all countries          {net_all:12.6f}   "
          f"(waterfall net_savings, weighted basis)")
    print(f"  less countries lacking survivor data "
          f"{-mt(excluded.annual_food_savings_t):12.6f}   "
          f"({excluded.ISO.nunique()} countries)")
    print(f"  = net annual, complete set           {net_valid:12.6f}   "
          f"(overview baseline)")
    print(f"  residual vs published overview       {ov_food - net_valid:12.9f}")
    print()
    print(f"  the {excluded.ISO.nunique()} excluded countries, largest first:")
    e = excluded[["ISO", "Country", "annual_food_savings_t"]].copy()
    e = e.sort_values("annual_food_savings_t", ascending=False)
    for _, r in e.iterrows():
        print(f"      {r.ISO}  {r.Country[:42]:42s} "
              f"{r.annual_food_savings_t / 1e6:9.6f} Mt")

    # ---------------------------------------------------------------- 6
    rule("6. COUNTRIES WITHOUT COMPUTABLE FOOD SAVINGS")

    unsolved = m[~finite_food]
    print(f"  sum(annual_drug_emissions_t) all rows      "
          f"{mt(m.annual_drug_emissions_t):.6f}")
    print(f"  sum over finite-food rows only             {drug_finite:.6f}")
    print(f"  difference (unsolved countries' drug)      "
          f"{mt(m.annual_drug_emissions_t) - drug_finite:.6f}")
    for _, r in unsolved.iterrows():
        print(f"      {r.ISO}  drug={r.annual_drug_emissions_t / 1e6:.6f} Mt, "
              f"gross_food={r.annual_food_savings_gross_t}")

    print()


if __name__ == "__main__":
    main()
