#include <gm-geometry/distance.hpp>

#include <algorithm>
#include <cmath>

namespace gm::geometry {

namespace {
constexpr double kRoundoffTolerance = 1e-9;
}

Result<Eigen::MatrixXd> mantegna_distance(const Eigen::MatrixXd& correlation) {
    const Eigen::Index n = correlation.rows();

    if (correlation.rows() != correlation.cols()) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "correlation matrix must be square"));
    }
    if (n < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "empty correlation matrix"));
    }

    Eigen::MatrixXd clamped = correlation;
    for (Eigen::Index i = 0; i < n; ++i) {
        for (Eigen::Index j = 0; j < n; ++j) {
            double v = clamped(i, j);
            if (v > 1.0 + kRoundoffTolerance || v < -1.0 - kRoundoffTolerance) {
                return tl::unexpected(gm::Error::make(
                    gm::ErrorCode::kInvalidArgument, "correlation value outside [-1, 1]",
                    "(" + std::to_string(i) + "," + std::to_string(j) + ") = " + std::to_string(v)));
            }
            clamped(i, j) = std::clamp(v, -1.0, 1.0);
        }
    }

    // d_ij = sqrt(2*(1 - rho_ij)); on the diagonal rho_ii = 1 so d_ii =
    // 0 exactly (clamped(i,i) is forced to 1.0 above only if it was
    // fractionally off already - the formula handles an exact 1.0
    // diagonal correctly regardless).
    Eigen::MatrixXd distance = (2.0 * (Eigen::MatrixXd::Ones(n, n) - clamped)).cwiseMax(0.0).cwiseSqrt();

    // Numerical hygiene: force exact symmetry and an exact zero
    // diagonal (sqrt of a tiny negative-due-to-roundoff clamped-to-zero
    // value is exactly 0, but the off-diagonal symmetry can still drift
    // by ~1e-16 through the elementwise sqrt if the input correlation
    // wasn't perfectly symmetric to begin with).
    distance = (distance + distance.transpose()) / 2.0;
    for (Eigen::Index i = 0; i < n; ++i) distance(i, i) = 0.0;

    return distance;
}

} // namespace gm::geometry
