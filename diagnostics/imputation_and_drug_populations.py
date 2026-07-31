"""Three loose ends, answered together and written to markdown.

1. The two drug percentages in the pi commit (-3.73% and -3.28%) are over
   DIFFERENT country sets. Establish which each is over.
2. Derive the exclusion criterion as "imputed life table identical to the donor's"
   rather than a hardcoded region list, and recompute the sensitivity over the
   whole derived set.
3. Why Japan reverses the pi > pi_dose ordering: how eer_diff and survival
   correlate there.

Reads committed outputs plus the pickle. Runs no model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_visualization.breakeven_analysis import _complete_data_subset
from data_visualization.deterministic_mortality import (
    compute_individual_survival_diffs,
    load_inputs,
)
from data_visualization.drug_footprint import ANNUAL_DRUG_KG_CO2E_PER_USER
from data_visualization.pipeline import ROOT
from data_visualization.survival_weighting import (
    countries_with_donor_life_table,
    load_food_shock_survival_weight,
)
from diagnostics.report import Report

DONOR = "ISR"
rep = Report(
    "imputation_and_drug_populations",
    "Populations behind the two drug percentages, the derived imputation-donor "
    "exclusion set, and why Japan reverses the pi / pi_dose ordering.",
)

be = pd.read_csv(ROOT / "data_result" / "net_emissions_with_drug.csv",
                 float_precision="round_trip")
drug = pd.read_csv(ROOT / "data_result" / "drug_emissions_by_country.csv",
                   float_precision="round_trip")

# ── 1. Which population is which ─────────────────────────────────────────
rep.h2("1. The two drug percentages are over different country sets")
rep.text(
    "`sum_y pi_dose(y)` is a weighted average, so its shortfall against 10 "
    "depends on which countries are averaged. The two figures quoted in "
    "`9fe9cdd` are both correct and neither follows from the other."
)
rows = []
for sc in ("max_uptake", "mod_uptake"):
    d = drug[drug["scenario"] == sc]
    all_1yr = d["drug_emissions_1yr_t"].sum()
    all_10yr = d["drug_emissions_10yr_t"].sum()
    keep = set(_complete_data_subset(be, scenario=sc)["ISO"])
    k = d[d["ISO"].isin(keep)]
    k_1yr = k["drug_emissions_1yr_t"].sum()
    k_10yr = k["drug_emissions_10yr_t"].sum()
    rows.append({
        "scenario": sc,
        "population": f"all {d['ISO'].nunique()} modelled ISO",
        "implied sum pi_dose": all_10yr / all_1yr,
        "shortfall vs 10": (all_10yr / all_1yr / 10 - 1) * 100,
        "10-yr drug (Mt)": all_10yr / 1e6,
        "legacy x10 (Mt)": all_1yr * 10 / 1e6,
    })
    rows.append({
        "scenario": sc,
        "population": f"{len(keep)}-country break-even set",
        "implied sum pi_dose": k_10yr / k_1yr,
        "shortfall vs 10": (k_10yr / k_1yr / 10 - 1) * 100,
        "10-yr drug (Mt)": k_10yr / 1e6,
        "legacy x10 (Mt)": k_1yr * 10 / 1e6,
    })
tab1 = pd.DataFrame(rows)
rep.table(tab1)
rep.text(
    "So **-3.73%** is the shortfall over all 63 modelled countries and "
    "**-3.28%** is the shortfall over the 40-country break-even set. The "
    "break-even set is the smaller shortfall because it excludes the small, "
    "younger-population states whose `pi_dose` falls fastest."
)

# ── 2. Derived exclusion set ──────────────────────────────────────────────
rep.h2("2. Exclusion criterion derived from the imputation donor")
donor_set = countries_with_donor_life_table(DONOR)
rep.text(
    f"Countries whose imputed `(age, Sex) -> mortality_rate` map is identical to "
    f"**{DONOR}**'s, derived from `final_df_imputed.pkl` rather than listed: "
    f"`{donor_set}` ({len(donor_set)} countries)."
)
in_be = sorted(set(donor_set) & set(_complete_data_subset(be, scenario="max_uptake")["ISO"]))
rep.text(
    f"Of those, inside the break-even set: `{in_be}`. The rest have no OECD "
    f"per-capita factor and so never reach a ratio."
)

gdp = pd.read_csv(ROOT / "data_result" / "gdp_share_of_global_economy.csv")
gsub = gdp[gdp["ISO3"].isin(in_be)][["ISO3", "Country", "share_of_world_pct"]]
rep.h3("GDP coverage at stake")
rep.table(gsub.sort_values("share_of_world_pct", ascending=False))
complete_share = gdp.loc[gdp["in_complete_subset"], "share_of_world_pct"].sum()
rep.kv({
    "complete-data coverage, retained": complete_share,
    "coverage if the donor set is excluded": complete_share - gsub["share_of_world_pct"].sum(),
    "coverage given up (percentage points)": gsub["share_of_world_pct"].sum(),
})

rep.h3("Ratio effect of excluding the whole derived set")
rows = []
for sc in ("max_uptake", "mod_uptake"):
    full = _complete_data_subset(be, scenario=sc)
    for label, v in (("retained", full), ("excluded", full[~full["ISO"].isin(donor_set)])):
        years = np.arange(1, 11)
        cf = np.array([v[f"cum_food_Y{y}"].sum() for y in years], dtype=float)
        cm = np.array([v[f"cum_mort_Y{y}"].sum() for y in years], dtype=float)
        af, am = np.diff(cf, prepend=0.0), np.diff(cm, prepend=0.0)
        i = v["ratio_food_to_mort"].idxmin()
        rows.append({
            "scenario": sc, "arm": label, "N": len(v),
            "cum ratio 10yr": cf[-1] / cm[-1],
            "y10 annual ratio": af[-1] / am[-1],
            "min ratio": float(v.loc[i, "ratio_food_to_mort"]),
            "min ISO": v.loc[i, "ISO"],
        })
tab2 = pd.DataFrame(rows)
rep.table(tab2)
for sc in ("max_uptake", "mod_uptake"):
    a = tab2[(tab2.scenario == sc) & (tab2.arm == "retained")].iloc[0]
    b = tab2[(tab2.scenario == sc) & (tab2.arm == "excluded")].iloc[0]
    rep.bullet(
        f"{sc}: cum 10-yr {(b['cum ratio 10yr']/a['cum ratio 10yr']-1)*100:+.2f}%, "
        f"y10 annual {(b['y10 annual ratio']/a['y10 annual ratio']-1)*100:+.2f}%, "
        f"binding country {a['min ISO']} -> {b['min ISO']}"
    )
rep.text("")

# ── 3. Japan ──────────────────────────────────────────────────────────────
rep.h2("3. Why Japan reverses the pi / pi_dose ordering")
rep.text(
    "`pi` weights survival by `w * eer_diff`, `pi_dose` by `w`. So "
    "`pi > pi_dose` exactly when survival is positively correlated with "
    "`eer_diff` across adherers -- the patients cutting the most intake are the "
    "ones more likely to be alive. Japan is the only country where that "
    "correlation is negative."
)
pi = load_food_shock_survival_weight(horizon=10, column="pi")
dose = load_food_shock_survival_weight(horizon=10, column="pi_dose")
gap = (pi - dose)
neg = gap[(gap < 0).any(axis=1)]
rep.text(f"Cells with `pi < pi_dose`: {int((gap < 0).to_numpy().sum())} of {gap.size}, "
         f"confined to `{sorted({i for i, _ in neg.index})}`.")

sim = load_inputs()
ind = compute_individual_survival_diffs(
    sim, horizon=10, survival_columns=True, extra_columns=("eer_diff",),
    population_weighted=False,
)
adh = ind[ind["eer_diff"] != 0]
rows = []
for iso in sorted(set(adh["ISO"])):
    for sc in ("max_uptake", "mod_uptake"):
        s = adh[(adh["ISO"] == iso) & (adh["scenario"] == sc)]
        if len(s) < 3:
            continue
        w = s["weighting"].to_numpy()
        x = s["eer_diff"].to_numpy()
        y = s["p_sg_Y10"].to_numpy()
        mx = np.average(x, weights=w)
        my = np.average(y, weights=w)
        cov = np.average((x - mx) * (y - my), weights=w)
        sx = np.sqrt(np.average((x - mx) ** 2, weights=w))
        sy = np.sqrt(np.average((y - my) ** 2, weights=w))
        rows.append({
            "ISO": iso, "scenario": sc,
            "weighted corr(eer_diff, p_sg_Y10)": cov / (sx * sy) if sx * sy else np.nan,
            "mean age of adherers": np.average(s["age"].to_numpy(), weights=w),
            "mean eer_diff": mx,
        })
corr = pd.DataFrame(rows)
rep.h3("Weighted correlation between eer_diff and 10-year survival, by country")
rep.text("Five most negative and five most positive:")
rep.table(corr.nsmallest(5, "weighted corr(eer_diff, p_sg_Y10)"))
rep.table(corr.nlargest(5, "weighted corr(eer_diff, p_sg_Y10)"))
jpn = corr[corr["ISO"] == "JPN"]
rep.h3("Japan against the rest")
rep.table(jpn)
rep.kv({
    "countries with a negative correlation, max_uptake": int(
        (corr[(corr.scenario == "max_uptake")]["weighted corr(eer_diff, p_sg_Y10)"] < 0).sum()),
    "countries with a negative correlation, mod_uptake": int(
        (corr[(corr.scenario == "mod_uptake")]["weighted corr(eer_diff, p_sg_Y10)"] < 0).sum()),
    "median correlation across all countries": float(
        corr["weighted corr(eer_diff, p_sg_Y10)"].median()),
})

rep.save()
