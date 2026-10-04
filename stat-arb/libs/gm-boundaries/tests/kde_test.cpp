#include <gm-boundaries/kde.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::boundaries::fit_kde;
using gm::boundaries::kde_density;
using gm::boundaries::score_kde;

namespace {
constexpr double kTol = 1e-9;
}

TEST_CASE("density is higher near a dense cluster than far from all points", "[kde]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_kde(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd near_center(2);
    near_center << 0.0, 0.0;
    Eigen::VectorXd far_away(2);
    far_away << 1000.0, 1000.0;

    auto d_near = kde_density(*fit, near_center);
    auto d_far = kde_density(*fit, far_away);
    REQUIRE(d_near.has_value());
    REQUIRE(d_far.has_value());
    CHECK(*d_near > *d_far);
    CHECK(*d_far >= 0.0);  // a density must never be negative
}

TEST_CASE("a point at the cluster center scores inside; a far point scores outside", "[kde]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_kde(points, 0.05);
    REQUIRE(fit.has_value());

    Eigen::VectorXd near_center(2);
    near_center << 0.0, 0.0;
    auto inside_score = score_kde(*fit, near_center);
    REQUIRE(inside_score.has_value());
    CHECK(inside_score->inside);
    CHECK(inside_score->depth < 0.0);

    Eigen::VectorXd far_away(2);
    far_away << 1000.0, 1000.0;
    auto outside_score = score_kde(*fit, far_away);
    REQUIRE(outside_score.has_value());
    CHECK_FALSE(outside_score->inside);
    CHECK(outside_score->depth > 0.0);
}

TEST_CASE("kde_density and score_kde agree on the density value", "[kde]") {
    Eigen::MatrixXd points(6, 2);
    points.col(0) << 1, 2, 3, 4, 5, 6;
    points.col(1) << 6, 5, 4, 3, 2, 1;

    auto fit = fit_kde(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd p(2);
    p << 3.5, 3.5;
    auto density = kde_density(*fit, p);
    auto score = score_kde(*fit, p);
    REQUIRE(density.has_value());
    REQUIRE(score.has_value());
    CHECK(std::abs(*density - score->density) < kTol);
}

TEST_CASE("roughly (1-alpha) of the training points score inside their own fit", "[kde]") {
    // A larger, denser sample so the order-statistic level threshold
    // (an in-sample, not leave-one-out, quantile - documented as a
    // deliberate phase-1 simplification) behaves close to its nominal
    // rate rather than being dominated by small-sample noise.
    Eigen::MatrixXd points(40, 2);
    for (int i = 0; i < 40; ++i) {
        double angle = 2.0 * 3.14159265358979 * static_cast<double>(i) / 40.0;
        points(i, 0) = std::cos(angle) * (1.0 + 0.1 * (i % 3));
        points(i, 1) = std::sin(angle) * (1.0 + 0.1 * (i % 5));
    }

    auto fit = fit_kde(points, 0.05);
    REQUIRE(fit.has_value());

    int inside_count = 0;
    for (int i = 0; i < 40; ++i) {
        Eigen::VectorXd p = points.row(i);
        auto score = score_kde(*fit, p);
        REQUIRE(score.has_value());
        if (score->inside) ++inside_count;
    }
    // With alpha=0.05 and n=40, expect close to 38/40 inside by
    // construction of the level (some slack for ties/rounding at the
    // threshold itself).
    CHECK(inside_count >= 36);
}

TEST_CASE("the level-sampling stride path (N > kde_max_level_sample_points) behaves correctly",
          "[kde]") {
    // Regression test for the M3 code review finding: the striding
    // branch (only reached when N exceeds the cap) had zero test
    // coverage, and its stride calculation had a real bug (floor
    // division under-strided, visiting up to ~26% more points than the
    // intended cap). N=300 here is comfortably above the 200 cap, so
    // this actually exercises the sampled path, not the exact one.
    REQUIRE(300 > gm::boundaries::kde_max_level_sample_points());

    Eigen::MatrixXd points(300, 2);
    for (int i = 0; i < 300; ++i) {
        double angle = 2.0 * 3.14159265358979 * static_cast<double>(i) / 300.0;
        points(i, 0) = std::cos(angle);
        points(i, 1) = std::sin(angle);
    }

    auto fit = fit_kde(points, 0.05);
    REQUIRE(fit.has_value());
    CHECK(fit->level > 0.0);
    CHECK(std::isfinite(fit->level));

    // Coverage should still land close to the nominal (1-alpha) rate
    // even from a strided sample of the level, not just the exact path.
    int inside_count = 0;
    for (int i = 0; i < 300; ++i) {
        Eigen::VectorXd p = points.row(i);
        auto score = score_kde(*fit, p);
        REQUIRE(score.has_value());
        if (score->inside) ++inside_count;
    }
    double coverage = static_cast<double>(inside_count) / 300.0;
    CHECK(coverage > 0.85);  // nominal 0.95, generous slack for sampling noise
}

TEST_CASE("fewer than 2 points is rejected", "[kde]") {
    Eigen::MatrixXd points(1, 2);
    points.setZero();
    auto fit = fit_kde(points);
    REQUIRE_FALSE(fit.has_value());
    CHECK(fit.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("out-of-range alpha is rejected", "[kde]") {
    Eigen::MatrixXd points(3, 2);
    points.col(0) << 1, 2, 3;
    points.col(1) << 3, 1, 2;
    CHECK_FALSE(fit_kde(points, 0.0).has_value());
    CHECK_FALSE(fit_kde(points, 1.0).has_value());
}

TEST_CASE("dimension mismatch on scoring is rejected", "[kde]") {
    Eigen::MatrixXd points(3, 2);
    points.col(0) << 1, 2, 3;
    points.col(1) << 3, 1, 2;
    auto fit = fit_kde(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd bad(3);
    bad << 1, 2, 3;
    CHECK_FALSE(kde_density(*fit, bad).has_value());
    CHECK_FALSE(score_kde(*fit, bad).has_value());
}
