# HANDOFF

This file is for a fresh agent after context refresh. It summarizes the project, recent work, key decisions, validation results, and likely next steps.

## Project Goal

This repository analyzes the population-level impact of broad semaglutide adoption on:

- Food demand and food-system greenhouse gas emissions
- Mortality/person-years saved
- Net climate impact after accounting for emissions from additional survivor person-years

The main comparison is food-emission savings versus survivor emissions over a 10-year horizon, under maximum uptake and moderate uptake scenarios.

## Core Pipeline

Main execution/data flow:

1. `Data_Cleaning9.8.R` / archived R code generates synthetic population outputs.
2. `Mortality Model.ipynb` / mortality pipeline estimates additional survivor person-years.
3. `data_visualization/consumption_ghg.py` rebuilds survivor emissions using OECD consumption-based GHG factors.
4. `data_visualization/pipeline.py` computes baseline food-emission savings using the price rebound model.
5. `data_visualization/breakeven_analysis.py` computes food-to-survivor ratios and break-even summaries.
6. `data_visualization/generate_dashboard_figure.py` creates paper-style dashboard figures.
7. `diet_sensitivity/analysis.py` runs the diet-composition sensitivity analysis.

## Important Recent Methodology Change: OECD GHG Replacement

The professor requested replacing the old World Bank survivor-emissions source because it was not ideal for comparison with food emissions:

- Food emissions use Poore & Nemecek CO2e, including methane and nitrous oxide.
- The old survivor-emissions source was closer to territorial/production-based CO2 accounting.
- The new method uses OECD demand-based final-consumption GHG, including direct household emissions and excluding gross capital formation.

Implemented in:

- `data_visualization/consumption_ghg.py`
- Input file: `oecd/consumption_ghg_2025.csv`
- Main output overwritten/preserved schema: `mortality model total emissions.csv`
- Comparison outputs:
  - `data_result/oecd_consumption_ghg_per_capita.csv`
  - `data_result/oecd_vs_worldbank_survivor_emissions.csv`

### OECD Filtering

The script filters the OECD file to:

- `FINAL_DEMAND_CATEGORY == "CONS"`
- `ACTIVITY == "_T"`
- `TIME_PERIOD == 2022`
- `UNIT_MEASURE == "T_CO2E"`
- `UNIT_MULT == 6`

This corresponds to 2022 final-consumption GHG totals in Mt CO2e.

### Per-Capita Factor

OECD per-capita factor is calculated as:

`OECD final-consumption GHG in Mt CO2e * 1,000,000 / UN WPP 2022 population`

This gives tonnes CO2e/person.

Validation:

- USA OECD filtered 2022 total = `5892.9 Mt CO2e`
- USA per-capita factor = about `17.25 t CO2e/person`
- This matches the professor's expected check of about 17 tonnes/person.

### Key Result Impact

The mortality/person-year estimates did not change. Only the emissions factor applied to those person-years changed.

Observed impact:

- USA max-uptake 10-year survivor emissions changed from about `104 Mt CO2e` to about `139 Mt CO2e`.
- Across countries with both old and new factors, OECD factors are higher by about 36% at the median.
- The baseline max-uptake food-to-survivor-emissions ratio is now about `5.3x` among complete-data countries.
- All complete-data countries still break even in Year 1.
- The conclusion weakens but does not reverse.

### OECD Coverage Caveat

OECD coverage is narrower than the old source. Missing OECD ISO codes observed:

`AND, ASM, ATG, BHR, BHS, BMU, BRB, GRL, GUY, KNA, KWT, NRU, OMN, PAN, PRI, PYF, QAT, SYC, TTO, URY`

Handling:

- Missing OECD survivor-emissions factors remain missing.
- `breakeven_analysis.py` was updated so missing survivor-emissions data become `NaN` ratios, not infinite ratios.
- Ratio summaries exclude incomplete rows.

## Diet-Composition Sensitivity Analysis

The professor requested sensitivity analyses because semaglutide may change food preference, not just total volume.

Implemented as a separate package:

- `diet_sensitivity/__init__.py`
- `diet_sensitivity/scenarios.py`
- `diet_sensitivity/pipeline.py`
- `diet_sensitivity/analysis.py`

### Scenarios

Defined in `diet_sensitivity/scenarios.py`:

1. `baseline_uniform`
   - Original model.
   - Every food group receives the same country/scenario-specific EER demand shock.

2. `fatty_food_down`
   - Meat, Dairy, Fats and oils receive multiplier `1.5`.
   - Motivated by Blundell et al. (2017) and Gibbons et al. (2021).

3. `cereal_sweets_up`
   - Cereals and Sweets receive multiplier `1.5`.
   - Meat receives multiplier `0.5`.
   - Motivated by Hironaka et al. (2025).

### Calibration Logic

Important: the diet sensitivity does not change total calorie reduction or mortality.

It redistributes the same country/scenario-specific total calorie reduction across food groups. It uses FAOSTAT kcal shares and calibrates neutral food-group multipliers so the calorie-weighted average multiplier equals 1.

This means:

- Total EER-based calorie reduction stays fixed.
- BMI/mortality/person-years saved stay fixed.
- Food-emission savings change because different food groups have different carbon intensities.

### Diet Sensitivity Results After OECD Update

Under maximum uptake, among valid complete-data countries:

- Uniform baseline: about `5.3x`
- Fatty foods decrease more: about `6.7x`
- Cereals/sweets decrease more while meat decreases less: about `3.5x`

No valid country tips into net positive emissions under any diet scenario.

Closest countries under conservative cereal/sweets scenario are around `2.4x` (Poland/Lithuania).

## Food-Side Model Status

The OECD update did not change the food-emissions side.

Unchanged:

- FAOSTAT food quantity inputs
- Poore & Nemecek carbon intensity inputs
- `CI_{c,g}` country-food-group carbon intensity calculation
- Hegwood-style price rebound/equilibrium model
- Baseline food-savings numerator

Main file:

- `data_visualization/pipeline.py`

## Generated/Updated Outputs

Important files generated or updated during recent work:

- `mortality model total emissions.csv`
- `data_result/oecd_consumption_ghg_per_capita.csv`
- `data_result/oecd_vs_worldbank_survivor_emissions.csv`
- `data_result/diet_sensitivity_results.csv`
- `data_result/diet_sensitivity_ratio_comparison.csv`
- `figures/breakeven_by_country.png`
- `figures/breakeven_curves.png`
- `figures/country_dashboard.png`
- `figures/food_group_breakdown.png`
- `figures/diet_sensitivity_global_comparison.png`
- `figures/diet_sensitivity_lowest_ratio_countries.png`
- `oecd_methodology_changes_summary.docx`

There was also an earlier `professor_oecd_methodology_update.docx` on the Desktop, but the user removed it and asked for a paragraph-only version in the repo. The current repo document is:

- `oecd_methodology_changes_summary.docx`

## Documentation Updates

`README.md` was updated to describe:

- OECD consumption-based GHG survivor-emissions rebuild
- `data_visualization/consumption_ghg.py`
- `oecd/consumption_ghg_2025.csv`
- Updated diet sensitivity results after OECD replacement
- OECD as active survivor-emissions source and World Bank as legacy/comparison source

`.gitignore` was updated to unignore:

- `oecd/consumption_ghg_2025.csv`
- `data_result/oecd_consumption_ghg_per_capita.csv`
- `data_result/oecd_vs_worldbank_survivor_emissions.csv`

`.gitattributes` already tracks `*.csv` via Git LFS.

## Important Commands Already Run

OECD rebuild:

```bash
.\venv\Scripts\python.exe -m data_visualization.consumption_ghg
```

Downstream reruns:

```bash
.\venv\Scripts\python.exe -m data_visualization.breakeven_analysis
.\venv\Scripts\python.exe -m data_visualization.generate_dashboard_figure
.\venv\Scripts\python.exe -m diet_sensitivity.analysis
```

These completed successfully after missing-data handling was fixed.

Linter checks for edited Python files reported no linter errors.

## User Communication Preferences / Current Context

The user has been preparing an update for the professor and wants concise but technically accurate explanation.

Key phrasing to preserve:

- This is a methodology improvement, not a change to the mortality simulation itself.
- Mortality/person-years saved are unchanged.
- Food-side carbon intensity and rebound model are unchanged.
- The survivor-emissions factor changed from World Bank territorial/production-based emissions to OECD demand-based final-consumption GHG in CO2e.
- The conclusion is more conservative but unchanged: food savings still exceed survivor emissions for complete-data countries.
- Diet sensitivity formulas are new and separate from the OECD update; they explain how total calorie reduction is preserved while diet composition changes.

Avoid saying "we made a mistake." Better phrasing:

- "We identified a data-source mismatch and updated the survivor-emissions methodology."
- "The OECD source better aligns survivor emissions with the CO2e accounting used for food emissions."

## Likely Next Steps

1. Review `oecd_methodology_changes_summary.docx` for wording and formatting.
2. If requested, draft a final email to the professor summarizing:
   - OECD replacement
   - validation
   - observed result changes
   - diet sensitivity result changes
   - caveat about OECD coverage
3. Consider whether to commit changes. Do not commit unless the user explicitly asks.
4. If committing, check LFS state first and ensure no large unintended files are included.
5. If professor asks about missing OECD countries, explain that no imputation was done and ratio summaries use complete data only.

## Current Safety Notes

- Do not revert user changes.
- The repo may include generated outputs and data files tracked via LFS.
- Do not run destructive git commands.
- Do not commit unless explicitly requested.
