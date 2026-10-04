"""Native Lattice Parquet ingest and causal study for QuantHaxs option contracts.

The existing equity geometry stays an equity model. This module adds option
artifacts and joins only same-session, pre-event View B equity scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday,
    USLaborDay, USMartinLutherKingJr, USMemorialDay, USPresidentsDay,
    USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.options_bridge import _read_csv


SOURCE_TABLES = ("events", "results", "capacity", "option_legs", "option_bars")
ESTIMATORS = ("mahalanobis", "kde", "fastmcd")
EVENT_COLUMNS = ("cik", "accession_number", "ticker", "event_date", "t_pre", "t_0")
RESULT_COLUMNS = ("ticker", "event_date", "t_0", "bucket", "entry", "entry_date")
CAPACITY_COLUMNS = ("ticker", "event_date", "entry_date", "bucket", "strategy")
LEG_COLUMNS = ("event_id", "bucket", "leg_code", "contract_ticker", "underlying_ticker",
               "contract_type", "strike", "expiration_date", "selection_date", "spot_pre",
               "shares_per_contract")
BAR_COLUMNS = ("contract_ticker", "session", "close", "volume")
QUOTE_COLUMNS = ("contract_ticker", "session", "mark_time_utc", "mark_time_et",
                 "bid", "ask", "mid", "bid_size", "ask_size", "spread",
                 "relative_spread", "minutes_before_1600", "source_job_id")
RESULT_NUMERIC = {"sessions_held", "dte_sessions", "S_entry", "S_exit",
                  "realized", "implied_move", "implied_scaled", "otm", "stock",
                  "long_call", "covered_call", "protective_put", "collar",
                  "cash_secured_put", "ratio"}
CAPACITY_NUMERIC = {"capital_per_contract", "max_loss_per_contract", "gross_max_loss_per_contract",
                    "round_trip_cost_per_contract", "capital_contracts", "risk_contracts",
                    "volume_contracts", "least_leg_volume", "capacity_contracts"}


class NYSEHolidays(AbstractHolidayCalendar):
    """Full-day closures matching QuantHaxs' option-study calendar."""

    rules = [
        Holiday("New Year's Day", month=1, day=1,
                observance=lambda d: d + pd.Timedelta(days=1) if d.weekday() == 6 else d),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
        Holiday("National day of mourning, President Carter", year=2025, month=1, day=9),
    ]


def _date(value: str, label: str) -> date:
    if len(value) != 10:
        raise ValueError(f"invalid {label}: {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def _number(value: str, label: str, *, positive: bool = False, allow_negative: bool = False) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc
    if not math.isfinite(result) or (result <= 0 if positive else result < 0 and not allow_negative):
        raise ValueError(f"invalid {label}: {value!r}")
    return result


def _optional_number(value: str, label: str, *, allow_negative: bool = False) -> float:
    return math.nan if value == "" else _number(value, label, allow_negative=allow_negative)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    return pa.Table.from_arrays([pa.array([row[field.name] for row in rows], type=field.type)
                                 for field in schema], schema=schema)


def _string_schema(columns: list[str]) -> pa.Schema:
    return pa.schema([(name, pa.string()) for name in columns])


def _write_manifest(path: Path, stage: str, run_id: str, hashes: dict[str, str], **details: object) -> dict:
    hashes = {**hashes, "tools/options_native.py": _sha(Path(__file__))}
    manifest = {"schema_version": "1.0.0", "stage": stage, "run_id": run_id,
                "git_commit": "unknown", "compiler_id": "Python/pyarrow",
                "build_type": "research", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "wall_time_seconds": 0.0, "status": "ok", "input_hashes": hashes, **details}
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _empty_destination(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"output directory is not empty: {path}")


def ingest_options(study_dir: Path, output_dir: Path, run_id: str,
                   quote_path: Path | None = None) -> dict:
    """Validate a QuantHaxs export and write typed, Lattice-readable Parquet tables."""
    study_dir, output_dir = Path(study_dir), Path(output_dir)
    _empty_destination(output_dir)
    producer = json.loads((study_dir / "manifest.json").read_text(encoding="utf-8"))
    source_hashes = {"manifest.json": _sha(study_dir / "manifest.json")}
    source = {}
    requirements = {"events": EVENT_COLUMNS, "results": RESULT_COLUMNS,
                    "capacity": CAPACITY_COLUMNS, "option_legs": LEG_COLUMNS,
                    "option_bars": BAR_COLUMNS}
    for name in SOURCE_TABLES:
        path = study_dir / f"{name}.csv"
        header, rows = _read_csv(path, requirements[name])
        expected = producer.get("exported_tables", {}).get(name)
        source_hashes[path.name] = _sha(path)
        if not expected or expected.get("sha256") != source_hashes[path.name]:
            raise ValueError(f"source hash mismatch or missing for {path.name}")
        if expected.get("rows") != len(rows):
            raise ValueError(f"source row count mismatch for {path.name}")
        source[name] = (header, rows)

    events, by_key, by_day = [], {}, {}
    for row in source["events"][1]:
        pre, event_day, post = (_date(row[name], name) for name in ("t_pre", "event_date", "t_0"))
        if not pre < event_day < post:
            raise ValueError(f"invalid event date ordering for {row['ticker']}")
        cik = row["cik"]
        if not cik.isdigit() or not row["accession_number"] or not row["ticker"]:
            raise ValueError("invalid event identity")
        event_id = f"CIK:{cik.zfill(10)}:{row['accession_number']}:{row['ticker']}"
        key = (row["ticker"], row["event_date"], row["t_0"])
        day_key = (row["ticker"], row["event_date"])
        if key in by_key or day_key in by_day:
            raise ValueError(f"ambiguous event: {day_key}")
        item = {"event_id": event_id, "cik": cik.zfill(10),
                **{name: row[name] for name in EVENT_COLUMNS if name != "cik"}}
        events.append(item)
        by_key[key], by_day[day_key] = item, item
    if producer.get("event_count") != len(events):
        raise ValueError("producer event_count mismatch")
    by_id = {event["event_id"]: event for event in events}

    contracts, contract_metadata, leg_keys = [], {}, set()
    for row in source["option_legs"][1]:
        event = by_id.get(row["event_id"])
        if not event:
            raise ValueError(f"option leg has no matching event: {row['event_id']}")
        if row["selection_date"] != event["t_pre"] or row["underlying_ticker"] != event["ticker"]:
            raise ValueError("option leg selection date or underlying mismatch")
        if _date(row["expiration_date"], "expiration_date") <= _date(row["selection_date"], "selection_date"):
            raise ValueError("option expiry is not after selection")
        if row["contract_type"] not in ("call", "put"):
            raise ValueError("invalid contract_type")
        if row["shares_per_contract"] != "100":
            raise ValueError(f"missing or nonstandard contract multiplier: {row['contract_ticker']}")
        key = (row["event_id"], row["bucket"], row["leg_code"])
        if key in leg_keys:
            raise ValueError(f"duplicate option leg: {key}")
        leg_keys.add(key)
        meta = tuple(row[name] for name in ("underlying_ticker", "contract_type", "strike",
                                            "expiration_date", "shares_per_contract"))
        ticker = row["contract_ticker"]
        if ticker in contract_metadata and contract_metadata[ticker] != meta:
            raise ValueError(f"conflicting contract metadata: {ticker}")
        contract_metadata[ticker] = meta
        contracts.append({**row, "strike": _number(row["strike"], "strike", positive=True),
                          "spot_pre": _number(row["spot_pre"], "spot_pre", positive=True),
                          "shares_per_contract": 100})

    bars, bar_keys = [], set()
    for row in source["option_bars"][1]:
        key = (row["contract_ticker"], row["session"])
        if key in bar_keys:
            raise ValueError(f"duplicate option bar: {key}")
        bar_keys.add(key)
        if row["contract_ticker"] not in contract_metadata:
            raise ValueError(f"bar references unknown contract: {key}")
        if _date(row["session"], "bar session") > _date(contract_metadata[row["contract_ticker"]][3], "expiry"):
            raise ValueError(f"bar after contract expiry: {key}")
        bars.append({"contract_ticker": row["contract_ticker"], "session": row["session"],
                     "close": _number(row["close"], "close", positive=True),
                     "volume": _number(row["volume"], "volume")})

    quotes, quote_keys = [], set()
    if quote_path is not None:
        quote_path = Path(quote_path)
        _, quote_rows = _read_csv(quote_path, QUOTE_COLUMNS)
        source_hashes["option_quotes_daily.csv"] = _sha(quote_path)
        for row in quote_rows:
            key = (row["contract_ticker"], row["session"])
            if key in quote_keys:
                raise ValueError(f"duplicate option quote: {key}")
            quote_keys.add(key)
            if row["contract_ticker"] not in contract_metadata:
                raise ValueError(f"quote references unknown contract: {key}")
            if _date(row["session"], "quote session") > _date(contract_metadata[row["contract_ticker"]][3], "expiry"):
                raise ValueError(f"quote after contract expiry: {key}")
            try:
                mark_utc = datetime.fromisoformat(row["mark_time_utc"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"invalid quote timestamp: {key}") from exc
            if mark_utc.tzinfo is None or mark_utc.astimezone(ZoneInfo("America/New_York")).date().isoformat() != row["session"]:
                raise ValueError(f"quote timestamp/session mismatch: {key}")
            bid = _number(row["bid"], "bid", positive=True)
            ask = _number(row["ask"], "ask", positive=True)
            mid = _number(row["mid"], "mid", positive=True)
            spread = _number(row["spread"], "spread")
            relative_spread = _number(row["relative_spread"], "relative_spread")
            if (ask < bid or not math.isclose(mid, (bid + ask) / 2, abs_tol=1e-6)
                    or not math.isclose(spread, ask - bid, abs_tol=1e-6)
                    or not math.isclose(relative_spread, spread / mid, abs_tol=1e-6)):
                raise ValueError(f"inconsistent option quote: {key}")
            bid_size = _number(row["bid_size"], "bid_size", positive=True)
            ask_size = _number(row["ask_size"], "ask_size", positive=True)
            minutes = _number(row["minutes_before_1600"], "minutes_before_1600")
            if not row["source_job_id"]:
                raise ValueError(f"missing quote source job: {key}")
            quotes.append({**row, "bid": bid, "ask": ask, "mid": mid,
                           "bid_size": bid_size, "ask_size": ask_size,
                           "spread": spread, "relative_spread": relative_spread,
                           "minutes_before_1600": minutes})

    contract_groups = {(c["event_id"], c["bucket"]) for c in contracts}
    outcome_rows = []
    for row in source["results"][1]:
        event = by_key.get((row["ticker"], row["event_date"], row["t_0"]))
        if event is None or (event["event_id"], row["bucket"]) not in contract_groups:
            raise ValueError("outcome has no matching event/bucket")
        if row["entry"] not in ("pre", "post") or row["entry_date"] != event["t_pre" if row["entry"] == "pre" else "t_0"]:
            raise ValueError("outcome entry date mismatch")
        outcome_rows.append({"event_id": event["event_id"], **{
            name: _optional_number(value, name, allow_negative=True) if name in RESULT_NUMERIC else value
            for name, value in row.items()}})
    capacity_rows = []
    for row in source["capacity"][1]:
        event = by_day.get((row["ticker"], row["event_date"]))
        if event is None or (event["event_id"], row["bucket"]) not in contract_groups:
            raise ValueError("capacity has no matching event/bucket")
        allowed = event["t_pre" if producer.get("entry") == "pre" else "t_0"]
        if row["entry_date"] != allowed:
            raise ValueError("capacity entry date mismatch")
        capacity_rows.append({"event_id": event["event_id"], **{
            name: _optional_number(value, name) if name in CAPACITY_NUMERIC else value
            for name, value in row.items()}})

    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(_table(events, _string_schema(list(events[0]) if events else ["event_id", *EVENT_COLUMNS])),
                   output_dir / "events.parquet")
    contract_schema = pa.schema([(name, pa.float64() if name in ("strike", "spot_pre") else
                                   pa.int64() if name == "shares_per_contract" else pa.string())
                                  for name in LEG_COLUMNS])
    pq.write_table(_table(contracts, contract_schema), output_dir / "contracts.parquet")
    pq.write_table(_table(bars, pa.schema([("contract_ticker", pa.string()), ("session", pa.string()),
                                          ("close", pa.float64()), ("volume", pa.float64())])),
                   output_dir / "bars.parquet")
    if quote_path is not None:
        numeric_quotes = {"bid", "ask", "mid", "bid_size", "ask_size", "spread",
                          "relative_spread", "minutes_before_1600"}
        quote_schema = pa.schema([(name, pa.float64() if name in numeric_quotes else pa.string())
                                  for name in QUOTE_COLUMNS])
        pq.write_table(_table(quotes, quote_schema), output_dir / "quotes.parquet")
    pq.write_table(_table(outcome_rows, pa.schema([(name, pa.float64() if name in RESULT_NUMERIC else
                                                   pa.string()) for name in ["event_id", *source["results"][0]]])),
                   output_dir / "outcomes.parquet")
    pq.write_table(_table(capacity_rows, pa.schema([(name, pa.float64() if name in CAPACITY_NUMERIC else
                                                    pa.string()) for name in ["event_id", *source["capacity"][0]]])),
                   output_dir / "capacity.parquet")
    output_hashes = {f"{name}.parquet": _sha(output_dir / f"{name}.parquet")
                     for name in ("events", "contracts", "bars", "outcomes", "capacity")}
    if quote_path is not None:
        output_hashes["quotes.parquet"] = _sha(output_dir / "quotes.parquet")
    return _write_manifest(output_dir / "manifest.json", "gm-options-ingest", run_id, source_hashes,
                           event_rows=len(events), contract_rows=len(contracts), bar_rows=len(bars),
                           quote_rows=len(quotes), outcome_rows=len(outcome_rows), capacity_rows=len(capacity_rows),
                           output_hashes=output_hashes)


def _session_age(mark: str, pre: str) -> int:
    start, end = pd.Timestamp(mark), pd.Timestamp(pre)
    holidays = NYSEHolidays().holidays(start - pd.Timedelta(days=7), end + pd.Timedelta(days=7))
    return len(pd.bdate_range(start + pd.Timedelta(days=1), end,
                              freq=CustomBusinessDay(holidays=holidays)))


def _score_number(value: object) -> tuple[float, bool]:
    if value is None:
        return math.nan, False
    number = float(value)
    return (number, True) if math.isfinite(number) else (math.nan, False)


def study_options(ingest_dir: Path, output_dir: Path, run_id: str,
                  scores_path: Path | None = None) -> dict:
    """Build pre-event option features and join exact-date View B equity scores."""
    ingest_dir, output_dir = Path(ingest_dir), Path(output_dir)
    _empty_destination(output_dir)
    ingest_manifest = json.loads((ingest_dir / "manifest.json").read_text(encoding="utf-8"))
    if (ingest_manifest.get("schema_version") != "1.0.0" or
            ingest_manifest.get("stage") != "gm-options-ingest" or
            ingest_manifest.get("run_id") != run_id):
        raise ValueError("ingest manifest stage/run identity mismatch")
    expected_hashes = ingest_manifest.get("output_hashes", {})
    ingest_hashes = {}
    artifact_names = ["events", "contracts", "bars", "outcomes", "capacity"]
    if "quotes.parquet" in expected_hashes:
        artifact_names.append("quotes")
    for name in artifact_names:
        path = ingest_dir / f"{name}.parquet"
        actual = _sha(path)
        if expected_hashes.get(path.name) != actual:
            raise ValueError(f"ingest Parquet hash mismatch: {path.name}")
        ingest_hashes[f"gm-options-ingest/{path.name}"] = actual
    events = pq.read_table(ingest_dir / "events.parquet").to_pylist()
    contracts = pq.read_table(ingest_dir / "contracts.parquet").to_pylist()
    bars = pq.read_table(ingest_dir / "bars.parquet").to_pylist()
    quotes = (pq.read_table(ingest_dir / "quotes.parquet").to_pylist()
              if "quotes" in artifact_names else [])
    outcomes = pq.read_table(ingest_dir / "outcomes.parquet")
    by_event = {row["event_id"]: row for row in events}
    by_bar = {}
    for row in bars:
        by_bar.setdefault(row["contract_ticker"], []).append(row)
    by_quote = {(row["contract_ticker"], row["session"]): row for row in quotes}
    scores = {}
    wanted = {(event["ticker"], event["t_pre"]) for event in events}
    wanted_tickers = {ticker for ticker, _ in wanted}
    score_tickers, score_dates = set(), set()
    if scores_path is not None:
        scores_path = Path(scores_path)
        score_file = pq.ParquetFile(scores_path)
        for batch in score_file.iter_batches(batch_size=65536,
                                             columns=["date", "ticker", "view", "estimator",
                                                      "depth", "pvalue", "inside"]):
            for row in batch.to_pylist():
                if row["view"] != "B" or row["ticker"] not in wanted_tickers:
                    continue
                score_tickers.add(row["ticker"])
                pair = (row["ticker"], row["date"])
                if pair not in wanted:
                    continue
                score_dates.add(pair)
                if row["estimator"] not in ESTIMATORS:
                    continue
                key = (*pair, row["estimator"])
                if key in scores:
                    raise ValueError(f"duplicate View B score: {key}")
                scores[key] = row
    by_group = {}
    for contract in contracts:
        by_group.setdefault((contract["event_id"], contract["bucket"]), {})[contract["leg_code"]] = contract
    feature_rows, matched = [], 0
    absent_ticker, absent_date, missing_estimator_pairs = 0, 0, 0
    nan = math.nan
    for (event_id, bucket), legs in sorted(by_group.items()):
        event = by_event[event_id]
        pre = event["t_pre"]
        marks = {}
        for code, leg in legs.items():
            prior = [bar for bar in by_bar.get(leg["contract_ticker"], []) if bar["session"] <= pre]
            if prior:
                mark = max(prior, key=lambda row: row["session"])
                marks[code] = (mark, _session_age(mark["session"], pre))
        atm_call, atm_put = legs.get("C_K"), legs.get("P_K")
        call_mark, put_mark = marks.get("C_K"), marks.get("P_K")
        spot = atm_call["spot_pre"] if atm_call else nan
        move = ((call_mark[0]["close"] + put_mark[0]["close"]) / spot
                if call_mark and put_mark and spot > 0 else nan)
        call_quote = by_quote.get((atm_call["contract_ticker"], pre)) if atm_call else None
        put_quote = by_quote.get((atm_put["contract_ticker"], pre)) if atm_put else None
        quote_present = call_quote is not None and put_quote is not None
        straddle_bid = call_quote["bid"] + put_quote["bid"] if quote_present else nan
        straddle_ask = call_quote["ask"] + put_quote["ask"] if quote_present else nan
        straddle_mid = (straddle_bid + straddle_ask) / 2 if quote_present else nan
        base = {"event_id": event_id, "bucket": bucket, "ticker": event["ticker"],
                "t_pre": pre, "atm_straddle_implied_move": move,
                "atm_mark_present": bool(call_mark and put_mark),
                "atm_quote_present": quote_present,
                "atm_straddle_bid": straddle_bid,
                "atm_straddle_ask": straddle_ask,
                "atm_straddle_mid": straddle_mid,
                "atm_straddle_relative_spread": ((straddle_ask - straddle_bid) / straddle_mid
                                                   if quote_present else nan),
                "atm_call_moneyness": atm_call["strike"] / spot if atm_call and spot > 0 else nan,
                "atm_put_moneyness": atm_put["strike"] / spot if atm_put and spot > 0 else nan,
                "atm_call_volume": call_mark[0]["volume"] if call_mark else nan,
                "atm_put_volume": put_mark[0]["volume"] if put_mark else nan,
                "dte_calendar_days": (_date(atm_call["expiration_date"], "expiry") - _date(pre, "t_pre")).days
                                     if atm_call else -1,
                "max_mark_age_sessions": max(call_mark[1], put_mark[1]) if call_mark and put_mark else -1}
        pair = (event["ticker"], pre)
        matched_scores = [scores[(*pair, estimator)] for estimator in ESTIMATORS
                          if (*pair, estimator) in scores]
        if not matched_scores:
            if event["ticker"] not in score_tickers:
                absent_ticker += 1
            elif pair not in score_dates:
                absent_date += 1
        missing_estimator_pairs += len(ESTIMATORS) - len(matched_scores)
        if matched_scores:
            matched += 1
        for score in matched_scores or [None]:
            depth, depth_present = _score_number(score["depth"]) if score else (nan, False)
            pvalue, pvalue_present = _score_number(score["pvalue"]) if score else (nan, False)
            feature_rows.append({**base, "score_date": pre if score else "",
                                 "score_estimator": score["estimator"] if score else "",
                                 "score_depth": depth, "score_depth_present": depth_present,
                                 "score_pvalue": pvalue, "score_pvalue_present": pvalue_present,
                                 "score_inside": bool(score["inside"]) if score and score["inside"] is not None else False,
                                 "score_inside_present": bool(score and score["inside"] is not None),
                                 "score_present": score is not None})
    schema = pa.schema([(name, kind) for name, kind in (
        ("event_id", pa.string()), ("bucket", pa.string()), ("ticker", pa.string()), ("t_pre", pa.string()),
        ("atm_straddle_implied_move", pa.float64()), ("atm_mark_present", pa.bool_()),
        ("atm_quote_present", pa.bool_()), ("atm_straddle_bid", pa.float64()),
        ("atm_straddle_ask", pa.float64()), ("atm_straddle_mid", pa.float64()),
        ("atm_straddle_relative_spread", pa.float64()),
        ("atm_call_moneyness", pa.float64()), ("atm_put_moneyness", pa.float64()),
        ("atm_call_volume", pa.float64()), ("atm_put_volume", pa.float64()),
        ("dte_calendar_days", pa.int64()), ("max_mark_age_sessions", pa.int64()),
        ("score_date", pa.string()), ("score_estimator", pa.string()),
        ("score_depth", pa.float64()), ("score_depth_present", pa.bool_()),
        ("score_pvalue", pa.float64()), ("score_pvalue_present", pa.bool_()),
        ("score_inside", pa.bool_()), ("score_inside_present", pa.bool_()),
        ("score_present", pa.bool_()))])
    output_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(_table(feature_rows, schema), output_dir / "event_features.parquet")
    pq.write_table(outcomes, output_dir / "event_outcomes.parquet")
    coverage = {"event_buckets": len(by_group), "matched_event_buckets": matched,
                "missing_score_event_buckets": len(by_group) - matched,
                "missing_score_absent_ticker": absent_ticker,
                "missing_score_absent_date": absent_date,
                "missing_estimator_pairs": missing_estimator_pairs,
                "atm_mark_event_buckets": len({(row["event_id"], row["bucket"]) for row in feature_rows
                                               if row["atm_mark_present"]}),
                "atm_quote_event_buckets": len({(row["event_id"], row["bucket"]) for row in feature_rows
                                                if row["atm_quote_present"]})}
    (output_dir / "coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8")
    hashes = {"gm-options-ingest/manifest.json": _sha(ingest_dir / "manifest.json"), **ingest_hashes}
    if scores_path is not None:
        hashes["gm-boundaries/scores.parquet"] = _sha(scores_path)
    manifest = _write_manifest(output_dir / "manifest.json", "gm-options-study", run_id, hashes,
                               **coverage)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--study-dir", type=Path, required=True)
    ingest.add_argument("--quotes", type=Path)
    study = sub.add_parser("study")
    study.add_argument("--ingest-dir", type=Path, required=True)
    study.add_argument("--scores", type=Path)
    for command in (ingest, study):
        command.add_argument("--run-id", required=True)
        command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "ingest":
        result = ingest_options(args.study_dir, args.output_dir, args.run_id, args.quotes)
    else:
        result = study_options(args.ingest_dir, args.output_dir, args.run_id, args.scores)
    print(json.dumps({"stage": result["stage"], "status": result["status"]}))


if __name__ == "__main__":
    main()
