"""
Shared semaglutide drug carbon-footprint helper.

Professor-approved US-market scaling from Ozempic 1.0 mg to 2.4 mg
(Novo Nordisk Ozempic FlexTouch carbon-footprint PDF, Appendix A Table 2):

    annual footprint = 1.2 * 2.4 + 2.1 + 0.4 = 5.38 kg CO2e/user-year

Used by the baseline break-even comparison so pharmaceutical emissions are
folded into net food savings before comparing against survivor emissions.
"""

from __future__ import annotations

import pandas as pd
import pyreadr

from .pipeline import ROOT

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
    return (
        treated.groupby(["ISO", "scenario"], as_index=False)["weighting"]
        .sum()
        .rename(columns={"weighting": "treated_users_initial"})
    )


def build_drug_emissions() -> pd.DataFrame:
    """Build one-year and 10-year approximate drug emissions by country."""
    drug = load_treated_users()
    drug["drug_kg_co2e_per_user_year"] = ANNUAL_DRUG_KG_CO2E_PER_USER
    drug["drug_emissions_1yr_t"] = (
        drug["treated_users_initial"] * drug["drug_kg_co2e_per_user_year"] / 1000
    )
    # Approximation: initially treated users remain on treatment over 10 years.
    drug["treated_user_years_10yr_approx"] = drug["treated_users_initial"] * 10
    drug["drug_emissions_10yr_t"] = (
        drug["treated_user_years_10yr_approx"]
        * drug["drug_kg_co2e_per_user_year"]
        / 1000
    )
    drug["drug_treated_year_method"] = "initial_treated_users_x_10"
    return drug
