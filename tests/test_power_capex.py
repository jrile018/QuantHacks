"""Accounting, timing and ranking checks for public power/capex integration."""
import sys
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0,str(Path(__file__).parents[1]/'data/packaged_software'))
import collect_power_capex as collector
import add_power_capex_features as builder


class PowerCapexTests(unittest.TestCase):
    def test_lease_components_require_same_filing(self):
        company=dict(cik='0000000001')
        common=dict(end='2024-03-31',filed='2024-05-01',form='10-Q')
        facts=[dict(common,tag='OperatingLeaseLiabilityCurrent',val=10,accn='a'),
               dict(common,tag='OperatingLeaseLiabilityNoncurrent',val=20,accn='b')]
        result=collector.make_instant(company,'operating_lease_liability_usd',facts,'h',collector.HERE/'cache.json')
        self.assertEqual(result,[])
        facts[1]['accn']='a'
        result=collector.make_instant(company,'operating_lease_liability_usd',facts,'h',collector.HERE/'cache.json')
        self.assertEqual(result[0]['value'],30)
        self.assertEqual(result[0]['available_date'],'2024-05-02')

    def test_total_conflict_is_withheld(self):
        common=dict(end='2024-03-31',filed='2024-05-01',form='10-Q',accn='a')
        facts=[dict(common,tag='FinanceLeaseLiability',val=40),dict(common,tag='FinanceLeaseLiabilityCurrent',val=10),
               dict(common,tag='FinanceLeaseLiabilityNoncurrent',val=20)]
        self.assertEqual(collector.make_instant(dict(cik='0000000001'),'finance_lease_liability_usd',facts,'h',collector.HERE/'cache'),[])

    def test_invalid_future_instant_period_does_not_enter_balances(self):
        facts=[dict(end='2022-12-31',filed='2022-05-09',form='10-Q',accn='a',tag='OperatingLeaseLiability',val=10)]
        self.assertEqual(collector.make_instant(dict(cik='0000000001'),'lease',facts,'h',collector.HERE/'cache'),[])

    def test_future_restatement_cannot_enter_old_decision(self):
        first=collector.observation('1','f',10,'2024-03-31','2024-05-01','a')
        later=collector.observation('1','f',50,'2024-03-31','2024-08-01','b')
        self.assertEqual(collector.pick([first,later],'2024-06-30')['value'],10)
        self.assertEqual(collector.pick([first,later],'2024-09-30')['value'],50)
        self.assertIsNone(collector.pick([first],'2024-04-30'))

    def test_growth_prior_must_be_known_and_nonzero(self):
        first=collector.observation('1','lease_usd',0,'2023-03-31','2023-05-01','a')
        current=collector.observation('1','lease_usd',10,'2024-03-31','2024-05-01','b')
        change=collector.changes([first,current],'lease',365,16,'yoy')
        self.assertEqual(len(change),1)
        self.assertEqual(change[0]['feature'],'lease_delta_yoy_usd')
        first['available_date']='2024-08-01'
        self.assertEqual(collector.changes([first,current],'lease',365,16,'yoy'),[])

    def test_yoy_prior_is_not_rejected_as_stale_at_current_publication(self):
        prior=collector.observation('1','f',10,'2023-03-31','2023-05-01','a')
        current=collector.observation('1','f',20,'2024-03-31','2024-05-10','b')
        changes=collector.changes([prior,current],'f',365,16,'yoy')
        self.assertEqual(len(changes),2)
        self.assertEqual(changes[1]['value'],1)

    def test_conflicting_same_grain_and_stale_values_withheld(self):
        first=collector.observation('1','f',10,'2024-03-31','2024-05-01','a')
        conflict=dict(first,value=11,evidence_ref='b')
        self.assertIsNone(collector.pick([first,conflict],'2024-06-30'))
        self.assertIsNone(collector.pick([first],'2025-06-30'))

    def test_macro_is_available_after_announcement_not_delivery_year(self):
        rows=[dict(available_date='2024-07-31',value=269.92)]
        f='pjm_rto_capacity_price_usd_mw_day'
        self.assertIsNone(builder.select(rows,'2024-06-30',f,'2024Q2'))
        self.assertEqual(builder.select(rows,'2024-09-30',f,'2024Q3')['value'],269.92)

    def test_guidance_not_carried_beyond_disclosure_quarter_or_horizon(self):
        f='capex_guidance_annual_high_usd'
        r=collector.observation('1',f,10,'2024-02-15','2024-02-16','a')
        r['valid_until']='2024-12-31'
        self.assertIsNotNone(builder.select([r],'2024-03-31',f,'2024Q1'))
        self.assertIsNone(builder.select([r],'2024-06-30',f,'2024Q2'))
        r['valid_until']='2024-03-01'
        self.assertIsNone(builder.select([r],'2024-03-31',f,'2024Q1'))

    def test_identical_macro_and_tied_values_have_identical_ranks(self):
        self.assertTrue((builder.ranks(pd.Series([50]*5))==0).all())
        ranked=builder.ranks(pd.Series([0,0,1,2,3]))
        self.assertEqual(ranked.iloc[0],ranked.iloc[1])
        self.assertTrue(builder.ranks(pd.Series([1,2,3,4])).isna().all())

    def test_visible_text_excludes_hidden_xbrl(self):
        p=collector.VisibleText()
        p.feed('<p>Visible</p><ix:header><ix:hidden>Capital expenditure $100 billion</ix:hidden></ix:header><p>End</p>')
        self.assertIn('Visible',''.join(p.parts))
        self.assertNotIn('billion',''.join(p.parts))
        self.assertIn('End',''.join(p.parts))

    def test_legal_names_reduce_pdf_creator_matches(self):
        self.assertEqual(collector.company_search_name(dict(ticker='ADBE',name='Adobe Inc.')),'Adobe Inc')
        self.assertEqual(collector.company_search_name(dict(ticker='MSFT',name='Microsoft Corp')),'Microsoft Corporation')


if __name__=='__main__':
    unittest.main()
