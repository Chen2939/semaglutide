
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

#Load Lancet BMI data
bmi_female <- read_csv("Lancet/NCD_RisC_Lancet_2024_BMI_female_age_specific_country.csv")
bmi_male <- read_csv("Lancet/NCD_RisC_Lancet_2024_BMI_male_age_specific_country.csv")

#bind two dfs
bmi <- rbind(bmi_female, bmi_male)

#Clean lancet data
bmi_small <- bmi %>% filter(Year > 2021) 

#New column names
lancet_col_names <- xl.read.file("Lancet/lancet_column_names.xlsx")

# Create a named vector for renaming
dict <- lancet_col_names %>% deframe()

#Rename column heads and clean
bmi_clean <- bmi_small %>% 
  rename(all_of(dict)) %>%
  select(-which(nchar(names(.)) > 20)) %>% 
  rename(Country = `Country/Region/World`,
         Age_Group = 'Age group') %>% 
  mutate(Country = recode(Country, "Turkiye" = "Turkey"))

####################################
#########   ADD HEIGHT  ############
####################################

height<-read.csv("Lancet/NCD_RisC_Lancet_2020_height_child_adolescent_country.csv")

#Clean height data
height_clean <- height %>% 
  filter(Year > 2018, Age.group > 18) %>%
  select(Country, Sex, Mean.height, Mean.height.standard.error) %>% 
  rename(Mean_height = Mean.height,
         Mean_height_s_e = Mean.height.standard.error) %>% 
  mutate(Sex = recode(Sex, "Girls" = "Women", "Boys" = "Men"),
         Country = recode(Country, 
                          "Czech Republic" = "Czechia", 
                          "Macedonia (TFYR)" = "North Macedonia"))

#Join height data
bmi_join <- left_join(bmi_clean, height_clean)

####################################
#########   ADD INCOME  ############
####################################

#Load WorldBank data
worldbank <- xl.read.file("Worldbank_incomes_cleaned.xlsx")

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
pop_male <- read_excel("UN/WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx",
                         sheet = 1,
                         skip = 16,
                         na = "")  # This tells R to only treat empty cells as NA

# Import population data
pop_female <- read_excel("UN/WPP2024_POP_F01_3_POPULATION_SINGLE_AGE_FEMALE.xlsx",
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
diabetes_new <- read.csv("Lancet/NCD_RisC_Lancet_2024_Diabetes_age_specific_countries.csv")


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
#########   BMI MIXTURE MODEL ######
####################################

# Helper function for skew normal distribution
rskewnorm <- function(n, location = 0, scale = 1, shape = 0) {
  delta <- shape/sqrt(1 + shape^2)
  u0 <- delta * sqrt(2/pi)
  sigma <- scale/sqrt(1 - 2*delta^2/pi)
  xi <- location - sigma*u0
  
  z <- rnorm(n)
  abs_z <- abs(rnorm(n))
  
  xi + sigma * (delta * abs_z + sqrt(1 - delta^2) * z)
}

# BMI mixture model fitting
fit_bmi_mixture <- function(props, bmi_grid = seq(13, 60, by = 0.1)) {
  midpoints <- c(17, 19.25, 22.5, 27.5, 32.5, 37.5, 42.5)
  bounds <- c(0, 18.5, 20, 25, 30, 35, 40, Inf)
  
  n_points <- 20000
  sample_points <- numeric(0)
  
  for(i in seq_along(props)) {
    n_cat <- round(n_points * props[i])
    if(n_cat > 0) {
      points <- if(i == 1) {
        rskewnorm(n_cat, location = midpoints[i], scale = 1.2, shape = -3)
      } else if(i == length(props)) {
        rskewnorm(n_cat, location = midpoints[i], scale = 4, shape = 4)
      } else {
        width <- bounds[i+1] - bounds[i]
        skew <- if(width < 5) 0 else (i - length(props)/2) * 0.5
        rskewnorm(n_cat, location = midpoints[i], scale = width/2.5, shape = skew)
      }
      sample_points <- c(sample_points, points)
    }
  }
  
  # Remove outliers and fit KDE
  q1 <- quantile(sample_points, 0.001)
  q99 <- quantile(sample_points, 0.999)
  sample_points <- sample_points[sample_points >= q1 & sample_points <= q99]
  
  bandwidth <- dpik(sample_points)
  bandwidth <- bandwidth * min(1.5, IQR(sample_points)/1.34/bandwidth)
  
  kde_fit <- try({
    bkde(sample_points,
         kernel = "normal",
         bandwidth = bandwidth,
         gridsize = length(bmi_grid),
         range.x = c(13, 60))
  })
  
  if(inherits(kde_fit, "try-error")) return(NULL)
  
  # Normalize and smooth
  kde_fit$y <- kde_fit$y / (sum(kde_fit$y) * diff(kde_fit$x)[1])
  window_size <- max(7, round(15 * (max(props) / 0.4)))
  kde_fit$y <- stats::filter(kde_fit$y,
                             rep(1/window_size, window_size),
                             sides = 2)
  
  kde_fit$y[is.na(kde_fit$y)] <- 0
  kde_fit$y <- kde_fit$y / (sum(kde_fit$y) * diff(kde_fit$x)[1])
  
  list(
    x = kde_fit$x,
    density = kde_fit$y,
    cdf = cumsum(kde_fit$y) * diff(kde_fit$x)[1],
    bandwidth = bandwidth,
    original_props = props,
    midpoints = midpoints
  )
}

# Wrapper for use with mutate
get_bmi_mixture <- function(under_18.5, bmi_18.5to20, bmi_20to25, 
                            bmi_25to30, bmi_30to35, bmi_35to40, over_40) {
  props <- c(under_18.5, bmi_18.5to20, bmi_20to25, 
             bmi_25to30, bmi_30to35, bmi_35to40, over_40)
  
  if(any(is.na(props)) || abs(sum(props) - 1) > 0.01 || any(props < 0)) {
    return(NULL)
  }
  
  fit_bmi_mixture(props)
}



# Apply mixture model to data
lancet_dia_with_dist <- lancet_dia %>%
  rowwise() %>%
  mutate(
    bmi_distribution = list(get_bmi_mixture(
      BMI_under_18.5, BMI_18.5to20, BMI_20to25, 
      BMI_25to30, BMI_30to35, BMI_35to40, BMI_over_40
    ))
  ) %>%
  ungroup()

####################################
#########   SIMULATION  ############
####################################

# Helper function to simulate a single population
simulate_single_population <- function(data_row, n_individuals = 500) {
  if(!"Population" %in% names(data_row)) {
    stop("Population column missing from input data")
  }
  
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
  
  # Calculate weights
  heights_m <- heights / 100
  weights <- as.vector(bmi_values * (heights_m^2))
  
  # Generate ages as vector
  ages <- get_age_sample(data_row$Age_Group, n_individuals)
  
  # Generate PAL values
  sex_vector <- rep(sex, n_individuals)
  pal_values <- generate_pal_vectorized(sex_vector, bmi_values)
  
  # Calculate BMR and EER as vectors
  bmr_values <- if(sex == "Men") {
    (10 * weights) + (6.25 * heights) - (5 * ages) + 5
  } else {
    (10 * weights) + (6.25 * heights) - (5 * ages) - 161
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
  
  # Create result tibble
  tibble(
    bmi = bmi_values,
    height = heights,
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

# Run simulation in batches
run_simulation_in_batches <- function(data, batch_size = 10, n_individuals = 500) {
  n_batches <- ceiling(nrow(data) / batch_size)
  
  map_dfr(1:n_batches, function(i) {
    cat(sprintf("\nProcessing batch %d of %d\n", i, n_batches))
    
    start_idx <- (i-1) * batch_size + 1
    end_idx <- min(i * batch_size, nrow(data))
    current_batch <- data[start_idx:end_idx, ]
    
    current_batch %>%
      group_split(row_number()) %>%
      map_dfr(~simulate_single_population(.x, n_individuals))
  })
}

# Run full simulation
full_results <- lancet_dia_with_dist %>%
  run_simulation_in_batches(batch_size = 10, n_individuals = 500) %>%
  group_by(ISO, Sex, Age_Group) %>%
  mutate(
    weighting = Population / n()
  ) %>%
  ungroup()

#Add a column that specifies Type 1 or Type 2 diabetes
#With 90% of individuals assigned to Type 2

full_results <- full_results %>%
  mutate(diabetes_type = case_when(
    diabetes == 1 ~ if_else(runif(n()) <= 0.1, 1, 2),
    TRUE ~ NA_real_
  ))




####################################
#########   INTERVENTION  ##########
####################################


# Function to run the treatment simulation with a specified adherence rate
run_treatment_scenario <- function(data, adherence_rate, scenario_name) {
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
      
      # Apply the adherence rate parameter
      #This allows us to make sure there is a high adherence rate for the max scneario
      #And a low adherence rate for the moderate scenario
      adheres_to_treatment = case_when(
        qualifies_for_treatment ~ rbinom(n(), 1, adherence_rate) == 1,
        TRUE ~ FALSE
      ),
      
      # Generate individual treatment effects
      #Where semaglutide is expected to reduce weight by 11.8%
      individual_effect = case_when(
        adheres_to_treatment ~ rnorm(n(), mean = 0.118, sd = 0.06),
        TRUE ~ 0
      ),
      
      treatment_weight = case_when(
        adheres_to_treatment ~ weight * (1 - individual_effect),
        TRUE ~ weight
      ),
      
      treatment_bmr = case_when(
        Sex == "Men" ~ (10 * treatment_weight) + (6.25 * height) - (5 * age) + 5,
        Sex == "Women" ~ (10 * treatment_weight) + (6.25 * height) - (5 * age) - 161
      ),
      
      treatment_eer = treatment_bmr * pal,
      
      weight_diff = weight - treatment_weight,
      eer_diff = eer - treatment_eer,
      new_bmi = treatment_weight/(height/100)^2
    )
}

# Run both scenarios
#First scenario assumes maximum uptake where only those with negative side effects drop out
results_max_uptake <- run_treatment_scenario(full_results, 0.95, "max_uptake")
#Second scenario assumes uptake consistent with e.g. statins or ACE inhibitors where only half of those eligible actually persist with treatment
results_mod_uptake <- run_treatment_scenario(full_results, 0.50, "mod_uptake")

# Combine results for analysis
all_results <- bind_rows(results_max_uptake, results_mod_uptake)





# Save results
saveRDS(all_results, "full_simulation_results8.rds")
 

##### VARIOUS CHECKS #####

#Check list of countries
countries<-all_results %>% select(ISO) %>% distinct()

print(countries)

# Check adherence rates by scenario
# Simple way to check adherence rates
max_uptake_data <- all_results[all_results$scenario == "Maximum uptake", ]
mod_uptake_data <- all_results[all_results$scenario == "Moderate uptake", ]

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

#Load simulated population
full_results <- readRDS("full_simulation_results8.rds")


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

# Create long format data for BMI comparison
bmi_comparison <- full_results %>%
  select(bmi, new_bmi, weighting) %>%
  pivot_longer(cols = c(bmi, new_bmi),
               names_to = "measurement",
               values_to = "bmi_value") %>%
  mutate(measurement = ifelse(measurement == "bmi", "Initial BMI", "Post-Treatment BMI"))

# Create BMI distribution plot (this part worked fine but let's enhance it)
ggplot(bmi_comparison, aes(x = bmi_value, weight = weighting, fill = measurement)) +
  geom_density(alpha = 0.5, position = "identity") +
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
  group_by(ISO) %>%
  summarise(
    total_eer_diff = sum(eer_diff * weighting * 365.25 / 1e9)  # Convert to billion kcal per year
  ) %>%
  ungroup() %>%
  arrange(desc(total_eer_diff))


ggplot(eer_national, aes(x = reorder(ISO, total_eer_diff), y = total_eer_diff)) +
  geom_col(fill = "#69b3a2") +
  #coord_flip() +
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
  group_by(ISO) %>%
  summarise(
    total_weight_diff = sum(weight_diff * weighting / 1e6)  # Convert to million kg
  ) %>%
  ungroup() %>%
  arrange(desc(total_weight_diff))

weight_national

ggplot(weight_national, aes(x = reorder(ISO, total_weight_diff), y = total_weight_diff)) +
  geom_col(fill = "#404080") +
  #coord_flip() +
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


# Korean age vs weight plot
full_results %>%
  filter(ISO == "KOR") %>%
  ggplot(aes(x = age, y = bmi, color = Sex)) +
  geom_point(alpha = 0.4) +
  scale_color_brewer(palette = "Set1") +
  labs(title = "Age vs BMI Distribution in Korea",
       subtitle = "Point size indicates population weighting",
       x = "Age (years)",
       y = "BMI",
       size = "Population\nWeight") +
  theme_minimal() +
  theme(legend.position = "right",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9)) +
  scale_size_continuous(range = c(0.5, 3))

# US height vs weight plot
full_results %>%
  filter(ISO == "USA") %>%
  ggplot(aes(x = height, y = weight, color = factor(diabetes))) +
  geom_point(alpha = 0.4) +
  scale_color_manual(values = c("0" = "#69b3a2", "1" = "#e15759"),
                     labels = c("No Diabetes", "Diabetes"),
                     name = "Diabetes Status") +
  labs(title = "Height vs Weight Distribution in United States",
       subtitle = "Point size indicates population weighting",
       x = "Height (cm)",
       y = "Weight (kg)",
       size = "Population\nWeight") +
  theme_minimal() +
  theme(legend.position = "right",
        plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9)) +
  scale_size_continuous(range = c(0.5, 3))


# Norway EER comparison plot
full_results %>%
  filter(ISO == "NOR") %>%
  ggplot(aes(x = eer, y = treatment_eer)) +
  geom_point(alpha = 0.4, size = 1) +
  geom_abline(linetype = "dashed", color = "red", alpha = 0.5) +  # Add y=x reference line
  labs(title = "Energy Expenditure Requirements Before vs After Treatment in Norway",
       x = "Initial EER (kcal/day)",
       y = "Post-Treatment EER (kcal/day)") +
  theme_minimal() +
  theme(plot.title = element_text(size = 11),
        axis.title = element_text(size = 10),
        axis.text = element_text(size = 9))



# BMI vs EER difference plot with faceting
full_results %>%
  filter(ISO %in% c("JPN", "CAN")) %>%
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
        strip.text = element_text(size = 10, face = "bold"))



# BMI vs EER difference plot with faceting
full_results %>%
  filter(ISO %in% c("ASM", "CAN")) %>%
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
        strip.text = element_text(size = 10, face = "bold"))


#Create table summarizing results
eer_effects<-full_results %>%
  filter(adheres_to_treatment == TRUE) %>%
  summarise(
    n_treated = n(),
    mean_eer_decrease = mean(eer_diff),
    mean_eer_decrease_percent = mean(eer_diff/eer * 100),
    sd_eer_decrease = sd(eer_diff),
    sd_eer_decrease_percent = sd(eer_diff/eer * 100),
    median_eer_decrease_percent = median(eer_diff/eer * 100),
    q25_eer_decrease_percent = quantile(eer_diff/eer * 100, 0.25),
    q75_eer_decrease_percent = quantile(eer_diff/eer * 100, 0.75)
  )

#Intervention only results in a 7% decrease in calories
#Studies show more like a 20-30% decrease in calories, but they are small sample sizes


#Check that our intervention worked
intervention_effects<- full_results %>%
  filter(adheres_to_treatment == TRUE) %>%
  summarise(
    n_treated = n(),
    mean_weight_decrease = mean(weight_diff),
    mean_weight_decrease_percent = mean(weight_diff/weight * 100),
    sd_weight_decrease_percent = sd(weight_diff/weight * 100),
    median_weight_decrease_percent = median(weight_diff/weight * 100),
    q25_weight_decrease_percent = quantile(weight_diff/weight * 100, 0.25),
    q75_weight_decrease_percent = quantile(weight_diff/weight * 100, 0.75)
  )
#Here we find that mean intervention was more than 11.8% since we prevented weight gain
#But median intervention was 11.8%
#Standard deviations were 9%, again due to capping
#So intervention looks good

# Analyze mean weight loss in treated sample
full_results %>% 
  filter(adheres_to_treatment == TRUE) %>% 
  ggplot(aes(x = weight_diff)) +
  geom_histogram(
    fill = "#2C3E50",
    color = "white",
    bins = 30
  ) +
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
