#pragma once

// Time-to-reversion as a survival curve (Kaplan-Meier), which is what
// ADR-013's gate actually asks for: P(the point returns inside within H
// days | exit depth >= d).
//
// WHY THIS EXISTS
// ---------------
// The first version of the reversion study reported one number per
// bucket: the fraction of excursions whose `reverted` flag was true.
// That flag means "closed before the price series ran out", with no
// horizon at all, and over sixteen years a rolling-window z-score
// essentially always crosses back eventually. The study duly reported
// 99.8% - overall, in every peak-depth quartile, with earnings and
// without. A figure that flat across every conditioning variable is a
// property of the definition, not a fact about markets.
//
// "It comes back eventually" is not tradable and not even interesting.
// The horizon is the whole question, and ADR-013 says so in as many
// words; it was lost in implementation.
//
// WHY KAPLAN-MEIER RATHER THAN A COUNT
// ------------------------------------
// Because some episodes are RIGHT-CENSORED: still outside the band when
// the data ended. Such an episode, observed for 4 days, tells us the
// point had not returned by day 4 - and nothing whatever about day 20.
// The two naive repairs are both wrong in known directions:
//
//   - counting censored episodes as non-reversions biases P(revert)
//     DOWN, inventing failures that were never observed;
//   - dropping them biases it UP, since an episode is censored
//     precisely because it was still dislocated, i.e. the slow ones.
//
// Kaplan-Meier uses each censored episode for exactly the period it was
// observed and then removes it from the risk set, which is the only
// treatment that uses the information without inventing any. It also
// gives a variance (Greenwood), so a bucket of 40 excursions reports a
// wide interval instead of a confident-looking point estimate.

#include <gm-core/error.hpp>

#include <cstdint>
#include <optional>
#include <utility>
#include <vector>

namespace gm::signals {

/// One observed episode. `reverted == false` means right-censored at
/// `duration_days`: still outside the band when observation stopped.
struct Episode {
    std::int64_t duration_days{};
    bool reverted{};
};

/// One step of the curve, at a day on which at least one reversion
/// happened.
struct SurvivalPoint {
    std::int64_t day{};
    std::int64_t at_risk{};     // episodes still outside and still observed
    std::int64_t events{};      // reversions on this day
    double survival{};          // S(t): still outside at t
    double reverted_by{};       // 1 - S(t): the number the gate asks for
    double reverted_by_ci_low{};
    double reverted_by_ci_high{};
};

/// P(reverted by H) with a 95% interval, for one horizon.
struct HorizonEstimate {
    std::int64_t horizon_days{};
    double reverted_by{};
    double ci_low{};
    double ci_high{};
    std::int64_t at_risk_at_horizon{};  // 0 means the curve says nothing here
};

class SurvivalCurve {
public:
    [[nodiscard]] const std::vector<SurvivalPoint>& points() const noexcept { return points_; }
    [[nodiscard]] std::int64_t n() const noexcept { return n_; }
    [[nodiscard]] std::int64_t events() const noexcept { return events_; }
    [[nodiscard]] std::int64_t censored() const noexcept { return n_ - events_; }

    /// P(reverted by `horizon`), a right-continuous step function: the
    /// value carried by the last step at or before `horizon`.
    [[nodiscard]] double reverted_by(std::int64_t horizon) const;

    /// The same with its Greenwood interval and the risk set still
    /// under observation at that horizon - a probability computed from
    /// two remaining episodes deserves to be read differently from one
    /// computed from two thousand.
    [[nodiscard]] HorizonEstimate at(std::int64_t horizon) const;

    /// First day on which the curve has fallen to or below 0.5. Absent
    /// when it never does - which is the honest answer, not the largest
    /// observed duration.
    [[nodiscard]] std::optional<std::int64_t> median_days() const;

private:
    friend Result<SurvivalCurve> kaplan_meier(const std::vector<Episode>&);
    std::vector<SurvivalPoint> points_;
    // (day, episodes still outside and still observed AFTER that day),
    // for every day on which anything happened - reversions and
    // censorings alike. points_ alone cannot answer this: it holds only
    // the days with events, so an episode censored after the last
    // reversion would look like it was still being watched.
    std::vector<std::pair<std::int64_t, std::int64_t>> risk_after_;
    std::int64_t n_{};
    std::int64_t events_{};
};

/// Kaplan-Meier product-limit estimator with Greenwood standard errors.
/// Ties are handled at the day level: all events on a day are counted
/// against the risk set at the start of that day, and censored episodes
/// sharing that day leave AFTER it (the standard convention - a censored
/// observation at time t is assumed still at risk for the event at t).
///
/// Fails on a negative duration. An empty input is NOT an error: it
/// yields an empty curve whose reverted_by() is 0 and whose at() reports
/// zero at risk, so an empty bucket reads as "nothing observed" rather
/// than as a reversion rate of zero.
[[nodiscard]] Result<SurvivalCurve> kaplan_meier(const std::vector<Episode>& episodes);

} // namespace gm::signals
