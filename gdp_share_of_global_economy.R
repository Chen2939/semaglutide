# =============================================================================
# Share of the global economy (2022) for the semaglutide analysis country sets
# =============================================================================
#
# Serves one sentence in the manuscript: what share of the world economy the
# modelled countries account for. Two sets are reported, both DERIVED from the
# committed model outputs rather than hardcoded:
#
#   * the food-data sample     -- every country with positive food-emission
#                                 savings
#   * the complete-data subset -- those of them that also carry survivor
#                                 emissions, i.e. the set every ratio in the
#                                 paper is computed over
#
# Why derived and not listed
# --------------------------
# This script used to hardcode a 35-country subset, a 13-country
# "missing OECD factor" list and a 5-country "missing life table" list. All three
# went stale the moment the mortality source changed: the complete-data subset is
# now 40 countries, and the five countries that had no life table -- ARE, CYP,
# MLT, ROU, SAU -- are exactly the ones that gained one. A hardcoded list cannot
# notice that, and this script would have kept reporting a share for a set the
# model no longer uses.
#
# The sets are therefore read from the same artefacts the paper's numbers come
# from, using the same filter break-even applies, so they track whatever the
# current inclusion decisions are. Change which countries are excluded and this
# script follows without edit.
#
# Exclusion reasons are derived too, from the survivor-emissions file: a country
# can fail to reach a ratio for want of an OECD per-capita factor or for want of
# mortality data, and which it is matters when writing the limitation up.
#
# Data source
# -----------
# World Bank, World Development Indicators.
# Indicator: "GDP (current US$)", code NY.GDP.MKTP.CD
#   https://data.worldbank.org/indicator/NY.GDP.MKTP.CD
# Downloaded time-series file (includes the 2022 target year), copied into the
# repo at "World Bank/World_Bank_National_GDP.csv".
#
# Note on units (current US$ vs "2022 dollars")
# ---------------------------------------------
# For a SHARE within a single year, current (nominal) US$ is appropriate: the
# numerator (a country's 2022 GDP) and the denominator (2022 world GDP) are both
# in the same year's current US$, so the price level cancels in the ratio.
# Constant/real ("2022 $") figures only matter when comparing across years.
#
# Usage: Rscript gdp_share_of_global_economy.R      (from the repository root)
# =============================================================================

# --- Configuration -----------------------------------------------------------
wb_path      <- file.path("World Bank", "World_Bank_National_GDP.csv")
breakeven_csv <- file.path("data_result", "net_emissions_with_drug.csv")
survivor_csv <- "mortality model total emissions_oecd.csv"
target_year  <- "2022"
scenario     <- "max_uptake"   # the country sets are identical across scenarios;
                               # asserted below rather than assumed
out_csv      <- file.path("data_result", "gdp_share_of_global_economy.csv")

# --- Derive the country sets from the committed model outputs -----------------
if (!file.exists(breakeven_csv)) {
  stop("Break-even output not found: ", breakeven_csv,
       "\nBuild it with: python -m drug_effect.analysis")
}
if (!file.exists(survivor_csv)) {
  stop("Survivor-emissions file not found: ", survivor_csv,
       "\nBuild it with: python -m data_visualization.consumption_ghg")
}

be <- read.csv(breakeven_csv, check.names = FALSE, stringsAsFactors = FALSE)

# The same filter break-even and every downstream aggregate applies. Kept in one
# place here so the two definitions cannot drift apart silently.
complete_mask <- function(d) {
  d$annual_food_savings_t > 0 &
    d$total_survivor_emissions_10yr > 0 &
    is.finite(d$ratio_food_to_mort)
}

sets_for <- function(sc) {
  d <- be[be$scenario == sc, ]
  if (nrow(d) == 0) stop("No rows for scenario '", sc, "' in ", breakeven_csv)
  list(
    food     = sort(unique(d$ISO[d$annual_food_savings_t > 0])),
    complete = sort(unique(d$ISO[complete_mask(d)]))
  )
}

scenarios <- sort(unique(be$scenario))
all_sets <- lapply(scenarios, sets_for)
names(all_sets) <- scenarios

# The manuscript quotes one share, so the sets had better not depend on which
# uptake scenario is read. Check rather than assume.
for (sc in scenarios) {
  if (!identical(all_sets[[sc]]$food, all_sets[[scenario]]$food) ||
      !identical(all_sets[[sc]]$complete, all_sets[[scenario]]$complete)) {
    stop("Country sets differ between scenarios (", sc, " vs ", scenario,
         "). The manuscript quotes a single share, so this needs a decision ",
         "before the number can be reported.")
  }
}

iso_food     <- all_sets[[scenario]]$food
iso_complete <- all_sets[[scenario]]$complete
iso_excluded <- setdiff(iso_food, iso_complete)

if (length(iso_food) == 0) stop("Derived food sample is empty -- check ", breakeven_csv)

# --- Why each excluded country is excluded ------------------------------------
surv <- read.csv(survivor_csv, check.names = FALSE, stringsAsFactors = FALSE)
surv <- surv[surv$scenario == scenario, ]
factor_cols <- c("oecd_nonfood_ghg_t_per_capita", "food_add_back_t_per_capita")
missing_factor <- factor_cols[!(factor_cols %in% names(surv))]
if (length(missing_factor) > 0) {
  stop("Survivor file is missing ", paste(missing_factor, collapse = ", "),
       ". Rebuild with: python -m data_visualization.consumption_ghg")
}
diff_cols <- grep("^diff_Y[0-9]+$", names(surv), value = TRUE)

no_factor <- surv$ISO[!complete.cases(surv[, factor_cols])]
zero_py   <- surv$ISO[rowSums(abs(as.matrix(surv[, diff_cols])), na.rm = TRUE) == 0]

data_status <- function(iso) {
  ifelse(iso %in% iso_complete,
         sprintf("Complete (in %d-country subset)", length(iso_complete)),
    ifelse(iso %in% no_factor, "Missing OECD survivor-emissions factor",
      ifelse(iso %in% zero_py, "Missing mortality data (zero person-years)",
             "Excluded (reason not identified)")))
}

unexplained <- iso_excluded[!(iso_excluded %in% c(no_factor, zero_py))]
if (length(unexplained) > 0) {
  warning("Excluded for an unidentified reason: ",
          paste(unexplained, collapse = ", "),
          " -- classify these before quoting the share.")
}

# Countries that have survivor data but never enter the food sample. Reported as
# a coverage note only: with no food savings they are outside the analysis, so
# their GDP does not belong in either share.
iso_no_food <- sort(setdiff(unique(surv$ISO), iso_food))

# --- Load World Bank data -----------------------------------------------------
if (!file.exists(wb_path)) stop("World Bank GDP file not found: ", wb_path)

# The World Bank export has metadata rows before the header; detect the header
# row (the one beginning with "Country Name") so we skip the right number.
raw_lines <- readLines(wb_path, warn = FALSE)
header_row <- grep("^\"?Country Name", raw_lines)[1]
if (is.na(header_row)) stop("Could not locate the 'Country Name' header row.")

gdp <- read.csv(
  wb_path,
  skip = header_row - 1,
  check.names = FALSE,
  stringsAsFactors = FALSE
)

if (!(target_year %in% names(gdp))) {
  stop("Target year column '", target_year, "' not found in the file.")
}

# --- World (global) denominator ----------------------------------------------
world_row <- gdp[gdp[["Country Code"]] == "WLD", ]
if (nrow(world_row) != 1) stop("Expected exactly one 'WLD' (World) row.")
world_gdp <- as.numeric(world_row[[target_year]])
if (is.na(world_gdp)) stop("World GDP for ", target_year, " is missing.")

# --- Per-country table --------------------------------------------------------
sample_iso <- data.frame(ISO3 = iso_food, stringsAsFactors = FALSE)
gdp_sub <- gdp[gdp[["Country Code"]] %in% iso_food,
               c("Country Name", "Country Code", target_year)]
names(gdp_sub) <- c("Country", "ISO3", "gdp_current_usd")
gdp_sub$gdp_current_usd <- as.numeric(gdp_sub$gdp_current_usd)

result <- merge(sample_iso, gdp_sub, by = "ISO3", all.x = TRUE)
result$data_status <- data_status(result$ISO3)
result$in_complete_subset <- result$ISO3 %in% iso_complete
result$share_of_world_pct <- 100 * result$gdp_current_usd / world_gdp

# Warn about any country not matched or missing 2022 GDP
missing_match <- result$ISO3[is.na(result$gdp_current_usd)]
if (length(missing_match) > 0) {
  warning("No ", target_year, " GDP found for: ",
          paste(missing_match, collapse = ", "),
          " -- these contribute 0 to the totals, which understates them.")
}

# Order: complete subset first, then by descending share
result <- result[order(!result$in_complete_subset, -result$share_of_world_pct), ]
result <- result[, c("ISO3", "Country", "data_status", "in_complete_subset",
                     "gdp_current_usd", "share_of_world_pct")]

# --- Totals -------------------------------------------------------------------
share_food     <- sum(result$share_of_world_pct, na.rm = TRUE)
share_complete <- sum(result$share_of_world_pct[result$in_complete_subset],
                      na.rm = TRUE)
n_food     <- sum(!is.na(result$gdp_current_usd))
n_complete <- sum(!is.na(result$gdp_current_usd) & result$in_complete_subset)

# --- Output -------------------------------------------------------------------
if (!dir.exists("data_result")) dir.create("data_result", recursive = TRUE)
write.csv(result, out_csv, row.names = FALSE)

cat("\n============================================================\n")
cat(" Share of global economy (", target_year,
    ", World Bank GDP current US$)\n", sep = "")
cat("============================================================\n")
cat(sprintf("Country sets derived from %s (scenario: %s)\n",
            breakeven_csv, scenario))
cat(sprintf("World GDP %s: US$ %.2f trillion\n\n",
            target_year, world_gdp / 1e12))

fmt <- result
fmt$gdp_tn <- fmt$gdp_current_usd / 1e12
for (i in seq_len(nrow(fmt))) {
  cat(sprintf("  %-4s %-40s %6.3f%%  (US$ %5.2f tn)  [%s]\n",
              fmt$ISO3[i], substr(fmt$Country[i], 1, 40),
              fmt$share_of_world_pct[i], fmt$gdp_tn[i],
              ifelse(fmt$in_complete_subset[i], "complete", "food only")))
}

cat("\n------------------------------------------------------------\n")
cat(sprintf("Complete-data subset : %.2f%% of world GDP  (n = %d)\n",
            share_complete, n_complete))
cat(sprintf("Food-data sample     : %.2f%% of world GDP  (n = %d)\n",
            share_food, n_food))
cat("------------------------------------------------------------\n")

cat(sprintf("\nExcluded from the complete-data subset (%d):\n",
            length(iso_excluded)))
if (length(iso_excluded) == 0) {
  cat("  none\n")
} else {
  for (reason in unique(data_status(iso_excluded))) {
    in_reason <- iso_excluded[data_status(iso_excluded) == reason]
    cat(sprintf("  %-42s %2d  %s\n", reason, length(in_reason),
                paste(in_reason, collapse = " ")))
  }
}

if (length(iso_no_food) > 0) {
  cat(sprintf(
    paste0("\nHave survivor data but no food savings, so outside both sets ",
           "(%d):\n  %s\n"),
    length(iso_no_food), paste(iso_no_food, collapse = " ")))
}

cat("\nSaved per-country table to: ", out_csv, "\n", sep = "")
