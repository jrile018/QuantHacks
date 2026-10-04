// Tests for matched-control construction.
//
// The load-bearing ones are "a control outside the caliper is refused"
// and "every treated unit is accounted for": between them they are what
// stops a matched study quietly degrading into an unmatched one that
// still reports a matched-looking number.

#include <gm-signals/matching.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cmath>
#include <vector>

using Catch::Approx;
using gm::signals::match_on_covariates;
using gm::signals::MatchOptions;
using gm::signals::MatchUnit;

namespace {

MatchUnit unit(std::size_t id, std::string stratum, bool treated, std::vector<double> cov) {
    MatchUnit u;
    u.id = id;
    u.stratum = std::move(stratum);
    u.treated = treated;
    u.covariates = std::move(cov);
    return u;
}

}  // namespace

TEST_CASE("a treated unit is never matched across its exact stratum", "[gm-signals][matching]") {
    // The only control that resembles the treated unit numerically sits
    // in a different stratum. Exact matching must refuse it even though
    // the alternative in-stratum control is far away, because the
    // stratum is the part of the design that is not negotiable: a
    // same-day, same-sector comparison is the whole reason a market-wide
    // move cannot masquerade as an effect.
    const std::vector<MatchUnit> units{
        unit(0, "2014-03-05|Energy", true, {0.0, 0.0}),
        unit(1, "2014-03-05|Financials", false, {0.0, 0.0}),  // perfect twin, wrong stratum
        unit(2, "2014-03-05|Energy", false, {5.0, 5.0}),      // right stratum, miles away
    };

    MatchOptions opt;
    opt.caliper = 100.0;  // deliberately huge: only the stratum can refuse
    const auto report = match_on_covariates(units, opt);
    REQUIRE(report.has_value());
    REQUIRE(report->pairs.size() == 1);
    CHECK(report->pairs[0].treated_id == 0);
    CHECK(report->pairs[0].control_id == 2);
}

TEST_CASE("the nearest control wins and ties go to the lower id", "[gm-signals][matching]") {
    const std::vector<MatchUnit> units{
        unit(0, "s", true, {0.0}),
        unit(1, "s", false, {3.0}),
        unit(2, "s", false, {1.0}),  // nearest
        unit(3, "s", false, {9.0}),
    };
    MatchOptions opt;
    opt.caliper = 100.0;
    auto report = match_on_covariates(units, opt);
    REQUIRE(report.has_value());
    REQUIRE(report->pairs.size() == 1);
    CHECK(report->pairs[0].control_id == 2);

    // Two controls exactly equidistant: the pairing must not depend on
    // iteration luck, or two runs of the same study disagree (ADR-003).
    const std::vector<MatchUnit> tied{
        unit(0, "s", true, {0.0}),
        unit(1, "s", false, {2.0}),
        unit(2, "s", false, {-2.0}),
    };
    auto tie_report = match_on_covariates(tied, opt);
    REQUIRE(tie_report.has_value());
    REQUIRE(tie_report->pairs.size() == 1);
    CHECK(tie_report->pairs[0].control_id == 1);
}

TEST_CASE("a control serves one treated unit and only one", "[gm-signals][matching]") {
    // Two treated units, one control. Matching with replacement would
    // hand the same control to both and report a sample of two where
    // there is really one - the second "pair" carries no independent
    // information at all.
    const std::vector<MatchUnit> units{
        unit(0, "s", true, {0.0}),
        unit(1, "s", true, {0.1}),
        unit(2, "s", false, {0.05}),
    };
    MatchOptions opt;
    opt.caliper = 100.0;
    const auto report = match_on_covariates(units, opt);
    REQUIRE(report.has_value());
    CHECK(report->pairs.size() == 1);
    CHECK(report->treated_matched == 1);
    CHECK(report->treated_unmatched_exhausted == 1);
}

TEST_CASE("a control outside the caliper is refused, not stretched to", "[gm-signals][matching]") {
    // THE test. Dropping the caliper check turns every treated unit into
    // a matched one paired with whatever was nearest, however unlike it,
    // and the study still reports a match rate of 100% and a balance
    // table nobody reads. The refusal has to be visible.
    //
    // Covariate values are {0, 10} so the pooled SD is 5 and the single
    // available control sits 2.0 SDs away - comfortably outside any
    // sane caliper.
    const std::vector<MatchUnit> units{
        unit(0, "s", true, {0.0}),
        unit(1, "s", false, {10.0}),
    };

    MatchOptions tight;
    tight.caliper = 0.25;
    const auto refused = match_on_covariates(units, tight);
    REQUIRE(refused.has_value());
    CHECK(refused->pairs.empty());
    CHECK(refused->treated_unmatched_caliper == 1);
    CHECK(refused->match_rate() == Approx(0.0));

    // The same pool with a caliper wide enough to admit it does match,
    // which shows the refusal above was the caliper doing its job and
    // not some unrelated failure.
    MatchOptions loose;
    loose.caliper = 2.5;
    const auto admitted = match_on_covariates(units, loose);
    REQUIRE(admitted.has_value());
    CHECK(admitted->pairs.size() == 1);
    CHECK(admitted->pairs[0].distance == Approx(2.0));
}

TEST_CASE("every treated unit is accounted for exactly once", "[gm-signals][matching]") {
    // An arithmetic invariant rather than a scenario: matched plus the
    // three refusal reasons must equal the treated total. If a unit can
    // vanish between the two, the match rate is a fiction.
    const std::vector<MatchUnit> units{
        unit(0, "a", true, {0.0}),   unit(1, "a", false, {0.1}),  // matches
        unit(2, "a", true, {0.2}),                                 // controls exhausted
        unit(3, "b", true, {0.0}),                                 // stratum has no controls
        unit(4, "c", true, {0.0}),   unit(5, "c", false, {50.0}),  // outside caliper
    };
    MatchOptions opt;
    opt.caliper = 0.25;
    const auto report = match_on_covariates(units, opt);
    REQUIRE(report.has_value());

    CHECK(report->treated_total == 4);
    CHECK(report->treated_matched + report->treated_unmatched_no_controls +
              report->treated_unmatched_exhausted + report->treated_unmatched_caliper ==
          report->treated_total);
    CHECK(report->treated_unmatched_no_controls == 1);
    CHECK(report->treated_unmatched_exhausted == 1);
    CHECK(report->treated_unmatched_caliper == 1);
    CHECK(report->controls_available == 2);
}

TEST_CASE("matching improves covariate balance", "[gm-signals][matching]") {
    // The point of the exercise, stated as a measurement. The treated
    // arm is drawn around 1.0 and the control pool spans 0.0 to 3.0, so
    // the raw arms differ; after matching, each treated unit is paired
    // with a control near 1.0 and the standardized difference collapses.
    //
    // A balance table that does NOT improve is the signal that the
    // matching failed - which is why the report carries both numbers
    // rather than only the flattering one.
    std::vector<MatchUnit> units;
    std::size_t id = 0;
    for (int i = 0; i < 8; ++i) {
        units.push_back(unit(id++, "s", true, {1.0 + 0.01 * i}));  // 1.00 .. 1.07
    }
    // A dense band of plausible twins, plus a broad pool that drags the
    // unmatched control mean away from the treated arm. Both are needed:
    // without the band nothing matches, and without the broad pool the
    // "before" difference is already small and the test proves nothing.
    for (int i = 0; i < 20; ++i) {
        units.push_back(unit(id++, "s", false, {0.95 + 0.015 * i}));  // 0.950 .. 1.235
    }
    for (int i = 0; i < 30; ++i) {
        units.push_back(unit(id++, "s", false, {0.0 + 0.1 * i}));  // 0.0 .. 2.9
    }

    MatchOptions opt;
    opt.caliper = 0.25;
    const auto report = match_on_covariates(units, opt);
    REQUIRE(report.has_value());
    REQUIRE(report->treated_matched == 8);

    const double before = std::abs(report->standardized_diff_before[0]);
    const double after = report->worst_balance_after();
    CHECK(before > 0.3);
    CHECK(after < 0.1);
    CHECK(after < before);
}

TEST_CASE("a covariate with no variance is excluded rather than trusted", "[gm-signals][matching]") {
    // A constant covariate contributes nothing but would drag the
    // root-mean-square distance towards zero if it were counted,
    // silently loosening the caliper by a factor that depends on how
    // many dead covariates were supplied.
    const std::vector<MatchUnit> units{
        unit(0, "s", true, {0.0, 7.0}),
        unit(1, "s", false, {10.0, 7.0}),
    };
    MatchOptions opt;
    opt.caliper = 100.0;
    const auto report = match_on_covariates(units, opt);
    REQUIRE(report.has_value());
    REQUIRE(report->degenerate_covariates.size() == 1);
    CHECK(report->degenerate_covariates[0] == 1);
    // 2.0 SDs on the live covariate alone. Counting the dead one would
    // have averaged it down to sqrt(4/2) = 1.41.
    REQUIRE(report->pairs.size() == 1);
    CHECK(report->pairs[0].distance == Approx(2.0));
}

TEST_CASE("matching on nothing at all is an error", "[gm-signals][matching]") {
    // Every covariate constant means every candidate is at distance
    // zero and the "nearest" control is simply the first one. Returning
    // a report there would be arbitrary pairing dressed as matching,
    // complete with a balance table of perfect zeros.
    const std::vector<MatchUnit> units{
        unit(0, "s", true, {1.0}),
        unit(1, "s", false, {1.0}),
    };
    const auto report = match_on_covariates(units, MatchOptions{});
    REQUIRE_FALSE(report.has_value());
    CHECK(report.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("units disagreeing on covariate count is an error", "[gm-signals][matching]") {
    const std::vector<MatchUnit> units{
        unit(0, "s", true, {1.0, 2.0}),
        unit(1, "s", false, {1.0}),
    };
    const auto report = match_on_covariates(units, MatchOptions{});
    REQUIRE_FALSE(report.has_value());
    CHECK(report.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("an empty pool is an empty report, not an error", "[gm-signals][matching]") {
    const auto report = match_on_covariates({}, MatchOptions{});
    REQUIRE(report.has_value());
    CHECK(report->pairs.empty());
    CHECK(report->treated_total == 0);
}

TEST_CASE("the pairing does not depend on input order", "[gm-signals][matching]") {
    // Same units, same ids, supplied in reverse. Two runs of the study
    // over the same data must produce the same pairs (ADR-003).
    std::vector<MatchUnit> units{
        unit(0, "s", true, {0.0}),  unit(1, "s", false, {0.4}), unit(2, "s", true, {1.0}),
        unit(3, "s", false, {1.4}), unit(4, "s", false, {9.0}),
    };
    MatchOptions opt;
    opt.caliper = 1.0;

    const auto forward = match_on_covariates(units, opt);
    std::reverse(units.begin(), units.end());
    const auto reversed = match_on_covariates(units, opt);

    REQUIRE(forward.has_value());
    REQUIRE(reversed.has_value());
    REQUIRE(forward->pairs.size() == reversed->pairs.size());
    for (std::size_t i = 0; i < forward->pairs.size(); ++i) {
        CHECK(forward->pairs[i].treated_id == reversed->pairs[i].treated_id);
        CHECK(forward->pairs[i].control_id == reversed->pairs[i].control_id);
    }
}
