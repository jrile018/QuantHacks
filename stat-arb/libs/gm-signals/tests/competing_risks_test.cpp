// Tests for Aalen-Johansen cumulative incidence.
//
// The first is hand-computable and pins the arithmetic. The third is the
// reason the file exists: it shows, on the same four episodes, that
// treating a takeover as ordinary censoring overstates the reversion
// probability - the bias the gate was carrying.

#include <gm-signals/competing_risks.hpp>
#include <gm-signals/survival.hpp>

#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include <vector>

using Catch::Approx;
using gm::signals::aalen_johansen;
using gm::signals::CompetingEpisode;
using gm::signals::Outcome;

namespace {

/// Four episodes, worked through by hand in the test below.
const std::vector<CompetingEpisode> kWorked{
    {1, Outcome::kEvent},
    {2, Outcome::kCompeting},
    {3, Outcome::kEvent},
    {4, Outcome::kCensored},
};

}  // namespace

TEST_CASE("Aalen-Johansen matches a hand-computed example", "[gm-signals][competing-risks]") {
    // n = 4. Walking the days, with S carried in from the previous step:
    //
    //   day 1  at risk 4, one reversion
    //          CIF_event    = 1.00 * 1/4               = 0.25
    //          S            = 1.00 * (1 - 1/4)         = 0.75
    //   day 2  at risk 3, one competing event
    //          CIF_competing= 0.75 * 1/3               = 0.25
    //          S            = 0.75 * (1 - 1/3)         = 0.50
    //   day 3  at risk 2, one reversion
    //          CIF_event    = 0.25 + 0.50 * 1/2        = 0.50
    //          S            = 0.50 * (1 - 1/2)         = 0.25
    //   day 4  at risk 1, censored - nothing moves
    //
    // Each increment is weighted by the probability of still being at
    // risk just before that day. That factor is the entire difference
    // between this and running two independent Kaplan-Meiers, and it is
    // where a hand-rolled implementation goes wrong.
    const auto curve = aalen_johansen(kWorked);
    REQUIRE(curve.has_value());
    CHECK(curve->n() == 4);
    CHECK(curve->events() == 2);
    CHECK(curve->competing() == 1);
    CHECK(curve->censored() == 1);

    CHECK(curve->cif_event_by(1) == Approx(0.25));
    CHECK(curve->cif_competing_by(1) == Approx(0.0));
    CHECK(curve->cif_event_by(2) == Approx(0.25));
    CHECK(curve->cif_competing_by(2) == Approx(0.25));
    CHECK(curve->cif_event_by(3) == Approx(0.50));
    CHECK(curve->cif_event_by(10) == Approx(0.50));

    // Before anything has happened, nothing has happened.
    CHECK(curve->cif_event_by(0) == Approx(0.0));
}

TEST_CASE("the two incidences and the survivor account for everyone",
          "[gm-signals][competing-risks]") {
    // CIF_event(t) + CIF_competing(t) + S(t) = 1 at every step. This is
    // the identity that makes cumulative incidence interpretable as a
    // probability at all - every episode is, at any time, either
    // reverted, removed by the competing cause, or still outside. An
    // implementation that redistributes the competing mass onto
    // reversion breaks it.
    const auto curve = aalen_johansen(kWorked);
    REQUIRE(curve.has_value());
    REQUIRE_FALSE(curve->points().empty());
    for (const auto& p : curve->points()) {
        CHECK(p.cif_event + p.cif_competing + p.overall_survival == Approx(1.0));
    }
}

TEST_CASE("treating a competing event as censoring overstates reversion",
          "[gm-signals][competing-risks]") {
    // The bug this file exists to correct, measured on the same four
    // episodes.
    //
    // Naive Kaplan-Meier, competing folded into censoring:
    //   day 1  at risk 4, one event   -> S = 0.75
    //   day 2  one leaves (censored)  -> S unchanged, at risk 2
    //   day 3  at risk 2, one event   -> S = 0.75 * 0.5 = 0.375
    //   so it reports 1 - 0.375 = 0.625 reverted.
    //
    // Aalen-Johansen reports 0.50. The 0.125 gap is real probability
    // mass belonging to an episode that could never revert, handed to
    // reversion because Kaplan-Meier was told to assume the departed
    // episode behaved like the survivors.
    const auto curve = aalen_johansen(kWorked);
    REQUIRE(curve.has_value());

    const auto est = curve->at(3);
    CHECK(est.cif_event == Approx(0.50));
    CHECK(est.naive_km == Approx(0.625));
    CHECK(est.naive_overstatement == Approx(0.125));
    // The direction is not incidental - it can only go this way.
    CHECK(est.naive_km >= est.cif_event);
}

TEST_CASE("with no competing events it reduces to Kaplan-Meier", "[gm-signals][competing-risks]") {
    // Cross-checked against the OTHER implementation in this library
    // rather than against a hardcoded table, so the two cannot drift
    // apart unnoticed. Any episode set with no competing cause must give
    // identical answers from both estimators.
    const std::vector<CompetingEpisode> episodes{
        {2, Outcome::kEvent},    {2, Outcome::kEvent},   {3, Outcome::kCensored},
        {5, Outcome::kEvent},    {7, Outcome::kCensored}, {8, Outcome::kEvent},
        {11, Outcome::kCensored},
    };
    std::vector<gm::signals::Episode> km_episodes;
    km_episodes.reserve(episodes.size());
    for (const auto& e : episodes) {
        km_episodes.push_back(gm::signals::Episode{e.duration_days, e.outcome == Outcome::kEvent});
    }

    const auto cif = aalen_johansen(episodes);
    const auto km = gm::signals::kaplan_meier(km_episodes);
    REQUIRE(cif.has_value());
    REQUIRE(km.has_value());

    for (const std::int64_t h : {0, 1, 2, 3, 5, 8, 11, 20}) {
        CHECK(cif->cif_event_by(h) == Approx(km->reverted_by(h)));
        CHECK(cif->at(h).naive_overstatement == Approx(0.0));
    }
}

TEST_CASE("the risk set is tracked past the last event", "[gm-signals][competing-risks]") {
    // An episode that leaves after the final event must not look like it
    // is still under observation forever - the same bookkeeping trap
    // survival.hpp has, since the points list only carries event days.
    const std::vector<CompetingEpisode> episodes{
        {1, Outcome::kEvent}, {2, Outcome::kCompeting}, {3, Outcome::kCensored}};
    const auto curve = aalen_johansen(episodes);
    REQUIRE(curve.has_value());
    CHECK(curve->at(1).at_risk_at_horizon == 2);
    CHECK(curve->at(2).at_risk_at_horizon == 1);
    CHECK(curve->at(3).at_risk_at_horizon == 0);
    CHECK(curve->at(99).at_risk_at_horizon == 0);
}

TEST_CASE("an empty bucket reports nothing observed, not zero incidence",
          "[gm-signals][competing-risks]") {
    const auto curve = aalen_johansen({});
    REQUIRE(curve.has_value());
    CHECK(curve->n() == 0);
    CHECK(curve->points().empty());
    CHECK(curve->at(20).cif_event == Approx(0.0));
    CHECK(curve->at(20).at_risk_at_horizon == 0);
}

TEST_CASE("a negative duration is an error", "[gm-signals][competing-risks]") {
    const auto curve = aalen_johansen({{-1, Outcome::kEvent}});
    REQUIRE_FALSE(curve.has_value());
    CHECK(curve.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("the curve does not depend on episode order", "[gm-signals][competing-risks]") {
    std::vector<CompetingEpisode> forward{{1, Outcome::kEvent},     {2, Outcome::kCompeting},
                                           {2, Outcome::kEvent},     {4, Outcome::kCensored},
                                           {5, Outcome::kCompeting}, {6, Outcome::kEvent}};
    const std::vector<CompetingEpisode> backward(forward.rbegin(), forward.rend());

    const auto a = aalen_johansen(forward);
    const auto b = aalen_johansen(backward);
    REQUIRE(a.has_value());
    REQUIRE(b.has_value());
    for (const std::int64_t h : {1, 2, 4, 6, 12}) {
        CHECK(a->cif_event_by(h) == Approx(b->cif_event_by(h)));
        CHECK(a->cif_competing_by(h) == Approx(b->cif_competing_by(h)));
    }
}
