"""Diff the R hazard ladder against the Python one.

Section 2.15.7 requires this BEFORE commit 2 (as a check for a pre-existing
defect -- if they differ, report and stop, do not silently reconcile) and it is
worth re-running AFTER, because the change has to land on both sides.

Method. The R ladder is not re-implemented here. A generated R script sources
`bmi_hazard_ratio()` out of `legacy/R_scripts/Mortality_model2.R`, evaluates it
on a grid this script writes, and writes the results back. That survived the
2.15 change; an earlier version parsed the `case_when` arms into a Python
re-implementation and could not read `~ hr_top(b)`. Evaluating the real
function is both simpler and immune to that.

Also carries G9 assertion 4's Python half: every bin below 40 must be
bit-identical to the pre-2.15 Python code.

ASCII only.
"""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyreadr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_visualization.deterministic_mortality import (  # noqa: E402
    get_raw_bmi_hazard_ratio,
)

RSCRIPT = r"C:\Program Files\R\R-4.4.1\bin\Rscript.exe"
R_FILE = ROOT / "legacy" / "R_scripts" / "Mortality_model2.R"
OUT = ROOT / "diagnostics" / "reports" / "ladder_diff.md"

lines: list[str] = []


def say(s: str = "") -> None:
    print(s)
    lines.append(s)


def eval_r_ladder(x: np.ndarray) -> np.ndarray:
    """Evaluate the REAL R bmi_hazard_ratio() on x, via Rscript."""
    tmp = Path(tempfile.mkdtemp())
    inp, outp, scr = tmp / "in.csv", tmp / "out.csv", tmp / "run.R"
    np.savetxt(inp, x, delimiter=",")
    scr.write_text(f'''
suppressMessages(library(dplyr))
src <- readLines({str(R_FILE)!r})
grab <- function(pattern, nlines = 60) {{
  i <- grep(pattern, src); stopifnot(length(i) == 1)
  j <- i + which(trimws(src[(i+1):(i+nlines)]) == "}}")[1]
  eval(parse(text = paste(src[i:j], collapse = "\\n")), envir = globalenv())
}}
ga <- function(pattern) {{
  i <- grep(pattern, src); stopifnot(length(i) == 1)
  for (n in 0:8) {{
    e <- tryCatch(parse(text = paste(src[i:(i+n)], collapse = "\\n")),
                  error = function(...) NULL)
    if (!is.null(e) && length(e) == 1) {{ eval(e, envir = globalenv()); return(invisible()) }}
  }}
  stop("unparsed: ", pattern)
}}
for (nm in c("^CLASS3_N      <- ", "^CLASS3_SHARE  <- ", "^HR_TOP_BASE   <- ",
             "^HR_PER_5      <- ", "^HR_TOP_K      <- ", "^HR_TOP_ANCHOR <- ")) ga(nm)
ga("^hr_top <- function")
grab("^bmi_hazard_ratio <- function\\\\(b\\\\) \\\\{{")
v <- scan({str(inp)!r}, sep = ",", quiet = TRUE)
# %.17g is the shortest format guaranteed to round-trip an IEEE754 double.
# write.table() ignores options(digits) and emits 15 significant figures, which
# loses the low bits of the CONTINUOUS top band and makes an exact comparison
# report differences of ~7e-15 that are the file format, not the ladder.
writeLines(ifelse(is.na(bmi_hazard_ratio(v)), "NA",
                  sprintf("%.17g", bmi_hazard_ratio(v))), {str(outp)!r})
''', encoding="utf-8")
    r = subprocess.run([RSCRIPT, str(scr)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"R evaluation failed:\n{r.stdout}\n{r.stderr}")
    return np.genfromtxt(outp, dtype=float)


def main() -> int:
    say("# ladder_diff")
    say()
    say("R `bmi_hazard_ratio()` against Python `get_raw_bmi_hazard_ratio()`. "
        "The R side is **evaluated**, not re-implemented: a generated script "
        "sources the real function out of `Mortality_model2.R`.")
    say()

    edges = [18.5, 20.0, 25.0, 27.5, 30.0, 35.0, 40.0]
    pts = set(np.round(np.arange(5.0, 80.0, 0.01), 6).tolist())
    for e in edges + [45.0, 50.0, 55.0, 60.0]:
        pts |= {e, math.nextafter(e, -math.inf), math.nextafter(e, math.inf),
                e - 1e-12, e + 1e-12}
    pts |= {0.0, 13.0, 59.9994, 60.0, 60.7824, 65.0, 1e6}
    grid = np.array(sorted(pts))

    ok = True
    say("## R against Python")
    say()
    say("Bars: **exact** below 40 (step constants); **<= 4 ULP** at and above "
        "40 (continuous, and HR_TOP_ANCHOR itself differs by 1 ULP across the "
        "two runtimes -- see the bar note in the source).")
    say()
    say("| input set | n below 40 | differing | n >= 40 | max ULP | over bar |")
    say("|---|--:|--:|--:|--:|--:|")

    def ulp(a, b):
        ia = np.asarray(a, dtype=np.float64).view(np.int64).copy()
        ib = np.asarray(b, dtype=np.float64).view(np.int64).copy()
        lo = np.int64(np.iinfo(np.int64).min)
        ia[ia < 0] = lo - ia[ia < 0]
        ib[ib < 0] = lo - ib[ib < 0]
        return np.abs(ia - ib)

    # BARS. Below 40 the ladder returns step CONSTANTS, so the two runtimes must
    # agree EXACTLY. At and above 40 it evaluates
    # HR_TOP_ANCHOR * 1.4^((min(b,60)-40)/5), and HR_TOP_ANCHOR itself differs
    # between the runtimes by 1 ULP -- R 1.9773779867007644, Python
    # 1.9773779867007648 -- because K is a four-term reduction and R's sum() and
    # numpy's .sum() associate differently. 1.4^0.2 is bit-identical in both, so
    # pow() is not the cause. That 1 ULP multiplies through, so the top band gets
    # a 4 ULP bar. Both values satisfy the declared |K - 1.395788| < 1e-6.
    #
    # This divergence reaches nothing published: Mortality_model2.R writes only
    # mortality2.rds and final_df_imputed.rds, both superseded, so the Python
    # value is the only one on the production path.
    BAR_TOP_ULP = 4

    def cmp(label, x):
        nonlocal ok
        x = np.asarray(x, dtype=float)
        r = eval_r_ladder(x)
        p = np.asarray(get_raw_bmi_hazard_ratio(x), dtype=float)
        both_nan = np.isnan(r) & np.isnan(p)
        below = (x < 40.0) & ~both_nan
        above = (x >= 40.0) & ~both_nan

        n_below = int((r[below] != p[below]).sum())
        u_above = ulp(r[above], p[above]) if above.any() else np.array([0])
        n_above = int((u_above > BAR_TOP_ULP).sum())
        say(f"| {label} | {int(below.sum()):,} | {n_below} | "
            f"{int(above.sum()):,} | {int(u_above.max())} | {n_above} |")
        if n_below or n_above:
            ok = False
            for i in np.flatnonzero((below & (r != p)))[:5]:
                say(f"    BELOW 40  x={x[i]!r}  R={r[i]!r}  Py={p[i]!r}")

    cmp("boundary / pathological grid", grid)

    sim = list(pyreadr.read_r(str(ROOT / "full_simulation_results9.rds")).values())[0]
    # Subsample the million-row vectors: the R round-trip is per-value and the
    # grid above already covers every boundary densely.
    rng = np.random.default_rng(43)
    for col in ("bmi", "new_bmi"):
        v = sim[col].to_numpy()
        idx = rng.choice(len(v), size=50_000, replace=False)
        top = np.flatnonzero(v >= 40.0)
        take = np.unique(np.concatenate([idx, top[:20_000]]))
        cmp(f"Run C `{col}` (n={len(take):,}, top band over-sampled)", v[take])

    # --- G9 assertion 4, Python half --------------------------------------
    say()
    say("## G9 assertion 4 (Python half): bins below 40 unchanged by 2.15")
    say()

    def old_py(b):
        b = np.asarray(b, dtype=float)
        return np.select(
            [b < 18.5, (b >= 18.5) & (b < 20.0), (b >= 20.0) & (b < 25.0),
             (b >= 25.0) & (b < 27.5), (b >= 27.5) & (b < 30.0),
             (b >= 30.0) & (b < 35.0), (b >= 35.0) & (b < 40.0), b >= 40.0],
            [1.51, 1.13, 1.00, 1.07, 1.20, 1.45, 1.94, 2.76],
            default=np.nan)

    sub = grid[grid < 40.0]
    same = np.array_equal(old_py(sub), get_raw_bmi_hazard_ratio(sub))
    say(f"- grid below 40 (n={len(sub):,}): "
        f"{'identical -- PASS' if same else '**DIFFER -- FAIL**'}")
    ok &= bool(same)
    for col in ("bmi", "new_bmi"):
        v = sim[col].to_numpy()
        v = v[v < 40.0]
        s = np.array_equal(old_py(v), get_raw_bmi_hazard_ratio(v))
        say(f"- real `{col}` below 40 (n={len(v):,}): "
            f"{'identical -- PASS' if s else '**DIFFER -- FAIL**'}")
        ok &= bool(s)
    v = sim["bmi"].to_numpy()
    v = v[v >= 40.0]
    changed = not np.array_equal(old_py(v), get_raw_bmi_hazard_ratio(v))
    say(f"- top band DID change (guards a vacuous pass): "
        f"{'yes -- PASS' if changed else '**no -- FAIL**'}  "
        f"(mean {old_py(v).mean():.4f} -> "
        f"{np.asarray(get_raw_bmi_hazard_ratio(v)).mean():.4f})")
    ok &= changed

    say()
    say(f"## VERDICT: {'AGREE' if ok else 'DIFFER'}")
    if not ok:
        say()
        say("**STOP.** Report rather than silently reconcile.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
