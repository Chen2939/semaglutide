"""Phase 1 patch 3: guard the country-specific diagnostic plots.

The smoke run died in ggplot's combine_vars() because the 30-stratum cap
contains only Andorra, so the JPN/CAN facet had zero rows. That is a smoke
artifact, but the fragility is real in a full run too: if a country ever drops
out of the simulation universe, a facetted plot on it kills the script AFTER the
.rds has been written and before the G2 / 2.11 diagnostics that follow. Each
per-country plot now skips with a notice instead.

Also drops the ggplot `size` aesthetic labels the run warns about: three plots
declare size = "Population\\nWeight" in labs() with no size aesthetic mapped, so
ggplot emits "Ignoring unknown labels" every time. Pre-existing noise, removed
while here.

ASCII only.
"""
import io
import re
import sys

P = r"C:\Users\sethw\repos\legacy\R_scripts\Data_Cleaning9.8.R"
s = io.open(P, encoding="utf-8").read()

HELPER = '''# Country-specific diagnostic plots. Guarded: a facetted plot on an absent
# country aborts the script AFTER the .rds is written and BEFORE the G2 and
# diabetes diagnostics below, so a missing country would cost the run its
# verification rather than just its picture.
plot_if_present <- function(isos, f) {
  have <- intersect(isos, unique(full_results$ISO))
  if (length(have) != length(isos)) {
    cat(sprintf("  plot skipped -- absent ISO: %s\\n",
                paste(setdiff(isos, have), collapse = ", ")))
    return(invisible(NULL))
  }
  print(f())
  invisible(NULL)
}

'''

BLOCKS = [
    ("KOR", '"KOR"', 1),
    ("USA", '"USA"', 1),
    ("NOR", '"NOR"', 1),
]

# Locate each `full_results %>%\n  filter(ISO ...` plot block and wrap it. A
# block runs to the blank line before the next top-level statement.
pattern = re.compile(
    r'^full_results %>%\n(?:.*\n)*?  filter\(ISO (==|%in%) ([^\n]*?), scenario == "max_uptake"\) %>%\n(?:(?!\n\n)(?:.*\n))*',
    re.MULTILINE,
)

matches = list(pattern.finditer(s))
if len(matches) != 5:
    print(f"expected 5 per-country plot blocks, found {len(matches)}")
    for m in matches:
        print("---", m.group(0).splitlines()[1][:70])
    sys.exit(1)

out = []
last = 0
for m in matches:
    block = m.group(0)
    isos_expr = m.group(2)
    if m.group(1) == "==":
        isos_r = f"c({isos_expr})"
    else:
        isos_r = isos_expr
    body = block.rstrip("\n")
    # indent the body one level and drop the leading `full_results %>%`
    indented = "\n".join("  " + ln if ln.strip() else ln
                         for ln in body.splitlines())
    wrapped = (
        f"plot_if_present({isos_r}, function() {{\n"
        f"{indented}\n"
        f"}})\n"
    )
    out.append(s[last:m.start()])
    out.append(wrapped)
    last = m.end()
out.append(s[last:])
s = "".join(out)

# insert the helper just before the first wrapped call
anchor = "plot_if_present(c(\"KOR\")"
assert s.count(anchor) == 1
s = s.replace(anchor, HELPER + anchor, 1)

# remove the unmapped size labels that produce "Ignoring unknown labels"
n_size = s.count('       size = "Population\\nWeight") +\n')
s = s.replace('       size = "Population\\nWeight") +\n', '       ) +\n')
n_size2 = s.count('\n       size = "Population\\nWeight"')
s = re.sub(r',\n *size = "Population\\\\nWeight"\)', ')', s)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print(f"wrapped {len(matches)} per-country plot blocks; size-label cleanups {n_size}/{n_size2}")
