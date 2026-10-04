#include <gm-signals/peer_basket.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

using gm::signals::fit_peer_basket_weights;

TEST_CASE("weights always sum to exactly 1 and are non-negative", "[peer_basket]") {
    Eigen::VectorXd target(6);
    target << 1.0, 2.0, -1.0, 3.0, 0.0, 1.5;
    Eigen::MatrixXd neighbors(6, 3);
    neighbors << 1.0, 0.5, -0.2, 2.1, -1.0, 0.3, -0.9, 3.0, 1.1, 3.2, 0.1, -0.5, 0.1, 1.0, 2.0, 1.4, -0.3, 0.8;

    auto weights = fit_peer_basket_weights(target, neighbors);
    REQUIRE(weights.has_value());
    REQUIRE(weights->size() == 3);
    CHECK((weights->array() >= 0.0).all());
    CHECK(weights->sum() == Catch::Approx(1.0).margin(1e-6));
}

TEST_CASE("an exact convex combination of two neighbors is recovered", "[peer_basket]") {
    // Two genuinely non-collinear return series (checked by inspection:
    // no scalar k satisfies neighbor_1 = k * neighbor_0 across all 6
    // points), so the true weight split is unique, not an arbitrary
    // point along a degenerate ridge-regularized tie.
    Eigen::VectorXd neighbor0(6);
    neighbor0 << 1.0, 2.0, -1.0, 3.0, 0.0, 1.0;
    Eigen::VectorXd neighbor1(6);
    neighbor1 << 2.0, -1.0, 3.0, 0.0, 1.0, 2.0;

    Eigen::VectorXd target = 0.5 * neighbor0 + 0.5 * neighbor1; // exact, no noise

    Eigen::MatrixXd neighbors(6, 2);
    neighbors.col(0) = neighbor0;
    neighbors.col(1) = neighbor1;

    auto weights = fit_peer_basket_weights(target, neighbors, /*ridge_lambda=*/1e-8);
    REQUIRE(weights.has_value());
    CHECK((*weights)(0) == Catch::Approx(0.5).margin(0.02));
    CHECK((*weights)(1) == Catch::Approx(0.5).margin(0.02));
}

TEST_CASE("a target that exactly equals one neighbor concentrates weight there", "[peer_basket]") {
    Eigen::VectorXd match(6);
    match << 1.0, 2.0, -1.0, 3.0, 0.0, 1.0;
    Eigen::VectorXd noise0(6);
    noise0 << 5.0, -3.0, 2.0, -1.0, 4.0, -2.0;
    Eigen::VectorXd noise1(6);
    noise1 << -2.0, 1.0, 5.0, 3.0, -4.0, 0.5;

    Eigen::MatrixXd neighbors(6, 3);
    neighbors.col(0) = noise0;
    neighbors.col(1) = match; // this one exactly explains the target
    neighbors.col(2) = noise1;

    auto weights = fit_peer_basket_weights(match, neighbors, /*ridge_lambda=*/1e-8);
    REQUIRE(weights.has_value());
    CHECK((*weights)(1) > 0.9); // weight concentrated on the matching neighbor
}

TEST_CASE("row count mismatch between target and neighbors is rejected", "[peer_basket]") {
    Eigen::VectorXd target(5);
    target.setZero();
    Eigen::MatrixXd neighbors(6, 2); // 6 rows, target has 5
    neighbors.setZero();
    auto weights = fit_peer_basket_weights(target, neighbors);
    REQUIRE_FALSE(weights.has_value());
}

TEST_CASE("zero neighbor columns is rejected", "[peer_basket]") {
    Eigen::VectorXd target(6);
    target.setZero();
    Eigen::MatrixXd neighbors(6, 0);
    auto weights = fit_peer_basket_weights(target, neighbors);
    REQUIRE_FALSE(weights.has_value());
}

TEST_CASE("negative ridge_lambda is rejected", "[peer_basket]") {
    Eigen::VectorXd target(6);
    target.setZero();
    Eigen::MatrixXd neighbors(6, 2);
    neighbors.setZero();
    auto weights = fit_peer_basket_weights(target, neighbors, -1.0);
    REQUIRE_FALSE(weights.has_value());
}

TEST_CASE("a single neighbor gets all the weight by construction", "[peer_basket]") {
    Eigen::VectorXd target(4);
    target << 1.0, -2.0, 3.0, 0.5;
    Eigen::MatrixXd neighbors(4, 1);
    neighbors.col(0) << 2.0, -1.0, 4.0, 1.0;

    auto weights = fit_peer_basket_weights(target, neighbors);
    REQUIRE(weights.has_value());
    CHECK((*weights)(0) == Catch::Approx(1.0).margin(1e-9)); // sum(w)=1 with only 1 weight forces w=1
}
