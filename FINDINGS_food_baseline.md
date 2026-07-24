# Findings: food-emissions baseline is inflated (session handoff)

Concise, self-contained handoff for a fresh session. Diagnoses why the model's
food-emission savings are too high, separates genuine bugs from modeling
choices, and lists fixes. Nothing here has been committed yet.

## Environment / where things are
- Repo: `C:\Users\sethw\repos`. Run Python with `C:\Python314\python.exe`.
- Untracked data (`Food data/`, `oecd/`, `.rds`, `World Bank/`) was copied in from
  OneDrive; it must be present for the pipeline to run.
- Working branch: `seth`.

## What this session produced
- Committed + pushed on `seth` (PR opened): 10-year emissions waterfall edits +
  reconciliation note, **Panel A** (`data_visualization/generate_waterfall_1yr_figure.py`,
  1-year, no survivorship, 53-country), the combined A/B figure
  (`generate_waterfall_combined_figure.py`), and `gdp_share_of_global_economy.R`.
- Uncommitted: `scripts/build_supplement_table.py` (supplementary results table +
  per-treated-patient savings). It faithfully reports whatever the pipeline
  produces, so it will self-correct once the pipeline is fixed.

## Core problem
The model's **baseline food emissions are ~12 t CO2e/person/yr — roughly 4-5x the
realistic 2-3 t.** Headline food savings = `r_pop x baseline`, so this inflates
every food-side number (the 244/116 Mt waterfall values, Panels A/B, break-even
ratios, per-patient savings). The reduction fraction (`r_pop = -1.99%`) and the
treated headcount (247.7M max / 129.6M moderate) are CORRECT — the problem is
entirely in the baseline.

## Issues, in order of size

### 1. BUG — FAOSTAT aggregate double-counting (largest)
`Food data/FBS_Group_Mapping.csv` contains both aggregate items (`Meat`,
`Cereals - Excluding Beer`, `Vegetables`, ...) AND their components, and
`data_visualization/pipeline.py`'s food-quantity step sums both.
`build_carbon_intensity.py` already excludes these via its `AGGREGATE_ITEMS` set
(19 items), but the pipeline's quantity step does not.
- **Fix:** apply the same `AGGREGATE_ITEMS` exclusion in `pipeline.py`
  `compute_food_savings()` before grouping food quantities.
- **Effect:** per-capita 12.0 -> 7.0 t; baseline 11,693 -> 6,818 Mt.

### 2. BUG — dairy basis mismatch
`Milk - Excluding Butter` FAOSTAT mass is in whole-milk-equivalent, but its CI
(4.04) is a per-PRODUCT milk+cheese blend
(`(470267*3.15 + 21191*23.88)/491458`), so cheese intensity is counted twice.
- **Fix:** apply raw-milk CI (~3.15) to milk-equivalent mass.
- **Effect:** ~-400 Mt (~6%); baseline -> ~6,417 Mt (~6.6 t/adult).

### 3. SUBTLE / verify first — adults-only demand percentage applied to all-ages food
NOTE: this is an internal pipeline scaling issue. It is NOT about the
per-patient metric (see below).
- **Stage:** `data_visualization/pipeline.py`, `compute_food_savings()`, ~lines
  166-186. `expected_demand_reduction_percent = weighted_treatment_eer /
  weighted_eer - 1` is summed over the simulation (adults 18-89 only), then
  `expected_demand_reduction = initial_eql_quantity * percent` applies it to the
  ENTIRE national FAOSTAT food supply (eaten by all ages).
- **Mechanism:** the percentage is normalized on the adult energy pool (~974M,
  ~82% of people) but applied to all-ages food (~1,188M). It implicitly assumes
  adults are 100% of national food consumption; they are ~85-88%.
- **Effect:** overstates the AGGREGATE food reduction by ~1.10-1.15x. Smallest
  and least certain of the issues — verify empirically before fixing.
- **Fix:** normalize the percentage on the same population base as the food it
  is applied to (total population), or apply the absolute calorie reduction
  directly instead of as a percent-of-total.

### 4. CHOICE, not a bug — meat/beef CI is high
The meat CI (~20-29 by country) is FAITHFUL Poore & Nemecek: `Bovine Meat` =
production-weighted composite of beef-herd (99.48) + dairy-herd (33.30) = 70.6
kg CO2e/kg; other leaves (lamb 39.7, pork 12.3, poultry 9.9, cheese 23.9, milk
3.15) also match P&N retail-weight means. It is high because P&N's global-mean
beef includes land-use change. After fixing #1-#3 the baseline is still
~5.4 t/total-person, ~2x the 2-3 t benchmark; the remainder is this CI choice,
not a bug. Reaching 2-3 t requires choosing a lower/regional beef CI — a
scientific decision for the professor.
- **Action:** present meat/beef CI as an explicit sensitivity (P&N global-mean
  vs regional/retail), do not change unilaterally.

## What is CORRECT and should not be touched
- **Per-treated-patient metric** (`scripts/build_supplement_table.py`):
  `after-rebound emissions reduced (kg) / treated patients`. Both numerator and
  denominator are patient-scoped (95%/50% of eligible adults). Total population
  does NOT belong here. Issue #3 scales the aggregate numerator ~1.1x but never
  changes this denominator to population.
- **The "12 t/person" figure** was a sanity-check diagnostic (national food
  emissions / population), not a deliverable; total population is the correct
  denominator there because it is a per-capita footprint, not a per-patient one.

## Directional implication (flag for the professor)
Higher food CI -> bigger food savings, so the current setup is GENEROUS to the
paper's thesis (food savings > survivor emissions). Fixing #1-#2 shrinks the
food-savings baseline ~45%; a lower beef CI (#4) shrinks it further and NARROWS
the margin vs survivor emissions. These corrections tighten the headline
conclusion, so quantify them before the paper leans on current numbers.

## Recommended next steps
1. New branch. Implement #1 (aggregate exclusion in `pipeline.py`).
2. Add #2 (dairy raw-milk basis).
3. Verify #3 empirically; if confirmed, normalize the demand percentage on total
   population (or apply absolute calorie reduction).
4. Re-run the full figure/table set; show corrected vs current side by side
   (waterfalls, break-even ratios, Panels A/B, supplement table).
5. Present #4 (meat/beef CI) as a sensitivity for the professor to choose, with
   the direction (lower CI -> smaller margin) called out.
6. Commit only after the professor signs off on #4.

## Key files
- `data_visualization/pipeline.py` — `compute_food_savings()`; food baseline
  (fixes #1 and #3 live here).
- `build_carbon_intensity.py` — `AGGREGATE_ITEMS` set + meat/dairy CI derivation
  (source of #2 basis and the #4 choice).
- `scripts/build_supplement_table.py` — uncommitted; per-patient metric is
  correct; will self-correct once the pipeline baseline is fixed.
