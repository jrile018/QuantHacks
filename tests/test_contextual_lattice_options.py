"""Small causal fixtures for the exploratory fixed-contract options audit."""
from __future__ import annotations

import pandas as pd
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.contextual_lattice.options import build_audit, summarize_audit


def _fixtures():
    events = pd.DataFrame([dict(event_id="e1", ticker="ABC", t_pre="2024-01-05",
                                event_date="2024-01-08", t_0="2024-01-09")])
    contracts = pd.DataFrame([dict(event_id="e1", bucket="1m", leg_code=code,
                                   contract_ticker=code, contract_type=kind,
                                   strike=100.0, expiration_date="2024-02-16",
                                   selection_date="2024-01-05", shares_per_contract=100)
                              for code, kind in (("C_K", "call"), ("P_K", "put"))])
    quotes = pd.DataFrame([dict(contract_ticker=code, session=day,
                                mark_time_utc=f"{day}T20:59:00Z", bid=mid-.1,
                                ask=mid+.1, mid=mid, bid_size=2, ask_size=2,
                                minutes_before_1600=1)
                           for code, marks in (("C_K", (2.0, 2.4)), ("P_K", (1.8, 1.5)))
                           for day, mid in zip(("2024-01-09", "2024-01-10"), marks)])
    prices = pd.DataFrame([dict(ticker="ABC", date=day, close=raw, adjclose=adj)
                           for day, raw, adj in (("2024-01-09", 100., 50.),
                                                  ("2024-01-10", 101., 50.5))])
    scores = pd.DataFrame([dict(ticker="ABC", date="2024-01-05", view="B",
                                estimator="mahalanobis", depth=1.2)])
    return events, contracts, quotes, prices, scores


def test_paired_marks_are_descriptive_and_adjusted_price_is_distinct_from_raw():
    rows = build_audit(*_fixtures())
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row.status == "descriptive_mark_pair"
    assert row.target_observed
    assert abs(row.adjusted_abs_log_return - 0.009950330853168092) < 1e-12
    assert row.straddle_mid_entry == 3.8
    assert row.straddle_mid_exit == 3.9
    assert pd.isna(row.unadjusted_spot_entry)
    assert row.option_premium_status == "blocked"
    assert pd.isna(row.prediction)


def test_late_or_invalid_quote_keeps_attempt_and_blocks_pair():
    events, contracts, quotes, prices, scores = _fixtures()
    quotes.loc[quotes.contract_ticker.eq("P_K") & quotes.session.eq("2024-01-10"),
               "minutes_before_1600"] = 8
    rows = build_audit(events, contracts, quotes, prices, scores)
    row = rows.iloc[0]
    assert row.status == "incomplete_mark_pair"
    assert row.target_observed
    assert "invalid_exit_quote" in row.abstention_reason
    assert pd.isna(row.straddle_mid_exit)


def test_exact_1600_interval_end_is_descriptive_only():
    events, contracts, quotes, prices, scores = _fixtures()
    quotes["mark_time_utc"] = quotes["session"] + "T21:00:00Z"
    quotes["minutes_before_1600"] = 0
    row = build_audit(events, contracts, quotes, prices, scores).iloc[0]
    assert row.status == "descriptive_mark_pair"
    assert row.option_premium_status == "blocked"


def test_wrong_atm_contract_type_retains_blocked_attempt():
    events, contracts, quotes, prices, scores = _fixtures()
    contracts.loc[contracts.leg_code.eq("P_K"), "contract_type"] = "call"
    row = build_audit(events, contracts, quotes, prices, scores).iloc[0]
    assert row.status == "incomplete_mark_pair"
    assert "missing_or_inconsistent_atm_pair_terms" in row.abstention_reason


def test_noncausal_event_chronology_cannot_be_descriptive_pair():
    events, contracts, quotes, prices, scores = _fixtures()
    events.loc[0, "event_date"] = "2024-01-10"
    row = build_audit(events, contracts, quotes, prices, scores).iloc[0]
    assert row.status == "incomplete_mark_pair"
    assert "event_chronology_unverified" in row.abstention_reason


def test_evaluated_movement_adapter_is_recorded_diagnostic_only():
    events, contracts, quotes, prices, scores = _fixtures()
    # Shape emitted by run_contextual_study.py's equities movement adapter.
    adapter = pd.DataFrame([dict(ticker="ABC", decision_date="2024-01-09",
                                 predicted_abs_return=.012, status="evaluated")])
    row = build_audit(events, contracts, quotes, prices, scores, adapter).iloc[0]
    assert row.prediction == .012
    assert row.status == "descriptive_mark_pair"
    assert row.abstention_reason == "forecast_timing_unverified"
    assert row.option_premium_status == "blocked"


def test_diagnostic_gate_counts_distinct_events_and_does_not_select_rows():
    rows = pd.DataFrame([dict(event_id=f"e{i // 2}", status="descriptive_mark_pair",
                              target_observed=True, prediction=None,
                              abstention_reason="no_clock_qualified_movement_forecast")
                         for i in range(36)])
    summary = summarize_audit(rows)
    assert summary["distinct_descriptive_events"] == 18
    assert summary["association_status"] == "inconclusive"
    assert summary["status"] == "inconclusive"
    assert summary["minimum_distinct_events"] == 20
    assert summary["target_observed_rows"] == 36
    assert summary["prediction_rows"] == 0
    assert summary["abstention_reason_counts"]["no_clock_qualified_movement_forecast"] == 36


def test_original_18_event_gate_survives_more_descriptive_pairs():
    rows = pd.DataFrame([dict(event_id=f"e{i}", status="descriptive_mark_pair")
                         for i in range(25)])
    original = {"coverage": {"primary_distinct_event_ids": 18}}
    summary = summarize_audit(rows, original)
    assert summary["distinct_descriptive_events"] == 25
    assert summary["source_primary_distinct_events"] == 18
    assert summary["association_status"] == "inconclusive"
    assert summary["status"] == "inconclusive"


def test_runner_writes_reproducible_attempt_audit_and_preserves_source_gate():
    script = Path(__file__).resolve().parents[1] / "scripts/contextual_lattice/run_options.py"
    spec = importlib.util.spec_from_file_location("context_options_runner", script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    events, contracts, quotes, prices, scores = _fixtures()
    with TemporaryDirectory() as temp:
        root = Path(temp)
        ingest = root / "ingest"
        ingest.mkdir()
        hashes = {}
        for name, frame in (("events", events), ("contracts", contracts), ("quotes", quotes)):
            path = ingest / f"{name}.parquet"
            frame.to_parquet(path, index=False)
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (ingest / "manifest.json").write_text(json.dumps({"stage": "gm-options-ingest",
            "schema_version": "1.0.0", "output_hashes": hashes}))
        prices_path, scores_path = root / "prices.parquet", root / "scores.parquet"
        prices.to_parquet(prices_path, index=False)
        scores.to_parquet(scores_path, index=False)
        matched = root / "matched.json"
        matched.write_text(json.dumps({"coverage": {"primary_distinct_event_ids": 18}}))
        output = root / "result"
        runner.run_study(ingest, prices_path, scores_path, matched, output)
        summary = json.loads((output / "summary.json").read_text())
        protocol = json.loads((output / "protocol.json").read_text())
        audit = pd.read_csv(output / "row_audit.csv")
        assert summary["association_status"] == "inconclusive"
        assert len(audit) == 1 and bool(audit.iloc[0].target_observed)
        assert protocol["source_sha256"]["native_prices"] == hashlib.sha256(prices_path.read_bytes()).hexdigest()
        assert "15:55-16:00 ET" in protocol["quotes"]
        assert "interval" in protocol["quotes"]


class ContextualLatticeOptionsTest(unittest.TestCase):
    test_paired_marks_are_descriptive_and_adjusted_price_is_distinct_from_raw = staticmethod(
        test_paired_marks_are_descriptive_and_adjusted_price_is_distinct_from_raw)
    test_late_or_invalid_quote_keeps_attempt_and_blocks_pair = staticmethod(
        test_late_or_invalid_quote_keeps_attempt_and_blocks_pair)
    test_exact_1600_interval_end_is_descriptive_only = staticmethod(
        test_exact_1600_interval_end_is_descriptive_only)
    test_wrong_atm_contract_type_retains_blocked_attempt = staticmethod(
        test_wrong_atm_contract_type_retains_blocked_attempt)
    test_noncausal_event_chronology_cannot_be_descriptive_pair = staticmethod(
        test_noncausal_event_chronology_cannot_be_descriptive_pair)
    test_evaluated_movement_adapter_is_recorded_diagnostic_only = staticmethod(
        test_evaluated_movement_adapter_is_recorded_diagnostic_only)
    test_diagnostic_gate_counts_distinct_events_and_does_not_select_rows = staticmethod(
        test_diagnostic_gate_counts_distinct_events_and_does_not_select_rows)
    test_original_18_event_gate_survives_more_descriptive_pairs = staticmethod(
        test_original_18_event_gate_survives_more_descriptive_pairs)
    test_runner_writes_reproducible_attempt_audit_and_preserves_source_gate = staticmethod(
        test_runner_writes_reproducible_attempt_audit_and_preserves_source_gate)
