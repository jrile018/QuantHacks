#pragma once

// gm-topology: Vietoris-Rips persistent homology (H0, H1) computation via
// the real vendored Ripser reference implementation (Bauer 2021,
// third_party/ripser/ripser.hpp - see ADR-012). This wrapper builds a
// distance matrix from a point cloud, runs the actual Ripser algorithm
// (not a hand-rolled approximation), and parses its persistence-interval
// text output back into structured (birth, death) pairs.
//
// Ripser's reference implementation is a CLI tool: compute_barcodes()
// only emits its results via std::cout, gated behind
// PRINT_PERSISTENCE_PAIRS, with no programmatic accessor. This header
// defines that macro, redirects std::cout into a local buffer for the
// duration of the call, and parses the captured "persistence intervals
// in dim N:" / " [birth,death)" / " [birth, )" text back into
// PersistencePair values - a minimal, behavior-preserving adaptation of
// the reference tool into a library call. The actual algorithm
// (third_party/ripser/ripser.hpp) is untouched except for guarding its
// CLI main() out via RIPSER_BUILD_CLI, which this header does not
// define, so main() never gets compiled into this library.

// The vendored reference implementation predates this codebase's
// -Wconversion -Wsign-conversion -Werror policy (ADR-004) and was never
// written to satisfy it - this is third-party code we deliberately do
// not modify beyond the RIPSER_BUILD_CLI guard, so its warnings are
// suppressed locally rather than either weakening the project-wide
// warning policy or hand-editing every index_t/size_t site in someone
// else's reference algorithm.
#define PRINT_PERSISTENCE_PAIRS

// Guarded because MSVC does not know `#pragma GCC` and warns C4068 for
// each one - which /WX then turns into an error, so the unguarded version
// failed the Windows build on the suppressions themselves rather than on
// anything they were suppressing.
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wconversion"
#pragma GCC diagnostic ignored "-Wsign-conversion"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wignored-qualifiers"
#pragma GCC diagnostic ignored "-Wfloat-conversion"
#pragma GCC diagnostic ignored "-Wsign-compare"
#elif defined(_MSC_VER)
#pragma warning(push)
#pragma warning(disable : 4244)  // conversion, possible loss of data
#pragma warning(disable : 4245)  // signed/unsigned mismatch in conversion
#pragma warning(disable : 4267)  // size_t to smaller type
#pragma warning(disable : 4100)  // unreferenced formal parameter
#pragma warning(disable : 4389)  // signed/unsigned mismatch in comparison
#pragma warning(disable : 4018)  // signed/unsigned mismatch
#pragma warning(disable : 4456)  // declaration hides previous local
#pragma warning(disable : 4457)  // declaration hides function parameter
#pragma warning(disable : 4458)  // declaration hides class member
#pragma warning(disable : 4459)  // declaration hides global
#endif

#include <ripser/ripser.hpp>

#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic pop
#elif defined(_MSC_VER)
#pragma warning(pop)
#endif

#include <gm-core/error.hpp>
#include <tl/expected.hpp>

#include <Eigen/Dense>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

namespace gm::topology {

/// A single persistence pair: (birth, death) diameter values.
struct PersistencePair {
    double birth;
    double death;
};

/// H0/H1 persistence features for a single frame.
struct PersistenceFeatures {
    double h0_total_persistence = 0.0;
    std::vector<PersistencePair> h0_pairs;

    double h1_total_persistence = 0.0;
    std::vector<PersistencePair> h1_pairs;
};

inline double euclidean_distance(const Eigen::MatrixXd& points,
                                  Eigen::Index i, Eigen::Index j) noexcept {
    return (points.row(i) - points.row(j)).norm();
}

/// Build a full Euclidean distance matrix from a point cloud (N x D, one
/// point per row).
inline gm::Result<Eigen::MatrixXd> distance_matrix_from_points(const Eigen::MatrixXd& points) {
    if (points.rows() < 2) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kInvalidArgument,
            "point cloud must have at least 2 points",
            std::to_string(points.rows()) + " points provided",
            std::source_location::current()});
    }

    Eigen::Index n = points.rows();
    Eigen::MatrixXd dist(n, n);
    for (Eigen::Index i = 0; i < n; ++i) {
        dist(i, i) = 0.0;
        for (Eigen::Index j = i + 1; j < n; ++j) {
            double d = euclidean_distance(points, i, j);
            dist(i, j) = d;
            dist(j, i) = d;
        }
    }
    return dist;
}

/// Deterministic (greedy, nearest-unmatched-first) approximate Wasserstein
/// distance between two persistence diagrams - ADR SS3 determinism (no RNG,
/// fixed iteration order); an exact optimal-transport solve is not needed
/// for a "shape change rate" signal.
inline gm::Result<double> wasserstein_distance(const std::vector<PersistencePair>& diagram1,
                                                const std::vector<PersistencePair>& diagram2) noexcept {
    if (diagram1.empty() && diagram2.empty()) return 0.0;

    double total_distance = 0.0;
    std::vector<bool> matched(diagram2.size(), false);
    for (const auto& p1 : diagram1) {
        double min_dist = std::numeric_limits<double>::infinity();
        int best_j = -1;
        for (std::size_t j = 0; j < diagram2.size(); ++j) {
            if (matched[j]) continue;
            const auto& p2 = diagram2[j];
            double dist = std::abs(p1.birth - p2.birth) + std::abs(p1.death - p2.death);
            if (dist < min_dist) {
                min_dist = dist;
                best_j = static_cast<int>(j);
            }
        }
        if (best_j >= 0) {
            matched[static_cast<std::size_t>(best_j)] = true;
            total_distance += min_dist;
        } else {
            total_distance += std::abs(p1.death - p1.birth);
        }
    }
    for (std::size_t j = 0; j < diagram2.size(); ++j) {
        if (!matched[j]) total_distance += std::abs(diagram2[j].death - diagram2[j].birth);
    }

    std::size_t max_size = std::max(diagram1.size(), diagram2.size());
    return max_size > 0 ? total_distance / static_cast<double>(max_size) : 0.0;
}

namespace detail {

/// RAII std::cout redirect - swaps the stream buffer to an internal
/// ostringstream for the lifetime of the guard and restores the original
/// on destruction (including on early return), so a failure partway
/// through never leaves std::cout silently redirected for the rest of
/// the program (which would otherwise be a very confusing bug to chase
/// down in an unrelated later log line).
class CoutCaptureGuard {
public:
    CoutCaptureGuard() : old_buf_(std::cout.rdbuf(buffer_.rdbuf())) {}
    ~CoutCaptureGuard() { std::cout.rdbuf(old_buf_); }
    CoutCaptureGuard(const CoutCaptureGuard&) = delete;
    CoutCaptureGuard& operator=(const CoutCaptureGuard&) = delete;

    std::string str() const { return buffer_.str(); }

private:
    std::ostringstream buffer_;
    std::streambuf* old_buf_;
};

/// Parse Ripser's "persistence intervals in dim N:" text output into
/// per-dimension vectors of PersistencePair. Infinite-death pairs
/// (" [birth, )") are capped at `threshold` (the enclosing radius used
/// to build the complex) rather than dropped, since an uncapped H0
/// component that never dies is a well-known, expected feature (the
/// whole point cloud is one component at infinite scale) and dropping
/// it silently would make h0_total_persistence miss the dominant term.
inline void parse_ripser_output(const std::string& text, double threshold,
                                 std::vector<PersistencePair>& dim0,
                                 std::vector<PersistencePair>& dim1) {
    int current_dim = -1;
    std::istringstream lines(text);
    std::string line;
    while (std::getline(lines, line)) {
        if (line.find("persistence intervals in dim 0:") != std::string::npos) {
            current_dim = 0;
            continue;
        }
        if (line.find("persistence intervals in dim 1:") != std::string::npos) {
            current_dim = 1;
            continue;
        }
        if (line.find("persistence intervals in dim") != std::string::npos) {
            current_dim = -1;  // dim >= 2: not collected (dim_max is fixed at 1)
            continue;
        }
        auto lbracket = line.find('[');
        auto comma = line.find(',');
        auto rbracket = line.find(')');
        if (lbracket == std::string::npos || comma == std::string::npos ||
            rbracket == std::string::npos || (current_dim != 0 && current_dim != 1)) {
            continue;
        }
        try {
            double birth = std::stod(line.substr(lbracket + 1, comma - lbracket - 1));
            std::string death_str = line.substr(comma + 1, rbracket - comma - 1);
            death_str.erase(0, death_str.find_first_not_of(' '));
            double death = death_str.empty() ? threshold : std::stod(death_str);
            (current_dim == 0 ? dim0 : dim1).push_back({birth, death});
        } catch (const std::exception&) {
            continue;  // malformed line - skip rather than crash on a parse hiccup
        }
    }
}

}  // namespace detail

/// Compute real H0/H1 persistence for a point cloud by running Ripser's
/// actual Vietoris-Rips algorithm (not a hand-rolled approximation).
inline gm::Result<PersistenceFeatures> compute_persistence(const Eigen::MatrixXd& point_cloud) {
    if (point_cloud.rows() < 2) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kInvalidArgument,
            "point cloud must have at least 2 points",
            std::to_string(point_cloud.rows()) + " points provided",
            std::source_location::current()});
    }

    auto dist_result = distance_matrix_from_points(point_cloud);
    if (!dist_result) return tl::unexpected(dist_result.error());
    const Eigen::MatrixXd& dist = *dist_result;
    auto n = static_cast<std::size_t>(point_cloud.rows());

    // Flatten to Ripser's lower-triangular layout: for i in 1..n-1, for j
    // in 0..i-1, append dist(i,j) - matches compressed_lower_distance_matrix's
    // init_rows() layout exactly (see third_party/ripser/ripser.hpp).
    // Ripser's value_t is float, not double (a property of the vendored
    // reference implementation, not something this wrapper changes) - the
    // flat vector's element type must match float exactly, or the intended
    // std::vector<value_t>&& move constructor silently fails to match
    // overload resolution and falls through to a completely different,
    // broken constructor. Full double precision is preserved everywhere
    // else in this wrapper (the parsed birth/death output, the enclosing-
    // radius computation below); only Ripser's own internal computation
    // runs at float precision, same as the reference tool always has.
    std::vector<float> flat;
    flat.reserve(n * (n - 1) / 2);
    for (std::size_t i = 1; i < n; ++i) {
        for (std::size_t j = 0; j < i; ++j) {
            flat.push_back(static_cast<float>(
                dist(static_cast<Eigen::Index>(i), static_cast<Eigen::Index>(j))));
        }
    }

    // Enclosing radius: the same default threshold Ripser's own CLI uses
    // when none is given (main(), third_party/ripser/ripser.hpp) - the
    // smallest radius such that every point has at least one neighbor
    // within it, bounding the complex to the range that matters.
    double enclosing_radius = std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < n; ++i) {
        double r_i = -std::numeric_limits<double>::infinity();
        for (std::size_t j = 0; j < n; ++j) {
            r_i = std::max(r_i, dist(static_cast<Eigen::Index>(i), static_cast<Eigen::Index>(j)));
        }
        enclosing_radius = std::min(enclosing_radius, r_i);
    }

    ripser<compressed_lower_distance_matrix> r(
        compressed_lower_distance_matrix(std::move(flat)),
        /*dim_max=*/1, /*threshold=*/static_cast<float>(enclosing_radius), /*ratio=*/1.0f,
        /*modulus=*/2);

    std::string captured;
    {
        detail::CoutCaptureGuard guard;
        r.compute_barcodes();
        captured = guard.str();
    }

    PersistenceFeatures features;
    detail::parse_ripser_output(captured, enclosing_radius, features.h0_pairs, features.h1_pairs);

    for (const auto& p : features.h0_pairs) features.h0_total_persistence += (p.death - p.birth);
    for (const auto& p : features.h1_pairs) features.h1_total_persistence += (p.death - p.birth);

    return features;
}

}  // namespace gm::topology
