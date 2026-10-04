#!/bin/bash
#SBATCH --job-name=bio_v3
#SBATCH --cpus-per-task=4
#SBATCH --mem=8gb
#SBATCH --time=00:40:00
#SBATCH --output=v3_%j.log

# Biologics (SIC 2836): FROZEN RUN of the corrected offering short (dataset v2, quote clock, cash ledger) on a HiPerGator compute node,
# then a strict comparison with the laptop run that is committed in the branch. Every stage fails the job on error (set -e, pipefail).
# Submit from biological_products/hpg_bundle in a checkout of the branch:   sbatch run_noleak.sbatch
set -euo pipefail
echo "host: $(hostname)   job: ${SLURM_JOB_ID:-local}   date: $(date)"
module load python
python --version
VENV="$HOME/qh_bio_venv"
if python -m venv --system-site-packages "$VENV" && source "$VENV/bin/activate" && python -m pip install -q "scikit-learn==1.7.2"; then echo "scikit-learn pinned to 1.7.2"; else echo "NOTE: could not pin scikit-learn 1.7.2, using the module version"; fi
python -c "import sklearn, pandas, numpy, matplotlib; print('scikit-learn', sklearn.__version__, '| pandas', pandas.__version__, '| numpy', numpy.__version__, '| matplotlib', matplotlib.__version__)"
BP="$(cd "${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}/.." && pwd)"
cd "$BP/scripts"
echo "code: $(git -C "$BP" rev-parse HEAD 2>/dev/null)   tree: $(git -C "$BP" status --porcelain 2>/dev/null | grep -v '^??' | wc -l) modified tracked files (0 = clean)   folder: $BP"
echo "input hashes (sha256):"; sha256sum ../data/fds/fds_features.csv ../data/fds/fds_labels.csv ../data/fds/fds_options.csv ../data/fds/stock_trades_real_v3.csv ../data/raw/prices.csv ../data/raw/splits.csv | sed 's/^/  /'
REF="$BP/hpg_bundle/hpg_results/v3_ref_${SLURM_JOB_ID:-local}"; mkdir -p "$REF"
cp ../reports/standard_results.csv ../reports/standard_portfolio.csv ../reports/ledger_daily.csv ../reports/ledger_trades.csv ../reports/ledger_summary.csv ../data/fds/offer_trades_v3.csv ../data/fds/offer_strategy_trades_v3.csv "$REF/"
echo "reference = the committed laptop outputs, copied before the run; their hashes:"; sha256sum "$REF"/* | sed 's/^/  /'

echo; echo "################ 1. OFFERING MODEL ON DATASET V2 + MATCHED CONTROLS (script 48) ################"
python -W ignore 48_offer_v3.py
echo; echo "################ 2. JOIN TRADES WITH REAL QUOTES, QUOTE CLOCK (script 45) ################"
python -W ignore 45_offer_trades_v2.py --version v3
echo; echo "################ 3. STANDARD PER-TRADE TABLES, CHARTS (script 42) ################"
python -W ignore 42_standard_results.py
echo; echo "################ 4. AUDIT NUMBERS (script 47) ################"
python -W ignore 47_offer_audit.py --version v3
echo; echo "################ 5. CASH LEDGER, SELF TEST THEN REAL RUN (script 49) ################"
python -W ignore 49_ledger.py --selftest
python -W ignore 49_ledger.py --trades offer_strategy_trades_v3.csv --quotes stock_trades_real_v3.csv
echo; echo "################ 6. STRICT COMPARISON WITH THE COMMITTED LAPTOP RUN (script 46) ################"
python -W ignore 46_compare_run.py --fixtures
python -W ignore 46_compare_run.py --ref "$REF"
echo; echo "output hashes (sha256):"; sha256sum ../reports/standard_results.csv ../reports/standard_portfolio.csv ../reports/ledger_daily.csv ../reports/ledger_trades.csv ../data/fds/offer_trades_v3.csv ../data/fds/offer_strategy_trades_v3.csv | sed 's/^/  /'
echo; echo "finished OK: $(date)"
