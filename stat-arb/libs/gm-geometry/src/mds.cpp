#include <gm-geometry/mds.hpp>

#include <algorithm>
#include <cmath>

namespace gm::geometry {

Result<MdsResult> classical_mds(const Eigen::MatrixXd& distance, int k) {
    const Eigen::Index n = distance.rows();

    if (distance.rows() != distance.cols()) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "distance matrix must be square"));
    }
    if (n < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "empty distance matrix"));
    }
    if (k < 1 || k > n) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "k must satisfy 1 <= k <= N",
            "k=" + std::to_string(k) + ", N=" + std::to_string(n)));
    }

    // Double-centering: B = -1/2 J D^2 J, J = I - (1/N) 11^T.
    Eigen::MatrixXd d2 = distance.cwiseProduct(distance);
    Eigen::MatrixXd j =
        Eigen::MatrixXd::Identity(n, n) - Eigen::MatrixXd::Ones(n, n) / static_cast<double>(n);
    Eigen::MatrixXd b = -0.5 * j * d2 * j;
    b = (b + b.transpose()) / 2.0;  // symmetrize away floating-point drift from the two products

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(b);
    if (solver.info() != Eigen::Success) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNumericFailure, "MDS eigendecomposition failed to converge"));
    }

    // Eigen returns eigenvalues ascending; the largest k are the last k.
    Eigen::VectorXd eigenvalues = solver.eigenvalues();
    const Eigen::MatrixXd& eigenvectors = solver.eigenvectors();

    Eigen::MatrixXd coordinates(n, k);
    std::vector<double> eigenvalues_used;
    eigenvalues_used.reserve(static_cast<std::size_t>(k));
    int num_negative_clipped = 0;

    for (int col = 0; col < k; ++col) {
        Eigen::Index idx = n - 1 - col;
        double lambda = eigenvalues(idx);
        eigenvalues_used.push_back(lambda);
        if (lambda < 0.0) {
            ++num_negative_clipped;
            coordinates.col(col).setZero();
        } else {
            coordinates.col(col) = eigenvectors.col(idx) * std::sqrt(lambda);
        }
    }

    return MdsResult{std::move(coordinates), std::move(eigenvalues_used), num_negative_clipped};
}

} // namespace gm::geometry
