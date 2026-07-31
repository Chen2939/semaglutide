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

Status: the references are stale on this branch
-----------------------------------------------
`python -m reference.metrics` currently fails, and that is expected. Two
committed changes moved the numbers after these snapshots were taken:

    6e826a4  Fix aggregate double-count in load_kcal_shares' calorie-share
             weights
    be44eb4  Weight oilcrops composite by P&N food-and-waste supply volumes

The snapshots have deliberately not been regenerated. A survivor-emissions
change is planned, and refreshing now would mean doing it again straight
afterwards -- two reference commits describing the same intermediate state. So
the regeneration is being held and will be done once, after that change lands.

Until then, read a failure here as the known staleness above rather than a new
regression. See the README section "Reproduction check" for the policy and the
reasoning.
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


# Which row of the headline snapshot is the live reproduction target. Earlier rows
# are kept for provenance; this names the one the check compares against, so
# refreshing the snapshot is a data change plus a one-line label change rather
# than an edit scattered through the file.
ACTIVE_RUN = "survival_weighted"


def canonical_targets() -> list[tuple[str, float]]:
    """The recorded reproduction target, at full committed precision."""
    head = pd.read_csv(HEADLINE_CSV, float_precision="round_trip")
    head = head[head["run"] == ACTIVE_RUN].set_index("scenario")
    if head.empty:
        raise SystemExit(
            f"{HEADLINE_CSV.name} has no rows for run={ACTIVE_RUN!r}. "
            "Regenerate with: python -m reference.metrics --write"
        )
    out = [("baseline food emissions (Mt)",
            float(head["baseline_food_emissions_mt"].iloc[0]))]
    for sc in SCENARIOS:
        for col, lab in HEAD_COLS.items():
            out.append((f"{lab} [{sc}]", float(head.loc[sc, col])))
        out.append((f"min-country iso [{sc}]", head.loc[sc, "min_country_iso"]))
    suite = pd.read_csv(SUITE_CSV, float_precision="round_trip")
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


def measure(snap: dict) -> dict:
    """Compute every canonical metric from a snapshot dict of pipeline outputs.

    Each configuration is scored against the survivor frame for ITS OWN
    carbon-intensity scenario, taken from the ``ci_scenario`` recorded on the
    snapshot. This used to take one mean-basis ``mort`` frame and reuse it for all
    four, which stopped being right when the survivor factor became CI-aware: its
    P&N food add-back is priced with the same intensities as the food side, so
    pairing P10 food savings with a mean survivor frame compares two bases.
    """
    from data_visualization.breakeven_analysis import compute_breakeven
    from data_visualization.pipeline import load_mortality_emissions

    mort_cache: dict[str, object] = {}

    def mort_for(label: str):
        ci = snap[label]["ci_scenario"]
        if ci not in mort_cache:
            mort_cache[ci] = load_mortality_emissions(ci)
        return mort_cache[ci]

    got: dict = {}
    rdf = snap["main"]["result_df"]
    fs = snap["main"]["food_savings"]
    be = compute_breakeven(fs, mort_for("main"), include_drug=True)
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
        be_s = compute_breakeven(
            snap[label]["food_savings"], mort_for(label), include_drug=True
        )
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

    # combined_conservative is cereal_sweets_up x ALL-FOOD P10, scored against the
    # p10 survivor basis -- the production definition, which
    # combined_analysis.py, sensitivity_overview.py and sensitivity_suite.py all
    # share and combined_analysis.assert_combined_conservative() holds in step.
    # This copy used to name the derived meat-only carbon-intensity file, a
    # definition production retired; that assertion does not reach into
    # reference/, so it drifted silently. Reconciled here.
    #
    # ci_scenario pairs each configuration with its own survivor frame; see
    # measure().
    configs = [
        ("main",                  None,               "carbon_intensity.csv",     "mean"),
        ("uniform_p10",           "baseline_uniform", "carbon_intensity_p10.csv", "p10"),
        ("uniform_p90",           "baseline_uniform", "carbon_intensity_p90.csv", "p90"),
        ("combined_conservative", "cereal_sweets_up", "carbon_intensity_p10.csv", "p10"),
    ]
    snap = {}
    for label, diet, ci, ci_scenario in configs:
        print(f"  [{label}] diet={diet}, ci={Path(ci).name}, "
              f"survivor={ci_scenario}", flush=True)
        fs, rdf = compute_food_savings(diet_scenario=diet, ci_file=ci)
        snap[label] = {
            "food_savings": fs, "result_df": rdf, "ci_scenario": ci_scenario,
        }
    return snap


def write_references(snap: dict) -> None:
    """Regenerate both reference snapshots from a fresh pipeline run.

    Appends a new ``run`` row named ACTIVE_RUN to the headline snapshot, keeping
    earlier rows for provenance, and replaces the sensitivity suite outright (it
    has no run column). Values are written at full repr precision so the check can
    hold a 1e-12 tolerance rather than a rounding-limited one.

    Existed as a manual step before: there was no writer, so refreshing the
    snapshot meant hand-editing the CSVs, which is how a stale configuration
    survived in here unnoticed. Regenerating is now one command.
    """
    from data_visualization.breakeven_analysis import compute_breakeven
    from data_visualization.pipeline import load_mortality_emissions

    rdf = snap["main"]["result_df"]
    fs = snap["main"]["food_savings"]
    be = compute_breakeven(
        fs, load_mortality_emissions(snap["main"]["ci_scenario"]), include_drug=True
    )
    base_mt = baseline_food_emissions_mt(rdf)
    sav = total_food_savings_mt(fs)

    head_rows = []
    for sc in SCENARIOS:
        rat = ratios_for_scenario(be, sc)
        mr, mi, mc, _ntip, nval = min_and_tipping(be, sc)
        head_rows.append({
            "run": ACTIVE_RUN,
            "scenario": sc,
            "baseline_food_emissions_mt": base_mt,
            "total_annual_food_savings_mt": sav[sc],
            "cum_food_to_survivor_ratio_10yr": rat["cum_ratio_10yr"],
            "annual_food_to_survivor_ratio_y10": rat["annual_ratio_y10"],
            "min_country_ratio_10yr": mr,
            "min_country_iso": mi,
            "min_country_name": mc,
            "n_complete_countries": nval,
        })
    existing = pd.read_csv(HEADLINE_CSV, float_precision="round_trip")
    existing = existing[existing["run"] != ACTIVE_RUN]
    pd.concat([existing, pd.DataFrame(head_rows)], ignore_index=True).to_csv(
        HEADLINE_CSV, index=False
    )
    print(f"Wrote {HEADLINE_CSV.name} (run={ACTIVE_RUN})")

    spec_map = {"P10": "uniform_p10", "P90": "uniform_p90",
                "combined_conservative": "combined_conservative"}
    suite_rows = []
    for spec, label in spec_map.items():
        be_s = compute_breakeven(
            snap[label]["food_savings"],
            load_mortality_emissions(snap[label]["ci_scenario"]),
            include_drug=True,
        )
        for sc in SCENARIOS:
            rat = ratios_for_scenario(be_s, sc)
            mr, mi, mc, ntip, nval = min_and_tipping(be_s, sc)
            suite_rows.append({
                "scenario_spec": spec,
                "uptake": sc,
                "cum_ratio_10yr": rat["cum_ratio_10yr"],
                "annual_ratio_y10": rat["annual_ratio_y10"],
                "min_country_ratio": mr,
                "min_country_iso": mi,
                "min_country_name": mc,
                "n_tipping_countries": ntip,
                "n_complete_countries": nval,
            })
    pd.DataFrame(suite_rows).to_csv(SUITE_CSV, index=False)
    print(f"Wrote {SUITE_CSV.name}")


def main(write: bool = False) -> int:
    print("Running the pipeline for the reference configurations "
          "(about two minutes)...")
    snap = run_configurations()
    if write:
        write_references(snap)
        print()
    got = measure(snap)
    print()
    ok = report(got, "REPRODUCTION CHECK — recomputed vs reference snapshot")
    return 0 if ok else 1


if __name__ == "__main__":
    # Redirected stdout on Windows falls back to cp1252, which cannot encode the
    # non-ASCII this script prints. Set UTF-8 on the streams here rather than at
    # module level, so importing this module never mutates global stream state.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    sys.exit(main(write="--write" in sys.argv[1:]))
