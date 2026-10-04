"""Independent arithmetic witnesses for the Lattice math audit.

These use only the Python standard library and do not import production code.
They demonstrate interpretation limits, not a replacement estimator.
"""

import math
import statistics


def test_fitted_five_point_gaussian_radius_cannot_flag_any_training_point():
    # For sample mean and sample covariance in one dimension, any training
    # observation's absolute studentized residual is bounded by (n-1)/sqrt(n).
    n = 5
    maximum_fitted_radius = (n - 1) / math.sqrt(n)
    normal_95_radius = 1.959963984540054  # sqrt(chi2.ppf(.95, df=1))
    assert maximum_fitted_radius < normal_95_radius

    # A nonsingular, positive-MAD training cloud with a massive outlier.
    points = [-2.0, -1.0, 0.0, 1.0, 100.0]
    radius = abs(points[-1] - statistics.mean(points)) / statistics.stdev(points)
    assert math.isclose(radius, 1.788301, abs_tol=0.002)
    assert radius < normal_95_radius


def test_training_frozen_cash_control_can_gain_only_from_exposure():
    # Same +1% next-session mark at every holdout opportunity: there is no
    # cross-sectional or time variation for any filter to select.
    outcomes = [0.01] * 4
    training_mean_exposure = 0.5
    holdout_candidate_exposures = [1.0] * 4
    candidate = statistics.mean(e * y for e, y in zip(holdout_candidate_exposures, outcomes))
    training_cash = statistics.mean(training_mean_exposure * y for y in outcomes)
    holdout_exposure_matched_cash = statistics.mean(statistics.mean(holdout_candidate_exposures) * y for y in outcomes)
    assert math.isclose(candidate - training_cash, 0.005)
    assert math.isclose(candidate - holdout_exposure_matched_cash, 0.0, abs_tol=1e-15)
