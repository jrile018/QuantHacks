#!/usr/bin/env bash
set -euo pipefail
test -n "${SLURM_JOB_ID:-}" || { echo 'Submit this job with sbatch' >&2; exit 2; }
environment_script=$1
python_bin=$2
model_cache=$3
output_dir=$4
manifest=$5
filings=$6
source "$environment_script"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
"$python_bin" hpc/run_document_pilot.py --model-cache "$model_cache" --output-dir "$output_dir" \
  --manifest "$manifest" --filings "$filings"
