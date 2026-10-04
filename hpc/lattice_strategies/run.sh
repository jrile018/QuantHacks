#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/john-riley/QuantHacks/lattice-strategies-20261004
cd "$ROOT"
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 ARROW_NUM_THREADS=2
exec 9>/home/john-riley/.cache/quanthaxs-heavy-compute.lock
printf 'WAITING_FOR_SHARED_LOCK\n'
flock 9
printf 'ACQUIRED_SHARED_LOCK\n'
ulimit -v 4194304
trap 'code=$?; printf "EXIT_CODE:%s\n" "$code"' EXIT
.venv/bin/python -m pytest tests/test_lattice*.py -q > tests.log 2>&1
if [[ ${1:-all} == preflight ]]; then exit 0; fi
.venv/bin/python scripts/lattice_strategies/run_study.py \
  --prices /home/john-riley/projects/geomarket/runs/pit-survivorship/gm-ingest/prices.parquet \
  --config configs/experiments/lattice-strategies-v1.json --environment environment.txt \
  --output results/strategies-v1
