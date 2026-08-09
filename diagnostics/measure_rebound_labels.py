"""Measure candidate label strings for generate_rebound_figure at print size.

The figure is built at 183 mm with real point sizes, so a label that overruns
its allotted width is clipped on the page rather than shrunk. Pick the strings
by measuring them, not by eye.

Usage:
    python -m diagnostics.measure_rebound_labels
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from data_visualization.figure_style import DOUBLE_COLUMN_IN, PT
from data_visualization import generate_rebound_figure as g

MM = 25.4


def width_in(fig, text, fontsize, weight="normal", style="normal"):
    """Rendered width of one string, in inches, at final figure scale."""
    t = fig.text(0.5, 0.5, text, fontsize=fontsize, fontweight=weight,
                 style=style)
    fig.canvas.draw()
    bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
    t.remove()
    return bb.width / fig.dpi


def main() -> None:
    n_rows = 9  # every food group; only used for the height arithmetic
    fig_h = (n_rows * g.ROW_AXES_IN + (n_rows - 1) * g.ROW_GAP_IN
             + g.TOP_IN + g.BOTTOM_IN)
    axes_w = (DOUBLE_COLUMN_IN - g.LEFT_IN - g.RIGHT_PAD_IN
              - 2 * g.COL_GAP_IN) / 3

    fig = plt.figure(figsize=(DOUBLE_COLUMN_IN, fig_h))

    print(f"page width      {DOUBLE_COLUMN_IN * MM:6.1f} mm")
    print(f"one column axes {axes_w * MM:6.1f} mm")
    print()

    print("-- column unit labels (must fit one axes width) --")
    for s in ("Mt / year", "Mt at t = 0", "kt CO₂eq / year",
              "kt CO₂eq at t = 0", "kt CO₂eq / year at t = 0"):
        w = width_in(fig, s, PT["axis_label"])
        fits = "OK " if w <= axes_w else "OVER"
        print(f"  [{fits}] {w * MM:6.1f} mm  {s!r}")

    print()
    print("-- suptitle candidates (must fit page width) --")
    for s in (
        "Rebound Decomposition by Food Group and Country (Max Uptake 95%)",
        "Rebound Decomposition by Food Group and Country "
        "(Max Uptake 95%, t = 0)",
        "Rebound Decomposition by Food Group and Country "
        "(Max Uptake 95%, t = 0, mortality effects excluded)",
    ):
        w = width_in(fig, s, PT["suptitle"], weight="bold")
        fits = "OK " if w <= DOUBLE_COLUMN_IN else "OVER"
        print(f"  [{fits}] {w * MM:6.1f} mm  {s!r}")

    print()
    print("-- footnote candidates (must fit page width) --")
    for s in (
        "Gap between A and B = rebound effect "
        "(price-induced consumption recovery)",
        "Gap between A and B = rebound effect "
        "(price-induced consumption recovery).  "
        "All panels at t = 0, mortality effects excluded.",
        "Gap between A and B = rebound effect "
        "(price-induced consumption recovery).  "
        "All panels at t = 0: no survival weighting, no survivor emissions, "
        "no manufacturing charge.",
    ):
        w = width_in(fig, s, PT["note"], style="italic")
        fits = "OK " if w <= DOUBLE_COLUMN_IN else "OVER"
        print(f"  [{fits}] {w * MM:6.1f} mm  {s!r}")

    plt.close(fig)


if __name__ == "__main__":
    main()
