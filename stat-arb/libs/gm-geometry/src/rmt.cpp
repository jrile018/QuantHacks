#include <gm-geometry/rmt.hpp>

#include <cmath>

namespace gm::geometry {

Result<RmtResult> mp_denoise(const Eigen::MatrixXd& correlation, double q) {
    const Eigen::Index n = correlation.rows();

    if (correlation.rows() != correlation.cols()) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "correlation matrix must be square"));
    }
    if (n < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "empty correlation matrix"));
    }
    if (!(q > 0.0)) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "q (N/T) must be positive"));
    }

    double sqrt_q = std::sqrt(q);
    double lambda_plus = (1.0 + sqrt_q) * (1.0 + sqrt_q);
    double lambda_minus = (q < 1.0) ? (1.0 - sqrt_q) * (1.0 - sqrt_q) : 0.0;

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(correlation);
    if (solver.info() != Eigen::Success) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "eigendecomposition failed to converge"));
    }

    // Eigen returns eigenvalues in ascending order for SelfAdjointEigenSolver.
    Eigen::VectorXd eigenvalues = solver.eigenvalues();
    const Eigen::MatrixXd& eigenvectors = solver.eigenvectors();

    double bulk_sum = 0.0;
    int bulk_count = 0;
    for (Eigen::Index i = 0; i < n; ++i) {
        if (eigenvalues(i) <= lambda_plus) {
            bulk_sum += eigenvalues(i);
            ++bulk_count;
        }
    }

    Eigen::VectorXd denoised_eigenvalues = eigenvalues;
    if (bulk_count > 0) {
        double bulk_mean = bulk_sum / static_cast<double>(bulk_count);
        for (Eigen::Index i = 0; i < n; ++i) {
            if (eigenvalues(i) <= lambda_plus) denoised_eigenvalues(i) = bulk_mean;
        }
    }
    // bulk_count == 0 (every eigenvalue is above the MP bulk edge) is
    // left as-is: nothing classifies as noise, so there is nothing to
    // replace - not a special case requiring different handling, just
    // the natural result of the loop above finding no matches.

    Eigen::MatrixXd reconstructed =
        eigenvectors * denoised_eigenvalues.asDiagonal() * eigenvectors.transpose();

    // Rescale the diagonal back to exactly 1: replacing eigenvalues
    // changes the reconstructed matrix's diagonal away from 1 in
    // general, even though the ORIGINAL correlation matrix's diagonal
    // was exactly 1 (ADR-009: "rescale to unit diagonal").
    Eigen::VectorXd diag = reconstructed.diagonal();
    for (Eigen::Index i = 0; i < n; ++i) {
        if (!(diag(i) > 0.0)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kNumericFailure,
                "RMT reconstruction produced a non-positive diagonal entry - denoising is not "
                "well-defined for this input",
                "index " + std::to_string(i)));
        }
    }
    Eigen::VectorXd inv_std = diag.array().sqrt().inverse();
    Eigen::MatrixXd denoised = inv_std.asDiagonal() * reconstructed * inv_std.asDiagonal();

    denoised = (denoised + denoised.transpose()) / 2.0;
    for (Eigen::Index i = 0; i < n; ++i) denoised(i, i) = 1.0;

    int num_signal = static_cast<int>(n) - bulk_count;
    return RmtResult{std::move(denoised), lambda_plus, lambda_minus, num_signal};
}

} // namespace gm::geometry
