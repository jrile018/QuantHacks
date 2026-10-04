#include <gm-signals/matching.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <vector>

namespace gm::signals {

namespace {

/// Population standard deviation over every supplied unit, treated and
/// control together. Pooling both arms is deliberate: it makes the
/// caliper and the balance table read in the same units, and it keeps
/// the denominator fixed as pairs are formed, so "before" and "after"
/// standardized differences are comparable to each other rather than
/// each being scaled by its own sample.
std::vector<double> pooled_sd(const std::vector<MatchUnit>& units, std::size_t k) {
    std::vector<double> mean(k, 0.0), sd(k, 0.0);
    if (units.empty()) return sd;
    for (const auto& u : units) {
        for (std::size_t j = 0; j < k; ++j) mean[j] += u.covariates[j];
    }
    const double n = static_cast<double>(units.size());
    for (std::size_t j = 0; j < k; ++j) mean[j] /= n;
    for (const auto& u : units) {
        for (std::size_t j = 0; j < k; ++j) {
            const double d = u.covariates[j] - mean[j];
            sd[j] += d * d;
        }
    }
    for (std::size_t j = 0; j < k; ++j) sd[j] = std::sqrt(sd[j] / n);
    return sd;
}

/// Standardized difference per covariate over a chosen subset of units,
/// scaled by the SAME pooled SD in both the before and after tables.
std::vector<double> standardized_diff(const std::vector<const MatchUnit*>& treated,
                                       const std::vector<const MatchUnit*>& control,
                                       const std::vector<double>& sd, std::size_t k) {
    std::vector<double> out(k, 0.0);
    if (treated.empty() || control.empty()) return out;
    for (std::size_t j = 0; j < k; ++j) {
        if (!(sd[j] > 0.0)) continue;  // degenerate: difference is zero by construction
        double mt = 0.0, mc = 0.0;
        for (const auto* u : treated) mt += u->covariates[j];
        for (const auto* u : control) mc += u->covariates[j];
        mt /= static_cast<double>(treated.size());
        mc /= static_cast<double>(control.size());
        out[j] = (mt - mc) / sd[j];
    }
    return out;
}

}  // namespace

double MatchReport::worst_balance_after() const {
    double worst = 0.0;
    for (const double d : standardized_diff_after) worst = std::max(worst, std::abs(d));
    return worst;
}

Result<MatchReport> match_on_covariates(const std::vector<MatchUnit>& units, const MatchOptions& options) {
    MatchReport report;
    if (units.empty()) return report;

    const std::size_t k = units.front().covariates.size();
    if (k == 0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "matching requires at least one covariate", "0 supplied"));
    }
    for (const auto& u : units) {
        if (u.covariates.size() != k) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "matching units disagree on covariate count",
                                                   "expected " + std::to_string(k) + ", got " +
                                                       std::to_string(u.covariates.size())));
        }
    }

    const std::vector<double> sd = pooled_sd(units, k);
    std::size_t usable = 0;
    for (std::size_t j = 0; j < k; ++j) {
        if (sd[j] > 0.0) {
            ++usable;
        } else {
            report.degenerate_covariates.push_back(j);
        }
    }
    if (usable == 0) {
        // Every covariate is constant, so every candidate is at distance
        // zero and the "nearest" control is whichever happens to be
        // first. That is not matching; it is arbitrary pairing wearing
        // matching's clothes, and it would produce a confident-looking
        // balance table full of zeros.
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "every matching covariate has zero variance",
                                               std::to_string(k) + " covariates supplied"));
    }

    // std::map, not unordered: strata are visited in a fixed order so
    // control consumption - and therefore every pair - is identical
    // across runs (ADR-003).
    std::map<std::string, std::vector<std::size_t>> treated_by_stratum, control_by_stratum;
    for (std::size_t i = 0; i < units.size(); ++i) {
        (units[i].treated ? treated_by_stratum : control_by_stratum)[units[i].stratum].push_back(i);
        if (units[i].treated) {
            ++report.treated_total;
        } else {
            ++report.controls_available;
        }
    }
    // Order by the caller's id, NOT by position in the input vector.
    // Greedy matching consumes controls, so the order treated units are
    // served in decides who gets the good ones - and if that order came
    // from input position, handing the same units to this function in a
    // different order would produce a different set of pairs. It did,
    // until this sort existed. Ids are the study's own row numbering and
    // are stable, so keying on them makes the pairing a function of the
    // data rather than of how the data happened to be stacked (ADR-003).
    const auto by_caller_id = [&units](std::size_t l, std::size_t r) { return units[l].id < units[r].id; };
    for (auto& [stratum, idx] : treated_by_stratum) {
        (void)stratum;
        std::sort(idx.begin(), idx.end(), by_caller_id);
    }
    for (auto& [stratum, idx] : control_by_stratum) {
        (void)stratum;
        std::sort(idx.begin(), idx.end(), by_caller_id);
    }

    const double caliper = options.caliper;

    for (const auto& [stratum, treated_idx] : treated_by_stratum) {
        auto ctrl_it = control_by_stratum.find(stratum);
        if (ctrl_it == control_by_stratum.end()) {
            report.treated_unmatched_no_controls += treated_idx.size();
            continue;
        }
        // Consumed flags rather than erasing from the vector: erasing
        // would make the surviving order depend on which controls were
        // taken earlier in a way that is harder to reason about.
        std::vector<bool> taken(ctrl_it->second.size(), false);
        std::size_t remaining = ctrl_it->second.size();

        for (const std::size_t t : treated_idx) {  // ascending by construction
            if (remaining == 0) {
                ++report.treated_unmatched_exhausted;
                continue;
            }
            double best = std::numeric_limits<double>::infinity();
            std::size_t best_slot = 0;
            bool found = false;
            for (std::size_t s = 0; s < ctrl_it->second.size(); ++s) {
                if (taken[s]) continue;
                const std::size_t c = ctrl_it->second[s];
                double acc = 0.0;
                for (std::size_t j = 0; j < k; ++j) {
                    if (!(sd[j] > 0.0)) continue;
                    const double d = (units[t].covariates[j] - units[c].covariates[j]) / sd[j];
                    acc += d * d;
                }
                // Root MEAN square, so the caliper carries the same
                // meaning whatever the covariate count.
                const double dist = std::sqrt(acc / static_cast<double>(usable));
                // Strict <: ties go to the earlier (lower-id) control,
                // since the candidate list is already in ascending id
                // order.
                if (dist < best) {
                    best = dist;
                    best_slot = s;
                    found = true;
                }
            }
            if (!found) {
                ++report.treated_unmatched_exhausted;
                continue;
            }
            if (best > caliper) {
                ++report.treated_unmatched_caliper;
                continue;
            }
            taken[best_slot] = true;
            --remaining;
            ++report.treated_matched;
            report.pairs.push_back(MatchedPair{units[t].id, units[ctrl_it->second[best_slot]].id, best});
        }
    }

    // Balance. "Before" is every unit supplied; "after" is only the
    // units that ended up in a pair.
    std::vector<const MatchUnit*> t_all, c_all, t_matched, c_matched;
    for (const auto& u : units) (u.treated ? t_all : c_all).push_back(&u);
    // id is the caller's row index and pairs store ids, so map back.
    std::map<std::size_t, const MatchUnit*> by_id;
    for (const auto& u : units) by_id[u.id] = &u;
    for (const auto& p : report.pairs) {
        t_matched.push_back(by_id.at(p.treated_id));
        c_matched.push_back(by_id.at(p.control_id));
    }
    report.standardized_diff_before = standardized_diff(t_all, c_all, sd, k);
    report.standardized_diff_after = standardized_diff(t_matched, c_matched, sd, k);

    return report;
}

}  // namespace gm::signals
