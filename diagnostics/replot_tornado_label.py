"""Re-plot the tornado figure from the committed results CSV, label change only.

Does NOT re-run the sensitivity analysis: the numbers come from
``data_result/sensitivity_tornado_results.csv`` exactly as committed. The CSV's
digest is taken before and after so a stray write cannot pass unnoticed.

Bars checked here:
  B1  the diet endpoint renders as the new display label, and no text artist
      still carries the old one
  B3  every label lies inside the final x-limits, and each value annotation
      lies fully outside its bar's span
  B4  the results CSV is byte-identical across the re-plot
  B5  the change is confined to that one label: with the display mapping
      switched off, the x-limits and every other label's placement are the same

G1-G5 (placement gates) are checked separately by check_tornado_labels.py.

Usage:
    python -m diagnostics.replot_tornado_label
"""

from __future__ import annotations

import hashlib

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from data_visualization.pipeline import output_path
from diet_sensitivity import tornado_analysis as t

OLD_LABEL = "Fatty foods down"
NEW_LABEL = "Meat/Dairy/Oils down"


def digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plans(rows):
    """Reproduce plot_tornado's axes and converged label plan, figure kept open."""
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
    return ax, plans


def placements(ax, plans) -> dict:
    """{(row index, end): (string, left x, right x)} for one plan set."""
    out = {}
    for idx, plan in enumerate(plans):
        for p in plan:
            w = t._data_width(ax, p["s"])
            x0 = p["x"] - w if p["ha"] == "right" else p["x"]
            out[(idx, p["end"])] = (p["s"], round(x0, 6), round(x0 + w, 6))
    return out


def main() -> None:
    csv_path = output_path("sensitivity_tornado_results.csv")
    before = digest(csv_path)

    results = pd.read_csv(csv_path)
    out_fig = t.plot_tornado(results)
    after = digest(csv_path)

    # Rebuild the same plan on an equivalent axes to inspect the text artists.
    rows = results.reset_index(drop=True)
    ax, plans = build_plans(rows)

    xlo, xhi = ax.get_xlim()
    strings = [p["s"] for plan in plans for p in plan]

    # The width comparison that decides inside-bar vs both-outside, reported so
    # the margin behind each row's outcome is visible rather than inferred.
    pad = t.PAD_FRAC * (xhi - xlo)
    print()
    print(f"Width test at final xlim (pad {pad:.1f} Mt, 3 pads required):")
    for _, row in rows.iterrows():
        lo_v = float(row["low_net_savings_10yr_Mt"])
        hi_v = float(row["high_net_savings_10yr_Mt"])
        bar = abs(hi_v - lo_v)
        w = sum(
            t._data_width(ax, t._display_label(str(row[c])))
            for c in ("low_label", "high_label")
        )
        print(f"  {row['parameter']:30} bar={bar:7.1f}  names={w:7.1f}  "
              f"names+3pad={w + 3 * pad:7.1f}  "
              f"fits={'yes' if w + 3 * pad <= bar else 'no'}  "
              f"names_only_margin={bar - w:+7.1f}")

    b1 = any(NEW_LABEL in s for s in strings) and not any(
        OLD_LABEL in s for s in strings
    )

    b3_clip = True
    b3_value_outside = True
    print()
    print("Rendered labels (data units at final xlim):")
    for plan, (_, row) in zip(plans, rows.iterrows()):
        lo_v = float(row["low_net_savings_10yr_Mt"])
        hi_v = float(row["high_net_savings_10yr_Mt"])
        bar_l, bar_r = min(lo_v, hi_v), max(lo_v, hi_v)
        print(f"  {row['parameter']}  bar [{bar_l:.1f}, {bar_r:.1f}]")
        for p in plan:
            w = t._data_width(ax, p["s"])
            x0 = p["x"] - w if p["ha"] == "right" else p["x"]
            x1 = x0 + w
            clipped = x0 < xlo or x1 > xhi
            if clipped:
                b3_clip = False
            # A value annotation is any label carrying " Mt". In the fallback
            # form the name and value share one string, so the whole string is
            # required to sit outside the bar.
            is_value = " Mt" in p["s"]
            outside = x1 <= bar_l or x0 >= bar_r
            if is_value and not outside:
                b3_value_outside = False
            flags = []
            flags.append("inside-bar" if p.get("inside") else "outside-bar")
            if is_value:
                flags.append("value:" + ("OUTSIDE" if outside else "OVERLAPS BAR"))
            if clipped:
                flags.append("CLIPPED")
            print(f"    [{x0:8.1f}, {x1:8.1f}]  w={w:6.1f}  "
                  f"{p['s']!r:34} {' '.join(flags)}")

    # B5: re-plan with the mapping switched off and diff the placements, so the
    # claim "only that one label moved" is measured rather than assumed.
    new_places = placements(ax, plans)
    saved = t.DISPLAY_LABELS
    try:
        t.DISPLAY_LABELS = {}
        ax_old, plans_old = build_plans(rows)
        old_xlim = ax_old.get_xlim()
        old_places = placements(ax_old, plans_old)
        old_pad = t.PAD_FRAC * (old_xlim[1] - old_xlim[0])
        old_names = {
            row["parameter"]: sum(
                t._data_width(ax_old, str(row[c]))
                for c in ("low_label", "high_label")
            )
            for _, row in rows.iterrows()
        }
    finally:
        t.DISPLAY_LABELS = saved

    moved = sorted(k for k in new_places if new_places[k] != old_places.get(k))
    expected_moved = [
        k for k in new_places if OLD_LABEL in old_places.get(k, ("",))[0]
    ]
    b5_xlim = tuple(round(v, 6) for v in (xlo, xhi)) == tuple(
        round(v, 6) for v in old_xlim
    )
    b5_local = moved == sorted(expected_moved)

    print()
    print(f"  final xlim [{xlo:.1f}, {xhi:.1f}]")
    print(f"  xlim without mapping [{old_xlim[0]:.1f}, {old_xlim[1]:.1f}]")
    print(f"  placements that differ from the old label: "
          f"{[old_places[k][0] for k in moved]}")
    print("  width test with the old labels (same xlim, so directly comparable):")
    for _, row in rows.iterrows():
        w = old_names[row["parameter"]]
        print(f"    {row['parameter']:30} names={w:7.1f}  "
              f"names+3pad={w + 3 * old_pad:7.1f}")
    print(f"  figure -> {out_fig}")
    print()
    print(f"B1 new label present, old label absent : "
          f"{'PASS' if b1 else 'FAIL'}")
    print(f"B3 no label clipped by axes x-limits   : "
          f"{'PASS' if b3_clip else 'FAIL'}")
    print(f"B3 value annotations outside their bar : "
          f"{'PASS' if b3_value_outside else 'FAIL'}")
    print(f"B4 results CSV unchanged               : "
          f"{'PASS' if before == after else 'FAIL'}")
    print(f"   sha256 before {before[:16]}  after {after[:16]}")
    print(f"B5 x-limits unchanged vs old label     : "
          f"{'PASS' if b5_xlim else 'FAIL'}")
    print(f"B5 only the renamed label moved        : "
          f"{'PASS' if b5_local else 'FAIL'}")
    plt.close("all")


if __name__ == "__main__":
    main()
