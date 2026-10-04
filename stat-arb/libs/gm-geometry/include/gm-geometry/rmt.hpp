#pragma once

// Random Matrix Theory (Marchenko-Pastur) eigenvalue denoising
// (ADR-009). The second, complementary half of the denoising pipeline
// (shrinkage.hpp is the first): eigenvalues that fall inside the
// Marchenko-Pastur "noise bulk" for the given aspect ratio q = N/T are
// replaced by their mean; eigenvalues above the bulk edge (signal,
// dominated by the market mode and genuine cluster structure) are kept.
//
// Reference: Laloux, Cizeau, Bouchaud & Potters (1999), "Noise dressing
// of financial correlation matrices."

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::geometry {

struct RmtResult {
    Eigen::MatrixXd denoised_correlation;  // N x N, unit diagonal
    double lambda_plus;                    // MP bulk upper edge, (1+sqrt(q))^2
    double lambda_minus;                   // MP bulk lower edge, (1-sqrt(q))^2 (0 if q >= 1)
    int num_signal_eigenvalues;            // count of eigenvalues kept above lambda_plus
};

/// `correlation` must be square and symmetric (as produced by
/// sample_correlation() or ledoit_wolf_shrink_correlation()). `q` is
/// N/T, the aspect ratio the correlation matrix was estimated under
/// (T = window length, N = correlation.rows()) - callers pass this
/// explicitly rather than it being inferred, since a shrunk correlation
/// matrix alone doesn't carry T with it.
[[nodiscard]] Result<RmtResult> mp_denoise(const Eigen::MatrixXd& correlation, double q);

} // namespace gm::geometry
