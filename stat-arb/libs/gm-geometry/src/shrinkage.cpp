#include <gm-geometry/correlation.hpp>
#include <gm-geometry/shrinkage.hpp>

#include <algorithm>
#include <cmath>

namespace gm::geometry {

Result<ShrinkageResult> ledoit_wolf_shrink_correlation(const Eigen::MatrixXd& returns) {
    const Eigen::Index t = returns.rows();
    const Eigen::Index n = returns.cols();

    if (t < 2) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "ledoit_wolf_shrink_correlation requires at least 2 observations",
            "got " + std::to_string(t)));
    }
    if (n < 1) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "returns matrix has zero columns"));
    }

    auto demeaned = demean_columns(returns);
    if (!demeaned) return tl::unexpected(demeaned.error());

    // Standardize each column to unit sample variance (T-1 divisor, the
    // conventional estimator) so the LW covariance-shrinkage formula
    // below operates on z-scored data - its "sample covariance" is then
    // exactly the sample correlation of the original returns.
    Eigen::VectorXd col_var = demeaned->array().square().colwise().sum() / static_cast<double>(t - 1);
    for (Eigen::Index j = 0; j < n; ++j) {
        if (!(col_var(j) > 0.0)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument, "returns column has zero or negative variance",
                "column " + std::to_string(j)));
        }
    }
    Eigen::MatrixXd standardized = *demeaned;
    for (Eigen::Index j = 0; j < n; ++j) {
        standardized.col(j) /= std::sqrt(col_var(j));
    }

    // Ledoit-Wolf (2004) Section 2, shrinkage-to-identity-target,
    // applied to the standardized data. LW's own convention divides by
    // T (not T-1) for the "sample covariance" S being shrunk.
    Eigen::MatrixXd s = (standardized.transpose() * standardized) / static_cast<double>(t);
    double mu = s.trace() / static_cast<double>(n);
    Eigen::MatrixXd centered = s - mu * Eigen::MatrixXd::Identity(n, n);
    double d2 = centered.squaredNorm();  // ||S - mu*I||_F^2

    // b_bar^2 = (1/T^2) * sum_t ||x_t x_t^T - S||_F^2, expanded into a
    // closed form to avoid materializing T separate N x N outer
    // products:
    //   ||x_t x_t^T - S||_F^2 = ||x_t||^4 - 2 x_t^T S x_t + ||S||_F^2
    Eigen::VectorXd row_sqnorms = standardized.rowwise().squaredNorm();  // ||x_t||^2 per row
    double sum_norm4 = row_sqnorms.array().square().sum();
    Eigen::MatrixXd xs = standardized * s;  // T x N
    double sum_xtSxt = xs.cwiseProduct(standardized).sum();  // sum_t x_t^T S x_t
    double s_frob2 = s.squaredNorm();
    double t_d = static_cast<double>(t);
    double b_bar2 = (sum_norm4 - 2.0 * sum_xtSxt + t_d * s_frob2) / (t_d * t_d);

    double b2 = std::min(b_bar2, d2);
    // d2 == 0 only when S is already exactly mu*I (e.g. a perfectly
    // orthogonal, equal-variance standardized panel) - shrinkage is
    // then moot; delta = 0 (no shrinkage applied, S already equals the
    // target) is the well-defined convention rather than a 0/0 NaN.
    double delta = (d2 > 0.0) ? (b2 / d2) : 0.0;

    Eigen::MatrixXd shrunk_correlation = delta * mu * Eigen::MatrixXd::Identity(n, n) + (1.0 - delta) * s;

    // Numerical hygiene: exact symmetry and exact unit diagonal (mu, in
    // the standardized-data case, is 1 only in expectation - clamp
    // explicitly rather than rely on floating-point identities holding
    // to more digits than IEEE 754 double actually gives).
    shrunk_correlation = (shrunk_correlation + shrunk_correlation.transpose()) / 2.0;
    for (Eigen::Index i = 0; i < n; ++i) shrunk_correlation(i, i) = 1.0;

    return ShrinkageResult{std::move(shrunk_correlation), delta};
}

} // namespace gm::geometry
