"""Go down industries.csv one ticker at a time and pull daily settlements for any futures that exist.

For each ticker: resolve TICKER.FUT on GLBX.MDP3 (free). If it doesn't resolve, log it as no
futures and move on. If it does, check the cost (free), pull daily settlements (stat type 3),
and write one CSV per ticker. The run stops once the cumulative cost passes --budget.
Re-running skips tickers already written, so it can resume.

Usage:
  python extract_ticker_futures.py --dry-run
  python extract_ticker_futures.py --budget 5
"""
import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

import databento as db
import pandas as pd

from extract_futures_settles import DATASET, SCHEMA, SETTLEMENT_STAT_TYPE, START, load_key

OUT = Path("exports/futures_by_ticker")
LOG = OUT / "_status.csv"


def tickers(csv_path: str):
    seen, out = set(), []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            if t and t not in seen and re.fullmatch(r"[A-Z0-9]{1,6}", t):
                seen.add(t)
                out.append(t)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="industries.csv")
    p.add_argument("--end", default=dt.date.today().isoformat())
    p.add_argument("--budget", type=float, default=float("inf"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    client = db.Historical(load_key())
    OUT.mkdir(parents=True, exist_ok=True)
    done = {f.stem.removesuffix("_settles") for f in OUT.glob("*_settles.csv")}
    status = []
    spent = 0.0

    for t in tickers(args.csv):
        if t in done:
            continue
        kw = dict(dataset=DATASET, symbols=[f"{t}.FUT"], stype_in="parent",
                  schema=SCHEMA, start=START, end=args.end)
        try:
            cost = client.metadata.get_cost(**kw)
        except Exception as e:
            status.append({"ticker": t, "result": "no_futures", "detail": str(e).splitlines()[0][:120]})
            continue
        if spent + cost > args.budget:
            status.append({"ticker": t, "result": "stopped_budget", "detail": f"cost {cost:.4f}"})
            break
        if args.dry_run:
            status.append({"ticker": t, "result": "would_pull", "detail": f"cost {cost:.4f}"})
            continue
        try:
            df = client.timeseries.get_range(**kw).to_df()
        except Exception as e:
            status.append({"ticker": t, "result": "error", "detail": str(e).splitlines()[0][:120]})
            continue
        spent += cost
        settles = df[df["stat_type"] == SETTLEMENT_STAT_TYPE] if len(df) else df
        if settles.empty:
            status.append({"ticker": t, "result": "no_settlements", "detail": ""})
            continue
        settles.to_csv(OUT / f"{t}_settles.csv")
        status.append({"ticker": t, "result": "written", "detail": f"{len(settles)} rows, cost {cost:.4f}"})
        print(f"{t}: {len(settles)} settlement rows")

    if status:
        mode = "a" if LOG.exists() else "w"
        with LOG.open(mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ticker", "result", "detail"])
            if mode == "w":
                w.writeheader()
            w.writerows(status)
    from collections import Counter
    print("summary:", dict(Counter(s["result"] for s in status)), f"spent ${spent:.4f}")


if __name__ == "__main__":
    sys.exit(main())
