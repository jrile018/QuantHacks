#pragma once

// Classical (metric) MDS via double-centering (ADR-010 chose this over
// UMAP/t-SNE specifically for determinism and global-distance
// preservation - both required for Procrustes alignment, procrustes.hpp,
// to be meaningful frame to frame).

#include <gm-core/error.hpp>

#include <Eigen/Dense>

#include <vector>

namespace gm::geometry {

struct MdsResult {
    Eigen::MatrixXd coordinates;         // N x k
    std::vector<double> eigenvalues_used;  // the k eigenvalues the coordinates were built from,
                                            // largest first (before any negative-eigenvalue clipping)
    int num_negative_clipped;              // how many of the k were negative and clipped to a
                                            // zero-contribution column (non-Euclidean input distances)
};

/// `distance` must be square, symmetric, with a zero diagonal (as
/// produced by mantegna_distance()). `k` is the embedding dimension
/// (ADR §6.2: 3 for display, up to 10 for scoring) and must satisfy
/// 1 <= k <= N. A negative eigenvalue among the top k (distances that
/// aren't exactly Euclidean, which real correlation-derived distances
/// generally aren't) contributes a zero column rather than an error or
/// an imaginary coordinate - reported via num_negative_clipped so a
/// caller can tell embedding quality degraded rather than silently
/// trusting a clipped dimension.
[[nodiscard]] Result<MdsResult> classical_mds(const Eigen::MatrixXd& distance, int k);

} // namespace gm::geometry
