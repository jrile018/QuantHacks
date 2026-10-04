#include <gm-data/liquidity.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cstdio>

using gm::data::rank_by_liquidity;
using gm::io::Table;

namespace {

/// Builds a table with `days` bars for each of the given tickers, dates
/// "2024-01-01" ascending, with dollar_volume(ticker) = close*volume
/// constant across all its bars for simplicity - the test cares about
/// *ranking between tickers*, not intra-ticker variation, so a flat
/// series per ticker keeps each case's arithmetic obvious.
Table make_panel(const std::vector<std::pair<std::string, double>>& ticker_to_dollar_volume, int days) {
    std::vector<std::string> tickers, dates;
    std::vector<double> closes;
    std::vector<std::int64_t> volumes;

    for (const auto& [ticker, dv] : ticker_to_dollar_volume) {
        for (int d = 1; d <= days; ++d) {
            // Oversized for GCC's -Wformat-truncation worst-case
            // analysis on %02d given int's full range - see the
            // identical comment in gm-core/date.cpp and manifest.cpp.
            char buf[32];
            std::snprintf(buf, sizeof(buf), "2024-01-%02d", d);
            tickers.push_back(ticker);
            dates.push_back(buf);
            closes.push_back(100.0);
            volumes.push_back(static_cast<std::int64_t>(dv / 100.0));
        }
    }

    Table t;
    REQUIRE(t.add_string_column("ticker", std::move(tickers)).has_value());
    REQUIRE(t.add_string_column("date", std::move(dates)).has_value());
    REQUIRE(t.add_double_column("close", std::move(closes)).has_value());
    REQUIRE(t.add_int64_column("volume", std::move(volumes)).has_value());
    return t;
}

} // namespace

TEST_CASE("ranks tickers by descending median dollar volume", "[liquidity]") {
    auto panel = make_panel({{"LOW", 1'000'000.0}, {"HIGH", 100'000'000.0}, {"MID", 10'000'000.0}}, 5);

    auto ranked = rank_by_liquidity(panel, /*window_days=*/60, /*top_n=*/10);
    REQUIRE(ranked.has_value());
    REQUIRE(ranked->size() == 3);
    CHECK((*ranked)[0].ticker == "HIGH");
    CHECK((*ranked)[1].ticker == "MID");
    CHECK((*ranked)[2].ticker == "LOW");
}

TEST_CASE("top_n truncates the ranked list", "[liquidity]") {
    auto panel = make_panel({{"A", 300.0}, {"B", 200.0}, {"C", 100.0}}, 3);

    auto ranked = rank_by_liquidity(panel, 60, /*top_n=*/2);
    REQUIRE(ranked.has_value());
    REQUIRE(ranked->size() == 2);
    CHECK((*ranked)[0].ticker == "A");
    CHECK((*ranked)[1].ticker == "B");
}

TEST_CASE("a ticker with fewer bars than window_days is still ranked, not dropped", "[liquidity]") {
    // NEW has only 2 bars, far short of a 60-day window - still must
    // appear in the output (per the documented "don't bias toward
    // incumbents" contract), with bars_used reflecting the shortfall.
    auto panel = make_panel({{"OLD", 500.0}, {"NEW", 10'000.0}}, 2);

    auto ranked = rank_by_liquidity(panel, /*window_days=*/60, /*top_n=*/10);
    REQUIRE(ranked.has_value());
    REQUIRE(ranked->size() == 2);
    CHECK((*ranked)[0].ticker == "NEW");
    CHECK((*ranked)[0].bars_used == 2);
}

TEST_CASE("median uses only the trailing window, not the ticker's full history", "[liquidity]") {
    Table t;
    // AAPL: 5 low-volume days, then 3 recent high-volume days. A
    // 3-day window must see only the high-volume tail.
    REQUIRE(t.add_string_column("ticker", {"AAPL", "AAPL", "AAPL", "AAPL", "AAPL", "AAPL", "AAPL", "AAPL"})
                .has_value());
    REQUIRE(t.add_string_column("date", {"2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
                                          "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"})
                .has_value());
    REQUIRE(t.add_double_column("close", {100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0})
                .has_value());
    REQUIRE(t.add_int64_column("volume", {10, 10, 10, 10, 10, 100000, 100000, 100000}).has_value());

    auto ranked = rank_by_liquidity(t, /*window_days=*/3, /*top_n=*/10);
    REQUIRE(ranked.has_value());
    REQUIRE(ranked->size() == 1);
    CHECK((*ranked)[0].bars_used == 3);
    CHECK((*ranked)[0].median_dollar_volume == 100.0 * 100000.0);
}

TEST_CASE("invalid window_days or top_n is rejected", "[liquidity]") {
    auto panel = make_panel({{"A", 100.0}}, 1);
    CHECK_FALSE(rank_by_liquidity(panel, 0, 10).has_value());
    CHECK_FALSE(rank_by_liquidity(panel, -5, 10).has_value());
    CHECK_FALSE(rank_by_liquidity(panel, 60, 0).has_value());
    CHECK_FALSE(rank_by_liquidity(panel, 60, -1).has_value());
}

TEST_CASE("an empty price panel ranks nothing, without erroring", "[liquidity]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {}).has_value());
    REQUIRE(t.add_string_column("date", {}).has_value());
    REQUIRE(t.add_double_column("close", {}).has_value());
    REQUIRE(t.add_int64_column("volume", {}).has_value());

    auto ranked = rank_by_liquidity(t, 60, 100);
    REQUIRE(ranked.has_value());
    CHECK(ranked->empty());
}

TEST_CASE("a panel missing a required column fails cleanly", "[liquidity]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {"A"}).has_value());
    REQUIRE(t.add_string_column("date", {"2024-01-01"}).has_value());
    // no close/volume columns

    auto ranked = rank_by_liquidity(t, 60, 10);
    REQUIRE_FALSE(ranked.has_value());
    CHECK(ranked.error().code == gm::ErrorCode::kNotFound);
}

TEST_CASE("tickers tied on median dollar volume break the tie by ticker name, deterministically",
          "[liquidity]") {
    // Regression test for the M1 code review finding: the ranking
    // sort's comparator originally only looked at median_dollar_volume,
    // so an exact tie's relative order depended on std::unordered_map's
    // iteration order - itself unspecified and not guaranteed stable
    // across runs or platforms (ADR §3 principle 2: same inputs must
    // give bit-identical output). Every tied ticker here has the exact
    // same dollar volume; the only thing that can make the output
    // order well-defined is a secondary sort key.
    auto panel = make_panel({{"ZEBRA", 1000.0}, {"ALPHA", 1000.0}, {"MIKE", 1000.0}}, 5);

    auto ranked = rank_by_liquidity(panel, 60, 10);
    REQUIRE(ranked.has_value());
    REQUIRE(ranked->size() == 3);
    CHECK((*ranked)[0].ticker == "ALPHA");
    CHECK((*ranked)[1].ticker == "MIKE");
    CHECK((*ranked)[2].ticker == "ZEBRA");
}
