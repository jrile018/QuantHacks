// ADR-020 layer 4: benchmarks on the frame loop, with a regression gate.
//
// The option to build these has been on since the project started, the
// dependency has been pinned since then, and no benchmark existed - so the
// rule that a regression beyond threshold fails a milestone had nothing to
// enforce it. This is that rule's subject.
//
// WHAT IS MEASURED, AND WHY THESE
// -------------------------------
// ADR-020 names "the frame loop (corr -> MDS -> align -> fit -> score)".
// That is the inner loop of gm-geometry and gm-boundaries: it runs once
// per trading day, ~4100 times on the real panel, and it is where every
// minute of a full run goes. Each stage is benchmarked separately as well
// as end to end, because a whole-loop regression tells you something got
// slower and a per-stage one tells you what.
//
// Sized at 81 names by 60 days - the real panel's shape (ADR-001's top-100
// liquidity screen yields ~81 survivors; ADR §6.2's window is 60 days), not
// a round number. A benchmark run at a size the system never sees measures
// a cache behaviour the system never has.
//
// The input is deterministic (a fixed seed, hand-rolled generator per
// ADR-003 - std::shuffle and the distribution engines are
// implementation-defined and would make the numbers incomparable across
// compilers). Same data every run, on every machine.

#include <gm-boundaries/fastmcd.hpp>
#include <gm-boundaries/kde.hpp>
#include <gm-boundaries/mahalanobis.hpp>
#include <gm-geometry/correlation.hpp>
#include <gm-geometry/distance.hpp>
#include <gm-geometry/mds.hpp>
#include <gm-geometry/procrustes.hpp>
#include <gm-geometry/shrinkage.hpp>

#include <benchmark/benchmark.h>

#include <Eigen/Dense>

#include <cstdint>

namespace {

constexpr int kTickers = 81;   // the real panel's surviving name count
constexpr int kWindow = 60;    // ADR 6.2's correlation window
constexpr int kDims = 3;       // the embedding the artifacts carry

/// A deterministic returns panel, [kWindow x kTickers].
///
/// Hand-rolled xorshift and a hand-rolled normal transform rather than
/// <random>: the standard distributions are implementation-defined, so the
/// same seed gives different numbers on different standard libraries and
/// the benchmark would not be comparing like with like across the two
/// platforms this project builds on.
Eigen::MatrixXd deterministic_returns() {
    std::uint64_t state = 0x9E3779B97F4A7C15ULL;
    const auto next = [&state]() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        // 53 bits into [0,1), the same construction everywhere.
        return static_cast<double>(state >> 11) / 9007199254740992.0;
    };

    Eigen::MatrixXd returns(kWindow, kTickers);
    for (int t = 0; t < kWindow; ++t) {
        // One shared market factor plus idiosyncratic noise, so the
        // correlation matrix has the leading eigenvalue real data has and
        // the RMT/shrinkage paths do the work they would really do. Pure
        // noise would make the market mode absent and the benchmark
        // unrepresentative of the thing it is timing.
        const double market = (next() - 0.5) * 0.02;
        for (int i = 0; i < kTickers; ++i) {
            returns(t, i) = market + (next() - 0.5) * 0.03;
        }
    }
    return returns;
}

const Eigen::MatrixXd& returns_panel() {
    static const Eigen::MatrixXd panel = deterministic_returns();
    return panel;
}

/// The embedding for one frame, computed once and reused by the benchmarks
/// that need coordinates rather than returns.
const Eigen::MatrixXd& embedding() {
    static const Eigen::MatrixXd coords = [] {
        auto shrunk = gm::geometry::ledoit_wolf_shrink_correlation(returns_panel());
        auto distance = gm::geometry::mantegna_distance(shrunk->correlation);
        auto mds = gm::geometry::classical_mds(*distance, kDims);
        return mds->coordinates;
    }();
    return coords;
}

} // namespace

static void BM_Shrinkage(benchmark::State& state) {
    for (auto _ : state) {
        auto result = gm::geometry::ledoit_wolf_shrink_correlation(returns_panel());
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_Shrinkage);

static void BM_MantegnaDistance(benchmark::State& state) {
    static const Eigen::MatrixXd corr =
        gm::geometry::ledoit_wolf_shrink_correlation(returns_panel())->correlation;
    for (auto _ : state) {
        auto result = gm::geometry::mantegna_distance(corr);
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_MantegnaDistance);

static void BM_ClassicalMds(benchmark::State& state) {
    static const Eigen::MatrixXd dist =
        *gm::geometry::mantegna_distance(
            gm::geometry::ledoit_wolf_shrink_correlation(returns_panel())->correlation);
    for (auto _ : state) {
        auto result = gm::geometry::classical_mds(dist, kDims);
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_ClassicalMds);

static void BM_ProcrustesAlign(benchmark::State& state) {
    // Aligning a frame against the previous one - what the real loop does
    // every day, and the reason x/y/z are not comparable across a change
    // to the embedding dimension.
    static const Eigen::MatrixXd reference = embedding();
    for (auto _ : state) {
        auto result = gm::geometry::align(embedding(), reference);
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_ProcrustesAlign);

static void BM_FitMahalanobis(benchmark::State& state) {
    for (auto _ : state) {
        auto result = gm::boundaries::fit_mahalanobis(embedding());
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_FitMahalanobis);

static void BM_FitKde(benchmark::State& state) {
    for (auto _ : state) {
        auto result = gm::boundaries::fit_kde(embedding(), 0.05);
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_FitKde);

static void BM_FitFastMcd(benchmark::State& state) {
    // The expensive one, and the one whose cost is worth watching: FastMCD
    // runs many C-step trials, so an accidental extra iteration or a
    // widened trial count is a real slowdown that no test would catch.
    for (auto _ : state) {
        auto result = gm::boundaries::fit_fastmcd(embedding());
        benchmark::DoNotOptimize(result);
    }
}
BENCHMARK(BM_FitFastMcd);

static void BM_FrameLoopEndToEnd(benchmark::State& state) {
    // corr -> MDS -> align -> fit -> score, exactly as ADR-020 names it.
    // The per-stage benchmarks above say WHERE a regression is; this one
    // says whether the thing anybody waits on got slower.
    static const Eigen::MatrixXd reference = embedding();
    for (auto _ : state) {
        auto shrunk = gm::geometry::ledoit_wolf_shrink_correlation(returns_panel());
        auto distance = gm::geometry::mantegna_distance(shrunk->correlation);
        auto mds = gm::geometry::classical_mds(*distance, kDims);
        auto aligned = gm::geometry::align(mds->coordinates, reference);
        auto fit = gm::boundaries::fit_mahalanobis(aligned->aligned);
        auto score = gm::boundaries::score_mahalanobis(*fit, aligned->aligned.row(0), 0.05);
        benchmark::DoNotOptimize(score);
    }
}
BENCHMARK(BM_FrameLoopEndToEnd);

BENCHMARK_MAIN();
