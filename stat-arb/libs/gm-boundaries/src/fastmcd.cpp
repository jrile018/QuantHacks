#include <gm-boundaries/fastmcd.hpp>

#include "fastmcd_detail.hpp"
#include <boost/math/distributions/chi_squared.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <numeric>
#include <random>
#include <utility>
#include <vector>

namespace gm::boundaries {
namespace detail {

// Exposed purely so the acceptance-region arithmetic can be asserted
// exactly rather than probed statistically. The off-by-one this
// replaced (`>` instead of `>=`) skews residue 0 by ~1e-7 at 2^32 -
// far too small for any feasible sampling test to detect, which is
// exactly why the original bug survived a review that only ran the
// estimator. The invariant below is exact and checkable: the number of
// accepted generator outputs must be a whole multiple of `bound`, or
// some residue is over-represented.
std::uint32_t portable_bounded_random_accept_limit(std::uint32_t bound) {
    if (bound <= 1u) return 0u;
    constexpr std::uint32_t kRngMax = std::mt19937::max();
    return kRngMax - (kRngMax % bound);
}

// Portable, unbiased bounded random index from a std::mt19937's raw
// output.
//
// The rejection bound is `val >= limit`, NOT `val > limit`. limit is the
// largest multiple of `bound` that fits in the generator's range, so the
// half-open interval [0, limit) holds exactly limit/bound whole cycles of
// residues and every residue is equally likely. Accepting `val == limit`
// (the earlier `>` form) admits one extra value whose residue is always
// 0, over-representing index 0 on every draw. A third review caught this
// by enumerating a 4-bit generator exhaustively: with `>` and bound=3 the
// residue counts were (6,5,5); with `>=` they are (5,5,5). At 2^32 the
// skew is ~1e-7 relative and changes no current fit, but this routine's
// entire reason to exist is bit-exact cross-platform reproducibility, so
// "too small to matter" is not the standard it is held to.
//
// Note also that for bounds where 2^32 is an exact multiple of `bound`
// (3, 5, 15, 17, 257, ...) limit == kRngMax under the old arithmetic and
// the loop never rejected at all, silently degrading to plain modulo
// bias. Both Fisher-Yates passes below draw bounds of 3 and 5 routinely. std::mt19937's own generated sequence IS exactly specified by
// the standard given a seed - but std::shuffle (and std::uniform_int_
// distribution, which a hand-rolled Fisher-Yates would naturally reach
// for instead) both consume that sequence via an IMPLEMENTATION-DEFINED
// algorithm, so libstdc++ and MSVC's STL produce different permutations
// from the identical seeded engine. The second Opus review measured this
// directly: substituting one standards-conforming shuffle for another
// changed the fit on 80.62% of real frames, with per-point depth deltas
// up to 571 - a real cross-platform reproducibility break for a project
// whose CMakePresets.json explicitly targets both linux-gcc and
// windows-msvc. Rejection sampling on the RAW rng() output avoids any
// library-level algorithm choice, using only the portable part of the
// standard.
std::uint32_t portable_bounded_random(std::mt19937& rng, std::uint32_t bound) {
    if (bound <= 1u) return 0u;
    constexpr std::uint32_t kRngMax = std::mt19937::max(); // exactly 2^32-1, portable
    std::uint32_t limit = kRngMax - (kRngMax % bound);
    std::uint32_t val;
    do {
        val = static_cast<std::uint32_t>(rng());
    } while (val >= limit);
    return val % bound;
}

// Picks h of the n row indices for one C-step starting point via a
// portable Fisher-Yates shuffle (see portable_bounded_random above).
// h = (n+p+1)/2 is always > n/2, so any scheme striding by n/h
// degenerates to stride=1 (integer division) regardless of seed - the
// bug this replaced, where every trial started from the identical
// subset. A seed derived from the data itself (order-invariant, XORed
// per trial) keeps this reproducible for a given row order without
// depending on wall-clock or external entropy (ADR-003).
std::vector<int> deterministic_h_subset(int n, int h, int trial_num, std::uint32_t seed) {
    std::vector<int> indices(static_cast<std::size_t>(n));
    std::iota(indices.begin(), indices.end(), 0);
    std::mt19937 rng(seed ^ (static_cast<std::uint32_t>(trial_num) * 0x9E3779B9u + 1u));
    for (int i = n - 1; i > 0; --i) {
        std::uint32_t j = portable_bounded_random(rng, static_cast<std::uint32_t>(i) + 1u);
        std::swap(indices[static_cast<std::size_t>(i)], indices[static_cast<std::size_t>(j)]);
    }
    indices.resize(static_cast<std::size_t>(h));
    std::sort(indices.begin(), indices.end());
    return indices;
}

}  // namespace detail

namespace {
// A second Opus review (independent, real-data verification, not just
// reading the diff) found the first attempt at numerical hardening here
// was wrong in two ways:
//  (A) kMinEigenvalue=1e-6, checked INSIDE the C-step's per-iteration
//      compute_mcd_statistics(), silently truncated the C-step early on
//      78% of real View A frames - 40% of accepted fits did ZERO
//      concentration steps, returning an unconverged, effectively
//      arbitrary covariance rather than the actual MCD optimum.
//  (B) the post-hoc condition-number reject (checked, not enforced)
//      still let condition numbers up to ~1.9e5 through - the floor
//      ITSELF pinned the smallest eigenvalue near 2.4e-6, so the
//      "safety check" was producing exactly the marginal, barely-passing
//      cases it existed to catch, just less extremely (depth 638 instead
//      of 57594 on the same failure mode: >99% of the Mahalanobis
//      distance from a single near-null eigendirection).
//
// Fixed by separating two different jobs that were conflated under one
// constant:
//  - kSingularityGuard (1e-12): a bare "is this literally singular"
//    floor used ONLY inside the C-step's own iterative re-subsetting
//    (which needs to invert the CURRENT candidate covariance to rank
//    points for the next iteration - a truly singular matrix there
//    would produce NaN/Inf and corrupt the search, not just an
//    ill-conditioned but still meaningful ranking). This floor is far
//    below anything a real, meaningful covariance ever approaches, so
//    it does not block genuine C-step convergence.
//  - Condition-number regularization, applied EXACTLY ONCE to the final
//    selected fit (see fit_fastmcd below): eigenvalues are floored
//    relative to that same fit's own largest eigenvalue and the
//    covariance is reconstructed from the floored spectrum. This
//    GUARANTEES a bounded condition number by construction - there is
//    no threshold left to "barely pass" the way a checked-then-rejected
//    gate can.
constexpr double kSingularityGuard = 1e-12;
constexpr double kCstepTolerance = 1e-9;
constexpr int kMaxCstepIterations = 100;
constexpr int kNumInitialTrials = 5;

// Relative floor applied to the C-step's internal re-subsetting inverse.
// This is search-internal bookkeeping, not the returned answer, so it
// only has to keep the inverse finite and usable; it is expressed as a
// fraction of the largest eigenvalue so that it means the same thing
// whatever units the input happens to be in.
constexpr double kCstepInverseConditionFloor = 1e-12;

// Scale-invariant, order-invariant seed.
//
// The values are normalized by the largest absolute value in the column
// before their bits are hashed. Without that, rescaling the input - the
// same cloud expressed in different units - produces entirely different
// double bit patterns, hence a different seed, hence different trial
// starting subsets, hence a different local optimum from the C-step
// search. A regression test in this library caught exactly that: the
// same Gaussian cloud fitted at scale 1 and at scale 1e-6 returned
// locations differing by 1.10 after dividing the scale back out.
//
// MCD is defined to be affine equivariant, so a fit that changes when
// the units change is wrong on the estimator's own terms - and this
// project's determinism requirement (ADR-003) is about reproducing a
// result, which a unit-dependent seed quietly undermines.
//
// Scope, stated honestly: this buys invariance to SCALING of the first
// column only. FastMCD is a heuristic search over random starts, so
// full affine equivariance is not achievable by seeding alone and is
// not claimed here.
std::uint32_t compute_data_seed(const Eigen::MatrixXd& points) {
    std::vector<double> sorted_first_col(static_cast<std::size_t>(points.rows()));
    for (int i = 0; i < points.rows(); ++i) {
        sorted_first_col[static_cast<std::size_t>(i)] = points(i, 0);
    }
    double max_abs = 0.0;
    for (double v : sorted_first_col) {
        max_abs = std::max(max_abs, std::abs(v));
    }
    if (max_abs > 0.0 && std::isfinite(max_abs)) {
        for (double& v : sorted_first_col) {
            v /= max_abs;
        }
    }
    std::sort(sorted_first_col.begin(), sorted_first_col.end());
    std::uint32_t hash = 0;
    for (double val : sorted_first_col) {
        std::uint32_t bits = 0;
        std::memcpy(&bits, &val, std::min(sizeof(bits), sizeof(val)));
        hash ^= bits;
        hash = (hash << 5) | (hash >> 27);
    }
    return hash;
}


struct McdCandidate {
    Eigen::VectorXd location;
    Eigen::MatrixXd covariance;
    // The h-subset this candidate's location/covariance were computed
    // from. Needed downstream because the Ledoit-Wolf intensity is
    // estimated from the actual observations, not from the covariance
    // matrix alone.
    std::vector<int> subset;
    double log_determinant;
    int converged_iterations;
};

// Only rejects a subset whose covariance is genuinely, numerically
// singular (see kSingularityGuard above) - NOT merely ill-conditioned.
// Ill-conditioning is handled once, on the final selected fit, by
// regularization rather than by rejecting candidates mid-search.
bool compute_mcd_statistics(const Eigen::MatrixXd& points, const std::vector<int>& subset,
                            Eigen::VectorXd& location, Eigen::MatrixXd& covariance) {
    int h = static_cast<int>(subset.size());
    int p = static_cast<int>(points.cols());
    Eigen::MatrixXd subset_matrix(h, p);
    for (int i = 0; i < h; ++i) {
        subset_matrix.row(i) = points.row(static_cast<Eigen::Index>(subset[static_cast<std::size_t>(i)]));
    }
    location = subset_matrix.colwise().mean();
    Eigen::MatrixXd centered = subset_matrix.rowwise() - location.transpose();
    covariance = (centered.transpose() * centered) / static_cast<double>(h - 1);
    covariance = ((covariance + covariance.transpose()) / 2.0).eval();
    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(covariance);
    if (solver.info() != Eigen::Success) return false;
    // Relative, not absolute. An absolute 1e-12 floor rejects data purely
    // for being expressed in small units: a third review measured the
    // same well-conditioned Gaussian cloud (cond ~3.8) accepted at scale
    // 1e-5 and rejected as "singular" at 1e-6, and a cond-100 cloud
    // accepted at 1e-2 and rejected at 1e-3. That breaks the affine
    // equivariance MCD is defined by, and puts a silent cliff under the
    // embedding that moves if its coordinates are ever rescaled. Scaling
    // the tolerance by the largest eigenvalue makes the test
    // scale-invariant and is the standard numerical rank criterion.
    double lambda_max = solver.eigenvalues()(p - 1);
    if (!(lambda_max > 0.0) || !std::isfinite(lambda_max)) return false;
    double rank_tolerance = lambda_max * static_cast<double>(std::max(h, p))
                            * std::numeric_limits<double>::epsilon();
    if (!(solver.eigenvalues()(0) > rank_tolerance)) return false;
    return true;
}

// Ledoit-Wolf shrinkage of an MCD h-subset covariance toward a
// scaled-identity target, with the intensity ESTIMATED FROM THE DATA
// rather than picked as a constant (Ledoit & Wolf 2004, Section 2).
//
// This is the covariance analogue of gm-geometry's
// ledoit_wolf_shrink_correlation (ADR section 6.1 / ADR-009). It is
// implemented here rather than reused from there because that function
// consumes a raw returns panel and produces a unit-diagonal CORRELATION
// matrix - a different input and a different output - and because
// gm-boundaries does not otherwise depend on gm-geometry; a numerical
// bug-fix is not the place to introduce that dependency edge.
//
// One honest caveat on the statistics: the classical LW intensity is
// derived for the sample covariance of an i.i.d. draw. The h-subset here
// is not an i.i.d. draw - it is the deliberately selected
// lowest-determinant half of the data - so delta is an approximation in
// this setting, not the provably optimal intensity. It is nonetheless a
// quantity computed FROM the data with a published derivation, which is
// the property the constant it replaces did not have.
struct ShrinkageOutcome {
    Eigen::MatrixXd covariance;
    double intensity; // delta in [0, 1]; 0 = untouched sample covariance
};

ShrinkageOutcome ledoit_wolf_shrink_covariance(const Eigen::MatrixXd& points,
                                               const std::vector<int>& subset,
                                               const Eigen::VectorXd& location,
                                               const Eigen::MatrixXd& sample_cov) {
    const int p = static_cast<int>(sample_cov.rows());
    const int m = static_cast<int>(subset.size());
    const double pd = static_cast<double>(p);

    // Target: the scaled identity carrying the same average variance.
    const double mu = sample_cov.trace() / pd;
    const Eigen::MatrixXd target = mu * Eigen::MatrixXd::Identity(p, p);

    // d^2 = how far the sample covariance is from that target.
    const double d2 = (sample_cov - target).squaredNorm() / pd;

    // b^2 = the sampling error in the sample covariance itself,
    // estimated from the dispersion of the per-observation outer
    // products around it.
    double b_bar2 = 0.0;
    for (int k = 0; k < m; ++k) {
        Eigen::VectorXd dev =
            points.row(static_cast<Eigen::Index>(subset[static_cast<std::size_t>(k)])).transpose() - location;
        Eigen::MatrixXd outer = dev * dev.transpose();
        b_bar2 += (outer - sample_cov).squaredNorm() / pd;
    }
    b_bar2 /= static_cast<double>(m) * static_cast<double>(m);

    // b^2 is capped at d^2, which caps delta at 1 (pure target).
    const double b2 = std::min(b_bar2, d2);
    double delta = (d2 > 0.0) ? (b2 / d2) : 0.0;
    if (!(delta >= 0.0)) delta = 0.0;
    if (delta > 1.0) delta = 1.0;

    Eigen::MatrixXd shrunk = delta * target + (1.0 - delta) * sample_cov;
    shrunk = ((shrunk + shrunk.transpose()) / 2.0).eval();
    return ShrinkageOutcome{std::move(shrunk), delta};
}

// log_determinant here is always 0.5 * sum(log(eigenvalues)) = log(sqrt(det)),
// i.e. log(det)/2, NOT log(det). Every comparison and consumer of this field
// within this file is consistent about that convention.
McdCandidate run_cstep_trial(const Eigen::MatrixXd& points, const std::vector<int>& initial_subset) {
    int n = static_cast<int>(points.rows());
    int p = static_cast<int>(points.cols());
    int h = (n + p + 1) / 2;
    McdCandidate candidate;
    candidate.converged_iterations = 0;
    candidate.log_determinant = std::numeric_limits<double>::max();
    std::vector<int> current_subset = initial_subset;
    if (static_cast<int>(current_subset.size()) != h) {
        current_subset.resize(static_cast<std::size_t>(h));
    }
    for (int iter = 0; iter < kMaxCstepIterations; ++iter) {
        Eigen::VectorXd location;
        Eigen::MatrixXd covariance;
        if (!compute_mcd_statistics(points, current_subset, location, covariance)) {
            // Only reached on genuine singularity now (kSingularityGuard,
            // 1e-12) - real-data measurement after this fix: this path
            // is essentially never taken by real frames (see commit
            // message for the real before/after truncation-rate numbers).
            return candidate;
        }
        double prev_log_det = candidate.log_determinant;
        Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(covariance);
        // Checked BEFORE any of this solver's results are read. It used
        // to be checked ~20 lines further down, by which point
        // log_determinant, location and covariance had already been
        // populated from a failed decomposition's garbage eigenvalues -
        // satisfying ADR-019's "every eigendecomposition checks
        // convergence status" only nominally.
        if (solver.info() != Eigen::Success) return candidate;
        candidate.log_determinant = 0.5 * solver.eigenvalues().array().log().sum();
        // Keep the candidate's location/covariance in sync with whatever
        // produced this log-determinant on EVERY iteration, not just on
        // convergence - a C-step that hits kMaxCstepIterations without
        // meeting the tolerance must still return a valid (location,
        // covariance) pair matching its last log_determinant, not the
        // default-constructed empty matrices McdCandidate started with.
        candidate.location = location;
        candidate.covariance = covariance;
        candidate.subset = current_subset;
        if (iter > 0 && std::abs(candidate.log_determinant - prev_log_det) < kCstepTolerance) {
            candidate.converged_iterations = iter + 1;
            return candidate;
        }
        // Re-subsetting inverse: guard only against literal singularity
        // (kSingularityGuard) here too, for the same reason as above -
        // this is search-internal bookkeeping, not the final answer.
        // Relative floor, for the same reason the rank test in
        // compute_mcd_statistics is relative. An absolute 1e-12 floor
        // here silently rewrote the spectrum whenever the data happened
        // to be expressed in small units - at an input scale of 1e-6 the
        // eigenvalues land ON the floor, so the re-subsetting distances
        // that choose the next C-step subset were computed from a
        // fabricated inverse and the search converged somewhere else
        // entirely. A regression test in this library caught it: the
        // same cloud at scale 1 and 1e-6 gave locations differing by
        // 1.10 after dividing the scale back out. Scaling the floor by
        // the largest eigenvalue makes the step scale-invariant, which
        // is what affine equivariance requires.
        Eigen::VectorXd eigs = solver.eigenvalues();
        double eig_max = eigs(eigs.size() - 1);
        double cstep_floor = (eig_max > 0.0 && std::isfinite(eig_max))
                                 ? eig_max * kCstepInverseConditionFloor
                                 : kSingularityGuard;
        for (Eigen::Index i = 0; i < eigs.size(); ++i) {
            eigs(i) = std::max(eigs(i), cstep_floor);
        }
        Eigen::VectorXd inv_eigs = eigs.array().inverse();
        Eigen::MatrixXd inv_cov = solver.eigenvectors() * inv_eigs.asDiagonal() * solver.eigenvectors().transpose();
        std::vector<std::pair<double, int>> distances;
        distances.reserve(static_cast<std::size_t>(n));
        for (int i = 0; i < n; ++i) {
            Eigen::VectorXd diff = points.row(i).transpose() - location;
            double mahal_sq = diff.transpose() * inv_cov * diff;
            distances.emplace_back(mahal_sq, i);
        }
        std::sort(distances.begin(), distances.end());
        current_subset.clear();
        for (int i = 0; i < h; ++i) {
            current_subset.push_back(distances[static_cast<std::size_t>(i)].second);
        }
    }
    candidate.converged_iterations = kMaxCstepIterations;
    return candidate;
}
}

namespace detail {

// Per-trial candidate summaries, exposed so the selection rule itself
// can be asserted. Testing "does it take the minimum determinant?"
// through the public API is only meaningful if the trials actually
// converge to DIFFERENT candidates - otherwise min and max coincide and
// any such test is vacuous, which is precisely how an earlier version of
// this library's regression test passed against the very bug it named.
std::vector<TrialSummary> trial_summaries(const Eigen::MatrixXd& points) {
    std::vector<TrialSummary> out;
    int n = static_cast<int>(points.rows());
    int p = static_cast<int>(points.cols());
    if (p < 1 || n < p + 1 || !points.allFinite()) return out;
    int h = (n + p + 1) / 2;
    std::uint32_t seed = compute_data_seed(points);
    for (int trial = 0; trial < kNumInitialTrials; ++trial) {
        auto initial_subset = deterministic_h_subset(n, h, trial, seed);
        if (static_cast<int>(initial_subset.size()) < h) continue;
        auto candidate = run_cstep_trial(points, initial_subset);
        if (candidate.covariance.size() == 0) continue;
        out.push_back(TrialSummary{candidate.log_determinant, candidate.location});
    }
    return out;
}

}  // namespace detail

Result<FastMCDFit> fit_fastmcd(const Eigen::MatrixXd& points) {
    int n = static_cast<int>(points.rows());
    int p = static_cast<int>(points.cols());
    if (p < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "points has zero columns",
            "n=" + std::to_string(n)));
    }
    // A third review found NaN/Inf input produced a clean-looking
    // SUCCESS: the poisoned row's Mahalanobis distance sorts to the end
    // of the C-step's re-subsetting and is quietly dropped, so NaN was
    // acting as an implicit "discard this row" sentinel - exactly what
    // ADR-019 forbids ("NaN is never a sentinel"). It also fed NaN into
    // two std::sort comparators, which breaks strict weak ordering and
    // is undefined behaviour regardless of whether it happens to crash.
    if (!points.allFinite()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kValidationFailure,
            "FastMCD: input contains non-finite values (NaN or Inf)",
            "n=" + std::to_string(n) + ", p=" + std::to_string(p)));
    }
    if (n < p + 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "fewer points than degrees of freedom + 1",
            "n=" + std::to_string(n) + ", p=" + std::to_string(p)));
    }
    int h = (n + p + 1) / 2;
    std::uint32_t seed = compute_data_seed(points);
    McdCandidate best_candidate;
    // MCD selects the MINIMUM determinant h-subset - that is the entire
    // definition of the estimator.
    best_candidate.log_determinant = std::numeric_limits<double>::max();
    bool found_any = false;
    for (int trial = 0; trial < kNumInitialTrials; ++trial) {
        auto initial_subset = detail::deterministic_h_subset(n, h, trial, seed);
        if (static_cast<int>(initial_subset.size()) < h) {
            continue;
        }
        auto candidate = run_cstep_trial(points, initial_subset);
        if (candidate.covariance.size() == 0) {
            continue; // this trial never produced a valid statistics computation
        }
        if (!found_any || candidate.log_determinant < best_candidate.log_determinant) {
            best_candidate = std::move(candidate);
            found_any = true;
        }
    }
    if (!found_any) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "FastMCD: no valid candidate found across all trials",
                                               "n=" + std::to_string(n) + ", p=" + std::to_string(p)
                                                   + ", h=" + std::to_string(h)
                                                   + ", trials=" + std::to_string(kNumInitialTrials)));
    }
    // Consistency factor (Rousseeuw & Van Driessen 1999 Sec 3.2; Croux &
    // Haesbroeck 1999): the raw MCD covariance from an h-of-n subset
    // systematically underestimates the true covariance under a Gaussian
    // model, by a known factor depending only on p and the subset
    // fraction alpha = h/n. c = alpha / F_{chisq(p+2)}(chi2_quantile(p, alpha)).
    // This is a pure positive scalar multiplier, so it does not change
    // best_candidate.covariance's condition number - the regularization
    // below is equally valid applied before or after; applied after,
    // matching the previous code's structure.
    double alpha_fraction = static_cast<double>(h) / static_cast<double>(n);
    double consistency_factor = 1.0;
    // h == n exactly when n == p+1 (the documented minimum input), making
    // alpha_fraction 1.0 and quantile(chi2, 1.0) overflow - so the
    // smallest input the API explicitly admits always failed, with a
    // misleading "consistency-factor computation failed" message. At
    // alpha = 1 the h-subset IS the full sample, so there is no
    // subsetting bias to correct and the factor is exactly 1.
    if (alpha_fraction >= 1.0) {
        consistency_factor = 1.0;
    } else try {
        boost::math::chi_squared_distribution<double> chi2_p(static_cast<double>(p));
        double chi2_quantile = boost::math::quantile(chi2_p, alpha_fraction);
        boost::math::chi_squared_distribution<double> chi2_p2(static_cast<double>(p) + 2.0);
        double denom = boost::math::cdf(chi2_p2, chi2_quantile);
        if (denom > 0.0) {
            consistency_factor = alpha_fraction / denom;
        }
    } catch (const std::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "FastMCD: consistency-factor computation failed", e.what()));
    }
    Eigen::MatrixXd reweighted_cov = best_candidate.covariance * consistency_factor;
    reweighted_cov = ((reweighted_cov + reweighted_cov.transpose()) / 2.0).eval();
    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> final_solver(reweighted_cov);
    if (final_solver.info() != Eigen::Success) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "FastMCD: reweighted covariance eigendecomposition failed"));
    }
    // Ledoit-Wolf shrinkage, replacing this file's earlier hard
    // eigenvalue floor at max_eig / 100.
    //
    // The floor was not wrong as a MECHANISM - a third review confirmed
    // it bounded the condition number by construction, with 0 violations
    // across 4000 fuzz cases and 17818 real fits. It was wrong as a
    // CLAIM. The same review measured two things that invalidated the
    // reasoning around it:
    //
    //   * 86.6% of real View A fits had at least one eigenvalue replaced
    //     by the constant, and 29.7% had two of three replaced. The
    //     "regularizer" was therefore the dominant estimator rather than
    //     a rare safety net, and a large share of the returned shape was
    //     fabricated rather than estimated.
    //   * Consequently the depths this file previously reported as
    //     measurements were functions of the constant: the before/after
    //     pair 1712 -> 169.79 is a ratio of 10.08, which is exactly
    //     sqrt(1e4 / 100). Citing them as evidence the fix worked was
    //     circular reasoning.
    //
    // A further claim in that revision - that the constant reflected
    // "~42 effective points in 3 dimensions" - described a sample size
    // that does not exist anywhere in this pipeline. View B fits 756
    // points; View A fits 81.
    //
    // Ledoit-Wolf shrinks toward a scaled-identity target with an
    // intensity estimated FROM THE DATA (Ledoit & Wolf 2004 Sec 2) -
    // which is what ADR section 6.1 / ADR-009 already specify for this
    // project's correlation matrices. It is smooth rather than a cliff,
    // and its strength is a measurement rather than a choice. The
    // intensity travels out in the fit so callers can see how much
    // correction was applied.
    ShrinkageOutcome shrunk = ledoit_wolf_shrink_covariance(
        points, best_candidate.subset, best_candidate.location, reweighted_cov);

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> shrunk_solver(shrunk.covariance);
    if (shrunk_solver.info() != Eigen::Success) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
            "FastMCD: shrunk covariance eigendecomposition failed",
            "n=" + std::to_string(n) + ", p=" + std::to_string(p)
                + ", delta=" + std::to_string(shrunk.intensity)));
    }
    Eigen::VectorXd eigs = shrunk_solver.eigenvalues();
    double max_eig = eigs(p - 1);
    if (!(max_eig > 0.0) || !std::isfinite(max_eig)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
            "FastMCD: covariance has no well-determined direction (degenerate in every axis)",
            "n=" + std::to_string(n) + ", p=" + std::to_string(p)
                + ", max_eig=" + std::to_string(max_eig)));
    }

    // Numerical backstop, NOT a statistical choice.
    //
    // Shrinkage does not by itself bound the condition number: the
    // shrunk spectrum is (1-d)*lambda_i + d*mu, so the ratio is bounded
    // by roughly p/d, which is only finite once d > 0. When the data
    // genuinely supports a wide spectrum, LW correctly returns a small
    // d and the matrix stays ill-conditioned - which is the statistically
    // right answer and the numerically dangerous one.
    //
    // This ceiling exists solely so the returned inverse does not become
    // numerical noise. It is sized to double precision's usable range
    // (eps ~ 2.2e-16; a ratio of 1e8 still leaves ~8 significant digits
    // in the smallest direction), NOT to any claim about what is
    // statistically estimable. If it turns out to engage often, that is
    // a finding about the upstream embedding producing near-collinear
    // point clouds - and it is reported through the fit rather than
    // silently absorbed, which is precisely what the previous revision
    // failed to do.
    constexpr double kNumericalConditionCeiling = 1e8;
    const double eig_floor = max_eig / kNumericalConditionCeiling;
    const bool backstop_engaged = (eigs(0) < eig_floor);
    Eigen::VectorXd final_eigs = eigs.array().max(eig_floor);

    Eigen::MatrixXd final_cov =
        shrunk_solver.eigenvectors() * final_eigs.asDiagonal() * shrunk_solver.eigenvectors().transpose();
    final_cov = ((final_cov + final_cov.transpose()) / 2.0).eval();
    Eigen::VectorXd inv_eigs = final_eigs.array().inverse();
    Eigen::MatrixXd inv_cov =
        shrunk_solver.eigenvectors() * inv_eigs.asDiagonal() * shrunk_solver.eigenvectors().transpose();
    inv_cov = ((inv_cov + inv_cov.transpose()) / 2.0).eval();

    double max_mahal_sq = 0.0;
    for (int i = 0; i < n; ++i) {
        Eigen::VectorXd diff = points.row(i).transpose() - best_candidate.location;
        double mahal_sq = diff.transpose() * inv_cov * diff;
        max_mahal_sq = std::max(max_mahal_sq, mahal_sq);
    }
    return FastMCDFit{std::move(best_candidate.location), std::move(final_cov), std::move(inv_cov),
                      p, max_mahal_sq, shrunk.intensity, backstop_engaged};
}

Result<FastMCDScore> score_fastmcd(const FastMCDFit& fit, const Eigen::VectorXd& point, double alpha) {
    if (point.size() != fit.location.size()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "point dimension does not match fit dimension",
            "point: " + std::to_string(point.size()) + ", fit: " + std::to_string(fit.location.size())));
    }
    if (!(alpha > 0.0 && alpha < 1.0)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "alpha must be in (0, 1)"));
    }
    Eigen::VectorXd diff = point - fit.location;
    double distance_squared = diff.transpose() * fit.inv_covariance * diff;
    if (distance_squared < 0.0) distance_squared = 0.0;
    double distance = std::sqrt(distance_squared);
    double p_value = 0.0, critical_distance = 0.0;
    try {
        boost::math::chi_squared_distribution<double> chi2(static_cast<double>(fit.degrees_of_freedom));
        p_value = boost::math::cdf(boost::math::complement(chi2, distance_squared));
        double critical_distance_squared = boost::math::quantile(chi2, 1.0 - alpha);
        critical_distance = std::sqrt(critical_distance_squared);
    } catch (const std::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNumericFailure,
                                               "chi-squared distribution evaluation failed", e.what()));
    }
    double depth = distance - critical_distance;
    bool inside = depth <= 0.0;
    return FastMCDScore{distance, critical_distance, p_value, depth, inside};
}
}
