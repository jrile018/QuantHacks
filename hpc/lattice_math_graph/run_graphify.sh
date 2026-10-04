#!/usr/bin/env bash
set -u

snapshot_dir="$1"
graphify_bin="/home/john-riley/quanthaxs-architecture-graph/9dcbe287-4d69-429a-acd6-774e49e0d22e/venv/bin/graphify"
lock_file="/home/john-riley/.cache/quanthaxs-heavy-compute.lock"

exec 9>"$lock_file"
flock -x 9
ulimit -v 4194304
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
cd "$snapshot_dir" || exit 2

"$graphify_bin" update . --no-cluster --force
status=$?
if [ "$status" -eq 0 ]; then
  "$graphify_bin" cluster-only . --no-label
  status=$?
fi
printf 'EXIT_CODE:%s\n' "$status"
exit "$status"
