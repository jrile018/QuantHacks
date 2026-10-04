import unittest

from src.reit_cash_facts import cash_flow_rows, cash_bridge_checks


def fact(value, *, accn="0000123456-26-000001", start="2026-01-01", end="2026-03-31"):
    return {"val": value, "accn": accn, "start": start, "end": end,
            "filed": "2026-05-01", "form": "10-Q", "fy": 2026, "fp": "Q1"}


class CashFactsTests(unittest.TestCase):
    def test_cash_bridge_excluding_fx_needs_no_assumed_zero_fx(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20)],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect": [fact(50)],
        }
        rows = cash_flow_rows("123456", {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}})
        check = cash_bridge_checks(rows)[0]
        self.assertEqual(check["status"], "balanced")
        self.assertFalse(check["fx_included"])
        self.assertEqual(check["cash_basis"], "cash_and_restricted_cash")

    def test_cash_and_restricted_cash_cannot_use_cash_only_fx(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20)],
            "EffectOfExchangeRateOnCashAndCashEquivalents": [fact(2)],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": [fact(52)],
        }
        rows = cash_flow_rows("123456", {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}})
        check = cash_bridge_checks(rows)[0]
        self.assertEqual(check["status"], "incomplete")
        self.assertIn("fx", check["missing"])

    def test_debt_balance_is_separate_from_cash_flow_and_not_summed(self):
        balance = fact(900)
        del balance["start"]
        payload = {"facts": {"us-gaap": {
            "LongTermDebtNoncurrent": {"units": {"USD": [balance]}},
            "ProceedsFromIssuanceOfCommonStock": {"units": {"USD": [fact(20)]}},
            "ProceedsFromCollectionOfLoansReceivable": {"units": {"USD": [fact(30)]}},
        }}}
        rows = cash_flow_rows("123456", payload)
        self.assertEqual(len(rows), 3)
        debt = next(row for row in rows if row["tag"] == "LongTermDebtNoncurrent")
        self.assertEqual(debt["amount_kind"], "balance")
        self.assertEqual(debt["period_start"], "")
        self.assertEqual(cash_bridge_checks(rows), [])
        self.assertEqual(next(row for row in rows if row["value"] == 20)["cash_direction"], "inflow")

    def test_unknown_precision_does_not_hide_a_small_difference(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20)],
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": [fact(0)],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": [fact(51)],
        }
        payload = {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}}
        check = cash_bridge_checks(cash_flow_rows("123456", payload))[0]
        self.assertEqual(check["status"], "unresolved")
        self.assertEqual(check["precision_status"], "unknown")
        self.assertEqual(check["tolerance"], "")
        for values in tags.values():
            values[0]["decimals"] = -3
        check = cash_bridge_checks(cash_flow_rows("123456", payload))[0]
        self.assertEqual(check["status"], "balanced")
        self.assertEqual(check["precision_status"], "reported")
        self.assertGreater(check["tolerance"], 1)

    def test_invalid_nonfinite_facts_are_not_financial_evidence(self):
        payload = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities":
                   {"units": {"USD": [fact(True), fact(float("nan")), fact(float("inf"))]}}}}}
        self.assertEqual(cash_flow_rows("123456", payload), [])

    def test_different_currency_and_period_do_not_complete_a_bridge(self):
        payload = {"facts": {"us-gaap": {
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fact(100)]}},
            "NetCashProvidedByUsedInInvestingActivities": {"units": {"USD": [fact(-30)]}},
            "NetCashProvidedByUsedInFinancingActivities": {"units": {"CAD": [fact(-20)]}},
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                "units": {"USD": [fact(0, start="2026-04-01", end="2026-06-30")]}},
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": {
                "units": {"USD": [fact(50)]}},
        }}}
        rows = cash_flow_rows("123456", payload)
        self.assertIn("CAD", {row["unit"] for row in rows})
        self.assertTrue(all(check["status"] == "incomplete" for check in cash_bridge_checks(rows)))

    def test_source_and_context_are_preserved(self):
        payload = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities":
                   {"units": {"USD": [fact(100)]}}}}}
        rows = cash_flow_rows("0000123456", payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 100)
        self.assertEqual(rows[0]["cik"], "0000123456")
        self.assertEqual(rows[0]["accession"], "0000123456-26-000001")
        self.assertEqual(rows[0]["period_start"], "2026-01-01")
        self.assertIn("/123456/000012345626000001/", rows[0]["filing_url"])
        self.assertTrue(rows[0]["filing_url"].endswith("0000123456-26-000001-index.html"))

    def test_cash_bridge_balanced_only_in_same_context(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20)],
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": [fact(2)],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": [fact(52)],
        }
        rows = cash_flow_rows("123456", {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}})
        checks = cash_bridge_checks(rows)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "balanced")
        self.assertEqual(checks[0]["difference"], 0)

    def test_missing_or_different_accession_is_incomplete(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20, accn="0000123456-26-000002")],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": [fact(50)],
        }
        rows = cash_flow_rows("123456", {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}})
        checks = cash_bridge_checks(rows)
        self.assertTrue(all(c["status"] == "incomplete" for c in checks))
        self.assertTrue(any("financing" in c["missing"] for c in checks))

    def test_mismatch_is_unresolved_and_debt_tag_is_kept(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20)],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": [fact(60)],
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": [fact(0)],
            "ProceedsFromIssuanceOfLongTermDebt": [fact(500)],
        }
        rows = cash_flow_rows("123456", {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}})
        self.assertIn("debt_proceeds", {row["metric"] for row in rows})
        self.assertEqual(cash_bridge_checks(rows)[0]["status"], "unresolved")

    def test_conflicting_duplicate_fact_makes_bridge_incomplete(self):
        tags = {
            "NetCashProvidedByUsedInOperatingActivities": [fact(100), fact(101)],
            "NetCashProvidedByUsedInInvestingActivities": [fact(-30)],
            "NetCashProvidedByUsedInFinancingActivities": [fact(-20)],
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": [fact(0)],
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": [fact(50)],
        }
        rows = cash_flow_rows("123456", {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in tags.items()}}})
        check = cash_bridge_checks(rows)[0]
        self.assertEqual(check["status"], "incomplete")
        self.assertIn("ambiguous:operating", check["missing"])


if __name__ == "__main__":
    unittest.main()
