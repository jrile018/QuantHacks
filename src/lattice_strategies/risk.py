"""Past-only covariance and allocation diagnostics on a fixed return panel.

All returns are fractional session returns. Forecast variance, observed squared
return, and MSE have units fractional_return_squared_per_session. QLIKE uses
``y / max(v, 1e-12) + log(max(v, 1e-12))`` and is dimensionless up to its
chosen return unit. Allocation costs are assumed one-way basis-point scenarios;
their net proxy is not executable P&L.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .graphs import tree_covariance


ESTIMATORS = ("diagonal_cov", "sample_cov", "ledoit_wolf", "one_factor", "mst_tree")
POLICIES = ("equal_weight", "inverse_vol", "lw_min_variance", "tree_min_variance")
VARIANCE_FLOOR = 1e-12


def _covariances(window_returns: np.ndarray) -> dict[str, np.ndarray | None]:
    """Each estimator sees exactly the same complete trailing window."""
    from sklearn.covariance import LedoitWolf

    sample = np.atleast_2d(np.cov(window_returns, rowvar=False, ddof=1))
    diagonal = np.diag(np.diag(sample))
    lw = LedoitWolf().fit(window_returns).covariance_
    centered = window_returns - window_returns.mean(axis=0)
    factor = centered.mean(axis=1)
    factor_variance = float(np.var(factor, ddof=1))
    if factor_variance > VARIANCE_FLOOR:
        beta = (centered.T @ factor) / ((len(factor) - 1) * factor_variance)
    else:
        beta = np.zeros(centered.shape[1])
    residual = centered - np.outer(factor, beta)
    one_factor = factor_variance * np.outer(beta, beta) + np.diag(np.var(residual, axis=0, ddof=1))
    return {
        "diagonal_cov": diagonal,
        "sample_cov": sample,
        "ledoit_wolf": lw,
        "one_factor": one_factor,
        "mst_tree": tree_covariance(sample) if np.all(np.diag(sample) > 0) else None,
    }


def _capped_inverse_vol(covariance: np.ndarray, cap: float) -> np.ndarray:
    inverse_vol = 1.0 / np.sqrt(np.maximum(np.diag(covariance), VARIANCE_FLOOR))
    lo, hi = 0.0, 1.0 / min(inverse_vol)
    while np.minimum(hi * inverse_vol, cap).sum() < 1.0:
        hi *= 2.0
    for _ in range(80):
        middle = (lo + hi) / 2.0
        if np.minimum(middle * inverse_vol, cap).sum() < 1.0:
            lo = middle
        else:
            hi = middle
    result = np.minimum(hi * inverse_vol, cap)
    return result / result.sum()


def _minimum_variance(covariance: np.ndarray, cap: float) -> np.ndarray | None:
    from scipy.optimize import minimize

    n = len(covariance)
    result = minimize(
        lambda w: float(w @ covariance @ w),
        np.full(n, 1.0 / n),
        jac=lambda w: 2.0 * covariance @ w,
        method="SLSQP",
        bounds=[(0.0, cap)] * n,
        constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0,
                     "jac": lambda w: np.ones_like(w)},
        options={"ftol": 1e-12, "maxiter": 500},
    )
    weights = np.asarray(result.x, dtype=float)
    if (not result.success or not np.isfinite(weights).all()
            or abs(weights.sum() - 1.0) > 1e-7
            or np.min(weights) < -1e-8 or np.max(weights) > cap + 1e-8):
        return None
    return weights


def _weights_json(columns: pd.Index, weights: np.ndarray | None) -> str | None:
    if weights is None:
        return None
    return json.dumps(dict(zip(columns, map(float, weights))), separators=(",", ":"))


def build_risk_forecasts(
    returns: pd.DataFrame,
    *,
    diagnostic_start,
    diagnostic_end,
    window: int = 126,
    max_weight: float = .25,
    cost_bps: tuple[float, ...] = (0., 1., 5., 10.),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build fixed-book risk scores and secondary weekly allocation ledgers.

    A row dated t uses only returns through t. Its mark is the next panel
    session t+1. Missing windows and missing marks remain explicit rows.
    Allocation rows are long by policy and cost scenario, including daily
    holds between first-session-of-ISO-week rebalance opportunities. The cap
    applies to target weights at entries and rebalances; daily drift may
    exceed it. A missing mark after entry quarantines the economic path.
    """
    if not isinstance(returns.index, pd.DatetimeIndex) or not returns.index.is_unique or not returns.index.is_monotonic_increasing:
        raise ValueError("returns need a unique, ascending DatetimeIndex")
    if not returns.columns.is_unique or list(returns.columns) != sorted(returns.columns) or not all(isinstance(c, str) for c in returns.columns):
        raise ValueError("returns need unique, sorted string columns")
    if window < 2 or len(returns.columns) < 1:
        raise ValueError("window must be at least two and panel nonempty")
    n = len(returns.columns)
    if not (0 < max_weight <= 1) or n * max_weight < 1 - 1e-12:
        raise ValueError("max_weight makes a fully invested book impossible")
    if any(not np.isfinite(c) or c < 0 for c in cost_bps):
        raise ValueError("cost_bps must be finite and nonnegative")
    numeric = returns.to_numpy(dtype=float)
    dates = returns.index
    diagnostic_positions = [i for i, date in enumerate(dates) if pd.Timestamp(diagnostic_start) <= date <= pd.Timestamp(diagnostic_end)]
    equal = np.full(n, 1.0 / n)
    risk_rows: list[dict] = []
    allocation_rows: list[dict] = []
    # State is drifted after the previous observed mark, ready for date t.
    state: dict[str, np.ndarray | None] = {policy: None for policy in POLICIES}
    last_rebalance_week: dict[str, tuple[int, int] | None] = {policy: None for policy in POLICIES}
    quarantined: dict[str, bool] = {policy: False for policy in POLICIES}

    for pos in diagnostic_positions:
        date = dates[pos]
        next_date = dates[pos + 1] if pos + 1 < len(dates) else pd.NaT
        next_returns = numeric[pos + 1] if pos + 1 < len(dates) else None
        markable = next_returns is not None and np.isfinite(next_returns).all()
        complete = pos + 1 >= window and np.isfinite(numeric[pos - window + 1:pos + 1]).all()
        covariances = _covariances(numeric[pos - window + 1:pos + 1]) if complete else {}
        fixed_observed = float((equal @ next_returns) ** 2) if markable else np.nan
        for estimator in ESTIMATORS:
            covariance = covariances.get(estimator)
            forecast = float(equal @ covariance @ equal) if covariance is not None else np.nan
            status = "abstain" if covariance is None else "forecast" if markable else "unmarked"
            reason = (("incomplete_window" if not complete else "zero_variance_tree_input") if covariance is None else "" if markable
                      else "missing_next_return" if next_returns is not None else "no_next_session")
            floored = max(forecast, VARIANCE_FLOOR) if np.isfinite(forecast) else np.nan
            risk_rows.append({
                "date": date, "target_next_date": next_date, "estimator": estimator,
                "status": status, "reason": reason, "forecast_variance": forecast,
                "observed_squared_return": fixed_observed,
                "qlike": fixed_observed / floored + np.log(floored) if covariance is not None and markable else np.nan,
                "mse": (fixed_observed - forecast) ** 2 if covariance is not None and markable else np.nan,
                "units": "fractional_return_squared_per_session",
                "mse_units": "fractional_return_to_fourth_per_session_squared",
                "book_weights_json": _weights_json(returns.columns, equal),
            })

        iso = date.isocalendar()
        week = (int(iso.year), int(iso.week))
        for policy in POLICIES:
            prior = state[policy]
            rebalance = prior is None and last_rebalance_week[policy] is None or week != last_rebalance_week[policy]
            chosen = None
            event = "hold"
            reason = ""
            volume = 0.0
            if quarantined[policy]:
                reason, event = "quarantined_after_missing_mark", "abstain"
            elif not complete:
                reason, event = "incomplete_window", "abstain"
                if prior is not None:
                    quarantined[policy] = True
            elif next_returns is None:
                # No trade is invented at the panel boundary. If a book is
                # live, its last observed mark receives the terminal charge.
                chosen, event, reason = prior, "terminal_pending", "no_next_session"
            elif rebalance:
                event = "initial_entry" if prior is None else "weekly_rebalance"
                last_rebalance_week[policy] = week
                covariance_name = "ledoit_wolf" if policy == "lw_min_variance" else "mst_tree"
                if policy == "equal_weight":
                    chosen = equal.copy()
                elif policy == "inverse_vol":
                        chosen = _capped_inverse_vol(covariances["sample_cov"], max_weight)
                else:
                    optimizer_covariance = covariances[covariance_name]
                    if optimizer_covariance is None:
                        reason, event = "zero_variance_tree_input", "abstain"
                    else:
                        chosen = _minimum_variance(optimizer_covariance, max_weight)
                        if chosen is None:
                            reason, event = "optimizer_failed", "abstain"
                if chosen is None and prior is not None:
                    chosen, event = prior.copy(), "rebalance_failed_hold"
                if chosen is not None and event != "rebalance_failed_hold":
                    volume = 1.0 if prior is None else float(np.abs(chosen - prior).sum())
            elif prior is not None:
                chosen = prior.copy()
            else:
                reason, event = "no_live_book_until_next_week", "abstain"

            if chosen is None:
                state[policy] = None
            elif next_returns is None:
                state[policy] = prior
            elif not markable:
                state[policy] = None
                reason = "missing_next_return"
                quarantined[policy] = True
            else:
                gross = float(chosen @ next_returns)
                if 1.0 + gross > 0:
                    state[policy] = chosen * (1.0 + next_returns) / (1.0 + gross)
                else:
                    state[policy] = None
            marked = chosen is not None and markable
            mark_return = float(chosen @ next_returns) if marked else np.nan
            terminal = marked and pos == diagnostic_positions[-1]
            for bps in cost_bps:
                trade_cost = float(bps) * volume / 10000.0 if chosen is not None else 0.0
                terminal_cost = float(bps) / 10000.0 if terminal else 0.0
                allocation_rows.append({
                    "date": date, "target_next_date": next_date, "policy": policy,
                    "cost_bps": float(bps), "status": "marked" if marked else "abstain" if chosen is None else "unmarked",
                    "reason": reason, "event_reason": event, "weights_json": _weights_json(returns.columns, chosen),
                    "one_way_trade_volume": volume if chosen is not None else np.nan,
                    "turnover": volume if chosen is not None else np.nan,
                    "initial_cost": trade_cost if event == "initial_entry" and chosen is not None else 0.0,
                    "rebalance_cost": trade_cost if event == "weekly_rebalance" and chosen is not None else 0.0,
                    "terminal_cost": terminal_cost,
                    "mark_return": mark_return,
                    "net_proxy_return": mark_return - trade_cost - terminal_cost if marked else np.nan,
                    "cost_limitations": "assumed one-way bps on trade volume; research proxy, not verified net P&L or cash",
                })

    # If the terminal diagnostic session has no successor, the live book is
    # known at that date from the preceding mark. Charge liquidation against
    # that last complete mark, never against an unobserved future return.
    if diagnostic_positions and diagnostic_positions[-1] == len(dates) - 1:
        for policy in POLICIES:
            if quarantined[policy] or state[policy] is None:
                continue
            marked_rows = [row for row in allocation_rows if row["policy"] == policy and row["status"] == "marked"]
            if not marked_rows:
                continue
            last_mark_date = marked_rows[-1]["date"]
            for row in allocation_rows:
                if row["policy"] == policy and row["date"] == last_mark_date:
                    row["terminal_cost"] = row["cost_bps"] / 10000.0
                    row["net_proxy_return"] -= row["terminal_cost"]

    return pd.DataFrame(risk_rows), pd.DataFrame(allocation_rows)
