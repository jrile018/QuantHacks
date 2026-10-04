#include <gm-backtest/deflated_sharpe.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>

using gm::backtest::deflated_sharpe_ratio;
using gm::backtest::expected_max_sharpe;

// The paper's own worked numerical example (Bailey & Lopez de Prado
// 2014, "A NUMERICAL EXAMPLE" section, p.9-10): a strategist backtests
// many treasury-auction-seasonality configurations, finds one with an
// annualized SR of 2.5 over T=1250 daily observations (5 years x 250
// obs/year), discloses N=100 independent trials with
// V[{SR_n}]=1/2 (annualized), skewness=-3, kurtosis=10. The paper
// states the resulting SR_0 ~= 0.1132 and DSR ~= 0.9004 < 0.95 - NOT
// significant at the conventional 95% level, which is the whole point
// of the example (an investor correctly declines funding a strategy
// that looks great unconditionally but isn't once multiple testing and
// non-Normality are accounted for).
//
// Independently re-derived by hand during design (not just copied from
// the paper) before writing this test: SR_0 = sqrt((1/2)/250) *
// [(1-gamma)*Phi^-1(0.99) + gamma*Phi^-1(1-1/(100e))] ~= 0.0447 * 2.533
// ~= 0.1132, and DSR = Phi[(0.15811-0.1132)*sqrt(1249) /
// sqrt(1+3*0.15811+2.25*0.15811^2)] ~= Phi[1.283] ~= 0.9004 - matching
// the paper's own stated figures to the precision it reports them at.
TEST_CASE("matches the paper's own worked numerical example", "[deflated_sharpe]") {
    const int n_trials = 100;
    const double periods_per_year = 250.0;
    const double annualized_variance = 0.5;
    const double per_period_variance = annualized_variance / periods_per_year;
    const int t_observations = 1250;
    const double skewness = -3.0;
    const double kurtosis = 10.0;
    const double annualized_sr = 2.5;
    const double per_period_sr = annualized_sr / std::sqrt(periods_per_year);

    auto sr0 = expected_max_sharpe(per_period_variance, n_trials);
    REQUIRE(sr0.has_value());
    CHECK(*sr0 == Catch::Approx(0.1132).margin(0.0005));

    auto dsr = deflated_sharpe_ratio(per_period_sr, *sr0, t_observations, skewness, kurtosis);
    REQUIRE(dsr.has_value());
    CHECK(*dsr == Catch::Approx(0.9004).margin(0.0005));
    CHECK(*dsr < 0.95); // the paper's own conclusion: not significant at 95%
}

TEST_CASE("the paper's own Normal-returns counterfactual: DSR=0.9505 at N=88", "[deflated_sharpe]") {
    // The paper states: "If the strategy had exhibited Normal returns
    // (skew=0, kurtosis=3), DSR=0.9505 after N=88 independent trials."
    // Same T and annualized SR/variance as the main example.
    const double periods_per_year = 250.0;
    const double per_period_variance = 0.5 / periods_per_year;
    const int t_observations = 1250;
    const double per_period_sr = 2.5 / std::sqrt(periods_per_year);

    auto sr0 = expected_max_sharpe(per_period_variance, 88);
    REQUIRE(sr0.has_value());

    auto dsr = deflated_sharpe_ratio(per_period_sr, *sr0, t_observations, /*skewness=*/0.0, /*kurtosis=*/3.0);
    REQUIRE(dsr.has_value());
    CHECK(*dsr == Catch::Approx(0.9505).margin(0.001));
}

TEST_CASE("n_trials=1 returns SR_0=0 exactly (the paper's stated special case)", "[deflated_sharpe]") {
    auto sr0 = expected_max_sharpe(/*trial_sharpe_variance=*/2.0, /*n_trials=*/1);
    REQUIRE(sr0.has_value());
    CHECK(*sr0 == Catch::Approx(0.0).margin(1e-12));
}

TEST_CASE("expected_max_sharpe increases with n_trials", "[deflated_sharpe]") {
    // Directly demonstrates the paper's own headline point (Eq. 1's
    // discussion): more trials -> a higher bar of "looks good by luck
    // alone," monotonically.
    auto sr0_10 = expected_max_sharpe(1.0, 10);
    auto sr0_100 = expected_max_sharpe(1.0, 100);
    auto sr0_1000 = expected_max_sharpe(1.0, 1000);
    REQUIRE(sr0_10.has_value());
    REQUIRE(sr0_100.has_value());
    REQUIRE(sr0_1000.has_value());
    CHECK(*sr0_10 < *sr0_100);
    CHECK(*sr0_100 < *sr0_1000);
}

TEST_CASE("expected_max_sharpe with V=1 at N=1000 matches the paper's own headline figure (~3.26)",
          "[deflated_sharpe]") {
    // From the search summary used during design: "Assuming E[SR]=0
    // and V[SR]=1, after only 1,000 independent backtests the expected
    // maximum Sharpe Ratio is 3.26, even if the true SR of the strategy
    // is zero."
    auto sr0 = expected_max_sharpe(1.0, 1000);
    REQUIRE(sr0.has_value());
    CHECK(*sr0 == Catch::Approx(3.26).margin(0.02));
}

TEST_CASE("negative trial_sharpe_variance is rejected", "[deflated_sharpe]") {
    auto sr0 = expected_max_sharpe(-1.0, 100);
    REQUIRE_FALSE(sr0.has_value());
}

TEST_CASE("n_trials < 1 is rejected", "[deflated_sharpe]") {
    auto sr0 = expected_max_sharpe(1.0, 0);
    REQUIRE_FALSE(sr0.has_value());
}

TEST_CASE("a Sharpe ratio well above SR_0 with Normal returns gives a high DSR", "[deflated_sharpe]") {
    auto dsr = deflated_sharpe_ratio(/*observed_sharpe=*/0.5, /*sr0=*/0.05, /*t_observations=*/1000,
                                      /*skewness=*/0.0, /*kurtosis=*/3.0);
    REQUIRE(dsr.has_value());
    CHECK(*dsr > 0.99);
}

TEST_CASE("a Sharpe ratio at SR_0 gives DSR=0.5 exactly", "[deflated_sharpe]") {
    // (sr - sr0) = 0 -> Z[0] = 0.5, regardless of skew/kurtosis/T (as
    // long as the denominator stays positive and finite).
    auto dsr = deflated_sharpe_ratio(/*observed_sharpe=*/0.2, /*sr0=*/0.2, /*t_observations=*/500,
                                      /*skewness=*/-1.0, /*kurtosis=*/6.0);
    REQUIRE(dsr.has_value());
    CHECK(*dsr == Catch::Approx(0.5).margin(1e-9));
}

TEST_CASE("t_observations < 2 is rejected", "[deflated_sharpe]") {
    auto dsr = deflated_sharpe_ratio(0.5, 0.1, 1, 0.0, 3.0);
    REQUIRE_FALSE(dsr.has_value());
}
