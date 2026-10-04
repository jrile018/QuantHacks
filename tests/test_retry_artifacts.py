import base64
import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.retry_hipergator_pilot import save_artifact


class RetryArtifactTests(unittest.TestCase):
    def test_verified_artifact_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = {'path': 'results/pilot.json', 'base64': base64.b64encode(b'{}').decode(),
                      'sha256': hashlib.sha256(b'{}').hexdigest()}
            save_artifact(Path(tmp), record)
            self.assertEqual((Path(tmp) / record['path']).read_bytes(), b'{}')

    def test_invalid_hash_or_escaping_path_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, digest in [('inside.json', '0'*64), ('../escape.json', hashlib.sha256(b'{}').hexdigest())]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    save_artifact(Path(tmp), {'path': name, 'base64': 'e30=', 'sha256': digest})
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
