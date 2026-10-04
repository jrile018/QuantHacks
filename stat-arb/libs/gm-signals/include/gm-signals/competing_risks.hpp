#pragma once

// Cumulative incidence with a competing risk (Aalen-Johansen).
//
// WHY THIS EXISTS
// ---------------
// Kaplan-Meier (survival.hpp) assumes that censoring is INDEPENDENT of
// the outcome: an episode that stops being observed is assumed to have
// been on the same trajectory as the episodes still being watched. For
// the panel simply running out of dates, that is fine.
//
// It is not fine for a takeover. A name dislocated because it is being
// acquired will never revert - not "was not observed reverting", but
// cannot. Feeding that to Kaplan-Meier as a censored observation tells
// the estimator "assume this one behaves like the survivors", and the
// survivors are exactly the episodes that do revert. The result is a
// reversion probability biased UP, and biased up hardest in precisely
// the deep-excursion buckets where takeovers concentrate - which is to
// say, in the buckets the gate is most interested in.
//
// Aalen-Johansen keeps the two apart. It estimates the cumulative
// incidence of each cause separately against the SAME overall survival
// function, so a takeover removes the episode from the risk set without
// its probability mass being redistributed onto reversion.
//
// THE COMPARISON IS THE POINT
// ---------------------------
// This class deliberately computes both estimates and exposes them side
// by side, because the size of the gap is itself a finding. If naive KM
// and Aalen-Johansen agree to the third decimal, competing risks were
// never material here and the gate can stop worrying about them. If they
// diverge, the KM number was overstating reversion and by how much is
// now a measured quantity rather than an argument.
//
// WHERE THE CLASSIFICATION COMES FROM, AND WHY IT IS A HEURISTIC
// --------------------------------------------------------------
// This library does not decide what a competing event is; the caller
// does. In the gate an episode is classed competing when the ticker's
// price series ends materially before the panel does and the ticker is
// in the departed-membership set. With no corporate-actions feed, a name
// that stopped being COVERED looks the same as one that stopped
// EXISTING. That limit is real and is recorded in BLOCKED.md entry 9;
// the tolerance is configurable so the estimate can be recomputed under
// a different assumption.

#include <gm-core/error.hpp>

#include <cstdint>
#include <utility>
#include <vector>

namespace gm::signals {

enum class Outcome {
    kCensored = 0,   // still outside, still being watched when observation stopped
    kEvent = 1,      // reverted - the outcome the gate is about
    kCompeting = 2,  // the episode can no longer revert (delisted, acquired)
};

struct CompetingEpisode {
    std::int64_t duration_days{};
    Outcome outcome{Outcome::kCensored};
};

struct IncidencePoint {
    std::int64_t day{};
    std::int64_t at_risk{};
    std::int64_t events{};
    std::int64_t competing{};
    double overall_survival{};  // free of BOTH causes at t
    double cif_event{};         // P(reverted by t), competing risks respected
    double cif_competing{};     // P(removed by the competing cause by t)
};

/// P(reverted by H) three ways, so the correction is visible rather than
/// asserted.
struct IncidenceEstimate {
    std::int64_t horizon_days{};
    double cif_event{};       // Aalen-Johansen - the one to quote
    double cif_competing{};
    double naive_km{};        // 1 - KM, competing events treated as censoring
    /// naive_km - cif_event. Non-negative by construction: treating a
    /// competing event as censoring can only push the reversion estimate
    /// up. This is the bias the gate was carrying before.
    double naive_overstatement{};
    std::int64_t at_risk_at_horizon{};
};

class CumulativeIncidence {
public:
    [[nodiscard]] const std::vector<IncidencePoint>& points() const noexcept { return points_; }
    [[nodiscard]] std::int64_t n() const noexcept { return n_; }
    [[nodiscard]] std::int64_t events() const noexcept { return events_; }
    [[nodiscard]] std::int64_t competing() const noexcept { return competing_; }
    [[nodiscard]] std::int64_t censored() const noexcept { return n_ - events_ - competing_; }

    [[nodiscard]] double cif_event_by(std::int64_t horizon) const;
    [[nodiscard]] double cif_competing_by(std::int64_t horizon) const;
    /// 1 - S_KM(horizon) with competing events folded into censoring:
    /// what survival.hpp would report on the same episodes.
    [[nodiscard]] double naive_km_by(std::int64_t horizon) const;

    [[nodiscard]] IncidenceEstimate at(std::int64_t horizon) const;

private:
    friend Result<CumulativeIncidence> aalen_johansen(const std::vector<CompetingEpisode>&);
    std::vector<IncidencePoint> points_;
    // (day, 1 - S_KM after that day), competing folded into censoring.
    std::vector<std::pair<std::int64_t, double>> naive_after_;
    // (day, episodes still at risk AFTER that day) for every day on
    // which anything at all happened - the same bookkeeping survival.hpp
    // needs, and for the same reason: points_ holds only event days, so
    // an episode leaving after the last event would otherwise look like
    // it was still under observation forever.
    std::vector<std::pair<std::int64_t, std::int64_t>> risk_after_;
    std::int64_t n_{};
    std::int64_t events_{};
    std::int64_t competing_{};
};

/// Aalen-Johansen cumulative incidence for one event of interest against
/// one competing cause.
///
/// Ties follow the same convention as survival.hpp: everything happening
/// on a day is counted against the risk set at the START of that day,
/// and censored episodes leave after it.
///
/// Fails on a negative duration. An empty input is not an error: it
/// yields an empty curve reporting zero incidence and zero at risk, so
/// an empty bucket reads as "nothing observed" rather than as an
/// incidence of zero.
[[nodiscard]] Result<CumulativeIncidence> aalen_johansen(const std::vector<CompetingEpisode>& episodes);

}  // namespace gm::signals
