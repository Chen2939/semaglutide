# CHANGES — internal audit of food-model corrections

**Branch:** `seth_bug_fixes`  ·  **Audience:** Yimin's review + our archive (not the clean public tree)  ·  **Status:** draft, uncommitted.

This records the corrections made to the semaglutide food-emissions model this
session. Every factual claim is sourced from the repo itself: commit history
(`git log`), diffs, committed code/comments, committed docs
(`FINDINGS_food_baseline.md`, `HANDOFF.md`), and the verification scripts under
`outputs/`. Rationale that is **not** recoverable from those sources is marked
`[SETH: ...]` for you to fill in rather than invented.

All numbers below are the actual outputs of the named verification scripts,
persisted as CSVs under `outputs/` (headline tables) — not approximations.

Baseline-food-emissions progression (max_uptake = mod_uptake; emissions are
δ-independent), from the headline CSVs:

| stage | baseline food emissions (Mt) | source CSV |
|---|--:|---|
| pre-fix (legacy double-count) | 11,858.008448 | `outputs/headline_numbers.csv` (`current`) |
| + fix #1 | 6,908.551527 | `outputs/headline_numbers.csv` (`corrected_fix1`) |
| + fix #2 | 6,504.306529 | `outputs/headline_numbers_fix2.csv` (`fix1_fix2`) |
| + stale-CI regen (canonical) | 6,510.906562 | `outputs/cireg/headline_numbers_cireg.csv` |
| + fix #3 | 6,510.906562 (unchanged) | `outputs/fix3/headline_numbers_fix3.csv` |

---

## 1. Aggregate double-count (fix #1) — `AGGREGATE_ITEMS` exclusion

**What was wrong.** `compute_food_savings()` in `data_visualization/pipeline.py`
built its national food-quantity table by summing the FAOSTAT Food Balance Sheet
`Element == "Food"` rows over `final_food_group`, **without excluding the
parent-level aggregate items**. The FBS contains both parent aggregates (e.g.
`Meat`, `Cereals - Excluding Beer`, `Vegetables`) *and* their component items,
so the parents' tonnage was summed on top of their own components — every
aggregated group was counted roughly twice. `build_carbon_intensity.py` already
excluded these 19 items via its `AGGREGATE_ITEMS` set for the CI weighting, but
the quantity step in the pipeline did not.

**History check (per your caution).** The committed `data_visualization/pipeline.py`
now *does* carry the exclusion — `git show HEAD:data_visualization/pipeline.py`
shows `from build_carbon_intensity import AGGREGATE_ITEMS` (line 24) and, inside
`compute_food_savings()`, `if exclude_aggregates: food_norm =
food_norm[~food_norm["Item"].isin(AGGREGATE_ITEMS)]` (lines ~131–134).
`git log -S"AGGREGATE_ITEMS" -- data_visualization/pipeline.py` returns **exactly
one commit: `0c05b2e`**. So the main copy did **not** have this "all along" — it
was introduced this session in `0c05b2e`. (The diet-pipeline copy did not get it
until later; see §5.)

**Correct behavior.** Gated by `exclude_aggregates: bool = True` (default). When
True, the 19 `AGGREGATE_ITEMS` are dropped from `food_norm` before grouping;
`False` reproduces the legacy double-counting for comparison.

**Why.** Mechanism recoverable from the code comment (lines 132–133: "drop
parent-level aggregate items before grouping so their tonnage is not summed on
top of their own components") and `FINDINGS_food_baseline.md` §1.
`[SETH: rejected alternatives, if any were considered (e.g. remapping the FBS
groups vs. set-exclusion) — not recoverable from the repo.]`

**Numerical effect** (`outputs/headline_numbers.csv`):
- baseline food emissions 11,858.008448 → 6,908.551527 Mt (−4,949.456921 Mt, −41.7%).
- annual food savings max 116.064318 → 68.500530 Mt/yr; mod 59.425463 → 35.076839.
- cum 10-yr food:survivor max 5.416 → 3.175; mod 5.225 → 3.063.
- year-10 annual food:survivor max 2.904 → 1.702; mod 2.809 → 1.646.

**Verification.** `outputs/compare_fix1.py` — runs the pipeline both ways from
one process and checks the invariant **"tonnage removed (before − after) ==
tonnage of the excluded aggregate items,"** computed independently from raw
FAOSTAT + the FBS mapping (per-cell |gap| < 1 t). Per `HANDOFF.md` the invariant
held exactly.

**Commit(s).** `0c05b2e` — `data_visualization/pipeline.py` (+22/−1).

---

## 2. Dairy raw-milk basis (fix #2)

**What was wrong.** In `build_carbon_intensity.py`, the `Milk - Excluding Butter`
group received a carbon intensity of ≈4.04 kg CO₂e/kg, which is a
**per-product milk+cheese blend** (`(470267*3.15 + 21191*23.88)/491458`). But the
FAOSTAT mass that CI is applied to is in **whole-milk-equivalent**, so cheese
intensity is effectively counted twice for the dairy group.

**Correct behavior.** `build_carbon_intensity.py` gained a
`dairy_raw_milk_basis` flag threaded through `build_faostat_ghg_map` /
`compute_global_group_averages` / `build_ci`; when True, `Milk - Excluding
Butter` uses the raw-milk CI `g["milk"]` = 3.15 instead of the blend. Butter and
Cream are unchanged. It is now the **default** (commit message `7ca038c`:
"Default to raw-milk dairy so canonical CI files regenerate reproducibly"), and
is baked into the committed canonical CI files (mean 3.15, p10 1.70, p90 4.83
per `HANDOFF.md`).

**Why.** Mechanism recoverable from `FINDINGS_food_baseline.md` §2 (mass is
whole-milk-equivalent; the blended CI double-counts cheese). `[SETH: the
scientific justification you want on record, and why correct the CI rather than
the FBS mass — not fully in the repo. Also: professor sign-off on the raw-milk
sensitivity bounds is still pending per HANDOFF.]`

**Numerical effect.** fix #1 → fix #1+fix #2 baseline 6,908.551527 →
6,504.306529 Mt = **−404.244998 Mt**, entirely in the Dairy group
(`outputs/headline_numbers_fix2.csv`). Annual savings max 68.500530 → 64.236312;
mod 35.076839 → 32.891117.

**Verification.** `outputs/compare_fix2.py` — checks **Δ(dairy emissions) ==
dairy tonnage × ΔCI** and that only the Dairy column moves (per HANDOFF the
invariant held exactly at −404.245 Mt).

**Commit(s).** `7ca038c` — `build_carbon_intensity.py` (+the driver updates
`outputs/compare_cireg.py`, `outputs/verify_promotion.py`). Canonical CI files
carrying the raw-milk value committed in `dba51f2`
(`Food data/carbon_intensity{,_p10,_p90}.csv`, git-LFS).

---

## 3. Stale carbon-intensity file — `carbon_intensity.csv` / `build_carbon_intensity.py`

**What was wrong.** The committed `Food data/carbon_intensity.csv` was generated
from an **older version of `build_carbon_intensity.py`** in which
`"Oilcrops Oil, Other"` was a hardcoded proxy `4.50`. The current code instead
**computes** `oilcrops_avg` (mean of soybean/palm/sunflower… oil intensities)
≈ 5.286. So the committed mean CI file no longer matched what the code produces —
only the `Fats and oils` column was affected.

**Upstream commit (verified in git, per your caution).**
`git log -S"oilcrops_avg" -- build_carbon_intensity.py` → **`c1746f1`**
("Update sensitivity analysis"); `git show c1746f1 -- build_carbon_intensity.py`
confirms it removes `"Oilcrops Oil, Other": 4.50` and adds
`oilcrops_avg = (g["soybean_oil"] + g["palm_oil"] + g["sunflower_oil"] …)` then
`"Oilcrops Oil, Other": oilcrops_avg`. The stale committed CSV predated
`c1746f1`. (Hash confirmed in `git log`/`git show`, not taken from a summary.)

**Correct behavior.** The three CI files were regenerated from current code and
promoted to canonical (`build_ci` gained an `out_path` override to write without
clobbering baselines). The committed canonical `carbon_intensity{,_p10,_p90}.csv`
now reproduce bit-for-bit from a default `build_ci` run, and the pipeline default
reads them directly.

**Why.** Reproducibility — commit messages `dba51f2` ("Track canonical
carbon-intensity files (raw-milk dairy + computed oilcrops)") and `7ca038c`.
`[SETH: any additional context on why promote now / whether p10/p90 ever existed
before — HANDOFF says they were created for the first time here.]`

**Numerical effect.** fix #1+fix #2 → +canonical-regen baseline 6,504.306529 →
6,510.906562 Mt = **+6.600033 Mt**, entirely in the Fats-and-oils group
(`outputs/cireg/headline_numbers_cireg.csv`). Annual savings max 64.236312 →
64.302212; mod 32.891117 → 32.924730.

**Verification.**
- `outputs/compare_cireg.py` — regenerates the CI files, checks that **only the
  Fats-and-oils column changes** and that **Δ(fats emissions) == tonnage × ΔCI**
  (per HANDOFF the invariant held exactly at +6.600 Mt).
- `outputs/verify_promotion.py` — confirms the default pipeline path reproduces
  the promoted headline exactly.
- `outputs/repro_sensitivity.py` — reproduces the manuscript sensitivity ratios
  on the regenerated CI files (note: it runs the *pre-fix* diet path; see §5).

**Commit(s).** Upstream code change `c1746f1` (`build_carbon_intensity.py`).
This session's promotion: `7ca038c` (code) + `dba51f2` (canonical CSVs +
`.gitignore`).

---

## 4. All-ages EER denominator (fix #3)

**What was wrong.** In `compute_food_savings()`
(`data_visualization/pipeline.py`), the demand-reduction fraction δ was
`weighted_treatment_eer / weighted_eer − 1`, summed over the simulated
population — which is **adults 18+ only** (`full_simulation_results8.rds`). That
adults-only fraction was then applied, via the Hegwood proportional shock
`Qd = Cd·P^Ed·(1+δ)`, to the **all-ages** national FAOSTAT food supply. Children
(0–17) are untreated but still eat, so the fraction was normalised on the adult
energy pool while applied to all-ages food — implicitly assuming adults are 100%
of national food consumption and overstating the reduction.

**Correct behavior.** The untreated child (0–17) energy pool is added, unchanged,
to **both** the baseline and treatment pools before forming δ:
`δ = (weighted_treatment_eer + child) / (weighted_eer + child) − 1`. The adult
pools are national-18+ *daily* kcal (`eer` = Mifflin-St-Jeor BMR/day × PAL;
`weighting` expands the sim to national 18+ counts, verified == UN WPP 18+ to
0.000%). The child pool is national *annual* kcal from
`Food data/child_energy_by_country.xlsx`, converted to daily (`/365`). A
raise-on-NA guard refuses to proceed if any shocked country lacks a child pool
(never silently reverts to the adults-only δ). Gated by
`all_ages_denominator: bool = True` (default); `False` reproduces the legacy
fraction. δ stays proportional; the Hegwood rebound solver is untouched.

Child input provenance: `outputs/fix3/compute_child_energy.R` builds the pool
from UN WPP 2024 single-age populations × FAO/WHO/UNU (2004) moderate-activity
energy requirements (ages 0–17), committed with its hardcoded lookup in
`31cfd72`.

**Why.** The bug mechanism and the chosen fix are documented in the code comments
(the fix #3 block in `pipeline.py`), `FINDINGS_food_baseline.md` §3, and the
commit message `f71572c`. The **rejected alternatives are partly recoverable**
from `outputs/fix3/investigate.py` (committed `d750566`), which quantifies that a
FAOSTAT-kcal/capita/day denominator over-corrects (factor ≈0.64 vs. the expected
≈0.85) because FAOSTAT supply includes household waste.
`[SETH: the full rationale for choosing the child-EER (all-ages intake)
denominator over (a) an absolute-calorie reformulation and (b) an
adult-population-share proxy, and the scientific basis for the FAO/WHO/UNU 2004
child requirement schedule — state what you want on record beyond what
investigate.py already shows.]`

**Numerical effect** (`outputs/fix3/headline_numbers_fix3.csv`, canonical mean CI):
- baseline food emissions **unchanged** at 6,510.906562 Mt (δ-independent).
- annual food savings max 64.302212 → 54.197555 Mt/yr (−15.71%); mod 32.924730
  → 27.766417 (−15.67%).
- cum 10-yr food:survivor max 2.976 → 2.502; mod 2.871 → 2.415.
- year-10 annual food:survivor max 1.595 → 1.341; mod 1.543 → 1.298.
- minimum-country ratio (cum 10-yr): legacy LTU (Lithuania) 2.029 → fix #3 POL
  (Poland) 1.747 (max); mod LTU 1.993 → LTU 1.726.
- per-country dilution (`outputs/fix3/delta_verification.csv`): new/old δ median
  0.8535, mean 0.841, range 0.6615 (NRU) – 0.887 (QAT). Identity: new/old =
  adult/(adult+child) = 1/dilution (treatment term cancels; scenario-independent).

**Verification.**
- `outputs/compare_fix3.py` — baseline both ways; checks baseline emissions are
  **δ-independent** (identical across runs) and that the legacy run reproduces
  the committed reference exactly.
- `outputs/fix3/verify_delta.py` — per-country dilution factor and new/old δ,
  flags any value near the rejected-proxy signatures (0.79 pop-share / 0.64
  FAOSTAT).
- `outputs/fix3/proof_port.py` — see §5 (bit-for-bit check).

**Commit(s).** `f71572c` — `data_visualization/pipeline.py` (+66/−4),
`Food data/child_energy_by_country.xlsx`, `outputs/compare_fix3.py`,
`outputs/fix3/verify_delta.py`. Child input built in `31cfd72`
(`compute_child_energy.R`, xlsx, lookup CSV); investigation/docs in `d750566`.

---

## 5. The two-copies problem — `compute_food_savings` vs `compute_food_savings_diet`, and the parity port

**What was wrong.** The model exists in **two separate copies**: the baseline
`compute_food_savings()` in `data_visualization/pipeline.py`, and
`compute_food_savings_diet()` in `diet_sensitivity/pipeline.py` (used by the
whole sensitivity/diet suite: `sensitivity_overview.py`, `combined_analysis.py`,
`analysis.py`, `tornado_analysis.py`). The diet copy had received **neither
fix #1 nor fix #3**: it summed FBS quantities with no `AGGREGATE_ITEMS`
exclusion, and used the adults-only δ `weighted_treatment_eer / weighted_eer − 1`.
`outputs/repro_sensitivity.py` states this outright in its docstring ("the SAME
code path the manuscript used … no fix1/fix2 applied there"). So every committed
sensitivity number (P10/P90/combined-conservative) reflected the *inflated*,
pre-fix-#1/#3 model. (fix #2 did reach it, because it arrives via the CI files.)

**Correct behavior.** `compute_food_savings_diet()` was ported to mirror the
main pipeline: `exclude_aggregates` (fix #1), `all_ages_denominator` +
`child_energy_file` with the same all-ages δ and raise-on-NA guard (fix #3), all
defaulting True. The diet redistribution consumes the corrected all-ages base
shock, so fix #3 flows through to the calibrated per-group shocks
(combined-conservative) too.

**Numerical effect (post-fix sensitivity suite, `outputs/fix3/sensitivity_suite_fix3.csv`,
35 complete-data countries):**

| spec | uptake | cum 10-yr | yr-10 annual | min-country | tipping (<1) |
|---|---|--:|--:|---|--:|
| P10 | max | 1.106 | 0.593 | 0.795 LTU | 6 |
| P10 | mod | 1.067 | 0.574 | 0.780 LTU | 7 |
| P90 | max | 4.717 | 2.529 | 3.083 POL | 0 |
| P90 | mod | 4.553 | 2.448 | 3.049 POL | 0 |
| combined-conservative | max | 1.292 | 0.693 | 0.993 POL | 1 |
| combined-conservative | mod | 1.248 | 0.671 | 0.980 POL | 2 |

For comparison, the *pre-fix* committed sensitivity overview had P10 = 2.356,
P90 = 10.373, combined = 2.719, all with 0 tipping
(`outputs/cireg/…` / `data_result/all_sensitivity_overview_results.csv` PRE, per
the §Cumulative review). Tipping countries appear **only after** the fixes.

**Verification.**
- `outputs/fix3/proof_port.py` — proves the port is faithful: the diet pipeline
  in uniform-diet / mean-CI (the one case where it must reduce to the main
  pipeline) reproduces the main post-fix-#3 baseline **bit-for-bit** —
  6,510.906562 Mt and 54.197555 / 27.766417 Mt/yr, **max per-country savings diff
  0.0 across 112 rows.**
- `outputs/compare_sensitivity_fix3.py` — runs the P10/P90/combined suite on the
  ported path (source of the table above).

**Commit(s).** `7ec6f21` — `diet_sensitivity/pipeline.py` (+61/−4),
`outputs/compare_sensitivity_fix3.py`, `outputs/fix3/proof_port.py`.

---

## Cumulative effect

The corrections compound multiplicatively on annual food savings (max uptake),
from the headline CSVs:

| step | savings max (Mt/yr) | step multiplier |
|---|--:|--:|
| pre-fix | 116.064318 | — |
| fix #1 | 68.500530 | ×0.5902 |
| + fix #2 | 64.236312 | ×0.9377 |
| + stale-CI regen | 64.302212 | ×1.0010 |
| + fix #3 | 54.197555 | ×0.8429 |

Net: **×0.4670** overall (116.064 → 54.198 Mt/yr). This is close to the informal
"~fix1 ×0.55 × ~fix3 ×0.85 ≈ ×0.47" chain, with the caveat that the ×0.55 term
bundles fix #1 (×0.59) with fix #2 and the CI regen (together ×0.554), and fix #3
is ×0.843.

**Headline PRE→POST shifts** from the Part 3 regeneration review
(`outputs/fix3/review_diffs.py`, committed outputs vs. their pre-regeneration
committed state):
- 10-yr global waterfall (max, 35 countries): actual food savings 1,098.620 →
  513.963 Mt; net climate savings 885.957 → 301.300 Mt.
- 1-yr waterfall (max, 53 countries): actual food savings 116.064 → 54.198 Mt.
- supplement table (max, after rebound): emissions reduced 116 → 54.2 Mt;
  mod 59.4 → 27.8. Calories-reduced unchanged (adult kcal reduction preserved).
- sensitivity global 10-yr ratio: baseline 5.423 → 2.502; P10 2.356 → 1.106
  (0 → 6 tipping); combined-conservative 2.719 → 1.292 (0 → 1); P90 10.373 → 4.717.

**Stated plainly:** the committed `data_result/`/`figures/` outputs were **stale
relative to fix #1, fix #2, and the CI promotion** — they had last been generated
before any of those. So the large (~50%) observed drop on regeneration is the
**full cumulative correction, not fix #3 alone** (fix #3's own increment is
≈−15.7%). Invariants that must not move held: survivor emissions constant at
200.607 Mt across all scenarios; supplement calories-reduced unchanged;
`drug_emissions_by_country.csv` unchanged (drug footprint is treated-user-based,
independent of the food fixes).

---

## Open items / known issues

- **Bug-toggles still in the code**, kept so legacy behavior is reproducible;
  slated for removal once the corrections are accepted:
  `exclude_aggregates` and `all_ages_denominator` in **both**
  `compute_food_savings()` and `compute_food_savings_diet()`
  (`False` reproduces the pre-fix results); `dairy_raw_milk_basis` in
  `build_carbon_intensity.py`.
- **Two pipelines still un-consolidated.** `compute_food_savings` and
  `compute_food_savings_diet` were brought to parity by **mirroring** the fixes,
  not by merging into one function. They can drift again (this is exactly how
  fix #1/#3 came to be missing from the diet copy). Consolidation to a single
  shared function is recommended and not yet done.
- **`rebound_validation.py` self-copy bug — FIXED this session** (`107a992`): it
  `shutil.copy`'d the figure onto itself and raised `SameFileError` (exit 1)
  after the figure was already written; guarded so the copy only runs when
  source ≠ destination. Re-run now exits 0.
- **Working-tree / untracked** (not part of the clean tree): `outputs/verify_promotion.log`;
  `outputs/fix3/` scratch CSVs (`sensitivity_suite_fix3.csv`,
  `carbon_intensity_meat_p10_fix3.csv`, `delta_verification.csv`,
  `denominator_investigation.csv`, `child_energy_diagnostics.csv`) and logs;
  byte-churn on `outputs/fix3/child_energy_by_country.xlsx`. Gitignored
  regenerable deliverables not committed: `data_result/supplement_results_table{,_raw}.csv`,
  `figures/breakeven_publication.pdf`.


---

## Known stale outputs

Survivor emissions moved to the Poore & Nemecek food basis, and the survivor
path became carbon-intensity-aware. The outputs below are still on the
**pre-change survivor basis** and do not match the code that produces them.

| Script | Stale output |
| --- | --- |
| `diet_sensitivity/analysis.py` | `data_result/diet_sensitivity_results.csv`, `data_result/diet_sensitivity_ratio_comparison.csv` |
| `drug_effect/analysis.py` | `data_result/net_emissions_with_drug.csv`, `data_result/drug_footprint_summary.csv` |
| `data_visualization/generate_dashboard_figure.py` | `figures/country_dashboard.png` |
| `data_visualization/generate_waterfall_figure.py` | `data_result/global_emissions_waterfall.csv`, `figures/global_emissions_waterfall.png` |
| `reference/metrics.py` | reference snapshot — already expected-failing for two prior reasons |

**These are deliberately not regenerated in this commit.** They are terminal
outputs: nothing in the pipeline reads them, so leaving them stale cannot
propagate a wrong number into anything else. They will move again when the
break-even extension and the survivor-decline fix land, so regenerating now
would burn a full pipeline pass to produce numbers that are superseded before
they are used. One regeneration pass after those changes covers all of these
plus the reference metrics.

`reference/metrics.py` additionally carries a stale *configuration*, not just
stale values: its `combined_conservative` row still names the derived
meat-only carbon-intensity file, which production retired in favour of
all-food P10. See the comment at its `run_configurations()`. That must be
reconciled in the same pass.

**Not stale — food-side only, unaffected by the survivor basis:**

- `data_result/drug_emissions_by_country.csv` — a function of treated-user
  counts from the simulation alone (`drug_footprint.py:33-46`); reads neither
  food savings nor survivor emissions.
- `figures/food_group_breakdown.png` — built from `result_df`, which the
  survivor change leaves bit-identical.

Both were verified unchanged by the food-side check that accompanied the
basis change: `actual_reduction`, `expected_demand_reduction_percent` and all
food-savings columns reproduced at exactly 0.0 across the mean, P10 and P90
carbon-intensity scenarios.


---

## How to reproduce

```
# fix #1
PYTHONUTF8=1 C:\Python314\python.exe outputs\compare_fix1.py
# fix #2
PYTHONUTF8=1 C:\Python314\python.exe outputs\compare_fix2.py
# stale CI regen/promotion
PYTHONUTF8=1 C:\Python314\python.exe outputs\compare_cireg.py
PYTHONUTF8=1 C:\Python314\python.exe outputs\verify_promotion.py
# fix #3
PYTHONUTF8=1 C:\Python314\python.exe outputs\compare_fix3.py
PYTHONUTF8=1 C:\Python314\python.exe outputs\fix3\verify_delta.py
# two-copies port (bit-for-bit) + sensitivity suite
PYTHONUTF8=1 C:\Python314\python.exe outputs\fix3\proof_port.py
PYTHONUTF8=1 C:\Python314\python.exe outputs\compare_sensitivity_fix3.py
```
