"""Daily settlement prices for futures roots from Databento (GLBX.MDP3).

Uses the statistics schema and keeps only stat_type 3 (settlement price), so the output is the
official daily settle per contract, not a bar close. Parent symbology pulls every listed contract
for the root (ES.FUT returns all ES expiries).

Usage:
  python extract_futures_settles.py --roots ES MES --dry-run     # cost estimate only
  python extract_futures_settles.py --roots ES MES               # pull and write CSV

API key: DATABENTO_API_KEY from the environment, or a DATABENTO_API_KEY line in .env.
The key is never printed.
"""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import databento as db
import pandas as pd

DATASET = "GLBX.MDP3"
SCHEMA = "statistics"
SETTLEMENT_STAT_TYPE = 3   # Databento StatType.SETTLEMENT_PRICE
START = "2022-01-01"


def load_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if key:
        return key
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABENTO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("No DATABENTO_API_KEY in environment or .env")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--roots", nargs="+", required=True, help="Futures roots, e.g. ES MES")
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=dt.date.today().isoformat())
    p.add_argument("--out", default="exports/futures_settles")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    client = db.Historical(load_key())
    symbols = [f"{r.upper()}.FUT" for r in args.roots]
    kwargs = dict(dataset=DATASET, symbols=symbols, stype_in="parent",
                  schema=SCHEMA, start=args.start, end=args.end)

    if args.dry_run:
        cost = client.metadata.get_cost(**kwargs)
        print(f"{symbols} {args.start} -> {args.end}: estimated cost ${cost:,.2f}")
        return

    store = client.timeseries.get_range(**kwargs)
    df = store.to_df()
    if df.empty:
        sys.exit("No statistics rows returned")
    settles = df[df["stat_type"] == SETTLEMENT_STAT_TYPE].copy()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for root in args.roots:
        sub = settles[settles["symbol"].str.startswith(root.upper())]
        path = out / f"{root.upper()}_daily_settles.csv"
        sub.to_csv(path)
        print(f"{root.upper()}: {len(sub):,} settlement rows -> {path}")


if __name__ == "__main__":
    main()
