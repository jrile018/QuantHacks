#!/bin/bash
#SBATCH --job-name=quanthacks-backtest
#SBATCH --account=YOUR_ACCOUNT        # run `slurmInfo` on HiPerGator to find yours
#SBATCH --qos=YOUR_QOS                # usually the same as the account, or `<account>-b`
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16gb
#SBATCH --time=02:00:00
#SBATCH --output=%x-%j.out

# Usage (from the repo root on HiPerGator):
#   sbatch run_backtest.sbatch                     # full run, default window
#   sbatch --export=ALL,SMOKE=1 run_backtest.sbatch  # 1-event API smoke test
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$PWD}"

TAG="${TAG:-cfo_appointment}"
START="${START:-2024-01-01}"
END="${END:-2025-12-31}"
OUT="${OUT:-data/processed/${TAG}_${SLURM_JOB_ID:-local}}"

module purge
module load python/3.11 2>/dev/null || module load python

[ -f .env ] || { echo "Missing .env with MASSIVE_API_KEY (see .env.example)" >&2; exit 1; }
grep -q "your-key-here" .env && { echo ".env still has the placeholder key" >&2; exit 1; }

if [ ! -d .venv ]; then
  python -m venv .venv
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install -r requirements.txt --quiet
fi

EXTRA=()
[ "${SMOKE:-0}" = "1" ] && EXTRA+=(--max-events 1)

echo "Running: run_all.py --tag $TAG --start $START --end $END --output-dir $OUT ${EXTRA[*]:-}"
.venv/bin/python run_all.py --tag "$TAG" --start "$START" --end "$END" --output-dir "$OUT" "${EXTRA[@]}"
echo "Done. Results in $OUT"
