"""
Reproduce the x-axis tick labels of figures/rebound_decomposition.png without
running the pipeline.

Replays the exact locator/formatter pair from
data_visualization/generate_rebound_figure.py:128-131 against each panel's
observed data maximum (read off the top bar's value label in the committed
figure), plus matplotlib's default 5% barh margins.

Question being answered: are the "0, 0, 0, 1, 1" labels a formatting artifact,
or do they reflect the tick positions the locator actually chose?
"""

import sys

import matplotlib.ticker as mticker

sys.stdout.reconfigure(encoding="utf-8")

# (row, column, data max as printed on the top bar of the committed figure)
PANELS = [
    ("Meat",    "A expected", 1.0),
    ("Meat",    "B actual",   0.53),
    ("Meat",    "C carbon",   15490.0),
    ("Dairy",   "A expected", 3.8),
    ("Dairy",   "B actual",   2.0),
    ("Dairy",   "C carbon",   6211.0),
    ("Cereals", "A expected", 1.5),
    ("Cereals", "B actual",   0.62),
    ("Cereals", "C carbon",   931.0),
]

# Verbatim from generate_rebound_figure.py:128-131
LOCATOR = mticker.MaxNLocator(nbins=5)
CURRENT = mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")

# Proposed: restrict to decimal-friendly steps so ticks land on 0.2 / 0.5 / 5000
# rather than 0.15 / 0.25, then pick the decimals those ticks need.
PROPOSED_LOCATOR = mticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10])


def decimals_for(ticks):
    """Fewest decimals that render every tick faithfully (no rounding drift)."""
    for d in range(0, 7):
        if all(abs(float(f"{t:.{d}f}") - t) < 1e-9 for t in ticks):
            return d
    return 6


def main():
    print(f"{'panel':20s} {'current labels':32s} {'proposed labels':34s} verdict")
    print("-" * 104)
    broken = 0
    unfaithful = 0
    for group, col, vmax in PANELS:
        # BEFORE: barh data range [0, vmax] with matplotlib's default 5% margins
        lo, hi = -0.05 * vmax, 1.05 * vmax
        cur_ticks = [t for t in LOCATOR.tick_values(lo, hi) if lo <= t <= hi]
        current = [CURRENT(t, None) for t in cur_ticks]

        # AFTER: the label-clipping fix pins xlim to (0, vmax * 1.18), which
        # changes the range the locator sees -- so re-derive ticks from it.
        lo, hi = 0.0, vmax * 1.18
        new_ticks = [t for t in PROPOSED_LOCATOR.tick_values(lo, hi)
                     if lo <= t <= hi]
        d = decimals_for(new_ticks)
        proposed = [f"{t:,.{d}f}" for t in new_ticks]

        dupes = len(current) != len(set(current))
        broken += dupes
        # Does each proposed label still name its own tick exactly?
        faithful = all(
            abs(float(lbl.replace(",", "")) - t) < 1e-9
            for lbl, t in zip(proposed, new_ticks)
        ) and len(proposed) == len(set(proposed))
        unfaithful += not faithful

        verdict = ("COLLAPSED -> fixed" if dupes else "ok already")
        if not faithful:
            verdict = "PROPOSAL STILL WRONG"
        print(f"{group + ' ' + col:20s} {', '.join(current):32s} "
              f"{', '.join(proposed):34s} {verdict}")

    print()
    print(f"Panels with duplicate labels under current code: {broken} / {len(PANELS)}")
    print(f"Panels still mislabelled under proposal:         {unfaithful} / {len(PANELS)}")


if __name__ == "__main__":
    main()
