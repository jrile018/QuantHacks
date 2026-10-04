"""Tiny audit witnesses; no market data, parameter search, or native binary run.

These establish algebra and interpretation, not trading profitability.
"""
import numpy as np
import pandas as pd

from src.lattice_strategies.evaluation import residual_cost_sensitivity
from src.lattice_strategies.graphs import tree_covariance
from src.lattice_strategies.residuals import _state_fit
from src.lattice_strategies.risk import _covariances


def test_exact_ou_mapping_and_half_life_units():
    phi, c, innovation_variance, dt = .8, .04, .0009, 1 / 252
    theta = -np.log(phi) / dt
    mu = c / (1 - phi)
    sigma_squared = innovation_variance * 2 * theta / (1 - phi**2)
    assert np.isclose(np.exp(-theta * dt), phi)
    assert np.isclose(mu * (1 - np.exp(-theta * dt)), c)
    assert np.isclose(sigma_squared / (2 * theta) * (1 - phi**2), innovation_variance)
    assert np.isclose(np.log(2) / theta / dt, np.log(2) / -np.log(phi))


def test_native_guard_counterexample_changes_with_time_unit():
    # Native ou_fit.cpp:81 compares physical half-life with observation count.
    # A 100-session half-life on 59 pairs is rejected in days but accepted in years.
    phi = np.exp(-np.log(2) / 100)
    in_days = np.log(2) / (-np.log(phi))
    in_years = np.log(2) / (-np.log(phi) / (1 / 252))
    assert in_days > 59
    assert not in_years > 59
    assert in_years > 59 / 252  # Correct physical sample-span comparison rejects.


def test_disjoint_calibration_has_no_forced_zero_endpoint_and_correct_hedge():
    rng = np.random.default_rng(19)
    formation = rng.normal(0, .01, (12, 3))
    calibration = rng.normal(0, .01, (8, 3))
    alpha, market_beta, peer_beta = .001, .7, .4
    formation[:, 0] = alpha + market_beta * formation[:, 1:].mean(1) + peer_beta * formation[:, 1]
    residual = np.array([.001, .004, -.002, .003, -.001, .002, -.003, .005])
    calibration[:, 0] = alpha + market_beta * calibration[:, 1:].mean(1) + peer_beta * calibration[:, 1] + residual
    details, _ = _state_fit(formation, calibration, 0, [1], max_tau=100)
    weights = np.array([details['weights'][i] for i in range(3)])
    np.testing.assert_allclose(weights, [1, -.75, -.35], atol=1e-12)
    np.testing.assert_allclose(calibration @ weights, alpha + residual, atol=1e-12)
    assert np.isclose(details['state'], residual.sum())
    assert not np.isclose(details['state'], 0)


def test_raw_stock_mse_can_lose_while_hedge_forecast_is_exact():
    forecast, factor_return, hedged_return = .01, -.10, .01
    raw_stock_return = factor_return + hedged_return
    assert (forecast - raw_stock_return)**2 > raw_stock_return**2
    assert np.isclose(forecast - hedged_return, 0)


def test_gross_normalization_and_two_sided_trade_cost():
    rows = pd.DataFrame([dict(date=pd.Timestamp('2024-01-02'), ticker='A',
        model='mst_peer_state', horizon=1, hedge_weights={'A': 1, 'B': -2},
        status='ok', forecast=.01, outcome=.04, hedge_outcome=.03)])
    result = residual_cost_sensitivity(rows, [1]).iloc[0]
    assert np.isclose(result.gross_normalization, 3)
    assert np.isclose(result.gross_mark_return, .01)
    assert np.isclose(result.round_trip_cost, .0002)
    assert np.isclose(result.net_mark_proxy, .0098)


def test_additive_return_is_not_buy_and_hold_or_log_spread():
    returns = np.array([.1, -.1])
    assert np.isclose(returns.sum(), 0)
    assert np.isclose(np.prod(1 + returns) - 1, -.01)
    assert np.isclose(np.log1p(returns).sum(), np.log(.99))


def test_one_factor_equal_book_variance_is_inflated_by_diagonal_residuals():
    factor = np.array([.01, -.01, .01, -.01])
    residual = np.array([.02, .02, -.02, -.02])
    returns = np.column_stack([factor + residual, factor - residual, factor])
    covariances = _covariances(returns)
    equal = np.full(3, 1 / 3)
    sample_book = equal @ covariances['sample_cov'] @ equal
    factor_book = equal @ covariances['one_factor'] @ equal
    excess = 2 * np.var(residual, ddof=1) / 9
    assert np.isclose(sample_book, np.var(factor, ddof=1))
    assert np.isclose(factor_book - sample_book, excess)
    assert factor_book > sample_book


def test_tree_covariance_is_valid_but_changes_nonedge_correlations():
    correlation = np.array([[1, .8, .5], [.8, 1, .7], [.5, .7, 1]])
    tree = tree_covariance(correlation)
    assert np.isclose(tree[0, 2], .8 * .7)
    assert not np.isclose(tree[0, 2], correlation[0, 2])
    assert np.linalg.eigvalsh(tree).min() > 0
    np.testing.assert_allclose(np.diag(tree), 1)
