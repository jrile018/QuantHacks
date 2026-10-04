#!/bin/bash
#SBATCH --job-name=bio_lead_sig
#SBATCH --cpus-per-task=1
#SBATCH --mem=8gb
#SBATCH --time=01:00:00
#SBATCH --output=lead_signal_%j.log

# Runs OUR offering signal (155 flagged days) through the TEAM backtest engine, unchanged. Needs MASSIVE_API_KEY in the environment.
REPO=${REPO:-/blue/ai-workshop/kkatiyar/QuantHacks}
echo "host: $(hostname)   job: $SLURM_JOB_ID   date: $(date)   repo: $REPO"
cd "${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
module load python
if [ -z "$MASSIVE_API_KEY" ]; then echo "MASSIVE_API_KEY is not set. Stop."; exit 1; fi
( cd "$REPO" && echo "team repo commit: $(git log --oneline -1)" )
python -W ignore lead_backtest_signal.py --repo "$REPO" --events offer_signal_events.csv --out out_signal_offer
echo; echo "finished: $(date)"
