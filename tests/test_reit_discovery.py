import unittest
from src.reit_universe import build_universe
try:
    from src.reit_discovery import reitwatch_candidates, resolve_candidates, filing_eligibility_evidence
except ImportError:
    reitwatch_candidates = None


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(reitwatch_candidates, 'Discovery integration is missing')

    def test_roster_is_discovery_and_has_exact_quote(self):
        quote='1 Example Trust, Inc. EXM Equity Apartments S&P 500 50.0'
        rows=reitwatch_candidates([{'number':29,'text':'REITs in the FTSE Nareit All REITs Index\n'+quote}],source_url='https://www.reit.com/RW2401.pdf',source_sha256='a'*64)
        self.assertEqual(rows[0]['ticker'],'EXM')
        self.assertEqual(rows[0]['source_quote'],quote)
        self.assertEqual(rows[0]['discovery_status'],'candidate_only')
        self.assertIsNone(rows[0]['cik'])

    def test_ticker_reuse_does_not_bind_changed_legal_name(self):
        rows=resolve_candidates([{'name':'Old Company','ticker':'ABC'}],[{'name':'New Company','ticker':'ABC','cik':'0000000001','exchange':'NYSE'}])
        self.assertIsNone(rows[0]['cik'])
        self.assertEqual(rows[0]['resolution'],'ticker_name_conflict')

    def test_legal_suffix_alias_and_sec_jurisdiction_are_candidate_only(self):
        rows=resolve_candidates([{'name':'American Tower Corporation','ticker':'AMT'}],
            [{'name':'AMERICAN TOWER CORP /MA/','ticker':'AMT','cik':'0001053507','exchange':'NYSE'}])
        self.assertEqual(rows[0]['cik'],'0001053507')
        self.assertEqual(rows[0]['resolution'],'current_ticker_and_name_candidate')

    def test_legal_suffix_alias_matches_visible_filing_identity(self):
        html='<html><p>Example Corporation</p><table><tr><td>Common Stock</td><td>EXM</td><td>NYSE</td></tr></table><p>We operate as a real estate investment trust.</p></html>'
        doc={'cik':'0000000001','issuer':'EXAMPLE CORP /MA/','ticker':'EXM','security_id':'exm',
             'report_date':'2025-12-31','url':'https://www.sec.gov/Archives/x.htm','sha256':'a'*64,
             'retrieved_at':'2026-10-04T01:00:00+00:00'}
        self.assertEqual({r['kind'] for r in filing_eligibility_evidence(doc,html)},
                         {'reit_status','listing','security_type'})

    def test_explicit_cover_and_current_reit_claim_support_three_axes(self):
        html='<html><p>Example Trust Inc.</p><table><tr><td>Common Stock</td><td>EXM</td><td>New York Stock Exchange</td></tr></table><p>We have elected to be taxed as a real estate investment trust for federal income tax purposes.</p></html>'
        doc={'cik':'0000000001','issuer':'Example Trust Inc.','ticker':'EXM','security_id':'exm','report_date':'2025-12-31','url':'https://www.sec.gov/Archives/x.htm','sha256':'a'*64,'retrieved_at':'2026-10-04T01:00:00+00:00'}
        proof=filing_eligibility_evidence(doc,html)
        self.assertEqual({x['kind'] for x in proof},{'reit_status','listing','security_type'})
        self.assertTrue(all(x['known_from']==doc['retrieved_at'] for x in proof))

    def test_hypothetical_reit_and_preferred_cover_not_common(self):
        html='<html>Example Trust Inc.<table><tr><td>Preferred Stock</td><td>EXM</td><td>New York Stock Exchange</td></tr></table><p>If we elected to be taxed as a real estate investment trust, we could reduce taxes.</p></html>'
        doc={'cik':'0000000001','issuer':'Example Trust Inc.','ticker':'EXM','security_id':'exm','report_date':'2025-12-31','url':'https://www.sec.gov/Archives/x.htm','sha256':'a'*64,'retrieved_at':'2026-10-04T01:00:00+00:00'}
        proof=filing_eligibility_evidence(doc,html)
        self.assertFalse(any(row['kind']=='reit_status' and row['value'] is True for row in proof))
        self.assertFalse(any(row['kind']=='security_type' for row in proof))

    def test_xbrl_hidden_context_does_not_displace_visible_identity(self):
        html='<html><ix:header>'+('context '*9000)+'</ix:header><p>Example Trust Inc.</p><table><tr><td>Common Stock</td><td>EXM</td><td>New York Stock Exchange</td></tr></table><p>We operate as a real estate investment trust.</p></html>'
        doc={'cik':'0000000001','issuer':'Example Trust Inc.','ticker':'EXM','security_id':'exm','report_date':'2025-12-31','url':'https://www.sec.gov/Archives/x.htm','sha256':'a'*64,'retrieved_at':'2026-10-04T01:00:00+00:00'}
        self.assertEqual({r['kind'] for r in filing_eligibility_evidence(doc,html)},{'reit_status','listing','security_type'})
        self.assertEqual(filing_eligibility_evidence(dict(doc,issuer=''),html),[])

    def context_proof(self, paragraphs):
        doc={'cik':'0000000001','issuer':'Example Trust Inc.','ticker':'EXM','security_id':'exm',
             'report_date':'2025-12-31','url':'https://www.sec.gov/Archives/x.htm','sha256':'a'*64,
             'retrieved_at':'2026-10-04T01:00:00+00:00'}
        html='<html><p>Example Trust Inc.</p><table><tr><td>Common Stock</td><td>EXM</td><td>The Nasdaq Stock Market LLC</td></tr></table>'
        html+=''.join('<p>'+text+'</p>' for text in paragraphs)+'</html>'
        return doc,filing_eligibility_evidence(doc,html)

    def assert_unresolved_tax_status(self, paragraphs):
        doc,proof=self.context_proof(paragraphs)
        self.assertFalse(any(row['kind']=='reit_status' and row['value'] is True for row in proof))
        review=[row for row in proof if row['kind']=='reit_status_review']
        self.assertTrue(review, 'Unresolved tax context must be retained for review')
        self.assertTrue(all(row['review_required'] for row in review))
        result=build_universe([{'cik':doc['cik'],'ticker':doc['ticker'],'security_id':doc['security_id']}],
                              proof,'2026-10-04T02:00:00Z')
        self.assertEqual(result['validated'],[])
        self.assertEqual(len(result['candidates']),1)
        return doc,proof

    def test_revoked_election_in_same_paragraph_blocks_positive_fragment(self):
        context='We have elected to be taxed as a REIT, but revoked our REIT election effective January 1, 2026.'
        _,proof=self.assert_unresolved_tax_status([context])
        self.assertTrue(any(row['quote']==context for row in proof if row['kind']=='reit_status_review'))

    def test_revocation_elsewhere_blocks_an_earlier_positive_claim(self):
        self.assert_unresolved_tax_status(['We have elected to be taxed as a REIT.',
                                         'The Company revoked its REIT election effective January 1, 2026.'])

    def test_actual_nonqualification_elsewhere_blocks_positive_claim(self):
        for negative in ['We did not qualify as a REIT for the current year.',
                         'We failed to qualify as a real estate investment trust.',
                         'The Company no longer qualifies as a REIT.',
                         'Our REIT election was terminated effective January 1, 2026.',
                         'Our election to be taxed as a REIT has been revoked.',
                         'We are not a REIT for the current tax year.',
                         'We are no longer taxed as a REIT.']:
            with self.subTest(negative=negative):
                self.assert_unresolved_tax_status(['We have elected to be taxed as a REIT.',negative])

    def test_conditional_qualification_after_positive_fragment_is_unresolved(self):
        self.assert_unresolved_tax_status(['We qualify as a REIT only if we satisfy the annual tax requirements.'])

    def test_long_conditional_prefix_cannot_escape_context_check(self):
        self.assert_unresolved_tax_status(['If all of the many annual distribution and ownership requirements are satisfied, we qualify as a REIT.'])

    def test_historical_qualification_alone_does_not_prove_current_status(self):
        self.assert_unresolved_tax_status(['We qualified as a REIT for the tax year ended December 31, 2020.'])

    def test_whole_positive_paragraph_and_retrieval_provenance_retained(self):
        context='We qualify as a real estate investment trust for federal income tax purposes. Our tax year ends December 31.'
        doc,proof=self.context_proof([context])
        row=next(row for row in proof if row['kind']=='reit_status')
        self.assertEqual(row['quote'],context)
        self.assertEqual(row['known_from'],doc['retrieved_at'])
        self.assertEqual(row['source_sha256'],doc['sha256'])
        self.assertEqual(row['source_url'],doc['url'])
        self.assertFalse(row['historical_trading_ready'])
        self.assertIn('paragraph',row['locator'])

    def test_conditional_risk_disclosure_does_not_negate_actual_current_claim(self):
        _,proof=self.context_proof(['The Company qualifies as a REIT for federal tax purposes.',
            'If we fail to qualify as a REIT, we would be subject to additional taxation.'])
        self.assertTrue(any(row['kind']=='reit_status' and row['value'] is True for row in proof))


if __name__=='__main__':
    unittest.main()
