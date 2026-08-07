#!/usr/bin/env bash
# Re-run C_rep1 for G5.1. The first attempt died on a parse error because the
# script was edited WHILE IT WAS RUNNING: Rscript parses incrementally, not
# all-up-front, so it re-read the file after the simulation stage and found
# shifted byte offsets. Do not edit a script that has a run in flight.
set -u
R="C:/Program Files/R/R-4.4.1/bin/Rscript.exe"
REPO="C:/Users/sethw/repos"
cd "$REPO" || exit 1

# Wait for any in-flight Rscript to finish first, so the two do not contend.
while tasklist //FI "IMAGENAME eq Rscript.exe" 2>/dev/null | grep -qi Rscript; do
  sleep 20
done
echo "no Rscript in flight at $(date +%H:%M:%S); starting C_rep1"

SEMAG_RUN_LABEL=C_rep1 SEMAG_COHORT_HEIGHT=TRUE SEMAG_HEIGHT_LOSS=TRUE \
SEMAG_BATCH_SIZE=10 \
SEMAG_OUT_RDS="$REPO/data_result/regeneration/sim_runC_rep1.rds" \
  "$R" "$REPO/legacy/R_scripts/Data_Cleaning9.8.R" \
  > "$REPO/diagnostics/run_C_rep1.log" 2>&1
echo "C_rep1 exit=$? at $(date +%H:%M:%S)"
