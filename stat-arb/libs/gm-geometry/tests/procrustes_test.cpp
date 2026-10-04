// Reference test for align(): the standard validation is to apply a
// KNOWN rotation to a point set and confirm Procrustes recovers it -
// i.e. aligning the rotated set back to the original reproduces the
// original almost exactly (residual near zero).

#include <gm-geometry/procrustes.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::geometry::align;

namespace {
constexpr double kTol = 1e-8;
}

TEST_CASE("recovers a known 90-degree rotation", "[procrustes]") {
    Eigen::MatrixXd y(4, 2);
    y << 1, 0, 0, 1, -1, 0, 0, -1;

    // R = [[0,-1],[1,0]]: a 90-degree rotation.
    Eigen::MatrixXd r(2, 2);
    r << 0, -1, 1, 0;
    Eigen::MatrixXd y_rotated = y * r;

    auto result = align(y_rotated, y);
    REQUIRE(result.has_value());

    // Aligning the rotated set back to the original should reproduce
    // the original almost exactly.
    Eigen::MatrixXd diff = result->aligned - y;
    CHECK(diff.cwiseAbs().maxCoeff() < kTol);
    CHECK(result->raw_residual < kTol);
    CHECK(result->normalized_residual < kTol);

    // The recovered rotation should undo R, i.e. equal R' (R is
    // orthogonal, so R^-1 = R').
    Eigen::MatrixXd diff_rot = result->rotation - r.transpose();
    CHECK(diff_rot.cwiseAbs().maxCoeff() < kTol);
}

TEST_CASE("recovers a known reflection (orthogonal Procrustes permits det(R) = -1)",
          "[procrustes]") {
    Eigen::MatrixXd y(4, 2);
    y << 1, 0, 0, 1, -1, 0, 0, -1;

    Eigen::MatrixXd reflect(2, 2);
    reflect << 1, 0, 0, -1;  // flip the y-axis: a reflection, det = -1
    Eigen::MatrixXd y_reflected = y * reflect;

    auto result = align(y_reflected, y);
    REQUIRE(result.has_value());
    Eigen::MatrixXd diff = result->aligned - y;
    CHECK(diff.cwiseAbs().maxCoeff() < kTol);
}

TEST_CASE("aligning identical point sets gives near-identity rotation and zero residual",
          "[procrustes]") {
    Eigen::MatrixXd y(3, 2);
    y << 1, 2, 3, 4, 5, 6;

    auto result = align(y, y);
    REQUIRE(result.has_value());
    CHECK(result->raw_residual < kTol);

    Eigen::MatrixXd identity2 = Eigen::MatrixXd::Identity(2, 2);
    Eigen::MatrixXd diff = result->rotation - identity2;
    CHECK(diff.cwiseAbs().maxCoeff() < kTol);
}

TEST_CASE("a mismatched shape between y and reference is rejected", "[procrustes]") {
    Eigen::MatrixXd y(3, 2);
    y.setZero();
    Eigen::MatrixXd reference(4, 2);
    reference.setZero();

    auto result = align(y, reference);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("a zero reference falls back to the raw residual instead of dividing by zero",
          "[procrustes]") {
    Eigen::MatrixXd y(2, 2);
    y << 1, 0, 0, 1;
    Eigen::MatrixXd reference = Eigen::MatrixXd::Zero(2, 2);

    auto result = align(y, reference);
    REQUIRE(result.has_value());
    // reference is exactly zero, so normalized == raw (the documented
    // fallback), not NaN/Inf from a 0/0 or x/0 division.
    CHECK(std::abs(result->normalized_residual - result->raw_residual) < kTol);
    CHECK(std::isfinite(result->normalized_residual));
}
