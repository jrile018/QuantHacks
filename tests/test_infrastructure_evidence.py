import json
import sys
import unittest
import urllib.request
from unittest.mock import patch
import pandas as pd
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data/packaged_software'))
from extract_infrastructure_evidence import classify, split_sentences
from review_infrastructure_sources import appian_spending
from collect_subsidiary_accounts import StripAuthorizationRedirect
from publish_infrastructure_evidence import reviewed_candidate_commitments


class InfrastructureTests(unittest.TestCase):
    def cloud_review_fixture(self):
        row={'cik':'1','ticker':'AI','name':'Example','filed_date':'2024-12-10',
             'source_url':'https://example.com/filing','local_path':'example.htm',
             'evidence_id':'checked','amount_usd_candidate':355000000}
        review={'ticker':'AI','evidence_id':'checked','amount_usd':355000000,
                'source_sha256':'pinned','source_pattern':'cloud hosting commitment',
                'metric':'cloud_remaining_obligations','measure_type':'remaining_commitment_not_cash_paid',
                'scope_note':'Professional services excluded'}
        return pd.DataFrame([row]),{'additional_cloud_commitment_reviews':[review]}

    def test_reviewed_commitment_keeps_late_availability_and_no_cash_value(self):
        frame,registry=self.cloud_review_fixture()
        with patch('publish_infrastructure_evidence.pd.read_csv',return_value=frame), patch('publish_infrastructure_evidence.source_text',return_value=('cloud hosting commitment','pinned')):
            row=reviewed_candidate_commitments(registry).iloc[0]
        self.assertEqual(row.available_date_conservative,'2024-12-11')
        self.assertEqual(row.actual_cash_paid_usd,'')
        self.assertEqual(row.metric,'cloud_remaining_obligations')

    def test_reviewed_commitment_rejects_changed_source(self):
        frame,registry=self.cloud_review_fixture()
        with patch('publish_infrastructure_evidence.pd.read_csv',return_value=frame), patch('publish_infrastructure_evidence.source_text',return_value=('cloud hosting commitment','changed')):
            with self.assertRaisesRegex(ValueError,'source has changed'):
                reviewed_candidate_commitments(registry)

    def test_reviewed_commitment_rejects_other_amount_in_same_excerpt(self):
        frame,registry=self.cloud_review_fixture()
        frame.loc[0,'amount_usd_candidate']=43500000
        with patch('publish_infrastructure_evidence.pd.read_csv',return_value=frame):
            with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
                reviewed_candidate_commitments(registry)

    def test_land_dimension_is_balance_not_spending(self):
        result=classify('us-gaap:PropertyPlantAndEquipmentGross',json.dumps({'us-gaap:PropertyPlantAndEquipmentTypeAxis':'us-gaap:LandMember'}),'')
        self.assertEqual(result[:2],('land_gross_asset_balance','asset_balance'))

    def test_combined_land_building_is_not_land_only(self):
        result=classify('us-gaap:PropertyPlantAndEquipmentGross',json.dumps({'axis':'us-gaap:LandAndBuildingMember'}),'')
        self.assertEqual(result[0],'land_and_buildings_combined_gross_asset_balance')

    def test_cloud_selling_revenue_is_excluded(self):
        self.assertIsNone(classify('orcl:CloudServicesAndLicenseSupportRevenue','{}','2022-01-01'))

    def test_prepaid_is_not_expense(self):
        self.assertEqual(classify('ampl:PrepaidHostingCurrent','{}','')[1],'prepaid_asset_balance')

    def test_duration_custom_tag_does_not_establish_total_expense(self):
        self.assertEqual(classify('ddog:CloudHostingAndInfrastructureExpenses','{}','2022-01-01')[2],'custom_concept_requires_context_review')

    def test_decimal_amount_not_split(self):
        self.assertEqual(len(split_sentences('Cloud commitment is $110.0 million. Another sentence.')),2)

    def test_spending_comparison_keeps_separate_periods(self):
        rows=list(appian_spending('Spending under this agreement for the three and six months ended June 30, 2026 totaled $ 17.2 million and $ 33.4 million, respectively.'))
        self.assertEqual([(r['period_start'],r['amount_usd']) for r in rows],[('2026-04-01',17200000),('2026-01-01',33400000)])

    def test_annual_spend_not_inferred_from_commitment(self):
        rows=list(appian_spending('Spending under this agreement for the years ended December 31, 2024, 2023, and 2022 totaled $41.2 million, $36.6 million, and $33.1 million, respectively.'))
        self.assertEqual([(r['period_end'],r['amount_usd']) for r in rows],[('2024-12-31',41200000),('2023-12-31',36600000),('2022-12-31',33100000)])
        self.assertEqual(list(appian_spending('Purchase commitments total $220 million.')),[])

    def test_signed_document_redirect_strips_api_credentials(self):
        request=urllib.request.Request('https://document-api.company-information.service.gov.uk/document/test/content',headers={'Authorization':'Basic example'})
        redirected=StripAuthorizationRedirect().redirect_request(request,None,302,'Found',{},'https://example.s3.amazonaws.com/document.pdf')
        self.assertIsNone(redirected.get_header('Authorization'))

    def test_document_redirect_requires_https(self):
        request=urllib.request.Request('https://document-api.company-information.service.gov.uk/document/test/content')
        with self.assertRaises(ValueError):
            StripAuthorizationRedirect().redirect_request(request,None,302,'Found',{},'http://example.com/document.pdf')


if __name__=='__main__':
    unittest.main()
