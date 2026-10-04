// Tests for two-way cluster-robust inference.
//
// The central one is "duplicating an observation inside its own cluster
// buys no evidence": it is the whole reason this file exists, and it
// fails immediately if the clustering is removed.

#include <gm-signals/cluster.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>
#include <vector>

using Catch::Approx;
using gm::signals::ClusterObservation;
using gm::signals::clustered_difference;

namespace {

ClusterObservation obs(double value, bool treated, std::string a, std::string b) {
    ClusterObservation o;
    o.value = value;
    o.treated = treated;
    o.cluster_a = std::move(a);
    o.cluster_b = std::move(b);
    return o;
}

/// A deterministic, reproducible spread of values - no RNG, so the test
/// asserts the same thing on every platform (ADR-003). The sequence is
/// irrational-ish enough to be uncorrelated with the treatment pattern.
double wobble(int i) { return std::sin(static_cast<double>(i) * 1.7) * 0.5; }

}  // namespace

TEST_CASE("the point estimate is exactly the difference in means", "[gm-signals][cluster]") {
    // Writing this as a regression rather than as two sample means is
    // what makes the sandwich available; it must not change the answer.
    const std::vector<ClusterObservation> data{
        obs(1.0, true, "AAPL", "2014-03"), obs(3.0, true, "MSFT", "2014-04"),
        obs(0.0, false, "XOM", "2014-03"), obs(2.0, false, "CVX", "2014-05"),
    };
    const auto est = clustered_difference(data);
    REQUIRE(est.has_value());
    CHECK(est->treated_mean == Approx(2.0));
    CHECK(est->control_mean == Approx(1.0));
    CHECK(est->difference == Approx(1.0));
    CHECK(est->n_treated == 2);
    CHECK(est->n_control == 2);
}

TEST_CASE("duplicating an observation inside its own cluster buys no evidence",
          "[gm-signals][cluster]") {
    // The finding this library exists for, as an experiment.
    //
    // Take a panel of 40 independent units. Now replace each unit with
    // four identical copies of itself, all carrying the SAME ticker and
    // the SAME month. Nothing new has been learned - it is one
    // observation written down four times - but the sample now looks
    // four times bigger.
    //
    // A naive standard error believes it: it falls by roughly sqrt(4).
    // A clustered one does not. The design effect should land near 4
    // and the effective sample size should come back to roughly the 40
    // real observations, not the 160 rows.
    //
    // Delete the clustering and this test fails at once: design_effect
    // collapses to ~1 and effective_n reports 160.
    constexpr int kUnits = 40;
    constexpr int kCopies = 4;

    std::vector<ClusterObservation> singles, duplicated;
    for (int i = 0; i < kUnits; ++i) {
        const bool treated = (i % 2 == 0);
        const double value = (treated ? 1.0 : 0.0) + wobble(i);
        const std::string ticker = "T" + std::to_string(i);
        const std::string month = "M" + std::to_string(i);
        singles.push_back(obs(value, treated, ticker, month));
        for (int c = 0; c < kCopies; ++c) {
            duplicated.push_back(obs(value, treated, ticker, month));
        }
    }

    const auto one = clustered_difference(singles);
    const auto many = clustered_difference(duplicated);
    REQUIRE(one.has_value());
    REQUIRE(many.has_value());

    // The estimate itself is untouched by the duplication.
    CHECK(many->difference == Approx(one->difference));

    // The naive standard error was fooled...
    CHECK(many->se_iid < one->se_iid * 0.6);
    // ...and the clustered one was not.
    CHECK(many->se_clustered > many->se_iid * 1.5);

    CHECK(many->design_effect > 3.0);
    CHECK(many->design_effect < 5.0);
    // 160 rows carrying the information of about 40.
    CHECK(many->effective_n < 60.0);
    CHECK(many->effective_n > 25.0);
    CHECK(many->clusters_a == kUnits);
}

TEST_CASE("independent observations are not penalised", "[gm-signals][cluster]") {
    // The complement of the test above, and just as necessary: an
    // estimator that always inflates the standard error is not robust,
    // it is merely timid. With every observation in its own ticker AND
    // its own month there is no dependence to find, and the design
    // effect should sit near one.
    std::vector<ClusterObservation> data;
    for (int i = 0; i < 60; ++i) {
        const bool treated = (i % 2 == 0);
        data.push_back(obs((treated ? 1.0 : 0.0) + wobble(i), treated, "T" + std::to_string(i),
                            "M" + std::to_string(i)));
    }
    const auto est = clustered_difference(data);
    REQUIRE(est.has_value());
    CHECK(est->design_effect > 0.5);
    CHECK(est->design_effect < 2.0);
    CHECK(est->effective_n > 30.0);
}

TEST_CASE("a market-wide move that hits both arms alike costs no evidence",
          "[gm-signals][cluster]") {
    // Worth pinning because the intuition points the wrong way. Every
    // name in a stressed month moves together, so it is tempting to
    // assume any month effect must inflate the standard error of
    // anything measured on that month.
    //
    // It does not, for a DIFFERENCE. A shock that lands equally on the
    // flagged names and on their controls cancels in the contrast, and
    // the clustered variance correctly reports that nothing was lost.
    // This is also the reason the gate matches on the SAME DAY: it
    // converts market-wide moves into exactly this harmless case.
    std::vector<ClusterObservation> data;
    for (int m = 0; m < 4; ++m) {
        const double month_shock = (m % 2 == 0) ? 1.0 : -1.0;
        for (int i = 0; i < 15; ++i) {
            const bool treated = (i % 2 == 0);
            data.push_back(obs((treated ? 0.2 : 0.0) + month_shock, treated,
                                "T" + std::to_string(m * 100 + i), "M" + std::to_string(m)));
        }
    }
    const auto est = clustered_difference(data);
    REQUIRE(est.has_value());
    CHECK(est->clusters_b == 4);
    CHECK(est->difference == Approx(0.2));
    CHECK(est->design_effect > 0.7);
    CHECK(est->design_effect < 1.4);
}

TEST_CASE("clustering by calendar catches dependence the ticker clustering misses",
          "[gm-signals][cluster]") {
    // The case that does bite, and the realistic one: the treated-minus-
    // control GAP itself varies by month. Flagged names revert hard in
    // some months and not at all in others, so the whole panel really
    // carries about four observations of the effect, not sixty.
    //
    // Every ticker here is distinct, so a one-way clustering on name
    // would find nothing whatsoever - it is the calendar dimension that
    // sees it. Drop the second clustering dimension and the effective
    // sample size jumps back to sixty.
    std::vector<ClusterObservation> data;
    for (int m = 0; m < 4; ++m) {
        const double month_effect = (m < 2) ? 1.0 : -1.0;  // averages to zero
        for (int i = 0; i < 15; ++i) {
            const bool treated = (i % 2 == 0);
            data.push_back(obs(treated ? month_effect : 0.0, treated,
                                "T" + std::to_string(m * 100 + i), "M" + std::to_string(m)));
        }
    }
    const auto est = clustered_difference(data);
    REQUIRE(est.has_value());
    CHECK(est->clusters_a == 60);
    CHECK(est->clusters_b == 4);
    CHECK(est->min_clusters == 4);

    CHECK(est->se_clustered > est->se_iid * 2.0);
    CHECK(est->design_effect > 5.0);
    // Sixty rows worth roughly the four months they came from. Four
    // calendar clusters is also far too few for the normal interval to
    // be trusted, which is exactly why min_clusters sits next to it.
    // See BLOCKED.md entry 10.
    CHECK(est->effective_n < 15.0);
}

TEST_CASE("the interval is centred on the estimate", "[gm-signals][cluster]") {
    std::vector<ClusterObservation> data;
    for (int i = 0; i < 30; ++i) {
        const bool treated = (i % 2 == 0);
        data.push_back(obs((treated ? 1.0 : 0.0) + wobble(i), treated, "T" + std::to_string(i % 6),
                            "M" + std::to_string(i % 5)));
    }
    const auto est = clustered_difference(data);
    REQUIRE(est.has_value());
    CHECK((est->ci_low + est->ci_high) / 2.0 == Approx(est->difference));
    CHECK(est->ci_high > est->ci_low);
    CHECK(est->t_statistic == Approx(est->difference / est->se_clustered));
}

TEST_CASE("a missing arm is an error, not a difference", "[gm-signals][cluster]") {
    const std::vector<ClusterObservation> all_treated{
        obs(1.0, true, "A", "M"), obs(2.0, true, "B", "M"), obs(3.0, true, "C", "M")};
    const auto est = clustered_difference(all_treated);
    REQUIRE_FALSE(est.has_value());
    CHECK(est.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("too few observations is an error", "[gm-signals][cluster]") {
    const std::vector<ClusterObservation> two{obs(1.0, true, "A", "M"), obs(0.0, false, "B", "M")};
    const auto est = clustered_difference(two);
    REQUIRE_FALSE(est.has_value());
    CHECK(est.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("the estimate does not depend on observation order", "[gm-signals][cluster]") {
    std::vector<ClusterObservation> data;
    for (int i = 0; i < 24; ++i) {
        const bool treated = (i % 3 == 0);
        data.push_back(obs((treated ? 0.7 : 0.1) + wobble(i), treated, "T" + std::to_string(i % 5),
                            "M" + std::to_string(i % 4)));
    }
    const auto forward = clustered_difference(data);
    std::vector<ClusterObservation> backward(data.rbegin(), data.rend());
    const auto reversed = clustered_difference(backward);

    REQUIRE(forward.has_value());
    REQUIRE(reversed.has_value());
    CHECK(forward->difference == Approx(reversed->difference));
    CHECK(forward->se_clustered == Approx(reversed->se_clustered));
    CHECK(forward->effective_n == Approx(reversed->effective_n));
}
