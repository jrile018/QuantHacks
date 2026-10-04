#!/bin/bash
#SBATCH --job-name=feature-backtest
#SBATCH --account=YOUR_ACCOUNT        # run `slurmInfo` to find yours
#SBATCH --qos=YOUR_QOS
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8gb
#SBATCH --time=00:30:00
#SBATCH --output=%x-%j.out

# Submit from the repo root:  sbatch run_feature_backtest.sbatch
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"
PS=data/packaged_software

for f in $PS/final/feature_matrix_qualified.csv \
         $PS/extracts/company_coverage/daily_bars_reviewed.csv \
         $PS/output/factor_returns_daily.csv; do
  [ -s "$f" ] || { echo "Missing input: $f" >&2; exit 1; }
done

module purge
module load python/3.11 2>/dev/null || module load python

if [ ! -d .venv ]; then
  python -m venv .venv
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install pandas numpy matplotlib --quiet
fi

.venv/bin/python $PS/backtest_feature_strategies.py
echo "Done. Outputs in data/processed/feature_strategies/ (REPORT.md, strategy_summary.csv, ...)"
