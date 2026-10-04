#include <gm-geometry/distance.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::geometry::mantegna_distance;

namespace {
constexpr double kTol = 1e-9;
}

TEST_CASE("d = sqrt(2*(1-rho)) matches direct computation at known correlation values",
          "[distance]") {
    Eigen::MatrixXd c(3, 3);
    // rho=1 (self) -> d=0; rho=0 -> d=sqrt(2); rho=-1 -> d=2.
    c << 1.0, 0.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 1.0;

    auto result = mantegna_distance(c);
    REQUIRE(result.has_value());
    CHECK(std::abs((*result)(0, 0) - 0.0) < kTol);
    CHECK(std::abs((*result)(0, 1) - std::sqrt(2.0)) < kTol);
    CHECK(std::abs((*result)(0, 2) - 2.0) < kTol);
}

TEST_CASE("a correlation fractionally outside [-1,1] by roundoff is clamped, not rejected",
          "[distance]") {
    Eigen::MatrixXd c(2, 2);
    c << 1.0000000000000002, 0.5, 0.5, 1.0;
    auto result = mantegna_distance(c);
    REQUIRE(result.has_value());
    CHECK((*result)(0, 0) >= 0.0);  // clamped to 1.0 -> d=0, not NaN from a negative sqrt argument
}

TEST_CASE("a correlation genuinely outside [-1,1] is rejected", "[distance]") {
    Eigen::MatrixXd c(2, 2);
    c << 1.0, 1.5, 1.5, 1.0;  // 1.5 is not roundoff-close to the valid range
    auto result = mantegna_distance(c);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("output distance matrix is exactly symmetric with an exact zero diagonal", "[distance]") {
    Eigen::MatrixXd c(3, 3);
    c << 1.0, 0.3, 0.6, 0.3, 1.0, 0.1, 0.6, 0.1, 1.0;
    auto result = mantegna_distance(c);
    REQUIRE(result.has_value());
    for (int i = 0; i < 3; ++i) CHECK((*result)(i, i) == 0.0);
    Eigen::MatrixXd diff = *result - result->transpose();
    CHECK(diff.cwiseAbs().maxCoeff() < kTol);
}

TEST_CASE("a non-square matrix is rejected", "[distance]") {
    Eigen::MatrixXd c(2, 3);
    c.setZero();
    auto result = mantegna_distance(c);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}
