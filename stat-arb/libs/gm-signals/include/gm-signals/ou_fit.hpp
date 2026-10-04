#pragma once

// Ornstein-Uhlenbeck fit for a spread series (ADR §6.4/§13's "OU fitting
// ... exact AR(1) MLE mapping"): ds = theta*(mu - s) dt + sigma dW,
// fitted by mapping the closed-form MLE of a discretely-sampled AR(1)
// process onto the OU process's known exact discretization. This is
// the direct ancestor Avellaneda & Lee (2010) use for their s-score.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::signals {

struct OuFit {
    double theta;     // mean-reversion speed (> 0)
    double mu;         // long-run mean
    double sigma;       // continuous-time volatility (> 0)
    double half_life;   // ln(2) / theta, in the same time units as `dt`
};

/// `s` is an evenly-spaced spread series (one point per `dt`, typically
/// one trading day, dt=1). Requires at least 3 points (2 AR(1) pairs -
/// the minimum for a non-degenerate slope/variance estimate) and a
/// non-constant series. The underlying AR(1) coefficient phi must fall
/// strictly in (0, 1): phi <= 0 has no valid continuous-time OU mapping
/// (ln(phi) is undefined for phi <= 0 - the discrete process would be
/// oscillating or degenerate, not a sampled OU path), and phi >= 1
/// means non-stationary (unit-root or explosive) - no finite half-life
/// exists.
[[nodiscard]] Result<OuFit> fit_ou(const Eigen::VectorXd& s, double dt = 1.0);

/// Standardized deviation from the fitted long-run mean, in units of
/// the process's stationary standard deviation: z = (s_t - mu) /
/// (sigma / sqrt(2*theta)). This is exactly Avellaneda & Lee's s-score.
[[nodiscard]] Result<double> ou_zscore(const OuFit& fit, double s_t);

} // namespace gm::signals
