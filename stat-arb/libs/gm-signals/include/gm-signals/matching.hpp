#pragma once

// Matched controls for the ADR-013 gate.
//
// WHY THIS EXISTS
// ---------------
// The reversion study measures how often a flagged excursion comes back
// within H days. That is a BASE RATE, and a base rate is not an edge.
// Anything that has moved a long way tends to move back some of it -
// regression to the mean is a property of noisy series, not a property
// of this geometry. So "68% of deep excursions revert within 20 days"
// is compatible with the boundary carrying real information AND with it
// carrying none at all, and nothing in the study as it stood could tell
// the two apart.
//
// The comparison that can is a matched control: for each flagged
// excursion, find a unit on the SAME DAY that looks like it in every
// respect that is not the flag itself - same sector, similar volatility,
// similar size, and above all a similar recent move - but which the
// boundary did NOT flag. If the flagged units revert more than their
// twins, the geometry is adding something. If they revert the same
// amount, the study was measuring regression to the mean the whole time.
//
// Matching on the prior move is the load-bearing part. A name can fall
// 15% in a month alongside its whole sector (small z - close to its
// peers) or fall 15% while its sector was flat (large z - far from its
// peers). Those two have the same "it went down a lot" and differ in
// exactly the thing under test.
//
// WHY GREEDY NEAREST NEIGHBOUR, NOT A PROPENSITY SCORE
// ----------------------------------------------------
// A propensity score would need a fitted treatment model, which is one
// more thing to be wrong and one more thing to defend. With a handful of
// covariates and an exact-match stratum doing most of the work, distance
// matching in standardized units is both simpler and easier to audit -
// and it produces the balance table below, which is the evidence that
// the matching worked. Greedy without replacement, treated units
// processed in id order and ties broken by the lower control id, so the
// result is bit-identical across runs (ADR-003).
//
// WHAT THIS DELIBERATELY DOES NOT DO
// ----------------------------------
// It does not tell you the match was good. It tells you how good it was:
// standardized differences per covariate before and after, plus counts
// of every treated unit it failed to match and why. A matched study
// whose balance table is not read is worth no more than the base rate it
// replaced.

#include <gm-core/error.hpp>

#include <cstddef>
#include <string>
#include <vector>

namespace gm::signals {

/// One unit available for matching. `stratum` is an EXACT-match key -
/// nothing is ever matched across it. In the gate it is "date|sector",
/// which forces same-day comparison (so market-wide moves affect both
/// arms identically) and same-sector comparison (so the covariate
/// distance is not asked to stand in for industry).
struct MatchUnit {
    std::string stratum;
    std::vector<double> covariates;  // same length for every unit
    bool treated{};
    std::size_t id{};  // the caller's own row index, handed back in pairs
};

struct MatchedPair {
    std::size_t treated_id{};
    std::size_t control_id{};
    double distance{};  // standardized covariate distance, in pooled SDs
};

/// Why a treated unit ended up without a control. Reported separately
/// because they mean different things: a stratum with no controls at all
/// is a coverage problem, whereas a caliper failure means controls
/// existed but none of them actually resembled the treated unit - and
/// silently matching those anyway is how a matched study quietly becomes
/// an unmatched one.
struct MatchReport {
    std::vector<MatchedPair> pairs;

    std::size_t treated_total{};
    std::size_t treated_matched{};
    std::size_t treated_unmatched_no_controls{};  // stratum held no controls
    std::size_t treated_unmatched_exhausted{};    // controls existed, all taken
    std::size_t treated_unmatched_caliper{};      // nearest control too far
    std::size_t controls_available{};

    /// Standardized difference per covariate, (mean_treated -
    /// mean_control) / pooled SD. `before` is over every unit supplied,
    /// `after` over the matched pairs only. The conventional reading is
    /// that |d| < 0.1 is well balanced; a covariate that does not shrink
    /// is one the matching failed on, and the finding should be read
    /// with that in mind rather than in spite of it.
    std::vector<double> standardized_diff_before;
    std::vector<double> standardized_diff_after;

    /// Covariates with zero variance across the supplied units. They
    /// carry no information, are excluded from the distance, and are
    /// named so their exclusion is visible rather than silent.
    std::vector<std::size_t> degenerate_covariates;

    [[nodiscard]] double match_rate() const {
        return treated_total > 0 ? static_cast<double>(treated_matched) / static_cast<double>(treated_total)
                                 : 0.0;
    }
    /// The largest |standardized difference| left after matching - one
    /// number for "did this work at all".
    [[nodiscard]] double worst_balance_after() const;
};

struct MatchOptions {
    /// Maximum acceptable distance, in pooled standard deviations. The
    /// distance is a ROOT-MEAN-SQUARE across covariates, so the caliper
    /// means the same thing whether three covariates are supplied or
    /// eight. 0.25 SD is the conventional choice; loosening it buys
    /// match rate at the cost of comparability, and the balance table
    /// will say so.
    double caliper{0.25};
};

/// Greedy nearest-neighbour matching without replacement, within exact
/// strata, on standardized covariates.
///
/// Fails if the units disagree about how many covariates they have, or
/// if every covariate is degenerate (a "match" on nothing at all is not
/// a match, and returning one would be worse than returning an error).
/// An empty input is not an error: it yields an empty report.
[[nodiscard]] Result<MatchReport> match_on_covariates(const std::vector<MatchUnit>& units,
                                                       const MatchOptions& options);

}  // namespace gm::signals
