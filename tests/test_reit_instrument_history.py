"""The breaks guarded here are unsupported joins and fabricated cash/lifecycle events."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest

try:
    from src.reit_instrument_history import build_instrument_history_packet
except ModuleNotFoundError:
    build_instrument_history_packet = None


def row(identifier='i1', quote='A borrower entered a credit agreement.', **changes):
    result = {'assertion_id': identifier, 'instrument_id': identifier,
              'company_id': 'cik:1', 'subject_id': 'entity:borrower',
              'effective_at': '2021-01-01', 'available_at': '2026-02-01T12:00:00Z',
              'relation_type': 'borrower_under', 'history_type': 'agreement',
              'is_cash_movement': False, 'additive': False,
              'eligibility': {'source_eligible': True, 'pit_eligible': True, 'eligible': True, 'reasons': []},
              'evidence': {'document_id': 'doc', 'source_sha256': sha256(quote.encode()).hexdigest(),
                           'quote': quote, 'locator': 'page 1', 'page_number': 1}, 'unknowns': []}
    result.update(changes)
    return result


def bind_document(*rows, document_id='doc'):
    """A document hash binds the complete fixture body, not individual quotes."""
    body = '\n'.join(r['evidence']['quote'] for r in rows)
    digest = sha256(body.encode()).hexdigest()
    for r in rows:
        r['evidence'].update(document_id=document_id, source_sha256=digest)
    return body


class InstrumentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build_instrument_history_packet, 'Instrument history builder is missing')

    def packet(self, rows, instruments=(), roles=(), entities=(), **kw):
        return build_instrument_history_packet(rows, instruments, roles, entities, **kw)

    def test_similar_name_date_and_amount_do_not_merge_agreements(self):
        a, b = row('i1'), row('i2')
        instruments = [{'instrument_id': 'i1', 'legal_name': 'Credit Agreement'},
                       {'instrument_id': 'i2', 'legal_name': 'Credit Agreement'}]
        p = self.packet([a, b], instruments)
        self.assertEqual({e['instrument_id'] for e in p['events']}, {'i1', 'i2'})
        self.assertEqual(p['instrument_links'], [])

    def test_series_link_preserves_separate_instrument_and_entity_scope(self):
        base = row('base', 'Indenture, dated January 26, 2021, among Alpha LP, as issuer, Bank NA, as trustee.',
                   subject_id='alpha-lp', relation_type='issuer_under_indenture')
        series = row('series', 'Certificate pursuant to the Indenture, dated as of January 26, 2021, among Alpha LP, as issuer, Bank NA, as trustee, establishing a series of securities entitled 6.150% Senior Notes due 2034.',
                     subject_id='alpha-lp', relation_type='series_established_under_indenture')
        bind_document(base, series)
        p = self.packet([base, series])
        self.assertEqual(len(p['instrument_links']), 1)
        self.assertEqual(p['instrument_links'][0]['relation_type'], 'series_under_agreement')
        self.assertEqual(p['instrument_links'][0]['from_instrument_id'], 'series')
        self.assertEqual(p['instrument_links'][0]['to_instrument_id'], 'base')
        self.assertEqual(len({e['instrument_id'] for e in p['events']}), 2)
        series['subject_id'] = 'alpha-inc'
        self.assertEqual(self.packet([base, series])['instrument_links'], [])

    def test_note_series_split_amount_rate_and_maturity_without_parent_double_count(self):
        r = row('offering', 'Completed an offering of $500.0 million aggregate principal amount of its 5.300% senior unsecured notes due 2031 and $600.0 million aggregate principal amount of its 5.750% senior unsecured notes due 2036.',
                relation_type='completed_debt_issuance')
        p = self.packet([r])
        self.assertEqual(len(p['components']), 2)
        terms = p['events'][0]['terms']
        self.assertEqual([(t['value'], t['amount_kind']) for t in terms if t['metric'] == 'amount'],
                         [('500000000.0', 'issued_principal'), ('600000000.0', 'issued_principal')])
        self.assertTrue(all(t['component_id'] for t in terms))
        self.assertEqual(p['views']['nonoverlapping_flow'], [])

    def test_amendment_capacity_and_missing_mentions_never_imply_termination(self):
        r = row('facility', 'We entered new $4.0 billion revolving credit facilities to amend and restate our previous $4.25 billion revolving credit facility. (a) a $2.0 billion unsecured multicurrency revolving credit facility, consisting of two tranches, that will mature in April 2027 and (b) a $2.0 billion unsecured multicurrency revolving credit facility, consisting of two tranches, that will mature in April 2029.',
                relation_type='entered_revolving_credit_facilities', effective_at='2025-04')
        p = self.packet([r, row('unrelated')])
        event = next(e for e in p['events'] if e['instrument_id'] == 'facility')
        self.assertEqual(event['lifecycle_status'], 'agreement_reported')
        self.assertFalse(event['is_cash_movement'])
        self.assertEqual([c['tranche_count'] for c in p['components'] if c['component_kind'] == 'facility'], [2, 2])
        self.assertEqual(len([l for l in p['instrument_links'] if l['relation_type'] == 'amends_and_restates_reference']), 1)
        self.assertTrue(all(t['amount_kind'] != 'outstanding' for t in event['terms'] if t['metric'] == 'amount'))
        self.assertTrue(all(e['lifecycle_status'] != 'terminated' for e in p['events']))

    def test_roles_candidate_flags_and_same_name_affiliates_survive(self):
        r = row()
        roles = [{'edge_id': 'e1', 'instrument_id': 'i1', 'subject_id': 'bank-trust', 'subject_name': 'Bank',
                  'role': 'trustee', 'is_lender': False, 'candidate_expansion': True,
                  'eligibility': {'source_eligible': True, 'pit_eligible': True, 'eligible': False,
                                  'reasons': ['human_review_required']}, 'evidence': r['evidence']},
                 {'edge_id': 'e2', 'instrument_id': 'i1', 'subject_id': 'bank-lender', 'subject_name': 'Bank',
                  'role': 'lender', 'is_lender': True, 'eligibility': r['eligibility'], 'evidence': r['evidence']}]
        p = self.packet([r], roles=roles)
        self.assertEqual([x['subject_id'] for x in p['role_assertions']], ['bank-trust', 'bank-lender'])
        self.assertFalse(p['role_assertions'][0]['eligibility']['eligible'])
        self.assertFalse(p['role_assertions'][0]['is_lender'])
        self.assertIsNone(p['role_assertions'][1]['syndicate_share'])

    def test_backdated_effective_date_does_not_backdate_information(self):
        p = self.packet([row(quote='6.150% Senior Notes due 2034.')], as_of='2025-01-01T00:00:00Z')
        self.assertEqual(p['events'][0]['effective_at'], '2021-01-01')
        self.assertFalse(p['events'][0]['eligibility']['pit_eligible'])
        self.assertEqual(p['views']['original'], [])
        self.assertEqual(p['views']['latest'], [])

    def test_mixed_currency_flows_and_overlapping_periods_are_not_summed(self):
        rows = [row('usd', 'Received USD 100 net proceeds.', relation_type='cash_flow_reported',
                    is_cash_movement=True, period_start='2026-01-01', period_end='2026-02-01'),
                row('eur', 'Received EUR 50 net proceeds.', relation_type='cash_flow_reported',
                    is_cash_movement=True, period_start='2026-01-01', period_end='2026-02-01'),
                row('overlap', 'Received USD 120 net proceeds.', instrument_id='usd', relation_type='cash_flow_reported',
                    is_cash_movement=True, period_start='2026-01-15', period_end='2026-02-15')]
        for item in rows:
            item['evidence']['document_id'] = 'doc-' + item['assertion_id']
        rows[-1]['available_at'] = '2026-03-01T00:00:00Z'
        baseline = self.packet(rows)
        usd_components = {**baseline, 'components': [c for c in baseline['components'] if c['parent_instrument_id'] == 'usd']}
        reviewed = ReviewedCorrespondenceContractTests().review(usd_components)
        p = self.packet(rows, reviewed_correspondences=[reviewed])
        self.assertEqual({x['currency'] for x in p['views']['nonoverlapping_flow']}, {'USD', 'EUR'})
        self.assertEqual(len(p['views']['nonoverlapping_flow']), 2)
        self.assertTrue(any(q['status'] == 'overlapping_flow_period' for q in p['missing_evidence_queue']))

    def test_planned_repayment_and_source_quarantine_never_enter_completed_view(self):
        r = row('plan', 'The Company intends to repay $600.0 million aggregate principal amount of its 1.450% senior unsecured notes due 2026.', relation_type='planned_use_of_proceeds')
        bad = row('bxmt-conflict', '6.250% Senior Notes due 2031.',
                  eligibility={'source_eligible': False, 'pit_eligible': True, 'eligible': False,
                               'reasons': ['conflicting_source_url']})
        p = self.packet([r, bad])
        self.assertEqual(len(p['events']), 1)
        self.assertEqual(p['events'][0]['lifecycle_status'], 'planned_only')
        self.assertEqual(p['views']['nonoverlapping_flow'], [])
        self.assertTrue(any(q['status'] == 'source_quarantined' for q in p['missing_evidence_queue']))

    def test_snapshot_packet_is_real_bounded_and_preserves_source_locators(self):
        root = Path(__file__).resolve().parents[1]
        snapshot = root / 'data/processed/reit_build/20261003/integrated/snapshots/snapshot-419fe98b772e4b3116b6e29535e434dce97afcf6e4137aba75c8aaa0a0dc1f04'
        def read(name):
            return [json.loads(line) for line in (snapshot / (name + '.jsonl')).read_text(encoding='utf-8').splitlines()]
        histories = read('instrument_financial_histories')
        untouched = deepcopy(histories)
        p = self.packet(histories, read('instruments'), read('role_edges'), read('entities'))
        self.assertEqual(len(p['events']), 8)
        self.assertEqual(len(p['role_assertions']), 14)
        self.assertEqual(len(p['components']), 11)
        self.assertEqual(len(p['instrument_links']), 2)
        self.assertEqual(histories, untouched)
        self.assertTrue(all(e['evidence']['source_sha256'] and e['evidence']['locator'] for e in p['events']))
        self.assertEqual(p['views']['nonoverlapping_flow'], [])
        self.assertTrue(any(q['status'] == 'agreement_series_link_unresolved' for q in p['missing_evidence_queue']))




class InstrumentHistoryBoundaryTests(unittest.TestCase):
    def test_different_trustee_same_issuer_and_base_date_cannot_prove_agreement_link(self):
        base = row('base', 'Indenture, dated January 26, 2021, among Alpha LP, as issuer, Bank One, as trustee.', relation_type='issuer_under_indenture')
        series = row('series', 'Certificate pursuant to the Indenture, dated January 26, 2021, among Alpha LP, as issuer, Bank Two, as trustee, establishing 6.150% Senior Notes due 2034.', relation_type='series_established_under_indenture')
        bind_document(base, series)
        self.assertEqual(build_instrument_history_packet([base, series])['instrument_links'], [])

    def test_repeated_reports_original_latest_use_information_order_and_cutoff(self):
        old = row('old', 'Received USD 100 net proceeds.', instrument_id='same', effective_at='2026-01-01', available_at='2026-02-01T00:00:00Z')
        new = row('new', 'Received USD 120 net proceeds.', instrument_id='same', effective_at='2025-12-01', available_at='2026-03-01T00:00:00Z')
        old['evidence']['document_id'] = 'doc-old'
        new['evidence']['document_id'] = 'doc-new'
        baseline = build_instrument_history_packet([new, old])
        review = ReviewedCorrespondenceContractTests().review(baseline)
        p = build_instrument_history_packet([new, old], reviewed_correspondences=[review])
        self.assertEqual(p['views']['original'][0]['value'], '100')
        self.assertEqual(p['views']['latest'][0]['value'], '120')
        p = build_instrument_history_packet([new, old], as_of='2026-02-10T00:00:00Z', reviewed_correspondences=[review])
        self.assertEqual(p['views']['latest'][0]['value'], '100')

    def test_invalid_calendar_period_and_ambiguous_dollar_currency_exclude_flows(self):
        invalid = row('invalid', 'Received USD 100 net proceeds.', relation_type='cash_flow_reported', is_cash_movement=True, period_start='2026-02-30', period_end='2026-03-31')
        ambiguous = row('dollar', 'Received $100 net proceeds.', relation_type='cash_flow_reported', is_cash_movement=True, period_start='2026-01-01', period_end='2026-02-01')
        p = build_instrument_history_packet([invalid, ambiguous])
        self.assertEqual(p['views']['nonoverlapping_flow'], [])

    def test_explicit_termination_is_instrument_scoped_and_never_inferred_from_other_party(self):
        named = [{'instrument_id': 'i1', 'legal_name': 'Loan A'}]
        r = row('i1', 'Loan A was terminated effective January 1, 2021.', relation_type='instrument_terminated')
        self.assertEqual(build_instrument_history_packet([r], named)['events'][0]['lifecycle_status'], 'terminated_reported')
        r['evidence']['quote'] = 'Loan B was terminated effective January 1, 2021. Loan A remains outstanding.'
        p = build_instrument_history_packet([r], named)
        self.assertEqual(p['events'][0]['lifecycle_status'], 'assertion_only')
        self.assertTrue(any(q['status'] == 'lifecycle_scope_unresolved' for q in p['missing_evidence_queue']))

class HistoryPacketExportTests(unittest.TestCase):
    def setUp(self):
        try:
            from scripts.build_reit_instrument_history import write_history_packet
        except ModuleNotFoundError:
            write_history_packet = None
        self.assertIsNotNone(write_history_packet, 'Bounded packet exporter is missing')
        self.export = write_history_packet

    def snapshot(self, folder):
        values = {'instrument_financial_histories': [row()], 'instruments': [], 'role_edges': [], 'entities': []}
        manifest = {'fingerprint': 'fixture-snapshot', 'artifacts': {}, 'counts': {}}
        for name, rows in values.items():
            raw = ''.join(json.dumps(r) + '\n' for r in rows).encode()
            (folder / (name + '.jsonl')).write_bytes(raw)
            manifest['artifacts'][name + '.jsonl'] = {'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}
            manifest['counts'][name] = len(rows)
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_export_hashes_real_packet_and_retains_upstream_eligibility_counts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'source'
            source.mkdir()
            self.snapshot(source)
            receipt = self.export(source, base / 'output')
            raw = (base / 'output' / 'packet.json').read_bytes()
            self.assertEqual(receipt['artifacts']['packet.json']['sha256'], sha256(raw).hexdigest())
            self.assertEqual(receipt['counts']['events'], 1)
            self.assertEqual(receipt['source_snapshot_fingerprint'], 'fixture-snapshot')
            self.assertFalse(receipt['raw_sources_revalidated'])
            self.assertEqual(len(json.loads(raw)['source_quarantine']), 2)

    def test_tampered_input_fails_before_any_packet_is_written(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'source'
            source.mkdir()
            self.snapshot(source)
            (source / 'role_edges.jsonl').write_text('{}\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash|size'):
                self.export(source, base / 'output')
            self.assertFalse((base / 'output').exists())

class PublishedQuarantineTests(unittest.TestCase):
    def test_only_declared_conflicting_exhibits_are_quarantined(self):
        from scripts.build_reit_instrument_history import BXMT_QUARANTINE_URLS
        self.assertEqual(set(BXMT_QUARANTINE_URLS), {
            'https://www.sec.gov/Archives/edgar/data/1061630/000106163026000009/exhibit10504q25.htm',
            'https://www.sec.gov/Archives/edgar/data/1061630/000106163026000009/exhibit10664q25.htm',
        })

    def test_missing_agreement_request_preserves_effective_month_and_role_scope(self):
        r = row('ri', 'We entered new $4.0 billion credit facilities.', relation_type='entered_revolving_credit_facilities', effective_at='2025-04')
        p = build_instrument_history_packet([r])
        requests = [q for q in p['missing_evidence_queue'] if q['status'] == 'operative_agreement_missing']
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['effective_at'], '2025-04')
        self.assertEqual(requests[0]['requested_evidence_roles'], ['borrower', 'lender', 'administrative_agent', 'guarantor'])



class ImmutableSnapshotOutputTests(unittest.TestCase):
    def test_output_inside_source_snapshot_fails_before_rewriting_manifest(self):
        import tempfile
        from scripts.build_reit_instrument_history import write_history_packet
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            source.mkdir()
            HistoryPacketExportTests().snapshot(source)
            raw = (source / 'manifest.json').read_bytes()
            for output in (source, source / 'child'):
                with self.assertRaisesRegex(ValueError, 'snapshot'):
                    write_history_packet(source, output)
                self.assertEqual((source / 'manifest.json').read_bytes(), raw)



class HistoryReviewRegressionTests(unittest.TestCase):
    def test_prior_facility_reference_target_is_explicitly_a_component(self):
        r = row('facility', 'We amend and restate our previous $4.25 billion unsecured revolving credit facility.', relation_type='entered_revolving_credit_facilities')
        p = build_instrument_history_packet([r])
        link = p['instrument_links'][0]
        self.assertEqual(link.get('target_kind'), 'component')
        self.assertNotIn('to_instrument_id', link)
        self.assertIn(link['to_component_id'], {c['component_id'] for c in p['components']})
        self.assertFalse(link['identity_merge'])

    def test_unknown_information_time_cannot_outrank_known_latest_observation(self):
        known = row('known', 'Received USD 100 net proceeds.', instrument_id='same', available_at='2026-02-01T00:00:00Z')
        unknown = row('unknown', 'Received USD 120 net proceeds.', instrument_id='same', available_at=None)
        p = build_instrument_history_packet([unknown, known])
        self.assertEqual(p['views']['latest'][0]['value'], '100')
        self.assertEqual(p['views']['original'][0]['value'], '100')
        self.assertEqual(p['views']['information_time_unordered'][0]['value'], '120')
        self.assertEqual(len(p['events']), 2)




class SourceVersionIntegrationRegressionTests(unittest.TestCase):
    def test_asof_component_matches_selected_old_source_without_provenance_overwrite(self):
        old = row('old', 'Received USD 100 net proceeds.', instrument_id='same', available_at='2026-02-01T00:00:00Z')
        new = row('new', 'Received USD 120 net proceeds.', instrument_id='same', available_at='2026-03-01T00:00:00Z')
        old['evidence']['document_id'] = 'doc-old'
        new['evidence']['document_id'] = 'doc-new'
        p = build_instrument_history_packet([old, new], as_of='2026-02-10T00:00:00Z')
        self.assertEqual(len(p['components']), 2)
        chosen = p['views']['latest'][0]
        component = next(c for c in p['components'] if c['component_id'] == chosen['component_id'])
        self.assertEqual(chosen['value'], '100')
        self.assertEqual(component['evidence']['document_id'], 'doc-old')
        self.assertEqual(component['evidence']['source_sha256'], old['evidence']['source_sha256'])
        self.assertTrue(component['eligibility']['eligible'])

    def test_same_label_in_two_clauses_of_one_event_has_two_component_identities(self):
        r = row('clauses', 'Received USD 100 net proceeds and USD 120 net proceeds.')
        p = build_instrument_history_packet([r])
        self.assertEqual(len(p['components']), 2)
        self.assertEqual(len({c['component_id'] for c in p['components']}), 2)
        self.assertEqual(len({tuple(c['quote_span']) for c in p['components']}), 2)

    def test_same_declared_document_different_raw_versions_cannot_link_base_series(self):
        base = row('base', 'Indenture, dated January 26, 2021, among Alpha LP, as issuer, Bank NA, as trustee.', relation_type='issuer_under_indenture')
        series = row('series', 'Certificate pursuant to the Indenture, dated January 26, 2021, among Alpha LP, as issuer, Bank NA, as trustee, establishing 6.150% Senior Notes due 2034.', relation_type='series_established_under_indenture')
        # Version 1 contained only the base excerpt; version 2 also has the series.
        body_v1 = base['evidence']['quote']
        body_v2 = body_v1 + '\n' + series['evidence']['quote']
        base['evidence']['source_sha256'] = sha256(body_v1.encode()).hexdigest()
        series['evidence']['source_sha256'] = sha256(body_v2.encode()).hexdigest()
        p = build_instrument_history_packet([base, series])
        self.assertEqual(p['instrument_links'], [])
        self.assertTrue(any(q['status'] == 'agreement_series_link_unresolved' for q in p['missing_evidence_queue']))

    def test_existing_packet_directory_is_never_replaced(self):
        import tempfile
        from scripts.build_reit_instrument_history import write_history_packet
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'source'
            source.mkdir()
            HistoryPacketExportTests().snapshot(source)
            output = base / 'accepted-v1'
            write_history_packet(source, output)
            retained = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError, 'fresh|exist'):
                write_history_packet(source, output)
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, retained)



class ReviewedCorrespondenceContractTests(unittest.TestCase):
    def setUp(self):
        import inspect
        self.assertIn('reviewed_correspondences', inspect.signature(build_instrument_history_packet).parameters,
                      'Explicit reviewed correspondence input is missing')

    def records(self):
        old = row('old', 'Received USD 100 net proceeds.', instrument_id='same', available_at='2026-02-01T00:00:00Z')
        new = row('new', 'Received USD 120 net proceeds.', instrument_id='same', available_at='2026-03-01T00:00:00Z')
        old['evidence']['document_id'] = 'doc-old'
        new['evidence']['document_id'] = 'doc-new'
        return [old, new]

    def review(self, packet):
        return {'correspondence_id': 'review-1', 'review_status': 'approved',
                'reviewed_at': '2026-03-02T00:00:00Z',
                'identity_basis': 'Reviewer verified these clauses concern the same reported proceeds scope.',
                'component_anchors': [
                    {'component_id': c['component_id'], 'document_id': c['evidence']['document_id'],
                     'source_sha256': c['evidence']['source_sha256'], 'locator': c['evidence']['locator'],
                     'quote_span': c['quote_span']} for c in packet['components']]}

    def test_no_cross_source_ordering_without_explicit_approved_correspondence(self):
        p = build_instrument_history_packet(self.records())
        self.assertEqual(sorted(t['value'] for t in p['views']['original']), ['100', '120'])
        self.assertEqual(sorted(t['value'] for t in p['views']['latest']), ['100', '120'])
        self.assertEqual(p['reviewed_correspondences'], [])

    def test_approved_provenance_bound_correspondence_orders_without_merging_components(self):
        rows = self.records()
        baseline = build_instrument_history_packet(rows)
        p = build_instrument_history_packet(rows, reviewed_correspondences=[self.review(baseline)])
        self.assertEqual(len(p['components']), 2)
        self.assertEqual(len(p['reviewed_correspondences']), 1)
        self.assertEqual([t['value'] for t in p['views']['original']], ['100'])
        self.assertEqual([t['value'] for t in p['views']['latest']], ['120'])
        self.assertNotEqual(p['views']['original'][0]['component_id'], p['views']['latest'][0]['component_id'])
        self.assertEqual(p['instrument_links'], [])

    def test_wrong_source_hash_or_unapproved_review_cannot_establish_correspondence(self):
        rows = self.records()
        baseline = build_instrument_history_packet(rows)
        for problem in ('hash', 'status'):
            review = self.review(baseline)
            if problem == 'hash':
                review['component_anchors'][0]['source_sha256'] = '0' * 64
            else:
                review['review_status'] = 'candidate'
            p = build_instrument_history_packet(rows, reviewed_correspondences=[review])
            self.assertEqual(len(p['views']['latest']), 2)
            self.assertEqual(p['reviewed_correspondences'], [])
            self.assertTrue(any(q['status'] == 'correspondence_review_unresolved' for q in p['missing_evidence_queue']))



class NoteClauseIdentityRegressionTests(unittest.TestCase):
    def test_identical_note_terms_in_two_clauses_do_not_collapse_source_scopes(self):
        r = row('two-note-clauses', 'First tranche: USD 100 aggregate principal amount of its 6.150% Senior Notes due 2034. Second tranche: USD 100 aggregate principal amount of its 6.150% Senior Notes due 2034.', relation_type='completed_debt_issuance')
        p = build_instrument_history_packet([r])
        self.assertEqual(len(p['components']), 2)
        self.assertEqual(len({c['component_id'] for c in p['components']}), 2)
        self.assertEqual(len({tuple(c['quote_span']) for c in p['components']}), 2)
        self.assertEqual(len([t for t in p['events'][0]['terms'] if t['metric'] == 'amount']), 2)


if __name__ == '__main__':
    unittest.main()
