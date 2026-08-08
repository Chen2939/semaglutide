# Percentage of calories reduced, per country x scenario and globally.
#
#   Rscript scripts/build_calorie_reduction.R
#   -> data_result/calorie_reduction_percent.csv
#
# WHY A SEPARATE SCRIPT. The model computes calorie reductions in three places
# and none of them writes a PERCENTAGE anywhere: the supplement table has
# absolute kcal/yr, the pipeline computes the demand shock in memory and keeps
# only its consequences, and the per-patient figure is printed by the R
# simulation and never persisted. This is the one script that reads the .rds,
# so build_manuscript_numbers.R can stay CSV-only and take seconds; re-run this
# only when the population changes.
#
# THREE DEFINITIONS, AND THEY ARE NOT INTERCHANGEABLE. Quoting one where a
# reader expects another is the trap this file exists to prevent, so all three
# are emitted side by side and every row is labelled.
#
#   per_treated_patient   Population-weighted mean over ADHERERS of the
#                         individual ratio eer_diff / eer. "A treated patient
#                         eats X% fewer calories." This is the ~7% figure the
#                         manuscript discussion quotes. It says nothing about
#                         national food demand, because most people are not
#                         treated.
#
#   adults_aggregate      Total kcal removed / total ADULT kcal requirement.
#                         Smaller than the per-patient figure by roughly the
#                         treated share of the adult population.
#
#   all_ages_aggregate    Total kcal removed / (adult + child kcal requirement).
#                         THIS IS THE ONE THE FOOD MODEL USES -- it is
#                         `expected_demand_reduction_percent` in pipeline.py,
#                         the shock applied to FAOSTAT supply. Children are
#                         untreated but still eat, so their requirement belongs
#                         unchanged in the denominator; normalising on adults
#                         alone would implicitly assume adults are 100% of
#                         national food consumption and overstate the shock.
#
# The child pool is DAILY kcal (the source file is annual; /365 here), matching
# the adult side, which is Mifflin BMR x PAL per day.
#
# ASCII only.

suppressMessages({
  library(dplyr)
  library(readxl)
  library(readr)
})

REPO <- getwd()
if (!dir.exists(file.path(REPO, "data_result"))) {
  stop("Run from the repository root: Rscript scripts/build_calorie_reduction.R")
}
SIM   <- file.path(REPO, "full_simulation_results9.rds")
CHILD <- file.path(REPO, "Food data", "child_energy_by_country.xlsx")
OUT   <- file.path(REPO, "data_result", "calorie_reduction_percent.csv")
for (f in c(SIM, CHILD)) if (!file.exists(f)) stop("missing input: ", f)

cat(sprintf("reading %s\n", basename(SIM)))
x  <- readRDS(SIM)
ch <- read_excel(CHILD)
child_daily <- setNames(ch$total_annual_child_kcal / 365, ch$ISO3)

# Countries with no child pool would silently fall onto an adults-only
# denominator, which is exactly the error the all-ages basis exists to avoid.
# Named rather than absorbed.
missing_child <- setdiff(unique(x$ISO), names(child_daily))
if (length(missing_child)) {
  cat(sprintf("  NOTE: no child energy pool for %d of %d modelled countries: %s\n",
              length(missing_child), length(unique(x$ISO)),
              paste(sort(missing_child), collapse = ", ")))
  cat("  Their all_ages_aggregate is reported as NA rather than falling back\n")
  cat("  to an adults-only denominator, which would overstate the shock.\n")
}

per_country <- x %>%
  group_by(scenario, ISO) %>%
  summarise(
    kcal_removed_daily   = sum(eer_diff * weighting),
    adult_pool_daily     = sum(eer * weighting),
    pop_adult            = sum(weighting),
    pop_treated          = sum(weighting * adheres_to_treatment),
    # weighted mean of the individual ratio, over adherers only
    per_treated_patient_pct = {
      i <- adheres_to_treatment
      if (any(i)) weighted.mean((eer_diff / eer)[i], weighting[i]) * 100 else NA_real_
    },
    .groups = "drop"
  ) %>%
  mutate(
    child_pool_daily     = unname(child_daily[ISO]),
    all_ages_pool_daily  = adult_pool_daily + child_pool_daily,
    adults_aggregate_pct   = kcal_removed_daily / adult_pool_daily * 100,
    all_ages_aggregate_pct = kcal_removed_daily / all_ages_pool_daily * 100,
    treated_share_of_adults_pct = pop_treated / pop_adult * 100,
    kcal_removed_annual  = kcal_removed_daily * 365.25,
    scope = "country"
  )

# Global rows. The all-ages figure is computed only over countries that HAVE a
# child pool, so its numerator and denominator cover the same set -- summing a
# numerator over 63 countries against a denominator over 56 would be wrong.
have_child <- !is.na(per_country$child_pool_daily)
global <- bind_rows(lapply(unique(per_country$scenario), function(sc) {
  d  <- per_country %>% filter(scenario == sc)
  dc <- d %>% filter(!is.na(child_pool_daily))
  xs <- x %>% filter(scenario == sc, adheres_to_treatment)
  tibble(
    scenario = sc, ISO = "GLOBAL", scope = "global",
    kcal_removed_daily = sum(d$kcal_removed_daily),
    adult_pool_daily   = sum(d$adult_pool_daily),
    child_pool_daily   = sum(dc$child_pool_daily),
    all_ages_pool_daily = sum(dc$adult_pool_daily) + sum(dc$child_pool_daily),
    pop_adult   = sum(d$pop_adult),
    pop_treated = sum(d$pop_treated),
    per_treated_patient_pct = weighted.mean(xs$eer_diff / xs$eer, xs$weighting) * 100,
    adults_aggregate_pct    = sum(d$kcal_removed_daily) / sum(d$adult_pool_daily) * 100,
    all_ages_aggregate_pct  = sum(dc$kcal_removed_daily) /
                              (sum(dc$adult_pool_daily) + sum(dc$child_pool_daily)) * 100,
    treated_share_of_adults_pct = sum(d$pop_treated) / sum(d$pop_adult) * 100,
    kcal_removed_annual = sum(d$kcal_removed_daily) * 365.25,
    n_countries = nrow(d),
    n_countries_with_child_pool = nrow(dc)
  )
}))

# A third global row per scenario on the SUPPLEMENT'S basis, so the annual-kcal
# figure here and the one in supplement_results_table_raw.csv agree by
# construction instead of looking like two answers to one question. They differ
# for two reasons and no others, verified exactly by
# diagnostics/reconcile_kcal.R (ratio 1.0000000000):
#
#   * scope    -- the supplement restricts to countries with POSITIVE food
#                 savings (53), this file covers all 63 simulated (+1.68%)
#   * day count -- the supplement uses 365, the rest of the model uses 365.25
#                 (+0.07%)
#
# Neither is wrong; they are different quantities. 365.25 is kept as the
# default here because the R simulation and eer_national already use it.
fs_path <- file.path(REPO, "data_result", "net_emissions_with_drug.csv")
global_sup <- NULL
if (file.exists(fs_path)) {
  fs <- suppressMessages(read_csv(fs_path, show_col_types = FALSE))
  global_sup <- bind_rows(lapply(unique(x$scenario), function(sc) {
    iso <- fs %>% filter(scenario == sc, !is.na(annual_food_savings_t),
                         annual_food_savings_t > 0) %>% pull(ISO) %>% unique()
    d <- x %>% filter(scenario == sc, ISO %in% iso)
    a <- d %>% filter(adheres_to_treatment)
    tibble(
      scope = "global_supplement_basis", scenario = sc, ISO = "GLOBAL",
      per_treated_patient_pct = weighted.mean(a$eer_diff / a$eer, a$weighting) * 100,
      adults_aggregate_pct = sum(d$eer_diff * d$weighting) /
                             sum(d$eer * d$weighting) * 100,
      all_ages_aggregate_pct = NA_real_,
      treated_share_of_adults_pct = sum(d$weighting * d$adheres_to_treatment) /
                                    sum(d$weighting) * 100,
      kcal_removed_daily = sum(d$eer_diff * d$weighting),
      # 365, not 365.25 -- this row exists to match the supplement
      kcal_removed_annual = sum(d$eer_diff * d$weighting) * 365,
      adult_pool_daily = sum(d$eer * d$weighting),
      pop_adult = sum(d$weighting),
      pop_treated = sum(d$weighting * d$adheres_to_treatment),
      n_countries = length(iso)
    )
  }))
} else {
  cat("  NOTE: net_emissions_with_drug.csv absent; the supplement-basis rows\n")
  cat("  are skipped. Run the analysis suite to get them.\n")
}

res <- bind_rows(global, global_sup, per_country) %>%
  select(scope, scenario, ISO,
         per_treated_patient_pct, adults_aggregate_pct, all_ages_aggregate_pct,
         treated_share_of_adults_pct,
         kcal_removed_daily, kcal_removed_annual,
         adult_pool_daily, child_pool_daily, all_ages_pool_daily,
         pop_adult, pop_treated,
         n_countries, n_countries_with_child_pool)

write_csv(res, OUT, na = "")
cat(sprintf("\nwrote %s  (%d rows)\n\n", OUT, nrow(res)))

cat("GLOBAL, percentage of calories reduced:\n\n")
g <- res %>% filter(scope == "global")
for (i in seq_len(nrow(g))) {
  cat(sprintf("  %s\n", g$scenario[i]))
  cat(sprintf("    per treated patient      %8.4f %%   <- the manuscript's ~7%%\n",
              g$per_treated_patient_pct[i]))
  cat(sprintf("    all adults, aggregate    %8.4f %%\n", g$adults_aggregate_pct[i]))
  cat(sprintf("    all ages, aggregate      %8.4f %%   <- the demand shock the food model applies\n",
              g$all_ages_aggregate_pct[i]))
  cat(sprintf("    treated share of adults  %8.4f %%\n", g$treated_share_of_adults_pct[i]))
  cat(sprintf("    kcal removed per year    %.4e   (%d countries, %d with a child pool)\n\n",
              g$kcal_removed_annual[i], g$n_countries[i],
              g$n_countries_with_child_pool[i]))
}
cat("The three are different quantities. Label any of them wherever quoted.\n")
