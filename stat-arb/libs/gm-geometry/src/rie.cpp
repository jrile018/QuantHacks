#include <gm-geometry/rie.hpp>

#include <Eigen/Eigenvalues>

#include <cmath>
#include <complex>

namespace gm::geometry {

namespace {

constexpr double kSymmetryTolerance = 1e-9;

}  // namespace

Result<RieResult> rie_clean_correlation(const Eigen::MatrixXd& correlation, double q) {
    const Eigen::Index n = correlation.rows();
    if (n == 0 || correlation.cols() != n) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "RIE requires a non-empty square correlation matrix",
                                               std::to_string(correlation.rows()) + "x" +
                                                   std::to_string(correlation.cols())));
    }
    if (!(q > 0.0)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "RIE requires q = N/T > 0", std::to_string(q)));
    }
    const double asymmetry = (correlation - correlation.transpose()).cwiseAbs().maxCoeff();
    if (asymmetry > kSymmetryTolerance) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "RIE requires a symmetric correlation matrix",
                                               "max |C - C^T| = " + std::to_string(asymmetry)));
    }

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(correlation);
    if (solver.info() != Eigen::Success) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "RIE eigendecomposition did not converge",
                                               std::to_string(n) + "x" + std::to_string(n)));
    }

    const Eigen::VectorXd lambda = solver.eigenvalues();  // ascending
    const Eigen::MatrixXd& vectors = solver.eigenvectors();

    RieResult result;
    result.q = q;
    result.sample_eigenvalues = lambda;
    // The eigenvalue spacing of an N x N sample spectrum is O(1/N), so a
    // regulator of N^(-1/2) is comfortably wider than one level and
    // comfortably narrower than the bulk: the Stieltjes transform gets
    // smoothed over a handful of neighbours rather than over everything.
    const double eta = 1.0 / std::sqrt(static_cast<double>(n));
    result.eta = eta;

    Eigen::VectorXd xi(n);
    for (Eigen::Index i = 0; i < n; ++i) {
        const double lam = lambda(i);
        if (!(lam > 0.0)) {
            // A non-positive eigenvalue is numerical debris from a
            // matrix that is singular to working precision. There is no
            // sensible cleaned value for it; carrying it through would
            // make the rebuilt matrix indefinite, so it is floored.
            xi(i) = 0.0;
            continue;
        }
        const std::complex<double> z(lam, -eta);
        std::complex<double> g(0.0, 0.0);
        for (Eigen::Index j = 0; j < n; ++j) {
            g += 1.0 / (z - lambda(j));
        }
        g /= static_cast<double>(n);

        const std::complex<double> denom = 1.0 - q + q * z * g;
        // std::norm is the SQUARED magnitude, which is exactly what the
        // estimator calls for - no sqrt, and no second squaring.
        const double d = std::norm(denom);
        xi(i) = (d > 0.0 && std::isfinite(d)) ? lam / d : lam;
        if (!std::isfinite(xi(i)) || xi(i) < 0.0) xi(i) = lam;
    }

    // Same eigenvectors, cleaned eigenvalues. Keeping the rotation is
    // the defining property of the estimator: a sample covariance
    // carries no information about the true eigenvectors beyond what its
    // own already express.
    Eigen::MatrixXd cleaned = vectors * xi.asDiagonal() * vectors.transpose();

    // Back to a correlation matrix. This also restores trace = N
    // exactly, which the eigenvalue map on its own does not preserve.
    Eigen::VectorXd scale = cleaned.diagonal();
    for (Eigen::Index i = 0; i < n; ++i) {
        scale(i) = scale(i) > 0.0 ? 1.0 / std::sqrt(scale(i)) : 0.0;
    }
    cleaned = scale.asDiagonal() * cleaned * scale.asDiagonal();
    for (Eigen::Index i = 0; i < n; ++i) cleaned(i, i) = 1.0;
    // Symmetrize away the last bit of floating-point asymmetry, so
    // downstream symmetry checks (mantegna_distance) cannot trip on
    // rounding.
    cleaned = 0.5 * (cleaned + cleaned.transpose()).eval();

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> cleaned_solver(cleaned);
    if (cleaned_solver.info() != Eigen::Success) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "RIE eigendecomposition of the cleaned matrix failed",
                                               std::to_string(n) + "x" + std::to_string(n)));
    }

    result.cleaned_eigenvalues = cleaned_solver.eigenvalues();
    result.cleaned_correlation = std::move(cleaned);
    return result;
}

}  // namespace gm::geometry
