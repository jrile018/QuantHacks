#include <gm-signals/excursion.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

using gm::signals::detect_excursions;

TEST_CASE("a single excursion that reverts is detected with the correct span and peak", "[excursion]") {
    Eigen::VectorXd z(8);
    z << 0.1, 0.5, 2.5, 3.0, 2.8, 0.3, 0.2, 0.1;

    auto excursions = detect_excursions(z, 2.0, 0.5);
    REQUIRE(excursions.has_value());
    REQUIRE(excursions->size() == 1);

    const auto& e = (*excursions)[0];
    CHECK(e.start_index == 2);
    CHECK(e.end_index == 5);
    CHECK(e.peak_depth == Catch::Approx(3.0));
    CHECK(e.reverted);
}

TEST_CASE("an excursion still outside when the series ends is censored, not reverted", "[excursion]") {
    Eigen::VectorXd z(4);
    z << 0.1, 2.5, 3.0, 2.2;

    auto excursions = detect_excursions(z, 2.0, 0.5);
    REQUIRE(excursions.has_value());
    REQUIRE(excursions->size() == 1);

    const auto& e = (*excursions)[0];
    CHECK(e.start_index == 1);
    CHECK(e.end_index == 3); // last index of the series
    CHECK(e.peak_depth == Catch::Approx(3.0));
    CHECK_FALSE(e.reverted);
}

TEST_CASE("two separate excursions are both detected, not merged", "[excursion]") {
    Eigen::VectorXd z(4);
    z << 3.0, 0.2, 2.5, 0.1;

    auto excursions = detect_excursions(z, 2.0, 0.5);
    REQUIRE(excursions.has_value());
    REQUIRE(excursions->size() == 2);

    CHECK((*excursions)[0].start_index == 0);
    CHECK((*excursions)[0].end_index == 1);
    CHECK((*excursions)[0].peak_depth == Catch::Approx(3.0));
    CHECK((*excursions)[0].reverted);

    CHECK((*excursions)[1].start_index == 2);
    CHECK((*excursions)[1].end_index == 3);
    CHECK((*excursions)[1].peak_depth == Catch::Approx(2.5));
    CHECK((*excursions)[1].reverted);
}

TEST_CASE("values in the hysteresis dead zone neither close nor fragment an open excursion",
          "[excursion]") {
    // 1.0 is between exit(0.5) and entry(2.0) - must not trigger a
    // close (it's not <= exit) and, since we're already in an
    // excursion, is correctly not re-evaluated against entry either.
    Eigen::VectorXd z(4);
    z << 3.0, 1.0, 1.0, 0.2;

    auto excursions = detect_excursions(z, 2.0, 0.5);
    REQUIRE(excursions.has_value());
    REQUIRE(excursions->size() == 1);

    const auto& e = (*excursions)[0];
    CHECK(e.start_index == 0);
    CHECK(e.end_index == 3);
    CHECK(e.peak_depth == Catch::Approx(3.0)); // the dead-zone values don't raise the peak
    CHECK(e.reverted);
}

TEST_CASE("a series that never crosses the entry threshold produces no excursions", "[excursion]") {
    Eigen::VectorXd z(5);
    z << 0.1, -0.5, 1.0, -1.5, 0.8;

    auto excursions = detect_excursions(z, 2.0, 0.5);
    REQUIRE(excursions.has_value());
    CHECK(excursions->empty());
}

TEST_CASE("negative z-scores are handled via absolute value symmetrically", "[excursion]") {
    Eigen::VectorXd z(4);
    z << -0.1, -2.5, -3.0, -0.2;

    auto excursions = detect_excursions(z, 2.0, 0.5);
    REQUIRE(excursions.has_value());
    REQUIRE(excursions->size() == 1);
    CHECK((*excursions)[0].peak_depth == Catch::Approx(3.0));
}

TEST_CASE("nonpositive entry_threshold is rejected", "[excursion]") {
    Eigen::VectorXd z(3);
    z << 1.0, 2.0, 3.0;
    auto excursions = detect_excursions(z, 0.0, 0.5);
    REQUIRE_FALSE(excursions.has_value());
}

TEST_CASE("nonpositive exit_threshold is rejected", "[excursion]") {
    Eigen::VectorXd z(3);
    z << 1.0, 2.0, 3.0;
    auto excursions = detect_excursions(z, 2.0, 0.0);
    REQUIRE_FALSE(excursions.has_value());
}

TEST_CASE("exit_threshold >= entry_threshold is rejected", "[excursion]") {
    Eigen::VectorXd z(3);
    z << 1.0, 2.0, 3.0;
    auto excursions = detect_excursions(z, 1.0, 1.0);
    REQUIRE_FALSE(excursions.has_value());
}
