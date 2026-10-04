#pragma once

// Internal helpers of fastmcd.cpp, exposed ONLY so they can be tested
// directly.
//
// This header exists because of a specific review finding: the previous
// revision's "FastMCD's 5 trials use genuinely different starting
// subsets" test called the deterministic public fit_fastmcd() three
// times on identical data and asserted the results matched. That is
// structurally incapable of detecting whether the trials differ - it
// would pass identically if all five trials started from the same
// subset, which is the exact bug it was named after. Testing subset
// generation requires reaching the subset generator.
//
// Nothing outside this library's own tests should include this header.

#include <Eigen/Dense>

#include <cstdint>
#include <random>
#include <vector>

namespace gm::boundaries::detail {

/// Largest generator output NOT accepted by the rejection sampler; the
/// accepted set is [0, limit). Must be an exact multiple of `bound`.
[[nodiscard]] std::uint32_t portable_bounded_random_accept_limit(std::uint32_t bound);

/// Uniform index in [0, bound) drawn from `rng`'s raw output, using no
/// implementation-defined library algorithm.
[[nodiscard]] std::uint32_t portable_bounded_random(std::mt19937& rng, std::uint32_t bound);

/// The `trial_num`-th starting h-subset of n row indices, sorted ascending.
[[nodiscard]] std::vector<int> deterministic_h_subset(int n, int h, int trial_num, std::uint32_t seed);

struct TrialSummary {
    double log_determinant;
    Eigen::VectorXd location;
};

/// The converged candidate from each of FastMCD's initial trials.
/// Exposed so a test can assert that the estimator returns the MINIMUM
/// determinant candidate - which is only a meaningful assertion when the
/// trials genuinely differ, so a test using this should verify that too.
[[nodiscard]] std::vector<TrialSummary> trial_summaries(const Eigen::MatrixXd& points);

}  // namespace gm::boundaries::detail
