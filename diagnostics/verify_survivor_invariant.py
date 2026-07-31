"""INVARIANT, declared before the run: pi must not touch the survivor side.

_survivor_food_factor is built from BASELINE tonnage (initial_eql_quantity) and
the carbon intensities, not from the reduction, so survival weighting the shock
must leave it bit-identical. If it moves, pi has leaked into the survivor path and
the food:survivor ratio would be double-counting the correction.

Bar: exactly 0 differing cells against the existing
data_result/survivor_food_factor.csv, compared as raw field text.

That file is gitignored -- it is not in the data_result whitelist -- so there is no
HEAD blob to anchor to. The reference is therefore the copy already on disk, which
predates both the mortality source swap and pi. That is a sound anchor for exactly
this invariant: the factor depends on FAOSTAT tonnage, carbon intensity and the
all-ages energy pool, none of which either change touched, so the pre-existing file
should reproduce regardless of which of the two ran since.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_visualization.pipeline import build_survivor_food_factor

ROOT = Path(__file__).resolve().parent.parent
REL = "data_result/survivor_food_factor.csv"

path = ROOT / REL
if not path.is_file():
    raise SystemExit(f"No reference copy at {path} -- cannot check the invariant.")
committed = path.read_text()
print(f"Reference: existing {REL} ({len(committed):,} bytes)")

print("Rebuilding the survivor food factor under survival weighting...")
new = build_survivor_food_factor()

old_lines = committed.replace("\r\n", "\n").strip("\n").split("\n")
new_text = (ROOT / REL).read_text().replace("\r\n", "\n").strip("\n")
new_lines = new_text.split("\n")

print()
print(f"  committed rows: {len(old_lines)}   regenerated rows: {len(new_lines)}")
if len(old_lines) != len(new_lines):
    raise SystemExit("row count changed -- INVARIANT FAILED")
ndiff = 0
ncells = 0
first = []
for i, (lo, ln) in enumerate(zip(old_lines, new_lines)):
    fo, fn = lo.split(","), ln.split(",")
    ncells += len(fo)
    for j, (a, b) in enumerate(zip(fo, fn)):
        if a != b:
            ndiff += 1
            if len(first) < 8:
                first.append((i, old_lines[0].split(",")[j], a, b))
print(f"  cells compared: {ncells:,}   differing: {ndiff}")
for row, col, a, b in first:
    print(f"    row {row} {col}: committed={a!r} new={b!r}")
print()
if ndiff:
    raise SystemExit("INVARIANT FAILED: pi has leaked into the survivor path")
print("INVARIANT HELD: survivor food factor bit-identical (exactly 0).")
