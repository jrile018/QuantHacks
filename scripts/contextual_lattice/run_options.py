#!/usr/bin/env python3
"""Audit fixed selected option contracts against one-session stock movement.

Run large source scans on the remote host in detached tmux. This is a
descriptive, previously inspected sample, never a trading or IV backtest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.contextual_lattice.options import build_audit, summarize_audit


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _score_subset(path: Path, events: pd.DataFrame) -> pd.DataFrame:
    data = ds.dataset(path, format="parquet")
    dates = sorted(set(events["t_pre"].astype(str)))
    date_type = data.schema.field("date").type
    if pa.types.is_date(date_type):
        dates = [pd.Timestamp(day).date() for day in dates]
    elif pa.types.is_timestamp(date_type):
        dates = [pd.Timestamp(day).to_pydatetime() for day in dates]
    predicate = (ds.field("ticker").isin(sorted(set(events["ticker"].astype(str))))
                 & ds.field("date").isin(dates)
                 & (ds.field("view") == "B")
                 & (ds.field("estimator") == "mahalanobis"))
    return data.to_table(columns=["ticker", "date", "view", "estimator", "depth"],
                         filter=predicate).to_pandas()


def _price_subset(path: Path, events: pd.DataFrame) -> pd.DataFrame:
    data = ds.dataset(path, format="parquet")
    first = min(events["t_0"].astype(str))
    last = (pd.Timestamp(max(events["t_0"].astype(str))) + pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    tickers = sorted(set(events["ticker"].astype(str)))
    date_type = data.schema.field("date").type
    if pa.types.is_date(date_type):
        first, last = pd.Timestamp(first).date(), pd.Timestamp(last).date()
    elif pa.types.is_timestamp(date_type):
        first, last = pd.Timestamp(first).to_pydatetime(), pd.Timestamp(last).to_pydatetime()
    predicate = (ds.field("ticker").isin(tickers) & (ds.field("date") >= first)
                 & (ds.field("date") <= last))
    result = data.to_table(columns=["ticker", "date", "close", "adjclose"], filter=predicate).to_pandas()
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    return result


def run_study(ingest_dir: Path, native_prices: Path, scores: Path,
              matched_summary: Path, output: Path,
              equity_predictions: Path | None = None) -> dict:
    """Write a fail-closed audit with original diagnostic gate preserved."""
    ingest_dir, native_prices, scores, matched_summary, output = map(
        Path, (ingest_dir, native_prices, scores, matched_summary, output))
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    manifest_path = ingest_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("stage") != "gm-options-ingest" or manifest.get("schema_version") != "1.0.0":
        raise ValueError("unexpected native options manifest")
    sources = {name: ingest_dir / f"{name}.parquet" for name in ("events", "contracts", "quotes")}
    sources.update(native_prices=native_prices, scores=scores,
                   matched_summary=matched_summary, ingest_manifest=manifest_path,
                   runner=Path(__file__), audit_module=ROOT / "src/contextual_lattice/options.py")
    if equity_predictions is not None:
        sources["equity_predictions"] = Path(equity_predictions)
    hashes = {name: _sha(path) for name, path in sources.items()}
    for name in ("events", "contracts", "quotes"):
        if manifest.get("output_hashes", {}).get(sources[name].name) != hashes[name]:
            raise ValueError(f"native ingest hash mismatch: {name}")
    events = pq.read_table(sources["events"]).to_pandas()
    contracts = pq.read_table(sources["contracts"]).to_pandas()
    quotes = pq.read_table(sources["quotes"]).to_pandas()
    prices = _price_subset(native_prices, events)
    scores_frame = _score_subset(scores, events)
    predictions = pd.read_csv(equity_predictions) if equity_predictions is not None else None
    matched = json.loads(matched_summary.read_text(encoding="utf-8"))
    rows = build_audit(events, contracts, quotes, prices, scores_frame, predictions)
    summary = summarize_audit(rows, matched)
    summary["stock_target"] = "absolute log return of native adjusted-close marks, t_0 to next panel session"
    summary["movement_forecast_status"] = ("diagnostic_only" if predictions is not None
                                           else "blocked_no_clock_qualified_forecast")
    protocol = {
        "stage": "contextual-lattice-options-exploratory-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_paths": {name: str(path.resolve()) for name, path in sources.items()},
        "source_sha256": hashes,
        "selection": "original fixed event/contract universe only; cannot prove unbiased full-chain opportunity",
        "lattice_score": "exact ticker,t_pre; View B mahalanobis; no date fill",
        "stock_target": summary["stock_target"],
        "native_close": "separate observed close from Yahoo quote/0/close; unadjusted/split continuity and quote synchronization not certified",
        "quotes": "same fixed ATM call and put, sampled CBBO 15:55-16:00 ET interval-end marks at t_0 and next session, positive sizes; original update freshness unknown",
        "forecast_clock": "optional stock movement predictions are diagnostics only; must be independently verified available before option entry to support pricing hypothesis",
        "excluded_claims": ["implied volatility", "maturity-matched option mispricing", "ask-to-bid executable fills", "net option profit"],
        "pricing_blockers": ["stock/option mark synchronization", "original quote update freshness",
                              "dated rates and dividends", "exercise and contract lifecycle",
                              "untouched holdout and full chain selection"],
        "minimum_distinct_events": 20,
        "source_primary_distinct_events": summary["source_primary_distinct_events"],
        "economic_profit_claim": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "protocol.json", protocol)
    _write_json(output / "summary.json", summary)
    rows.to_csv(output / "row_audit.csv", index=False)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingest-dir", type=Path, required=True)
    parser.add_argument("--native-prices", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--matched-summary", type=Path, required=True)
    parser.add_argument("--equity-predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = run_study(args.ingest_dir, args.native_prices, args.scores,
                        args.matched_summary, args.output, args.equity_predictions)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
