"""Small, past-only fixtures for the lattice covariance diagnostics."""

import json

import numpy as np
import pandas as pd

from src.lattice_strategies.risk import build_risk_forecasts


def panel():
    dates = pd.bdate_range("2024-01-01", periods=9)
    values = np.array([
        [.01, .02, -.01, .00],
        [.02, -.01, .01, .00],
        [-.01, .01, .02, .01],
        [.03, .00, -.02, .01],
        [.01, -.02, .00, .02],
        [-.02, .01, .01, -.01],
        [.02, .03, -.01, .00],
        [.01, -.01, .02, .01],
        [-.01, .02, .00, .03],
    ])
    return pd.DataFrame(values, index=dates, columns=list("ABCD"))


def run(frame, start=None, end=None, **kwargs):
    return build_risk_forecasts(frame, diagnostic_start=start or frame.index[2],
                                diagnostic_end=end or frame.index[-2], window=3,
                                **kwargs)


def test_fixed_book_next_session_target_and_estimators_share_it():
    frame = panel()
    risks, allocations = run(frame)
    day = frame.index[2]
    rows = risks.loc[risks.date.eq(day)]
    assert set(rows.estimator) == {"diagonal_cov", "sample_cov", "ledoit_wolf", "one_factor", "mst_tree"}
    assert set(rows.status) == {"forecast"}
    assert set(rows.target_next_date) == {frame.index[3]}
    expected = float(np.mean(frame.loc[frame.index[3]]) ** 2)
    np.testing.assert_allclose(rows.observed_squared_return, expected)
    diagonal = rows.set_index("estimator").loc["diagonal_cov"]
    expected_diagonal = float(np.diag(frame.iloc[:3].cov()).sum() / 16)
    np.testing.assert_allclose(diagonal.forecast_variance, expected_diagonal)
    assert np.isfinite(rows.qlike).all()
    assert np.isfinite(rows.mse).all()
    assert set(allocations.target_next_date.loc[allocations.date.eq(day)]) == {frame.index[3]}


def test_future_append_cannot_change_frozen_diagnostics():
    frame = panel()
    end = frame.index[5]
    first = run(frame.loc[:frame.index[6]], end=end)
    extra = pd.DataFrame([[.9, -.8, .7, -.6]], index=[frame.index[-1] + pd.Timedelta(days=1)], columns=frame.columns)
    second = run(pd.concat([frame, extra]), end=end)
    pd.testing.assert_frame_equal(first[0], second[0])
    pd.testing.assert_frame_equal(first[1], second[1])


def test_weights_respect_cap_and_drift_makes_turnover_nonzero():
    frame = panel()
    _, allocations = run(frame, max_weight=.4, cost_bps=(0., 10.))
    active = allocations.loc[allocations.status.eq("marked")]
    assert not active.empty
    target_rows = active.loc[active.event_reason.isin(["initial_entry", "weekly_rebalance"])]
    for encoded in target_rows.weights_json:
        weights = np.array(list(json.loads(encoded).values()))
        assert weights.min() >= -1e-9
        assert weights.max() <= .4 + 1e-9
        np.testing.assert_allclose(weights.sum(), 1)
    assert any(max(json.loads(encoded).values()) > .4 for encoded in
               active.loc[active.event_reason.eq("hold"), "weights_json"])
    first = active.loc[active.policy.eq("equal_weight") & active.cost_bps.eq(10.)].iloc[0]
    np.testing.assert_allclose(first.one_way_trade_volume, 1)
    np.testing.assert_allclose(first.initial_cost, .001)
    np.testing.assert_allclose(first.net_proxy_return, first.mark_return - .001)
    assert (active.one_way_trade_volume >= 0).all()
    monday = frame.index[5]
    rebalance = active.loc[active.policy.eq("equal_weight") & active.cost_bps.eq(10.)
                           & active.date.eq(monday)].iloc[0]
    drifted = .25 * (1 + frame.iloc[3:6]).prod(axis=0).to_numpy()
    drifted /= drifted.sum()
    np.testing.assert_allclose(rebalance.one_way_trade_volume, np.abs(.25 - drifted).sum())
    assert rebalance.event_reason == "weekly_rebalance"


def test_entry_and_exit_charged_even_when_single_mark_and_end_has_no_next_session():
    frame = panel()
    _, one_day = run(frame, start=frame.index[2], end=frame.index[2], cost_bps=(10.,))
    one = one_day.loc[one_day.policy.eq("equal_weight")].iloc[0]
    np.testing.assert_allclose(one.initial_cost, .001)
    np.testing.assert_allclose(one.terminal_cost, .001)
    np.testing.assert_allclose(one.net_proxy_return, one.mark_return - .002)
    _, through_end = run(frame, start=frame.index[2], end=frame.index[-1], cost_bps=(10.,))
    prior = through_end.loc[through_end.policy.eq("equal_weight")
                            & through_end.date.eq(frame.index[-2])].iloc[0]
    last = through_end.loc[through_end.policy.eq("equal_weight")
                           & through_end.date.eq(frame.index[-1])].iloc[0]
    np.testing.assert_allclose(prior.terminal_cost, .001)
    assert last.status == "unmarked"
    assert last.one_way_trade_volume == 0


def test_missing_window_or_mark_abstains_without_bridging():
    frame = panel()
    frame.loc[frame.index[4], "A"] = np.nan
    risks, allocations = run(frame, end=frame.index[6])
    day3 = risks.loc[risks.date.eq(frame.index[3])]
    assert set(day3.status) == {"unmarked"}
    assert day3.observed_squared_return.isna().all()
    day4 = risks.loc[risks.date.eq(frame.index[4])]
    assert set(day4.status) == {"abstain"}
    assert day4.forecast_variance.isna().all()
    assert set(allocations.loc[allocations.date.eq(frame.index[4]), "status"]) == {"abstain"}
    assert set(allocations.loc[allocations.date.eq(frame.index[6]), "status"]) == {"abstain"}
    assert set(allocations.loc[allocations.date.eq(frame.index[6]), "reason"]) == {"quarantined_after_missing_mark"}


def test_constant_asset_rejects_only_undefined_tree_estimator():
    frame = panel()
    frame.loc[frame.index[:3], "A"] = .01
    risks, allocations = run(frame, start=frame.index[2], end=frame.index[2])
    tree = risks.loc[risks.estimator.eq("mst_tree")].iloc[0]
    assert tree.status == "abstain"
    assert tree.reason == "zero_variance_tree_input"
    assert risks.loc[risks.estimator.eq("sample_cov"), "status"].iloc[0] == "forecast"
    assert allocations.loc[allocations.policy.eq("tree_min_variance"), "reason"].eq("zero_variance_tree_input").all()


def test_failed_weekly_tree_rebalance_keeps_known_live_book():
    frame = panel()
    frame.loc[frame.index[3:6], "A"] = .01
    _, allocations = run(frame, max_weight=.4, cost_bps=(10.,))
    monday = frame.index[5]
    tree = allocations.loc[allocations.policy.eq("tree_min_variance") & allocations.date.eq(monday)].iloc[0]
    assert tree.status == "marked"
    assert tree.event_reason == "rebalance_failed_hold"
    assert tree.reason == "zero_variance_tree_input"
    assert tree.one_way_trade_volume == 0
    assert tree.initial_cost == 0
