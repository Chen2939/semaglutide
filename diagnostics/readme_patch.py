"""Update README.md for the regeneration.

Several passages now state things that are false: the BMI caveat, the
"not reproducible from a clean clone" note, the `test/` save-path note, the
reconciled manuscript numbers, and eleven references to the superseded
`.rds` filename. ASCII only in what it writes, except where the existing file
already uses non-ASCII.
"""
import io
import sys

P = r"C:\Users\sethw\repos\README.md"
s = io.open(P, encoding="utf-8").read()
subs = []


def sub(a, b, n=1):
    subs.append((a, b, n))


# ---- 1. the BMI caveat is resolved -----------------------------------------
sub(
    "> **Caveat on the BMI distribution.** The mixture step that turns the "
    "NCD-RisC category shares into continuous BMI values does not reproduce "
    "those shares: it inflates the population-weighted BMI >= 30 share by "
    "1.57 pp (+5.82% relative, and +36% in Japan). Measured, not fixed. See "
    '"Known gaps and warts".',

    "> **The BMI distribution caveat is RESOLVED.** The mixture step used to "
    "inflate the population-weighted BMI >= 30 share by 1.57 pp (+5.82% "
    "relative, +36% in Japan). It has been replaced by a piecewise-linear CDF "
    "through the NCD-RisC cumulative points with a Kitahara class III top "
    "band, which reproduces the seven band shares by construction. Measured "
    "deviation is now **-0.23 pp**, inside one standard error, with Japan at "
    "-0.22 pp and Korea at -0.03 pp. See `diagnostics/reports/"
    "phase2_population_gates.md`."
)

# ---- 2. reconciled manuscript numbers --------------------------------------
sub(
    "- Maximum uptake: average HR reduction `18.6%`, starting treated users "
    "`252.6 million`, extra survivors alive at year 10 `3.15 million`, "
    "cumulative 10-year person-years saved `16.83 million`\n"
    "- Moderate uptake: average HR reduction `18.4%`, starting treated users "
    "`132.2 million`, extra survivors alive at year 10 `1.66 million`, "
    "cumulative 10-year person-years saved `8.89 million`",

    "- Maximum uptake: average HR reduction `17.21%`, starting treated users "
    "`238.8 million`, extra survivors alive at year 10 `2.79 million`, "
    "cumulative 10-year person-years saved `14.92 million`\n"
    "- Moderate uptake: average HR reduction `17.28%`, starting treated users "
    "`126.6 million`, extra survivors alive at year 10 `1.47 million`, "
    "cumulative 10-year person-years saved `7.88 million`\n"
    "\n"
    "> These moved with the regeneration. The pre-regeneration figures were "
    "18.6% / 252.6M / 3.15M / 16.83M and 18.4% / 132.2M / 1.66M / 8.89M. "
    "**The 18.6% is not a renumbering** -- the manuscript builds a rhetorical "
    "point on SELECT having found the same figure, and that coincidence no "
    "longer holds. See `diagnostics/reports/phase5_reconciliation.md`."
)

# ---- 3. the test/ save-path note is wrong ----------------------------------
sub(
    "Note the R script saves to `test/full_simulation_results8.rds` "
    "(line 585) but loads from the project root (line 637); the `test/` copy "
    "does not exist, and the root copy is what is upstream of the Python "
    "pipeline.",

    "The save path and the load path are now one `OUT_RDS` constant, read "
    "once at each site. They used to be separated by 50 lines and an "
    "interactive `setwd()`, and had diverged: measured, **no script on disk "
    "has ever written `test/`** except the repo's own copy of the R script, "
    "and `test/` does not exist. Three copies of the script and two distinct "
    "`.rds` artefacts were found on disk; see "
    "`diagnostics/reports/phase0_recon.md` section 2."
)

# ---- 4. "no committed build script" is no longer true ----------------------
sub(
    "**The simulation has no committed build script.** "
    "`full_simulation_results8.rds`\n"
    "is the input to every food-emissions figure, and the script that "
    "produced it\n"
    "(`Data_Cleaning9.8.R`) is archived in `legacy/R_scripts/` but is not "
    "wired to run\n"
    "against data in this repository. Its NCD-RisC and UN WPP inputs are not "
    "present.\n"
    "So the simulation is **not reproducible from a clean clone** — it is "
    "consumed as\n"
    "a fixed, committed artifact. Anyone re-deriving the population from "
    "source data\n"
    "must reconstruct that step independently.",

    "**The simulation is reproducible on this machine but not from a clean "
    "clone.** `full_simulation_results9.rds` is the input to every "
    "food-emissions figure. `legacy/R_scripts/Data_Cleaning9.8.R` now runs "
    "end to end and regenerates it in about 15 minutes, driven entirely by "
    "environment variables (`SEMAG_DATA_DIR`, `SEMAG_OUT_RDS`, "
    "`SEMAG_COHORT_HEIGHT`, `SEMAG_HEIGHT_LOSS`, `SEMAG_BATCH_SIZE`), and it "
    "is deterministic: `GLOBAL_SEED = 43` keyed per stratum, verified "
    "bit-identical across repeat runs **and across a change of batch size**.\n"
    "\n"
    "What is still missing from a clean clone is the *inputs*: the NCD-RisC, "
    "UN WPP and World Bank files live under `SEMAG_DATA_DIR` (by default the "
    "researcher's OneDrive) and are not in this repository. Anyone "
    "re-deriving the population from source data needs those files; they do "
    "not need to reconstruct the step."
)

# ---- 5. the known-gaps BMI section --------------------------------------
old_gap_start = ("**The simulated BMI distribution does not reproduce its "
                 "NCD-RisC input, and this")
i = s.find(old_gap_start)
j = s.find("Measured, not fixed — "
           "`diagnostics/bmi_mixture_reproduction_check.py`, read-only.")
if i == -1 or j == -1:
    print("could not locate the known-gaps BMI block")
    sys.exit(1)
j += len("Measured, not fixed — "
         "`diagnostics/bmi_mixture_reproduction_check.py`, read-only.")
sub(
    s[i:j],
    "**The simulated BMI distribution used not to reproduce its NCD-RisC "
    "input. FIXED.** `fit_bmi_mixture()` drew skew-normal components at fixed "
    "midpoints, concatenated them in the observed proportions, ran a KDE and "
    "applied a moving-average smoother. All seven categories deviated 9 to 52 "
    "standard errors from zero; the population-weighted BMI >= 30 share was "
    "0.28467 realized against 0.26901 target (**+1.57 pp, +5.82% relative**), "
    "with 51 of 63 countries overstating by more than 1.0 pp. The signature "
    "was flattening toward uniform: deviation fell near-linearly in the "
    "target share (corr -0.684 over 13,230 cells) and crossed zero at "
    "**1/7**, so the worst relative cases were the leanest countries -- Japan "
    "+36.2%, Korea +35.4%.\n"
    "\n"
    "It is now a **piecewise-linear CDF** through the NCD-RisC cumulative "
    "points, following the OECD SPHeP-NCDs precedent, with the top band split "
    "at 45/50/55/60 using the class III participant composition from Kitahara "
    "et al. (2014). The seven band shares are correct by construction: gate "
    "G1 evaluates the fitted CDF at all ten knots for all 1,890 strata and "
    "finds **max deviation 0.000e+00**. Realized deviation on BMI >= 30 is "
    "**-0.23 pp** pooled (bar 0.37 pp, 3 SE), Japan -0.22 pp, Korea -0.03 pp, "
    "and no country now overstates by more than 1.0 pp.\n"
    "\n"
    "The known and accepted cost is that the implied density is uniform "
    "within each band and discontinuous at band boundaries. That is the cost "
    "OECD accepted on the same data for the same reason.\n"
    "\n"
    "Verified by `diagnostics/reports/phase2_population_gates.md`. The "
    "pre-fix measurement is preserved at "
    "`diagnostics/reports/bmi_mixture_reproduction_check.md`."
)

# ---- 6. filename references -------------------------------------------------
FILE_SUBS = [
    ("| `data_visualization/pipeline.py` | FAOSTAT FBS + CPI, elasticities, "
     "mappings, CI file, `child_energy_by_country.xlsx`, "
     "`full_simulation_results8.rds`,",
     "| `data_visualization/pipeline.py` | FAOSTAT FBS + CPI, elasticities, "
     "mappings, CI file, `child_energy_by_country.xlsx`, "
     "`full_simulation_results9.rds`,"),
    ("| `scripts/build_supplement_table.py` | pipeline, "
     "`full_simulation_results8.rds` |",
     "| `scripts/build_supplement_table.py` | pipeline, "
     "`full_simulation_results9.rds` |"),
    ("- **Output:** `full_simulation_results8.rds`",
     "- **Output:** `full_simulation_results9.rds`"),
    ("- Loads `full_simulation_results8.rds` and all `Food data/` files",
     "- Loads `full_simulation_results9.rds` and all `Food data/` files"),
    ("**All scripts share inputs:** `full_simulation_results8.rds`,",
     "**All scripts share inputs:** `full_simulation_results9.rds`,"),
    ("| `full_simulation_results8.rds`, `final_df_imputed.pkl` | upstream "
     "simulation output (LFS) |",
     "| `full_simulation_results9.rds`, `final_df_imputed9.pkl` | upstream "
     "simulation output (LFS). `...8.rds` / `final_df_imputed.pkl` are "
     "retained unchanged as the pre-regeneration baseline and are read by no "
     "production path |"),
    ("(already baked into `full_simulation_results8.rds`)",
     "(already baked into `full_simulation_results9.rds`)"),
    ("### `full_simulation_results8.rds`",
     "### `full_simulation_results9.rds`"),
    ("`final_df_imputed.pkl` carries the same baseline `bmi` vector "
     "bit-for-bit, plus `Age`, `mortality_rate` and `Year`.",
     "`final_df_imputed9.pkl` carries the same baseline `bmi` vector "
     "bit-for-bit, plus `Age`, `mortality_rate` and `Year`. It is built by "
     "`diagnostics/build_population_pickle.py`, which lifts the existing "
     "`(ISO, age, Sex) -> mortality_rate` map off the committed pickle rather "
     "than re-running the imputation; that imputation does not depend on the "
     "simulated population."),
    ("- `*.rds` — R data files (`full_simulation_results8.rds`, "
     "`mortality2.rds`, `legacy/data/*.rds`)",
     "- `*.rds` — R data files (`full_simulation_results9.rds`, "
     "`full_simulation_results8.rds`, `mortality2.rds`, `legacy/data/*.rds`)"),
]
for a, b in FILE_SUBS:
    sub(a, b)

# ---- 7. run order: the new steps -------------------------------------------
sub(
    "# 1. Survivor person-years  (only if the mortality model changed)\n"
    "python -m data_visualization.deterministic_mortality",

    "# 0. Regenerate the population  (only if the simulation changed)\n"
    "Rscript legacy/R_scripts/Data_Cleaning9.8.R\n"
    "#    reads  $SEMAG_DATA_DIR (NCD-RisC, UN WPP, World Bank)\n"
    "#    writes full_simulation_results9.rds\n"
    "python -m diagnostics.build_population_pickle\n"
    "#    reads  full_simulation_results9.rds, final_df_imputed.pkl\n"
    "#    writes final_df_imputed9.pkl\n"
    "\n"
    "# 1. Survivor person-years  (only if the mortality model changed)\n"
    "python -m data_visualization.deterministic_mortality"
)
sub(
    "python scripts/build_supplement_table.py\n",
    "python scripts/build_supplement_table.py\n"
    "python scripts/build_per_capita_table.py\n",
)
sub(
    "Rscript gdp_share_of_global_economy.R\n```",
    "Rscript gdp_share_of_global_economy.R\n"
    "\n"
    "# 7. Collate every Results-section number into one CSV, beside the value\n"
    "#    currently written in the draft. Reads committed CSVs only, seconds.\n"
    "Rscript scripts/build_manuscript_numbers.R\n"
    "#    writes data_result/manuscript_headline_numbers.csv\n```"
)

# ---- apply -----------------------------------------------------------------
failed = []
for k, (a, b, n) in enumerate(subs):
    c = s.count(a)
    if c != n:
        failed.append((k, c, a[:90]))
        continue
    s = s.replace(a, b)

if failed:
    for k, c, head in failed:
        print(f"SUB {k}: {c} matches -- {head!r}")
    sys.exit(1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print(f"README.md updated: {len(subs)} substitutions")
rem = s.count("full_simulation_results8.rds")
print(f"remaining references to ...8.rds: {rem} (expected: deliberate "
      "baseline mentions only)")
