# G9 -- hazard ladder, deterministic. Four assertions, all exact or 1e-6, plus
# one report. Run AFTER sec 2.15's commit 2.
#
# Assertion 2 is the one with a trap in it. Integrating hr_top against the
# CLOSED-FORM segment means makes the assertion (2.76/K)*K and tests nothing.
# It is integrated here against THE ELEVEN-KNOT CDF THE SAMPLER ACTUALLY
# RECEIVES, produced by the production fit_bmi_cdf() sourced out of
# Data_Cleaning9.8.R and fed the real NCD-RisC stratum shares -- so it
# cross-checks the closed form and the constructed object, which is the pair
# that can actually diverge.
#
# ASCII only.

suppressMessages(library(dplyr))
options(width = 160)

fail <- 0
note <- function(ok, label, detail) {
  cat(sprintf("  [%s] %-52s %s\n", if (ok) "PASS" else "FAIL", label, detail))
  if (!ok) fail <<- fail + 1
}

# ---- source the production objects, do not re-type them ---------------------
grab <- function(file, pattern, nlines = 60) {
  src <- readLines(file)
  i <- grep(pattern, src)
  if (length(i) != 1) stop("could not uniquely locate ", pattern, " in ", file)
  j <- i + which(trimws(src[(i + 1):(i + nlines)]) == "}")[1]
  eval(parse(text = paste(src[i:j], collapse = "\n")), envir = globalenv())
}

DC <- "legacy/R_scripts/Data_Cleaning9.8.R"
MM <- "legacy/R_scripts/Mortality_model2.R"

# Extract one top-level assignment starting at a matching line, accumulating
# lines until it parses. Some of these span two lines and are followed by a
# multi-line stopifnot(), so a fixed line count does not work.
grab_assign <- function(src, pattern) {
  i <- grep(pattern, src)
  if (length(i) != 1) stop("could not uniquely locate ", pattern)
  for (n in 0:8) {
    txt <- paste(src[i:(i + n)], collapse = "\n")
    e <- tryCatch(parse(text = txt), error = function(...) NULL)
    if (!is.null(e) && length(e) == 1) {
      eval(e, envir = globalenv())
      return(invisible(TRUE))
    }
  }
  stop("could not parse the assignment at ", pattern)
}

# constants from the BMI construction
src <- readLines(DC)
for (nm in c("^BMI_LOWER_BOUND <- ", "^BMI_BAND_EDGES <- ", "^BMI_TOP_EDGES <- ",
             "^CLASS3_N     <- ", "^CLASS3_SHARE <- ", "^CLASS3_TAIL  <- ")) {
  grab_assign(src, nm)
}
grab(DC, "^fit_bmi_cdf <- function\\(props\\) \\{")

# the hazard ladder and its constants from the mortality model
msrc <- readLines(MM)
for (nm in c("^CLASS3_N      <- ", "^CLASS3_SHARE  <- ", "^HR_TOP_BASE   <- ",
             "^HR_PER_5      <- ", "^HR_TOP_K      <- ", "^HR_TOP_ANCHOR <- ")) {
  grab_assign(msrc, nm)
}
grab_assign(msrc, "^hr_top <- function")
grab(MM, "^bmi_hazard_ratio <- function\\(b\\) \\{")

cat("G9 -- hazard ladder\n\n")

# ============================================================ assertion 1
cat("1. K and HR_TOP_ANCHOR computed from CLASS3_SHARE\n")
note(abs(HR_TOP_K - 1.395788) < 1e-6, "K == 1.395788 to 1e-6",
     sprintf("K = %.9f", HR_TOP_K))
note(abs(HR_TOP_ANCHOR - 1.977378) < 1e-6, "HR_TOP_ANCHOR == 1.977378 to 1e-6",
     sprintf("anchor = %.9f", HR_TOP_ANCHOR))
note(isTRUE(all.equal(CLASS3_SHARE, c(6803, 1978, 627, 156) / 9564)),
     "CLASS3_SHARE matches the Kitahara counts", "participants, not deaths")

# ============================================================ assertion 2
cat("\n2. composition-weighted mean of hr_top, integrated against the\n")
cat("   ELEVEN-KNOT CDF the sampler receives (not the closed form)\n")

lancet <- readRDS("diagnostics/inputs_cache_cohort.rds")$lancet_dia
SHARE_COLS <- c("BMI_under_18.5", "BMI_18.5to20", "BMI_20to25",
                "BMI_25to30", "BMI_30to35", "BMI_35to40", "BMI_over_40")
cat(sprintf("   strata: %d\n", nrow(lancet)))

# Fine grid on the conditional top band, inverted through the constructed CDF.
NU <- 200000
worst <- 0; worst_lab <- NA_character_; worst_bmi <- 0
for (i in seq_len(nrow(lancet))) {
  props <- as.numeric(lancet[i, SHARE_COLS])
  d <- fit_bmi_cdf(props)
  F40 <- d$cdf[7]                      # knot at BMI 40
  if (1 - F40 < 1e-12) next            # empty top band, nothing to integrate
  u <- F40 + (1 - F40) * ((seq_len(NU) - 0.5) / NU)
  b <- approx(d$cdf, d$x, u, rule = 2)$y
  m <- mean(hr_top(b))
  e <- abs(m - 2.76)
  if (e > worst) {
    worst <- e
    worst_lab <- paste(lancet$ISO[i], lancet$Sex[i], lancet$Age_Group[i], sep = "/")
    worst_bmi <- mean(b)
  }
}
note(worst < 1e-6, "mean hr_top over the top band == 2.76 to 1e-6",
     sprintf("max dev %.3e  (worst %s, mean BMI %.4f)", worst, worst_lab, worst_bmi))

# ============================================================ assertion 3
# The plan says "monotonically non-decreasing across the WHOLE BMI range".
# That is wrong as written and always was: the published ladder is J-shaped, so
# it DECREASES twice below BMI 20 (1.51 -> 1.13 at 18.5, 1.13 -> 1.00 at 20),
# because thin people carry elevated all-cause mortality. Sec 2.15 does not
# touch those bins -- assertion 4 proves the sub-40 range is bit-identical --
# so the correct gate is:
#   (a) monotone non-decreasing from BMI 20 upward, the reference bin and the
#       only region the change can affect; and
#   (b) sec 2.15 introduces no new non-monotonicity anywhere, tested by
#       requiring the OLD and NEW ladders to have the SAME dip set.
cat("\n3. monotonicity\n")
grid <- sort(unique(c(seq(5, 80, by = 0.001),
                      18.5, 20, 25, 27.5, 30, 35, 40, 45, 50, 55, 60)))
old_ladder0 <- function(b) {
  case_when(
    b < 18.5 ~ 1.51, b >= 18.5 & b < 20.0 ~ 1.13, b >= 20.0 & b < 25.0 ~ 1.00,
    b >= 25.0 & b < 27.5 ~ 1.07, b >= 27.5 & b < 30.0 ~ 1.20,
    b >= 30.0 & b < 35.0 ~ 1.45, b >= 35.0 & b < 40.0 ~ 1.94,
    b >= 40.0 ~ 2.76, TRUE ~ NA_real_
  )
}
h  <- bmi_hazard_ratio(grid)
h0 <- old_ladder0(grid)
dips_new <- which(diff(h)  < -1e-12)
dips_old <- which(diff(h0) < -1e-12)

cat("   dips present in BOTH ladders (pre-existing J-shape, out of scope):\n")
if (length(dips_old)) {
  print(data.frame(bmi = grid[dips_old], from = h0[dips_old],
                   to = h0[dips_old + 1]))
}
note(identical(grid[dips_new], grid[dips_old]),
     "sec 2.15 introduces no NEW non-monotonicity",
     sprintf("old %d dip(s), new %d dip(s), same locations",
             length(dips_old), length(dips_new)))

above20 <- grid >= 20
h20 <- h[above20]
note(all(diff(h20) >= -1e-12),
     "non-decreasing from BMI 20 upward",
     sprintf("n = %d, min step = %.3e", length(h20), min(diff(h20))))

old40 <- 2.76 - 1.94
new40 <- HR_TOP_ANCHOR - 1.94
cat(sprintf("   40-boundary discontinuity: %.4f -> %.4f\n", old40, new40))
note(abs(new40 - 0.0374) < 1e-4, "40-boundary step narrows to 0.0374",
     sprintf("%.6f", new40))

# ============================================================ assertion 4
cat("\n4. every bin below 40 bit-identical to the pre-2.15 code (R side)\n")
old_ladder <- function(b) {
  case_when(
    b < 18.5 ~ 1.51, b >= 18.5 & b < 20.0 ~ 1.13, b >= 20.0 & b < 25.0 ~ 1.00,
    b >= 25.0 & b < 27.5 ~ 1.07, b >= 27.5 & b < 30.0 ~ 1.20,
    b >= 30.0 & b < 35.0 ~ 1.45, b >= 35.0 & b < 40.0 ~ 1.94,
    b >= 40.0 ~ 2.76, TRUE ~ NA_real_
  )
}
edges <- c(18.5, 20, 25, 27.5, 30, 35, 40)
sub40 <- sort(unique(c(seq(5, 39.999, by = 0.001), edges[-7],
                       edges - 1e-12, edges - .Machine$double.eps * edges)))
sub40 <- sub40[sub40 < 40]
note(identical(old_ladder(sub40), bmi_hazard_ratio(sub40)),
     "identical for every BMI < 40",
     sprintf("n = %d, max|diff| = %.3e", length(sub40),
             max(abs(old_ladder(sub40) - bmi_hazard_ratio(sub40)))))

x <- readRDS("full_simulation_results9.rds")
for (col in c("bmi", "new_bmi")) {
  v <- x[[col]][x[[col]] < 40]
  note(identical(old_ladder(v), bmi_hazard_ratio(v)),
       sprintf("identical on the real `%s` below 40", col),
       sprintf("n = %d", length(v)))
}
# and the top band MUST have changed, or the change did not land
v <- x$bmi[x$bmi >= 40]
note(!identical(old_ladder(v), bmi_hazard_ratio(v)),
     "top band DID change (guards a vacuous pass)",
     sprintf("n = %d, mean %.4f -> %.4f", length(v),
             mean(old_ladder(v)), mean(bmi_hazard_ratio(v))))

# ============================================================ reported only
cat("\nREPORTED, NOT GATED\n")
nb_bmi <- sum(x$bmi > 60)
nb_new <- sum(x$new_bmi > 60)
cat(sprintf("   rows where pmin(b,60) binds on `bmi`     : %d\n", nb_bmi))
cat(sprintf("   rows where pmin(b,60) binds on `new_bmi` : %d of %d (%.2e)\n",
            nb_new, nrow(x), nb_new / nrow(x)))
cat(sprintf("   max realized bmi / new_bmi               : %.4f / %.4f\n",
            max(x$bmi), max(x$new_bmi)))
cat("   (the new_bmi binding is expected and seed-dependent; do not assert it\n")
cat("    never happens)\n")

cat("\n")
if (fail > 0) stop(sprintf("G9 FAILED on %d assertion(s).", fail))
cat("G9 PASS -- all four assertions.\n")
