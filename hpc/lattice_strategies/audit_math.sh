#!/usr/bin/env bash
set -Eeuo pipefail
run_dir=${1:?audit run directory required}
exec >"$run_dir/audit.log" 2>&1
trap 'echo "EXIT_CODE:$?"' EXIT
mkdir -p /home/john-riley/.cache
exec 9>/home/john-riley/.cache/quanthaxs-heavy-compute.lock
flock -x 9
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 ARROW_NUM_THREADS=2
ulimit -v 4194304
cd "$run_dir"
tar -xzf source.tar.gz
sha256sum source.tar.gz > source-archive.sha256
PY=/home/john-riley/QuantHacks/lattice-strategies-20261004/.venv/bin/python
"$PY" -m pip freeze > environment.txt
"$PY" -m pytest tests/audit/test_signal_math.py tests/audit/test_boundary_math.py -q > tests.log 2>&1
NATIVE=stat-arb
EIGEN=/home/john-riley/projects/geomarket/build/linux-gcc-release/vcpkg_installed/x64-linux/include/eigen3
g++ -std=c++20 -O0 -fno-fast-math -I"$EIGEN" -I"$NATIVE/third_party" -I"$NATIVE/libs/gm-core/include" -I"$NATIVE/libs/gm-geometry/include" -I"$NATIVE/libs/gm-signals/include" \
  tests/audit/native_spectral_witness.cpp "$NATIVE/libs/gm-geometry/src/correlation.cpp" "$NATIVE/libs/gm-geometry/src/shrinkage.cpp" "$NATIVE/libs/gm-geometry/src/rie.cpp" "$NATIVE/libs/gm-geometry/src/rmt.cpp" "$NATIVE/libs/gm-signals/src/ou_fit.cpp" -o native-math-witness
./native-math-witness > native-witness.json
PYTHONPATH=. "$PY" scripts/lattice_strategies/audit_frozen_targets.py \
  --input /home/john-riley/QuantHacks/lattice-strategies-20261004/results/strategies-v1/residual_forecasts.csv.gz \
  --output frozen-target-audit.json
echo 'Native witness, focused algebra tests and frozen-target re-scoring completed; zero model refits.'
