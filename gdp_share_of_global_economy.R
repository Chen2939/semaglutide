# =============================================================================
# Share of the global economy (2022) for the semaglutide analysis country sets
# =============================================================================
#
# Computes each country's share of 2022 world GDP, then totals the shares for:
#   * the 53-country food-data sample, and
#   * the 35-country OECD complete-data subset (used in the paper figures).
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
# Country sets are the ISO3 lists from the coverage analysis
# (data_result/country_data_coverage.xlsx).
# =============================================================================

# --- Configuration -----------------------------------------------------------
wb_path <- file.path("World Bank", "World_Bank_National_GDP.csv")
target_year <- "2022"
out_csv <- file.path("data_result", "gdp_share_of_global_economy.csv")

# --- Country sets (ISO3) ------------------------------------------------------
# 35-country OECD complete-data subset (food + mortality + OECD survivor factor)
iso35 <- c(
  "AUS", "AUT", "BEL", "CAN", "CHL", "HRV", "CZE", "DNK", "EST", "FIN",
  "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR", "ITA", "JPN", "LVA",
  "LTU", "LUX", "NLD", "NZL", "NOR", "POL", "PRT", "KOR", "SVK", "SVN",
  "ESP", "SWE", "CHE", "GBR", "USA"
)

# 13 countries missing the OECD consumption-based GHG (survivor-emissions) factor
iso_oecd_missing <- c(
  "ATG", "BHS", "BHR", "BRB", "PYF", "KWT", "OMN", "PAN", "QAT", "KNA",
  "SYC", "TTO", "URY"
)

# 5 countries missing HLD life-table data (0 person-years saved)
iso_mort_missing <- c("CYP", "MLT", "ROU", "SAU", "ARE")

# Full 53-country food-data sample
iso53 <- c(iso35, iso_oecd_missing, iso_mort_missing)

data_status <- function(iso) {
  ifelse(iso %in% iso35, "Complete (in 35-country subset)",
    ifelse(iso %in% iso_oecd_missing,
      "Missing OECD survivor-emissions factor",
      "Missing HLD mortality life table"))
}

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
sample_iso <- data.frame(ISO3 = iso53, stringsAsFactors = FALSE)
gdp_sub <- gdp[gdp[["Country Code"]] %in% iso53,
               c("Country Name", "Country Code", target_year)]
names(gdp_sub) <- c("Country", "ISO3", "gdp_current_usd")
gdp_sub$gdp_current_usd <- as.numeric(gdp_sub$gdp_current_usd)

result <- merge(sample_iso, gdp_sub, by = "ISO3", all.x = TRUE)
result$data_status <- data_status(result$ISO3)
result$in_35_subset <- result$ISO3 %in% iso35
result$share_of_world_pct <- 100 * result$gdp_current_usd / world_gdp

# Warn about any country not matched or missing 2022 GDP
missing_match <- result$ISO3[is.na(result$gdp_current_usd)]
if (length(missing_match) > 0) {
  warning("No 2022 GDP found for: ", paste(missing_match, collapse = ", "))
}

# Order: 35-subset first, then by descending share
result <- result[order(!result$in_35_subset, -result$share_of_world_pct), ]
result <- result[, c("ISO3", "Country", "data_status", "in_35_subset",
                     "gdp_current_usd", "share_of_world_pct")]

# --- Totals -------------------------------------------------------------------
share_53 <- sum(result$share_of_world_pct, na.rm = TRUE)
share_35 <- sum(result$share_of_world_pct[result$in_35_subset], na.rm = TRUE)
n_53 <- sum(!is.na(result$gdp_current_usd))
n_35 <- sum(!is.na(result$gdp_current_usd) & result$in_35_subset)

# --- Output -------------------------------------------------------------------
if (!dir.exists("data_result")) dir.create("data_result", recursive = TRUE)
write.csv(result, out_csv, row.names = FALSE)

cat("\n============================================================\n")
cat(" Share of global economy (", target_year,
    ", World Bank GDP current US$)\n", sep = "")
cat("============================================================\n")
cat(sprintf("World GDP %s: US$ %.2f trillion\n\n",
            target_year, world_gdp / 1e12))

fmt <- result
fmt$gdp_tn <- fmt$gdp_current_usd / 1e12
for (i in seq_len(nrow(fmt))) {
  cat(sprintf("  %-4s %-40s %6.3f%%  (US$ %5.2f tn)  [%s]\n",
              fmt$ISO3[i], substr(fmt$Country[i], 1, 40),
              fmt$share_of_world_pct[i], fmt$gdp_tn[i],
              ifelse(fmt$in_35_subset[i], "35-subset", "extra")))
}

cat("\n------------------------------------------------------------\n")
cat(sprintf("35-country OECD complete subset: %.2f%% of world GDP  (n = %d)\n",
            share_35, n_35))
cat(sprintf("53-country food-data sample    : %.2f%% of world GDP  (n = %d)\n",
            share_53, n_53))
cat("------------------------------------------------------------\n")
cat("Saved per-country table to: ", out_csv, "\n", sep = "")
