#pragma once

// Cluster-robust inference for the ADR-013 gate.
//
// WHY THIS EXISTS
// ---------------
// The study counts 7,110 excursions. It does not have 7,110 independent
// observations, and the gap between those two numbers is large enough to
// change the conclusion.
//
// Two dependencies, both severe:
//
//   BY NAME. One ticker contributes many episodes over sixteen years,
//   driven by the same business, the same sector exposure and the same
//   liquidity. Its episodes are more like repeated measurements of one
//   thing than like separate facts.
//
//   BY CALENDAR. Excursions cluster in time - a stressed fortnight
//   throws dozens of names outside the band at once, and they revert
//   together when the stress passes. Fifty episodes from March 2020 are
//   close to one observation of March 2020.
//
// Treating any of that as independent shrinks the standard error by a
// factor that has nothing to do with evidence, and manufactures
// significance. The fix is a two-way cluster-robust sandwich (Cameron,
// Gelbach and Miller 2011), clustering on ticker AND on calendar month:
//
//     V = V_ticker + V_month - V_ticker_and_month
//
// with the intersection subtracted so overlap is not counted twice.
//
// THE NUMBER WORTH READING
// ------------------------
// `effective_n`. It is the sample size an independent study would have
// needed to produce the same standard error, and it is the honest
// headline: if 7,110 episodes carry the information of 300, the report
// should say 300. It is computed as n divided by the design effect, the
// ratio of clustered to naive variance - so it falls out of the same
// arithmetic rather than being asserted.
//
// LIMITATION, STATED HERE RATHER THAN DISCOVERED LATER
// ----------------------------------------------------
// Intervals use a normal critical value, not a t quantile on a cluster
// count. With ~79 tickers and ~200 months that is a negligible
// difference; on a narrow slice it is not, and the interval will read
// too tight. `min_clusters` is reported for exactly this reason - below
// roughly 30 the interval is indicative only. See BLOCKED.md entry 10.

#include <gm-core/error.hpp>

#include <cstdint>
#include <string>
#include <vector>

namespace gm::signals {

/// One outcome observation with its two cluster memberships. In the gate
/// `cluster_a` is the ticker and `cluster_b` is the calendar month of
/// the excursion's start.
struct ClusterObservation {
    double value{};
    bool treated{};
    std::string cluster_a;
    std::string cluster_b;
};

struct DifferenceEstimate {
    double treated_mean{};
    double control_mean{};
    double difference{};  // treated - control; the estimate under test

    std::int64_t n_treated{};
    std::int64_t n_control{};

    /// The naive standard error, assuming every observation is its own
    /// independent fact. Reported not because it should be used but
    /// because the ratio to the clustered one IS the finding about how
    /// much of the sample was double counting.
    double se_iid{};
    double se_clustered{};

    double t_statistic{};  // difference / se_clustered
    double ci_low{};
    double ci_high{};

    std::int64_t clusters_a{};
    std::int64_t clusters_b{};
    std::int64_t clusters_ab{};
    std::int64_t min_clusters{};  // below ~30, read the interval as indicative

    /// (se_clustered / se_iid)^2 - how many observations the dependence
    /// costs, per observation.
    double design_effect{};
    /// n / design_effect. The sample size this evidence is actually
    /// worth.
    double effective_n{};

    /// The two-way subtraction can leave a non-positive variance (a
    /// known property of the estimator, not a bug in this code). When it
    /// does, the larger one-way variance is used instead and this is
    /// set, so a reader is never handed a standard error that the
    /// arithmetic did not actually produce.
    bool two_way_variance_adjusted{};
};

/// Difference in means between the treated and control arms, with a
/// two-way cluster-robust standard error.
///
/// Fails if either arm is empty or fewer than three observations are
/// supplied - a difference between one observation and one observation
/// has no standard error, and returning a number there would invite it
/// to be quoted.
[[nodiscard]] Result<DifferenceEstimate> clustered_difference(const std::vector<ClusterObservation>& obs);

}  // namespace gm::signals
