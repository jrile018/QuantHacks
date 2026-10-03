#!/usr/bin/env bash
# One-step setup for macOS / Linux: ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

# Find a Python 3.10+
PY=""
for cand in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or later is required. Install it from https://www.python.org/downloads/ and re-run." >&2
  exit 1
fi
echo "Using $($PY --version) ($(command -v "$PY"))"

# Virtual environment
if [ ! -d .venv ]; then
  echo "Creating .venv ..."
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"

echo "Installing packages ..."
"$VPY" -m pip install --upgrade pip --quiet
"$VPY" -m pip install -r requirements.txt --quiet

echo "Registering the Jupyter kernel ..."
"$VPY" -m ipykernel install --user --name gator-quant-hacks --display-name "Python (Gator Quant Hacks .venv)" >/dev/null

# API key file
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo ">> Created .env — open it and replace 'your-key-here' with your Massive API key."
elif grep -q "your-key-here" .env; then
  echo
  echo ">> .env still has the placeholder — replace 'your-key-here' with your Massive API key."
else
  echo ".env found."
fi

echo
echo "Done. Start Jupyter with:"
echo "  source .venv/bin/activate && jupyter lab"
echo "then open the notebook and pick the kernel \"Python (Gator Quant Hacks .venv)\"."
