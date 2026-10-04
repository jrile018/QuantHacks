import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data/packaged_software"))
from recover_financial_density import same_filing_quarters, unique_fact


def fact(start, end, value, accession="a", tag="tag", unit="USD", filed="2024-08-01", fact_id="x"):
    return dict(cik="0000000001", metric="revenue", accession=accession, tag=tag, unit=unit,
                period_start=start, period_end=end, filed_date=filed, value=str(value), fact_id=fact_id)


class DensityTests(unittest.TestCase):
    def test_same_accession_ytd_difference(self):
        rows = [fact("2024-01-01", "2024-03-31", 10), fact("2024-01-01", "2024-06-30", 25, fact_id="y")]
        result = same_filing_quarters(rows)
        self.assertEqual([(r[1], r[2]) for r in result], [(10, "2024-01-01"), (15, "2024-04-01")])

    def test_cross_accession_never_recovers_ytd_difference(self):
        rows = [fact("2024-01-01", "2024-03-31", 10), fact("2024-01-01", "2024-06-30", 25, accession="b")]
        self.assertEqual(len(same_filing_quarters(rows)), 1)

    def test_conflicting_values_are_not_arbitrarily_selected(self):
        self.assertIsNone(unique_fact([fact("2024-01-01", "2024-03-31", 10), fact("2024-01-01", "2024-03-31", 11)]))

    def test_units_tags_and_filing_dates_cannot_be_mixed(self):
        for change in [dict(unit="EUR"), dict(tag="other"), dict(filed="2024-09-01")]:
            rows = [fact("2024-01-01", "2024-03-31", 10), fact("2024-01-01", "2024-06-30", 25, **change)]
            self.assertEqual(len(same_filing_quarters(rows)), 1)

    def test_half_year_is_not_treated_as_a_quarter(self):
        self.assertEqual(same_filing_quarters([fact("2024-01-01", "2024-06-30", 25)]), [])


if __name__ == "__main__":
    unittest.main()
