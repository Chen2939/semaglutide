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
- **QUEUED SWEEP: mortality-channel coherence across every published number.**
  Not a vintage check. The question for each number is **which of the three
  mortality channels it has switched on** -- (1) food-side survival weighting
  `pi(t)`, (2) pharmaceutical-side weighting `pi_dose(t)`, (3) survivor
  emissions -- and whether that combination is coherent for what the number
  claims to be. Panel A of the emissions waterfall was **current and
  incoherent, not stale**: it carried channels 1 and 2 in mismatched states and
  omitted 3, and produced entirely plausible output with no warning. A
  vintage check would have passed it.
  Settling an individual number is a **provenance** question rather than an
  arithmetic one: which script wrote it, what that script's weighting state was
  at the time of writing, and whether that path still exists in the tree. Where
  provenance cannot be established, **record that as the finding** rather than
  inferring it from a ratio.
  Specifically do **not** record the manuscript's 54.2 Mt as a stale vintage.
  The test established only that it is unweighted; it did not establish why.
  Three candidate causes remain and the test does not distinguish them: it
  predates the survival-weighting change; it came from a path that legitimately
  does not weight; or it came from a path that weights inconsistently, as
  Panel A did.
  *Evidence, not an answer:* **both** manuscript Panel A numbers sit on the
  unweighted basis, not only the 54.2. Net after manufacturing recomputes to
  **52.895507**, which rounds to the draft's **53**; the old weighted
  52.609522 reached 53 only by loose rounding. Nothing was tuned to hit that --
  the net figure is a by-product of a change made for the food side alone --
  so it is independent corroboration that the draft's Panel A figures came from
  **one consistent unweighted basis** rather than from a coincidence on a single
  cell. It says nothing about *which* of the three causes produced that basis,
  and it must not be read as upgrading this entry to a settled answer.
- **OPEN, AND IT MOVES PUBLISHED NUMBERS: the simulated BMI distribution does
  not reproduce its NCD-RisC input.** Measured, not fixed. The smoothing chain in
  `fit_bmi_mixture()` flattens each stratum's distribution toward the 1/7 uniform
  share, inflating population-weighted BMI >= 30 by **+1.57 pp (+5.82% relative)**
  and by 36% relative in Japan and 35% in Korea. That inflates the eligible
  population and therefore every food-savings, mortality and emissions number
  downstream. Full measurement and its declared bars in the section below; nothing
  was changed and the remedy is an open decision.
- **Working-tree / untracked** (not part of the clean tree): `outputs/verify_promotion.log`;
  `outputs/fix3/` scratch CSVs (`sensitivity_suite_fix3.csv`,
  `carbon_intensity_meat_p10_fix3.csv`, `delta_verification.csv`,
  `denominator_investigation.csv`, `child_energy_diagnostics.csv`) and logs;
  byte-churn on `outputs/fix3/child_energy_by_country.xlsx`. Gitignored
  regenerable deliverables not committed: `data_result/supplement_results_table{,_raw}.csv`,
  `figures/breakeven_publication.pdf`.


---

## Known stale outputs — RESOLVED

> **All clear as of the survival-weighting commit.** The single regeneration pass
> this section was waiting for has run: every output below, plus the reference
> snapshots, was regenerated and `reference/metrics.py` now passes at exactly 0.0
> on all 47 values. `metrics.py`'s stale *configuration* was reconciled in the
> same pass. Nothing in this section is outstanding; it is kept as the record of
> why the staleness was allowed to stand for three commits.
>
> **This does not mean the outputs are final.** A further reference refresh is
> expected if the donor-imputation exclusion arm is ever run as the headline
> specification — it changes N from 40 to 37 and moves every ratio — and likewise
> for any horizon extension. "Resolved" here means the deferred backlog is cleared
> and the snapshots describe what the code currently produces, not that no future
> change is anticipated.

The original note follows.

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
break-even extension lands, so regenerating now would burn a full pipeline pass
to produce numbers that are superseded before they are used. One regeneration
pass after that change covers all of these plus the reference metrics.

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

## Survivor GHG decline applies to non-food only

**What was wrong.** The annual decline was applied to the whole per-capita
survivor factor. Post-basis-change that factor is
`oecd_nonfood_ghg_t_per_capita + food_add_back_t_per_capita`, so the decline
was declining food as well. The food-savings side of the same comparison holds
carbon intensity constant across all ten years, so the same food sat on two
different trajectories: falling on the survivor side, flat on the savings side.

**Correct behavior.** Only the non-food component declines; food is held flat,
on the grounds that food emissions are difficult-to-abate and plateau while
other sectors decarbonise. `emissions_factor_Y0` is unchanged — it remains the
undeclined sum, and year 0 was never declined.

The decline had three near-identical implementations. It now has one:
`pipeline.adjust_survivor_decline`, beside `load_mortality_emissions`. The
tornado's local copy was deleted and the call site rewired; the inert copy in
`rebuild_mortality_emissions` was corrected in place rather than left as a
landmine for the first caller to pass a nonzero rate. The two components are
carried into the three survivor-emissions CSVs (36 → 38 columns, appended so no
pre-existing column changes position) with an assertion that they sum to the
factor and that their null patterns agree.

**Direction — this change is CONSERVATIVE.** No prior note in this repository
recorded a direction; if one exists elsewhere calling it anti-conservative, that
is backwards. Holding food flat *removes* a discount the old code applied to the
food share of the factor (37.7% of it for the USA), so every year-1..10 factor
is **larger** than before. The survivor charge rises and the food:survivor ratio
falls.

Measured, USA max_uptake, mean CI, 2%/yr:

| quantity | before | after | movement |
|---|--:|--:|--:|
| survivor emissions, 10-yr cum (Mt) | 144.944598 | 153.235993 | **+8.291395 (+5.72%)** |
| net food savings, 10-yr (Mt) | 283.478483 | 283.478483 | 0 (bit-identical) |
| ratio food:survivor | 1.955771 | 1.849947 | **−0.105824 (−5.41%)** |

The effect compounds with year — +0.77% at year 1 to +8.44% at year 10 — because
the withheld discount is `food × (1 − (1 − r)^t)`. Year 10 closes exactly:
`food × (1 − 0.98^10) = 1.494174` Mt of factor.

**Implementation note.** The per-year factor is written as
`Y0 − nonfood × (1 − (1 − r)^t)`, not the algebraically identical
`nonfood × (1 − r)^t + food`. The two forms differ in float rounding, and the
second one breaks the null check: `pandas.read_csv` defaults to
`float_precision=None` (the fast `xstrtod` converter), which parses 26 cells of
these three columns one ULP away from an exact `strtod`. The file text is
exactly round-trippable — Python's `float()` reproduces the identity — so the
components sum to the factor in memory but not always after a read, and
re-deriving the sum moved 20 rows by 1–2 ULP at `decline_rate=0.0`, where the
decline must be an exact no-op. The anchored form makes `(1 − (1 − 0.0)^t)`
exactly `0.0`, so year 1–10 factors are `Y0` bit-for-bit regardless of the
parser. Both copies use the anchored form; comments in both say not to
"simplify" it back.

**Verification.** Every gate was declared before its run.
- Plumbing no-op: all 36 pre-existing columns of all three survivor CSVs
  bit-identical to the committed versions, compared as raw field text against
  the HEAD blobs (LFS-smudged, OID-verified) — 13,608 cells, 0 differing.
- Verbatim move no-op: function body byte-identical (661 bytes) across the move,
  and `sensitivity_tornado_results.csv` reproduced byte-for-byte.
- Arithmetic null: the shared function at `decline_rate=0.0` differs from the
  old whole-factor form on 0 rows of 126 under the anchored form (20 rows at
  1–2 ULP under the re-derived form).
- Table-wide null: all seven tornado runs forced to 0.0 — the decline function
  is called unconditionally for the baseline and all six axis endpoints, not
  just the decline arm — gives 27 of 30 cells bit-identical, with the 3 cells
  fed by the 0.02 endpoint landing on their predicted values (high equals its
  own low bit-exactly, range exactly 0.0).

**Still divergent, queued:** `Mortality Model.ipynb` (~line 2488) carries a
third copy, still in the whole-factor form at rate 0.0. Left untouched
deliberately: it is out of the execution path. It also writes the wide
22-emissions-column schema and knows nothing of the two component columns, so
re-running it would restore the removed columns *and* reintroduce the old
decline. Queued action: a "DO NOT RUN — superseded" cell at the top.

---

## Mortality rates come from the imputed column, not the raw HLD extract

**What was wrong.** `deterministic_mortality.py` took the population from
`final_df_imputed.pkl` but looked mortality rates up from `mortality2.rds`. Those
two files are different stages of the same pipeline:
`Mortality_model2.R` extracts the Human Life-Table `Mx_1x1` tables, drops
territorial subdivisions and truncates ISO codes, giving **`mortality2.rds` — 41
countries**, which is simply HLD's coverage. Cell 4 of `Mortality Model.ipynb`
merges that onto the 63-country population with
`right_on=['ISO','Age','Sex']`, cell 5 imputes the 22 unmatched countries
(regional median stratified by age and sex → global median for that age–sex
cohort → a `0 → 0.00001` floor) and writes `final_df_imputed.pkl`.

So the lookup reached *past* the imputation to its own input. The merge in
`compute_individual_survival_diffs` returned NaN for every country HLD lacks, and
`.fillna(0)` turned that into a zero hazard — arithmetically immortality, since
`p_bl = p_sg = exp(0) = 1` and the survival difference is exactly zero. **27 of 63
countries were written out with `diff_Y0`–`diff_Y10` identically 0.0**, and the
downstream `total_survivor_emissions_10yr > 0` filter then dropped them, which is
where break-even's "36 complete-data countries" came from. Nothing warned.

The capital `Age` column in the pickle is the leftover right-hand merge key from
cell 4, which is why it is null on 42.86% of rows — on exactly the countries the
extract lacks. Keying on it drops them a second, independent way.

**Correct behavior.** The lookup is built from the simulation frame's own
`mortality_rate` column via a new `build_mortality_map()`, keyed on lowercase
`age`. That column is the imputation the manuscript methods describe, and it is a
complete single-valued function of `(ISO, age, Sex)` over 63 ISO × ages 18–89 × 2
sexes = 9,072 cells — asserted at build time, not assumed. `mortality2.rds` is no
longer read; it is retained as the provenance record of which countries have
measured rather than imputed rates. `survivor_manuscript_numbers.py` shares the
same machinery and moved with it.

`.fillna(0)` is kept, because non-adherent rows are legitimately walked past age
89 at longer horizons and a zero rate is inert for them — their hazard ratio is
unchanged, so `p_sg == p_bl` and their contribution is zero either way. It is now
**guarded**: a missing rate on a *treated* row raises with the offending
`(ISO, age+t, Sex)` keys. That is the specific silent path that produced the 27
zeroed countries, so it gets a check that fails loudly rather than a comment.

**Direction — the survivor charge RISES.** Restoring 27 countries adds
person-years that were being counted as zero:

| quantity | before | after | movement |
|---|--:|--:|--:|
| person-years saved, 10-yr, max (M) | 15.747011 | 16.829833 | **+1.082822 (+6.88%)** |
| person-years saved, 10-yr, mod (M) | 8.324684 | 8.891283 | **+0.566599 (+6.81%)** |
| extra survivors at year 10, max (M) | 2.940404 | 3.147531 | **+0.207127 (+7.04%)** |
| extra survivors at year 10, mod (M) | 1.550409 | 1.659044 | **+0.108635 (+7.01%)** |
| survivor emissions, 10-yr cum, max (Mt) | 264.846 | 273.300 | **+8.454 (+3.19%)** |
| survivor emissions, 10-yr cum, mod (Mt) | 140.195 | 144.626 | **+4.431 (+3.16%)** |
| countries qualifying (person-years > 0 **and** both factor components) | 36 | 41 | **+5** |

The emissions rise (+3.19%) is smaller than the person-years rise (+6.88%)
because only 5 of the 27 restored countries carry an OECD demand-based per-capita
factor: **ARE, CYP, MLT, ROU, SAU**. The other 22 now have non-zero person-years
but still no factor, so they contribute nothing. That is a separate coverage gap
in the OECD input and is untouched here.

The effect on the food:survivor ratio is **not** stated, because it is not
computed: a survival-weighting correction to the food-side demand shock is queued
directly behind this change, and the ratio is only meaningful once both have
landed. Reporting it twice from two intermediate states would be worse than
reporting it once.

**Implementation note.** Everything after `df_input` on
`compute_individual_survival_diffs` and `run_deterministic_mortality` is now
keyword-only. The mortality lookup used to be the second positional parameter, so
a stale `f(sim, mortality)` call would otherwise have bound a DataFrame to
`benefit_reduction` and run silently on a wrong benefit; it raises `TypeError`
instead. The same defence `compute_food_savings` already carries, for the same
reason.

`compute_individual_survival_diffs` also gained `horizon`, `survival_columns` and
`extra_columns`, all defaulting to current behaviour. They exist so the queued
food-side survival weighting reuses this loop rather than keeping a second copy —
this pipeline has had near-identical copies of the same arithmetic in three
modules before. The per-year missing-lookup counts and masks are exposed on
`.attrs` so coverage is readable rather than inferred.

**The age-89 lookup ceiling is a hard data-coverage bound.** The map covers ages
18–89 (`LOOKUP_AGE_MIN` / `LOOKUP_AGE_MAX`). Treated adherers span 18–74, so they
reach 89 at a 15-year horizon and fall off the table at year 16, where the
guarded `.fillna(0)` would raise rather than silently grant immortality. **Any
horizon extension past 15 years needs more mortality data, not a code change.**

**Verification.** Every gate was declared before its run
(`diagnostics/verify_mortality_source_swap.py`).
- Coverage: the map is 9,072 cells over 63 × 72 × 2 with no holes, asserted at
  build time.
- Guard silent where it should be: 0 treated rows miss a lookup in any year 1–10.
  The non-adherent misses it deliberately tolerates run 15,862 at year 1 to
  252,000 at year 10.
- Premise behind keeping the fill: 0 of 1,539,576 non-adherent rows change their
  hazard ratio. Stated first as `new_bmi == bmi`, which **failed** on 230,520
  rows; diagnosed rather than relaxed — those rows carry `individual_effect == 0`
  and `weight_diff == 0`, and `new_bmi` differs from `bmi` by at most `2.1e-16`
  relative (one ULP) from recomputing BMI off an unchanged weight, with an
  identical hazard band on all 230,520. Exact BMI equality was never the
  load-bearing condition; a zero hazard change is, and it holds exactly.
- **Partition, against the pre-change function run on the same inputs in the same
  process.** The change must move exactly three disjoint sets and nothing else:
  32 HLD countries with no floored cells → **exactly 0.0**; EST, ISL, LUX, SVN →
  small, from the 22 `(ISO, age, Sex)` cells where the extract holds `0.0` and the
  pickle holds the floored `1e-5` (EST 1 cell, ISL 10, LUX 8, SVN 3, all ages
  18–38), max relative movement `1.447e-04`; the 27 previously zeroed → non-zero.
  Result: 31 ISO moved, exactly 4 + 27, no fifth country. The partition survives
  into the survivor-emissions file: 32 countries bit-for-bit identical, 4 moved by
  ≤ 1.0001×, 5 off zero.
- The reference for that gate is the **pre-change function**, not the committed
  CSV. The committed blob already differs from what the pre-change code produces
  on 131 of 1512 cells at 1–2 ULP (worst relative `3.685e-16`); both the old and
  new functions differ from it identically, which is what establishes the gap
  belongs to the blob. Anchoring to it would have put a ULP floor under the
  exactly-0.0 bucket. See the corrected wart entry in the README.

**Regenerated:** `mortality model total emissions.csv`,
`mortality model total emissions_oecd{,_p10,_p90}.csv`,
`data_result/deterministic_mortality_comparison.csv`.

**Deliberately not regenerated:** break-even, the tornado, the diet ×
carbon-intensity grid, the diet-sensitivity module, every figure script,
`reference/metrics.py`, and `survivor_manuscript_numbers`. All of them depend on
food savings, which the queued survival-weighting change moves next; they get one
regeneration pass afterwards rather than two. The manuscript survivor numbers
quoted in the README (2.94 M survivors at year 10, 15.75 M person-years) are left
at their old 36-country values with a stale-pending note, for the same reason.

---

## Survival weighting on the food side of the model

**What was wrong.** The food-side demand shock counted every treated patient as
eating less in every year of the horizon. Some of them die anyway. At any year the
treated population contains three groups, and the model handled two of them:

| Group | True contribution | What the model did |
|---|---|---|
| Alive in both worlds | saves food | counted the saving — correct |
| Alive only because of the drug | eats a diet nobody would have eaten | counted the saving, and charged the whole footprint on the survivor side — correct |
| **Died despite the drug** | **nothing — dead in both worlds** | **still counted a food saving, every year — wrong** |

The exact difference in national food energy between the treated and untreated
worlds in year *t*, with `p_sg` and `p_bl` the treatment- and baseline-world
survival probabilities, splits in two:

```
Delta(t) = sum w*p_sg(t)*(treatment_eer - eer)  +  sum w*(p_sg(t) - p_bl(t))*eer
           \________ term 1: diet effect ______/    \____ term 2: extra _____/
                     among survivors                      survivors
```

`pipeline.py` computed term 1 with no survival probability and no year index —
equivalent to `p_sg == 1` for everyone forever — which is why one
`annual_food_savings_t` was reused for all ten years.

**The survivor food add-back is unchanged and was already correct.** Term 2 is
the additional-survivor population, priced by `pipeline._survivor_food_factor` on
*baseline* `eer`. **This fix concerns a different population**: patients who were
treated, saved food while alive, and then died. The two groups do not overlap and
`_survivor_food_factor` is not touched. A future reader will assume they are the
same fix; they are not.

**Correct behaviour.** The missing scalar is

```
pi(t) = sum w*p_sg(t)*(eer - treatment_eer) / sum w*(eer - treatment_eer)
```

a difference-weighted mean of treatment-world survival, `pi(0) = 1` and falling.
`eer_diff` is non-zero on exactly the treated-adherer rows, so `pi` averages over
adherers without needing to filter for them. The corrected shock is
`delta(t) = delta * pi(t)`. **Only the numerator is weighted** — the denominator
stays on the 2022 baseline energy pool, which is the basis of the observed FAOSTAT
tonnage the shock is applied to.

New module `data_visualization/survival_weighting.py` writes
`data_result/food_shock_survival_weight.csv` — `(ISO, scenario, year) -> pi,
pi_dose` for 63 ISO × 2 scenarios × 15 years — so the food side reads a committed
artefact instead of opening mortality data.

**Two weights, not one.** `pi` weights survival by `w * eer_diff`, i.e. by how
much each patient's intake fell. That is right for the food shock and wrong for
the pharmaceutical term, where a surviving patient is dosed once regardless of
what their appetite did. `pi_dose` weights by `w` alone. The brief for this work
said to apply `pi` to the drug term; that would have been an error, though a small
one.

`pi` exceeds `pi_dose` on **1,248 of 1,260** `(ISO, scenario, year)` cells over a
10-year horizon, by up to **0.85 percentage points** — survival is usually a little
higher among the patients who cut their intake most. The ordering is **not
universal**: Japan reverses it in both scenarios, by up to 3.9e-04. Over the
15-year artefact the largest gap is 1.33 pp.

Direction: substituting `pi` would **overstate** treated-user-years and therefore
**overstate the drug charge** — measured at **+0.126%** (max uptake) and +0.100%
(moderate) on the 10-year total. Since the drug charge is *subtracted* from food
savings, that would push net savings and the food:survivor ratio **down**. The
magnitude is negligible; the reason to keep the two weights apart is that they
answer different questions, not that the numbers diverge much.
Verified in `diagnostics/check_pi_dose_direction.py`.

> **Correction to `9fe9cdd`.** Four claims in one paragraph of that commit message
> were wrong. It cannot be edited after the fact, so this is the corrected record.
>
> **(a) Direction.** It says using `pi` for the drug term "would have understated
> it". Backwards: `pi > pi_dose`, so `pi` gives larger weights, more
> treated-user-years and a **larger** drug charge. It overstates it. And since the
> charge is subtracted from food savings, the error pushes net savings and the
> ratio **down**, not up.
>
> **(b) Antecedent.** "it" had no clear referent — the drug charge or the user
> count — which is how the sign slipped through.
>
> **(c) The two percentages are over different populations, and one of them was
> wrong.** The paragraph reads as though −3.73% and "3.3% on the break-even set"
> were the same arithmetic. They are not, and the second figure was mis-derived.
> `sum_y pi_dose(y)` is a weighted average, so its shortfall against 10 depends on
> which countries are averaged:
>
> | population | Σ pi_dose | shortfall vs 10 | 10-yr drug | legacy ×10 |
> |---|--:|--:|--:|--:|
> | all 63 modelled ISO, max | 9.626778 | **−3.73%** | 13.080718 Mt | 13.587846 Mt |
> | 40-country break-even set, max | 9.619712 | **−3.80%** | 12.477086 Mt | 12.970333 Mt |
> | all 63 modelled ISO, mod | 9.622077 | −3.78% | 6.841641 Mt | 7.110358 Mt |
> | 40-country break-even set, mod | 9.614831 | −3.85% | 6.521616 Mt | 6.782871 Mt |
>
> So the break-even-set figure is **−3.80%**, not 3.3%. The 3.3% came from
> comparing the correct ten-year total against
> `drug_footprint_summary.drug_emissions_1yr_t × 10` — but that column is
> *already* `pi_dose(1)`-weighted (by a factor of 0.994607), so it compared a
> weighted year-1 value against an unweighted sum and mixed two bases. The correct
> legacy baseline is the undiscounted year-1 charge times ten. The two populations
> in fact give nearly the same shortfall, −3.73% and −3.80%; the apparent gap was
> the error, not a real difference between the sets.
>
> **(d) Which countries reverse.** It says `pi_dose` is "consistently the lower"
> and, in `d24475f`, that "Japan reverses it in both scenarios". Both wrong. 12 of
> 1,260 cells reverse, **all under moderate uptake**: Japan in all ten years and
> **the Netherlands** in years 9–10, which that message omits entirely. Japan's
> *max*-uptake rows do not reverse at all. The original claims were checked against
> the min and max of each year's range, which establishes neither an elementwise
> ordering nor which rows are involved.
>
> Derived in `diagnostics/imputation_and_drug_populations.py`.

**Why Japan and the Netherlands reverse.** `pi > pi_dose` exactly when survival is
positively correlated with `eer_diff` across adherers — when the patients cutting
the most intake are also the ones more likely to be alive. That correlation is
weakly positive almost everywhere: median **+0.042**, maximum +0.127 (Korea).
Japan and the Netherlands sit essentially at zero, **−0.008** and **−0.002**, and
under moderate uptake land marginally negative.

So the reversal is not a property of those countries' demography — it is what a
correlation indistinguishable from zero does. The reading that matters if `pi` is
ever used for a per-country claim: because the correlation is weak everywhere,
`pi` and `pi_dose` are near interchangeable at country level, and the **sign** of
their difference carries no interpretation for a country near zero. It would be a
mistake to read Japan's negative value as evidence that heavy intake-reducers there
die sooner.

**Direction — this change is CONSERVATIVE. It reduces food savings and lowers
every ratio.** Isolated by holding everything else fixed and moving only the
weighting (`diagnostics/compare_pi_effect.py`), mean CI, drug folded in, N = 40:

| quantity | pi off | pi on | movement |
|---|--:|--:|--:|
| 10-yr food savings, max (Mt) | 521.8331 | 501.7655 | **−20.0676 (−3.85%)** |
| 10-yr food savings, mod (Mt) | 267.1340 | 256.6671 | **−10.4669 (−3.92%)** |
| ratio food:survivor, max | 1.9212 | 1.8474 | **−0.0738 (−3.85%)** |
| ratio food:survivor, mod | 1.8594 | 1.7865 | **−0.0729 (−3.92%)** |
| annual food, max, year 1 (Mt) | 52.141 | 51.857 | −0.284 (−0.54%) |
| annual food, max, year 10 (Mt) | 52.235 | 48.128 | **−4.107 (−7.86%)** |
| **year-10 annual ratio, max** | **1.0297** | **0.9488** | **crosses below 1** |
| minimum-country ratio, max | 1.2986 HUN | 1.2053 HUN | −0.0933 |
| survivor emissions (Mt) | 271.6114 | 271.6114 | **0 (bit-identical)** |

The effect compounds with year, from −0.5% at year 1 to −7.9% at year 10, because
`pi` falls monotonically. **The qualitative change worth noting: the year-10
annual flow ratio crosses below 1.** Under the old model the annual food saving
still exceeded annual survivor emissions in year 10; under survival weighting it
does not. The cumulative ten-year ratio stays above 1 at 1.85×.

The drug term moves the other way and partly offsets. Treated-user-years over ten
years are `initial_users x sum_y pi_dose(y)`; that sum is **9.6268** (max) and
**9.6221** (mod) rather than 10, so the 10-year drug charge falls 3.3% on the
break-even set (12.90038 → 12.47709 Mt). A smaller drug subtraction raises net
food savings slightly.

**Controls.** The 32 countries whose survivor emissions the mortality source swap
left bit-identical isolate `pi` from that earlier change. 31 of them are in the
break-even set (Taiwan is excluded — see below). Their survivor emissions are
identical across the two runs, confirming the isolation, and their own aggregate
ratio moves 1.9094 → 1.8354, **−3.87%** — matching the global −3.85%. Per-country
ratio change runs −2.43% to −7.18%, median −3.71%.

**Implementation note — exact, not approximate.** The equilibrium is re-solved for
each year at `delta * pi(t)` rather than the year-1 answer being scaled by
`pi(t)`. Measured before choosing: 1,008 rows enter
`result_df.apply(_compute_equilibrium)`, the apply costs **0.4 s** against a
**33 s** whole call, so ten years adds **4.0 s** — 12% of one call. Scaling
instead would be wrong by 0.048% (median), 0.142% (worst row) and **0.062% on the
global aggregate** at `pi = 0.86`. That is the same order as the smallest real
correction recorded in this document (~0.1%), so the approximation would inject
error indistinguishable from a finding, to save four seconds.

`annual_food_savings_t` becomes the **year-1** saving, with
`annual_food_savings_t_Y1..Y10` alongside and `actual_reduction_Y{t}`,
`carbon_savings_t_Y{t}`, `expected_demand_reduction_Y{t}` on `result_df`. The
unsuffixed columns are year 1 so single-value consumers keep working and keep
meaning something. Figure captions that said "annual" or "/ year" now say
"year 1", because year 1 is the *largest* year of the series and "annual" would
read as an overstatement. `scripts/build_supplement_table.py` runs
`survival_weighted=False` on purpose: every row of that table is an instantaneous
t = 0 reduction, `pi(0) == 1`, and its calorie row comes from the raw cohort EER
gap — putting tonnage and emissions on a year-1 basis would have left three rows
of one table on two different bases. Its numbers are unchanged (emissions reduced
after rebound 54.2 / 27.8 Mt).

**The `annual x 10` trap — nine sites, one of which no literal-`10` grep finds.**
Cumulative food is `sum_y F*pi(y)`, not `10 x F`. Eight sites multiplied an annual
food quantity by a literal 10: `breakeven_analysis.py` (3),
`diet_sensitivity/analysis.py` (3), `combined_analysis.py` (1),
`sensitivity_overview.py` (1). All now sum `total_food_savings_10yr`, which
`compute_breakeven` already accumulated correctly. The ninth,
`generate_waterfall_figure.py`, multiplies by the *named constant*
`HORIZON_YEARS` on all three legs (naive, rebound, actual) — invisible to a
search for `* 10`. Its naive leg also needed a new per-year column, being a
pre-rebound quantity not derivable from `carbon_savings_t`. Left overstated, these
would have inflated ten-year food by about 4%.

`compute_breakeven` now accumulates both sides per year: food from the series,
dosing from `drug_emissions_t_Y{t}`. Treated-user-years use an **anchored** form —
sum the ten weights, then multiply the headcount once — because accumulating
`initial x weight` ten times moved the result 2–3 ULP at `pi_dose == 1`, where the
weighting must be an exact no-op. Ten exact `1.0`s sum to exactly `10.0`, so the
anchored form reproduces the legacy `initial * 10` bit for bit. Same lesson as
`adjust_survivor_decline`; the comment there says the same thing.

`load_food_shock_survival_weight` reads with `float_precision="round_trip"`, and
this is load-bearing rather than tidy. pandas defaults to the fast `xstrtod`
converter, which parsed **721 of 1,890** cells of this table one ULP off an exact
`strtod`. `pi` multiplies every food number, so a 1-ULP parse wobble would
propagate into every downstream figure.

**A defect in the preceding commit, found and fixed here.** That commit put numpy
arrays in `.attrs["missing_masks"]`. pandas compares `attrs` with `==` when it
finalises a `concat`, so *any* caller concatenating a frame derived from
`compute_individual_survival_diffs` raised "truth value of an array is
ambiguous". The masks are now optional `mx_missing_Y{t}` columns; `.attrs` keeps
only the int dict, which compares cleanly.

**Verification.** Every gate was declared before its run.
- Opening gate, re-run against the live lookup: `Delta(t) == term1 + term2` to
  **4.5e-14** worst relative and `term1(t)/term1(0) == pi(t)` to **3.9e-16**, over
  63 × 2 × 15, bar 1e-12. `term2/diff_Yt` lands at 3,040–3,046 kcal/day, a
  baseline `eer`, confirming term 2 belongs to the survivor side.
- `pi` regression: the production builder reproduces the reviewed values at
  **exactly 0 of 1,890 cells**. It first showed 721 cells differing at 1 ULP;
  diagnosed rather than relaxed — the reference is a CSV and the default parser was
  the whole cause (mixed sign 364/357, mean signed difference 4e-19, no drift).
  Subset-vs-full-frame is exactly 0.0, so summing over rows whose weight is an
  exact zero is genuinely inert.
- Null at `pi == 1.0`, full new code path (ten solves) vs the pre-`pi` function:
  `annual_food_savings_t` **0 of 112**; every year equal to year 1, **0 cells**;
  `result_df`'s 15 shared numeric columns **0 of 15,120**;
  `survival_weighted=False` **0 of 112**. Anchored to a committed column as well
  as an in-process reference: `net_emissions_with_drug.csv`'s
  `annual_food_savings_gross_t` reproduces at **0 of 112**.
  (`diet_sensitivity_results.csv` differs on all 112 — that blob was stale, as
  this document already recorded.)
- Downstream null: drug legacy lever **0 of 630**; per-year drug series constant
  at `pi_dose == 1` and equal to the old function, **0 cells**;
  `compute_breakeven` at `pi == 1` vs the old one, **0 of 3,136 across 28 numeric
  columns**. Three of these failed first and the causes were fixed, not the bars —
  the anchored user-years form, a harness bug where the old breakeven resolved
  `build_drug_emissions` to the live module and so compared `pi_dose` against 1,
  and one bar that was genuinely too tight (below).
- The one gate not held to 0.0, declared as such in advance: summed series vs
  `annual x 10` at `pi == 1` is **2 ULP**, not the 1 ULP first written. `cum_food`
  is ten sequential additions where the old form multiplied once, and the error
  bound for *n* additions grows like *n*·eps, so a few ULP at n = 10 is expected;
  the "≤1 ulp" row in the brief covers a restructured expression, not a change to
  an n-term accumulation. Unlike the drug term this one cannot be anchored: under
  real `pi` the ten addends genuinely differ. Measured 2.00 ULP, 25 positive / 25
  negative, aggregate agreeing to **1.5e-16** relative.
- Survivor-side invariant: `pi` must not touch it. `survivor_food_factor.csv`
  rebuilt under survival weighting is **bit-identical, 0 of 3,790 cells**, and
  survivor emissions are identical across the `pi` off/on runs. `consumption_ghg`
  therefore did not need re-running.
- Baseline food emissions must be delta-independent: **exactly identical** with
  weighting off and on (6514.542208459 Mt), and `initial_eql_quantity` /
  `carbon_intensity_t` differ on 0 of 1,008 cells.

**Tornado — the parameter ranking survives.** Carbon intensity remains the
dominant axis, diet preference second, survivor GHG decline a distant third:

| axis | range before (Mt) | range after (Mt) |
|---|--:|--:|
| Carbon intensity (all foods) | 571.773 | 566.265 |
| Diet preference | 296.053 | 294.961 |
| Survivor GHG decline | 20.404 | 21.042 |

The decline stays the least influential at 3.7% of the carbon-intensity range
(3.6% before). Note these two columns differ by N as well as by `pi` — 35
countries before, 40 after — because the mortality source swap changed the
country set; they are not a clean `pi`-only comparison, unlike the table above.

**The price level cancels out of the equilibrium solve.** Worth recording because
the FAOSTAT food CPI is an index normalised to each country's own base year, so if
the level entered substantively every country's output would depend on an arbitrary
normalisation. By inspection of `_compute_equilibrium` it does not. With
`Cs = Q0 / P0^Es` and `Cd = Q0 / P0^Ed`, the market-clearing condition
`Cs·P^Es = Cd·P^Ed·(1+δ)` reduces to `(P/P0)^(Es−Ed) = 1+δ`, so

```
P/P0    = (1 + delta) ^ ( 1      / (Es - Ed))
Q_new/Q0 = (1 + delta) ^ ( Es    / (Es - Ed))
```

Both `Q0` and `P0` drop out: the equilibrium quantity **ratio** is a function of
the demand shock and the two elasticities alone. `actual_reduction`,
`rebound_effect`, `rebound_effect_percent` and `carbon_savings_t` are therefore all
invariant to the price index's base year. The only price-dependent output is
`P_eq_new = P0 · (1+δ)^(1/(Es−Ed))`, which is in index units and is written but
never read — nothing downstream consumes it.

One latent fragility, currently inert, now commented in the code: the solver's
`bracket=[1e-3, 1e3]` is in **level** units even though the answer is scale-free,
and a failed solve is swallowed by a bare `except` into a NaN that groups to a
silent zero. Seven countries in the FAOSTAT file have a Dec-2022 food CPI at or
above 1e3 (Venezuela at 9.1e11, then ZWE, LBN, SDN, SSD, ARG, SUR) and would fail
that way. **None is in the modelled set**, whose 53 priced countries span
103.247–190.779, a factor of five inside the bracket. So nothing is affected today,
but a country set that ever reached high-inflation economies would lose them
silently.

**Coverage: Taiwan, and why the break-even set is 40 and not 41.** 41 countries
have non-zero survivor person-years *and* both OECD factor components, but
break-even also requires positive food savings, and **TWN** has
`annual_food_savings_t` exactly `0.0`. Cause traced rather than assumed: TWN has
FAOSTAT tonnage for all 9 food groups, a carbon intensity, elasticities and a
demand shock, but FAOSTAT's **Consumer Price Index** dataset has no rows for
"China, Taiwan Province of" — so `price` is NaN, `Cs`/`Cd` are NaN, the solver
returns NaN and the group-by sum yields 0.0. This is pre-existing and unrelated to
`pi` or to the mortality swap: it also explains the old numbers, where 36
survivor-qualifying countries produced aggregates over 35. Three distinct coverage
gaps now sit on this model and are worth keeping separate, and all three belong in
the methods coverage paragraph: **22** countries lack an OECD demand-based
per-capita factor and so cannot be charged survivor emissions; **3** lack a usable
FAOSTAT Consumer Price Index, so their demand shock never solves and they carry no
food savings; and **none** now lacks mortality.

The three unpriced countries are **GUY, NRU and TWN**, and the gap is not the same
in each: NRU and TWN are absent from the Consumer Price Indices file entirely,
while **GUY is present with 297 rows but has no December-2022 food-index row** — a
gap inside the file rather than absence from it. An earlier version of this entry
said only TWN, which was wrong: it was found by inspecting the one country that
surfaced in a count, not by asking which rows fail to solve. All three stay
excluded on that basis regardless of anything else in this entry.

**Imputation exposure: the donor-imputed countries are retained.**

**The criterion is the imputation donor, not the region.** Where a country's UN region contains exactly one Human Life-Table member, the
regional median for that region *is* that country, so every imputed recipient
carries the donor's life table verbatim rather than a blend. Israel is one such
donor, and the seven countries carrying its schedule (ARE, BHR, CYP, KWT, OMN,
QAT, SAU) are the instance that touches the reported set. Of those, **ARE, CYP and
SAU** have an OECD per-capita factor and enter a ratio.

The mechanism is general — other single-country regions exist and have their own
donors — and no attempt has been made here to enumerate them.
`countries_with_donor_life_table` takes any donor, so the arm generalises by
changing one argument.

The other four of the seven have no OECD per-capita factor and so cannot move a
ratio. The set is derived from
`final_df_imputed.pkl` by `survival_weighting.countries_with_donor_life_table`, not
listed: a hardcoded list is a claim about the imputation that nothing keeps true,
and the region-based equivalent went stale the moment the mortality source
changed. **Cyprus falls inside the set by construction** and is excluded with the
rest when the arm is run — it is the most defensible of the seven on other
grounds, but that belongs in the methods text, not in a code-level exception.

**The difference is immaterial to every conclusion.** Excluding all three in-set
countries, max uptake: cumulative 10-year ratio 1.8474 → 1.8364 (**−0.59%**),
year-10 annual ratio 0.9488 → 0.9437 (−0.54%), N 40 → 37. Moderate uptake: 1.7865
→ 1.7752 (−0.63%), 0.9191 → 0.9138 (−0.58%). Hungary and Lithuania stay binding in
their respective scenarios; the cumulative ratio stays near 1.84×; the year-10
annual ratio stays below 1. Half a percent on a ratio, and no qualitative change.

**So the decision rests on other grounds, and those grounds are coverage.** Saudi
Arabia alone is **1.20 percentage points** of world GDP; the three together are
**1.73**, taking the complete-data sample from **58.96%** to **57.22%** of the
global economy. Coverage is a claim the paper makes on its own account, so trading
it away to be rid of a proxy we distrust is a real cost — and one paid for no
change in any reported conclusion. The countries are therefore retained, the
imputation limitation is stated in methods either way, and the exclusion arm is
available behind a single argument.

An earlier draft of this note argued the opposite way round — that excluding makes
the headline slightly worse, so keeping is the choice. That is choosing a method by
the number it produces and it is struck from the record. The immateriality is what
licenses the decision; coverage is what decides it.

`breakeven_analysis.print_imputation_sensitivity()` prints the comparison on every
run rather than leaving it a one-off, and
`diagnostics/imputation_and_drug_populations.py` re-derives the donor set from the
pickle and reports the GDP at stake alongside the ratios.

**Age-89 ceiling, restated as a horizon bound.** `pi` is built to 15 years because
that is the last year with complete mortality coverage for treated patients:
adherers span ages 18–74 and the rate lookup ends at 89. At year 16 they fall off
the table, where the guarded `.fillna(0)` raises rather than silently granting
immortality. The food model still runs 10. **Extending past 15 years needs more
mortality data, not a code change.**

**Regenerated in one pass:** break-even (all figures), the three diet-sensitivity
modules, the sensitivity suite and overview, the tornado, the drug-effect
accounting, all waterfalls, the emissions and dashboard figures, the supplement
table, `survivor_manuscript_numbers`, and both reference snapshots. This is the
single pass the "Known stale outputs" section above was deferring; that section is
now resolved.

---

## GDP-share script derives its country sets instead of hardcoding them

**What was wrong.** `gdp_share_of_global_economy.R` serves one manuscript
sentence — what share of the world economy the modelled countries cover — and
hardcoded three ISO lists to do it: a 35-country complete-data subset, a
13-country "missing OECD factor" list and a 5-country "missing life table" list.

All three went stale the moment the mortality source changed. The complete-data
subset is now **40**, and the five countries that had no life table — ARE, CYP,
MLT, ROU, SAU — are **exactly** the ones that gained one. Nothing connected the
script to that, so it would have gone on reporting a share for a country set the
model no longer uses, with no signal that it had drifted.

**Numerical effect.** The stale lists give **56.92%** of 2022 world GDP over 35
countries. The derived sets give **58.96%** over 40 — a **+2.04 percentage-point**
understatement, of which Saudi Arabia alone is 1.20 pp. The food-data sample is
unchanged at **59.72%** over 53, since none of the five was ever missing food data.

**Correct behaviour.** Both sets are read from `net_emissions_with_drug.csv` using
the same filter break-even and every downstream aggregate applies — positive food
savings, positive survivor emissions, finite ratio — kept in one function here so
the two definitions cannot drift apart. Change which countries are excluded
anywhere upstream and this script follows without an edit.

Exclusion reasons are derived too, from the survivor-emissions file: a country can
fail to reach a ratio for want of an OECD per-capita factor or for want of
mortality data, and which it is matters when writing the limitation up. Currently
all 13 excluded countries lack an OECD factor and none lacks mortality — the
5-country mortality exclusion the old script encoded no longer exists.

**Guards, because a silently wrong share is the failure mode here.** It errors if
either input CSV is absent, naming the command that builds it; errors if the two
uptake scenarios disagree on the country sets, since the manuscript quotes a single
number and that would need a decision rather than a silent choice; warns if a
country is excluded for a reason it cannot classify rather than filing it under a
default; and warns that the totals are *understated* if any country has no GDP
match, rather than reporting a quiet sum over NAs. It also reports the 10
countries that have survivor data but no food savings (AND, ASM, BMU, BRN, GRL,
GUY, NRU, PRI, SGP, TWN), which belong in neither share.

**Verification.** Run against the regenerated outputs: 53 rows, 0 missing GDP
matches, no warnings, derived sets 53/40/13 matching what
`net_emissions_with_drug.csv` and the survivor file independently report. The
per-country table and both totals are printed, so the manuscript number is
visible rather than inferred.

Documented in the README as step 10, including why it derives rather than lists
and what the stale version would have said.

---

## Two silent-failure paths in the equilibrium solve

**What was wrong.** A country whose demand shock could not be solved disappeared
into a zero. Two mechanisms, both quiet:

1. `_compute_equilibrium` wrapped the solve in `except Exception: pass` and
   returned NaN.
2. The groupby that builds `annual_food_savings_t` used a bare `.sum()`, and an
   **all-NaN group sums to exactly 0.0** in pandas.

Together those turn "this country cannot be computed" into "this country saves
nothing", which no filter and no reader can distinguish. **Three countries had
been sitting in the outputs at exactly zero food savings for the life of the
model** with no line of output: **GUY, NRU and TWN**.

**Correct behaviour.** `min_count=1` on both the headline groupby and the per-year
series, so an all-NaN group returns NaN. On its own that is barely an improvement —
the downstream `> 0` filters drop a NaN exactly as they dropped a zero — so the
load-bearing half is a new guard, `_report_unsolved`, which names every such
country and which input it is missing, and attaches the list to
`result_df.attrs["unsolved"]`. It prints rather than raises: an absent price index
is a permanent input gap, so raising would break every run over a known condition.

`_compute_equilibrium` now separates its two failure modes. NaN inputs return NaN
without pretending to solve; a genuine solver failure or non-convergence on finite
inputs **raises**, naming the country, food group, scenario and every input.

**Measured before changing, because narrowing an except that fires would break the
run.** Instrumented over all 10,080 solver calls
(`diagnostics/check_except_paths.py`):

| path | fires |
|---|--:|
| `except Exception` | **0** |
| `if result.converged` falling through | **540** |

So the bare except caught nothing — `brentq` does not raise on these inputs, it
returns `converged=False`. All 540 non-convergences have a NaN argument, i.e. 54
rows (3 countries × 9 food groups × 2 scenarios) × 10 years. **The except was not
the path doing the damage**, which is worth recording: fixing only the thing that
looked wrong would have left the actual silent path in place.

**The unpriced three are not one gap but two.** An earlier entry in this document
said only TWN lacked a price index. Wrong, and wrong because it was found by
inspecting the one country that happened to surface in a count rather than by
asking which rows fail to solve. NRU and TWN are absent from the FAOSTAT Consumer
Price Indices file entirely; **GUY is present with 297 rows but has no
December-2022 food-index row**. Same symptom, different gap.

**Verification.** Gates declared before the run
(`diagnostics/null_check_min_count.py`), against the pre-change pipeline in one
process:
- `result_df`, 45 shared numeric columns × 1,008 rows: **0 cells differ**. The
  narrowed except is arithmetically inert.
- Only 6 of 112 `food_savings` rows move, all **exactly 0.0 → NaN**, all three
  unsolvable countries × two scenarios. Nothing else moves.
- Every **reported** aggregate is bit-identical, difference **exactly 0.0**: rows
  with food > 0 (53), the annual food sum, N complete (40), 10-year food, 10-year
  survivor, the cumulative ratio and the minimum-country ratio, both scenarios.
- **No aggregate became NaN** — 0 of them. pandas `.sum()` skips NaN, so an
  aggregate cannot acquire one; the risk was the reverse, a value silently ceasing
  to be counted, which is what the two movements below are.

**Two movements, accepted and named rather than absorbed.** Both are consumers
that read `annual_food_savings_t` with no `> 0` filter, found by auditing all 55
read sites:
- `generate_emissions_figure.py` drew a zero-length bar for each unsolvable
  country and sorted them *first*, as though they were the countries saving least.
  It now filters `> 0` like every other consumer: three degenerate bars go, and the
  country ordering shifts by those three positions.
- `diet_sensitivity/analysis.py:289` sums the break-even frame unfiltered, where
  these countries carry `0 − drug` and so a **negative** value. Dropping them moves
  that total by **+15,427.225174 t** (0.0154 Mt). It is a console VALIDATION line,
  written to no CSV.

**Regenerated in the following commit**, as a full pass rather than a partial one,
with the movement set predicted in writing beforehand
(`diagnostics/predicted_movement.txt`) and checked afterwards
(`diagnostics/verify_predicted_diff.py`). Seven files moved and the actual set
matched the prediction exactly, with no eighth file and no fourth cause:

| file | movement |
|---|---|
| `net_emissions_with_drug.csv` | 108 cells, 20 columns |
| `combined_sensitivity_results.csv` | 258 cells, 15 columns |
| `diet_sensitivity_results.csv` | 60 cells, 4 columns |
| `all_sensitivity_overview_country_ratios.csv` | TWN row dropped, 41 → 40 |
| `diet_sensitivity_ratio_comparison.csv` | TWN row dropped, 41 → 40 |
| `combined_sensitivity_ratio_comparison.csv` | TWN row dropped, 41 → 40 |
| `figures/emissions_saved_by_country.png` | 56 → 53 bars |

Every differing cell belongs to GUY, NRU or TWN; **every one moved to NaN**, none
to a different finite value; and every retained pivot row is bit-identical. GUY and
NRU were already absent from the three pivots, their ratios having already been
NaN. `reference/metrics.py` passes at **exactly 0.0 on all 47 values** with no
`--write`, the break-even set is still **40**, and complete-data GDP coverage is
still **58.956583%**. The reference snapshots were not touched by the pass.

---

## Rebound-decomposition figure — collapsed x-axis ticks and clipped value labels

**Status: code changed, figure not yet regenerated.** Both fixes are in
`data_visualization/generate_rebound_figure.py`; `figures/rebound_decomposition.png`
is still the old render. Deliberate — regenerating needs a full
`compute_food_savings()` pass, and it is being held so other figure changes can
ride the same run.

**Not a survivorship regression.** `generate_rebound_figure.py` is absent from
`git diff main...survivorship`, so it is byte-identical to `main`. The PNG *was*
regenerated on this branch, so the branch surfaced the defect but did not cause
it. It has been latent since the file was written.

**What was wrong (1) — one format for nine panels.** Lines 128–131 applied a
single formatter to every axis in the grid:

```python
ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
```

`{x:,.0f}` suits column C (kt CO₂eq, up to 15,490) and destroys columns A and B,
which are Mt/year and peak below 4: the locator picks fractional ticks and the
formatter rounds every one to an integer. **5 of 9 panels carried duplicate tick
labels.** The four that read correctly escaped only because their ticks happened
to be integral.

Replayed the committed locator/formatter pair against each panel's real range
(`diagnostics/check_rebound_axis_format.py`), which reproduces the committed
render exactly:

| panel | ticks the locator chose | rendered as | after |
|---|---|---|---|
| Meat A | 0, 0.25, 0.5, 0.75, 1.0 | **`0, 0, 0, 1, 1`** | `0.0, 0.2, 0.4, 0.6, 0.8, 1.0` |
| Meat B | 0, 0.15, 0.30, 0.45 | `0, 0, 0, 0` | `0.0, 0.2, 0.4, 0.6` |
| Meat C | 0, 4000 … 16000 | `0, 4,000, … 16,000` | `0, 5,000, 10,000, 15,000` |
| Dairy A | 0, 1, 2, 3 | `0, 1, 2, 3` | `0, 1, 2, 3, 4` |
| Dairy B | 0, 0.5, 1.0, 1.5, 2.0 | `0, 0, 1, 2, 2` | `0.0, 0.5, 1.0, 1.5, 2.0` |
| Dairy C | 0, 1500 … 6000 | `0, 1,500, … 6,000` | `0, 2,000, 4,000, 6,000` |
| Cereals A | 0, 0.4, 0.8, 1.2 | `0, 0, 1, 1` | `0.0, 0.5, 1.0, 1.5` |
| Cereals B | 0, 0.15 … 0.60 | `0, 0, 0, 0, 1` | `0.0, 0.2, 0.4, 0.6` |
| Cereals C | 0, 250, 500, 750 | `0, 250, 500, 750` | `0, 200, 400, 600, 800, 1,000` |

`0, 0, 0, 1, 1` is exact, including 0.5 → "0": Python's format rounds half to
even.

**The underlying data was never implicated.** Bars and their printed value labels
read from the same `vals` array (line 93), but the value labels use a *separate*
adaptive format at lines 116–122 (`≥100` → 0dp, `≥1` → 1dp, else 2dp) — which is
why `0.10`, `3.8` and `15,490` are right and match their bar lengths. Only the
tick formatter was broken. Nothing in `compute_food_savings()` is involved.

Also inspected and **not** a defect: in column A the countries are not monotonic
(Meat shows Saudi Arabia 0.05 below Romania 0.03). Each row is ranked once by
**actual reduction** (lines 73–77) and that order is reused across all three
columns, as the module docstring states. Correct as designed.

**Correct behaviour (1).** `steps=[1, 2, 5, 10]` constrains the locator to
decimal-friendly ticks (0.2 / 0.5 / 5000, never 0.15 / 0.25), and the decimals
are then derived per-axis from the ticks that axis actually received, via a new
`_tick_decimals()`. Two bars, both declared before the check and both met at
**0/9**: no panel may contain a duplicate label, and every label must name its
own tick exactly. The second bar killed the first attempt at this fix, which
deduplicated correctly but printed tick `0.25` as "0.2" — a fix that silently
mislabels an axis is worse than the collapse it replaces, being wrong instead of
merely ambiguous.

`nbins` was raised 5 → 6. At `nbins=5` under the new limits Meat A thins to three
ticks; at 8, Dairy C over-densifies to eight. 6 gives 4–6 ticks per panel.

**What was wrong (2) — value labels drawn across the frame.** Line 115 places each
label at `v + 3%` of the row maximum while the axes extended only to
`max × 1.05`, so **in all nine panels the longest bar's label started inside the
frame and ran out of it** — USA rendering as a broken "1 0" in Meat A, `15,490`
bleeding past the spine in Meat C.

**Correct behaviour (2).** `ax.set_xlim(0, vmax * 1.18)` after the label loop,
guarded on `vmax > 0`. This also seats the bars flush on the spine instead of
leaving matplotlib's 5% negative left margin.

**The two fixes interact, and were re-verified together rather than separately.**
Widening `xlim` changes the range the tick locator sees (`-0.05→1.05 × max`
becomes `0→1.18 × max`), so the tick choices verified for fix 1 did not carry
over untouched. `check_rebound_axis_format.py` models the post-fix limits and
both bars still hold at 0/9. Verifying fix 1 against the old limits would have
signed off on tick positions the shipped code never produces.

**Bar for the deferred regeneration, declared now:** axis labels and the right-hand
margin change; data does not. The 36 printed bar values must be identical to the
current figure, and the country order within each row unchanged.

---

## Orphaned figure removed — `comparison_before_after_recategorize.png`

Deleted (`git rm`, staged, uncommitted). It documented the P&N recategorization,
a change already accepted, and was left sitting in `figures/` where it reads as a
live output.

Nothing generated it and nothing referenced it. `git log --all -S` for the
filename returns **no commit on any branch that ever put that string in a file**;
it is absent from the README figure inventory and from every `.py`, `.R`, `.ipynb`
and `.md` in the tree. Its whole history is one commit, `1d2c4f7` ("Refactor,
remove tesst folder"), where it lands as a plain `A` — not a rename out of
`test/` like the four CSVs in that same commit. So it was produced by hand and
committed without its generator. **No code was deleted, because none exists.**
`build_carbon_intensity.py`, which performs the recategorization the figure
illustrated, is untouched and remains a live input to
`Food data/carbon_intensity{,_p10,_p90}.csv`.

Three further tracked PNGs in `figures/` are orphaned the same way and were
**left in place** pending a decision: `sensitivity_ci_scenarios.png` and
`sensitivity_country_range.png` (written only by `Price rebound model.ipynb`
cells that `savefig` to the deleted `test/`, inside the notebook marked
do-not-run) and `breakeven_stock_flow_all_countries.png` (superseded output name;
`plot_stock_flow_all_countries()` now writes `breakeven_stock_all_countries.png`
and `breakeven_flow_all_countries.png`).

---

## The simulated BMI distribution does not reproduce its NCD-RisC input — MEASURED, NOT FIXED

> **Unresolved.** This is a measurement of the upstream R stage, not a
> correction. Nothing was changed and no output was regenerated. The remedy is a
> separate decision. Recorded here because it moves published numbers.

**What was tested.** `fit_bmi_mixture()` in `legacy/R_scripts/Data_Cleaning9.8.R`
(line 316) does not fit a distribution to the NCD-RisC category shares. It draws
skew-normal components at fixed midpoints `c(17, 19.25, 22.5, 27.5, 32.5, 37.5,
42.5)` with `scale = width/2.5`, concatenates them in the observed proportions,
runs a KDE (`dpik` bandwidth, `range.x = c(13, 60)`), and applies a
moving-average smoother of width `max(7, round(15 * max(props) / 0.4))` grid
cells. Every one of those stages moves mass across the category boundaries. The
question is whether the population that comes out still carries the proportions
that went in.

**Bars, declared before the run.** Fail if the population-weighted realized
BMI >= 30 share differs from target by more than **1.0 pp**; fail if any
category's mean deviation across strata exceeds **2 standard errors** from zero.
Noise floor: at 500 individuals per stratum a realized share near 0.05 has a
binomial sd of 0.98 pp, so individual per-stratum deviations under roughly 2 pp
are expected and mean nothing — the signal is a systematic mean across strata.

**Method.** Baseline `bmi`, never `new_bmi`. `max_uptake` only (the saved object
binds both scenarios and each individual appears twice; baseline `bmi` was
verified bit-identical across the two, and 1,890,000 rows halve to 945,000
exactly). Binned on `c(0, 18.5, 20, 25, 30, 35, 40, Inf)`, left-closed. Compared
at **ISO x Sex x Age_Group**, the level the mixture was fitted at, because
aggregating first lets opposing errors cancel. NCD-RisC side filtered
`Year > 2021` as the R script does, which keeps 2022 alone; its seven shares sum
to 1.00000000 on every row. **1,890 strata matched with zero asymmetry** — 63
ISO x 2 sexes x 15 age groups, nothing present on one side and missing on the
other.

**Result — FAIL on both bars.**

Per-category mean deviation across the 1,890 strata (realized − target, pp):

| category | mean | SE | t | n > +2pp | n < −2pp |
|---|--:|--:|--:|--:|--:|
| under 18.5 | +1.6981 | 0.0327 | +51.97 | 624 | 0 |
| 18.5–20 | +1.3481 | 0.0334 | +40.33 | 580 | 44 |
| 20–25 | −2.3054 | 0.0881 | −26.18 | 221 | 902 |
| 25–30 | −2.3087 | 0.0776 | −29.76 | 215 | 1057 |
| 30–35 | +0.4407 | 0.0491 | +8.97 | 430 | 247 |
| 35–40 | +1.6369 | 0.0372 | +44.04 | 666 | 7 |
| >= 40 | −0.5096 | 0.0307 | −16.62 | 13 | 166 |
| **>= 30** | **+1.5679** | 0.0525 | **+29.89** | 813 | 118 |

All seven categories sit 9 to 52 standard errors from zero. This is not binomial
noise. Population-weighted over the modelled 1.00 billion people, **BMI >= 30 is
0.28467 realized against 0.26901 target: +1.57 pp absolute, +5.82% relative.**
Per country, **51 of 63 overstate by more than 1.0 pp and only 2 understate by
more than 1.0 pp** — ASM (−1.76) and NRU (−1.09), the two highest-obesity
countries in the set.

**The mechanism is flattening toward uniform, not outward leakage from the 25–30
bin.** Deviation is a near-linear decreasing function of the target share: over
13,230 stratum-category cells, corr = **−0.684**, deciles run monotonically from
+0.79 pp in the sparsest to **−5.64 pp** in the densest, and the OLS zero-crossing
sits at target share **0.142857 — which is 1/7, the uniform share across seven
categories, to six decimals.** Every category holding more than 1/7 of the mass
loses; every category holding less gains. That is why 20–25 and 25–30 lose
equally rather than the second leaking into the first, and why the largest single
gainer is `under 18.5`. `>= 40` is the one category moving against the pattern
(−0.51 pp on a 0.039 share); it is the boundary bin, where the `range.x` cap, the
0.001/0.999 trim and the boxcar filter's zeroed edge NAs all act before
renormalisation. **This run does not isolate which of the four smoothing stages
contributes what** — that is a separate diagnostic and the attribution above is
deliberately not claimed as settled.

**Consequence for published numbers.** Eligibility is `bmi >= 30`, or `bmi >= 27`
with type-2 diabetes, so an inflated obese share inflates the treated population
and every food-savings, mortality and emissions number computed from it. Because
flattening is a relative-error amplifier at low shares, the damage is worst
exactly where obesity is lowest: **JPN +36.2% and KOR +35.4% relative** on the
BMI >= 30 share, then TWN +22.4%, FRA +19.5%, SWE +18.1%. `[SETH: whether this
warrants refitting the mixture, resampling from the empirical category shares
directly, or a stated caveat — not a call this measurement makes.]`

**What could not be checked.** The NCD-RisC age-specific country BMI files carry
only category prevalences and their uncertainty intervals; **there is no mean BMI
column**, and no mean-BMI file is present in the `Lancet` directory or read by
the R script. So the complementary failure mode — right shares, wrong mean, or
the reverse — cannot be distinguished from this source. Simulated side alone:
population-weighted mean BMI 27.1164, per-stratum range 20.41 to 36.94.

**Verification.** `diagnostics/bmi_mixture_reproduction_check.py`, read-only;
writes `diagnostics/reports/bmi_mixture_reproduction_check.md` plus per-stratum
detail in `diagnostics/bmi_mixture_realized_shares.csv` (both gitignored). The
NCD-RisC inputs are **not in this repository** — `/Lancet/` is gitignored and
absent, as the README's "Known gaps and warts" records — so the script reads them
from the researcher's canonical store and takes a `LANCET_DIR` override.
`test/full_simulation_results8.rds`, the save path at line 585 of the R script,
does not exist; the root `.rds` (the line-637 load path) and
`final_df_imputed.pkl` were verified to carry a bit-identical baseline `bmi`
vector, which establishes the root `.rds` as what is upstream of the Python
pipeline.

**Commit(s).** None. Diagnostic added, no model or pipeline code touched.

---

## Regeneration — the simulated population and the hazard ladder

**Branch:** `regeneration`, from `survivorship`.

Three defects fixed, two modelling gaps closed, two bugs repaired. Every number
in the manuscript moves. The work was sequenced so the population was verified
before anything downstream consumed it, and so each change is attributable
separately.

### What changed

| # | change | effect |
|---|---|---|
| 2.1 | BMI: piecewise-linear CDF through the NCD-RisC cumulative points, with a four-knot Kitahara class III top band, replacing the point-cloud + KDE + moving-average mixture | dominant |
| 2.2 | Height matched to attained height by birth cohort, not 19-year-olds in 2019 for everyone | small |
| 2.3 | Age-related height loss subtracted (Sorkin et al. 1999, printed coefficients, per individual from age 30) | small |
| 2.6 | Scenario-string bug: the adherence diagnostic filtered on labels the code never assigned, so every rate it printed was `NaN` | diagnostic only |
| 2.7 | Save path and load path unified behind one constant | see below |
| 2.8 | Per-stratum seeding, `GLOBAL_SEED = 43` | makes runs order-independent |
| 2.9 | Common random numbers across the two uptake scenarios | moves moderate only |
| 2.10 | Four diagnostic blocks (plus a fifth found here) were pooling scenarios; `eer_effects` was also unweighted | the "~7%" figure |
| 2.15 | Continuous hazard above BMI 40, anchored to preserve 2.76 | small, both directions |

### Headline movements (OLD -> Run D)

| quantity | OLD | new |
|---|--:|--:|
| annual food savings, yr 1, max (Mt) | 53.9421 | 50.7726 |
| **CUM-10Y** food:survivor, max | 1.8474 | 1.9428 |
| **Y10-FLOW** food:survivor, max | 0.9488 | 0.9989 |
| average HR reduction, max (%) | 18.6 | 17.21 |
| extra survivors at year 10, max | 3,150,000 | 2,787,760 |
| population-weighted BMI >= 30 deviation | +1.5665 pp | -0.2251 pp |

The BMI construction accounts for -2.96 Mt of the -3.17 Mt food-savings move;
cohort height -0.17, height loss -0.04, section 2.15 +0.0004. Full attribution
in `diagnostics/reports/phase5_reconciliation.md`.

### Provenance corrections to the plan

The regeneration plan described the save/load defect as `test/...rds` versus a
root read. Measured: **no script on disk has ever written `test/`** except the
repo's own copy of `Data_Cleaning9.8.R`, and `test/` does not exist. Three
copies of the script exist and two distinct `.rds` artefacts. The repo's
artefact is bit-identical (md5 `1b56ef87...`) to
`OneDrive/.../Code and data/full_simulation_results8.rds`; a second, different
file sits at `OneDrive/.../Data Analysis/` (md5 `ad7663f2...`) carrying
`Maximum uptake`/`Moderate uptake` labels. The divergence was real but by
another route. See `diagnostics/reports/phase0_recon.md` section 2.

### Artefacts

`full_simulation_results9.rds` is the regenerated population.
`full_simulation_results8.rds` is **retained unchanged** as the
pre-regeneration baseline; it is read by no production path.
`final_df_imputed9.pkl` is the population with the imputed `mortality_rate`
column reattached — built by `diagnostics/build_population_pickle.py`, which
lifts the existing `(ISO, age, Sex)` map off the committed pickle rather than
re-running the imputation. The imputation does not depend on the simulated
population, and the only script that writes the pickle is the superseded
notebook.

### Bars that were mis-specified in the plan and were corrected

Each was diagnosed before being changed, and each replacement is at least as
sharp as what it replaced.

- **G4 adherence.** A flat `+/- 0.01`, set without calibrating to `n`. Replaced
  with an analytic 4-SE bar from the eligible count: `+/-0.0018` / `+/-0.0042`
  at production `n`, five times tighter.
- **G7 `new_bmi`.** "Within 2 ULP" pairwise. `new_bmi` is a three-rounding
  chain, so two correct runs can sit ~4 ULP apart; measured 3. Replaced with
  the absolute test — each run within 2 ULP of the exact `bmi*(1-effect)` —
  which passes with zero violations. All 3-ULP rows were treated rows;
  untreated rows max at exactly 2, the shorter chain.
- **G3 cohort height.** "Attained height must decrease with age group" does not
  hold per-country and cannot: 51 of 126 country x sex groups show a local
  increase, and Italian male attained height peaks at the 1994 cohort. Replaced
  with the aggregate direction.
- **G9 assertion 3.** "Monotonically non-decreasing across the whole BMI range."
  The ladder is J-shaped and dips twice below BMI 20. The pre-change ladder was
  verified to carry the same two dips in the same places, so section 2.15
  introduces none.

### An R/Python 1-ULP divergence that reaches nothing

After section 2.15, `HR_TOP_K` differs between the runtimes by 1 ULP (R
`1.3957877646878392`, Python `...89`) because `sum()` and `numpy.sum()`
associate the four-term reduction differently — `1.4^0.2` is bit-identical, so
`pow()` is not the cause. Both satisfy the declared `1e-6` assertion.

This reaches no published figure, verified rather than assumed:
`Mortality_model2.R` writes only to `test/`, which does not exist; its last
write is line 555 while `bmi_hazard_ratio()` is defined at line 596, so the
ladder's results are never persisted even there; and no production script reads
`mortality2.rds` or `final_df_imputed.rds`. Documented curiosity, not a live
risk, and the two sides are deliberately not being forced to reduce in the same
order.

### `phase5_metrics_runC.json` was overwritten and recovered, not recomputed

Run D is Run C's population with the section 2.15 ladder, so it reads the same
`.rds`. Re-running the Phase 5 harness with label `C` therefore overwrote the
Run C column with Run D values. **It was recovered in full from
`diagnostics/phase5_runC.log`**, which prints all 47 metrics; the recovered key
set was verified identical to Run D's before writing. It was **not recomputed**,
so the Run C column is the original computation rather than a fresh one — worth
knowing if that column is ever audited.

`diagnostics/phase5_run_columns.py` now takes `--out-label` and refuses to
overwrite an existing metrics file without `--force`.

### Country exclusions (section 2.13) are measurable, not held externally

63 simulated; 56 have FAOSTAT tonnage; 53 have a FAOSTAT food CPI; 40 have an
OECD GHGFP factor. P&N carbon intensity and the elasticity files kill nobody —
both carry a row for every modelled country by construction. **No country is
lost to a name mismatch**: zero unmapped `Area` values in the 2022 FBS, and the
seven mapping-absent countries appear nowhere in the FBS in any year. One
residue: **TWN** fails the CPI stage yet carries positive survivor emissions,
so it contributes to the denominator and never to the numerator. Full trace in
`diagnostics/reports/exclusion_attrition.md`.

**Commit(s).** `3712f84` (structural ladder refactor, committed on
bit-identical output per the plan's stated exception), `3420e8f` (artefact
naming), `a59aa83` (section 2.15 behavioural).

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

Mortality source swap. The partition gate needs the pre-change function to
compare against; it is not left in the tree, so extract it first and delete it
afterwards:

```
git show <rev-before-this-commit>:data_visualization/deterministic_mortality.py \
    > data_visualization/_head_dm.py
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.verify_mortality_source_swap
rm data_visualization/_head_dm.py

# then the two production runs, in this order
PYTHONUTF8=1 C:\Python314\python.exe -m data_visualization.deterministic_mortality
UN_WPP_DIR=... PYTHONUTF8=1 C:\Python314\python.exe -m data_visualization.consumption_ghg

# coverage read straight off the regenerated CSVs, no model run
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.readout_survivor_coverage
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.compare_survivor_totals
```

Survival weighting (pi). Gates first, then the artefact, then the pass:

```
# opening gate: the term-1/term-2 decomposition, against the live lookup
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.verify_algebra

# build pi and regression-gate it against the reviewed values
PYTHONUTF8=1 C:\Python314\python.exe -m data_visualization.survival_weighting
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.compute_pi

# route measurement: cost of exact vs error of approximate
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.measure_pi_route

# nulls at pi == 1. Both need the pre-pi modules; extract, run, delete.
git show <rev-before-this-commit>:data_visualization/pipeline.py \
    > data_visualization/_head_pipeline.py
git show <rev-before-this-commit>:data_visualization/drug_footprint.py \
    > data_visualization/_head_drug.py
git show <rev-before-this-commit>:data_visualization/breakeven_analysis.py \
    > data_visualization/_head_breakeven.py
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.null_check_pi
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.null_check_downstream
rm data_visualization/_head_pipeline.py data_visualization/_head_drug.py \
   data_visualization/_head_breakeven.py

# invariants: pi must not reach the survivor side or the baseline
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.verify_survivor_invariant
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.check_baseline_independence

# the isolated pi effect, and the Taiwan coverage fact
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.compare_pi_effect
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.name_dropped_country
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.diagnose_twn

# donor-imputed set, the two drug populations, and the Japan/NLD reversal
#   (writes diagnostics/reports/*.md rather than printing a wide table)
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.imputation_and_drug_populations

# the two silent-failure paths, and the null for min_count=1
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.check_except_paths
git show <rev-before-this-commit>:data_visualization/pipeline.py     > data_visualization/_head_pipeline.py
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.null_check_min_count
rm data_visualization/_head_pipeline.py
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.imputation_and_drug_populations

# sign of (pi - pi_dose) elementwise, and which way substituting pi moves the drug
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.check_pi_dose_direction

# simulated BMI shares against the NCD-RisC input they were drawn to reproduce
#   (read-only; needs the NCD-RisC CSVs, which are not in this repository --
#    set LANCET_DIR if they are not at the default canonical-store path)
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.bmi_mixture_reproduction_check

# full regeneration, then refresh + verify the reference snapshots
sh diagnostics/run_full_pass.sh
PYTHONUTF8=1 C:\Python314\python.exe -m reference.metrics --write
```

Rebound-figure axis fixes. The tick check needs no model run — it replays the
locator/formatter pair against each panel's range, so it stands alone and can be
run before the regeneration:

```
PYTHONUTF8=1 C:\Python314\python.exe diagnostics\check_rebound_axis_format.py

# the regeneration itself, still outstanding
UN_WPP_DIR=... PYTHONUTF8=1 C:\Python314\python.exe -m data_visualization.generate_rebound_figure
```
