"""Small synthetic clock fixtures; these are not market results."""
import unittest
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from src.contextual_lattice.context import build_context
from scripts.contextual_lattice.build_context import main


def feature_panel(n=9):
    dates = pd.bdate_range('2024-01-02', periods=n)
    rows = []
    for i, day in enumerate(dates):
        for ticker, own, peer in [('AAA', [0, .01, .02, .01, .01, .015, -.08, .01, .01][i], .01),
                                  ('BBB', .01, .01)]:
            rows.append(dict(date=day, ticker=ticker, return_1d=own,
                             volatility=.02, beta=0., market_return=.01,
                             residual_peer_shock=peer / .02,
                             target=.001, label_available_at=day + pd.Timedelta(days=1)))
    return pd.DataFrame(rows)


class ContextTests(unittest.TestCase):
    def test_all_opportunities_and_labels_survive_even_when_future_filing_is_appended(self):
        features = feature_panel()
        coverage = pd.DataFrame([{'ticker': 'AAA', 'status': 'complete'},
                                 {'ticker': 'BBB', 'status': 'complete'}])
        past = pd.DataFrame([{'ticker': 'AAA', 'form': '8-K', 'filing_date': '2024-01-04',
                              'acceptance_datetime': '2024-01-04T15:00:00-05:00', 'accession': 'old'}])
        future = pd.DataFrame([{'ticker': 'AAA', 'form': '8-K', 'filing_date': '2024-01-12',
                                'acceptance_datetime': '2024-01-12T15:00:00-05:00', 'accession': 'future'}])
        before = build_context(features, filings=past, coverage=coverage, window=3)
        after = build_context(features, filings=pd.concat([past, future]), coverage=coverage, window=3)
        self.assertEqual(len(before), len(features))
        pd.testing.assert_frame_equal(before[before.date < '2024-01-12'].reset_index(drop=True),
                                      after[after.date < '2024-01-12'].reset_index(drop=True))
        pd.testing.assert_series_equal(before.target, features.target)

    def test_appending_future_price_rows_does_not_change_prior_context(self):
        features = feature_panel()
        past = features[features.date <= pd.Timestamp('2024-01-09')].reset_index(drop=True)
        before = build_context(past, window=3)
        after = build_context(features, window=3)
        pd.testing.assert_frame_equal(before,
            after[after.date <= pd.Timestamp('2024-01-09')].reset_index(drop=True))

    def test_acceptance_after_close_is_not_known_until_next_decision(self):
        features = feature_panel(3)
        filing = pd.DataFrame([{'ticker': 'AAA', 'form': '8-K', 'filing_date': '2024-01-03',
                                'acceptance_datetime': '2024-01-03T16:01:00-05:00', 'accession': 'one'}])
        coverage = pd.DataFrame([{'ticker': 'AAA', 'status': 'complete'}])
        got = build_context(features, filings=filing, coverage=coverage, window=3)
        aaa = got[got.ticker.eq('AAA')].reset_index(drop=True)
        self.assertFalse(aaa.loc[1, 'known_8k'])
        self.assertTrue(aaa.loc[2, 'known_8k'])
        self.assertEqual(aaa.loc[2, 'filing_clock_quality'], 'acceptance_timestamp_next_calendar_day_proxy')

    def test_date_only_filing_is_approximate_and_next_calendar_day_available(self):
        filing = pd.DataFrame([{'ticker': 'AAA', 'form': '8-K/A',
                                'filing_date': '2024-01-03', 'accession': 'one'}])
        coverage = pd.DataFrame([{'ticker': 'AAA', 'status': 'complete'}])
        got = build_context(feature_panel(3), filings=filing, coverage=coverage, window=3)
        aaa = got[got.ticker.eq('AAA')].reset_index(drop=True)
        self.assertFalse(aaa.loc[1, 'known_8k'])
        self.assertTrue(aaa.loc[2, 'known_8k'])
        self.assertEqual(aaa.loc[2, 'filing_clock_quality'], 'date_only_next_calendar_day_proxy')

    def test_missing_monitoring_is_unknown_even_if_filings_are_empty(self):
        got = build_context(feature_panel(3), window=3)
        self.assertTrue(got.known_8k.isna().all())
        self.assertTrue(got.filing_context_available.eq(False).all())
        self.assertTrue(got.filing_monitoring_status.eq('unknown').all())
        self.assertTrue(got.filing_context_abstain.all())
        self.assertTrue(got.filing_abstention_reason.eq('filing_monitoring_unknown').all())

    def test_reversal_event_uses_prior_gap_scale_and_current_gap(self):
        coverage = pd.DataFrame([{'ticker': 'AAA', 'status': 'complete'},
                                 {'ticker': 'BBB', 'status': 'complete'}])
        got = build_context(feature_panel(), filings=pd.DataFrame(), coverage=coverage, window=3)
        shock = got[(got.ticker == 'AAA') & (got.date == pd.Timestamp('2024-01-10'))].iloc[0]
        self.assertTrue(shock.reversal_event)
        self.assertLess(shock.peer_reaction_gap, 0)
        self.assertGreaterEqual(abs(shock.peer_reaction_gap), 2 * shock.peer_gap_prior_std)
        self.assertFalse(got.loc[(got.ticker == 'AAA') & (got.date < '2024-01-05'), 'reversal_event'].any())

    def test_catchup_requires_qualified_link_and_prior_available_source_shock(self):
        dates = pd.bdate_range('2024-01-02', periods=76)
        shock = np.sin(np.arange(len(dates)) * .7) + .3 * np.cos(np.arange(len(dates)) * .13)
        shock[-2] = 9.
        features = pd.DataFrame([dict(date=day, ticker='AAA',
                                      return_1d=.004 * (shock[i - 1] if i else 0),
                                      volatility=.02, beta=0., market_return=.001,
                                      residual_peer_shock=0., target=.001,
                                      label_available_at=day + pd.Timedelta(days=1))
                                 for i, day in enumerate(dates)])
        sources = pd.DataFrame([dict(date=day, ticker='CL', shock=value,
                                     available_at=day + pd.Timedelta(hours=9, minutes=36))
                                for day, value in zip(dates, shock)])
        links = pd.DataFrame([{'source_ticker': 'CL', 'target_ticker': 'AAA', 'sign': 1,
                               'effective_from': '2023-01-01', 'effective_to': '2025-01-01',
                               'public_at': '2023-05-01T12:00:00-04:00',
                               'source_url': 'https://example.org/filing', 'sha256': 'a' * 64}])
        got = build_context(features, source_shocks=sources, links=links, window=63)
        row = got[(got.ticker == 'AAA') & (got.date == dates[-1])].iloc[0]
        self.assertEqual(row.source_shock_proxy, 9.)
        self.assertEqual(row.catchup_eligibility, 'price_proxy_exploratory')
        self.assertEqual(row.catchup_reason, 'actual_news_surprise_unavailable')
        self.assertTrue(row.source_price_proxy_event)
        self.assertGreater(row.prior_source_relationship, .2)
        self.assertEqual(row.source_shock_date, dates[-2])
        self.assertLessEqual(row.source_shock_available_at, row.decision_at)
        self.assertLessEqual(row.economic_link_public_at, row.decision_at)
        no_link = build_context(features, source_shocks=sources, window=63)
        self.assertTrue(no_link.catchup_eligibility.eq('blocked').all())

    def test_supplied_futures_decision_clock_is_respected(self):
        features = feature_panel(3)
        features['decision_at'] = features.date + pd.Timedelta(hours=9, minutes=30)
        filing = pd.DataFrame([{'ticker': 'AAA', 'form': '8-K', 'filing_date': '2024-01-03',
                                'acceptance_datetime': '2024-01-03T10:00:00-05:00'}])
        coverage = pd.DataFrame([{'ticker': 'AAA', 'status': 'complete'}])
        got = build_context(features, filings=filing, coverage=coverage, window=3)
        self.assertFalse(got[(got.ticker == 'AAA') & (got.date == pd.Timestamp('2024-01-03'))].known_8k.iloc[0])

    def test_futures_feature_packet_is_already_prior_session_normalized(self):
        features = feature_panel(5).query("ticker == 'AAA'").copy()
        features['root'] = 'ES'
        features['return_1d'] = [1., 2., 1.5, 2.5, 2.]
        features['beta'] = .5
        features['market_return'] = 1.
        features['residual_peer_shock'] = .25
        features['volatility'] = 3.  # ratio of risk scales, not a return denominator
        got = build_context(features, window=3)
        expected = 1.5 / np.std([1.5, 1., 2.], ddof=1) - .25
        self.assertAlmostEqual(got.peer_reaction_gap.iloc[-1], expected)
        self.assertEqual(got.lagged_market_shock.iloc[-1], 1.)
        self.assertEqual(got.context_units.iloc[-1], 'futures_prior_residual_scale_approximation')

    def test_equity_gap_is_invariant_to_common_return_unit_rescaling(self):
        features = feature_panel()
        original = build_context(features, window=3)
        scaled = features.copy()
        for name in ['return_1d', 'volatility', 'market_return']:
            scaled[name] *= 100
        changed = build_context(scaled, window=3)
        pd.testing.assert_series_equal(original.peer_reaction_gap, changed.peer_reaction_gap)
        pd.testing.assert_series_equal(original.reversal_event, changed.reversal_event)

    def test_cli_writes_audited_all_row_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            features = root / 'features.parquet'
            feature_panel(5).to_parquet(features, index=False)
            output = root / 'result'
            self.assertEqual(main(['--features', str(features), '--output', str(output), '--window', '3']), 0)
            actual = pd.read_parquet(output / 'context.parquet')
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(len(actual), 10)
            self.assertEqual(manifest['status'], 'price_proxy_exploratory_actual_news_blocked')
            self.assertEqual(manifest['rows'], 10)
            self.assertTrue(actual.known_8k.isna().all())


if __name__ == '__main__':
    unittest.main()
