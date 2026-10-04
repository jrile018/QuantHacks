#!/usr/bin/env bash
set -euo pipefail
test -n "${SLURM_JOB_ID:-}" || exit 2
source "$1"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
"$2" hpc/diagnose_glm_ocr.py --model-cache "$3" --output-dir "$4" --manifest "$5"
