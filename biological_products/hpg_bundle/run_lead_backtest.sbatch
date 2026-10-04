#!/bin/bash
#SBATCH --job-name=bio_lead_bt
#SBATCH --cpus-per-task=1
#SBATCH --mem=8gb
#SBATCH --time=01:30:00
#SBATCH --output=lead_backtest_%j.log

# Runs the TEAM backtest (QuantHacks run_all.py engine) on the biologics universe, tag public_offering.
# Needs MASSIVE_API_KEY in the environment of the shell that calls sbatch (it is passed to the job, never written to disk).
REPO=${REPO:-/blue/ai-workshop/kkatiyar/QuantHacks}
TAG=${TAG:-public_offering}
MODE=${MODE:-full}
echo "host: $(hostname)   job: $SLURM_JOB_ID   date: $(date)   repo: $REPO   tag: $TAG   mode: $MODE"
cd "${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
module load python
python -c "import pandas, numpy, requests; print('python ok | pandas', pandas.__version__, '| numpy', numpy.__version__)"
if [ -z "$MASSIVE_API_KEY" ]; then echo "MASSIVE_API_KEY is not set. Stop."; exit 1; fi
( cd "$REPO" && echo "team repo commit: $(git log --oneline -1)" )

if [ "$MODE" = "smoke" ]; then
  echo; echo "######## SMOKE TEST: first 8 events only ########"
  python -W ignore lead_backtest_run.py --repo "$REPO" --universe fds_lookup_cik_ticker.csv --tag "$TAG" --start 2024-01-01 --end 2025-12-31 --max-events 8 --out out_smoke_$TAG
else
  echo; echo "######## IN SAMPLE 2024-01-01..2025-12-31 (the team's study window) ########"
  python -W ignore lead_backtest_run.py --repo "$REPO" --universe fds_lookup_cik_ticker.csv --tag "$TAG" --start 2024-01-01 --end 2025-12-31 --out out_insample_$TAG
  echo; echo "######## OUT OF SAMPLE 2026-01-01..2026-08-31 (the team's out-of-sample window) ########"
  python -W ignore lead_backtest_run.py --repo "$REPO" --universe fds_lookup_cik_ticker.csv --tag "$TAG" --start 2026-01-01 --end 2026-08-31 --out out_oos_$TAG
fi
echo; echo "finished: $(date)"
