# Handoff — implement fix #3 (adults-only demand scaling)

State-only handoff for a fresh session. The CI promotion is now **committed** (two
commits, below); fix #1 (`pipeline.py`) and everything else remain uncommitted.

## Branch & working tree
- Branch: `seth_bug_fixes`.
- Commits added by the CI promotion (most recent first):
  - `7ca038c` — code: raw-milk dairy default (`dairy_raw_milk_basis=True` in all three functions) + `_fix2` filename-suffix drop + explicit flag threading through `regen_ci_files()` + git-LFS-pointer guard in `build_ci`. Touches `build_carbon_intensity.py`, `outputs/compare_cireg.py`, `outputs/verify_promotion.py`.
  - `dba51f2` — the three canonical CI files + narrowed `.gitignore`.
- Still uncommitted (`git status -s`):
  - ` M data_visualization/pipeline.py`  (fix #1 — NOT yet committed)
  - ` M HANDOFF.md`  (this file)
  - `?? FINDINGS_food_baseline.md`  (untracked; original diagnosis of issues #1–#4)
  - `?? outputs/*.py + result dirs`  (untracked drivers/results). NOTE: `compare_fix1.py`, `compare_fix2.py`, `repro_sensitivity.py` are NOT committed, yet the committed `compare_cireg.py`/`verify_promotion.py` import them — those two won't run standalone from a clean checkout until the deps are committed too.
- `Food data/` is **no longer fully gitignored**: `.gitignore` now tracks exactly three files there — `carbon_intensity.csv`, `_p10.csv`, `_p90.csv` — via **git LFS** (`*.csv filter=lfs`). All FAOSTAT source data and other inputs remain ignored. A fresh clone needs `git lfs pull` to hydrate them; `build_ci` raises a clear "run git lfs pull" error if handed a pointer stub.

## What each change did and where outputs live

### Fix #1 — FAOSTAT aggregate double-counting (DONE)
- Code: `data_visualization/pipeline.py`. Added `from build_carbon_intensity import AGGREGATE_ITEMS` (line 24) and an `exclude_aggregates: bool = True` param to `compute_food_savings()`; when True it drops the 19 parent aggregate items from `food_norm` before grouping (lines 118–121). `False` reproduces legacy double-counting.
- Outputs: `outputs/current/` (pre-fix, `exclude_aggregates=False`), `outputs/corrected_fix1/` (fixed). Tonnage comparison + invariant in `outputs/tonnage_comparison_by_*.csv`, `outputs/headline_numbers.csv`. Driver: `outputs/compare_fix1.py`. Invariant (tonnage removed == excluded-aggregate tonnage) held exactly.

### Fix #2 — dairy raw-milk CI basis (DONE)
- Code: `build_carbon_intensity.py`. Added `dairy_raw_milk_basis=False` param threaded through `build_faostat_ghg_map`/`compute_global_group_averages`/`build_ci`; when True, `Milk - Excluding Butter` uses raw-milk CI `g["milk"]`=3.15 instead of milk+cheese blend `g["dairy"]`=4.043849. Butter/Cream unchanged.
- The pipeline reads a CI CSV, so fix #2 is delivered as a CI file: `Food data/carbon_intensity_fix2.csv` = the restored original mean CI with **only** the Dairy column set to 3.15.
- Outputs: `outputs/corrected_fix2/`, `outputs/headline_numbers_fix2.csv`. Driver: `outputs/compare_fix2.py`. Invariant Δ(dairy emissions)=tonnage×ΔCI held exactly (−404.245 Mt); only Dairy moved.

### CI-REGEN — reproducibility cleanup (DONE; not a numbered fix)
- Committed mean `carbon_intensity.csv` was stale: generated pre-commit `c1746f1`, when `"Oilcrops Oil, Other"` was a hardcoded 4.50; current code computes `oilcrops_avg`=5.286. Only the `Fats and oils` column is affected.
- Code: added `out_path=None` override to `build_ci()` so regen writes to `*_cireg` names without clobbering baselines.
- Regenerated `Food data/carbon_intensity_cireg.csv`, `carbon_intensity_p10_cireg.csv`, `carbon_intensity_p90_cireg.csv` from current code. p10/p90 **never existed before** (gitignored, no copies anywhere) — created for the first time; `diet_sensitivity/*` reads them with no fallback (FileNotFoundError if absent).
- `carbon_intensity_cireg_fix2.csv` = cireg mean + Dairy 3.15 (used for the fix1+fix2+cireg run). `carbon_intensity_meat_p10_cireg.csv` = repro artifact (mean + Meat from p10). The `*_cireg`/`*_fix2` scratch files were **deleted after promotion**; only `carbon_intensity_meat_p10_cireg.csv` (the live combined-conservative input for issue #4) is kept.
- Outputs: `outputs/cireg/` (`headline_numbers_cireg.csv`, `fats_invariant_by_country.csv`, `sensitivity_reproduction.csv`, `food_savings.csv`, `breakeven.csv`). Drivers: `outputs/compare_cireg.py`, `outputs/repro_sensitivity.py`. Fats invariant held exactly (+6.600 Mt). Sensitivity reproduction **on the blend `_cireg` p10/p90**: P10 2.36 vs manuscript 2.34, combined 2.71 vs 2.71, P90 10.37 vs 10.13. These bounds changed once p10/p90 adopted raw-milk dairy at promotion — see the CI-promotion section below for the canonical numbers.

## Current headline numbers — fix1+fix2+cireg = now the DEFAULT path (complete-data countries; savings gross of drug)
- After promotion these ARE the numbers a default `compute_food_savings()` run produces (verified exact match, `outputs/verify_promotion.log`).
- Baseline national food emissions: **6,510.9 Mt** CO2e (progression: original 11,858.0 → fix1 6,908.6 → fix1+fix2 6,504.3 → +cireg 6,510.9).
- Annual food savings: **max_uptake 64.3 Mt/yr, mod_uptake 32.9 Mt/yr**.
- Cumulative 10-yr food:survivor ratio: **max 2.98×, mod 2.87×**.
- Year-10 annual food:survivor ratio: **max 1.60×, mod 1.54×**.

## CI promotion — DONE (committed 2026-07-23)
- The regenerated CIs are now **canonical and committed** (`dba51f2` files, `7ca038c` code). The pipeline default (`compute_food_savings()` → `carbon_intensity.csv`) reads them directly. Verified: the default path reproduces the fix1+fix2+cireg headline **exactly** (baseline 6,510.9 Mt) — promotion changed nothing but which file the default reads. See `outputs/verify_promotion.py` / `.log`.
- **Canonical values** (raw-milk dairy basis `dairy_raw_milk_basis=True` is now the code default, applied to all three scenarios):
  - Dairy CI: **3.15** (mean) / **1.70** (p10) / **4.83** (p90) — supersedes the milk+cheese blend (mean 4.043849). Fix #2 is a units correction (FAOSTAT milk mass is whole-milk-equivalent), so it applies to every scenario, not just the mean.
  - `Oilcrops Oil, Other`: computed `oilcrops_avg = 5.286` (mean), superseding the old hardcoded 4.50. Only the Fats-and-oils column moves.
  - All three reproduce **bit-for-bit** from a fresh default `build_ci` run. Tracked via **git LFS**; `git lfs pull` required after clone.
- **Sensitivity bounds under raw-milk dairy** (global max-uptake ratio, `outputs/cireg/sensitivity_raw_milk.csv`): **P10 2.27** (was blend 2.36; manuscript 2.34), **P90 10.04** (was 10.37; manuscript 10.13), **combined-conservative 2.57** (was 2.71; manuscript 2.71). Raw-milk pulls P90 much closer to the published value, lands P10 slightly under, and drops combined below 2.71. **Professor to confirm before these enter the manuscript.**
- Still NOT decided by the professor: the meat/beef CI sensitivity (issue #4) — do not change unilaterally. (Oilcrops 5.286 and raw-milk dairy are now baked into canonical per this session's explicit instruction.)

## Fix #3 target — `compute_food_savings()` in `data_visualization/pipeline.py`
- Function starts at **line 60**: `compute_food_savings(ci_file="carbon_intensity.csv", exclude_aggregates=True)`. Returns `(food_savings, result_df)`. Loads `full_simulation_results8.rds` (adults 18–89 only), FAOSTAT FBS, price index, elasticities, and the CI CSV.
- The bug (issue #3, from `FINDINGS_food_baseline.md`): `expected_demand_reduction_percent` is computed on the adult energy pool — `sim_result.groupby(["ISO","scenario"]).sum()` then `weighted_treatment_eer/weighted_eer − 1` at **lines 187–193** — but is applied to the **all-ages** national FAOSTAT supply: `result_df["expected_demand_reduction"] = initial_eql_quantity * expected_demand_reduction_percent` at **lines ~204–206**. Adults are ~85–88% of consumers, so this overstates the aggregate reduction by ~1.10–1.15×.
- Fix direction  apply the absolute adult calorie reduction directly instead of a percent-of-total. Do NOT change the per-treated-patient metric in `scripts/build_supplement_table.py` (patient-scoped numerator and denominator; correct as-is).
- Verification pattern used for #1/#2/cireg (reuse): run the pipeline both ways from one process via a param, save to `outputs/corrected_fix3/`, print an explicit invariant, confirm nothing unintended moved, then report the headline table with a `fix1+fix2+cireg` column alongside `+fix3`. Suffix outputs `_fix3`.

## How to run
`PYTHONUTF8=1 C:\Python314\python.exe outputs\compare_cireg.py` (Windows console needs `PYTHONUTF8=1` for the Δ glyph). Python: `C:\Python314\python.exe`. The `.rds` is 167 MB and re-read per `compute_food_savings`/`build_drug_emissions` call.
