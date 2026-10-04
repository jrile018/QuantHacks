"""Small producer handoff fixtures; real panel scans run remotely."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/contextual_lattice/export_integration_fixture.py"


def _load():
    spec = importlib.util.spec_from_file_location("integration_fixture_exporter", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup(root: Path, *, bad_target=False):
    run = root / "run"
    run.mkdir()
    names = ["AAA", "BBB", "CCC", "DDD"]
    dates = ["2024-01-04", "2024-01-08", "2024-12-30", "2025-01-02"]
    next_dates = ["2024-01-05", "2024-01-09", "2024-12-31", "2025-01-03"]
    returns = [.01, .02, -.01, .03]
    rows = []
    price_rows = []
    for ticker, day, nxt, ret in zip(names, dates, next_dates, returns):
        entry = (pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(hours=16)).tz_convert("UTC").isoformat()
        available = (pd.Timestamp(nxt).tz_localize("America/New_York") + pd.Timedelta(hours=16)).tz_convert("UTC").isoformat()
        rows.append(dict(market_group="equities", hypothesis="catchup", ticker=ticker,
                         date=day, next_date=nxt, status="evaluated", decision_at=entry,
                         feature_available_at=entry, context_available_at=entry,
                         label_available_at=available, source_version="frozen-v1",
                         target=(ret+.1 if bad_target and ticker == "BBB" else ret),
                         outcome_observed=True, context_lattice=.002, baseline=.001,
                         context_only=.0015, lattice_only=.0017, zero=0.,
                         simple_substitute=.0005, target_units="fractional_adjusted_close_change"))
        price_rows += [dict(ticker=ticker, date=day, close=200., adjclose=100.),
                       dict(ticker=ticker, date=nxt, close=200.*(1+ret), adjclose=100.*(1+ret))]
    opportunities = pd.DataFrame(rows)
    predictions = opportunities.copy()
    candidates = ("baseline", "context_only", "context_lattice", "lattice_only", "zero", "simple_substitute")
    ledgers = pd.DataFrame([dict(ticker=row.ticker, date=row.date, next_date=row.next_date,
                                 market_group="equities", hypothesis="catchup", candidate=candidate,
                                 prediction=getattr(row, candidate), status="evaluated")
                            for row in opportunities.itertuples() for candidate in candidates])
    for name, frame in (("all_opportunities", opportunities), ("all_candidate_decisions", ledgers),
                        ("all_paired_predictions", predictions)):
        frame.to_csv(run / f"{name}.csv", index=False)
    manifest = {"config_sha256": "config-hash", "config": {"experiment_id": "frozen-v1"},
                "sources": {"equity_features": {"sha256": "feature-hash"},
                            "SEC_filings": {"sha256": "sec-hash"}}}
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    outputs = {f"{name}.csv": {"sha256": _sha(run / f"{name}.csv")}
               for name in ("all_opportunities", "all_candidate_decisions", "all_paired_predictions")}
    (run / "events.jsonl").write_text(json.dumps({"stage": "comparisons_complete", "outputs": outputs}) + "\n")
    prices = root / "prices.parquet"
    pd.DataFrame(price_rows).to_parquet(prices, index=False)
    return run, prices


class IntegrationFixtureTest(unittest.TestCase):
    def test_only_2024_verified_rows_and_stable_ids(self):
        exporter = _load()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            run, prices = _setup(root)
            first = root / "first"
            second = root / "second"
            exporter.export_fixture(run, prices, first, max_rows=3)
            exporter.export_fixture(run, prices, second, max_rows=3)
            one = json.loads((first / "fixture.json").read_text())
            two = json.loads((second / "fixture.json").read_text())
            self.assertEqual(len(one["rows"]), 3)
            self.assertEqual([r["ids"] for r in one["rows"]], [r["ids"] for r in two["rows"]])
            self.assertTrue(all(r["coordination"]["decision_date"].startswith("2024") and
                                r["coordination"]["next_date"].startswith("2024") for r in one["rows"]))
            self.assertAlmostEqual(one["rows"][0]["coordination"]["target_reconstructed"], .01)
            self.assertEqual(one["rows"][0]["coordination"]["source_price_kind"], "adjustedclose")
            self.assertIsNone(one["rows"][0]["coordination"]["security_id"])
            self.assertNotIn("producer_candidate_id", one["rows"][0]["raw_candidate_ledger"][0])
            manifest = json.loads((first / "manifest.json").read_text())
            self.assertEqual(manifest["output_sha256"]["fixture.json"], _sha(first / "fixture.json"))
            self.assertEqual(manifest["source_sha256"]["native_prices"], _sha(prices))
            self.assertEqual(manifest["run_source_sha256"]["equity_features"], "feature-hash")

    def test_target_mismatch_quarantines_row_without_replacing_target(self):
        exporter = _load()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            run, prices = _setup(root, bad_target=True)
            output = root / "out"
            exporter.export_fixture(run, prices, output, max_rows=3)
            fixture = json.loads((output / "fixture.json").read_text())
            quarantine = json.loads((output / "quarantine.json").read_text())
            self.assertEqual([r["raw_opportunity"]["ticker"] for r in fixture["rows"]], ["AAA", "CCC"])
            self.assertEqual(quarantine["rows"][0]["ticker"], "BBB")
            self.assertEqual(quarantine["rows"][0]["reason"], "target_reconstruction_mismatch")

    def test_tampered_run_output_hash_is_rejected(self):
        exporter = _load()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            run, prices = _setup(root)
            with (run / "all_opportunities.csv").open("a") as stream:
                stream.write("tampered\n")
            with self.assertRaisesRegex(ValueError, "run output hash mismatch"):
                exporter.export_fixture(run, prices, root / "out", max_rows=3)
