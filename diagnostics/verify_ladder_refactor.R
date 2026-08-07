# Verify that sec 2.15.7's structural refactor of the R hazard ladder is
# bit-identical. One function called twice, replacing two duplicated case_when
# blocks. No value change is intended and none is permitted.
#
# Mortality_model2.R cannot be executed to compare end-to-end: line 45 reads
# `test/full_simulation_results8.rds`, a path that has never existed on this
# machine (see diagnostics/reports/phase0_recon.md 2.2). So equivalence is
# established the direct way -- evaluate the OLD form and the NEW form over the
# actual bmi and new_bmi vectors the model would consume, plus a grid that hits
# every boundary, every midpoint, and the pathological inputs.
#
# ASCII only.

suppressMessages(library(dplyr))
options(width = 150)

# ---- OLD form, transcribed verbatim from the pre-refactor file --------------
old_bmi_hr <- function(bmi) {
  case_when(
    bmi < 18.5 ~ 1.51,
    bmi >= 18.5 & bmi < 20.0 ~ 1.13,
    bmi >= 20.0 & bmi < 25.0 ~ 1.00,
    bmi >= 25.0 & bmi < 27.5 ~ 1.07,
    bmi >= 27.5 & bmi < 30.0 ~ 1.20,
    bmi >= 30.0 & bmi < 35.0 ~ 1.45,
    bmi >= 35.0 & bmi < 40.0 ~ 1.94,
    bmi >= 40.0 ~ 2.76,
    TRUE ~ NA_real_
  )
}
old_new_bmi_hr <- function(new_bmi) {
  case_when(
    new_bmi < 18.5 ~ 1.51,
    new_bmi >= 18.5 & new_bmi < 20.0 ~ 1.13,
    new_bmi >= 20.0 & new_bmi < 25.0 ~ 1.00,
    new_bmi >= 25.0 & new_bmi < 27.5 ~ 1.07,
    new_bmi >= 27.5 & new_bmi < 30.0 ~ 1.20,
    new_bmi >= 30.0 & new_bmi < 35.0 ~ 1.45,
    new_bmi >= 35.0 & new_bmi < 40.0 ~ 1.94,
    new_bmi >= 40.0 ~ 2.76,
    TRUE ~ NA_real_
  )
}

# ---- NEW form, sourced from the refactored file so this cannot drift --------
src <- readLines("legacy/R_scripts/Mortality_model2.R")
i0 <- grep("^bmi_hazard_ratio <- function\\(b\\) \\{", src)
stopifnot(length(i0) == 1)
i1 <- i0 + which(trimws(src[(i0 + 1):(i0 + 40)]) == "}")[1]
eval(parse(text = paste(src[i0:i1], collapse = "\n")))
cat("new form sourced from lines", i0, "-", i1, "of the refactored file\n\n")

fail <- 0

check <- function(label, a, b) {
  same <- identical(a, b)
  # identical() covers NA placement and type; also report the numeric max diff.
  d <- suppressWarnings(max(abs(a - b), na.rm = TRUE))
  if (!is.finite(d)) d <- 0
  cat(sprintf("  %-46s identical=%-5s  max|diff|=%.3e  n=%d\n",
              label, same, d, length(a)))
  if (!same) fail <<- fail + 1
  invisible(same)
}

# ---- 1. boundary and pathological grid --------------------------------------
cat("1. boundary / pathological grid\n")
edges <- c(18.5, 20, 25, 27.5, 30, 35, 40)
grid <- sort(unique(c(
  seq(5, 80, by = 0.01),
  edges,
  edges - 1e-12, edges + 1e-12,
  edges - .Machine$double.eps * edges, edges + .Machine$double.eps * edges,
  0, 13, 59.9994, 60, 60.7824, 1e6,
  NA_real_, NaN, Inf, -Inf
)))
check("grid, bmi path", old_bmi_hr(grid), bmi_hazard_ratio(grid))
check("grid, new_bmi path", old_new_bmi_hr(grid), bmi_hazard_ratio(grid))
check("the two OLD blocks agreed with each other",
      old_bmi_hr(grid), old_new_bmi_hr(grid))

# ---- 2. the real vectors -----------------------------------------------------
cat("\n2. the actual Run C vectors the model consumes\n")
x <- readRDS("full_simulation_results9.rds")
check("bmi      (1,890,000 rows)", old_bmi_hr(x$bmi),         bmi_hazard_ratio(x$bmi))
check("new_bmi  (1,890,000 rows)", old_new_bmi_hr(x$new_bmi), bmi_hazard_ratio(x$new_bmi))

# ---- 3. and against the pre-regeneration population too ----------------------
cat("\n3. the pre-regeneration Run 8 vectors, for completeness\n")
y <- readRDS("full_simulation_results8.rds")
check("bmi      (baseline population)", old_bmi_hr(y$bmi),         bmi_hazard_ratio(y$bmi))
check("new_bmi  (baseline population)", old_new_bmi_hr(y$new_bmi), bmi_hazard_ratio(y$new_bmi))

# ---- 4. bin occupancy, so a silent all-NA pass cannot hide --------------------
cat("\n4. bin occupancy under the new function (guards against a vacuous pass)\n")
tb <- table(bmi_hazard_ratio(x$bmi), useNA = "ifany")
for (k in names(tb)) cat(sprintf("     HR %-6s %10d rows\n", k, tb[[k]]))
cat(sprintf("     NA rows: %d\n", sum(is.na(bmi_hazard_ratio(x$bmi)))))

cat("\n")
if (fail > 0) {
  stop(sprintf("REFACTOR VERIFICATION FAILED on %d check(s).", fail))
}
cat("REFACTOR VERIFICATION PASS -- bit-identical on every check.\n")
