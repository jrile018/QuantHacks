from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from src.reit_histories import build_histories


def fixture(kind='flow', value='100'):
    raw = '<html><span id="fact">100</span></html>'
    digest = sha256(raw.encode()).hexdigest()
    doc = {'document_id': 'doc', 'sha256': digest, 'raw_text': raw,
           'cik': '0000000001', 'acceptanceDateTime': '2026-07-01T12:00:00Z'}
    row = {'record_id': 'fact', 'document_id': 'doc', 'issuer_cik': '0000000001',
           'entity_identifier': '0000000001', 'entity_scheme': 'http://www.sec.gov/CIK',
           'source_sha256': digest, 'source_kind': 'filing_xbrl', 'status': 'parsed',
           'quality_flags': [], 'metric': 'cash_from_operations', 'amount_kind': kind,
           'amount_basis': 'reported_cash_movement' if kind == 'flow' else 'reported_debt_balance',
           'value': value, 'currency': 'USD', 'period_type': 'duration' if kind == 'flow' else 'instant',
           'period_start': '2026-01-01', 'period_end': '2026-06-30', 'as_of_date': '2026-06-30',
           'acceptance_datetime': '2026-07-01T12:00:00Z', 'dimensions': [],
           'evidence': [{'document_id': 'doc', 'source_sha256': digest, 'quoted_text': '100',
                         'locator_type': 'xml_element', 'element_id': 'fact'}]}
    return row, doc


class HistoryTests(unittest.TestCase):
    def test_balance_and_period_flow_keep_distinct_meaning_and_exact_evidence(self):
        flow, doc = fixture()
        balance, _ = fixture('balance')
        balance['record_id'] = 'balance'
        result = build_histories([flow, balance], [doc])
        rows = {r['record_id']: r for r in result['financial_history']}
        self.assertEqual(rows['fact']['history_type'], 'period_flow')
        self.assertEqual(rows['balance']['history_type'], 'stock_balance')
        self.assertEqual(rows['fact']['evidence'], flow['evidence'])
        self.assertTrue(rows['fact']['eligibility']['eligible'])
        self.assertFalse(rows['balance']['is_cash_movement'])

    def test_pit_inclusive_boundary_and_unknown_timestamp_never_uses_effective(self):
        row, doc = fixture()
        before = build_histories([row], [doc], '2026-07-01T11:59:59Z')
        self.assertEqual(before['financial_history'], [])
        at = build_histories([row], [doc], '2026-07-01T08:00:00-04:00')
        self.assertEqual(len(at['financial_history']), 1)
        row['acceptance_datetime'] = None
        doc['acceptanceDateTime'] = None
        row['effective_at'] = '2024-01-01'
        self.assertEqual(build_histories([row], [doc], '2026-07-01T12:00:00Z')['financial_history'], [])
        self.assertFalse(build_histories([row], [doc])['financial_history'][0]['eligibility']['pit_eligible'])
        with self.assertRaises(ValueError):
            build_histories([row], [doc], '2026-07-01')

    def test_tampered_source_or_evidence_cannot_enter_history(self):
        row, doc = fixture()
        doc['raw_text'] += 'tamper'
        result = build_histories([row], [doc])
        self.assertEqual(result['financial_history'], [])
        self.assertIn('source_hash_mismatch', result['review'][0]['issues'])
        row, doc = fixture()
        row['evidence'][0]['quoted_text'] = '999'
        result = build_histories([row], [doc])
        self.assertEqual(result['financial_history'], [])
        self.assertIn('quote_not_found', result['review'][0]['issues'])

    def test_conflicts_and_comparison_sources_are_review_not_additive_cash(self):
        row, doc = fixture()
        conflicting = deepcopy(row)
        conflicting.update(record_id='conflict', value='101')
        comparison = deepcopy(row)
        comparison.update(record_id='api', source_kind='companyfacts_comparison')
        result = build_histories([row, conflicting, comparison], [doc])
        self.assertEqual(result['financial_history'], [])
        self.assertTrue(result['reconciliation'])
        self.assertEqual(len(result['review']), 3)

    def test_same_fact_in_later_filing_is_a_revision_never_summed(self):
        row, doc = fixture()
        later = deepcopy(row)
        later.update(record_id='later', accession='later', acceptance_datetime='2026-08-01T12:00:00Z')
        result = build_histories([row, later], [doc])
        self.assertEqual(len(result['financial_history']), 2)
        self.assertEqual(result['reconciliation'][0]['kind'], 'cross_filing_observations')
        self.assertTrue(all(not r['additive'] for r in result['financial_history']))


class HistoryEvidenceTests(unittest.TestCase):
    def test_collector_text_hash_rejects_mutated_pdf_cache(self):
        row, doc = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / 'source.pdf'
            raw.write_bytes(b'%PDF- retained source bytes')
            digest = sha256(raw.read_bytes()).hexdigest()
            text = Path(tmp) / 'text.json'
            payload = {'sha256': digest, 'pages': [{'number': 1, 'text': '100'}]}
            text.write_text(json.dumps(payload), encoding='utf-8')
            declared = sha256(text.read_bytes()).hexdigest()
            payload['pages'][0]['text'] = 'Modified extracted text 100'
            text.write_text(json.dumps(payload), encoding='utf-8')
            doc.pop('raw_text')
            doc.update(source_path=str(raw), sha256=digest, text_path=str(text), text_sha256=declared)
            row['source_sha256'] = digest
            row['evidence'] = [{'document_id': 'doc', 'source_sha256': digest,
                                'quote': '100', 'page_number': 1, 'locator': 'page 1'}]
            result = build_histories([row], [doc])
            self.assertEqual(result['financial_history'], [])
            self.assertIn('text_artifact_hash_mismatch', result['review'][0]['issues'])

    def test_xml_locator_cannot_bind_quote_from_another_element(self):
        row, doc = fixture()
        row['evidence'][0]['element_id'] = 'missing'
        result = build_histories([row], [doc])
        self.assertEqual(result['financial_history'], [])
        self.assertIn('xml_locator_quote_mismatch', result['review'][0]['issues'])

    def test_future_conflict_does_not_poison_earlier_known_pit_view(self):
        row, doc = fixture()
        later = deepcopy(row)
        later.update(record_id='late-conflict', value='101', acceptance_datetime='2026-08-01T12:00:00Z')
        result = build_histories([row, later], [doc], '2026-07-01T12:00:00Z')
        self.assertEqual([r['record_id'] for r in result['financial_history']], ['fact'])



class IssuerEvidenceTests(unittest.TestCase):
    def test_record_issuer_must_match_its_retained_document_issuer(self):
        row, doc = fixture()
        doc['cik'] = '0000000002'
        result = build_histories([row], [doc])
        self.assertEqual(result['financial_history'], [])
        self.assertIn('issuer_source_identity_mismatch', result['review'][0]['issues'])


if __name__ == '__main__':
    unittest.main()
