"""Verify the mortality-source swap: mortality2.rds -> the pickle's own column.

GATES, all declared before the run:

  G1  Coverage assertion in build_mortality_map passes, and the map is
      63 ISO x 72 ages (18-89) x 2 sexes = 9,072 cells.
  G2  The treated-row guard on fillna(0) stays silent at horizon 10.
  G3  Premise behind keeping fillna(0) at all: no non-adherent row changes its
      hazard ratio, hence p_sg == p_bl on those rows and a missing rate cannot
      corrupt their contribution. Bar: 0 rows with hr_conversion_factor != 0.

      Stated first as "new_bmi == bmi", which FAILED on 230,520 rows. Diagnosed
      in diagnostics/diagnose_g3.py: those rows carry individual_effect == 0 and
      weight_diff == 0, and new_bmi differs from bmi by 1.8e-15 to 7.1e-15
      absolute -- at most 2.1e-16 relative, one ULP -- from recomputing BMI off an
      unchanged weight. Their hazard band is identical on all 230,520. So exact
      BMI equality was never the load-bearing condition; a zero hazard change is,
      and it holds exactly. G3b keeps the ULP claim as supporting evidence.
  G4  PARTITION. Against the HEAD code run on the same inputs:
        bucket 1  HLD countries with no floored cells   -> exactly 0.0, 32 ISO
        bucket 2  EST, ISL, LUX, SVN                    -> small change, 4 ISO
        bucket 3  previously zeroed                     -> 0 becomes non-zero, 27 ISO
      and NO country outside buckets 2 and 3 moves at all.

The reference for G4 is the HEAD code, not the committed CSV. The committed blob
already differs from what HEAD produces on 131/1512 cells at 1-2 ULP -- shown by
diagnostics/isolate_refactor.py, where HEAD and the refactor differ from it
identically. Comparing to it would put a 1-2 ULP floor under bucket 1 that has
nothing to do with this change. The committed-CSV comparison is reported too, for
the record.

To re-run, re-create the HEAD reference module first (it is deliberately not left
in the tree, so it cannot be committed by accident):

    git show <pre-swap-rev>:data_visualization/deterministic_mortality.py \
        > data_visualization/_head_dm.py

using the revision before the source swap, then delete it again afterwards.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr

from data_visualization import _head_dm as head
from data_visualization import deterministic_mortality as work

ROOT = Path(__file__).resolve().parent.parent
FLOORED = ["EST", "ISL", "LUX", "SVN"]
DIFFS = [f"diff_Y{y}" for y in range(0, 11)]
VALUE_COLS = DIFFS + ["total_person_years_saved"]
pd.set_option("display.width", 220)

failures: list[str] = []


def gate(label: str, ok: bool) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        failures.append(label)


sim = work.load_inputs()

# ── G1 ────────────────────────────────────────────────────────────────────
print("=" * 78)
print("G1  mortality map coverage")
print("=" * 78)
mmap = work.build_mortality_map(sim)
n_iso = sim["ISO"].nunique()
n_sex = sim["Sex"].nunique()
n_age = work.LOOKUP_AGE_MAX - work.LOOKUP_AGE_MIN + 1
print(f"  cells: {len(mmap):,}   expected {n_iso} x {n_age} x {n_sex} = "
      f"{n_iso * n_age * n_sex:,}")
print(f"  rate min {mmap.min():.6e}   max {mmap.max():.6e}")
gate("map is 9,072 cells with no holes (assertion did not raise)",
     len(mmap) == n_iso * n_age * n_sex == 9072)

# ── G3 ────────────────────────────────────────────────────────────────────
print()
print("=" * 78)
print("G3  non-adherent rows have no hazard change, so a missing rate is inert")
print("=" * 78)
non_adh = ~sim["adheres_to_treatment"].to_numpy(dtype=bool)
bmi_d = (sim["new_bmi"] - sim["bmi"]).to_numpy()
bmi_moved_mask = (bmi_d != 0) & non_adh
hr_base = work.get_raw_bmi_hazard_ratio(sim["bmi"])
hr_sg = work.get_raw_bmi_hazard_ratio(sim["new_bmi"])
hr_conv = (hr_sg / hr_base) - 1
hr_moved = int((hr_conv[non_adh] != 0).sum())
print(f"  non-adherent rows: {int(non_adh.sum()):,}")
print(f"  of those with hr_conversion_factor != 0:   {hr_moved:,}")
gate("G3a no non-adherent row changes its hazard ratio", hr_moved == 0)

rel = np.abs(bmi_d[bmi_moved_mask]) / sim["bmi"].to_numpy()[bmi_moved_mask]
print(f"  of those with new_bmi != bmi:              {int(bmi_moved_mask.sum()):,}")
print(f"    their max |new_bmi - bmi| / bmi:         {rel.max():.3e}  (1 ULP)")
print(f"    their individual_effect range: "
      f"{sim['individual_effect'].to_numpy()[bmi_moved_mask].min():.1e} to "
      f"{sim['individual_effect'].to_numpy()[bmi_moved_mask].max():.1e}")
gate("G3b where new_bmi != bmi on a non-adherent row it is ULP-scale (<1e-12 rel) "
     "with individual_effect == 0",
     bool(rel.max() < 1e-12)
     and float(np.abs(sim["individual_effect"].to_numpy()[bmi_moved_mask]).max()) == 0.0)

# ── run both ──────────────────────────────────────────────────────────────
print()
print("=" * 78)
print("G2  treated-row guard at horizon 10")
print("=" * 78)
new = work.run_deterministic_mortality(sim)
print("  run_deterministic_mortality completed without raising")
ind = work.compute_individual_survival_diffs(sim, horizon=10, missing_columns=True)
miss = ind.attrs["missing_lookups"]
treated = sim["adheres_to_treatment"].to_numpy(dtype=bool)
print(f"  {'year':>4}  {'missing (all rows)':>19}  {'missing (treated)':>18}")
tre_miss = []
for y in range(1, 11):
    m = ind[f"mx_missing_Y{y}"].to_numpy()
    tm = int((m & treated).sum())
    tre_miss.append(tm)
    print(f"  {y:>4}  {miss[y]:>19,}  {tm:>18,}")
print("  Non-zero counts in the left column are the non-adherent rows walked past")
print("  age 89; G3 shows they are inert. The guard fires on the right column.")
gate("no treated row misses its lookup in any year 1-10", max(tre_miss) == 0)

mort_rds = list(pyreadr.read_r(str(ROOT / "mortality2.rds")).values())[0]
old = head.run_deterministic_mortality(sim, mort_rds)

# ── G4 partition ──────────────────────────────────────────────────────────
print()
print("=" * 78)
print("G4  PARTITION against the HEAD code")
print("=" * 78)
m = old.merge(new, on=["ISO", "scenario"], suffixes=("_old", "_new"), how="outer",
              indicator=True)
print(f"  merge: {m['_merge'].value_counts().to_dict()}")
assert (m["_merge"] == "both").all()

old_zero = (
    old.assign(z=old[DIFFS].abs().sum(axis=1) == 0)
    .groupby("ISO")["z"].all()
)
prev_zero = sorted(old_zero.index[old_zero])
hld = sorted(set(old["ISO"]) - set(prev_zero))
hld_clean = sorted(set(hld) - set(FLOORED))
print(f"  bucket 1  HLD, unfloored : {len(hld_clean)} ISO")
print(f"  bucket 2  floored cells  : {len(FLOORED)} ISO -> {FLOORED}")
print(f"  bucket 3  previously zero: {len(prev_zero)} ISO")
print(f"  total {len(hld_clean) + len(FLOORED) + len(prev_zero)} of {old['ISO'].nunique()}")

changed = {}
for _, r in m.iterrows():
    a = np.array([r[f"{c}_old"] for c in VALUE_COLS], dtype=float)
    b = np.array([r[f"{c}_new"] for c in VALUE_COLS], dtype=float)
    nd = int((a != b).sum())
    if nd:
        rel = np.max(np.abs(b - a) / np.where(a != 0, np.abs(a), np.inf))
        changed.setdefault(r["ISO"], []).append((r["scenario"], nd, rel))

moved = sorted(changed)
print()
print(f"  ISO with ANY changed cell: {len(moved)}")
b1_moved = sorted(set(moved) & set(hld_clean))
print(f"  bucket 1 ISO that moved (must be empty): {b1_moved}")
gate(f"bucket 1: all {len(hld_clean)} unfloored HLD countries exactly 0.0",
     len(b1_moved) == 0)
gate("no fifth country moved outside buckets 2 and 3",
     set(moved) <= set(FLOORED) | set(prev_zero))

print()
print("  bucket 2, per (ISO, scenario): cells changed of 12, and max relative change")
for iso in FLOORED:
    for scen, nd, rel in changed.get(iso, []):
        print(f"    {iso} {scen:11s}  cells={nd:>3}/12   max rel change={rel:.3e}")
b2_all_present = all(iso in changed for iso in FLOORED)
b2_rel = max((rel for iso in FLOORED for _, _, rel in changed.get(iso, [])), default=0)
gate("bucket 2: all four floored countries moved", b2_all_present)
gate(f"bucket 2: max relative change is small (<1e-3); measured {b2_rel:.3e}",
     b2_rel < 1e-3)

print()
print("  bucket 3: old exactly zero -> new non-zero")
b3_ok = True
for iso in prev_zero:
    rows = m[m["ISO"] == iso]
    o = rows[[f"{c}_old" for c in DIFFS]].to_numpy(dtype=float)
    nw = rows[[f"{c}_new" for c in DIFFS]].to_numpy(dtype=float)
    if not (np.all(o == 0) and np.any(nw != 0)):
        b3_ok = False
        print(f"    UNEXPECTED {iso}: old all-zero={np.all(o == 0)} "
              f"new any-non-zero={np.any(nw != 0)}")
gate(f"bucket 3: all {len(prev_zero)} previously-zeroed countries now non-zero", b3_ok)

# ── for the record: committed CSV ─────────────────────────────────────────
print()
print("=" * 78)
print("For the record: HEAD code vs the committed CSV (pre-existing, not this change)")
print("=" * 78)
committed = pd.read_csv(work.OUTPUT_FILE)
mc = committed.merge(old, on=["ISO", "scenario"], suffixes=("_c", "_h"))
nd = 0
wr = 0.0
for c in VALUE_COLS:
    a = mc[f"{c}_c"].to_numpy(float)
    b = mc[f"{c}_h"].to_numpy(float)
    nd += int((a != b).sum())
    nz = a != 0
    if nz.any():
        wr = max(wr, float(np.max(np.abs(b[nz] - a[nz]) / np.abs(a[nz]))))
print(f"  cells differing: {nd}/{len(mc) * len(VALUE_COLS)}   worst relative: {wr:.3e}")
print("  (diff_Y0 is identically 0 in both and is excluded from the relative figure)")

# ── headline movements ────────────────────────────────────────────────────
print()
print("=" * 78)
print("Headline person-years and year-10 survivors, old vs new")
print("=" * 78)
print(f"  {'scenario':<12}{'quantity':<28}{'old':>18}{'new':>18}{'ratio':>9}")
for scen in ("max_uptake", "mod_uptake"):
    o = old[old["scenario"] == scen]
    n = new[new["scenario"] == scen]
    for label, col in (("person-years saved (10y)", "total_person_years_saved"),
                       ("extra survivors at Y10", "diff_Y10")):
        ov, nv = o[col].sum(), n[col].sum()
        print(f"  {scen:<12}{label:<28}{ov:>18,.0f}{nv:>18,.0f}{nv / ov:>9.4f}")

nz_old = old.groupby("ISO")[DIFFS].apply(lambda d: d.abs().to_numpy().sum() > 0)
nz_new = new.groupby("ISO")[DIFFS].apply(lambda d: d.abs().to_numpy().sum() > 0)
print()
print(f"  ISO with non-zero person-years: old {int(nz_old.sum())}, new {int(nz_new.sum())}")

new.to_csv(ROOT / "diagnostics" / "person_years_new.csv", index=False)
old.to_csv(ROOT / "diagnostics" / "person_years_old.csv", index=False)

print()
print("=" * 78)
if failures:
    print(f"{len(failures)} GATE(S) FAILED:")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("All gates passed.")
