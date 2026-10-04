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
source "$environment_script"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
"$python_bin" scripts/run_document_batch.py --manifest "$manifest" \
  --output-dir "$output_dir" --engine glm --model-revision "$revision" \
  --model-cache "$model_cache" --dtype "$dtype" --device cuda:0
