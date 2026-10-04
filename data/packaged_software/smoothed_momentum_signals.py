"""Causal technical signal helpers shared by standalone and overlay research."""
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


def causal_savgol(series, window=21, degree=2):
    """Save only the endpoint fit of each past-only window; never revise history."""
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)
    if len(values) >= window:
        windows = np.lib.stride_tricks.sliding_window_view(values, window)
        valid = np.isfinite(windows).all(axis=1)
        endpoints = np.full(len(windows), np.nan)
        endpoints[valid] = savgol_filter(windows[valid], window, degree, axis=1,
                                        mode='interp')[:, -1]
        result[window-1:] = endpoints
    return pd.Series(result, index=series.index, name=series.name)


def momentum_signals(smoothed, horizons=(21, 63, 168, 252)):
    """Mean of four signs times an explicit agreement multiplier.

    Four positives => 1; three positives and one negative => .25.
    Incomplete horizon history stays missing. No shorts are implied.
    """
    differences = pd.concat([smoothed-smoothed.shift(h) for h in horizons], axis=1)
    signs = np.sign(differences)
    complete = differences.notna().all(axis=1)
    positive = (signs>0).sum(axis=1)
    negative = (signs<0).sum(axis=1)
    agreement = np.maximum(positive, negative)
    multiplier = pd.Series(np.where(agreement==4, 1., np.where(agreement==3, .5, 0.)),
                           index=smoothed.index)
    score = (signs.mean(axis=1)*multiplier).where(complete)
    return pd.DataFrame({'momentum_score':score, 'positive_horizons':positive,
                         'negative_horizons':negative, 'agreement_multiplier':multiplier})
