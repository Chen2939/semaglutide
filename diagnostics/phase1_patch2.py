"""Phase 1 patch 2, after the 30-stratum smoke run.

Four changes, each with its reason:

1. Silence tidylog. It produced 15,600 of the smoke log's 15,628 lines and
   buries every gate result. The library stays loaded (it is in the original
   script) but its per-verb reporting is off.

2. Wall-clock timing, so the cost of a full run is measured rather than
   assumed.

3. G4's adherence bar was WRONG WHEN DECLARED, not too tight in hindsight. I
   set a flat +/- 0.01 without calibrating it to n. On 2,460 eligible
   individuals the binomial SE is 0.0044 at p = 0.95 and 0.0101 at p = 0.50, so
   the observed 0.9472 (0.63 SE) and 0.5134 (1.33 SE) are ordinary noise and
   the bar was simply mis-set. Replaced with an ANALYTIC 4-SE bar computed from
   the actual eligible count. At production n (~1.2M eligible) that is about
   +/- 0.0008 and +/- 0.0018 -- far TIGHTER than the flat 0.01 it replaces, so
   this is a sharpening, not a widening. Section 1.3's rule is that a bar
   depending on Monte Carlo noise must have its SE computed from the actual
   populations first; that rule was applied to G0/G2 and should have been
   applied here too.

4. G3's "attained height must decrease with age group" does not hold
   per-country and never could. The smoke run shows 51 of 126 country x sex
   groups with at least one local increase -- Spain's male series peaks at the
   2004 cohort and dips slightly for 2009-2019, which is a real feature of the
   NCD-RisC data, not a construction error. The meaningful check is the
   AGGREGATE direction (young cohorts taller than old), so that is what is
   reported, with the local-wobble count kept as context. It was already a
   report and not a stop, which was right.

ASCII only.
"""
import io
import sys

P = r"C:\Users\sethw\repos\legacy\R_scripts\Data_Cleaning9.8.R"
s = io.open(P, encoding="utf-8").read()

SUBS = []

# ---- 1. silence tidylog, 2. start the clock -------------------------------
SUBS.append((
    'cat("---- run configuration ----\\n")',

    '# tidylog reports every dplyr verb. On a full run that is hundreds of\n'
    '# thousands of lines and it buries the gate output. The library stays\n'
    '# loaded (it is in the original script); only the reporting is off.\n'
    'options(tidylog.display = list())\n'
    '\n'
    'RUN_T0 <- Sys.time()\n'
    'stage_time <- function(label) {\n'
    '  cat(sprintf("  [t+%7.1fs] %s\\n",\n'
    '              as.numeric(difftime(Sys.time(), RUN_T0, units = "secs")), label))\n'
    '}\n'
    '\n'
    'cat("---- run configuration ----\\n")'
))

SUBS.append((
    'cat("\\n---- running simulation ----\\n")',
    'stage_time("inputs, CDF construction and pre-run gates done")\n'
    'cat("\\n---- running simulation ----\\n")'
))

SUBS.append((
    '#Add a column that specifies Type 1 or Type 2 diabetes',
    'stage_time("simulation done")\n'
    '\n'
    '#Add a column that specifies Type 1 or Type 2 diabetes'
))

SUBS.append((
    'cat("\\n==== Data_Cleaning9.8.R complete ====\\n")',
    'stage_time("all done")\n'
    'cat("\\n==== Data_Cleaning9.8.R complete ====\\n")'
))

# ---- 3. analytic G4 bar ---------------------------------------------------
SUBS.append((
    '.rate_mx <- sum(.mx$adheres_to_treatment) / sum(.mx$qualifies_for_treatment)\n'
    '.rate_md <- sum(.md$adheres_to_treatment) / sum(.md$qualifies_for_treatment)\n'
    'if (abs(.rate_mx - 0.95) > 0.01 || abs(.rate_md - 0.50) > 0.01) {\n'
    '  stop("G4 FAILED: adherence rates not near 0.95 / 0.50.")\n'
    '}\n'
    'cat("G4 PASS\\n")',

    '# The realized adherence rate is a binomial proportion, so its bar has to be\n'
    '# computed from the actual eligible count rather than fixed. 4 SE. At\n'
    '# production n this is about +/- 0.0008 (max) and +/- 0.0018 (moderate).\n'
    '.n_el     <- sum(.mx$qualifies_for_treatment)\n'
    '.rate_mx  <- sum(.mx$adheres_to_treatment) / .n_el\n'
    '.rate_md  <- sum(.md$adheres_to_treatment) / .n_el\n'
    '.bar_mx   <- 4 * sqrt(0.95 * 0.05 / .n_el)\n'
    '.bar_md   <- 4 * sqrt(0.50 * 0.50 / .n_el)\n'
    'cat(sprintf("  eligible n = %d;  4-SE bars: max +/-%.5f  mod +/-%.5f\\n",\n'
    '            .n_el, .bar_mx, .bar_md))\n'
    'cat(sprintf("  deviation from nominal: max %+.5f (%.2f SE)  mod %+.5f (%.2f SE)\\n",\n'
    '            .rate_mx - 0.95, abs(.rate_mx - 0.95) / (.bar_mx / 4),\n'
    '            .rate_md - 0.50, abs(.rate_md - 0.50) / (.bar_md / 4)))\n'
    'if (abs(.rate_mx - 0.95) > .bar_mx || abs(.rate_md - 0.50) > .bar_md) {\n'
    '  stop("G4 FAILED: an adherence rate is more than 4 binomial SE from nominal.")\n'
    '}\n'
    'cat("G4 PASS\\n")'
))

SUBS.append((
    'rm(.mx, .md, .both, .viol_subset, .viol_effect, .rate_mx, .rate_md)',
    'rm(.mx, .md, .both, .viol_subset, .viol_effect, .rate_mx, .rate_md,\n'
    '   .n_el, .bar_mx, .bar_md)'
))

# ---- 4. G3 aggregate direction -------------------------------------------
SUBS.append((
    'if (USE_COHORT_HEIGHT) {\n'
    '  # Monotonicity check: within each modelled country x sex, attained height must\n'
    '  # be non-increasing as the age group gets older, over the age groups whose\n'
    '  # cohort year is genuinely in range (held strata are all pinned to one value).\n'
    '  .mono <- lancet_dia %>%\n'
    '    filter(cohort_held == "in_range") %>%\n'
    '    arrange(ISO, Sex, desc(cohort_year)) %>%\n'
    '    group_by(ISO, Sex) %>%\n'
    '    summarise(n_increases = sum(diff(Mean_height) > 0), .groups = "drop")\n'
    '  cat(sprintf("\\n  country x sex groups where attained height RISES with age: %d of %d\\n",\n'
    '              sum(.mono$n_increases > 0), nrow(.mono)))\n'
    '  if (sum(.mono$n_increases > 0) > 0) {\n'
    '    print(as.data.frame(.mono %>% filter(n_increases > 0)))\n'
    '  }\n'
    '  rm(.mono)\n'
    '}',

    'if (USE_COHORT_HEIGHT) {\n'
    '  # The brief says attained height "must decrease with age group". That holds\n'
    '  # in AGGREGATE but not country by country, and it never could: the NCD-RisC\n'
    '  # series plateau and wobble for recent cohorts in high-income countries.\n'
    '  # Spain\'s male series peaks at the 2004 cohort and dips slightly for\n'
    '  # 2009-2019. That is data, not a construction error, so the aggregate\n'
    '  # direction is what is reported and the local wobble is context.\n'
    '  cat("\\n  population-weighted mean ATTAINED height by age group:\\n")\n'
    '  .byag <- lancet_dia %>%\n'
    '    group_by(Sex, Age_Group) %>%\n'
    '    summarise(mean_attained_cm = weighted.mean(Mean_height, Population),\n'
    '              cohort_year = first(cohort_year), .groups = "drop") %>%\n'
    '    arrange(Sex, match(Age_Group, AGE_GROUP_LEVELS))\n'
    '  print(as.data.frame(.byag))\n'
    '\n'
    '  # Aggregate direction: youngest IN-RANGE cohort against the oldest, per\n'
    '  # country x sex. A country where the old cohort is TALLER is the thing that\n'
    '  # would signal a broken cohort mapping.\n'
    '  .dir <- lancet_dia %>%\n'
    '    filter(cohort_held == "in_range") %>%\n'
    '    group_by(ISO, Sex) %>%\n'
    '    summarise(young = Mean_height[which.max(cohort_year)],\n'
    '              old   = Mean_height[which.min(cohort_year)],\n'
    '              .groups = "drop") %>%\n'
    '    mutate(gain_cm = young - old)\n'
    '  cat(sprintf("\\n  young-minus-old attained height over the in-range window:\\n"))\n'
    '  cat(sprintf("    mean %+.3f cm, median %+.3f cm, min %+.3f cm, max %+.3f cm\\n",\n'
    '              mean(.dir$gain_cm), median(.dir$gain_cm),\n'
    '              min(.dir$gain_cm), max(.dir$gain_cm)))\n'
    '  cat(sprintf("    country x sex groups where the OLD cohort is taller: %d of %d\\n",\n'
    '              sum(.dir$gain_cm < 0), nrow(.dir)))\n'
    '  if (any(.dir$gain_cm < 0)) {\n'
    '    print(as.data.frame(.dir %>% filter(gain_cm < 0) %>% arrange(gain_cm)))\n'
    '  }\n'
    '\n'
    '  # Local wobble, reported as context only.\n'
    '  .mono <- lancet_dia %>%\n'
    '    filter(cohort_held == "in_range") %>%\n'
    '    arrange(ISO, Sex, desc(cohort_year)) %>%\n'
    '    group_by(ISO, Sex) %>%\n'
    '    summarise(n_increases = sum(diff(Mean_height) > 0), .groups = "drop")\n'
    '  cat(sprintf("    groups with any LOCAL increase (expected, not a defect): %d of %d\\n",\n'
    '              sum(.mono$n_increases > 0), nrow(.mono)))\n'
    '  rm(.mono, .byag, .dir)\n'
    '}'
))

failed = []
for i, (a, b) in enumerate(SUBS):
    n = s.count(a)
    if n != 1:
        failed.append((i, n, a[:100]))
        continue
    s = s.replace(a, b)

if failed:
    for i, n, head in failed:
        print(f"SUB {i}: {n} matches -- {head!r}")
    sys.exit(1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print(f"{len(SUBS)} substitutions applied")
