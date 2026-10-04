#!/usr/bin/env bash
# Detached remote runner. Raw purchased files stay immutable.
set -u
set -o pipefail
study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$study_root" || exit 1
mkdir -p logs results
study_output="${1:-results/futures-v1}"
study_log="${2:-logs/futures-v1.log}"
export PYTHONPATH="$study_root/python_deps:$study_root${PYTHONPATH:+:$PYTHONPATH}"
study_python="${STUDY_PYTHON:-/home/john-riley/QuantHacks/.venv/bin/python}"
"$study_python" -u scripts/multi_market/run_futures_study.py \
  --raw-root data/raw/databento \
  --jobs-json request_jobs.json \
  --config configs/experiments/multi-market-v1.json \
  --output "$study_output" > "$study_log" 2>&1
study_exit=$?
printf '\nEXIT_CODE:%s\n' "$study_exit" >> "$study_log"
exit "$study_exit"
