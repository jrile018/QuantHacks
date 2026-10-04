#include "centrality.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cmath>

namespace {

constexpr double kTol = 1e-9;

// Two dates. On date1, sector "X" has {AAA, BBB} and sector "Y" has
// {CCC}. On date2, ticker "DDD" joins sector "X" partway through (a new
// listing / new universe member), and sector "Y" still has just {CCC}.
// This is the exact shape the review asked for: a ticker that enters
// partway through the universe.
struct Fixture {
    std::vector<std::string> dates = {
        "2020-01-01", "2020-01-01", "2020-01-01",              // date1: AAA, BBB (X), CCC (Y)
        "2020-01-02", "2020-01-02", "2020-01-02", "2020-01-02",  // date2: + DDD (X)
    };
    std::vector<std::string> tickers = {"AAA", "BBB", "CCC", "AAA", "BBB", "CCC", "DDD"};
    std::vector<std::string> sectors = {"X", "X", "Y", "X", "X", "Y", "X"};
};

} // namespace

TEST_CASE("compute_pit_sector_centrality is point-in-time, not look-ahead", "[gm-features][centrality]") {
    Fixture fx;
    auto centrality = gm::features::compute_pit_sector_centrality(fx.dates, fx.tickers, fx.sectors);
    REQUIRE(centrality.size() == fx.dates.size());

    // date1: sector X has 2 members (AAA, BBB), sector Y has 1 (CCC).
    // max sector size on date1 is 2, so divisor is 3.
    CHECK(std::abs(centrality[0] - 2.0 / 3.0) < kTol);  // AAA
    CHECK(std::abs(centrality[1] - 2.0 / 3.0) < kTol);  // BBB
    CHECK(std::abs(centrality[2] - 1.0 / 3.0) < kTol);  // CCC

    // date2: sector X now has 3 members (AAA, BBB, DDD) because DDD
    // joined; sector Y still has 1 (CCC). max sector size on date2 is
    // 3, so divisor is 4.
    CHECK(std::abs(centrality[3] - 3.0 / 4.0) < kTol);  // AAA
    CHECK(std::abs(centrality[4] - 3.0 / 4.0) < kTol);  // BBB
    // CCC on date2: sector Y size is still 1, but the DIVISOR changed
    // (max sector size is now 3, not 2) because DDD joined sector X -
    // this divisor is a real per-date quantity, not stale.
    CHECK(std::abs(centrality[5] - 1.0 / 4.0) < kTol);  // CCC
    CHECK(std::abs(centrality[6] - 3.0 / 4.0) < kTol);  // DDD

    // The critical look-ahead-bias check: AAA's centrality on date1
    // must be UNAFFECTED by DDD joining on date2. If this were still
    // computed from the whole-file ticker set (the old bug), AAA's
    // date1 value would incorrectly already reflect DDD's membership.
    CHECK(centrality[0] != centrality[3]);
}

TEST_CASE("compute_pit_sector_centrality: single date matches simple formula", "[gm-features][centrality]") {
    std::vector<std::string> dates = {"2020-01-01", "2020-01-01"};
    std::vector<std::string> tickers = {"AAA", "BBB"};
    std::vector<std::string> sectors = {"X", "X"};
    auto centrality = gm::features::compute_pit_sector_centrality(dates, tickers, sectors);
    REQUIRE(centrality.size() == 2);
    // Only sector, 2 members, divisor 3.
    CHECK(std::abs(centrality[0] - 2.0 / 3.0) < kTol);
    CHECK(std::abs(centrality[1] - 2.0 / 3.0) < kTol);
}
