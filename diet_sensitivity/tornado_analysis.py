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


def plot_tornado(results: pd.DataFrame) -> Path:
    """Generate a horizontal tornado plot."""
    baseline = float(results["baseline_net_savings_10yr_Mt"].iloc[0])
    fig, ax = plt.subplots(figsize=(9, 4.8))

    y = np.arange(len(results))
    colors = {"low": "#9ecae1", "high": "#08519c"}

    for idx, (_, row) in enumerate(results.reset_index(drop=True).iterrows()):
        low = row["low_net_savings_10yr_Mt"]
        high = row["high_net_savings_10yr_Mt"]
        left = min(low, high)
        width = abs(high - low)
        ax.barh(
            idx,
            width,
            left=left,
            height=0.55,
            color="#6baed6",
            edgecolor="white",
        )
        ax.text(
            low,
            idx - 0.33,
            f"{row['low_label']}: {low:,.0f} Mt",
            ha="right" if low < baseline else "left",
            va="center",
            fontsize=8,
            color=colors["low"],
            fontweight="bold",
        )
        ax.text(
            high,
            idx + 0.33,
            f"{row['high_label']}: {high:,.0f} Mt",
            ha="left" if high >= baseline else "right",
            va="center",
            fontsize=8,
            color=colors["high"],
            fontweight="bold",
        )

    ax.axvline(
        baseline,
        color="black",
        linestyle="--",
        linewidth=1.0,
        label=f"Baseline: {baseline:,.0f} Mt",
    )
    ax.set_yticks(y)
    ax.set_yticklabels(results["parameter"], fontsize=10)
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
        abs(results["low_net_savings_10yr_Mt"].min() - baseline),
        abs(results["high_net_savings_10yr_Mt"].max() - baseline),
    )
    ax.set_xlim(baseline - span * 1.35, baseline + span * 1.35)

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
