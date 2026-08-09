"""Per-country data coverage: who is in the complete-data set, and why not.

Replaces ``data_result/country_data_coverage.xlsx``, which had no producer. That
file was built by hand in an interactive R session -- it is untracked, has no git
history, and the only reference to it anywhere on disk is a comment in
``.Rhistory`` saying the country sets were taken *from* it. It had gone stale
without anything to say so: its header column still read "In 35-country complete
set", from before the mortality source changed and the subset became 40.

**One row per modelled country, all 63.** That is wider than the two artefacts it
overlaps, and deliberately:

  * the old xlsx carried 53 -- the food-data sample -- so the seven countries with
    no FAOSTAT food data at all were invisible in it;
  * ``gdp_share_of_global_economy.csv`` also carries 53, for the same reason, and
    reports one exclusion reason ("Missing OECD survivor-emissions factor")
    because that is the only one that arises inside the food-data sample.

Neither shows the three distinct gaps the model actually has. This does.

Gap types, all DERIVED from the committed model outputs rather than listed:

  1. No FAOSTAT food data      -- absent from the food frame entirely
  2. No FAOSTAT price index    -- present, but the equilibrium never solves, so
                                  food savings are NaN rather than zero
  3. No OECD survivor factor   -- food savings exist, but the country cannot be
                                  charged survivor emissions
  4. No mortality data         -- currently empty, and checked rather than assumed

A country can have more than one gap. ``exclusion_reason`` reports the first in
that order, and ``all_gaps`` reports every one, so the cascade's priority cannot
hide a second problem. Anything that lands in none of the four is reported as
unclassified and raises -- the point of this table is that the exclusions are
accounted for, and a silent "other" bucket would defeat it.

Output: data_result/country_data_coverage.csv

Usage:
    python scripts/build_country_coverage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_visualization.breakeven_analysis import (  # noqa: E402
    _complete_data_subset,
    compute_breakeven,
)
from data_visualization.pipeline import (  # noqa: E402
    ROOT,
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)

SCENARIO = "max_uptake"
OUTPUT_FILE = "country_data_coverage.csv"

# World Bank WDI export, used ONLY as a name source for the countries with no
# FAOSTAT row -- there is no other file on disk carrying a name for all 63. Its
# three-line preamble is why the skiprows is here. FAOSTAT names win wherever
# they exist, so this table stays joinable by eye against every other output.
WB_GDP = Path("World Bank") / "World_Bank_National_GDP.csv"
WB_SKIPROWS = 2


def _country_names(food: pd.DataFrame) -> pd.Series:
    """ISO3 -> display name, FAOSTAT first and World Bank for the remainder."""
    faostat = (
        food.dropna(subset=["Country"])
        .drop_duplicates("ISO")
        .set_index("ISO")["Country"]
    )
    wb = pd.read_csv(ROOT / WB_GDP, skiprows=WB_SKIPROWS)
    wb = wb.drop_duplicates("Country Code").set_index("Country Code")["Country Name"]
    return faostat.combine_first(wb)


def build_coverage(scenario: str = SCENARIO) -> pd.DataFrame:
    """One row per modelled country, with its gaps and its status."""
    print("[1/3] Running the price-rebound pipeline...")
    food, result_df = compute_food_savings()

    print("[2/3] Loading survivor emissions and person-years...")
    mort = load_mortality_emissions()

    print("[3/3] Computing break-even...")
    be = compute_breakeven(food, mort)

    # The modelled universe is the mortality file: every country the simulation
    # covers appears there, including the ones with no food data.
    m = mort[mort["scenario"] == scenario].drop_duplicates("ISO").set_index("ISO")
    f = food[food["scenario"] == scenario].drop_duplicates("ISO").set_index("ISO")
    b = be[be["scenario"] == scenario].drop_duplicates("ISO").set_index("ISO")
    complete = set(_complete_data_subset(be, scenario=scenario)["ISO"])

    isos = sorted(m.index)
    names = _country_names(food)

    # Price gap, read straight off the solved frame rather than reclassified: a
    # country whose `price` is NaN on every row has no usable FAOSTAT December
    # 2022 food index, so Cs/Cd are NaN and the equilibrium never solves.
    price_ok = (
        result_df.groupby("ISO")["price"].apply(lambda s: bool(s.notna().any()))
        if "price" in result_df.columns
        else pd.Series(dtype=bool)
    )
    # Cross-check rather than assume: among countries that HAVE food rows, the
    # ones the pipeline could not solve should be exactly the ones missing a
    # price. If a fourth gap type ever appears, this is where it surfaces instead
    # of being absorbed silently.
    #
    # Restricted to the food frame on purpose. A country with no FAOSTAT rows at
    # all has no `price` cell either, so an unrestricted comparison calls all
    # seven of them "missing price" and the check fires on every run over a
    # condition that is really gap type 1, not gap type 2.
    unsolved = set(result_df.attrs.get("unsolved", []))
    priceless = {
        i for i in isos if i in f.index and not bool(price_ok.get(i, False))
    }
    if unsolved != priceless:
        print(
            f"  NOTE: unsolved {sorted(unsolved)} != missing-price "
            f"{sorted(priceless)}. A country is unsolved for a reason other "
            "than price; classify it before quoting this table."
        )

    rows = []
    for iso in isos:
        in_food = iso in f.index
        has_price = bool(price_ok.get(iso, False))
        food_t = float(f.loc[iso, "annual_food_savings_t"]) if in_food else np.nan
        surv = float(b.loc[iso, "total_survivor_emissions_10yr"]) if iso in b.index else np.nan
        py = float(m.loc[iso, "total_person_years_saved"])
        # The OECD factor is read from the survivor-emissions file so it is
        # available for the countries that never reach break-even at all.
        factor = m.get("emissions_factor_Y1", pd.Series(dtype=float)).get(iso, np.nan)
        has_oecd = bool(pd.notna(factor) and factor > 0)
        has_mort = bool(pd.notna(py) and py > 0)

        gaps = []
        if not in_food:
            gaps.append("No FAOSTAT food data")
        elif not has_price:
            gaps.append("No FAOSTAT price index")
        if not has_oecd:
            gaps.append("No OECD survivor-emissions factor")
        if not has_mort:
            gaps.append("No mortality data")

        if iso in complete:
            reason = "None (complete data)"
        elif gaps:
            reason = gaps[0]
        else:
            reason = "UNCLASSIFIED"

        rows.append({
            "ISO": iso,
            "Country": names.get(iso, "?"),
            "in_complete_subset": iso in complete,
            "exclusion_reason": reason,
            "all_gaps": "; ".join(gaps) if gaps else "",
            "has_faostat_food_data": in_food,
            "has_price_index": has_price,
            "has_oecd_survivor_factor": has_oecd,
            "has_mortality": has_mort,
            "annual_food_savings_t": food_t,
            "total_food_savings_10yr_t": (
                float(b.loc[iso, "total_food_savings_10yr"]) if iso in b.index else np.nan
            ),
            "total_survivor_emissions_10yr_t": surv,
            "ratio_food_to_mort": (
                float(b.loc[iso, "ratio_food_to_mort"]) if iso in b.index else np.nan
            ),
            "total_person_years_saved": py,
        })

    out = pd.DataFrame(rows).sort_values(
        ["in_complete_subset", "exclusion_reason", "ISO"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

    bad = out[out["exclusion_reason"] == "UNCLASSIFIED"]
    if not bad.empty:
        raise ValueError(
            "Excluded for an unidentified reason: "
            f"{bad['ISO'].tolist()} -- classify these before quoting this table."
        )
    return out


def assert_scenarios_agree(scenario_a: str = "max_uptake",
                           scenario_b: str = "mod_uptake") -> None:
    """The complete set must not depend on uptake, or the table needs a column.

    Same guard ``gdp_share_of_global_economy.R`` applies for the same reason: the
    manuscript quotes one country count, so a disagreement would need a decision
    rather than a silent choice of scenario.
    """
    food, _ = compute_food_savings()
    be = compute_breakeven(food, load_mortality_emissions())
    a = set(_complete_data_subset(be, scenario=scenario_a)["ISO"])
    b = set(_complete_data_subset(be, scenario=scenario_b)["ISO"])
    if a != b:
        raise ValueError(
            f"Complete-data set differs by uptake: only in {scenario_a} "
            f"{sorted(a - b)}, only in {scenario_b} {sorted(b - a)}."
        )


def main() -> None:
    print("=" * 72)
    print("COUNTRY DATA COVERAGE")
    print("=" * 72)
    out = build_coverage()

    path = output_path(OUTPUT_FILE)
    out.to_csv(path, index=False)

    n_complete = int(out["in_complete_subset"].sum())
    print(f"\n  Modelled countries : {len(out)}")
    print(f"  Complete-data set  : {n_complete}")
    print(f"  Excluded           : {len(out) - n_complete}")
    print("\n  Exclusion reasons (derived, not listed):")
    for reason, grp in out[~out["in_complete_subset"]].groupby("exclusion_reason"):
        print(f"    {reason:38s} {len(grp):2d}  {' '.join(sorted(grp['ISO']))}")

    multi = out[out["all_gaps"].str.contains(";", na=False)]
    if not multi.empty:
        print("\n  Countries with more than one gap:")
        for _, r in multi.iterrows():
            print(f"    {r['ISO']}  {r['all_gaps']}")

    print(f"\nCoverage table -> {path}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
