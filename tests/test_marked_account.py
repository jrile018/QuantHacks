import copy
import json
import unittest
from pathlib import Path

from src.research_validation.marked_account import export_marked_account_panel


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    protocol = json.loads((ROOT/'configs/wording_equity_pilot-v2.json').read_text(encoding='utf-8'))
    calendar = json.loads((ROOT/'configs/wording_equity_calendar-2024-v1.json').read_text(encoding='utf-8'))
    marks = [dict(session_id=s['session_id'], at_utc=s['close_at_utc'],
                  wording_equity=1000000.0, baseline_equity=1000000.0,
                  cash_reference=1000000.0) for s in calendar['rows']]
    replay = dict(schema_version='wording-equity-pilot-result-v2',
                  status='contract_replayed', economic_qualification='contract_only',
                  canonical_economic_qualified=False, headline_eligible=False,
                  marks=marks,
                  wording=dict(ledger=[], trades=[], rejected=[], open_positions=0, diagnostics=[]),
                  baseline=dict(ledger=[], trades=[], rejected=[], open_positions=0, diagnostics=[]))
    return replay, calendar, protocol


class MarkedAccountTests(unittest.TestCase):
    def test_cash_days_have_252_zero_returns_and_unqualified_probe(self):
        replay, calendar, protocol = fixture()
        out = export_marked_account_panel(replay, calendar, protocol)
        panel, args = out['panel'], out['probe_args']
        self.assertEqual(panel['status'], 'contract_exported')
        self.assertEqual(len(panel['rows']), 252)
        self.assertEqual(panel['anchor']['period_index'], 0)
        self.assertIsNone(panel['anchor']['observed_at_utc'])
        self.assertEqual(args['net_returns'], [0.0]*252)
        self.assertEqual(args['reference_returns'], [0.0]*252)
        self.assertEqual(args['reference_kind'], 'declared_zero')
        self.assertEqual(args['periods_per_year'], 252)
        self.assertFalse(args['timing_verified'])
        self.assertFalse(args['costs_complete'])
        self.assertFalse(args['flows_reconciled'])
        self.assertFalse(panel['canonical_economic_qualified'])

    def test_mixed_long_short_uses_full_net_nav_once(self):
        replay, calendar, protocol = fixture()
        day = calendar['rows'][1]
        close = day['close_at_utc']
        replay['wording']['ledger'] = [
            dict(at_utc=day['open_at_utc'], action='entry', equity=999990.0,
                 positions={'long':{'side':'long'}, 'short':{'side':'short'}},
                 collateral=200000.0, restricted_short_proceeds=200000.0),
            dict(at_utc=close, action='exit', decision_id='long', equity=1000025.0, positions={'short':{'side':'short'}},
                 collateral=200000.0, restricted_short_proceeds=200000.0),
            dict(at_utc=close, action='exit', decision_id='short', equity=1000030.0, positions={},
                 collateral=0.0, restricted_short_proceeds=0.0)]
        replay['wording']['trades'] = [
            dict(decision_id='long',cash_gain=25.0),
            dict(decision_id='short',cash_gain=5.0)]
        for mark in replay['marks'][1:]:
            mark['wording_equity']=1000030.0
        out=export_marked_account_panel(replay,calendar,protocol)
        rows=out['panel']['rows']
        self.assertEqual(out['panel']['status'],'contract_exported')
        self.assertEqual(rows[1]['nav'],1000030.0)
        self.assertAlmostEqual(rows[1]['net_return'],.00003)
        self.assertEqual(rows[2]['net_return'],0.0)
        self.assertEqual(out['probe_args']['net_returns'][1],rows[1]['net_return'])
        self.assertEqual(out['panel']['provenance']['economic_qualified'],False)

    def test_calendar_and_mark_clocks_must_match_without_reindexing(self):
        replay, calendar, protocol = fixture()
        with self.assertRaises(ValueError):
            export_marked_account_panel(replay,dict(calendar,rows=calendar['rows'][:-1]),protocol)
        replay['marks'][1]['at_utc']='2024-01-03T20:00:00+00:00'
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(out['panel']['status'],'insufficient')
        self.assertIsNone(out['panel']['rows'][1]['nav'])
        self.assertEqual(out['panel']['rows'][1]['reason'],'mark_timestamp_mismatch')
        self.assertIsNone(out['probe_args']['net_returns'][2])

    def test_unresolved_and_missing_nav_are_never_filled(self):
        replay, calendar, protocol = fixture()
        day=calendar['rows'][1]
        replay['marks'][1]['wording_equity']=None
        replay['wording']['open_positions']=1
        replay['wording']['ledger']=[dict(at_utc=day['open_at_utc'],action='entry',
            equity=1000000.0,positions={'open':{'side':'short'}},
            collateral=500000.0,restricted_short_proceeds=500000.0)]
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(out['panel']['status'],'insufficient')
        self.assertIsNone(out['panel']['rows'][1]['nav'])
        self.assertIsNone(out['panel']['rows'][2]['nav'])
        self.assertFalse(out['probe_args']['marks_complete'])

    def test_ruin_and_unsupported_flows_refuse_panel(self):
        replay, calendar, protocol = fixture()
        replay['marks'][0]['wording_equity']=-1
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertIsNone(out['panel']['rows'][0]['nav'])
        self.assertEqual(out['panel']['rows'][0]['reason'],'nonpositive_nav')
        replay, calendar, protocol = fixture()
        replay['external_flows']=[{'amount':100}]
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(out['panel']['status'],'insufficient')
        self.assertIsNone(out['probe_args']['net_returns'][0])

    def test_does_not_mutate_inputs_or_add_fees_again(self):
        replay, calendar, protocol = fixture()
        before=copy.deepcopy(replay)
        out=export_marked_account_panel(replay,calendar,protocol,arm='baseline')
        self.assertEqual(replay,before)
        self.assertEqual(out['panel']['rows'][0]['nav'],1000000.0)
        self.assertIn('ledger_sha256',out['panel']['provenance'])
        self.assertIn('replay_sha256',out['panel']['provenance'])
        self.assertIn('protocol_sha256',out['panel']['provenance'])
        self.assertIn('calendar_sha256',out['panel']['provenance'])

    def test_export_guards_ordinary_writes_and_is_json_serializable(self):
        replay, calendar, protocol = fixture()
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(len(json.loads(json.dumps(out))['panel']['rows']),252)
        with self.assertRaises(TypeError):
            out['panel']['rows'][0]['nav']=7
        with self.assertRaises(TypeError):
            out['probe_args']['net_returns'][0]=7

    def test_nonempty_trades_or_orders_require_ledger_evidence(self):
        for key in ('trades', 'reserved_orders'):
            replay, calendar, protocol = fixture()
            replay['wording'][key] = [dict(decision_id='missing', cash_gain=0)]
            out = export_marked_account_panel(replay, calendar, protocol)
            self.assertEqual(out['panel']['status'], 'insufficient')
            self.assertFalse(out['probe_args']['marks_complete'])
            self.assertTrue(all(r['net_return'] is None for r in out['panel']['rows']))

    def test_unexplained_income_and_trade_gain_mismatch_are_refused(self):
        for action, gain in [('interest', 1), ('exit', 2)]:
            replay, calendar, protocol = fixture()
            day = calendar['rows'][0]
            replay['wording']['ledger'] = [dict(at_utc=day['close_at_utc'], action=action,
                decision_id='t1', equity=1000001., positions={}, collateral=0., restricted_short_proceeds=0.)]
            replay['wording']['trades'] = [dict(decision_id='t1', cash_gain=gain)]
            for mark in replay['marks']: mark['wording_equity'] = 1000001.
            out = export_marked_account_panel(replay, calendar, protocol)
            self.assertEqual(out['panel']['status'], 'insufficient')
            self.assertIsNone(out['panel']['rows'][0]['net_return'])

    def test_extreme_finite_nav_return_overflow_remains_missing(self):
        replay, calendar, protocol = fixture()
        values = [1e-308, 1e308]
        previous = protocol['initial_cash']
        for i, value in enumerate(values):
            day = calendar['rows'][i]
            replay['wording']['ledger'].append(dict(at_utc=day['close_at_utc'], action='exit',
                decision_id=str(i), equity=value, positions={}, collateral=0., restricted_short_proceeds=0.))
            replay['wording']['trades'].append(dict(decision_id=str(i), cash_gain=value-previous))
            previous=value
        replay['marks'][0]['wording_equity']=values[0]
        for mark in replay['marks'][1:]: mark['wording_equity']=values[1]
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(out['panel']['status'],'insufficient')
        self.assertIsNone(out['panel']['rows'][1]['net_return'])
        json.dumps(out,allow_nan=False)

    def test_oversized_integer_nav_and_collateral_are_refused(self):
        replay, calendar, protocol = fixture()
        replay['marks'][0]['wording_equity']=10**400
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(out['panel']['status'],'insufficient')
        replay, calendar, protocol = fixture()
        replay['wording']['ledger']=[dict(at_utc=calendar['rows'][0]['close_at_utc'],action='exit',
            decision_id='t', equity=1000000.,positions={},collateral=10**400,restricted_short_proceeds=0)]
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertEqual(out['panel']['status'],'insufficient')

    def test_non_numeric_nav_and_untagged_synthetic_scope_refused(self):
        replay, calendar, protocol = fixture()
        replay['marks'][0]['wording_equity']='1000000'
        out=export_marked_account_panel(replay,calendar,protocol)
        self.assertIsNone(out['panel']['rows'][0]['nav'])
        self.assertEqual(out['panel']['rows'][0]['reason'],'nonpositive_nav')
        with self.assertRaises(ValueError):
            export_marked_account_panel(replay,calendar,protocol,scope='synthetic_engineering')
