#include <gm-backtest/deflated_sharpe.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::backtest::sample_moments;

TEST_CASE("a symmetric dataset has exactly zero skewness", "[sample_moments]") {
    // {1,2,3,4,5}: hand-computed mean=3, population variance=2,
    // std=sqrt(2), skewness=0 (exactly, by symmetry), kurtosis=1.7 -
    // independently verified via a second calculation (Python) during
    // design, not just derived once and trusted.
    std::vector<double> data = {1, 2, 3, 4, 5};
    auto moments = sample_moments(data);
    REQUIRE(moments.has_value());
    CHECK(moments->mean == Catch::Approx(3.0));
    CHECK(moments->std_dev == Catch::Approx(std::sqrt(2.0)));
    CHECK(moments->skewness == Catch::Approx(0.0).margin(1e-12));
    CHECK(moments->kurtosis == Catch::Approx(1.7));
}

TEST_CASE("a right-skewed dataset has the hand-computed positive skewness", "[sample_moments]") {
    // {1,1,1,1,10}: mean=2.8, population variance=12.96, std=3.6,
    // skewness=1.5 (exactly), kurtosis=3.25 - both hand-derived and
    // cross-checked independently during design.
    std::vector<double> data = {1, 1, 1, 1, 10};
    auto moments = sample_moments(data);
    REQUIRE(moments.has_value());
    CHECK(moments->mean == Catch::Approx(2.8));
    CHECK(moments->std_dev == Catch::Approx(3.6));
    CHECK(moments->skewness == Catch::Approx(1.5));
    CHECK(moments->kurtosis == Catch::Approx(3.25));
}

TEST_CASE("a left-skewed dataset (mirror of the right-skewed case) has negated skewness",
          "[sample_moments]") {
    // Negating every value negates the mean and skewness, but leaves
    // std_dev and kurtosis unchanged - a cheap way to exercise the
    // opposite sign without a fresh hand derivation.
    std::vector<double> data = {-1, -1, -1, -1, -10};
    auto moments = sample_moments(data);
    REQUIRE(moments.has_value());
    CHECK(moments->mean == Catch::Approx(-2.8));
    CHECK(moments->std_dev == Catch::Approx(3.6));
    CHECK(moments->skewness == Catch::Approx(-1.5));
    CHECK(moments->kurtosis == Catch::Approx(3.25));
}

TEST_CASE("fewer than 2 observations is rejected", "[sample_moments]") {
    auto moments = sample_moments({1.0});
    REQUIRE_FALSE(moments.has_value());
}

TEST_CASE("a constant series is rejected (zero variance)", "[sample_moments]") {
    auto moments = sample_moments({5.0, 5.0, 5.0});
    REQUIRE_FALSE(moments.has_value());
}
