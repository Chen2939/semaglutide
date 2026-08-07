
#Latest change: 
#Version 9.7 to 9.8
#Better documentation, added age limit to eligibility (75)
#Removed floor on efficacy (now simulated individuals can gain weight)
#Removed slice_tail function because it was a failsafe for unclean data (where BMI values have no matching category)
#But our data should be clean
#Version 9.6 to 9.7 update population data to be grouped by age AND sex
#Previously was only grouped by age

#Use alternative libraries (e.g. SAS)
library(haven)
library(excel.link)
library(tidyverse)
library(readxl)
library("tidylog", warn.conflicts=FALSE)
library(Hmisc)
library(cowplot)
library(gridExtra)
library(janitor)
library(lubridate)
library(forcats)
library(mixtools)
library(KernSmooth)

#Clear workspace and run garbage collection
rm(list = ls())
gc()

##########################################
#########   RUN CONFIGURATION   ##########
##########################################

# Input directory. Every raw file this script reads lives here. Overridable so
# the script is not pinned to one machine; the default is the directory whose
# copy of full_simulation_results8.rds is bit-identical to the repo's, i.e. the
# lineage the Python pipeline actually consumes.
DATA_DIR <- Sys.getenv(
  "SEMAG_DATA_DIR",
  "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Code and data"
)

# Output. ONE constant, read once at the save site and once at the load site, so
# the two cannot drift apart again. The previous divergence was not a typo -- the
# save site and the load site were separated by 50 lines and an interactive
# setwd(), and the diagnostics below spent the life of the model reading a
# different file from the one the script had just written.
#
# sec 2.7, RESOLVED. The regenerated population gets its OWN filename rather
# than overwriting full_simulation_results8.rds:
#
#   * ...8.rds is the artefact every pre-regeneration manuscript number rests
#     on and the baseline Phase 5 reconciles against. Keeping it as a FILE, not
#     just as a column in a table, keeps the reconciliation auditable after the
#     fact.
#   * The regeneration changes what the file means -- different BMI
#     construction, different heights, different seeding -- so a new name is
#     honest about that.
#
# Written straight to the repository root. The old OneDrive round-trip is
# precisely what produced the two divergent artefacts: the save-site setwd() and
# the load-site setwd() disagreed and nobody noticed for the life of the model.
#
# Runs A and B are separability scaffolding, not production, and are pointed at
# data_result/regeneration/ by passing SEMAG_OUT_RDS explicitly.
RUN_LABEL <- Sys.getenv("SEMAG_RUN_LABEL", "C")
OUT_RDS <- Sys.getenv(
  "SEMAG_OUT_RDS",
  "C:/Users/sethw/repos/full_simulation_results9.rds"
)

# Scratch/diagnostic outputs. Never the repo root.
DIAG_DIR <- Sys.getenv("SEMAG_DIAG_DIR", "C:/Users/sethw/repos/diagnostics")
dir.create(DIAG_DIR, showWarnings = FALSE, recursive = TRUE)

# Reference year for the population, the BMI shares and the birth-cohort
# arithmetic. Not a free parameter -- changing it desynchronises three inputs.
REFERENCE_YEAR <- 2022

# NCD-RisC age groups in age order. Defined here, above every consumer, because
# the labels' LEXICAL order is not their numeric order and a locale-sensitive
# sort would silently reshuffle the per-stratum seed keys on another machine.
# Used by the G3 report, the stratum table (sec 2.8) and the seed assignment.
AGE_GROUP_LEVELS <- c("18-19", "20-24", "25-29", "30-34", "35-39", "40-44",
                      "45-49", "50-54", "55-59", "60-64", "65-69", "70-74",
                      "75-79", "80-84", "85plus")

# The seven NCD-RisC category-share columns, post-rename, in band order. Named
# here so the select() in the data-loading stage, the CDF construction and the
# G2 gate cannot disagree about which columns are the shares or what order they
# are in -- the knot vector depends on the order.
#
# Defined ABOVE the input cache, not inside the data-loading stage. It was
# inside, which meant it simply did not exist on a cache hit and G2 died with
# "object 'BMI_SHARE_COLS' not found". Runs A and C both BUILT their cache so
# they never saw it; Run B was the first cache-hit full run and was the first to
# fail. Anything the script needs after the cache block has to be defined
# outside it -- see the guard immediately after that block.
BMI_SHARE_COLS <- c("BMI_under_18.5", "BMI_18.5to20", "BMI_20to25",
                    "BMI_25to30", "BMI_30to35", "BMI_35to40", "BMI_over_40")

# Seeding (sec 2.8). A single top-level seed does not survive the BMI change:
# the old fit_bmi_mixture() burned ~20,000 rnorm/rskewnorm draws per stratum and
# the replacement burns none, so every downstream draw in every stratum would
# shift and no movement in the results could be attributed to anything. Each
# stratum instead gets its own seed keyed on its index in a deterministically
# sorted stratum table, which also makes the run order-independent (gate G5).
GLOBAL_SEED     <- 43
# Offset for the scenario draws, which are made once outside both scenario calls
# (sec 2.9). Chosen far above the 1,890 stratum indices so the two streams cannot
# collide.
SCENARIO_OFFSET <- 1000000L

# ---- TEMPORARY Phase 3 scaffolding. REMOVE BEFORE THE FINAL COMMIT. ----
# The three substantive changes must be attributable separately, so each is
# individually switchable for the A/B/C separability runs. The BMI fix is not
# switchable: it is the basis of all three runs.
#   Run A: cohort height off, height loss off
#   Run B: cohort height on,  height loss off
#   Run C: cohort height on,  height loss on   <- the production run
USE_COHORT_HEIGHT <- as.logical(Sys.getenv("SEMAG_COHORT_HEIGHT", "TRUE"))
USE_HEIGHT_LOSS   <- as.logical(Sys.getenv("SEMAG_HEIGHT_LOSS",   "TRUE"))
stopifnot(!is.na(USE_COHORT_HEIGHT), !is.na(USE_HEIGHT_LOSS))
# Height loss is a correction to the cohort-matched height; applying it on top
# of the single 2019 height would be a third thing neither run isolates.
stopifnot(!(USE_HEIGHT_LOSS && !USE_COHORT_HEIGHT))

# Batch size is a pure performance knob once seeding is per-stratum. G5 runs the
# whole simulation at 7 instead of 10 and requires bit-identical output.
BATCH_SIZE    <- as.integer(Sys.getenv("SEMAG_BATCH_SIZE", "10"))
N_INDIVIDUALS <- as.integer(Sys.getenv("SEMAG_N_INDIVIDUALS", "500"))

# ---- SMOKE TEST. Also temporary scaffolding. ----
# Cap the number of strata simulated, to shake out runtime errors and measure
# throughput without paying for a full run. A capped run CANNOT produce a
# production artefact: the gates that need the whole country set are skipped
# with a loud notice and OUT_RDS is not written. That is deliberate -- a smoke
# mode that can silently write a truncated .rds is worse than no smoke mode.
MAX_STRATA <- as.integer(Sys.getenv("SEMAG_MAX_STRATA", "0"))   # 0 = no cap
SMOKE <- MAX_STRATA > 0
if (SMOKE) {
  cat("\n*** SMOKE RUN: strata capped at ", MAX_STRATA,
      ". Gates G2/G8 skipped; OUT_RDS will NOT be written. ***\n", sep = "")
}

# tidylog reports every dplyr verb. On a full run that is hundreds of
# thousands of lines and it buries the gate output. The library stays
# loaded (it is in the original script); only the reporting is off.
options(tidylog.display = list())

RUN_T0 <- Sys.time()
stage_time <- function(label) {
  cat(sprintf("  [t+%7.1fs] %s\n",
              as.numeric(difftime(Sys.time(), RUN_T0, units = "secs")), label))
}

cat("---- run configuration ----\n")
cat(sprintf("  DATA_DIR          : %s\n", DATA_DIR))
cat(sprintf("  OUT_RDS           : %s\n", OUT_RDS))
cat(sprintf("  GLOBAL_SEED       : %d\n", GLOBAL_SEED))
cat(sprintf("  USE_COHORT_HEIGHT : %s\n", USE_COHORT_HEIGHT))
cat(sprintf("  USE_HEIGHT_LOSS   : %s\n", USE_HEIGHT_LOSS))
cat(sprintf("  BATCH_SIZE        : %d\n", BATCH_SIZE))
cat(sprintf("  N_INDIVIDUALS     : %d\n", N_INDIVIDUALS))
cat("---------------------------\n")

# Provenance of every raw input, owed to methods (sec 2.1.4). Printed rather
# than reconstructed later, because an access date cannot be recovered from a
# file that has since been re-downloaded.
report_input <- function(path) {
  fi <- file.info(path)
  if (is.na(fi$size)) stop("Input file not found: ", path)
  cat(sprintf("  %-62s %s  %12.0f bytes\n",
              basename(path),
              format(fi$mtime, "%Y-%m-%d %H:%M:%S"),
              fi$size))
  invisible(path)
}

###############  THEME  ################

clean_theme <- function() {
  theme_bw() +
    theme(
      panel.grid.major = element_blank(),
      panel.grid.minor = element_blank(),
      axis.text = element_text(size = 13),
      plot.margin = margin(5.5, 6, 5.5, 6),
      axis.title = element_text(size = 13),
      panel.border = element_rect(color = "black", fill = NA)
    )
}

##########################################
############ DATA LOADING ###############
##########################################

cat("\n---- input files ----\n")

# Everything from here to the stratum table is DETERMINISTIC and consumes no
# RNG: file reads, renames, joins, and the closed-form CDF construction. Phases
# 2, 3 and 5 need five or six runs of the simulation and every one of them would
# otherwise re-parse two 212 MB WPP workbooks to produce a byte-identical frame.
#
# The cache is keyed on the size and mtime of EVERY raw input plus the config
# values that change the frame, so a changed input or a toggle flip invalidates
# it rather than silently reusing a stale join. Delete the file, or set
# SEMAG_NO_CACHE=1, to force a rebuild.
# One cache file per height variant. The frame genuinely differs between them
# (Run A joins the 2019 cohort for everyone), and a single path would make
# Runs A and B/C evict each other and re-parse 425 MB of workbooks every time.
CACHE_PATH <- file.path(DIAG_DIR, sprintf(
  "inputs_cache_%s.rds", if (USE_COHORT_HEIGHT) "cohort" else "flat2019"))
USE_CACHE  <- Sys.getenv("SEMAG_NO_CACHE", "") == ""

.raw_inputs <- file.path(DATA_DIR, c(
  "Lancet/NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv",
  "Lancet/NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv",
  "Lancet/lancet_column_names.xlsx",
  "Lancet/NCD_RisC_Lancet_2020_height_child_adolescent_country.csv",
  "Worldbank_incomes_cleaned.xlsx",
  "UN/WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx",
  "UN/WPP2024_POP_F01_3_POPULATION_SINGLE_AGE_FEMALE.xlsx",
  "Lancet/NCD_RisC_Lancet_2024_Diabetes_age_specific_countries.csv"
))
.fi <- file.info(.raw_inputs)
if (any(is.na(.fi$size))) {
  stop("Missing input file(s):\n  ",
       paste(.raw_inputs[is.na(.fi$size)], collapse = "\n  "))
}
CACHE_KEY <- list(
  files = data.frame(path = basename(.raw_inputs), size = .fi$size,
                     mtime = as.character(.fi$mtime)),
  reference_year = REFERENCE_YEAR,
  use_cohort_height = USE_COHORT_HEIGHT
)
for (i in seq_along(.raw_inputs)) {
  cat(sprintf("  %-62s %s  %12.0f bytes\n", basename(.raw_inputs[i]),
              format(.fi$mtime[i], "%Y-%m-%d %H:%M:%S"), .fi$size[i]))
}

CACHE_HIT <- FALSE
if (USE_CACHE && file.exists(CACHE_PATH)) {
  .cached <- readRDS(CACHE_PATH)
  if (identical(.cached$key, CACHE_KEY)) {
    cat("\n  input cache HIT -- skipping the data-loading stage.\n")
    cat(sprintf("  %s\n", CACHE_PATH))
    lancet_dia  <- .cached$lancet_dia
    lancet_high <- .cached$lancet_high
    lancet_pop  <- .cached$lancet_pop
    CACHE_HIT   <- TRUE
  } else {
    cat("\n  input cache STALE (inputs or config changed) -- rebuilding.\n")
  }
  rm(.cached)
}

if (!CACHE_HIT) {

# Load Lancet BMI data.
# Vintage: the Lancet 2024 adult release (sec 2.1.4). NCD-RisC has since
# superseded it with NCD_RisC_Nature_2026_BMI_*, which is deliberately NOT used:
# the 2024 vintage matches the 2022 reference year used throughout, and swapping
# it would add a confound to this regeneration.
f_bmi_female <- report_input(file.path(DATA_DIR, "Lancet/NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv"))
f_bmi_male   <- report_input(file.path(DATA_DIR, "Lancet/NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv"))
bmi_female <- read_csv(f_bmi_female)
bmi_male <- read_csv(f_bmi_male)

#bind two dfs
bmi <- rbind(bmi_female, bmi_male)

#Clean lancet data
bmi_small <- bmi %>% filter(Year > 2021)

#New column names
f_col_names <- report_input(file.path(DATA_DIR, "Lancet/lancet_column_names.xlsx"))
lancet_col_names <- xl.read.file(f_col_names)

# Create a named vector for renaming
dict <- lancet_col_names %>% deframe()

#Rename column heads and clean
# sec 2.1.3: this used to be select(-which(nchar(names(.)) > 20)), which drops
# columns by NAME LENGTH. It works on today's file, but only just:
# "Country/Region/World" is exactly 20 characters and survives by one. A rename
# upstream -- or a release that spells it "Country/Region/World Name" -- would
# silently drop a needed variable and the script would carry on. An explicit
# select turns that silent failure into a loud one. Safe to do now: the mean-BMI
# column this might have been protecting does not exist in this release.
bmi_clean <- bmi_small %>%
  rename(all_of(dict)) %>%
  select(Year, Sex, `Country/Region/World`, ISO, `Age group`,
         all_of(BMI_SHARE_COLS)) %>%
  rename(Country = `Country/Region/World`,
         Age_Group = 'Age group') %>%
  mutate(Country = recode(Country, "Turkiye" = "Turkey"))

# The reference year is load-bearing for the cohort-height arithmetic below, so
# assert it rather than trusting the Year > 2021 filter to have left one year.
stopifnot(identical(sort(unique(bmi_clean$Year)), REFERENCE_YEAR))
# sec 2.2 / G6: the population step builds the label "85plus". If NCD-RisC ever
# spells it differently the join silently drops the oldest stratum.
stopifnot("85plus" %in% bmi_clean$Age_Group)

####################################
#########   ADD HEIGHT  ############
####################################

f_height <- report_input(file.path(DATA_DIR, "Lancet/NCD_RisC_Lancet_2020_height_child_adolescent_country.csv"))
height<-read.csv(f_height)

# sec 2.2 -- MATCH ATTAINED HEIGHT BY BIRTH COHORT.
#
# This used to filter Year > 2018 and Age.group > 18 and join on Country and Sex
# alone, i.e. it took the mean height of NINETEEN-YEAR-OLDS IN 2019 and assigned
# it to every adult age group. That gives the whole population the height of the
# tallest, most recent cohort, overstating height and therefore weight for older
# age groups.
#
# Each age group now takes age-19 height from the year that cohort turned 19.
# Someone aged `a` in 2022 turned 19 in 2022 - a + 19 = 2041 - a; a 70-year-old
# in 2022 therefore gets 1971.
#
# COVERAGE. The series runs 1985-2019, so the cohort year is clamped to that
# range at BOTH ends.
#   Lower edge (sec 2.2, decided): cohorts turning 19 before 1985 -- roughly ages
#   56 and up -- are held at the 1985 cohort. Falling back to 2019 instead would
#   reintroduce the defect for exactly the strata it matters most for.
#   Upper edge (NOT in the brief; see phase0_recon.md 5.4): the series ENDS at
#   2019, so the 18-19 group's cohort turned 19 in 2022-2023 and is also outside
#   the data. Held at 2019, which is what the old code did for everyone -- but
#   now only for the one group where it happens to be right.
# Back-extrapolating each country's secular trend outside the data was
# considered and not adopted.
#
# Height does not affect eligibility, which is keyed on `bmi`.
HEIGHT_YEAR_MIN <- min(height$Year)
HEIGHT_YEAR_MAX <- max(height$Year)
stopifnot(HEIGHT_YEAR_MIN == 1985, HEIGHT_YEAR_MAX == 2019)

# Representative age per NCD-RisC age group, used only to pick the cohort year.
# The midpoint; "85plus" takes 87, the midpoint of the 85-89 range the age
# sampler actually draws from.
age_group_midpoint <- function(ag) {
  vapply(ag, function(g) {
    if (grepl("plus", g)) return(87)
    v <- as.numeric(str_extract_all(g, "\\d+")[[1]])
    mean(v)
  }, numeric(1))
}

height_clean <- height %>%
  filter(Age.group == 19) %>%
  select(Country, Sex, Year, Mean.height, Mean.height.standard.error) %>%
  rename(Mean_height = Mean.height,
         Mean_height_s_e = Mean.height.standard.error,
         cohort_year = Year) %>%
  mutate(Sex = recode(Sex, "Girls" = "Women", "Boys" = "Men"),
         Country = recode(Country,
                          "Czech Republic" = "Czechia",
                          "Macedonia (TFYR)" = "North Macedonia"))

if (USE_COHORT_HEIGHT) {
  bmi_clean <- bmi_clean %>%
    mutate(
      age_mid       = age_group_midpoint(Age_Group),
      cohort_year_r = REFERENCE_YEAR - age_mid + 19,
      cohort_year   = pmin(pmax(round(cohort_year_r), HEIGHT_YEAR_MIN),
                           HEIGHT_YEAR_MAX),
      cohort_held   = case_when(
        round(cohort_year_r) < HEIGHT_YEAR_MIN ~ "held_at_1985",
        round(cohort_year_r) > HEIGHT_YEAR_MAX ~ "held_at_2019",
        TRUE                                   ~ "in_range"
      )
    )
  bmi_join <- left_join(bmi_clean, height_clean,
                        by = c("Country", "Sex", "cohort_year"))
} else {
  # Run A comparator: the pre-fix behaviour, age-19 height in 2019 for everyone.
  height_2019 <- height_clean %>%
    filter(cohort_year == HEIGHT_YEAR_MAX) %>%
    select(-cohort_year)
  bmi_clean <- bmi_clean %>%
    mutate(age_mid = age_group_midpoint(Age_Group),
           cohort_year_r = NA_real_,
           cohort_year = HEIGHT_YEAR_MAX,
           cohort_held = "disabled")
  bmi_join <- left_join(bmi_clean, height_2019, by = c("Country", "Sex"))
}

# G3 -- cohort coverage, reported here because the counts are only meaningful
# against the modelled country set, which is not known until the income filter
# below. Recomputed there; this is the all-country view.
cat("\n---- G3 cohort-year coverage (all countries in the BMI file) ----\n")
print(bmi_join %>% count(Age_Group, cohort_year, cohort_held) %>% as.data.frame())

####################################
#########   ADD INCOME  ############
####################################

#Load WorldBank data
f_worldbank <- report_input(file.path(DATA_DIR, "Worldbank_incomes_cleaned.xlsx"))
worldbank <- xl.read.file(f_worldbank)

worldbank_high <- worldbank %>% 
  select(ISO, '2022') %>% 
  rename(Income = '2022') %>% 
  filter(Income %in% c("H"))

#Create df for high income countries
lancet_high <- left_join(worldbank_high, bmi_join, by = "ISO") %>% 
  filter(!is.na(Year))

####################################
#########   ADD POPULATION  ########
####################################
#https://population.un.org/wpp/downloads?folder=Standard%20Projections&group=Population

# Import population data
f_pop_male   <- report_input(file.path(DATA_DIR, "UN/WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx"))
f_pop_female <- report_input(file.path(DATA_DIR, "UN/WPP2024_POP_F01_3_POPULATION_SINGLE_AGE_FEMALE.xlsx"))

pop_male <- read_excel(f_pop_male,
                         sheet = 1,
                         skip = 16,
                         na = "")  # This tells R to only treat empty cells as NA

# Import population data
pop_female <- read_excel(f_pop_female,
                       sheet = 1,
                       skip = 16,
                       na = "")  # This tells R to only treat empty cells as NA

# Clean population data
pop_male_clean <- pop_male %>%
  mutate(across(starts_with(as.character(0:100)), as.numeric)) %>%
  filter(Year == 2022) %>%
  rename(Country = `Region, subregion, country or area *`) %>%
  pivot_longer(
    cols = matches("^\\d+\\+?$"),
    names_to = "Age",
    values_to = "Population"
  ) %>%
  mutate(
    Age = as.numeric(str_replace(Age, "\\+", "")),
    Age_Group = case_when(
      Age >= 18 & Age <= 19 ~ "18-19",
      Age >= 20 & Age <= 24 ~ "20-24",
      Age >= 25 & Age <= 29 ~ "25-29",
      Age >= 30 & Age <= 34 ~ "30-34",
      Age >= 35 & Age <= 39 ~ "35-39",
      Age >= 40 & Age <= 44 ~ "40-44",
      Age >= 45 & Age <= 49 ~ "45-49",
      Age >= 50 & Age <= 54 ~ "50-54",
      Age >= 55 & Age <= 59 ~ "55-59",
      Age >= 60 & Age <= 64 ~ "60-64",
      Age >= 65 & Age <= 69 ~ "65-69",
      Age >= 70 & Age <= 74 ~ "70-74",
      Age >= 75 & Age <= 79 ~ "75-79",
      Age >= 80 & Age <= 84 ~ "80-84",
      Age >= 85 ~ "85plus"
    )
  ) %>%
  filter(!is.na(Age_Group)) %>%
  group_by(Country, Year, Age_Group) %>%
  summarise(Population = sum(Population * 1000, na.rm = TRUE), .groups = "drop") %>% 
  mutate(Sex="Men")

# Clean female population data
pop_female_clean <- pop_female %>%
  mutate(across(starts_with(as.character(0:100)), as.numeric)) %>%
  filter(Year == 2022) %>%
  rename(Country = `Region, subregion, country or area *`) %>%
  pivot_longer(
    cols = matches("^\\d+\\+?$"),
    names_to = "Age",
    values_to = "Population"
  ) %>%
  mutate(
    Age = as.numeric(str_replace(Age, "\\+", "")),
    Age_Group = case_when(
      Age >= 18 & Age <= 19 ~ "18-19",
      Age >= 20 & Age <= 24 ~ "20-24",
      Age >= 25 & Age <= 29 ~ "25-29",
      Age >= 30 & Age <= 34 ~ "30-34",
      Age >= 35 & Age <= 39 ~ "35-39",
      Age >= 40 & Age <= 44 ~ "40-44",
      Age >= 45 & Age <= 49 ~ "45-49",
      Age >= 50 & Age <= 54 ~ "50-54",
      Age >= 55 & Age <= 59 ~ "55-59",
      Age >= 60 & Age <= 64 ~ "60-64",
      Age >= 65 & Age <= 69 ~ "65-69",
      Age >= 70 & Age <= 74 ~ "70-74",
      Age >= 75 & Age <= 79 ~ "75-79",
      Age >= 80 & Age <= 84 ~ "80-84",
      Age >= 85 ~ "85plus"
    )
  ) %>%
  filter(!is.na(Age_Group)) %>%
  group_by(Country, Year, Age_Group) %>%
  summarise(Population = sum(Population * 1000, na.rm = TRUE), .groups = "drop") %>% 
  mutate(Sex="Women")

population_clean <- rbind(pop_female_clean, pop_male_clean)


# Join population pop_male# Join population data
lancet_pop <- lancet_high %>%
  mutate(Country = case_when(
    Country == "South Korea" ~ "Republic of Korea",
    Country == "Taiwan" ~ "China, Taiwan Province of China",
    TRUE ~ Country
  )) %>%
  left_join(population_clean, by = c("Country", "Year", "Age_Group", "Sex"))


####################################
#########   ADD DIABETES  ##########
####################################

#diabetes prevalence is from 2014 (stratified by age)
#diabetes_men <- read.csv("C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Lancet/NCD-RisC_Lancet_2016_Diabetes_Men_Agespecific_Prevalence_by_Country.csv")
#diabetes_women <- read.csv("C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Lancet/NCD-RisC_Lancet_2016_Diabetes_Women_Agespecific_Prevalence_by_Country.csv")

#Add new diabetes prevalence data
f_diabetes <- report_input(file.path(DATA_DIR, "Lancet/NCD_RisC_Lancet_2024_Diabetes_age_specific_countries.csv"))
diabetes_new <- read.csv(f_diabetes)


#Clean and combine diabetes data
diabetes <- diabetes_new %>% 
  filter(Year == "2022") %>% 
  select(Country.Region.World, Prevalence.of.diabetes, Age, Sex) %>% 
  rename(Age_Group = Age,
         Diabetes_prevalence = Prevalence.of.diabetes,
         Country = Country.Region.World) %>%
  mutate(Country = recode(Country,
                          "Czech Republic" = "Czechia",
                          "Taiwan" = "China, Taiwan Province of China",
                          "South Korea" = "Republic of Korea"))

# Join diabetes data
lancet_dia <- left_join(lancet_pop, diabetes, by = c("Country", "Age_Group", "Sex"))

saveRDS(list(key = CACHE_KEY, lancet_dia = lancet_dia,
             lancet_high = lancet_high, lancet_pop = lancet_pop),
        CACHE_PATH)
cat(sprintf("\n  input cache written: %s\n", CACHE_PATH))

}  # end if (!CACHE_HIT)

# Whatever the cache path, the rest of the script needs these. A name defined
# only inside the block above exists on a cache MISS and vanishes on a HIT, so
# the bug hides until the second run with unchanged inputs -- which is exactly
# how it escaped Runs A and C and killed Run B's G2. Assert rather than trust.
.needed <- c("lancet_dia", "lancet_high", "lancet_pop",
             "BMI_SHARE_COLS", "AGE_GROUP_LEVELS")
.absent <- .needed[!vapply(.needed, exists, logical(1))]
if (length(.absent)) {
  stop("Objects missing after the input-cache block: ",
       paste(.absent, collapse = ", "),
       ". Define them ABOVE the block, not inside it.")
}
rm(.needed, .absent)

##########################################
#####   GATE G3 -- cohort height      ####
##########################################
# On the MODELLED set. Mean attained (pre-loss) assigned height by age group
# must DECREASE with age group for countries with strong secular height trends.
cat("\n---- G3 cohort height, modelled set ----\n")
cat("  strata held at a coverage edge, and the population they represent:\n")
.held <- lancet_dia %>%
  group_by(cohort_held) %>%
  summarise(strata = n(), population = sum(Population), .groups = "drop") %>%
  mutate(pop_share = population / sum(population))
print(as.data.frame(.held))

cat("\n  mean attained height by age group, countries with strong secular trends:\n")
.g3 <- lancet_dia %>%
  filter(ISO %in% c("KOR", "JPN", "ESP", "ITA", "PRT", "GRC")) %>%
  select(ISO, Sex, Age_Group, cohort_year, Mean_height) %>%
  arrange(ISO, Sex, match(Age_Group, c("18-19","20-24","25-29","30-34","35-39",
                                       "40-44","45-49","50-54","55-59","60-64",
                                       "65-69","70-74","75-79","80-84","85plus")))
print(as.data.frame(.g3 %>% filter(Sex == "Men")))

if (USE_COHORT_HEIGHT) {
  # The brief says attained height "must decrease with age group". That holds
  # in AGGREGATE but not country by country, and it never could: the NCD-RisC
  # series plateau and wobble for recent cohorts in high-income countries.
  # Spain's male series peaks at the 2004 cohort and dips slightly for
  # 2009-2019. That is data, not a construction error, so the aggregate
  # direction is what is reported and the local wobble is context.
  cat("\n  population-weighted mean ATTAINED height by age group:\n")
  .byag <- lancet_dia %>%
    group_by(Sex, Age_Group) %>%
    summarise(mean_attained_cm = weighted.mean(Mean_height, Population),
              cohort_year = first(cohort_year), .groups = "drop") %>%
    arrange(Sex, match(Age_Group, AGE_GROUP_LEVELS))
  print(as.data.frame(.byag))

  # Aggregate direction: youngest IN-RANGE cohort against the oldest, per
  # country x sex. A country where the old cohort is TALLER is the thing that
  # would signal a broken cohort mapping.
  .dir <- lancet_dia %>%
    filter(cohort_held == "in_range") %>%
    group_by(ISO, Sex) %>%
    summarise(young = Mean_height[which.max(cohort_year)],
              old   = Mean_height[which.min(cohort_year)],
              .groups = "drop") %>%
    mutate(gain_cm = young - old)
  cat(sprintf("\n  young-minus-old attained height over the in-range window:\n"))
  cat(sprintf("    mean %+.3f cm, median %+.3f cm, min %+.3f cm, max %+.3f cm\n",
              mean(.dir$gain_cm), median(.dir$gain_cm),
              min(.dir$gain_cm), max(.dir$gain_cm)))
  cat(sprintf("    country x sex groups where the OLD cohort is taller: %d of %d\n",
              sum(.dir$gain_cm < 0), nrow(.dir)))
  if (any(.dir$gain_cm < 0)) {
    print(as.data.frame(.dir %>% filter(gain_cm < 0) %>% arrange(gain_cm)))
  }

  # Local wobble, reported as context only.
  .mono <- lancet_dia %>%
    filter(cohort_held == "in_range") %>%
    arrange(ISO, Sex, desc(cohort_year)) %>%
    group_by(ISO, Sex) %>%
    summarise(n_increases = sum(diff(Mean_height) > 0), .groups = "drop")
  cat(sprintf("    groups with any LOCAL increase (expected, not a defect): %d of %d\n",
              sum(.mono$n_increases > 0), nrow(.mono)))
  rm(.mono, .byag, .dir)
}
rm(.held, .g3)

####################################
#########   HELPER FUNCTIONS  ######
####################################

# Function to get BMI category
get_bmi_category <- function(bmi) {
  case_when(
    bmi < 18.5 ~ "< 18.5",
    bmi < 25 ~ ">= 18.5 & <25",
    bmi < 30 ~ ">= 25 & <30",
    bmi < 35 ~ ">= 30 & <35",
    bmi < 40 ~ ">= 35 & <40",
    TRUE ~ ">= 40"
  )
}

# Function to sample ages from age groups
get_age_sample <- function(age_group, n = 1) {
  if(length(age_group) == 1) age_group <- rep(age_group, n)
  
  sapply(age_group, function(ag) {
    if(grepl("plus", ag)) {
      return(round(runif(1, 85, 89)))
    }
    ages <- as.numeric(str_extract_all(ag, "\\d+")[[1]])
    round(runif(1, min = ages[1], max = ages[2]))
  })
}

# PAL parameters
pal_params_men <- tribble(
  ~bmi_cat, ~mean_pal, ~sd_pal,
  "< 18.5", 1.52, 0.28,
  ">= 18.5 & <25", 1.78, 0.32,
  ">= 25 & <30", 1.75, 0.29,
  ">= 30 & <35", 1.78, 0.33,
  ">= 35 & <40", 1.81, 0.36,
  ">= 40", 1.75, 0.36
)

pal_params_women <- tribble(
  ~bmi_cat, ~mean_pal, ~sd_pal,
  "< 18.5", 1.82, 0.32,
  ">= 18.5 & <25", 1.73, 0.32,
  ">= 25 & <30", 1.68, 0.25,
  ">= 30 & <35", 1.67, 0.23,
  ">= 35 & <40", 1.66, 0.30,
  ">= 40", 1.60, 0.30
)

# Vectorized PAL generation
generate_pal_vectorized <- function(sex_vector, bmi_vector) {
  bmi_cats <- get_bmi_category(bmi_vector)
  
  mapply(function(sex, bmi_cat) {
    params <- if(sex == "Men") pal_params_men else pal_params_women
    cat_params <- params %>% filter(bmi_cat == !!bmi_cat)
    
    pal <- rnorm(1, mean = cat_params$mean_pal, sd = cat_params$sd_pal)
    pmin(pmax(pal, 1.0), 2.5)
  }, sex_vector, bmi_cats, USE.NAMES = FALSE)
}

####################################
#########   BMI DISTRIBUTION  ######
####################################
#
# sec 2.1 -- PIECEWISE-LINEAR CDF, replacing the synthetic-point-cloud + KDE +
# moving-average mixture.
#
# The old fit_bmi_mixture() built a 20,000-point cloud per band, concatenated
# the seven clouds in the observed proportions, then applied a KDE and a
# moving-average smoother. The result was flattened toward the 1/7 uniform
# share: deviation correlated -0.68 with target share across 13,230 stratum x
# category cells, zero-crossing at 0.1429. Population-weighted BMI >= 30 was
# overstated by 1.57 pp, and because flattening amplifies relative error at low
# shares, Japan and Korea were overstated by roughly a third. See
# diagnostics/reports/bmi_mixture_reproduction_check.md.
#
# The four smoothing stages are not repaired -- the construction is discarded.
# The NCD-RisC shares give the cumulative probability at each band boundary
# EXACTLY, so a piecewise-linear CDF through those points reproduces the seven
# band shares by construction, with no residual to tune. This follows the OECD
# SPHeP-NCDs microsimulation model, which builds BMI distributions from the same
# NCD-RisC dataset using the identical seven categories.
#
# Known and accepted cost: the implied density is uniform within each band and
# discontinuous at band boundaries, including inside the four top-band
# sub-bands. That is the cost OECD accepted on the same data for the same
# reason. It is not a defect to be fixed.
#
# The sampler does not change. simulate_single_population() already inverts a
# CDF with approx(dist$cdf, dist$x, u, rule = 2), and approx() defaults to
# linear interpolation, which is exactly what is wanted. It is now fed eleven
# knots instead of a 471-point KDE grid.
#
# Monotonicity is free: a piecewise-linear CDF through non-decreasing cumulative
# points cannot decrease. No monoH.FC, no overshoot risk.
#
# Two interior thresholds become constants rather than outputs, and so are not
# reported as diagnostics: under a linear CDF exactly 60% of the 25-30 band sits
# above BMI 27 (type-2-diabetes eligibility) and exactly 50% above BMI 27.5 (a
# hazard-ratio bin break, 1.07 below / 1.20 above).

# Lower anchor of the BMI support. This is the value the previous grid used
# (seq(13, 60, by = 0.1), range.x = c(13, 60)) and it is kept unchanged.
# It is inert for results: nobody below BMI 27 is eligible, so
# individual_effect = 0, new_bmi = bmi, and both eer_diff and the survivor-side
# hazard conversion are identically zero across the entire underweight band.
BMI_LOWER_BOUND <- 13

# Band boundaries the NCD-RisC shares cumulate to.
BMI_BAND_EDGES <- c(18.5, 20, 25, 30, 35, 40)

# --- Top band (sec 2.1.2) --------------------------------------------------
#
# The share above BMI 40 is known from NCD-RisC; its EXTENT is not. The CDF
# needs an upper anchor and this is the thing that most affects results,
# because top-band BMI drives weight -> BMR -> EER -> food savings directly.
#
# Two anchors are rejected and must not be re-proposed. OECD's 150 kg/m^2 bound
# is a plausibility clamp for a model in which the top band's shape is
# immaterial; a linear segment from 40 to 150 puts the mean of the >= 40 group
# near 95. The old grid capped at 60 with a KDE inside it, implying a top-band
# mean of 50, which is too high. Pinning the tail to a published stratum mean is
# not available: the NCD-RisC Lancet 2024 adult release carries no mean BMI
# column in any file.
#
# Kitahara et al. 2014, PLOS Medicine, Table 4 (also Table 2) participant counts
# for BMI 40-45 / 45-50 / 50-55 / 55-60. PARTICIPANTS, not deaths.
# Deaths-weighting (669/245/87/35) would give a top-band mean of 45.03; the
# composition of the LIVING top band is the quantity wanted, so participants is
# correct.
CLASS3_N     <- c(6803, 1978, 627, 156)          # total 9564
CLASS3_SHARE <- CLASS3_N / sum(CLASS3_N)
# Tail fractions: P(BMI > 45 | >= 40), P(> 50 | >= 40), P(> 55 | >= 40).
# Derived, never literals -- sec 2.15 reads the same CLASS3_SHARE object and
# that shared derivation is what stops the two sections drifting apart.
CLASS3_TAIL  <- rev(cumsum(rev(CLASS3_SHARE)))[-1]
BMI_TOP_EDGES <- c(45, 50, 55, 60)

# The anchor sits deliberately at the low end of the plausible range. Every
# identifiable bias in the Kitahara composition pushes it down. Do not adjust
# it; a per-country or per-sex tail was considered and rejected.

# Build the eleven-knot CDF for one stratum's seven category shares.
#
# Given the stratum's share above 40 (p40), the absolute CDF values in the top
# band are F(40) = 1 - p40, F(45) = 1 - p40*tail1, F(50) = 1 - p40*tail2,
# F(55) = 1 - p40*tail3, F(60) = 1.
fit_bmi_cdf <- function(props) {
  cum6 <- cumsum(props)[1:6]          # F at 18.5, 20, 25, 30, 35, 40
  p40  <- props[7]

  x <- c(BMI_LOWER_BOUND, BMI_BAND_EDGES, BMI_TOP_EDGES)
  cdf <- c(0, cum6, 1 - p40 * CLASS3_TAIL, 1)

  list(x = x, cdf = cdf, original_props = props)
}

# Wrapper for use with mutate.
#
# RETAINS the existing sanity guard on the input proportions (NA, negative, or
# not summing to 1 within tolerance), but reports the offending stratum instead
# of silently returning NULL. The old failure mode was worse than silent: a NULL
# bmi_distribution reached approx(NULL, NULL, u) and errored mid-run with
# nothing identifying which stratum caused it.
#
# EXTENDED by one line: the assembled cdf must be STRICTLY increasing. With a
# stratum's >= 40 share at or near zero the four tail knots collapse to
# duplicate values and approx() silently averages ties rather than erroring.
bad_strata <- new.env(parent = emptyenv())
bad_strata$rows <- list()

get_bmi_cdf <- function(props, label) {
  if (any(is.na(props)) || abs(sum(props) - 1) > 0.01 || any(props < 0)) {
    bad_strata$rows[[length(bad_strata$rows) + 1]] <-
      list(label = label, reason = "props NA / negative / do not sum to 1",
           props = props)
    return(NULL)
  }
  d <- fit_bmi_cdf(props)
  if (any(diff(d$cdf) <= 0)) {
    bad_strata$rows[[length(bad_strata$rows) + 1]] <-
      list(label = label, reason = "assembled cdf not strictly increasing",
           props = props)
    return(NULL)
  }
  d
}

# Apply to data.
lancet_dia_with_dist <- lancet_dia %>%
  mutate(.stratum_label = paste(ISO, Sex, Age_Group, sep = "/")) %>%
  rowwise() %>%
  mutate(
    bmi_distribution = list(get_bmi_cdf(
      c(BMI_under_18.5, BMI_18.5to20, BMI_20to25,
        BMI_25to30, BMI_30to35, BMI_35to40, BMI_over_40),
      .stratum_label
    ))
  ) %>%
  ungroup()

if (length(bad_strata$rows) > 0) {
  cat("\n*** strata that failed the BMI-share guard ***\n")
  for (r in bad_strata$rows) {
    cat(sprintf("  %-24s %s  [%s]\n", r$label, r$reason,
                paste(sprintf("%.6f", r$props), collapse = ", ")))
  }
  stop(sprintf("%d stratum/strata failed the BMI-share guard; see above.",
               length(bad_strata$rows)))
}

####################################
#####   AGE-RELATED HEIGHT LOSS  ###
####################################
#
# sec 2.3 -- sec 2.2 corrects the SECULAR component of height differences across
# age groups. This corrects the AGING component, which is separate and was
# previously unmodelled.
#
# NCD-RisC BMI comes from population-based measurement studies: measured weight
# over measured height, both taken contemporaneously. A 70-year-old's reported
# BMI was computed against their stature AT 70. But sec 2.2 assigns each
# individual their cohort's attained height AT 19, before any aging loss.
# Reconstructing weight = bmi * (height_at_19/100)^2 therefore divides a
# contemporaneous BMI by a stature the person no longer has, and overstates
# weight. Since eer_diff = 10 * pal * weight * individual_effect, the
# overstatement passes straight into food savings.
#
# The two corrections are genuinely orthogonal. Sorkin et al. (1999) establishes
# they are separable: cross-sectional height differences by age combine secular
# and aging effects, longitudinal differences isolate aging alone. Cohort
# matching handles the secular part from NCD-RisC's own country-specific series;
# this handles the aging part.
#
# This does NOT touch the survivor denominator. new_bmi = treatment_weight /
# (height_used/100)^2 = bmi * (1 - effect), so whichever height is used, it
# cancels -- but ONLY if the same height_used appears in the weight
# construction, the BMR term and the new_bmi computation. If one site keeps the
# cohort height while another uses height_used, the cancellation breaks and
# height leaks into the denominator. Gate G7 exists to catch exactly that.
#
# `bmi` itself is unchanged -- it comes from NCD-RisC directly. The hazard
# ratios in the mortality ladder were themselves estimated against measured BMI,
# so the height-loss artifact is already embedded in them. No correction is
# warranted on the mortality side and none is made.
#
# Sorkin JD, Muller DC, Andres R. "Longitudinal Change in Height of Men and
# Women: Implications for Interpretation of the Body Mass Index. The Baltimore
# Longitudinal Study of Aging." Am J Epidemiol 1999;150(9):969-77.
# doi:10.1093/oxfordjournals.aje.a010106

# TRANSCRIBED from Sorkin et al. 1999, appendix eq. 8 and 9.
# Do not edit without re-checking against the PDF.
#
# These are the paper's PRINTED cumulative-change integrals, deliberately not
# re-integrated. Re-integrating appendix eq. 3 and 4 gives men
# (0.043478, -0.000093660, -0.000014633) and women (0.071357, -0.000753400,
# -0.000015867); the printed set inflates modelled loss by +2.9% to +4.1% for
# men and +0.5% for women -- about 0.1 cm at age 70 for men, on the order of
# 0.03 cm at the treated population's mean age. That is a deliberate legibility
# compromise: the invariant above is worth more than 0.03 cm, and it is lost the
# moment the constants are ones nobody can verify by eye.
#
# Names are Men / Women, matching the Sex values carried through bmi_clean and
# the recode at the height join. A Male / Female naming would return NULL on
# lookup and fail silently or throw depending on call site.
HEIGHT_LOSS_COEF <- list(
  Men   = c(k1 = 0.0435, k2 = -0.00009, k3 = -0.000015),
  Women = c(k1 = 0.0714, k2 = -0.00075, k3 = -0.000016)
)

# Loss begins at about age 30 (Sorkin et al., abstract); below that the fitted
# cubic implies slight growth, which we do not extrapolate. Capped at 90: the
# oldest BLSA cell has n = 3 and the cubic steepens without support.
HEIGHT_LOSS_START_AGE <- 30
HEIGHT_LOSS_AGE_CAP   <- 90

height_loss_cm <- function(age, sex) {
  k <- HEIGHT_LOSS_COEF[[sex]]
  # Deliberately not named `F` -- that shadows base::F, the FALSE abbreviation.
  # Harmless here but a standing footgun in a reference function others read.
  cum_change <- function(A) k["k1"] * A + k["k2"] * A^2 + k["k3"] * A^3
  a <- pmin(pmax(age, HEIGHT_LOSS_START_AGE), HEIGHT_LOSS_AGE_CAP)
  as.numeric(pmax(0, cum_change(HEIGHT_LOSS_START_AGE) - cum_change(a)))
}

# Two behaviours recorded so nobody later mistakes them for load-bearing:
#  - pmax(0, ...) never binds. The cubic's derivative turns negative at age
#    29.16 (men) and 25.99 (women), so the function is monotonically decreasing
#    across the whole [30, 90] window. The clamp is defensive only.
#  - The age cap at 90 never binds either. Simulated ages top out at 89 (the
#    85plus group draws round(runif(85, 89))) and eligibility cuts at 75
#    regardless. Also defensive.

##########################################
#####   GATE G3b -- height loss, exact  ##
##########################################
# height_loss_cm() is a pure function, so it is gated directly, before it is
# wired into anything. Values computed from the PRINTED coefficients.
#
# NOT gated on the paper's abstract. Sorkin states roughly 3 cm (men) and 5 cm
# (women) of loss by age 70, rising to 5 cm and 8 cm by 80. Three of those four
# reproduce closely, but men at 80 computes to 5.595, which does not round to 5.
# That is a property of the paper's own rounded coefficients, not an
# implementation error: re-integrating from the un-rounded eq. 3 gives 5.438,
# which does round to 5. A gate phrased as "rounds to the abstract's figures"
# would fail correct code.
cat("\n---- G3b height loss, deterministic ----\n")
g3b <- data.frame(
  sex  = c("Men", "Men", "Men", "Women", "Women", "Women"),
  age  = c(50, 70, 80, 50, 70, 80),
  want = c(0.744, 3.360, 5.595, 1.340, 5.200, 8.315)
)
g3b$got <- mapply(function(a, s) height_loss_cm(a, s), g3b$age, g3b$sex)
g3b$err <- abs(g3b$got - g3b$want)
print(g3b)
if (any(g3b$err > 1e-6)) stop("G3b FAILED: height_loss_cm does not match the declared constants.")

# Three structural assertions.
.ages <- 18:89
for (.s in c("Men", "Women")) {
  .l <- height_loss_cm(.ages, .s)
  if (any(.l < 0)) stop("G3b FAILED: negative loss for ", .s)
  if (any(diff(.l) < -1e-12)) stop("G3b FAILED: not monotonically non-decreasing for ", .s)
  if (any(.l[.ages <= 30] != 0)) stop("G3b FAILED: non-zero loss at or below age 30 for ", .s)
}
cat("G3b PASS (six values to 1e-6; non-negative, monotone, zero at <= 30 for both sexes)\n")

# Sanity note only, per above.
cat("Sorkin abstract comparison (reported, NOT gated):\n")
for (i in seq_len(nrow(g3b))) {
  cat(sprintf("  %-6s age %d: model %.3f cm\n", g3b$sex[i], g3b$age[i], g3b$got[i]))
}
rm(.ages, .s, .l)

####################################
#########   SIMULATION  ############
####################################

# Helper function to simulate a single population
simulate_single_population <- function(data_row, n_individuals = 500) {
  if(!"Population" %in% names(data_row)) {
    stop("Population column missing from input data")
  }

  # sec 2.8 -- PER-STRATUM SEED, set before the first RNG call in this stratum.
  # stratum_index is this row's position in a table sorted deterministically on
  # (ISO, Sex, Age_Group), attached upstream. Consequences: the BMI change
  # perturbs only the BMI draws within a stratum, leaving ages, PAL and diabetes
  # bit-identical; and the run becomes order-independent, so batching no longer
  # affects results (gate G5).
  if (is.null(data_row$stratum_index) || is.na(data_row$stratum_index)) {
    stop("stratum_index missing -- per-stratum seeding cannot be applied")
  }
  set.seed(GLOBAL_SEED + data_row$stratum_index)

  # Extract parameters as vectors
  dist <- data_row$bmi_distribution[[1]]
  mean_height <- data_row$Mean_height
  sex <- data_row$Sex
  population <- data_row$Population

  # Generate BMI values
  u <- runif(n_individuals)
  bmi_values <- approx(dist$cdf, dist$x, u, rule = 2)$y

  # Generate heights
  height_sd <- if(sex == "Men") 7.0 else 6.5
  heights <- rnorm(n_individuals, mean = mean_height, sd = height_sd)

  # Generate ages as vector.
  # MOVED ABOVE the weight construction: height loss needs an individual age.
  # Ages are drawn from the same RNG position as before this move only because
  # nothing between the height draw and here consumes RNG -- the weight and
  # height_used arithmetic is deterministic.
  ages <- get_age_sample(data_row$Age_Group, n_individuals)

  # sec 2.3.4 -- apply age-related height loss PER INDIVIDUAL, here rather than
  # at the height join. `sex` is scalar-indexed via [[ and data_row$Sex is
  # length 1 per stratum, so that is safe; and the function needs an individual
  # age, which does not exist at the join (one row per country x sex x age
  # group). Within-group variation in loss is captured for free.
  #
  # For the record, the alternative -- applying at the join with the age-group
  # midpoint -- differs by under 0.02 cm across a five-year band. This is done
  # per individual because that is where the data lives, not because the
  # midpoint would have been wrong.
  height_used <- if (USE_HEIGHT_LOSS) {
    heights - height_loss_cm(ages, sex)
  } else {
    heights
  }

  # Calculate weights.
  # height_used must be used CONSISTENTLY here, in the BMR term and in new_bmi,
  # or the height-independence identity of sec 2.4 breaks and height leaks into
  # the survivor denominator. G7 tests this exactly.
  heights_m <- height_used / 100
  weights <- as.vector(bmi_values * (heights_m^2))

  # Generate PAL values
  sex_vector <- rep(sex, n_individuals)
  pal_values <- generate_pal_vectorized(sex_vector, bmi_values)

  # Calculate BMR and EER as vectors.
  # The direct 6.25 * height term cancels in eer_diff (identical pre- and
  # post-treatment), so height loss reaches eer_diff only through `weight`. It
  # does reach eer and bmr directly, so the PERCENTAGE EER reduction moves too.
  bmr_values <- if(sex == "Men") {
    (10 * weights) + (6.25 * height_used) - (5 * ages) + 5
  } else {
    (10 * weights) + (6.25 * height_used) - (5 * ages) - 161
  }

  eer_values <- bmr_values * pal_values

  # Diabetes relative risks calculation
  rr_per_5_bmi <- if(sex == "Men") 1.75 else 1.69
  bmi_reference <- 22
  bmi_difference <- (bmi_values - bmi_reference) / 5
  individual_rr <- rr_per_5_bmi^bmi_difference
  
  # Calibrate diabetes relative risks
  #This ensures the relative risks we calculate for each age group, country and sex
  #are calibrated to values in the real world
  target_prev <- data_row$Diabetes_prevalence
  scaled_rr <- individual_rr / mean(individual_rr)
  initial_probs <- target_prev * scaled_rr
  diabetes_prob <- pmin(pmax(initial_probs, 0), 1)
  diabetes_status <- rbinom(n_individuals, 1, diabetes_prob)
  
  # Create result tibble.
  # `height` is the ATTAINED (pre-loss) draw and `height_used` is what every
  # calculation actually uses. Carrying both rather than overwriting `height`
  # makes the sec 2.3.1 leak visible: if a downstream site reads `height` where
  # it should read `height_used`, the two columns differ and G7 catches it. No
  # Python consumer reads `height`, checked.
  tibble(
    bmi = bmi_values,
    height = heights,
    height_used = height_used,
    weight = weights,
    age = ages,
    pal = pal_values,
    bmr = bmr_values,
    eer = eer_values,
    diabetes = diabetes_status,
    diabetes_prob = diabetes_prob,
    Age_Group = data_row$Age_Group,
    Sex = sex,
    ISO = data_row$ISO,
    Population = population
  )
}

# Run simulation in batches.
# Batching is now a pure performance knob: seeding is per stratum, so results do
# not depend on batch_size. G5 asserts that by re-running at 7.
run_simulation_in_batches <- function(data, batch_size = 10, n_individuals = 500) {
  n_batches <- ceiling(nrow(data) / batch_size)

  map_dfr(1:n_batches, function(i) {
    if (i %% 20 == 1 || i == n_batches) {
      cat(sprintf("  batch %d of %d\n", i, n_batches))
    }

    start_idx <- (i-1) * batch_size + 1
    end_idx <- min(i * batch_size, nrow(data))
    current_batch <- data[start_idx:end_idx, ]

    current_batch %>%
      group_split(row_number()) %>%
      map_dfr(~simulate_single_population(.x, n_individuals))
  })
}

##########################################
#####   STRATUM TABLE AND SEED KEYS   ####
##########################################
# sec 2.8 -- build the stratum table sorted deterministically on
# (ISO, Sex, Age_Group) ONCE, and use each stratum's row index as its seed key.
# The sort must not depend on locale: Age_Group is a character label whose
# lexical order differs from its numeric order, and a locale-sensitive
# collation would silently reshuffle the keys on another machine. Both are
# pinned below.
stopifnot(setequal(unique(lancet_dia_with_dist$Age_Group), AGE_GROUP_LEVELS))

lancet_dia_with_dist <- lancet_dia_with_dist %>%
  arrange(ISO, Sex, match(Age_Group, AGE_GROUP_LEVELS)) %>%
  mutate(stratum_index = row_number())

# The cap is applied AFTER stratum_index is assigned, so a smoke run's strata
# carry the same seeds they would in a full run and its numbers are directly
# comparable to the corresponding slice of one.
if (SMOKE) {
  lancet_dia_with_dist <- head(lancet_dia_with_dist, MAX_STRATA)
}

cat(sprintf("\nStrata: %d  (seeds %d..%d)\n", nrow(lancet_dia_with_dist),
            GLOBAL_SEED + 1L, GLOBAL_SEED + nrow(lancet_dia_with_dist)))
stopifnot(GLOBAL_SEED + nrow(lancet_dia_with_dist) < SCENARIO_OFFSET)

##########################################
#####   GATE G1 -- CDF exactness      ####
##########################################
# Deterministic. For every stratum, evaluate the fitted CDF at the ten band
# boundaries and confirm it returns the input cumulative shares to machine
# precision. No sampling noise, no bar to calibrate, no multiple-comparisons
# problem: it either equals the input or it does not. The three tail knots are
# where a conditional-versus-absolute confusion would show up.
cat("\n---- G1 CDF exactness (deterministic) ----\n")
G1_EVAL_AT <- c(18.5, 20, 25, 30, 35, 40, 45, 50, 55, 60)

g1_max_err <- 0
g1_worst   <- NA_character_
for (i in seq_len(nrow(lancet_dia_with_dist))) {
  d  <- lancet_dia_with_dist$bmi_distribution[[i]]
  pr <- d$original_props
  p40 <- pr[7]
  want <- c(cumsum(pr)[1:6], 1 - p40 * CLASS3_TAIL, 1)
  got  <- approx(d$x, d$cdf, G1_EVAL_AT, rule = 2)$y
  e <- max(abs(got - want))
  if (e > g1_max_err) {
    g1_max_err <- e
    g1_worst <- lancet_dia_with_dist$.stratum_label[i]
  }
}
cat(sprintf("  strata checked      : %d\n", nrow(lancet_dia_with_dist)))
cat(sprintf("  knots per stratum   : %d\n", length(G1_EVAL_AT)))
cat(sprintf("  max abs deviation   : %.3e  (worst stratum %s)\n",
            g1_max_err, g1_worst))
if (g1_max_err > 1e-12) {
  stop(sprintf("G1 FAILED: max CDF deviation %.3e exceeds machine precision.",
               g1_max_err))
}
cat("G1 PASS\n")

##########################################
#####   GATE G0 -- bar calibration    ####
##########################################
# Computed from the ACTUAL stratum populations, BEFORE the run, so G2's bar is
# declared rather than negotiated afterwards.
#   SE = sqrt( p(1-p) * sum_s P_s^2 / ( n_individuals * (sum_s P_s)^2 ) )
cat("\n---- G0 bar calibration (before the run) ----\n")
.P <- lancet_dia_with_dist$Population
.p_ge30 <- sum(.P * (lancet_dia_with_dist$BMI_30to35 +
                     lancet_dia_with_dist$BMI_35to40 +
                     lancet_dia_with_dist$BMI_over_40)) / sum(.P)
G0_SE <- sqrt(.p_ge30 * (1 - .p_ge30) * sum(.P^2) /
              (N_INDIVIDUALS * sum(.P)^2))
G2_BAR_POOLED <- 3 * G0_SE
cat(sprintf("  target pop-weighted BMI >= 30 share : %.6f\n", .p_ge30))
cat(sprintf("  total modelled population           : %.0f\n", sum(.P)))
cat(sprintf("  analytic Monte Carlo SE             : %.6f pp\n", G0_SE * 100))
cat(sprintf("  G2 pooled bar (3 SE)                : %.6f pp\n", G2_BAR_POOLED * 100))
cat(sprintf("  G2 Japan/Korea bar (declared)       : 0.500000 pp\n"))
saveRDS(list(se = G0_SE, bar = G2_BAR_POOLED, target_p = .p_ge30,
             total_pop = sum(.P), n_individuals = N_INDIVIDUALS),
        file.path(DIAG_DIR, "g0_calibration.rds"))
rm(.P, .p_ge30)

# Run full simulation
stage_time("inputs, CDF construction and pre-run gates done")
cat("\n---- running simulation ----\n")
full_results <- lancet_dia_with_dist %>%
  run_simulation_in_batches(batch_size = BATCH_SIZE,
                            n_individuals = N_INDIVIDUALS) %>%
  group_by(ISO, Sex, Age_Group) %>%
  mutate(
    weighting = Population / n()
  ) %>%
  ungroup()

stage_time("simulation done")

#Add a column that specifies Type 1 or Type 2 diabetes
#With 90% of individuals assigned to Type 2
#
# sec 2.11 -- documented, not fixed. diabetes_type is drawn as 10% of whoever
# was flagged diabetic, and diabetic status was assigned with a BMI-graded
# relative risk, so the model gives type 1 a BMI gradient it should not have.
# Direction is conservative, magnitude is small. DO NOT FIX.
#
# Seeded explicitly: this draw sits outside simulate_single_population(), so the
# per-stratum seeds do not cover it.
set.seed(GLOBAL_SEED + SCENARIO_OFFSET - 1L)
full_results <- full_results %>%
  mutate(diabetes_type = case_when(
    diabetes == 1 ~ if_else(runif(n()) <= 0.1, 1, 2),
    TRUE ~ NA_real_
  ))




####################################
#########   INTERVENTION  ##########
####################################


# sec 2.9 -- COMMON RANDOM NUMBERS. Drawn ONCE, outside both scenario calls.
#
# run_treatment_scenario() used to be called twice with independent rbinom and
# rnorm draws, so moderate-uptake adherers were not a subset of maximum-uptake
# adherers, and an individual adhering in both received a DIFFERENT
# individual_effect in each. The max-vs-moderate contrast therefore carried
# sampling noise on top of the adherence-rate difference.
#
# qualifies_for_treatment already depends only on age, diabetes_type and bmi,
# all fixed across scenarios, so eligibility is identical either way. Only
# adherence differs, and under CRN the moderate set is a strict subset of the
# maximum set. G4 tests this exactly.
#
# This is its own flagged change in the reconciliation table: it moves the
# moderate-uptake numbers independently of the defect fixes.
set.seed(GLOBAL_SEED + SCENARIO_OFFSET)
.n_rows  <- nrow(full_results)
u_adhere <- runif(.n_rows)
effect   <- rnorm(.n_rows, mean = 0.118, sd = 0.06)

# sec 2.12 -- the SD of 0.118/0.06 is kept and no sensitivity is run.
# eer_diff = 10 * pal * weight * individual_effect and individual_effect is
# drawn independently of pal and weight, so the mean food saving depends only on
# the mean (0.118), not the SD. The SD cannot move the numerator. It does reach
# the survivor denominator, because new_bmi = bmi * (1 - effect) feeds a step
# function, so E[HR(new_bmi)] depends on the spread. Decided: keep 0.06.

# Function to run the treatment simulation with a specified adherence rate
run_treatment_scenario <- function(data, adherence_rate, scenario_name) {
  stopifnot(nrow(data) == length(u_adhere))
  data %>%
    mutate(
      scenario = scenario_name,

      qualifies_for_treatment = case_when(
        age >= 75 ~ FALSE,  # Add age restriction from methods
        diabetes_type == 1 ~ FALSE,  #Type 1 diabetes not eligible
        bmi >= 30 ~ TRUE,   #high bmi eligible
        bmi >= 27 & bmi < 30 & diabetes == 1 & diabetes_type == 2 ~ TRUE,
        TRUE ~ FALSE
      ),

      # Adherence, from the shared uniform draw. An individual adheres in the
      # moderate scenario only if they adhere in the maximum one, because
      # 0.50 < 0.95 and the same u is compared against both.
      adheres_to_treatment = qualifies_for_treatment & (u_adhere < adherence_rate),

      # Individual treatment effect, from the shared normal draw.
      # Semaglutide is expected to reduce weight by 11.8%. There is no floor:
      # simulated individuals can gain weight, and about 2.5% of adherers do.
      individual_effect = if_else(adheres_to_treatment, effect, 0),

      treatment_weight = case_when(
        adheres_to_treatment ~ weight * (1 - individual_effect),
        TRUE ~ weight
      ),

      # sec 2.5 -- PAL is NOT redrawn from the post-treatment BMI category. This
      # is not an oversight. The intervention being modelled is weight loss
      # WITHOUT a change in activity, which is the point of the drug; holding
      # pal fixed per individual IS the model of the intervention. No change.
      #
      # height_used, not height. sec 2.3.1: the height-independence identity
      # holds only if the same height appears in the weight construction, the
      # BMR term and new_bmi. G7 tests it exactly.
      treatment_bmr = case_when(
        Sex == "Men" ~ (10 * treatment_weight) + (6.25 * height_used) - (5 * age) + 5,
        Sex == "Women" ~ (10 * treatment_weight) + (6.25 * height_used) - (5 * age) - 161
      ),

      treatment_eer = treatment_bmr * pal,

      weight_diff = weight - treatment_weight,
      eer_diff = eer - treatment_eer,
      new_bmi = treatment_weight/(height_used/100)^2
    )
}

# Run both scenarios
#First scenario assumes maximum uptake where only those with negative side effects drop out
results_max_uptake <- run_treatment_scenario(full_results, 0.95, "max_uptake")
#Second scenario assumes uptake consistent with e.g. statins or ACE inhibitors where only half of those eligible actually persist with treatment
results_mod_uptake <- run_treatment_scenario(full_results, 0.50, "mod_uptake")

# Combine results for analysis
all_results <- bind_rows(results_max_uptake, results_mod_uptake)

##########################################
#####   GATE G4 -- adherence and CRN  ####
##########################################
cat("\n---- G4 adherence rates and CRN nesting ----\n")
.mx <- results_max_uptake
.md <- results_mod_uptake
stopifnot(identical(.mx$qualifies_for_treatment, .md$qualifies_for_treatment))
cat(sprintf("  eligibility identical across scenarios : TRUE\n"))
for (nm in c("max", "mod")) {
  d <- if (nm == "max") .mx else .md
  el <- sum(d$qualifies_for_treatment); ad <- sum(d$adheres_to_treatment)
  cat(sprintf("  %s: eligible %d  adhering %d  rate %.4f\n", nm, el, ad, ad / el))
}
# Strict subset.
.viol_subset <- sum(.md$adheres_to_treatment & !.mx$adheres_to_treatment)
cat(sprintf("  moderate adherers not in the maximum set : %d\n", .viol_subset))
# Identical effect for anyone adhering in both.
.both <- .mx$adheres_to_treatment & .md$adheres_to_treatment
.viol_effect <- sum(.mx$individual_effect[.both] != .md$individual_effect[.both])
cat(sprintf("  adherers in both with differing effect   : %d  (of %d)\n",
            .viol_effect, sum(.both)))
if (.viol_subset != 0 || .viol_effect != 0) stop("G4 FAILED: CRN nesting violated.")
# The realized adherence rate is a binomial proportion, so its bar has to be
# computed from the actual eligible count rather than fixed. 4 SE. At
# production n this is about +/- 0.0008 (max) and +/- 0.0018 (moderate).
.n_el     <- sum(.mx$qualifies_for_treatment)
.rate_mx  <- sum(.mx$adheres_to_treatment) / .n_el
.rate_md  <- sum(.md$adheres_to_treatment) / .n_el
.bar_mx   <- 4 * sqrt(0.95 * 0.05 / .n_el)
.bar_md   <- 4 * sqrt(0.50 * 0.50 / .n_el)
cat(sprintf("  eligible n = %d;  4-SE bars: max +/-%.5f  mod +/-%.5f\n",
            .n_el, .bar_mx, .bar_md))
cat(sprintf("  deviation from nominal: max %+.5f (%.2f SE)  mod %+.5f (%.2f SE)\n",
            .rate_mx - 0.95, abs(.rate_mx - 0.95) / (.bar_mx / 4),
            .rate_md - 0.50, abs(.rate_md - 0.50) / (.bar_md / 4)))
if (abs(.rate_mx - 0.95) > .bar_mx || abs(.rate_md - 0.50) > .bar_md) {
  stop("G4 FAILED: an adherence rate is more than 4 binomial SE from nominal.")
}
cat("G4 PASS\n")
rm(.mx, .md, .both, .viol_subset, .viol_effect, .rate_mx, .rate_md,
   .n_el, .bar_mx, .bar_md)





##########################################
#####  GATE G6 -- NA leakage / joins  ####
##########################################
# A failed join on Diabetes_prevalence gives rbinom(n, 1, NA) -> NA, so
# diabetes_type is NA, the eligibility case_when falls through, and the
# individual is silently treated as a non-diabetic. No error, wrong answer.
# Three country-naming conventions are in play with recodes applied at different
# points (Czechia / North Macedonia before the height join; Korea / Taiwan only
# before the population join), so this is checked as a JOIN-COMPLETENESS check
# broken out by country, not just an NA tally.
cat("\n---- G6 NA leakage and join completeness ----\n")
.g6_cols <- c("weighting", "Population", "bmi", "height", "height_used", "age",
              "pal", "bmr", "eer", "diabetes_prob", "eer_diff", "new_bmi")
.g6 <- sapply(.g6_cols, function(cc) sum(is.na(all_results[[cc]])))
print(data.frame(column = names(.g6), n_na = as.integer(.g6), row.names = NULL))

cat("\n  post-join NA by country, at each join site:\n")
# Checked on the MODELLED set only. bmi_join covers all ~200 countries in the
# NCD-RisC file and the income filter comes later, so an unmatched height for a
# country that is never simulated is not a defect. lancet_high is the first
# frame restricted to the high-income set.
.join_report <- function(df, cols, label) {
  bad <- df %>%
    filter(if_any(all_of(cols), is.na)) %>%
    count(Country, name = "n_rows")
  cat(sprintf("    %-28s strata with NA: %d\n", label, sum(bad$n_rows)))
  if (nrow(bad) > 0) print(as.data.frame(bad))
  sum(bad$n_rows)
}
.b1 <- .join_report(lancet_high, c("Mean_height"),          "height join (high-income)")
.b2 <- .join_report(lancet_pop,  c("Population"),           "population join")
.b3 <- .join_report(lancet_dia,  c("Diabetes_prevalence"),  "diabetes join")
if (any(.g6 > 0) || .b1 + .b2 + .b3 > 0) {
  stop("G6 FAILED: NA present in a modelled column or an incomplete join.")
}
cat("G6 PASS\n")

##########################################
#####  GATE G8 -- country universe    ####
##########################################
# sec 2.13 -- the R simulation keeps the full 63-country high-income set. The
# restriction to the analysis countries is a SINGLE named filter applied once in
# the Python pipeline, not here. Restricting here would add a confound to the
# reconciliation table, make a country lost to a name mismatch invisible, and
# break the ASM/CAN diagnostic plot below.
cat("\n---- G8 country universe entering the simulation ----\n")
.iso <- sort(unique(all_results$ISO))
cat(sprintf("  countries: %d\n", length(.iso)))
cat(sprintf("  ISO list : %s\n", paste(.iso, collapse = " ")))
if (SMOKE) {
  cat("G8 SKIPPED (smoke run -- strata capped, country set truncated by construction)\n")
} else if (length(.iso) != 63) {
  stop(sprintf("G8 FAILED: %d countries, expected 63.", length(.iso)))
} else {
  cat("G8 PASS\n")
}

# Realized top-band mean BMI. REPORTED, NOT GATED (sec 2.1.2): this is the only
# check that the tail knots actually reach the sampler -- G1 tests the CDF
# object and G2 tests only the >= 30 threshold. Once G1 passes, a
# sampled-composition gate would test approx() and runif() rather than the
# construction, and calibrating its bar costs more than the number is worth.
.base <- all_results %>% filter(scenario == "max_uptake")
.top  <- .base %>% filter(bmi >= 40)
cat(sprintf("\n  realized top-band mean BMI (pop-weighted): %.4f   [target 44.4343]\n",
            weighted.mean(.top$bmi, .top$weighting)))
cat(sprintf("  realized top-band mean BMI (unweighted)  : %.4f\n", mean(.top$bmi)))
cat(sprintf("  max realized bmi / new_bmi               : %.4f / %.4f\n",
            max(.base$bmi), max(all_results$new_bmi)))

# Population-weighted mean height loss applied, by sex -- a Phase 5 diagnostic
# row, computed here where both heights are in scope.
cat("\n  mean height loss applied (pop-weighted), by sex:\n")
print(as.data.frame(.base %>%
  group_by(Sex) %>%
  summarise(mean_loss_cm = weighted.mean(height - height_used, weighting),
            .groups = "drop")))
rm(.base, .top, .iso, .g6, .b1, .b2, .b3)

# Save results.
# sec 2.7 -- ONE path constant, used at the save site and at the load site
# below, so the two cannot diverge again.
if (SMOKE) {
  cat("\nSMOKE RUN -- OUT_RDS deliberately NOT written.\n")
} else {
  cat(sprintf("\nWriting %s\n", OUT_RDS))
  dir.create(dirname(OUT_RDS), showWarnings = FALSE, recursive = TRUE)
  saveRDS(all_results, OUT_RDS)
}

##### VARIOUS CHECKS #####

#Check list of countries
countries<-all_results %>% select(ISO) %>% distinct()

print(countries)

# Check adherence rates by scenario
# sec 2.6 -- these two filters used to read "Maximum uptake" / "Moderate
# uptake" while the scenario column was assigned "max_uptake" / "mod_uptake" at
# the two calls above. The strings never matched, both subsets were empty, and
# every adherence rate this block printed was NaN. Fixed by matching the FILTERS
# to the assigned values, not the other way round: the production .rds and the
# whole Python pipeline key on max_uptake / mod_uptake, so changing the
# assignments would break every downstream consumer.
max_uptake_data <- all_results[all_results$scenario == "max_uptake", ]
mod_uptake_data <- all_results[all_results$scenario == "mod_uptake", ]

# Calculate adherence rates
max_eligible <- sum(max_uptake_data$qualifies_for_treatment)
max_adheres <- sum(max_uptake_data$adheres_to_treatment)
max_rate <- max_adheres / max_eligible

mod_eligible <- sum(mod_uptake_data$qualifies_for_treatment)
mod_adheres <- sum(mod_uptake_data$adheres_to_treatment)
mod_rate <- mod_adheres / mod_eligible

# Print results
cat("Maximum uptake scenario:\n")
cat("- Eligible individuals:", max_eligible, "\n")
cat("- Adhering individuals:", max_adheres, "\n")
cat("- Adherence rate:", round(max_rate * 100, 1), "%\n\n")

cat("Moderate uptake scenario:\n")
cat("- Eligible individuals:", mod_eligible, "\n")
cat("- Adhering individuals:", mod_adheres, "\n")
cat("- Adherence rate:", round(mod_rate * 100, 1), "%\n")

# Additional useful metrics
cat("\nMean weight loss for those on treatment:\n")
cat("- Maximum scenario:", 
    round(mean(max_uptake_data$individual_effect[max_uptake_data$adheres_to_treatment] * 100, na.rm = TRUE), 1), 
    "%\n")
cat("- Moderate scenario:", 
    round(mean(mod_uptake_data$individual_effect[mod_uptake_data$adheres_to_treatment] * 100, na.rm = TRUE), 1), 
    "%\n")




####################################
#########   VISUALIZATION  #########
####################################

# Rscript's default device drops an Rplots.pdf in the working directory.
# Send it somewhere deliberate instead.
pdf(file.path(DIAG_DIR, "data_cleaning_plots.pdf"), width = 8, height = 6)

#Load simulated population.
# Same OUT_RDS constant as the save site. This used to be a bare filename
# resolved against whatever the working directory happened to be, 50 lines and
# an interactive setwd() away from the save -- which is how every diagnostic
# below spent the life of the model describing a different file from the one the
# script had just produced.
full_results <- if (SMOKE) all_results else readRDS(OUT_RDS)


library(tidyr)
library(scales)

# Create BMI distribution comparison plot
bmi_categories <- c("<18.5", "18.5-20", "20-25", "25-30", "30-35", "35-40", ">= 40")

# Create BMI categories based on continuous BMI values
full_results$bmi_cat <- cut(full_results$bmi, 
                            breaks = c(0, 18.5, 20, 25, 30, 35, 40, Inf),
                            labels = c("<18.5", "18.5-20", "20-25", "25-30", "30-35", "35-40", ">= 40"))


# Create factors for proper ordering
full_results$bmi_cat <- factor(full_results$bmi_cat, levels = bmi_categories)

# sec 2.10 -- every block below used to operate on the COMBINED object without
# filtering `scenario`, silently pooling max and moderate uptake. Each now
# filters and emits per-scenario output. SCENARIOS drives them all so a new
# scenario cannot be added and quietly missed by one block.
SCENARIOS <- c("max_uptake", "mod_uptake")

# Create long format data for BMI comparison
bmi_comparison <- full_results %>%
  select(scenario, bmi, new_bmi, weighting) %>%
  pivot_longer(cols = c(bmi, new_bmi),
               names_to = "measurement",
               values_to = "bmi_value") %>%
  mutate(measurement = ifelse(measurement == "bmi", "Initial BMI", "Post-Treatment BMI"))

# Create BMI distribution plot (this part worked fine but let's enhance it)
ggplot(bmi_comparison, aes(x = bmi_value, weight = weighting, fill = measurement)) +
  geom_density(alpha = 0.5, position = "identity") +
  facet_wrap(~scenario, ncol = 1) +
  scale_fill_brewer(palette = "Set2") +
  labs(title = "Population-Weighted BMI Distribution Before and After Treatment",
       x = "BMI (kg/m²)",
       y = "Density",
       fill = "Measurement") +
  theme_minimal() +
  theme(legend.position = "bottom",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9)) +
  scale_x_continuous(limits = c(15, 50))

# Calculate and plot national totals for EER difference
eer_national <- full_results %>%
  group_by(scenario, ISO) %>%
  summarise(
    total_eer_diff = sum(eer_diff * weighting * 365.25 / 1e9),  # Convert to billion kcal per year
    .groups = "drop"
  ) %>%
  arrange(scenario, desc(total_eer_diff))

cat("\n---- eer_national, per scenario (top 10) ----\n")
for (s in SCENARIOS) {
  cat(sprintf("  %s:\n", s))
  print(as.data.frame(head(eer_national[eer_national$scenario == s, ], 10)))
}

ggplot(eer_national, aes(x = reorder(ISO, total_eer_diff), y = total_eer_diff)) +
  geom_col(fill = "#69b3a2") +
  facet_wrap(~scenario, ncol = 1, scales = "free_y") +
  labs(title = "Annual Energy Requirement Reduction",
       subtitle = "After Treatment Implementation",
       x = "Country",
       y = "Reduction in Energy Requirements\n(billion kcal/year)") +
  theme_minimal() +
  theme(plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9),
        axis.text.x = element_text(angle = 90)) +
  scale_y_continuous(labels = comma)

# Calculate and plot national totals for weight difference
weight_national <- full_results %>%
  group_by(scenario, ISO) %>%
  summarise(
    total_weight_diff = sum(weight_diff * weighting / 1e6),  # Convert to million kg
    .groups = "drop"
  ) %>%
  arrange(scenario, desc(total_weight_diff))

cat("\n---- weight_national, per scenario (top 10) ----\n")
for (s in SCENARIOS) {
  cat(sprintf("  %s:\n", s))
  print(as.data.frame(head(weight_national[weight_national$scenario == s, ], 10)))
}

ggplot(weight_national, aes(x = reorder(ISO, total_weight_diff), y = total_weight_diff)) +
  geom_col(fill = "#404080") +
  facet_wrap(~scenario, ncol = 1, scales = "free_y") +
  labs(title = "Total National Weight Reduction",
       subtitle = "After Treatment Implementation",
       x = "Country",
       y = "Weight Reduction (million kg)") +
  theme_minimal() +
  theme(plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9),
        axis.text.x = element_text(angle = 90)) +
  scale_y_continuous(labels = comma)


# Country-specific diagnostic plots, guarded.
#
# A facetted plot on an absent country aborts the script inside ggplot's
# combine_vars() -- and it does so AFTER the .rds has been written and BEFORE
# the G2 and diabetes diagnostics below, so a missing country would cost the run
# its verification rather than just its picture. `p` is lazily evaluated, so an
# absent country never builds the plot at all.
show_plot <- function(isos, p) {
  have <- intersect(isos, unique(full_results$ISO))
  if (length(have) != length(isos)) {
    cat(sprintf("  plot skipped -- absent ISO: %s\n",
                paste(setdiff(isos, have), collapse = ", ")))
    return(invisible(NULL))
  }
  print(p)
  invisible(NULL)
}

# Korean age vs weight plot
show_plot(c("KOR"), full_results %>%
  filter(ISO == "KOR", scenario == "max_uptake") %>%
  ggplot(aes(x = age, y = bmi, color = Sex)) +
  geom_point(alpha = 0.4) +
  scale_color_brewer(palette = "Set1") +
  labs(title = "Age vs BMI Distribution in Korea",
       x = "Age (years)",
       y = "BMI") +
  theme_minimal() +
  theme(legend.position = "right",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9)))

# US height vs weight plot
show_plot(c("USA"), full_results %>%
  filter(ISO == "USA", scenario == "max_uptake") %>%
  ggplot(aes(x = height, y = weight, color = factor(diabetes))) +
  geom_point(alpha = 0.4) +
  scale_color_manual(values = c("0" = "#69b3a2", "1" = "#e15759"),
                     labels = c("No Diabetes", "Diabetes"),
                     name = "Diabetes Status") +
  labs(title = "Height vs Weight Distribution in United States",
       x = "Height (cm)",
       y = "Weight (kg)") +
  theme_minimal() +
  theme(legend.position = "right",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9)))


# Norway EER comparison plot
# sec 2.10, same defect as the four listed blocks: this plots
# treatment-dependent quantities and used to pool both scenarios.
show_plot(c("NOR"), full_results %>%
  filter(ISO == "NOR", scenario == "max_uptake") %>%
  ggplot(aes(x = eer, y = treatment_eer)) +
  geom_point(alpha = 0.4, size = 1) +
  geom_abline(linetype = "dashed", color = "red", alpha = 0.5) +  # Add y=x reference line
  labs(title = "Energy Expenditure Requirements Before vs After Treatment in Norway",
       x = "Initial EER (kcal/day)",
       y = "Post-Treatment EER (kcal/day)") +
  theme_minimal() +
  theme(plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9)))



# BMI vs EER difference plot with faceting
show_plot(c("JPN", "CAN"), full_results %>%
  filter(ISO %in% c("JPN", "CAN"), scenario == "max_uptake") %>%
  ggplot(aes(x = bmi, y = eer_diff, color = factor(diabetes))) +
  geom_point(alpha = 0.4, size = 1) +
  scale_color_manual(values = c("0" = "#69b3a2", "1" = "#e15759"),
                     labels = c("No Diabetes", "Diabetes"),
                     name = "Diabetes Status") +
  labs(title = "BMI vs Change in Energy Expenditure Requirements",
       x = "BMI (kg/m²)",
       y = "Change in EER (kcal/day)") +
  facet_wrap(~ISO, ncol = 2, 
             labeller = labeller(ISO = c("JPN" = "Japan", "CAN" = "Canada"))) +
  theme_minimal() +
  theme(legend.position = "right",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9),
        strip.text = element_text(size = 10, face = "bold")))



# BMI vs EER difference plot with faceting
show_plot(c("ASM", "CAN"), full_results %>%
  filter(ISO %in% c("ASM", "CAN"), scenario == "max_uptake") %>%
  ggplot(aes(x = bmi, y = eer_diff, color = factor(diabetes))) +
  geom_point(alpha = 0.4, size = 1) +
  scale_color_manual(values = c("0" = "#69b3a2", "1" = "#e15759"),
                     labels = c("No Diabetes", "Diabetes"),
                     name = "Diabetes Status") +
  labs(title = "BMI vs Change in Energy Expenditure Requirements",
       x = "BMI (kg/m²)",
       y = "Change in EER (kcal/day)") +
  facet_wrap(~ISO, ncol = 2, 
             labeller = labeller(ISO = c("ASM" = "American Samoa", "CAN" = "Canada"))) +
  theme_minimal() +
  theme(legend.position = "right",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9),
        strip.text = element_text(size = 10, face = "bold")))


#Create table summarizing results
#
# sec 2.10 -- this block had a second and worse problem than the missing
# scenario filter: IT WAS UNWEIGHTED. It is the source of the ~7% figure in the
# manuscript discussion. mean(eer_diff / eer * 100) carries no `weighting`, so
# every stratum contributed exactly 500 rows regardless of whether it represents
# Nauru or the United States. The percentage reduction rises with body weight,
# so small high-BMI populations were massively over-represented -- and the
# manuscript then paired that simulation-sample mean with a population-weighted
# survivor statistic.
#
# n_treated was likewise n(), a count of SIMULATED ROWS, not people.
#
# Both the weighted and the old unweighted values are emitted, because the
# unweighted one is what the current manuscript text quotes and Phase 5 has to
# reconcile against it.
weighted_quantile <- function(x, w, probs) {
  o <- order(x); x <- x[o]; w <- w[o]
  cw <- cumsum(w) / sum(w)
  approx(cw, x, probs, rule = 2, ties = "ordered")$y
}
weighted_sd <- function(x, w) {
  m <- weighted.mean(x, w)
  sqrt(sum(w * (x - m)^2) / sum(w))
}

eer_effects <- full_results %>%
  filter(adheres_to_treatment == TRUE) %>%
  group_by(scenario) %>%
  summarise(
    n_treated                     = sum(weighting),
    n_rows_unweighted             = n(),
    mean_eer_decrease             = weighted.mean(eer_diff, weighting),
    mean_eer_decrease_percent     = weighted.mean(eer_diff/eer * 100, weighting),
    sd_eer_decrease               = weighted_sd(eer_diff, weighting),
    sd_eer_decrease_percent       = weighted_sd(eer_diff/eer * 100, weighting),
    median_eer_decrease_percent   = weighted_quantile(eer_diff/eer * 100, weighting, 0.50),
    q25_eer_decrease_percent      = weighted_quantile(eer_diff/eer * 100, weighting, 0.25),
    q75_eer_decrease_percent      = weighted_quantile(eer_diff/eer * 100, weighting, 0.75),
    # The old, unweighted figure, retained solely for the Phase 5 reconciliation.
    OLD_unweighted_mean_eer_pct   = mean(eer_diff/eer * 100),
    .groups = "drop"
  )
cat("\n---- eer_effects, per scenario, POPULATION WEIGHTED ----\n")
print(as.data.frame(eer_effects))


#Check that our intervention worked
#
# NOT in the plan's four-item list, but it carries the same two defects and the
# plan's prose names mean_weight_decrease -- which lives here, not in
# eer_effects. See diagnostics/reports/phase0_recon.md 5.3.
#
# mean_weight_decrease_percent is deliberately left unweighted-equivalent: it
# reduces to mean(individual_effect) and weighting does not move it. It is
# computed weighted anyway for consistency; the two agree to rounding.
intervention_effects <- full_results %>%
  filter(adheres_to_treatment == TRUE) %>%
  group_by(scenario) %>%
  summarise(
    n_treated                      = sum(weighting),
    n_rows_unweighted              = n(),
    mean_weight_decrease           = weighted.mean(weight_diff, weighting),
    mean_weight_decrease_percent   = weighted.mean(weight_diff/weight * 100, weighting),
    sd_weight_decrease_percent     = weighted_sd(weight_diff/weight * 100, weighting),
    median_weight_decrease_percent = weighted_quantile(weight_diff/weight * 100, weighting, 0.50),
    q25_weight_decrease_percent    = weighted_quantile(weight_diff/weight * 100, weighting, 0.25),
    q75_weight_decrease_percent    = weighted_quantile(weight_diff/weight * 100, weighting, 0.75),
    OLD_unweighted_mean_weight_kg  = mean(weight_diff),
    .groups = "drop"
  )
cat("\n---- intervention_effects, per scenario, POPULATION WEIGHTED ----\n")
print(as.data.frame(intervention_effects))

# Eligible and treated population counts, weighted -- a Phase 5 row.
eligible_treated <- full_results %>%
  group_by(scenario, ISO) %>%
  summarise(
    pop_adult    = sum(weighting),
    pop_eligible = sum(weighting * qualifies_for_treatment),
    pop_treated  = sum(weighting * adheres_to_treatment),
    .groups = "drop"
  )
cat("\n---- eligible / treated population, totals ----\n")
print(as.data.frame(eligible_treated %>%
  group_by(scenario) %>%
  summarise(across(c(pop_adult, pop_eligible, pop_treated), sum), .groups = "drop")))
write.csv(eligible_treated,
          file.path(DIAG_DIR, "eligible_treated_by_country.csv"), row.names = FALSE)

# Analyze mean weight loss in treated sample
full_results %>%
  filter(adheres_to_treatment == TRUE) %>%
  ggplot(aes(x = weight_diff)) +
  geom_histogram(
    fill = "#2C3E50",
    color = "white",
    bins = 30
  ) +
  facet_wrap(~scenario, ncol = 1, scales = "free_y") +
  labs(
    title = "Weight Loss Among Treated Individuals",
    subtitle = "Unweighted Analysis",
    x = "Weight Difference (kg)",
    y = "Count"
  ) +
  clean_theme() +
  theme(
    plot.title = element_text(size = 14, face = "bold"),
    plot.subtitle = element_text(size = 12)
  )

##########################################
#####  GATE G2 -- sampled shares      ####
##########################################
# Bars declared by G0 BEFORE the run and not adjusted here.
cat("\n---- G2 sampled BMI category shares ----\n")
if (SMOKE) {
  cat("G2 SKIPPED (smoke run -- the pooled bar is calibrated on the full population)\n")
} else {
.g0 <- readRDS(file.path(DIAG_DIR, "g0_calibration.rds"))

.base <- full_results %>% filter(scenario == "max_uptake")
.target <- lancet_dia_with_dist %>%
  select(ISO, Sex, Age_Group, Population, all_of(BMI_SHARE_COLS)) %>%
  mutate(target_ge30 = BMI_30to35 + BMI_35to40 + BMI_over_40)

.realized <- .base %>%
  group_by(ISO, Sex, Age_Group) %>%
  summarise(realized_ge30 = mean(bmi >= 30),
            Population = first(Population), .groups = "drop")

.cmp <- left_join(.realized, .target %>% select(ISO, Sex, Age_Group, target_ge30),
                  by = c("ISO", "Sex", "Age_Group"))
stopifnot(!any(is.na(.cmp$target_ge30)))

.pooled_real <- weighted.mean(.cmp$realized_ge30, .cmp$Population)
.pooled_targ <- weighted.mean(.cmp$target_ge30,   .cmp$Population)
.pooled_diff <- .pooled_real - .pooled_targ
cat(sprintf("  pooled realized / target / diff : %.6f / %.6f / %+.6f pp\n",
            .pooled_real, .pooled_targ, .pooled_diff * 100))
cat(sprintf("  bar (3 SE from G0)              : %.6f pp\n", .g0$bar * 100))

.by_country <- .cmp %>%
  group_by(ISO) %>%
  summarise(realized = weighted.mean(realized_ge30, Population),
            target   = weighted.mean(target_ge30,   Population),
            .groups = "drop") %>%
  mutate(diff_pp = (realized - target) * 100)
cat("\n  worst ten countries by |diff_pp|:\n")
print(as.data.frame(head(.by_country[order(-abs(.by_country$diff_pp)), ], 10)))
cat("\n  Japan / Korea (declared bar 0.5 pp):\n")
print(as.data.frame(.by_country[.by_country$ISO %in% c("JPN", "KOR"), ]))
write.csv(.by_country, file.path(DIAG_DIR, "g2_bmi_ge30_by_country.csv"),
          row.names = FALSE)

.jk <- .by_country[.by_country$ISO %in% c("JPN", "KOR"), ]
.fail <- abs(.pooled_diff) * 100 > .g0$bar * 100 || any(abs(.jk$diff_pp) > 0.5)
if (.fail) {
  cat("\nG2 FAILED. Escalation per the plan: re-run a subset of strata at\n")
  cat("n_individuals = 5000 and check whether the deviation shrinks as 1/sqrt(n)\n")
  cat("BEFORE diagnosing further. Sampling noise shrinks; a construction bug does not.\n")
  stop("G2 FAILED.")
}
cat("G2 PASS\n")
}

##########################################
#####  sec 2.11 -- diabetes, REPORT ONLY #
##########################################
# The mortality model does not consume diabetes status: the hazard ladder is a
# pure step function of BMI, and diabetes / diabetes_type appear in no hazard
# computation anywhere in the pipeline. The clipping at pmin(pmax(p, 0), 1)
# therefore reaches results only through eligibility, and both channels are
# inert: the 27-30 + T2D pathway sits at BMI < 30 where the clip never binds,
# and where the clip does bind those individuals qualify via bmi >= 30 anyway.
# Report realized vs target prevalence, confirm eligibility impact is nil, close
# the item. No code change.
cat("\n---- 2.11 diabetes realized vs target prevalence ----\n")
.base <- full_results %>% filter(scenario == "max_uptake")
.dia <- .base %>%
  group_by(ISO, Sex, Age_Group) %>%
  summarise(realized_prev = mean(diabetes),
            n_clipped     = sum(diabetes_prob >= 1 - 1e-12),
            Population    = first(Population), .groups = "drop")
.dia <- left_join(
  .dia,
  lancet_dia_with_dist %>% select(ISO, Sex, Age_Group, Diabetes_prevalence),
  by = c("ISO", "Sex", "Age_Group")
) %>% rename(target_prev = Diabetes_prevalence)
cat(sprintf("  pop-weighted realized / target : %.6f / %.6f  (diff %+.6f pp)\n",
            weighted.mean(.dia$realized_prev, .dia$Population),
            weighted.mean(.dia$target_prev,   .dia$Population),
            (weighted.mean(.dia$realized_prev, .dia$Population) -
             weighted.mean(.dia$target_prev,   .dia$Population)) * 100))
cat(sprintf("  strata with any clipped probability : %d of %d\n",
            sum(.dia$n_clipped > 0), nrow(.dia)))
cat(sprintf("  individuals with a clipped probability : %d\n", sum(.dia$n_clipped)))
# Eligibility impact of the clip: anyone whose probability was clipped has BMI
# in the 40s and qualifies via bmi >= 30 regardless.
.clipped_rows <- .base %>% filter(diabetes_prob >= 1 - 1e-12)
cat(sprintf("  of those, share with bmi >= 30 (qualify regardless) : %s\n",
            if (nrow(.clipped_rows) == 0) "n/a (none)"
            else sprintf("%.6f", mean(.clipped_rows$bmi >= 30))))
write.csv(.dia, file.path(DIAG_DIR, "diabetes_realized_vs_target.csv"),
          row.names = FALSE)

rm(list = intersect(c(".g0", ".base", ".target", ".realized", ".cmp",
                      ".by_country", ".jk", ".fail", ".dia", ".clipped_rows",
                      ".pooled_real", ".pooled_targ", ".pooled_diff"),
                    ls(all.names = TRUE)))

try(dev.off(), silent = TRUE)
stage_time("all done")
cat("\n==== Data_Cleaning9.8.R complete ====\n")
