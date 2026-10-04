// Tests for the Kaplan-Meier time-to-reversion estimator.
//
// The first is ADR-020 layer 1: a reference derived independently of
// this implementation. The fourth is the bug this whole file exists to
// prevent coming back.

#include <gm-signals/survival.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
#include <vector>

using Catch::Approx;
using gm::signals::Episode;
using gm::signals::kaplan_meier;

TEST_CASE("Kaplan-Meier reproduces the published Freireich 6-MP example",
          "[gm-signals][survival]") {
    // Freireich et al. (1963), the remission-duration data used as the
    // worked Kaplan-Meier example in every survival textbook (e.g.
    // Kleinbaum & Klein, "Survival Analysis: A Self-Learning Text").
    // 21 observations, 9 events, 12 right-censored (the "+" entries):
    //
    //   6, 6, 6, 6+, 7, 9+, 10, 10+, 11+, 13, 16, 17+, 19+, 20+,
    //   22, 23, 25+, 32+, 32+, 34+, 35+
    //
    // The published survival estimates are 0.857, 0.807, 0.753, 0.690,
    // 0.627, 0.538, 0.448 at t = 6, 7, 10, 13, 16, 22, 23. Matching
    // them pins the risk-set bookkeeping - in particular that a
    // censored observation at time t is still at risk for an event at
    // t, which is where a hand-rolled implementation usually goes
    // wrong.
    const std::vector<Episode> data{
        {6, true},   {6, true},   {6, true},   {6, false},  {7, true},   {9, false},  {10, true},
        {10, false}, {11, false}, {13, true},  {16, true},  {17, false}, {19, false}, {20, false},
        {22, true},  {23, true},  {25, false}, {32, false}, {32, false}, {34, false}, {35, false},
    };

    const auto curve = kaplan_meier(data);
    REQUIRE(curve.has_value());
    CHECK(curve->n() == 21);
    CHECK(curve->events() == 9);
    CHECK(curve->censored() == 12);

    REQUIRE(curve->points().size() == 7);
    const double expected[] = {18.0 / 21.0, 0.8067227, 0.7529412, 0.6901961,
                               0.6274510,   0.5378151, 0.4481793};
    const std::int64_t days[] = {6, 7, 10, 13, 16, 22, 23};
    for (std::size_t i = 0; i < 7; ++i) {
        CHECK(curve->points()[i].day == days[i]);
        CHECK(curve->points()[i].survival == Approx(expected[i]).epsilon(1e-6));
    }

    // The published median remission time for this group is 23 weeks -
    // the first time at which survival falls to or below one half.
    REQUIRE(curve->median_days().has_value());
    CHECK(*curve->median_days() == 23);
}

TEST_CASE("without censoring the curve is the plain empirical fraction",
          "[gm-signals][survival]") {
    // The sanity anchor: when nothing is censored, Kaplan-Meier must
    // agree with simply counting. If it does not, the product-limit
    // bookkeeping is wrong and every other number here is decoration.
    const std::vector<Episode> data{{1, true}, {2, true}, {3, true}, {4, true}, {5, true},
                                    {6, true}, {7, true}, {8, true}, {9, true}, {10, true}};
    const auto curve = kaplan_meier(data);
    REQUIRE(curve.has_value());
    for (std::int64_t h = 1; h <= 10; ++h) {
        CHECK(curve->reverted_by(h) == Approx(static_cast<double>(h) / 10.0).epsilon(1e-12));
    }
    CHECK(curve->reverted_by(0) == Approx(0.0));
    CHECK(curve->reverted_by(100) == Approx(1.0));
}

TEST_CASE("Greenwood reduces to the binomial standard error when nothing is censored",
          "[gm-signals][survival]") {
    // An independent check of the variance, not a restatement of it.
    // With no censoring, Greenwood's sum telescopes and the variance of
    // S(t) collapses to S(1-S)/n - the ordinary binomial result, which
    // can be written down without reference to the implementation.
    const std::size_t n = 20;
    std::vector<Episode> data;
    for (std::size_t i = 1; i <= n; ++i) data.push_back({static_cast<std::int64_t>(i), true});

    const auto curve = kaplan_meier(data);
    REQUIRE(curve.has_value());

    for (std::int64_t h = 1; h <= 15; ++h) {
        const auto est = curve->at(h);
        const double s = 1.0 - est.reverted_by;
        const double binomial_se = std::sqrt(s * (1.0 - s) / static_cast<double>(n));
        const double half_width = 1.959963984540054 * binomial_se;
        CHECK(est.ci_low == Approx(std::max(0.0, est.reverted_by - half_width)).epsilon(1e-9));
        CHECK(est.ci_high == Approx(std::min(1.0, est.reverted_by + half_width)).epsilon(1e-9));
    }
}

TEST_CASE("an episode censored before the horizon is not counted as a failure",
          "[gm-signals][survival]") {
    // THE BUG. An episode still outside the band when the data ran out,
    // observed for 2 days, says nothing whatever about day 20. Counting
    // it as "did not revert within 20 days" invents a failure that was
    // never observed and biases the reversion probability DOWN; simply
    // dropping it biases UP, since episodes are censored precisely
    // because they were still dislocated. Kaplan-Meier removes it from
    // the risk set at day 2 and neither counts nor discards it.
    //
    // Nine episodes revert on day 1; one is censored on day 2. If
    // censoring were mishandled the answer at day 20 would be 0.9
    // (counted as a failure). Handled correctly, the one survivor left
    // the risk set with no event recorded, so the estimate is 1.0 - the
    // curve says every episode it could still see had reverted.
    const std::vector<Episode> data{{1, true}, {1, true}, {1, true},  {1, true}, {1, true},
                                    {1, true}, {1, true}, {1, true},  {1, true}, {2, false}};
    const auto curve = kaplan_meier(data);
    REQUIRE(curve.has_value());
    CHECK(curve->events() == 9);
    CHECK(curve->censored() == 1);

    CHECK(curve->reverted_by(1) == Approx(0.9).epsilon(1e-12));
    CHECK(curve->reverted_by(20) == Approx(0.9).epsilon(1e-12));  // NOT 0.9 -> 1.0 by attrition

    // And the risk set is honest about how little is behind the long
    // horizon: nothing is still under observation at day 20.
    CHECK(curve->at(20).at_risk_at_horizon == 0);
    CHECK(curve->at(1).at_risk_at_horizon == 1);  // the censored one, still outside on day 1
}

TEST_CASE("the horizon is what makes the estimate mean anything", "[gm-signals][survival]") {
    // The whole point of the fix. Two populations with IDENTICAL
    // "reverted eventually" rates of 100% - which is what the old study
    // reported for every bucket - but completely different behaviour at
    // any horizon a trader could use.
    std::vector<Episode> fast, slow;
    for (int i = 0; i < 100; ++i) {
        fast.push_back({3, true});
        slow.push_back({90, true});
    }
    const auto fast_curve = kaplan_meier(fast);
    const auto slow_curve = kaplan_meier(slow);
    REQUIRE(fast_curve.has_value());
    REQUIRE(slow_curve.has_value());

    CHECK(fast_curve->reverted_by(1000) == Approx(1.0));
    CHECK(slow_curve->reverted_by(1000) == Approx(1.0));  // indistinguishable, the old measurement

    CHECK(fast_curve->reverted_by(10) == Approx(1.0));
    CHECK(slow_curve->reverted_by(10) == Approx(0.0));  // and entirely distinguishable at a horizon
}

TEST_CASE("a bucket in which nothing reverted reports no reversion and no median",
          "[gm-signals][survival]") {
    const std::vector<Episode> data{{5, false}, {5, false}, {6, false}};
    const auto curve = kaplan_meier(data);
    REQUIRE(curve.has_value());
    CHECK(curve->events() == 0);
    CHECK(curve->points().empty());
    CHECK(curve->reverted_by(100) == Approx(0.0));
    // Not "the largest duration we happened to see" - the curve never
    // reaches one half, and saying so is the honest answer.
    CHECK_FALSE(curve->median_days().has_value());
}

TEST_CASE("an empty bucket is empty, not a reversion rate of zero", "[gm-signals][survival]") {
    const auto curve = kaplan_meier({});
    REQUIRE(curve.has_value());
    CHECK(curve->n() == 0);
    CHECK(curve->at(20).at_risk_at_horizon == 0);
    CHECK(curve->reverted_by(20) == Approx(0.0));
}

TEST_CASE("a negative duration is an error", "[gm-signals][survival]") {
    CHECK_FALSE(kaplan_meier({{5, true}, {-1, true}}).has_value());
}

TEST_CASE("the curve is identical on every run over the same episodes",
          "[gm-signals][survival]") {
    // ADR-003. The episodes arrive in whatever order the parquet row
    // order gives; the curve must not.
    const std::vector<Episode> shuffled{{16, true}, {6, true},  {23, true}, {6, false},
                                        {7, true},  {13, true}, {6, true},  {10, true},
                                        {22, true}, {6, true},  {9, false}};
    std::optional<double> first;
    for (int repeat = 0; repeat < 5; ++repeat) {
        const auto curve = kaplan_meier(shuffled);
        REQUIRE(curve.has_value());
        const double value = curve->reverted_by(16);
        if (!first) {
            first = value;
        } else {
            CHECK(value == Approx(*first).epsilon(0.0));
        }
    }
}
