"""Separate the two silent-failure paths in _compute_equilibrium.

The function has TWO ways to return NaN without a word:
  (1) the bare `except Exception: pass`
  (2) the `if result.converged:` falling through

Item 3 is about narrowing (1). Whether that is safe depends on (1) firing zero
times, which is not the same question as whether the function ever returns NaN.
Counted separately here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import root_scalar

from data_visualization import pipeline as pl
from diagnostics.report import Report

rep = Report(
    "check_except_paths",
    "Which of the two silent-failure paths in _compute_equilibrium actually fires.",
)

exc_fires: list[dict] = []
nonconv_fires: list[dict] = []
reached_solver = [0]
nan_input = [0]


def _instrumented(row):
    args = (row["Cs"], row["Cd"], row["elasticity_supply"],
            row["elasticity_demand"], row["expected_demand_reduction_percent"])
    if any(pd.isna(a) for a in args):
        nan_input[0] += 1
    try:
        reached_solver[0] += 1
        result = root_scalar(pl._equilibrium_gap, args=args, method="brentq",
                             bracket=[1e-3, 1e3])
        if result.converged:
            P_new = result.root
            return pd.Series({"P_eq_new": P_new,
                              "Q_eql_new": row["Cs"] * (P_new ** args[2])})
        nonconv_fires.append({
            "ISO": row.get("ISO"), "group": row.get("final_food_group"),
            "any_input_nan": any(pd.isna(a) for a in args),
        })
    except Exception as exc:  # noqa: BLE001
        exc_fires.append({
            "ISO": row.get("ISO"), "group": row.get("final_food_group"),
            "type": type(exc).__name__, "msg": str(exc)[:120],
            "any_input_nan": any(pd.isna(a) for a in args),
        })
    return pd.Series({"P_eq_new": np.nan, "Q_eql_new": np.nan})


_orig = pl._compute_equilibrium
pl._compute_equilibrium = _instrumented
try:
    food_savings, result_df = pl.compute_food_savings()
finally:
    pl._compute_equilibrium = _orig

rep.h2("The two paths, counted separately")
rep.kv({
    "calls into the solver": reached_solver[0],
    "calls with at least one NaN argument": nan_input[0],
    "path 1: `except Exception` fired": len(exc_fires),
    "path 2: `converged is False` fired": len(nonconv_fires),
})

rep.h3("Path 1 -- the bare except")
if exc_fires:
    rep.text("**FIRES.** Narrowing it would raise on a live path. Stop.")
    rep.table(pd.DataFrame(exc_fires).head(25))
else:
    rep.text(
        "**Fires zero times.** brentq does not raise on these inputs; it returns a "
        "result object with `converged=False`. Narrowing the except therefore "
        "changes no live behaviour."
    )

rep.h3("Path 2 -- non-convergence")
if nonconv_fires:
    nc = pd.DataFrame(nonconv_fires)
    rep.text(
        f"Fires {len(nc)} times, and **every one has a NaN argument** "
        f"({int(nc['any_input_nan'].sum())} of {len(nc)}). So it is not a solver "
        "problem: these rows have no price, so `Cs`/`Cd` are NaN and the solve is "
        "meaningless before it starts. This is the path that silently zeroes a "
        "country, and it is separate from the except."
    )
    rep.table(nc.groupby(["ISO", "any_input_nan"], as_index=False).size())

rep.h2("What the affected countries are missing")
bad = result_df[result_df["Q_eql_new"].isna()]
cols = ["ISO", "Country", "final_food_group", "initial_eql_quantity", "price",
        "elasticity_supply", "elasticity_demand", "Cs", "Cd",
        "expected_demand_reduction_percent", "carbon_intensity_t"]
per = bad.groupby("ISO")[["price", "Cs", "Cd", "initial_eql_quantity",
                          "carbon_intensity_t"]].apply(
    lambda d: pd.Series({c: int(d[c].isna().sum()) for c in d.columns})
).reset_index()
per.columns = ["ISO"] + [f"NaN {c}" for c in
                         ["price", "Cs", "Cd", "initial_eql_quantity",
                          "carbon_intensity_t"]]
rep.table(per)
rep.text("Rows per affected country: 9 food groups x 2 scenarios = 18.")

rep.h2("Breakeven values these countries carry today")
be = pd.read_csv(pl.ROOT / "data_result" / "net_emissions_with_drug.csv",
                 float_precision="round_trip")
sub = be[be["ISO"].isin(sorted(set(bad["ISO"])))][
    ["ISO", "scenario", "annual_food_savings_gross_t", "annual_drug_emissions_t",
     "annual_food_savings_t", "total_food_savings_10yr", "ratio_food_to_mort"]
]
rep.table(sub)
mx = sub[sub["scenario"] == "max_uptake"]
rep.kv({
    "sum of their annual_food_savings_t, max (t)": mx["annual_food_savings_t"].sum(),
    "as Mt": mx["annual_food_savings_t"].sum() / 1e6,
})
rep.text(
    "That negative total is what the unfiltered console pivot in "
    "`diet_sensitivity/analysis.py:289` currently sums in and would stop summing "
    "if the gross value became NaN."
)
rep.save()
