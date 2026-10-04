"""
Export daily OHLCV from Databento for every ticker in industries.csv.

Equities : EQUS.MINI  (consolidated US equities, ohlcv-1d)
Options  : OPRA.PILLAR (all listed options on each underlying, ohlcv-1d)
Futures  : GLBX.MDP3  (only for root symbols you pass with --futures-roots)

Usage:
  set DATABENTO_API_KEY=db-xxxx           (Windows cmd)   /  export DATABENTO_API_KEY=db-xxxx  (bash)
  python extract_all_prize.py --dry-run          # cost estimate only
  python extract_all_prize.py                    # run equities + options
  python extract_all_prize.py --futures-roots ES NQ CL
"""
import argparse
import csv
import datetime as dt
import os
import sys
from pathlib import Path

import databento as db

START = "2022-01-01"
BATCH = 100  # symbols per request


def load_tickers(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        seen, out = set(), []
        for r in rows:
            t = (r.get("ticker") or "").strip().upper()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def batches(items, n):
    for i in range(0, len(items), n):
        yield i // n, items[i:i + n]


def pull(client, out_dir, label, dataset, symbols, stype_in, end, dry_run, suffix=""):
    part_dir = out_dir / label
    part_dir.mkdir(parents=True, exist_ok=True)
    total_cost = 0.0
    for idx, chunk in batches(symbols, BATCH):
        part = part_dir / f"{label}_{idx:05d}.csv"
        if part.exists() and not dry_run:
            continue  # resume support
        syms = [s + suffix for s in chunk]
        kwargs = dict(dataset=dataset, symbols=syms, stype_in=stype_in,
                      schema="ohlcv-1d", start=START, end=end)
        if dry_run:
            cost = client.metadata.get_cost(**kwargs)
            total_cost += cost
            print(f"[{label} batch {idx}] {len(syms)} symbols  est. cost ${cost:,.2f}")
            continue
        try:
            store = client.timeseries.get_range(**kwargs)
            df = store.to_df()
            if df.empty:
                print(f"[{label} batch {idx}] no rows")
                part.write_text("")
                continue
            df.to_csv(part)
            print(f"[{label} batch {idx}] {len(df):,} rows -> {part.name}")
        except Exception as e:  # keep going; rerun resumes missing parts
            print(f"[{label} batch {idx}] FAILED: {e}", file=sys.stderr)
    if dry_run:
        print(f"{label} total est. cost: ${total_cost:,.2f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="industries.csv")
    p.add_argument("--out", default="exports/databento_industries")
    p.add_argument("--end", default=dt.date.today().isoformat())
    p.add_argument("--futures-roots", nargs="*", default=[],
                   help="Futures root symbols, e.g. ES NQ CL. Equity tickers have no futures.")
    p.add_argument("--skip-options", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Estimate cost only, no data pulled")
    args = p.parse_args()

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit("Set DATABENTO_API_KEY first.")

    tickers = load_tickers(args.csv)
    print(f"{len(tickers):,} tickers, {START} -> {args.end}")
    client = db.Historical(key)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Equities
    pull(client, out_dir, "equities", "EQUS.MINI", tickers, "raw_symbol", args.end, args.dry_run)

    # Options: parent symbology "TICKER.OPT" returns all option contracts on the underlying
    if not args.skip_options:
        pull(client, out_dir, "options", "OPRA.PILLAR", tickers, "parent", args.end,
             args.dry_run, suffix=".OPT")

    # Futures: only the roots you supply, parent symbology "ROOT.FUT"
    if args.futures_roots:
        roots = [r.upper() for r in args.futures_roots]
        pull(client, out_dir, "futures", "GLBX.MDP3", roots, "parent", args.end,
             args.dry_run, suffix=".FUT")

    print("Done." if not args.dry_run else "Dry run complete.")


if __name__ == "__main__":
    main()
