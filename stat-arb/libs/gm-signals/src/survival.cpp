#include <gm-signals/survival.hpp>

#include <algorithm>
#include <cmath>
#include <map>

namespace gm::signals {

namespace {

/// Greenwood's formula gives the variance of S(t); the interval is
/// needed on 1 - S(t). The two differ only by sign, so the half-width
/// carries over unchanged, and the result is clamped to [0, 1] - a
/// naive normal interval runs outside the unit interval near 0 and 1,
/// and a reported probability of 1.04 destroys confidence in every
/// other number on the page.
double clamp01(double x) { return x < 0.0 ? 0.0 : (x > 1.0 ? 1.0 : x); }

} // namespace

Result<SurvivalCurve> kaplan_meier(const std::vector<Episode>& episodes) {
    SurvivalCurve curve;
    curve.n_ = static_cast<std::int64_t>(episodes.size());

    // std::map, not unordered: the curve is emitted in day order and
    // two runs over the same episodes must produce the same bytes
    // (ADR-003).
    std::map<std::int64_t, std::int64_t> events_on;    // day -> reversions
    std::map<std::int64_t, std::int64_t> censored_on;  // day -> censored
    for (const auto& e : episodes) {
        if (e.duration_days < 0) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "survival episode has a negative duration",
                                                   std::to_string(e.duration_days)));
        }
        if (e.reverted) {
            ++events_on[e.duration_days];
            ++curve.events_;
        } else {
            ++censored_on[e.duration_days];
        }
    }

    std::int64_t at_risk = curve.n_;
    double survival = 1.0;
    double greenwood_sum = 0.0;  // running sum of d / (n * (n - d))

    // Walk every day on which anything happened, so censored episodes
    // leave the risk set at the right moment even on days with no event.
    std::map<std::int64_t, bool> days;
    for (const auto& [day, count] : events_on) { (void)count; days[day] = true; }
    for (const auto& [day, count] : censored_on) { (void)count; days[day] = true; }

    for (const auto& [day, unused] : days) {
        (void)unused;
        const auto it = events_on.find(day);
        const std::int64_t d = it == events_on.end() ? 0 : it->second;

        if (d > 0 && at_risk > 0) {
            survival *= 1.0 - static_cast<double>(d) / static_cast<double>(at_risk);
            if (at_risk > d) {
                greenwood_sum += static_cast<double>(d) /
                                  (static_cast<double>(at_risk) * static_cast<double>(at_risk - d));
            } else {
                // Every remaining episode reverted on this day: S(t) is
                // exactly 0 and Greenwood's term is undefined. The
                // variance is left where it stood rather than made
                // infinite; the interval is degenerate here either way
                // and at_risk_at_horizon tells the reader why.
            }

            const double se_survival = survival * std::sqrt(greenwood_sum);
            const double half_width = 1.959963984540054 * se_survival;  // 95%, two-sided
            SurvivalPoint p;
            p.day = day;
            p.at_risk = at_risk;
            p.events = d;
            p.survival = survival;
            p.reverted_by = 1.0 - survival;
            p.reverted_by_ci_low = clamp01(p.reverted_by - half_width);
            p.reverted_by_ci_high = clamp01(p.reverted_by + half_width);
            curve.points_.push_back(p);
        }

        // Both events and censorings observed on this day leave the risk
        // set afterwards: an episode censored at t was still at risk for
        // an event at t, which is the standard convention and the one
        // that keeps a censoring from silently deleting a same-day
        // reversion.
        at_risk -= d;
        const auto cit = censored_on.find(day);
        if (cit != censored_on.end()) at_risk -= cit->second;
        if (at_risk < 0) at_risk = 0;
        curve.risk_after_.emplace_back(day, at_risk);
    }

    return curve;
}

double SurvivalCurve::reverted_by(std::int64_t horizon) const {
    double value = 0.0;
    for (const auto& p : points_) {
        if (p.day > horizon) break;
        value = p.reverted_by;
    }
    return value;
}

HorizonEstimate SurvivalCurve::at(std::int64_t horizon) const {
    HorizonEstimate est;
    est.horizon_days = horizon;

    const SurvivalPoint* last = nullptr;
    for (const auto& p : points_) {
        if (p.day > horizon) break;
        last = &p;
    }
    if (last != nullptr) {
        est.reverted_by = last->reverted_by;
        est.ci_low = last->reverted_by_ci_low;
        est.ci_high = last->reverted_by_ci_high;
    }

    // How many episodes were still outside AND still under observation
    // once the horizon passed. Zero means every episode either reverted
    // or was censored before the horizon, so the estimate beyond that
    // point rests on nothing new - the difference between "20% had not
    // reverted by day 40" and "we stopped watching before day 40".
    std::int64_t still_at_risk = n_;
    for (const auto& [day, after] : risk_after_) {
        if (day > horizon) break;
        still_at_risk = after;
    }
    est.at_risk_at_horizon = still_at_risk < 0 ? 0 : still_at_risk;
    return est;
}

std::optional<std::int64_t> SurvivalCurve::median_days() const {
    for (const auto& p : points_) {
        if (p.survival <= 0.5) return p.day;
    }
    return std::nullopt;
}

} // namespace gm::signals
