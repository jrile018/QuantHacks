#pragma once

// Sample correlation from a returns panel (ADR §6.1). Foundational: every
// other gm-geometry module (shrinkage, RMT, distance) consumes a
// correlation matrix this produces.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::geometry {

/// `returns` is T x N (T trading days, N assets; ADR-009's rolling
/// window W is T here). Each column is demeaned internally - callers
/// pass raw returns, not pre-centered data. Requires T >= 2 (need at
/// least two observations for a defined sample variance) and every
/// column to have nonzero variance (a constant column has an undefined
/// correlation with anything, including itself) - both are input-
/// quality problems the caller should have already screened for
/// upstream (ADR-015), not something this function should paper over
/// with a fallback value.
[[nodiscard]] Result<Eigen::MatrixXd> sample_correlation(const Eigen::MatrixXd& returns);

/// The T x N demeaned returns matrix, i.e. returns with each column's
/// mean subtracted - exposed separately because shrinkage.hpp's
/// Ledoit-Wolf estimator needs the demeaned data itself, not just the
/// resulting correlation matrix.
[[nodiscard]] Result<Eigen::MatrixXd> demean_columns(const Eigen::MatrixXd& returns);

} // namespace gm::geometry
