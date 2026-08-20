# ============================================================================
# China 2050 scope sensitivity
# ============================================================================
#
# WHAT THIS IS. The manuscript estimates annual food-system emissions savings
# from population-scale semaglutide adoption across a set of high-income
# countries. China is excluded on income grounds. This script asks a single
# back-of-envelope question: if China met the study's income conditions by
# 2050, how much would including it add?
#
# The answer is reported as a MULTIPLE of the manuscript's headline savings.
#
#
# THE ARITHMETIC, in full:
#
#   eligible_2050 = sum over (age band x sex) of
#                     [ WPP China 2050 population x NCD-RisC China 2022 P(BMI>=30) ]
#   treated       = eligible_2050 x uptake fraction
#   savings       = treated x Korea per-patient annual saving
#   multiple      = savings / manuscript headline savings
#
# WHAT IS DELIBERATELY ABSENT. Each of these is a fixed assumption, not an
# oversight, and none of them appears anywhere below:
#
#   - Year 1 only (t = 0). No accumulation and no time series.
#   - No survivorship.
#   - No pharmaceutical manufacturing emissions.
#   - Eligibility is BMI >= 30 only. No diabetes arm and no BMI 27-30 group.
#   - BMI prevalence is 2022 and is NOT projected forward; only population is 2050.
#   - Per-patient savings are Korea's, taken from committed pipeline output.
#   - No carbon-intensity adjustment. 2022 intensities throughout.
#   - Rebound is NOT recomputed for China. The rebound equilibrium is already
#     embedded in the Korea per-patient value. Rebuilding it for China would
#     need Chinese elasticities and food-balance data, which is the whole point
#     of not doing it this way.
#
# ONE QUALIFICATION to "no mortality". No mortality term is computed
# anywhere in this script, but the borrowed Korea per-patient value is not
# perfectly free of one. annual_food_savings_gross_t is survival-weighted (it
# carries Korea's first-year food-side weight pi(1) = 0.997094), while its
# divisor treated_users_initial is an initial headcount. The headline
# denominator, by contrast, comes from the manuscript's Panel A, which switches
# survival weighting off. So numerator and denominator sit on bases that differ
# by about 0.29%.
#
# That is left uncorrected on purpose. Dividing the Korea value by pi(1) would
# put a survivorship term into a script whose brief forbids one, in exchange for
# moving the reported multiple from 0.164 to 0.165 -- far below the resolution of
# a back-of-envelope scope sensitivity. It is recorded here so nobody has to
# rediscover it.
#
# READ-ONLY. This script modifies nothing in the pipeline and writes no files.
# It reads three committed CSVs, two NCD-RisC CSVs and two UN WPP workbooks,
# and prints. Running it cannot change any manuscript number.
#
# RUNTIME. Expect roughly 10-20 minutes. The two WPP workbooks are about 210 MB
# each and are read twice apiece (once for the 2022 estimates and once for the
# 2050 projections). Almost all the wall-clock is Excel parsing.
#
#   Rscript scripts/china_2050_scope_sensitivity.R
#
# ASCII only in print statements; the Windows console here breaks on arrows and
# other non-ASCII.
# ============================================================================

suppressMessages({
  library(readxl)
  library(dplyr)
  library(tidyr)
  library(readr)
})

options(scipen = 999)

# The Gate 3 table is about 90 characters wide. Left at the default 80, R splits
# the label and value columns into two separate blocks and the table stops being
# readable, which defeats the point of printing a table at all.
options(width = 130)


# ============================================================================
# CONSTANTS. Every one names where it came from.
# ============================================================================

# --- Input locations --------------------------------------------------------

# UN WPP 2024 revision, single-age population by sex. This is the directory
# given in the brief. Not
UN_DIR <- "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Code and data/UN"
F_POP_MALE   <- file.path(UN_DIR, "WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx")
F_POP_FEMALE <- file.path(UN_DIR, "WPP2024_POP_F01_3_POPULATION_SINGLE_AGE_FEMALE.xlsx")

# NCD-RisC Lancet 2024 adult BMI release, age-specific by country. These are the
# same two files the pipeline reads at Data_Cleaning9.8.R:265-266.
LANCET_DIR <- "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Code and data/Lancet"
F_BMI_MALE   <- file.path(LANCET_DIR, "NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv")
F_BMI_FEMALE <- file.path(LANCET_DIR, "NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv")

# Committed pipeline outputs, for the Korea per-patient value and the headline
# denominator.
REPO <- "C:/Users/sethw/repos"
F_NET_EMISSIONS <- file.path(REPO, "data_result", "net_emissions_with_drug.csv")
F_PER_CAPITA    <- file.path(REPO, "data_result", "per_capita_emissions_savings.csv")

# --- WPP sheet selection ----------------------------------------------------

# The workbooks carry one sheet per projection variant. 2050 is a projection
# year and is therefore NOT on the Estimates sheet, which stops at 2023. The
# brief specifies the medium variant.
#
# Note that the two halves of this script read DIFFERENT sheets: the China 2050
# figures come from "Medium variant", while the Korea 2022 reconciliation in
# Gate 2 comes from "Estimates". That is correct, not an inconsistency.
WPP_SHEET_ESTIMATES <- "Estimates"       # 1950-2023, holds Korea 2022
WPP_SHEET_MEDIUM    <- "Medium variant"  # 2024-2100, holds China 2050

# The WPP data block starts on row 17 of every sheet in these workbooks, so the
# first 16 rows are skipped. Same value the pipeline uses at
# Data_Cleaning9.8.R:426. Verified to hold on the Medium variant sheet too:
# both sheets have an identical 112-column layout.
WPP_SKIP <- 16

# WPP reports population in THOUSANDS of persons.
WPP_UNITS_PER_PERSON <- 1000

# --- Scenario parameters ----------------------------------------------------

# Uptake (adherence) fractions, from legacy/R_scripts/Data_Cleaning9.8.R lines
# 1319 and 1321, where run_treatment_scenario() is called with these rates.
#
# These are NOMINAL rates. In the pipeline, adherence is an individual Bernoulli
# draw against these thresholds, so the realised rate differs slightly: Korea's
# committed treated/eligible is 0.9417 for max and 0.5072 for moderate. This
# script applies the nominal fractions, which makes the max figure roughly 0.9%
# higher than a draw-matched calculation would give.
UPTAKE_MAX <- 0.95
UPTAKE_MOD <- 0.50

# Adult eligibility age bounds, both read from the pipeline rather than assumed.
# Lower bound 18: Data_Cleaning9.8.R:448 begins the age bands at "18-19" and
# discards younger ages. Upper bound 74: Data_Cleaning9.8.R:1274 sets
# `age >= 75 ~ FALSE` in qualifies_for_treatment.
AGE_MIN <- 18
AGE_MAX <- 74

# The NCD-RisC reference year for BMI prevalence. Held at 2022 by assumption;
# prevalence is not projected.
BMI_YEAR <- 2022

# Population years.
POP_YEAR_CHINA <- 2050
POP_YEAR_KOREA <- 2022

# --- Gate 2 reconciliation targets and bars ---------------------------------
# BARS ARE DECLARED HERE, BEFORE THE RUN. If one fails the script stops and
# reports rather than proceeding to the China figures.

# Korea 2022 adult (18+) population as the pipeline computed it, from
# diagnostics/eligible_treated_by_country.csv, column pop_adult. This tests the
# WPP read and the age-band mapping with no BMI involved at all.
KOREA_POP_ADULT_PIPELINE <- 44526968.5
BAR_POP_ADULT_REL <- 0.001   # 0.1 percent relative

# Korea's population-weighted NCD-RisC target share of BMI >= 30, from the
# pipeline's own G2 check (diagnostics/run_C.log, "G2 sampled BMI category
# shares", Japan/Korea block: KOR target 0.06733571). This tests the
# NCD-RisC x WPP prevalence weighting.
KOREA_BMI30_TARGET_SHARE <- 0.06733571
BAR_BMI30_SHARE_PP <- 0.005  # 0.5 percentage points, the bar that same G2
                             # check declared for Japan and Korea.


# ============================================================================
# AGE BAND MATCHING
# ============================================================================
#
# This is the only genuinely new machinery in the script and it is where errors
# would enter, so it is spelled out at length.
#
# The two sources do not share an age granularity. NCD-RisC reports prevalence
# in fifteen bands: "18-19", then five-year bands from "20-24" up to "80-84",
# then an open-ended "85plus". UN WPP reports population by SINGLE year of age,
# in columns labelled "0" through "99" plus an open-ended "100+".
#
# The finest granularity common to both is therefore the NCD-RisC band. We
# aggregate WPP single ages UP into those bands. We do this in that direction on
# purpose: summing populations is exact, whereas splitting a band's prevalence
# across single ages would require interpolation, and the brief forbids
# interpolating, smoothing or extrapolating prevalence.
#
# The mapping below is a copy of the pipeline's own mapping at
# Data_Cleaning9.8.R:447-463, so the bands here are the bands the manuscript
# already uses. Single ages below 18 fall through to NA and are dropped.
#
# The eligible age range 18 to 74 lands exactly on band boundaries: it is the
# twelve bands "18-19" through "70-74", because the 70-74 band ends at 74 and
# the age restriction excludes 75 and over. No band has to be split, and so no
# partial-band approximation enters anywhere.
#
# Prevalence is joined on ISO3 x sex x band, and never on country name: the two
# sources disagree on names, with NCD-RisC calling Korea "South Korea" while WPP
# calls it "Republic of Korea". Male and female are carried separately the whole
# way through and only summed at the very end, so no sex-combined prevalence is
# ever formed.

assign_age_band <- function(age) {
  case_when(
    age >= 18 & age <= 19 ~ "18-19",
    age >= 20 & age <= 24 ~ "20-24",
    age >= 25 & age <= 29 ~ "25-29",
    age >= 30 & age <= 34 ~ "30-34",
    age >= 35 & age <= 39 ~ "35-39",
    age >= 40 & age <= 44 ~ "40-44",
    age >= 45 & age <= 49 ~ "45-49",
    age >= 50 & age <= 54 ~ "50-54",
    age >= 55 & age <= 59 ~ "55-59",
    age >= 60 & age <= 64 ~ "60-64",
    age >= 65 & age <= 69 ~ "65-69",
    age >= 70 & age <= 74 ~ "70-74",
    age >= 75 & age <= 79 ~ "75-79",
    age >= 80 & age <= 84 ~ "80-84",
    age >= 85            ~ "85plus"
  )
}

# All fifteen adult bands, and the twelve that fall inside the eligible range.
BANDS_ALL      <- c("18-19", "20-24", "25-29", "30-34", "35-39", "40-44",
                    "45-49", "50-54", "55-59", "60-64", "65-69", "70-74",
                    "75-79", "80-84", "85plus")
BANDS_ELIGIBLE <- BANDS_ALL[1:12]   # "18-19" through "70-74", i.e. ages 18-74


# ============================================================================
# READERS
# ============================================================================

# Used four times (two sexes x two sheet/year combinations), so it earns being a
# function. Returns one row per age band for the requested ISO3 codes and year.
read_wpp_bands <- function(path, sheet, year, iso3, sex_label) {
  cat(sprintf("  reading %s [%s] %d ...\n", basename(path), sheet, year))

  raw <- read_excel(path, sheet = sheet, skip = WPP_SKIP, na = "",
                    col_types = "text")

  out <- raw %>%
    rename(Country = `Region, subregion, country or area *`,
           ISO3    = `ISO3 Alpha-code`) %>%
    filter(ISO3 %in% iso3, as.numeric(Year) == year) %>%
    pivot_longer(cols = matches("^\\d+\\+?$"),
                 names_to = "Age", values_to = "Population") %>%
    mutate(
      # "100+" becomes 100. It lands in the 85plus band either way.
      Age        = as.numeric(sub("\\+$", "", Age)),
      Population = suppressWarnings(as.numeric(Population)),
      Age_Band   = assign_age_band(Age)
    ) %>%
    filter(!is.na(Age_Band))

  # A silent NA in an age we actually use would quietly shrink the population,
  # so refuse to continue if one appears.
  if (any(is.na(out$Population))) {
    stop("non-numeric WPP population cell for ", paste(iso3, collapse = "/"),
         " ", year, " on sheet '", sheet, "'")
  }

  out %>%
    group_by(ISO3, Country, Age_Band) %>%
    summarise(Population = sum(Population) * WPP_UNITS_PER_PERSON,
              .groups = "drop") %>%
    mutate(Sex = sex_label)
}

# Used twice, for the two sexes.
read_ncdrisc_obesity <- function(path, year, iso3, sex_label) {
  cat(sprintf("  reading %s ...\n", basename(path)))

  raw <- suppressMessages(read_csv(path, show_col_types = FALSE,
                                   progress = FALSE))

  # The obesity column name contains a superscript 2 ("kg/m^2"), which is not
  # ASCII, so it is located by pattern rather than typed out here. The file also
  # carries lower and upper 95% uncertainty interval columns with the same
  # prefix, so the point estimate is pinned by also requiring the name to END
  # with "(obesity)". That anchor additionally excludes the BMI>=40 column,
  # which ends with "(morbid obesity)".
  col <- grep("^Prevalence of BMI>=30.*\\(obesity\\)$", names(raw), value = TRUE)
  if (length(col) != 1) {
    stop("expected exactly one BMI>=30 point-estimate column in ",
         basename(path), ", found ", length(col))
  }

  raw %>%
    rename(Age_Band = `Age group`) %>%
    filter(ISO %in% iso3, Year == year) %>%
    transmute(ISO3 = ISO, Age_Band = Age_Band,
              P_obese = .data[[col]], Sex = sex_label)
}


# ============================================================================
# STEP 1. Korea per-patient saving and the headline denominator
# ============================================================================

cat("\n================ STEP 1: pipeline values ================\n")

net <- suppressMessages(read_csv(F_NET_EMISSIONS, show_col_types = FALSE,
                                progress = FALSE))

# Per TREATED patient, verified as such at Gate 1: summing treated_users_initial
# across the 53 complete countries reproduces the patient_years divisor in
# per_capita_emissions_savings.csv to eight figures, and that divisor is what
# build_per_capita_table.py:206 uses to form per_patient_year_kg.
#
# annual_food_savings_gross_t is gross of DRUG MANUFACTURING but already net of
# REBOUND, which is what this exercise needs: the brief excludes pharmaceutical
# emissions and requires the rebound equilibrium to stay embedded.
korea <- net %>%
  filter(ISO == "KOR") %>%
  transmute(scenario,
            food_t  = annual_food_savings_gross_t,
            treated = treated_users_initial,
            per_patient_kg = annual_food_savings_gross_t * 1000 /
                             treated_users_initial)

print(as.data.frame(korea))

KOR_PP_MAX <- korea$per_patient_kg[korea$scenario == "max_uptake"]
KOR_PP_MOD <- korea$per_patient_kg[korea$scenario == "mod_uptake"]
stopifnot(length(KOR_PP_MAX) == 1, length(KOR_PP_MOD) == 1)

# Manuscript headline year-1 food savings, read not recomputed. Panel A is the
# one-year no-mortality panel; actual_food_savings is post-rebound and before
# pharmaceutical manufacturing, matching the basis used for China.
pc <- suppressMessages(read_csv(F_PER_CAPITA, show_col_types = FALSE,
                                progress = FALSE)) %>%
  filter(panel == "A_1yr_no_mortality", spec == "baseline_mean_ci",
         step == "actual_food_savings")

HEADLINE_MAX <- pc$value_Mt[pc$uptake == "max_uptake"]
HEADLINE_MOD <- pc$value_Mt[pc$uptake == "mod_uptake"]
stopifnot(length(HEADLINE_MAX) == 1, length(HEADLINE_MOD) == 1)

cat(sprintf("\n  Korea per-patient, max     : %8.3f kg CO2e / treated patient-yr\n",
            KOR_PP_MAX))
cat(sprintf("  Korea per-patient, mod     : %8.3f kg CO2e / treated patient-yr\n",
            KOR_PP_MOD))
cat(sprintf("  Headline savings, max      : %8.3f Mt CO2e/yr (%d countries)\n",
            HEADLINE_MAX, unique(pc$n_countries)[1]))
cat(sprintf("  Headline savings, mod      : %8.3f Mt CO2e/yr\n", HEADLINE_MOD))


# ============================================================================
# STEP 2. Load prevalence and population
# ============================================================================

cat("\n================ STEP 2: reading inputs ================\n")

bmi <- bind_rows(
  read_ncdrisc_obesity(F_BMI_MALE,   BMI_YEAR, c("CHN", "KOR"), "Men"),
  read_ncdrisc_obesity(F_BMI_FEMALE, BMI_YEAR, c("CHN", "KOR"), "Women")
)

# Both sexes, both countries, all fifteen bands, or something is wrong.
stopifnot(nrow(bmi) == 2 * 2 * length(BANDS_ALL))
stopifnot(length(setdiff(BANDS_ALL, unique(bmi$Age_Band))) == 0)

pop_china <- bind_rows(
  read_wpp_bands(F_POP_MALE,   WPP_SHEET_MEDIUM, POP_YEAR_CHINA, "CHN", "Men"),
  read_wpp_bands(F_POP_FEMALE, WPP_SHEET_MEDIUM, POP_YEAR_CHINA, "CHN", "Women")
)

pop_korea <- bind_rows(
  read_wpp_bands(F_POP_MALE,   WPP_SHEET_ESTIMATES, POP_YEAR_KOREA, "KOR", "Men"),
  read_wpp_bands(F_POP_FEMALE, WPP_SHEET_ESTIMATES, POP_YEAR_KOREA, "KOR", "Women")
)

stopifnot(nrow(pop_china) == 2 * length(BANDS_ALL))
stopifnot(nrow(pop_korea) == 2 * length(BANDS_ALL))

cat("\n  age bands used, and how they were matched:\n")
cat("    NCD-RisC native bands (15) : ", paste(BANDS_ALL, collapse = ", "), "\n")
cat("    WPP single ages 0-99,100+ were summed up into those bands.\n")
cat("    Eligible range ages ", AGE_MIN, "-", AGE_MAX,
    " = the 12 bands ", BANDS_ELIGIBLE[1], " .. ",
    BANDS_ELIGIBLE[12], ", no band split.\n", sep = "")
cat("    Joined on ISO3 x sex x band. Sexes summed only at the end.\n")


# ============================================================================
# GATE 2. Reconciliation on Korea, 2022
# ============================================================================
#
# Two decomposed tests. The literal reconciliation named in the brief -- run the
# eligible-population path on Korea, multiply by the Korea per-patient value and
# compare to the pipeline's Korea food savings -- cannot work as a test here,
# because that per-patient value's denominator (treated_users_initial) descends
# from the pipeline's WIDER eligibility: BMI >= 30 union (BMI 27-30 and type-2
# diabetes), less type-1 diabetics. This script's rule is BMI >= 30 only, by
# design. The comparison would be algebraically forced to show a gap that is a
# definitional difference rather than a matching error.
#
# So the reconciliation is split into the two tests that actually isolate the
# new machinery, agreed before the run:
#
#   Test A -- WPP read and age-band mapping, with no BMI involved.
#   Test B -- the NCD-RisC x WPP prevalence weighting.

cat("\n================ GATE 2: Korea 2022 reconciliation ================\n")

korea_joined <- pop_korea %>%
  inner_join(bmi, by = c("ISO3", "Age_Band", "Sex"))
stopifnot(nrow(korea_joined) == nrow(pop_korea))

# --- Test A: adult population, no BMI --------------------------------------
korea_pop_18plus <- sum(korea_joined$Population)
rel_a <- (korea_pop_18plus - KOREA_POP_ADULT_PIPELINE) / KOREA_POP_ADULT_PIPELINE

cat("\n  TEST A -- Korea 2022 adult (18+) population, WPP read and band mapping\n")
cat(sprintf("    this script          : %15.1f\n", korea_pop_18plus))
cat(sprintf("    pipeline pop_adult   : %15.1f\n", KOREA_POP_ADULT_PIPELINE))
cat(sprintf("    relative difference  : %+.5f%%   (bar: +/- %.3f%%)\n",
            100 * rel_a, 100 * BAR_POP_ADULT_REL))
pass_a <- abs(rel_a) <= BAR_POP_ADULT_REL
cat(sprintf("    RESULT               : %s\n", if (pass_a) "PASS" else "FAIL"))

# --- Test B: population-weighted BMI >= 30 share ---------------------------
# The pipeline's G2 target is a population-weighted mean over the simulated
# adult population, which is everyone 18 and over, so the denominator here is
# the full 18+ population rather than the eligible 18-74 range.
korea_share_18plus <- sum(korea_joined$Population * korea_joined$P_obese) /
                      sum(korea_joined$Population)
diff_b <- korea_share_18plus - KOREA_BMI30_TARGET_SHARE

korea_elig_range <- korea_joined %>% filter(Age_Band %in% BANDS_ELIGIBLE)
korea_share_1874 <- sum(korea_elig_range$Population * korea_elig_range$P_obese) /
                    sum(korea_elig_range$Population)

cat("\n  TEST B -- Korea BMI>=30 population-weighted share, NCD-RisC x WPP\n")
cat(sprintf("    this script (18+)    : %.7f\n", korea_share_18plus))
cat(sprintf("    pipeline G2 target   : %.7f\n", KOREA_BMI30_TARGET_SHARE))
cat(sprintf("    difference           : %+.4f pp   (bar: +/- %.2f pp)\n",
            100 * diff_b, 100 * BAR_BMI30_SHARE_PP))
pass_b <- abs(diff_b) <= BAR_BMI30_SHARE_PP
cat(sprintf("    RESULT               : %s\n", if (pass_b) "PASS" else "FAIL"))
cat(sprintf("    for information, share over the eligible 18-74 range: %.7f\n",
            korea_share_1874))

if (!(pass_a && pass_b)) {
  stop("Gate 2 failed. Stopping before the China figures, as briefed. ",
       "Diagnose the cause; do not adjust the bar.")
}
cat("\n  GATE 2 PASSED. Proceeding to the China figures.\n")


# ============================================================================
# STEP 3. China 2050
# ============================================================================

china_joined <- pop_china %>%
  inner_join(bmi, by = c("ISO3", "Age_Band", "Sex"))
stopifnot(nrow(china_joined) == nrow(pop_china))

# Restrict to the eligible age range, then take the product band by band and sex
# by sex. Male and female are still separate at this point.
china_elig <- china_joined %>%
  filter(Age_Band %in% BANDS_ELIGIBLE) %>%
  mutate(eligible = Population * P_obese)

# Only now are the sexes and bands summed.
china_adult_pop   <- sum(china_elig$Population)
china_eligible    <- sum(china_elig$eligible)
china_elig_share  <- china_eligible / china_adult_pop

treated_max <- china_eligible * UPTAKE_MAX
treated_mod <- china_eligible * UPTAKE_MOD

# persons x kg per person = kg; 1e9 kg = 1 Mt.
savings_max <- treated_max * KOR_PP_MAX / 1e9
savings_mod <- treated_mod * KOR_PP_MOD / 1e9

multiple_max <- savings_max / HEADLINE_MAX
multiple_mod <- savings_mod / HEADLINE_MOD


# ============================================================================
# GATE 3. Results for review
# ============================================================================

cat("\n================ GATE 3: results ================\n")

cat("\n---- China, by sex, within the eligible age range 18-74 ----\n")
print(as.data.frame(
  china_elig %>%
    group_by(Sex) %>%
    summarise(adult_pop = sum(Population),
              eligible  = sum(eligible),
              share     = sum(eligible) / sum(Population),
              .groups   = "drop")
))

results <- data.frame(
  quantity = c(
    "China 2050 population, ages 18-74",
    "China eligible (BMI>=30), persons",
    "  eligible as share of that adult population",
    "China treated, max uptake (0.95)",
    "China treated, moderate uptake (0.50)",
    "Korea per-patient saving, max (kg CO2e/patient-yr)",
    "Korea per-patient saving, moderate (kg CO2e/patient-yr)",
    "China annual savings, max (Mt CO2e/yr)",
    "China annual savings, moderate (Mt CO2e/yr)",
    "Manuscript headline savings, max (Mt CO2e/yr)",
    "Manuscript headline savings, moderate (Mt CO2e/yr)",
    "MULTIPLE of headline, max",
    "MULTIPLE of headline, moderate"
  ),
  value = c(
    formatC(china_adult_pop,  format = "f", big.mark = ",", digits = 0),
    formatC(china_eligible,   format = "f", big.mark = ",", digits = 0),
    formatC(100 * china_elig_share, format = "f", digits = 2, flag = " "),
    formatC(treated_max,      format = "f", big.mark = ",", digits = 0),
    formatC(treated_mod,      format = "f", big.mark = ",", digits = 0),
    formatC(KOR_PP_MAX,       format = "f", digits = 3),
    formatC(KOR_PP_MOD,       format = "f", digits = 3),
    formatC(savings_max,      format = "f", digits = 3),
    formatC(savings_mod,      format = "f", digits = 3),
    formatC(HEADLINE_MAX,     format = "f", digits = 3),
    formatC(HEADLINE_MOD,     format = "f", digits = 3),
    formatC(multiple_max,     format = "f", digits = 3),
    formatC(multiple_mod,     format = "f", digits = 3)
  ),
  stringsAsFactors = FALSE
)
names(results)[2] <- "value (share row is percent)"

cat("\n")
print(results, row.names = FALSE, right = FALSE)

cat("\n---- reading of the headline output ----\n")
cat(sprintf("  Including China at its 2050 population would add %.3f times the\n",
            multiple_max))
cat(sprintf("  manuscript's max-uptake annual food savings -- that is, about\n"))
cat(sprintf("  %.0f%% on top of the current 53-country total. Under moderate\n",
            100 * multiple_max))
cat(sprintf("  uptake the figure is %.3f times, or about %.0f%% on top.\n",
            multiple_mod, 100 * multiple_mod))
cat("\n  The two scenarios give almost the same multiple because both the\n")
cat("  China numerator and the headline denominator scale with uptake, so the\n")
cat("  uptake fraction very nearly cancels. It does not cancel exactly, only\n")
cat("  because Korea's per-patient saving differs slightly between scenarios.\n")

cat("\n  The eligible share above is printed so it can be eyeballed against\n")
cat("  published Chinese obesity prevalence. It is not an output of interest.\n")

cat("\n  REMINDER: scope sensitivity, not a forecast. 2022 prevalence on 2050\n")
cat("  population, Korea per-patient savings, no mortality, no accumulation.\n")
