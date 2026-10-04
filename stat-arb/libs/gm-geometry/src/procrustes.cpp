#include <gm-geometry/procrustes.hpp>

namespace gm::geometry {

Result<ProcrustesResult> align(const Eigen::MatrixXd& y, const Eigen::MatrixXd& reference) {
    if (y.rows() != reference.rows() || y.cols() != reference.cols()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "y and reference must have the same shape",
            "y: " + std::to_string(y.rows()) + "x" + std::to_string(y.cols()) +
                ", reference: " + std::to_string(reference.rows()) + "x" + std::to_string(reference.cols())));
    }
    if (y.rows() < 1 || y.cols() < 1) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "y/reference must be non-empty"));
    }

    // M = y' * reference (k x k); SVD M = U S V', R* = U V' (ADR §6.2,
    // which specifically names BDCSVD). This Eigen version deprecates
    // passing compute options to the constructor - they're a template
    // parameter now.
    Eigen::MatrixXd m = y.transpose() * reference;
    Eigen::BDCSVD<Eigen::MatrixXd, Eigen::ComputeFullU | Eigen::ComputeFullV> svd(m);
    if (svd.info() != Eigen::Success) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNumericFailure, "Procrustes SVD failed to converge"));
    }

    Eigen::MatrixXd rotation = svd.matrixU() * svd.matrixV().transpose();
    Eigen::MatrixXd aligned = y * rotation;

    double raw_residual = (aligned - reference).norm();  // Frobenius norm
    double reference_scale = reference.norm();

    double normalized_residual;
    if (reference_scale > 0.0) {
        normalized_residual = raw_residual / reference_scale;
    } else {
        // reference is exactly the zero matrix - a degenerate case
        // (e.g. a single-point or origin-centered-to-nothing frame)
        // where "normalized by scale" is undefined. Falling back to the
        // raw residual means a real misalignment is never silently
        // reported as 0 just because the denominator vanished.
        normalized_residual = raw_residual;
    }

    return ProcrustesResult{std::move(aligned), std::move(rotation), raw_residual, normalized_residual};
}

} // namespace gm::geometry
