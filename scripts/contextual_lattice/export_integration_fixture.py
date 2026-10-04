#!/usr/bin/env python3
"""Export a tiny verified 2024 producer handoff from an existing contextual run.

Development evidence only. The original rows are retained; this script never
fits a model, backdates processing, or supplies a trading identity or fill.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds


CANDIDATES = ("baseline", "context_only", "context_lattice", "lattice_only", "zero", "simple_substitute")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(_jsonable(value), sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def _id(prefix: str, *parts: object) -> str:
    raw = json.dumps([str(part) for part in parts], separators=(",", ":"))
    return prefix + "_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _day(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _clock(value) -> pd.Timestamp:
    instant = pd.Timestamp(value)
    if instant.tzinfo is None:
        raise ValueError("clock_without_timezone")
    return instant.tz_convert("UTC")


def _four_pm(day: str) -> pd.Timestamp:
    return (pd.Timestamp(day).tz_localize("America/New_York")
            + pd.Timedelta(hours=16)).tz_convert("UTC")


def _source_hashes(run_dir: Path, native_prices: Path) -> tuple[dict, dict]:
    paths = {name: run_dir / f"{name}.csv" for name in
             ("all_opportunities", "all_candidate_decisions", "all_paired_predictions")}
    paths.update(run_manifest=run_dir / "manifest.json", run_events=run_dir / "events.jsonl",
                 native_prices=native_prices, producer_code=Path(__file__))
    hashes = {name: _sha(path) for name, path in paths.items()}
    manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    events = [json.loads(line) for line in paths["run_events"].read_text(encoding="utf-8").splitlines()]
    completed = [event for event in events if event.get("stage") == "comparisons_complete"]
    if len(completed) != 1:
        raise ValueError("run lacks one comparisons_complete lifecycle event")
    registered = completed[0].get("outputs", {})
    for name in ("all_opportunities", "all_candidate_decisions", "all_paired_predictions"):
        if registered.get(f"{name}.csv", {}).get("sha256") != hashes[name]:
            raise ValueError(f"run output hash mismatch: {name}.csv")
    return hashes, manifest


def _prices(path: Path, opportunities: pd.DataFrame) -> dict:
    names = sorted(set(opportunities["ticker"].astype(str)))
    dates = sorted(set(opportunities["date"].map(_day)) |
                   set(opportunities["next_date"].map(_day)))
    data = ds.dataset(path, format="parquet")
    field_type = data.schema.field("date").type
    if pa.types.is_date(field_type):
        dates = [pd.Timestamp(day).date() for day in dates]
    elif pa.types.is_timestamp(field_type):
        dates = [pd.Timestamp(day).to_pydatetime() for day in dates]
    table = data.to_table(columns=["ticker", "date", "close", "adjclose"],
                          filter=ds.field("ticker").isin(names) & ds.field("date").isin(dates))
    frame = table.to_pandas()
    frame["date"] = frame["date"].map(_day)
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("duplicate native price ticker/date")
    return {(str(row.ticker), str(row.date)): row for row in frame.itertuples(index=False)}


def _validated_row(opportunity: dict, ledger: pd.DataFrame, predictions: pd.DataFrame,
                   prices: dict, manifest: dict, processed_at: str) -> dict:
    ticker, day, nxt = (str(opportunity["ticker"]), _day(opportunity["date"]),
                        _day(opportunity["next_date"]))
    if not day < nxt or not day.startswith("2024") or not nxt.startswith("2024"):
        raise ValueError("outside_2024_decision_outcome")
    if opportunity.get("target_units") != "fractional_adjusted_close_change":
        raise ValueError("unexpected_target_units")
    decision = _clock(opportunity["decision_at"])
    feature = _clock(opportunity["feature_available_at"])
    context = _clock(opportunity["context_available_at"])
    available = _clock(opportunity["label_available_at"])
    if decision != _four_pm(day) or feature > decision or context > decision or available < _four_pm(nxt):
        raise ValueError("invalid_clock_or_information_cutoff")
    if str(opportunity.get("outcome_observed")).lower() not in {"true", "1"}:
        raise ValueError("outcome_not_observed")
    key = lambda frame: frame[frame["ticker"].astype(str).eq(ticker)
                              & frame["date"].map(_day).eq(day)
                              & frame["next_date"].map(_day).eq(nxt)]
    paired = key(predictions)
    if len(paired) != 1:
        raise ValueError("missing_or_ambiguous_paired_prediction")
    paired_row = paired.iloc[0].to_dict()
    candidate_rows = key(ledger)
    if len(candidate_rows) != len(CANDIDATES) or set(candidate_rows["candidate"]) != set(CANDIDATES):
        raise ValueError("incomplete_or_ambiguous_candidate_ledger")
    for item in candidate_rows.to_dict("records"):
        candidate = item["candidate"]
        if (not math.isfinite(float(item["prediction"]))
                or not math.isclose(float(item["prediction"]), float(paired_row[candidate]),
                                    rel_tol=1e-9, abs_tol=1e-12)):
            raise ValueError("candidate_prediction_mismatch")
    p0, p1 = prices.get((ticker, day)), prices.get((ticker, nxt))
    if p0 is None or p1 is None:
        raise ValueError("missing_native_price_pair")
    adj0, adj1 = float(p0.adjclose), float(p1.adjclose)
    if not (math.isfinite(adj0) and math.isfinite(adj1) and adj0 > 0 and adj1 > 0):
        raise ValueError("invalid_native_adjusted_close")
    target = adj1 / adj0 - 1
    if not math.isclose(target, float(opportunity["target"]), rel_tol=1e-8, abs_tol=1e-10):
        raise ValueError("target_reconstruction_mismatch")
    if not math.isclose(target, float(paired_row["target"]), rel_tol=1e-8, abs_tol=1e-10):
        raise ValueError("paired_target_mismatch")
    source_version = str(opportunity["source_version"])
    if source_version != str(manifest.get("config", {}).get("experiment_id")):
        raise ValueError("source_version_mismatch")
    trial = _id("trial", source_version, "equities", "catchup")
    opportunity_id = _id("opportunity", source_version, ticker, day, nxt)
    decision_id = _id("decision", opportunity_id, decision.isoformat())
    ledger_items = sorted(candidate_rows.to_dict("records"), key=lambda row: row["candidate"])
    return {"ids": {"producer_trial_id": trial, "producer_opportunity_id": opportunity_id,
                    "producer_decision_id": decision_id,
                    "producer_candidate_ids": {r["candidate"]: _id("candidate", decision_id, r["candidate"])
                                               for r in ledger_items}},
            "raw_opportunity": opportunity, "raw_candidate_ledger": ledger_items,
            "raw_paired_prediction": paired_row,
            "coordination": {"market_group": "equities", "hypothesis": "catchup",
                             "decision_date": day, "next_date": nxt,
                             "information_cutoff_at_utc": decision.isoformat(),
                             "outcome_end_at_utc": _four_pm(nxt).isoformat(),
                             "target_available_at_utc": available.isoformat(),
                             "actual_export_processed_at_utc": processed_at,
                             "assumed_historical_close_availability": "replay assumption: same-session 16:00 ET close mark at decision; execution unverified",
                             "source_price_kind": "adjustedclose",
                             "adjusted_close_entry": adj0, "adjusted_close_outcome": adj1,
                             "native_close_entry": float(p0.close), "native_close_outcome": float(p1.close),
                             "target_reconstructed": target,
                             "current_adjustment_vintage": "unknown",
                             "source_version": source_version,
                             "context_source_hash": manifest["sources"].get("SEC_filings", {}).get("sha256"),
                             "feature_source_hash": manifest["sources"].get("equity_features", {}).get("sha256"),
                             "config_sha256": manifest.get("config_sha256"),
                             "security_id": None, "cik": None, "first_public_at_utc": None,
                             "source_received_at_utc": None, "source_retrieved_at_utc": None,
                             "futures_contract_id": None, "futures_root": None,
                             "identity_status": "blocked_unverified", "action_status": "blocked",
                             "actual_historical_receipt_status": "unobserved"}}


def export_fixture(run_dir: Path, native_prices: Path, output: Path, max_rows: int = 3) -> dict:
    run_dir, native_prices, output = Path(run_dir), Path(native_prices), Path(output)
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    if not 1 <= max_rows <= 3:
        raise ValueError("max_rows must be between 1 and 3")
    hashes, manifest = _source_hashes(run_dir, native_prices)
    opportunities = pd.read_csv(run_dir / "all_opportunities.csv")
    ledger = pd.read_csv(run_dir / "all_candidate_decisions.csv")
    predictions = pd.read_csv(run_dir / "all_paired_predictions.csv")
    for frame in (opportunities, ledger, predictions):
        if not {"market_group", "hypothesis", "ticker", "date", "next_date"} <= set(frame):
            raise ValueError("source lacks producer grain or trial fields")
    selected = opportunities[(opportunities.market_group == "equities") &
                             (opportunities.hypothesis == "catchup") &
                             (opportunities.status == "evaluated")].copy()
    selected = selected[selected.date.map(_day).str.startswith("2024") &
                        selected.next_date.map(_day).str.startswith("2024")]
    selected = selected.sort_values(["date", "ticker", "next_date"])
    if selected.duplicated(["ticker", "date", "next_date"]).any():
        raise ValueError("duplicate producer opportunity grain")
    ledger = ledger[(ledger.market_group == "equities") & (ledger.hypothesis == "catchup")]
    predictions = predictions[(predictions.market_group == "equities") & (predictions.hypothesis == "catchup")]
    native = _prices(native_prices, selected) if not selected.empty else {}
    processed_at = datetime.now(timezone.utc).isoformat()
    rows, quarantine = [], []
    for opportunity in selected.to_dict("records"):
        if len(rows) >= max_rows:
            break
        try:
            rows.append(_validated_row(opportunity, ledger, predictions, native, manifest, processed_at))
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            quarantine.append({"ticker": str(opportunity.get("ticker")),
                               "decision_date": _day(opportunity["date"]),
                               "next_date": _day(opportunity["next_date"]),
                               "reason": str(error)})
    fixture = {"stage": "descriptive_development_handoff", "schema_version": 1,
               "evidence_window": "2024-only subset of previously exposed 2024/2025 development diagnostics",
               "rows": rows, "fit_performed": False, "promotion": False,
               "consumer_gate": "verify hashes, grain, clocks, target math, source treatment and identity before any fit"}
    quarantined = {"rows": quarantine, "count": len(quarantine)}
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "fixture.json", fixture)
    _write_json(output / "quarantine.json", quarantined)
    output_hashes = {name: _sha(output / name) for name in ("fixture.json", "quarantine.json")}
    result = {"stage": "producer_handoff_export", "schema_version": 1,
              "created_at_utc": processed_at, "source_sha256": hashes,
              "source_run_config_sha256": manifest.get("config_sha256"),
              "run_source_sha256": {name: record.get("sha256")
                                    for name, record in manifest.get("sources", {}).items()},
              "output_sha256": output_hashes, "verified_rows": len(rows),
              "quarantined_rows": len(quarantine), "requested_max_rows": max_rows,
              "status": "ready_for_consumer_audit" if len(rows) == max_rows else "insufficient_verified_2024_rows",
              "no_fit_or_orders": True}
    _write_json(output / "manifest.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--native-prices", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(export_fixture(args.run_dir, args.native_prices, args.output,
                                    max_rows=args.max_rows), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
