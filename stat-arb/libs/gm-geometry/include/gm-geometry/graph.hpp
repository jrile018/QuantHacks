#pragma once

// k-nearest-neighbour and minimum-spanning-tree edges over a Mantegna
// correlation-distance matrix D(t) (ADR §6.4: View C's peer basket is
// built from "k nearest neighbours under D(t)" - the raw distance
// matrix, not the 3D MDS embedding, since embedding to k=3 for display
// loses information the full distance matrix still has). Also the
// source of the ADR's documented edges.parquet artifact (ticker_a,
// ticker_b, distance, in_mst) and, downstream, the viewer's MST overlay
// and gm-signals' peer-basket selection - one canonical computation
// feeding both, per ADR §3 principle 3 (one-way data flow: no stage
// recomputes what an earlier stage already established).

#include <gm-core/error.hpp>

#include <Eigen/Dense>

#include <string>
#include <vector>

namespace gm::geometry {

struct Edge {
    int i;
    int j; // i < j always - one canonical direction per unordered pair
    double distance;
    bool in_mst;
    // Whether this edge belongs to the symmetric closure of some node's
    // own k-nearest-neighbour set (as opposed to existing ONLY because
    // it's an MST bridge - see the header comment on why the union
    // needs this distinction). View C's peer-basket selection (gm-signals)
    // must filter on this, not in_mst: an MST bridge between distant
    // clusters is a real graph edge but not a genuine "these two names
    // behave alike" relationship, and using one as a hedge component
    // would be financially nonsensical even though it's a legitimate
    // edge for the viewer's MST overlay.
    bool in_knn;
};

/// D must be square, symmetric (within floating-point tolerance), with
/// a zero diagonal - the same distance matrix gm-geometry already
/// builds per frame (distance.hpp). Returns every edge that belongs to
/// EITHER endpoint's k-nearest-neighbour set (the symmetric closure of
/// a directed k-NN relation, flagged in_knn=true) - not just edges
/// where both directions agree - so a strong one-directional neighbour
/// relationship (i's closest match is j, even if j has k closer options
/// than i) is never silently dropped. Each returned edge additionally
/// reports whether it is also part of the graph's minimum spanning tree
/// (in_mst), computed once over the same D and merged in here rather
/// than as a second pass a caller would have to reconcile by hand. The
/// two flags are independent: an edge can be in_knn only, in_mst only
/// (a bridge outside every endpoint's own k-NN list), or both.
[[nodiscard]] Result<std::vector<Edge>> knn_and_mst_edges(const Eigen::MatrixXd& D, int k);

} // namespace gm::geometry
