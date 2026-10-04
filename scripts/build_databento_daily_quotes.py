"""Reduce Databento OPRA CBBO-1m files to daily option bid/ask marks.

The output preserves bids and asks. It never substitutes quote midpoints for
trade closes or interprets the last trade size as daily volume.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from contextlib import contextmanager
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa


NEW_YORK = ZoneInfo("America/New_York")
TICKER = re.compile(r"^O:([A-Z0-9.]+)(\d{6}[CP]\d{8})$")
OUTPUT_COLUMNS = (
    "contract_ticker", "session", "mark_time_utc", "mark_time_et", "bid", "ask", "mid",
    "bid_size", "ask_size", "spread", "relative_spread", "minutes_before_1600",
    "source_job_id",
)


def raw_symbol_from_ticker(ticker: str) -> str:
    match = TICKER.fullmatch(ticker)
    if not match:
        raise ValueError(f"Invalid Massive option ticker: {ticker}")
    return match.group(1).ljust(6) + match.group(2)


def _canonical_symbol(symbol: str) -> str:
    return symbol.replace(" ", "").replace(".", "").strip()


def aggregate_rows(rows, symbol_to_ticker: dict[str, str], job_id: str):
    """Keep the last valid regular-session quote for each contract and date."""
    mapping = {_canonical_symbol(k): v for k, v in symbol_to_ticker.items()}
    marks: dict[tuple[str, str], dict] = {}
    mark_times: dict[tuple[str, str], datetime] = {}
    stats = {"total_records": 0, "matched_records": 0, "accepted_records": 0,
             "outside_session": 0, "invalid_quote": 0, "unknown_symbol": 0}
    for row in rows:
        stats["total_records"] += 1
        ticker = mapping.get(_canonical_symbol(row.get("symbol", "")))
        if ticker is None:
            stats["unknown_symbol"] += 1
            continue
        stats["matched_records"] += 1
        ts = datetime.fromisoformat(row["ts_recv"].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            raise ValueError("Databento timestamp has no timezone")
        eastern = ts.astimezone(NEW_YORK)
        clock = eastern.time()
        if eastern.weekday() >= 5 or not (time(9, 30) <= clock <= time(16, 0)):
            stats["outside_session"] += 1
            continue
        try:
            bid, ask = float(row["bid_px_00"]), float(row["ask_px_00"])
            bid_size, ask_size = int(row["bid_sz_00"]), int(row["ask_sz_00"])
        except (KeyError, TypeError, ValueError):
            stats["invalid_quote"] += 1
            continue
        if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask < 1_000_000
                and 0 < bid_size < 100_000_000 and 0 < ask_size < 100_000_000):
            stats["invalid_quote"] += 1
            continue
        stats["accepted_records"] += 1
        session = eastern.date().isoformat()
        key = (ticker, session)
        if key in mark_times and mark_times[key] >= ts:
            continue
        mark_times[key] = ts
        mid = (bid + ask) / 2
        minutes_before_close = (datetime.combine(eastern.date(), time(16), tzinfo=NEW_YORK)
                                - eastern).total_seconds() / 60
        marks[key] = {
            "contract_ticker": ticker, "session": session,
            "mark_time_utc": ts.isoformat().replace("+00:00", "Z"),
            "mark_time_et": eastern.isoformat(), "bid": bid, "ask": ask, "mid": mid,
            "bid_size": bid_size, "ask_size": ask_size, "spread": ask - bid,
            "relative_spread": (ask - bid) / mid, "minutes_before_1600": minutes_before_close,
            "source_job_id": job_id,
        }
    return marks, stats


@contextmanager
def _csv_rows(path: Path):
    with pa.OSFile(str(path), "rb") as raw:
        with pa.CompressedInputStream(raw, "zstd") as decompressed:
            with io.TextIOWrapper(decompressed, encoding="utf-8", newline="") as text:
                yield csv.DictReader(text)


def build(project: Path, job_id: str) -> dict:
    legs_path = project / "data" / "processed" / "cfo-2024-2025-massive" / "option_legs.csv"
    with legs_path.open(newline="", encoding="utf-8-sig") as stream:
        legs = list(csv.DictReader(stream))
    symbol_to_ticker = {raw_symbol_from_ticker(row["contract_ticker"]): row["contract_ticker"]
                        for row in legs}
    raw_dir = project / "data" / "raw" / "databento" / job_id
    files = sorted(raw_dir.glob("*.csv.zst"))
    if not files:
        raise FileNotFoundError(f"No Databento CSV files in {raw_dir}")

    def all_rows():
        for path in files:
            with _csv_rows(path) as rows:
                yield from rows

    marks, stats = aggregate_rows(all_rows(), symbol_to_ticker, job_id)
    output_dir = project / "data" / "processed" / "cfo-2024-2025-databento" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "option_quotes_daily.csv"
    with output_file.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(marks[key] for key in sorted(marks))
    required_marks = {(row["contract_ticker"], row["selection_date"]) for row in legs}
    covered_marks = required_marks & marks.keys()
    groups: dict[tuple[str, str, str], set[str]] = {}
    for row in legs:
        key = (row["event_id"], row["bucket"], row["selection_date"])
        groups.setdefault(key, set()).add(row["contract_ticker"])
    complete_groups = sum(len(tickers) == 8 and all((ticker, key[2]) in marks for ticker in tickers)
                          for key, tickers in groups.items())
    summary = {
        "job_id": job_id, "input_files": len(files), "requested_contracts": len(symbol_to_ticker),
        "daily_quote_marks": len(marks), "selection_contract_dates": len(required_marks),
        "selection_contract_dates_covered": len(covered_marks),
        "event_bucket_groups": len(groups), "event_bucket_groups_complete": complete_groups,
        "stats": stats, "output": str(output_file),
    }
    (output_dir / "quote_coverage.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[1], args.job_id), indent=2))
