import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data/packaged_software'))
from audit_research_quality import normalize_cik


class CikAuditTests(unittest.TestCase):
    def test_csv_integer_and_float_serializations_have_same_identity(self):
        self.assertEqual(normalize_cik('935036.0'),normalize_cik('0000935036'))

    def test_fractional_and_missing_identifiers_are_invalid(self):
        self.assertIsNone(normalize_cik('935036.5'))
        self.assertIsNone(normalize_cik('nan'))
        self.assertIsNone(normalize_cik('0'))

    def test_oversized_identifiers_are_not_truncated(self):
        self.assertIsNone(normalize_cik('12345678901'))


if __name__=='__main__': unittest.main()
