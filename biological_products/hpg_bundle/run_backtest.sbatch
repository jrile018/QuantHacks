#!/bin/bash
#SBATCH --job-name=bio_backtest
#SBATCH --cpus-per-task=1
#SBATCH --mem=4gb
#SBATCH --time=00:20:00
#SBATCH --output=backtest_%j.log

# Biologics (SIC 2836) strategy backtests. Runs on a HiPerGator compute node.
echo "host: $(hostname)   job: $SLURM_JOB_ID   date: $(date)"
module load python
python --version
python -c "import pandas, numpy; print('pandas', pandas.__version__, 'numpy', numpy.__version__)" || python -m pip install --user pandas numpy
cd "${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}/scripts"

echo; echo "################ 1. OFFERING STRATEGY: Sharpe, 95% interval, audit ################"
python -W ignore 40_offer_strategy_pnl.py --data ../data

echo; echo "################ 2. TRIAL STAGE STRATEGY, DESIGN HALF (in sample) ################"
python -W ignore 39_strategy_audit.py --data ../data

echo; echo "################ 3. TRIAL STAGE STRATEGY, HOLDOUT HALF (out of sample, same rule, replication run) ################"
python -W ignore 39_strategy_audit.py --data ../data --set holdout --confirm_holdout

echo; echo "finished: $(date)"
