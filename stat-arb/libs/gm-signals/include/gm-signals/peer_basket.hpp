#pragma once

// View C's peer basket (ADR §6.4): given a target equity's returns and
// a candidate set of k neighbour returns (selected upstream via
// gm-geometry's k-NN graph over D(t)), find non-negative weights
// summing to 1 that best explain the target's returns as a linear
// combination of the neighbours - i.e. constrained ridge regression,
// solved as a small QP via OSQP (ADR §5.2: "a tested solver beats a
// hand-rolled active set" for this).
//
// minimize   ||X w - r||^2 + lambda ||w||^2
// subject to w >= 0, sum(w) = 1
//
// where X is the T x k neighbour-return matrix and r is the T-vector
// target return series over the same fit window.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::signals {

/// `ridge_lambda` >= 0 is a small regularization term added to X'X
/// before solving, for numerical stability when neighbour returns are
/// highly collinear (a real risk here: neighbours were chosen BECAUSE
/// they are close in correlation-distance, i.e. highly correlated with
/// each other, not just with the target).
[[nodiscard]] Result<Eigen::VectorXd> fit_peer_basket_weights(const Eigen::VectorXd& target_returns,
                                                                const Eigen::MatrixXd& neighbor_returns,
                                                                double ridge_lambda = 1e-6);

} // namespace gm::signals
