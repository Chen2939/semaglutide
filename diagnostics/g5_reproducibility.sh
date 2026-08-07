#!/usr/bin/env bash
# G5 -- reproducibility. Two checks, both requiring BIT-IDENTICAL output:
#
#   1. Same seed, same batch size, run twice.
#   2. Same seed, batch size 10 -> 7.
#
# Check 2 is the one that actually tests sec 2.8. A single top-level seed would
# pass check 1 and fail check 2, because reordering the strata across batch
# boundaries would reshuffle the RNG stream. Per-stratum seeding makes the run
# order-independent.
#
# Compares the serialized .rds byte for byte. That is stricter than comparing
# columns and needs no tolerance argument -- but note saveRDS() compresses, so a
# match is genuinely a match while a mismatch still has to be diagnosed at the
# column level (g5_diff.R does that).
set -u

R="C:/Program Files/R/R-4.4.1/bin/Rscript.exe"
REPO="C:/Users/sethw/repos"
SCRIPT="$REPO/legacy/R_scripts/Data_Cleaning9.8.R"
OUTDIR="$REPO/data_result/regeneration"
LOGDIR="$REPO/diagnostics"

cd "$REPO" || exit 1

run () {  # run <label> <batch_size>
  local label="$1" bs="$2"
  echo "--- G5 run $label (batch_size=$bs) ---"
  SEMAG_RUN_LABEL="$label" \
  SEMAG_COHORT_HEIGHT=TRUE \
  SEMAG_HEIGHT_LOSS=TRUE \
  SEMAG_BATCH_SIZE="$bs" \
    "$R" "$SCRIPT" > "$LOGDIR/run_$label.log" 2>&1
  local rc=$?
  echo "    exit=$rc  log=$LOGDIR/run_$label.log"
  return $rc
}

run C_rep1 10 || exit 1
run C_bs7   7 || exit 1

echo
echo "=== G5 comparison (bar: bit-identical) ==="
for f in sim_runC sim_runC_rep1 sim_runC_bs7; do
  printf "  %-22s %s\n" "$f" "$(md5sum "$OUTDIR/$f.rds" | cut -d' ' -f1)"
done

A=$(md5sum "$OUTDIR/sim_runC.rds"      | cut -d' ' -f1)
B=$(md5sum "$OUTDIR/sim_runC_rep1.rds" | cut -d' ' -f1)
C=$(md5sum "$OUTDIR/sim_runC_bs7.rds"  | cut -d' ' -f1)

fail=0
if [ "$A" = "$B" ]; then echo "  G5.1 same seed, same batch : PASS"; else echo "  G5.1 same seed, same batch : FAIL"; fail=1; fi
if [ "$A" = "$C" ]; then echo "  G5.2 batch 10 vs 7         : PASS"; else echo "  G5.2 batch 10 vs 7         : FAIL"; fail=1; fi

if [ "$fail" -ne 0 ]; then
  echo "  G5 FAILED -- diagnose with diagnostics/g5_diff.R before touching the bar."
  exit 1
fi
echo "  G5 PASS"
