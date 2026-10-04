#include <cmath>
#include "../data_loader.hpp"

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <map>
#include <set>

using gm::view::load_run;
using gm::view::LoadedRun;

namespace {

/// Resolves the real run directory these tests load against.
///
/// Prefers GM_VIEW_TEST_RUN_DIR when set, so any machine/CI can point
/// this at whatever real run it has without editing source. Otherwise
/// falls back to "runs/m6-review" resolved relative to *this source
/// file's own location* (repo_root/runs/m6-review) rather than a
/// hardcoded machine-specific absolute path (the previous
/// /home/john-riley/... literal broke on any other checkout, and a
/// worktree - see FIX report - is exactly such a case). Real run data
/// is gitignored and provisioned per-machine the same way every other
/// stage's runs/ directory is; each checkout/worktree that wants to run
/// these tests needs its own runs/m6-review (a symlink to a shared copy
/// works fine).
///
/// m6-review is a real M6 run (git_commit 3375f90e637d, the exact
/// commit this branch forked from): 3-estimator scores.parquet
/// (mahalanobis/fastmcd/kde - unlike the old pre-M6 m1-full-2010-2026
/// fixture this used to point at, which predates View C/the kde
/// estimator entirely) and gm-signals' tear-vetoed spreads.parquet
/// (ADR-012's regime.parquet tear_flag veto).
std::filesystem::path test_run_dir() {
    if (const char* env = std::getenv("GM_VIEW_TEST_RUN_DIR"); env != nullptr && *env != '\0') {
        return std::filesystem::path(env);
    }
    std::filesystem::path here = std::filesystem::path(__FILE__).parent_path();
    return here / ".." / ".." / ".." / "runs" / "m6-review";
}

// A real-data audit found these tests hard-fail (10/10) on a fresh
// clone: runs/ is entirely gitignored and nothing provisions
// runs/m6-review, so REQUIRE(result) fails immediately with no
// explanation. Every test now checks this first and SKIPs (not FAILs)
// when the fixture isn't there - a missing optional local fixture is
// not the same claim as "the code under test is broken", and a
// fresh-clone CI run should say so rather than reporting 10 failures.
bool test_fixture_available() {
    std::error_code ec;
    return std::filesystem::exists(test_run_dir(), ec) && !ec;
}

}  // namespace

TEST_CASE("load_run loads all data structures from real run directory", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    
    const LoadedRun& run = *result;
    CHECK(!run.frames.empty());
    for (const auto& frame : run.frames) {
        CHECK(!frame.date.empty());
        CHECK(frame.tickers.size() == frame.positions.size());
        CHECK(frame.tickers.size() > 0);
    }
}

TEST_CASE("load_run loads ticker metadata from universe.parquet", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    
    const LoadedRun& run = *result;
    CHECK(!run.ticker_metadata.empty());
    CHECK(run.ticker_metadata.size() > 90);
    
    for (const auto& [ticker, meta] : run.ticker_metadata) {
        CHECK(!meta.ticker.empty());
        CHECK(meta.ticker == ticker);
        CHECK(!meta.security_name.empty());
        CHECK(!meta.gics_sector.empty());
    }
}

TEST_CASE("load_run loads scores from scores.parquet", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    
    const LoadedRun& run = *result;
    CHECK(!run.scores.empty());
    
    for (const auto& score : run.scores) {
        CHECK(!score.date.empty());
        CHECK(!score.ticker.empty());
        CHECK(!score.view.empty());
        CHECK(!score.estimator.empty());
        // depth is a SIGNED margin from the boundary (negative = inside,
        // positive = outside) - not a magnitude - so it legitimately
        // goes negative for the large majority of (ticker, date) pairs
        // that are unremarkable on a given day. The real invariant is
        // that its sign agrees with the inside flag gm-boundaries wrote
        // (see libs/gm-boundaries: bool inside = depth <= 0.0).
        CHECK((score.depth <= 0.0) == score.inside);
        // pvalue is only meaningful for estimators with a parametric
        // reference distribution (mahalanobis, fastmcd - both use a
        // chi-squared complement CDF). The kde estimator has no such
        // distribution and legitimately reports NaN - confirmed by
        // checking the real data directly: every pvalue=NaN row in
        // this run real scores.parquet is estimator="kde".
        if (score.estimator == "kde") {
            CHECK(std::isnan(score.pvalue));
        } else {
            CHECK((score.pvalue >= 0.0 && score.pvalue <= 1.0));
        }
    }
}

TEST_CASE("load_run loads spreads from spreads.parquet", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    
    const LoadedRun& run = *result;
    CHECK(!run.spreads.empty());
    
    for (const auto& spread : run.spreads) {
        CHECK(!spread.date.empty());
        CHECK(!spread.ticker.empty());
        CHECK(spread.n_neighbors > 0);
    }
}

TEST_CASE("load_run loads baskets from baskets.parquet", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    
    const LoadedRun& run = *result;
    CHECK(!run.baskets.empty());
    
    for (const auto& basket : run.baskets) {
        CHECK(!basket.date.empty());
        CHECK(!basket.ticker.empty());
        CHECK(!basket.neighbor_ticker.empty());
        CHECK((basket.weight >= 0.0 && basket.weight <= 1.0));
    }
}

TEST_CASE("load_run loads excursions from excursions.parquet", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    
    const LoadedRun& run = *result;
    CHECK(!run.excursions.empty());
    
    for (const auto& exc : run.excursions) {
        CHECK(!exc.ticker.empty());
        CHECK(!exc.start_date.empty());
        CHECK(!exc.end_date.empty());
        CHECK(exc.peak_depth > 0.0);
        CHECK(exc.duration_days >= 0); // a same-day excursion (enter/revert within one session) legitimately has duration 0
    }
}

TEST_CASE("geometry frame data can be associated with metadata", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);

    const LoadedRun& run = *result;
    for (const auto& frame : run.frames) {
        for (const auto& ticker : frame.tickers) {
            CHECK(run.ticker_metadata.find(ticker) != run.ticker_metadata.end());
        }
    }
}

TEST_CASE("load_run builds ticker/date indices matching the raw vectors", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);

    const LoadedRun& run = *result;
    std::size_t indexed_scores = 0;
    for (const auto& [key, rows] : run.scores_by_ticker_date) indexed_scores += rows.size();
    CHECK(indexed_scores == run.scores.size());

    std::size_t indexed_baskets = 0;
    for (const auto& [key, rows] : run.baskets_by_ticker_date) indexed_baskets += rows.size();
    CHECK(indexed_baskets == run.baskets.size());

    std::size_t indexed_excursions = 0;
    for (const auto& [ticker, rows] : run.excursions_by_ticker) indexed_excursions += rows.size();
    CHECK(indexed_excursions == run.excursions.size());
}

TEST_CASE("Learn panel ticker/date lookup: indexed vs linear scan on real M6 data", "[data_loader][performance]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    // Reproduces the Learn panel's per-frame cost before/after the
    // scores_by_ticker_date/baskets_by_ticker_date indices: a linear
    // scan of every loaded scores/baskets row (what
    // main.cpp used to do on every single rendered frame) vs. the
    // indexed O(log n) lookup it does now. Run against the real M6
    // data (1.82M+ score rows, 3.92M+ basket rows - see gm-boundaries
    // and gm-signals manifest.json rows_written/basket_rows_written in
    // this run), not a synthetic fixture, so the measured gap is real.
    auto result = load_run(test_run_dir());
    REQUIRE(result);
    const LoadedRun& run = *result;
    REQUIRE(!run.scores.empty());
    REQUIRE(!run.baskets.empty());

    const std::string ticker = run.scores.front().ticker;
    const std::string date = run.scores.front().date;

    auto linear_scan = [&]() {
        std::size_t hits = 0;
        for (const auto& score : run.scores) {
            if (score.ticker == ticker && score.date == date) ++hits;
        }
        for (const auto& basket : run.baskets) {
            if (basket.ticker == ticker && basket.date == date) ++hits;
        }
        return hits;
    };
    auto indexed_lookup = [&]() {
        std::size_t hits = 0;
        auto scores_it = run.scores_by_ticker_date.find({ticker, date});
        if (scores_it != run.scores_by_ticker_date.end()) hits += scores_it->second.size();
        auto baskets_it = run.baskets_by_ticker_date.find({ticker, date});
        if (baskets_it != run.baskets_by_ticker_date.end()) hits += baskets_it->second.size();
        return hits;
    };

    // Same (ticker, date): the index must agree with the ground-truth scan.
    REQUIRE(linear_scan() == indexed_lookup());

    constexpr int kSimulatedFrames = 100;
    auto scan_start = std::chrono::steady_clock::now();
    std::size_t scan_sink = 0;
    for (int i = 0; i < kSimulatedFrames; ++i) scan_sink += linear_scan();
    auto scan_end = std::chrono::steady_clock::now();

    std::size_t index_sink = 0;
    auto index_start = std::chrono::steady_clock::now();
    for (int i = 0; i < kSimulatedFrames; ++i) index_sink += indexed_lookup();
    auto index_end = std::chrono::steady_clock::now();

    CHECK(scan_sink == index_sink);  // both approaches must find the same rows

    double scan_ms_per_frame =
        std::chrono::duration<double, std::milli>(scan_end - scan_start).count() / kSimulatedFrames;
    double index_ms_per_frame =
        std::chrono::duration<double, std::milli>(index_end - index_start).count() / kSimulatedFrames;

    std::cerr << "[data_loader][performance] real M6 data: " << run.scores.size() << " score rows, "
              << run.baskets.size() << " basket rows -> linear scan " << scan_ms_per_frame
              << " ms/simulated-frame, indexed lookup " << index_ms_per_frame
              << " ms/simulated-frame (" << (scan_ms_per_frame / std::max(index_ms_per_frame, 1e-6))
              << "x faster)\n";

    // The index must be dramatically faster - not a tight timing race
    // that could flake under load. A conservative, hardware-independent
    // bound: still >=20x faster than the O(rows) scan.
    CHECK(index_ms_per_frame * 20.0 < scan_ms_per_frame);
}

TEST_CASE("load_run loads meta/profiles.json when present", "[data_loader]") {
    if (!test_fixture_available()) { SKIP("real run fixture not provisioned - set GM_VIEW_TEST_RUN_DIR or provision runs/m6-review"); }
    auto result = load_run(test_run_dir());
    REQUIRE(result);

    const LoadedRun& run = *result;
    std::error_code ec;
    bool profiles_file_exists =
        std::filesystem::exists(test_run_dir() / "meta" / "profiles.json", ec);
    if (!profiles_file_exists) {
        // Not every run has been through gm-profiles yet - this is a
        // legitimate state, not a failure (the Learn panel is expected
        // to show "no profile data" for such a run).
        SUCCEED("no meta/profiles.json for this run - skipping profile content checks");
        return;
    }

    CHECK(!run.profiles.empty());
    for (const auto& [ticker, profile] : run.profiles) {
        CHECK(!profile.ticker.empty());
        // Canonical schema (apps/gm-profiles/main.cpp, data_loader.hpp):
        // ticker/company_name/sic_code/sic_description/edgar_url, with
        // sic_code as a STRING - this would throw during parsing (and
        // this REQUIRE above would already have failed) if the writer
        // and reader schemas had drifted back out of agreement.
        CHECK(profile.ticker == ticker);
    }
}
