#include <gm-geometry/graph.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>

namespace gm::geometry {

namespace {
constexpr double kRoundoffTolerance = 1e-9; // matches distance.cpp's convention

std::pair<int, int> canonical(int a, int b) { return a < b ? std::make_pair(a, b) : std::make_pair(b, a); }

/// Prim's algorithm, O(N^2) - dense and simple, appropriate at N~100
/// (ADR-001's universe size); a heap-based O(E log N) approach would
/// only matter at a scale this project isn't targeting.
std::set<std::pair<int, int>> minimum_spanning_tree_edges(const Eigen::MatrixXd& D) {
    const int n = static_cast<int>(D.rows());
    std::set<std::pair<int, int>> mst;
    if (n < 2) return mst;

    std::vector<bool> in_tree(static_cast<std::size_t>(n), false);
    std::vector<double> min_edge(static_cast<std::size_t>(n), std::numeric_limits<double>::infinity());
    std::vector<int> nearest_in_tree(static_cast<std::size_t>(n), -1);

    in_tree[0] = true;
    for (int j = 1; j < n; ++j) {
        min_edge[static_cast<std::size_t>(j)] = D(0, j);
        nearest_in_tree[static_cast<std::size_t>(j)] = 0;
    }

    for (int step = 1; step < n; ++step) {
        int best = -1;
        double best_dist = std::numeric_limits<double>::infinity();
        for (int j = 0; j < n; ++j) {
            if (!in_tree[static_cast<std::size_t>(j)] && min_edge[static_cast<std::size_t>(j)] < best_dist) {
                best_dist = min_edge[static_cast<std::size_t>(j)];
                best = j;
            }
        }
        // best == -1 would mean the graph is disconnected under D, which
        // cannot happen here: D is a dense matrix over every ticker
        // pair (correlation distance is always defined), so every node
        // has a finite distance to every other node.
        in_tree[static_cast<std::size_t>(best)] = true;
        mst.insert(canonical(best, nearest_in_tree[static_cast<std::size_t>(best)]));

        for (int j = 0; j < n; ++j) {
            if (!in_tree[static_cast<std::size_t>(j)] && D(best, j) < min_edge[static_cast<std::size_t>(j)]) {
                min_edge[static_cast<std::size_t>(j)] = D(best, j);
                nearest_in_tree[static_cast<std::size_t>(j)] = best;
            }
        }
    }
    return mst;
}

} // namespace

Result<std::vector<Edge>> knn_and_mst_edges(const Eigen::MatrixXd& D, int k) {
    const Eigen::Index n = D.rows();
    if (D.rows() != D.cols()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "D must be square"));
    }
    if (k < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "k must be >= 1"));
    }
    if (n < k + 1) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "fewer nodes than k+1 - every node needs k distinct neighbours",
            "n=" + std::to_string(n) + ", k=" + std::to_string(k)));
    }
    for (Eigen::Index i = 0; i < n; ++i) {
        if (std::abs(D(i, i)) > kRoundoffTolerance) {
            return tl::unexpected(
                gm::Error::make(gm::ErrorCode::kInvalidArgument, "D has a nonzero diagonal entry",
                                 "index " + std::to_string(i)));
        }
        for (Eigen::Index j = i + 1; j < n; ++j) {
            if (std::abs(D(i, j) - D(j, i)) > kRoundoffTolerance) {
                return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "D is not symmetric",
                                                       "(" + std::to_string(i) + "," + std::to_string(j) + ")"));
            }
        }
    }

    const int nn = static_cast<int>(n);
    std::set<std::pair<int, int>> knn_set;

    // Symmetric closure of each node's own k-NN set: node i's k nearest
    // neighbours are found by sorting ITS OWN row, independent of
    // whether those neighbours reciprocate - see the header comment on
    // why the union (not the intersection) is what's returned.
    for (int i = 0; i < nn; ++i) {
        std::vector<int> others;
        others.reserve(static_cast<std::size_t>(nn - 1));
        for (int j = 0; j < nn; ++j) {
            if (j != i) others.push_back(j);
        }
        std::partial_sort(others.begin(), others.begin() + k, others.end(),
                           [&](int a, int b) { return D(i, a) < D(i, b); });
        for (int idx = 0; idx < k; ++idx) {
            knn_set.insert(canonical(i, others[static_cast<std::size_t>(idx)]));
        }
    }

    std::set<std::pair<int, int>> mst = minimum_spanning_tree_edges(D);

    // Union of both sets for the returned edge list - every MST edge is
    // included even when it falls outside every endpoint's own k-NN set
    // (a legitimate "bridge" between otherwise distant clusters, needed
    // for the viewer's MST overlay to render the complete tree) - but
    // in_knn and in_mst are tracked and reported independently, so a
    // consumer that only wants genuine k-nearest-neighbour relationships
    // (gm-signals' peer-basket selection) can filter on in_knn alone
    // without accidentally picking up an MST-only bridge.
    std::set<std::pair<int, int>> edge_set = knn_set;
    for (const auto& e : mst) edge_set.insert(e);

    std::vector<Edge> result;
    result.reserve(edge_set.size());
    for (const auto& [i, j] : edge_set) {
        result.push_back(Edge{i, j, D(i, j), mst.count({i, j}) > 0, knn_set.count({i, j}) > 0});
    }
    return result;
}

} // namespace gm::geometry
