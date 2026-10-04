#include <gm-topology/ripser_wrapper.hpp>
#include <catch2/catch_test_macros.hpp>
#include <Eigen/Dense>
#include <cmath>
#include <numbers>

TEST_CASE("TopologyH0: SingleLinkageDetectsConnectedComponents") {
    Eigen::MatrixXd points(3, 2);
    points << 0.0, 0.0,
              1.0, 0.0,
              2.0, 0.0;

    auto result = gm::topology::compute_persistence(points);
    REQUIRE(result.has_value());

    auto features = *result;

    // Real Ripser emits N dim-0 pairs for N points: N-1 finite merges plus
    // 1 pair for the single component that survives forever (this wrapper
    // caps that infinite death at the enclosing-radius threshold rather
    // than dropping it - see parse_ripser_output). For 3 collinear points
    // at (0,0),(1,0),(2,0): two merges at distance 1 (the two adjacent
    // pairs), the (0,2) edge (distance 2) is never needed since the chain
    // is already connected via the two distance-1 edges, and the
    // enclosing radius (the threshold Ripser itself picks) is 1 - so all
    // three pairs die at 1. This differs from the old expectation (2
    // pairs, total 2.0), which was written against a hand-rolled
    // approximation that never emitted the ever-persisting component as
    // its own pair - that convention was never real Ripser's, so the
    // test is updated to match the real algorithm's actual output rather
    // than kept as a regression check against a fabricated baseline.
    REQUIRE(features.h0_pairs.size() == 3);
    REQUIRE(features.h0_total_persistence == 3.0);
}

TEST_CASE("TopologyH1: FilledDiskHasZeroH1") {
    Eigen::MatrixXd points(10, 2);

    points << 0.0, 0.0,
             0.3, 0.0,
             0.0, 0.3,
             0.2, 0.2,
             -0.2, 0.1,
             0.1, -0.2,
             -0.1, -0.1,
             0.25, -0.1,
             -0.15, 0.25,
             0.0, -0.3;

    auto result = gm::topology::compute_persistence(points);
    REQUIRE(result.has_value());

    auto features = *result;

    CHECK(features.h1_total_persistence < 0.15);
}

TEST_CASE("TopologyH1: RingHasNonzeroH1") {
    Eigen::MatrixXd points(12, 2);

    for (int i = 0; i < 12; ++i) {
        // std::numbers::pi, not M_PI: M_PI is a POSIX extension, not
        // standard C++, and MSVC does not define it without
        // _USE_MATH_DEFINES. This project is C++20 and has the real one.
        double angle = 2.0 * std::numbers::pi * i / 12.0;
        points(i, 0) = std::cos(angle);
        points(i, 1) = std::sin(angle);
    }

    auto result = gm::topology::compute_persistence(points);
    REQUIRE(result.has_value());

    auto features = *result;

    CHECK(features.h1_total_persistence > 0.1);
    CHECK(features.h1_pairs.size() > 0);
}

TEST_CASE("TopologyWasserstein: EmptyDiagrams") {
    std::vector<gm::topology::PersistencePair> empty;
    auto result = gm::topology::wasserstein_distance(empty, empty);
    REQUIRE(result.has_value());
    CHECK(*result == 0.0);
}

TEST_CASE("TopologyWasserstein: IdenticalDiagrams") {
    std::vector<gm::topology::PersistencePair> diagram1 = {
        {0.0, 1.0},
        {0.5, 2.0}
    };
    std::vector<gm::topology::PersistencePair> diagram2 = diagram1;

    auto result = gm::topology::wasserstein_distance(diagram1, diagram2);
    REQUIRE(result.has_value());
    CHECK(*result == 0.0);
}
