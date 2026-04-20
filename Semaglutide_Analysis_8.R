
####################################################
############# ANALYSIS OF FULL RESULTS #############
####################################################

#AS OF May 2
#NOT FULLY UPDATED FOR NEW full_simulation_8 which contains
#two scenarios - max and moderate uptake



#Use alternative libraries (e.g. SAS)
library(haven)
library(excel.link)
library(tidyverse)
library(readxl)
library("tidylog", warn.conflicts=FALSE)
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

#Load simulated population
#using naming convention to match Data Cleaning
#So the seventh number on this matches the 9.7 file in Data Cleaning
full_results <- readRDS("full_simulation_results8.rds")



str(full_results)


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

############### SOME CHECKS #################

full_results %>% filter(ISO=="NRU") %>% 
  filter(scenario=="max_uptake") %>% 
  select(ISO, Population, Age_Group, Sex, weighting) %>% 
  count()

NRU <- full_results %>% filter(ISO=="NRU") %>% 
  filter(scenario=="max_uptake") %>% 
  select(ISO, Population, Age_Group, Sex, weighting) %>% 
  distinct()

sum(NRU$Population)





####################################
#########   VISUALIZATION  #########
####################################



library(tidyr)
library(scales)

# Create BMI distribution comparison plot
bmi_categories <- c("<18.5", "18.5-20", "20-25", "25-30", "30-35", "35-40", ">= 40")

# Create BMI categories
full_results <- full_results %>%
  mutate(bmi_cat = case_when(
    bmi < 18.5 ~ "<18.5",
    bmi >= 18.5 & bmi < 20 ~ "18.5-20",
    bmi >= 20 & bmi < 25 ~ "20-25",
    bmi >= 25 & bmi < 30 ~ "25-30",
    bmi >= 30 & bmi < 35 ~ "30-35",
    bmi >= 35 & bmi < 40 ~ "35-40",
    bmi >= 40 ~ ">= 40"
  ))

# Create factors for proper ordering
full_results$bmi_cat <- factor(full_results$bmi_cat, levels = bmi_categories)

# Create long format data for BMI comparison
bmi_comparison <- full_results %>%
  select(bmi, new_bmi, weighting) %>%
  pivot_longer(cols = c(bmi, new_bmi),
               names_to = "measurement",
               values_to = "bmi_value") %>%
  mutate(measurement = ifelse(measurement == "bmi", "Initial BMI", "Post-Treatment BMI"))

# Create BMI distribution plot 
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
        axis.text.x = element_text(angle = 90))+
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


