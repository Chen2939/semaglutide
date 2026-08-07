"""Phase 5: compute the headline metric set for one simulation run.

The reconciliation table needs each manuscript number under Run A, Run B and
Run C. Only the FOOD side differs between them: G7 established that `bmi`, both
hazard-ratio columns and every survivor count are bit-identical across the
three, so the mortality chain, `pi(t)` and the survivor-emissions files are
shared and are NOT recomputed per run. Recomputing them would be three runs of
an identical calculation.

Reuses `reference.metrics` rather than restating its metric definitions, so
what is measured here is computed identically to the committed baseline
snapshot. The only thing this script does is repoint
`data_visualization.pipeline.SIMULATION_RDS` before the metrics run.

Usage:
    python -m diagnostics.phase5_run_columns A
    python -m diagnostics.phase5_run_columns B

ASCII only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUN_PATHS = {
    "A": ROOT / "data_result" / "regeneration" / "sim_runA.rds",
    "B": ROOT / "data_result" / "regeneration" / "sim_runB.rds",
    "C": ROOT / "full_simulation_results9.rds",
}
OUTDIR = ROOT / "data_result" / "regeneration"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("label", choices=sorted(RUN_PATHS),
                    help="which simulation artefact to read")
    # Run D is Run C's POPULATION with the section 2.15 ladder, so it reads the
    # same .rds and would otherwise overwrite Run C's output file. It did once.
    ap.add_argument("--out-label", default=None,
                    help="output label if it differs from the input run "
                         "(use --out-label D for the 2.15 ladder pass)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing metrics file")
    a = ap.parse_args()
    out_label = a.out_label or a.label

    path = RUN_PATHS[a.label]
    if not path.is_file():
        raise SystemExit(f"missing run artefact: {path}")

    from data_visualization import pipeline

    print(f"repointing SIMULATION_RDS: {pipeline.SIMULATION_RDS.name} -> {path.name}")
    pipeline.SIMULATION_RDS = path

    from reference import metrics

    snap = metrics.run_configurations()
    got = metrics.measure(snap)

    out = OUTDIR / f"phase5_metrics_run{out_label}.json"
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if out.exists() and not a.force:
        raise SystemExit(
            f"{out.name} already exists. Pass --force to overwrite, or "
            "--out-label to write a different column. Refusing rather than "
            "silently replacing a computed column."
        )
    # numpy scalars are not JSON-serialisable; coerce.
    clean = {}
    for k, v in got.items():
        try:
            clean[k] = float(v)
        except (TypeError, ValueError):
            clean[k] = str(v)
    out.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nwritten: {out}  ({len(clean)} metrics)")

    for k in sorted(clean):
        v = clean[k]
        print(f"  {k:<52} {v if isinstance(v, str) else f'{v:.10f}'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
