#pragma once

// Ledoit-Wolf shrinkage-to-identity (ADR-009/ADR §6.1). At N~100,
// W~60-120 the sample correlation matrix is more noise than signal
// (q = N/W ~ 1); this is the first of the two required denoising steps
// (the second is RMT eigenvalue clipping, rmt.hpp) - not optional, per
// ADR-009's "non-negotiable for stability."
//
// Reference: Ledoit & Wolf (2004), "A well-conditioned estimator for
// large-dimensional covariance matrices," J. Multivariate Analysis.
// Section 2's shrinkage-to-identity-target formulas, applied here to
// the CORRELATION matrix directly: standardizing each column to unit
// variance before running the covariance-shrinkage formula makes the
// "sample covariance" being shrunk equal to the sample correlation of
// the original (unstandardized) data, so the result is a shrunk
// correlation matrix (unit diagonal) with the LW-optimal intensity -
// exactly what ADR-009 specifies ("every correlation matrix passes
// through Ledoit-Wolf shrinkage"), not a covariance-shrinkage result
// that would need a separate rescaling step.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::geometry {

struct ShrinkageResult {
    Eigen::MatrixXd correlation;  // N x N, unit diagonal
    double shrinkage_intensity;   // delta in [0, 1]; 0 = no shrinkage, 1 = pure identity target
};

/// `returns` is T x N (T >= 2). Internally standardizes each column
/// (demean + unit variance) before applying the Ledoit-Wolf formula, so
/// the result is a shrunk CORRELATION matrix, not a covariance matrix.
[[nodiscard]] Result<ShrinkageResult> ledoit_wolf_shrink_correlation(const Eigen::MatrixXd& returns);

} // namespace gm::geometry
