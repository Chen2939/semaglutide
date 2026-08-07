# Phase 0 recon: establish which .rds the repo carries, what scenario strings it
# holds, and therefore whether the sec 2.6 / sec 2.7 defects in the plan describe
# the run of record or only the repo's legacy copy of the script.
# ASCII only.

options(width = 200)

files <- c(
  repo_root   = "C:/Users/sethw/repos/full_simulation_results8.rds",
  code_n_data = "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/Code and data/full_simulation_results8.rds",
  data_anal   = "C:/Users/sethw/OneDrive - University of Waterloo/Semaglutide/Data Analysis/full_simulation_results8.rds"
)

# repo_root and code_n_data are already known bit-identical (md5 1b56ef87...),
# so only read one of them plus the other candidate.
to_read <- c("repo_root", "data_anal")

for (nm in to_read) {
  f <- files[[nm]]
  cat("\n================================================================\n")
  cat(sprintf("%s\n  %s\n", nm, f))
  cat(sprintf("  size  : %d\n", file.info(f)$size))
  cat(sprintf("  mtime : %s\n", format(file.info(f)$mtime, "%Y-%m-%d %H:%M:%S")))
  x <- readRDS(f)
  cat(sprintf("  nrow  : %d   ncol: %d\n", nrow(x), ncol(x)))
  cat("  scenario values and counts:\n")
  tb <- table(x$scenario, useNA = "ifany")
  for (k in names(tb)) cat(sprintf("    [%s] %d\n", k, tb[[k]]))
  cat(sprintf("  distinct ISO : %d\n", length(unique(x$ISO))))
  cat("  columns:\n")
  cat(paste0("    ", paste(names(x), collapse = ", ")), "\n")
  # baseline bmi fingerprint, for cross-file comparison
  b <- x$bmi[x$scenario == unique(x$scenario)[1]]
  cat(sprintf("  baseline bmi: n=%d  sum=%.10f  first=%.12f  last=%.12f\n",
              length(b), sum(b), b[1], b[length(b)]))
  rm(x, b); gc(verbose = FALSE)
}

cat("\n================================================================\n")
cat("done\n")
