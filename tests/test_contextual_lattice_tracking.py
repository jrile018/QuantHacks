"""Frozen manifest and append-only lifecycle tests."""
import json
import tempfile
import unittest
from pathlib import Path

from src.contextual_lattice.tracking import append_lifecycle_event, file_sha256, write_frozen_manifest


class TrackingTests(unittest.TestCase):
    def test_manifest_freezes_configuration_and_source_before_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.csv'
            source.write_text('date,ticker\n2020-01-01,A\n', encoding='utf-8')
            manifest = write_frozen_manifest(root / 'run', {'hypothesis': 'catchup', 'ridge': 1},
                                             {'price_panel': source})
            self.assertEqual(manifest['sources']['price_panel']['sha256'], file_sha256(source))
            self.assertEqual(manifest['lifecycle'][0]['stage'], 'frozen_before_fit')
            with self.assertRaises(FileExistsError):
                write_frozen_manifest(root / 'run', {'hypothesis': 'reversal'}, {'price_panel': source})

    def test_events_are_append_only_and_output_hashes_are_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.csv'
            source.write_text('a', encoding='utf-8')
            run = root / 'run'
            write_frozen_manifest(run, {'hypothesis': 'reversal'}, {'panel': source})
            output = root / 'report.json'
            output.write_text('{}', encoding='utf-8')
            event = append_lifecycle_event(run, 'evaluated', {'report': output}, details={'status': 'blocked'})
            self.assertEqual(event['outputs']['report']['sha256'], file_sha256(output))
            output.write_text('{"changed":true}', encoding='utf-8')
            with self.assertRaises(ValueError):
                append_lifecycle_event(run, 'evaluated', {'report': output})
            saved = [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[1]['stage'], 'evaluated')


if __name__ == '__main__':
    unittest.main()
