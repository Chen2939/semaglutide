"""Section 2.15 step 1 -- DECISION DIAGNOSTIC. Read, then stop.

No refactor, no commit, no gates. This touches nothing in the pipeline and
produces no artefact that anything downstream consumes. Everything after step 1
happens only on an explicit decision to proceed.

THE DEFECT. The hazard ladder assigns 2.76 to all ``bmi >= 40`` with no upper
bound. Two consequences: a bounded published estimate (top category 40.0-59.9)
is applied to an unbounded bin; and because the bin has no floor, weight loss
INSIDE it produces a hazard ratio of exactly 1.0 between baseline and
treatment. Integrating over the weight-loss distribution, 36.5% of top-band
adherers stay above 40 and receive zero modelled survival benefit -- in the
range where the real gradient is steepest.

SHAPE. Substitute ``get_raw_bmi_hazard_ratio`` for a version carrying
``hr_top()`` above 40 and call the EXISTING survival routine. The HR columns do
not live in the pickle; they are computed inside that routine from ``bmi`` and
``new_bmi``. Rebuilding the loop by hand would produce a second implementation
of the thing being tested.

WHAT ONLY THE RATIO BUYS. ``deterministic_mortality`` builds
``hr_conversion_factor = semaglutide_bmi_hr / baseline_bmi_hr - 1`` and
``sg_mx = mx * (1 + hr_conversion_factor)``. Only the ratio enters; the level
never does, and there is no calibration constant anywhere in the conversion.
So the aggregate treated-versus-baseline figure below is a genuine OUTPUT, not
a target, and nothing about it licenses adjusting the change to restore the old
one. ``HR_TOP_ANCHOR`` cancels entirely for anyone whose baseline and treated
BMI both sit above 40 -- their ratio is just ``1.4^(-0.118 * bmi / 5)``. What K
actually buys is the size of the step at the 40 boundary, and therefore the
benefit credited to crossers.

Per section 1.1, no expectation about the direction or size of the aggregate
change is formed or stated before this runs. The two channels below are the
same order of magnitude, so that instruction is doing real work here.

ASCII only.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_visualization import deterministic_mortality as dm  # noqa: E402

PKL = ROOT / "final_df_imputed9.pkl"
OUT = ROOT / "diagnostics" / "reports" / "s215_step1_decision.md"

lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    lines.append(s)


# ---------------------------------------------------------------- constants
# Shared with the BMI top-band construction (sec 2.1.2). Derived from the same
# participant counts, never hardcoded -- that shared derivation is what stops
# the two sections drifting apart.
CLASS3_N = np.array([6803.0, 1978.0, 627.0, 156.0])
CLASS3_SHARE = CLASS3_N / CLASS3_N.sum()

HR_TOP_BASE = 2.76
HR_PER_5 = 1.40

# K is the composition-weighted mean of 1.4^((b-40)/5) over the top band. Under
# the sec 2.1.2 CDF each sub-band is uniform, so the mean over a five-unit
# segment starting at 40 + 5j is 1.4^j * (1.4 - 1) / ln(1.4).
_SEG = (HR_PER_5 - 1.0) / math.log(HR_PER_5)
SEG_MEANS = np.array([_SEG * HR_PER_5 ** j for j in range(4)])
HR_TOP_K = float((SEG_MEANS * CLASS3_SHARE).sum())
HR_TOP_ANCHOR = HR_TOP_BASE / HR_TOP_K

assert abs(HR_TOP_K - 1.395788) < 1e-6, HR_TOP_K
assert abs(HR_TOP_ANCHOR - 1.977378) < 1e-6, HR_TOP_ANCHOR


def hr_top(b):
    return HR_TOP_ANCHOR * HR_PER_5 ** ((np.minimum(b, 60.0) - 40.0) / 5.0)


_ORIGINAL = dm.get_raw_bmi_hazard_ratio


def patched_hazard_ratio(bmi: pd.Series) -> np.ndarray:
    """The existing ladder below 40; the continuous form above it."""
    base = _ORIGINAL(bmi)
    b = np.asarray(bmi, dtype=float)
    return np.where(b >= 40.0, hr_top(b), base)


# ---------------------------------------------------------------- reporting
def summarise(individual: pd.DataFrame) -> pd.DataFrame:
    diff_cols = [f"diff_Y{y}" for y in range(1, 11)]
    rows = []
    for scenario, s in individual.groupby("scenario", sort=False):
        treated = s[s["adheres_to_treatment"] == True]  # noqa: E712
        w = treated["weighting"].to_numpy()
        red = 1 - treated["semaglutide_bmi_hr"] / treated["baseline_bmi_hr"]
        rows.append({
            "scenario": scenario,
            "avg_hr_reduction_pct": (red * w).sum() / w.sum() * 100,
            "treated_users": w.sum(),
            "extra_survivors_y10": s["diff_Y10"].sum(),
            "total_person_years_saved": s[diff_cols].sum(axis=1).sum(),
        })
    return pd.DataFrame(rows)


def main() -> int:
    if not PKL.is_file():
        raise SystemExit(f"missing {PKL}; run diagnostics/build_population_pickle.py")

    say("# s215_step1_decision")
    say()
    say("Section 2.15 step 1. **Decision diagnostic only** -- nothing is "
        "committed, no pipeline artefact is written, and nothing downstream "
        "reads anything produced here.")
    say()
    say(f"Population: `{PKL.name}` (Run C).")
    say()

    say("## The ladder")
    say()
    say("| constant | value |")
    say("|---|--:|")
    say(f"| K, composition-weighted mean of 1.4^((b-40)/5) | {HR_TOP_K:.6f} |")
    say(f"| HR_TOP_ANCHOR = 2.76 / K | {HR_TOP_ANCHOR:.6f} |")
    say()
    say("| BMI | old HR | new HR |")
    say("|---|--:|--:|")
    for b in (40, 45, 50, 55, 60):
        say(f"| {b} | 2.7600 | {float(hr_top(b)):.4f} |")
    say()
    say(f"Discontinuity at the 40 boundary narrows from "
        f"**{2.76 - 1.94:.4f}** to **{HR_TOP_ANCHOR - 1.94:.4f}**.")
    say()

    sim = pd.read_pickle(PKL)

    # --- old ---------------------------------------------------------------
    dm.get_raw_bmi_hazard_ratio = _ORIGINAL
    old_ind = dm.compute_individual_survival_diffs(sim, population_weighted=True)
    old = summarise(old_ind)

    # --- new ---------------------------------------------------------------
    dm.get_raw_bmi_hazard_ratio = patched_hazard_ratio
    new_ind = dm.compute_individual_survival_diffs(sim, population_weighted=True)
    new = summarise(new_ind)
    dm.get_raw_bmi_hazard_ratio = _ORIGINAL

    say("## Aggregate, old ladder against new")
    say()
    for col, label, fmt in [
        ("avg_hr_reduction_pct", "average HR reduction (%)", "{:.4f}"),
        ("extra_survivors_y10", "extra survivors alive at year 10", "{:,.0f}"),
        ("total_person_years_saved", "cumulative 10-yr person-years saved", "{:,.0f}"),
        ("treated_users", "treated users (unchanged by construction)", "{:,.0f}"),
    ]:
        say(f"**{label}**")
        say()
        say("| scenario | old | new | change | % change |")
        say("|---|--:|--:|--:|--:|")
        for sc in old["scenario"]:
            o = float(old.loc[old.scenario == sc, col].iloc[0])
            n = float(new.loc[new.scenario == sc, col].iloc[0])
            pct = (n / o - 1) * 100 if o else float("nan")
            say(f"| {sc} | {fmt.format(o)} | {fmt.format(n)} | "
                f"{fmt.format(n - o)} | {pct:+.2f}% |")
        say()

    # --- mechanism ---------------------------------------------------------
    say("## Mechanism -- the change moves in both directions")
    say()
    mx = sim[sim["scenario"] == "max_uptake"]
    adh = mx[mx["adheres_to_treatment"] == True]  # noqa: E712
    top = adh[adh["bmi"] >= 40]
    w = top["weighting"].to_numpy()
    stay = (top["new_bmi"] >= 40).to_numpy()
    sub4045 = (top["bmi"] < 45).to_numpy()
    gain = (top["new_bmi"] > top["bmi"]).to_numpy()

    say("Top-band adherers, max_uptake, population-weighted:")
    say()
    say("| quantity | value |")
    say("|---|--:|")
    say(f"| top-band adherers (weighted) | {w.sum():,.0f} |")
    say(f"| share staying >= 40 after treatment | **{(w*stay).sum()/w.sum():.4f}** "
        f"(plan predicts 0.3645) |")
    say(f"| share in the 40-45 sub-band | {(w*sub4045).sum()/w.sum():.4f} "
        f"(plan predicts 0.7113) |")
    say(f"| share whose new_bmi EXCEEDS baseline (weight gainers) | "
        f"{(w*gain).sum()/w.sum():.4f} |")
    say(f"| mean baseline HR over 40-45, new ladder | "
        f"{float(np.average(hr_top(top['bmi'][sub4045]), weights=w[sub4045])):.4f} "
        f"(was 2.76) |")
    say()
    say("The three channels, all real and pulling against each other:")
    say()
    say("1. The 40-45 sub-band's baseline hazard falls from 2.76 to a mean of "
        "about 2.35. These people already crossed out of the bin under the old "
        "ladder, so a LOWER baseline makes their modelled benefit SMALLER. They "
        "are ~71% of the top band.")
    say("2. Those who stay above 40 gain a benefit where they previously had "
        "exactly none.")
    say("3. Weight GAINERS now receive a modelled hazard increase within the "
        "top band, where the old flat bin gave them a ratio of exactly 1.0. "
        "Correct behaviour, but new.")
    say()

    # --- pmin binding ------------------------------------------------------
    n_bind_new = int((mx["new_bmi"] > 60).sum())
    n_bind_bmi = int((mx["bmi"] > 60).sum())
    say("## Reported, not gated -- where pmin(b, 60) binds")
    say()
    say(f"- rows where `bmi` > 60: **{n_bind_bmi}** (the terminal knot "
        "guarantees zero)")
    say(f"- rows where `new_bmi` > 60: **{n_bind_new}** of {len(mx):,} "
        f"({n_bind_new/len(mx):.2e}) -- negative draws of `individual_effect` "
        "push a handful above the terminal knot. Do not assert this never "
        "happens; that assertion fails on correct code at a seed-dependent rate.")
    say(f"- max realized `bmi` / `new_bmi`: {mx['bmi'].max():.4f} / "
        f"{mx['new_bmi'].max():.4f}")
    say()
    say("---")
    say()
    say("**STOP HERE.** Section 2.15 proceeds only on an explicit decision. Nothing "
        "above has been applied to the R ladder or to "
        "`deterministic_mortality.get_raw_bmi_hazard_ratio`.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
