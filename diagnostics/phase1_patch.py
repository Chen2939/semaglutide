"""Phase 1 patch: wire SMOKE mode through the gates and redirect the plot
device. Kept as a file rather than a heredoc so a failed match can be debugged
instead of re-guessed. ASCII only.
"""
import io
import sys

P = r"C:\Users\sethw\repos\legacy\R_scripts\Data_Cleaning9.8.R"
s = io.open(P, encoding="utf-8").read()

SUBS = []

SUBS.append((
    'if (length(.iso) != 63) stop(sprintf("G8 FAILED: %d countries, expected 63.", length(.iso)))\n'
    'cat("G8 PASS\\n")',

    'if (SMOKE) {\n'
    '  cat("G8 SKIPPED (smoke run -- strata capped, country set truncated by construction)\\n")\n'
    '} else if (length(.iso) != 63) {\n'
    '  stop(sprintf("G8 FAILED: %d countries, expected 63.", length(.iso)))\n'
    '} else {\n'
    '  cat("G8 PASS\\n")\n'
    '}'
))

SUBS.append((
    'cat(sprintf("\\nWriting %s\\n", OUT_RDS))\n'
    'dir.create(dirname(OUT_RDS), showWarnings = FALSE, recursive = TRUE)\n'
    'saveRDS(all_results, OUT_RDS)',

    'if (SMOKE) {\n'
    '  cat("\\nSMOKE RUN -- OUT_RDS deliberately NOT written.\\n")\n'
    '} else {\n'
    '  cat(sprintf("\\nWriting %s\\n", OUT_RDS))\n'
    '  dir.create(dirname(OUT_RDS), showWarnings = FALSE, recursive = TRUE)\n'
    '  saveRDS(all_results, OUT_RDS)\n'
    '}'
))

SUBS.append((
    'full_results <- readRDS(OUT_RDS)',
    'full_results <- if (SMOKE) all_results else readRDS(OUT_RDS)'
))

SUBS.append((
    'cat("\\n---- G2 sampled BMI category shares ----\\n")\n'
    '.g0 <- readRDS(file.path(DIAG_DIR, "g0_calibration.rds"))',

    'cat("\\n---- G2 sampled BMI category shares ----\\n")\n'
    'if (SMOKE) {\n'
    '  cat("G2 SKIPPED (smoke run -- the pooled bar is calibrated on the full population)\\n")\n'
    '} else {\n'
    '.g0 <- readRDS(file.path(DIAG_DIR, "g0_calibration.rds"))'
))

SUBS.append((
    'cat("G2 PASS\\n")\n\n'
    '##########################################\n'
    '#####  sec 2.11 -- diabetes, REPORT ONLY #',

    'cat("G2 PASS\\n")\n'
    '}\n\n'
    '##########################################\n'
    '#####  sec 2.11 -- diabetes, REPORT ONLY #'
))

SUBS.append((
    'cat("\\n---- 2.11 diabetes realized vs target prevalence ----\\n")\n'
    '.dia <- .base %>%',

    'cat("\\n---- 2.11 diabetes realized vs target prevalence ----\\n")\n'
    '.base <- full_results %>% filter(scenario == "max_uptake")\n'
    '.dia <- .base %>%'
))

SUBS.append((
    'rm(.g0, .base, .target, .realized, .cmp, .by_country, .jk, .fail, .dia,\n'
    '   .clipped_rows, .pooled_real, .pooled_targ, .pooled_diff)',

    'rm(list = intersect(c(".g0", ".base", ".target", ".realized", ".cmp",\n'
    '                      ".by_country", ".jk", ".fail", ".dia", ".clipped_rows",\n'
    '                      ".pooled_real", ".pooled_targ", ".pooled_diff"),\n'
    '                    ls(all.names = TRUE)))'
))

SUBS.append((
    '####################################\n'
    '#########   VISUALIZATION  #########\n'
    '####################################',

    '####################################\n'
    '#########   VISUALIZATION  #########\n'
    '####################################\n\n'
    "# Rscript's default device drops an Rplots.pdf in the working directory.\n"
    '# Send it somewhere deliberate instead.\n'
    'pdf(file.path(DIAG_DIR, "data_cleaning_plots.pdf"), width = 8, height = 6)'
))

SUBS.append((
    'cat("\\n==== Data_Cleaning9.8.R complete ====\\n")',
    'try(dev.off(), silent = TRUE)\n'
    'cat("\\n==== Data_Cleaning9.8.R complete ====\\n")'
))

failed = []
for i, (a, b) in enumerate(SUBS):
    n = s.count(a)
    if n != 1:
        failed.append((i, n, a[:90]))
        continue
    s = s.replace(a, b)

if failed:
    for i, n, head in failed:
        print(f"SUB {i}: {n} matches -- {head!r}")
    sys.exit(1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print(f"{len(SUBS)} substitutions applied")
