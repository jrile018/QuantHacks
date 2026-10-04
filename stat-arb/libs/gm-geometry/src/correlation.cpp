#include <gm-geometry/correlation.hpp>

namespace gm::geometry {

Result<Eigen::MatrixXd> demean_columns(const Eigen::MatrixXd& returns) {
    if (returns.rows() < 1) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "returns matrix has zero rows"));
    }
    Eigen::RowVectorXd column_means = returns.colwise().mean();
    return returns.rowwise() - column_means;
}

Result<Eigen::MatrixXd> sample_correlation(const Eigen::MatrixXd& returns) {
    const Eigen::Index t = returns.rows();
    const Eigen::Index n = returns.cols();

    if (t < 2) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "sample_correlation requires at least 2 observations",
            "got " + std::to_string(t)));
    }
    if (n < 1) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "returns matrix has zero columns"));
    }

    auto demeaned = demean_columns(returns);
    if (!demeaned) return tl::unexpected(demeaned.error());

    // Sample covariance, T-1 (Bessel-corrected) divisor - the
    // conventional unbiased estimator; Ledoit-Wolf's own T-divisor
    // convention is handled locally inside shrinkage.cpp, not here,
    // since this function's contract is "the ordinary sample
    // correlation," used on its own (ADR-009's raw/diagnostic matrix)
    // as well as by the shrinkage/RMT pipeline.
    Eigen::MatrixXd covariance = (demeaned->transpose() * (*demeaned)) / static_cast<double>(t - 1);

    Eigen::VectorXd variances = covariance.diagonal();
    for (Eigen::Index i = 0; i < n; ++i) {
        if (!(variances(i) > 0.0)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument, "returns column has zero or negative variance",
                "column " + std::to_string(i)));
        }
    }

    Eigen::VectorXd inv_std = variances.array().sqrt().inverse();
    Eigen::MatrixXd correlation = inv_std.asDiagonal() * covariance * inv_std.asDiagonal();

    // Numerical hygiene: force exact symmetry (floating-point matrix
    // products can drift by ~1e-16 off-diagonal) and an exact unit
    // diagonal, so downstream SelfAdjointEigenSolver calls (which
    // assume, but do not verify, exact symmetry) never see a matrix
    // that is merely symmetric "up to rounding."
    correlation = (correlation + correlation.transpose()) / 2.0;
    for (Eigen::Index i = 0; i < n; ++i) correlation(i, i) = 1.0;

    return correlation;
}

} // namespace gm::geometry
