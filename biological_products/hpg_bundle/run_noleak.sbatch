#!/bin/bash
#SBATCH --job-name=bio_noleak
#SBATCH --cpus-per-task=4
#SBATCH --mem=8gb
#SBATCH --time=00:30:00
#SBATCH --output=noleak_%j.log

# Biologics (SIC 2836): the CORRECTED offering short (no look-ahead leak) and the standard tables, on a HiPerGator compute node.
# Submit from biological_products/hpg_bundle in a checkout of the branch biological-products-audit:   sbatch run_noleak.sbatch
# It reruns scripts 44, 45 and 42 from the files in the branch, then compares the result with the numbers committed from the laptop run.
echo "host: $(hostname)   job: $SLURM_JOB_ID   date: $(date)"
module load python
python --version
# same scikit-learn version as the laptop run, so the model picks the same trades (falls back to the module version if this fails)
VENV="$HOME/qh_bio_venv"
if python -m venv --system-site-packages "$VENV" && source "$VENV/bin/activate" && python -m pip install -q "scikit-learn==1.7.2"; then echo "scikit-learn pinned to 1.7.2"; else echo "NOTE: could not pin scikit-learn 1.7.2, using the version of the python module"; fi
python -c "import sklearn, pandas, numpy, matplotlib; print('scikit-learn', sklearn.__version__, '| pandas', pandas.__version__, '| numpy', numpy.__version__, '| matplotlib', matplotlib.__version__)"
BP="$(cd "${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}/.." && pwd)"
cd "$BP/scripts"
echo "code: $(git -C "$BP" rev-parse --short HEAD 2>/dev/null)   folder: $BP"
REF="$BP/hpg_bundle/hpg_results/noleak_ref_${SLURM_JOB_ID:-local}"; mkdir -p "$REF"
cp ../reports/standard_results.csv ../reports/standard_portfolio.csv ../data/fds/offer_trades_v2.csv "$REF/"

echo; echo "################ 1. REAL PRICES + OFFERING MODEL WITHOUT THE LEAK (script 44) ################"
python -W ignore 44_offer_noleak.py || exit 1
echo; echo "################ 2. JOIN THE TRADES WITH THE REAL QUOTES (script 45) ################"
python -W ignore 45_offer_trades_v2.py || exit 1
echo; echo "################ 3. STANDARD RESULTS: P&L, win rate, Sharpe, 95% interval, equity curves (script 42) ################"
python -W ignore 42_standard_results.py || exit 1
echo; echo "################ 4. DOES HIPERGATOR MATCH THE LAPTOP RUN? (script 46) ################"
python -W ignore 46_compare_run.py --ref "$REF"
echo; echo "finished: $(date)"
