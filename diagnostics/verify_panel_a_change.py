"""
Verify the Panel A no-mortality change against diagnostics/predicted_movement_panel_a.txt.

Order matters. The Panel B re-solve (S2) runs in the SAME interpreter that has
already executed an unweighted Panel A call, because the failure mode worth
testing is cross-contamination through shared state, not whether two separate
processes agree.

Writes: data_result/global_emissions_waterfall_1yr.csv and its PNG (via the
module's own main). Does NOT write anything on the Panel B side -- it calls
compute_waterfall_components() and compares in memory.
"""

import hashlib
import io
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"C:\Users\sethw\repos")
WATCH = [ROOT / "data_result", ROOT / "figures"]

COMMITTED_1YR = {
    "naive_reductions": 112.61729928417304,
    "rebound_effect": 58.67516486604079,
    "actual_food_savings": 53.942134418132255,
    "manufacturing": 1.3326121641356403,
    "net_savings": 52.60952225399661,
}
PREDICTED_ESTIMATE = 54.226594
MANUFACTURING_EXACT = 1.3326121641356403

failures = []


def gate(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def snapshot():
    out = {}
    for d in WATCH:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                # as_posix(): relative_to yields backslashes on Windows, which
                # never match the forward-slash expected set below.
                key = p.relative_to(ROOT).as_posix()
                out[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main():
    print("=" * 78)
    print("PANEL A VERIFICATION")
    print("=" * 78)

    before = snapshot()
    committed_10yr = pd.read_csv(
        ROOT / "data_result" / "global_emissions_waterfall.csv",
        float_precision="round_trip",
    )

    # ---- Panel A, unweighted -------------------------------------------
    print("\n[1/3] Panel A: generate_waterfall_1yr_figure.main() "
          "(survival_weighted=False)")
    from data_visualization import generate_waterfall_1yr_figure as p1

    buf = io.StringIO()
    real, sys.stdout = sys.stdout, buf
    try:
        p1.main()
    finally:
        sys.stdout = real
    for line in buf.getvalue().splitlines():
        if line.strip():
            print("      | " + line)

    new1 = pd.read_csv(
        ROOT / "data_result" / "global_emissions_waterfall_1yr.csv",
        float_precision="round_trip",
    )
    v = dict(zip(new1["step"], new1["value_Mt"]))

    print("\n  step                    committed        new         delta      %")
    for k, old in COMMITTED_1YR.items():
        n = v[k]
        print(f"  {k:22s} {old:12.6f} {n:12.6f} {n-old:+10.6f} "
              f"{(n-old)/old*100:+7.3f}")

    # ---- Panel B, same interpreter (S2) --------------------------------
    print("\n[2/3] Panel B (S2): compute_waterfall_components() in THIS "
          "interpreter, after the unweighted call above")
    from data_visualization import generate_waterfall_figure as p10

    buf = io.StringIO()
    real, sys.stdout = sys.stdout, buf
    try:
        got10 = p10.compute_waterfall_components()
    finally:
        sys.stdout = real

    m = committed_10yr.merge(got10, on="step", suffixes=("_old", "_new"))
    ok_rows = len(m) == len(committed_10yr) == len(got10)
    worst = (m["value_Mt_new"] - m["value_Mt_old"]).abs().max()
    print(f"      rows matched: {len(m)}   worst abs delta: {worst!r}")
    for _, r in m.iterrows():
        d = r["value_Mt_new"] - r["value_Mt_old"]
        if d != 0.0:
            print(f"      MOVED  {r['step']}: {r['value_Mt_old']!r} -> "
                  f"{r['value_Mt_new']!r}  ({d:+.9e})")

    after = snapshot()

    # ---- Gates ---------------------------------------------------------
    print("\n[3/3] Gates")
    gate("H1  manufacturing exactly unchanged",
         v["manufacturing"] == MANUFACTURING_EXACT,
         f"{v['manufacturing']!r}")
    gate("H2  n_countries == 53",
         int(new1["n_countries"].iloc[0]) == 53,
         f"got {int(new1['n_countries'].iloc[0])}")
    gate("H3  Panel B exactly 0.0 on every cell", ok_rows and worst == 0.0,
         f"worst={worst!r}")
    gate("S2  Panel B unaffected by prior unweighted call in-process",
         ok_rows and worst == 0.0)

    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    expected = {
        "data_result/global_emissions_waterfall_1yr.csv",
        "figures/global_emissions_waterfall_1yr.png",
    }
    unexpected = [c for c in changed if c not in expected]
    print("\n      files changed by this run:")
    for c in changed:
        print(f"        {'expected  ' if c in expected else 'UNEXPECTED'} {c}")
    gate("H4  movement set contains no unexpected file", not unexpected,
         f"{unexpected}" if unexpected else "")

    above = v["actual_food_savings"] > PREDICTED_ESTIMATE
    gap = v["actual_food_savings"] - PREDICTED_ESTIMATE
    gate("SIGN  re-solve lands ABOVE the pi-scaled estimate 54.226594",
         above, f"delta {gap:+.6f} Mt")
    gate("MAG   gap below 0.01 Mt", abs(gap) < 0.01, f"{gap:+.6f} Mt")

    print("\n  internal consistency of the new rows:")
    r1 = v["naive_reductions"] - v["actual_food_savings"] - v["rebound_effect"]
    r2 = v["actual_food_savings"] - v["manufacturing"] - v["net_savings"]
    gate("      rebound == naive - actual", abs(r1) < 1e-9, f"residual {r1:+.3e}")
    gate("      net == actual - manufacturing", abs(r2) < 1e-9, f"residual {r2:+.3e}")

    print("\n" + "=" * 78)
    print("FAILURES: " + (", ".join(failures) if failures else "none"))
    print("=" * 78)


if __name__ == "__main__":
    main()
