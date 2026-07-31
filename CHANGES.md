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

## Known stale outputs — RESOLVED

> **All clear as of the survival-weighting commit.** The single regeneration pass
> this section was waiting for has run: every output below, plus the reference
> snapshots, was regenerated and `reference/metrics.py` now passes at exactly 0.0
> on all 47 values. `metrics.py`'s stale *configuration* was reconciled in the
> same pass. Nothing in this section is outstanding; it is kept as the record of
> why the staleness was allowed to stand for three commits.

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

> **Correction.** The commit message for `9fe9cdd` states this backwards — it says
> using `pi` "would have understated it", and separately calls `pi_dose`
> "consistently the lower" when the ordering has 12 exceptions. Both claims were
> checked only against the min/max of each year's range, which does not establish
> an elementwise ordering and does not fix a sign. The text above is the corrected
> record; the commit message cannot be edited after the fact.

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
gaps now sit on this model and are worth keeping separate: **22** countries lack an
OECD factor, **1** (TWN) lacks a FAOSTAT price index, and **none** lacks mortality.

**Imputation exposure: the headline does not rest on Israel's life table.** Five
of the countries the mortality swap restored were imputed from a UN region whose
only Human Life-Table member is Israel, so their life table is literally Israel's.
Seven countries carry Israel's schedule bit-for-bit — ARE, BHR, CYP, KWT, OMN,
QAT, SAU — but only **ARE, CYP and SAU** have an OECD per-capita factor and so
enter a ratio at all; the other four cannot move one. Cyprus is defensible as
taking Israel's values; the two Gulf states are the exposure worth testing.

Dropping ARE and SAU, max uptake: cumulative 10-year ratio 1.8474 → 1.8369
(**−0.57%**), year-10 annual ratio 0.9488 → 0.9439 (**−0.51%**), binding country
Hungary either way. Moderate uptake: 1.7865 → 1.7758 (−0.60%), 0.9191 → 0.9140
(−0.55%), Lithuania either way. Together the two are 2.0% of ten-year food savings
and 1.4% of survivor emissions.

So they are retained and the limitation is stated rather than the countries
dropped. Note the movement is **downward**: both sit above the global ratio (ARE
2.76×, SAU 2.50×), so excluding them would make the headline slightly worse, and
keeping them is the marginally less conservative choice — by half a percent. No
qualitative conclusion turns on it: the cumulative ratio stays near 1.84×, the
year-10 annual ratio stays below 1, and the binding country is untouched.

`breakeven_analysis.print_imputation_sensitivity()` prints this on every run
rather than leaving it a one-off, and
`diagnostics/imputation_sensitivity.py` derives the Israel-identical list from the
pickle rather than trusting a hardcoded one — re-run it if
`final_df_imputed.pkl` is ever rebuilt.

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

# which countries share Israel's imputed life table, and what they are worth
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.imputation_sensitivity

# sign of (pi - pi_dose) elementwise, and which way substituting pi moves the drug
PYTHONUTF8=1 C:\Python314\python.exe -m diagnostics.check_pi_dose_direction

# full regeneration, then refresh + verify the reference snapshots
sh diagnostics/run_full_pass.sh
PYTHONUTF8=1 C:\Python314\python.exe -m reference.metrics --write
```
