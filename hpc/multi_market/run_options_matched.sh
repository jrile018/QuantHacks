#!/usr/bin/env bash
# Launch this wrapper in detached tmux. The CLI refuses an existing result dir.
set -euo pipefail
TASK_ROOT=/home/john-riley/QuantHacks/multi-market-20261003
cd "$TASK_ROOT"
mkdir -p logs results
exec >logs/options-v1.log 2>&1
trap 'job_exit=$?; printf "EXIT_CODE:%s\n" "$job_exit"' EXIT
/home/john-riley/QuantHacks/.venv/bin/python \
  scripts/multi_market/run_options_matched_study.py \
  --ingest-dir options-ingest \
  --scores /home/john-riley/projects/geomarket/runs/pit-survivorship/gm-boundaries/scores.parquet \
  --output results/options-matched-v1
