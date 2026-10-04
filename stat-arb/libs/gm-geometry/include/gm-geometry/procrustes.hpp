#pragma once

// Orthogonal Procrustes alignment (ADR-010/ADR §6.2). MDS/every other
// embedding is invariant to rotation and reflection; refitting each
// frame independently makes the animation thrash even when nothing
// structural changed. This aligns one frame's embedding to the
// previous (already-aligned) frame's, and the alignment residual - the
// part rotation cannot explain - becomes the structural change metric
// (ADR-008/ADR-010's regime-change series).

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::geometry {

struct ProcrustesResult {
    Eigen::MatrixXd aligned;    // y rotated/reflected to best match reference, N x k
    Eigen::MatrixXd rotation;   // the k x k orthogonal matrix applied (R'R = I)
    double raw_residual;        // ||aligned - reference||_F
    double normalized_residual; // raw_residual / ||reference||_F (0 if reference is exactly zero
                                 // and raw_residual is also 0; otherwise raw_residual unnormalized
                                 // as a fallback so a real residual is never silently reported as 0)
};

/// `y` and `reference` must both be N x k with the same shape, N >= 1,
/// k >= 1. Solves R* = argmin_R ||y*R - reference||_F subject to
/// R'R = I via SVD of y'*reference (ADR §6.2) - this is the standard
/// orthogonal Procrustes solution and permits R to include a reflection
/// (det(R) = -1), not just a rotation; that is what "R'R = I" (rather
/// than the stricter SO(k) det(R)=+1) specifies.
[[nodiscard]] Result<ProcrustesResult> align(const Eigen::MatrixXd& y, const Eigen::MatrixXd& reference);

} // namespace gm::geometry
