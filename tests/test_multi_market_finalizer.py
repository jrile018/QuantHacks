"""Bounded finalizer guard checks; no API calls, credentials, or normalization."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / 'scripts/multi_market/finalize_options_remote.py'
spec = importlib.util.spec_from_file_location('full_options_finalizer', MODULE)
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


class FullOptionsFinalizerTest(unittest.TestCase):
    def test_real_provider_id_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'different job'):
            finalizer.safe_job_details({'id': 'OTHER', 'state': 'done'})

    def test_legacy_job_id_mismatch_is_rejected_even_with_correct_id(self):
        with self.assertRaisesRegex(ValueError, 'different job'):
            finalizer.safe_job_details({'id': finalizer.JOB_ID, 'job_id': 'OTHER', 'state': 'done'})

    def test_metadata_keeps_only_nonsensitive_status_fields(self):
        result = finalizer.safe_job_details({'id': finalizer.JOB_ID, 'state': 'done',
            'progress': 100, 'cost_usd': 1.25, 'record_count': 12, 'actual_size': 345,
            'download_url': 'fixture_url', 'api_key': 'fixture_value', 'user': 'fixture_user'})
        self.assertEqual(result, {'state': 'done', 'progress': 100, 'cost_usd': 1.25,
                                  'record_count': 12, 'actual_size': 345})

    def test_local_or_different_root_cannot_start_heavy_work(self):
        with self.assertRaisesRegex(RuntimeError, 'isolated home-pc root'):
            finalizer.run(Path(tempfile.gettempdir()))

    def test_unexpected_provider_metadata_shape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            finalizer.safe_job_details([{'id': finalizer.JOB_ID}])


if __name__ == '__main__':
    unittest.main()
