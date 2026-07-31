#!/bin/sh
# Full regeneration pass after the survival-weighting (pi) change.
# consumption_ghg is deliberately NOT here: the survivor food factor was verified
# bit-identical under pi (diagnostics/verify_survivor_invariant.py), so the
# survivor-emissions files are already current.
# reference/metrics.py is run separately, after its stale configuration is
# reconciled.
set -u
cd /c/Users/sethw/repos || exit 1
export PYTHONUTF8=1
PY="/c/Python314/python.exe"
LOG=diagnostics/full_pass
mkdir -p "$LOG"

run() {
  name="$1"; shift
  printf '=== %-44s ' "$name"
  if "$@" > "$LOG/$name.log" 2>&1; then
    echo "OK"
  else
    echo "FAILED (see $LOG/$name.log)"
    echo "$name" >> "$LOG/FAILURES"
  fi
}

rm -f "$LOG/FAILURES"

run breakeven_analysis            $PY -m data_visualization.breakeven_analysis
run survivor_manuscript_numbers   $PY -m data_visualization.survivor_manuscript_numbers
run generate_emissions_figure     $PY -m data_visualization.generate_emissions_figure
run generate_dashboard_figure     $PY -m data_visualization.generate_dashboard_figure
run generate_rebound_figure       $PY -m data_visualization.generate_rebound_figure
run generate_rebound_validation   $PY -m data_visualization.generate_rebound_validation
run generate_waterfall_figure     $PY -m data_visualization.generate_waterfall_figure
run generate_waterfall_1yr        $PY -m data_visualization.generate_waterfall_1yr_figure
run generate_waterfall_combined   $PY -m data_visualization.generate_waterfall_combined_figure
run diet_analysis                 $PY -m diet_sensitivity.analysis
run diet_combined_analysis        $PY -m diet_sensitivity.combined_analysis
run diet_sensitivity_overview     $PY -m diet_sensitivity.sensitivity_overview
run diet_sensitivity_suite        $PY -m diet_sensitivity.sensitivity_suite
run diet_tornado_analysis         $PY -m diet_sensitivity.tornado_analysis
run drug_effect_analysis          $PY -m drug_effect.analysis
run build_supplement_table        $PY scripts/build_supplement_table.py

echo
if [ -f "$LOG/FAILURES" ]; then
  echo "FAILURES:"; cat "$LOG/FAILURES"
else
  echo "All steps completed."
fi
