"""
Build the supplementary results table from the semaglutide pipeline outputs.

This is a rerunnable script: it reads the upstream model outputs at runtime and
regenerates the table. It hardcodes no result numbers -- rerunning after the
upstream data changes produces updated figures.

What it reads (all at runtime; nothing pasted in)
-------------------------------------------------
* full_simulation_results8.rds
      Simulation output. Columns used: ISO, scenario, weighting, eer,
      treatment_eer, adheres_to_treatment. Provides the caloric reduction and
      the treated-patient headcount.
* The price-rebound model, invoked via
  ``data_visualization.pipeline.compute_food_savings()``, which itself reads:
      - Food data/FoodBalanceSheets_E_All_Data_(Normalized)/...csv (FAOSTAT food quantities)
      - Food data/carbon_intensity.csv                             (mean carbon intensity)
      - Food data/elasticity_supply.csv, elasticity_demand.csv
      - Food data/FBS_Group_Mapping.csv, faostat_country_mapping.csv
      - Food data/ConsumerPriceIndices_E_All_Data_(Normalized)/...csv
  NOTE: the before-rebound tonnage is an in-model intermediate
  (``expected_demand_reduction``); it is not persisted to any standalone CSV, so
  this script obtains it by invoking the model rather than reading a file.

What it writes
--------------
* data_result/supplement_results_table.csv       (wide, rounded display values)
* data_result/supplement_results_table_raw.csv    (tidy long: raw + display + provenance)
* stdout: Markdown table, provenance map, per-treated-patient metrics, N, CI scenario.

Usage
-----
    python scripts/build_supplement_table.py
    (or: python -m scripts.build_supplement_table  from the repo root)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr

# Make the repo root importable no matter where the script is launched from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data_visualization.pipeline import (  # noqa: E402
    ROOT as PIPELINE_ROOT,
    SIMULATION_RDS,
    compute_food_savings,
    output_path,
)

# ── Configuration constants (adjust here) ─────────────────────────────────
CI_FILE = "carbon_intensity.csv"          # carbon-intensity file inside Food data/
CI_SCENARIO_LABEL = "mean"                 # which CI scenario CI_FILE represents
SIM_PATH = SIMULATION_RDS

SCENARIOS = ["max_uptake", "mod_uptake"]
SCENARIO_LABELS = {"max_uptake": "Max uptake", "mod_uptake": "Moderate uptake"}

KCAL_PER_DAY_TO_YEAR = 365                 # eer/treatment_eer are kcal/day

# Semaglutide annual product carbon footprint, scaled from the Novo Nordisk
# Ozempic FlexTouch product-carbon-footprint document (Appendix A, Table 2, US
# market): API scaled 1.0 -> 2.4 mg (1.2 * 2.4) plus device (2.1) and needle
# (0.4) held constant = 5.38 kg CO2e/patient-year. Update if that estimate is
# revised.
DRUG_FOOTPRINT_KG_CO2E_PER_PATIENT_YEAR = 5.38

# Flag if per-patient savings diverge between scenarios by more than this (%).
DIVERGENCE_FLAG_PCT = 5.0

OUTPUT_TABLE_CSV = "supplement_results_table.csv"
OUTPUT_RAW_CSV = "supplement_results_table_raw.csv"

EMDASH = "—"
TODO = "TODO"


# ── Formatting helpers ────────────────────────────────────────────────────


def fmt_sig(x: float, n: int = 3) -> str:
    """Format ``x`` to ``n`` significant figures as a clean (non-scientific) string."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return TODO
    if x == 0:
        return "0"
    decimals = n - 1 - math.floor(math.log10(abs(x)))
    rounded = round(x, decimals)
    if decimals <= 0:
        return f"{int(round(rounded)):,}"
    return f"{rounded:,.{decimals}f}"


def fmt_sci(x: float, n: int = 3) -> str:
    """Format ``x`` in scientific notation to ``n`` significant figures."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return TODO
    return f"{x:.{n - 1}e}"


def fmt_pct(x: float) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return TODO
    return f"{x:.1f}"


# ── Core computation ──────────────────────────────────────────────────────


def compute_scenario_metrics(scenario, food, detail, sim):
    """Return raw (unrounded) metrics for one uptake scenario over the
    data-complete emissions sample."""
    # Emissions sample = countries with real (positive) food-emission savings.
    sample = set(
        food.loc[
            (food["scenario"] == scenario) & (food["annual_food_savings_t"] > 0),
            "ISO",
        ]
    )

    d = detail[(detail["scenario"] == scenario) & (detail["ISO"].isin(sample))]
    # Common valid mask so tonnage and emissions share the same food-group basis.
    valid = d.dropna(
        subset=[
            "expected_demand_reduction",
            "actual_reduction",
            "carbon_intensity_t",
            "carbon_savings_t",
        ]
    )

    # Tonnage is in thousand tonnes (kt); /1e3 -> Mt.
    before_tonnage_kt = valid["expected_demand_reduction"].abs().sum()
    after_tonnage_kt = valid["actual_reduction"].abs().sum()
    # Emissions in tonnes CO2e; /1e6 -> Mt.
    before_emissions_t = (
        valid["expected_demand_reduction"].abs() * valid["carbon_intensity_t"]
    ).sum()
    after_emissions_t = valid["carbon_savings_t"].abs().sum()

    # Calories: kcal/day reduction -> kcal/yr (pre-rebound, from the sim EER gap).
    s = sim[(sim["scenario"] == scenario) & (sim["ISO"].isin(sample))]
    kcal_day = (s["weighting"] * (s["eer"] - s["treatment_eer"])).sum()
    calories_kcal_yr = kcal_day * KCAL_PER_DAY_TO_YEAR

    treated_headcount = s.loc[s["adheres_to_treatment"], "weighting"].sum()

    rebound_offset_pct = (
        (before_tonnage_kt - after_tonnage_kt) / before_tonnage_kt * 100
        if before_tonnage_kt
        else float("nan")
    )

    return {
        "scenario": scenario,
        "sample": sample,
        "N": len(sample),
        "calories_kcal_yr": calories_kcal_yr,
        "tonnage_before_Mt": before_tonnage_kt / 1e3,
        "tonnage_after_Mt": after_tonnage_kt / 1e3,
        "emissions_before_Mt": before_emissions_t / 1e6,
        "emissions_after_Mt": after_emissions_t / 1e6,
        "rebound_offset_pct": rebound_offset_pct,
        "treated_headcount": treated_headcount,
    }


# Row definitions: (row label, unit, key or None, populated stages, formatter, provenance)
# `stages` says which of before/after are populated; the rest get an em-dash.
ROWS = [
    {
        "label": "Calories reduced (kcal/yr, t=0)",
        "unit": "kcal/yr",
        "before_key": "calories_kcal_yr",
        "after_key": None,  # rebound acts on tonnage downstream, not calories
        "fmt": fmt_sci,
        "source_var": "eer, treatment_eer, weighting",
        "source_detail": (
            "full_simulation_results8.rds; "
            "Sum(weighting * (eer - treatment_eer)) * 365"
        ),
    },
    {
        "label": "Food tonnage reduced (Mt, t=0)",
        "unit": "Mt",
        "before_key": "tonnage_before_Mt",
        "after_key": "tonnage_after_Mt",
        "fmt": fmt_sig,
        "source_var": "expected_demand_reduction (before) / actual_reduction (after)",
        "source_detail": (
            "pipeline.compute_food_savings() result_df "
            "(price-rebound model; FAOSTAT FoodBalanceSheets + sim EER)"
        ),
    },
    {
        "label": "Emissions reduced (MtCO2e, mean CI, t=0)",
        "unit": "MtCO2e",
        "before_key": "emissions_before_Mt",
        "after_key": "emissions_after_Mt",
        "fmt": fmt_sig,
        "source_var": (
            "expected_demand_reduction * carbon_intensity_t (before) / "
            "carbon_savings_t (after)"
        ),
        "source_detail": (
            "pipeline.compute_food_savings() result_df + "
            f"Food data/{CI_FILE} ({CI_SCENARIO_LABEL})"
        ),
    },
    {
        "label": "Rebound offset (% tonnage)",
        "unit": "%",
        "before_key": None,  # derived after-rebound metric
        "after_key": "rebound_offset_pct",
        "fmt": fmt_pct,
        "source_var": "derived from expected_demand_reduction & actual_reduction",
        "source_detail": (
            "(sum|expected_demand_reduction| - sum|actual_reduction|) / "
            "sum|expected_demand_reduction| * 100"
        ),
    },
]

COLUMNS = [
    ("max_uptake", "before", "Max uptake\nBefore rebound"),
    ("max_uptake", "after", "Max uptake\nAfter rebound"),
    ("mod_uptake", "before", "Moderate uptake\nBefore rebound"),
    ("mod_uptake", "after", "Moderate uptake\nAfter rebound"),
]


def build_table(metrics):
    """Return (display_rows, raw_records) for the main table."""
    display_rows = []       # list of dicts: {"Metric": ..., col_label: display_str}
    raw_records = []        # tidy long records with raw + display + provenance

    for row in ROWS:
        disp = {"Metric": f"{row['label']}"}
        for scenario, stage, col_label in COLUMNS:
            key = row["before_key"] if stage == "before" else row["after_key"]
            flat_col = col_label.replace("\n", " - ")
            if key is None:
                disp[flat_col] = EMDASH
                raw_records.append({
                    "metric": row["label"],
                    "unit": row["unit"],
                    "scenario": scenario,
                    "stage": stage,
                    "value_raw": "",
                    "value_display": EMDASH,
                    "source_variable": "n/a",
                    "source_detail": (
                        "n/a: rebound acts on tonnage downstream of caloric demand"
                        if row["label"].startswith("Calories")
                        else "n/a: rebound offset is a derived after-rebound metric"
                    ),
                })
                continue

            value = metrics[scenario].get(key, float("nan"))
            if value is None or (isinstance(value, float) and math.isnan(value)):
                # Value unavailable -> emit expectation instead of guessing.
                display = TODO
                print(
                    f"  [MISSING] {row['label']} / {scenario} / {stage}: "
                    f"expected variable '{row['source_var']}' from "
                    f"{row['source_detail']} -> writing TODO"
                )
            else:
                display = row["fmt"](value)

            disp[flat_col] = display
            raw_records.append({
                "metric": row["label"],
                "unit": row["unit"],
                "scenario": scenario,
                "stage": stage,
                "value_raw": value,
                "value_display": display,
                "source_variable": row["source_var"],
                "source_detail": row["source_detail"],
            })
        display_rows.append(disp)

    return display_rows, raw_records


def to_markdown(display_rows):
    headers = ["Metric"] + [c[2].replace("\n", " — ") for c in COLUMNS]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in display_rows:
        cells = [r["Metric"]] + [
            r[c[2].replace("\n", " - ")] for c in COLUMNS
        ]
        lines.append("| " + " | ".join(str(x) for x in cells) + " |")
    return "\n".join(lines)


def print_provenance(raw_records):
    print("\nProvenance map (populated cells only):")
    for rec in raw_records:
        if rec["value_display"] in (EMDASH,):
            continue
        print(
            f"  {rec['metric']} | {rec['scenario']} | {rec['stage']}"
            f"  <-  {rec['source_variable']}"
            f"  [{rec['source_detail']}]"
        )


def per_treated_metrics(metrics):
    """Compute and print per-treated-patient emissions savings (kg CO2e/patient-year)."""
    print("\n" + "=" * 72)
    print(" Per-treated-patient emissions savings (kg CO2e/patient-year)")
    print("=" * 72)

    drug = DRUG_FOOTPRINT_KG_CO2E_PER_PATIENT_YEAR
    per = {}
    for sc in SCENARIOS:
        m = metrics[sc]
        treated = m["treated_headcount"]
        # Mt CO2e -> kg (1 Mt = 1e9 kg).
        gross_after = m["emissions_after_Mt"] * 1e9 / treated
        gross_before = m["emissions_before_Mt"] * 1e9 / treated
        net_after = gross_after - drug
        drug_pct = drug / gross_after * 100 if gross_after else float("nan")
        per[sc] = {
            "treated": treated,
            "gross_after": gross_after,
            "gross_before": gross_before,
            "net_after": net_after,
            "drug_pct": drug_pct,
        }

    header = f"{'':32s}" + "".join(f"{SCENARIO_LABELS[sc]:>22s}" for sc in SCENARIOS)
    print(header)
    print(f"{'treated headcount (weighted)':32s}"
          + "".join(f"{per[sc]['treated']:>22,.0f}" for sc in SCENARIOS))
    print(f"{'AFTER-rebound gross [HEADLINE]':32s}"
          + "".join(f"{per[sc]['gross_after']:>22.3f}" for sc in SCENARIOS))
    print(f"{'  drug footprint (subtracted)':32s}"
          + "".join(f"{drug:>22.3f}" for _ in SCENARIOS))
    print(f"{'AFTER-rebound NET (gross-5.38)':32s}"
          + "".join(f"{per[sc]['net_after']:>22.3f}" for sc in SCENARIOS))
    print(f"{'  drug as % of gross':32s}"
          + "".join(f"{per[sc]['drug_pct']:>21.2f}%" for sc in SCENARIOS))
    print(f"{'(pre-rebound gross, not headline)':32s}"
          + "".join(f"{per[sc]['gross_before']:>22.3f}" for sc in SCENARIOS))

    print("\nRaw unrounded (after-rebound gross, kg CO2e/patient-year):")
    for sc in SCENARIOS:
        print(f"  {SCENARIO_LABELS[sc]:16s}: {float(per[sc]['gross_after'])!r}")

    # Cross-scenario consistency check on the headline per-patient figure.
    a, b = per["max_uptake"]["gross_after"], per["mod_uptake"]["gross_after"]
    divergence = abs(a - b) / ((a + b) / 2) * 100
    print(f"\nMax vs Moderate after-rebound per-patient divergence: {divergence:.2f}%")
    if divergence > DIVERGENCE_FLAG_PCT:
        print(
            f"  ** FLAG: divergence exceeds {DIVERGENCE_FLAG_PCT:.1f}% -- the scenarios "
            "differ by more than headcount alone (possible compositional shift in the "
            "treated population). Investigate before reporting. **"
        )
    else:
        print(
            f"  OK: within {DIVERGENCE_FLAG_PCT:.1f}% -- scenarios differ mainly in how "
            "many are treated, not per-person savings, as expected."
        )
    return per


def main():
    # Emit UTF-8 so em-dashes render in the console instead of mojibake.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("Building supplementary results table...")
    print(f"Carbon-intensity scenario: {CI_SCENARIO_LABEL}  (Food data/{CI_FILE})")
    assert CI_FILE == "carbon_intensity.csv", (
        "CI_FILE is not the mean carbon-intensity file; update CI_SCENARIO_LABEL."
    )

    # survival_weighted=False on purpose: every row of this table is an
    # INSTANTANEOUS reduction at t = 0 -- calories, tonnage and emissions all on
    # the same basis, the whole treated cohort alive. pi(0) == 1 by construction,
    # so the unweighted shock IS the t = 0 shock. Survival weighting would put
    # tonnage and emissions on a year-1 basis while the calorie row stayed at t = 0
    # (it comes from the raw cohort EER gap), leaving three rows of one table on
    # two different bases. Cumulative and per-year quantities live in the
    # break-even outputs, not here.
    food, detail = compute_food_savings(ci_file=CI_FILE, survival_weighted=False)
    sim = list(pyreadr.read_r(str(SIM_PATH)).values())[0]

    metrics = {sc: compute_scenario_metrics(sc, food, detail, sim) for sc in SCENARIOS}

    # Sample size N (read from data, not assumed).
    ns = {sc: metrics[sc]["N"] for sc in SCENARIOS}
    samples_equal = metrics["max_uptake"]["sample"] == metrics["mod_uptake"]["sample"]
    print(
        f"\nEmissions sample N: "
        + ", ".join(f"{SCENARIO_LABELS[sc]} = {ns[sc]}" for sc in SCENARIOS)
    )
    if samples_equal:
        print(f"  Both scenarios use the same {ns['max_uptake']} data-complete countries.")
    else:
        only_max = metrics["max_uptake"]["sample"] - metrics["mod_uptake"]["sample"]
        only_mod = metrics["mod_uptake"]["sample"] - metrics["max_uptake"]["sample"]
        print(f"  ** Samples differ: only in max {sorted(only_max)}; "
              f"only in mod {sorted(only_mod)} **")

    display_rows, raw_records = build_table(metrics)

    print("\n" + "=" * 72)
    print(" Supplementary results table (Markdown)")
    print("=" * 72)
    print(to_markdown(display_rows))

    print_provenance(raw_records)

    per = per_treated_metrics(metrics)

    # ── Write outputs ──────────────────────────────────────────────────
    # Wide display table (mirrors the printed Markdown).
    wide = pd.DataFrame(display_rows).set_index("Metric")
    wide_path = output_path(OUTPUT_TABLE_CSV)
    wide.to_csv(wide_path, encoding="utf-8-sig")

    # Tidy long: table cells + per-patient scalars, raw + display + provenance.
    raw_df = pd.DataFrame(raw_records)
    pp_records = []
    for sc in SCENARIOS:
        pp = per[sc]
        pp_records.extend([
            _pp_row("per_treated_after_rebound_gross", "kg CO2e/patient-yr", sc,
                    pp["gross_after"], "carbon_savings_t / treated_headcount"),
            _pp_row("per_treated_after_rebound_net", "kg CO2e/patient-yr", sc,
                    pp["net_after"], "gross_after - DRUG_FOOTPRINT(5.38)"),
            _pp_row("per_treated_pre_rebound_gross", "kg CO2e/patient-yr", sc,
                    pp["gross_before"], "expected_demand_reduction*CI / treated_headcount"),
            _pp_row("drug_footprint_pct_of_gross", "%", sc,
                    pp["drug_pct"], "5.38 / gross_after * 100"),
            _pp_row("treated_headcount", "patients", sc,
                    pp["treated"], "sum(weighting) where adheres_to_treatment"),
        ])
    raw_out = pd.concat([raw_df, pd.DataFrame(pp_records)], ignore_index=True)
    raw_path = output_path(OUTPUT_RAW_CSV)
    raw_out.to_csv(raw_path, index=False, encoding="utf-8-sig")

    print("\nSaved:")
    print(f"  {wide_path}")
    print(f"  {raw_path}")


def _pp_row(metric, unit, scenario, value, source_detail):
    return {
        "metric": metric,
        "unit": unit,
        "scenario": scenario,
        "stage": "after" if "after" in metric or metric in ("drug_footprint_pct_of_gross",) else "n/a",
        "value_raw": value,
        "value_display": (fmt_pct(value) if unit == "%" else f"{value:,.3f}"),
        "source_variable": "per-treated derived",
        "source_detail": source_detail,
    }


if __name__ == "__main__":
    # Redirected stdout on Windows falls back to cp1252, which cannot encode the
    # non-ASCII this script prints. Set UTF-8 on the streams here rather than at
    # module level, so importing this module never mutates global stream state.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    main()
