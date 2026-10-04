#pragma once

// Robust Mahalanobis ellipsoid boundary (ADR-011 phase-1 stand-in: "a
// shrunk-covariance Mahalanobis with MAD-standardized inputs" - full
// FastMCD is a scheduled later milestone with its own reference-vector
// validation against the published Rousseeuw examples, not attempted
// here). Each dimension is centered on its MEDIAN and scaled by its MAD
// (median absolute deviation, x1.4826 for consistency with the normal
// std-dev under Gaussian data) before the ordinary sample covariance is
// computed on the standardized data - this bounds the influence any
// single outlying point has on the fit, which the plain sample mean/
// covariance does not.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::boundaries {

struct MahalanobisFit {
    Eigen::VectorXd median;         // k, per-dimension robust center
    Eigen::VectorXd mad_scale;      // k, per-dimension robust scale (1.4826 * MAD, floored)
    Eigen::VectorXd standardized_mean; // k, mean of the MAD-standardized training data
    Eigen::MatrixXd covariance;     // k x k, covariance of the standardized training data
    Eigen::MatrixXd inv_covariance; // precomputed inverse for fast scoring
    int degrees_of_freedom;         // k
};

struct MahalanobisScore {
    double distance;      // Mahalanobis distance (not squared) in standardized space
    double critical_distance; // the chi-squared-quantile distance at `alpha`
    double p_value;        // chi-squared survival probability at distance^2, df=k
    double depth;           // distance - critical_distance: negative=inside, positive=outside
    bool inside;
};

/// `points` is N x k (N >= k+1 required for a non-degenerate covariance
/// estimate). Every dimension's MAD must be nonzero (a dimension with
/// more than half its values identical has an undefined/zero MAD) -
/// rejected rather than silently flooring to an arbitrary scale.
[[nodiscard]] Result<MahalanobisFit> fit_mahalanobis(const Eigen::MatrixXd& points);

/// `alpha` is the boundary's exceedance probability (default 0.05, i.e.
/// the ellipsoid contains ~95% of a well-behaved fit's own training
/// mass) - the critical distance is chi2.quantile(1-alpha, k), and
/// `inside` is `distance <= critical_distance` (equivalently
/// `p_value >= alpha`).
[[nodiscard]] Result<MahalanobisScore> score_mahalanobis(const MahalanobisFit& fit,
                                                          const Eigen::VectorXd& point,
                                                          double alpha = 0.05);

} // namespace gm::boundaries
