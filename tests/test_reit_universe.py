import unittest

from src.reit_universe import build_universe, parse_sec_exchange_map, parse_nareit_ticker_table


class UniverseTests(unittest.TestCase):
    def candidate(self, **kwargs):
        return {"cik": "123", "name": "Example Trust", "ticker": "EX", **kwargs}

    def evidence(self, **kwargs):
        base = {"cik": "123", "ticker": "EX", "valid_from": "2024-06-01",
                "known_from": "2024-06-02T00:00:00Z", "source_url": "https://www.sec.gov/example",
                "locator": "cover page", "quote": "Example Trust common shares listed on NYSE; REIT election"}
        return [{**base, "kind": "reit_status", "value": True, **kwargs},
                {**base, "kind": "listing", "value": True, "exchange": "NYSE", **kwargs},
                {**base, "kind": "security_type", "value": "common", **kwargs}]

    def test_sic_and_directory_are_only_candidates(self):
        result = build_universe([self.candidate(sic="6798")], [], "2026-10-03")
        self.assertEqual(result["validated"], [])
        self.assertEqual(result["coverage"]["candidate_count"], 1)
        self.assertIn("missing_reit_status_evidence", result["candidates"][0]["reasons"])

    def test_dated_evidence_does_not_backfill_current_membership(self):
        rows = [self.candidate()]
        self.assertEqual(build_universe(rows, self.evidence(), "2024-01-01")["validated"], [])
        self.assertEqual(build_universe(rows, self.evidence(), "2024-06-01")["validated"], [])
        result = build_universe(rows, self.evidence(), "2024-06-02")
        self.assertEqual(result["validated"][0]["cik"], "0000000123")
        self.assertEqual(result["validated"][0]["eligibility_intervals"][0]["valid_from"], "2024-06-01")

    def test_preferred_and_expired_listing_are_separate_exclusions(self):
        ev = self.evidence()
        ev[2]["value"] = "preferred"
        result = build_universe([self.candidate()], ev, "2026-10-03")
        self.assertEqual(result["exclusions"][0]["reasons"], ["security_type_preferred"])
        ev = self.evidence(valid_to="2025-01-01")
        result = build_universe([self.candidate()], ev, "2026-10-03")
        self.assertEqual(len(result["securities"][0]["eligibility_intervals"]), 1)
        self.assertEqual(result["validated"], [])

    def test_aliases_retained_without_merging_distinct_ciks(self):
        alias = {**self.evidence()[0], "kind": "alias", "value": "Former Trust"}
        result = build_universe([self.candidate(), self.candidate(cik="456")], [alias], "2026-10-03")
        self.assertEqual(len(result["issuers"]), 2)
        self.assertEqual(result["issuers"][0]["aliases"][0]["value"], "Former Trust")

    def test_unverifiable_and_naive_evidence_remain_errors(self):
        ev = self.evidence()
        ev[0]["known_from"] = "2024-06-02"
        ev[1].pop("quote")
        result = build_universe([self.candidate()], ev, "2026-10-03")
        self.assertEqual(len(result["coverage"]["evidence_errors"]), 2)
        self.assertEqual(result["validated"], [])

    def test_historical_intersection_exposes_later_exit_blocker(self):
        ev = self.evidence()
        exit_row = {**ev[1], "kind": "exit", "valid_from": "2025-01-01", "known_from": "2025-01-02T00:00:00Z"}
        result = build_universe([self.candidate()], ev + [exit_row], "2026-10-03")
        self.assertTrue(result["securities"][0]["eligibility_intervals"][0]["blocking_evidence_ids"])

    def test_false_listing_and_backdated_source_knowledge_cannot_validate(self):
        ev = self.evidence()
        ev[1]["value"] = False
        result = build_universe([self.candidate()], ev, "2026-10-03")
        self.assertIn("not_listed", result["exclusions"][0]["reasons"])
        ev = self.evidence()
        ev[0]["source_available_at"] = "2025-01-01T00:00:00Z"
        result = build_universe([self.candidate()], ev, "2026-10-03")
        self.assertTrue(result["coverage"]["evidence_errors"])
        self.assertEqual(result["validated"], [])

    def test_nonoverlapping_knowledge_does_not_create_historical_interval(self):
        ev = self.evidence()
        ev[0]["known_to"] = "2024-06-03T00:00:00Z"
        ev[1]["known_from"] = "2024-06-04T00:00:00Z"
        result = build_universe([self.candidate()], ev, "2026-10-03")
        self.assertEqual(result["securities"][0]["eligibility_intervals"], [])

    def test_observed_sec_columnar_exchange_map_and_strict_validation(self):
        rows = parse_sec_exchange_map({"fields": ["cik", "name", "ticker", "exchange"],
                                       "data": [[123, "Example Trust", "EX", "NYSE"]]})
        self.assertEqual(rows[0]["cik"], "0000000123")
        self.assertNotIn("security_type", rows[0])
        with self.assertRaises(ValueError):
            parse_sec_exchange_map({"fields": ["cik", "ticker"], "data": [[123]]})
        with self.assertRaises(ValueError):
            build_universe([self.candidate(cik="wrong")], [], "2026-10-03")

    def test_unsafe_evidence_urls_remain_errors(self):
        for url in ["https://u:p@www.sec.gov/example", "https://www.sec.gov:444/example",
                    "https://www.sec.gov/\nexample", "https://www.sec.gov/\x7fexample"]:
            with self.subTest(url=url):
                result = build_universe([self.candidate()], self.evidence(source_url=url), "2026-10-03")
                self.assertEqual(result["validated"], [])
                self.assertEqual(len(result["coverage"]["evidence_errors"]), 3)

    def test_class_evidence_without_identifiers_cannot_validate(self):
        ev = self.evidence()
        for row in ev:
            row.pop("ticker")
        candidate = {"cik": "123", "security_id": "preferred-no-ticker", "security_type": "preferred"}
        result = build_universe([candidate], ev, "2026-10-03")
        self.assertEqual(result["validated"], [])
        self.assertIn("missing_security_type_evidence", result["candidates"][0]["reasons"])

    def test_missing_kind_is_retained_as_an_evidence_error(self):
        ev = self.evidence()
        ev[0].pop("kind")
        try:
            result = build_universe([self.candidate()], ev, "2026-10-03")
        except KeyError as exc:
            self.fail(f"Malformed evidence escaped validation: {exc}")
        self.assertEqual(len(result["coverage"]["evidence_errors"]), 1)
        self.assertEqual(result["validated"], [])

    def test_observed_nareit_html_table_import_retains_unknown_class(self):
        html = b'''<table class="views-table views-view-table cols-2 responsive"><thead><tr>
        <th id="view-field-ticker-symbol-table-column">RTC Ticker</th>
        <th id="view-title-table-column">Company name</th></tr></thead><tbody>
        <tr><td headers="view-field-ticker-symbol-table-column"><a href="https://www.reit.com/investing/reit-directory/american-assets-trust">AAT</a></td>
        <td headers="view-title-table-column"><a href="/investing/reit-directory/american-assets-trust">American Assets Trust</a></td></tr>
        <tr><td><a href="/investing/reit-directory/alexanders-inc">ALX</a></td><td>Alexander&#039;s, Inc.</td></tr>
        </tbody></table>'''
        rows = parse_nareit_ticker_table(html, retrieved_at="2026-10-04T00:50:00Z")
        self.assertEqual([row["ticker"] for row in rows], ["AAT", "ALX"])
        self.assertEqual(rows[1]["name"], "Alexander's, Inc.")
        self.assertEqual(rows[0]["profile_url"], "https://www.reit.com/investing/reit-directory/american-assets-trust")
        self.assertEqual(rows[0]["source_classification"], "unknown_reit_or_reoc")
        self.assertIsNone(rows[0]["cik"])
        self.assertNotIn("security_type", rows[0])
        self.assertEqual(len(rows[0]["source_sha256"]), 64)
        with self.assertRaises(ValueError):
            parse_nareit_ticker_table("<html>Access denied</html>")


if __name__ == "__main__":
    unittest.main()

