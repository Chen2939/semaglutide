"""Part 2 orchestrator: regenerate all Group A + Group B outputs on the
post-fix (fix1+fix2+fix3) pipeline, in dependency order, and report which
committed files changed. Regenerates figures + tables; commits nothing."""
import hashlib
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(r"C:\Users\sethw\repos")
PY = r"C:\Python314\python.exe"
env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(ROOT))
START = time.time()

# (label, argv after python)  -- dependency order: waterfalls before combined.
STEPS = [
    ("breakeven_analysis",      ["-m", "data_visualization.breakeven_analysis"]),
    ("emissions_figure",        ["-m", "data_visualization.generate_emissions_figure"]),
    ("dashboard_figure",        ["-m", "data_visualization.generate_dashboard_figure"]),
    ("rebound_figure",          ["-m", "data_visualization.generate_rebound_figure"]),
    ("rebound_validation",      ["-m", "data_visualization.generate_rebound_validation"]),
    ("drug_effect",             ["-m", "drug_effect.analysis"]),
    ("supplement_table",        ["scripts/build_supplement_table.py"]),
    ("waterfall",               ["-m", "data_visualization.generate_waterfall_figure"]),
    ("waterfall_1yr",           ["-m", "data_visualization.generate_waterfall_1yr_figure"]),
    ("waterfall_combined",      ["-m", "data_visualization.generate_waterfall_combined_figure"]),
    ("sensitivity_overview",    ["-m", "diet_sensitivity.sensitivity_overview"]),
    ("diet_analysis",           ["-m", "diet_sensitivity.analysis"]),
    ("combined_analysis",       ["-m", "diet_sensitivity.combined_analysis"]),
    ("tornado",                 ["-m", "diet_sensitivity.tornado_analysis"]),
]

TRACKED_CSV = [
    "data_result/global_emissions_waterfall.csv",
    "data_result/global_emissions_waterfall_1yr.csv",
    "data_result/drug_emissions_by_country.csv",
    "data_result/net_emissions_with_drug.csv",
    "data_result/drug_footprint_summary.csv",
    "data_result/diet_sensitivity_results.csv",
    "data_result/diet_sensitivity_ratio_comparison.csv",
    "data_result/combined_sensitivity_results.csv",
    "data_result/combined_sensitivity_ratio_comparison.csv",
    "data_result/carbon_intensity_meat_p10.csv",
    "data_result/carbon_intensity_meat_p90.csv",
    "data_result/all_sensitivity_overview_results.csv",
    "data_result/all_sensitivity_overview_country_ratios.csv",
    "data_result/sensitivity_tornado_results.csv",
]
TRACKED_FIG = [
    "figures/breakeven_by_country.png", "figures/breakeven_curves.png",
    "figures/breakeven_stock_all_countries.png", "figures/breakeven_flow_all_countries.png",
    "figures/breakeven_publication.png",
    "figures/emissions_saved_by_country.png",
    "figures/country_dashboard.png", "figures/food_group_breakdown.png",
    "figures/rebound_decomposition.png", "figures/rebound_by_income.png",
    "figures/global_emissions_waterfall.png", "figures/global_emissions_waterfall_1yr.png",
    "figures/global_emissions_waterfall_combined.png",
    "figures/drug_footprint_summary.png",
    "figures/diet_sensitivity_global_comparison.png",
    "figures/diet_sensitivity_lowest_ratio_countries.png",
    "figures/combined_sensitivity_lowest_ratio_countries.png",
    "figures/all_sensitivity_overview.png",
    "figures/sensitivity_tornado.png",
]
UNTRACKED_ALSO = [
    "data_result/supplement_results_table.csv",
    "data_result/supplement_results_table_raw.csv",
    "figures/breakeven_publication.pdf",
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def committed_bytes(path):
    r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=str(ROOT),
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


results = []
for label, args in STEPS:
    t0 = time.time()
    r = subprocess.run([PY] + args, cwd=str(ROOT), env=env,
                       capture_output=True, text=True)
    dt = time.time() - t0
    results.append((label, r.returncode, dt))
    print(f"[{label}] rc={r.returncode}  {dt:.0f}s", flush=True)
    if r.returncode != 0:
        print("  --- STDERR tail ---")
        print("  " + "\n  ".join((r.stderr or "").strip().splitlines()[-25:]), flush=True)

print("\n" + "=" * 90)
print("SCRIPT RUN SUMMARY")
print("=" * 90)
for label, rc, dt in results:
    print(f"  {label:<24} {'OK' if rc == 0 else 'FAILED rc=%d' % rc:<12}  {dt:6.0f}s")

print("\n" + "=" * 90)
print("COMMITTED CSV CHANGES (vs HEAD)")
print("=" * 90)
for p in TRACKED_CSV:
    fp = ROOT / p
    written = fp.exists() and fp.stat().st_mtime >= START
    cb = committed_bytes(p)
    if not fp.exists():
        state = "MISSING (not written!)"
    elif cb is None:
        state = "written (no HEAD blob)"
    else:
        changed = sha(fp.read_bytes()) != sha(cb)
        state = ("CHANGED" if changed else "unchanged (flag!)") + (
            "" if written else "  [mtime not updated!]")
    print(f"  {p:<52} {state}")

print("\n" + "=" * 90)
print("COMMITTED FIGURES WRITTEN (mtime updated this run)")
print("=" * 90)
for p in TRACKED_FIG:
    fp = ROOT / p
    ok = fp.exists() and fp.stat().st_mtime >= START
    print(f"  {p:<52} {'written' if ok else 'NOT WRITTEN (flag!)'}")

print("\n" + "=" * 90)
print("ALSO WRITTEN (untracked)")
print("=" * 90)
for p in UNTRACKED_ALSO:
    fp = ROOT / p
    ok = fp.exists() and fp.stat().st_mtime >= START
    print(f"  {p:<52} {'written' if ok else 'NOT WRITTEN'}")
print("\nDONE_REGEN")
