#!/usr/bin/env bash
set -u
cd /home/john-riley/QuantHacks/multi-market-20261003 || exit 1
PY=/home/john-riley/QuantHacks/.venv/bin/python
"$PY" -m pip install --quiet --target ./python_deps zstandard
install_code=$?
if [ "$install_code" -ne 0 ]; then
  echo "DEPENDENCY_INSTALL_FAILED EXIT_CODE:$install_code"
  exit "$install_code"
fi
export PYTHONPATH="$PWD/python_deps:$PWD"
"$PY" -u scripts/multi_market/download_remote_pilot.py --project "$PWD" --jobs request_jobs.json --workers 4
job_code=$?
echo "EXIT_CODE:$job_code"
exit "$job_code"
