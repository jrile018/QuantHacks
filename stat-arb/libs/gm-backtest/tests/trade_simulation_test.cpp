#include <gm-backtest/trade_simulation.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

using gm::backtest::simulate_portfolio;
using gm::backtest::TradeCandidate;

namespace {
std::map<std::string, double> series(const std::vector<std::pair<std::string, double>>& points) {
    std::map<std::string, double> result;
    for (const auto& [date, spread] : points) result[date] = spread;
    return result;
}
} // namespace

TEST_CASE("a long position's daily returns are the spread's day-over-day change", "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-01", "2024-01-03", /*long_the_spread=*/true, /*num_legs=*/2,
                      series({{"2024-01-01", 1.0}, {"2024-01-02", 1.2}, {"2024-01-03", 1.5}})};

    auto result = simulate_portfolio({c}, /*cost_bps_per_leg=*/0.0);
    REQUIRE(result.has_value());
    REQUIRE(result->dates.size() == 2);
    CHECK(result->dates[0] == "2024-01-02");
    CHECK(result->daily_returns[0] == Catch::Approx(0.2));
    CHECK(result->dates[1] == "2024-01-03");
    CHECK(result->daily_returns[1] == Catch::Approx(0.3));
    CHECK(result->num_open_positions[0] == 1);
}

TEST_CASE("a short position's daily returns are the negated spread change", "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-01", "2024-01-03", /*long_the_spread=*/false, /*num_legs=*/2,
                      series({{"2024-01-01", 1.0}, {"2024-01-02", 1.2}, {"2024-01-03", 1.5}})};

    auto result = simulate_portfolio({c}, 0.0);
    REQUIRE(result.has_value());
    REQUIRE(result->dates.size() == 2);
    CHECK(result->daily_returns[0] == Catch::Approx(-0.2));
    CHECK(result->daily_returns[1] == Catch::Approx(-0.3));
}

TEST_CASE("a single-return-day trade is charged the full round-trip cost on that one day",
          "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-01", "2024-01-02", true, /*num_legs=*/2,
                      series({{"2024-01-01", 1.0}, {"2024-01-02", 1.2}})};

    // total_cost = (10/10000) * 2 legs * 2 (entry+exit) = 0.004
    auto result = simulate_portfolio({c}, /*cost_bps_per_leg=*/10.0);
    REQUIRE(result.has_value());
    REQUIRE(result->dates.size() == 1);
    CHECK(result->daily_returns[0] == Catch::Approx(0.2 - 0.004));
}

TEST_CASE("a multi-day trade splits round-trip cost across the first and last day only",
          "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-01", "2024-01-04", true, /*num_legs=*/1,
                      series({{"2024-01-01", 1.0}, {"2024-01-02", 1.1}, {"2024-01-03", 1.3}, {"2024-01-04", 1.6}})};

    // total_cost = (10/10000) * 1 leg * 2 = 0.002, split 0.001 entry / 0.001 exit
    auto result = simulate_portfolio({c}, /*cost_bps_per_leg=*/10.0);
    REQUIRE(result.has_value());
    REQUIRE(result->dates.size() == 3);
    CHECK(result->daily_returns[0] == Catch::Approx(0.1 - 0.001));  // entry day: charged
    CHECK(result->daily_returns[1] == Catch::Approx(0.2));          // middle day: no cost
    CHECK(result->daily_returns[2] == Catch::Approx(0.3 - 0.001));  // exit day: charged
}

TEST_CASE("two candidates on different tickers on overlapping dates are equal-weight averaged",
          "[trade_simulation]") {
    TradeCandidate aapl{"AAPL", "2024-01-01", "2024-01-02", true, 1,
                         series({{"2024-01-01", 1.0}, {"2024-01-02", 1.4}})}; // +0.4
    TradeCandidate msft{"MSFT", "2024-01-01", "2024-01-02", true, 1,
                         series({{"2024-01-01", 2.0}, {"2024-01-02", 1.8}})}; // -0.2

    auto result = simulate_portfolio({aapl, msft}, 0.0);
    REQUIRE(result.has_value());
    REQUIRE(result->dates.size() == 1);
    CHECK(result->daily_returns[0] == Catch::Approx((0.4 + (-0.2)) / 2.0));
    CHECK(result->num_open_positions[0] == 2);
}

TEST_CASE("the same ticker can have two candidates with different (e.g. differently-based) spread series "
          "without interference",
          "[trade_simulation]") {
    // Directly exercises the reason each candidate carries its own
    // spread_series instead of a shared per-ticker lookup: two AAPL
    // trades, entered at different times against different (here,
    // deliberately very different) baskets, must not clobber each
    // other or get merged.
    TradeCandidate first{"AAPL", "2024-01-01", "2024-01-02", true, 1,
                         series({{"2024-01-01", 1.0}, {"2024-01-02", 1.5}})}; // +0.5
    TradeCandidate second{"AAPL", "2024-06-01", "2024-06-02", true, 1,
                          series({{"2024-06-01", 10.0}, {"2024-06-02", 10.3}})}; // +0.3

    auto result = simulate_portfolio({first, second}, 0.0);
    REQUIRE(result.has_value());
    REQUIRE(result->dates.size() == 2);
    CHECK(result->dates[0] == "2024-01-02");
    CHECK(result->daily_returns[0] == Catch::Approx(0.5));
    CHECK(result->dates[1] == "2024-06-02");
    CHECK(result->daily_returns[1] == Catch::Approx(0.3));
}

TEST_CASE("a candidate with an empty spread_series is silently skipped, not an error", "[trade_simulation]") {
    TradeCandidate c{"NOTREAL", "2024-01-01", "2024-01-02", true, 1, {}};
    auto result = simulate_portfolio({c}, 0.0);
    REQUIRE(result.has_value());
    CHECK(result->dates.empty());
}

TEST_CASE("a candidate with only one spread observation in range contributes nothing", "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-01", "2024-01-01", true, 1,
                      series({{"2024-01-01", 1.0}, {"2024-06-01", 5.0}})};
    auto result = simulate_portfolio({c}, 0.0);
    REQUIRE(result.has_value());
    CHECK(result->dates.empty());
}

TEST_CASE("exit_date before entry_date is rejected", "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-05", "2024-01-01", true, 1, series({{"2024-01-01", 1.0}})};
    auto result = simulate_portfolio({c}, 0.0);
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("num_legs < 1 is rejected", "[trade_simulation]") {
    TradeCandidate c{"AAPL", "2024-01-01", "2024-01-02", true, 0, series({{"2024-01-01", 1.0}})};
    auto result = simulate_portfolio({c}, 0.0);
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("negative cost_bps_per_leg is rejected", "[trade_simulation]") {
    auto result = simulate_portfolio({}, -1.0);
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("an empty candidate list produces an empty result, not an error", "[trade_simulation]") {
    auto result = simulate_portfolio({}, 5.0);
    REQUIRE(result.has_value());
    CHECK(result->dates.empty());
}
