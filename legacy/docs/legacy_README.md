# Semaglutide Population Impact Analysis

## Project Goal

This project models the population-wide effects of broad semaglutide adoption across high-income countries. The central research question is: if semaglutide were prescribed to all eligible individuals (BMI ≥ 30, or BMI ≥ 27 with Type 2 diabetes, age < 75), what would be the downstream impacts on:

1. **Caloric demand** — how much less food would treated populations eat?
2. **Mortality** — how many life-years would be saved due to BMI reduction?
3. **Greenhouse gas emissions** — what is the net emissions effect when food savings are weighed against the additional emissions from longer-lived people?
4. **Economic rebound** — does reduced food demand lower prices, which then partially offsets consumption savings?

Two uptake scenarios are modeled: **Maximum uptake** (95% of eligible individuals remain on treatment) and **Moderate uptake** (50% remain on treatment, analogous to statin adherence rates).

All analysis is conducted in R (version 4.4.1).

---

## Folder Structure

```
Code and data/
├── Data_Cleaning9.7.R            # Main simulation pipeline (version 9.7)
├── Data_Cleaning9.8.R            # Main simulation pipeline (version 9.8, current)
├── Semaglutide_Analysis_7.R      # Analysis & visualisation (paired with v9.7)
├── Semaglutide_Analysis_8.R      # Analysis & visualisation (paired with v9.8)
├── Mortality_model2.R            # Mortality impact model
├── full_simulation_results7.rds  # Cached simulation output from v9.7
├── full_simulation_results8.rds  # Cached simulation output from v9.8
├── Worldbank_incomes_cleaned.xlsx # World Bank 2022 high-income country list
├── Methodology document.docx     # Detailed methodology for mortality & economic models
├── Lancet/                       # NCD-RisC input data
│   ├── NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv
│   ├── NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv
│   ├── NCD_RisC_Lancet_2024_Diabetes_age_specific_countries.csv
│   ├── NCD_RisC_Lancet_2020_height_child_adolescent_country.csv
│   ├── lancet_column_names.csv   # Column name reference
│   └── lancet_column_names.xlsx
├── HLD/                          # Mortality data
│   ├── HLD.txt                   # Main mortality dataset
│   └── Mx_1x1/                   # Country-specific mortality life tables (~61 countries)
│       ├── AUS.Mx_1x1.txt
│       ├── USA.Mx_1x1.txt
│       └── ... (one file per country)
└── UN/                           # UN population data
    ├── WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx
    └── WPP2024_POP_F01_3_POPULATION_SINGLE_AGE_FEMALE.xlsx
```

---

## File Descriptions

### R Scripts

#### `Data_Cleaning9.8.R` _(current version — use this one)_
The core simulation pipeline. Runs end-to-end from raw data to a saved `.rds` results file. Steps:
1. Loads BMI, height, and diabetes data from the `Lancet/` folder and population counts from `UN/`.
2. Filters to high-income countries using `Worldbank_incomes_cleaned.xlsx`.
3. Builds seven-component skew-normal mixture models for each country × sex × age BMI distribution.
4. Generates 500 synthetic individuals per country–sex–age group (≈945,000 total).
5. Assigns heights, physical activity levels (PAL), and diabetes status to each individual.
6. Applies semaglutide eligibility criteria and samples weight-loss from N(11.8%, SD 6%).
7. Calculates baseline and post-treatment BMR (Mifflin-St Jeor) and total energy expenditure (BMR × PAL).
8. Saves results to `full_simulation_results8.rds`.

**Key changes from v9.7 → v9.8:**
- Added age-75 upper limit to treatment eligibility
- Removed the efficacy floor (individuals can now experience weight gain, not just no effect)
- Removed a `slice_tail()` failsafe that was only needed for unclean input data
- Improved inline documentation

**Key changes from v9.6 → v9.7:**
- Population weighting now stratified by age **and** sex (previously age only)

#### `Data_Cleaning9.7.R`
Previous version of the simulation pipeline. Retained for reproducibility. Output is `full_simulation_results7.rds`.

#### `Semaglutide_Analysis_8.R`
Loads `full_simulation_results8.rds` and produces all analysis outputs: summary statistics, country-level caloric reduction estimates, and visualisations. Paired with `Data_Cleaning9.8.R`.

#### `Semaglutide_Analysis_7.R`
Same as above, paired with the v9.7 simulation. Loads `full_simulation_results7.rds`.

#### `Mortality_model2.R`
Standalone mortality impact model. Inputs are the `.rds` simulation output and the `HLD/` mortality files. Steps:
1. Loads and imputes missing mortality data (imputation hierarchy: regional median → global median → floor of 0.00001).
2. Assigns BMI-based hazard ratios (from published literature) to each simulated individual, using BMI 20–25 as the reference category.
3. Runs a 10-year Monte Carlo survival simulation, comparing baseline vs. post-treatment mortality year by year.
4. Individuals who age past 75 during the simulation receive a 50% reduction in treatment benefit (reflecting real-world de-prescribing).
5. Computes **person-years saved** over the 10-year horizon.
6. Multiplies person-years saved by country-specific per-capita CO₂ emissions (projected to decline 1%/year) to estimate the emissions cost of the additional survivors.

---

### Data Files

#### `full_simulation_results8.rds` / `full_simulation_results7.rds`
Cached R objects containing the full synthetic population with baseline and treated attributes. Loading these files skips the computationally expensive simulation in `Data_Cleaning` and allows you to jump straight to analysis. These files are large and should not be manually edited.

#### `Worldbank_incomes_cleaned.xlsx`
World Bank 2022 country income classifications, cleaned for direct join with the simulation data. Used to restrict the analysis to high-income nations.

#### `Methodology document.docx`
Narrative methodology write-up covering the **mortality model** and the **economic rebound model**. The economic model follows the approach of Margaret et al., modelling how reduced food demand lowers equilibrium prices, which partially offsets the initial demand reduction (the rebound effect). Also includes food-group mapping tables used to reconcile FAOSTAT categories with supply/demand elasticity datasets.

---

### `Lancet/` — NCD-RisC Input Data

| File | Contents |
|------|----------|
| `NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv` | Age- and country-specific female BMI distributions, 2022 |
| `NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv` | Age- and country-specific male BMI distributions, 2022 |
| `NCD_RisC_Lancet_2024_Diabetes_age_specific_countries.csv` | Age- and country-specific diabetes prevalence |
| `NCD_RisC_Lancet_2020_height_child_adolescent_country.csv` | Country- and sex-specific height data (19-year-olds used as adult proxy) |
| `lancet_column_names.csv/.xlsx` | Reference files for column naming conventions |

---

### `HLD/` — Mortality Data

Contains life-table mortality rates (Mx) from the Human Life-table Database (or Human Mortality Database). `HLD.txt` is the main combined file. The `Mx_1x1/` subfolder contains one file per country with single-year-of-age, single-calendar-year mortality rates (the `Mx_1x1` format). Approximately 61 high-income countries are represented.

---

### `UN/` — Population Data

UN World Population Prospects 2024 population counts by single year of age, separately for males and females. Used to weight simulated individuals to national population sizes so that per-country aggregate caloric and mortality results are on an absolute scale.

---

## How to Run the Analysis

1. **Run the simulation** (slow — ~30 min depending on hardware):
   ```r
   source("Data_Cleaning9.8.R")
   # Outputs: full_simulation_results8.rds
   ```

2. **Run the analysis and generate figures**:
   ```r
   source("Semaglutide_Analysis_8.R")
   # Reads: full_simulation_results8.rds
   ```

3. **Run the mortality model** (requires simulation output):
   ```r
   source("Mortality_model2.R")
   # Reads: full_simulation_results8.rds + HLD/ mortality files
   ```

> If you only want to regenerate figures or explore results without re-running the simulation, start at step 2. The `.rds` files are pre-computed.

---

## Key Modelling Assumptions

| Assumption | Value / Source |
|------------|---------------|
| Weight loss distribution | N(mean = 11.8%, SD = 6%) |
| Maximum uptake (adverse effect discontinuation) | 95% of eligible patients remain on treatment |
| Moderate uptake | 50% of eligible patients remain on treatment |
| Treatment eligibility upper age limit | 75 years |
| Synthetic individuals per country–sex–age cell | 500 |
| Mortality simulation horizon | 10 years |
| Annual per-capita CO₂ decline rate | 1% per year |
| BMR equation | Mifflin-St Jeor |
| Diabetes type split | 90% of diabetic individuals assigned Type 2 |
| Diabetes relative risk per 5-unit BMI increase above 22 | 1.75 (men), 1.69 (women) |

---

## Version History (Data_Cleaning scripts)

| Version | Notable Changes |
|---------|----------------|
| 9.8 | Age-75 eligibility cutoff; removed efficacy floor; improved documentation |
| 9.7 | Population weighting stratified by age **and** sex |
| 9.6 | Population weighting by age only |
