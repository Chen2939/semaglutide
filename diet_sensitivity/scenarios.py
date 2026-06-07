"""
Diet-composition sensitivity scenarios for semaglutide food-demand analysis.

Each scenario is a dict mapping ``final_food_group`` names to demand-shock
*multipliers* relative to the country-level uniform baseline shock computed
from the EER (estimated energy requirement) change in the R simulation.

A multiplier of 1.0 means that food group gets the same percentage reduction as
the uniform baseline.  A multiplier of 1.5 means 50 % more reduction; 0.5 means
half as much reduction.  The calibration step in ``pipeline.py`` normalises these
multipliers so the *calorie-weighted* average multiplier equals 1, preserving the
total calorie reduction for each country × scenario exactly.

────────────────────────────────────────────────────────────────────────────────
Scenario 1 – ``fatty_food_down``
Source: Blundell et al. (2017), Diabetes Obes Metab, doi:10.1111/dom.12932
        Gibbons et al. (2021), Diabetes Obes Metab, doi:10.1111/dom.14255

Key evidence:
• Ad libitum snack-box intake from high-fat, non-sweet foods was ~35 % lower
  with semaglutide vs placebo, while overall energy intake fell ~24 %.
• The Leeds Food Preference Task (LFPT) confirmed lower explicit liking AND
  lower implicit wanting for high-fat, non-sweet foods.
• Fat-rich breakfast produced greater satiety/satiation differences than a
  standard breakfast.

Mapping:  Meat (high-fat, non-sweet), Dairy (high-fat), and Fats and oils
receive a multiplier of 1.5 (≈ 35/24 ≈ 1.46, rounded up conservatively).
All other groups receive a neutral multiplier determined by the calibration to
ensure total calories are preserved.
────────────────────────────────────────────────────────────────────────────────
Scenario 2 – ``cereal_sweets_up``
Source: Hironaka et al. (2025), Diabetes Vasc Dis Res, doi:10.1177/14791641251318309

Key evidence:
• In Japanese T2D patients on oral semaglutide (n = 23, 3 months), total energy
  fell significantly; carbohydrate intake showed the greatest absolute reduction
  (starchy cravings).
• CoEQ showed significant reductions in cravings for *sweet*, *chocolate-flavoured*,
  and *starchy* foods.
• Animal protein intake change was NOT statistically significant (p = 0.053).

Mapping:  Cereals (starchy/carb-heavy) and Sweets (sweet/chocolate) receive
multiplier 1.5; Meat receives 0.5 (less reduction, consistent with animal
protein not being significant).  Other groups receive the neutral multiplier.
────────────────────────────────────────────────────────────────────────────────
Background:
  Gibbons et al. (2021), PMID 33184979 — confirms similar pattern for oral
  semaglutide: reduced ad libitum energy 38.9 %, enhanced satiety after
  fat-rich breakfast, improved craving control.
"""

from typing import Dict

# Nine FAOSTAT final_food_group names used throughout the pipeline.
FOOD_GROUPS = [
    "Cereals",
    "Dairy",
    "Eggs",
    "Fats and oils",
    "Fish",
    "Fruit and vegetables",
    "Meat",
    "Other",
    "Sweets, confectionery, and sweetened beverages",
]

# Scenario definitions: food_group → multiplier relative to the uniform shock.
# An empty dict means the uniform shock is applied to all groups (baseline).
SCENARIOS: Dict[str, Dict[str, float]] = {
    # ── Baseline: uniform reduction across all food groups ──────────────
    "baseline_uniform": {},

    # ── Scenario 1: fatty / high-fat foods fall more ────────────────────
    # Motivated by: Blundell et al. (2017), Gibbons et al. (2021)
    "fatty_food_down": {
        "Meat":          1.50,
        "Dairy":         1.50,
        "Fats and oils": 1.50,
    },

    # ── Scenario 2: cereals & sweets fall more, meat falls less ─────────
    # Motivated by: Hironaka et al. (2025)
    "cereal_sweets_up": {
        "Meat":                                              0.50,
        "Cereals":                                           1.50,
        "Sweets, confectionery, and sweetened beverages":   1.50,
    },
}
