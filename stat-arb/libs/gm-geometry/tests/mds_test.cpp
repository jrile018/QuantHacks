// Reference test for classical_mds: the standard way to validate MDS is
// to recover a KNOWN point configuration's own distance matrix and
// check that the embedding's pairwise distances match the input
// distances - not that specific coordinate values match, since MDS
// only recovers a configuration up to rotation/reflection/translation
// (which is exactly why Procrustes alignment, procrustes_test.cpp,
// exists as a separate concern).

#include <gm-geometry/mds.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::geometry::classical_mds;

namespace {
constexpr double kTol = 1e-8;

double pairwise_distance(const Eigen::MatrixXd& coords, int i, int j) {
    return (coords.row(i) - coords.row(j)).norm();
}
} // namespace

TEST_CASE("recovers exact pairwise distances for a known 2D unit square", "[mds]") {
    // Points (0,0), (1,0), (1,1), (0,1) - a unit square.
    double s2 = std::sqrt(2.0);
    Eigen::MatrixXd d(4, 4);
    d << 0, 1, s2, 1, 1, 0, 1, s2, s2, 1, 0, 1, 1, s2, 1, 0;

    auto result = classical_mds(d, 2);
    REQUIRE(result.has_value());
    CHECK(result->num_negative_clipped == 0);  // exactly Euclidean input, embeds perfectly in k=2

    CHECK(std::abs(pairwise_distance(result->coordinates, 0, 1) - 1.0) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 0, 2) - s2) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 0, 3) - 1.0) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 1, 2) - 1.0) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 1, 3) - s2) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 2, 3) - 1.0) < kTol);
}

TEST_CASE("recovers exact pairwise distances for a known 1D line embedded in k=1", "[mds]") {
    // Points at 0, 1, 3, 6 on a line.
    Eigen::MatrixXd d(4, 4);
    d << 0, 1, 3, 6, 1, 0, 2, 5, 3, 2, 0, 3, 6, 5, 3, 0;

    auto result = classical_mds(d, 1);
    REQUIRE(result.has_value());
    CHECK(result->num_negative_clipped == 0);

    CHECK(std::abs(pairwise_distance(result->coordinates, 0, 1) - 1.0) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 0, 2) - 3.0) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 0, 3) - 6.0) < kTol);
    CHECK(std::abs(pairwise_distance(result->coordinates, 2, 3) - 3.0) < kTol);
}

TEST_CASE("all points at zero distance from each other embed at the origin", "[mds]") {
    Eigen::MatrixXd d = Eigen::MatrixXd::Zero(3, 3);
    auto result = classical_mds(d, 2);
    REQUIRE(result.has_value());
    CHECK(result->coordinates.cwiseAbs().maxCoeff() < kTol);
}

TEST_CASE("k out of [1, N] range is rejected", "[mds]") {
    Eigen::MatrixXd d = Eigen::MatrixXd::Zero(3, 3);
    CHECK_FALSE(classical_mds(d, 0).has_value());
    CHECK_FALSE(classical_mds(d, 4).has_value());  // N=3, k=4 is out of range
}

TEST_CASE("a non-square matrix is rejected", "[mds]") {
    Eigen::MatrixXd d(2, 3);
    d.setZero();
    auto result = classical_mds(d, 1);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}
