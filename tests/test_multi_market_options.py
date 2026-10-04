"""Offline fixtures test causal matching and dependent-row handling only."""
import importlib.util
from pathlib import Path
import unittest

import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / 'scripts/multi_market/run_options_matched_study.py'


class MatchedOptionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MODULE.exists():
            cls.study = None
        else:
            spec = importlib.util.spec_from_file_location('matched_options', MODULE)
            cls.study = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.study)

    def require_module(self):
        self.assertIsNotNone(self.study, 'matched diagnostic is not implemented')

    def test_only_exact_pre_view_b_fixed_estimator_matches(self):
        self.require_module()
        events = pd.DataFrame([dict(event_id='e', ticker='ABC', t_pre='2024-01-05')])
        scores = pd.DataFrame([
            dict(date=d, ticker='ABC', view=v, estimator=est, depth=x, pvalue=.2, inside=True)
            for d, v, est, x in [('2024-01-09','B','mahalanobis',999),
                ('2024-01-05','A','mahalanobis',999), ('2024-01-05','B','kde',999),
                ('2024-01-05','B','mahalanobis',1.5)]])
        matched = self.study.match_scores(events, scores)
        self.assertEqual(matched.iloc[0].score_depth, 1.5)
        absent = self.study.match_scores(events, scores.iloc[:3])
        self.assertFalse(absent.iloc[0].score_present)

    def test_expiry_and_otm_rows_collapse_to_one_event_strategy(self):
        self.require_module()
        rows = pd.DataFrame([dict(event_id='e', ticker='ABC', t_pre='2024-01-05',
            strategy='long_call', bucket=b, otm=o, outcome=y, paired_stock=.1,
            score_depth=1.5, score_pvalue=.2, score_present=True, primary_eligible=True,
            mark_grade='fresh_last_trade', quote_valid=True, quote_size_eligible=True)
            for b, o, y in [('1m', .03, .2), ('1m', .05, .2), ('3m', .03, .4)]])
        groups = self.study.collapse_groups(rows, 'primary_eligible')
        self.assertEqual(len(groups), 1)
        self.assertAlmostEqual(groups.iloc[0].outcome, .3)
        self.assertEqual(groups.iloc[0].expiry_buckets, 2)

    def test_sparse_events_report_inconclusive(self):
        self.require_module()
        groups = pd.DataFrame([dict(event_id=f'e{i}', ticker='ABC', score_depth=i,
            outcome=i / 100, excess_vs_stock=i / 200) for i in range(6)])
        result = self.study.association(groups)
        self.assertEqual(result['status'], 'inconclusive')
        self.assertIn('insufficient_independent_events', result['reasons'])
        self.assertNotIn('correlation', result)

    def test_stale_and_missing_bars_cannot_grade_fresh(self):
        self.require_module()
        bars = pd.DataFrame([dict(contract_ticker='C', session='2024-01-04', close=2., volume=3),
                             dict(contract_ticker='C', session='2024-01-09', close=999., volume=3)])
        grade, age = self.study.grade_marks(bars, ['C'], ['2024-01-05'])
        self.assertEqual(grade, 'stale_last_trade')
        self.assertEqual(age, 1)
        self.assertEqual(self.study.grade_marks(bars, ['X'], ['2024-01-05'])[0], 'missing_last_trade')
        # MLK closure does not add an age session.
        holiday = pd.DataFrame([dict(contract_ticker='C', session='2024-01-12', close=2.)])
        self.assertEqual(self.study.grade_marks(holiday, ['C'], ['2024-01-16'])[1], 1)

    def test_quote_mid_changes_use_one_session_post_entry_and_pair_stock(self):
        self.require_module()
        events = pd.DataFrame([dict(event_id='e', ticker='ABC', t_pre='2024-01-05',
            event_date='2024-01-08', t_0='2024-01-09', score_present=True,
            score_depth=1.5, score_pvalue=.2)])
        legs = pd.DataFrame([dict(event_id='e', bucket='1m', leg_code=code,
            contract_ticker=code, selection_date='2024-01-05', expiration_date='2024-02-16',
            spot_pre=100., strike=100.) for code in ['C_K', 'P_K', 'C_U0.03', 'P_L0.03']])
        quotes, bars = [], []
        for day in ['2024-01-05', '2024-01-09', '2024-01-10']:
            for code in legs.leg_code:
                mid = 5. if code == 'C_K' and day == '2024-01-10' else 4.
                quotes.append(dict(contract_ticker=code, session=day,
                    mark_time_utc=day+'T21:00:00Z', bid=mid-.1, ask=mid+.1, mid=mid,
                    bid_size=2., ask_size=3., minutes_before_1600=0.))
                bars.append(dict(contract_ticker=code, session=day, close=mid, volume=1.))
        source = dict(event_id='e', bucket='1m', entry='post', entry_date='2024-01-09',
            horizon='1', sessions_held=1., exit_date='2024-01-10', otm=.03,
            stock=.01, long_call=.01, covered_call=.01, protective_put=.01,
            collar=.01, cash_secured_put=0.)
        longer = {**source, 'entry': 'pre', 'entry_date': '2024-01-05', 'sessions_held': 3.}
        rows = self.study.build_rows(events, legs, pd.DataFrame(bars), pd.DataFrame(quotes),
                                     pd.DataFrame([source, longer]))
        self.assertEqual(len(rows), 6)
        call = rows[rows.strategy == 'long_call'].iloc[0]
        self.assertTrue(call.primary_eligible)
        self.assertAlmostEqual(call.outcome, .01)
        self.assertAlmostEqual(call.paired_stock, .01)
        self.assertEqual(call.entry_date, '2024-01-09')
        crossed = pd.DataFrame(quotes)
        crossed.loc[crossed.session == '2024-01-10', 'bid'] = 100.
        invalid = self.study.build_rows(events, legs, pd.DataFrame(bars), crossed, pd.DataFrame([source]))
        self.assertFalse(invalid.primary_eligible.any())

    def test_duplicate_exact_scores_fail_closed(self):
        self.require_module()
        events = pd.DataFrame([dict(event_id='e', ticker='ABC', t_pre='2024-01-05')])
        score = dict(date='2024-01-05', ticker='ABC', view='B', estimator='mahalanobis',
                     depth=1., pvalue=.1, inside=True)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.study.match_scores(events, pd.DataFrame([score, score]))


if __name__ == '__main__':
    unittest.main()
