"""Tiny safety fixtures; no fixture output is a market result."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.multi_market.labels import Quote, executable_price


def fixture_panel(n=100):
    rng = np.random.default_rng(23)
    dates = pd.bdate_range('2024-01-02', periods=n)
    marks = []
    for j, root in enumerate(['ES', 'ZN', 'CL', 'GC']):
        prices = 100 + np.cumsum(rng.normal(size=n) + .2 * np.sin(np.arange(n)))
        for date, price in zip(dates, prices):
            marks.append(dict(date=date, root=root, rank=0, instrument_id=j + 1,
                              contract_id=root + 'A', midpoint=price, valid=True,
                              mark_at=pd.Timestamp(date).tz_localize('America/New_York') + pd.Timedelta(hours=9, minutes=36)))
    return pd.DataFrame(marks), dates


class FuturesTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('src.multi_market.futures_study'),
                             'actual-contract futures adapter must exist')
        self.api = importlib.import_module('src.multi_market.futures_study')

    def test_rank_change_compares_same_contract_on_both_sides(self):
        dates = pd.bdate_range('2024-01-02', periods=3)
        marks = pd.DataFrame([
            dict(date=dates[0], root='ES', rank=0, instrument_id=1, contract_id='A', midpoint=100, valid=True),
            dict(date=dates[0], root='ES', rank=1, instrument_id=2, contract_id='B', midpoint=200, valid=True),
            dict(date=dates[1], root='ES', rank=0, instrument_id=2, contract_id='B', midpoint=202, valid=True),
            dict(date=dates[1], root='ES', rank=1, instrument_id=1, contract_id='A', midpoint=101, valid=True),
            dict(date=dates[2], root='ES', rank=0, instrument_id=1, contract_id='A', midpoint=103, valid=True),
            dict(date=dates[2], root='ES', rank=1, instrument_id=2, contract_id='B', midpoint=205, valid=True),
        ])
        got = self.api.build_contract_panel(marks, dates, roots=('ES',))
        middle = got.iloc[1]
        self.assertEqual(middle.innovation_points, 2)
        self.assertEqual(middle.target_points, 3)
        self.assertEqual(middle.contract_id, 'B')
        self.assertEqual(got.iloc[0].target_points, 1)

    def test_missing_fixed_exit_never_skips_forward(self):
        marks, dates = fixture_panel(5)
        marks = marks[~((marks.root == 'CL') & (marks.date == dates[2]))]
        got = self.api.build_contract_panel(marks, dates)
        prior = got[(got.root == 'CL') & (got.date == dates[1])].iloc[0]
        self.assertTrue(np.isnan(prior.target_points))
        self.assertEqual(prior.label_missing_reason, 'missing_same_contract_fixed_exit')
        after = got[(got.root == 'CL') & (got.date == dates[3])].iloc[0]
        self.assertTrue(np.isnan(after.innovation_points))

    def test_fixed_interval_uses_recv_end_and_handles_dst(self):
        timestamps = ['2024-03-08T14:35:00Z', '2024-03-08T14:36:00Z',
                      '2024-03-11T13:36:00Z', '2024-03-11T14:36:00Z']
        raw = pd.DataFrame({'ts_recv': [pd.Timestamp(x).value for x in timestamps],
                            'ts_event': [pd.Timestamp(x).value for x in timestamps],
                            'instrument_id': [1] * 4, 'symbol': ['ES.v.0'] * 4,
                            'bid_px_00': [100000000000] * 4, 'ask_px_00': [102000000000] * 4,
                            'bid_sz_00': [3] * 4, 'ask_sz_00': [4] * 4})
        got = self.api.fixed_interval_rows(raw)
        self.assertEqual(len(got), 2)
        self.assertEqual(got.midpoint.tolist(), [101, 101])
        self.assertEqual(got.mark_at.dt.strftime('%H:%M').tolist(), ['14:36', '13:36'])
        self.assertEqual(got.interval_start.dt.tz_convert('America/New_York').dt.strftime('%H:%M').tolist(), ['09:35', '09:35'])

    def test_features_strictly_lag_entry_and_scale_uses_only_past(self):
        marks, dates = fixture_panel()
        panel = self.api.build_contract_panel(marks, dates)
        first = self.api.build_futures_features(panel, window=10)
        changed = marks.copy()
        changed.loc[changed.date >= dates[70], 'midpoint'] *= 1000
        second = self.api.build_futures_features(self.api.build_contract_panel(changed, dates), window=10)
        columns = self.api.BASELINE_FEATURES + ['residual_peer_shock', 'residual_concentration', 'edge_turnover', 'risk_scale_points']
        a = first[first.date <= dates[70]].reset_index(drop=True)
        b = second[second.date <= dates[70]].reset_index(drop=True)
        pd.testing.assert_frame_equal(a[columns], b[columns])
        row = first[(first.date == dates[70]) & (first.ticker == 'ES')].iloc[0]
        historical = panel[(panel.root == 'ES') & panel.date.between(dates[60], dates[69])].innovation_points
        self.assertAlmostEqual(row.risk_scale_points, historical.std())
        self.assertEqual(row.feature_last_session, dates[69])

    def test_future_append_leaves_earlier_features_unchanged(self):
        marks, dates = fixture_panel()
        before = self.api.build_futures_features(self.api.build_contract_panel(marks[marks.date <= dates[70]], dates[:71]), window=10)
        after = self.api.build_futures_features(self.api.build_contract_panel(marks, dates), window=10)
        columns = self.api.BASELINE_FEATURES + ['residual_peer_shock', 'residual_concentration', 'edge_turnover', 'risk_scale_points']
        pd.testing.assert_frame_equal(before[columns], after[after.date <= dates[70]].reset_index(drop=True)[columns])

    def test_changing_constant_price_units_preserves_model_inputs(self):
        marks, dates = fixture_panel()
        first = self.api.build_futures_features(self.api.build_contract_panel(marks, dates), window=10)
        changed = marks.copy()
        changed.loc[changed.root == 'ZN', 'midpoint'] *= 32
        second = self.api.build_futures_features(self.api.build_contract_panel(changed, dates), window=10)
        columns = self.api.BASELINE_FEATURES + ['residual_peer_shock', 'residual_concentration', 'edge_turnover', 'target']
        np.testing.assert_allclose(first[columns], second[columns], equal_nan=True, atol=1e-10)

    def test_quote_invalid_and_size_gates_reuse_cash_adapter(self):
        now = datetime(2024, 1, 2, 14, 36, tzinfo=timezone.utc)
        quote = Quote('actual-contract', now, now, 101, 100, 5, 5, 'interval_sample')
        self.assertIsNone(executable_price(quote, 'buy', 1, now, 60, allow_sampled_proxy=True))
        thin = Quote('actual-contract', now, now, 99, 100, 1, 0, 'interval_sample')
        self.assertIsNone(executable_price(thin, 'buy', 1, now, 60, allow_sampled_proxy=True))

    def test_declared_streaming_inputs_preserve_identity_without_future_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            jobs = json.loads(Path('data/raw/databento/multi-market-pilot/provider_jobs.json').read_text())
            selected = {'GLBX-20261004-HPJ4GHJME5', 'GLBX-20261004-PGTVBDDMSY',
                        'GLBX-20261004-4AGNVKMCB3', 'GLBX-20261004-UE5HA8BEA9', 'EQUS-20261004-REQKYD4HUY',
                        'EQUS-20261004-QKMVNWHJWT'}
            stamp = pd.Timestamp('2024-01-02T14:36:00Z').value
            for job in jobs:
                if job['id'] not in selected:
                    continue
                folder = directory / job['id']
                folder.mkdir()
                if job['schema'] == 'ohlcv-1d':
                    raw = pd.DataFrame([dict(ts_event=pd.Timestamp(date, tz='UTC').value,
                                             instrument_id=15144, symbol='SPY', close=100000000000)
                                        for date in ['2024-01-02', '2024-01-03', '2024-01-04']])
                elif job['schema'] == 'bbo-1m':
                    alias = 'SPY' if job['dataset'] == 'EQUS.MINI' else ('ES.v.0' if 'HPJ4' in job['id'] else 'ES.v.1')
                    raw = pd.DataFrame([dict(ts_recv=stamp, ts_event=18446744073709551615,
                         instrument_id=1 if alias != 'ES.v.1' else 2, symbol=alias,
                         bid_px_00=100000000000, ask_px_00=102000000000,
                         bid_sz_00=1, ask_sz_00=1),
                         dict(ts_recv=stamp + 60_000_000_000, ts_event=18446744073709551615,
                         instrument_id=1, symbol=alias, bid_px_00=1, ask_px_00=2, bid_sz_00=1, ask_sz_00=1)])
                    if alias != 'ES.v.1':
                        raw = pd.concat([raw, pd.DataFrame([dict(ts_recv=stamp + 2 * 86400_000_000_000,
                            ts_event=18446744073709551615, instrument_id=1, symbol=alias,
                            bid_px_00=200000000000, ask_px_00=202000000000, bid_sz_00=2, ask_sz_00=2)])], ignore_index=True)
                else:
                    raw = pd.DataFrame([dict(instrument_id=1 if '4AGN' in job['id'] else 2,
                          raw_symbol='ESH4' if '4AGN' in job['id'] else 'ESM4',
                          ts_recv=stamp - 60_000_000_000 if '4AGN' in job['id'] else stamp + 60_000_000_000,
                          contract_multiplier=2147483647, unit_of_measure_qty=50000000000)])
                raw.to_csv(folder / 'fixture.csv', index=False)
            # An undeclared directory is deliberately malformed and must never
            # be read merely because it is under the supplied raw root.
            extra = directory / 'undeclared'
            extra.mkdir()
            (extra / 'bad.csv').write_text('not a declared market job')
            jobs_path = directory / 'jobs.json'
            jobs_path.write_text(json.dumps(jobs))
            marks, definitions, calendar, manifest = self.api.load_sampled_marks(directory, jobs_path, chunk_rows=1)
            front = marks[marks['rank'].eq(0)].iloc[0]
            back = marks[marks['rank'].eq(1)].iloc[0]
            self.assertEqual(front.contract_id, 'ESH4')
            self.assertTrue(pd.isna(back.contract_id))
            self.assertEqual(list(pd.to_datetime(calendar)), list(pd.date_range('2024-01-02', periods=3)))
            self.assertEqual(len(manifest['input_files']), 6)
            built = self.api.build_contract_panel(marks, calendar, roots=('ES',))
            self.assertTrue(pd.isna(built.iloc[0].target_points))
            self.assertEqual(built.iloc[0].label_missing_reason, 'missing_same_contract_fixed_exit')
            self.assertEqual(manifest['spy_fixed_interval_audit'][1]['missing_reason'], 'missing_SPY_fixed_interval')
            self.assertEqual(definitions.contract_multiplier.tolist(), [2147483647, 2147483647])
            self.assertEqual(front.midpoint, 101)
            report = self.api.run_study(directory, jobs_path, directory / 'fixture-output')
            self.assertEqual(set(report['roots']), {'ES', 'ZN', 'CL', 'GC'})
            self.assertTrue(all(r['status'] == 'blocked' for r in report['roots'].values()))
            self.assertFalse(report['MES_implementation_diagnostic']['independent_alpha_cell'])
            self.assertEqual(report['economic_roles']['status'], 'blocked')
            saved = json.loads((directory / 'fixture-output' / 'study_report.json').read_text())
            self.assertEqual(saved['roots']['CL']['contract_coverage']['valid_exact_contract_labels'], 0)
            self.assertEqual([r['sha256'] for r in report['provenance']['input_files']],
                             [r['sha256'] for r in manifest['input_files']])

    def test_invalid_samples_are_retained_and_never_supply_labels(self):
        stamp = pd.Timestamp('2024-01-02T14:36:00Z').value
        raw = pd.DataFrame([dict(ts_recv=stamp, instrument_id=1, symbol='ES.v.0',
                   bid_px_00=102000000000, ask_px_00=100000000000, bid_sz_00=2, ask_sz_00=2),
                   dict(ts_recv=stamp, instrument_id=2, symbol='ES.v.1',
                   bid_px_00=99000000000, ask_px_00=100000000000, bid_sz_00=2, ask_sz_00=0)])
        got = self.api.fixed_interval_rows(raw)
        self.assertEqual(got.valid.tolist(), [False, False])
        self.assertTrue(got.quote_missing_reason.str.len().gt(0).all())


if __name__ == '__main__':
    unittest.main()
