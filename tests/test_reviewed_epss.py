import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'data/packaged_software'))
from expand_reviewed_epss import checked_scores


class ReviewedScoresTests(unittest.TestCase):
    def response(self, **changes):
        row = {'date': '2022-01-01', 'cve': 'CVE-2021-1', 'epss': '0.1', 'percentile': '0.9'}
        row.update(changes)
        return {'status': 'OK', 'data': [row]}

    def test_cached_wrong_date_is_rejected(self):
        with self.assertRaises(ValueError):
            checked_scores(self.response(date='2023-01-01'), '2022-01-01', ['CVE-2021-1'])

    def test_invalid_probability_is_rejected(self):
        for value in ['1.2', '-0.1', 'nan']:
            with self.assertRaises(ValueError):
                checked_scores(self.response(epss=value), '2022-01-01', ['CVE-2021-1'])

    def test_unrequested_cve_is_rejected_for_new_batch(self):
        with self.assertRaises(ValueError):
            checked_scores(self.response(), '2022-01-01', ['CVE-2021-2'], strict_cves=True)


if __name__ == '__main__':
    unittest.main()
