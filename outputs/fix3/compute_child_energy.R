# =============================================================================
# Fix #3 support: total annual child (0-17) energy requirement by country.
#
# For each of the in-scope high-income countries, computes the all-ages
# under-18 daily energy-requirement pool needed to build the all-ages EER
# denominator for the demand-shock correction (the adult 18+ pool comes from
# the sim; this supplies the child block).
#
# Population source : UN WPP 2024 single-age files (same files the adult sim's
#                     Data_Cleaning9.8.R reads; those drop 0-17 on import via a
#                     case_when starting at age 18, so 0-17 is present in-source
#                     and simply filtered out there -- here we keep 0-17).
# Requirement source: FAO/WHO/UNU (2004) "Human energy requirements",
#                     moderate physical activity, kcal/day. See lookup below.
#
# Output: outputs/fix3/child_energy_by_country.xlsx  (one row per country)
#         outputs/fix3/child_energy_requirement_lookup.csv  (hardcoded table)
# Commits nothing.
# =============================================================================

suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(writexl)
  library(readr)
})

# ---- paths ------------------------------------------------------------------
UN_DIR  <- "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Code and data/UN"
MALE_XLSX   <- file.path(UN_DIR, "WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx")
FEMALE_XLSX <- file.path(UN_DIR, "WPP2024_POP_F01_3_POPULATION_SINGLE_AGE_FEMALE.xlsx")
OUT_DIR <- "C:/Users/sethw/repos/outputs/fix3"
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

WPP_YEAR <- 2022  # matches Data_Cleaning9.8.R (sim population year)

# 56 in-scope high-income countries (ISO3), from the fix #3 baseline run.
IN_SCOPE <- c(
  "ARE","ATG","AUS","AUT","BEL","BHR","BHS","BRB","CAN","CHE","CHL","CYP","CZE",
  "DEU","DNK","ESP","EST","FIN","FRA","GBR","GRC","GUY","HRV","HUN","IRL","ISL",
  "ISR","ITA","JPN","KNA","KOR","KWT","LTU","LUX","LVA","MLT","NLD","NOR","NRU",
  "NZL","OMN","PAN","POL","PRT","PYF","QAT","ROU","SAU","SVK","SVN","SWE","SYC",
  "TTO","TWN","URY","USA"
)

# =============================================================================
# STEP 2 -- FAO/WHO/UNU (2004) daily energy requirement lookup, kcal/day.
# Single value per single year of age 0-17 and sex. Age interval "N-(N+1)" in
# the source is mapped to single age N (so "1-2" -> 1, ... "17-18" -> 17).
#
#   Age 0 : Table 3.2 (6-7 month value used to represent the whole infant year).
#           https://www.fao.org/4/y5686e/y5686e05.htm   boys 653, girls 604.
#   Ages 1-17 : Table 4.5 (boys) / Table 4.6 (girls), MODERATE physical activity
#           column, kcal/day. Ages 1-5 have only the moderate column in-source.
#           https://www.fao.org/4/y5686e/y5686e06.htm
# =============================================================================

energy_lookup <- tribble(
  ~age, ~male_kcal, ~female_kcal,
  # age 0: Table 3.2 (infant)
     0L,   653,        604,
  # ages 1-5: Tables 4.5/4.6, single (moderate) column
     1L,   950,        850,
     2L,  1125,       1050,
     3L,  1250,       1150,
     4L,  1350,       1250,
     5L,  1475,       1325,
  # ages 6-17: Tables 4.5/4.6, moderate physical activity column
     6L,  1575,       1425,
     7L,  1700,       1550,
     8L,  1825,       1700,
     9L,  1975,       1850,
    10L,  2150,       2000,
    11L,  2350,       2150,
    12L,  2550,       2275,
    13L,  2775,       2375,
    14L,  3000,       2450,
    15L,  3175,       2500,
    16L,  3325,       2500,
    17L,  3400,       2500
)

# long form: one row per (age, sex)
lookup_long <- energy_lookup %>%
  pivot_longer(c(male_kcal, female_kcal),
               names_to = "sex", values_to = "kcal_day") %>%
  mutate(sex = if_else(sex == "male_kcal", "male", "female")) %>%
  rename(Age = age)

# Export the hardcoded table for later reference
write_csv(energy_lookup,
          file.path(OUT_DIR, "child_energy_requirement_lookup.csv"))

# =============================================================================
# STEP 1 -- UN WPP population, single year of age, both sexes.
# =============================================================================

read_wpp <- function(path, sex_label) {
  # guess_max large: the top ~thousands of rows are aggregates (World, regions)
  # with a blank ISO3, so a small guess types ISO3 as logical(NA). Force a full
  # scan so ISO3 (and the single-age value columns) type correctly.
  raw <- read_excel(path, sheet = 1, skip = 16, na = "", guess_max = 1048576)
  raw %>%
    rename(Country = `Region, subregion, country or area *`,
           ISO3    = `ISO3 Alpha-code`) %>%
    filter(Year == WPP_YEAR) %>%
    pivot_longer(cols = matches("^\\d+\\+?$"),
                 names_to = "Age", values_to = "pop_thousands") %>%
    mutate(
      Age = as.integer(str_replace(Age, "\\+", "")),
      # values are in thousands; strip any space/nbsp thousands separators
      pop = as.numeric(gsub("[ \u00a0,]", "", as.character(pop_thousands))) * 1000,
      sex = sex_label
    ) %>%
    filter(!is.na(ISO3), ISO3 != "") %>%
    select(ISO3, Country, sex, Age, pop)
}

pop_all <- bind_rows(
  read_wpp(MALE_XLSX,   "male"),
  read_wpp(FEMALE_XLSX, "female")
)

# One name per ISO3 (from WPP).
country_names <- pop_all %>%
  distinct(ISO3, Country) %>%
  group_by(ISO3) %>% summarise(Country = first(Country), .groups = "drop")

# Partition sums per country (for sanity checks) -------------------------------
part <- pop_all %>%
  group_by(ISO3) %>%
  summarise(
    total_pop  = sum(pop, na.rm = TRUE),
    child_pop  = sum(pop[Age <= 17], na.rm = TRUE),
    adult_pop_wpp = sum(pop[Age >= 18], na.rm = TRUE),
    .groups = "drop"
  )

# =============================================================================
# STEP 3 -- compute child energy requirement.
#   per country: sum over ages 0-17 and both sexes of pop * kcal/day * 365.
# =============================================================================

child <- pop_all %>%
  filter(Age >= 0, Age <= 17) %>%
  inner_join(lookup_long, by = c("Age", "sex")) %>%
  mutate(annual_kcal = pop * kcal_day * 365)

by_country <- child %>%
  group_by(ISO3) %>%
  summarise(
    total_annual_child_kcal = sum(annual_kcal, na.rm = TRUE),
    total_child_pop         = sum(pop, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(mean_daily_kcal_per_child = total_annual_child_kcal /
                                     (total_child_pop * 365))

# =============================================================================
# STEP 4 -- assemble output for the 56 in-scope countries, one row each.
# =============================================================================

out <- tibble(ISO3 = IN_SCOPE) %>%
  left_join(country_names, by = "ISO3") %>%
  left_join(by_country,    by = "ISO3") %>%
  select(ISO3, Country,
         total_annual_child_kcal,
         total_child_pop,
         mean_daily_kcal_per_child) %>%
  arrange(ISO3)

missing <- out$ISO3[is.na(out$total_annual_child_kcal)]

write_xlsx(out, file.path(OUT_DIR, "child_energy_by_country.xlsx"))

# =============================================================================
# SANITY CHECKS -- printed only, not embedded in the output file.
# =============================================================================
cat("\n================= SANITY CHECKS =================\n")

cat(sprintf("\nIn-scope countries requested: %d\n", length(IN_SCOPE)))
cat(sprintf("Countries resolved in WPP:    %d\n",
            sum(!is.na(out$total_annual_child_kcal))))
if (length(missing) > 0) {
  cat("MISSING from WPP (no ISO3 match): ", paste(missing, collapse = ", "), "\n")
} else {
  cat("MISSING from WPP: none\n")
}

chk <- out %>%
  filter(!is.na(total_annual_child_kcal)) %>%
  left_join(part, by = "ISO3") %>%
  mutate(
    child_share_total = child_pop / total_pop,
    partition_gap     = total_pop - (child_pop + adult_pop_wpp)  # must be ~0
  )

cat("\n--- Child share of total population (expect ~0.15-0.22) ---\n")
flagged_share <- chk %>% filter(child_share_total < 0.15 | child_share_total > 0.22)
cat(sprintf("median = %.3f   min = %.3f (%s)   max = %.3f (%s)\n",
            median(chk$child_share_total),
            min(chk$child_share_total), chk$ISO3[which.min(chk$child_share_total)],
            max(chk$child_share_total), chk$ISO3[which.max(chk$child_share_total)]))
if (nrow(flagged_share) > 0) {
  cat("OUTSIDE 15-22% band:\n")
  print(flagged_share %>%
          transmute(ISO3, Country, child_share_total = round(child_share_total, 3)) %>%
          as.data.frame(), row.names = FALSE)
} else {
  cat("all within band\n")
}

cat("\n--- Implied mean daily kcal per child (expect ~1600-2000) ---\n")
flagged_kcal <- chk %>% filter(mean_daily_kcal_per_child < 1500 |
                               mean_daily_kcal_per_child > 2100)
cat(sprintf("median = %.0f   min = %.0f (%s)   max = %.0f (%s)\n",
            median(chk$mean_daily_kcal_per_child),
            min(chk$mean_daily_kcal_per_child), chk$ISO3[which.min(chk$mean_daily_kcal_per_child)],
            max(chk$mean_daily_kcal_per_child), chk$ISO3[which.max(chk$mean_daily_kcal_per_child)]))
if (nrow(flagged_kcal) > 0) {
  cat("OUTSIDE 1600-2000 (using 1500-2100 tolerance) band:\n")
  print(flagged_kcal %>%
          transmute(ISO3, Country, mean_daily_kcal_per_child = round(mean_daily_kcal_per_child, 0)) %>%
          as.data.frame(), row.names = FALSE)
} else {
  cat("all within band\n")
}

cat("\n--- Partition check: (0-17) + (18+) == total, no gap/overlap at 18 ---\n")
cat(sprintf("max |total - (child + adult)| across countries = %.6g persons\n",
            max(abs(chk$partition_gap))))
cat(sprintf("(relative to total pop, worst = %.2e)\n",
            max(abs(chk$partition_gap) / chk$total_pop)))

cat("\nWrote:\n  ", file.path(OUT_DIR, "child_energy_by_country.xlsx"),
    "\n  ", file.path(OUT_DIR, "child_energy_requirement_lookup.csv"), "\n")

# Save the diagnostics frame too (for the 18+ vs sim cross-check done separately)
write_csv(chk %>% select(ISO3, Country, total_pop, child_pop, adult_pop_wpp,
                         child_share_total, mean_daily_kcal_per_child),
          file.path(OUT_DIR, "child_energy_diagnostics.csv"))
