#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${SLURM_JOB_ID:-}" ]]; then
  echo 'Run this script through the validated Slurm launcher.' >&2
  exit 2
fi
environment_script=$1
python_bin=$2
manifest=$3
output_dir=$4
revision=$5
model_cache=$6
dtype=$7
dataset_dir=$8
source "$environment_script"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DISABLE_VERSION_CHECK=1
"$python_bin" -c 'import torch; assert torch.cuda.is_available(), "LoRA requires an allocated CUDA GPU"'
"$python_bin" hpc/prepare_lora_config.py --manifest "$manifest" --dataset-dir "$dataset_dir" \
  --output-dir "$output_dir" --model-revision "$revision" --model-cache "$model_cache" --dtype "$dtype"
"$python_bin" -m pip freeze > "$output_dir/runtime-packages.txt"
"$python_bin" -m llamafactory.cli train "$output_dir/lora-config.yaml"
