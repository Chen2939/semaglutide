# Collate every headline number in the manuscript's Results section into one
# CSV, beside the value currently written in the draft.
#
# WHY. The Results numbers are spread across eight committed CSVs, and several
# of them (food tonnage, calories, rebound-by-mass) live only in the supplement
# table rather than anywhere obvious. Checking a regenerated run against the
# draft meant opening all eight. This puts them in one place with the draft's
# current wording alongside, so a diff is one column comparison.
#
# READS ONLY COMMITTED CSVs under data_result/. It does not run the pipeline,
# does not read the .rds or the pickle, and takes seconds. Re-run it after any
# pipeline pass to refresh.
#
#   Rscript scripts/build_manuscript_numbers.R
#   -> data_result/manuscript_headline_numbers.csv
#
# The `draft_value` column is TRANSCRIBED BY HAND from
# "Semaglutide/Drafts/Draft 3.docx", Results section, and is not derived from
# anything. If the draft is edited, these go stale and the `changed` column
# starts lying. The paragraph reference in `draft_ref` is there so each one can
# be found and re-checked.
#
# ASCII only.

suppressMessages({
  library(dplyr)
  library(readr)
  library(tidyr)
})

# Run from the repository root, as every other script in this repo is.
REPO <- getwd()
DR <- file.path(REPO, "data_result")
if (!dir.exists(DR)) {
  stop("data_result/ not found under ", REPO,
       "\nRun from the repository root: Rscript scripts/build_manuscript_numbers.R")
}
OUT <- file.path(DR, "manuscript_headline_numbers.csv")

read_dr <- function(f) {
  p <- file.path(DR, f)
  if (!file.exists(p)) stop("missing input CSV: ", p, "\nRun the analysis suite first.")
  suppressMessages(read_csv(p, show_col_types = FALSE, progress = FALSE))
}

rows <- list()
add <- function(draft_ref, metric, scenario, spec, unit,
                value, draft_value, source_csv, source_field, note = "") {
  rows[[length(rows) + 1]] <<- tibble(
    draft_ref = draft_ref, metric = metric, scenario = scenario, spec = spec,
    unit = unit, regenerated_value = as.numeric(value),
    regenerated_text = NA_character_,
    draft_value = as.numeric(draft_value), draft_text = NA_character_,
    source_csv = source_csv, source_field = source_field, note = note
  )
}
add_txt <- function(draft_ref, metric, scenario, spec,
                    value, draft_value, source_csv, source_field, note = "") {
  # Capture BEFORE the tibble() call. tibble() evaluates its arguments in order
  # and each becomes visible to the next, so writing
  #   draft_value = NA_real_, draft_text = as.character(draft_value)
  # makes the second read the NA column just created rather than the function
  # argument, and every label silently comes out blank.
  .val <- as.character(value)
  .draft <- as.character(draft_value)
  rows[[length(rows) + 1]] <<- tibble(
    draft_ref = draft_ref, metric = metric, scenario = scenario, spec = spec,
    unit = "label", regenerated_value = NA_real_,
    regenerated_text = .val,
    draft_value = NA_real_, draft_text = .draft,
    source_csv = source_csv, source_field = source_field, note = note
  )
}

# ---------------------------------------------------------------- inputs
sup   <- read_dr("supplement_results_table_raw.csv")
names(sup)[1] <- sub("^﻿", "", names(sup)[1])
drug  <- read_dr("drug_footprint_summary.csv")
net   <- read_dr("net_emissions_with_drug.csv")
wf10  <- read_dr("global_emissions_waterfall.csv")
wf1   <- read_dr("global_emissions_waterfall_1yr.csv")
surv  <- read_dr("survivor_manuscript_numbers.csv")
pcap  <- read_dr("per_capita_emissions_savings.csv")
sens  <- read_dr("all_sensitivity_overview_results.csv") %>%
           filter(!is.na(ratio_food_to_mort))
torn  <- read_dr("sensitivity_tornado_results.csv")

sup_v <- function(m, sc, st) {
  v <- sup %>% filter(metric == m, scenario == sc,
                      if (is.na(st)) is.na(stage) else stage == st) %>%
       pull(value_raw)
  if (length(v) != 1) NA_real_ else as.numeric(v)
}

# ================================================ Results paragraph 1 (tonnage)
for (sc in c("max_uptake", "mod_uptake")) {
  dr_kcal  <- if (sc == "max_uptake") 1.9e13 else 9.6e12
  dr_pre   <- if (sc == "max_uptake") 24.5   else 12.6
  dr_post  <- if (sc == "max_uptake") 10.9   else 5.6
  dr_off   <- if (sc == "max_uptake") 55.4   else 55.5
  add("Results p1", "Calories reduced, annual", sc, "baseline", "kcal/yr",
      sup_v("Calories reduced (kcal/yr, t=0)", sc, "before"), dr_kcal,
      "supplement_results_table_raw.csv", "value_raw [before]")
  add("Results p1", "Food tonnage reduced, before rebound", sc, "baseline", "Mt",
      sup_v("Food tonnage reduced (Mt, t=0)", sc, "before"), dr_pre,
      "supplement_results_table_raw.csv", "value_raw [before]")
  add("Results p1", "Food tonnage reduced, after rebound", sc, "baseline", "Mt",
      sup_v("Food tonnage reduced (Mt, t=0)", sc, "after"), dr_post,
      "supplement_results_table_raw.csv", "value_raw [after]")
  add("Results p1", "Rebound offset, by mass", sc, "baseline", "%",
      sup_v("Rebound offset (% tonnage)", sc, "after"), dr_off,
      "supplement_results_table_raw.csv", "value_raw [after]",
      "by MASS, not by emissions")
}

# ================================================ Results paragraph 2 (emissions)
# na.rm = TRUE is required and is not a papering-over. Three countries -- GUY,
# NRU and TWN -- have no FAOSTAT food CPI, so the equilibrium cannot be solved
# for them and the pipeline records NaN rather than a silent zero. They are
# excluded from every downstream ratio by the '> 0' filters, so excluding them
# from the global total is the consistent choice. Without na.rm the whole
# global figure comes out NA.
netsum <- net %>% group_by(scenario) %>%
  summarise(gross = sum(annual_food_savings_gross_t, na.rm = TRUE) / 1e6,
            net   = sum(annual_food_savings_t, na.rm = TRUE) / 1e6,
            drug10 = sum(total_drug_emissions_10yr, na.rm = TRUE) / 1e6,
            n_na = sum(is.na(annual_food_savings_gross_t)),
            .groups = "drop")
# The Results-paragraph emissions chain is taken WITHOUT mortality, from the
# t = 0 no-mortality panel, not from net_emissions_with_drug.csv.
#
# Why this changed. These four figures used to come off netsum, which is the
# pi-weighted year-1 solve -- mortality partly on. Everything else in the same
# paragraph is t = 0: the calories, the tonnage and the rebound offset come from
# supplement_results_table_raw.csv (survival_weighted = FALSE), and the
# per-patient figures come from this same panel A. So one paragraph was quoting
# two bases, differing by about 0.5% (51.0 vs 50.8 Mt after rebound, 49.8 vs
# 49.5 net), and the text disagreed with Figure 1 Panel A sitting beside it --
# which is the t = 0 series and says so in its caption.
#
# The mortality-weighted versions are not lost: they are what every 10-year
# ratio in the paper is built from, and they remain in
# net_emissions_with_drug.csv and in the break-even rows below. They just have
# no business in this chain.
pa <- function(uptake, step_name) {
  pcap %>% filter(panel == "A_1yr_no_mortality", spec == "baseline_mean_ci",
                  uptake == !!uptake, step == !!step_name) %>%
    slice(1) %>% pull(value_Mt)
}
for (sc in c("max_uptake", "mod_uptake")) {
  r <- netsum %>% filter(scenario == sc)
  add("Results p2", "Annual emissions saved, after rebound", sc, "baseline", "MtCO2e",
      pa(sc, "actual_food_savings"), if (sc == "max_uptake") 54.2 else 27.8,
      "per_capita_emissions_savings.csv",
      "value_Mt [A_1yr_no_mortality, actual_food_savings]")
  add("Results p2", "Annual emissions saved, net of pharmaceutical production",
      sc, "baseline", "MtCO2e",
      pa(sc, "net_savings"), if (sc == "max_uptake") 52.9 else 27.1,
      "per_capita_emissions_savings.csv",
      "value_Mt [A_1yr_no_mortality, net_savings]")
  add("Results p2", "Drug footprint per treated patient-year", sc, "baseline",
      "kgCO2e",
      drug %>% filter(scenario == sc) %>% pull(annual_drug_kg_co2e_per_user),
      5.38, "drug_footprint_summary.csv", "annual_drug_kg_co2e_per_user")
  # One-year manufacturing total, same t = 0 basis as the two rows above, so the
  # chain closes exactly: after-rebound minus this equals net. The ten-year row
  # below cannot do that -- it is pi_dose-weighted and spans a different country
  # set (see its note).
  add("Results p2", "Drug manufacturing emissions, one year", sc, "baseline",
      "MtCO2e", pa(sc, "manufacturing"), NA,
      "per_capita_emissions_savings.csv",
      "value_Mt [A_1yr_no_mortality, manufacturing]",
      "no-mortality basis; closes the chain: after_rebound - this = net")
  add("Results p2", "Drug emissions over ten years", sc, "baseline", "MtCO2e",
      r$drug10, if (sc == "max_uptake") 12.5 else NA,
      "net_emissions_with_drug.csv", "sum(total_drug_emissions_10yr)/1e6",
      paste("spans all 56 ISO in net_emissions_with_drug, including GUY/NRU/TWN",
            "which have treated patients but no price index and so no food",
            "savings; over the 53-country food sample it is 12.12 Mt"))
}

# ================================================ Mortality model results
for (sc in c("max_uptake", "mod_uptake")) {
  s <- surv %>% filter(scenario == sc)
  add("Results, mortality", "Mortality reduction (mean HR reduction)", sc,
      "baseline", "%", s$avg_hr_reduction_pct,
      if (sc == "max_uptake") 18.6 else 18.4,
      "survivor_manuscript_numbers.csv", "avg_hr_reduction_pct",
      "draft says 'decreased by 18-19% (max-mod)'")
  add("Results, mortality", "Additional survivors at year 10", sc, "baseline",
      "people", s$extra_survivors_y10,
      if (sc == "max_uptake") 3.1e6 else 1.7e6,
      "survivor_manuscript_numbers.csv", "extra_survivors_y10")
  add("Results, mortality", "Treated users", sc, "baseline", "people",
      s$treated_users, if (sc == "max_uptake") NA else NA,
      "survivor_manuscript_numbers.csv", "treated_users")
  add("Results, mortality", "Cumulative person-years saved, 10-yr", sc,
      "baseline", "person-years", s$total_person_years_saved, NA,
      "survivor_manuscript_numbers.csv", "total_person_years_saved")
}
add("Results, mortality", "Total population of nations studied", NA, "baseline",
    "people",
    pcap %>% filter(panel == "B_10yr_with_survivorship",
                    spec == "baseline_mean_ci", uptake == "max_uptake") %>%
      slice(1) %>% pull(population_2022),
    1.2e9, "per_capita_emissions_savings.csv", "population_2022",
    "draft says '1.2 billion'")

# ================================================ Per patient-year
pp <- function(panel, uptake) {
  pcap %>% filter(panel == !!panel, spec == "baseline_mean_ci",
                  uptake == !!uptake, step == "net_savings") %>%
    slice(1) %>% pull(per_patient_year_kg)
}
add("Results p on per-patient", "Emissions reduced per patient-year, no mortality",
    "max_uptake", "baseline", "kgCO2e", pp("A_1yr_no_mortality", "max_uptake"),
    214, "per_capita_emissions_savings.csv",
    "per_patient_year_kg [A_1yr_no_mortality, net_savings]",
    "rebound + manufacturing, mortality excluded")
add("Results p on per-patient", "Emissions reduced per patient-year, with survivorship",
    "max_uptake", "baseline", "kgCO2e",
    pp("B_10yr_with_survivorship", "max_uptake"),
    99, "per_capita_emissions_savings.csv",
    "per_patient_year_kg [B_10yr_with_survivorship, net_savings]")
for (u in c("mod_uptake")) {
  add("Results p on per-patient", "Emissions reduced per patient-year, no mortality",
      u, "baseline", "kgCO2e", pp("A_1yr_no_mortality", u), NA,
      "per_capita_emissions_savings.csv", "per_patient_year_kg")
  add("Results p on per-patient", "Emissions reduced per patient-year, with survivorship",
      u, "baseline", "kgCO2e", pp("B_10yr_with_survivorship", u), NA,
      "per_capita_emissions_savings.csv", "per_patient_year_kg")
}

# ================================================ Waterfall / cumulative
wf <- function(tab, step, sc = "max_uptake") {
  tab %>% filter(step == !!step, scenario == sc) %>% slice(1) %>% pull(value_Mt)
}
for (st in c("naive_reductions", "rebound_effect", "actual_food_savings",
             "survivorship", "manufacturing", "net_savings")) {
  add("Figure 1 Panel B (10-yr)", paste0("Waterfall 10-yr: ", st),
      "max_uptake", "baseline", "MtCO2e", wf(wf10, st),
      if (st == "net_savings") 230 else NA,
      "global_emissions_waterfall.csv", "value_Mt")
}
for (st in c("naive_reductions", "rebound_effect", "actual_food_savings",
             "manufacturing", "net_savings")) {
  add("Figure 1 Panel A (1-yr)", paste0("Waterfall 1-yr: ", st),
      "max_uptake", "baseline", "MtCO2e", wf(wf1, st), NA,
      "global_emissions_waterfall_1yr.csv", "value_Mt")
}
add("Results, sensitivity", "10-yr net savings, survivor non-food declining 2%/yr",
    "max_uptake", "declining_2pct", "MtCO2e",
    torn %>% filter(parameter == "Survivor GHG decline") %>%
      slice(1) %>% pull(high_net_savings_10yr_Mt),
    251, "sensitivity_tornado_results.csv", "high_net_savings_10yr_Mt")
add("Results, sensitivity", "10-yr net savings, survivor emissions held flat",
    "max_uptake", "flat_0pct", "MtCO2e",
    torn %>% filter(parameter == "Survivor GHG decline") %>%
      slice(1) %>% pull(baseline_net_savings_10yr_Mt),
    230, "sensitivity_tornado_results.csv", "baseline_net_savings_10yr_Mt")

# ================================================ Table 1
T1 <- tribble(
  ~label,                             ~d_ratio, ~d_min,       ~d_minratio, ~d_n,
  "Baseline",                         1.8,      "Hungary",    1.2,         0,
  "Fatty foods down",                 2.3,      "Lithuania",  1.4,         0,
  "Cereals/sweets shift",             1.2,      "Hungary",    0.9,         5,
  "All foods P10 CI",                 1.1,      "Lithuania",  0.7,         9,
  "All foods P90 CI",                 2.6,      "Hungary",    1.6,         0,
  "Cereals/sweets + all-food P10 CI", 0.7,      "Hungary",    0.5,         21
)
for (i in seq_len(nrow(T1))) {
  lab <- T1$label[i]
  s <- sens %>% filter(overview_label == lab)
  if (nrow(s) != 1) { warning("Table 1 row not matched: ", lab); next }
  add("Table 1", "CUM-10Y food:survivor ratio", "max_uptake", lab, "ratio",
      s$ratio_food_to_mort, T1$d_ratio[i],
      "all_sensitivity_overview_results.csv", "ratio_food_to_mort",
      "cumulative ten-year, NOT the year-10 flow ratio")
  add_txt("Table 1", "Minimum country", "max_uptake", lab,
          s$min_country, T1$d_min[i],
          "all_sensitivity_overview_results.csv", "min_country")
  add("Table 1", "Ratio for minimum country", "max_uptake", lab, "ratio",
      s$min_country_ratio, T1$d_minratio[i],
      "all_sensitivity_overview_results.csv", "min_country_ratio")
  add("Table 1", "N countries with ratio < 1", "max_uptake", lab, "count",
      s$n_tipped_countries, T1$d_n[i],
      "all_sensitivity_overview_results.csv", "n_tipped_countries")
  add("Table 1", "N complete countries", "max_uptake", lab, "count",
      s$n_complete_countries, 40,
      "all_sensitivity_overview_results.csv", "n_complete_countries")
}

# ================================================ calorie reduction, as a %
# Built by scripts/build_calorie_reduction.R, which is the one script that
# reads the .rds. Three different denominators, all carried, all labelled --
# quoting one where a reader expects another is the trap. The draft states
# calories only in absolute kcal/yr, so these have no draft value to compare.
cal_path <- file.path(DR, "calorie_reduction_percent.csv")
if (file.exists(cal_path)) {
  cal <- read_dr("calorie_reduction_percent.csv") %>% filter(scope == "global")
  for (sc in c("max_uptake", "mod_uptake")) {
    r <- cal %>% filter(scenario == sc)
    add("Results p1 / discussion",
        "Calories reduced, % PER TREATED PATIENT", sc, "baseline", "%",
        r$per_treated_patient_pct, NA,
        "calorie_reduction_percent.csv", "per_treated_patient_pct [global]",
        "the manuscript's ~7%; says nothing about national demand")
    add("Results p1", "Calories reduced, % of ALL-ADULT requirement", sc,
        "baseline", "%", r$adults_aggregate_pct, NA,
        "calorie_reduction_percent.csv", "adults_aggregate_pct [global]",
        "denominator is adults only")
    add("Results p1", "Calories reduced, % of ALL-AGES requirement", sc,
        "baseline", "%", r$all_ages_aggregate_pct, NA,
        "calorie_reduction_percent.csv", "all_ages_aggregate_pct [global]",
        "THE DEMAND SHOCK the food model applies to FAOSTAT supply")
    add("Results p1", "Treated share of the adult population", sc, "baseline",
        "%", r$treated_share_of_adults_pct, NA,
        "calorie_reduction_percent.csv", "treated_share_of_adults_pct [global]",
        "why the per-patient and aggregate figures differ by ~4x")
  }
} else {
  warning("calorie_reduction_percent.csv absent; run ",
          "Rscript scripts/build_calorie_reduction.R")
}

# ================================================ US share of year-1 savings
# Built by scripts/build_us_share.py, which is the only route to it -- the share
# is not a ratio of anything already in data_result/, so it needs its own
# pipeline call. Basis is Supplementary Figure 1's: year 1, mean CI, no diet
# variant, survival_weighted = FALSE, pharmaceuticals excluded, and all 53
# countries with computable food savings rather than the 40-country
# complete-data subset. The 40-country set exists because a food:survivor ratio
# needs an OECD per-capita factor; nothing here touches survivor emissions, so
# that constraint does not apply and imposing it would inflate the share.
#
# total_mt is carried alongside the percentage on purpose. A share whose
# denominator is not written down cannot be audited if the sample is later
# disputed. It is also the cross-check: it equals the Results p2
# "Annual emissions saved, after rebound" row above, which comes from a
# different CSV on the same t = 0 basis.
us_path <- file.path(DR, "us_share_year1.csv")
if (file.exists(us_path)) {
  us <- read_dr("us_share_year1.csv")
  for (sc in c("max_uptake", "mod_uptake")) {
    r <- us %>% filter(scenario == sc)
    if (nrow(r) != 1) { warning("us_share_year1 row not matched: ", sc); next }
    add("Results p2", "US share of year-1 food-emission savings", sc, "baseline",
        "%", r$share_pct, NA, "us_share_year1.csv", "share_pct",
        paste("Supp Fig 1 basis; denominator is the 53-country food sample.",
              "Quoted near 'Most emissions savings are concentrated in the",
              "United States.'"))
    add("Results p2", "US year-1 food-emission savings", sc, "baseline",
        "MtCO2e", r$usa_mt, NA, "us_share_year1.csv", "usa_mt",
        "numerator of the share row")
    add("Results p2", "Total year-1 food-emission savings, 53-country sample",
        sc, "baseline", "MtCO2e", r$total_mt, NA,
        "us_share_year1.csv", "total_mt",
        paste("denominator of the share row; equals the Results p2",
              "after-rebound row, which is the same t = 0 basis"))
    # Baseline (pre-treatment) food-system emissions of the same 53-country
    # sample, emitted by build_us_share.py from the pipeline's pn_food_footprint
    # on pre-shock tonnage. Paired with total_mt by construction -- same basis,
    # same country set, one pipeline call -- so the manuscript can quote year-1
    # savings as a share of baseline food-system emissions. draft_ref is
    # "Discussion" because draft_ref is free text here, not validated against a
    # fixed list. draft_value is left empty on both rows: no draft number exists
    # to compare, so `changed` resolves to "no draft value".
    add("Discussion", "Baseline food emissions, 53-country sample", sc,
        "baseline", "MtCO2e", r$baseline_food_emissions_mt, NA,
        "us_share_year1.csv", "baseline_food_emissions_mt",
        paste("delta-independent and independent of all three mortality",
              "channels; denominator matching the 'Total year-1 food-emission",
              "savings' row"))
    # Row B: the percentage itself, computed HERE from the unrounded total_mt
    # and baseline_food_emissions_mt, so it can never be reconstructed from the
    # rounded values printed in the sheet.
    add("Discussion", "Year-1 food-emission savings, % of baseline food emissions",
        sc, "baseline", "%",
        r$total_mt / r$baseline_food_emissions_mt * 100, NA,
        "us_share_year1.csv", "total_mt / baseline_food_emissions_mt",
        paste("year-1 total food savings as a share of baseline food",
              "emissions; computed from unrounded values"))
  }
} else {
  warning("us_share_year1.csv absent; run ",
          "python scripts/build_us_share.py")
}

# ================================================ tornado ordering
for (i in seq_len(nrow(torn))) {
  add("Results, tornado", paste0("Tornado range: ", torn$parameter[i]),
      "max_uptake", "baseline", "MtCO2e", torn$range_Mt[i], NA,
      "sensitivity_tornado_results.csv", "range_Mt",
      "draft claims meat carbon intensity is the largest range")
}

# ------------------------------------------------ mortality basis
# Which mortality channels are live behind each number.
#
# This column exists because the Results paragraph mixes both WITHIN ITSELF.
# p1's calories, tonnage and rebound offset come from the t = 0 supplement
# table (survival_weighted = FALSE, no survivor emissions). p2's emissions come
# from net_emissions_with_drug.csv, which is the pi-weighted year-1 solve. The
# two bases differ by about 0.5%: 51.0 vs 50.8 Mt CO2e after rebound, 49.8 vs
# 49.5 net of the drug charge. Nothing in the table said so, and the per-patient
# figures sit on the t = 0 side, so the paragraph reads as one chain when it is
# two.
#
# Derived from source_csv and metric rather than written at each add() call, so
# a new row cannot forget it. Anything unmapped lands on UNCLASSIFIED and the
# run warns -- a blank would be indistinguishable from "mortality-neutral".
mortality_basis_of <- function(source_csv, metric, source_field) {
  case_when(
    # Panel first. per_capita_emissions_savings.csv carries BOTH bases in one
    # file and the panel name is the authority on which -- keying off the panel
    # in source_field rather than off the metric text means a new row drawn from
    # that file is classified correctly without anyone naming it "no mortality".
    grepl("A_1yr_no_mortality", source_field, fixed = TRUE)  ~ "without",
    grepl("B_10yr_with_survivorship", source_field, fixed = TRUE) ~ "with",
    grepl("no mortality", metric, fixed = TRUE)              ~ "without",
    grepl("with survivorship", metric, fixed = TRUE)         ~ "with",
    metric == "Total population of nations studied"          ~ "n/a (population count)",
    # 5.38 kg/user-year is a product constant; no survival weight touches it.
    metric == "Drug footprint per treated patient-year"      ~ "n/a (constant)",
    # us_share_year1.csv is survival_weighted = FALSE end to end, so EVERY field
    # drawn from it is "without" -- the US share/numerator/denominator rows and
    # the baseline_food_emissions_mt denominator + its percentage row added
    # alongside them. Classified by source_csv, not metric text, per this
    # function's rule that a new field from a known file is classified without
    # anyone having to name it.
    source_csv %in% c("supplement_results_table_raw.csv",
                      "global_emissions_waterfall_1yr.csv",
                      "calorie_reduction_percent.csv",
                      "us_share_year1.csv")                  ~ "without",
    source_csv %in% c("net_emissions_with_drug.csv",
                      "drug_footprint_summary.csv",
                      "global_emissions_waterfall.csv",
                      "sensitivity_tornado_results.csv",
                      "all_sensitivity_overview_results.csv") ~ "with",
    source_csv == "survivor_manuscript_numbers.csv"          ~ "mortality model output",
    TRUE                                                     ~ "UNCLASSIFIED"
  )
}

# ================================================ assemble
res <- bind_rows(rows) %>%
  mutate(
    mortality_basis = mortality_basis_of(source_csv, metric, source_field),
    abs_change = regenerated_value - draft_value,
    pct_change = ifelse(!is.na(draft_value) & draft_value != 0,
                        (regenerated_value / draft_value - 1) * 100, NA_real_),
    # Three levels rather than two. "minor" is a real category here: several
    # figures move by well under a percent and would round to the same printed
    # value, so lumping them in with the movers would bury the ones that matter.
    changed = case_when(
      !is.na(regenerated_text) & !is.na(draft_text) ~
        ifelse(regenerated_text == draft_text, "no", "YES"),
      !is.na(regenerated_text) ~ "no draft value",
      is.na(draft_value) ~ "no draft value",
      is.na(regenerated_value) ~ "NOT FOUND",
      abs_change == 0 ~ "no",
      is.na(pct_change) ~ "YES",
      abs(pct_change) >= 1 ~ "YES",
      TRUE ~ "minor"
    )
  ) %>%
  relocate(abs_change, pct_change, changed, .after = draft_text) %>%
  relocate(mortality_basis, .after = unit)

unmapped <- res %>% filter(mortality_basis == "UNCLASSIFIED")
if (nrow(unmapped) > 0) {
  warning("mortality_basis UNCLASSIFIED for ", nrow(unmapped), " row(s) from: ",
          paste(unique(unmapped$source_csv), collapse = ", "),
          " -- classify these in mortality_basis_of() before quoting the table.")
}

write_csv(res, OUT, na = "")
cat(sprintf("wrote %s  (%d rows)\n", OUT, nrow(res)))
for (lvl in c("YES", "minor", "no", "no draft value", "NOT FOUND")) {
  n <- sum(res$changed == lvl)
  if (n) cat(sprintf("  %-16s %d\n", lvl, n))
}
cat("\nrows that moved by 1 percent or more:\n")
res %>% filter(changed == "YES") %>%
  select(draft_ref, metric, spec, scenario, draft_value, draft_text,
         regenerated_value, regenerated_text) %>%
  as.data.frame() %>% print(row.names = FALSE)
