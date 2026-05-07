# Load
final_df_imputed <- readRDS("test/final_df_imputed.rds")  # path from project root

# Quick checks
dim(final_df_imputed)
names(final_df_imputed)
str(final_df_imputed)
summary(final_df_imputed)

# View as table in RStudio
View(final_df_imputed)

