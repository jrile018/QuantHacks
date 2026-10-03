"""Uncertainty estimates, comparison tables, and risk-budget limits."""

import numpy as np
import pandas as pd
import math

from .config import BASELINE_BUCKET, ENTRY, HORIZONS, OTM_PCT, STRATEGIES, STRATEGY_LABEL


def contracts_within_risk_budget(capital: float, risk_fraction: float, max_loss_per_contract: float) -> int:
    """Whole contracts whose worst-case loss fits an event-level cash risk budget."""
    if not math.isfinite(capital) or capital < 0:
        raise ValueError("capital must be finite and nonnegative")
    if not math.isfinite(risk_fraction) or not 0 < risk_fraction <= 1:
        raise ValueError("risk_fraction must be in (0, 1]")
    if not math.isfinite(max_loss_per_contract) or max_loss_per_contract <= 0:
        raise ValueError("max_loss_per_contract must be finite and positive")
    return math.floor(capital * risk_fraction / max_loss_per_contract)

def bootstrap_ci(x, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return tuple(np.percentile(means, [2.5, 97.5]).tolist())

def slice_results(res: pd.DataFrame, bucket: str, entry: str, otm: float) -> pd.DataFrame:
    return res[(res.bucket == bucket) & (res.entry == entry) & (res.otm == otm)]

def scoreboard(res: pd.DataFrame, bucket: str = None, entry: str = None, otm: float = None,
               horizons=None, strategies=STRATEGIES) -> pd.DataFrame:
    """Rows: strategy. Columns: horizon. Cells: mean P&L per $1 of spot, with n and a 95% bootstrap CI."""
    r = slice_results(res, bucket or BASELINE_BUCKET, entry or ENTRY, otm or OTM_PCT)
    horizons = horizons or [h for h in HORIZONS + ["exp"] if h in set(r.horizon)]
    rows = []
    for s in strategies:
        for h in horizons:
            x = r.loc[r.horizon == h, s].dropna()
            lo, hi = bootstrap_ci(x)
            rows.append({"strategy": s, "horizon": h, "n": len(x), "mean": x.mean(), "ci_lo": lo, "ci_hi": hi,
                         "median": x.median(), "hit_rate": (x > 0).mean()})
    return pd.DataFrame(rows)

def difference_board(res_a: pd.DataFrame, res_b: pd.DataFrame, bucket: str = None, entry: str = None, otm: float = None,
                     strategies=STRATEGIES, seed: int = 1) -> pd.DataFrame:
    """Mean P&L of group a minus group b, per strategy and horizon, with a bootstrap CI on the difference."""
    a = slice_results(res_a, bucket or BASELINE_BUCKET, entry or ENTRY, otm or OTM_PCT)
    b = slice_results(res_b, bucket or BASELINE_BUCKET, entry or ENTRY, otm or OTM_PCT)
    rng, rows = np.random.default_rng(seed), []
    for s in strategies:
        for h in [h for h in HORIZONS + ["exp"] if h in set(a.horizon) & set(b.horizon)]:
            xa, xb = a.loc[a.horizon == h, s].dropna().to_numpy(), b.loc[b.horizon == h, s].dropna().to_numpy()
            row = {"strategy": s, "horizon": h, "n_a": len(xa), "n_b": len(xb)}
            if len(xa) >= 5 and len(xb) >= 5:
                d = rng.choice(xa, (2000, len(xa))).mean(1) - rng.choice(xb, (2000, len(xb))).mean(1)
                row.update(mean_a=xa.mean(), mean_b=xb.mean(), difference=xa.mean() - xb.mean(),
                           ci_lo=np.percentile(d, 2.5), ci_hi=np.percentile(d, 97.5))
            rows.append(row)
    return pd.DataFrame(rows)

def rank_strategies(diff: pd.DataFrame, horizons=(21, 42, "exp")) -> pd.DataFrame:
    """Rank the five strategies by their event-minus-placebo edge, averaged over the given horizons."""
    d = diff[diff.horizon.isin(horizons) & (diff.strategy != "stock")]
    out = (d.groupby("strategy").agg(edge=("difference", "mean"), horizons_ci_excludes_0=("ci_lo", lambda s: int(((s > 0) | (d.loc[s.index, "ci_hi"] < 0)).sum())),
                                     n_events=("n_a", "max"))
             .sort_values("edge", ascending=False))
    out["edge"] = out["edge"].map(lambda v: f"{v * 100:+.2f}%")
    return out.rename(index=STRATEGY_LABEL)

def decay_table(r: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for h in [h for h in HORIZONS + ["exp"] if h in set(r.horizon)]:
        x = r.loc[r.horizon == h, "ratio"].dropna()
        lo, hi = bootstrap_ci(x)
        rows.append({"horizon": h, "n": len(x), "mean_ratio": x.mean(), "ci_lo": lo, "ci_hi": hi,
                     "median_ratio": x.median(), "share_above_1": (x > 1).mean()})
    return pd.DataFrame(rows).set_index("horizon")
