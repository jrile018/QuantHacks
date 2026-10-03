import argparse
import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / "data/packaged_software"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("news", HERE / "extract_company_news.py")
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


class NewsTests(unittest.TestCase):
    def test_pagination_sanitizes_auth_and_rejects_external_hosts(self):
        self.assertEqual(n.clean_url("https://api.massive.com:443/v2/reference/news?cursor=x&apiKey=secret"),
                         "https://api.massive.com/v2/reference/news?cursor=x")
        with self.assertRaises(ValueError):
            n.clean_url("https://example.org/v2/reference/news")

    def test_current_and_historical_symbol_articles_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            companies, aliases = root / "companies.csv", root / "aliases.csv"
            companies.write_text("cik,ticker,name\n0000000001,NEW,Example\n", encoding="utf-8")
            aliases.write_text("cik,alias,evidence_url\n0000000001,OLD,https://www.sec.gov/filing\n", encoding="utf-8")
            a = {"id": "a", "published_utc": "2022-01-03T12:00:00Z", "title": "Example announces an AI partnership", "tickers": ["NEW"]}
            b = {"id": "b", "published_utc": "2022-01-04T12:00:00Z", "title": "Example deploys AI for employees", "tickers": ["OLD"]}
            args = argparse.Namespace(companies=companies, aliases=aliases, check_api=False, cache=root / "cache", output=root / "out", start="2022-01-01", end="2022-12-31")
            with patch.object(n.NewsClient, "page", side_effect=[{"results": [a]}, {"results": [a, b]}]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n.run(args), 0)
            with (args.output / "news_articles.csv").open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["queried_ticker"], "OLD")
            self.assertEqual(rows[1]["ticker_alias_evidence_url"], "https://www.sec.gov/filing")
            self.assertTrue(all(r["review_status"] == "unreviewed_news_metadata" for r in rows))

    def test_out_of_range_api_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            companies = root / "companies.csv"
            companies.write_text("cik,ticker,name\n0000000001,NEW,Example\n", encoding="utf-8")
            args = argparse.Namespace(companies=companies, aliases=root / "missing.csv", check_api=False, cache=root / "cache", output=root / "out", start="2022-01-01", end="2022-12-31")
            with patch.object(n.NewsClient, "page", return_value={"results": [{"id": "a", "published_utc": "2026-01-01T00:00:00Z"}]}), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n.run(args), 1)
            with (args.output / "news_articles.csv").open(newline="", encoding="utf-8") as source:
                self.assertEqual(list(csv.DictReader(source)), [])


if __name__ == "__main__":
    unittest.main()
