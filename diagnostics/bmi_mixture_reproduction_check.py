"""Does the simulated BMI distribution reproduce the NCD-RisC input proportions?

READ-ONLY measurement. Modifies no script and regenerates no pipeline output.

`fit_bmi_mixture()` in `legacy/R_scripts/Data_Cleaning9.8.R` does not fit a
distribution to the NCD-RisC category shares. It draws skew-normal components at
fixed midpoints c(17, 19.25, 22.5, 27.5, 32.5, 37.5, 42.5) with scale = width/2.5,
concatenates them in the observed proportions, runs a KDE (`dpik` bandwidth,
`range.x = c(13, 60)`), and applies a moving-average smoother of width
max(7, round(15 * max(props) / 0.4)) grid cells. Each stage moves mass across the
category boundaries. This measures whether the realized simulated shares match
the input shares, per ISO x Sex x Age_Group stratum.

DECLARED BARS, set before the run and not adjusted afterwards:

  FAIL if the population-weighted realized BMI >= 30 share differs from target
       by more than 1.0 percentage point.
  FAIL if any category's mean deviation across strata exceeds 2 standard errors
       from zero.
  PASS if neither, and per-stratum deviations look like binomial noise around
       zero with no systematic direction.

Noise floor: 500 individuals per stratum, so a realized share near 0.05 carries a
binomial sd of 0.98 pp. Individual per-stratum deviations under roughly 2 pp mean
nothing; the signal is a systematic mean across strata.

The NCD-RisC inputs are not in this repository -- `/Lancet/` is gitignored and
absent, exactly as "Known gaps and warts" in the README records. LANCET_DIR below
points at the researcher's canonical store; override it with the LANCET_DIR
environment variable.

    PYTHONUTF8=1 C:\\Python314\\python.exe -m diagnostics.bmi_mixture_reproduction_check
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from diagnostics.report import Report

ROOT = Path(__file__).resolve().parent.parent
LANCET_DIR = Path(os.environ.get(
    "LANCET_DIR",
    r"C:\Users\sethw\OneDrive - University of Waterloo\Semaglutide"
    r"\Data Analysis\Code and data\Lancet",
))

F_FEMALE = LANCET_DIR / "NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv"
F_MALE = LANCET_DIR / "NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv"
F_MAP = LANCET_DIR / "lancet_column_names.xlsx"
F_RDS = ROOT / "full_simulation_results8.rds"
F_PKL = ROOT / "final_df_imputed.pkl"
OUT_CSV = ROOT / "diagnostics" / "bmi_mixture_realized_shares.csv"

BINS = [0, 18.5, 20, 25, 30, 35, 40, np.inf]
CATS = [
    "BMI_under_18.5", "BMI_18.5to20", "BMI_20to25", "BMI_25to30",
    "BMI_30to35", "BMI_35to40", "BMI_over_40",
]
OBESE = ["BMI_30to35", "BMI_35to40", "BMI_over_40"]
GRP = ["ISO", "Sex", "Age_Group"]

rep = Report(
    "bmi_mixture_reproduction_check",
    "Realized simulated BMI category shares against the NCD-RisC input shares "
    "they were drawn to reproduce, per ISO x Sex x Age_Group stratum.",
)


def mtime(p: Path) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))


# ── Declared bars, recorded before any number is computed ────────────────
rep.h2("Declared bars")
rep.text("Set before the run and not adjusted afterwards.")
rep.bullet("**Fail** if population-weighted realized BMI >= 30 differs from "
           "target by more than 1.0 percentage point.")
rep.bullet("**Fail** if any category's mean deviation across strata exceeds "
           "2 standard errors from zero.")
rep.bullet("**Pass** if neither, and per-stratum deviations look like binomial "
           "noise around zero with no systematic direction.")
rep.text("Noise floor: at 500 per stratum a realized share near 0.05 has a "
         "binomial sd of 0.98 pp, so per-stratum deviations under roughly 2 pp "
         "are expected and mean nothing.")

# ── Inputs ───────────────────────────────────────────────────────────────
rep.h2("Files used")
for p in (F_FEMALE, F_MALE, F_MAP, F_RDS, F_PKL):
    if not p.exists():
        raise SystemExit("STOP: required input missing: %s" % p)
rep.table(pd.DataFrame(
    [{"file": p.name, "modified": mtime(p), "bytes": p.stat().st_size}
     for p in (F_FEMALE, F_MALE, F_MAP, F_RDS, F_PKL)]))
rep.text("NCD-RisC inputs read from `%s`; they are not in this repository." % LANCET_DIR)
rep.text("`test/full_simulation_results8.rds`, the save path at line 585 of the R "
         "script, does not exist. The root `.rds` (the line-637 load path) and "
         "`final_df_imputed.pkl` carry a bit-identical baseline `bmi` vector, so "
         "the root `.rds` is what is upstream of the Python pipeline; it is what "
         "this check reads.")

# ── Target side ──────────────────────────────────────────────────────────
cmap = pd.read_excel(F_MAP)
dict_map = dict(zip(cmap["original_column"], cmap["new_column"]))
keep_raw = ["Year", "Sex", "ISO", "Age group"] + list(dict_map)

tgt = pd.concat(
    [pd.read_csv(f, usecols=keep_raw, encoding="utf-8-sig") for f in (F_FEMALE, F_MALE)],
    ignore_index=True,
).rename(columns=dict_map).rename(columns={"Age group": "Age_Group"})

rep.h2("Target side -- NCD-RisC")
n_all, y0, y1 = len(tgt), int(tgt["Year"].min()), int(tgt["Year"].max())
tgt = tgt[tgt["Year"] > 2021].copy()
ssum = tgt[CATS].sum(axis=1)
rep.kv({
    "rows, both sexes, all years": n_all,
    "year range": "%d to %d" % (y0, y1),
    "rows after the Year > 2021 filter": len(tgt),
    "years kept": ", ".join(str(y) for y in sorted(tgt["Year"].unique())),
    "duplicate ISO x Sex x Age_Group rows": int(tgt.duplicated(subset=GRP).sum()),
    "seven category shares sum to, min": float(ssum.min()),
    "seven category shares sum to, max": float(ssum.max()),
})
raw_cols = pd.read_csv(F_FEMALE, nrows=0, encoding="utf-8-sig").columns
has_mean_bmi = any("mean" in c.lower() for c in raw_cols)
tgt = tgt.set_index(GRP)

# ── Simulated side ───────────────────────────────────────────────────────
import pyreadr  # noqa: E402  heavy import, not needed until the inputs check out

sim = pyreadr.read_r(str(F_RDS))[None]
n_both = len(sim)

# The saved object binds both scenarios; each individual appears twice with an
# identical baseline bmi. Verify that rather than assume it, then keep one.
a = np.sort(sim.loc[sim["scenario"] == "max_uptake", "bmi"].to_numpy(float))
b = np.sort(sim.loc[sim["scenario"] == "mod_uptake", "bmi"].to_numpy(float))
same_baseline = a.size == b.size and bool(np.allclose(a, b, atol=1e-12))
sim = sim[sim["scenario"] == "max_uptake"].copy()
for c in ("ISO", "Sex", "Age_Group"):
    sim[c] = sim[c].astype(str)

# Binning convention: left-closed / right-open, [lo, hi), matching the NCD-RisC
# category definitions. bmi is continuous, so boundary ties are measure-zero.
sim["bmi_cat"] = pd.cut(sim["bmi"], bins=BINS, labels=CATS, right=False,
                        include_lowest=True)

counts = (sim.groupby(GRP + ["bmi_cat"], observed=True).size()
          .unstack("bmi_cat", fill_value=0).reindex(columns=CATS, fill_value=0))
n_per = counts.sum(axis=1)
real = counts.div(n_per, axis=0)
meta = sim.groupby(GRP, observed=True).agg(
    n=("bmi", "size"), Population=("Population", "first"),
    weighting=("weighting", "first"), mean_bmi=("bmi", "mean"))

rep.h2("Simulated side -- baseline `bmi`, `max_uptake` only")
rep.kv({
    "rows, both scenarios bound": n_both,
    "baseline bmi identical across the two scenarios": same_baseline,
    "rows, max_uptake only": len(sim),
    "rows falling outside all bins": int(sim["bmi_cat"].isna().sum()),
    "individuals per stratum, min": int(n_per.min()),
    "individuals per stratum, max": int(n_per.max()),
    "strata with more than one weighting value": int(
        (sim.groupby(GRP, observed=True)["weighting"].nunique() > 1).sum()),
})
rep.text("Uses baseline `bmi`, never `new_bmi`: the target is the pre-treatment "
         "distribution. Within a stratum every individual carries the same "
         "`weighting` (`Population / 500`), verified above, so within-stratum "
         "shares are plain counts and `weighting` matters only across strata.")

# ── 1. Strata ────────────────────────────────────────────────────────────
sim_idx, tgt_idx = set(real.index), set(tgt.index)
common = sorted(sim_idx & tgt_idx)
sim_iso = {i[0] for i in sim_idx}
tgt_sub = {i for i in tgt_idx if i[0] in sim_iso}

rep.h2("1. Strata compared")
rep.kv({
    "simulated strata": len(sim_idx),
    "target strata, all countries": len(tgt_idx),
    "target strata for the modelled ISOs": len(tgt_sub),
    "matched strata": len(common),
    "in the simulation but not the target": len(sim_idx - tgt_idx),
    "in the target but not simulated": len(tgt_sub - sim_idx),
    "distinct ISO": len(sim_iso),
})

R = real.loc[common]
T = tgt.loc[common, CATS]
M = meta.loc[common]
dev = R - T
w = M["Population"].to_numpy(float)
r30, t30 = R[OBESE].sum(axis=1), T[OBESE].sum(axis=1)

# ── 2. Per category ──────────────────────────────────────────────────────
rows, bar2 = [], []
for c in CATS + ["BMI_ge_30"]:
    d = (dev[OBESE].sum(axis=1) if c == "BMI_ge_30" else dev[c]).to_numpy(float) * 100
    m, se = d.mean(), d.std(ddof=1) / np.sqrt(d.size)
    t = m / se if se > 0 else np.nan
    rows.append({"category": c, "mean_pp": m, "se_pp": se, "t": t,
                 "n_over_plus2pp": int((d > 2).sum()),
                 "n_under_minus2pp": int((d < -2).sum())})
    if c != "BMI_ge_30" and abs(t) > 2:
        bar2.append((c, m, se, t))

rep.h2("2. Per-category mean deviation across strata")
rep.text("Realized minus target, percentage points, over %d strata." % len(dev))
rep.table(pd.DataFrame(rows))

# ── 3. Weighted aggregate ────────────────────────────────────────────────
agg = []
for c in CATS + ["BMI_ge_30"]:
    rv = (r30 if c == "BMI_ge_30" else R[c]).to_numpy(float)
    tv = (t30 if c == "BMI_ge_30" else T[c]).to_numpy(float)
    ra, ta = np.average(rv, weights=w), np.average(tv, weights=w)
    agg.append({"category": c, "realized": ra, "target": ta,
                "diff_pp": (ra - ta) * 100})
bar1_diff = abs(agg[-1]["diff_pp"])

rep.h2("3. Population-weighted aggregate, whole modelled set")
rep.text("Total modelled population %s." % f"{w.sum():,.0f}")
rep.table(pd.DataFrame(agg))

# ── 4. Per country ───────────────────────────────────────────────────────
iso_groups = pd.Series(range(len(common)),
                       index=pd.MultiIndex.from_tuples(common, names=GRP)
                       ).groupby(level="ISO").groups
per_iso = []
for iso, idx in iso_groups.items():
    ww = M.loc[idx, "Population"].to_numpy(float)
    ra = np.average(r30.loc[idx].to_numpy(float), weights=ww)
    ta = np.average(t30.loc[idx].to_numpy(float), weights=ww)
    per_iso.append({"ISO": iso, "realized": ra, "target": ta,
                    "diff_pp": (ra - ta) * 100,
                    "rel_pct": 100 * (ra - ta) / ta,
                    "population": ww.sum()})
iso_df = pd.DataFrame(per_iso).sort_values("diff_pp").reset_index(drop=True)

rep.h2("4. BMI >= 30 per country")
rep.text("Population-weighted within each country, sorted by absolute deviation.")
rep.table(iso_df)
d_iso = iso_df["diff_pp"].to_numpy(float)
rep.kv({
    "countries": len(iso_df),
    "diff_pp mean": float(d_iso.mean()),
    "diff_pp sd": float(d_iso.std(ddof=1)),
    "countries overstating by more than 1.0 pp": int((d_iso > 1).sum()),
    "countries understating by more than 1.0 pp": int((d_iso < -1).sum()),
})

# ── 5. Mean BMI ──────────────────────────────────────────────────────────
rep.h2("5. Mean BMI check")
if has_mean_bmi:
    rep.text("Source carries a mean BMI column; comparison belongs here.")
else:
    rep.text("**Not possible.** The NCD-RisC age-specific country BMI files carry "
             "only category prevalences and their uncertainty intervals (%d "
             "columns). There is no mean BMI column, and no mean-BMI file is "
             "present in the Lancet directory or read by the R script. So a "
             "distribution that got the shares right and the mean wrong, or the "
             "reverse, cannot be distinguished from this source. Simulated side "
             "alone:" % len(raw_cols))
    rep.kv({
        "population-weighted mean BMI": float(np.average(
            M["mean_bmi"].to_numpy(float), weights=w)),
        "per-stratum mean BMI, min": float(M["mean_bmi"].min()),
        "per-stratum mean BMI, median": float(M["mean_bmi"].median()),
        "per-stratum mean BMI, max": float(M["mean_bmi"].max()),
    })

# ── 6. Is the deviation a function of the target level? ──────────────────
tv_all = T[CATS].to_numpy(float).ravel()
dv_all = dev[CATS].to_numpy(float).ravel() * 100
slope, inter = np.polyfit(tv_all, dv_all, 1)
crossover = -inter / slope

rep.h2("6. Is the deviation a function of the target level?")
rep.text("If the smoothing chain moves mass from dense categories into sparse "
         "ones, deviation should fall as the target share rises. Pooled over "
         "every stratum x category cell:")
rep.kv({
    "cells": int(tv_all.size),
    "corr(target share, deviation_pp)": float(np.corrcoef(tv_all, dv_all)[0, 1]),
    "OLS slope, deviation_pp on target share": float(slope),
    "OLS intercept": float(inter),
    "target share at which deviation crosses zero": float(crossover),
    "1/7, the uniform share across seven categories": 1 / 7,
})
q = pd.qcut(pd.Series(tv_all), 10, labels=False, duplicates="drop")
rep.table(pd.DataFrame([
    {"decile": int(d) + 1, "mean_target_share": tv_all[q == d].mean(),
     "mean_deviation_pp": dv_all[q == d].mean()}
    for d in sorted(pd.Series(q).dropna().unique())]))
rep.text("Same question for BMI >= 30 at country level: "
         "corr(target, diff_pp) = %+.4f." % np.corrcoef(
             iso_df["target"], iso_df["diff_pp"])[0, 1])
rep.text("Relative error is what propagates to the eligible population, and it "
         "is largest where obesity is lowest:")
rep.table(iso_df.sort_values("rel_pct", ascending=False)
          .head(8)[["ISO", "realized", "target", "diff_pp", "rel_pct"]])
rel_all = 100 * (np.average(r30.to_numpy(float), weights=w) /
                 np.average(t30.to_numpy(float), weights=w) - 1)
rep.text("Population-weighted relative error on BMI >= 30 over the whole set: "
         "%+.2f%%." % rel_all)
rep.text("This run does not isolate which of the four smoothing stages -- the "
         "`width/2.5` component scale, the `dpik` bandwidth, the moving-average "
         "window, or the edge truncation at `range.x = c(13, 60)` -- contributes "
         "what. That is a separate diagnostic.")

# ── Verdict ──────────────────────────────────────────────────────────────
b1, b2 = bar1_diff > 1.0, bool(bar2)
rep.h2("Verdict against the declared bars")
rep.verdict("Bar 1 -- population-weighted BMI >= 30 deviation %.4f pp against a "
            "1.0 pp limit." % bar1_diff, not b1)
rep.verdict("Bar 2 -- %d of 7 categories have a mean deviation beyond 2 standard "
            "errors from zero." % len(bar2), not b2)
if bar2:
    rep.table(pd.DataFrame(
        [{"category": c, "mean_pp": m, "se_pp": se, "t": t} for c, m, se, t in bar2]))
rep.text("**OVERALL: %s**" % ("FAIL" if (b1 or b2) else "PASS"))

out = R.add_prefix("real_")
for c in CATS:
    out["tgt_" + c] = T[c]
    out["dev_" + c] = dev[c]
out["real_ge30"], out["tgt_ge30"], out["dev_ge30"] = r30, t30, r30 - t30
out["n"], out["Population"] = M["n"], M["Population"]
out["sim_mean_bmi"] = M["mean_bmi"]
out.reset_index().to_csv(OUT_CSV, index=False)

# The only things that reach the console: an ASCII verdict and two paths.
print("OVERALL: %s" % ("FAIL" if (b1 or b2) else "PASS"))
print("  bar 1  weighted BMI >= 30 deviation %+.4f pp (limit 1.0)   %s"
      % (bar1_diff, "FAIL" if b1 else "pass"))
print("  bar 2  categories beyond 2 SE: %d of 7                     %s"
      % (len(bar2), "FAIL" if b2 else "pass"))
print("Per-stratum detail: %s" % OUT_CSV.relative_to(ROOT))
rep.save()
