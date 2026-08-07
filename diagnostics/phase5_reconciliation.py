"""Phase 5: the reconciliation table.

Every number, its pre-regeneration value, and its value under each run, with
the successive differences. Five value columns, which is the point of Phase 3:

  OLD    the committed pre-regeneration figures
  A      BMI fix only            (cohort height off, height loss off)
  B      + cohort-matched height (height loss off)
  C      + age-related height loss   <- the production population
  D      + section 2.15 continuous hazard above BMI 40

LABELLING, which is load-bearing here. Two different food:survivor ratios
appear in the manuscript and they are not comparable to each other:

  * CUMULATIVE 10-YEAR -- total food savings over ten years divided by total
    survivor emissions over ten years. This is the one the manuscript quotes
    as 1.8.
  * YEAR-10 FLOW -- the tenth year's annual food saving divided by the tenth
    year's survivor emissions. Around 1.0.

A reader comparing 1.8 against 1.0006 without the label concludes something
false. Every ratio row below states which it is.

CRN FLAG. The moderate-uptake column carries the section 2.9 common-random-
numbers change on top of the three population changes: the old moderate figures
came from an independent draw, the new ones from a strict subset of the maximum
set. max_uptake is the clean old-versus-new comparison; moderate is not.

ASCII only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data_result" / "regeneration"
OUT = ROOT / "diagnostics" / "reports" / "phase5_reconciliation.md"

RUNS = ["A", "B", "C", "D"]
lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    lines.append(s)


def fmt(v, nd=4):
    if v is None:
        return "--"
    if isinstance(v, str):
        return v
    return f"{v:,.{nd}f}" if abs(v) < 1e5 else f"{v:,.0f}"


def row(label, old, vals, nd=4, crn=False, note=""):
    """One table row: label | OLD | A | B | C | D | OLD->D | note."""
    cells = [fmt(old, nd)] + [fmt(vals.get(r), nd) for r in RUNS]
    if isinstance(old, (int, float)) and isinstance(vals.get("D"), (int, float)):
        d = vals["D"] - old
        pct = (vals["D"] / old - 1) * 100 if old else float("nan")
        delta = f"{d:+,.{nd}f} ({pct:+.1f}%)"
    elif old is not None and vals.get("D") is not None and old != vals.get("D"):
        delta = f"**{old} -> {vals['D']}**"
    else:
        delta = "--"
    flag = " **[CRN]**" if crn else ""
    say(f"| {label}{flag} | " + " | ".join(cells) + f" | {delta} | {note} |")


def main() -> int:
    M = {}
    for r in RUNS:
        p = REG / f"phase5_metrics_run{r}.json"
        if not p.is_file():
            raise SystemExit(f"missing {p}")
        M[r] = json.load(open(p, encoding="utf-8"))

    ref = pd.read_csv(ROOT / "reference" / "reference_headline_numbers.csv")
    ref = ref[ref.run == "survival_weighted"].set_index("scenario")

    def old_ref(col, sc):
        return float(ref.loc[sc, col])

    say("# phase5_reconciliation")
    say()
    say("Pre-regeneration values against each separability run. See this "
        "script's docstring for what A/B/C/D are and for the ratio-labelling "
        "rule.")
    say()
    say("**Ratio labelling.** `CUM-10Y` is the cumulative ten-year "
        "food:survivor ratio -- the figure the manuscript quotes as 1.8. "
        "`Y10-FLOW` is the tenth year's annual saving over the tenth year's "
        "survivor emissions, which sits near 1.0. **They are different "
        "quantities and must not be compared to one another.**")
    say()
    say("**[CRN]** marks a row where the moderate-uptake figure also carries "
        "the section 2.9 common-random-numbers change, so its old-versus-new "
        "difference is not attributable to the population changes alone. "
        "`max_uptake` is the clean comparison.")
    say()

    HDR = ("| quantity | OLD | A | B | C | D | OLD -> D | note |\n"
           "|---|--:|--:|--:|--:|--:|--:|---|")

    # ---------------------------------------------------------------- food
    say("## Food emissions and savings")
    say()
    say(HDR)
    row("baseline food emissions (Mt)",
        old_ref("baseline_food_emissions_mt", "max_uptake"),
        {r: M[r]["baseline food emissions (Mt)"] for r in RUNS}, 4,
        note="simulation-independent; must not move")
    for sc, crn in (("max_uptake", False), ("mod_uptake", True)):
        row(f"annual food savings, year 1 (Mt) [{sc}]",
            old_ref("total_annual_food_savings_mt", sc),
            {r: M[r][f"annual food savings [{sc}]"] for r in RUNS}, 4, crn)
    say()

    # -------------------------------------------------------------- ratios
    say("## Food:survivor ratios")
    say()
    say(HDR)
    for sc, crn in (("max_uptake", False), ("mod_uptake", True)):
        row(f"**CUM-10Y** food:survivor [{sc}]",
            old_ref("cum_food_to_survivor_ratio_10yr", sc),
            {r: M[r][f"cum 10-yr food:survivor [{sc}]"] for r in RUNS}, 4, crn,
            "the manuscript's 1.8")
    for sc, crn in (("max_uptake", False), ("mod_uptake", True)):
        row(f"**Y10-FLOW** food:survivor [{sc}]",
            old_ref("annual_food_to_survivor_ratio_y10", sc),
            {r: M[r][f"yr-10 annual food:survivor [{sc}]"] for r in RUNS}, 4, crn,
            "NOT the 1.8 figure")
    for sc, crn in (("max_uptake", False), ("mod_uptake", True)):
        row(f"**CUM-10Y** minimum-country ratio [{sc}]",
            old_ref("min_country_ratio_10yr", sc),
            {r: M[r][f"min-country ratio 10-yr [{sc}]"] for r in RUNS}, 4, crn)
        row(f"minimum-country identity [{sc}]",
            ref.loc[sc, "min_country_iso"],
            {r: M[r][f"min-country iso [{sc}]"] for r in RUNS}, 0, crn)
    say()

    # --------------------------------------------------------- sensitivity
    say("## Table 1 -- sensitivity specifications")
    say()
    say("All ratios here are **CUM-10Y** unless the row says `Y10-FLOW`. "
        "`N < 1` is the count of countries whose ratio falls below one.")
    say()
    suite = pd.read_csv(ROOT / "reference" / "reference_sensitivity_suite.csv")
    suite = suite.set_index(["scenario_spec", "uptake"])
    say(HDR)
    for spec in ("P10", "P90", "combined_conservative"):
        for sc, crn in (("max_uptake", False), ("mod_uptake", True)):
            row(f"{spec} **CUM-10Y** [{sc}]",
                float(suite.loc[(spec, sc), "cum_ratio_10yr"]),
                {r: M[r][f"{spec} [{sc}] cum10"] for r in RUNS}, 4, crn)
            row(f"{spec} **Y10-FLOW** [{sc}]",
                float(suite.loc[(spec, sc), "annual_ratio_y10"]),
                {r: M[r][f"{spec} [{sc}] y10"] for r in RUNS}, 4, crn)
            row(f"{spec} min-country ratio [{sc}]",
                float(suite.loc[(spec, sc), "min_country_ratio"]),
                {r: M[r][f"{spec} [{sc}] min"] for r in RUNS}, 4, crn)
            row(f"{spec} min-country [{sc}]",
                suite.loc[(spec, sc), "min_country_iso"],
                {r: M[r][f"{spec} [{sc}] min-iso"] for r in RUNS}, 0, crn)
            row(f"{spec} **N < 1** [{sc}]",
                float(suite.loc[(spec, sc), "n_tipping_countries"]),
                {r: M[r][f"{spec} [{sc}] tipping"] for r in RUNS}, 0, crn,
                "flagged: this column moves")
            row(f"{spec} N complete countries [{sc}]",
                float(suite.loc[(spec, sc), "n_complete_countries"]),
                {r: M[r][f"{spec} [{sc}] n_complete"] for r in RUNS}, 0, crn)
        say("| | | | | | | | |")
    say()

    # ---------------------------------------------------------- mortality
    say("## Mortality and survivors")
    say()
    say("**A, B and C are identical here by construction, and that is a "
        "verified result rather than an assumption**: G7 established that "
        "`bmi`, both hazard-ratio columns and every survivor count are "
        "bit-identical across the three height variants, because "
        "`new_bmi = bmi * (1 - effect)` is independent of height. Only "
        "section 2.15 (column D) moves these.")
    say()
    say(HDR)
    MORT = {
        "average HR reduction (%) [max_uptake]":
            (18.6, {"A": 17.0985, "B": 17.0985, "C": 17.0985, "D": 17.2115}, 4,
             False, "**prose rewrite, not renumbering** -- see below"),
        "average HR reduction (%) [mod_uptake]":
            (18.4, {"A": 17.2378, "B": 17.2378, "C": 17.2378, "D": 17.2797}, 4,
             True, "**prose rewrite, not renumbering**"),
        "treated users (millions) [max_uptake]":
            (252.6, {r: 238.757004 for r in RUNS}, 3, False, ""),
        "treated users (millions) [mod_uptake]":
            (132.2, {r: 126.558552 for r in RUNS}, 3, True, ""),
        "extra survivors at year 10 [max_uptake]":
            (3_150_000.0,
             {"A": 2_781_417.0, "B": 2_781_417.0, "C": 2_781_417.0,
              "D": 2_787_760.0}, 0, False, ""),
        "extra survivors at year 10 [mod_uptake]":
            (1_660_000.0,
             {"A": 1_471_787.0, "B": 1_471_787.0, "C": 1_471_787.0,
              "D": 1_470_478.0}, 0, True, ""),
        "cumulative 10-yr person-years [max_uptake]":
            (16_830_000.0,
             {"A": 14_885_784.0, "B": 14_885_784.0, "C": 14_885_784.0,
              "D": 14_924_338.0}, 0, False, ""),
        "cumulative 10-yr person-years [mod_uptake]":
            (8_890_000.0,
             {"A": 7_882_658.0, "B": 7_882_658.0, "C": 7_882_658.0,
              "D": 7_881_235.0}, 0, True, ""),
    }
    for k, (o, v, nd, crn, note) in MORT.items():
        row(k, o, v, nd, crn, note)
    say()

    # --------------------------------------------------------- population
    say("## Population diagnostics")
    say()
    say("From the simulation directly. C and D share one population, so their "
        "columns are equal here by definition.")
    say()
    say(HDR)
    POP = {
        "eligible population (weighted)":
            (None, {r: 251_535_990.0 for r in RUNS}, 0, False,
             "identical across scenarios under CRN"),
        "treated population [max_uptake]":
            (None, {r: 238_757_004.0 for r in RUNS}, 0, False, ""),
        "treated population [mod_uptake]":
            (None, {r: 126_558_552.0 for r in RUNS}, 0, True, ""),
        "mean EER reduction (%), weighted [max_uptake]":
            (None, {"A": 6.790432, "B": 6.781274, "C": 6.774525,
                    "D": 6.774525}, 6, False,
             "the manuscript's ~7%; was 6.815471 unweighted"),
        "mean EER reduction (kcal/day) [max_uptake]":
            (None, {"A": 206.2336, "B": 203.6991, "C": 200.3491,
                    "D": 200.3491}, 4, False, ""),
        "mean height loss applied, men (cm)":
            (0.0, {"A": 0.0, "B": 0.0, "C": 1.357571, "D": 1.357571}, 6,
             False, "diagnostic row"),
        "mean height loss applied, women (cm)":
            (0.0, {"A": 0.0, "B": 0.0, "C": 2.570193, "D": 2.570193}, 6,
             False, "diagnostic row"),
        "realized top-band mean BMI (unweighted)":
            (50.0, {r: 44.4371 for r in RUNS}, 4, False,
             "target 44.4343; OLD is the implied value of the retired grid"),
        "population-weighted BMI >= 30 deviation (pp)":
            (1.566470, {r: -0.225145 for r in RUNS}, 6, False,
             "G2; bar was 0.370345 pp"),
    }
    for k, (o, v, nd, crn, note) in POP.items():
        row(k, o, v, nd, crn, note)
    say()

    # ------------------------------------------------------------- flags
    # ------------------------------------------------- downstream emissions
    say("## Downstream emissions, rebound and per-patient-year")
    say()
    say("Run D only. These come from the full analysis suite, which was run "
        "once on the production population; A/B/C were carried only as far as "
        "the 47 headline metrics, because the suite is a ~40-minute pass and "
        "the attribution above already localises the movement.")
    say()
    say("The OLD column here is the figure **as quoted in the manuscript**. "
        "Where it differs slightly from the committed reference CSV that is a "
        "pre-existing discrepancy, not something this regeneration introduced "
        "-- flagged per row.")
    say()
    say("| quantity | OLD (manuscript) | Run D | change | note |")
    say("|---|--:|--:|--:|---|")

    def d2(label, old, new, nd=1, note=""):
        if old is None:
            say(f"| {label} | -- | {new:,.{nd}f} | -- | {note} |")
        else:
            say(f"| {label} | {old:,.{nd}f} | {new:,.{nd}f} | "
                f"{new-old:+,.{nd}f} ({(new/old-1)*100:+.1f}%) | {note} |")

    d2("annual food savings gross, max (Mt)", 54.2, 50.7726, 4,
       "committed reference says 53.9421; the 0.26 gap to 54.2 is pre-existing")
    d2("annual food savings gross, mod (Mt)", 27.8, 26.8892, 4, "**[CRN]**")
    d2("net of pharmaceutical production, max (Mt)", 52.9, 49.5188, 4, "")
    d2("net of pharmaceutical production, mod (Mt)", 27.1, 26.2243, 4,
       "**[CRN]**")
    say("| | | | | |")
    d2("10-yr naive reduction, max (Mt)", None, 1004.3017, 4,
       "before rebound, survival-weighted, 40 countries")
    d2("10-yr rebound effect, max (Mt)", None, 520.4219, 4, "")
    d2("**rebound offset, 10-yr, max (%)**", None,
       520.421893 / 1004.301677 * 100, 2, "rebound / naive")
    d2("10-yr actual food savings, max (Mt)", None, 483.8798, 4, "after rebound")
    d2("10-yr survivorship emissions, max (Mt)", None, 243.0025, 4, "")
    d2("10-yr manufacturing emissions, max (Mt)", None, 11.7841, 4, "")
    d2("**10-yr cumulative net savings, max (Mt)**", 230.0, 229.0933, 4,
       "the manuscript's 230")
    d2("**10-yr net, declining-emissions variant (Mt)**", 251.0, 247.9602, 4,
       "survivor GHG declining 2%/yr; the manuscript's 251")
    say("| | | | | |")
    d2("1-yr naive reduction, max (Mt)", None, 106.5321, 4,
       "no-mortality basis, 53 countries")
    d2("1-yr rebound effect, max (Mt)", None, 55.4875, 4, "")
    d2("**rebound offset, 1-yr, max (%)**", None,
       55.487490 / 106.532147 * 100, 2, "")
    d2("1-yr net savings, max (Mt)", None, 49.7838, 4, "")
    say("| | | | | |")
    d2("**per patient-year, rebound + manufacturing only (kg)**", 214.0,
       212.4289, 2, "Panel A, 1-yr, no mortality; the manuscript's 214")
    d2("per patient-year, same basis, mod (kg)", None, 212.1556, 2, "**[CRN]**")
    d2("**per patient-year, including survivorship (kg)**", 99.0, 104.5924, 2,
       "Panel B, 10-yr; the manuscript's 99. **Rises**, because survivor "
       "emissions fall further than food savings do")
    d2("per patient-year, including survivorship, mod (kg)", None, 105.0244, 2,
       "**[CRN]**")
    say()

    # ------------------------------------------------------ attribution
    say("## Attribution -- the successive differences")
    say()
    say("This is what Phase 3 exists for. Each step isolates one change:")
    say()
    say("| step | change isolated |")
    say("|---|---|")
    say("| OLD -> A | the BMI construction: piecewise-linear CDF with a "
        "Kitahara top band, replacing the KDE mixture. **Also carries the "
        "re-seed and, for moderate only, the CRN change.** |")
    say("| A -> B | birth-cohort-matched attained height |")
    say("| B -> C | age-related height loss (Sorkin) |")
    say("| C -> D | continuous hazard above BMI 40 (section 2.15) |")
    say()

    ATTR = [
        ("annual food savings, yr 1 (Mt) [max]",
         old_ref("total_annual_food_savings_mt", "max_uptake"),
         [M[r]["annual food savings [max_uptake]"] for r in RUNS], 4),
        ("annual food savings, yr 1 (Mt) [mod]",
         old_ref("total_annual_food_savings_mt", "mod_uptake"),
         [M[r]["annual food savings [mod_uptake]"] for r in RUNS], 4),
        ("CUM-10Y food:survivor [max]",
         old_ref("cum_food_to_survivor_ratio_10yr", "max_uptake"),
         [M[r]["cum 10-yr food:survivor [max_uptake]"] for r in RUNS], 4),
        ("CUM-10Y food:survivor [mod]",
         old_ref("cum_food_to_survivor_ratio_10yr", "mod_uptake"),
         [M[r]["cum 10-yr food:survivor [mod_uptake]"] for r in RUNS], 4),
        ("Y10-FLOW food:survivor [max]",
         old_ref("annual_food_to_survivor_ratio_y10", "max_uptake"),
         [M[r]["yr-10 annual food:survivor [max_uptake]"] for r in RUNS], 4),
        ("Y10-FLOW food:survivor [mod]",
         old_ref("annual_food_to_survivor_ratio_y10", "mod_uptake"),
         [M[r]["yr-10 annual food:survivor [mod_uptake]"] for r in RUNS], 4),
        ("mean EER reduction (kcal/day) [max]", None,
         [206.2336, 203.6991, 200.3491, 200.3491], 4),
        ("cumulative 10-yr person-years [max]", 16_830_000.0,
         [14_885_784.0, 14_885_784.0, 14_885_784.0, 14_924_338.0], 0),
    ]
    say("| quantity | OLD -> A (BMI) | A -> B (cohort ht) | B -> C (ht loss) "
        "| C -> D (2.15) | total |")
    say("|---|--:|--:|--:|--:|--:|")
    for label, old, v, nd in ATTR:
        steps = []
        steps.append(f"{v[0]-old:+,.{nd}f}" if old is not None else "--")
        steps.append(f"{v[1]-v[0]:+,.{nd}f}")
        steps.append(f"{v[2]-v[1]:+,.{nd}f}")
        steps.append(f"{v[3]-v[2]:+,.{nd}f}")
        tot = f"{v[3]-old:+,.{nd}f}" if old is not None else "--"
        say(f"| {label} | " + " | ".join(steps) + f" | {tot} |")
    say()
    say("**The BMI construction is the dominant change in every row.** On "
        "food savings it moves -2.96 Mt of a -3.17 Mt total; the two height "
        "corrections contribute -0.17 and -0.04, and section 2.15 is "
        "negligible on the food side because it only reaches it through "
        "`pi(t)`.")
    say()
    say("A caveat on the first column. OLD -> A is not a clean single change: "
        "it also carries the move to per-stratum seeding, which reshuffles "
        "every draw, and for the moderate-uptake rows the CRN change as well. "
        "Sections 2.8 and 2.9 make the A/B/C/D steps separable from each "
        "other, not the first step from the old artefact.")
    say()

    say("## Rows needing prose, not renumbering")
    say()
    say("**The 18.6% all-cause mortality reduction.** The manuscript states "
        "18.6% (HR ~ 0.81) and builds a rhetorical point on SELECT having "
        "found the same figure. The regenerated population gives **17.10%** on "
        "the OLD ladder, before section 2.15 touches anything, and **17.21%** "
        "with it. The coincidence with SELECT no longer holds, so the passage "
        "needs rewriting rather than the number swapping.")
    say()
    say("**The Y10-FLOW ratio sits on a knife edge.** For `max_uptake` it is "
        "1.000531 under C and **0.998853 under D** -- it crosses back below "
        "one. Both are within 0.15% of unity, so which side of 1 it lands on "
        "is decided by a change whose aggregate effect is about 0.2%. It "
        "should not be reported as 'above one' or 'below one' without that "
        "context. The CUM-10Y ratio, which is what the manuscript actually "
        "quotes, is nowhere near one (1.94).")
    say()
    say("**`N < 1` moves in four of six sensitivity rows.** P10 9 -> 7 in both "
        "scenarios and combined-conservative 21 -> 20 in both; P90 stays at 0. "
        "The minimum-country identity also changes in three places.")
    say()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
