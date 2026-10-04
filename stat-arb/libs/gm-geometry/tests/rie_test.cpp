// Tests for the rotationally-invariant correlation estimator.
//
// The q -> 0 limit is the principled one: with a long enough window
// there is nothing to clean, and any estimator that does not hand back
// what it was given in that limit is doing something other than
// correcting for sample noise. The noise-compression and
// signal-preservation pair are the two halves of "does it work".

#include <gm-geometry/correlation.hpp>
#include <gm-geometry/rie.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <cstdint>
#include <vector>

using Catch::Approx;
using gm::geometry::rie_clean_correlation;
using gm::geometry::sample_correlation;

namespace {

/// Hand-rolled xorshift, per ADR-003: the tests must assert the same
/// thing on every platform and standard-library implementation, which
/// rules out <random>'s distributions.
struct Xorshift {
    std::uint64_t state = 0x9E3779B97F4A7C15ULL;
    double next_gaussian() {
        // Box-Muller from two uniforms, deterministic given the seed.
        const double u1 = next_uniform();
        const double u2 = next_uniform();
        return std::sqrt(-2.0 * std::log(u1 + 1e-12)) * std::cos(6.283185307179586 * u2);
    }
    double next_uniform() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        return static_cast<double>(state >> 11) / 9007199254740992.0;
    }
};

/// T x N of independent noise - a panel with no common structure at all,
/// so every eigenvalue of the true correlation is exactly 1 and the
/// entire observed spread is sampling error.
Eigen::MatrixXd pure_noise_panel(int T, int N, std::uint64_t seed) {
    Xorshift rng{seed};
    Eigen::MatrixXd out(T, N);
    for (int t = 0; t < T; ++t) {
        for (int i = 0; i < N; ++i) out(t, i) = rng.next_gaussian();
    }
    return out;
}

}  // namespace

TEST_CASE("with a long enough window the RIE returns what it was given",
          "[gm-geometry][rie]") {
    // q = N/T -> 0 means the sample correlation IS the true correlation,
    // and the estimator must become the identity map. Algebraically the
    // correction factor |1 - q + q*z*g|^2 -> 1, so every eigenvalue is
    // returned unchanged; numerically this pins the whole expression,
    // because almost any sign or factor error breaks it.
    const Eigen::MatrixXd panel = pure_noise_panel(400, 8, 12345);
    const auto corr = sample_correlation(panel);
    REQUIRE(corr.has_value());

    const auto rie = rie_clean_correlation(*corr, 1e-6);
    REQUIRE(rie.has_value());

    for (Eigen::Index i = 0; i < corr->rows(); ++i) {
        for (Eigen::Index j = 0; j < corr->cols(); ++j) {
            CHECK(rie->cleaned_correlation(i, j) == Approx((*corr)(i, j)).margin(1e-6));
        }
    }
}

TEST_CASE("the RIE compresses spectrum that is only sampling noise", "[gm-geometry][rie]") {
    // 100 assets on a 200-day window: q = 0.5, the regime this project
    // actually runs in. The truth is the identity, so every eigenvalue
    // SHOULD be 1 and the observed spread from roughly 0.1 to 3 is
    // entirely noise. A working estimator pulls that spread in hard.
    const int T = 200, N = 100;
    const Eigen::MatrixXd panel = pure_noise_panel(T, N, 99);
    const auto corr = sample_correlation(panel);
    REQUIRE(corr.has_value());

    const auto rie = rie_clean_correlation(*corr, static_cast<double>(N) / static_cast<double>(T));
    REQUIRE(rie.has_value());

    const double sample_spread =
        rie->sample_eigenvalues.maxCoeff() - rie->sample_eigenvalues.minCoeff();
    const double cleaned_spread =
        rie->cleaned_eigenvalues.maxCoeff() - rie->cleaned_eigenvalues.minCoeff();

    CHECK(cleaned_spread < sample_spread);
    // The cleaned spectrum should sit much closer to the truth of all
    // ones than the raw one does.
    const double sample_rms =
        std::sqrt((rie->sample_eigenvalues.array() - 1.0).square().mean());
    const double cleaned_rms =
        std::sqrt((rie->cleaned_eigenvalues.array() - 1.0).square().mean());
    CHECK(cleaned_rms < sample_rms);
}

TEST_CASE("the RIE keeps a real common factor", "[gm-geometry][rie]") {
    // An estimator that merely squashes everything toward one would pass
    // the compression test above and be useless. This is the other half:
    // a genuine market-wide factor must survive, in both its size and
    // its direction.
    const int T = 200, N = 60;
    Xorshift rng{2024};
    Eigen::MatrixXd panel(T, N);
    for (int t = 0; t < T; ++t) {
        const double market = rng.next_gaussian();
        for (int i = 0; i < N; ++i) {
            panel(t, i) = 0.8 * market + 0.6 * rng.next_gaussian();
        }
    }
    const auto corr = sample_correlation(panel);
    REQUIRE(corr.has_value());
    const auto rie = rie_clean_correlation(*corr, static_cast<double>(N) / static_cast<double>(T));
    REQUIRE(rie.has_value());

    // The factor eigenvalue is far outside the noise bulk and must stay
    // dominant rather than being clipped away with the noise.
    const double top_sample = rie->sample_eigenvalues(N - 1);
    const double top_cleaned = rie->cleaned_eigenvalues(N - 1);
    const double second_cleaned = rie->cleaned_eigenvalues(N - 2);
    CHECK(top_sample > 10.0);
    CHECK(top_cleaned > 10.0);
    CHECK(top_cleaned > 5.0 * second_cleaned);
}

TEST_CASE("the cleaned matrix is a correlation matrix", "[gm-geometry][rie]") {
    // Downstream, mantegna_distance() needs a unit diagonal and a
    // symmetric matrix, and an eigenvalue map on its own guarantees
    // neither. Trace = N falls out of the unit diagonal and is the
    // cheapest check that the renormalisation actually happened.
    const int T = 150, N = 40;
    const Eigen::MatrixXd panel = pure_noise_panel(T, N, 7);
    const auto corr = sample_correlation(panel);
    REQUIRE(corr.has_value());
    const auto rie = rie_clean_correlation(*corr, static_cast<double>(N) / static_cast<double>(T));
    REQUIRE(rie.has_value());

    const Eigen::MatrixXd& c = rie->cleaned_correlation;
    for (Eigen::Index i = 0; i < c.rows(); ++i) {
        CHECK(c(i, i) == Approx(1.0));
        for (Eigen::Index j = 0; j < c.cols(); ++j) {
            CHECK(c(i, j) == Approx(c(j, i)).margin(1e-12));
            CHECK(std::abs(c(i, j)) <= 1.0 + 1e-9);
        }
    }
    CHECK(c.trace() == Approx(static_cast<double>(N)));
    // Positive semi-definite: a correlation matrix that is not cannot be
    // turned into a distance matrix.
    CHECK(rie->cleaned_eigenvalues.minCoeff() > -1e-9);
}

TEST_CASE("the RIE is deterministic", "[gm-geometry][rie]") {
    const Eigen::MatrixXd panel = pure_noise_panel(120, 30, 555);
    const auto corr = sample_correlation(panel);
    REQUIRE(corr.has_value());
    const auto a = rie_clean_correlation(*corr, 0.25);
    const auto b = rie_clean_correlation(*corr, 0.25);
    REQUIRE(a.has_value());
    REQUIRE(b.has_value());
    CHECK((a->cleaned_correlation - b->cleaned_correlation).cwiseAbs().maxCoeff() == 0.0);
}

TEST_CASE("the RIE rejects input it cannot clean", "[gm-geometry][rie]") {
    Eigen::MatrixXd square = Eigen::MatrixXd::Identity(4, 4);

    SECTION("non-positive q") {
        const auto r = rie_clean_correlation(square, 0.0);
        REQUIRE_FALSE(r.has_value());
        CHECK(r.error().code == gm::ErrorCode::kInvalidArgument);
    }
    SECTION("non-square") {
        const Eigen::MatrixXd oblong = Eigen::MatrixXd::Zero(3, 4);
        const auto r = rie_clean_correlation(oblong, 0.5);
        REQUIRE_FALSE(r.has_value());
        CHECK(r.error().code == gm::ErrorCode::kInvalidArgument);
    }
    SECTION("empty") {
        const Eigen::MatrixXd empty(0, 0);
        const auto r = rie_clean_correlation(empty, 0.5);
        REQUIRE_FALSE(r.has_value());
        CHECK(r.error().code == gm::ErrorCode::kInvalidArgument);
    }
    SECTION("asymmetric") {
        // Caught rather than silently symmetrized: an asymmetric matrix
        // arriving here means something upstream is wrong, and quietly
        // averaging it away would hide that.
        square(0, 1) = 0.5;
        square(1, 0) = -0.5;
        const auto r = rie_clean_correlation(square, 0.5);
        REQUIRE_FALSE(r.has_value());
        CHECK(r.error().code == gm::ErrorCode::kInvalidArgument);
    }
}
