#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/john-riley/QuantHacks/lattice-strategies-20261004
cd "$ROOT"
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
exec 9>/home/john-riley/.cache/quanthaxs-heavy-compute.lock
flock 9
ulimit -v 4194304
trap 'code=$?; printf "EXIT_CODE:%s\n" "$code"' EXIT
python3 -m venv .venv
.venv/bin/python -m pip install numpy pandas pyarrow scipy scikit-learn pytest
.venv/bin/python -m pip freeze > environment.txt
