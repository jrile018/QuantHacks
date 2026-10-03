"""Checks for attribution, missingness, historical leakage and rate limiting."""
import datetime as dt
import gzip
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

PATH = Path(__file__).resolve().parents[1] / "data/packaged_software/extract_epss.py"
SPEC = importlib.util.spec_from_file_location("extract_epss", PATH)
epss = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(epss)


class EpssTests(unittest.TestCase):
    def test_environment_prerequisite_is_not_a_vulnerable_product(self):
        cve = {"configurations": [{"nodes": [{"cpeMatch": [
            {"criteria": "cpe:2.3:a:microsoft:example:*:*:*:*:*:*:*:*", "vulnerable": False},
            {"criteria": "cpe:2.3:a:adobe:example:*:*:*:*:*:*:*:*", "vulnerable": True},
            {"criteria": "cpe:2.3:o:microsoft:windows:*:*:*:*:*:*:*:*", "vulnerable": True},
        ]}]}]}
        self.assertFalse(epss.configuration_matches(cve, "microsoft"))
        self.assertTrue(epss.configuration_matches(cve, "adobe"))

    def test_negated_configuration_does_not_attribute(self):
        cve = {"configurations": [{"negate": True, "nodes": [{"cpeMatch": [
            {"criteria": "cpe:2.3:a:adobe:example", "vulnerable": True}]}]}]}
        self.assertFalse(epss.configuration_matches(cve, "adobe"))

    def test_missing_scores_and_future_cves_are_not_zero_scores(self):
        company = {"cik": "1", "ticker": "TEST", "name": "Test"}
        mapping = {"cpe_vendors": "test", "mapping_status": "curated_current_brand"}
        cves = [{"cve": "CVE-OLD", "published": "2021-01-01"},
                {"cve": "CVE-MISSING", "published": "2021-01-02"},
                {"cve": "CVE-FUTURE", "published": "2023-01-01"}]
        scores = {"CVE-OLD": (0.0, 0.0), "CVE-FUTURE": (0.99, 0.99)}
        result = epss.summary(company, mapping, cves, scores, "2022-01-01", "v1", 0.1)
        self.assertEqual(result["eligible_cve_count"], 2)
        self.assertEqual(result["scored_cve_count"], 1)
        self.assertEqual(result["missing_epss_count"], 1)
        self.assertEqual(result["max_product_cve_epss"], 0.0)
        self.assertEqual(result["coverage_status"], "partial_epss_coverage")
        missing = epss.summary(company, mapping, cves, {}, "2022-01-01", "v1", 0.1)
        self.assertEqual(missing["max_product_cve_epss"], "")
        self.assertEqual(missing["high_epss_cve_count"], "")
        unmapped = epss.summary(company, {}, [], {}, "2022-01-01", "v1", 0.1)
        self.assertEqual(unmapped["eligible_cve_count"], "")
        failed = epss.summary(company, mapping, cves, scores, "2022-01-01", "v1", 0.1, True)
        self.assertEqual(failed["eligible_cve_count"], "")
        self.assertEqual(failed["max_product_cve_epss"], "")

    def test_historical_file_date_is_verified_and_zero_preserved(self):
        raw = gzip.compress(b"#model_version:v1,score_date:2022-01-01\ncve,epss,percentile\nCVE-1,0,0\nCVE-2,0.99,0.99\n")
        scores, meta = epss.parse_epss(raw, {"CVE-1"}, "2022-01-01")
        self.assertEqual(scores, {"CVE-1": (0.0, 0.0)})
        self.assertEqual(meta["model_version"], "v1")
        with self.assertRaises(ValueError):
            epss.parse_epss(raw, {"CVE-1"}, "2022-01-02")

    def test_rate_limit_applies_to_separate_vendor_calls(self):
        client = epss.Client()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        with patch.object(epss.urllib.request, "urlopen", return_value=response), \
                patch.object(epss.time, "monotonic", side_effect=[0.0, 1.0, 6.5]), \
                patch.object(epss.time, "sleep") as sleep:
            client.get("https://example.org/vendor-a", nvd=True)
            client.get("https://example.org/vendor-b", nvd=True)
            sleep.assert_called_once_with(5.5)

    def test_early_v1_file_without_metadata_or_percentile(self):
        raw = gzip.compress(b"cve,epss\nCVE-1,0.5\n")
        scores, meta = epss.parse_epss(raw, {"CVE-1"}, "2022-01-01")
        self.assertEqual(scores, {"CVE-1": (0.5, "")})
        self.assertEqual(meta["model_version"], "v1_inferred_from_release_date")
        with self.assertRaises(ValueError):
            epss.parse_epss(raw, {"CVE-1"}, "2022-03-01")

    def test_monthly_is_snapshot_not_average(self):
        self.assertEqual(list(epss.dates_between(dt.date(2022, 1, 1), dt.date(2022, 3, 5), "monthly")),
                         ["2022-01-01", "2022-02-01", "2022-03-01"])

    def test_api_fallback_checks_each_historical_row_date(self):
        client = MagicMock()
        client.get.return_value = json.dumps({"status": "OK", "total": 1, "data": [
            {"cve": "CVE-1", "epss": "0.5", "percentile": "0.9", "date": "2024-12-01"}]}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            raw = epss.api_snapshot(client, "2024-12-01", Path(tmp))
            scores, meta = epss.parse_epss(raw, {"CVE-1"}, "2024-12-01")
            self.assertEqual(scores, {"CVE-1": (0.5, 0.9)})
            self.assertEqual(meta["model_version"], "unavailable_from_api")
            client.get.return_value = json.dumps({"status": "OK", "total": 1, "data": [
                {"cve": "CVE-1", "epss": "0.5", "percentile": "0.9", "date": "2026-01-01"}]}).encode()
            with self.assertRaises(ValueError):
                epss.api_snapshot(client, "2024-12-02", Path(tmp))


if __name__ == "__main__":
    unittest.main()
