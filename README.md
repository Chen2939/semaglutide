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
├── Mortality Model.ipynb          # Mortality data prep and legacy exploratory diagnostics
├── Price rebound model.ipynb      # Price rebound economics: equilibrium solver, carbon savings by country & food group
├── build_carbon_intensity.py      # Builds country-specific carbon intensity from Poore & Nemecek (2018) + FAOSTAT
├── requirements.txt               # Python dependencies
├── requirements_lock.txt          # Pinned dependency versions
│
├── data_visualization/            # Core model + figure scripts (Python package)
│   ├── pipeline.py                # THE price-rebound pipeline: compute_food_savings()
│   ├── deterministic_mortality.py # Deterministic expected-value survivor person-years
│   ├── survival_weighting.py      # pi(t) / pi_dose(t): survival weights for the food shock and dosing
│   ├── consumption_ghg.py         # OECD demand-based final-consumption GHG survivor-emissions rebuild
│   ├── breakeven_analysis.py          # Break-even: food savings vs. survivor emissions
│   ├── survivor_manuscript_numbers.py # Manuscript X/Y survivor numbers
│   ├── drug_footprint.py              # Per-country pharmaceutical emissions
│   ├── generate_emissions_figure.py   # Country-level carbon emissions saved figure
│   ├── generate_dashboard_figure.py   # Combined multi-panel country dashboard + food-group breakdown
│   ├── generate_rebound_figure.py     # Rebound decomposition by food group (analog to Hegwood Fig. 3)
│   ├── generate_rebound_validation.py # Rebound % by food type & income group (analog to Hegwood Fig. 4a)
│   └── generate_waterfall*.py         # 1-year, 10-year and combined emissions waterfalls
│
├── diet_sensitivity/              # Diet-composition and carbon-intensity sensitivity analyses
│   ├── scenarios.py               # Literature-motivated food-group shock assumptions
│   ├── analysis.py                # Three diet scenarios, CSVs + figures
│   ├── combined_analysis.py       # Combined conservative case (diet shift + all-food P10 CI)
│   ├── sensitivity_overview.py    # All six specifications, max uptake, overview figure
│   ├── sensitivity_suite.py       # Both uptake levels + year-10 annual ratio (manuscript table)
│   └── tornado_analysis.py        # Tornado plot over the sensitivity ranges
├── drug_effect/                   # Drug product carbon-footprint accounting
├── scripts/
│   └── build_supplement_table.py  # Supplementary results table
│
├── code/
│   └── compute_child_energy.R     # Builds the child (0-17) energy pool from UN WPP + FAO/WHO/UNU
├── data/
│   └── child_energy_requirement_lookup.csv  # FAO/WHO/UNU (2004) requirement table (generated)
│
├── reference/                     # Reference snapshots for the reproduction check
│   ├── reference_headline_numbers.csv
│   └── reference_sensitivity_suite.csv
│
├── figures/                       # Paper-ready figures (tracked in Git)
├── data_result/                   # Generated tabular analysis outputs (selected CSVs tracked)
├── Food data/                     # FAOSTAT bulk data (download), mappings + elasticities (tracked)
├── oecd/                          # OECD GHG footprint input tracked via LFS
├── HLD/                           # Human Life-Table Database — mortality rates (download from source)
├── Lancet/                        # NCD-RisC BMI & diabetes distributions (download from source)
├── recategorize/                  # Poore & Nemecek (2018) supplementary data (download from source)
├── test/                          # Legacy/intermediate upstream outputs (mostly ignored)
├── legacy/                        # Archived R scripts, old data, and docs (tracked via Git LFS for large files)
└── venv/                          # Python virtual environment (not tracked)
```

There is no `UN/` directory: the UN WPP workbooks are read from wherever they
already live, via the `UN_WPP_DIR` environment variable. Point it at the
directory containing
`WPP2024_POP_F01_1_POPULATION_SINGLE_AGE_BOTH_SEXES.xlsx` — with the variable
unset the code falls back to `<repo>/UN`, which does not exist, and fails with
the exact filename it wanted. Download the 2024 vintage from
<https://population.un.org/wpp/>. See
[External data](#external-data-three-buckets).

## Reproducing the paper's numbers

### Run order

Order matters between the mortality and food stages. Everything from step 3
onward reads `mortality model total emissions_oecd.csv`, so that file must exist
and be current before any analysis script runs. It is committed, so a fresh
clone can skip steps 1–2 entirely and go straight to step 3.

```bash
# 1. Survivor person-years  (only if the mortality model changed)
python -m data_visualization.deterministic_mortality
#    reads  final_df_imputed.pkl   (population AND its imputed mortality_rate)
#    writes mortality model total emissions.csv   (person-years only)

# 2. Attach OECD emissions factors  (only if step 1 was run)
export UN_WPP_DIR=/path/to/unwpp        # see External data
python -m data_visualization.consumption_ghg
#    reads  mortality model total emissions.csv, oecd/consumption_ghg_2025.csv,
#           $UN_WPP_DIR/WPP2024_POP_F01_1_POPULATION_SINGLE_AGE_BOTH_SEXES.xlsx
#    writes mortality model total emissions_oecd.csv      <- what everything reads
#           data_result/oecd_consumption_ghg_per_capita.csv

# 3. Survival weights for the food shock  (only if the mortality model changed)
python -m data_visualization.survival_weighting
#    reads  final_df_imputed.pkl
#    writes data_result/food_shock_survival_weight.csv   <- read by the food side

# 4. Carbon intensity  (regenerates the committed canonical files bit-for-bit)
python build_carbon_intensity.py --scenario mean
python build_carbon_intensity.py --scenario p10
python build_carbon_intensity.py --scenario p90

# 5. Analysis and figures — any order, all independent
python -m data_visualization.breakeven_analysis
python -m data_visualization.generate_emissions_figure
python -m data_visualization.generate_dashboard_figure
python -m data_visualization.generate_rebound_figure
python -m data_visualization.generate_rebound_validation
python -m data_visualization.generate_waterfall_figure
python -m data_visualization.generate_waterfall_1yr_figure
python -m data_visualization.generate_waterfall_combined_figure
python -m data_visualization.survivor_manuscript_numbers
python -m diet_sensitivity.analysis
python -m diet_sensitivity.combined_analysis
python -m diet_sensitivity.sensitivity_overview
python -m diet_sensitivity.sensitivity_suite
python -m diet_sensitivity.tornado_analysis
python -m drug_effect.analysis
python scripts/build_supplement_table.py
```

Run everything from the repository root; several scripts resolve inputs
relative to it.

**Do not run step 1 after step 2.** `deterministic_mortality.py` writes
`mortality model total emissions.csv` with NaN emissions placeholders, which
step 2 then fills in. Running them in the wrong order leaves the person-year
file stale relative to the OECD file, and nothing will warn you.

### The one model function

Every food-emissions number comes from a single function:

```python
from data_visualization.pipeline import compute_food_savings

food_savings, result_df = compute_food_savings(
    diet_scenario=None,               # None | baseline_uniform | fatty_food_down | cereal_sweets_up
    ci_file="carbon_intensity.csv",   # mean | _p10 | _p90 | a derived file
    survival_weighted=True,           # scale the shock by pi(t); False = legacy single solve
    horizon=10,                       # years of the per-year series
)
```

Arguments are keyword-only on purpose. Both uptake levels (`max_uptake`,
`mod_uptake`) are produced in one call and appear as the `scenario` column.

**`annual_food_savings_t` is the year-1 saving, not a constant annual rate.**
Under survival weighting the annual saving falls each year as treated patients
die, so a single number has to mean a particular year. `food_savings` also carries
`annual_food_savings_t_Y1`…`_Y10`, and `result_df` carries
`actual_reduction_Y{t}`, `carbon_savings_t_Y{t}` and
`expected_demand_reduction_Y{t}`. **Anything cumulative must sum the series** —
`annual × 10` overstates the ten-year total by roughly 4%. `survival_weighted=False`
reproduces the legacy behaviour exactly and is the right basis for an
instantaneous t = 0 quantity, which is what `scripts/build_supplement_table.py`
uses it for.

### Script → inputs → outputs

| Script | Reads | Writes |
|---|---|---|
| `build_carbon_intensity.py` | FAOSTAT FBS, `FBS_Group_Mapping.csv`, `faostat_country_mapping.csv`, hardcoded P&N values | `Food data/carbon_intensity{,_p10,_p90}.csv` |
| `code/compute_child_energy.R` | `$UN_WPP_DIR` male + female WPP workbooks | `Food data/child_energy_by_country.xlsx`, `data/child_energy_requirement_lookup.csv`, `data/child_energy_diagnostics.csv` |
| `data_visualization/deterministic_mortality.py` | `final_df_imputed.pkl` | `mortality model total emissions.csv` (person-years only), `data_result/deterministic_mortality_comparison.csv` |
| `data_visualization/survival_weighting.py` | `final_df_imputed.pkl` | `data_result/food_shock_survival_weight.csv` |
| `data_visualization/consumption_ghg.py` | `mortality model total emissions.csv`, `oecd/consumption_ghg_2025.csv`, `$UN_WPP_DIR` both-sexes workbook | `mortality model total emissions_oecd.csv`, `data_result/oecd_consumption_ghg_per_capita.csv` |
| `data_visualization/pipeline.py` | FAOSTAT FBS + CPI, elasticities, mappings, CI file, `child_energy_by_country.xlsx`, `full_simulation_results8.rds`, `..._oecd.csv`, `data_result/food_shock_survival_weight.csv` | *(library — no outputs)* |
| `data_visualization/breakeven_analysis.py` | pipeline + `..._oecd.csv` + drug footprint | `data_result/net_emissions_with_drug.csv` |
| `data_visualization/survivor_manuscript_numbers.py` | `final_df_imputed.pkl` | `data_result/survivor_manuscript_numbers.csv`, `..._top_countries.csv` |
| `data_visualization/generate_*_figure.py` | pipeline | `figures/*.png` (+ waterfall CSVs) |
| `diet_sensitivity/analysis.py` | pipeline, 3 diet scenarios | `data_result/diet_sensitivity_results.csv`, `..._ratio_comparison.csv`, 2 figures |
| `diet_sensitivity/combined_analysis.py` | pipeline, mean + P10 CI | `data_result/combined_sensitivity_results.csv`, `..._ratio_comparison.csv`, `carbon_intensity_meat_p10.csv` |
| `diet_sensitivity/sensitivity_overview.py` | pipeline, all 6 specifications | `data_result/all_sensitivity_overview_results.csv`, `..._country_ratios.csv`, 1 figure |
| `diet_sensitivity/sensitivity_suite.py` | pipeline, P10 / P90 / combined | `data_result/sensitivity_suite.csv` |
| `diet_sensitivity/tornado_analysis.py` | pipeline, meat P10/P90, decline rates | `data_result/sensitivity_tornado_results.csv`, 1 figure |
| `drug_effect/analysis.py` | pipeline, drug footprint | `data_result/drug_emissions_by_country.csv`, `drug_footprint_summary.csv` |
| `scripts/build_supplement_table.py` | pipeline, `full_simulation_results8.rds` | `data_result/supplement_results_table{,_raw}.csv` |

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

- Loads `final_df_imputed.pkl`, taking both the population and its imputed `mortality_rate` column from that one file — all 63 modelled countries
- Replaces the old stochastic Monte Carlo headline calculation with deterministic expected survival probabilities over 10 years
- Converts Human Life-Table `Mx` rates to annual death probabilities using `q = 1 - exp(-Mx)`
- Computes person-years saved under both uptake scenarios
- **Output:** `mortality model total emissions.csv`

`Mortality Model.ipynb` remains as the exploratory notebook for mortality data preparation and legacy diagnostics, but the deterministic script is the reproducible headline path.

For manuscript text that needs starting treated users (`Y`), average BMI-driven hazard-ratio reduction, and extra survivors alive at year 10 (`X`), run:

```bash
python -m data_visualization.survivor_manuscript_numbers
```

This helper uses the same deterministic mortality function and the same mortality lookup as the headline mortality output — both read `final_df_imputed.pkl`'s `mortality_rate` column. They must not diverge on that choice, or the manuscript numbers stop describing the headline output.

Current reconciled manuscript numbers:

- Maximum uptake: average HR reduction `18.6%`, starting treated users `252.6 million`, extra survivors alive at year 10 `3.15 million`, cumulative 10-year person-years saved `16.83 million`
- Moderate uptake: average HR reduction `18.4%`, starting treated users `132.2 million`, extra survivors alive at year 10 `1.66 million`, cumulative 10-year person-years saved `8.89 million`

These are on the imputed 63-country mortality source and cover all 63 countries.
Survival weighting the food shock does not touch them — it changes the food side
only.

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

**Imputation exposure.** Five of the countries the imputed mortality source
restored take their life table from a UN region whose only Human Life-Table member
is Israel. Of the seven carrying Israel's schedule bit-for-bit (ARE, BHR, CYP, KWT,
OMN, QAT, SAU), only **ARE, CYP and SAU** have an OECD per-capita factor and so
enter a ratio. Dropping the two Gulf states moves the cumulative 10-year ratio by
**−0.57%** (max uptake, 1.8474 → 1.8369) and the year-10 annual ratio by −0.51%,
leaving the binding country unchanged — so they are retained and the limitation
stated. `breakeven_analysis.py` prints this comparison on every run.

**Break-even analysis** — compares cumulative food-emission savings against cumulative emissions from additional survivors over a 10-year horizon. Pharmaceutical production emissions are folded into net food savings by default (`annual food savings - annual drug emissions`) before the comparison. Computes break-even year and 10-year food-to-survivor ratio for each country and uptake scenario.
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

Current headline result, with deterministic mortality on the imputed 63-country
mortality source, OECD consumption-based survivor emissions, survival-weighted
food savings, and pharmaceutical emissions folded in. For maximum uptake across
the **N = 40** countries with complete food and OECD survivor data, the global
10-year ratio is **1.85×** in the uniform baseline, **2.33×** when fatty foods
decrease more, and **1.25×** when cereals/sweets decrease more and meat decreases
less. In the cereals/sweets scenario **5 countries tip** into net positive
emissions, Hungary lowest at **0.86×**; the uniform baseline and fatty-foods
scenarios have none, Hungary closest at 1.21× and Lithuania at 1.41×.

### Step 7 — Combined Conservative Sensitivity Analysis

```bash
python -m diet_sensitivity.combined_analysis
```

Runs the reviewer-style stacked conservative case: the `cereal_sweets_up`
diet-composition scenario plus a low carbon-intensity assumption **across all
food groups** (`Food data/carbon_intensity_p10.csv`), scored against the matching
P10 survivor basis.

This definition superseded an earlier meat-only one, which kept every group at
the mean intensity and replaced only `Meat` with the P10 meat value.
`combined_analysis.assert_combined_conservative()` holds the three production
definitions in step. `data_result/carbon_intensity_meat_p10.csv` is the retired
meat-only derived file; it is still written but nothing production reads it.

Outputs:
- **Datasets:** `data_result/combined_sensitivity_results.csv`, `data_result/combined_sensitivity_ratio_comparison.csv`
- **Derived input:** `data_result/carbon_intensity_meat_p10.csv`
- **Figure:** `figures/combined_sensitivity_lowest_ratio_countries.png`

Current headline result: the stacked conservative case **does** tip. For maximum
uptake the global 10-year ratio falls from **1.25×** in the cereals/sweets
diet-shift scenario at mean carbon intensities to **0.69×** on all-food P10 —
below break-even — with **21 of 40** countries individually net positive and
Hungary lowest at **0.53×**. Moderate uptake behaves the same, at 0.67× with 21
tipping.

### Step 8 — All Sensitivities Overview

```bash
python -m diet_sensitivity.sensitivity_overview
```

Pharmaceutical emissions are folded into baseline net food savings through
``compute_breakeven(..., include_drug=True)``.

Outputs:
- **Datasets:** `data_result/all_sensitivity_overview_results.csv`, `data_result/all_sensitivity_overview_country_ratios.csv`
- **Figure:** `figures/all_sensitivity_overview.png`

Current headline result: for maximum uptake over **N = 40** countries, the global
10-year net-food-savings-to-survivor ratio ranges from **0.69×** in the combined
conservative case (cereals/sweets + all-food P10) up to **2.57×** under all-food
P90. The baseline is **1.85×**. Two specifications fall below break-even
globally — combined conservative at 0.69×, and all-food P10 marginally above at
**1.05×** with 9 countries individually tipping. The lowest country-level margin
is Hungary at **0.53×** in the combined conservative case.

### Step 9 — Drug Carbon Footprint Accounting

```bash
python -m drug_effect.analysis
```

Adds emissions from producing/administering semaglutide treatment itself to the net climate accounting. The implementation follows the professor-specified assumption using the Novo Nordisk Ozempic FlexTouch product-carbon-footprint document, Appendix A Table 2, US market. Ozempic 1.0 mg has annual components of 1.2 kg CO2e for API, 2.1 kg CO2e for device/cartridge, and 0.4 kg CO2e for needle. The API component is scaled to the modeled 2.4 mg dose while device and needle are held constant:

```text
annual drug footprint = 1.2 * 2.4 + 2.1 + 0.4 = 5.38 kg CO2e/user-year
```

The script calculates one-year drug emissions for comparison with annual food
savings, and a 10-year treated-user total for net accounting. Treated-user-years
are `initial_treated_users x sum_y pi_dose(y)`, **not**
`initial_treated_users * 10`: dead patients are not dosed. `pi_dose` is the
headcount-weighted mean treatment-world survival from
`data_result/food_shock_survival_weight.csv` — deliberately a different weight
from the `pi` that scales the food shock, which weights each patient by how much
their intake fell. Over ten years the sum comes to 9.63 rather than 10, so the
10-year drug total is about 3.7% lower than the old approximation.

Outputs:
- **Datasets:** `data_result/drug_emissions_by_country.csv`, `data_result/net_emissions_with_drug.csv`, `data_result/drug_footprint_summary.csv`
- **Figure:** `figures/drug_footprint_summary.png`

Current headline result: pharmaceutical emissions are folded into the baseline
break-even comparison as a subtraction from food savings. Under maximum uptake
this lowers the 10-year ratio from **1.893×** (gross food / survivor) to
**1.847×** ((food − drug) / survivor); under moderate uptake, from 1.832× to
1.787×. No complete-data country tips into net positive emissions in the
baseline specification.

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

## External data: three buckets

Every input falls into exactly one of three categories. Only the first is in the
repository.

### 1. Committed — in the repository, nothing to download

Hand-built inputs with no external source, plus generated files a clean clone
cannot rebuild. All are tracked; the small text ones are stored as ordinary git
blobs rather than LFS pointers so they survive a clone made without LFS.

| File | Why committed |
|---|---|
| `Food data/FBS_Group_Mapping.csv` | hand-built: 115 FAOSTAT items → 9 food groups |
| `Food data/faostat_country_mapping.csv` | hand-built: FAOSTAT area names → ISO3 |
| `Food data/elasticity_supply.csv` | transcribed from Hegwood et al. (2023) |
| `Food data/elasticity_demand.csv` | transcribed from Hegwood et al. (2023) |
| `Food data/carbon_intensity{,_p10,_p90}.csv` | generated; regenerate bit-for-bit with `build_carbon_intensity.py` |
| `Food data/child_energy_by_country.xlsx` | generated; needs UN WPP, so not rebuildable from a clean clone |
| `data/child_energy_requirement_lookup.csv` | FAO/WHO/UNU table hardcoded in the R script |
| `mortality model total emissions.csv` | mortality-model person-years (LFS) |
| `mortality model total emissions_oecd.csv` | generated; needs UN WPP, so not rebuildable from a clean clone |
| `data_result/food_shock_survival_weight.csv` | generated from `final_df_imputed.pkl`; the survival weights the food side reads |
| `full_simulation_results8.rds`, `final_df_imputed.pkl` | upstream simulation output (LFS) |
| `mortality2.rds` | raw 41-country HLD extract; provenance for the imputation, not read at runtime (LFS) |
| `oecd/consumption_ghg_2025.csv` | OECD extract (LFS) |

### 2. Documented download — public and redistributable, too large to ship

| Dataset | Version / filters | Consumed by | Where to put it |
|---|---|---|---|
| FAOSTAT Food Balance Sheets (Normalized), all data | 2022 reference year; `Element == "Food"` for quantities and `"Food supply (kcal/capita/day)"` for diet shares. ~582 MB. Accessed 2025-07. | `pipeline.py`, `build_carbon_intensity.py` | `Food data/FoodBalanceSheets_E_All_Data_(Normalized)/` |
| FAOSTAT Consumer Price Indices (Normalized), all data | December 2022; `Item == "Consumer Prices, Food Indices (2015 = 100)"`. ~35 MB. Accessed 2025-07. | `pipeline.py` | `Food data/ConsumerPriceIndices_E_All_Data_(Normalized)/` |
| UN World Population Prospects 2024, population by single age and sex | `WPP2024_POP_F01_1_..._BOTH_SEXES.xlsx`, `..._F01_2_..._MALE.xlsx`, `..._F01_3_..._FEMALE.xlsx`; 2022 reference year. Accessed 2025-07. | `consumption_ghg.py` (both-sexes), `code/compute_child_energy.R` (male + female) | **anywhere** — point `UN_WPP_DIR` at it |

Download FAOSTAT bulk files from <https://www.fao.org/faostat/en/#data> ("Bulk
downloads", All Data Normalized) and UN WPP from
<https://population.un.org/wpp/downloads>.

Two different patterns here, deliberately:

- **FAOSTAT goes into `Food data/`.** These are dated, immutable bulk releases,
  so provisioning one is a one-time act.
- **UN WPP is read in place via `UN_WPP_DIR`.** These workbooks are also used
  outside this repository, so copying one in would create a second version free
  to drift from the original without anything noticing. Both scripts read the
  same environment variable and fail with the exact filename if it is unset.

```bash
export UN_WPP_DIR="/path/to/your/UN WPP 2024"     # bash
$env:UN_WPP_DIR = "C:\path\to\UN WPP 2024"        # PowerShell
```

### 3. Link only — redistribution restricted, download from source

Check each provider's terms before redistributing any of these; none are
included here, and none is read at runtime by the Python analysis.

| Dataset | Source | Needed for |
|---|---|---|
| Poore & Nemecek (2018) supplementary data (`aaq0216_datas1/2.xls`) | <https://www.science.org/doi/10.1126/science.aaq0216> | Provenance for the GHG values transcribed into `GHG_SCENARIOS` in `build_carbon_intensity.py`. No script opens the file. |
| Human Life-Table Database, `Mx_1x1` | <https://www.lifetable.de/> | Upstream mortality tables. Extracted into `mortality2.rds` for the 41 countries HLD covers; the remaining 22 of the 63 modelled countries were imputed from those, and the imputed result is what `final_df_imputed.pkl` carries |
| NCD-RisC BMI and diabetes distributions | <https://ncdrisc.org/> | Upstream simulation inputs (already baked into `full_simulation_results8.rds`) |

## Required Datasets (detail)

### `full_simulation_results8.rds`
> **Location:** project root

Full synthetic population output from `Data_Cleaning9.8.R`. Contains ~945,000 simulated individuals with baseline/treated BMI, caloric intake, demographics, and population weights for ~200 countries. Required by both notebooks.

### `final_df_imputed.pkl`
> **Location:** project root

The modelled population *and its mortality rates*. This is the single input to
`deterministic_mortality.py` and `survivor_manuscript_numbers.py`: the
`mortality_rate` column is a complete, single-valued function of
`(ISO, age, Sex)` over 63 countries × ages 18–89 × 2 sexes — 9,072 cells, no
gaps, asserted at load.

Those rates are **imputed**, by cell 5 of `Mortality Model.ipynb`: regional
median stratified by age and sex, then the global median for that age–sex cohort,
then a `0 → 0.00001` floor. That is the procedure the manuscript methods
describe. Use the lowercase `age` column as the join key. The frame also carries
a capital `Age`, null on 42.86% of rows: it is the right-hand key left behind by
the notebook's merge against the 41-country HLD extract, so it is null on exactly
the countries that extract lacks, and joining on it silently drops them.

> **Reproducibility gap, stated plainly.** The pickle is committed, but the only
> script that regenerates it is `Mortality Model.ipynb`, which this repository
> marks superseded and does not run. So the imputation is consumed as a fixed
> artifact and cannot currently be rebuilt from source. This is a known state,
> recorded rather than fixed.

### `mortality2.rds`
> **Location:** project root

The **raw 41-country Human Life-Table extract**, written by `Mortality_model2.R`
after it drops territorial subdivisions and truncates ISO codes. 41 countries is
simply HLD's coverage.

It is an **input to the imputation, not a model input**, and no live script reads
it. It is retained for provenance: it is the record of which countries have real
measured mortality rather than imputed ones. Do not restore it as a lookup — a
model keyed on it silently zeroes the 22 modelled countries HLD lacks, which is
indistinguishable from immortality and was a live defect until the source swap.

`final_df_imputed.rds` — the older R-side vintage of the same imputation, built
on `full_simulation_results6` with a single scenario, a region+income tier and a
Seychelles special case — is superseded by the pickle and differs from it on 19
countries. Do not use it for anything.

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

### UN World Population Prospects 2024
> **Location:** anywhere — point `UN_WPP_DIR` at it. There is no `UN/` directory.

Population by single year of age and sex. Download from
[UN Population Division](https://population.un.org/wpp/downloads). Read in place
by `data_visualization/consumption_ghg.py` (both-sexes workbook) and
`code/compute_child_energy.R` (male + female workbooks), and also an input to
the upstream R simulation. See
[External data](#external-data-three-buckets) for the exact filenames.

### `recategorize/`
> **Location:** `recategorize/`

| File | Description |
|---|---|
| `aaq0216_datas2.xls` | Poore & Nemecek (2018) supplementary data — GHG emissions per kg of 43 food products ("Results - Retail Weight") and P&N food-and-waste supply volumes ("Results - Global Totals", column "Food and Waste ('000 t, 2009-11 avg.)"). The latter are the volumes entering the human food supply chain plus associated waste, not total production |
| `aaq0216_datas1.xls` | Poore & Nemecek (2018) supplementary data — farm-level observations |

Download from the [Science supplementary materials](https://www.science.org/doi/10.1126/science.aaq0216) for Poore & Nemecek (2018).

## Reproduction check

`reference/` holds two snapshots of the model's headline outputs:

| File | Contents |
|---|---|
| `reference_headline_numbers.csv` | baseline food emissions, annual food savings, cumulative and year-10 food:survivor ratios, minimum-country ratio and country — both uptake levels |
| `reference_sensitivity_suite.csv` | the P10 / P90 / combined-conservative suite: cumulative and year-10 ratios, minimum-country ratio, tipping counts — both uptake levels |

Together they pin 47 numbers.

### Running it

```bash
python -m reference.metrics        # from the repository root
```

Needs the FAOSTAT bulk downloads in `Food data/` and the committed inputs; it
does **not** need `UN_WPP_DIR`, since it reads the committed
`mortality model total emissions_oecd.csv` rather than rebuilding it. Runs the
pipeline for the four configurations the references cover — no-diet baseline on
mean carbon intensity, the P10 and P90 bounds, and the combined-conservative
case — and takes about two minutes. Exit status is 0 on pass, 1 on failure.

**These files are a snapshot of what the current code produces. They are not a
claim about final results.** They exist to answer one question: *did anything
move?* A refactor, a dependency upgrade, or a change intended to be purely
structural should reproduce them exactly, and if it does not, something changed
that the author did not intend.

**A deliberate methodological change is expected to fail this check.** Switching
to a different carbon-intensity source, revising the demand-shock denominator, or
changing an elasticity assumption *should* move these numbers — that is the
change working. The correct response is not to loosen the comparison but to
regenerate the reference files in their own visible commit, whose message records
which numbers moved, by how much, and why. The reference files then describe the
new state.

So read a failure as **"something moved"**, not "something is broken". The
distinction matters: the check has no opinion about which numbers are right, only
about whether they are the same as last time.

### Current status — the references pass

`python -m reference.metrics` passes on this branch, at **exactly 0.0** on all 47
values. The snapshots were refreshed once, after the survival-weighting change,
covering the four changes that had accumulated since they were last taken:

| Commit | Change |
|---|---|
| `6e826a4` | Fix aggregate double-count in `load_kcal_shares`' calorie-share weights |
| `be44eb4` | Weight the oilcrops composite by P&N food-and-waste supply volumes |
| `5aa62ed` | Take mortality rates from the pickle's imputed column, restoring 27 zeroed countries |
| *(this commit)* | Survival-weight the food-side demand shock by `pi(t)` |

Refreshing them was deferred until all four had landed rather than done four
times; see `CHANGES.md` for what each moved.

`--write` regenerates both snapshots from a fresh pipeline run:

```bash
python -m reference.metrics --write     # regenerate, then verify
python -m reference.metrics             # verify only
```

Before that flag existed the snapshots had to be hand-edited, which is how a
stale configuration survived inside `metrics.py` unnoticed — its
`combined_conservative` row still named the retired meat-only carbon-intensity
file, and all four configurations were scored against a single mean-basis survivor
frame after the survivor path became CI-aware. Both are reconciled: each
configuration now pairs with the survivor file for its own carbon-intensity
scenario, via the `ci_scenario` recorded on the snapshot.

`ACTIVE_RUN` at the top of `metrics.py` names which `run` row of
`reference_headline_numbers.csv` is the live target. Earlier rows
(`committed_legacy`, `corrected_fix3`) are kept for provenance and are not
compared against.

### Tolerance

The check passes when every value agrees to a **relative difference of 1e-12 or
better**, not bit-for-bit. Two things put an irreducible floor near the 16th
significant figure: a reference stored as decimal text need not reload to the
identical double (`6510.9065615889995` does not), and aggregate sums shift
slightly between pandas and numpy versions. Requiring exact equality would make
the check fail on a different machine for reasons that have nothing to do with
the model.

That costs no sensitivity. Observed agreement is around `1e-16` relative —
roughly four orders of magnitude inside the tolerance — whereas any genuine
change to the model moves these numbers by *many* orders of magnitude more. The
smallest real correction made during this work shifted the headline figure by
about 0.1%, or `1e-3` relative. Nothing meaningful can hide under `1e-12`. ISO
codes and integer counts are compared exactly, with no tolerance at all.

The check prints the worst absolute and worst relative difference on every run,
so how close it actually came is always visible rather than reduced to
pass/fail.

### The frozen consolidation proof

A second, one-time check proved that merging the two former pipelines into one
`compute_food_savings()` changed nothing: it compared the merged function's full
output — every column and row of `food_savings` and `result_df`, across all seven
diet × carbon-intensity configurations — against a snapshot of the two original
functions taken beforehand, and required exactly `0.0`.

That question is settled, and the snapshot cannot be regenerated because the
function it captured no longer exists. So `compare_merged.py` and
`ref_snapshot.pkl` live on the **`seth_bug_fixes` audit branch**, under
`outputs/fix3/`, rather than here. They are archived there, not runnable there:
the merged function they test exists only on this branch.

## Known gaps and warts

Recorded deliberately. None of these affects a published number unless stated.

**The simulation has no committed build script.** `full_simulation_results8.rds`
is the input to every food-emissions figure, and the script that produced it
(`Data_Cleaning9.8.R`) is archived in `legacy/R_scripts/` but is not wired to run
against data in this repository. Its NCD-RisC and UN WPP inputs are not present.
So the simulation is **not reproducible from a clean clone** — it is consumed as
a fixed, committed artifact. Anyone re-deriving the population from source data
must reconstruct that step independently.

**`data_result/oecd_vs_worldbank_survivor_emissions.csv` is not reproducible.**
It compares OECD demand-based factors against the older World Bank territorial
ones, and the World Bank baseline file it needs
(`mortality model total emissions_worldbank_backup.csv`) no longer exists in the
repository or in any working copy. `consumption_ghg.py` now skips writing that
table rather than silently regenerating it from OECD data against itself, which
would report a uniform 0% change. The committed table is the record.

**The mortality imputation is not reproducible from a clean clone.**
`final_df_imputed.pkl` carries the `mortality_rate` column the whole survivor
side is built on, and the only script that regenerates it is cell 5 of
`Mortality Model.ipynb` — which this repository marks superseded and does not
run. So the imputation is consumed as a fixed, committed artifact, exactly as the
simulation above is. Anyone re-deriving mortality from source must redo the
regional-median → global-median → 1e-5-floor step independently, against the
41-country `mortality2.rds` extract.

**A 1–2 ULP float artifact in the mortality person-years file.** Running
`deterministic_mortality.py` reproduces the committed
`mortality model total emissions.csv` in 1381 of 1512 cells exactly; 131 cells
differ by 1–2 units in the last place, worst relative difference `3.685e-16`.
Every input column is bit-identical, so the committed artifact was written by a
different library generation. Measured by running the pre- and post-change
functions in one process: both differ from the committed blob *identically*, which
is what establishes that the gap belongs to the blob and not to any code change.
Any bit-for-bit gate on this file must therefore be anchored to what the code
produces, not to the committed text, or it inherits a ULP floor that has nothing
to do with the model. This is the 16th significant figure and cannot reach a
published number.

The same artifact was previously recorded here as "2–3 ULP, 8 of 4536 cells",
measured when the file still carried 22 emissions columns and was compared
against `..._oecd.csv`. The figures above supersede it: the file is person-years
only now, so the comparison is 126 × 12.

**Dependency direction is inverted between two packages.**
`data_visualization/pipeline.py` imports `SCENARIOS` from
`diet_sensitivity/scenarios.py`, so the lower-level package depends on the
higher-level one. It is harmless — `scenarios.py` is pure data with no project
imports, so there is no cycle — but the natural fix is to move the scenario
definitions alongside the pipeline. Left alone deliberately: moving files
silently breaks paths, and the arrangement works.

**Two sensitivity scripts overlap.** `sensitivity_overview.py` and
`sensitivity_suite.py` both run the P10, P90 and combined-conservative
specifications. Neither subsumes the other: the overview covers all six
specifications but only max uptake and no year-10 annual ratio, while the suite
covers both uptake levels and the year-10 ratio for three specifications. They
agree exactly where they overlap. Consolidating them would mean regenerating
published numbers from new code, so they are left as they are.

**`population_weighted` is a units switch, not a correctness flag.** Only the
`True` path is valid for anything feeding the food:survivor ratio; see the
docstring in `data_visualization/deterministic_mortality.py`.

**`mortality model total emissions.csv` is person-years only.** It holds
`ISO`, `scenario`, `diff_Y0`–`diff_Y10` and `total_person_years_saved`, and
nothing else. Emissions are computed downstream: `consumption_ghg.py` reads the
`diff_Y*` columns, attaches OECD factors, and writes
`mortality model total emissions_oecd.csv`, which is the file every analysis
script reads. The person-years file previously carried 22 emissions columns as
well; they were confirmed byte-for-byte duplicates of the OECD output — matching
the OECD factors in all 84 recorded country-scenarios exactly and the World Bank
factors in none — and were removed.

**`Mortality Model.ipynb` still writes the wide schema.** It is an alternative
producer of `mortality model total emissions.csv` and emits all 22 emissions
columns, so **re-running it would restore the removed columns**. It is not in
the current execution path — `deterministic_mortality.py` is the maintained
producer — and it could not be updated here because it cannot be run in this
checkout: `HLD/`, `Lancet/` and the UN WPP inputs it needs are all absent, and
executing a notebook blind would be worse than leaving it. Anyone regenerating
mortality from the notebook must slim its output to the four column groups above
before the downstream scripts will behave as documented.

Note the awkward consequence: the same notebook is the **only** producer of the
`mortality_rate` imputation in `final_df_imputed.pkl` that the survivor side now
depends on. It is simultaneously superseded as an output producer and
load-bearing as an input producer. Both facts are true and neither is fixed here.

## Legacy Code

The original R-based pipeline (simulation, analysis, and mortality scripts) has been archived in `legacy/`. See `legacy/docs/legacy_README.md` for the original documentation. The `.rds` outputs from those scripts are still required as inputs to the Python notebooks.

Legacy R scripts and documentation are tracked via regular Git. Large binary data files (`.rds`, `.pkl`) are tracked via **Git LFS**.

### Git LFS

This repository uses [Git Large File Storage](https://git-lfs.com/) for binary data files. LFS-tracked patterns (defined in `.gitattributes`):

- `*.rds` — R data files (`full_simulation_results8.rds`, `mortality2.rds`, `legacy/data/*.rds`)
- `*.pkl` — Python pickle files (`final_df_imputed.pkl`)
- `*.csv` — generated and cached tabular outputs tracked in Git, including diet sensitivity result tables and OECD validation/comparison tables

**Exceptions stored as ordinary git blobs**, not LFS. These are small text files
that the analysis cannot run without, so they must survive a clone made without
LFS configured. `.gitattributes` unsets the LFS filter for:

- the four hand-built inputs (`FBS_Group_Mapping.csv`,
  `faostat_country_mapping.csv`, `elasticity_supply.csv`,
  `elasticity_demand.csv`)
- `child_energy_requirement_lookup.csv`
- `mortality model total emissions_oecd.csv`

Note that `.gitattributes` patterns containing spaces must be double-quoted, or
git reads only the first word as the pattern.

`build_carbon_intensity.py` guards against the related failure: on a clone where
LFS was never initialised, the tracked carbon-intensity CSVs materialise as
~130-byte pointer stubs, which pandas would parse into a garbage one-column
frame. `_assert_not_lfs_pointer()` raises a clear error instead.

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
