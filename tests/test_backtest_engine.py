import json
import numpy as np
import math

import pandas as pd
import pytest

from backtesting import (BacktestError, Config, chronological_splits, hash_frame,
                             record_trial, run_backtest)

DAYS = pd.bdate_range("2024-01-01", periods=8)


def marks(prices: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    for sym, closes in prices.items():
        for day, c in zip(DAYS, closes):
            rows.append({"date": day, "symbol": sym, "close": c})
    return pd.DataFrame(rows)


def event(eid, sym, side, entry_i, exit_i, ep, xp, decision_i=None):
    d = DAYS[decision_i if decision_i is not None else entry_i - 1 if entry_i else 0]
    return {"event_id": eid, "symbol": sym, "side": side, "decision_time": d,
            "entry_date": DAYS[entry_i], "exit_date": DAYS[exit_i],
            "entry_price": ep, "exit_price": xp}


def cfg(**kw):
    base = dict(starting_capital=1_000_000.0, max_gross=1.0, commission_bps=0.0,
                borrow_bps_annual=0.0)
    base.update(kw)
    return Config(**base)


def test_long_only_exact_pnl_no_costs():
    m = marks({"AAA": [10, 11, 12, 13, 14, 15, 16, 17]})
    d = pd.DataFrame([event("e1", "AAA", 1, 1, 4, 10.0, 14.0)])
    r = run_backtest(d, m, cfg())
    # 100% of NAV into one long at 10 -> 100,000 shares; exit at 14 -> +400,000
    assert r.trades.iloc[0]["gross_pnl"] == pytest.approx(400_000)
    assert r.summary["ending_nav"] == pytest.approx(1_400_000)
    assert r.summary["total_return"] == pytest.approx(0.4)


def test_short_pnl_and_borrow_charged_to_ledger():
    m = marks({"BBB": [20, 19, 18, 17, 16, 15, 14, 13]})
    d = pd.DataFrame([event("e1", "BBB", -1, 1, 4, 20.0, 16.0)])
    r = run_backtest(d, m, cfg(borrow_bps_annual=252 * 100))  # 100 bps per trading day
    # one short sized at full NAV: shares = 1,000,000/20 = 50,000; profit = 50,000 * 4 = 200,000
    assert r.trades.iloc[0]["gross_pnl"] == pytest.approx(200_000)
    # borrow accrues on steps where the short is held over the prior step: days 2 and 3
    # (the exit on day 4 closes the position before that day's accrual). Charged on prior closes 19 and 18.
    expected_borrow = 0.01 * 50_000 * (19 + 18)
    assert r.summary["borrow_total"] == pytest.approx(expected_borrow)
    assert r.trades.iloc[0]["net_pnl"] == pytest.approx(200_000 - expected_borrow)


def test_costs_reduce_nav_on_entry_and_exit():
    m = marks({"AAA": [10] * 8})
    d = pd.DataFrame([event("e1", "AAA", 1, 1, 4, 10.0, 10.0)])
    r = run_backtest(d, m, cfg(commission_bps=10))
    # 10 bps on 1,000,000 notional at entry and again at exit
    assert r.summary["commission_total"] == pytest.approx(2_000)
    assert r.summary["ending_nav"] == pytest.approx(998_000)


def test_equal_weight_respects_gross_cap():
    m = marks({"AAA": [10] * 8, "BBB": [10] * 8, "CCC": [10] * 8, "DDD": [10] * 8})
    d = pd.DataFrame([
        event("e1", "AAA", 1, 1, 3, 10.0, 10.0),
        event("e2", "BBB", -1, 1, 3, 10.0, 10.0),
        event("e3", "CCC", 1, 1, 3, 10.0, 10.0),
        event("e4", "DDD", -1, 1, 3, 10.0, 10.0),
    ])
    r = run_backtest(d, m, cfg(max_gross=0.5))
    entry_row = r.nav[r.nav["date"] == DAYS[1]].iloc[0]
    assert entry_row["gross_exposure"] == pytest.approx(0.5)
    assert entry_row["open_positions"] == 4


def test_invalid_price_is_excluded_not_filled():
    m = marks({"AAA": [10] * 8, "BBB": [10] * 8})
    d = pd.DataFrame([
        event("e1", "AAA", 1, 1, 3, 10.0, 11.0),
        event("e2", "BBB", 1, 1, 3, float("nan"), 11.0),
    ])
    r = run_backtest(d, m, cfg())
    assert r.summary["excluded_decisions"] == 1
    assert r.excluded.iloc[0]["reason"] == "invalid_price"
    assert len(r.trades) == 1


def test_missing_mark_raises():
    # BBB keeps the date on the calendar, so only AAA's mark on that day is missing
    m = marks({"AAA": [10] * 8, "BBB": [10] * 8})
    m = m[~((m["symbol"] == "AAA") & (m["date"] == DAYS[3]))]
    d = pd.DataFrame([event("e1", "AAA", 1, 1, 5, 10.0, 10.0)])
    with pytest.raises(BacktestError, match="missing mark"):
        run_backtest(d, m, cfg())


def test_decision_after_entry_is_lookahead():
    m = marks({"AAA": [10] * 8})
    d = pd.DataFrame([event("e1", "AAA", 1, 2, 4, 10.0, 10.0, decision_i=3)])
    with pytest.raises(BacktestError, match="lookahead"):
        run_backtest(d, m, cfg())


def test_overlapping_positions_same_symbol_raise():
    m = marks({"AAA": [10] * 8})
    d = pd.DataFrame([
        event("e1", "AAA", 1, 1, 4, 10.0, 10.0),
        event("e2", "AAA", 1, 2, 5, 10.0, 10.0),
    ])
    with pytest.raises(BacktestError, match="overlapping"):
        run_backtest(d, m, cfg())


def test_bad_side_and_bad_config_rejected():
    m = marks({"AAA": [10] * 8})
    with pytest.raises(BacktestError, match="side"):
        run_backtest(pd.DataFrame([event("e1", "AAA", 0, 1, 3, 10.0, 10.0)]), m, cfg())
    with pytest.raises(BacktestError):
        cfg(max_gross=1.5)
    with pytest.raises(BacktestError):
        Config(starting_capital=1e6, max_gross=1.0, commission_bps=-1, borrow_bps_annual=0)


def test_splits_purge_and_drop_straddlers():
    ev = pd.DataFrame([
        {"event_id": "a", "entry_date": "2024-01-02", "exit_date": "2024-01-05"},
        {"event_id": "b", "entry_date": "2024-01-08", "exit_date": "2024-01-20"},  # straddles
        {"event_id": "c", "entry_date": "2024-02-01", "exit_date": "2024-02-05"},
    ])
    train, test, dropped = chronological_splits(ev, "2024-01-10", "2024-01-25", purge_days=5)
    assert list(train["event_id"]) == ["a"]
    assert list(test["event_id"]) == ["c"]
    assert list(dropped["event_id"]) == ["b"]
    with pytest.raises(BacktestError):
        chronological_splits(ev, "2024-01-10", "2024-01-12", purge_days=5)


def test_hash_is_order_independent_and_trial_log_appends(tmp_path):
    a = pd.DataFrame({"x": [1, 2], "y": ["p", "q"]})
    b = a.iloc[::-1][["y", "x"]]
    assert hash_frame(a) == hash_frame(b)
    log = tmp_path / "trials.jsonl"
    record_trial(log, "t1", {"k": 1}, {"in": "h"}, {"s": 1})
    record_trial(log, "t2", {"k": 2}, {"in": "h"}, {"s": 2})
    lines = log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["name"] for x in lines] == ["t1", "t2"]


def test_engine_summary_reports_sharpe_pnl_winrate_and_intervals():
    m = marks({"AAA": [10, 11, 10.5, 11.5, 11, 12, 11.8, 12.5]})
    d = pd.DataFrame([
        event("e1", "AAA", 1, 1, 3, 10.0, 11.0),
        event("e2", "AAA", 1, 4, 6, 11.0, 10.0),
    ])
    r = run_backtest(d, m, cfg())
    s = r.summary
    for key in ("sharpe_annualized", "sharpe_ci95", "win_rate", "win_rate_ci95",
                "net_pnl", "mean_trade_pnl_ci95", "metrics"):
        assert key in s
    assert s["net_pnl"] == pytest.approx(s["ending_nav"] - 1_000_000)
    assert s["win_rate"] == pytest.approx(0.5)
    lo, hi = s["sharpe_ci95"]
    assert lo <= s["sharpe_annualized"] <= hi


def test_metrics_intervals_bracket_mean_and_are_deterministic():
    from backtesting import metrics
    x = np.array([0.01, -0.02, 0.03, 0.005, -0.01, 0.02, 0.015, -0.005])
    a = metrics.bootstrap_ci(x, np.mean)
    b = metrics.bootstrap_ci(x, np.mean)
    assert a == b
    assert a[0] <= x.mean() <= a[1]
    t = metrics.t_ci_mean(x)
    assert t[0] <= x.mean() <= t[1]
    assert metrics.trade_metrics(np.array([]), 1e6)["win_rate"] is None
