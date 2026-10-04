"""Small, deterministic checks for past-only lattice residual forecasts."""

import unittest

import numpy as np
import pandas as pd

from src.lattice_strategies.residuals import build_residual_forecasts


def _returns(days=210):
    rng = np.random.default_rng(42)
    common = rng.normal(0, 0.012, days)
    noise = rng.normal(0, 0.006, (days, 4))
    values = common[:, None] * np.array([1.0, 0.8, 1.2, -0.5]) + noise
    return pd.DataFrame(values, index=pd.date_range("2024-01-01", periods=days, freq="B"), columns=list("ABCD"))


class ResidualForecastTests(unittest.TestCase):
    def test_dense_rows_share_raw_additive_outcome_and_fixed_cutoffs(self):
        returns = _returns()
        date = returns.index[185]
        frame = build_residual_forecasts(returns, diagnostic_start=date, diagnostic_end=date)
        self.assertEqual(len(frame), 4 * 7 * 3)
        self.assertEqual(set(frame.model), {
            "zero", "historical_mean", "own_return_ar1", "market_state",
            "mst_peer_state", "topcorr_peer_state", "distance_peer_state",
        })
        self.assertEqual(set(frame.formation_cutoff), {returns.index[125]})
        self.assertEqual(set(frame.calibration_cutoff), {date})
        for horizon in (1, 5, 20):
            rows = frame[(frame.ticker == "A") & (frame.horizon == horizon)]
            expected = returns["A"].iloc[186:186 + horizon].sum()
            np.testing.assert_allclose(rows.outcome.to_numpy(dtype=float), expected)
        mean_row = frame[(frame.ticker == "A") & (frame.model == "historical_mean") & (frame.horizon == 5)].iloc[0]
        self.assertAlmostEqual(mean_row.forecast, 5 * returns["A"].iloc[126:186].mean())
        state = frame[(frame.ticker == "A") & (frame.model == "mst_peer_state") & (frame.horizon == 5)].iloc[0]
        self.assertEqual(state.status, "ok")
        self.assertNotIn("A", state.peer_tickers)
        self.assertEqual(len(state.peer_tickers), len(frame[(frame.ticker == "A") & (frame.model == "topcorr_peer_state") & (frame.horizon == 5)].iloc[0].peer_tickers))
        self.assertAlmostEqual(state.hedge_weights["A"], 1)
        self.assertAlmostEqual(sum(state.hedge_weights.values()), 1 - state.beta_market - state.beta_peer)
        self.assertAlmostEqual(state.forecast, 5 * state.alpha + (state.phi ** 5 - 1) * (state.state - state.equilibrium))
        actual_hedge = sum(returns[ticker].iloc[186:191].sum() * weight for ticker, weight in state.hedge_weights.items())
        self.assertAlmostEqual(state.hedge_outcome, actual_hedge)

    def test_future_extension_cannot_change_features_or_forecasts(self):
        returns = _returns()
        date = returns.index[185]
        before = build_residual_forecasts(returns.iloc[:186], diagnostic_start=date, diagnostic_end=date)
        after = build_residual_forecasts(returns, diagnostic_start=date, diagnostic_end=date)
        keys = ["date", "ticker", "model", "horizon"]
        before = before.sort_values(keys).reset_index(drop=True)
        after = after.sort_values(keys).reset_index(drop=True)
        for column in ("forecast", "status", "reason", "alpha", "beta_market", "beta_peer", "phi", "tau", "state"):
            pd.testing.assert_series_equal(before[column], after[column], check_names=False)
        self.assertTrue(before.outcome.isna().all())
        self.assertTrue(after.outcome.notna().all())

    def test_missing_calibration_day_abstains_without_bridging(self):
        returns = _returns()
        date = returns.index[185]
        returns.loc[returns.index[150], "A"] = np.nan
        frame = build_residual_forecasts(returns, diagnostic_start=date, diagnostic_end=date)
        stock = frame[(frame.ticker == "A") & (frame.model != "zero")]
        self.assertTrue((stock.status == "no_trade").all())
        self.assertTrue((stock.forecast == 0).all())
        self.assertTrue(stock.reason.str.contains("missing").all())

    def test_collinear_predictors_do_not_get_pseudoinverse_trade(self):
        returns = _returns()
        returns["B"] = returns["C"] = returns["D"] = returns["A"]
        date = returns.index[185]
        frame = build_residual_forecasts(returns, diagnostic_start=date, diagnostic_end=date)
        stock = frame[(frame.ticker == "A") & (frame.model.str.endswith("_state"))]
        self.assertTrue((stock.status == "no_trade").all())
        self.assertTrue((stock.forecast == 0).all())
        self.assertTrue(stock.reason.str.contains("rank|variance|collinear|invalid_state").all())


if __name__ == "__main__":
    unittest.main()
