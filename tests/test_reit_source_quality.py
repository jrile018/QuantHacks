import hashlib
import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from src.reit_source_quality import audit_source, audit_registry


BODY = b'<html><body>American Tower Corporation 2026-06-30 Revenue USD 100 million</body></html>'


def filing():
    return dict(url='https://www.sec.gov/Archives/edgar/data/1053507/000105350726000133/amt-20260630.htm',
                cik='0001053507', accession='0001053507-26-000133', document='amt-20260630.htm',
                issuer='American Tower Corporation', period='2026-06-30', form='10-Q',
                content_type='text/html', sha256=hashlib.sha256(BODY).hexdigest(),
                retrieved_at='2026-10-03T12:00:00Z', accepted_at='2026-08-01T12:00:00Z',
                financial_evidence=[dict(issuer='American Tower Corporation', period='2026-06-30',
                    metric='revenue', value='100', unit='USD', scale='1000000', basis='reported',
                    quote='Revenue USD 100 million', locator='body')])


class SourceQualityTests(unittest.TestCase):
    def test_sec_document_with_complete_evidence_is_primary(self):
        self.assertEqual(audit_source(filing(), BODY)['eligibility'], 'eligible_as_primary')

    def test_hash_mismatch_quarantined(self):
        source = filing(); source['sha256'] = '0' * 64
        self.assertEqual(audit_source(source, BODY)['eligibility'], 'quarantine')

    def test_false_issuer_quarantined(self):
        self.assertEqual(audit_source(filing(), BODY, {'issuer': 'Other Trust'})['eligibility'], 'quarantine')

    def test_access_notice_is_not_a_document_even_http200(self):
        source = filing(); source.pop('sha256'); source['http_status'] = 200
        result = audit_source(source, b'<html><title>Access Denied</title>Request rate threshold exceeded</html>')
        self.assertEqual(result['eligibility'], 'quarantine')

    def test_missing_timestamps_are_unknown(self):
        source = filing(); source.pop('retrieved_at'); source.pop('accepted_at')
        result = audit_source(source, BODY)
        self.assertEqual(result['eligibility'], 'eligible_as_primary')
        self.assertEqual(result['coverage']['point_in_time'], 'needs_review')
        self.assertEqual(result['evidence']['timestamps']['retrieved_at'], None)

    def test_claimed_issuer_domain_cannot_create_authority(self):
        source = filing(); source['url'] = 'https://fake.example/report.htm'; source['official'] = True
        source['official_domains'] = ['fake.example']
        self.assertEqual(audit_source(source, BODY)['eligibility'], 'needs_review')

    def test_unsigned_issuer_supplement_supporting(self):
        source = filing(); source.update(url='https://ir.agnc.com/report.htm', issuer='AGNC Investment Corp.', form='supplement')
        source.pop('sha256'); source['financial_evidence'] = []
        result = audit_source(source, b'<html>AGNC Investment Corp. 2026-06-30</html>')
        self.assertEqual(result['eligibility'], 'supporting_only')

    def test_403_is_access_restricted_not_dead(self):
        result = audit_source({'url': 'https://ir.agnc.com/report.pdf', 'http_status': 403})
        self.assertEqual(result['quality_axes']['availability']['state'], 'access_restricted')
        self.assertNotEqual(result['eligibility'], 'quarantine')

    def test_malicious_urls_are_quarantined(self):
        for url in ['http://www.sec.gov/report', 'https://www.sec.gov@evil.example/a', 'file:///secret', 'https://www.sec.gov:444/a']:
            self.assertEqual(audit_source({'url': url})['eligibility'], 'quarantine')

    def test_pdf_mime_must_match_actual_bytes(self):
        source = filing(); source['content_type'] = 'application/pdf'
        self.assertEqual(audit_source(source, BODY)['eligibility'], 'quarantine')

    def test_quote_must_be_in_content_with_matching_context(self):
        source = filing(); source['financial_evidence'][0]['quote'] = 'invented 100'
        self.assertEqual(audit_source(source, BODY)['eligibility'], 'quarantine')

    def test_same_amount_does_not_prove_duplicate(self):
        a, b = filing(), filing(); b['url'] = b['url'].replace('amt-', 'other-'); b['document'] = 'other-20260630.htm'
        b['accession'] = '0001053507-26-000134'; b['url'] = b['url'].replace('000105350726000133', '000105350726000134')
        a.pop('sha256'); b.pop('sha256')
        result = audit_registry([a, b])
        self.assertEqual(result['duplicate_groups'], [])

    def test_conflicts_require_same_metric_context(self):
        a, b = filing(), filing(); b['financial_evidence'][0]['value'] = '101'
        result = audit_registry([a, b])
        self.assertEqual(len(result['conflicts']), 1)
        self.assertTrue(all(x['eligibility'] == 'needs_review' for x in result['sources']))

    def test_directory_does_not_prove_universe(self):
        result = audit_source({'url': 'https://www.reit.com/investing/reit-directory', 'universe_complete': True})
        self.assertEqual(result['eligibility'], 'discovery_only')
        self.assertEqual(result['coverage']['universe_completeness'], 'unknown')

    def test_fact_value_must_align_with_exact_quote(self):
        source = filing(); source['financial_evidence'][0]['value'] = '101'
        self.assertEqual(audit_source(source, BODY)['eligibility'], 'quarantine')

    def test_pdf_signature_without_linked_text_leaves_identity_unknown(self):
        source = filing(); source.pop('sha256'); source['content_type'] = 'application/pdf'
        source['content_text'] = BODY.decode()
        result = audit_source(source, b'%PDF-1.7\nminimal fixture\n%%EOF')
        self.assertEqual(result['quality_axes']['content_identity']['state'], 'unknown')

    def test_receipt_is_not_silently_bound_to_old_document(self):
        source = filing(); source.pop('retrieved_at')
        result = audit_registry([source], [{'url': source['url'], 'retrieved_at': '2026-10-04T00:00:00Z', 'http_status': 200}])
        self.assertIsNone(result['sources'][0]['evidence']['timestamps']['retrieved_at'])

    def test_broker_receipt_status_preserves_restrictions_and_history(self):
        source = filing(); source['raw_bytes'] = BODY
        receipts = [{'url': source['url'], 'kind': 'http', 'status': 200},
                    {'url': source['url'], 'kind': 'http', 'status': 429}]
        result = audit_registry([source], receipts)['sources'][0]
        availability = result['quality_axes']['availability']
        self.assertEqual(availability['state'], 'access_restricted')
        self.assertEqual(availability['historical_status_counts'], {'200': 1, '429': 1})
        self.assertEqual(availability['observations'], receipts)

    def test_delete_control_character_url_is_quarantined(self):
        source = filing(); source['url'] += '\x7f'
        result = audit_source(source, BODY)
        self.assertEqual(result['eligibility'], 'quarantine')
        self.assertIn('unsafe_url', result['reasons'])

    def test_cli_keeps_original_input_and_emits_json_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); raw = folder / 'report.htm'; raw.write_bytes(BODY)
            source = filing(); source['source_path'] = str(raw)
            registry = folder / 'registry.json'; registry.write_text(json.dumps({'sources': [source]}))
            before = registry.read_bytes()
            run = subprocess.run([sys.executable, 'scripts/audit_reit_source_quality.py', '--registry', str(registry), '--output', str(folder / 'audit')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(registry.read_bytes(), before)
            self.assertEqual(raw.read_bytes(), BODY)
            result = json.loads((folder / 'audit' / 'source_quality.json').read_text(encoding='utf-8'))
            self.assertEqual(result['sources'][0]['eligibility'], 'eligible_as_primary')
            self.assertIn('Financial accuracy: not assessed', (folder / 'audit' / 'source_quality.md').read_text(encoding='utf-8'))

    def test_missing_period_cue_is_unresolved_not_contradictory(self):
        source = filing(); source.pop('sha256'); source['financial_evidence'] = []
        result = audit_source(source, b'<html>American Tower Corporation Credit Agreement</html>')
        self.assertEqual(result['eligibility'], 'needs_review')
        self.assertNotIn('content_period_mismatch', result['reasons'])

    def test_unanchored_first_public_claim_does_not_establish_pit(self):
        source = filing(); source['first_public_at'] = '2026-08-01T12:00:00Z'
        source['first_public_evidence'] = 'trust me'
        self.assertEqual(audit_source(source, BODY)['coverage']['point_in_time'], 'needs_review')

    def test_conflict_does_not_claim_source_grade_matches_old_eligibility(self):
        a, b = filing(), filing(); b['financial_evidence'][0]['value'] = '101'
        a['raw_bytes'] = BODY
        result = audit_registry([a, b])
        self.assertTrue(all(r['coverage']['source_grade'] == r['eligibility'] for r in result['sources']))


if __name__ == '__main__':
    unittest.main()
