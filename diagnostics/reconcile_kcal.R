# Reconcile the annual-calorie figure in calorie_reduction_percent.csv against
# the one in supplement_results_table_raw.csv. Two files, two values, same
# name -- confirm the gap is entirely scope + day-count and not a third thing.
suppressMessages({library(dplyr); library(readr)})

x  <- readRDS("full_simulation_results9.rds")
cr <- read_csv("data_result/calorie_reduction_percent.csv", show_col_types = FALSE)
sup <- read_csv("data_result/supplement_results_table_raw.csv", show_col_types = FALSE)
names(sup)[1] <- sub("^﻿", "", names(sup)[1])
fs <- read_csv("data_result/net_emissions_with_drug.csv", show_col_types = FALSE)

for (sc in c("max_uptake", "mod_uptake")) {
  d <- x %>% filter(scenario == sc)
  target <- sup %>%
    filter(metric == "Calories reduced (kcal/yr, t=0)", scenario == sc,
           stage == "before") %>% pull(value_raw) %>% as.numeric()
  mine <- cr %>% filter(scope == "global", scenario == sc) %>%
    pull(kcal_removed_annual)

  # the supplement's sample: countries with POSITIVE annual food savings
  iso <- fs %>% filter(scenario == sc, !is.na(annual_food_savings_t),
                       annual_food_savings_t > 0) %>% pull(ISO) %>% unique()
  daily_all <- sum(d$eer_diff * d$weighting)
  daily_sub <- sum(d$eer_diff[d$ISO %in% iso] * d$weighting[d$ISO %in% iso])

  cat(sprintf("\n%s\n", sc))
  cat(sprintf("  mine   : 63 countries x 365.25 = %.6e   (CSV says %.6e)\n",
              daily_all * 365.25, mine))
  cat(sprintf("  step 1 : 63 countries x 365    = %.6e\n", daily_all * 365))
  cat(sprintf("  step 2 : %2d countries x 365    = %.6e\n", length(iso),
              daily_sub * 365))
  cat(sprintf("  supplement                     = %.6e\n", target))
  cat(sprintf("  ratio step2 / supplement       = %.10f  %s\n",
              daily_sub * 365 / target,
              ifelse(abs(daily_sub * 365 / target - 1) < 1e-9,
                     "EXACT -- fully reconciled", "*** UNEXPLAINED RESIDUAL ***")))
}
