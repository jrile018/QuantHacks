import json
from pathlib import Path
import tempfile
import unittest
from hpc.start_ai_workshop import make_commands, dependent_command


class HiPerGatorSetupTests(unittest.TestCase):
    def test_commands_use_observed_account_and_separate_cpu_setup_from_gpu(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'pilot').mkdir()
            (root / 'pilot/documents.jsonl').write_text(json.dumps({'document_id': 'one', 'source_path': 'one.png'}))
            (root / 'pilot/filings.json').write_text(json.dumps([{'cik': '1', 'accession': 'x', 'submission_path': 'x.txt', 'source_sha256': 'a'*64}]))
            setup, pilot, profile = make_commands(root)
            self.assertIn('--account=ai-workshop', setup)
            self.assertIn('--qos=ai-workshop', pilot)
            self.assertFalse(any(arg.startswith('--gres') for arg in setup))
            self.assertIn('--partition=hpg-turin', pilot)
            self.assertIn('--gres=gpu:l4:1', pilot)
            self.assertEqual(profile['python'], str(root / 'runtime/env/bin/python'))
            chained = dependent_command(pilot, '123456;hipergator\n')
            self.assertIn('--dependency=afterok:123456', chained)
            self.assertIn('--kill-on-invalid-dep=yes', chained)
            self.assertNotIn('--dependency=afterok:123456', pilot)

    def test_dependency_rejects_non_job_ids(self):
        for value in ('', 'Submitted batch job 1', '123\n456', 'x;abc'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                dependent_command(['sbatch', 'job.sbatch'], value)


if __name__ == '__main__':
    unittest.main()
