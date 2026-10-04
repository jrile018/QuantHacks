#include <gm-boundaries/mahalanobis.hpp>

#include <boost/math/distributions/chi_squared.hpp>

#include <algorithm>
#include <cmath>
#include <exception>
#include <vector>

namespace gm::boundaries {

namespace {

constexpr double kMadConsistencyConstant = 1.4826;  // makes MAD ~= std dev under normality
constexpr double kMinScale = 1e-12;                 // floor to avoid dividing by an exact-zero MAD
constexpr double kMinEigenvalue = 1e-10;             // floor for treating the covariance as singular

double median_of(std::vector<double> values) {
    std::size_t n = values.size();
    std::size_t mid = n / 2;
    std::nth_element(values.begin(), values.begin() + static_cast<std::ptrdiff_t>(mid), values.end());
    double upper = values[mid];
    if (n % 2 == 1) return upper;
    std::nth_element(values.begin(), values.begin() + static_cast<std::ptrdiff_t>(mid) - 1, values.end());
    double lower = values[mid - 1];
    return (lower + upper) / 2.0;
}

} // namespace

Result<MahalanobisFit> fit_mahalanobis(const Eigen::MatrixXd& points) {
    const Eigen::Index n = points.rows();
    const Eigen::Index k = points.cols();

    if (k < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "points has zero columns"));
    }
    if (n < k + 1) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "fewer points than degrees of freedom + 1",
            "n=" + std::to_string(n) + ", k=" + std::to_string(k)));
    }

    Eigen::VectorXd median(k), mad_scale(k);
    for (Eigen::Index j = 0; j < k; ++j) {
        std::vector<double> col(static_cast<std::size_t>(n));
        for (Eigen::Index i = 0; i < n; ++i) col[static_cast<std::size_t>(i)] = points(i, j);
        double med = median_of(col);
        median(j) = med;

        std::vector<double> abs_dev(col.size());
        for (std::size_t i = 0; i < col.size(); ++i) abs_dev[i] = std::abs(col[i] - med);
        double mad = median_of(abs_dev);
        if (mad <= 0.0) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument,
                "dimension has zero median absolute deviation (more than half its values are "
                "identical) - MAD standardization is undefined",
                "column " + std::to_string(j)));
        }
        mad_scale(j) = std::max(kMadConsistencyConstant * mad, kMinScale);
    }

    Eigen::MatrixXd standardized(n, k);
    for (Eigen::Index j = 0; j < k; ++j) {
        standardized.col(j) = (points.col(j).array() - median(j)) / mad_scale(j);
    }

    Eigen::VectorXd standardized_mean = standardized.colwise().mean();
    Eigen::MatrixXd centered = standardized.rowwise() - standardized_mean.transpose();
    Eigen::MatrixXd covariance = (centered.transpose() * centered) / static_cast<double>(n - 1);
    covariance = (covariance + covariance.transpose()) / 2.0;  // symmetrize floating-point drift

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(covariance);
    if (solver.info() != Eigen::Success) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNumericFailure, "covariance eigendecomposition failed"));
    }
    Eigen::VectorXd eigenvalues = solver.eigenvalues();
    if (eigenvalues(0) < kMinEigenvalue) {  // ascending order - smallest is index 0
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kNumericFailure,
            "covariance matrix is (near-)singular - points may be degenerate/collinear in some "
            "dimension",
            "smallest eigenvalue = " + std::to_string(eigenvalues(0))));
    }

    // Invert via the eigendecomposition already computed, rather than a
    // second general matrix inverse - both more efficient and, for a
    // matrix we've just confirmed is well-conditioned, at least as
    // numerically stable.
    Eigen::VectorXd inv_eigenvalues = eigenvalues.array().inverse();
    Eigen::MatrixXd inv_covariance =
        solver.eigenvectors() * inv_eigenvalues.asDiagonal() * solver.eigenvectors().transpose();
    inv_covariance = (inv_covariance + inv_covariance.transpose()) / 2.0;

    return MahalanobisFit{std::move(median),
                           std::move(mad_scale),
                           std::move(standardized_mean),
                           std::move(covariance),
                           std::move(inv_covariance),
                           static_cast<int>(k)};
}

Result<MahalanobisScore> score_mahalanobis(const MahalanobisFit& fit, const Eigen::VectorXd& point,
                                            double alpha) {
    if (point.size() != fit.median.size()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "point dimension does not match fit dimension",
            "point: " + std::to_string(point.size()) + ", fit: " + std::to_string(fit.median.size())));
    }
    if (!(alpha > 0.0 && alpha < 1.0)) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "alpha must be in (0, 1)"));
    }

    Eigen::VectorXd standardized = (point - fit.median).array() / fit.mad_scale.array();
    Eigen::VectorXd centered = standardized - fit.standardized_mean;

    double distance_squared = centered.transpose() * fit.inv_covariance * centered;
    if (distance_squared < 0.0) distance_squared = 0.0;  // floating-point guard; must be non-negative
    double distance = std::sqrt(distance_squared);

    // Boost.Math's distribution functions can throw on pathological
    // inputs (extreme distance_squared feeding the incomplete gamma
    // function's internal series/continued-fraction evaluation) even
    // though every guard above is already satisfied - guarded here
    // rather than left to propagate past this function's Result<T>
    // boundary (ADR-019: no exceptions past a stage's error boundary).
    double p_value = 0.0, critical_distance = 0.0;
    try {
        boost::math::chi_squared_distribution<double> chi2(static_cast<double>(fit.degrees_of_freedom));
        p_value = boost::math::cdf(boost::math::complement(chi2, distance_squared));
        double critical_distance_squared = boost::math::quantile(chi2, 1.0 - alpha);
        critical_distance = std::sqrt(critical_distance_squared);
    } catch (const std::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "chi-squared distribution evaluation failed",
                                               e.what()));
    }

    double depth = distance - critical_distance;
    bool inside = depth <= 0.0;

    return MahalanobisScore{distance, critical_distance, p_value, depth, inside};
}

} // namespace gm::boundaries
