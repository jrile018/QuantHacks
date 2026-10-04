#!/bin/bash -l
set -eo pipefail
test -n "${SLURM_JOB_ID:-}" || { echo 'Submit environment setup through Slurm' >&2; exit 2; }
deployment_root=$1
cd "$deployment_root"
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME HF_HUB_OFFLINE TRANSFORMERS_OFFLINE
export CONDA_PKGS_DIRS="$deployment_root/runtime/conda-pkgs"
export PIP_CACHE_DIR="$deployment_root/runtime/pip-cache"
export HF_HOME="$deployment_root/runtime/hf-home"
module load conda/26.7
set -u
test ! -e "$deployment_root/runtime/env" || { echo 'Environment already exists; preserve it and inspect this deployment' >&2; exit 2; }
mamba create --yes --prefix "$deployment_root/runtime/env" --override-channels -c conda-forge python=3.11 pip
python_bin="$deployment_root/runtime/env/bin/python"
"$python_bin" -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu126
"$python_bin" -m pip install -r requirements-gpu-ocr.txt
"$python_bin" -m pip check
"$python_bin" -c 'from transformers import AutoProcessor, GlmOcrForConditionalGeneration; import torch, torchvision; assert torch.__version__.split("+")[0] == "2.9.1"; assert torch.version.cuda == "12.6"; print("Runtime imports verified; GPU availability is checked in the dependent GPU job.")'
"$python_bin" hpc/setup_model_cache.py --cache-dir "$deployment_root/runtime/models" --model both --download > "$deployment_root/runtime/model-snapshots.json"
"$python_bin" - <<'PY'
import json
from pathlib import Path
from transformers import AutoProcessor, AutoTokenizer
snapshots = json.loads(Path('runtime/model-snapshots.json').read_text())
for row in snapshots:
    loader = AutoProcessor if row['model_id'] == 'zai-org/GLM-OCR' else AutoTokenizer
    loader.from_pretrained(row['snapshot_path'], local_files_only=True, trust_remote_code=False)
print('Pinned processors/tokenizers verified locally.')
PY
"$python_bin" -m pip freeze > "$deployment_root/runtime/packages.txt"
printf 'Setup completed for Slurm job %s\n' "$SLURM_JOB_ID"
