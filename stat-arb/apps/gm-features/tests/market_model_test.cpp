// Tests for the market-model regression.
//
// The reference answers here are constructed, not recorded: a series built
// as exactly 1.5x the index plus a known residual pattern HAS a beta of
// 1.5 and a computable residual standard deviation, whatever this code
// does. That is what makes them a check on the implementation rather than
// a photograph of it.

#include "../market_model.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>
#include <vector>

using gm::features::compute_daily_returns;
using gm::features::compute_market_model;
using gm::features::equal_weighted_index;

namespace {

constexpr double kTol = 1e-9;

std::string day(int i) {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "2020-%02d-%02d", 1 + (i / 28) % 12, 1 + i % 28);
    return buf;
}

} // namespace

TEST_CASE("daily returns are per ticker, from that ticker's own previous bar",
          "[gm-features][market_model]") {
    // Interleaved rows, deliberately: if the implementation differenced
    // against the previous ROW rather than the previous bar OF THAT
    // TICKER, it would compute AAA's return against BBB's price and the
    // numbers would be nonsense that still looked like returns.
    const std::vector<std::string> tickers{"AAA", "BBB", "AAA", "BBB", "AAA", "BBB"};
    const std::vector<std::string> dates{"2024-01-02", "2024-01-02", "2024-01-03",
                                         "2024-01-03", "2024-01-04", "2024-01-04"};
    const std::vector<double> close{100.0, 50.0, 110.0, 45.0, 99.0, 90.0};

    const auto returns = compute_daily_returns(tickers, dates, close);

    REQUIRE(returns.count("AAA") == 1);
    REQUIRE(returns.count("BBB") == 1);
    // The first bar of each ticker has no predecessor, so no return.
    CHECK(returns.at("AAA").count("2024-01-02") == 0);
    CHECK(std::abs(returns.at("AAA").at("2024-01-03") - 0.10) < kTol);
    CHECK(std::abs(returns.at("AAA").at("2024-01-04") - (99.0 / 110.0 - 1.0)) < kTol);
    CHECK(std::abs(returns.at("BBB").at("2024-01-03") - (45.0 / 50.0 - 1.0)) < kTol);
    CHECK(std::abs(returns.at("BBB").at("2024-01-04") - 1.0) < kTol);
}

TEST_CASE("the equal-weighted index is the mean of the day's returns",
          "[gm-features][market_model]") {
    std::map<std::string, std::map<std::string, double>> returns;
    returns["A"]["2024-01-03"] = 0.02;
    returns["B"]["2024-01-03"] = -0.01;
    returns["C"]["2024-01-03"] = 0.05;
    returns["D"]["2024-01-03"] = 0.00;
    returns["E"]["2024-01-03"] = 0.04;
    // A second date with too few names to be an index.
    returns["A"]["2024-01-04"] = 0.01;
    returns["B"]["2024-01-04"] = 0.03;

    const auto index = equal_weighted_index(returns, /*min_names=*/5);
    REQUIRE(index.count("2024-01-03") == 1);
    CHECK(std::abs(index.at("2024-01-03") - (0.02 - 0.01 + 0.05 + 0.00 + 0.04) / 5.0) < kTol);
    // Two names is not an index, and a beta against one would describe
    // those two names rather than the market.
    CHECK(index.count("2024-01-04") == 0);
}

TEST_CASE("beta recovers a known slope exactly", "[gm-features][market_model]") {
    // Constructed so the answer is known independently: every stock return
    // is exactly 1.5x the index return, so beta is 1.5 and the residuals
    // are identically zero, whatever the code does.
    std::map<std::string, std::map<std::string, double>> returns;
    std::map<std::string, double> index;
    for (int i = 0; i < 60; ++i) {
        const double m = 0.01 * std::sin(0.7 * i);
        index[day(i)] = m;
        returns["LEV"][day(i)] = 1.5 * m;
    }

    const auto model = compute_market_model(returns, index, /*window=*/40);
    REQUIRE(model.count("LEV") == 1);
    const auto& series = model.at("LEV");
    REQUIRE(series.count(day(59)) == 1);

    const auto& m = series.at(day(59));
    CHECK(std::abs(m.beta - 1.5) < 1e-9);
    // An exact linear relationship leaves nothing unexplained.
    CHECK(m.idiosyncratic_volatility < 1e-9);
    CHECK(m.observations == 40);
}

TEST_CASE("idiosyncratic volatility measures what the market does not explain",
          "[gm-features][market_model]") {
    // Constructed so BOTH answers are exact, which takes a little care.
    //
    // The obvious construction - a sinusoidal index plus an alternating
    // (+e, -e) residual - does not give an exact answer, because that
    // residual is not orthogonal to that index: least squares absorbs part
    // of it into the slope, and beta comes out 1.0116 rather than 1. The
    // first version of this test made exactly that mistake and its
    // "expected" values were approximations dressed as exact ones.
    //
    // A LINEAR index with a period-4 residual pattern (+e, -e, -e, +e)
    // fixes it. Over every block of four,
    //
    //     sum(r) = 0        so the residual is orthogonal to the intercept
    //     sum(j * r) = 0    so it is orthogonal to the slope
    //
    // Nothing is absorbed. Beta is exactly 1, the residuals are exactly
    // +/-e, and both expectations hold to machine precision - so these
    // assertions test the implementation rather than the tolerance.
    //
    // Window and evaluation point are block-aligned (60 is a multiple of
    // 4, and the window ending at index 79 spans [20, 79], both multiples
    // of 4), because a window cutting a block in half would break the
    // orthogonality the construction depends on.
    constexpr double kResidual = 0.004;
    constexpr int kWindow = 60;
    std::map<std::string, std::map<std::string, double>> returns;
    std::map<std::string, double> index;
    const double pattern[4] = {kResidual, -kResidual, -kResidual, kResidual};
    for (int i = 0; i < 80; ++i) {
        const double m = 0.0001 * i;  // linear, so the fit has one slope to find
        index[day(i)] = m;
        returns["NOISY"][day(i)] = m + pattern[i % 4];
    }

    const auto model = compute_market_model(returns, index, kWindow);
    REQUIRE(model.at("NOISY").count(day(79)) == 1);
    const auto& m = model.at("NOISY").at(day(79));

    CHECK(std::abs(m.beta - 1.0) < 1e-12);
    // n/(n-2) on the variance: a two-parameter fit.
    const double expected =
        kResidual * std::sqrt(static_cast<double>(kWindow) / (kWindow - 2.0)) * std::sqrt(252.0);
    CHECK(std::abs(m.idiosyncratic_volatility - expected) < 1e-12);
    CHECK(m.observations == kWindow);
}

TEST_CASE("a window with no index movement produces no beta at all",
          "[gm-features][market_model]") {
    // Beta would be a division by zero. ADR-019's rule is that an
    // unavailable value is ABSENT, never invented - a fabricated slope
    // through a degenerate regression is exactly the plausible-looking
    // wrong number this project refuses to ship.
    std::map<std::string, std::map<std::string, double>> returns;
    std::map<std::string, double> index;
    for (int i = 0; i < 40; ++i) {
        index[day(i)] = 0.0;  // the index never moves
        returns["X"][day(i)] = 0.001 * (i % 3);
    }

    const auto model = compute_market_model(returns, index, /*window=*/20);
    CHECK(model.count("X") == 0);
}

TEST_CASE("insufficient history has no entry rather than a placeholder",
          "[gm-features][market_model]") {
    // The same convention compute_trailing_returns uses: a genuinely
    // missing value the caller represents as NaN, not a stand-in for
    // something unimplemented.
    std::map<std::string, std::map<std::string, double>> returns;
    std::map<std::string, double> index;
    for (int i = 0; i < 10; ++i) {
        index[day(i)] = 0.01 * std::sin(0.7 * i);
        returns["SHORT"][day(i)] = 1.2 * index[day(i)];
    }

    const auto model = compute_market_model(returns, index, /*window=*/40);
    // window/2 = 20 observations required; only 10 exist.
    CHECK(model.count("SHORT") == 0);
}

TEST_CASE("the regression window uses no return after the date it describes",
          "[gm-features][market_model]") {
    // Causality, checked the same way View B's is: computing over a
    // truncated series must give the identical answer for every date the
    // truncation kept.
    std::map<std::string, std::map<std::string, double>> full_returns, short_returns;
    std::map<std::string, double> full_index, short_index;
    for (int i = 0; i < 120; ++i) {
        const double m = 0.01 * std::sin(0.31 * i) + 0.003 * std::cos(1.7 * i);
        const double r = 0.9 * m + 0.002 * std::sin(2.3 * i);
        full_index[day(i)] = m;
        full_returns["T"][day(i)] = r;
        if (i < 70) {
            short_index[day(i)] = m;
            short_returns["T"][day(i)] = r;
        }
    }

    const auto full = compute_market_model(full_returns, full_index, /*window=*/40);
    const auto truncated = compute_market_model(short_returns, short_index, /*window=*/40);

    REQUIRE(truncated.count("T") == 1);
    std::size_t compared = 0;
    for (const auto& [date, m] : truncated.at("T")) {
        REQUIRE(full.at("T").count(date) == 1);
        const auto& f = full.at("T").at(date);
        INFO("date = " << date);
        // Exactly equal: both fits see the same window of the same numbers.
        CHECK(f.beta == m.beta);
        CHECK(f.idiosyncratic_volatility == m.idiosyncratic_volatility);
        CHECK(f.observations == m.observations);
        ++compared;
    }
    CHECK(compared > 20);
}
