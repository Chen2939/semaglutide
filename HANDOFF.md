# Handoff — food-model corrections (post-fix status)

Session state for collaborators. The food-emissions baseline bugs diagnosed in
[`FINDINGS_food_baseline.md`](FINDINGS_food_baseline.md) are **implemented**.
The audit with verification numbers is [`CHANGES.md`](CHANGES.md).

## Branches

| Branch | Role |
|---|---|
| `seth_bug_fixes` | Seth’s delivered fixes (fix #1–#3, CI promotion, verification drivers, regenerated figures/tables). Matches `origin/seth_bug_fixes` at `193c5ab`. |
| `yimin_validation` | Review branch: one commit on top of `seth_bug_fixes` — residual kcal-share aggregate exclusion, LFS pointer guards in both pipelines, regenerated diet/sensitivity outputs, portable `outputs/fix3` ROOT paths. |

Work from `yimin_validation` for the current corrected sensitivity numbers.

## What was fixed (canonical defaults)

1. **Fix #1 — FAOSTAT parent aggregates.** `compute_food_savings` /
   `compute_food_savings_diet` drop `AGGREGATE_ITEMS` before summing food
   tonnage (`exclude_aggregates=True`).
2. **Fix #2 — dairy raw-milk CI.** `build_carbon_intensity.py` defaults
   `dairy_raw_milk_basis=True` (Dairy = 3.15 / 1.70 / 4.83 for mean/p10/p90).
3. **CI regen.** Canonical `Food data/carbon_intensity{,_p10,_p90}.csv` use
   computed `Oilcrops Oil, Other` ≈ 5.286 (not hardcoded 4.50); tracked via
   git LFS.
4. **Fix #3 — all-ages demand shock.** Untreated child (0–17) energy pool from
   `Food data/child_energy_by_country.xlsx` is added to both baseline and
   treatment EER pools (`all_ages_denominator=True`). Dilutes δ by ~15–16%.
5. **Diet kcal-share parity (`yimin_validation`).** `load_kcal_shares()` applies
   the same aggregate exclusion so diet-scenario calibration preserves calories.

Legacy behaviour remains behind toggles (`exclude_aggregates=False`,
`all_ages_denominator=False`, `dairy_raw_milk_basis=False`) for verification
only — **strip these before a public cleanup** (see Open items).

## Current headline numbers (max uptake, 35 complete-data countries)

Net food savings = gross food − drug (5.38 kg CO₂e/user-year). Survivor
emissions fixed at **200.6 Mt** over 10 years.

| Spec | Annual food Mt/yr (net) | 10-yr food:survivor | Min country | Tipping (ratio below 1) |
|---|--:|--:|---|--:|
| Baseline (uniform, mean CI) | 50.2 | **2.50×** | Poland 1.75× | 0 |
| Fatty foods down | 63.5 | **3.16×** | Lithuania 2.05× | 0 |
| Cereals/sweets shift | 33.9 | **1.69×** | Poland 1.22× | 0 |
| All-food P10 CI | 22.2 | **1.11×** | Lithuania 0.79× | **6** |
| All-food P90 CI | 94.6 | **4.72×** | Poland 3.08× | 0 |
| Combined conservative | 27.2 | **1.35×** | USA 1.08× | 0 |

All-country gross annual food savings (post fix #1+#2+#3): **~54.2 Mt/yr** max /
**~27.8 Mt/yr** mod (see `CHANGES.md`). Pre-fix baseline food emissions were
~11,858 Mt; post-fix **~6,511 Mt**.

Drug fold-in alone: max ratio 2.56× → 2.50×; mod 2.47× → 2.41×.

## Key files

- Pipelines: `data_visualization/pipeline.py`, `diet_sensitivity/pipeline.py`
- CI builder: `build_carbon_intensity.py`
- Child energy: `Food data/child_energy_by_country.xlsx` (from
  `outputs/fix3/compute_child_energy.R`)
- Audit / findings: `CHANGES.md`, `FINDINGS_food_baseline.md`
- Verification drivers: `outputs/compare_fix{1,2,3}.py`, `compare_cireg.py`,
  `verify_promotion.py`, `compare_sensitivity_fix3.py`, `outputs/fix3/*`

Fresh clone: `git lfs install` then `git lfs pull`. Pipelines call
`_assert_not_lfs_pointer` before reading CI CSVs.

## Open items (cleanup)

- Remove legacy toggles once professor accepts the corrections.
- Consolidate `compute_food_savings` and `compute_food_savings_diet` into one
  shared function so fixes cannot land in only one copy again.
- Delete or archive one-off verification scratch under `outputs/` after review.
- Some `outputs/fix3/*` scripts still hardcode Seth machine paths except
  `proof_port.py` / `verify_delta.py` (made portable on `yimin_validation`).
- `verify_promotion.py` / `compare_cireg.py` targets predate fix #3 / promotion
  bit-for-bit success — fine to drop in cleanup.
- Manuscript narrative still needs updating to the lower food-side numbers
  (Seth).

## How to reproduce checks

```bash
# from repo root, with venv + FAOSTAT Food data/ present
python outputs/compare_fix1.py
python outputs/compare_fix3.py
python outputs/fix3/proof_port.py
python outputs/compare_sensitivity_fix3.py
python -m diet_sensitivity.sensitivity_overview
```
