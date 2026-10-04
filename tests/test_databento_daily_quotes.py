import csv
from pathlib import Path
import sys
import tempfile
import unittest
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_databento_daily_quotes import aggregate_rows, build, raw_symbol_from_ticker


class DatabentoDailyQuotesTest(unittest.TestCase):
    def test_massive_ticker_to_opra_symbol(self):
        self.assertEqual(raw_symbol_from_ticker("O:GD240202C00260000"), "GD    240202C00260000")

    def test_last_valid_regular_session_quote_wins(self):
        contract = "O:GD240202C00260000"
        symbol = raw_symbol_from_ticker(contract)
        def row(ts, bid, ask, bid_size=1, ask_size=1):
            return {"symbol": symbol, "ts_recv": ts, "bid_px_00": str(bid),
                    "ask_px_00": str(ask), "bid_sz_00": str(bid_size), "ask_sz_00": str(ask_size)}
        rows = [
            row("2024-01-04T20:58:00Z", 4.1, 4.3),
            row("2024-01-04T20:59:00Z", 4.2, 4.4),
            row("2024-01-04T21:00:00Z", 4.0, 3.9),  # crossed, reject
            row("2024-01-04T21:01:00Z", 5.0, 5.2),  # after 4 PM ET, reject
            row("2024-01-05T14:00:00Z", 5.0, 5.2),  # before 9:30 AM ET, reject
        ]
        marks, stats = aggregate_rows(rows, {symbol: contract}, "test-job")
        mark = marks[(contract, "2024-01-04")]
        self.assertAlmostEqual(mark["bid"], 4.2)
        self.assertAlmostEqual(mark["ask"], 4.4)
        self.assertAlmostEqual(mark["mid"], 4.3)
        self.assertEqual(mark["mark_time_utc"], "2024-01-04T20:59:00Z")
        self.assertEqual(stats["accepted_records"], 2)

    def test_compressed_file_build_and_eight_leg_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            source = project / "data" / "processed" / "cfo-2024-2025-massive"
            source.mkdir(parents=True)
            tickers = ["O:GD240202C00260000", "O:GD240202P00260000",
                       "O:GD240202C00265000", "O:GD240202P00255000",
                       "O:GD240202C00270000", "O:GD240202P00250000",
                       "O:GD240202C00275000", "O:GD240202P00245000"]
            with (source / "option_legs.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["event_id", "bucket", "contract_ticker", "selection_date"])
                writer.writeheader()
                writer.writerows({"event_id": "event-1", "bucket": "1m", "contract_ticker": ticker,
                                  "selection_date": "2024-01-04"} for ticker in tickers)
            batch = project / "data" / "raw" / "databento" / "job-1"
            batch.mkdir(parents=True)
            lines = ["ts_recv,symbol,bid_px_00,ask_px_00,bid_sz_00,ask_sz_00"]
            lines.extend(f"2024-01-04T20:59:00Z,{raw_symbol_from_ticker(ticker)},4,5,1,2"
                         for ticker in tickers)
            (batch / "sample.csv.zst").write_bytes(pa.compress(("\n".join(lines) + "\n").encode(), codec="zstd").to_pybytes())
            summary = build(project, "job-1")
            self.assertEqual(summary["daily_quote_marks"], 8)
            self.assertEqual(summary["selection_contract_dates_covered"], 8)
            self.assertEqual(summary["event_bucket_groups_complete"], 1)


if __name__ == "__main__":
    unittest.main()
