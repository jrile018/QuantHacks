#pragma once

// Mantegna correlation distance (ADR §6.2): d_ij = sqrt(2*(1 - rho_ij)),
// a proper metric on [0, 2]. Reference: Mantegna (1999), "Hierarchical
// structure in financial markets."

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::geometry {

/// `correlation` must be square with values in [-1, 1] and unit
/// diagonal (as produced upstream by sample_correlation() /
/// ledoit_wolf_shrink_correlation() / mp_denoise()). A correlation
/// value fractionally outside [-1, 1] due to floating-point roundoff
/// (e.g. 1.0000000000000002) is clamped rather than rejected; anything
/// outside a small tolerance of that range is a real input error, not
/// roundoff, and is rejected.
[[nodiscard]] Result<Eigen::MatrixXd> mantegna_distance(const Eigen::MatrixXd& correlation);

} // namespace gm::geometry
