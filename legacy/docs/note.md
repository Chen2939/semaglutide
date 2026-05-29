# Semaglutide Project Notes

Purpose: ongoing progress log for this part-time project.  
Use this file to track what was done, what is next, and blockers by date.

---

## Weekly Executive Summary: Apr 20–26, 2026

**Days worked:** 3 (Mon 4/20, Tue 4/21, Wed 4/23)

### Accomplishments

1. **Project Setup & Onboarding (4/20)**
   - Initialized version control with `.gitignore` for data/result assets
   - Documented project goals, codebase structure, and uptake scenarios
   - Fixed hardcoded file paths in all three main R scripts for portability

2. **Documentation & Initial Debugging (4/21)**
   - Created comprehensive documentation for `Mortality_model2.R`
   - Attempted mortality model run; identified out-of-memory (OOM) issue during validation stage (~3.4 GB allocation failure)
   - Added memory management code (`memory.limit`, `gc()` cleanup)

3. **Memory Optimization & Successful Run (4/23)**
   - Refactored validation logic to use lightweight lookups instead of full-table joins
   - Achieved end-to-end successful run of `Mortality_model2.R`
   - Set up Git branch (`test/memory-optimization`) and pushed changes

### Current Status

- Core simulation pipeline (`Data_Cleaning9.8.R`) runs successfully
- Mortality model (`Mortality_model2.R`) now completes without OOM
- Output shows expected survival differences (baseline 76.4% vs semaglutide 77.6% at Year 10)

### Open Issues

- Global summary shows NA for `lives_saved` metrics (likely join/scaling mismatch)
- `total_population` appears inflated (~200B vs expected ~1-2B)

### Next Steps

- Debug NA values in lives_saved calculation
- Verify population scaling join logic
- Validate scenario consistency in analysis scripts

---

## Project Goal

Model the population-wide impact of semaglutide adoption in high-income countries, including:
- Caloric demand reduction
- Mortality and person-years saved
- Emissions implications (food demand reduction vs longevity rebound)
- Economic rebound effects

Core eligibility assumption in simulation:
- BMI >= 30, or BMI >= 27 with Type 2 diabetes
- Age < 75

Uptake scenarios:
- Maximum uptake: 95% of eligible individuals remain/adhered in model
- Moderate uptake: 50% of eligible individuals remain/adhered in model

Important: uptake is applied to the eligible subgroup, not the whole population.

---

## Current Repository Status (as of 2026-04-20)

Main scripts:
- `Data_Cleaning9.8.R` (current simulation pipeline)
- `Semaglutide_Analysis_8.R` (analysis/figures for v9.8 output)
- `Mortality_model2.R` (mortality and life-years model)

Legacy scripts retained:
- `Data_Cleaning9.7.R`
- `Semaglutide_Analysis_7.R`

Data/result assets are intentionally ignored in git:
- `HLD/`, `Lancet/`, `UN/`
- `full_simulation_results7.rds`, `full_simulation_results8.rds`
- `Methodology document.docx`
- `Worldbank_incomes_cleaned.xlsx`

---

## Implementation Snapshot

### 1) Simulation pipeline (`Data_Cleaning9.8.R`)
- Loads BMI, height, diabetes, and population inputs
- Filters high-income countries
- Builds BMI mixture distributions
- Simulates synthetic individuals per country x sex x age group
- Computes baseline BMI/weight/BMR/EER
- Applies treatment scenario logic with adherence draw
- Saves output to `full_simulation_results8.rds`

### 2) Analysis pipeline (`Semaglutide_Analysis_8.R`)
- Loads simulation output
- Generates summary checks and visualization plots
- Produces country-level EER and weight-difference summaries

### 3) Mortality model (`Mortality_model2.R`)
- Reads mortality tables
- Imputes missing mortality rates using regional/income hierarchy
- Applies BMI hazard ratios
- Runs 10-year baseline vs treatment survival simulation
- Estimates person-years effects and related downstream calculations

---

## Working Notes / Risks

- `Semaglutide_Analysis_8.R` comments indicate partial updates around dual-scenario handling; verify all outputs are scenario-aware.
- Legacy scripts (`Data_Cleaning9.7.R`, `Semaglutide_Analysis_7.R`) still have old hardcoded paths (not fixed).

---

## Missing Files

None currently. All required data files are present.

---

## Daily Log

### 2026-04-20
- Focus: Project onboarding and cleanup
- Actions completed:
  - Created `.gitignore` to ignore data/result assets (`HLD/`, `Lancet/`, `UN/`, `.rds` files, `.docx`, `.xlsx`)
  - Created `note.md` for progress tracking (also gitignored)
  - Investigated repository structure, documented project goal, status, and code implementation
  - Clarified uptake scenarios (95% max, 50% moderate) — these are adherence rates among eligible individuals only
  - Fixed hardcoded paths in main scripts:
    - `Data_Cleaning9.8.R`: 8 path replacements, removed `setwd()` calls
    - `Semaglutide_Analysis_8.R`: removed `setwd()`, kept relative `.rds` path
    - `Mortality_model2.R`: 4 path replacements, updated to load `full_simulation_results8.rds` (was pointing to old v6)
- Decisions made:
  - Use relative paths so scripts run from project root
  - Did not fix legacy v9.7 scripts (lower priority)
- Issues/blockers:
  - (resolved) Missing UN population file — downloaded and added
- Next tasks:
  - Validate scenario labels in analysis scripts
  - Test full pipeline run

### 2026-04-21
- Focus: Documentation update and initial mortality run/debug
- Actions completed:
  - Updated `Mortality_Model_Documentation.md` with detailed methodology section:
    - Added 3-level imputation hierarchy (Primary: UN Region Median, Secondary: Global Median, Floor Constraint)
    - Documented hazard ratio normalization approach
    - Added 10-year simulation time horizon rationale
    - Documented age 75+ benefit reduction (50%) for participants aging beyond prescription cutoff
    - Added person-years saved calculation explanation (differs from lives saved)
    - Added CO2 emissions calculation methodology
  - Modified `Mortality_model2.R`:
    - Changed input/output paths to `test/` folder (original paths kept as comments)
    - Added `memory.limit(size = 32000)` at script start (Windows only) — did not resolve OOM
    - Added initial `rm()` + `gc()` cleanup around imputation/simulation sections
    - Fixed `percent_format()` error via `scales::percent_format`
  - Ran `Mortality_model2.R` multiple times and confirmed recurring OOM around validation joins (`cannot allocate vector of size 3.4 Gb`)
- Decisions made:
  - Keep original code paths commented (do not delete) when switching to `test/` paths
  - Keep validation logic but refactor execution approach due to memory constraints
- Issues/blockers:
  - OOM during validation stage prevented complete run with full checks enabled
- Next tasks:
  - Implement memory-safe validation approach (batched/lightweight joins)
  - Create isolated branch for testing and push fixes safely
  - Re-run full mortality script and review summary outputs

### 2026-04-23
- Focus: Memory-safe validation refactor, successful run, and git cleanup
- Actions completed:
  - Refactored validation in `Mortality_model2.R` to avoid OOM:
    - Replaced full-table `left_join` validation with small missing-key lookup (`ISO`, `age`, `Sex`)
    - Reworked Seychelles comparison to filtered subsets + aggregated medians
    - Re-enabled combination checks using `final_df_imputed` + `distinct()` (no `final_df` dependency after cleanup)
    - Fixed dplyr summarise error in Seychelles validation (`mortality = mortality_rate` -> `median(mortality_rate)`)
  - Ran `Mortality_model2.R` end-to-end successfully:
    - Imputation + validation + simulation completed without OOM
    - Survival output produced (Year 1: 97.3% baseline vs 97.5% semaglutide; Year 10: 76.4% vs 77.6%)
  - Git workflow:
    - Created and worked on branch `test/memory-optimization`
    - Added `.RData`, `.RDataTmp`, `.Rhistory` to `.gitignore`
    - Resolved push rejection caused by large `.RData` history and pushed branch successfully
- Decisions made:
  - Keep original heavy validation snippets as comments for traceability
  - Continue using `test/` paths for development runs
- Issues/blockers:
  - Script completes but global summary still shows NA for `lives_saved` metrics
  - `total_population` appears inflated (~200 billion vs expected 1-2 billion)
  - Likely cause: join mismatch or `Population.y` naming/scaling join inconsistency
- Next tasks:
  - Debug NA values in lives_saved calculation
  - Check `scaled_mortality$scaling_factor` for NAs
  - Verify population data join logic (`Population.y` and scaling join consistency)

### 2026-05-07
- Focus: Integrate `latest/` codebase, set up Python environment, run new Jupyter notebooks, fix pandas 3.0 / kernel-state errors
- Actions completed:
  - Codebase integration (merged `latest/` into project root):
    - Compared all same-name R files; kept root versions (already had path fixes / memory optimizations); discarded older `latest/` copies of `Data_Cleaning9.8.R`, `Semaglutide_Analysis_8.R`, `Mortality_model2.R`
    - Moved new assets to root: `Mortality Model.ipynb`, `Price rebound model.ipynb`, `Food data/`, `API_EN.GHG.CO2.PC.CE.AR5_DS2_en_excel_v2_3736.xls`, `mortality model total emissions.csv`, `mortality2.rds`, `final_df_imputed.rds`, `UN/API_EN.ATM.CO2E.PC_DS57_en_csv_v2_568353.csv`
    - Replaced `Worldbank_incomes_cleaned.xlsx` with newer 50KB version (verified schema: `ISO`, `2022` column intact)
    - Saved old methodology doc as `Methodology document_latest.docx` for manual diff
    - Verified identical files via MD5: `full_simulation_results7.rds`, `full_simulation_results8.rds`, all `HLD/Mx_1x1/*` and `Lancet/*` matched root
    - Merged `Mortality_model2.R` logic: added `saveRDS(mortality2, ...)` and `saveRDS(population_with_iso, ...)` block to `test/` so notebooks can consume R outputs
    - Updated `.gitignore`: added `/Food data/`, `/latest/`, `*.pdf`, `Methodology document_latest.docx`
  - R pipeline integrity verification:
    - Wrote temporary verification script confirming all 9 input files load and Worldbank schema is correct
    - All HLD (50 files), UN (3 files), Lancet (4 files) load cleanly
  - Python environment setup:
    - Created `venv` with Python 3.12 (rejected 3.14 — too new for `pyreadr`/`country_converter` wheels)
    - Installed packages: `pandas`, `numpy`, `scipy`, `matplotlib`, `seaborn`, `pyreadr`, `country_converter`, `openpyxl`, `xlrd`, `jupyter`, `ipykernel`
    - Generated `requirements.txt` and `requirements_lock.txt`
    - Registered Jupyter kernel `Python (semaglutide-venv)` for use in Cursor/VS Code
  - Notebook fixes (`Mortality Model.ipynb`):
    - Converted 4 stray `raw` cells back to Python code cells
    - Fixed pandas 3.0 incompatibility: `groupby('ISO').apply(lambda ...)` → `groupby('ISO')['Year'].transform('max')` for max-year-per-ISO selection
    - Installed `xlrd 2.0.2` for legacy `.xls` reading
    - Added missing `years = range(1, 11)` definition in numeric validation cell
    - Added helper cell after single-iteration simulation defining `mr_cols`/`bl_cols`/`sg_cols`/`diff_cols`
    - Commented out destructive `simulation_result = final_output.reset_index().copy()` in Plots setup that wiped rich per-individual columns
    - Added defensive `assert len(bl_cols) > 0` to Plots setup with helpful message about run order
  - Section labeling per author's guidance from `updated_Mortality Model.ipynb`:
    - Marked "R Code first part" as **Legacy — Not required for experiment** (fully skippable)
    - Marked "numeric Method for validation" as **Legacy — Not required for experiment** (fully skippable)
    - Marked "Mortaility Results testing" as **conditional** — required only if running Plots section (provides rich `simulation_result`)
    - Added `# LEGACY — Not required for experiment` comments to inspection-only cells
  - Validation runs:
    - Confirmed `final_output` from `run_multi_simulation()` is reproducible (seeded, averaged across 10 iterations) and matches old run byte-for-byte
    - Confirmed unseeded single-iteration `simulation_result` produces ±20% variance run-to-run (expected Monte Carlo noise)
    - Confirmed survival projection plot for HUN renders correctly (baseline vs semaglutide curves diverge over 10y)
    - Confirmed age-group breakdown shows older cohorts (60-74) gain the most life-years, consistent with biological expectation
- Decisions made:
  - Keep R pipeline (`Mortality_model2.R`) and Python notebooks as parallel implementations; R produces inputs (`final_df_imputed.rds`, `mortality2.rds`), notebooks consume them for downstream analysis
  - Use `test/` folder for all intermediate `.rds` outputs to keep root clean
  - Mark notebook sections clearly so future runs can skip non-essential cells
  - Defer adding `np.random.seed(42)` to single-iteration simulation; downstream `final_output` is already deterministic via `run_multi_simulation`
- Outputs generated:
  - `test/final_df_imputed.rds`, `test/mortality2.rds`, `test/population_with_iso.rds` (from R script)
  - `final_output` (averaged 10-iteration MC) with per-country `total_person_years_saved`
  - Country-level survival plots, age-group life-years-gained trajectories
  - `requirements.txt`, `requirements_lock.txt`
- Issues/blockers:
  - Numeric validation cell (legacy) shows ~2-15% deviation in JPN/per-country values vs old run; root cause likely path-dependence on unseeded `simulation_result`. Marked as not required for experiment so non-blocking.
  - Plots section depends on rich `simulation_result` from "Mortaility Results testing"; conflict with author marking that section "(not required)". Resolved by labeling it conditional.
- Next tasks:
  - (Carry forward) Investigate `Mortality_model2.R` global summary `lives_saved` NAs and inflated `total_population`
  - Optionally seed cell 18 to make per-country plots deterministic
  - Consider refactoring plots to consume averaged `final_output` directly (smoother, no legacy dependency)
  - Explore `Price rebound model.ipynb` next session

---

## Daily Log Template

Copy this block for each workday.

### YYYY-MM-DD
- Time spent:
- Focus:
- Actions completed:
  - 
- Decisions made:
  - 
- Outputs generated:
  - 
- Issues/blockers:
  - 
- Next tasks:
  - 

---

## Action Backlog

- [x] Refactor hardcoded file paths to project-relative paths (done for v9.8 scripts)
- [x] Download missing `WPP2024_POP_F01_1_POPULATION_SINGLE_AGE_BOTH_SEXES.xlsx` (added 2026-04-20)
- [x] Integrate `latest/` codebase into root (done 2026-05-07)
- [x] Set up Python venv with notebook dependencies (done 2026-05-07)
- [x] Fix pandas 3.0 incompatibilities in Mortality Model notebook (done 2026-05-07)
- [x] Label legacy notebook sections per author guidance (done 2026-05-07)
- [ ] Validate scenario labels and filters are consistent in analysis scripts
- [ ] Add a simple run-order checklist (cleaning -> analysis -> mortality -> notebooks)
- [ ] Debug `lives_saved` NAs and inflated `total_population` in `Mortality_model2.R`
- [ ] (Optional) Seed single-iteration sim cell for reproducible per-country plots
- [ ] (Optional) Refactor plots to consume averaged `final_output` directly
- [ ] Explore `Price rebound model.ipynb`
- [ ] Fix hardcoded paths in legacy v9.7 scripts (low priority)
