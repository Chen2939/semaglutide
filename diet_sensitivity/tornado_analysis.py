"""
Tornado sensitivity plot for manuscript drafting.

Metric:
    Global 10-year net GHG savings under maximum uptake, in Mt CO2e:

        net = 10-year (food savings - drug emissions) - 10-year survivor emissions

The central reference is the OECD-updated uniform baseline with mean carbon
intensity, pharmaceutical emissions folded into net food savings, and 0%
annual decline in survivor per-capita GHG factors.

Sensitivity ranges:
  1. Carbon intensity: all foods P10 to all foods P90, each end scored
     against the survivor-emissions file built from the same intensities.
  2. Diet preference: cereals/sweets shift to fatty foods decrease more.
  3. Survivor-emissions decline: 0% to 2% annual decline.

Outputs:
  data_result/sensitivity_tornado_results.csv
  figures/sensitivity_tornado.png

Usage:
    python -m diet_sensitivity.tornado_analysis
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import (
    ROOT,
    adjust_survivor_decline,
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)



SCENARIO = "max_uptake"


def build_meat_ci_file(source_ci: str, output_name: str) -> Path:
    """Create a carbon-intensity file with only Meat changed from mean.

    UNCONSUMED. The carbon-intensity axis moved from meat-only to all-food
    P10/P90, so nothing calls this any more. Kept because retiring it -- and
    deleting the derived files it writes into ``data_result/`` -- is separate
    cleanup, not part of the basis change.
    """
    mean_ci = pd.read_csv(ROOT / "Food data" / "carbon_intensity.csv")
    source = pd.read_csv(ROOT / "Food data" / source_ci)

    derived = mean_ci.set_index("ISO").copy()
    meat_ci = source.set_index("ISO")["Meat"]
    derived["Meat"] = meat_ci
    if derived["Meat"].isna().any():
        missing = ", ".join(derived[derived["Meat"].isna()].index.astype(str))
        raise ValueError(f"Meat CI missing for ISO codes after alignment: {missing}")
    derived = derived.reset_index()

    out = output_path(output_name)
    derived.to_csv(out, index=False)
    return out


def global_net_savings(
    diet_scenario: str = "baseline_uniform",
    ci_file: str | Path = "carbon_intensity.csv",
    survivor_decline_rate: float = 0.0,
    valid_isos: set[str] | None = None,
    ci_scenario: str = "mean",
) -> dict:
    """Compute global max-uptake net savings for one sensitivity setting.

    ``ci_scenario`` selects the survivor-emissions file, and must match the
    carbon intensities ``ci_file`` carries: the survivor factor's P&N food
    add-back is priced with those same intensities.
    """
    food, _ = compute_food_savings(
        diet_scenario=diet_scenario,
        ci_file=str(ci_file),
    )
    mort = adjust_survivor_decline(
        load_mortality_emissions(ci_scenario), survivor_decline_rate
    )
    be = compute_breakeven(food, mort)

    sub = be[
        (be["scenario"] == SCENARIO)
        & np.isfinite(be["ratio_food_to_mort"])
        & (be["annual_food_savings_t"] > 0)
        & (be["total_survivor_emissions_10yr"] > 0)
    ].copy()
    if valid_isos is not None:
        sub = sub[sub["ISO"].isin(valid_isos)]

    annual_food = sub["annual_food_savings_t"].sum()
    food_10yr = sub["total_food_savings_10yr"].sum()
    survivor_10yr = sub["total_survivor_emissions_10yr"].sum()
    net_10yr = food_10yr - survivor_10yr

    return {
        "n_countries": sub["ISO"].nunique(),
        "annual_food_savings_Mt": annual_food / 1e6,
        "food_savings_10yr_Mt": food_10yr / 1e6,
        "survivor_emissions_10yr_Mt": survivor_10yr / 1e6,
        "net_savings_10yr_Mt": net_10yr / 1e6,
        "ratio_food_to_survivor": food_10yr / survivor_10yr,
    }


def build_tornado_results(ci_scenario: str = "mean") -> pd.DataFrame:
    """Run tornado endpoints and return a tidy results table.

    ``ci_scenario`` sets the survivor basis for the central reference and for
    any endpoint that does not override it.  Endpoints on a carbon-intensity
    axis carry their own ``ci_scenario`` in their spec, so each end of that axis
    is scored against the survivor file built from its own intensities.
    """
    baseline = global_net_savings(ci_scenario=ci_scenario)
    # Keep country coverage fixed to central complete-data countries.
    baseline_food, _ = compute_food_savings(
        diet_scenario="baseline_uniform", ci_file="carbon_intensity.csv"
    )
    # DELIBERATELY PINNED TO MEAN -- do not parameterise this call.
    # This builds valid_isos, the fixed country set every endpoint is scored on.
    # If it followed ci_scenario, a P10 or P90 endpoint could admit or drop
    # countries relative to the others and the axes would no longer be
    # comparable: a bar would move because its country set changed, not because
    # its parameter did. The mean-basis complete-data set is the common
    # denominator by design.
    baseline_be = compute_breakeven(baseline_food, load_mortality_emissions("mean"))
    valid_isos = set(
        baseline_be[
            (baseline_be["scenario"] == SCENARIO)
            & np.isfinite(baseline_be["ratio_food_to_mort"])
            & (baseline_be["annual_food_savings_t"] > 0)
            & (baseline_be["total_survivor_emissions_10yr"] > 0)
        ]["ISO"]
    )

    sensitivity_specs = [
        {
            # All-food carbon intensity, not meat-only. Each end carries its own
            # ci_scenario so the survivor side is priced with the same
            # intensities as the food side; a P90 food bar scored against a
            # mean survivor basis would overstate the net saving.
            "parameter": "Carbon intensity (all foods)",
            "low_label": "All foods P10",
            "high_label": "All foods P90",
            "low": {"ci_file": "carbon_intensity_p10.csv", "ci_scenario": "p10"},
            "high": {"ci_file": "carbon_intensity_p90.csv", "ci_scenario": "p90"},
        },
        {
            "parameter": "Diet preference",
            "low_label": "Cereals/sweets shift",
            "high_label": "Fatty foods down",
            "low": {"diet_scenario": "cereal_sweets_up"},
            "high": {"diet_scenario": "fatty_food_down"},
        },
        {
            "parameter": "Survivor GHG decline",
            "low_label": "0%/yr",
            "high_label": "2%/yr",
            "low": {"survivor_decline_rate": 0.0},
            "high": {"survivor_decline_rate": 0.02},
        },
    ]

    rows = []
    for spec in sensitivity_specs:
        # The run's ci_scenario is the default; a spec endpoint may override it.
        low = global_net_savings(
            valid_isos=valid_isos, **{"ci_scenario": ci_scenario, **spec["low"]}
        )
        high = global_net_savings(
            valid_isos=valid_isos, **{"ci_scenario": ci_scenario, **spec["high"]}
        )
        rows.append(
            {
                "parameter": spec["parameter"],
                "low_label": spec["low_label"],
                "high_label": spec["high_label"],
                "baseline_net_savings_10yr_Mt": baseline["net_savings_10yr_Mt"],
                "low_net_savings_10yr_Mt": low["net_savings_10yr_Mt"],
                "high_net_savings_10yr_Mt": high["net_savings_10yr_Mt"],
                "low_ratio_food_to_survivor": low["ratio_food_to_survivor"],
                "high_ratio_food_to_survivor": high["ratio_food_to_survivor"],
                "n_countries": low["n_countries"],
            }
        )

    results = pd.DataFrame(rows)
    results["range_Mt"] = (
        results["high_net_savings_10yr_Mt"] - results["low_net_savings_10yr_Mt"]
    ).abs()
    return results.sort_values("range_Mt", ascending=True)


# Display-only renaming of endpoint labels, applied at plot time.
#
# The label that reaches the figure comes from the ``low_label``/``high_label``
# columns of the committed results CSV, which are written by the endpoint specs
# in ``build_tornado_results``. Renaming at plot time keeps the scenario key
# (``fatty_food_down``), the spec label and the CSV column values untouched, so
# no stored value changes and the figure can be re-plotted from the committed
# CSV without re-running the analysis. A label with no entry here passes through
# unchanged.
DISPLAY_LABELS = {
    "Fatty foods down": "Meat/Dairy/Oils down",
}


def _display_label(label: str) -> str:
    """Figure text for a stored endpoint label."""
    return DISPLAY_LABELS.get(label, label)


BAR_COLOR = "#6baed6"
# One colour for every label, inside the bar and out. The old scheme keyed the
# low end to #9ecae1 and the high end to #08519c, which did two things badly:
# #9ecae1 on white measures 1.8:1 and was barely readable outside the bar, and
# it is nearly the bar's own colour, so it would vanish entirely once the text
# moved inside. The low/high distinction was redundant anyway -- each end is
# named ("All foods P10" vs "All foods P90") and sits at its own end of the bar.
# #08306b measures 5.35:1 on the bar and 15.9:1 on white, so one colour is legible
# in both placements.
LABEL_COLOR = "#08306b"
LABEL_PT = 8
BAR_HEIGHT = 0.55

# Gap between a bar edge and the text on either side of it, as a fraction of the
# axes width. Applied in data units at render time so it stays a constant
# distance on the page whatever the x-range works out to.
PAD_FRAC = 0.008


def _data_width(ax, text: str) -> float:
    """Rendered width of ``text`` in x-axis DATA units at the current xlim.

    Measured off the renderer rather than estimated from character counts: the
    whole point of the placement rule below is that it knows whether a string
    actually fits, and a guess would reintroduce the overflow it exists to stop.
    """
    fig = ax.figure
    t = ax.text(0, 0, text, fontsize=LABEL_PT, fontweight="bold")
    fig.canvas.draw()
    bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
    t.remove()
    inv = ax.transData.inverted()
    return abs(inv.transform((bb.width, 0))[0] - inv.transform((0, 0))[0])


def _plan_row_labels(ax, row) -> list[dict]:
    """Where each of a row's two end labels goes, decided by measurement.

    The rule: put the descriptive text INSIDE the bar and leave only the numeric
    value outside, so a long parameter name cannot push past the axes. Where the
    bar is too narrow to hold both names, that row falls back to the old
    behaviour -- name and value together, outside the bar.

    The fallback is DERIVED, not listed, and measurement is why: the obvious
    guess is that only "Survivor GHG decline" needs it, since its bar spans
    19 Mt against a ~900 Mt axis. Measured, "Diet preference" needs it too --
    its two names want 352 Mt against a 278 Mt bar, and are still 52 Mt over
    with the padding taken to zero. Only "Carbon intensity (all foods)" holds
    both names, at 240 Mt inside a 541 Mt bar. A hardcoded exception list would
    have encoded the wrong guess and clipped a label.

    The names are the DISPLAY names, so a rename in ``DISPLAY_LABELS`` is
    measured like any other string rather than assumed to fit.

    Because it is a width comparison, a future run in which a range narrows gets
    the fallback automatically, and one in which the survivor range widens stops
    needing it. diagnostics/check_tornado_labels.py pins the current outcome.
    """
    low = float(row["low_net_savings_10yr_Mt"])
    high = float(row["high_net_savings_10yr_Mt"])
    lo_x, hi_x = min(low, high), max(low, high)
    span = hi_x - lo_x

    # Which named endpoint sits at which edge. low is not guaranteed to be the
    # left edge -- nothing in build_tornado_results orders the pair.
    left_end = ("low", low) if low <= high else ("high", high)
    right_end = ("high", high) if low <= high else ("low", low)

    pad = PAD_FRAC * (ax.get_xlim()[1] - ax.get_xlim()[0])
    name = {
        "low": _display_label(str(row["low_label"])),
        "high": _display_label(str(row["high_label"])),
    }
    value = {"low": f"{low:,.0f} Mt", "high": f"{high:,.0f} Mt"}

    w_left = _data_width(ax, name[left_end[0]])
    w_right = _data_width(ax, name[right_end[0]])
    # Three pads: one inside each bar edge, one keeping the two names apart.
    fits = (w_left + w_right + 3 * pad) <= span

    out = []
    if fits:
        for end, edge in ((left_end, "left"), (right_end, "right")):
            key, x = end
            inward, outward = (1, -1) if edge == "left" else (-1, 1)
            out.append({"x": x + inward * pad, "s": name[key],
                        "ha": "left" if edge == "left" else "right",
                        "inside": True, "end": key})
            out.append({"x": x + outward * pad, "s": value[key],
                        "ha": "right" if edge == "left" else "left",
                        "inside": False, "end": key})
    else:
        for end, edge in ((left_end, "left"), (right_end, "right")):
            key, x = end
            outward = -1 if edge == "left" else 1
            out.append({"x": x + outward * pad,
                        "s": f"{name[key]}: {value[key]}",
                        "ha": "right" if edge == "left" else "left",
                        "inside": False, "end": key})
    return out


def plot_tornado(results: pd.DataFrame) -> Path:
    """Generate a horizontal tornado plot.

    Labels are placed by measurement, in two passes: the x-limits have to be
    final before any string can be converted to data units, and the strings then
    decide whether the x-limits are wide enough. See ``_plan_row_labels``.
    """
    baseline = float(results["baseline_net_savings_10yr_Mt"].iloc[0])
    fig, ax = plt.subplots(figsize=(9, 4.8))

    rows = results.reset_index(drop=True)
    y = np.arange(len(rows))

    for idx, (_, row) in enumerate(rows.iterrows()):
        low = row["low_net_savings_10yr_Mt"]
        high = row["high_net_savings_10yr_Mt"]
        ax.barh(
            idx,
            abs(high - low),
            left=min(low, high),
            height=BAR_HEIGHT,
            color=BAR_COLOR,
            edgecolor="white",
        )

    ax.axvline(
        baseline,
        color="black",
        linestyle="--",
        linewidth=1.0,
        label=f"Baseline: {baseline:,.0f} Mt",
    )
    ax.set_yticks(y)
    ax.set_yticklabels(rows["parameter"], fontsize=10)
    ax.set_xlabel("Global 10-year net GHG savings (Mt CO2e)")
    ax.set_title(
        "Sensitivity of Net Emissions Results (Max Uptake)",
        loc="left",
        fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.2)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", fontsize=8)

    span = max(
        abs(rows["low_net_savings_10yr_Mt"].min() - baseline),
        abs(rows["high_net_savings_10yr_Mt"].max() - baseline),
    )
    ax.set_xlim(baseline - span * 1.35, baseline + span * 1.35)

    # Widen until every label fits, then place. Widening the axes makes a
    # fixed-pixel string cover MORE data units, so the requirement moves as the
    # limits do and one pass is not enough. It converges geometrically because a
    # label is a small fraction of the range; the loop asserts that rather than
    # trusting it, since a silent non-convergence would clip a label -- the exact
    # defect this replaces.
    for attempt in range(12):
        plans = [_plan_row_labels(ax, row) for _, row in rows.iterrows()]
        need_lo, need_hi = ax.get_xlim()
        for plan in plans:
            for p in plan:
                w = _data_width(ax, p["s"])
                x0 = p["x"] - w if p["ha"] == "right" else p["x"]
                need_lo, need_hi = min(need_lo, x0), max(need_hi, x0 + w)
        lo, hi = ax.get_xlim()
        margin = 0.01 * (hi - lo)
        if need_lo >= lo and need_hi <= hi:
            break
        ax.set_xlim(min(lo, need_lo - margin), max(hi, need_hi + margin))
    else:
        raise RuntimeError(
            "Tornado label placement did not converge in 12 passes. A label is "
            "wide enough relative to the axis that widening to fit it makes it "
            "wider still; shorten the label or drop the font size."
        )

    # va='center' on every label, inside and out: they sit on the bar's
    # centreline rather than the old +/-0.33 offsets, which put them in the gap
    # between rows and made a two-ended bar read as two separate annotations.
    for idx, plan in enumerate(plans):
        for p in plan:
            ax.text(
                p["x"], idx, p["s"],
                ha=p["ha"], va="center",
                fontsize=LABEL_PT, color=LABEL_COLOR, fontweight="bold",
            )

    plt.tight_layout()
    out = output_path("sensitivity_tornado.png")
    plt.savefig(out, dpi=220, bbox_inches="tight")
    plt.close()
    return out


def main() -> None:
    print("=" * 80)
    print("TORNADO SENSITIVITY ANALYSIS")
    print("=" * 80)
    results = build_tornado_results()

    out_csv = output_path("sensitivity_tornado_results.csv")
    results.to_csv(out_csv, index=False)
    out_fig = plot_tornado(results)

    print(results.to_string(index=False))
    print(f"\nResults -> {out_csv}")
    print(f"Figure -> {out_fig}")


if __name__ == "__main__":
    main()
