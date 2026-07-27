"""Reproduction check: recompute the model's headline numbers and compare them
against the reference snapshots in this directory.

Usage
-----
    python -m reference.metrics          # from the repository root

Reports 47 values -- baseline food emissions, annual food savings, cumulative
and year-10 food:survivor ratios, minimum-country ratios and ISO codes, and the
P10 / P90 / combined-conservative sensitivity suite -- for both uptake levels,
against reference_headline_numbers.csv and reference_sensitivity_suite.csv.

The reference files are a snapshot of what the current code produces, not a
claim about final results. A deliberate methodological change is expected to
fail this check; see the README section "Reproduction check" for what to do then.

Metric definitions are transcribed from the verification scripts that produced
the reference numbers, so what is measured here is computed identically to them.
Those scripts, and the frozen pre-consolidation comparison that used them, are
on the seth_bug_fixes audit branch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCENARIOS = ["max_uptake", "mod_uptake"]


def baseline_food_emissions_mt(result_df: pd.DataFrame) -> float:
    one = result_df[result_df["scenario"] == "max_uptake"].copy()
    one = one.drop_duplicates(subset=["ISO", "final_food_group"])
    return (one["initial_eql_quantity"] * one["carbon_intensity_t"]).sum() / 1e6


def total_food_savings_mt(food_savings: pd.DataFrame) -> dict:
    out = {}
    for sc in SCENARIOS:
        sub = food_savings[
            (food_savings["scenario"] == sc)
            & (food_savings["annual_food_savings_t"] > 0)
        ]
        out[sc] = sub["annual_food_savings_t"].sum() / 1e6
    return out


def ratios_for_scenario(be_df: pd.DataFrame, scenario: str) -> dict:
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
    }


def min_and_tipping(be, sc):
    v = be[
        (be["scenario"] == sc)
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
        & np.isfinite(be["ratio_food_to_mort"])
    ]
    i = v["ratio_food_to_mort"].idxmin()
    r = v.loc[i]
    return (float(r["ratio_food_to_mort"]), r["ISO"], r["Country"],
            int((v["ratio_food_to_mort"] < 1).sum()), len(v))


# ── canonical committed targets ─────────────────────────────────────────────

# Reference snapshots, tracked in the repository so the check runs from a clean
# clone. These are a snapshot of what the current code produces, not a claim
# about final results -- see the README on the reproduction check.
HEADLINE_CSV = ROOT / "reference" / "reference_headline_numbers.csv"
SUITE_CSV = ROOT / "reference" / "reference_sensitivity_suite.csv"

# committed column name -> metric label
HEAD_COLS = {
    "total_annual_food_savings_mt": "annual food savings",
    "cum_food_to_survivor_ratio_10yr": "cum 10-yr food:survivor",
    "annual_food_to_survivor_ratio_y10": "yr-10 annual food:survivor",
    "min_country_ratio_10yr": "min-country ratio 10-yr",
}


def canonical_targets() -> list[tuple[str, float]]:
    """The recorded reproduction target, at full committed precision."""
    head = pd.read_csv(HEADLINE_CSV)
    head = head[head["run"] == "corrected_fix3"].set_index("scenario")
    out = [("baseline food emissions (Mt)",
            float(head["baseline_food_emissions_mt"].iloc[0]))]
    for sc in SCENARIOS:
        for col, lab in HEAD_COLS.items():
            out.append((f"{lab} [{sc}]", float(head.loc[sc, col])))
        out.append((f"min-country iso [{sc}]", head.loc[sc, "min_country_iso"]))
    suite = pd.read_csv(SUITE_CSV)
    for _, e in suite.iterrows():
        k = f"{e['scenario_spec']} [{e['uptake']}]"
        out += [
            (f"{k} cum10", float(e["cum_ratio_10yr"])),
            (f"{k} y10", float(e["annual_ratio_y10"])),
            (f"{k} min", float(e["min_country_ratio"])),
            (f"{k} min-iso", e["min_country_iso"]),
            (f"{k} tipping", int(e["n_tipping_countries"])),
            (f"{k} n_complete", int(e["n_complete_countries"])),
        ]
    return out


def measure(snap: dict, mort) -> dict:
    """Compute every canonical metric from a snapshot dict of pipeline outputs."""
    from data_visualization.breakeven_analysis import compute_breakeven

    got: dict = {}
    rdf = snap["main"]["result_df"]
    fs = snap["main"]["food_savings"]
    be = compute_breakeven(fs, mort, include_drug=True)
    got["baseline food emissions (Mt)"] = baseline_food_emissions_mt(rdf)
    sav = total_food_savings_mt(fs)
    for sc in SCENARIOS:
        rat = ratios_for_scenario(be, sc)
        mr, mi, _mc, _nt, _nv = min_and_tipping(be, sc)
        got[f"annual food savings [{sc}]"] = sav[sc]
        got[f"cum 10-yr food:survivor [{sc}]"] = rat["cum_ratio_10yr"]
        got[f"yr-10 annual food:survivor [{sc}]"] = rat["annual_ratio_y10"]
        got[f"min-country ratio 10-yr [{sc}]"] = mr
        got[f"min-country iso [{sc}]"] = mi

    spec_map = {"P10": "uniform_p10", "P90": "uniform_p90",
                "combined_conservative": "combined_conservative"}
    for spec, label in spec_map.items():
        be_s = compute_breakeven(snap[label]["food_savings"], mort, include_drug=True)
        for sc in SCENARIOS:
            k = f"{spec} [{sc}]"
            rat = ratios_for_scenario(be_s, sc)
            mr, mi, _mc, ntip, nval = min_and_tipping(be_s, sc)
            got[f"{k} cum10"] = rat["cum_ratio_10yr"]
            got[f"{k} y10"] = rat["annual_ratio_y10"]
            got[f"{k} min"] = mr
            got[f"{k} min-iso"] = mi
            got[f"{k} tipping"] = ntip
            got[f"{k} n_complete"] = nval
    return got


# Relative tolerance. Comparing against CSV-stored references, across pandas and
# numpy versions, has an irreducible floor near the 16th significant figure: the
# stored decimal need not reload to the identical double, and aggregate sums are
# sensitive to library-level arithmetic differences. Any genuine change to the
# model moves these numbers by many orders of magnitude more than this, so the
# tolerance costs no sensitivity. Exact strings (ISO codes) and integer counts
# (tipping countries) are compared exactly.
REL_TOL = 1e-12


def report(got: dict, title: str) -> bool:
    print("=" * 100)
    print(title)
    print("=" * 100)
    print(f"{'metric':<46}{'reference':>19}{'recomputed':>19}{'|diff|':>12}{'rel':>10}")
    print("-" * 100)
    worst_abs = worst_rel = 0.0
    ok = True
    for name, exp in canonical_targets():
        g = got[name]
        if isinstance(exp, str):
            same = (g == exp)
            ok &= same
            print(f"{name:<46}{exp:>19}{str(g):>19}"
                  f"{('OK' if same else 'MISMATCH'):>22}")
        else:
            e, v = float(exp), float(g)
            d = abs(e - v)
            rel = d / abs(e) if e != 0.0 else d
            worst_abs = max(worst_abs, d)
            worst_rel = max(worst_rel, rel)
            within = rel <= REL_TOL
            ok &= within
            flag = "" if within else "  <-- MOVED"
            print(f"{name:<46}{e:>19.10f}{v:>19.10f}{d:>12.2e}{rel:>10.1e}{flag}")
    print("-" * 100)
    print(f"worst |diff|: {worst_abs:.3e}      worst relative: {worst_rel:.3e}"
          f"      tolerance: {REL_TOL:.0e}")
    print("RESULT:", "PASS — reproduces the reference snapshot" if ok
          else "FAIL — something moved; see the README, 'Reproduction check'")
    return ok


# ── driver ────────────────────────────────────────────────────────────────────
#
# The 47 reference values cover four configurations: the no-diet baseline on mean
# carbon intensity, the P10 and P90 carbon-intensity bounds, and the
# combined-conservative case. The diet-scenario variants have no reference values
# here; they are exercised by diet_sensitivity/analysis.py and
# sensitivity_overview.py.


def run_configurations() -> dict:
    """Run the pipeline for every configuration the reference values cover."""
    from data_visualization.pipeline import compute_food_savings
    from diet_sensitivity.combined_analysis import build_meat_p10_ci_file

    meat_p10 = build_meat_p10_ci_file()
    configs = [
        ("main",                  None,               "carbon_intensity.csv"),
        ("uniform_p10",           "baseline_uniform", "carbon_intensity_p10.csv"),
        ("uniform_p90",           "baseline_uniform", "carbon_intensity_p90.csv"),
        ("combined_conservative", "cereal_sweets_up", str(meat_p10)),
    ]
    snap = {}
    for label, diet, ci in configs:
        print(f"  [{label}] diet={diet}, ci={Path(ci).name}", flush=True)
        fs, rdf = compute_food_savings(diet_scenario=diet, ci_file=ci)
        snap[label] = {"food_savings": fs, "result_df": rdf}
    return snap


def main() -> int:
    from data_visualization.pipeline import load_mortality_emissions

    print("Running the pipeline for the reference configurations "
          "(about two minutes)...")
    snap = run_configurations()
    got = measure(snap, load_mortality_emissions())
    print()
    ok = report(got, "REPRODUCTION CHECK — recomputed vs reference snapshot")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
