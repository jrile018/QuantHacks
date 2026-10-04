import unittest
import json
import copy
from pathlib import Path
from src.research_validation.wording_equity_pilot import assess_pilot_candidates, replay_wording_pilot, validate_pilot_protocol

def fixture():
    root=Path(__file__).resolve().parents[1]
    p=json.loads((root/'configs/wording_equity_pilot-v2.json').read_text(encoding='utf-8'))
    s=json.loads((root/'configs/wording_equity_calendar-2024-v1.json').read_text(encoding='utf-8'))
    c=dict(candidate_id='c1',cik='0001053507',accession='a1',security_id='ABC',source_sha256='a'*64,signal=-.5,signal_recipe_id=p['signal_recipe_id'],form='8-K',items=['2.02'],signal_document_role='press_release_exhibit',source_quality='qualified',public_clock_quality='qualified',model_vintage_quality='qualified',identity_quality='qualified',public_by_utc='2024-01-02T20:00:00Z',corporate_actions=dict(status='verified_none',qualified=True,horizon_id=p['horizon_id'],available_at_utc='2024-01-03T14:00:00Z',start_at_utc='2024-01-03T14:30:00Z',end_at_utc='2024-01-03T21:00:00Z'),costs=dict(qualified=True,currency='USD',entry_fee=1,exit_fee=1,entry_slippage=0,exit_slippage=0,available_at_utc='2024-01-03T14:00:00Z',valid_through_utc='2024-01-03T21:00:00Z'),borrow=dict(qualified=True,available_at_utc='2024-01-03T14:00:00Z',valid_through_utc='2024-01-03T21:00:00Z',quantity=100000,total_fee=2),margin=500000,margin_available_at_utc='2024-01-03T14:00:00Z')
    q=[dict(quote_id='q1',instrument_id='ABC',at_utc='2024-01-03T14:31:00Z',available_at_utc='2024-01-03T14:31:00Z',bid=99,ask=100,bid_size=100000,ask_size=100000,evidence_kind='update',currency='USD',raw_price=True),dict(quote_id='q2',instrument_id='ABC',at_utc='2024-01-03T20:59:00Z',available_at_utc='2024-01-03T20:59:00Z',bid=101,ask=102,bid_size=100000,ask_size=100000,evidence_kind='update',currency='USD',raw_price=True)]
    return p,c,q,s

class PilotTests(unittest.TestCase):
    def test_gates(self):
        p,c,_,_=fixture()
        self.assertTrue(validate_pilot_protocol(p))
        c['public_clock_quality']='conditional'
        self.assertIn('public_clock_quality',assess_pilot_candidates([c],p)['excluded'][0]['reasons'])
        c['public_clock_quality']='qualified'
        c['public_by_utc']='2025-01-02T20:00:00Z'
        self.assertIn('protected_period',assess_pilot_candidates([c],p)['excluded'][0]['reasons'])
        c['public_by_utc']='2024-01-02T20:00:00Z'
        c['corporate_actions']['status']='unknown'
        self.assertIn('corporate_actions',assess_pilot_candidates([c],p)['excluded'][0]['reasons'])
    def test_replay_and_missing_exit(self):
        p,c,q,s=fixture()
        r=replay_wording_pilot([c],q,s,p)
        self.assertEqual(r['status'],'contract_replayed')
        self.assertLess(r['wording']['final_equity'],p['initial_cash'])
        self.assertGreater(r['baseline']['final_equity'],p['initial_cash'])
        self.assertGreater(r['wording']['ledger'][0]['restricted_short_proceeds'],0)
        r=replay_wording_pilot([c],q[:1],s,p)
        self.assertEqual(len(r['assessment']['eligible']),1)
        self.assertEqual(r['status'],'insufficient')
        self.assertEqual(r['wording']['open_positions'],1)
        self.assertIsNone(r['wording_pnl'])
    def test_empty_marks(self):
        p,c,q,s=fixture()
        r=replay_wording_pilot([],q,s,p)
        self.assertEqual([x['cash_reference'] for x in r['marks']],[1000000.0]*252)
        self.assertIsNone(r['wording_pnl'])



    def test_duplicate_cost_borrow_and_entry_budget(self):
        import copy
        p,c,q,s=fixture()
        self.assertEqual(assess_pilot_candidates([c,copy.deepcopy(c)],p)['eligible'],[])
        c['borrow']['qualified']=False
        self.assertIn('borrow_or_collateral',assess_pilot_candidates([c],p)['excluded'][0]['reasons'])
        c['borrow']['qualified']=True
        c['costs']['exit_fee']=float('nan')
        self.assertIn('cost_evidence',assess_pilot_candidates([c],p)['excluded'][0]['reasons'])
        c['costs']['exit_fee']=1
        r=replay_wording_pilot([c],q,s,p)
        order=r['wording']['reserved_orders'][0]
        self.assertLessEqual(order['quantity']*q[0]['bid'],p['initial_cash'])
        self.assertLessEqual(order['margin']+c['costs']['entry_fee']+c['costs']['entry_slippage'],p['initial_cash'])
        self.assertEqual(r['wording']['trades'][0]['cash_gain'],order['quantity']*(q[0]['bid']-q[1]['ask'])-4)


    def test_mixed_sides_equal_targets_and_flat_marks(self):
        import copy
        p,c,q,s=fixture()
        other=copy.deepcopy(c)
        other.update(candidate_id='c2',accession='a2',security_id='XYZ',signal=.5)
        other['corporate_actions']['security_id']='XYZ'
        other_quotes=[dict(x,quote_id=x['quote_id']+'x',instrument_id='XYZ') for x in q]
        r=replay_wording_pilot([c,other],q+other_quotes,s,p)
        self.assertEqual(r['status'],'contract_replayed')
        orders=r['wording']['reserved_orders']
        self.assertEqual({x['side'] for x in orders},{'long','short'})
        self.assertEqual(orders[0]['quantity'],orders[1]['quantity'])
        gross=sum(x['quantity']*100 for x in orders)
        self.assertLessEqual(gross,p['initial_cash']-2*c['costs']['entry_fee'])
        self.assertEqual(len(r['marks']),252)
        self.assertEqual(r['marks'][1]['wording_equity'],r['marks'][2]['wording_equity'])
        self.assertEqual(r['wording']['ledger'][-1]['positions'],{})
        self.assertEqual(r['wording']['ledger'][-1]['collateral'],0)
        self.assertEqual(r['wording']['ledger'][-1]['restricted_short_proceeds'],0)

    def test_future_exit_cannot_change_reserved_quantity(self):
        import copy
        p,c,q,s=fixture()
        original=replay_wording_pilot([c],q,s,p)
        changed=copy.deepcopy(q)
        changed[1]['bid']=.01
        changed[1]['ask']=10000
        changed[1]['bid_size']=0
        changed[1]['ask_size']=0
        missing=replay_wording_pilot([c],changed,s,p)
        self.assertEqual(original['wording']['reserved_orders'][0]['quantity'],
                         missing['wording']['reserved_orders'][0]['quantity'])
        self.assertEqual(missing['status'],'insufficient')
        self.assertIsNone(missing['marks'][1]['wording_equity'])

    def test_incomplete_horizon_expired_cost_and_borrow(self):
        import copy
        p,c,q,s=fixture()
        bad=copy.deepcopy(c)
        del bad['corporate_actions']['end_at_utc']
        self.assertIn('corporate_actions',assess_pilot_candidates([bad],p)['excluded'][0]['reasons'])
        bad=copy.deepcopy(c)
        del bad['costs']['entry_fee']
        self.assertIn('cost_evidence',assess_pilot_candidates([bad],p)['excluded'][0]['reasons'])
        bad=copy.deepcopy(c)
        bad['costs']['valid_through_utc']='2024-01-03T15:00:00Z'
        self.assertIn('cost_evidence',replay_wording_pilot([bad],q,s,p)['assessment']['excluded'][0]['reasons'])
        bad=copy.deepcopy(c)
        bad['borrow']['valid_through_utc']='2024-01-03T15:00:00Z'
        self.assertIn('borrow_evidence',replay_wording_pilot([bad],q,s,p)['assessment']['excluded'][0]['reasons'])

    def test_different_flat_cost_schedules_and_duplicate_instrument(self):
        import copy
        p,c,q,s=fixture()
        other=copy.deepcopy(c)
        other.update(candidate_id='c2',accession='a2',security_id='XYZ',signal=.5)
        q2=[dict(x,quote_id=x['quote_id']+'x',instrument_id='XYZ') for x in q]
        other['costs']['entry_fee']=2
        r=replay_wording_pilot([c,other],q+q2,s,p)
        self.assertEqual(r['status'],'insufficient')
        self.assertEqual(r['assessment']['eligible'],[])
        self.assertTrue(all('incompatible_flat_cost_schedule' in x['reasons'] for x in r['assessment']['excluded']))
        other['costs']['entry_fee']=1
        other['security_id']='ABC'
        r=replay_wording_pilot([c,other],q,s,p)
        self.assertEqual(r['status'],'insufficient')
        self.assertIn('duplicate_instrument_decision',[x['reason'] for x in r['wording']['rejected']])

    def test_neutral_signal_baseline_active_and_cash_marks(self):
        p,c,q,s=fixture()
        c['signal']=0
        r=replay_wording_pilot([c],q,s,p)
        self.assertEqual(r['status'],'contract_replayed')
        self.assertEqual(r['wording']['trades'],[])
        self.assertEqual(len(r['baseline']['trades']),1)
        self.assertEqual(r['marks'][0]['wording_equity'],p['initial_cash'])
        self.assertEqual(r['cash_reference']['final_equity'],p['initial_cash'])



    def test_different_costs_across_sessions_excluded(self):
        import copy
        p,c,q,s=fixture()
        other=copy.deepcopy(c)
        other.update(candidate_id='c2',accession='a2',security_id='XYZ',
                     public_by_utc='2024-01-03T21:30:00Z')
        for field in ('corporate_actions','costs','borrow'):
            for key,value in list(other[field].items()):
                if isinstance(value,str):
                    other[field][key]=value.replace('2024-01-03','2024-01-04')
        other['costs']['entry_fee']=2
        later=[dict(x,quote_id=x['quote_id']+'x',instrument_id='XYZ',
                    at_utc=x['at_utc'].replace('2024-01-03','2024-01-04'),
                    available_at_utc=x['available_at_utc'].replace('2024-01-03','2024-01-04')) for x in q]
        r=replay_wording_pilot([c,other],q+later,s,p)
        self.assertEqual(r['status'],'insufficient')
        self.assertEqual(r['assessment']['eligible'],[])
        self.assertEqual(len(r['marks']),252)
    def test_decision_is_entry_and_evidence_can_arrive_after_open(self):
        p,c,q,s=fixture()
        for field in ('corporate_actions','costs','borrow'):
            c[field]['available_at_utc']='2024-01-03T14:30:30Z'
        c['margin_available_at_utc']='2024-01-03T14:30:30Z'
        r=replay_wording_pilot([c],q,s,p)
        self.assertEqual(r['status'],'contract_replayed')
        order=r['wording']['reserved_orders'][0]
        self.assertEqual(order['decision_at_utc'],order['entry_at_utc'])
        self.assertEqual(order['decision_at_utc'],'2024-01-03T14:31:00+00:00')

    def test_accession_aliases_refuse_both_candidates(self):
        import copy
        p,c,q,s=fixture()
        alias=copy.deepcopy(c)
        alias.update(candidate_id='alias',security_id='XYZ')
        alias['corporate_actions']['security_id']='XYZ'
        a=assess_pilot_candidates([c,alias],p)
        self.assertEqual(a['eligible'],[])
        self.assertEqual(len(a['excluded']),2)
        self.assertTrue(all('duplicate_event_security' in x['reasons'] for x in a['excluded']))

    def test_bad_entry_size_or_crossed_quote_is_exclusion(self):
        import copy
        p,c,q,s=fixture()
        for mutation in ({'ask_size':float('nan')},{'bid_size':None},{'ask_size':-1},{'bid':101,'ask':100}):
            bad=copy.deepcopy(q)
            bad[0].update(mutation)
            r=replay_wording_pilot([c],bad,s,p)
            self.assertEqual(r['status'],'insufficient')
            self.assertIn('entry_quote_missing',r['assessment']['excluded'][0]['reasons'])

    def test_v2_frozen_protocol_and_complete_calendar(self):
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        p=json.loads((root/'configs/wording_equity_pilot-v2.json').read_text(encoding='utf-8'))
        cal=json.loads((root/'configs/wording_equity_calendar-2024-v1.json').read_text(encoding='utf-8'))
        self.assertTrue(validate_pilot_protocol(p))
        r=replay_wording_pilot([],[],cal,p)
        self.assertEqual(len(r['marks']),252)
        self.assertEqual(r['evidence_acceptance'],'external_receipt_required')
        self.assertEqual(r['economic_qualification'],'contract_only')
        self.assertFalse(r['headline_eligible'])
        altered=dict(p,signal_definition='changed')
        with self.assertRaises(ValueError):
            validate_pilot_protocol(altered)
        with self.assertRaises(ValueError):
            replay_wording_pilot([],[],cal['rows'][:-1],p)
        tampered=copy.deepcopy(cal)
        tampered['rows'][0]['close_at_utc']='2024-01-02T20:00:00+00:00'
        with self.assertRaises(ValueError):
            replay_wording_pilot([],[],tampered,p)