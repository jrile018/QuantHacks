#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/john-riley/QuantHacks/contextual-lattice-20261003
PY=/home/john-riley/QuantHacks/.venv/bin/python
MODE=${1:-all}
cd "$ROOT"
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 ARROW_NUM_THREADS=2
mkdir -p /home/john-riley/.cache
exec 9>/home/john-riley/.cache/quanthaxs-heavy-compute.lock
printf 'WAITING_FOR_SHARED_LOCK\n'
flock 9
printf 'ACQUIRED_SHARED_LOCK\n'
ulimit -v 4194304
trap 'code=$?; printf "EXIT_CODE:%s\n" "$code"' EXIT
"$PY" -m unittest discover -s tests -p 'test_contextual_lattice*.py' -v > tests.log 2>&1
if [[ "$MODE" != study ]]; then
  "$PY" scripts/contextual_lattice/export_sec_context.py --cache /home/john-riley/projects/geomarket/data/raw/sec_submissions --output inputs/sec-context-v1
fi
if [[ "$MODE" == preflight ]]; then exit 0; fi
"$PY" scripts/contextual_lattice/run_contextual_study.py --prior-root /home/john-riley/QuantHacks/multi-market-20261003 --sec-context inputs/sec-context-v1 --config configs/experiments/contextual-lattice-v1.json --output results/contextual-v1
"$PY" scripts/contextual_lattice/run_options.py --ingest-dir /home/john-riley/QuantHacks/multi-market-20261003/full-options/results/gm-options-ingest --native-prices /home/john-riley/projects/geomarket/runs/pit-survivorship/gm-ingest/prices.parquet --scores /home/john-riley/projects/geomarket/runs/pit-survivorship/gm-boundaries/scores.parquet --matched-summary /home/john-riley/QuantHacks/multi-market-20261003/full-options/results/options-matched-v1/summary.json --equity-predictions results/contextual-v1/equities_movement_option_adapter.csv --output results/options-context-v1
