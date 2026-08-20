# Gate 1 probe for the China 2050 scope sensitivity. Confirms the WPP workbooks
# carry Korea 2022 (Estimates) and China 2050 (Medium variant), and that the
# ISO3 join key is populated -- NCD-RisC and WPP disagree on country names
# ("South Korea" vs "Republic of Korea"), so the join has to go through ISO3.
# Throwaway diagnostic; not part of the deliverable.

suppressMessages({ library(readxl); library(dplyr) })

UN <- "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Code and data/UN"
f_m <- file.path(UN, "WPP2024_POP_F01_2_POPULATION_SINGLE_AGE_MALE.xlsx")

for (sh in list(1, "Medium variant")) {
  d <- read_excel(f_m, sheet = sh, skip = 16, na = "", col_types = "text") %>%
    rename(Country = `Region, subregion, country or area *`,
           ISO3 = `ISO3 Alpha-code`) %>%
    filter(ISO3 %in% c("CHN", "KOR")) %>%
    mutate(Year = as.numeric(Year))
  cat(sprintf("\n---- sheet %s ----\n", as.character(sh)))
  print(d %>%
          group_by(ISO3, Country, Type) %>%
          summarise(n = n(), yr_min = min(Year), yr_max = max(Year),
                    has_2022 = any(Year == 2022), has_2050 = any(Year == 2050),
                    .groups = "drop") %>%
          as.data.frame())
}

# The single-age columns are labelled "0".."99","100+" and are in THOUSANDS.
# Confirm the last column label so the pivot regex is right.
h <- read_excel(f_m, sheet = "Medium variant", skip = 16, n_max = 1, na = "")
cat("\nlast 4 column names:", paste(tail(names(h), 4), collapse = " | "), "\n")
