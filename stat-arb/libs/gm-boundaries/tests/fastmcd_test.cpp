#include <gm-boundaries/fastmcd.hpp>

// Internal helpers, reachable only for testing. Needed because subset
// generation and the RNG's acceptance arithmetic cannot be exercised
// through the deterministic public API - the failure mode that made two
// earlier "regression tests" untestable by construction.
#include "fastmcd_detail.hpp"

#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <cstdint>
#include <limits>
#include <random>
#include <string>
#include <vector>

using gm::boundaries::fit_fastmcd;
using gm::boundaries::score_fastmcd;

namespace {
constexpr double kTol = 1e-6;
}

TEST_CASE("FastMCD fit accepts sufficient points", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    CHECK(fit->degrees_of_freedom == 2);
}

TEST_CASE("FastMCD rejects fewer than p+1 points", "[fastmcd]") {
    Eigen::MatrixXd points(2, 3);
    points.setZero();
    auto fit = fit_fastmcd(points);
    REQUIRE_FALSE(fit.has_value());
    CHECK(fit.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("FastMCD rejects zero-column matrix", "[fastmcd]") {
    Eigen::MatrixXd points(5, 0);
    auto fit = fit_fastmcd(points);
    REQUIRE_FALSE(fit.has_value());
    CHECK(fit.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("FastMCD scores a point at the center as inside", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd center(2);
    center << 0.0, 0.0;
    auto score = score_fastmcd(*fit, center);
    REQUIRE(score.has_value());
    CHECK(score->inside);
    CHECK(score->depth < 0.0);
}

TEST_CASE("FastMCD scores a far point as outside", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd far_point(2);
    far_point << 100.0, 100.0;
    auto score = score_fastmcd(*fit, far_point);
    REQUIRE(score.has_value());
    CHECK_FALSE(score->inside);
    CHECK(score->depth > 0.0);
    CHECK(score->p_value < 0.01);
}

TEST_CASE("FastMCD scoring depth is monotonic along a ray", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    double prev_depth = -1e18;
    for (double d : {0.1, 1.0, 2.0, 5.0, 10.0}) {
        Eigen::VectorXd p(2);
        p << d, 0.0;
        auto score = score_fastmcd(*fit, p);
        REQUIRE(score.has_value());
        CHECK(score->depth > prev_depth);
        prev_depth = score->depth;
    }
}

// Renamed and rewritten from "FastMCD is deterministic on data in
// different order": a real-data audit found row-permutation invariance
// does NOT hold (fastmcd.hpp documents this explicitly - the seed hash
// is order-invariant, but the row indices it seeds a Fisher-Yates
// shuffle over are not, so a different order selects different actual
// points into the same numeric index positions). The old test's name
// and content asserted exactly the property the header now disclaims;
// it only "passed" because its tiny 10-point fixture happened not to
// violate its own 0.2/0.1 tolerance - real data violates it by up to
// 2.5x. What IS guaranteed, and worth a real test, is repeatability for
// a FIXED row order: the same points, called twice, must produce a
// bit-identical fit (this is the actual determinism ADR-003 requires,
// and the property every real caller in this codebase depends on,
// since they always build the training matrix in std::map order).
TEST_CASE("FastMCD is repeatable for a fixed row order", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit1 = fit_fastmcd(points);
    REQUIRE(fit1.has_value());
    auto fit2 = fit_fastmcd(points);
    REQUIRE(fit2.has_value());

    CHECK((fit1->location - fit2->location).norm() < kTol);
    CHECK((fit1->covariance - fit2->covariance).norm() < kTol);
}

TEST_CASE("FastMCD score dimension mismatch is rejected", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd bad_point(3);
    bad_point << 1, 2, 3;
    auto score = score_fastmcd(*fit, bad_point);
    REQUIRE_FALSE(score.has_value());
    CHECK(score.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("FastMCD rejects out-of-range alpha", "[fastmcd]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd p(2);
    p << 3, 6;
    CHECK_FALSE(score_fastmcd(*fit, p, 0.0).has_value());
    CHECK_FALSE(score_fastmcd(*fit, p, 1.0).has_value());
}

TEST_CASE("FastMCD fits synthetic Gaussian plus contamination", "[fastmcd]") {
    const int n = 50;
    Eigen::MatrixXd points(n, 2);

    for (int i = 0; i < 40; ++i) {
        points(i, 0) = static_cast<double>(i % 8) - 3.5;
        points(i, 1) = static_cast<double>(i / 8) - 2.5;
    }

    for (int i = 40; i < 50; ++i) {
        points(i, 0) = 10.0 + static_cast<double>(i);
        points(i, 1) = 10.0 + static_cast<double>(i);
    }

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd test_point(2);
    test_point << 0.0, 0.0;
    auto score = score_fastmcd(*fit, test_point);
    REQUIRE(score.has_value());
    CHECK(score->inside);

    Eigen::VectorXd outlier(2);
    outlier << 50.0, 50.0;
    auto outlier_score = score_fastmcd(*fit, outlier);
    REQUIRE(outlier_score.has_value());
    CHECK_FALSE(outlier_score->inside);
}

TEST_CASE("FastMCD produces valid covariance matrix", "[fastmcd]") {
    Eigen::MatrixXd points(15, 3);
    for (int i = 0; i < 15; ++i) {
        points(i, 0) = static_cast<double>(i) - 7.0;
        points(i, 1) = static_cast<double>(i) * 0.5 - 3.5 + (i % 2) * 0.3;
        points(i, 2) = -static_cast<double>(i) * 0.7 + 5.0 + (i % 3) * 0.2;
    }

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(fit->covariance);
    REQUIRE(solver.info() == Eigen::Success);

    for (int i = 0; i < fit->degrees_of_freedom; ++i) {
        CHECK(solver.eigenvalues()(i) > 1e-10);
    }
}

// Real-data audit findings, each with a dedicated regression test so
// they cannot silently regress again:

// ---------------------------------------------------------------------
// Regression tests below this line each pin a SPECIFIC bug. A previous
// revision of this file claimed exactly that and was wrong: a third
// review rebuilt the buggy implementations and ran these tests against
// them, and 13 of 14 passed. Two "regression tests" detected nothing at
// all. Each test below therefore records what it discriminates, and how
// that discrimination was checked, so the claim can be audited rather
// than taken on faith.
// ---------------------------------------------------------------------

// Bug pinned: the estimator selected the MAXIMUM-determinant candidate.
//
// Two earlier attempts at this test both passed against the bug, for the
// same underlying reason, and it is worth recording because the reason
// is not obvious:
//
//   1st attempt - a SYMMETRIC dumbbell asserting |location(0)| > 5. Both
//      lobes satisfy that, so the buggy code landed on the other lobe
//      and still passed.
//   2nd attempt - an ASYMMETRIC dumbbell asserting the SIGN of
//      location(0). Also passed against the bug. Measuring the trials
//      directly showed why: on that fixture all five trials converge to
//      the IDENTICAL candidate (log-determinant spread exactly 0.000),
//      so the minimum and the maximum are the same object and no
//      selection rule can be distinguished. The assertion was fine; the
//      fixture made it vacuous.
//
// A min-vs-max test is only meaningful when the trials reach genuinely
// different fixed points. This fixture - two crossing elongated bands -
// was measured to do that (log-determinant spread 8.40, minimum at
// location (3.000, 0.0023), maximum at (2.510, 0.520)). The test now
// asserts that divergence as a PRECONDITION, so if the fixture ever
// stops discriminating it fails loudly instead of passing vacuously.
TEST_CASE("FastMCD returns the minimum-determinant candidate, not the maximum", "[fastmcd]") {
    const int n = 50;
    Eigen::MatrixXd points(n, 2);
    for (int i = 0; i < 25; ++i) { // band along x
        double t = static_cast<double>(i) - 12.0;
        points(i, 0) = t;
        points(i, 1) = t * 0.02;
    }
    for (int i = 25; i < n; ++i) { // band along y, offset in x
        double t = static_cast<double>(i - 25) - 12.0;
        points(i, 0) = t * 0.02 + 3.0;
        points(i, 1) = t;
    }

    auto trials = gm::boundaries::detail::trial_summaries(points);
    REQUIRE(trials.size() >= 2);

    std::size_t min_i = 0;
    std::size_t max_i = 0;
    for (std::size_t k = 1; k < trials.size(); ++k) {
        if (trials[k].log_determinant < trials[min_i].log_determinant) min_i = k;
        if (trials[k].log_determinant > trials[max_i].log_determinant) max_i = k;
    }

    // PRECONDITION, not decoration: if every trial converged to the same
    // candidate, minimum and maximum coincide and this test proves
    // nothing about the selection rule. Fail rather than pass vacuously.
    INFO("log-determinant spread across trials = "
         << (trials[max_i].log_determinant - trials[min_i].log_determinant));
    REQUIRE(trials[max_i].log_determinant - trials[min_i].log_determinant > 1e-6);
    REQUIRE((trials[min_i].location - trials[max_i].location).norm() > 1e-3);

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    // Shrinkage and the consistency factor rescale the covariance but
    // leave the location untouched, so the returned location identifies
    // which candidate was selected.
    double to_min = (fit->location - trials[min_i].location).norm();
    double to_max = (fit->location - trials[max_i].location).norm();
    INFO("distance to min-determinant candidate = " << to_min
         << ", to max-determinant candidate = " << to_max);
    CHECK(to_min < 1e-9);
    CHECK(to_max > 1e-3);
}

TEST_CASE("FastMCD's trial subsets are genuinely different from each other", "[fastmcd]") {
    const int n = 40;
    const int p = 3;
    const int h = (n + p + 1) / 2;
    const std::uint32_t seed = 0xC0FFEEu;

    std::vector<std::vector<int>> subsets;
    for (int trial = 0; trial < 5; ++trial) {
        subsets.push_back(gm::boundaries::detail::deterministic_h_subset(n, h, trial, seed));
    }
    for (const auto& s : subsets) {
        REQUIRE(static_cast<int>(s.size()) == h);
    }
    int identical_pairs = 0;
    for (std::size_t i = 0; i < subsets.size(); ++i) {
        for (std::size_t j = i + 1; j < subsets.size(); ++j) {
            if (subsets[i] == subsets[j]) ++identical_pairs;
        }
    }
    INFO("identical pairs among the 5 trials = " << identical_pairs);
    CHECK(identical_pairs == 0);
}

// Bug pinned: the rejection sampler used `val > limit`, accepting
// limit+1 values. limit is a multiple of bound, so limit+1 never is
// (for bound > 1), and residue 0 gained one extra preimage per draw.
//
// HONEST SCOPE: this pins the acceptance-region ARITHMETIC, not the
// loop condition itself. The residual skew at 2^32 is ~1e-7 relative,
// which no feasible sampling test can resolve, so a statistical test
// here would be theatre. Covering the loop condition directly would
// require templating the routine on a narrow-range generator; that
// refactor is not made here, and this comment records the gap rather
// than implying coverage that does not exist.
TEST_CASE("portable_bounded_random's acceptance region is an exact multiple of its bound", "[fastmcd]") {
    for (std::uint32_t bound : {2u, 3u, 5u, 7u, 16u, 17u, 81u, 100u, 257u, 503u, 756u}) {
        std::uint32_t limit = gm::boundaries::detail::portable_bounded_random_accept_limit(bound);
        INFO("bound = " << bound << ", accept-region size = " << limit);
        CHECK(limit % bound == 0u);
        CHECK(limit > 0u);
    }
}

// Bug pinned: NaN/Inf input returned a clean-looking SUCCESS. The
// poisoned row's Mahalanobis distance sorted to the end of the C-step
// re-subsetting and was quietly dropped, so NaN acted as an implicit
// "discard this row" sentinel - which ADR-019 forbids outright. It also
// fed NaN into two std::sort comparators, breaking strict weak ordering
// (undefined behaviour, whether or not it happens to crash).
TEST_CASE("FastMCD rejects non-finite input instead of silently dropping it", "[fastmcd]") {
    const int n = 20;
    Eigen::MatrixXd base(n, 3);
    for (int i = 0; i < n; ++i) {
        base(i, 0) = static_cast<double>(i) - 10.0;
        base(i, 1) = static_cast<double>((i * 13) % 9) - 4.0;
        base(i, 2) = static_cast<double>((i * 37) % 7) - 3.0;
    }
    SECTION("NaN") {
        Eigen::MatrixXd points = base;
        points(4, 0) = std::numeric_limits<double>::quiet_NaN();
        auto fit = fit_fastmcd(points);
        REQUIRE_FALSE(fit.has_value());
        CHECK(fit.error().code == gm::ErrorCode::kValidationFailure);
    }
    SECTION("Inf") {
        Eigen::MatrixXd points = base;
        points(7, 2) = std::numeric_limits<double>::infinity();
        auto fit = fit_fastmcd(points);
        REQUIRE_FALSE(fit.has_value());
        CHECK(fit.error().code == gm::ErrorCode::kValidationFailure);
    }
}

// Bug pinned: n == p+1 - the smallest input the API explicitly
// documents as valid - made h == n, hence alpha = 1.0, hence
// quantile(chi2, 1.0) overflow. The documented minimum ALWAYS failed,
// with a misleading "consistency-factor computation failed" message.
TEST_CASE("FastMCD accepts its documented minimum input of n == p+1", "[fastmcd]") {
    const int p = 3;
    const int n = p + 1;
    Eigen::MatrixXd points(n, p);
    points << 0.0, 0.0, 0.0,
              1.0, 0.0, 0.0,
              0.0, 1.0, 0.0,
              0.0, 0.0, 1.0;
    auto fit = fit_fastmcd(points);
    INFO((fit.has_value() ? std::string("ok")
                          : (fit.error().message + " | " + fit.error().context)));
    REQUIRE(fit.has_value());
    CHECK(fit->degrees_of_freedom == p);
}

// Bug pinned: the singularity guard was an ABSOLUTE 1e-12 threshold, so
// the same cloud was accepted in one unit system and rejected as
// "singular" in a smaller one - breaking the affine equivariance MCD is
// defined by, and putting a silent cliff under the embedding that moves
// if its coordinates are ever rescaled. Measured before the fix: a
// cond-3.8 Gaussian accepted at scale 1e-5, rejected at 1e-6.
TEST_CASE("FastMCD is invariant to the scale of its input units", "[fastmcd]") {
    const int n = 60;
    Eigen::MatrixXd base(n, 3);
    for (int i = 0; i < n; ++i) {
        double t = static_cast<double>(i);
        base(i, 0) = std::sin(t * 0.7) * 2.0;
        base(i, 1) = std::cos(t * 1.3) * 1.5;
        base(i, 2) = std::sin(t * 2.1) * 0.8;
    }
    auto reference = fit_fastmcd(base);
    REQUIRE(reference.has_value());

    for (double scale : {1e-9, 1e-6, 1e-3, 1e3}) {
        Eigen::MatrixXd points = base * scale;
        auto fit = fit_fastmcd(points);
        INFO("scale = " << scale);
        REQUIRE(fit.has_value());
        // Location is equivariant: rescaling the input rescales it by
        // the same factor, so dividing it back out reproduces the
        // unscaled fit.
        CHECK(std::abs(fit->location(0) / scale - reference->location(0)) < 1e-6);
    }
}

// The Ledoit-Wolf intensity must be a real, REPORTED quantity in
// [0, 1], not a hidden constant. A previous revision applied a fixed
// eigenvalue floor that dominated 86.6% of real fits while presenting
// itself as a rare safety net; nothing in the returned fit revealed
// that, which is why only an external re-measurement caught it.
TEST_CASE("FastMCD reports its shrinkage intensity", "[fastmcd]") {
    const int n = 60;
    Eigen::MatrixXd points(n, 3);
    for (int i = 0; i < n; ++i) {
        double t = static_cast<double>(i);
        points(i, 0) = std::sin(t * 0.7) * 2.0;
        points(i, 1) = std::cos(t * 1.3) * 1.5;
        points(i, 2) = std::sin(t * 2.1) * 0.8;
    }
    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    INFO("shrinkage intensity = " << fit->shrinkage_intensity
         << ", backstop engaged = " << fit->numerical_backstop_engaged);
    CHECK(fit->shrinkage_intensity >= 0.0);
    CHECK(fit->shrinkage_intensity <= 1.0);
    // On well-conditioned, genuinely 3-dimensional data the numerical
    // backstop has no reason to fire.
    CHECK_FALSE(fit->numerical_backstop_engaged);
}

// The returned covariance and its cached inverse are rebuilt separately
// from the same eigendecomposition, so an error in either
// reconstruction would go unnoticed until it silently corrupted every
// score computed from the fit.
TEST_CASE("FastMCD's cached inverse really is the inverse of its covariance", "[fastmcd]") {
    const int n = 50;
    Eigen::MatrixXd points(n, 3);
    for (int i = 0; i < n; ++i) {
        double t = static_cast<double>(i);
        points(i, 0) = std::sin(t * 0.9) * 3.0;
        points(i, 1) = std::cos(t * 0.4) * 2.0 + std::sin(t * 1.7) * 0.5;
        points(i, 2) = std::sin(t * 2.3) * 1.2;
    }
    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    Eigen::MatrixXd product = fit->covariance * fit->inv_covariance;
    Eigen::MatrixXd identity = Eigen::MatrixXd::Identity(3, 3);
    double max_err = (product - identity).cwiseAbs().maxCoeff();
    INFO("max |C * C^-1 - I| = " << max_err);
    CHECK(max_err < 1e-8);
}

// Property test, NOT a regression test - the distinction is recorded
// deliberately. Both the covariance and its inverse are reconstructed as
// V*D*V^T, symmetric in exact arithmetic. A previous revision wrote
// `M = (M + M.transpose()) / 2.0` to enforce that, which ALIASES in
// Eigen - it reads M.transpose() while writing M coefficient by
// coefficient, so it does not symmetrize at all.
//
// HONEST SCOPE: this test was checked against the aliasing bug and did
// NOT catch it. On synthetic fixtures V*D*V^T comes back exactly
// symmetric already, so the aliased in-place form produces an identical
// result and there is nothing to detect. The aliasing was established
// instead by direct measurement - a 3x3 where the in-place form differed
// from the correct result by 1.5, and a real returned covariance with an
// asymmetry of 2.91e-11 where correct symmetrization gives exactly 0.
// What follows is therefore a genuine invariant worth holding, but it is
// not evidence that the aliasing cannot return.
TEST_CASE("FastMCD returns an exactly symmetric covariance and inverse", "[fastmcd]") {
    const int n = 40;
    Eigen::MatrixXd points(n, 3);
    for (int i = 0; i < n; ++i) {
        double t = static_cast<double>(i);
        points(i, 0) = std::sin(t) * 5.0;
        points(i, 1) = std::cos(t * 0.6) * 0.02; // deliberately anisotropic
        points(i, 2) = std::sin(t * 1.9) * 2.0;
    }
    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    double cov_asym = (fit->covariance - fit->covariance.transpose()).cwiseAbs().maxCoeff();
    double inv_asym = (fit->inv_covariance - fit->inv_covariance.transpose()).cwiseAbs().maxCoeff();
    INFO("covariance asymmetry = " << cov_asym << ", inverse asymmetry = " << inv_asym);
    CHECK(cov_asym == 0.0);
    CHECK(inv_asym == 0.0);
}

TEST_CASE("FastMCD recovers the SHAPE of the clean data, not just its center", "[fastmcd]") {
    // Found by mutation testing the Hawkins-Bradu-Kass reference test:
    // forcing the Ledoit-Wolf intensity to 1.0 - which discards the
    // sample covariance entirely and returns a scaled identity, i.e. an
    // estimator with NO shape information at all - passed every one of
    // the 23 test cases in this suite. Location was covered, symmetry was
    // covered, conditioning was covered, invariances were covered; the
    // single most important thing the estimator produces was not.
    //
    // Construction: a deterministic anisotropic Gaussian core with a
    // known covariance T, plus 20% contamination placed far off its long
    // axis. If the returned covariance S is proportional to T (all that
    // MCD promises - the consistency factor is a scale), then
    // W = T^(-1/2) S T^(-1/2) is proportional to the identity and its
    // eigenvalue ratio is 1. The ratio of W is therefore a single number
    // measuring how much of the true shape was recovered, invariant to
    // the arbitrary scale factor.
    const int n_clean = 48;
    const int n_dirty = 12;
    const int n = n_clean + n_dirty;

    // Box-Muller from raw mt19937 output. std::normal_distribution and
    // std::shuffle are implementation-defined; mt19937's integer sequence
    // is fixed by the standard, so doing the arithmetic here keeps this
    // fixture identical on every platform.
    std::mt19937 rng(20260902u);
    auto uniform01 = [&rng]() {
        return (static_cast<double>(rng()) + 0.5) / 4294967296.0;
    };
    std::vector<double> z;
    z.reserve(static_cast<std::size_t>(2 * n_clean));
    while (z.size() < static_cast<std::size_t>(2 * n_clean)) {
        const double u1 = uniform01();
        const double u2 = uniform01();
        const double r = std::sqrt(-2.0 * std::log(u1));
        z.push_back(r * std::cos(2.0 * 3.14159265358979323846 * u2));
        z.push_back(r * std::sin(2.0 * 3.14159265358979323846 * u2));
    }

    // Long axis at 30 degrees, axis lengths 10 and 1 -> true covariance
    // T = A A^T has an eigenvalue ratio of exactly 100.
    const double theta = 30.0 * 3.14159265358979323846 / 180.0;
    Eigen::Matrix2d rot;
    rot << std::cos(theta), -std::sin(theta),
           std::sin(theta),  std::cos(theta);
    Eigen::Matrix2d scale = Eigen::Vector2d(10.0, 1.0).asDiagonal();
    const Eigen::Matrix2d a = rot * scale;
    const Eigen::Matrix2d truth = a * a.transpose();

    Eigen::MatrixXd points(n, 2);
    for (int i = 0; i < n_clean; ++i) {
        Eigen::Vector2d raw(z[static_cast<std::size_t>(2 * i)], z[static_cast<std::size_t>(2 * i + 1)]);
        points.row(i) = (a * raw).transpose();
    }
    // Contamination: a tight clump displaced along the SHORT axis, which
    // is what would inflate the estimate toward isotropy if it leaked in.
    const Eigen::Vector2d short_axis = rot.col(1);
    for (int i = 0; i < n_dirty; ++i) {
        const Eigen::Vector2d offset = short_axis * (40.0 + 0.3 * static_cast<double>(i));
        points.row(n_clean + i) = offset.transpose();
    }

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());

    // W = T^(-1/2) S T^(-1/2); proportional to I exactly when S is
    // proportional to T.
    Eigen::SelfAdjointEigenSolver<Eigen::Matrix2d> t_solver(truth);
    REQUIRE(t_solver.info() == Eigen::Success);
    const Eigen::Matrix2d t_inv_sqrt =
        t_solver.eigenvectors()
        * t_solver.eigenvalues().cwiseInverse().cwiseSqrt().asDiagonal()
        * t_solver.eigenvectors().transpose();
    const Eigen::Matrix2d w = t_inv_sqrt * fit->covariance * t_inv_sqrt;

    Eigen::SelfAdjointEigenSolver<Eigen::Matrix2d> w_solver(w);
    REQUIRE(w_solver.info() == Eigen::Success);
    const double lo = w_solver.eigenvalues()(0);
    const double hi = w_solver.eigenvalues()(1);
    REQUIRE(lo > 0.0);
    const double shape_error = hi / lo;

    // Both reference points measured, not guessed:
    //   correct estimator            -> 3.43  (delta = 0.047; Ledoit-Wolf
    //                                   legitimately compresses a 100:1
    //                                   ratio toward its target, and that
    //                                   compression is most of this 3.43)
    //   shrinkage intensity forced 1 -> 100.0 (a scaled identity, i.e.
    //                                   the true ratio recovered in full
    //                                   as pure error)
    // The threshold sits ~3x above the correct value and ~10x below the
    // shape-free one, so it neither pins sampling noise nor leaves room
    // for an estimator with no shape information to slip through.
    INFO("shape error (eigenvalue ratio of T^-1/2 S T^-1/2) = " << shape_error
         << "; 1.0 is exact recovery, 100 is total loss of shape. delta="
         << fit->shrinkage_intensity);
    CHECK(shape_error < 10.0);

    // The estimate must also still be anisotropic in absolute terms - a
    // direct statement of the same thing, in the original coordinates.
    Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> s_solver(fit->covariance);
    REQUIRE(s_solver.info() == Eigen::Success);
    const double s_ratio = s_solver.eigenvalues()(1) / s_solver.eigenvalues()(0);
    INFO("returned eigenvalue ratio = " << s_ratio << " (true ratio is 100)");
    CHECK(s_ratio > 10.0);

    // And its long axis must point along the true long axis, not across
    // it. |cos| because eigenvector sign is arbitrary.
    const Eigen::Vector2d est_long = s_solver.eigenvectors().col(1);
    const double alignment = std::abs(est_long.dot(rot.col(0)));
    INFO("|cos| between estimated and true long axis = " << alignment);
    CHECK(alignment > 0.98);
}
