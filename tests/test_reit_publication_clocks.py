"""Clock boundaries: prevent period, amendment, receipt and quarantine leakage."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.reit_publication_clocks import build_clock_record, cutoff_status, build_packet, build_peer_packet, _path


def evidence(**changes):
    row = dict(source_id='0000001234-26-000001/main.htm', cik='0000001234',
               accession='0000001234-26-000001', source_sha256='a' * 64,
               selected_original_sha256='a' * 64, form='10-Q',
               effective_period='2024-12-31', sec_acceptance_at_utc='2026-01-02T15:00:00Z',
               acceptance_evidence={'source_sha256': 'b' * 64, 'locator': '/filings/recent/0'},
               retrieved_at_utc='2026-10-03T22:00:00Z', source_status='eligible_as_primary',
               identity_verified=True, integrity_verified=True)
    row.update(changes)
    return row


class ClockTests(unittest.TestCase):
    def record(self, **changes):
        return build_clock_record(evidence(**changes), review_at_utc='2026-10-04T12:00:00Z')

    def test_explicit_windows_origin_maps_to_runtime_without_guessing(self):
        origin = 'C:/Users/owner/QuantHaxs'
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp).resolve()
            wanted = runtime/'data'/'processed'/'source'/'receipt.json'
            for source in [r'C:\Users\owner\QuantHaxs\data\processed\source\receipt.json',
                           'C:/Users/owner/QuantHaxs/data/processed/source/receipt.json',
                           r'data\processed\source\receipt.json',
                           'data/processed/source/receipt.json']:
                with self.subTest(source=source):
                    self.assertEqual(_path(source,runtime,origin_project_root=origin),wanted)
            self.assertEqual(_path(wanted,runtime,origin_project_root=origin),wanted)

    def test_windows_origin_rejects_outside_drives_prefix_tricks_and_traversal(self):
        origin = 'C:/Users/owner/QuantHaxs'
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp).resolve()
            for source in ['D:/Users/owner/QuantHaxs/data/receipt.json',
                           'C:/Users/other/QuantHaxs/data/receipt.json',
                           'C:/Users/owner/QuantHaxs-elsewhere/data/receipt.json',
                           'C:relative.json', r'\outside\receipt.json',
                           r'..\outside.json', 'data/../../outside.json',
                           'C:/Users/owner/QuantHaxs/data/../outside.json',
                           r'data\receipt.json:alternate-stream']:
                with self.subTest(source=source), self.assertRaises(ValueError):
                    _path(source,runtime,origin_project_root=origin)

    def test_origin_is_opt_in_and_must_be_an_absolute_windows_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp).resolve()
            self.assertEqual(_path('data/receipt.json',runtime),runtime/'data'/'receipt.json')
            for origin in ['relative/root','C:relative', 'C:/Users/owner/../project']:
                with self.subTest(origin=origin), self.assertRaises(ValueError):
                    _path('data/receipt.json',runtime,origin_project_root=origin)

    def test_origin_mapping_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            runtime = Path(tmp).resolve()
            try:
                (runtime/'linked').symlink_to(Path(outside),target_is_directory=True)
            except OSError:
                self.skipTest('Host does not permit creating a directory symlink; run on Linux runtime')
            with self.assertRaises(ValueError):
                _path(r'linked\receipt.json',runtime,origin_project_root='C:/Users/owner/QuantHaxs')

    def test_later_disclosure_cannot_be_backdated_to_effective_period(self):
        row = self.record()
        self.assertEqual(row['effective_period'], '2024-12-31')
        self.assertEqual(row['assumed_available_at_utc'], '2026-01-03T15:00:00Z')
        self.assertIsNone(row['first_public_at_utc'])
        self.assertEqual(row['first_public_status'], 'unknown')
        self.assertFalse(cutoff_status(row, '2025-01-01T20:00:00Z', 'historical_replay')['eligible'])
        self.assertFalse(row['canonical_consumer_ready'])

    def test_current_retrieval_does_not_establish_historical_receipt(self):
        row = self.record()
        result = cutoff_status(row, '2026-02-01T20:00:00Z', 'observed')
        self.assertFalse(result['eligible'])
        self.assertIn('actual_receipt_unknown', result['reasons'])
        self.assertIsNone(row['received_at_utc'])

    def test_exact_cutoff_is_inclusive_and_one_microsecond_early_is_excluded(self):
        row = self.record()
        self.assertTrue(cutoff_status(row, '2026-01-03T15:00:00Z', 'historical_replay')['eligible'])
        self.assertFalse(cutoff_status(row, '2026-01-03T14:59:59.999999Z', 'historical_replay')['eligible'])

    def test_date_only_keeps_dst_day_interval_and_uses_upper_bound(self):
        row = self.record(sec_acceptance_at_utc=None, sec_acceptance_date='2024-03-10',
                          acceptance_timezone='America/New_York')
        self.assertEqual(row['acceptance_lower_utc'], '2024-03-10T05:00:00Z')
        self.assertEqual(row['acceptance_upper_utc'], '2024-03-11T04:00:00Z')
        self.assertEqual(row['assumed_available_at_utc'], '2024-03-12T04:00:00Z')
        self.assertEqual(row['acceptance_precision'], 'date')
        fall = self.record(sec_acceptance_at_utc=None, sec_acceptance_date='2024-11-03',
                           acceptance_timezone='America/New_York')
        self.assertEqual(fall['acceptance_lower_utc'], '2024-11-03T04:00:00Z')
        self.assertEqual(fall['acceptance_upper_utc'], '2024-11-04T05:00:00Z')

    def test_date_and_naive_timestamp_require_timezone_evidence(self):
        for changes in [dict(sec_acceptance_at_utc='2026-01-02T10:00:00'),
                        dict(sec_acceptance_at_utc=None, sec_acceptance_date='2024-03-10')]:
            with self.assertRaises(ValueError):
                self.record(**changes)

    def test_offset_timestamp_normalizes_without_guessing(self):
        row = self.record(sec_acceptance_at_utc='2026-01-02T10:00:00-05:00')
        self.assertEqual(row['sec_acceptance_at_utc'], '2026-01-02T15:00:00Z')

    def test_future_retrieval_and_review_before_retrieval_are_excluded(self):
        row = self.record(retrieved_at_utc='2026-10-05T12:00:00Z')
        self.assertIn('retrieval_after_review', row['exclusion_reasons'])
        self.assertFalse(cutoff_status(row, '2026-10-06T12:00:00Z', 'historical_replay')['eligible'])

    def test_quarantine_conflict_unselected_version_and_amendment_are_excluded(self):
        for changes, reason in [({'source_status':'quarantined'}, 'source_quarantined'),
                                ({'source_conflict':True}, 'source_conflict'),
                                ({'selected_original_sha256':'c'*64}, 'unselected_source_version'),
                                ({'form':'10-Q/A'}, 'amendment_not_original')]:
            row = self.record(**changes)
            self.assertIn(reason, row['exclusion_reasons'])
            self.assertIsNone(row['assumed_available_at_utc'])
            self.assertFalse(cutoff_status(row, '2026-12-01T00:00:00Z', 'historical_replay')['eligible'])

    def test_observed_requires_bound_public_evidence_and_actual_processing(self):
        row = self.record(first_public_at_utc='2026-01-02T15:03:00Z',
                          first_public_evidence={'source_sha256':'a'*64, 'locator':'release-receipt'},
                          received_at_utc='2026-01-02T15:04:00Z',
                          processed_at_utc='2026-01-02T15:05:00Z')
        self.assertTrue(cutoff_status(row, '2026-01-02T15:05:00Z', 'observed')['eligible'])
        self.assertFalse(cutoff_status(row, '2026-01-02T15:04:59Z', 'observed')['eligible'])
        unknown = self.record(first_public_at_utc='2026-01-02T15:03:00Z')
        self.assertIsNone(unknown['first_public_at_utc'])
        self.assertIn('unbound_public_evidence', unknown['exclusion_reasons'])

    def test_future_actual_receipt_and_reversed_processing_are_excluded(self):
        for receipt, processed in [('2026-10-05T15:04:00Z','2026-10-05T15:05:00Z'),
                                   ('2026-01-02T15:05:00Z','2026-01-02T15:04:00Z')]:
            row = self.record(first_public_at_utc='2026-01-02T15:03:00Z',
                              first_public_evidence={'source_sha256':'a'*64,'locator':'receipt'},
                              received_at_utc=receipt, processed_at_utc=processed)
            self.assertFalse(cutoff_status(row,'2026-12-01T00:00:00Z','observed')['eligible'])

    def test_frozen_policy_cannot_be_changed_silently(self):
        with self.assertRaises(ValueError):
            build_clock_record(evidence(), review_at_utc='2026-10-04T12:00:00Z',
                               policy={'name':'sec_acceptance_plus_24h_or_date_upper_plus_24h_v1','seconds':0})

    def test_unknown_grade_proposal_stays_excluded_and_does_not_fabricate_public(self):
        row = self.record(source_status='needs_review')
        self.assertEqual(row['proposed_assumed_available_at_utc'], '2026-01-03T15:00:00Z')
        self.assertIsNone(row['assumed_available_at_utc'])
        self.assertFalse(cutoff_status(row,'2026-02-01T00:00:00Z','historical_replay')['eligible'])
        self.assertIsNone(row['first_public_at_utc'])

    def test_public_date_interval_cannot_be_used_before_day_upper_bound(self):
        row = self.record(first_public_date='2026-01-02', public_timezone='America/New_York',
                          first_public_evidence={'source_sha256':'a'*64,'locator':'dated-release'},
                          received_at_utc='2026-01-02T15:04:00Z', processed_at_utc='2026-01-02T15:05:00Z')
        self.assertIsNone(row['first_public_at_utc'])
        self.assertEqual(row['first_public_status'],'date_interval_evidence_bound')
        self.assertIn('receipt_before_public_upper_bound',row['exclusion_reasons'])
        self.assertFalse(cutoff_status(row,'2026-01-02T15:05:00Z','observed')['eligible'])

    def test_packet_binds_bytes_and_source_identity_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / 'cache' / '0000001234'
            cache.mkdir(parents=True)
            raw = b'original filing'
            (cache/'filing.htm').write_bytes(raw)
            submissions = {'cik':'0000001234','filings':{'recent':{
                'accessionNumber':['0000001234-26-000001'], 'form':['10-Q'],
                'reportDate':['2024-12-31'],'acceptanceDateTime':['2026-01-02T15:00:00Z'],
                'primaryDocument':['main.htm']}}}
            (cache/'submissions.json').write_text(json.dumps(submissions))
            manifest = {'collected_at':'2026-10-03T22:00:00Z','companies':[{
                'cik':'0000001234','metadata_receipts':[{'url':'https://data.sec.gov/submissions/CIK0000001234.json',
                  'http_status':200,'source':'http','cache_path':str(cache/'submissions.json')}]}],
                'documents':[{'cik':'0000001234','accession':'0000001234-26-000001',
                'form':'10-Q','filename':'main.htm','url':'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/main.htm',
                'source_path':str(cache/'filing.htm'),'sha256':hashlib.sha256(raw).hexdigest(),
                'document_role':'primary','reportDate':'2024-12-31','acceptanceDateTime':'2026-01-02T15:00:00Z'}]}
            collection = root/'manifest.json'
            collection.write_text(json.dumps(manifest))
            snapshot = root/'sources.jsonl'
            snapshot.write_text(json.dumps({'source_id':'0000001234-26-000001/main.htm',
                'url':manifest['documents'][0]['url'],'source_sha256':hashlib.sha256(raw).hexdigest(),
                'eligibility':'eligible_as_primary','quality_axes':{'content_identity':{'state':'verified'},
                'integrity':{'state':'verified'}}})+'\n')
            out = root/'out'
            result = build_packet(collection, snapshot, out, root=root, review_at_utc='2026-10-04T12:00:00Z')
            self.assertEqual(result['row_count'],1)
            self.assertEqual(result['replay_proxy_candidate_count'],1)
            self.assertEqual(result['observed_ready_count'],0)
            self.assertTrue((out/'publication_clocks.jsonl').is_file())
            with self.assertRaises(FileExistsError):
                build_packet(collection,snapshot,out,root=root,review_at_utc='2026-10-04T12:00:00Z')
            (cache/'filing.htm').write_bytes(b'changed version')
            changed = build_packet(collection,snapshot,root/'changed',root=root,review_at_utc='2026-10-04T12:00:00Z')
            self.assertEqual(changed['replay_proxy_candidate_count'],0)
            self.assertEqual(changed['exclusion_counts']['source_bytes_mismatch'],1)
            (cache/'filing.htm').write_bytes(raw)
            original_grade = json.loads(snapshot.read_text())
            for index, wrong_identity in enumerate([
                    '0000001234-26-000002/main.htm',
                    '0000001234-26-000001/other.htm', None]):
                with self.subTest(source_id=wrong_identity):
                    mismatched_grade = dict(original_grade, source_id=wrong_identity)
                    snapshot.write_text(json.dumps(mismatched_grade)+'\n')
                    mismatched = build_packet(collection,snapshot,root/f'identity-mismatch-{index}',
                        root=root,review_at_utc='2026-10-04T12:00:00Z')
                    self.assertEqual(mismatched['replay_proxy_candidate_count'],0)
                    self.assertEqual(mismatched['exclusion_counts']['snapshot_source_identity_mismatch'],1)
                    excluded = json.loads((root/f'identity-mismatch-{index}'/'publication_clocks.jsonl').read_text())
                    self.assertEqual(excluded['source_id'],'0000001234-26-000001/main.htm')
                    self.assertIsNone(excluded['assumed_available_at_utc'])

    def test_peer_packet_requires_exact_receipt_metadata_and_separate_source_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = b'<html>retained original</html>'
            digest = hashlib.sha256(raw).hexdigest()
            (root/'original.htm').write_bytes(raw)
            recent = {'accessionNumber':['0000001234-24-000001'], 'form':['10-Q'],
                'reportDate':['2024-03-31'], 'primaryDocument':['main.htm'],
                'acceptanceDateTime':['2024-05-01T15:00:00Z']}
            metadata = root/'submissions.json'
            metadata.write_text(json.dumps({'cik':'0000001234','filings':{'recent':recent}}))
            meta_sha = hashlib.sha256(metadata.read_bytes()).hexdigest()
            collection = root/'collection.json'
            collection.write_text(json.dumps({'companies':[{'cik':'0000001234','metadata_receipts':[{
                'url':'https://data.sec.gov/submissions/CIK0000001234.json','http_status':200,
                'source':'http','cache_path':str(metadata)}]}]}))
            url = 'https://www.sec.gov/Archives/edgar/data/1234/000000123424000001/main.htm'
            receipt = {'receipt_id':'receipt-1','status':200,'publicly_available':True,
                'source_sha256':digest,'response_sha256':digest,'url':url,'final_url':url,
                'retrieved_at':'2026-10-03T22:00:00Z'}
            ledger = root/'receipts.json'
            ledger.write_text(json.dumps({'receipts':[receipt]}))
            doc = {'cik':'0000001234','accession':'0000001234-24-000001','form':'10-Q',
                'primary_document':'main.htm','source_path':'original.htm','sha256':digest,'url':url,
                'receipt':receipt,'report_date':'2024-03-31','sec_acceptance_datetime':'2024-05-01T15:00:00Z',
                'official_metadata':{'metadata_source_sha256':meta_sha,'accessionNumber':'0000001234-24-000001',
                    'form':'10-Q','primaryDocument':'main.htm','reportDate':'2024-03-31',
                    'acceptanceDateTime':'2024-05-01T15:00:00Z'}}
            peer = root/'peer.json'
            payload = {'broker_receipts_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest(),'documents':[doc]}
            peer.write_text(json.dumps(payload))
            proposed = build_peer_packet(peer,ledger,collection,root/'proposed',root=root,
                                         review_at_utc='2026-10-04T12:00:00Z')
            self.assertEqual(proposed['proposed_replay_clock_count'],1)
            self.assertEqual(proposed['replay_proxy_candidate_count'],0)
            self.assertEqual(proposed['historical_accession_count'],1)
            grades = root/'grades.jsonl'
            grade = {'source_id':'0000001234-24-000001/main.htm','source_sha256':digest,
                'eligibility':'eligible_as_primary','quality_axes':{'content_identity':{'state':'verified'}}}
            grades.write_text(json.dumps(grade)+'\n')
            qualified = build_peer_packet(peer,ledger,collection,root/'qualified',root=root,
                review_at_utc='2026-10-04T12:00:00Z',source_grades=grades)
            self.assertEqual(qualified['replay_proxy_candidate_count'],1)
            row = json.loads((root/'qualified/publication_clocks.jsonl').read_text())
            self.assertEqual(row['assumed_available_at_utc'],'2024-05-02T15:00:00Z')
            self.assertEqual(row['retrieved_at_utc'],'2026-10-03T22:00:00Z')
            self.assertIsNone(row['first_public_at_utc'])
            payload['documents'][0]['receipt']['response_sha256'] = 'b'*64
            peer.write_text(json.dumps(payload))
            bad = build_peer_packet(peer,ledger,collection,root/'bad-receipt',root=root,
                review_at_utc='2026-10-04T12:00:00Z',source_grades=grades)
            self.assertEqual(bad['replay_proxy_candidate_count'],0)
            self.assertEqual(bad['proposed_replay_clock_count'],0)
            self.assertEqual(bad['exclusion_counts']['document_receipt_mismatch'],1)
            payload['broker_receipts_sha256'] = 'c'*64
            peer.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                build_peer_packet(peer,ledger,collection,root/'bad-ledger',root=root,
                    review_at_utc='2026-10-04T12:00:00Z')
            # Portable reads consume the original Windows paths and BOM bytes,
            # without rewriting either the JSON or the retained HTTP receipts.
            origin = 'C:/Users/owner/QuantHaxs'
            payload['broker_receipts_sha256'] = hashlib.sha256(ledger.read_bytes()).hexdigest()
            payload['documents'][0]['receipt']['response_sha256'] = digest
            (root/'nested').mkdir()
            (root/'nested'/'original.htm').write_bytes(raw)
            payload['documents'][0]['source_path'] = r'nested\original.htm'
            metadata.write_bytes(b'\xef\xbb\xbf'+metadata.read_bytes())
            payload['documents'][0]['official_metadata']['metadata_source_sha256'] = hashlib.sha256(metadata.read_bytes()).hexdigest()
            peer.write_bytes(b'\xef\xbb\xbf'+json.dumps(payload).encode('utf-8'))
            collection_obj = json.loads(collection.read_text())
            collection_obj['companies'][0]['metadata_receipts'][0]['cache_path'] = origin+'/submissions.json'
            collection.write_bytes(b'\xef\xbb\xbf'+json.dumps(collection_obj).encode('utf-8'))
            grades.write_bytes(b'\xef\xbb\xbf'+grades.read_bytes())
            retained = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        [peer,ledger,collection,metadata,grades,root/'nested'/'original.htm']}
            portable = build_peer_packet(peer,ledger,collection,root/'portable',root=root,
                review_at_utc='2026-10-04T12:00:00Z',source_grades=grades,origin_project_root=origin)
            self.assertEqual(portable['replay_proxy_candidate_count'],1)
            self.assertEqual(portable['path_resolution']['origin_project_root'],origin)
            self.assertEqual(portable['path_resolution']['runtime_project_root'],str(root.resolve()))
            self.assertEqual(retained,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in retained})
            portable_row = json.loads((root/'portable/publication_clocks.jsonl').read_text())
            self.assertEqual(portable_row['retrieved_at_utc'],'2026-10-03T22:00:00Z')
            self.assertEqual(portable_row['present_public_observation']['receipt_id'],'receipt-1')
            self.assertIsNone(portable_row['first_public_at_utc'])


if __name__ == '__main__':
    unittest.main()
