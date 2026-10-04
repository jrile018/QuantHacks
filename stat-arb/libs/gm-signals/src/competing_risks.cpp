#include <gm-signals/competing_risks.hpp>

#include <algorithm>
#include <map>

namespace gm::signals {

Result<CumulativeIncidence> aalen_johansen(const std::vector<CompetingEpisode>& episodes) {
    CumulativeIncidence curve;
    curve.n_ = static_cast<std::int64_t>(episodes.size());

    // std::map throughout: days are visited in ascending order and the
    // arithmetic is therefore identical across runs (ADR-003).
    std::map<std::int64_t, std::int64_t> events_on, competing_on, censored_on;
    for (const auto& e : episodes) {
        if (e.duration_days < 0) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "competing-risks episode has a negative duration",
                                                   std::to_string(e.duration_days)));
        }
        switch (e.outcome) {
            case Outcome::kEvent:
                ++events_on[e.duration_days];
                ++curve.events_;
                break;
            case Outcome::kCompeting:
                ++competing_on[e.duration_days];
                ++curve.competing_;
                break;
            case Outcome::kCensored:
                ++censored_on[e.duration_days];
                break;
        }
    }

    std::map<std::int64_t, bool> days;
    for (const auto& [d, c] : events_on) { (void)c; days[d] = true; }
    for (const auto& [d, c] : competing_on) { (void)c; days[d] = true; }
    for (const auto& [d, c] : censored_on) { (void)c; days[d] = true; }

    std::int64_t at_risk = curve.n_;
    double survival = 1.0;  // S(t): free of BOTH causes
    double cif_event = 0.0, cif_competing = 0.0;
    double naive_survival = 1.0;  // KM with the competing cause folded into censoring

    for (const auto& [day, unused] : days) {
        (void)unused;
        const auto e_it = events_on.find(day);
        const auto k_it = competing_on.find(day);
        const auto c_it = censored_on.find(day);
        const std::int64_t d_event = e_it == events_on.end() ? 0 : e_it->second;
        const std::int64_t d_comp = k_it == competing_on.end() ? 0 : k_it->second;
        const std::int64_t d_cens = c_it == censored_on.end() ? 0 : c_it->second;

        if (at_risk > 0 && (d_event > 0 || d_comp > 0)) {
            const double n = static_cast<double>(at_risk);
            // Each cause's increment is weighted by the probability of
            // still being at risk just BEFORE this day. That factor -
            // survival carried in from the previous step, not the
            // cause-specific survival - is the whole difference between
            // this and running two independent Kaplan-Meiers.
            const double s_prev = survival;
            cif_event += s_prev * static_cast<double>(d_event) / n;
            cif_competing += s_prev * static_cast<double>(d_comp) / n;
            survival = s_prev * (1.0 - static_cast<double>(d_event + d_comp) / n);

            // The naive comparison, on the same risk set but with the
            // competing cause counted as if the episode had merely
            // stopped being watched.
            if (d_event > 0) {
                naive_survival *= 1.0 - static_cast<double>(d_event) / n;
            }
        }

        if (d_event > 0 || d_comp > 0) {
            curve.points_.push_back(IncidencePoint{day, at_risk, d_event, d_comp, survival, cif_event,
                                                    cif_competing});
        }

        at_risk -= (d_event + d_comp + d_cens);
        if (at_risk < 0) at_risk = 0;
        curve.risk_after_.emplace_back(day, at_risk);
        curve.naive_after_.emplace_back(day, 1.0 - naive_survival);
    }

    return curve;
}

namespace {

/// Right-continuous step lookup: the value carried by the last step at
/// or before `horizon`.
template <typename T>
T step_value(const std::vector<std::pair<std::int64_t, T>>& steps, std::int64_t horizon, T before_first) {
    T out = before_first;
    for (const auto& [day, value] : steps) {
        if (day > horizon) break;
        out = value;
    }
    return out;
}

}  // namespace

double CumulativeIncidence::cif_event_by(std::int64_t horizon) const {
    double out = 0.0;
    for (const auto& p : points_) {
        if (p.day > horizon) break;
        out = p.cif_event;
    }
    return out;
}

double CumulativeIncidence::cif_competing_by(std::int64_t horizon) const {
    double out = 0.0;
    for (const auto& p : points_) {
        if (p.day > horizon) break;
        out = p.cif_competing;
    }
    return out;
}

double CumulativeIncidence::naive_km_by(std::int64_t horizon) const {
    return step_value<double>(naive_after_, horizon, 0.0);
}

IncidenceEstimate CumulativeIncidence::at(std::int64_t horizon) const {
    IncidenceEstimate est;
    est.horizon_days = horizon;
    est.cif_event = cif_event_by(horizon);
    est.cif_competing = cif_competing_by(horizon);
    est.naive_km = naive_km_by(horizon);
    est.naive_overstatement = est.naive_km - est.cif_event;
    est.at_risk_at_horizon = step_value<std::int64_t>(risk_after_, horizon, n_);
    return est;
}

}  // namespace gm::signals
