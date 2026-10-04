"""Past-only residual state diagnostics on daily fractional stock returns.

The horizon target is the additive sum of raw stock returns, equivalent to a
fixed-notional price change approximation. It is not a compounded account PnL.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .graphs import mst_neighbors


MODELS = (
    "zero", "historical_mean", "own_return_ar1", "market_state",
    "mst_peer_state", "topcorr_peer_state", "distance_peer_state",
)
STATE_MODELS = MODELS[3:]


def _ols(y: np.ndarray, predictors: np.ndarray) -> np.ndarray | None:
    """Return OLS coefficients with intercept, refusing singular designs."""
    design = np.column_stack((np.ones(len(y)), predictors))
    if not np.isfinite(design).all() or not np.isfinite(y).all():
        return None
    if np.linalg.matrix_rank(design) != design.shape[1]:
        return None
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coefficients if np.isfinite(coefficients).all() else None


def _ar1(values: np.ndarray) -> tuple[float, float, float] | None:
    fit = _ols(values[1:], values[:-1, None])
    if fit is None:
        return None
    intercept, phi = map(float, fit)
    innovations = values[1:] - intercept - phi * values[:-1]
    variance = float(np.var(innovations, ddof=1))
    if not np.isfinite(variance) or variance <= 0:
        return None
    return intercept, phi, variance


def _peer_sets(formation: np.ndarray) -> dict[str, list[list[int]]] | None:
    """Fit graph relationships on the earlier formation window only."""
    count = formation.shape[1]
    if count < 3 or not np.isfinite(formation).all():
        return None
    residuals = np.empty_like(formation)
    for target in range(count):
        others = [j for j in range(count) if j != target]
        market = formation[:, others].mean(axis=1)
        fit = _ols(formation[:, target], market[:, None])
        if fit is None:
            return None
        residuals[:, target] = formation[:, target] - fit[0] - fit[1] * market
    if np.any(np.std(residuals, axis=0) <= 0):
        return None
    corr = np.corrcoef(residuals, rowvar=False)
    if not np.isfinite(corr).all():
        return None
    tree = mst_neighbors(corr)
    if len(tree) != count or any(not neighbors for neighbors in tree):
        return None
    tree = [[int(j) for j in neighbors if j != i] for i, neighbors in enumerate(tree)]
    if any(not neighbors for neighbors in tree):
        return None
    top = []
    distance = []
    if np.any(formation <= -1):
        return None
    paths = np.cumprod(1 + formation, axis=0)
    paths = np.vstack((np.ones(count), paths))
    for i in range(count):
        degree = len(tree[i])
        top.append(sorted((j for j in range(count) if j != i), key=lambda j: (-corr[i, j], j))[:degree])
        distance.append(sorted((j for j in range(count) if j != i), key=lambda j: (np.linalg.norm(paths[:, i] - paths[:, j]), j))[:degree])
    return {"mst_peer_state": tree, "topcorr_peer_state": top, "distance_peer_state": distance}


def _state_fit(
    formation: np.ndarray, calibration: np.ndarray, target: int, peers: list[int],
    *, max_tau: float,
) -> tuple[dict, str]:
    others = [j for j in range(formation.shape[1]) if j != target]
    formation_market = formation[:, others].mean(axis=1)
    calibration_market = calibration[:, others].mean(axis=1)
    formation_columns = [formation_market]
    calibration_columns = [calibration_market]
    if peers:
        formation_columns.append(formation[:, peers].mean(axis=1))
        calibration_columns.append(calibration[:, peers].mean(axis=1))
    fit = _ols(formation[:, target], np.column_stack(formation_columns))
    if fit is None:
        return {}, "rank_deficient_hedge"
    alpha, beta_market = map(float, fit[:2])
    beta_peer = float(fit[2]) if peers else 0.0
    weights = {j: -beta_market / len(others) for j in others}
    for j in peers:
        weights[j] += -beta_peer / len(peers)
    weights[target] = 1.0
    residual = calibration[:, target] - alpha - np.column_stack(calibration_columns) @ fit[1:]
    state = np.r_[0.0, np.cumsum(residual)]
    details = {
        "alpha": alpha, "beta_market": beta_market, "beta_peer": beta_peer,
        "state": float(state[-1]), "weights": weights,
    }
    ar = _ar1(state)
    if ar is None:
        return details, "invalid_state_ar1"
    intercept, phi, variance = ar
    details.update(phi=phi, innovation_var=variance)
    if not 0 < phi < 1:
        return details, "invalid_phi"
    tau = -1.0 / np.log(phi)
    details["tau"] = tau
    if not np.isfinite(tau) or tau > max_tau:
        return details, "invalid_tau"
    equilibrium = intercept / (1 - phi)
    if not np.isfinite(equilibrium):
        return details, "invalid_equilibrium"
    details["equilibrium"] = float(equilibrium)
    return details, ""


def build_residual_forecasts(
    returns: pd.DataFrame, *, diagnostic_start, diagnostic_end,
    formation: int = 126, calibration: int = 60,
    horizons: Sequence[int] = (1, 5, 20), max_tau: float = 30,
) -> pd.DataFrame:
    """Produce every date/ticker/model/horizon row, including abstentions.

    On date t, [t-calibration-formation+1, t-calibration] determines hedge
    coefficients and peers; [t-calibration+1, t] determines residual state.
    Future rows only populate realized outcomes. Missing values are never
    dropped from a window to bridge over a data gap.
    """
    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError("returns must be a nonempty DataFrame")
    if not isinstance(returns.index, pd.DatetimeIndex) or not returns.index.is_monotonic_increasing or not returns.index.is_unique:
        raise ValueError("returns needs a sorted unique DatetimeIndex")
    if returns.columns.has_duplicates or len(returns.columns) < 2:
        raise ValueError("returns needs at least two unique stock columns")
    if formation < 3 or calibration < 3 or max_tau <= 0 or not horizons or any(int(h) != h or h < 1 for h in horizons):
        raise ValueError("invalid window, horizon, or tau")
    values = returns.to_numpy(dtype=float)
    tickers = list(returns.columns)
    start, end = pd.Timestamp(diagnostic_start), pd.Timestamp(diagnostic_end)
    rows = []
    for t, date in enumerate(returns.index):
        if not start <= date <= end:
            continue
        eligible = t + 1 >= formation + calibration
        formation_values = values[t + 1 - formation - calibration:t + 1 - calibration] if eligible else None
        calibration_values = values[t + 1 - calibration:t + 1] if eligible else None
        formation_cutoff = returns.index[t - calibration] if eligible else pd.NaT
        graph_sets = None
        if eligible and np.isfinite(formation_values).all() and np.isfinite(calibration_values).all():
            graph_sets = _peer_sets(formation_values)
        for i, ticker in enumerate(tickers):
            target_valid = eligible and np.isfinite(formation_values[:, i]).all() and np.isfinite(calibration_values[:, i]).all()
            own_fit = _ar1(calibration_values[:, i]) if target_valid else None
            state_fits = {}
            for model in STATE_MODELS:
                if not eligible:
                    state_fits[model] = ({}, "insufficient_history")
                elif not np.isfinite(formation_values).all() or not np.isfinite(calibration_values).all():
                    state_fits[model] = ({}, "missing_window_return")
                elif model != "market_state" and graph_sets is None:
                    state_fits[model] = ({}, "invalid_graph_variance")
                else:
                    peers = [] if model == "market_state" else graph_sets[model][i]
                    state_fits[model] = _state_fit(formation_values, calibration_values, i, peers, max_tau=max_tau)
            for model in MODELS:
                details, state_reason = state_fits.get(model, ({}, ""))
                for horizon in horizons:
                    h = int(horizon)
                    future = values[t + 1:t + 1 + h]
                    outcome = float(future[:, i].sum()) if len(future) == h and np.isfinite(future[:, i]).all() else np.nan
                    base = {
                        "date": date, "ticker": ticker, "model": model, "horizon": h,
                        "outcome": outcome, "forecast": 0.0, "status": "ok", "reason": "",
                        "formation_cutoff": formation_cutoff, "calibration_cutoff": date,
                        "alpha": np.nan, "beta_market": np.nan, "beta_peer": np.nan,
                        "peer_tickers": (), "hedge_weights": {ticker: 1.0},
                        "phi": np.nan, "tau": np.nan, "state": np.nan,
                        "equilibrium": np.nan, "innovation_var": np.nan,
                        "hedge_outcome": np.nan if model in STATE_MODELS else outcome,
                    }
                    if model == "zero":
                        pass
                    elif not target_valid and model in ("historical_mean", "own_return_ar1"):
                        base.update(status="no_trade", reason="insufficient_history" if not eligible else "missing_window_return")
                    elif model == "historical_mean":
                        base["forecast"] = float(h * calibration_values[:, i].mean())
                    elif model == "own_return_ar1":
                        if own_fit is None or abs(own_fit[1]) >= 1:
                            base.update(status="no_trade", reason="invalid_return_ar1")
                        else:
                            own_alpha, own_phi, variance = own_fit
                            next_return = float(calibration_values[-1, i])
                            prediction = 0.0
                            for _ in range(h):
                                next_return = own_alpha + own_phi * next_return
                                prediction += next_return
                            base.update(forecast=prediction, alpha=own_alpha, phi=own_phi, innovation_var=variance)
                    else:
                        base.update({k: v for k, v in details.items() if k not in ("weights",)})
                        if model != "market_state" and graph_sets is not None:
                            base["peer_tickers"] = tuple(tickers[j] for j in graph_sets[model][i])
                        if "weights" in details:
                            base["hedge_weights"] = {tickers[j]: float(weight) for j, weight in details["weights"].items()}
                            if len(future) == h and np.isfinite(future).all():
                                base["hedge_outcome"] = float(sum(future[:, j].sum() * weight for j, weight in details["weights"].items()))
                        if state_reason:
                            base.update(status="no_trade", reason=state_reason)
                        else:
                            base["forecast"] = h * details["alpha"] + (details["phi"] ** h - 1) * (details["state"] - details["equilibrium"])
                    rows.append(base)
    return pd.DataFrame(rows)
