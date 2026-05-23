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
├── breakeven_analysis.py          # Break-even: food-emission savings vs. survivor emissions over 10-year horizon
├── generate_emissions_figure.py   # Country-level carbon emissions saved figure (mod & max uptake)
├── requirements.txt               # Python dependencies
├── requirements_lock.txt          # Pinned dependency versions
│
├── Food data/                     # FAOSTAT food balance sheets, elasticities, price indices, mappings (not tracked)
├── HLD/                           # Human Life-Table Database — mortality rates (not tracked)
├── Lancet/                        # NCD-RisC BMI & diabetes distributions (not tracked)
├── UN/                            # UN World Population Prospects 2024 (not tracked)
├── recategorize/                  # Poore & Nemecek (2018) paper + supplementary data (not tracked)
├── test/                          # Pipeline outputs and cached results (not tracked)
├── legacy/                        # Archived R scripts, old data, and docs (not tracked)
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

Run all cells in `Mortality Model.ipynb`:
- Loads `full_simulation_results8.rds`, `mortality2.rds`, and `HLD/Mx_1x1/` life tables
- Runs 10-year Monte Carlo survival simulation (`run_multi_simulation()`) with BMI-based hazard ratios
- `population_weighted=True` (default) multiplies individual survival diffs by their population weight before aggregation, producing output at the national population level; set to `False` for the original sample-level output
- Computes person-years saved under both uptake scenarios
- Links survivors to per-capita CO₂ emissions from the **World Bank** (`API_EN.GHG.CO2.PC.CE.AR5_DS2_en_excel_v2_3736.xls`, indicator EN.GHG.CO2.PC.CE.AR5), projected to decline at 1% per year over the 10-year horizon
- **Outputs:** `final_df_imputed.pkl`, `mortality model total emissions.csv`

### Step 4 — Price Rebound Model

Run all cells in `Price rebound model.ipynb`:
- Loads `full_simulation_results8.rds` and all `Food data/` files
- Implements constant-elasticity supply/demand equilibrium (Hegwood et al., 2023)
- Computes rebound effect, net food reduction, and carbon savings per country × food group
- Includes sensitivity analysis (cells 15–17): re-runs the model with P10/Mean/P90 carbon intensity files and generates comparison figures
- Generates summary tables and visualisations

### Step 5 — Break-Even Analysis

```bash
python breakeven_analysis.py
```

Compares cumulative food-emission savings against cumulative emissions from additional survivors over a 10-year horizon:
- **Food side:** re-runs the Price Rebound Model equilibrium to compute annual CO₂eq savings per country (static, based on 2022 FAOSTAT data)
- **Survivor side:** loads year-by-year emissions from `mortality model total emissions.csv` (requires population-weighted output from Step 3)
- Computes break-even year and 10-year food-to-survivor ratio for each country and uptake scenario

**Input:** `full_simulation_results8.rds`, `mortality model total emissions.csv`, all `Food data/` files

**Output:** `test/breakeven_by_country.png`, `test/breakeven_curves.png`

### Step 6 — Emissions Saved Figure

```bash
python generate_emissions_figure.py
```

Produces a horizontal bar chart of carbon emissions saved from food reduction by country, for both moderate and maximum uptake scenarios. Re-runs the full Price Rebound Model pipeline internally.

**Input:** `full_simulation_results8.rds`, all `Food data/` files

**Output:** `test/emissions_saved_by_country.png`

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

### `API_EN.GHG.CO2.PC.CE.AR5_DS2_en_excel_v2_3736.xls`
> **Location:** project root

World Bank per-capita greenhouse gas emissions (CO₂ equivalent, AR5 methodology). Used in `Mortality Model.ipynb` to estimate emissions from additional survivors. Download from the [World Bank Open Data](https://data.worldbank.org/) portal.

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

## Key References

- **Hegwood, M. et al. (2023).** Simulating the food-system impacts of anti-obesity medications. *Nature Food*, 4, 828–836. [doi:10.1038/s43016-023-00792-z](https://doi.org/10.1038/s43016-023-00792-z)
- **Poore, J. & Nemecek, T. (2018).** Reducing food's environmental impacts through producers and consumers. *Science*, 360(6392), 987–992. [doi:10.1126/science.aaq0216](https://doi.org/10.1126/science.aaq0216)
- **NCD Risk Factor Collaboration (2024).** Worldwide trends in underweight and obesity. *The Lancet*.

## Legacy Code

The original R-based pipeline (simulation, analysis, and mortality scripts) has been archived in `legacy/`. See `legacy/docs/legacy_README.md` for the original documentation. The `.rds` outputs from those scripts are still required as inputs to the Python notebooks.
