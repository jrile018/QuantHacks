from hashlib import sha256
import unittest
from unittest.mock import patch

from src.reit_money_records import build_document_records, consolidate_records
from tests.test_reit_inline_facts import filing, fact


def document(raw, filename='report.htm', cik='0000123456', accession='0000123456-26-000001'):
    return {'cik': cik, 'accession': accession, 'filename': filename,
            'url': 'https://www.sec.gov/example/' + filename, 'source_path': filename,
            'sha256': sha256(raw).hexdigest(), 'form': '10-Q', 'filed': '2026-07-20'}


class MoneyRecordTests(unittest.TestCase):
    def test_known_cash_fact_classified_with_exact_evidence(self):
        raw = filing(fact(attrs='scale="3"'))
        result = build_document_records(raw, document(raw), {'pages': []})
        row = result['records'][0]
        self.assertEqual(row['value'], '1234000')
        self.assertEqual(row['amount_kind'], 'flow')
        self.assertEqual(row['amount_basis'], 'reported_cash_movement')
        self.assertEqual(row['cash_direction'], 'inflow')
        self.assertEqual(row['relationship'], 'borrower')
        self.assertEqual(row['status'], 'parsed')
        self.assertEqual(row['source_sha256'], sha256(raw).hexdigest())
        self.assertEqual(row['evidence'][0]['element_id'], 'f')
        self.assertEqual(row['period_start'], '2026-01-01')

    def test_custom_namespace_cannot_borrow_standard_semantics(self):
        raw = filing(fact()).replace(b'name="g:', b'name="cust:')
        row = build_document_records(raw, document(raw), {})['records'][0]
        self.assertEqual(row['amount_kind'], 'unknown')
        self.assertEqual(row['status'], 'review_required')
        self.assertEqual(row['relationship'], 'unknown')

    def test_balances_and_period_type_do_not_imply_movements(self):
        raw = filing(fact()).replace(b'ProceedsFromBorrowings', b'LongTermDebt')
        row = build_document_records(raw, document(raw), {})['records'][0]
        self.assertEqual(row['amount_kind'], 'balance')
        self.assertEqual(row['status'], 'review_required')
        self.assertIn('concept_period_mismatch', row['quality_flags'])
        custom = raw.replace(b'name="g:LongTermDebt"', b'name="cust:CustomLoanCommitment"')
        row = build_document_records(custom, document(custom), {})['records'][0]
        self.assertEqual(row['amount_kind'], 'unknown')

    def test_nil_and_invalid_fact_are_never_ready_numeric_records(self):
        for raw in (filing(fact('', 'xsi:nil="true"')), filing(fact('—'))):
            result = build_document_records(raw, document(raw), {})
            self.assertEqual(result['records'][0]['status'], 'review_required')
            self.assertIsNone(result['records'][0]['value'])

    def test_identical_and_consistently_rounded_duplicates_keep_evidence(self):
        one = fact('1,234', 'scale="3"')
        two = fact('1.2', 'scale="6"').replace('id="f"', 'id="f2"').replace('decimals="-3"', 'decimals="-5"')
        raw = filing(one + two)
        rows = build_document_records(raw, document(raw), {})['records']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['value'], '1234000')
        self.assertEqual(rows[0]['duplicate_status'], 'consistent_rounded')
        self.assertEqual(len(rows[0]['evidence']), 2)

    def test_same_precision_different_values_are_inconsistent_even_at_boundary(self):
        raw = filing(fact('1', 'scale="3"') + fact('2', 'scale="3"').replace('id="f"', 'id="f2"'))
        row = build_document_records(raw, document(raw), {})['records'][0]
        self.assertEqual(row['status'], 'review_required')
        self.assertEqual(row['duplicate_status'], 'inconsistent')
        self.assertIsNone(row['value'])
        self.assertEqual({v['value'] for v in row['duplicate_values']}, {'1000', '2000'})

    def test_different_accessions_and_dimensions_remain_distinct(self):
        raw = filing(fact())
        a = build_document_records(raw, document(raw), {})['records'][0]
        b = {**a, 'accession': '0000123456-26-000002'}
        c = {**a, 'dimensions': [{'axis': 'facility', 'member': 'revolver'}]}
        self.assertEqual(len(consolidate_records([a, b, c])), 3)

    def test_equal_numeric_values_with_different_lexical_forms_are_not_conflicting(self):
        raw = filing(fact('1')).replace(b' decimals="-3"', b'')
        a = build_document_records(raw, document(raw), {})['records'][0]
        b = {**a, 'value': '1.0'}
        row = consolidate_records([a, b])[0]
        self.assertEqual(row['status'], 'parsed')
        self.assertEqual(row['duplicate_status'], 'identical')

    def test_other_entity_scope_is_preserved_for_review(self):
        raw = filing(fact()).replace(b'>0000123456<', b'>0000123457<')
        row = build_document_records(raw, document(raw), {})['records'][0]
        self.assertEqual(row['entity_identifier'], '0000123457')
        self.assertEqual(row['status'], 'review_required')

    def test_table_semantics_and_units_are_review_candidates_not_invented_facts(self):
        raw = b'<html><body><p>Loan portfolio (dollars in millions)</p><table><tr><th>Loan</th><th>Total Loan</th><th>Principal Balance</th><th>Net Book Value</th></tr><tr><td>Office loan</td><td>120</td><td>90</td><td>87</td></tr></table></body></html>'
        result = build_document_records(raw, document(raw), {})
        tables = [c for c in result['candidates'] if c['candidate_type'] == 'html_table']
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]['status'], 'review_required')
        self.assertEqual(tables[0]['amount_kind'], 'unknown')
        self.assertIn('Principal Balance', str(tables[0]['table']))
        self.assertIsNone(tables[0]['currency'])
        self.assertEqual(result['records'], [])

    def test_pdf_candidates_use_cached_text_and_exact_page_offsets(self):
        raw = b'%PDF-synthetic'
        text = 'A credit facility provides $100 million of capacity, with no amounts drawn.'
        result = build_document_records(raw, document(raw, 'scan.pdf'), {'pages': [{'number': 3, 'text': text, 'quality_flags': ['low_ocr_confidence']}]})
        row = result['candidates'][0]
        evidence = row['evidence'][0]
        self.assertEqual(text[evidence['char_start']:evidence['char_end']], evidence['quoted_text'])
        self.assertEqual(evidence['page_number'], 3)
        self.assertIn('low_ocr_confidence', row['quality_flags'])
        self.assertEqual(result['records'], [])

    def test_wrapped_money_phrases_keep_two_line_evidence_for_review(self):
        raw = b'%PDF-synthetic'
        text = ('The aggregate capacity can increase to $5.0\n'
                'billion subject to lender commitments.\n'
                'After the RI Credit Facilities, the Fund entered into a new $1.38 billion\n'
                'unsecured credit facility for its operations.')
        result = build_document_records(raw, document(raw, 'report.pdf'),
                                        {'pages': [{'number': 85, 'text': text}]})
        quotes = [c['evidence'][0]['quoted_text'] for c in result['candidates']]
        self.assertTrue(any('capacity can increase to $5.0\nbillion' in quote for quote in quotes))
        self.assertTrue(any('$1.38 billion\nunsecured credit facility' in quote for quote in quotes))
        self.assertEqual(result['records'], [])
        for candidate in result['candidates']:
            evidence = candidate['evidence'][0]
            self.assertEqual(text[evidence['char_start']:evidence['char_end']], evidence['quoted_text'])

    def test_supported_pdf_rows_are_classified_with_source_metadata(self):
        from tests.test_reit_pdf_money import cash_table, CURRENCY
        raw = b'%PDF-synthetic'
        text = cash_table('Proceeds from term loan 100 200 300')
        result = build_document_records(raw, document(raw, 'report.pdf'),
                                        {'pages': [{'number': 9, 'text': text}, {'number': 10, 'text': CURRENCY}]})
        self.assertEqual(len(result['records']), 3)
        self.assertTrue(all(r['status'] == 'parsed' for r in result['records']))
        self.assertEqual(result['coverage']['pdf_rule_records'], 3)
        self.assertEqual(result['coverage']['inline_records'], 0)
        self.assertTrue(all(r['source_sha256'] == sha256(raw).hexdigest() for r in result['records']))

    def test_wrong_source_hash_and_candidate_bounds_are_explicit(self):
        raw = filing(fact())
        bad = document(raw)
        bad['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash'):
            build_document_records(raw, bad, {})
        text = '\n'.join(f'Loan {i} has $100 million outstanding.' for i in range(5))
        result = build_document_records(b'text', document(b'text', 'terms.txt'), {'pages': [{'number': 1, 'text': text}]}, max_candidates=2)
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(result['coverage']['candidates_omitted'], 3)

    def test_repeated_consolidation_keeps_counts_values_status_and_evidence(self):
        for value, precision in [('1,234', '-3'), ('1.2', '-5'), ('999', '-3')]:
            with self.subTest(value=value):
                second = fact(value, 'scale="3"' if value != '1.2' else 'scale="6"').replace('id="f"', 'id="f2"').replace('decimals="-3"', f'decimals="{precision}"')
                raw = filing(fact('1,234', 'scale="3"') + second)
                first = build_document_records(raw, document(raw), {})['records']
                again = consolidate_records(first)
                self.assertEqual(first, again)
                self.assertEqual(again[0]['duplicate_count'], 2)

    def test_table_limits_survive_relevance_filter_and_mark_incomplete(self):
        raw = b'<html><table><tr><td>Loan 1</td></tr></table><p>Other section</p><table><tr><td>Unrelated</td></tr></table><table><tr><td>Loan 2</td></tr></table></html>'
        with patch('src.reit_tables.MAX_TABLES', 2):
            result = build_document_records(raw, document(raw), {})
        self.assertTrue(result['coverage']['incomplete'])
        self.assertTrue(any('table_limit' in x for x in result['coverage']['issues']))

    def test_table_quotes_are_bounded_and_full_locators_preserved(self):
        raw = ('<html><p>Loan portfolio</p>' + '<table><tr><td>' * 4 + 'Loan ' + 'x' * 10000 + '</td></tr></table>' * 4 + '</html>').encode()
        result = build_document_records(raw, document(raw), {})
        tables = [c for c in result['candidates'] if c['candidate_type'] == 'html_table']
        quoted = [e for c in tables for e in c['evidence']]
        self.assertLessEqual(sum(len(e['quoted_text']) for e in quoted), 16000)
        self.assertTrue(any(e.get('full_span_char_end', 0) > e['char_end'] for e in quoted))
        text = raw.decode()
        for evidence in quoted:
            self.assertEqual(text[evidence['char_start']:evidence['char_end']], evidence['quoted_text'])
        self.assertTrue(result['coverage']['incomplete'])

    def test_global_evidence_budget_counts_utf8_bytes(self):
        raw = b'text'
        text = '\n'.join('Loan €100 ' + '界' * 30 for _ in range(4))
        with patch('src.reit_money_records.MAX_QUOTED_BYTES_PER_DOCUMENT', 64):
            result = build_document_records(raw, document(raw, 'terms.txt'), {'pages': [{'number': 1, 'text': text}]})
        references = [e for c in result['candidates'] for e in c['evidence']]
        self.assertLessEqual(sum(len(e['quoted_text'].encode()) for e in references), 64)
        self.assertIn('evidence_quote_limit', result['coverage']['issues'])
        for e in references:
            self.assertEqual(text[e['char_start']:e['char_end']], e['quoted_text'])


if __name__ == '__main__':
    unittest.main()
