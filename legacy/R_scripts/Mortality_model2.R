
#Increase memory limit (Windows only)
if (.Platform$OS.type == "windows") {
  memory.limit(size = 32000)  # 32 GB
}

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

#Load simulated population
full_results <- readRDS("test/full_simulation_results8.rds")
#full_results <- readRDS("test/full_simulation_results6.rds")



str(full_results)

#Load death rates from HMD
#https://www.mortality.org/Data/ZippedDataFiles
#"C:\Users\sethw\OneDrive - University of Waterloo\Semaglutide\Data Analysis\HLD\Mx_1x1"



# Set the working directory to the folder containing the files
path <- "HLD/Mx_1x1"

# Get list of all Mx_1x1.txt files
files <- list.files(path = path, 
                    pattern = ".*\\.Mx_1x1\\.txt$", 
                    full.names = TRUE)

# Function to read each file and add ISO code
read_country_file <- function(file_path) {
  tryCatch({
    # Extract ISO code from filename
    ISO <- str_extract(basename(file_path), "^[A-Z_]+")
    
    # Read all lines
    lines <- readLines(file_path, warn = FALSE)
    
    # Find the line that starts with "Year" (this is our header)
    header_row <- which(grepl("^\\s*Year\\s+Age\\s+", lines))
    
    if(length(header_row) == 0) {
      warning(paste("No header found in file:", file_path))
      return(NULL)
    }
    
    # Get the data rows
    data_lines <- lines[header_row:length(lines)]
    
    # Write to a temporary file
    temp_file <- tempfile()
    writeLines(data_lines, temp_file)
    
    # Read the temporary file
    df <- read.table(temp_file, 
                     header = TRUE,
                     sep = "",
                     check.names = TRUE,
                     stringsAsFactors = FALSE,
                     fill = TRUE)
    
    # Clean column names
    names(df) <- c("Year", "Age", "Female", "Male", "Total")
    
    # Add ISO column
    df$ISO <- ISO
    
    # Remove temporary file
    unlink(temp_file)
    
    # Convert columns to appropriate types
    df <- df %>%
      mutate(
        Year = as.numeric(Year),
        Age = as.numeric(Age),
        Female = as.numeric(Female),
        Male = as.numeric(Male),
        Total = as.numeric(Total)
      )
    
    return(df)
    
  }, error = function(e) {
    warning(paste("Error processing file:", file_path, "\nError:", e$message))
    return(NULL)
  })
}

# Read and combine all files
mortality_df <- bind_rows(
  lapply(files, function(f) {
    result <- read_country_file(f)
    if(!is.null(result)) return(result)
  })
)

# Transform the data:
# 1. Keep only latest year for each country
# 2. Convert to long format for Sex
mortality_df_transformed <- mortality_df %>%
  # Group by ISO and get the latest year
  group_by(ISO) %>%
  filter(Year == max(Year)) %>%
  ungroup() %>%
  # Convert to long format
  pivot_longer(
    cols = c(Female, Male),
    names_to = "Sex",
    values_to = "mortality_rate"
  ) %>%
  # Recode sex to match demographic data
  mutate(
    Sex = case_when(
      Sex == "Female" ~ "Women",
      Sex == "Male" ~ "Men",
      TRUE ~ Sex
    )
  ) %>%
  # Select only needed columns
  select(ISO, Age, Sex, mortality_rate, Year)

#Some mortality data is available for countries with territorial issues
#Keep only rows for total populations
mortality2 <- mortality_df_transformed %>% 
  filter(!ISO %in% c("FRACNP", "NZL_MA", "NZL_NM",
                     "DEUTE", "DEUTW", "GBRTENW",
                     "GBRCENW", "GBR_SCO", "GBR_NIR"))

check <- mortality2 %>% select(ISO) %>% distinct()

#Keep only the first 3 letters in ISO
mortality2$ISO <- substr(mortality2$ISO, 1, 3)

# Print summary of the transformed data
cat("Number of countries:", length(unique(mortality_df_transformed$ISO)), "\n")
cat("Year range:", min(mortality_df_transformed$Year), "to", max(mortality_df_transformed$Year), "\n")
print(head(mortality_df_transformed))

# Join with demographic data
final_df <- full_results %>%
  left_join(
    mortality2,
    by = c("ISO", "age" = "Age", "Sex")
  )

# Check for any missing matches
missing_matches <- final_df %>%
  filter(is.na(mortality_rate)) %>%
  distinct(ISO, age, Sex) %>%
  arrange(ISO, age, Sex)

# Print summary of the final joined data
cat("\nFinal dataset summary:\n")
cat("Total rows:", nrow(final_df), "\n")
cat("Countries with missing mortality data:\n")
print(unique(missing_matches$ISO))

# Optional: Save the final dataset
# write.csv(final_df, "combined_demographic_mortality_data.csv", row.names = FALSE)



############################################
##########  IMPUTE MISSING DATA  ###########
############################################


# Get country classifications
country_info <- data.frame(
  ISO = countrycode::codelist$iso3c,
  region = countrycode::codelist$region,
  continent = countrycode::codelist$continent
) %>%
  filter(!is.na(ISO))

# Add World Bank income data
library(WDI)
wb_income <- WDI(indicator = "NY.GNP.PCAP.CD", start = 2020, end = 2020) %>%
  select(iso3c, NY.GNP.PCAP.CD) %>%
  rename(ISO = iso3c, income = NY.GNP.PCAP.CD)

# Combine country info datasets
country_info <- country_info %>%
  left_join(wb_income, by = "ISO")

# Get list of missing countries and their regions
missing_countries <- unique(missing_matches$ISO)
missing_regions <- country_info %>%
  filter(ISO %in% missing_countries) %>%
  select(region) %>%
  distinct()

# Create lookup table of mortality rates by region and income
mortality_lookup <- final_df %>%
  filter(!is.na(mortality_rate)) %>%
  inner_join(country_info, by = "ISO") %>%
  inner_join(missing_regions, by = "region") %>%
  group_by(region, income, age, Sex) %>%
  summarise(
    mortality_rate_income = median(mortality_rate, na.rm = TRUE),
    n_countries = n(),
    .groups = 'drop'
  )

# Create backup regional medians (without income matching)
regional_backup <- final_df %>%
  filter(!is.na(mortality_rate)) %>%
  inner_join(country_info, by = "ISO") %>%
  inner_join(missing_regions, by = "region") %>%
  group_by(region, age, Sex) %>%
  summarise(
    mortality_rate_region = median(mortality_rate, na.rm = TRUE),
    .groups = 'drop'
  )

# Apply first round of imputations
final_df_imputed <- final_df %>%
  left_join(country_info %>% select(ISO, region, income), by = "ISO") %>%
  left_join(
    mortality_lookup,
    by = c("region", "income", "age", "Sex")
  ) %>%
  left_join(
    regional_backup,
    by = c("region", "age", "Sex")
  ) %>%
  mutate(
    mortality_rate = case_when(
      !is.na(mortality_rate) ~ mortality_rate,
      !is.na(mortality_rate_income) ~ mortality_rate_income,
      !is.na(mortality_rate_region) ~ mortality_rate_region,
      TRUE ~ NA_real_
    )
  ) %>%
  select(-mortality_rate_income, -mortality_rate_region, -n_countries, -region, -income)

# Handle Seychelles separately using income-based approach
# First get Seychelles' income
seychelles_income <- country_info %>%
  filter(ISO == "SYC") %>%
  pull(income)

# Find countries with similar income levels (within 20% range)
income_patterns <- final_df %>%
  filter(!is.na(mortality_rate)) %>%
  inner_join(
    country_info %>% 
      filter(income >= seychelles_income * 0.8,
             income <= seychelles_income * 1.2) %>% 
      select(ISO),
    by = "ISO"
  ) %>%
  group_by(age, Sex) %>%
  summarise(
    median_mortality = median(mortality_rate, na.rm = TRUE),
    .groups = 'drop'
  )

# Apply to Seychelles only
final_df_imputed <- final_df_imputed %>%
  mutate(
    mortality_rate = case_when(
      ISO == "SYC" & is.na(mortality_rate) ~ 
        income_patterns$median_mortality[match(paste(age, Sex), paste(income_patterns$age, income_patterns$Sex))],
      TRUE ~ mortality_rate
    )
  )

# Final validation
validation_check <- final_df_imputed %>%
  group_by(ISO) %>%
  summarise(
    missing_values = sum(is.na(mortality_rate)),
    .groups = 'drop'
  )

print("Countries with missing values after imputation:")
print(validation_check %>% filter(missing_values > 0))

print("Total missing values before and after imputation:")
print(c(
  before = sum(is.na(final_df$mortality_rate)),
  after = sum(is.na(final_df_imputed$mortality_rate))
))



# Check summary statistics before and after imputation
before_after_stats <- bind_rows(
  final_df %>% 
    group_by(Sex) %>%
    summarise(
      mean = mean(mortality_rate, na.rm = TRUE),
      median = median(mortality_rate, na.rm = TRUE),
      sd = sd(mortality_rate, na.rm = TRUE),
      q25 = quantile(mortality_rate, 0.25, na.rm = TRUE),
      q75 = quantile(mortality_rate, 0.75, na.rm = TRUE)
    ) %>%
    mutate(dataset = "before"),
  
  final_df_imputed %>%
    group_by(Sex) %>%
    summarise(
      mean = mean(mortality_rate, na.rm = TRUE),
      median = median(mortality_rate, na.rm = TRUE),
      sd = sd(mortality_rate, na.rm = TRUE),
      q25 = quantile(mortality_rate, 0.25, na.rm = TRUE),
      q75 = quantile(mortality_rate, 0.75, na.rm = TRUE)
    ) %>%
    mutate(dataset = "after")
)

print("Overall statistics before and after imputation:")
print(before_after_stats)

# Check specifically imputed values for reasonableness
# BATCHED VERSION - process one country at a time to avoid OOM
# Original code kept below (commented) for reference

# --- Batched validation ---
cat("\nRunning batched validation of imputed values...\n")

# Pre-compute which (ISO, age, Sex) combinations had missing original rates
# Use a lightweight lookup instead of joining the full dataset
original_missing_keys <- final_df %>%
  filter(is.na(mortality_rate)) %>%
  distinct(ISO, age, Sex) %>%
  mutate(is_imputed = TRUE)
gc()

# Join only the small lookup table (not full final_df)
imputed_values <- final_df_imputed %>%
  left_join(original_missing_keys, by = c("ISO", "age", "Sex")) %>%
  filter(isTRUE(is_imputed) | is_imputed == TRUE) %>%
  group_by(ISO) %>%
  summarise(
    min_mortality = min(mortality_rate, na.rm = TRUE),
    max_mortality = max(mortality_rate, na.rm = TRUE),
    mean_mortality = mean(mortality_rate, na.rm = TRUE),
    n_imputed = n(),
    .groups = "drop"
  )

rm(original_missing_keys)
gc()

print("\nSummary of imputed values by country:")
print(imputed_values)

# Seychelles comparison - batched by processing smaller subsets
# Filter Seychelles only (small subset)
seychelles_imputed <- final_df_imputed %>%
  filter(ISO == "SYC") %>%
  group_by(age, Sex) %>%
  summarise(
    mortality = median(mortality_rate, na.rm = TRUE),
    type = "Imputed Seychelles",
    .groups = "drop"
  )

# Similar income countries - get ISO list first, then filter final_df
similar_income_isos <- country_info %>%
  filter(income >= seychelles_income * 0.8,
         income <= seychelles_income * 1.2) %>%
  pull(ISO)

similar_income_comparison <- final_df %>%
  filter(ISO %in% similar_income_isos, !is.na(mortality_rate)) %>%
  group_by(age, Sex) %>%
  summarise(
    mortality = median(mortality_rate, na.rm = TRUE),
    type = "Similar Income Countries",
    .groups = "drop"
  )

seychelles_comparison <- bind_rows(seychelles_imputed, similar_income_comparison)
rm(seychelles_imputed, similar_income_comparison, similar_income_isos)
gc()

# --- Original code (commented, kept for reference) ---
# imputed_values <- final_df_imputed %>%
#   left_join(final_df %>% select(ISO, age, Sex, original_rate = mortality_rate), 
#             by = c("ISO", "age", "Sex")) %>%
#   filter(is.na(original_rate)) %>%
#   group_by(ISO) %>%
#   summarise(
#     min_mortality = min(mortality_rate),
#     max_mortality = max(mortality_rate),
#     mean_mortality = mean(mortality_rate),
#     n_imputed = n()
#   )
# 
# seychelles_comparison <- bind_rows(
#   final_df_imputed %>%
#     filter(ISO == "SYC") %>%
#     group_by(age, Sex) %>%
#     summarise(mortality = mortality_rate, type = "Imputed Seychelles", .groups = "drop"),
#   final_df %>%
#     filter(!is.na(mortality_rate)) %>%
#     inner_join(
#       country_info %>%
#         filter(income >= seychelles_income * 0.8, income <= seychelles_income * 1.2) %>%
#         select(ISO),
#       by = "ISO"
#     ) %>%
#     group_by(age, Sex) %>%
#     summarise(mortality = median(mortality_rate), type = "Similar Income Countries", .groups = "drop")
# )

#Some countries have mortality rates for some ages at 0
#Set to a bare minimum of 1/100,000 instead
final_df_imputed$mortality_rate[final_df_imputed$mortality_rate == 0] <- 0.00001



#Save results (to test folder)
#saveRDS(final_df_imputed, "final_df_imputed.rds")
saveRDS(final_df_imputed, "test/final_df_imputed.rds")

str(final_df_imputed)

# Free up memory before simulation
# Note: seychelles_comparison, imputed_values commented out above due to memory
rm(final_df, mortality_df, mortality_df_transformed, mortality_lookup, 
   regional_backup, income_patterns, 
   missing_matches, missing_countries, missing_regions, validation_check,
   before_after_stats)
gc()





#
#
#
#
#
#


# Check original row counts
original_count <- nrow(full_results)
mortality_count <- nrow(mortality2)
cat("Original dataset rows:", original_count, "\n")
cat("Mortality dataset rows:", mortality_count, "\n")

# Check for duplicates in join keys in mortality2
mortality_key_dupes <- mortality2 %>%
  group_by(ISO, Age, Sex) %>%
  summarise(
    n = n(),
    .groups = 'drop'
  ) %>%
  filter(n > 1)

cat("\nDuplicate keys in mortality data:\n")
print(mortality_key_dupes)

# Check for duplicates in join keys in full_results
results_key_dupes <- full_results %>%
  group_by(ISO, age, Sex) %>%
  summarise(
    n = n(),
    .groups = 'drop'
  ) %>%
  filter(n > 1)

cat("\nDuplicate keys in full_results:\n")
print(results_key_dupes)

# Check distinct combinations before and after join
# BATCHED VERSION - use final_df_imputed (same structure as final_df but kept in memory)
# Use distinct() early to minimize memory usage
before_combos <- full_results %>%
  distinct(ISO, age, Sex) %>%
  nrow()

after_combos <- final_df_imputed %>%
  distinct(ISO, age, Sex) %>%
  nrow()

cat("\nDistinct key combinations before:", before_combos)
cat("\nDistinct key combinations after:", after_combos)

# Check which specific combinations were added (using final_df_imputed)
added_combos <- final_df_imputed %>%
  distinct(ISO, age, Sex) %>%
  anti_join(
    full_results %>% distinct(ISO, age, Sex),
    by = c("ISO", "age", "Sex")
  )

cat("\nAdded combinations:\n")
print(added_combos)
gc()

# --- Original code (commented, kept for reference) ---
# before_combos <- full_results %>% select(ISO, age, Sex) %>% distinct() %>% nrow()
# after_combos <- final_df %>% select(ISO, age, Sex) %>% distinct() %>% nrow()
# added_combos <- final_df %>% select(ISO, age, Sex) %>% distinct() %>%
#   anti_join(full_results %>% select(ISO, age, Sex) %>% distinct(), by = c("ISO", "age" = "age", "Sex"))

# Check if any values in the age column differ in type or format
cat("\nUnique age values in full_results:\n")
print(unique(full_results$age))
cat("\nUnique Age values in mortality2:\n")
print(unique(mortality2$Age))


#Next adjust mortality based on BMI hazard ratios
#https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(16)30175-1/fulltext?post=bl103252020a


#########
# Saving all the necessary variables for downstream notebooks (Mortality Model.ipynb, Price rebound model.ipynb)
saveRDS(final_df_imputed, "test/final_df_imputed.rds")
saveRDS(mortality2, "test/mortality2.rds")
saveRDS(population_with_iso, "test/population_with_iso.rds")
#########


###########################################
#######   MORTALITY SIMULATION   ##########
###########################################




# First extend mortality rates to include all ages up to 109
final_df_imputed <- final_df_imputed %>%
  select(-Year) %>%  # Remove Year column before join
  left_join(
    mortality2 %>% select(ISO, Age, Sex, mortality_rate),
    by = c("ISO", "age" = "Age", "Sex")
  ) %>%
  mutate(
    mortality_rate = coalesce(mortality_rate.x, mortality_rate.y)
  ) %>%
  select(-mortality_rate.x, -mortality_rate.y)

# Run baseline simulation
set.seed(42)  # for reproducibility




# --- sec 2.15: continuous hazard within the top band -------------------------
#
# THE DEFECT. The ladder used to assign a flat 2.76 to all `bmi >= 40` with no
# upper bound. Two consequences. A bounded published estimate (top category
# 40.0-59.9) was being applied to an unbounded bin. And because the bin had no
# FLOOR, weight loss inside it produced a hazard ratio of exactly 1.0 between
# baseline and treatment -- integrating over the weight-loss distribution, 36%
# of top-band adherers stay above 40 and were credited with zero modelled
# survival benefit, in the range where the real gradient is steepest.
#
# The converse error is the larger one. A flat bin gives everyone who CROSSES
# out of it the whole band's mean hazard as their baseline. Crossers come
# disproportionately from 40-45, whose true hazard is well below the band mean,
# so their modelled benefit was systematically overstated. That is the defect
# being fixed here.
#
# Kitahara et al. 2014, PLOS Medicine, Table 4: HR 1.40 per 5 kg/m^2 within
# BMI 40.0-59.9. K is the composition-weighted mean of 1.4^((b-40)/5) over the
# top band, using the same class III composition the BMI construction imposes
# (Data_Cleaning9.8.R, sec 2.1.2). Normalising by K PRESERVES the existing 2.76
# anchor: the population mean baseline hazard in the top band is unchanged, so
# total baseline deaths barely move. What changes is the treatment contrast.
#
# The anchor is preserved stratum by stratum, not merely on average, because
# sec 2.1.2 imposes the same conditional composition on every stratum's top
# band -- so K is one constant everywhere.
#
# CLASS3_N is duplicated in three places by necessity (this file,
# Data_Cleaning9.8.R and deterministic_mortality.py are three languages/two
# runtimes). The stopifnot below is what actually stops them drifting: if any
# copy is edited, K moves and this fails loudly at source time.
CLASS3_N      <- c(6803, 1978, 627, 156)          # participants, not deaths
CLASS3_SHARE  <- CLASS3_N / sum(CLASS3_N)
HR_TOP_BASE   <- 2.76
HR_PER_5      <- 1.40
# Under a piecewise-linear CDF each sub-band is uniform, so the mean of
# 1.4^((b-40)/5) over a five-unit segment starting at 40 + 5j is
# 1.4^j * (1.4 - 1) / ln(1.4).
HR_TOP_K      <- sum(CLASS3_SHARE *
                     ((HR_PER_5 - 1) / log(HR_PER_5)) * HR_PER_5^(0:3))
HR_TOP_ANCHOR <- HR_TOP_BASE / HR_TOP_K           # 1.977378
stopifnot(abs(HR_TOP_K - 1.395788) < 1e-6,
          abs(HR_TOP_ANCHOR - 1.977378) < 1e-6)

# pmin at 60 is the terminal knot of the BMI construction. It never binds on
# `bmi` -- the knot vector guarantees that -- but it DOES bind on `new_bmi` for
# a handful of rows, because negative draws of individual_effect push them
# above 60. Do not assert that never happens; the rate is seed-dependent.
hr_top <- function(b) HR_TOP_ANCHOR * HR_PER_5^((pmin(b, 60) - 40) / 5)

# All-cause mortality hazard ratio as a function of BMI.
#
# One function called twice, on `bmi` and on `new_bmi`. Two copies of a ladder
# are two places for a future edit to land in one and not the other, which is
# exactly the failure mode that would be invisible here: baseline and treated
# hazards would come from different ladders and the ratio -- the only thing the
# pipeline consumes -- would still look plausible.
#
# The bins BELOW 40 must stay in step with get_raw_bmi_hazard_ratio() in
# data_visualization/deterministic_mortality.py, and so must the top-band form.
# They are checked against each other by diagnostics/ladder_diff.py.
bmi_hazard_ratio <- function(b) {
  case_when(
    b < 18.5 ~ 1.51,  # Now includes all BMI < 18.5
    b >= 18.5 & b < 20.0 ~ 1.13,
    b >= 20.0 & b < 25.0 ~ 1.00,
    b >= 25.0 & b < 27.5 ~ 1.07,
    b >= 27.5 & b < 30.0 ~ 1.20,
    b >= 30.0 & b < 35.0 ~ 1.45,
    b >= 35.0 & b < 40.0 ~ 1.94,
    b >= 40.0 ~ hr_top(b),
    TRUE ~ NA_real_
  )
}

# Calculate BMI hazard ratios with updated grouping
simulation_results <- final_df_imputed %>%
  mutate(
    bmi_hr = bmi_hazard_ratio(bmi),
    new_bmi_hr = bmi_hazard_ratio(new_bmi),
    baseline_alive = 1,
    semaglutide_alive = 1
  )

# Let's verify the change with a quick check
hr_check <- simulation_results %>%
  group_by(
    hr_group = case_when(
      bmi < 18.5 ~ "<18.5",
      bmi >= 18.5 & bmi < 20.0 ~ "18.5-20.0",
      bmi >= 20.0 & bmi < 25.0 ~ "20.0-25.0",
      bmi >= 25.0 & bmi < 27.5 ~ "25.0-27.5",
      bmi >= 27.5 & bmi < 30.0 ~ "27.5-30.0",
      bmi >= 30.0 & bmi < 35.0 ~ "30.0-35.0",
      bmi >= 35.0 & bmi < 40.0 ~ "35.0-40.0",
      bmi >= 40.0 ~ "40.0+",
      TRUE ~ "Other"
    )
  ) %>%
  summarise(
    n = n(),
    mean_hr = mean(bmi_hr, na.rm = TRUE),
    .groups = "drop"
  )

print("Updated Hazard Ratio Distribution:")
print(hr_check)

# Run the rest of the simulation as before
for(year in 1:10) {
  current_age <- simulation_results$age + year
  
  current_mortality <- mortality2 %>%
    select(ISO, Age, Sex, mortality_rate) %>%
    rename(current_age = Age) %>%
    right_join(
      simulation_results %>% 
        select(ISO, Sex) %>%
        mutate(current_age = current_age),
      by = c("ISO", "Sex", "current_age")
    ) %>%
    pull(mortality_rate)
  
  random_numbers <- runif(nrow(simulation_results))
  
  baseline_mortality <- current_mortality * simulation_results$bmi_hr
  semaglutide_mortality <- current_mortality * 
    ifelse(simulation_results$adheres_to_treatment,
           simulation_results$new_bmi_hr * 0.81,
           simulation_results$bmi_hr)
  
  simulation_results[[paste0("baseline_alive_", year)]] <- 
    ifelse(simulation_results$baseline_alive == 1 & 
             random_numbers > baseline_mortality,
           1, 0)
  
  simulation_results[[paste0("semaglutide_alive_", year)]] <- 
    ifelse(simulation_results$semaglutide_alive == 1 & 
             random_numbers > semaglutide_mortality,
           1, 0)
  
  simulation_results$baseline_alive <- 
    simulation_results[[paste0("baseline_alive_", year)]]
  simulation_results$semaglutide_alive <- 
    simulation_results[[paste0("semaglutide_alive_", year)]]
}

# Check final results
survival_diff <- simulation_results %>%
  summarise(
    across(matches("alive_\\d+"), ~mean(.x, na.rm = TRUE))
  ) %>%
  pivot_longer(
    everything(),
    names_to = c("scenario", "year"),
    names_pattern = "(.*)_alive_(\\d+)",
    values_to = "survival_rate"
  ) %>%
  pivot_wider(
    names_from = scenario,
    values_from = survival_rate
  ) %>%
  mutate(
    difference = semaglutide - baseline,
    relative_reduction = (semaglutide - baseline) / baseline * 100
  )

print("\nUpdated Survival Differences:")
print(survival_diff)




#
##
#
#
#
#
#
#


# Check BMI distribution and hazard ratios
bmi_check <- simulation_results %>%
  summarise(
    min_bmi = min(bmi, na.rm = TRUE),
    max_bmi = max(bmi, na.rm = TRUE),
    mean_bmi = mean(bmi, na.rm = TRUE),
    na_bmi = sum(is.na(bmi))
  )
print("BMI Check:")
print(bmi_check)

# Check hazard ratio assignment
hr_check <- simulation_results %>%
  group_by(
    hr_group = case_when(
      bmi >= 15.0 & bmi < 18.5 ~ "15.0-18.5",
      bmi >= 18.5 & bmi < 20.0 ~ "18.5-20.0",
      bmi >= 20.0 & bmi < 25.0 ~ "20.0-25.0",
      bmi >= 25.0 & bmi < 27.5 ~ "25.0-27.5",
      bmi >= 27.5 & bmi < 30.0 ~ "27.5-30.0",
      bmi >= 30.0 & bmi < 35.0 ~ "30.0-35.0",
      bmi >= 35.0 & bmi < 40.0 ~ "35.0-40.0",
      bmi >= 40.0 & bmi <= 60.0 ~ "40.0-60.0",
      TRUE ~ "Other"
    )
  ) %>%
  summarise(
    n = n(),
    mean_hr = mean(bmi_hr, na.rm = TRUE),
    .groups = "drop"
  )
print("\nHazard Ratio Distribution:")
print(hr_check)

# Check semaglutide treatment assignment
treatment_check <- simulation_results %>%
  summarise(
    total_population = n(),
    treated = sum(adheres_to_treatment, na.rm = TRUE),
    percent_treated = mean(adheres_to_treatment, na.rm = TRUE) * 100
  )
print("\nSemaglutide Treatment Check:")
print(treatment_check)

# Check mortality rates progression
mortality_progression <- simulation_results %>%
  group_by(age) %>%
  summarise(
    n = n(),
    mean_mortality = mean(mortality_rate, na.rm = TRUE),
    median_mortality = median(mortality_rate, na.rm = TRUE),
    .groups = "drop"
  )
print("\nMortality Rate Progression by Age:")
print(head(mortality_progression))

# Check survival differences between scenarios
survival_diff <- simulation_results %>%
  summarise(
    across(matches("alive_\\d+"), ~mean(.x, na.rm = TRUE))
  ) %>%
  pivot_longer(
    everything(),
    names_to = c("scenario", "year"),
    names_pattern = "(.*)_alive_(\\d+)",
    values_to = "survival_rate"
  ) %>%
  pivot_wider(
    names_from = scenario,
    values_from = survival_rate
  ) %>%
  mutate(
    difference = semaglutide - baseline,
    relative_reduction = (semaglutide - baseline) / baseline * 100
  )

print("\nSurvival Differences:")
print(survival_diff)

# Check for any anomalies in age progression
age_check <- simulation_results %>%
  mutate(
    max_possible_age = age + 10
  ) %>%
  summarise(
    min_start_age = min(age, na.rm = TRUE),
    max_start_age = max(age, na.rm = TRUE),
    max_final_age = max(max_possible_age, na.rm = TRUE)
  )
print("\nAge Range Check:")
print(age_check)



########################################################
################   VISUALIZATIONS  #####################
########################################################


# Create survival data from simulation_results, including year 0
survival_data <- simulation_results %>%
  # Select only the survival columns
  select(matches("alive_\\d+")) %>%
  # Calculate means for each year
  summarise(across(everything(), ~mean(., na.rm = TRUE))) %>%
  # Pivot to long format
  pivot_longer(
    everything(),
    names_to = c("scenario", "year"),
    names_pattern = "(.*)_alive_(\\d+)",
    values_to = "survival_rate"
  ) %>%
  # Convert year to numeric
  mutate(year = as.numeric(year)) %>%
  # Add year 0 data points
  bind_rows(
    tibble(
      scenario = c("baseline", "semaglutide"),
      year = 0,
      survival_rate = 1.0
    )
  ) %>%
  arrange(scenario, year)

# Create the survival plot with year 0
survival_plot <- ggplot(survival_data, aes(x = year, y = survival_rate, color = scenario)) +
  geom_line(size = 1) +
  geom_point() +
  scale_y_continuous(
    labels = scales::percent_format(accuracy = 0.1),
    limits = c(0.75, 1)
  ) +
  scale_x_continuous(breaks = 0:10) +
  scale_color_manual(
    values = c("baseline" = "#82ca9d", "semaglutide" = "#8884d8"),
    labels = c("Baseline", "Semaglutide")
  ) +
  labs(
    title = "10-Year Survival Rates: Baseline vs Semaglutide Treatment",
    x = "Year",
    y = "Survival Rate",
    color = "Group"
  ) +
  theme_minimal() +
  theme(
    plot.title = element_text(hjust = 0.5),
    legend.position = "bottom"
  )

print(survival_plot)


# Analyze age distribution and mortality by age group
age_distribution <- simulation_results %>%
  mutate(
    age_group = case_when(
      age < 30 ~ "18-29",
      age < 40 ~ "30-39",
      age < 50 ~ "40-49",
      age < 60 ~ "50-59",
      age < 70 ~ "60-69",
      age < 80 ~ "70-79",
      TRUE ~ "80+"
    )
  ) %>%
  group_by(age_group) %>%
  summarise(
    count = n(),
    percent = n()/nrow(.) * 100,
    mean_mortality = mean(mortality_rate, na.rm = TRUE),
    mean_bmi_hr = mean(bmi_hr, na.rm = TRUE)
  ) %>%
  arrange(factor(age_group, levels = c("18-29", "30-39", "40-49", "50-59", 
                                       "60-69", "70-79", "80+")))

# Print results
print("Age Distribution and Mortality Rates:")
print(age_distribution)

# Calculate mean age
mean_age <- mean(simulation_results$age)
median_age <- median(simulation_results$age)
print(paste("Mean age:", round(mean_age, 1)))
print(paste("Median age:", round(median_age, 1)))


#Add UN population data

# Import population data
# NOTE: This file may need to be downloaded separately if not present.
# Available from: https://population.un.org/wpp/downloads
population <- read_excel("UN/WPP2024_POP_F01_1_POPULATION_SINGLE_AGE_BOTH_SEXES.xlsx", 
                         sheet = 1,
                         skip = 16,
                         na = "")  # This tells R to only treat empty cells as NA

# Clean population data
population_clean <- population %>%
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
  summarise(Population = sum(Population * 1000, na.rm = TRUE), .groups = "drop")


head(population_clean)

###########################################
######   SCALE TO ACTUAL POPULATION  ######
###########################################


# Load required packages
library(countrycode)

# Add ISO codes to population data
population_with_iso <- population_clean %>%
  mutate(
    ISO = countrycode(Country, "country.name", "iso3c", 
                      custom_match = c("China, Hong Kong SAR" = "HKG",
                                       "China, Macao SAR" = "MAC",
                                       "China, Taiwan Province of China" = "TWN",
                                       "Türkiye" = "TUR"))
  ) %>%
  filter(!is.na(ISO))

# Calculate scaling factors first
scaling_factors <- simulation_results %>%
  mutate(
    age_group = case_when(
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
      age >= 85 ~ "85plus"
    )
  ) %>%
  group_by(ISO, age_group) %>%
  summarise(
    simulated_n = n(),
    .groups = "drop"
  ) %>%
  left_join(
    population_with_iso %>%
      select(ISO, Age_Group, Population),
    by = c("ISO" = "ISO", "age_group" = "Age_Group")
  ) %>%
  mutate(
    scaling_factor = Population / simulated_n
  )

# Calculate scaled mortality results
scaled_mortality <- simulation_results %>%
  mutate(
    age_group = case_when(
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
      age >= 85 ~ "85plus"
    )
  ) %>%
  left_join(scaling_factors, by = c("ISO", "age_group"))


# Calculate population-weighted survival rates for each year
population_weighted_survival <- scaled_mortality %>%
  summarise(
    across(matches("alive_\\d+"), 
           ~weighted.mean(., w = scaling_factor, na.rm = TRUE)),
    .groups = "drop"
  ) %>%
  pivot_longer(
    everything(),
    names_to = c("scenario", "year"),
    names_pattern = "(.*)_alive_(\\d+)",
    values_to = "survival_rate"
  ) %>%
  mutate(year = as.numeric(year)) %>%
  # Add year 0 data points
  bind_rows(
    tibble(
      scenario = c("baseline", "semaglutide"),
      year = 0,
      survival_rate = 1.0
    )
  ) %>%
  arrange(scenario, year)

# Create population-weighted survival plot
survival_plot <- ggplot(population_weighted_survival, 
                        aes(x = year, y = survival_rate, color = scenario)) +
  geom_line(size = 1) +
  geom_point() +
  scale_y_continuous(
    labels = scales::percent_format(accuracy = 0.1),
    limits = c(0.75, 1)
  ) +
  scale_x_continuous(breaks = 0:10) +
  scale_color_manual(
    values = c("baseline" = "#82ca9d", "semaglutide" = "#8884d8"),
    labels = c("Baseline", "Semaglutide")
  ) +
  labs(
    title = "Population-Weighted 10-Year Survival Rates",
    subtitle = "Baseline vs Semaglutide Treatment",
    x = "Year",
    y = "Survival Rate",
    color = "Group"
  ) +
  theme_minimal() +
  theme(
    plot.title = element_text(hjust = 0.5),
    legend.position = "bottom"
  )


# Calculate scaled deaths and lives saved by country
country_summary <- scaled_mortality %>%
  group_by(ISO) %>%
  summarise(
    total_population = sum(Population.y),
    baseline_deaths_yr1 = sum(!baseline_alive_1 * scaling_factor),
    baseline_deaths_yr5 = sum(!baseline_alive_5 * scaling_factor),
    baseline_deaths_yr10 = sum(!baseline_alive_10 * scaling_factor),
    semaglutide_deaths_yr1 = sum(!semaglutide_alive_1 * scaling_factor),
    semaglutide_deaths_yr5 = sum(!semaglutide_alive_5 * scaling_factor),
    semaglutide_deaths_yr10 = sum(!semaglutide_alive_10 * scaling_factor)
  ) %>%
  mutate(
    lives_saved_yr1 = baseline_deaths_yr1 - semaglutide_deaths_yr1,
    lives_saved_yr5 = baseline_deaths_yr5 - semaglutide_deaths_yr5,
    lives_saved_yr10 = baseline_deaths_yr10 - semaglutide_deaths_yr10
  ) %>%
  arrange(desc(lives_saved_yr10))

# Print results
print("Top 10 countries by lives saved over 10 years:")
print(head(country_summary, 10))

# Calculate global totals
global_summary <- country_summary %>%
  summarise(
    total_population = sum(total_population),
    total_lives_saved_yr1 = sum(lives_saved_yr1),
    total_lives_saved_yr5 = sum(lives_saved_yr5),
    total_lives_saved_yr10 = sum(lives_saved_yr10)
  )

print("\nGlobal summary:")
print(global_summary)

# Display the survival plot
print(survival_plot)

usapop<-population_clean %>% filter(Country=="United States of America")
