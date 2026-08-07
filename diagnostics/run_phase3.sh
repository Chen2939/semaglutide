#!/usr/bin/env bash
# Phase 3 separability runs, plus the two G5 reproducibility runs.
# Sequential: each holds the 1.89M-row frame twice over, so running them
# concurrently risks swapping and making both slower than running them in turn.
set -u
R="C:/Program Files/R/R-4.4.1/bin/Rscript.exe"
REPO="C:/Users/sethw/repos"
S="$REPO/legacy/R_scripts/Data_Cleaning9.8.R"
OUT="$REPO/data_result/regeneration"
mkdir -p "$OUT"
cd "$REPO" || exit 1

go () {  # go <label> <cohort> <loss> <batch> <outpath>
  echo "=== $1: cohort=$2 loss=$3 batch=$4 -> $5"
  SEMAG_RUN_LABEL="$1" SEMAG_COHORT_HEIGHT="$2" SEMAG_HEIGHT_LOSS="$3" \
  SEMAG_BATCH_SIZE="$4" SEMAG_OUT_RDS="$5" \
    "$R" "$S" > "$REPO/diagnostics/run_$1.log" 2>&1
  echo "    exit=$? $(date +%H:%M:%S)"
}

# Phase 3 separability
go A FALSE FALSE 10 "$OUT/sim_runA.rds"
go B TRUE  FALSE 10 "$OUT/sim_runB.rds"
# G5 reproducibility: same seed repeat, and batch 10 -> 7
go C_rep1 TRUE TRUE 10 "$OUT/sim_runC_rep1.rds"
go C_bs7  TRUE TRUE  7 "$OUT/sim_runC_bs7.rds"
echo "ALL PHASE 3 RUNS DONE"
