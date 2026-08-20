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

# Food-energy coverage: the same two sets, measured against world food supply.
fbs_path     <- file.path("Food data",
                          "FoodBalanceSheets_E_All_Data_(Normalized)",
                          "FoodBalanceSheets_E_All_Data_(Normalized).csv")
iso_map_path <- file.path("Food data", "faostat_country_mapping.csv")
kcal_out_csv <- file.path("diagnostics", "calorie_share_coverage.csv")
fbs_year     <- 2022L
kcal_item    <- "Grand Total"                 # FAOSTAT's own national aggregate
kcal_element <- "Food supply (kcal)"          # national TOTAL, million kcal/year
world_area   <- "World"

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

# --- Share of global food energy supply ---------------------------------------
# The second half of the same manuscript sentence, over THE SAME two sets. It
# lives here rather than in a script of its own for one reason: a second script
# would have to derive the sets again, and two derivations of one thing is
# exactly the failure this file was rewritten to remove (see the header). Both
# vectors below are the ones derived above, reused as-is -- nothing here
# re-derives them and no ISO is listed anywhere in this section.
#
# Which element, and why no population step
# -----------------------------------------
# FAOSTAT publishes the national TOTAL, "Food supply (kcal)" in million kcal per
# year, alongside the familiar per-capita rate. Measured on this vintage: the
# World row is 8.658029e+09 million kcal against a World per-capita rate of
# 2984.86 kcal/cap/day, which back out to 7.95 billion people -- the two agree,
# and the total is annual. Reading the total directly removes the population
# multiplication entirely, and with it the question of whose population to use:
# FAO divided by its own, so anything else would turn an identity into an
# approximation.
#
# "Grand Total" is FAOSTAT's published national aggregate and is taken as
# published. It is NOT rebuilt by summing the mapped items -- the Food Balance
# Sheets carry parent items and their components in the same table, which is the
# double-count `pipeline.py` keeps AGGREGATE_ITEMS to avoid. Taking the
# aggregate sidesteps that rather than re-solving it.
if (!requireNamespace("data.table", quietly = TRUE)) {
  stop("data.table is required to read the Food Balance Sheets (about 610 MB).",
       "\nInstall it with: install.packages('data.table')")
}
if (!file.exists(fbs_path)) {
  stop("FAOSTAT Food Balance Sheets not found: ", fbs_path,
       "\nSee 'External data' in README.md -- this is a documented download.")
}
if (!file.exists(iso_map_path)) stop("ISO mapping not found: ", iso_map_path)

# select= keeps the read to the seven columns that matter; the frame is subset to
# the target year and element immediately and the full table dropped, so the
# 610 MB file never sits in memory in full.
fbs_all <- data.table::fread(
  fbs_path,
  select = c("Area Code", "Area", "Item", "Element", "Year", "Unit", "Value"),
  showProgress = FALSE
)
fbs <- fbs_all[Year == fbs_year & Item == kcal_item & Element == kcal_element]
rm(fbs_all)
invisible(gc(verbose = FALSE))

if (nrow(fbs) == 0) {
  stop("No rows for Item '", kcal_item, "' / Element '", kcal_element,
       "' / Year ", fbs_year, " in ", fbs_path,
       "\nFAOSTAT element labels vary between vintages -- inspect ",
       "unique(Element) for this item before assuming a replacement.")
}
kcal_unit <- unique(fbs$Unit)
if (length(kcal_unit) != 1 || kcal_unit != "million Kcal") {
  stop("Unexpected unit for '", kcal_element, "': ",
       paste(kcal_unit, collapse = ", "), " (expected 'million Kcal'). ",
       "The million-kcal scaling below would be wrong.")
}

# --- Denominator: FAOSTAT's published World row -------------------------------
world_kcal_row <- fbs[Area == world_area]
if (nrow(world_kcal_row) == 1) {
  world_kcal_year  <- as.numeric(world_kcal_row$Value) * 1e6
  kcal_denom_source <- "FAOSTAT published 'World' row"
} else {
  # Fallback only. Guarded twice: regional aggregates carry Area Code >= 5000,
  # and the 'China' aggregate (code 351) spans 'China, mainland' (41) plus Hong
  # Kong, Macao and Taiwan, so keeping both double-counts all four. NOTE the
  # codes: this vintage numbers mainland 41 and the aggregate 351; there is no
  # 357. Verified against the file rather than assumed.
  ctry <- fbs[`Area Code` < 5000 & `Area Code` != 351L]
  world_kcal_year  <- sum(as.numeric(ctry$Value), na.rm = TRUE) * 1e6
  kcal_denom_source <- paste0("summed country rows (no World row present; ",
                              "aggregates and the China 351 duplicate excluded)")
}
if (!is.finite(world_kcal_year) || world_kcal_year <= 0) {
  stop("World food-energy denominator is not a positive finite number.")
}

# Cross-check denominator, computed even when the World row is used: the same
# guarded sum of country rows. Reported, not substituted -- a large gap between
# the two would mean the guards or the aggregate flags have moved.
ctry_chk <- fbs[`Area Code` < 5000 & `Area Code` != 351L]
world_kcal_year_summed <- sum(as.numeric(ctry_chk$Value), na.rm = TRUE) * 1e6

# --- Map FAOSTAT areas to ISO3 ------------------------------------------------
iso_map <- read.csv(iso_map_path, check.names = FALSE, stringsAsFactors = FALSE)
if (!all(c("Area", "ISO") %in% names(iso_map))) {
  stop("Expected 'Area' and 'ISO' columns in ", iso_map_path)
}
fbs_iso <- merge(
  data.frame(Area = fbs$Area, kcal_year = as.numeric(fbs$Value) * 1e6,
             stringsAsFactors = FALSE),
  iso_map, by = "Area", all.x = FALSE
)

# One FBS row per ISO, or the sum below is silently wrong. Fires if the mapping
# ever points two FAOSTAT areas at one ISO -- e.g. a 'China' / 'China, mainland'
# pair -- for any ISO actually in our sets.
dup_iso <- fbs_iso$ISO[duplicated(fbs_iso$ISO) & fbs_iso$ISO %in% iso_food]
if (length(dup_iso) > 0) {
  stop("Multiple FAOSTAT areas map to one ISO in the food sample: ",
       paste(sort(unique(dup_iso)), collapse = ", "),
       " -- summing these would double-count.")
}

# --- Per-country table --------------------------------------------------------
kcal <- data.frame(ISO3 = iso_food, stringsAsFactors = FALSE)
kcal <- merge(kcal, fbs_iso[, c("ISO", "Area", "kcal_year")],
              by.x = "ISO3", by.y = "ISO", all.x = TRUE)
names(kcal)[names(kcal) == "Area"] <- "faostat_area"
kcal$matched            <- !is.na(kcal$kcal_year)
kcal$in_complete_subset <- kcal$ISO3 %in% iso_complete
kcal$kcal_day           <- kcal$kcal_year / 365      # 2022 is not a leap year
kcal$share_of_world_pct <- 100 * kcal$kcal_year / world_kcal_year

# --- The load-bearing check: anything unmatched understates the numerator ------
# An ISO that fails to match drops out of the sum and quietly shrinks the
# reported coverage, which is the same failure shape as the three countries that
# sat at exactly zero food savings for the life of the model with nothing said.
# So this reports by name and by count, and it is a stop rather than a warning:
# an understated coverage figure is not reportable.
kcal_unmatched <- sort(kcal$ISO3[!kcal$matched])
n_kcal_food     <- sum(kcal$matched)
n_kcal_complete <- sum(kcal$matched & kcal$in_complete_subset)

share_kcal_food     <- sum(kcal$share_of_world_pct[kcal$matched], na.rm = TRUE)
share_kcal_complete <- sum(
  kcal$share_of_world_pct[kcal$matched & kcal$in_complete_subset], na.rm = TRUE)

# --- Output -------------------------------------------------------------------
if (!dir.exists("data_result")) dir.create("data_result", recursive = TRUE)
write.csv(result, out_csv, row.names = FALSE)

# Food-energy detail. Written BEFORE the unmatched check stops the run, so a
# failure leaves the evidence on disk to diagnose from rather than nothing.
if (!dir.exists("diagnostics")) dir.create("diagnostics", recursive = TRUE)
kcal_out <- kcal[order(!kcal$in_complete_subset, -kcal$share_of_world_pct),
                 c("ISO3", "faostat_area", "matched", "in_complete_subset",
                   "kcal_year", "kcal_day", "share_of_world_pct")]
# Both denominators travel with the rows: the published World row that the
# reported share uses, and the guarded sum-of-countries cross-check.
kcal_out$world_kcal_year        <- world_kcal_year
kcal_out$world_kcal_day         <- world_kcal_year / 365
kcal_out$world_kcal_year_summed <- world_kcal_year_summed
kcal_out$denominator_source     <- kcal_denom_source
write.csv(kcal_out, kcal_out_csv, row.names = FALSE)

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

# --- Food-energy coverage, beside the GDP figures it is quoted with -----------
cat("\n============================================================\n")
cat(sprintf(" Share of global food energy supply (%d, FAOSTAT FBS)\n", fbs_year))
cat("============================================================\n")
cat(sprintf("Element    : %s / %s (million Kcal, annual)\n",
            kcal_item, kcal_element))
cat(sprintf("Denominator: %s\n", kcal_denom_source))
cat(sprintf("World food supply %d: %.4e kcal/year  (%.0f kcal/day)\n",
            fbs_year, world_kcal_year, world_kcal_year / 365))
cat(sprintf("Cross-check, summed country rows: %.4e kcal/year  (%+.2f%% vs the ",
            world_kcal_year_summed,
            100 * (world_kcal_year_summed / world_kcal_year - 1)))
cat("reported denominator)\n")

cat(sprintf("\nMatched %d of %d in the food-data sample, %d of %d in the ",
            n_kcal_food, length(iso_food),
            n_kcal_complete, length(iso_complete)))
cat("complete-data subset\n")
if (length(kcal_unmatched) == 0) {
  cat("Unmatched: none\n")
} else {
  cat(sprintf("Unmatched (%d) -- each drops out of the numerator and ",
              length(kcal_unmatched)))
  cat("understates coverage:\n")
  for (iso in kcal_unmatched) {
    cat(sprintf("  %-4s no FAOSTAT '%s' row for %d\n", iso, kcal_item, fbs_year))
  }
}

cat("\n------------------------------------------------------------\n")
cat(sprintf("Complete-data subset : %.1f%% of global food energy supply  (n = %d)\n",
            share_kcal_complete, n_kcal_complete))
cat(sprintf("Food-data sample     : %.1f%% of global food energy supply  (n = %d)\n",
            share_kcal_food, n_kcal_food))
cat("------------------------------------------------------------\n")
cat("NOTE: the FBS element measures food SUPPLY at household availability,\n")
cat("      which includes waste and is not intake. The manuscript sentence\n")
cat("      should read 'global food energy supply', not 'calorie consumption'.\n")

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
cat("Saved food-energy coverage to: ", kcal_out_csv, "\n", sep = "")

# Last, so everything above is on screen and both CSVs are on disk first. An
# unmatched country means the food-energy percentages above are understated by an
# unknown amount, so they are not reportable until it is resolved.
if (length(kcal_unmatched) > 0) {
  stop("Food-energy coverage is understated: no FAOSTAT match for ",
       paste(kcal_unmatched, collapse = ", "),
       ". The two percentages above exclude them. Resolve the mapping in ",
       iso_map_path, " before quoting either figure.")
}
