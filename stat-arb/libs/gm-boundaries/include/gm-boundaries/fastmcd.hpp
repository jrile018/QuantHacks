#pragma once

// Robust Minimum Covariance Determinant (FastMCD) estimator (ADR-011 phase 2)
//
// Implements Rousseeuw & Van Driessen (1999): "A fast algorithm for the
// minimum covariance determinant estimator" - finds the h-subset of n points
// (where h = floor((n+p+1)/2), C++ integer division) whose covariance matrix has the smallest
// determinant, yielding a robust location/covariance estimate resistant to
// ~50% contamination.
//
// KNOWN BEHAVIOR ON NON-STATIONARY (View B) DATA - not a bug, verified
// against real data: MCD's contamination model assumes i.i.d. draws
// from an elliptical distribution with a minority of outliers. View B
// (apps/gm-boundaries/main.cpp) feeds it a single ticker's own trailing
// 756-day trajectory through the embedding, which is a genuinely
// trending time series, not i.i.d. data. When a ticker has drifted
// meaningfully over that window, MCD's minimum-determinant h-subset
// naturally concentrates on whichever sub-period was most stable/tight
// - which, for a drifting series, is often NOT the most recent period -
// so "today" can score as extremely far from that robust core even
// though the point is unremarkable by the full-window's own classical
// (non-robust) statistics. Measured on the real 2010-2026 run: ticker T
// on 2014-06-25, a well-conditioned fit (eigenvalue condition number
// 276 - nowhere near the ill-conditioning this file otherwise guards
// against) with a real early-to-late quarter drift of 0.14 in embedding
// units, scored FastMCD distance=201.2 against a classical
// full-window Mahalanobis distance of only 6.2 from the same data. This
// is real MCD behavior on trending input, not a numerical defect - it
// is exactly the kind of estimator disagreement ADR-011 calls a
// first-class output, not something to suppress. Whether View B's
// FastMCD sensitivity to drift is a genuinely useful early-regime-shift
// signal or systematically over-sensitive is an empirical question for
// the ADR-013 reversion study to answer, not something this file should
// pre-judge by, say, quietly capping depth or re-weighting for
// staleness - that would be a modeling decision disguised as a bug fix.
//
// DETERMINISM RESOLUTION (ADR-003 conflict with classical algorithm):
// The published FastMCD uses random initial h-subsets in the C-step.
// To maintain bit-reproducibility (ADR-003: "no wall-clock, no unseeded RNG
// in production paths"), we:
// 1. Derive a fixed seed from a canonical (sorted) representation of the
//    data's first column via a deterministic hash function.
// 2. Use a std::mt19937 seeded from that hash (XOR the trial number) to
//    shuffle the row indices and take the first h as each trial's
//    starting subset - a seeded, fully reproducible PRNG, not an
//    unseeded/wall-clock one, so this stays within ADR-003's rule while
//    actually giving each of the 5 trials a genuinely different starting
//    point (an earlier stride-based scheme here degenerated to the
//    identical subset on every trial, since h = (n+p+1)/2 is always more
//    than half of n, making its stride computation always resolve to 1 -
//    caught by an independent audit against real data, not by the
//    original unit tests, whose tiny fixtures never exercised more than
//    one meaningfully different h-subset either way).
// 3. Run the C-step concentration procedure identically on each subset.
// 4. Select the MINIMUM-determinant result across trials - the actual
//    definition of MCD (a maximum-determinant selection bug, also only
//    caught against real data, was silently picking the LEAST robust of
//    the candidates).
//
// This preserves the algorithm's robustness (multiple starting points, hill
// climbing to a local optimum, selecting the global best found) while
// guaranteeing run-to-run reproducibility for a given, fixed row order of
// the input data - every caller in this codebase builds that input from a
// std::map, so this is the reproducibility this project actually needs.
// It does NOT guarantee the estimate is invariant under an arbitrary
// permutation of otherwise-identical rows (the seed hash is
// order-invariant, but the row indices it seeds a shuffle over are not -
// two different orderings of the same point set select different actual
// points into the same numeric index positions). True permutation
// invariance would require either an exhaustive search over all
// C(n,h) subsets or a selection criterion defined directly on the point
// SET rather than on row position, which is a materially bigger change
// than this codebase's actual (fixed-order) usage requires.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::boundaries {

struct FastMCDFit {
    Eigen::VectorXd location;       // p, the robust center estimate
    Eigen::MatrixXd covariance;     // p x p, the robust covariance estimate
    Eigen::MatrixXd inv_covariance; // precomputed inverse for fast scoring
    int degrees_of_freedom;         // p
    double max_mahalanobis_squared_over_all_points;  // diagnostic: max M-distance over ALL n rows
    // Ledoit-Wolf shrinkage intensity actually applied to this fit, in
    // [0, 1]. Reported rather than hidden: an earlier revision applied a
    // fixed eigenvalue floor that turned out to dominate 86.6% of real
    // fits while presenting itself as a rare safety net, which was only
    // discovered by an external review re-measuring the spectra. A
    // caller can now see how much of the returned shape was estimated
    // and how much was shrunk toward the target.
    double shrinkage_intensity;
    // True if the numerical backstop below the shrinkage had to engage
    // for this fit (see kNumericalConditionCeiling in fastmcd.cpp).
    // Expected to be rare; if it is not, that is a finding about the
    // upstream embedding, not a detail to leave unreported.
    bool numerical_backstop_engaged;
};

struct FastMCDScore {
    double distance;      // Mahalanobis distance (not squared) in robust space
    double critical_distance; // the chi-squared-quantile distance at `alpha`
    double p_value;        // chi-squared survival probability at distance^2, df=p
    double depth;           // distance - critical_distance: negative=inside, positive=outside
    bool inside;
};

/// `points` is N x k (N >= k+1 required; typically k is 2-5 for boundary scoring).
/// Every dimension's variance must be nonzero.
/// 
/// Returns the robust location and covariance estimate, along with the inverse
/// covariance precomputed for efficient scoring.
[[nodiscard]] Result<FastMCDFit> fit_fastmcd(const Eigen::MatrixXd& points);

/// Score a single point under the robust fit.
/// `alpha` is the boundary's exceedance probability (default 0.05).
[[nodiscard]] Result<FastMCDScore> score_fastmcd(const FastMCDFit& fit,
                                                    const Eigen::VectorXd& point,
                                                    double alpha = 0.05);

} // namespace gm::boundaries
