#!/usr/bin/env bash
set -Eeuo pipefail

run_dir=${1:?isolated run directory required}
mode=${2:-install}
exec >"$run_dir/$mode.log" 2>&1
trap 'echo "EXIT_CODE:$?"' EXIT
lock=/home/john-riley/.cache/quanthaxs-heavy-compute.lock
mkdir -p "$(dirname "$lock")" "$run_dir"
exec 9>"$lock"
flock -x 9
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export GRAPHIFY_NO_AUTO_REFRESH=1
ulimit -v 4194304

if [[ "$mode" == install ]]; then
  python3 -m venv "$run_dir/venv"
  "$run_dir/venv/bin/python" -m pip install --disable-pip-version-check 'graphifyy==0.9.75'
  "$run_dir/venv/bin/python" -m pip show graphifyy > "$run_dir/package.txt"
  "$run_dir/venv/bin/graphify" --help > "$run_dir/graphify-help.txt" 2>&1
  exit 0
fi

if [[ "$mode" == build ]]; then
  cd "$run_dir"
  "$run_dir/venv/bin/python" - <<'PY'
import hashlib, json, pathlib, sys, zipfile
base = pathlib.Path.cwd()
manifest = json.loads((base / 'source-manifest.json').read_text(encoding='utf-8-sig'))
with zipfile.ZipFile(base / 'source.zip') as archive:
    for member in archive.namelist():
        if member.startswith('/') or '..' in pathlib.PurePosixPath(member).parts:
            raise SystemExit(f'unsafe archive member: {member}')
    archive.extractall(base)
for item in manifest['files']:
    path = base / 'source' / item['snapshot_path']
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item['sha256'] or path.stat().st_size != item['bytes']:
        raise SystemExit(f'source mismatch: {path}')
print(f"Verified {len(manifest['files'])} scoped source files")
PY
  cd "$run_dir/source"
  "$run_dir/venv/bin/graphify" update . --no-cluster
  "$run_dir/venv/bin/graphify" cluster-only . --no-label
  exit 0
fi

echo "unknown mode: $mode" >&2
exit 2
