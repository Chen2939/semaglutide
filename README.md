# Semaglutide Population Impact Analysis

Modelling the population-level impact of broad semaglutide (GLP-1 weight-loss drug) adoption on food demand, mortality, and greenhouse-gas emissions across ~200 countries.

## Research Question

If semaglutide were prescribed to all eligible individuals (BMI ≥ 30, or BMI ≥ 27 with Type 2 diabetes, age < 75), what are the downstream effects on:

1. **Caloric demand** — reduced BMI → lower energy expenditure → less food consumed
2. **Mortality** — lower BMI → fewer obesity-related deaths → person-years saved
3. **Price rebound** — lower food demand → lower prices → partial consumption recovery (Hegwood et al., 2023)
4. **Net carbon emissions** — food savings × carbon intensity, offset by emissions from additional survivors

Two uptake scenarios: **maximum (95%)** and **moderate (50%)** of eligible populations.

## Repository Structure

```
semaglutide/
├── Mortality Model.ipynb          # Mortality impact: Monte Carlo survival, person-years saved, emissions from survivors
├── Price rebound model.ipynb      # Price rebound economics: equilibrium solver, carbon savings by country & food group
├── build_carbon_intensity.py      # Builds country-specific carbon intensity from Poore & Nemecek (2018) + FAOSTAT
├── requirements.txt               # Python dependencies
├── requirements_lock.txt          # Pinned dependency versions
│
├── data_visualization/            # Visualization scripts (Python package)
│   ├── pipeline.py                # Shared data-loading & equilibrium-solving pipeline
│   ├── deterministic_mortality.py # Deterministic expected-value survivor person-years
│   ├── consumption_ghg.py         # OECD demand-based final-consumption GHG survivor-emissions rebuild
│   ├── generate_emissions_figure.py   # Country-level carbon emissions saved figure
│   ├── breakeven_analysis.py          # Break-even: food savings vs. survivor emissions
│   ├── generate_dashboard_figure.py   # Combined multi-panel country dashboard + food-group breakdown
│   ├── generate_rebound_figure.py     # Rebound decomposition by food group (analog to Hegwood Fig. 3)
│   └── generate_rebound_validation.py # Rebound % by food type & income group (analog to Hegwood Fig. 4a)
│
├── diet_sensitivity/              # Diet-composition sensitivity analysis
│   ├── scenarios.py               # Literature-motivated food-group shock assumptions
│   ├── pipeline.py                # Calorie-preserving diet-shock calibration + rebound model
│   └── analysis.py                # Runs sensitivity analysis, outputs CSVs and figures
├── drug_effect/                   # Drug product carbon-footprint accounting
│
├── figures/                       # Paper-ready figures (tracked in Git)
├── data_result/                   # Generated tabular analysis outputs (selected CSVs tracked via LFS)
├── Food data/                     # FAOSTAT food balance sheets, elasticities, price indices, mappings (not tracked)
├── oecd/                          # OECD GHG footprint input tracked via LFS
├── HLD/                           # Human Life-Table Database — mortality rates (not tracked)
├── Lancet/                        # NCD-RisC BMI & diabetes distributions (not tracked)
├── UN/                            # UN World Population Prospects 2024 (not tracked)
├── recategorize/                  # Poore & Nemecek (2018) paper + supplementary data (not tracked)
├── test/                          # Legacy/intermediate upstream outputs (mostly ignored)
├── legacy/                        # Archived R scripts, old data, and docs (tracked via Git LFS for large files)
└── venv/                          # Python virtual environment (not tracked)
```

## Pipeline

### Step 1 — R Simulation (upstream, pre-computed)

`Data_Cleaning9.8.R` (now in `legacy/R_scripts/`) generates the synthetic population with baseline and treated BMI, caloric intake, and demographics for ~200 countries. Its output is the `.rds` file consumed by subsequent steps:

- **Output:** `full_simulation_results8.rds`

`Mortality_model2.R` (now in `legacy/R_scripts/`) computes mortality tables and imputed demographic data:

- **Outputs:** `mortality2.rds`, `final_df_imputed.rds`

> These R scripts have already been run. The `.rds` outputs are required datasets (see below).

### Step 2 — Carbon Intensity Build

```bash
python build_carbon_intensity.py
```

Constructs country × food-group carbon intensity values (kg CO₂eq / kg food) by:
- Mapping 43 products from Poore & Nemecek (2018) to 115 FAOSTAT items → 9 `final_food_group` categories
- Computing country-specific weighted averages based on each nation's FAOSTAT consumption mix
- Excluding 18 FAOSTAT aggregate items to prevent double-counting
- Falling back to regional or global averages where country data is missing
- Generating three scenarios: mean (central), P10 (10th percentile), P90 (90th percentile)

**Input:** `recategorize/aaq0216_datas2.xls`, `Food data/FBS_Group_Mapping.csv`, FAOSTAT normalized food balance sheets, `Food data/faostat_country_mapping.csv`

**Output:** `Food data/carbon_intensity.csv` (mean), `Food data/carbon_intensity_p10.csv`, `Food data/carbon_intensity_p90.csv`

### Step 3 — Mortality Model (with population weighting)

Run the deterministic expected-value mortality model:

```bash
python -m data_visualization.deterministic_mortality
```

- Loads `final_df_imputed.pkl` and `mortality2.rds`
- Replaces the old stochastic Monte Carlo headline calculation with deterministic expected survival probabilities over 10 years
- Converts Human Life-Table `Mx` rates to annual death probabilities using `q = 1 - exp(-Mx)`
- Computes person-years saved under both uptake scenarios
- **Output:** `mortality model total emissions.csv`

`Mortality Model.ipynb` remains as the exploratory notebook for mortality data preparation and legacy diagnostics, but the deterministic script is the reproducible headline path.

The legacy notebook path:
- Loads `full_simulation_results8.rds`, `mortality2.rds`, and `HLD/Mx_1x1/` life tables
- `population_weighted=True` (default) multiplies individual survival diffs by their population weight before aggregation, producing output at the national population level; set to `False` for the original sample-level output
- **Output:** `final_df_imputed.pkl`

Then rebuild survivor emissions with the OECD consumption-based GHG source:

```bash
python -m data_visualization.consumption_ghg
```

This replaces the old World Bank territorial CO2 per-capita factor with OECD demand-based final-consumption GHG, including direct household emissions and excluding gross capital formation. The script filters `oecd/consumption_ghg_2025.csv` to final consumption (`FINAL_DEMAND_CATEGORY == CONS`), all activities (`ACTIVITY == _T`), 2022, tonnes CO2e, and unit multiplier 6 (Mt CO2e). It divides national totals by UN WPP 2022 total population to produce t CO2e/person, validates the professor's USA check (`5892.9 Mt`, about `17.25 t/person`), and rewrites `mortality model total emissions.csv` while preserving the downstream schema.

**OECD rebuild outputs:** `mortality model total emissions.csv`, `data_result/oecd_consumption_ghg_per_capita.csv`, `data_result/oecd_vs_worldbank_survivor_emissions.csv`

### Step 4 — Price Rebound Model

Run all cells in `Price rebound model.ipynb`:
- Loads `full_simulation_results8.rds` and all `Food data/` files
- Implements constant-elasticity supply/demand equilibrium (Hegwood et al., 2023)
- Computes rebound effect, net food reduction, and carbon savings per country × food group
- Includes sensitivity analysis (cells 15–17): re-runs the model with P10/Mean/P90 carbon intensity files and generates comparison figures
- Generates summary tables and visualisations

### Step 5 — Visualization Scripts

All visualization scripts live in the `data_visualization/` package. They share a common pipeline module (`pipeline.py`) that handles data loading and equilibrium solving, eliminating code duplication.

```bash
# Break-even analysis: food savings vs. survivor emissions
python -m data_visualization.breakeven_analysis

# Emissions saved by country (horizontal bar chart)
python -m data_visualization.generate_emissions_figure

# Combined country dashboard + food-group breakdown
python -m data_visualization.generate_dashboard_figure

# Rebound decomposition by food group & country (analog to Hegwood Fig. 3)
python -m data_visualization.generate_rebound_figure

# Rebound % by food type & income group (analog to Hegwood Fig. 4a)
python -m data_visualization.generate_rebound_validation
```

**Break-even analysis** — compares cumulative food-emission savings against cumulative emissions from additional survivors over a 10-year horizon. Computes break-even year and 10-year food-to-survivor ratio for each country and uptake scenario.
- **Output:** `figures/breakeven_by_country.png`, `figures/breakeven_curves.png`

**Emissions saved figure** — horizontal bar chart of carbon emissions saved from food reduction by country, for both moderate and maximum uptake scenarios.
- **Output:** `figures/emissions_saved_by_country.png`

**Country dashboard** — combined multi-panel figure for the paper showing the top 15 countries across three dimensions: (A) food-emission savings, (B) person-years saved, and (C) break-even ratio. Also generates a stacked bar chart breaking down savings by food group.
- **Output:** `figures/country_dashboard.png`, `figures/food_group_breakdown.png`

**Rebound decomposition** — 3×3 grid showing expected demand reduction, actual demand reduction (after price rebound), and resulting carbon emissions saved for the top countries across Meat, Dairy, and Cereals. Analogous to Hegwood et al. (2023) Figure 3.
- **Output:** `figures/rebound_decomposition.png`

**Rebound validation** — horizontal bar chart of rebound percentages by food type, grouped by World Bank income classification. Validates model consistency against Hegwood et al.'s reported range (53–71% for high-income countries).
- **Output:** `figures/rebound_by_income.png`

Generated figures are written to `figures/`; generated tabular outputs are written to `data_result/`.

**All scripts share inputs:** `full_simulation_results8.rds`, OECD-updated `mortality model total emissions.csv`, all `Food data/` files

### Step 6 — Diet-Composition Sensitivity Analysis

```bash
python -m diet_sensitivity.analysis
```

Runs the professor-requested diet-composition sensitivity analysis while keeping each country × uptake scenario's total calorie reduction fixed. The baseline model applies the EER-based demand reduction uniformly to every food group; this extension uses FAOSTAT `Food supply (kcal/capita/day)` shares to redistribute the same calorie reduction across food groups before running the existing Hegwood-style rebound equilibrium solver.

Scenarios:
- **`baseline_uniform`** — current model, all food groups reduce uniformly.
- **`fatty_food_down`** — meat, dairy, and fats/oils reduce 1.5× more than the baseline shock; other foods are adjusted so total calories remain unchanged. Motivated by Blundell et al. (2017) and Gibbons et al. (2021), which report lower preference/intake for high-fat foods with semaglutide.
- **`cereal_sweets_up`** — cereals and sweets reduce 1.5× more, while meat reduces 0.5× as much; other foods are adjusted to preserve total calories. Motivated by Hironaka et al. (2025), which reports stronger reductions in carbohydrate, sweet, chocolate, and starchy-food cravings, with animal protein not statistically significant.

The mortality model is not rerun for these scenarios because total calorie reduction, BMI, and person-years saved are held fixed. The sensitivity changes the food-emission savings numerator and therefore the mortality-adjusted food-to-survivor-emissions ratio.

Outputs:
- **Datasets:** `data_result/diet_sensitivity_results.csv`, `data_result/diet_sensitivity_ratio_comparison.csv`
- **Paper figures:** `figures/diet_sensitivity_global_comparison.png`, `figures/diet_sensitivity_lowest_ratio_countries.png`

Current headline result with deterministic mortality and OECD consumption-based survivor emissions: no valid country tips into net positive emissions after accounting for mortality under either diet-composition scenario. For maximum uptake among countries with complete food and OECD survivor-emissions data, the global 10-year food-savings-to-survivor-emissions ratio is 5.5× in the uniform baseline, 7.0× when fatty foods decrease more, and 3.6× when cereals/sweets decrease more and meat decreases less. Poland is closest to tipping in the cereal/sweets scenario at approximately 2.4×.

### Step 7 — Combined Conservative Sensitivity Analysis

```bash
python -m diet_sensitivity.combined_analysis
```

Runs the reviewer-style stacked conservative case: the `cereal_sweets_up` diet-composition scenario plus a meat-only low carbon-intensity assumption. The derived carbon-intensity file keeps all food groups at the mean Poore & Nemecek/FAOSTAT intensity except `Meat`, which is replaced with the P10 meat intensity from `Food data/carbon_intensity_p10.csv`.

Outputs:
- **Datasets:** `data_result/combined_sensitivity_results.csv`, `data_result/combined_sensitivity_ratio_comparison.csv`
- **Derived input:** `data_result/carbon_intensity_meat_p10.csv`
- **Figure:** `figures/combined_sensitivity_lowest_ratio_countries.png`

Current headline result: no complete-data country tips into net positive emissions in the stacked conservative case. For maximum uptake, the global 10-year food-savings-to-survivor-emissions ratio falls from 3.6× in the cereals/sweets diet-shift scenario with mean carbon intensities to 2.8× when Meat is assigned the P10 carbon intensity. Poland is closest to tipping at approximately 2.1×.

### Step 8 — All Sensitivities Overview

```bash
python -m diet_sensitivity.sensitivity_overview
```

Generates a compact comparison of all current sensitivity analyses against the OECD-updated baseline. This includes the uniform baseline, both diet-composition scenarios, full food carbon-intensity P10/P90 scenarios, and the combined conservative cereals/sweets + low-meat-CI scenario. Drug-manufacturing emissions are not included yet.

Outputs:
- **Datasets:** `data_result/all_sensitivity_overview_results.csv`, `data_result/all_sensitivity_overview_country_ratios.csv`
- **Figure:** `figures/all_sensitivity_overview.png`

Current headline result: no complete-data country tips into net positive emissions in any current sensitivity analysis. For maximum uptake, the global 10-year food-savings-to-survivor-emissions ratio ranges from 2.4× under the full all-food P10 carbon-intensity case to 10.4× under the full all-food P90 carbon-intensity case. The lowest country-level margin is Lithuania at approximately 1.6× in the all-food P10 case; the combined cereals/sweets + low-meat-CI case remains above break-even at 2.8× globally, with Poland closest at approximately 2.1×.

### Step 9 — Drug Carbon Footprint Accounting

```bash
python -m drug_effect.analysis
```

Adds emissions from producing/administering semaglutide treatment itself to the net climate accounting. The implementation follows the professor-specified assumption using the Novo Nordisk Ozempic FlexTouch product-carbon-footprint document, Appendix A Table 2, US market. Ozempic 1.0 mg has annual components of 1.2 kg CO2e for API, 2.1 kg CO2e for device/cartridge, and 0.4 kg CO2e for needle. The API component is scaled to the modeled 2.4 mg dose while device and needle are held constant:

```text
annual drug footprint = 1.2 * 2.4 + 2.1 + 0.4 = 5.38 kg CO2e/user-year
```

The script calculates one-year drug emissions for comparison with annual food savings, and a 10-year treated-user approximation (`initial_treated_users * 10`) for net accounting. The approximation is used because the saved headline mortality output does not contain treated-specific alive years.

Outputs:
- **Datasets:** `data_result/drug_emissions_by_country.csv`, `data_result/net_emissions_with_drug.csv`, `data_result/drug_footprint_summary.csv`
- **Figure:** `figures/drug_footprint_summary.png`

Current headline result: drug product emissions are small relative to food-emission savings. Under maximum uptake, including drug emissions lowers the 10-year food-savings-to-offset-emissions ratio from 5.48× to 5.17×; under moderate uptake, it lowers the ratio from 5.29× to 5.00×. No complete-data country tips into net positive emissions after adding drug emissions.

## Setup

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

Requires **Python 3.12+** and the virtual environment activated before running notebooks or scripts.

## Required Datasets (not tracked in Git)

The following datasets are too large or are third-party data that cannot be redistributed. They must be obtained separately and placed in the specified directories.

### `full_simulation_results8.rds`
> **Location:** project root

Full synthetic population output from `Data_Cleaning9.8.R`. Contains ~945,000 simulated individuals with baseline/treated BMI, caloric intake, demographics, and population weights for ~200 countries. Required by both notebooks.

### `mortality2.rds`
> **Location:** project root

Pre-computed mortality model output from `Mortality_model2.R`. Contains country-level mortality rates and hazard ratio assignments. Required by `Mortality Model.ipynb`.

### `oecd/consumption_ghg_2025.csv`
> **Location:** `oecd/`

OECD Greenhouse Gas Footprints data for demand-based final-consumption GHG emissions. The analysis uses final consumption, all activities, 2022, tonnes CO2e, and Mt units, then divides by UN WPP 2022 total population to estimate survivor emissions. This is the active emissions source for `mortality model total emissions.csv`.

### `API_EN.GHG.CO2.PC.CE.AR5_DS2_en_excel_v2_3736.xls`
> **Location:** project root

Legacy World Bank territorial CO2 per-capita source used before the OECD replacement. Retained only for comparison/backups; it is no longer the preferred survivor-emissions source.

### `Food data/`
> **Location:** `Food data/`

| File / Folder | Source | Description |
|---|---|---|
| `FoodBalanceSheets_E_All_Data_(Normalized)/` | [FAOSTAT](https://www.fao.org/faostat/) | Normalized food balance sheets — country-level food supply/consumption in 1000 tonnes |
| `FoodBalanceSheets_E_All_Data/` | [FAOSTAT](https://www.fao.org/faostat/) | Raw (non-normalized) food balance sheets |
| `ConsumerPriceIndices_E_All_Data_(Normalized)/` | [FAOSTAT](https://www.fao.org/faostat/) | Consumer food price indices by country |
| `FBS_Group_Mapping.csv` | Project-specific | Maps 115 FAOSTAT items to 9 `final_food_group` categories |
| `faostat_country_mapping.csv` | Project-specific | Maps FAOSTAT area names to ISO3 country codes |
| `elasticity_supply.csv` | Hegwood et al. (2023) | Supply elasticity estimates by food group |
| `elasticity_demand.csv` | Hegwood et al. (2023) | Demand elasticity estimates by food group and country |
| `carbon_intensity.csv` | Built by `build_carbon_intensity.py` | Country × food-group carbon intensity — mean (kg CO₂eq/kg) |
| `carbon_intensity_p10.csv` | Built by `build_carbon_intensity.py` | Country × food-group carbon intensity — 10th percentile |
| `carbon_intensity_p90.csv` | Built by `build_carbon_intensity.py` | Country × food-group carbon intensity — 90th percentile |

### `HLD/Mx_1x1/`
> **Location:** `HLD/Mx_1x1/`

Single-year-of-age, single-calendar-year mortality rate tables from the [Human Life-Table Database](https://www.lifetable.de/). One `.txt` file per country (e.g., `USA.Mx_1x1.txt`). ~61 countries. Required by `Mortality Model.ipynb`.

### `Lancet/`
> **Location:** `Lancet/`

NCD-RisC BMI and diabetes distribution data, downloaded from the [NCD Risk Factor Collaboration](https://ncdrisc.org/). Required by the upstream R simulation (already pre-computed).

### `UN/`
> **Location:** `UN/`

UN World Population Prospects 2024 — population by single year of age and sex. Download from [UN Population Division](https://population.un.org/wpp/). Required by the upstream R simulation (already pre-computed).

### `recategorize/`
> **Location:** `recategorize/`

| File | Description |
|---|---|
| `aaq0216_datas2.xls` | Poore & Nemecek (2018) supplementary data — GHG emissions per kg of 43 food products and global production totals |
| `aaq0216_datas1.xls` | Poore & Nemecek (2018) supplementary data — farm-level observations |

Download from the [Science supplementary materials](https://www.science.org/doi/10.1126/science.aaq0216) for Poore & Nemecek (2018).

## Legacy Code

The original R-based pipeline (simulation, analysis, and mortality scripts) has been archived in `legacy/`. See `legacy/docs/legacy_README.md` for the original documentation. The `.rds` outputs from those scripts are still required as inputs to the Python notebooks.

Legacy R scripts and documentation are tracked via regular Git. Large binary data files (`.rds`, `.pkl`) are tracked via **Git LFS**.

### Git LFS

This repository uses [Git Large File Storage](https://git-lfs.com/) for binary data files. LFS-tracked patterns (defined in `.gitattributes`):

- `*.rds` — R data files (`full_simulation_results8.rds`, `mortality2.rds`, `legacy/data/*.rds`)
- `*.pkl` — Python pickle files (`final_df_imputed.pkl`)
- `*.csv` — generated and cached tabular outputs tracked in Git, including diet sensitivity result tables and OECD validation/comparison tables

**For collaborators cloning the repo:**

```bash
# Install Git LFS (one-time setup)
git lfs install

# Clone as usual — LFS files are downloaded automatically
git clone <repo-url>
```

If you cloned before LFS was configured, run `git lfs pull` to download the large files.

## References

- **Hegwood, M. et al. (2023).** Simulating the food-system impacts of anti-obesity medications. *Nature Food*, 4, 828–836. [doi:10.1038/s43016-023-00792-z](https://doi.org/10.1038/s43016-023-00792-z)
- **Blundell, J. et al. (2017).** Effects of once-weekly semaglutide on appetite, energy intake, control of eating, food preference and body weight in subjects with obesity. *Diabetes, Obesity and Metabolism*, 19, 1242–1251. [doi:10.1111/dom.12932](https://doi.org/10.1111/dom.12932)
- **Gibbons, C. et al. (2021).** Effects of oral semaglutide on energy intake, food preference, appetite, control of eating and body weight in subjects with type 2 diabetes. *Diabetes, Obesity and Metabolism*, 23, 581–588. [doi:10.1111/dom.14255](https://doi.org/10.1111/dom.14255)
- **Hironaka, J. et al. (2025).** Changes in food preferences after oral semaglutide administration in Japanese patients with type 2 diabetes: KAMOGAWA-DM cohort. *Diabetes & Vascular Disease Research*, 22. [doi:10.1177/14791641251318309](https://doi.org/10.1177/14791641251318309)
- **Poore, J. & Nemecek, T. (2018).** Reducing food's environmental impacts through producers and consumers. *Science*, 360(6392), 987–992. [doi:10.1126/science.aaq0216](https://doi.org/10.1126/science.aaq0216)
- **NCD Risk Factor Collaboration (2024).** Worldwide trends in underweight and obesity. *The Lancet*.
- **OECD.** Greenhouse Gas Footprints: demand-based final-consumption GHG emissions. Dataset: `DSD_ICIO_GHG_EXPD_2025@DF_ICIO_GHG_EXPD_2025`. [OECD Data Explorer](https://data-explorer.oecd.org/)
- **World Bank.** Total greenhouse gas emissions per capita. Indicator: EN.GHG.CO2.PC.CE.AR5. Legacy comparison source. [World Bank Open Data](https://data.worldbank.org/)
- **UN Population Division (2024).** World Population Prospects 2024. [population.un.org/wpp](https://population.un.org/wpp/)
- **Human Life-Table Database.** Max Planck Institute for Demographic Research & University of California, Berkeley. [lifetable.de](https://www.lifetable.de/)
- **FAOSTAT.** Food Balance Sheets, Consumer Price Indices. Food and Agriculture Organization of the United Nations. [fao.org/faostat](https://www.fao.org/faostat/)
