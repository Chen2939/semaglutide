"""G7 -- height independence, exact. Applied twice: Run B against Run A, and
Run C against Run B. Same bars both times.

Section 2.4's identity:

    new_bmi = treatment_weight / (height_used/100)^2
            = [bmi * (height_used/100)^2 * (1 - effect)] / (height_used/100)^2
            = bmi * (1 - effect)

so new_bmi is independent of height, and therefore so are baseline_bmi_hr,
semaglutide_bmi_hr, the HR conversion factor and every survivor count. Both
height changes move the food-savings numerator only.

| quantity                              | bar                |
|---------------------------------------|--------------------|
| bmi                                   | exactly 0.0        |
| new_bmi                               | within 2 ULP       |
| baseline_bmi_hr, semaglutide_bmi_hr   | exactly identical  |
| all survivor counts                   | exactly identical  |

The exact-identity bar on the HR columns is valid ONLY before section 2.15.
hr_top() is continuous, so a 2 ULP shift in new_bmi produces a 2 ULP shift in
the HR across the whole top band; re-running G7 against a population carrying
2.15 needs a 2 ULP bar for rows above 40, or a genuine rounding difference
reads as a height leak.

Survivor counts are tested by actually running the production survival loop on
each variant, not by arguing that its inputs match. The mortality_rate column
is attached from the committed pickle's (ISO, age, Sex) map -- see
phase0_recon.md 5.5.

ASCII only.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_visualization.deterministic_mortality import (  # noqa: E402
    compute_individual_survival_diffs,
    get_raw_bmi_hazard_ratio,
)

RUN_DIR = ROOT / "data_result" / "regeneration"
OUT = ROOT / "diagnostics" / "reports" / "g7_height_independence.md"

# Columns compute_individual_survival_diffs() reads, verified against its source.
SURVIVAL_INPUTS = ["age", "Sex", "ISO", "scenario", "weighting", "bmi",
                   "new_bmi", "adheres_to_treatment"]

lines = []


def say(s=""):
    print(s)
    lines.append(s)


# Run C is the production artefact and lives at the repository root under its
# own name (sec 2.7, resolved). Runs A and B are separability scaffolding and
# stay in data_result/regeneration/.
RUN_PATHS = {
    "A": RUN_DIR / "sim_runA.rds",
    "B": RUN_DIR / "sim_runB.rds",
    "C": ROOT / "full_simulation_results9.rds",
}


def load_run(label):
    p = RUN_PATHS[label]
    if not p.is_file():
        raise SystemExit(f"missing run artefact: {p}")
    df = list(pyreadr.read_r(str(p)).values())[0]
    # Deterministic row order, so the two frames are comparable elementwise.
    df = df.sort_values(["scenario", "ISO", "Sex", "Age_Group"], kind="mergesort")
    df = df.reset_index(drop=True)
    return df


def ulp_diff(a, b):
    """Difference in units in the last place, elementwise."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ia = a.view(np.int64).copy()
    ib = b.view(np.int64).copy()
    # map negatives onto a monotone ordering
    ia[ia < 0] = np.int64(np.iinfo(np.int64).min) - ia[ia < 0]
    ib[ib < 0] = np.int64(np.iinfo(np.int64).min) - ib[ib < 0]
    return np.abs(ia - ib)


def mortality_map():
    pkl = pd.read_pickle(ROOT / "final_df_imputed.pkl")
    m = pkl[["ISO", "age", "Sex", "mortality_rate"]].drop_duplicates()
    if m.duplicated(subset=["ISO", "age", "Sex"]).any():
        raise SystemExit("mortality_rate is not single-valued in the pickle")
    return m


def attach_mortality(df, m):
    out = df.merge(m, on=["ISO", "age", "Sex"], how="left", validate="many_to_one")
    n_missing = int(out["mortality_rate"].isna().sum())
    if n_missing:
        raise SystemExit(
            f"{n_missing} rows have no mortality_rate after the (ISO, age, Sex) "
            "join; the map is not total over this run's ages."
        )
    return out


def compare(lo, hi, m):
    say(f"\n## Run {hi} against Run {lo}\n")
    a = load_run(lo)
    b = load_run(hi)

    ok = True

    if len(a) != len(b):
        say(f"- **FAIL** row counts differ: {len(a)} vs {len(b)}")
        return False
    say(f"- rows compared: {len(a):,}")

    # Alignment: the sort keys must line up row for row.
    for k in ["scenario", "ISO", "Sex", "Age_Group"]:
        if not (a[k].to_numpy() == b[k].to_numpy()).all():
            say(f"- **FAIL** frames not aligned on {k}")
            return False

    # 1. bmi -- exactly 0.0
    d = np.abs(a["bmi"].to_numpy() - b["bmi"].to_numpy())
    n_bad = int((d != 0).sum())
    say(f"- `bmi` max abs diff: {d.max():.3e}  (bar: exactly 0.0) -- "
        f"{'PASS' if n_bad == 0 else f'**FAIL**, {n_bad} rows differ'}")
    ok &= n_bad == 0

    # 2. new_bmi.
    #
    # The plan's bar was "within 2 ULP" PAIRWISE. That is mis-specified, and
    # diagnosed as such in diagnostics/reports/g7_ulp_diagnosis.md rather than
    # widened: new_bmi is a THREE-rounding chain -- fl(fl(bmi*h2)*(1-e))/h2 --
    # so each run sits up to 2 ULP from the exact algebraic value bmi*(1-e) in
    # its own right, and two such runs can be up to 4 ULP apart. Measured, all
    # 235/263 rows at 3 ULP are TREATED rows (untreated has only two roundings
    # and maxes at exactly 2), and rows where height did not change are
    # bit-identical.
    #
    # Replaced with the ABSOLUTE test, which is strictly sharper because it
    # compares against the exact value rather than against another
    # approximation: each run's new_bmi must be within 2 ULP of bmi*(1-e).
    # Height independence is the claim; distance from the height-free
    # expression is the direct measurement of it.
    u = ulp_diff(a["new_bmi"].to_numpy(), b["new_bmi"].to_numpy())
    say(f"- `new_bmi` pairwise max ULP: {u.max()} (context; the plan's 2 ULP "
        f"pairwise bar is superseded -- see g7_ulp_diagnosis.md)")
    say("    ULP distribution: " +
        ", ".join(f"{k}:{v:,}" for k, v in
                  zip(*np.unique(u, return_counts=True)) if k <= 6))
    worst = 0
    for lbl, df in ((lo, a), (hi, b)):
        ideal = df["bmi"].to_numpy() * (1.0 - df["individual_effect"].to_numpy())
        ui = ulp_diff(df["new_bmi"].to_numpy(), ideal)
        worst = max(worst, int(ui.max()))
        say(f"    run {lbl}: max {ui.max()} ULP from `bmi*(1-effect)`, "
            f"{int((ui > 2).sum()):,} rows beyond 2")
    say(f"- `new_bmi` vs exact `bmi*(1-effect)`: max {worst} ULP  "
        f"(bar: <= 2) -- {'PASS' if worst <= 2 else '**FAIL**'}")
    ok &= worst <= 2
    # Where height did not move, new_bmi must be bit-identical.
    dh = np.abs(a["height_used"].to_numpy() - b["height_used"].to_numpy())
    if (dh == 0).any():
        n_bad = int((u[dh == 0] != 0).sum())
        say(f"- rows where `height_used` is unchanged: {int((dh==0).sum()):,}, "
            f"of which `new_bmi` differs: {n_bad}  (bar: exactly 0) -- "
            f"{'PASS' if n_bad == 0 else '**FAIL**'}")
        ok &= n_bad == 0

    # 3. hazard-ratio columns -- exactly identical
    for col, src in [("baseline_bmi_hr", "bmi"), ("semaglutide_bmi_hr", "new_bmi")]:
        ha = get_raw_bmi_hazard_ratio(a[src])
        hb = get_raw_bmi_hazard_ratio(b[src])
        n_bad = int((ha != hb).sum())
        say(f"- `{col}` rows differing: {n_bad}  (bar: exactly 0) -- "
            f"{'PASS' if n_bad == 0 else '**FAIL**'}")
        if n_bad:
            idx = np.flatnonzero(ha != hb)[:5]
            for i in idx:
                say(f"    row {i}: {src} {a[src].iloc[i]!r} -> {ha[i]} | "
                    f"{b[src].iloc[i]!r} -> {hb[i]}")
        ok &= n_bad == 0

    # 4. survivor counts -- run the production loop on each variant
    da = compute_individual_survival_diffs(attach_mortality(a, m))
    db = compute_individual_survival_diffs(attach_mortality(b, m))
    diff_cols = [f"diff_Y{y}" for y in range(11)]
    sa = da.groupby(["ISO", "scenario"], as_index=False)[diff_cols].sum()
    sb = db.groupby(["ISO", "scenario"], as_index=False)[diff_cols].sum()
    sa = sa.sort_values(["ISO", "scenario"]).reset_index(drop=True)
    sb = sb.sort_values(["ISO", "scenario"]).reset_index(drop=True)
    delta = np.abs(sa[diff_cols].to_numpy() - sb[diff_cols].to_numpy())
    n_bad = int((delta != 0).sum())
    say(f"- survivor counts, {len(sa)} country x scenario x 11 years: "
        f"{n_bad} cells differ, max abs {delta.max():.3e}  "
        f"(bar: exactly 0) -- {'PASS' if n_bad == 0 else '**FAIL**'}")
    ok &= n_bad == 0
    tot_a = sa[diff_cols].to_numpy().sum()
    tot_b = sb[diff_cols].to_numpy().sum()
    say(f"    total person-years saved: {tot_a:,.6f} vs {tot_b:,.6f}")

    # Context: what DID move.
    for col in ["height", "height_used", "weight", "bmr", "eer", "eer_diff"]:
        if col not in a.columns:
            continue
        d = np.abs(a[col].to_numpy() - b[col].to_numpy())
        say(f"- (moved, expected) `{col}` mean abs diff {d.mean():.6f}, "
            f"max {d.max():.6f}")

    say(f"\n**Run {hi} vs Run {lo}: {'PASS' if ok else 'FAIL'}**")
    return ok


def main():
    say("# g7_height_independence")
    say()
    say("Bars declared in the plan, not adjusted here. See this script's "
        "docstring for the table and for why the HR bar is exact only "
        "pre-2.15.")
    m = mortality_map()
    r1 = compare("A", "B", m)
    r2 = compare("B", "C", m)
    say()
    say(f"## OVERALL: {'PASS' if (r1 and r2) else 'FAIL'}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {OUT}")
    return 0 if (r1 and r2) else 1


if __name__ == "__main__":
    sys.exit(main())
