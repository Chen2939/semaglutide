"""STEP 1 CONSOLIDATION PROOF — ARCHIVED, NOT RUNNABLE ON THIS BRANCH.

Runs the single merged compute_food_savings() across every diet x CI
configuration the published analysis uses, and diffs the FULL outputs
(food_savings + result_df, every column, every row) against ref_snapshot.pkl —
the outputs of the two ORIGINAL functions captured before the merge.

Requirement: max |diff| == 0.0 exactly, on every numeric column of both frames,
for every configuration. Column sets, row counts and dtypes must match too.

Result when it was run: PASS. All seven configurations reproduced at exactly 0.0
across 112 rows of food_savings and 1008 rows of result_df, and all 47 canonical
metrics were unchanged.

WHY IT IS HERE AND WHY IT WILL NOT RUN
--------------------------------------
This is an audit artifact, kept for the record rather than for re-execution.

  * It needs the MERGED compute_food_savings(), which exists only on the
    'cleanup' branch. This branch still has the two original functions that the
    merge replaced, so there is nothing here for it to test.
  * It imports a 'metrics' module, which lives on 'cleanup' as
    reference/metrics.py.
  * ref_snapshot.pkl alongside it CANNOT be regenerated: it captured the output
    of compute_food_savings_diet(), which was deleted when the two pipelines
    were consolidated. Reproducing it would need a pre-consolidation checkout.
    It is a pandas pickle and may not load under a different pandas version.

The ongoing reproduction check is a different thing and lives on 'cleanup':
reference/metrics.py, run with 'python -m reference.metrics'. It compares the
current code against committed reference values and is designed to keep working.
"""
from __future__ import annotations

import pickle
import sys

import numpy as np
import pandas as pd

from metrics import ROOT, SCRATCH, measure, report

sys.path.insert(0, str(ROOT))
from data_visualization.pipeline import compute_food_savings, load_mortality_emissions

MEAT_P10 = SCRATCH / "carbon_intensity_meat_p10_ref.csv"

# Same matrix as snapshot_ref.py, now all through the ONE function.
CONFIGS = [
    ("main",                  None,                "carbon_intensity.csv"),
    ("uniform_mean",          "baseline_uniform",  "carbon_intensity.csv"),
    ("uniform_p10",           "baseline_uniform",  "carbon_intensity_p10.csv"),
    ("uniform_p90",           "baseline_uniform",  "carbon_intensity_p90.csv"),
    ("fatty_mean",            "fatty_food_down",   "carbon_intensity.csv"),
    ("cereal_mean",           "cereal_sweets_up",  "carbon_intensity.csv"),
    ("combined_conservative", "cereal_sweets_up",  str(MEAT_P10)),
]

KEYS = {"food_savings": ["ISO", "scenario"],
        "result_df": ["ISO", "final_food_group", "scenario"]}


def diff_frames(ref: pd.DataFrame, new: pd.DataFrame, keys: list[str]):
    """Return (worst_abs_diff, list_of_problem_strings) comparing two frames."""
    problems = []
    if set(ref.columns) != set(new.columns):
        problems.append(
            f"column set differs: ref-only={sorted(set(ref.columns) - set(new.columns))} "
            f"new-only={sorted(set(new.columns) - set(ref.columns))}")
        return np.nan, problems
    if len(ref) != len(new):
        problems.append(f"row count differs: ref={len(ref)} new={len(new)}")
        return np.nan, problems

    r = ref.sort_values(keys).reset_index(drop=True)
    n = new[ref.columns].sort_values(keys).reset_index(drop=True)

    worst = 0.0
    for col in ref.columns:
        if pd.api.types.is_numeric_dtype(r[col]) and pd.api.types.is_numeric_dtype(n[col]):
            a, b = r[col].to_numpy(float), n[col].to_numpy(float)
            both_nan = np.isnan(a) & np.isnan(b)
            if not np.array_equal(np.isnan(a), np.isnan(b)):
                problems.append(f"{col}: NaN pattern differs "
                                f"(ref {np.isnan(a).sum()} vs new {np.isnan(b).sum()})")
            d = np.abs(a - b)
            d[both_nan] = 0.0
            m = float(np.nanmax(d)) if len(d) else 0.0
            worst = max(worst, m)
            if m != 0.0:
                problems.append(f"{col}: max |diff| = {m:.6e}")
        else:
            neq = (r[col].astype(object) != n[col].astype(object)) & ~(
                r[col].isna() & n[col].isna())
            if neq.any():
                problems.append(f"{col}: {int(neq.sum())} non-numeric value(s) differ")
    return worst, problems


def main():
    with open(SCRATCH / "ref_snapshot.pkl", "rb") as fh:
        ref = pickle.load(fh)

    new = {}
    for label, diet, ci in CONFIGS:
        print(f"[merged] {label:<22} diet_scenario={diet!s:<18} ci_file={ci.split(chr(92))[-1]}",
              flush=True)
        fs, rdf = compute_food_savings(diet_scenario=diet, ci_file=ci)
        new[label] = {"food_savings": fs, "result_df": rdf}

    print("\n" + "=" * 100)
    print("STEP 1 PROOF — merged compute_food_savings()  vs  original two functions")
    print("  (full frames, every column, every row; requirement is EXACTLY 0.0)")
    print("=" * 100)
    print(f"{'configuration':<24}{'frame':<14}{'rows':>7}{'cols':>6}{'max |diff|':>15}  status")
    print("-" * 100)

    all_ok = True
    for label, diet, ci in CONFIGS:
        for frame in ("food_savings", "result_df"):
            r, n = ref[label][frame], new[label][frame]
            worst, problems = diff_frames(r, n, KEYS[frame])
            ok = (worst == 0.0) and not problems
            all_ok &= ok
            shown = "0.0" if worst == 0.0 else f"{worst:.6e}"
            print(f"{label:<24}{frame:<14}{len(n):>7}{len(n.columns):>6}{shown:>15}  "
                  f"{'OK' if ok else 'MISMATCH'}")
            for p in problems:
                print(f"{'':>24}  ! {p}")
    print("-" * 100)
    print("FULL-FRAME RESULT:", "PASS — merged function is bit-identical to both originals"
          if all_ok else "FAIL — merged function diverges")

    # Headline + sensitivity metrics recomputed from the merged pipeline.
    print()
    got = measure(new, load_mortality_emissions())
    metrics_ok = report(
        got, "STEP 1 — canonical metrics recomputed from the MERGED pipeline")

    # And the same metrics from the reference, to show any residual gap is the
    # committed-CSV precision limit, not the merge.
    ref_got = measure(ref, load_mortality_emissions())
    print("\nmerged vs reference, metric by metric (must be exactly 0.0):")
    worst = 0.0
    for k in got:
        if isinstance(got[k], str):
            assert got[k] == ref_got[k], f"{k}: {got[k]} != {ref_got[k]}"
            continue
        d = abs(float(got[k]) - float(ref_got[k]))
        worst = max(worst, d)
        if d:
            print(f"  {k}: {d:.3e}")
    print(f"  worst |merged - reference| across all {len(got)} metrics: {worst:.3e}")

    print("\n" + "=" * 100)
    print("VERDICT:", "PASS" if (all_ok and worst == 0.0) else "FAIL")
    print("  full frames identical      :", all_ok)
    print("  metrics identical to ref   :", worst == 0.0)
    print("  metrics vs committed CSVs  :", metrics_ok,
          "(<=1 ULP text-precision gap expected; see note)")
    print("=" * 100)
    sys.exit(0 if (all_ok and worst == 0.0) else 1)


if __name__ == "__main__":
    main()
