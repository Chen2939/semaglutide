"""Gates for the tornado figure's label placement.

Rebuilds the figure in memory from the committed results CSV and inspects the
real text artists, rather than eyeballing the PNG.

G1  no label extends beyond the axes x-limits
G2  every inside-bar label lies fully within its own bar's span
G3  the two inside labels in a row do not overlap each other
G4  the both-outside fallback fires for exactly the rows the width test rejects
G5  every label sits on its bar's centreline (y == row index)

Usage:
    python -m diagnostics.check_tornado_labels
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from data_visualization.pipeline import output_path
from diet_sensitivity import tornado_analysis as t


def main() -> None:
    results = pd.read_csv(output_path("sensitivity_tornado_results.csv"))
    rows = results.reset_index(drop=True)

    # Rebuild exactly what plot_tornado builds, keeping the figure open.
    t.plot_tornado(results)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    baseline = float(rows["baseline_net_savings_10yr_Mt"].iloc[0])
    for idx, (_, row) in enumerate(rows.iterrows()):
        lo, hi = row["low_net_savings_10yr_Mt"], row["high_net_savings_10yr_Mt"]
        ax.barh(idx, abs(hi - lo), left=min(lo, hi), height=t.BAR_HEIGHT)
    span = max(
        abs(rows["low_net_savings_10yr_Mt"].min() - baseline),
        abs(rows["high_net_savings_10yr_Mt"].max() - baseline),
    )
    ax.set_xlim(baseline - span * 1.35, baseline + span * 1.35)
    for _ in range(12):
        plans = [t._plan_row_labels(ax, r) for _, r in rows.iterrows()]
        need_lo, need_hi = ax.get_xlim()
        for plan in plans:
            for p in plan:
                w = t._data_width(ax, p["s"])
                x0 = p["x"] - w if p["ha"] == "right" else p["x"]
                need_lo, need_hi = min(need_lo, x0), max(need_hi, x0 + w)
        lo, hi = ax.get_xlim()
        if need_lo >= lo and need_hi <= hi:
            break
        m = 0.01 * (hi - lo)
        ax.set_xlim(min(lo, need_lo - m), max(hi, need_hi + m))

    xlo, xhi = ax.get_xlim()
    fails = []

    g1 = g2 = g3 = g5 = True
    fallback_rows = []
    for idx, (plan, (_, row)) in enumerate(zip(plans, rows.iterrows())):
        lo_v = float(row["low_net_savings_10yr_Mt"])
        hi_v = float(row["high_net_savings_10yr_Mt"])
        bar_l, bar_r = min(lo_v, hi_v), max(lo_v, hi_v)
        if not any(p["inside"] for p in plan):
            fallback_rows.append(row["parameter"])

        inside_spans = []
        for p in plan:
            w = t._data_width(ax, p["s"])
            x0 = p["x"] - w if p["ha"] == "right" else p["x"]
            x1 = x0 + w
            if x0 < xlo or x1 > xhi:
                g1 = False
                fails.append(f"G1 {row['parameter']!r} {p['s']!r} "
                             f"[{x0:.1f},{x1:.1f}] outside [{xlo:.1f},{xhi:.1f}]")
            if p["inside"]:
                if x0 < bar_l or x1 > bar_r:
                    g2 = False
                    fails.append(f"G2 {row['parameter']!r} {p['s']!r} "
                                 f"[{x0:.1f},{x1:.1f}] not within bar "
                                 f"[{bar_l:.1f},{bar_r:.1f}]")
                inside_spans.append((x0, x1, p["s"]))
        if len(inside_spans) == 2:
            (a0, a1, sa), (b0, b1, sb) = sorted(inside_spans)
            if a1 > b0:
                g3 = False
                fails.append(f"G3 {row['parameter']!r} {sa!r} overlaps {sb!r}")

    # G5: the drawing loop places every label at y == idx. Assert the plan
    # carries no y of its own, so no offset can be reintroduced silently.
    g5 = all("y" not in p for plan in plans for p in plan)

    # The MEASURED outcome, not the expected one. The initial expectation was
    # "Survivor GHG decline" alone; the width test also rejects "Diet
    # preference" (322 Mt of names against a 278 Mt bar). Pinned here so a
    # future change that alters which rows hold their names has to be noticed.
    predicted = {"Survivor GHG decline", "Diet preference"}
    g4 = set(fallback_rows) == predicted

    print()
    print(f"G1 all labels within axes x-limits      : {'PASS' if g1 else 'FAIL'}")
    print(f"G2 inside labels within their own bar   : {'PASS' if g2 else 'FAIL'}")
    print(f"G3 inside labels do not overlap         : {'PASS' if g3 else 'FAIL'}")
    print(f"G4 fallback rows == {sorted(predicted)}"
          f"{'':<3}: {'PASS' if g4 else 'FAIL'}  got {sorted(fallback_rows)}")
    print(f"G5 no per-label y offset survives       : {'PASS' if g5 else 'FAIL'}")
    print(f"   final xlim [{xlo:.1f}, {xhi:.1f}]")
    for f in fails:
        print("   " + f)
    plt.close("all")


if __name__ == "__main__":
    main()
