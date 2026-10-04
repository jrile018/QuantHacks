#include <gm-geometry/rmt.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::geometry::mp_denoise;

namespace {
constexpr double kTol = 1e-9;
}

TEST_CASE("Marchenko-Pastur bulk edges match the published closed-form formula", "[rmt]") {
    // lambda_plus = (1+sqrt(q))^2, lambda_minus = (1-sqrt(q))^2.
    Eigen::MatrixXd identity3 = Eigen::MatrixXd::Identity(3, 3);

    auto q1 = mp_denoise(identity3, 1.0);  // sqrt(1)=1 -> lambda_plus=4, lambda_minus=0
    REQUIRE(q1.has_value());
    CHECK(std::abs(q1->lambda_plus - 4.0) < kTol);
    CHECK(std::abs(q1->lambda_minus - 0.0) < kTol);

    auto q_quarter = mp_denoise(identity3, 0.25);  // sqrt(0.25)=0.5 -> (1.5)^2=2.25, (0.5)^2=0.25
    REQUIRE(q_quarter.has_value());
    CHECK(std::abs(q_quarter->lambda_plus - 2.25) < kTol);
    CHECK(std::abs(q_quarter->lambda_minus - 0.25) < kTol);
}

TEST_CASE("an identity correlation matrix denoises to itself", "[rmt]") {
    // Every eigenvalue of I is exactly 1. With q=1 (lambda_plus=4), all
    // three eigenvalues fall inside the bulk and get replaced by their
    // mean - which is still exactly 1, so the reconstruction (and the
    // subsequent unit-diagonal rescale, itself a no-op here) must
    // reproduce I exactly. A self-consistency property, not a
    // hand-derived numeric case, but a strong one: if this failed it
    // would mean the eigendecomposition/reconstruction round-trip
    // itself is broken, independent of any MP-specific logic.
    Eigen::MatrixXd identity3 = Eigen::MatrixXd::Identity(3, 3);
    auto result = mp_denoise(identity3, 1.0);
    REQUIRE(result.has_value());
    CHECK(result->num_signal_eigenvalues == 0);
    Eigen::MatrixXd diff = result->denoised_correlation - identity3;
    CHECK(diff.cwiseAbs().maxCoeff() < 1e-8);
}

TEST_CASE("a dominant market-mode eigenvalue is correctly classified as signal", "[rmt]") {
    // Construct a correlation matrix with one clearly dominant
    // eigenvalue (a "market factor" structure: equal pairwise
    // correlation rho among all N=4 assets has eigenvalues
    // 1+(N-1)*rho once, and 1-rho with multiplicity N-1 - a standard,
    // independently-verifiable closed form for equicorrelation
    // matrices).
    const int n = 4;
    const double rho = 0.6;
    Eigen::MatrixXd c = Eigen::MatrixXd::Constant(n, n, rho);
    for (int i = 0; i < n; ++i) c(i, i) = 1.0;

    double expected_dominant = 1.0 + (n - 1) * rho;  // 1 + 3*0.6 = 2.8
    double expected_bulk = 1.0 - rho;                // 0.4, multiplicity 3

    // With q small enough that lambda_plus falls between 0.4 and 2.8,
    // the dominant eigenvalue is signal and the other 3 are bulk.
    double q = 0.09;  // sqrt(q)=0.3 -> lambda_plus=(1.3)^2=1.69
    auto result = mp_denoise(c, q);
    REQUIRE(result.has_value());
    CHECK(result->num_signal_eigenvalues == 1);

    // Sanity-check the closed-form eigenvalues used to construct this
    // case actually bracket lambda_plus as intended.
    CHECK(expected_bulk < result->lambda_plus);
    CHECK(expected_dominant > result->lambda_plus);
}

TEST_CASE("denoised correlation always has an exact unit diagonal", "[rmt]") {
    Eigen::MatrixXd c(3, 3);
    c << 1.0, 0.5, 0.2, 0.5, 1.0, 0.3, 0.2, 0.3, 1.0;

    auto result = mp_denoise(c, 0.5);
    REQUIRE(result.has_value());
    for (int i = 0; i < 3; ++i) {
        CHECK(std::abs(result->denoised_correlation(i, i) - 1.0) < kTol);
    }
}

TEST_CASE("a non-square matrix is rejected", "[rmt]") {
    Eigen::MatrixXd c(2, 3);
    c.setZero();
    auto result = mp_denoise(c, 1.0);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("a non-positive q is rejected", "[rmt]") {
    Eigen::MatrixXd c = Eigen::MatrixXd::Identity(2, 2);
    CHECK_FALSE(mp_denoise(c, 0.0).has_value());
    CHECK_FALSE(mp_denoise(c, -1.0).has_value());
}
