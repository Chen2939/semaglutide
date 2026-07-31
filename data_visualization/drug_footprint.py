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


def build_drug_emissions(
    survival_weighted: bool = True,
    horizon: int = 10,
    survival_weight: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build per-year, one-year and multi-year drug emissions by country.

    Every column here is a NATIONAL TOTAL in tonnes CO2e, not a per-patient
    figure: ``treated_users_initial`` is the population-weighted headcount of
    adherers in the country, so multiplying by the per-user annual footprint gives
    the national annual total directly.

    Dead patients are not dosed. Treated-user-years over the horizon are therefore
    ``initial users x sum_y pi_dose(y)``, not ``initial users x horizon``.

    ``pi_dose`` is used here, NOT ``pi``. Both are means of treatment-world
    survival, but ``pi`` weights each patient by ``w * eer_diff`` -- how much their
    intake fell -- which is right for the food shock and wrong for dosing, where a
    surviving patient gets one dose whatever their appetite did.

    ``pi`` exceeds ``pi_dose`` on 1,248 of 1,260 (ISO, scenario, year) cells over a
    10-year horizon, by up to 0.85 percentage points -- so survival is usually a
    little higher among the patients who cut their intake most. The ordering is not
    universal: 12 cells reverse, all under moderate uptake, 10 of them Japan (all
    years) and 2 the Netherlands (years 9-10). Substituting ``pi`` here would
    therefore **overstate** treated-user-years and so **overstate the drug charge**
    -- measured at +0.126% (max uptake) and +0.100% (moderate) on the 10-year
    total. Because the drug charge is subtracted from food savings, that would push
    net savings and the food:survivor ratio *down*.

    The reversal is not a structural feature of those two countries. The weighted
    correlation between ``eer_diff`` and 10-year survival is weakly positive almost
    everywhere -- median +0.042, maximum +0.127 -- and Japan and the Netherlands sit
    essentially at zero (-0.008 and -0.002). Their sign flip is what a correlation
    indistinguishable from zero does, not evidence that big intake-reducers there
    die sooner. The practical reading: ``pi`` and ``pi_dose`` are near
    interchangeable per country, and the *sign* of their difference carries no
    meaning for a country near zero.

    The size of that error is negligible; the reason to keep the two weights apart
    is that they answer different questions, not that the numbers diverge much.
    See diagnostics/check_pi_dose_direction.py.
    """
    drug = load_treated_users()
    drug["drug_kg_co2e_per_user_year"] = ANNUAL_DRUG_KG_CO2E_PER_USER
    drug["drug_emissions_1yr_t"] = (
        drug["treated_users_initial"] * drug["drug_kg_co2e_per_user_year"] / 1000
    )

    years = list(range(1, horizon + 1))
    if survival_weighted:
        if survival_weight is None:
            from .survival_weighting import load_food_shock_survival_weight

            survival_weight = load_food_shock_survival_weight(
                horizon=horizon, column="pi_dose"
            )
        idx = pd.MultiIndex.from_arrays(
            [drug["ISO"], drug["scenario"]], names=["ISO", "scenario"]
        )
        missing = sorted(set(idx) - set(survival_weight.index))
        if missing:
            raise ValueError(
                f"Drug footprint: no pi_dose for {missing}. Refusing to proceed -- "
                "these would be dosed as if nobody ever died. Rebuild with: "
                "python -m data_visualization.survival_weighting"
            )
        weights = {y: survival_weight[y].reindex(idx).to_numpy(dtype=float)
                   for y in years}
        drug["drug_treated_year_method"] = f"initial_treated_users_x_sum_pi_dose_1_{horizon}"
    else:
        # Legacy: initially treated users remain on treatment for the whole
        # horizon, nobody dies.
        weights = {y: 1.0 for y in years}
        drug["drug_treated_year_method"] = f"initial_treated_users_x_{horizon}"

    # Anchored form: sum the WEIGHTS, then multiply the headcount once. Do not
    # "simplify" this to accumulating `initial * weight` year by year. The two are
    # algebraically identical, but ten sequential additions of a double are not
    # bit-identical to one multiplication, so the accumulating form moved
    # treated_user_years by 2-3 ULP at pi_dose == 1, where the weighting must be an
    # exact no-op. Summing ten exact 1.0s gives exactly 10.0, so the anchored form
    # reproduces the legacy `initial * 10` bit for bit.
    weight_sum = 0.0
    for year in years:
        alive = drug["treated_users_initial"] * weights[year]
        drug[f"drug_emissions_t_Y{year}"] = (
            alive * drug["drug_kg_co2e_per_user_year"] / 1000
        )
        weight_sum = weight_sum + weights[year]
    drug["treated_user_years_10yr_approx"] = (
        drug["treated_users_initial"] * weight_sum
    )
    drug["drug_emissions_10yr_t"] = (
        drug["treated_user_years_10yr_approx"]
        * drug["drug_kg_co2e_per_user_year"]
        / 1000
    )
    return drug
