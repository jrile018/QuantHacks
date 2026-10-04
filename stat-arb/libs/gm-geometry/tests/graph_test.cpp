#include <gm-geometry/graph.hpp>

#include <catch2/catch_test_macros.hpp>

#include <algorithm>

using gm::geometry::Edge;
using gm::geometry::knn_and_mst_edges;

namespace {
bool has_edge(const std::vector<Edge>& edges, int i, int j) {
    int lo = std::min(i, j), hi = std::max(i, j);
    return std::any_of(edges.begin(), edges.end(),
                        [&](const Edge& e) { return e.i == lo && e.j == hi; });
}
const Edge* find_edge(const std::vector<Edge>& edges, int i, int j) {
    int lo = std::min(i, j), hi = std::max(i, j);
    auto it = std::find_if(edges.begin(), edges.end(),
                            [&](const Edge& e) { return e.i == lo && e.j == hi; });
    return it == edges.end() ? nullptr : &*it;
}
} // namespace

TEST_CASE("MST on 5 collinear points recovers the connecting path", "[graph][mst]") {
    // Points at 1D positions 0, 1, 3, 10, 20 (chosen non-uniform so no
    // k-nearest-neighbour tie exists at k=1 - see the header derivation
    // for why). The MST of points on a line is always the path
    // connecting them in sorted order - a well-known fact, and also
    // hand-verifiable directly via Prim's: the cheapest edge from any
    // growing tree on a line is always to the immediately adjacent
    // untree'd point.
    std::vector<double> pos = {0, 1, 3, 10, 20};
    Eigen::MatrixXd D(5, 5);
    for (int i = 0; i < 5; ++i)
        for (int j = 0; j < 5; ++j) D(i, j) = std::abs(pos[static_cast<std::size_t>(i)] - pos[static_cast<std::size_t>(j)]);

    auto result = knn_and_mst_edges(D, 1);
    REQUIRE(result.has_value());

    // Expected path edges with hand-computed weights: (0,1)=1, (1,2)=2,
    // (2,3)=7, (3,4)=10.
    double mst_weight = 0.0;
    int mst_edge_count = 0;
    for (const auto& e : *result) {
        if (e.in_mst) {
            mst_weight += e.distance;
            ++mst_edge_count;
        }
    }
    CHECK(mst_edge_count == 4); // N-1 edges for N=5 nodes
    CHECK(mst_weight == 1.0 + 2.0 + 7.0 + 10.0);
    CHECK(find_edge(*result, 0, 1)->in_mst);
    CHECK(find_edge(*result, 1, 2)->in_mst);
    CHECK(find_edge(*result, 2, 3)->in_mst);
    CHECK(find_edge(*result, 3, 4)->in_mst);
}

TEST_CASE("k=1 nearest-neighbour graph is the symmetric closure, not just each node's own pick",
          "[graph][knn]") {
    // Same 5-point line. k=1 NN independently per node happens to
    // coincide with the path here (each node's single nearest neighbour
    // is its line-adjacent point in both directions), which is itself a
    // useful check that the symmetric closure doesn't fabricate extra
    // edges beyond what individual nearest-neighbour lookups produce.
    std::vector<double> pos = {0, 1, 3, 10, 20};
    Eigen::MatrixXd D(5, 5);
    for (int i = 0; i < 5; ++i)
        for (int j = 0; j < 5; ++j) D(i, j) = std::abs(pos[static_cast<std::size_t>(i)] - pos[static_cast<std::size_t>(j)]);

    auto result = knn_and_mst_edges(D, 1);
    REQUIRE(result.has_value());
    CHECK(result->size() == 4);
    CHECK(has_edge(*result, 0, 1));
    CHECK(has_edge(*result, 1, 2));
    CHECK(has_edge(*result, 2, 3));
    CHECK(has_edge(*result, 3, 4));
    CHECK_FALSE(has_edge(*result, 0, 2)); // not a neighbour of anyone at k=1
}

TEST_CASE("MST bridges two k=1-disconnected clusters with the cheapest cross-cluster edge",
          "[graph][mst][knn]") {
    // Two tight pairs far apart: {0,1} at positions 0,1 and {2,3} at
    // positions 100,101. At k=1, node0's nearest is node1 and node2's
    // nearest is node3 (and vice versa) - the k=1 graph alone is TWO
    // disconnected components, {0,1} and {2,3}. The MST must still
    // connect everything, via whichever cross-cluster edge is cheapest:
    // D(0,2)=100, D(0,3)=101, D(1,2)=99, D(1,3)=100 -> (1,2) at 99 is
    // the unique minimum, so the MST's bridge edge must be (1,2), which
    // is NOT in either endpoint's own k=1 nearest-neighbour list (node1's
    // nearest is node0, not node2).
    std::vector<double> pos = {0, 1, 100, 101};
    Eigen::MatrixXd D(4, 4);
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) D(i, j) = std::abs(pos[static_cast<std::size_t>(i)] - pos[static_cast<std::size_t>(j)]);

    auto result = knn_and_mst_edges(D, 1);
    REQUIRE(result.has_value());

    // The bridge edge must be present at all (proving MST edges outside
    // the k-NN symmetric closure are still included), marked in_mst,
    // and - the actual point of this test - marked in_knn=false: it is
    // NOT a genuine nearest-neighbour relationship for either endpoint,
    // only a structural necessity for connecting the tree. A consumer
    // that used in_mst as a proxy for "these are similar names" (rather
    // than filtering on in_knn) would get this one wrong.
    const Edge* bridge = find_edge(*result, 1, 2);
    REQUIRE(bridge != nullptr);
    CHECK(bridge->in_mst);
    CHECK_FALSE(bridge->in_knn);
    CHECK(bridge->distance == 99.0);

    // The two within-cluster edges are both k-NN edges AND MST edges.
    CHECK(find_edge(*result, 0, 1)->in_mst);
    CHECK(find_edge(*result, 0, 1)->in_knn);
    CHECK(find_edge(*result, 2, 3)->in_mst);
    CHECK(find_edge(*result, 2, 3)->in_knn);

    // Exactly 3 edges total for 4 nodes' worth of MST, with nothing
    // extra sneaking in (e.g. the non-bridge cross-cluster pairs).
    int mst_count = 0;
    for (const auto& e : *result) mst_count += e.in_mst ? 1 : 0;
    CHECK(mst_count == 3);
}

TEST_CASE("a k-NN edge that the MST does not need is reported with in_mst=false", "[graph][mst][knn]") {
    // A hand-picked triangle: D(A,B)=1, D(A,C)=2, D(B,C)=1.5. With only
    // 3 nodes, k=2 means "all other nodes" - the k-NN graph is
    // necessarily the complete triangle (all 3 edges). Kruskal's on
    // this triangle sorts edges [AB=1, BC=1.5, AC=2] and greedily adds
    // AB then BC (which already connects all 3 nodes) - AC is
    // redundant and excluded. This is the one case in this file where a
    // returned edge must have in_mst=false; every other test above only
    // exercises in_mst=true.
    Eigen::MatrixXd D(3, 3);
    D << 0.0, 1.0, 2.0, 1.0, 0.0, 1.5, 2.0, 1.5, 0.0;

    auto result = knn_and_mst_edges(D, 2);
    REQUIRE(result.has_value());
    CHECK(result->size() == 3); // complete triangle at k=2 with only 3 nodes

    CHECK(find_edge(*result, 0, 1)->in_mst); // AB
    CHECK(find_edge(*result, 1, 2)->in_mst); // BC
    CHECK_FALSE(find_edge(*result, 0, 2)->in_mst); // AC - the redundant edge

    // All three are genuine k-NN edges at k=2 with only 3 nodes (every
    // other node is, trivially, among the top 2 nearest) - AC being
    // excluded from the MST does not make it any less a real neighbour
    // relationship, which is exactly the distinction in_knn vs in_mst
    // exists to preserve.
    CHECK(find_edge(*result, 0, 1)->in_knn);
    CHECK(find_edge(*result, 1, 2)->in_knn);
    CHECK(find_edge(*result, 0, 2)->in_knn);
}

TEST_CASE("a non-square matrix is rejected", "[graph]") {
    Eigen::MatrixXd D(3, 4);
    D.setZero();
    auto result = knn_and_mst_edges(D, 1);
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("a nonzero diagonal is rejected", "[graph]") {
    Eigen::MatrixXd D(3, 3);
    D.setZero();
    D(1, 1) = 0.5;
    auto result = knn_and_mst_edges(D, 1);
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("an asymmetric matrix is rejected", "[graph]") {
    Eigen::MatrixXd D(3, 3);
    D.setZero();
    D(0, 1) = 1.0;
    D(1, 0) = 2.0; // deliberately mismatched
    auto result = knn_and_mst_edges(D, 1);
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("k >= n is rejected (not enough other nodes to be neighbours)", "[graph]") {
    Eigen::MatrixXd D(3, 3);
    D << 0.0, 1.0, 2.0, 1.0, 0.0, 1.5, 2.0, 1.5, 0.0;
    auto result = knn_and_mst_edges(D, 3); // only 2 other nodes exist
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("k <= 0 is rejected", "[graph]") {
    Eigen::MatrixXd D(3, 3);
    D << 0.0, 1.0, 2.0, 1.0, 0.0, 1.5, 2.0, 1.5, 0.0;
    auto result = knn_and_mst_edges(D, 0);
    REQUIRE_FALSE(result.has_value());
}
