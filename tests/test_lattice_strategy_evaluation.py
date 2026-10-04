import unittest
import numpy as np
import pandas as pd
from src.lattice_strategies.evaluation import summarize_forecasts, paired_interval, residual_cost_sensitivity


class EvaluationTests(unittest.TestCase):
    def rows(self):
        rows = []
        for date in pd.bdate_range('2024-01-01', periods=4):
            for ticker in ['A', 'B']:
                for model, prediction in [('zero', 0.), ('mst_peer_state', .1)]:
                    rows.append(dict(date=date, ticker=ticker, model=model,
                                     horizon=1, forecast=prediction, outcome=.1,
                                     status='ok', reason=''))
        return pd.DataFrame(rows)

    def test_matched_same_target_and_date_cluster_loss(self):
        report = summarize_forecasts(self.rows(), repetitions=30, block=2, seed=1)
        first = report['horizons']['1']
        self.assertEqual(first['common_opportunities'], 8)
        self.assertAlmostEqual(first['models']['zero']['mse'], .01)
        self.assertAlmostEqual(first['models']['mst_peer_state']['mse'], 0.)
        self.assertEqual(first['paired_graph_comparisons']['zero']['cluster_dates'], 4)

    def test_different_targets_rejected(self):
        rows = self.rows()
        rows.loc[0, 'outcome'] = .2
        with self.assertRaises(ValueError):
            summarize_forecasts(rows)

    def test_constant_paired_loss_has_exact_interval(self):
        losses = pd.DataFrame({'tree': [1.]*8, 'sample': [2.]*8},
                              index=pd.bdate_range('2024-01-01', periods=8))
        result = paired_interval(losses, 'tree', 'sample', repetitions=40, block=3, seed=1)
        self.assertEqual(result['improvement'], 1.)
        self.assertEqual(result['interval_95'], [1., 1.])

    def test_incomplete_candidate_is_not_scored_against_extra_rows(self):
        rows = self.rows()
        rows.loc[rows.model.eq('mst_peer_state') & rows.ticker.eq('B'), 'outcome'] = np.nan
        report = summarize_forecasts(rows, repetitions=20, block=2)
        self.assertEqual(report['horizons']['1']['common_opportunities'], 4)

    def test_costs_charge_both_sides_of_gross_normalized_hedge(self):
        rows = self.rows().iloc[:2].copy()
        rows['hedge_weights'] = [{'A': 1., 'B': -2.} for _ in range(2)]
        rows['hedge_outcome'] = .03
        result = residual_cost_sensitivity(rows, [10.]).set_index('model')
        self.assertAlmostEqual(result.loc['mst_peer_state', 'gross_mark_return'], .01)
        self.assertAlmostEqual(result.loc['mst_peer_state', 'round_trip_cost'], .002)
        self.assertAlmostEqual(result.loc['mst_peer_state', 'net_mark_proxy'], .008)
        self.assertEqual(result.loc['zero', 'net_mark_proxy'], 0.)


if __name__ == '__main__':
    unittest.main()
