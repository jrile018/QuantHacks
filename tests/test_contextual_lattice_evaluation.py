"""Decision-time and paired-cohort checks for the contextual study."""
import unittest

import numpy as np
import pandas as pd

from src.contextual_lattice.evaluation import evaluate_contextual_hypothesis


def fixture():
    dates = pd.bdate_range('2020-01-01', periods=75)
    frame = pd.DataFrame({'date': np.repeat(dates, 2), 'ticker': ['A', 'B'] * len(dates)})
    frame['decision_at'] = frame.date + pd.Timedelta(hours=21)
    frame['label_available_at'] = frame.date + pd.Timedelta(days=1, hours=23)
    frame['next_date'] = frame.date + pd.Timedelta(days=1)
    frame['feature_available_at'] = frame.date + pd.Timedelta(hours=20)
    frame['context_available_at'] = frame.date + pd.Timedelta(hours=19)
    frame['context_qualified'] = True
    rng = np.random.default_rng(12)
    frame['ordinary'] = rng.normal(size=len(frame))
    frame['source_shock_exposure'] = rng.normal(size=len(frame))
    frame['lattice_interaction'] = frame.source_shock_exposure * rng.uniform(.2, 1, len(frame))
    frame['target_return'] = .02 * frame.ordinary + .03 * frame.source_shock_exposure + rng.normal(0, .02, len(frame))
    frame['volatility'] = .02
    frame['source_version'] = 'synthetic-v1'
    frame['target_units'] = 'fractional_adjusted_close_change'
    return frame, dates


def run(frame, dates):
    return evaluate_contextual_hypothesis(frame, hypothesis='catchup',
        baseline_columns=['ordinary'], context_columns=['source_shock_exposure'],
        interaction_columns=['lattice_interaction'], train_start=dates[0],
        holdout_start=dates[55], holdout_end=dates[69],
        bootstrap_repetitions=25, block_sessions=3)


class ContextualEvaluationTests(unittest.TestCase):
    def test_late_and_unqualified_context_abstains_without_discarding_opportunities(self):
        frame, dates = fixture()
        late = (frame.date == dates[60]) & frame.ticker.eq('A')
        unknown = (frame.date == dates[61]) & frame.ticker.eq('B')
        frame.loc[late, 'context_available_at'] = frame.loc[late, 'decision_at'] + pd.Timedelta(seconds=1)
        frame.loc[unknown, 'context_qualified'] = False
        result = run(frame, dates)
        self.assertEqual(len(result.decisions), 30)
        self.assertEqual(len(result.predictions), 28)
        self.assertEqual(set(result.decisions.loc[~result.decisions.eligible, 'abstention_reason']),
                         {'context_after_decision', 'context_unqualified'})
        self.assertEqual(result.report['coverage']['holdout_opportunities'], 30)
        self.assertEqual(result.report['coverage']['qualified_decisions'], 28)
        self.assertEqual(result.report['metrics']['context_only']['rows'], 28)
        self.assertEqual(result.report['metrics']['context_lattice']['rows'], 28)

    def test_future_targets_and_late_training_labels_cannot_change_forecasts(self):
        frame, dates = fixture()
        changed = frame.copy()
        changed.loc[changed.date >= dates[55], 'target_return'] += 100
        changed.loc[changed.date == dates[53], 'target_return'] -= 100
        changed.loc[changed.date == dates[53], 'label_available_at'] = dates[57]
        prior = frame.copy()
        prior.loc[prior.date == dates[53], 'label_available_at'] = dates[57]
        reference = run(prior, dates)
        again = run(changed, dates)
        np.testing.assert_allclose(reference.predictions.context_lattice, again.predictions.context_lattice)

    def test_appending_later_calendar_rows_cannot_change_frozen_holdout(self):
        frame, dates = fixture()
        truncated = run(frame.loc[frame.date <= dates[69]], dates)
        extended = run(frame, dates)
        pd.testing.assert_frame_equal(truncated.predictions, extended.predictions)
        pd.testing.assert_frame_equal(truncated.ledger, extended.ledger)

    def test_shuffled_input_preserves_target_alignment_by_date_and_ticker(self):
        frame, dates = fixture()
        ordered = run(frame, dates)
        shuffled = run(frame.sample(frac=1, random_state=44).reset_index(drop=True), dates)
        pd.testing.assert_frame_equal(ordered.predictions, shuffled.predictions)
        pd.testing.assert_frame_equal(ordered.ledger, shuffled.ledger)

    def test_geometry_only_control_uses_same_cohort_without_context_columns(self):
        frame, dates = fixture()
        frame['geometry_signal'] = frame.lattice_interaction * .5
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'geometry_signal'] = np.nan
        result = evaluate_contextual_hypothesis(frame, hypothesis='catchup',
            baseline_columns=['ordinary'], context_columns=['source_shock_exposure'],
            interaction_columns=['lattice_interaction'], lattice_columns=['geometry_signal'],
            train_start=dates[0], holdout_start=dates[55], holdout_end=dates[69],
            bootstrap_repetitions=25, block_sessions=3)
        self.assertEqual(len(result.predictions), 29)
        self.assertEqual(result.report['metrics']['lattice_only']['rows'], 29)
        self.assertEqual(result.report['metrics']['context_lattice']['rows'], 29)
        self.assertEqual(result.report['fits']['lattice_only']['features'], ['ordinary', 'geometry_signal'])
        self.assertIn('lattice_only', result.report['paired_comparisons']['context_lattice'])
        self.assertEqual(len(result.ledger), 15 * 2 * 6)
        self.assertEqual(result.decisions.loc[
            (result.decisions.date == dates[65]) & result.decisions.ticker.eq('A'),
            'abstention_reason'].iloc[0], 'nonfinite_lattice_only')
        with self.assertRaisesRegex(ValueError, 'disjoint'):
            evaluate_contextual_hypothesis(frame, hypothesis='catchup',
                baseline_columns=['ordinary'], context_columns=['source_shock_exposure'],
                interaction_columns=['lattice_interaction'], lattice_columns=['source_shock_exposure'],
                train_start=dates[0], holdout_start=dates[55], holdout_end=dates[69])

    def test_source_version_must_be_populated_for_every_attempt(self):
        frame, dates = fixture()
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'source_version'] = None
        with self.assertRaisesRegex(ValueError, 'source_version'):
            run(frame, dates)

    def test_next_session_clock_must_follow_decision_date(self):
        frame, dates = fixture()
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'next_date'] = dates[65]
        with self.assertRaisesRegex(ValueError, 'next_date'):
            run(frame, dates)

    def test_terminal_unobserved_row_after_holdout_cannot_change_frozen_forecasts(self):
        frame, dates = fixture()
        terminal = (frame.date == dates[-1]) & frame.ticker.eq('A')
        frame.loc[terminal, ['target_return', 'next_date', 'label_available_at']] = pd.NA
        without_terminal = run(frame.loc[frame.date <= dates[69]], dates)
        with_terminal = run(frame, dates)
        pd.testing.assert_frame_equal(without_terminal.predictions, with_terminal.predictions)
        pd.testing.assert_frame_equal(without_terminal.ledger, with_terminal.ledger)

    def test_unobserved_holdout_opportunity_remains_abstained_in_ledger(self):
        frame, dates = fixture()
        missing = (frame.date == dates[65]) & frame.ticker.eq('A')
        frame.loc[missing, ['target_return', 'next_date', 'label_available_at']] = pd.NA
        result = run(frame, dates)
        row = result.decisions.loc[
            (result.decisions.date == dates[65]) & result.decisions.ticker.eq('A')].iloc[0]
        self.assertFalse(row.outcome_observed)
        self.assertFalse(row.eligible)
        self.assertEqual(row.abstention_reason, 'outcome_unobserved')
        attempted = result.ledger.loc[(result.ledger.date == dates[65]) & result.ledger.ticker.eq('A')]
        self.assertEqual(len(attempted), 5)
        self.assertEqual(set(attempted.status), {'abstain'})
        self.assertEqual(set(attempted.trade_status), {'no_trade'})
        self.assertTrue(attempted.prediction.isna().all())

    def test_common_cohort_and_all_controls_are_reported(self):
        frame, dates = fixture()
        frame.loc[(frame.date == dates[64]) & frame.ticker.eq('A'), 'lattice_interaction'] = np.nan
        result = run(frame, dates)
        self.assertEqual(len(result.predictions), 29)
        self.assertTrue({'baseline', 'context_only', 'context_lattice', 'zero',
                         'simple_substitute'} <= set(result.report['metrics']))
        self.assertEqual(result.report['paired_comparisons']['context_lattice']['context_only']['calendar_sessions'], 15)
        self.assertIn('exposure_matched_cash_control', result.report['risk_filter'])
        self.assertEqual(result.report['status'], 'exploratory')
        self.assertEqual(result.report['direct_signal']['economic_status'], 'blocked')

    def test_missing_context_never_becomes_a_known_zero(self):
        frame, dates = fixture()
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'source_shock_exposure'] = np.nan
        result = run(frame, dates)
        row = result.decisions.loc[(result.decisions.date == dates[65]) & result.decisions.ticker.eq('A')].iloc[0]
        self.assertFalse(row.eligible)
        self.assertEqual(row.abstention_reason, 'nonfinite_context')
        self.assertTrue(pd.isna(row.context_lattice))

    def test_unknown_qualification_abstains_without_crashing(self):
        frame, dates = fixture()
        frame['context_qualified'] = frame.context_qualified.astype('boolean')
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'context_qualified'] = pd.NA
        result = run(frame, dates)
        row = result.decisions.loc[(result.decisions.date == dates[65]) & result.decisions.ticker.eq('A')].iloc[0]
        self.assertEqual(row.abstention_reason, 'context_unqualified')
        self.assertFalse(row.eligible)

    def test_movement_is_separate_absolute_target_with_history_baseline(self):
        frame, dates = fixture()
        with self.assertRaisesRegex(ValueError, 'historical_abs_return_mean'):
            evaluate_contextual_hypothesis(frame, hypothesis='movement',
                baseline_columns=['ordinary', 'volatility'], context_columns=['source_shock_exposure'],
                interaction_columns=['lattice_interaction'], train_start=dates[0],
                holdout_start=dates[55], holdout_end=dates[69])
        frame['historical_abs_return_mean'] = .02
        result = evaluate_contextual_hypothesis(frame, hypothesis='movement',
            baseline_columns=['ordinary', 'volatility', 'historical_abs_return_mean'],
            context_columns=['source_shock_exposure'], interaction_columns=['lattice_interaction'],
            train_start=dates[0], holdout_start=dates[55], holdout_end=dates[69],
            bootstrap_repetitions=25)
        self.assertGreaterEqual(result.predictions.target.min(), 0)
        self.assertEqual(result.report['specification']['target'], 'absolute_next_session_mark_change')
        self.assertNotIn('uncosted_direction_mark_increment', result.report['direct_signal'])
        self.assertIsNone(result.report['metrics']['context_lattice']['direction_accuracy'])
        self.assertEqual(set(result.decisions.trade_status), {'no_trade'})
        self.assertEqual(set(result.decisions.trade_abstention_reason), {'movement_has_no_direction'})

    def test_candidate_ledger_tracks_every_attempt_and_source_version(self):
        frame, dates = fixture()
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'context_qualified'] = False
        result = run(frame, dates)
        self.assertEqual(len(result.ledger), 150)
        self.assertEqual(set(result.ledger.candidate),
                         {'baseline', 'context_only', 'context_lattice', 'zero', 'simple_substitute'})
        self.assertTrue(result.ledger.source_version.eq('synthetic-v1').all())
        self.assertTrue(result.ledger.target_units.eq('fractional_adjusted_close_change').all())
        self.assertTrue({'next_date', 'label_available_at', 'feature_available_at',
                         'context_available_at'} <= set(result.ledger))
        declined = result.ledger.loc[(result.ledger.date == dates[65]) & result.ledger.ticker.eq('A')]
        self.assertEqual(set(declined.status), {'abstain'})
        self.assertTrue(declined.outcome_observed.all())
        self.assertTrue(declined.prediction.isna().all())
        self.assertEqual(set(declined.abstention_reason), {'context_unqualified'})
        self.assertTrue(result.ledger.cost_limitations.notna().all())

    def test_direction_conflict_keeps_forecast_but_abstains_from_mark_policy(self):
        frame, dates = fixture()
        frame['target_return'] += .2 * frame.lattice_interaction
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'source_shock_exposure'] = 10.
        frame.loc[(frame.date == dates[65]) & frame.ticker.eq('A'), 'lattice_interaction'] = -100.
        result = run(frame, dates)
        conflict = result.decisions.loc[
            result.decisions.eligible &
            (np.sign(result.decisions.context_only) != np.sign(result.decisions.context_lattice))]
        self.assertGreater(len(conflict), 0)
        self.assertTrue(conflict.context_lattice.notna().all())
        self.assertTrue(conflict.exposure_prediction.eq(0).all())
        self.assertEqual(set(conflict.trade_abstention_reason), {'direction_conflict'})
        self.assertEqual(set(conflict.trade_status), {'no_trade'})
        self.assertEqual(result.report['coverage']['forecast_qualified_decisions'], 30)
        self.assertEqual(result.report['coverage']['mark_no_trade_direction_conflict'], len(conflict))
        self.assertEqual(result.report['coverage']['observed_direction_conflict_no_trade_rows'], len(conflict))
        self.assertAlmostEqual(result.report['coverage']['mean_absolute_target_on_direction_conflict'],
                               conflict.target.abs().mean())


if __name__ == '__main__':
    unittest.main()
