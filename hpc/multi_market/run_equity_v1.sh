#!/usr/bin/env bash
set -euo pipefail
run_root=/home/john-riley/QuantHacks/multi-market-20261003
python_bin=/home/john-riley/QuantHacks/.venv/bin/python
cd "$run_root"
export OPENBLAS_NUM_THREADS=2
export OMP_NUM_THREADS=2
trap 'job_code=$?; printf "EXIT_CODE:%s\n" "$job_code" >> "$run_root/logs/equity-v1.log"' EXIT
"$python_bin" scripts/multi_market/run_numeric_study.py \
  --prices /home/john-riley/projects/geomarket/runs/pit-survivorship/gm-ingest/prices.parquet \
  --output results/native-equity-v1 \
  --benchmark __equal_weight_panel__ \
  --start 2018-01-01 --end 2026-01-06 --train-start 2018-01-01 \
  --holdout-start 2024-01-01 --holdout-end 2025-12-31 --window 63 \
  --source-note 'Previously inspected native equities; frozen 12-name internal equal-weight factor; broad-market benchmark absent; historical eligibility and adjustment vintages unaudited'
