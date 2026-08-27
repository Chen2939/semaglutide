"""
Semaglutide drug carbon-footprint accounting.

Pharmaceutical emissions are now folded into the baseline break-even path by
default:

    net annual food savings = gross food savings - annual drug emissions
    ratio = net food savings / survivor emissions

This module remains the reporting layer for drug emissions and before/after
comparison. It no longer subtracts drug a second time from already-netted
break-even outputs.

Drug-footprint assumption follows the specified assumption using the
Novo Nordisk Ozempic FlexTouch carbon-footprint PDF, Appendix A Table 2
(US market):

    annual footprint = 1.2 * 2.4 + 2.1 + 0.4 = 5.38 kg CO2e/user-year

Outputs:
  data_result/drug_emissions_by_country.csv
  data_result/net_emissions_with_drug.csv
  data_result/drug_footprint_summary.csv
  figures/drug_footprint_summary.png

Usage:
    python -m drug_effect.analysis
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.drug_footprint import (
    ANNUAL_DRUG_KG_CO2E_PER_USER,
    build_drug_emissions,
)
from data_visualization.pipeline import (
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)


def build_net_accounting() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build country-level and summary drug-netted accounting outputs."""
    food_savings, _ = compute_food_savings()
    mort = load_mortality_emissions()
    drug = build_drug_emissions()

    be_with = compute_breakeven(food_savings, mort, include_drug=True)
    be_without = compute_breakeven(food_savings, mort, include_drug=False)[
        ["ISO", "scenario", "annual_food_savings_t", "total_food_savings_10yr", "ratio_food_to_mort"]
    ].rename(
        columns={
            "annual_food_savings_t": "annual_food_savings_gross_from_be_t",
            "total_food_savings_10yr": "total_food_savings_gross_10yr",
            "ratio_food_to_mort": "ratio_without_drug",
        }
    )

    merged = pd.merge(be_with, be_without, on=["ISO", "scenario"], how="left")
    merged = pd.merge(
        merged,
        drug[
            [
                "ISO",
                "scenario",
                "treated_users_initial",
                "drug_kg_co2e_per_user_year",
                "treated_user_years_10yr_approx",
                "drug_treated_year_method",
            ]
        ],
        on=["ISO", "scenario"],
        how="left",
    )

    # Break-even with include_drug=True already uses net food savings.
    merged["net_savings_after_survivor_t"] = (
        merged["total_food_savings_gross_10yr"]
        - merged["total_survivor_emissions_10yr"]
    )
    merged["net_savings_after_survivor_and_drug_t"] = (
        merged["total_food_savings_10yr"]
        - merged["total_survivor_emissions_10yr"]
    )
    merged["ratio_food_to_survivor_plus_drug"] = merged["ratio_food_to_mort"]
    merged["net_positive_after_drug"] = (
        (merged["annual_food_savings_t"] > 0)
        & np.isfinite(merged["ratio_food_to_mort"])
        & (merged["ratio_food_to_mort"] < 1.0)
    )

    summary_rows = []
    for scenario in ["max_uptake", "mod_uptake"]:
        sub_all = merged[merged["scenario"] == scenario]
        valid = sub_all[
            np.isfinite(sub_all["ratio_food_to_mort"])
            & (sub_all["annual_food_savings_gross_t"] > 0)
            & (sub_all["total_survivor_emissions_10yr"] > 0)
        ]
        total_food_gross_annual = valid["annual_food_savings_gross_t"].sum()
        total_food_net_annual = valid["annual_food_savings_t"].sum()
        total_food_gross_10yr = valid["total_food_savings_gross_10yr"].sum()
        total_food_net_10yr = valid["total_food_savings_10yr"].sum()
        total_survivor = valid["total_survivor_emissions_10yr"].sum()
        total_drug_1yr = valid["annual_drug_emissions_t"].sum()
        total_drug_10yr = valid["total_drug_emissions_10yr"].sum()
        summary_rows.append(
            {
                "scenario": scenario,
                "n_complete_countries": valid["ISO"].nunique(),
                "annual_food_savings_gross_t": total_food_gross_annual,
                "annual_food_savings_t": total_food_net_annual,
                "total_food_savings_gross_10yr_t": total_food_gross_10yr,
                "total_food_savings_10yr_t": total_food_net_10yr,
                "survivor_emissions_10yr_t": total_survivor,
                "drug_emissions_1yr_t": total_drug_1yr,
                "drug_emissions_10yr_t": total_drug_10yr,
                "drug_as_pct_annual_food_savings": (
                    total_drug_1yr / total_food_gross_annual * 100
                    if total_food_gross_annual > 0
                    else np.nan
                ),
                "drug_as_pct_10yr_food_savings": (
                    total_drug_10yr / total_food_gross_10yr * 100
                    if total_food_gross_10yr > 0
                    else np.nan
                ),
                "ratio_without_drug": total_food_gross_10yr / total_survivor,
                "ratio_with_drug": total_food_net_10yr / total_survivor,
                "net_savings_after_survivor_and_drug_t": (
                    total_food_net_10yr - total_survivor
                ),
                "n_tipped_after_drug": int(valid["net_positive_after_drug"].sum()),
                "annual_drug_kg_co2e_per_user": ANNUAL_DRUG_KG_CO2E_PER_USER,
                "drug_folded_into_food_savings": True,
            }
        )

    return merged, pd.DataFrame(summary_rows)


def save_outputs(net: pd.DataFrame, summary: pd.DataFrame) -> tuple:
    """Save country-level and summary outputs."""
    drug = build_drug_emissions()
    out_drug = output_path("drug_emissions_by_country.csv")
    out_net = output_path("net_emissions_with_drug.csv")
    out_summary = output_path("drug_footprint_summary.csv")
    drug.to_csv(out_drug, index=False)
    net.to_csv(out_net, index=False)
    summary.to_csv(out_summary, index=False)
    return out_drug, out_net, out_summary


def plot_summary(summary: pd.DataFrame) -> str:
    """Plot global food, survivor, and drug emissions for both uptake scenarios."""
    labels = ["Max uptake (95%)", "Moderate uptake (50%)"]
    x = np.arange(len(summary))
    width = 0.24

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    food_bars = axes[0].bar(
        x - width,
        summary["total_food_savings_gross_10yr_t"] / 1e6,
        width,
        label="Gross food savings",
        color="#2ca02c",
    )
    survivor_bars = axes[0].bar(
        x,
        summary["survivor_emissions_10yr_t"] / 1e6,
        width,
        label="Survivor emissions",
        color="#d62728",
    )
    drug_bars = axes[0].bar(
        x + width,
        summary["drug_emissions_10yr_t"] / 1e6,
        width,
        label="Drug emissions",
        color="#1f77b4",
    )
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_ylabel("Mt CO2e over 10 years")
    axes[0].set_title("A. Gross food, survivor, and drug emissions")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].set_ylim(
        0,
        (summary["total_food_savings_gross_10yr_t"] / 1e6).max() * 1.16,
    )

    for bars, values in (
        (food_bars, summary["total_food_savings_gross_10yr_t"] / 1e6),
        (survivor_bars, summary["survivor_emissions_10yr_t"] / 1e6),
        (drug_bars, summary["drug_emissions_10yr_t"] / 1e6),
    ):
        for bar, val in zip(bars, values):
            axes[0].text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{val:.1f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    axes[1].bar(
        x - width / 2,
        summary["ratio_without_drug"],
        width,
        label="Gross food / survivor",
        color="#7f7f7f",
    )
    axes[1].bar(
        x + width / 2,
        summary["ratio_with_drug"],
        width,
        label="(Food - drug) / survivor",
        color="#9467bd",
    )
    axes[1].axhline(1.0, color="black", linestyle="--", linewidth=1)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylabel("Food savings / survivor emissions")
    axes[1].set_title("B. Ratio before vs after folding in drug emissions")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].set_ylim(
        0,
        max(summary["ratio_without_drug"].max(), summary["ratio_with_drug"].max()) * 1.22,
    )

    for i, row in summary.reset_index(drop=True).iterrows():
        axes[1].text(
            i - width / 2,
            row["ratio_without_drug"] + 0.08,
            f"{row['ratio_without_drug']:.2f}x",
            ha="center",
            va="bottom",
            fontsize=8,
        )
        axes[1].text(
            i + width / 2,
            row["ratio_with_drug"] + 0.08,
            f"{row['ratio_with_drug']:.2f}x",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    fig.tight_layout()
    out = output_path("drug_footprint_summary.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def main() -> None:
    print("=" * 80)
    print("DRUG CARBON FOOTPRINT ANALYSIS")
    print("=" * 80)
    print("\nDrug footprint assumption")
    print(f"  Scaled 2.4 mg total: {ANNUAL_DRUG_KG_CO2E_PER_USER:.2f} kg CO2e/user-year")
    print("  Baseline break-even now folds drug emissions into net food savings.")

    net, summary = build_net_accounting()
    out_drug, out_net, out_summary = save_outputs(net, summary)
    fig_path = plot_summary(summary)

    print("\nGlobal drug footprint impact")
    print(
        f"{'Scenario':<12}{'Drug 1yr (kt)':>16}{'Drug 10yr (Mt)':>16}"
        f"{'% annual food':>14}{'Ratio before':>14}{'Ratio after':>13}{'Tipped':>8}"
    )
    print("-" * 96)
    for _, row in summary.iterrows():
        label = "Max uptake" if row["scenario"] == "max_uptake" else "Moderate"
        print(
            f"{label:<12}"
            f"{row['drug_emissions_1yr_t'] / 1e3:>14,.2f}  "
            f"{row['drug_emissions_10yr_t'] / 1e6:>15,.3f}  "
            f"{row['drug_as_pct_annual_food_savings']:>12.4f}%  "
            f"{row['ratio_without_drug']:>12.3f}x  "
            f"{row['ratio_with_drug']:>11.3f}x  "
            f"{int(row['n_tipped_after_drug']):>6}"
        )

    print(f"\nDrug emissions by country -> {out_drug}")
    print(f"Net emissions with drug -> {out_net}")
    print(f"Summary -> {out_summary}")
    print(f"Figure -> {fig_path}")


if __name__ == "__main__":
    main()
