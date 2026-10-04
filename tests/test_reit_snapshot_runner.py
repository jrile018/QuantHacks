"""Small retained fixtures; these tests perform no acquisition or PDF parsing."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

import tempfile
import unittest

from scripts.build_reit_snapshot import build_snapshot, publish_prepared, resolve_input_path
from src.reit_dataset import verify_snapshot


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def fixture(tmp_path, *, conditional=False, legacy_paths=False):
    build = tmp_path / 'data/processed/reit_build/fixture'
    collection = build / 'collection'
    raw_path = collection / 'cache/annual.htm'
    raw_path.parent.mkdir(parents=True)
    claim = 'If we qualify as a REIT, taxes may be lower.' if conditional else 'We have elected to be taxed as a REIT.'
    html = ('<html><body><p>Example REIT Corporation 2025-12-31</p><p>' + claim +
            '</p><table><tr><td>Common stock</td><td>EXR</td><td>NYSE</td></tr></table>'
            '<p>Cash proceeds 10. Example REIT Corporation, as issuer.</p></body></html>')
    raw_path.write_text(html, encoding='utf-8')
    digest = sha256(raw_path.read_bytes()).hexdigest()
    text_path = collection / 'text/annual.json'
    old = lambda p: 'C:\\old\\QuantHaxs\\' + str(p.relative_to(tmp_path)).replace('/', '\\') if legacy_paths else p.relative_to(tmp_path).as_posix()
    save(text_path, {'sha256': digest, 'source_path': old(raw_path), 'source_url': 'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/annual.htm',
                     'accession': '0000000001-26-000001', 'pages': [{'number': 1, 'text': 'Cash proceeds 10. Example REIT Corporation, as issuer.'}]})
    document = {'cik': '0000000001', 'accession': '0000000001-26-000001', 'filename': 'annual.htm',
                'url': 'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/annual.htm', 'form': '10-K',
                'reportDate': '2025-12-31', 'retrieved_at': '2026-10-03T20:00:00+00:00',
                'source_path': old(raw_path), 'text_path': old(text_path), 'sha256': digest}
    save(collection / 'manifest.json', {'companies': [{'cik': '0000000001', 'company_name': 'Example REIT Corporation'}], 'documents': [document]})
    save(build / 'discovery_candidates.json', {'candidates': [{'cik': '0000000001', 'ticker': 'EXR', 'name': 'Example REIT Corporation', 'security_id': '0000000001:EXR:common_candidate'}]})
    save(build / 'relationship_seed_assertions.json', {'assertions': [{'assertion_id': 'issuer', 'subject': {'legal_name': 'Example REIT Corporation', 'identifier': 'CIK 1'},
        'relation_type': 'issuer_under_indenture', 'object': {'legal_name': 'Example note'}, 'available_at': None,
        'evidence': {'document_id': '0000000001-26-000001/annual.htm', 'source_sha256': digest, 'quote': 'Example REIT Corporation, as issuer.', 'locator': 'page 1'}}]})
    return build, document, raw_path, text_path


def check_portable_path_resolution_handles_project_and_windows_manifest_paths(tmp_path):
    path = tmp_path / 'data/example.htm'
    path.parent.mkdir()
    path.write_text('example')
    assert resolve_input_path('data/example.htm', tmp_path) == path
    assert resolve_input_path(r'C:\old\QuantHaxs\data\example.htm', tmp_path) == path
    with unittest.TestCase().assertRaisesRegex(ValueError, 'outside|resolve'):
        resolve_input_path('../outside.htm', tmp_path)


def check_runner_recomputes_eligibility_and_publishes_verified_unknown_availability(tmp_path):
    build, document, raw, text = fixture(tmp_path)
    original = text.read_bytes()
    result = build_snapshot(build, project_root=tmp_path, retained_roots=[], as_of='2026-10-04T01:00:00+00:00')
    assert result['universe']['coverage']['validated_count'] == 1
    assert result['snapshot']['verified'] is True
    assert verify_snapshot(result['snapshot']['snapshot_dir'], source_root=tmp_path)['valid']
    assert result['snapshot']['counts']['role_edges'] == 1
    assert result['network']['role_edges'][0]['available_at'] is None
    assert result['snapshot']['historical_ready'] is False
    assert result['coverage']['collection_complete'] is False
    assert text.read_bytes() == original
    assert result['path_mapping']
    assert result['coverage']['extraction_integrity_gaps'][0]['kind'] == 'original_extraction_digest_unanchored'


def check_conditional_claim_cannot_reuse_old_validated_universe(tmp_path):
    build, *_ = fixture(tmp_path, conditional=True)
    save(build / 'universe.json', {'validated': [{'cik': '0000000001'}]})
    save(build / 'universe_evidence.json', {'evidence': [{'kind': 'reit_status', 'value': True}]})
    result = build_snapshot(build, project_root=tmp_path, retained_roots=[], as_of='2026-10-04T01:00:00+00:00')
    assert result['universe']['coverage']['validated_count'] == 0
    assert any(r.get('kind') == 'reit_status_review' for r in result['eligibility_evidence'])


def check_relocated_extraction_keeps_original_bytes_and_hash_provenance(tmp_path):
    build, _, _, text = fixture(tmp_path, legacy_paths=True)
    before = text.read_bytes()
    result = build_snapshot(build, project_root=tmp_path, retained_roots=[], as_of='2026-10-04T01:00:00+00:00')
    assert text.read_bytes() == before
    assert verify_snapshot(result['snapshot']['snapshot_dir'], source_root=tmp_path)['valid']
    copy = result['extraction_derivations'][0]
    assert copy['original_sha256'] == sha256(before).hexdigest()
    assert copy['derived_sha256'] == sha256(Path(copy['derived_path']).read_bytes()).hexdigest()


def check_modified_retained_raw_is_rejected_before_publication(tmp_path):
    build, _, raw, _ = fixture(tmp_path)
    raw.write_text('corrupt')
    with unittest.TestCase().assertRaisesRegex(ValueError, 'hash mismatch'):
        build_snapshot(build, project_root=tmp_path, retained_roots=[], as_of='2026-10-04T01:00:00+00:00')


class SnapshotRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_portable_paths(self):
        check_portable_path_resolution_handles_project_and_windows_manifest_paths(self.root)

    def test_legacy_metadata_size_clarification_preserves_input_manifest(self):
        build,document,raw,_=fixture(self.root)
        document['size']=50392915
        manifest=build/'collection/manifest.json'
        save(manifest,{'companies':[],'documents':[document]})
        original=manifest.read_bytes()
        result=build_snapshot(build,project_root=self.root,retained_roots=[],as_of='2026-10-04T01:00:00+00:00')
        exported=json.loads((build/'integrated/prepared/prepared_inputs.json').read_text())['documents'][0]
        self.assertEqual(exported['legacy_metadata_size'],50392915)
        self.assertEqual(exported['source_byte_count'],len(raw.read_bytes()))
        self.assertNotIn('size',exported)
        self.assertNotIn('filing_metadata_size',exported)
        self.assertEqual(manifest.read_bytes(),original)

    def test_integrated_publication(self):
        check_runner_recomputes_eligibility_and_publishes_verified_unknown_availability(self.root)

    def test_conditional_claim(self):
        check_conditional_claim_cannot_reuse_old_validated_universe(self.root)

    def test_relocated_extraction(self):
        check_relocated_extraction_keeps_original_bytes_and_hash_provenance(self.root)

    def test_corrupt_raw(self):
        check_modified_retained_raw_is_rejected_before_publication(self.root)

    def duplicate_fixture(self, *, substantive=False, same_bytes=False, arbitrary_scripts=False, short_scripts=False, non_sec=False):
        build, document, raw, text = fixture(self.root)
        original = raw.read_bytes()
        first_src = b'/hEyxvy/tDTQ/C5W/N8y/CEN74LRlKz4/wYOaNzSVtcwhtffaf7/U3FqJk0lAg/cDg9eQ/IuTns'
        second_src = b'/ve5kkgOKS/1tZ/IOZiCw/m5Q3Q8mpJLpc2XXi/W3QcSzUB/EnhTd/C15D1U'
        if arbitrary_scripts:
            first_src, second_src = b'https://arbitrary.example/first.js', b'https://arbitrary.example/change.js'
        if short_scripts:
            first_src, second_src = b'/first.js', b'/loan.js'
        first = original.replace(b'</body>', b'<script type="text/javascript"  src="' + first_src + b'"></script></body>')
        second = first if same_bytes else original.replace(b'</body>', b'<script type="text/javascript"  src="' + second_src + b'"></script></body>')
        if substantive:
            second = second.replace(b'Cash proceeds 10.', b'Cash proceeds 11.')
        raw.write_bytes(second)
        document['sha256'] = sha256(second).hexdigest()
        existing_text = json.loads(text.read_text())
        existing_text['sha256'] = document['sha256']
        if non_sec:
            document['url'] = 'https://issuer.example/annual.htm'
            existing_text['source_url'] = document['url']
        save(text, existing_text)
        save(build / 'collection/manifest.json', {'companies': [{'cik': '0000000001', 'company_name': 'Example REIT Corporation'}], 'documents': [document]})
        pilot = self.root / 'data/processed/pilot'
        pilot_raw = pilot / 'cache/annual.htm'
        pilot_raw.parent.mkdir(parents=True)
        pilot_raw.write_bytes(first)
        pilot_doc = {**document, 'source_path': pilot_raw.relative_to(self.root).as_posix(),
                     'text_path': (pilot / 'text/annual.json').relative_to(self.root).as_posix(), 'sha256': sha256(first).hexdigest()}
        save(self.root / pilot_doc['text_path'], {**existing_text, 'sha256': pilot_doc['sha256'], 'source_path': pilot_doc['source_path']})
        save(pilot / 'manifest.json', {'companies': [{'cik': '0000000001', 'company_name': 'Example REIT Corporation'}], 'documents': [pilot_doc]})
        return build, pilot

    def test_trailing_empty_external_script_variants_retain_both_raw_chains(self):
        build, pilot = self.duplicate_fixture()
        result = build_snapshot(build, project_root=self.root, retained_roots=[pilot], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['coverage']['source_representation_variant_count'], 1)
        self.assertEqual(result['coverage']['quarantined_source_url_count'], 0)
        inputs = json.loads(Path(result['prepared_inputs']).read_text())
        self.assertEqual(len(inputs['documents']), 2)
        self.assertEqual(len({d['sha256'] for d in inputs['documents']}), 2)
        self.assertEqual(result['universe']['coverage']['validated_count'], 1)
        self.assertEqual(inputs['provenance']['representation_variants'][0]['classification'], 'identical_except_trailing_empty_external_script')

    def test_substantive_same_url_variants_quarantine_eligibility_without_aborting(self):
        build, pilot = self.duplicate_fixture(substantive=True)
        result = build_snapshot(build, project_root=self.root, retained_roots=[pilot], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['coverage']['quarantined_source_url_count'], 1)
        self.assertEqual(result['universe']['coverage']['validated_count'], 0)
        self.assertEqual(len(result['network']['role_edges']), 0)
        inputs = json.loads(Path(result['prepared_inputs']).read_text())
        self.assertTrue(all(d['source_issues'] for d in inputs['documents']))
        self.assertTrue(any(r.get('item_type') == 'retained_source_conflict' for r in inputs['histories']['review']))

    def test_same_raw_duplicate_preserves_extraction_provenance(self):
        build, pilot = self.duplicate_fixture(same_bytes=True)
        result = build_snapshot(build, project_root=self.root, retained_roots=[pilot], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        inputs = json.loads(Path(result['prepared_inputs']).read_text())
        self.assertEqual(len(inputs['documents']), 2)
        self.assertEqual(inputs['provenance']['representation_variants'][0]['classification'], 'identical_raw_bytes_distinct_retained_chains')

    def test_arbitrary_external_script_changes_remain_quarantined(self):
        build, pilot = self.duplicate_fixture(arbitrary_scripts=True)
        result = build_snapshot(build, project_root=self.root, retained_roots=[pilot], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['coverage']['quarantined_source_url_count'], 1)
        self.assertEqual(result['universe']['coverage']['validated_count'], 0)

    def test_ordinary_relative_script_changes_remain_quarantined(self):
        build, pilot = self.duplicate_fixture(short_scripts=True)
        result = build_snapshot(build, project_root=self.root, retained_roots=[pilot], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['coverage']['quarantined_source_url_count'], 1)

    def test_sec_shaped_script_on_non_sec_source_remains_quarantined(self):
        build, pilot = self.duplicate_fixture(non_sec=True)
        result = build_snapshot(build, project_root=self.root, retained_roots=[pilot], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['coverage']['quarantined_source_url_count'], 1)

    def test_default_financial_scope_parses_only_completed_batch_sources(self):
        build, document, *_ = fixture(self.root)
        first = build_snapshot(build, project_root=self.root, retained_roots=[], prepare_only=True,
                               as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(first['coverage']['fresh_money_documents'], 0)
        self.assertEqual(first['coverage']['money_skipped_documents'], 1)
        save(build / 'batches/batch-1/batch_manifest.json', {'completed_document_urls': [document['url']],
             'completed_exhibit_urls': [], 'selected_collection_complete': False, 'history_complete': False})
        second = build_snapshot(build, project_root=self.root, retained_roots=[], prepare_only=True,
                                as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(second['coverage']['fresh_money_documents'], 1)
        self.assertEqual(second['coverage']['money_skipped_documents'], 0)
        self.assertFalse(second['coverage']['collection_complete'])

    def test_prepared_inputs_publish_after_project_is_moved(self):
        build, *_ = fixture(self.root, legacy_paths=True)
        prepared = build_snapshot(build, project_root=self.root, retained_roots=[], prepare_only=True,
                                  as_of='2026-10-04T01:00:00+00:00')
        moved = self.root / 'moved'
        shutil.copytree(self.root / 'data', moved / 'data')
        portable_path = Path(prepared['prepared_inputs']).relative_to(self.root)
        snapshot = publish_prepared(str(portable_path), project_root=moved)
        self.assertTrue(verify_snapshot(snapshot['snapshot_dir'], source_root=moved)['valid'])
        self.assertTrue(all(row['source_path'].startswith('data/') for row in snapshot['lineage']))

    def test_reused_records_bind_portable_text_without_changing_original(self):
        build, document, raw, text = fixture(self.root, legacy_paths=True)
        collection = build / 'collection'
        analysis = collection / 'money_analysis_v2'
        record = {'record_id': 'flow', 'issuer_cik': '0000000001', 'accession': document['accession'],
                  'source_kind': 'native_text', 'status': 'parsed', 'amount_kind': 'flow',
                  'amount_basis': 'reported_cash_movement', 'currency': 'USD', 'metric': 'proceeds',
                  'value': '10', 'period_type': 'duration', 'period_start': '2025-01-01', 'period_end': '2025-12-31',
                  'source_path': document['source_path'], 'source_sha256': document['sha256'],
                  'text_artifact_path': document['text_path'], 'text_artifact_sha256': sha256(text.read_bytes()).hexdigest(),
                  'evidence': [{'quote': 'Cash proceeds 10.', 'locator': 'page 1', 'source_path': document['source_path'], 'source_sha256': document['sha256']}]}
        analysis.mkdir()
        records = analysis / 'money_records.jsonl'
        records.write_text(json.dumps(record) + '\n', encoding='utf-8')
        review = analysis / 'review_candidates.jsonl'
        review.write_text('')
        save(analysis / 'analysis_manifest.json', {'collection_manifest_sha256': sha256((collection / 'manifest.json').read_bytes()).hexdigest(),
            'output_sha256': {'money_records.jsonl': sha256(records.read_bytes()).hexdigest(), 'review_candidates.jsonl': sha256(review.read_bytes()).hexdigest()},
            'documents': [{'source_url': document['url'], 'extracted_text_sha256': sha256(text.read_bytes()).hexdigest()}]})
        before = records.read_bytes()
        result = build_snapshot(build, project_root=self.root, retained_roots=[], as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['snapshot']['counts']['financial_histories'], 1)
        self.assertEqual(records.read_bytes(), before)
        exported = json.loads((Path(result['snapshot']['snapshot_dir']) / 'financial_histories.jsonl').read_text())
        self.assertEqual(exported['original_text_artifact_sha256'], sha256(text.read_bytes()).hexdigest())
        self.assertNotEqual(exported['text_artifact_path'], str(text))
        self.assertEqual(result['coverage']['extraction_integrity_gaps'], [])

    def test_older_positive_claim_does_not_mask_newer_conditional_annual(self):
        build, document, raw, text = fixture(self.root, conditional=True)
        older_raw = raw.with_name('older.htm')
        older_raw.write_text('<html><p>Example REIT Corporation 2024-12-31</p><p>We have elected to be taxed as a REIT.</p>'
                             '<table><tr><td>Common stock</td><td>EXR</td><td>NYSE</td></tr></table></html>')
        older_text = text.with_name('older.json')
        older = {**document, 'accession': '0000000001-25-000001', 'filename': 'older.htm', 'reportDate': '2024-12-31',
                 'url': 'https://www.sec.gov/Archives/edgar/data/1/000000000125000001/older.htm',
                 'source_path': older_raw.relative_to(self.root).as_posix(), 'text_path': older_text.relative_to(self.root).as_posix(),
                 'sha256': sha256(older_raw.read_bytes()).hexdigest()}
        save(older_text, {'source_path': older['source_path'], 'sha256': older['sha256'], 'source_url': older['url'],
                         'accession': older['accession'], 'pages': [{'number': 1, 'text': ''}]})
        manifest = build / 'collection/manifest.json'
        contents = json.loads(manifest.read_text())
        contents['documents'].append(older)
        save(manifest, contents)
        result = build_snapshot(build, project_root=self.root, retained_roots=[], as_of='2026-10-04T01:00:00+00:00')
        self.assertEqual(result['universe']['coverage']['validated_count'], 0)
        historical = [r for r in result['eligibility_evidence'] if r.get('value') is True and r['valid_from'] == '2024-12-31']
        self.assertTrue(historical)
        self.assertTrue(all(r['valid_to'] == '2025-12-31' for r in historical))


if __name__ == '__main__':
    unittest.main()
