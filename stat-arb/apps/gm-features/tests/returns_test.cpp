#include "returns.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cmath>

namespace {
constexpr double kTol = 1e-9;
}

TEST_CASE("compute_trailing_returns: insufficient history has no entry", "[gm-features][returns]") {
    // 3 bars for AAA - not enough for a 5-day lookback.
    std::vector<std::string> tickers = {"AAA", "AAA", "AAA"};
    std::vector<std::string> dates = {"2020-01-01", "2020-01-02", "2020-01-03"};
    std::vector<double> adjclose = {100.0, 101.0, 102.0};

    auto returns = gm::features::compute_trailing_returns(tickers, dates, adjclose, 5);
    REQUIRE(returns.count("AAA") == 1);
    CHECK(returns.at("AAA").empty());  // no row has 5 prior bars
}

TEST_CASE("compute_trailing_returns: computes real trailing return once enough history exists",
          "[gm-features][returns]") {
    std::vector<std::string> tickers;
    std::vector<std::string> dates;
    std::vector<double> adjclose;
    // 7 daily bars, price doubling day over day starting at 100.
    double price = 100.0;
    for (int day = 1; day <= 7; ++day) {
        tickers.push_back("AAA");
        char buf[16];
        std::snprintf(buf, sizeof(buf), "2020-01-%02d", day);
        dates.emplace_back(buf);
        adjclose.push_back(price);
        price *= 1.01;  // +1% per day
    }

    auto returns = gm::features::compute_trailing_returns(tickers, dates, adjclose, 5);
    const auto& aaa = returns.at("AAA");

    // Days 1-5 (indices 0-4) have fewer than 5 PRIOR bars, so no entry.
    CHECK(aaa.count("2020-01-01") == 0);
    CHECK(aaa.count("2020-01-05") == 0);
    // Day 6 (index 5) has exactly 5 prior bars (index 0): valid.
    REQUIRE(aaa.count("2020-01-06") == 1);
    double expected_day6 = std::pow(1.01, 5) - 1.0;  // 5 daily +1% compounding steps
    CHECK(std::abs(aaa.at("2020-01-06") - expected_day6) < kTol);
    // Day 7 (index 6) vs day 2 (index 1): also 5 bars back.
    REQUIRE(aaa.count("2020-01-07") == 1);
    CHECK(std::abs(aaa.at("2020-01-07") - expected_day6) < kTol);
}

TEST_CASE("compute_trailing_returns: tickers are independent", "[gm-features][returns]") {
    // AAA and BBB interleaved in input order - series_by_ticker grouping
    // must not mix them, and per-ticker sort must not depend on input order.
    std::vector<std::string> tickers = {"BBB", "AAA", "BBB", "AAA", "BBB", "AAA"};
    std::vector<std::string> dates = {"2020-01-02", "2020-01-01", "2020-01-01", "2020-01-02",
                                       "2020-01-03", "2020-01-03"};
    std::vector<double> adjclose = {110.0, 100.0, 100.0, 105.0, 121.0, 102.0};

    auto returns = gm::features::compute_trailing_returns(tickers, dates, adjclose, 2);
    REQUIRE(returns.at("AAA").count("2020-01-03") == 1);
    // AAA: day1=100, day2=105, day3=102 -> 2-day return = 102/100 - 1 = 0.02
    CHECK(std::abs(returns.at("AAA").at("2020-01-03") - 0.02) < kTol);
    REQUIRE(returns.at("BBB").count("2020-01-03") == 1);
    // BBB: day1=100, day2=110, day3=121 -> 2-day return = 121/100 - 1 = 0.21
    CHECK(std::abs(returns.at("BBB").at("2020-01-03") - 0.21) < kTol);
}
