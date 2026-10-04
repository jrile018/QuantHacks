#!/usr/bin/env bash
# Launch only after the old local finalizer is verified stopped.
set -euo pipefail
umask 077
FULL_ROOT=/home/john-riley/QuantHacks/multi-market-20261003/full-options
cd "$FULL_ROOT"
exec 9>"$FULL_ROOT/full_options_launch.lock"
if ! flock -n 9; then
  printf 'FULL_OPTIONS_ALREADY_RUNNING\n' >&2
  exit 1
fi
mkdir -p logs
exec >logs/full-options-v1.log 2>&1
trap 'job_exit=$?; rm -f -- "$FULL_ROOT/.env"; printf "EXIT_CODE:%s\n" "$job_exit"' EXIT
/home/john-riley/QuantHacks/.venv/bin/python -u \
  scripts/multi_market/finalize_options_remote.py --project "$FULL_ROOT"
