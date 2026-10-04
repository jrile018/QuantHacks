#include <gm-boundaries/mahalanobis.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::boundaries::fit_mahalanobis;
using gm::boundaries::score_mahalanobis;

namespace {
constexpr double kTol = 1e-9;
}

TEST_CASE("median and MAD scale match hand-computed values for a fixed column", "[mahalanobis]") {
    // Column 0: [1,2,3,4,5,10,11] -> sorted already; median (n=7, mid=3,
    // 0-indexed) = 4. abs deviations = [3,2,1,0,1,6,7] -> sorted
    // [0,1,1,2,3,6,7], median (mid=3) = 2. mad_scale = 1.4826*2 = 2.9652.
    Eigen::MatrixXd points(7, 2);
    points.col(0) << 1, 2, 3, 4, 5, 10, 11;
    points.col(1) << 1, 2, 3, 4, 5, 6, 7;  // arbitrary second column, just needs n >= k+1

    auto fit = fit_mahalanobis(points);
    REQUIRE(fit.has_value());
    CHECK(std::abs(fit->median(0) - 4.0) < kTol);
    CHECK(std::abs(fit->mad_scale(0) - 2.9652) < 1e-6);
}

TEST_CASE("a point at the fit's own center scores deep inside", "[mahalanobis]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_mahalanobis(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd center(2);
    center << 0.0, 0.0;
    auto score = score_mahalanobis(*fit, center);
    REQUIRE(score.has_value());
    CHECK(score->inside);
    CHECK(score->depth < 0.0);
    CHECK(score->p_value > 0.5);  // near the center, very unlikely to be an outlier
}

TEST_CASE("a point far outside the training cloud scores outside", "[mahalanobis]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_mahalanobis(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd far_point(2);
    far_point << 1000.0, 1000.0;
    auto score = score_mahalanobis(*fit, far_point);
    REQUIRE(score.has_value());
    CHECK_FALSE(score->inside);
    CHECK(score->depth > 0.0);
    CHECK(score->p_value < 0.01);
}

TEST_CASE("depth is monotonic with distance from center along a fixed direction", "[mahalanobis]") {
    Eigen::MatrixXd points(10, 2);
    points.col(0) << -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 0;
    points.col(1) << -1, -0.8, -0.5, -0.2, 0, 0.2, 0.5, 0.8, 1, 0.1;

    auto fit = fit_mahalanobis(points);
    REQUIRE(fit.has_value());

    double prev_depth = -1e18;
    for (double d : {0.0, 1.0, 2.0, 5.0, 10.0, 50.0}) {
        Eigen::VectorXd p(2);
        p << d, 0.0;
        auto score = score_mahalanobis(*fit, p);
        REQUIRE(score.has_value());
        CHECK(score->depth > prev_depth);
        prev_depth = score->depth;
    }
}

TEST_CASE("fewer than k+1 points is rejected", "[mahalanobis]") {
    Eigen::MatrixXd points(2, 3);  // n=2, k=3: need n >= 4
    points.setZero();
    auto fit = fit_mahalanobis(points);
    REQUIRE_FALSE(fit.has_value());
    CHECK(fit.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("a dimension with zero MAD (more than half identical) is rejected", "[mahalanobis]") {
    Eigen::MatrixXd points(5, 2);
    points.col(0) << 1, 2, 3, 4, 5;
    points.col(1) << 7, 7, 7, 7, 1;  // >= half the values are exactly 7 -> MAD = 0
    auto fit = fit_mahalanobis(points);
    REQUIRE_FALSE(fit.has_value());
    CHECK(fit.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("score dimension mismatch is rejected", "[mahalanobis]") {
    Eigen::MatrixXd points(5, 2);
    points.col(0) << 1, 2, 3, 4, 5;
    points.col(1) << 5, 1, 8, 2, 9;
    auto fit = fit_mahalanobis(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd bad_point(3);
    bad_point << 1, 2, 3;
    auto score = score_mahalanobis(*fit, bad_point);
    REQUIRE_FALSE(score.has_value());
    CHECK(score.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("out-of-range alpha is rejected", "[mahalanobis]") {
    Eigen::MatrixXd points(5, 2);
    points.col(0) << 1, 2, 3, 4, 5;
    points.col(1) << 5, 1, 8, 2, 9;
    auto fit = fit_mahalanobis(points);
    REQUIRE(fit.has_value());

    Eigen::VectorXd p(2);
    p << 3, 6;
    CHECK_FALSE(score_mahalanobis(*fit, p, 0.0).has_value());
    CHECK_FALSE(score_mahalanobis(*fit, p, 1.0).has_value());
}
