"""
Semaglutide drug carbon-footprint accounting.

Adds emissions from producing/administering the drug treatment itself to the
existing net climate accounting:

    net savings = food savings - survivor emissions - drug emissions

Drug-footprint assumption follows the professor's instruction using the
Novo Nordisk Ozempic FlexTouch carbon-footprint PDF, Appendix A Table 2
(US market):

    Ozempic 1.0 mg API      = 1.2 kg CO2e/year
    Device incl. cartridge  = 2.1 kg CO2e/year
    Needle                  = 0.4 kg CO2e/year

Only the API component is scaled from 1.0 mg to the modeled 2.4 mg dose;
device and needle are held constant:

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
import pyreadr

from data_visualization.breakeven_analysis import compute_breakeven
from data_visualization.pipeline import (
    ROOT,
    compute_food_savings,
    load_mortality_emissions,
    output_path,
)


# Professor-approved US-market scaling from Ozempic 1.0 mg to 2.4 mg.
API_1MG_US_KG_CO2E_PER_YEAR = 1.2
DEVICE_US_KG_CO2E_PER_YEAR = 2.1
NEEDLE_US_KG_CO2E_PER_YEAR = 0.4
TARGET_DOSE_MG = 2.4
REFERENCE_DOSE_MG = 1.0

ANNUAL_DRUG_KG_CO2E_PER_USER = (
    API_1MG_US_KG_CO2E_PER_YEAR * (TARGET_DOSE_MG / REFERENCE_DOSE_MG)
    + DEVICE_US_KG_CO2E_PER_YEAR
    + NEEDLE_US_KG_CO2E_PER_YEAR
)


def load_treated_users() -> pd.DataFrame:
    """Calculate initial treated users by country and uptake scenario."""
    sim = list(pyreadr.read_r(str(ROOT / "full_simulation_results8.rds")).values())[0]
    treated = sim[sim["adheres_to_treatment"]].copy()
    treated_users = (
        treated.groupby(["ISO", "scenario"], as_index=False)["weighting"]
        .sum()
        .rename(columns={"weighting": "treated_users_initial"})
    )
    return treated_users


def build_drug_emissions() -> pd.DataFrame:
    """Build one-year and 10-year approximate drug emissions by country."""
    treated_users = load_treated_users()
    drug = treated_users.copy()
    drug["drug_kg_co2e_per_user_year"] = ANNUAL_DRUG_KG_CO2E_PER_USER
    drug["drug_emissions_1yr_t"] = (
        drug["treated_users_initial"] * drug["drug_kg_co2e_per_user_year"] / 1000
    )
    # Approximation: initially treated users remain on treatment over 10 years.
    # The saved mortality output lacks treated-specific alive years, so this is
    # clearly labeled and intentionally conservative/simple.
    drug["treated_user_years_10yr_approx"] = drug["treated_users_initial"] * 10
    drug["drug_emissions_10yr_t"] = (
        drug["treated_user_years_10yr_approx"]
        * drug["drug_kg_co2e_per_user_year"]
        / 1000
    )
    drug["drug_treated_year_method"] = "initial_treated_users_x_10"
    return drug


def build_net_accounting() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge food, survivor, and drug emissions into net accounting outputs."""
    food_savings, _ = compute_food_savings()
    mort = load_mortality_emissions()
    drug = build_drug_emissions()

    be = compute_breakeven(food_savings, mort)
    merged = pd.merge(
        be,
        drug,
        on=["ISO", "scenario"],
        how="left",
    )
    merged["drug_emissions_1yr_t"] = merged["drug_emissions_1yr_t"].fillna(0)
    merged["drug_emissions_10yr_t"] = merged["drug_emissions_10yr_t"].fillna(0)
    merged["net_savings_after_survivor_t"] = (
        merged["total_food_savings_10yr"]
        - merged["total_survivor_emissions_10yr"]
    )
    merged["net_savings_after_survivor_and_drug_t"] = (
        merged["total_food_savings_10yr"]
        - merged["total_survivor_emissions_10yr"]
        - merged["drug_emissions_10yr_t"]
    )
    merged["ratio_food_to_survivor_plus_drug"] = np.where(
        (merged["total_survivor_emissions_10yr"] + merged["drug_emissions_10yr_t"]) > 0,
        merged["total_food_savings_10yr"]
        / (merged["total_survivor_emissions_10yr"] + merged["drug_emissions_10yr_t"]),
        np.nan,
    )
    merged["net_positive_after_drug"] = (
        (merged["annual_food_savings_t"] > 0)
        & np.isfinite(merged["ratio_food_to_survivor_plus_drug"])
        & (merged["ratio_food_to_survivor_plus_drug"] < 1.0)
    )

    summary_rows = []
    for scenario in ["max_uptake", "mod_uptake"]:
        sub_all = merged[merged["scenario"] == scenario]
        valid = sub_all[
            np.isfinite(sub_all["ratio_food_to_mort"])
            & (sub_all["annual_food_savings_t"] > 0)
            & (sub_all["total_survivor_emissions_10yr"] > 0)
        ]
        total_food_annual = valid["annual_food_savings_t"].sum()
        total_food_10yr = valid["total_food_savings_10yr"].sum()
        total_survivor = valid["total_survivor_emissions_10yr"].sum()
        total_drug_1yr = valid["drug_emissions_1yr_t"].sum()
        total_drug_10yr = valid["drug_emissions_10yr_t"].sum()
        summary_rows.append(
            {
                "scenario": scenario,
                "n_complete_countries": valid["ISO"].nunique(),
                "annual_food_savings_t": total_food_annual,
                "total_food_savings_10yr_t": total_food_10yr,
                "survivor_emissions_10yr_t": total_survivor,
                "drug_emissions_1yr_t": total_drug_1yr,
                "drug_emissions_10yr_t": total_drug_10yr,
                "drug_as_pct_annual_food_savings": (
                    total_drug_1yr / total_food_annual * 100
                ),
                "drug_as_pct_10yr_food_savings": (
                    total_drug_10yr / total_food_10yr * 100
                ),
                "ratio_without_drug": total_food_10yr / total_survivor,
                "ratio_with_drug": total_food_10yr / (total_survivor + total_drug_10yr),
                "net_savings_after_survivor_and_drug_t": (
                    total_food_10yr - total_survivor - total_drug_10yr
                ),
                "n_tipped_after_drug": int(valid["net_positive_after_drug"].sum()),
                "annual_drug_kg_co2e_per_user": ANNUAL_DRUG_KG_CO2E_PER_USER,
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

    axes[0].bar(
        x - width,
        summary["total_food_savings_10yr_t"] / 1e6,
        width,
        label="Food savings",
        color="#2ca25f",
    )
    axes[0].bar(
        x,
        summary["survivor_emissions_10yr_t"] / 1e6,
        width,
        label="Survivor emissions",
        color="#3182bd",
    )
    axes[0].bar(
        x + width,
        summary["drug_emissions_10yr_t"] / 1e6,
        width,
        label="Drug emissions",
        color="#de2d26",
    )
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=15, ha="right")
    axes[0].set_ylabel("Mt CO2e over 10 years")
    axes[0].set_title("A. Global 10-Year Components", loc="left", fontweight="bold")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.2)
    axes[0].set_axisbelow(True)

    axes[1].bar(
        x,
        summary["ratio_without_drug"],
        width,
        label="Before drug emissions",
        color="#9ecae1",
    )
    axes[1].bar(
        x + width,
        summary["ratio_with_drug"],
        width,
        label="After drug emissions",
        color="#08519c",
    )
    axes[1].axhline(1, color="black", linestyle="--", linewidth=0.8, alpha=0.65)
    axes[1].set_xticks(x + width / 2)
    axes[1].set_xticklabels(labels, rotation=15, ha="right")
    axes[1].set_ylabel("Food savings / (survivor + drug emissions)")
    axes[1].set_title("B. Ratio Impact", loc="left", fontweight="bold")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.2)
    axes[1].set_axisbelow(True)

    for row_idx, row in summary.reset_index(drop=True).iterrows():
        axes[1].text(
            row_idx,
            row["ratio_without_drug"] + 0.08,
            f"{row['ratio_without_drug']:.2f}x",
            ha="center",
            fontsize=8,
            fontweight="bold",
        )
        axes[1].text(
            row_idx + width,
            row["ratio_with_drug"] + 0.08,
            f"{row['ratio_with_drug']:.2f}x",
            ha="center",
            fontsize=8,
            fontweight="bold",
        )

    fig.suptitle(
        "Semaglutide Drug Carbon Footprint in Net Emissions Accounting",
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()
    out = output_path("drug_footprint_summary.png")
    plt.savefig(out, dpi=220, bbox_inches="tight")
    plt.close()
    return str(out)


def print_summary(summary: pd.DataFrame) -> None:
    """Print key results."""
    print("\nDrug footprint assumption")
    print(f"  API 1.0 mg US:       {API_1MG_US_KG_CO2E_PER_YEAR:.2f} kg CO2e/year")
    print(f"  Device US:           {DEVICE_US_KG_CO2E_PER_YEAR:.2f} kg CO2e/year")
    print(f"  Needle US:           {NEEDLE_US_KG_CO2E_PER_YEAR:.2f} kg CO2e/year")
    print(f"  Scaled 2.4 mg total: {ANNUAL_DRUG_KG_CO2E_PER_USER:.2f} kg CO2e/user-year")

    print("\nGlobal drug footprint impact")
    print(
        f"{'Scenario':<16}  {'Drug 1yr (kt)':>14}  {'Drug 10yr (Mt)':>15}  "
        f"{'% annual food':>13}  {'Ratio before':>13}  {'Ratio after':>12}  {'Tipped':>6}"
    )
    print("-" * 96)
    labels = {
        "max_uptake": "Max uptake",
        "mod_uptake": "Moderate",
    }
    for _, row in summary.iterrows():
        print(
            f"{labels.get(row['scenario'], row['scenario']):<16}  "
            f"{row['drug_emissions_1yr_t'] / 1e3:>14,.2f}  "
            f"{row['drug_emissions_10yr_t'] / 1e6:>15,.3f}  "
            f"{row['drug_as_pct_annual_food_savings']:>12.4f}%  "
            f"{row['ratio_without_drug']:>12.3f}x  "
            f"{row['ratio_with_drug']:>11.3f}x  "
            f"{int(row['n_tipped_after_drug']):>6d}"
        )


def main() -> None:
    print("=" * 80)
    print("DRUG CARBON FOOTPRINT ANALYSIS")
    print("=" * 80)
    net, summary = build_net_accounting()
    print_summary(summary)
    out_drug, out_net, out_summary = save_outputs(net, summary)
    out_fig = plot_summary(summary)

    print(f"\nDrug emissions by country -> {out_drug}")
    print(f"Net emissions with drug -> {out_net}")
    print(f"Summary -> {out_summary}")
    print(f"Figure -> {out_fig}")


if __name__ == "__main__":
    main()
