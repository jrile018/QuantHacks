import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

SPEC = importlib.util.spec_from_file_location("metrics", Path(__file__).resolve().parents[1] / "data/packaged_software/extract_company_metrics.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fact(start, end, value, filed, accn="a", tag="Revenues", priority=0):
    return {"start": start, "end": end, "val": value, "filed": filed, "accn": accn, "tag": tag, "priority": priority, "id": f"{tag}:{start}:{end}:{filed}:{accn}"}


class MetricsTests(unittest.TestCase):
    def test_same_filing_restatement_basis_is_used_for_difference(self):
        facts = [fact("2022-01-01", "2022-03-31", 100, "2022-05-01", "a"),
                 fact("2022-01-01", "2022-03-31", 110, "2022-08-01", "b"),
                 fact("2022-01-01", "2022-06-30", 250, "2022-08-01", "b")]
        quarters = m.quarterly_series(facts)
        self.assertEqual(quarters["2022-06-30"]["value"], 140)
        self.assertEqual(quarters["2022-06-30"]["quality"], "same_filing_difference")
        self.assertEqual(quarters["2022-03-31"]["value"], 100)

    def test_cross_filing_difference_is_flagged(self):
        facts = [fact("2022-01-01", "2022-03-31", 100, "2022-05-01", "a"),
                 fact("2022-01-01", "2022-06-30", 250, "2022-08-01", "b")]
        self.assertEqual(m.quarterly_series(facts)["2022-06-30"]["quality"], "cross_filing_basis_unverified")

    def test_missing_capex_is_not_zero_in_fcf(self):
        company = {"cik": "1", "ticker": "TEST", "name": "Test"}
        from collections import defaultdict
        facts = defaultdict(list)
        for end, start in [("2022-03-31", "2022-01-01"), ("2022-06-30", "2022-04-01"), ("2022-09-30", "2022-07-01"), ("2022-12-31", "2022-10-01")]:
            facts["revenue"].append(fact(start, end, 100, m.next_day(end)))
            facts["operating_cash_flow"].append(fact(start, end, 20, m.next_day(end), tag="NetCashProvidedByUsedInOperatingActivities"))
        rows, sources = m.build_quarters(company, facts, "2022-01-01", "2023-12-31")
        self.assertEqual(rows[-1]["ttm_revenue"], 400)
        self.assertEqual(rows[-1]["fcf_physical_capex_margin"], "")

    def test_no_backdated_later_tag_preference(self):
        facts = [fact("2022-01-01", "2022-03-31", 100, "2022-05-01", tag="Revenues", priority=1),
                 fact("2022-01-01", "2022-03-31", 120, "2023-05-01", tag="RevenueFromContractWithCustomerExcludingAssessedTax")]
        q = m.quarterly_series(facts)["2022-03-31"]
        self.assertEqual(q["value"], 100)
        self.assertEqual(q["filed"], "2022-05-01")

    def test_risk_boilerplate_is_not_employee_deployment(self):
        text = "Our employees may use generative AI, which could adversely affect our business through unauthorized disclosures."
        hits = m.evidence(text)
        self.assertTrue(hits)
        self.assertEqual(hits[0][1], "employee_ai_policy_or_risk")
        self.assertFalse(m.evidence("We sell AI products to customers worldwide."))

    def test_employee_and_vendor_evidence_is_candidate_not_numeric_fact(self):
        hits = m.evidence("We deployed ChatGPT Enterprise from OpenAI to our employees to improve internal productivity, covering 500 employees.")
        self.assertEqual(hits[0][1], "employee_ai_adoption_candidate")

    def test_hidden_xbrl_does_not_create_disclosure(self):
        parser = m.FilingText()
        parser.feed('<html><ix:hidden>We deployed ChatGPT to our employees.</ix:hidden><p>We sell software.</p></html>')
        self.assertFalse(m.evidence(parser.text()))

    def test_productive_assets_are_not_physical_capex_fallback(self):
        self.assertNotIn("PaymentsToAcquireProductiveAssets", m.FLOWS["physical_asset_purchases"])
        self.assertNotIn("CapitalizedComputerSoftwareAdditions", m.FLOWS["software_development_cash_payments"])
        self.assertFalse(m.asset_concept("cloud:StockIssuedDuringPeriod"))
        self.assertTrue(m.asset_concept("example:CloudHostingCosts"))

    def test_inline_custom_asset_fact_preserves_scale_dimensions_and_period(self):
        parser = m.FilingText()
        parser.feed('''<html><ix:header><ix:resources>
        <xbrli:context id="c1"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:AssetAxis">test:ComputerEquipmentMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2022-12-31</xbrli:instant></xbrli:period></xbrli:context>
        <xbrli:unit id="u1"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
        </ix:resources></ix:header><ix:nonFraction name="test:ComputerEquipment" contextRef="c1" unitRef="u1" scale="3" format="ixt:num-dot-decimal">1,250</ix:nonFraction></html>''')
        record = list(parser.tagged_facts())[0]
        self.assertEqual(record["value"], 1250000)
        self.assertEqual(record["unit"], "iso4217:USD")
        self.assertEqual(record["period_end"], "2022-12-31")
        self.assertIn("ComputerEquipmentMember", record["dimensions"])

    def test_unsupported_inline_decimal_format_is_not_guessed(self):
        parser = m.FilingText()
        parser.feed('<ix:nonFraction name="test:Land" format="ixt:num-comma-decimal">1.234,56</ix:nonFraction>')
        self.assertEqual(list(parser.tagged_facts())[0]["value"], "")

    def test_fast_filing_parser_excludes_hidden_mentions_and_resolves_context(self):
        raw = '''<html><ix:header><xbrli:context id="c"><xbrli:period><xbrli:instant>2022-12-31</xbrli:instant></xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit></ix:header><ix:hidden>Our employees use ChatGPT.</ix:hidden><p>Equipment: <ix:nonFraction name="test:Equipment" contextRef="c" unitRef="u" scale="3">123</ix:nonFraction></p></html>'''
        parser, text = m.parse_relevant_filing(raw)
        self.assertFalse(m.evidence(text))
        f = list(parser.tagged_facts())[0]
        self.assertEqual(f["value"], 123000)
        self.assertEqual(f["period_end"], "2022-12-31")
        self.assertEqual(f["unit"], "iso4217:USD")

    def test_dotenv_contact_loads_without_dependency_and_environment_overrides(self):
        import sec_common
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text('SEC_USER_AGENT="Research tester@example.org"\n', encoding="utf-8")
            with patch.object(sec_common, "ROOT", Path(tmp)), patch.dict(sec_common.os.environ, {}, clear=True):
                self.assertEqual(sec_common.env_value("SEC_USER_AGENT"), "Research tester@example.org")
                with patch.dict(sec_common.os.environ, {"SEC_USER_AGENT": "Other contact@example.org"}):
                    self.assertEqual(sec_common.env_value("SEC_USER_AGENT"), "Other contact@example.org")

    def test_sec_index_follows_archive_pages_and_keeps_foreign_filings(self):
        import extract_sec_filings as sec
        import json
        recent = {"form": ["10-Q"], "filingDate": ["2026-01-01"], "accessionNumber": ["a"], "primaryDocument": ["a.htm"], "acceptanceDateTime": ["2026-01-01T21:00:00Z"]}
        archive = {"form": ["20-F", "10-K"], "filingDate": ["2022-03-01", "2021-03-01"], "accessionNumber": ["b", "c"], "primaryDocument": ["b.htm", "c.htm"]}
        record = {"filings": {"recent": recent, "files": [{"name": "older.json"}]}}
        with patch.object(sec, "get", side_effect=[json.dumps(record).encode(), json.dumps(archive).encode()]):
            filings = sec.collect_filings("0000000001", "Test contact@example.org", "2022-01-01")
        self.assertEqual([f["form"] for f in filings], ["10-Q", "20-F"])
        self.assertEqual(filings[0]["acceptance_datetime"], "2026-01-01T21:00:00Z")
        self.assertEqual(filings[1]["acceptance_datetime"], "")


if __name__ == "__main__":
    unittest.main()
