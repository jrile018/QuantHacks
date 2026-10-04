from copy import deepcopy
from hashlib import sha256
import unittest

from src.reit_relationships import build_relationships, discover_relationship_candidates


def fixture(role='trustee_under_supplemental_indenture', name='Named Trust Bank', cik='0000000001', suffix='1', quote=None):
    quote = quote or f'Issuer {suffix} and {name}, as trustee, entered an indenture.'
    digest = sha256(quote.encode()).hexdigest()
    doc = {'document_id': f'doc{suffix}', 'sha256': digest, 'raw_text': quote,
           'pages': [{'number': 1, 'text': quote}], 'cik': cik,
           'acceptanceDateTime': '2026-07-01T12:00:00Z'}
    assertion = {'assertion_id': suffix, 'subject': {'legal_name': name, 'identifier': None},
                 'relation_type': role, 'object': {'legal_name': f'Indenture {suffix}', 'identifier': '$100'},
                 'instrument_identifier': f'Indenture {suffix}', 'effective_at': '2021-01-01',
                 'available_at': '2026-07-01T12:00:00Z',
                 'evidence': {'document_id': f'doc{suffix}', 'source_sha256': digest,
                              'quote': quote, 'locator': 'page 1'}, 'unknowns': []}
    return assertion, doc


class RelationshipTests(unittest.TestCase):
    def test_assertion_cannot_precede_later_source_availability(self):
        assertion, doc = fixture()
        assertion['available_at'] = '2024-01-01T00:00:00Z'
        result = build_relationships([assertion], [doc], '2024-01-02T00:00:00Z')
        self.assertEqual(result['role_edges'], [])
        self.assertIn('not_yet_available', result['review'][0]['eligibility']['reasons'])
        doc['available_at'] = '2026-08-01T00:00:00Z'
        result = build_relationships([assertion], [doc])
        self.assertEqual(result['role_edges'][0]['available_at'], '2026-08-01T00:00:00+00:00')

    def test_trustee_quote_cannot_adjudicate_borrower_issuer_or_planned_use(self):
        for relation in ('borrower_under', 'issuer_under_indenture', 'planned_use_of_proceeds',
                         'facility_terms_and_balance_snapshot', 'entered_revolving_credit_facilities',
                         'series_established_under_indenture'):
            with self.subTest(relation=relation):
                assertion, doc = fixture(role=relation)
                result = build_relationships([assertion], [doc])
                self.assertEqual(result['role_edges'], [])
                self.assertIn('asserted_role_not_in_quote', result['review'][0]['issues'])

    def test_quote_supported_borrower_and_planned_user_remain_eligible(self):
        for relation, quote in (
            ('borrower_under', 'Named Trust Bank, as borrower, entered a credit agreement.'),
            ('planned_use_of_proceeds', 'Named Trust Bank intends to use the net proceeds to repay debt.'),
        ):
            with self.subTest(relation=relation):
                assertion, doc = fixture(role=relation)
                digest = sha256(quote.encode()).hexdigest()
                doc.update(raw_text=quote, sha256=digest, pages=[{'number': 1, 'text': quote}])
                assertion['evidence'].update(quote=quote, source_sha256=digest)
                self.assertTrue(build_relationships([assertion], [doc])['role_edges'][0]['eligibility']['eligible'])

    def test_identified_issuer_narrator_supports_decimal_facility_and_planned_use(self):
        for relation, quote in (
            ('entered_revolving_credit_facilities', 'In April 2025, we entered into new $4.0 billion revolving credit facilities.'),
            ('planned_use_of_proceeds', 'The Company intends to use the net proceeds to repay debt.'),
            ('facility_terms_and_balance_snapshot', 'Our new $4.0 billion credit facilities mature in April 2027.'),
        ):
            with self.subTest(relation=relation):
                assertion, doc = fixture(role=relation, name='Issuer Corporation', quote=quote)
                raw = 'Issuer Corporation\n' + quote
                digest = sha256(raw.encode()).hexdigest()
                doc.update(company_name='Issuer Corporation', raw_text=raw, sha256=digest)
                assertion['evidence']['source_sha256'] = digest
                assertion['subject']['identifier'] = 'CIK 0000000001'
                self.assertTrue(build_relationships([assertion], [doc])['role_edges'][0]['eligibility']['eligible'])

    def test_issuer_action_cannot_be_assigned_to_named_trustee(self):
        for relation in ('borrower_under', 'facility_terms_and_balance_snapshot', 'planned_use_of_proceeds'):
            with self.subTest(relation=relation):
                quote = 'Named Trust Bank, as trustee, entered a credit facility. The Company intends to use proceeds to repay debt.'
                assertion, doc = fixture(role=relation, quote=quote)
                doc['company_name'] = 'Issuer Corporation'
                self.assertEqual(build_relationships([assertion], [doc])['role_edges'], [])

    def test_trustee_role_retains_evidence_without_becoming_lender(self):
        assertion, doc = fixture()
        result = build_relationships([assertion], [doc])
        edge = result['role_edges'][0]
        self.assertEqual(edge['role'], 'trustee')
        self.assertFalse(edge['is_lender'])
        self.assertEqual(edge['evidence'], assertion['evidence'])
        self.assertTrue(edge['eligibility']['eligible'])
        self.assertEqual(result['entities'][0]['identity_status'], 'unresolved_name')

    def test_pit_uses_available_not_effective_and_rejects_naive_dates(self):
        assertion, doc = fixture()
        self.assertEqual(build_relationships([assertion], [doc], '2024-01-01T00:00:00Z')['role_edges'], [])
        self.assertEqual(len(build_relationships([assertion], [doc], '2026-07-01T08:00:00-04:00')['role_edges']), 1)
        assertion['available_at'] = None
        doc['acceptanceDateTime'] = None
        self.assertEqual(build_relationships([assertion], [doc], '2026-09-01T00:00:00Z')['role_edges'], [])
        self.assertFalse(build_relationships([assertion], [doc])['role_edges'][0]['eligibility']['pit_eligible'])
        with self.assertRaises(ValueError):
            build_relationships([assertion], [doc], '2026-09-01')

    def test_source_hash_and_quote_integrity_gate(self):
        assertion, doc = fixture()
        doc['raw_text'] += 'tamper'
        result = build_relationships([assertion], [doc])
        self.assertEqual(result['role_edges'], [])
        self.assertIn('source_hash_mismatch', result['review'][0]['issues'])
        assertion, doc = fixture()
        assertion['evidence']['quote'] = 'made up evidence'
        result = build_relationships([assertion], [doc])
        self.assertEqual(result['role_edges'], [])
        self.assertIn('quote_not_found', result['review'][0]['issues'])

    def test_equal_amounts_do_not_merge_instruments_and_names_do_not_merge_legal_entities(self):
        a, da = fixture(suffix='1')
        b, db = fixture(name='Named Trust Bank, N.A.', cik='0000000002', suffix='2')
        result = build_relationships([a, b], [da, db])
        self.assertEqual(len(result['instruments']), 2)
        self.assertEqual(len(result['entities']), 2)
        self.assertEqual(result['intersections'], [])

    def test_shared_exact_counterparty_is_name_candidate_until_identity_resolved(self):
        a, da = fixture(suffix='1')
        b, db = fixture(cik='0000000002', suffix='2')
        result = build_relationships([a, b], [da, db])
        intersection = result['intersections'][0]
        self.assertEqual(set(intersection['company_ids']), {'cik:0000000001', 'cik:0000000002'})
        self.assertEqual(intersection['basis'], 'shared_exact_name_counterparty')
        self.assertFalse(intersection['eligibility']['eligible'])

    def test_operating_partnership_does_not_inherit_filing_cik(self):
        a, doc = fixture(name='Issuer Operating Partnership')
        a['subject']['identifier'] = "CIK 0000000001; issuer's Operating Partnership"
        result = build_relationships([a], [doc])
        self.assertTrue(result['entities'][0]['entity_id'].startswith('name:'))
        self.assertIn('ambiguous_identifier', result['entities'][0]['issues'])

    def test_planned_repayment_and_capacity_are_never_completed_cash_events(self):
        a, da = fixture(role='planned_use_of_proceeds', suffix='1',
                        quote='Named Trust Bank intends to use net proceeds to repay debt.')
        b, db = fixture(role='facility_terms_and_balance_snapshot', suffix='2',
                        quote='Named Trust Bank has outstanding borrowings under its credit facility.')
        result = build_relationships([a, b], [da, db])
        rows = {r['assertion_id']: r for r in result['financial_history']}
        self.assertEqual(rows['1']['history_type'], 'planned_event')
        self.assertEqual(rows['2']['history_type'], 'terms')
        self.assertTrue(all(not r['is_cash_movement'] for r in rows.values()))

    def test_compound_named_roles_expand_to_review_candidates_only(self):
        a, doc = fixture(name='Bank Example, N.A.')
        quote = 'Issuer One, as issuer, Company Two, as guarantor, and Bank Example, N.A., as trustee and notes collateral agent.'
        digest = sha256(quote.encode()).hexdigest()
        doc.update(raw_text=quote, sha256=digest, pages=[{'number': 1, 'text': quote}])
        a.update(relation_type='issuer_under_indenture', subject={'legal_name': 'Issuer One', 'identifier': None})
        a['evidence'].update(quote=quote, source_sha256=digest)
        result = build_relationships([a], [doc])
        expanded = [r for r in result['role_edges'] if r.get('candidate_expansion')]
        bank = [r for r in expanded if r['subject_name'] == 'Bank Example, N.A.']
        self.assertEqual({r['role'] for r in bank}, {'trustee', 'collateral_agent'})
        self.assertTrue(all(not r['eligibility']['eligible'] for r in expanded))
        self.assertFalse(any(r['is_lender'] for r in bank))

    def test_native_discovery_is_read_only_exact_evidence_candidate(self):
        _, doc = fixture()
        found = discover_relationship_candidates([doc])
        self.assertEqual(len(found['candidates']), 1)
        candidate = found['candidates'][0]
        self.assertEqual(candidate['evidence']['quote'], doc['raw_text'])
        self.assertFalse(candidate['eligibility']['eligible'])


class RelationshipNormalizationTests(unittest.TestCase):
    def test_whitespace_normalization_preserves_exact_native_quote_and_corrects_locator(self):
        from src.reit_relationships import normalize_assertions
        a, doc = fixture()
        native = 'prefix\n' + a['evidence']['quote'].replace(' and ', '\n\nand\u00a0') + '\nend'
        doc.update(raw_text=native, sha256=sha256(native.encode()).hexdigest(),
                   pages=[{'number': 7, 'text': native}])
        a['evidence']['source_sha256'] = doc['sha256']
        original = deepcopy(a)
        result = normalize_assertions([a], [doc])
        quote = result['assertions'][0]['evidence']['quote']
        self.assertEqual(quote, 'Issuer 1\n\nand\u00a0Named Trust Bank, as trustee, entered an indenture.')
        evidence = result['assertions'][0]['evidence']
        self.assertEqual(native[evidence['char_start']:evidence['char_end']], quote)
        self.assertEqual(evidence['page_number'], 7)
        self.assertEqual(result['changes'][0]['original_evidence'], original['evidence'])
        self.assertEqual(a, original)
        self.assertTrue(build_relationships(result['assertions'], [doc])['role_edges'])

    def test_normalization_does_not_change_substantive_quote_or_accept_bad_hash(self):
        from src.reit_relationships import normalize_assertions
        a, doc = fixture()
        a['evidence']['quote'] = a['evidence']['quote'].replace('trustee', 'lender')
        result = normalize_assertions([a], [doc])
        self.assertEqual(result['assertions'], [])
        self.assertIn('quote_not_found', result['review'][0]['issues'])
        a, doc = fixture()
        doc['raw_text'] += 'tamper'
        self.assertEqual(normalize_assertions([a], [doc])['assertions'], [])

    def test_successor_trustee_is_separate_from_predecessor_named_entity(self):
        a, doc = fixture(name='Issuer One')
        quote = 'Issuer One, as issuer, Company Two, as guarantor, and U.S. Bank Trust Company, National Association, as successor in interest to U.S. Bank National Association, as trustee.'
        doc.update(raw_text=quote, sha256=sha256(quote.encode()).hexdigest(), pages=[{'number': 1, 'text': quote}])
        a.update(relation_type='issuer_under_indenture')
        a['evidence'].update(quote=quote, source_sha256=doc['sha256'])
        result = build_relationships([a], [doc])
        trustee = [e for e in result['role_edges'] if e['role'] == 'trustee']
        self.assertEqual([e['subject_name'] for e in trustee], ['U.S. Bank Trust Company, National Association'])
        self.assertTrue(all(not e['is_lender'] for e in trustee))

    def test_same_instrument_amount_cannot_create_an_explicit_reference_merge_without_name(self):
        a, da = fixture(suffix='1')
        b = deepcopy(a)
        b.update(assertion_id='2')
        b['object'] = {'legal_name': 'Another Indenture', 'identifier': 'same facility as assertion 1'}
        result = build_relationships([a, b], [da])
        self.assertEqual(len(result['instruments']), 2)

class RelationshipIdentityTests(unittest.TestCase):
    def test_explicit_counterparty_identifier_supports_resolved_intersection(self):
        assertions, documents = [], []
        for suffix, issuer in [('1', '0000000001'), ('2', '0000000002')]:
            a, doc = fixture(cik=issuer, suffix=suffix)
            quote = f'Issuer {suffix} and Named Trust Bank (CIK 0000000003), as trustee, entered an indenture.'
            doc.update(raw_text=quote, sha256=sha256(quote.encode()).hexdigest(), pages=[{'number': 1, 'text': quote}])
            a['subject']['identifier'] = 'CIK 0000000003'
            a['evidence'].update(quote=quote, source_sha256=doc['sha256'])
            assertions.append(a)
            documents.append(doc)
        result = build_relationships(assertions, documents)
        intersection = result['intersections'][0]
        self.assertEqual(intersection['counterparty_id'], 'cik:0000000003')
        self.assertTrue(intersection['eligibility']['eligible'])
        self.assertEqual(intersection['basis'], 'shared_verified_counterparty')

    def test_mismatched_issuer_identifier_remains_unresolved(self):
        a, doc = fixture()
        a['subject']['identifier'] = 'CIK 0000999999'
        result = build_relationships([a], [doc])
        self.assertTrue(result['entities'][0]['entity_id'].startswith('name:'))
        self.assertIn('identifier_not_supported_by_source_identity', result['entities'][0]['issues'])

class RoleEvidenceTests(unittest.TestCase):
    def test_asserted_lender_role_requires_literal_lender_evidence(self):
        a, doc = fixture(role='lender_under')
        result = build_relationships([a], [doc])
        self.assertEqual(result['role_edges'], [])
        self.assertIn('asserted_role_not_in_quote', result['review'][0]['issues'])

    def test_completed_event_label_cannot_override_planned_quote(self):
        a, doc = fixture(role='completed_debt_issuance')
        quote = 'Named Trust Bank intends to issue notes next month.'
        doc.update(raw_text=quote, sha256=sha256(quote.encode()).hexdigest(), pages=[{'number': 1, 'text': quote}])
        a['evidence'].update(quote=quote, source_sha256=doc['sha256'])
        result = build_relationships([a], [doc])
        self.assertEqual(result['financial_history'], [])
        self.assertIn('completed_event_not_in_quote', result['review'][0]['issues'])

    def test_literal_legal_name_includes_lowercase_connectors(self):
        a, doc = fixture(name='Issuer One')
        quote = 'Issuer One, as issuer, and The Bank of New York Mellon Trust Company, N.A., as trustee and notes collateral agent.'
        doc.update(raw_text=quote, sha256=sha256(quote.encode()).hexdigest(), pages=[{'number': 1, 'text': quote}])
        a['relation_type'] = 'issuer_under_indenture'
        a['evidence'].update(quote=quote, source_sha256=doc['sha256'])
        edges = build_relationships([a], [doc])['role_edges']
        self.assertEqual({e['subject_name'] for e in edges if e['role'] == 'trustee'}, {'The Bank of New York Mellon Trust Company, N.A.'})

    def test_atm_candidate_preserves_all_fourteen_exact_names_without_sale_allocation(self):
        names = ['Goldman Sachs & Co. LLC', 'Academy Securities, Inc.', 'Barclays Capital Inc.', 'BTIG, LLC',
                 'Citadel Securities Institutional LLC', 'Citizens JMP Securities, LLC', 'J.P. Morgan Securities LLC',
                 'Keefe, Bruyette & Woods, Inc.', 'Moelis & Company LLC', 'Morgan Stanley & Co. LLC',
                 'RBC Capital Markets, LLC', 'UBS Securities LLC', 'Virtu Americas LLC', 'Wells Fargo Securities, LLC']
        quote = 'AGNC entered separate sales agreements with each of ' + ', '.join(names[:-1]) + ', and ' + names[-1] + ' (each, an \ufffdAgent\ufffd and collectively the \ufffdAgents\ufffd).'
        _, doc = fixture()
        doc.update(raw_text=quote, sha256=sha256(quote.encode()).hexdigest(), pages=[{'number': 1, 'text': quote}])
        candidates = discover_relationship_candidates([doc])['candidates']
        self.assertEqual([r['legal_name'] for r in candidates[0]['named_role_candidates']], names)
        self.assertFalse(candidates[0]['eligibility']['eligible'])
        self.assertIn('native_text_decode_loss', candidates[0]['issues'])

class AssertionIntegrityTests(unittest.TestCase):
    def test_conflicting_same_assertion_id_is_review_not_two_accepted_edges(self):
        a, doc = fixture()
        other = deepcopy(a)
        other['relation_type'] = 'lender_under'
        result = build_relationships([a, other], [doc])
        self.assertEqual(result['role_edges'], [])
        self.assertTrue(all('assertion_id_conflict' in r['issues'] for r in result['review']))

    def test_local_manifest_accession_matches_explicit_document_id(self):
        from src.reit_relationships import normalize_assertions
        a, doc = fixture()
        doc.pop('document_id')
        doc.update(accession='local-example-report', filename='report.pdf')
        a['evidence']['document_id'] = 'local-example-report'
        self.assertEqual(len(normalize_assertions([a], [doc])['assertions']), 1)



class CompanyNodeTests(unittest.TestCase):
    def test_company_metadata_node_is_separate_from_operating_partnership(self):
        a, doc = fixture(name='Issuer Operating Partnership')
        doc['company_name'] = 'Issuer Holding Corporation'
        a['subject']['identifier'] = "CIK 0000000001; issuer's Operating Partnership"
        result = build_relationships([a], [doc])
        self.assertTrue(result['entities'][0]['entity_id'].startswith('name:'))
        company = result.get('company_entities', [])
        self.assertEqual(len(company), 1)
        self.assertEqual(company[0]['entity_id'], 'cik:0000000001')
        self.assertEqual(company[0]['legal_name'], 'Issuer Holding Corporation')
        self.assertEqual(company[0]['source_documents'][0]['source_sha256'], doc['sha256'])

    def test_future_and_unavailable_company_metadata_cannot_leak_into_pit_view(self):
        a, doc = fixture()
        self.assertEqual(build_relationships([a], [doc], '2024-01-01T00:00:00Z').get('company_entities', []), [])
        doc['acceptanceDateTime'] = None
        self.assertEqual(build_relationships([], [doc], '2026-08-01T00:00:00Z').get('company_entities', []), [])
        company = build_relationships([], [doc]).get('company_entities', [])
        self.assertEqual(len(company), 1)
        self.assertFalse(company[0]['eligibility']['pit_eligible'])



class CounterpartyIdentityGateTests(unittest.TestCase):
    def test_counterparty_does_not_inherit_source_issuer_cik_without_named_id(self):
        assertion, doc = fixture()
        doc['company_name'] = 'Issuer Holding Corporation'
        assertion['subject']['identifier'] = 'CIK 0000000001'
        result = build_relationships([assertion], [doc])
        self.assertTrue(result['entities'][0]['entity_id'].startswith('name:'))
        self.assertIn('identifier_not_supported_by_source_identity', result['entities'][0]['issues'])



class PartnershipIdentifierTests(unittest.TestCase):
    def test_standalone_cik_does_not_identify_lp_from_unnamed_issuer_metadata(self):
        assertion, doc = fixture(role='borrower_under', name='Issuer L.P.',
                                 quote='Issuer L.P., as borrower, entered a credit agreement.')
        assertion['subject']['identifier'] = 'CIK 0000000001'
        result = build_relationships([assertion], [doc])
        self.assertTrue(result['entities'][0]['entity_id'].startswith('name:'))


if __name__ == '__main__':
    unittest.main()
